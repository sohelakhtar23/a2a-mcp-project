"""CLIENT-SIDE TEST MATRIX -- drives the real A2A servers as a client.
Fakes injected ONLY at the LLM + tool boundaries (tests/fakes.py). Everything
else (executor, auth, cards, JSON-RPC/REST routing, task state machine,
multi-turn continuation, artifact production, registry) is REAL + UNMODIFIED.
"""
import importlib, json, sys
import tests.fakes as F
from fastapi.testclient import TestClient

H = {"X-API-Key": "test-secret-key", "A2A-Version": "1.0"}
RESULTS = []
def check(name, cond, detail=""):
    RESULTS.append((name, bool(cond), detail))
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"   [{detail}]" if detail and not cond else ""))

AGENTS = [
    dict(key="weather", brain="a2a_agents.weather.brain", client="weather_mcp", tool="get_weather",
         server="a2a_agents.weather.server", skill="get-weather", artifact="weather-lookup",
         asserts={"city": "Karachi", "temp_max_c": 39.5}),
    dict(key="flight", brain="a2a_agents.flight.brain", client="flight_mcp", tool="search_flights",
         server="a2a_agents.flight.server", skill="book-flight", artifact="flight-search",
         asserts={"route": "LHE -> KHI", "price": "$123.45", "airline": "Fake Air"}),
    dict(key="hotel", brain="a2a_agents.hotel.brain", client="hotel_mcp", tool="search_hotels",
         server="a2a_agents.hotel.server", skill="book-hotel", artifact="hotel-search",
         asserts={"city": "Karachi", "hotel": "Grand Fake Hotel", "price_per_night": "88.00 USD"}),
    dict(key="airbnb", brain="a2a_agents.airbnb.brain", client="airbnb_mcp", tool="search_airbnb",
         server="a2a_agents.airbnb.server", skill="book-airbnb", artifact="airbnb-search",
         asserts={"location": "Lahore", "listing": "Cozy Fake Loft", "price_per_night": "54.00 USD"}),
]

def rpc(client, text, task=None, ctx=None, mid="m1", method="SendMessage"):
    msg = {"role": "ROLE_USER", "parts": [{"text": text}], "messageId": mid}
    if task: msg["taskId"] = task
    if ctx: msg["contextId"] = ctx
    body = {"jsonrpc": "2.0", "id": "1", "method": method, "params": {"message": msg}}
    return client.post("/", json=body, headers=H).json()

def task_of(r): return r.get("result", {}).get("task", {})
def state_of(r): return task_of(r).get("status", {}).get("state")
def artifacts_of(r): return task_of(r).get("artifacts", [])
def reply_of(r): return task_of(r).get("status", {}).get("message", {}).get("parts", [{}])[0].get("text", "")

for cfg in AGENTS:
    print(f"\n===== {cfg['key'].upper()} AGENT =====")
    brain = importlib.import_module(cfg["brain"])
    brain.get_model = F.fake_model_for(cfg["tool"])
    setattr(getattr(brain, cfg["client"]), "get_tools", F.fake_tool_for(cfg["tool"]))
    server = importlib.import_module(cfg["server"])

    with TestClient(server.app) as client:
        # 1. Agent card (public, no auth)
        c = client.get("/.well-known/agent-card.json")
        cj = c.json() if c.status_code == 200 else {}
        check(f"{cfg['key']}: agent card 200 + correct skill", c.status_code == 200 and cfg["skill"] in [s.get("id") for s in cj.get("skills", [])])
        check(f"{cfg['key']}: card declares apiKey security scheme", "apiKeyAuth" in (cj.get("securitySchemes") or {}))

        # 2. Auth enforcement
        no_key = client.post("/", json={"jsonrpc":"2.0","id":"1","method":"SendMessage","params":{"message":{"role":"ROLE_USER","parts":[{"text":"hi"}],"messageId":"x"}}}, headers={"A2A-Version":"1.0"})
        check(f"{cfg['key']}: missing API key -> 401", no_key.status_code == 401, f"got {no_key.status_code}")
        bad_key = client.post("/", json={"jsonrpc":"2.0","id":"1","method":"SendMessage","params":{"message":{"role":"ROLE_USER","parts":[{"text":"hi"}],"messageId":"x"}}}, headers={"A2A-Version":"1.0","X-API-Key":"WRONG"})
        check(f"{cfg['key']}: wrong API key -> 401", bad_key.status_code == 401, f"got {bad_key.status_code}")

        # 3. Complete request -> COMPLETED + artifact with ground-truth data
        r = rpc(client, "complete request for 2026-08-10")
        check(f"{cfg['key']}: complete req -> TASK_STATE_COMPLETED", state_of(r) == "TASK_STATE_COMPLETED", str(state_of(r)))
        arts = artifacts_of(r)
        check(f"{cfg['key']}: exactly one artifact named '{cfg['artifact']}'", len(arts) == 1 and arts[0].get("name") == cfg["artifact"], str([a.get('name') for a in arts]))
        data = arts[0]["parts"][0]["data"] if arts else {}
        ok = all(data.get(k) == v for k, v in cfg["asserts"].items())
        check(f"{cfg['key']}: artifact carries GROUND-TRUTH tool data (not model prose)", ok, json.dumps({k:data.get(k) for k in cfg['asserts']}))

        # 4. Incomplete request -> INPUT_REQUIRED, no artifact
        r2 = rpc(client, "I need help please", mid="i1")   # no date -> fake asks a question
        check(f"{cfg['key']}: incomplete req -> TASK_STATE_INPUT_REQUIRED", state_of(r2) == "TASK_STATE_INPUT_REQUIRED", str(state_of(r2)))
        check(f"{cfg['key']}: incomplete req produces NO artifact", len(artifacts_of(r2)) == 0)
        check(f"{cfg['key']}: incomplete req returns a non-empty clarifying reply", len(reply_of(r2)) > 0)

        # 5. Multi-turn continuation: reuse taskId+contextId -> COMPLETED
        t, cx = task_of(r2).get("id"), task_of(r2).get("contextId")
        r3 = rpc(client, "here it is for 2026-08-10", task=t, ctx=cx, mid="i2")
        check(f"{cfg['key']}: multi-turn continuation -> COMPLETED", state_of(r3) == "TASK_STATE_COMPLETED", str(state_of(r3)))
        check(f"{cfg['key']}: continuation keeps SAME task id", task_of(r3).get("id") == t, f"{task_of(r3).get('id')} vs {t}")
        check(f"{cfg['key']}: continuation now yields an artifact", len(artifacts_of(r3)) == 1)

        # 5b. Conversation memory is namespaced by AUTHENTICATED CALLER, not by
        # the client-supplied taskId alone. The brain's checkpointer is keyed
        # only by thread_id, so if the raw taskId were the key, anyone who
        # learned another caller's taskId could resume their conversation and
        # have the model replay their details back. Assert the memory the
        # executor hands the brain is caller-scoped.
        import common.executor as EX

        class _FakeUser:
            def __init__(self, name, auth=True): self.user_name, self.is_authenticated = name, auth

        class _FakeCtx:
            def __init__(self, user): self.call_context = type("C", (), {"user": user})()

        k_alice = EX._memory_key(_FakeCtx(_FakeUser("alice")), "task-123")
        k_bob = EX._memory_key(_FakeCtx(_FakeUser("bob")), "task-123")
        check(f"{cfg['key']}: same taskId under different callers -> different memory keys",
              k_alice != k_bob, f"{k_alice} vs {k_bob}")
        check(f"{cfg['key']}: same caller + same taskId -> stable memory key (multi-turn still works)",
              k_alice == EX._memory_key(_FakeCtx(_FakeUser("alice")), "task-123"))
        check(f"{cfg['key']}: memory key is not the bare client-supplied taskId",
              k_alice != "task-123", k_alice)

        # 6. REST binding
        rest = client.post("/message:send", json={"message":{"role":"ROLE_USER","parts":[{"text":"rest req for 2026-08-10"}],"messageId":"r1"}}, headers=H)
        rj = rest.json()
        rest_state = rj.get("task", {}).get("status", {}).get("state") or rj.get("result", {}).get("task", {}).get("status", {}).get("state")
        check(f"{cfg['key']}: REST /message:send -> COMPLETED", rest.status_code == 200 and rest_state == "TASK_STATE_COMPLETED", f"{rest.status_code}/{rest_state}")

        # 7. Malformed protocol
        unknown = rpc(client, "x", method="TotallyBogusMethod")
        check(f"{cfg['key']}: unknown method -> JSON-RPC -32601", unknown.get("error", {}).get("code") == -32601)
        badparams = client.post("/", json={"jsonrpc":"2.0","id":"1","method":"SendMessage","params":{"message":{"role":"user","parts":[{"text":"x"}],"messageId":"x"}}}, headers=H).json()
        check(f"{cfg['key']}: invalid params (bad role enum) -> -32602", badparams.get("error", {}).get("code") == -32602)

# ---- REGISTRY (catalog must be running on :9000; agents registered during lifespans above) ----
print("\n===== AGENT CATALOG (registry) =====")
import httpx
try:
    agents = httpx.get("http://localhost:9000/agents", timeout=3).json()
    check("registry: all 4 agents registered", len(agents) == 4, f"found {len(agents)}")
    s1 = httpx.get("http://localhost:9000/agents/search", params={"skill":"book-flight"}, timeout=3).json()
    check("registry: search skill=book-flight -> 1 match", len(s1.get("matches", [])) == 1, str(len(s1.get('matches',[]))))
    s0 = httpx.get("http://localhost:9000/agents/search", params={"skill":"does-not-exist"}, timeout=3).json()
    check("registry: search unknown skill -> 0 matches (graceful)", len(s0.get("matches", [])) == 0)
    # /register requires the shared key -- send it, so this exercises the
    # name check rather than stopping at auth.
    reg_headers = {"X-API-Key": H["X-API-Key"]}
    bad = httpx.post("http://localhost:9000/register", json={"no_name": True}, headers=reg_headers, timeout=3)
    check("registry: register without name -> 400", bad.status_code == 400, f"got {bad.status_code}")

    noauth = httpx.post("http://localhost:9000/register", json={"name": "x", "url": "http://evil/"}, timeout=3)
    check("registry: register without API key -> 401", noauth.status_code == 401, f"got {noauth.status_code}")

    # Name-takeover: re-registering an existing name at a DIFFERENT url is
    # rejected even with a valid key, so a leaked key can't silently
    # repoint a real agent at an attacker's address.
    steal = httpx.post("http://localhost:9000/register",
                       json={"name": "flight-booking-agent", "url": "http://evil/"},
                       headers=reg_headers, timeout=3)
    check("registry: hijacking a registered name -> 409", steal.status_code == 409, f"got {steal.status_code}")
except Exception as e:
    check("registry: catalog reachable on :9000", False, str(e)[:80])

# ---- SUMMARY ----
p = sum(1 for _, ok, _ in RESULTS if ok); n = len(RESULTS)
print(f"\n{'='*60}\nTOTAL: {p}/{n} passed" + ("" if p == n else f"  ({n-p} FAILED)"))
for name, ok, detail in RESULTS:
    if not ok: print(f"  FAILED: {name}   [{detail}]")
sys.exit(0 if p == n else 1)
