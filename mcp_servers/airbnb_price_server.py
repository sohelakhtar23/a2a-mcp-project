"""
MCP Server — Real Airbnb Search (Airbnb13 via RapidAPI)
==========================================================
One tool: search_airbnb(location, checkin, checkout, adults) -- calls
Airbnb13's real search (via RapidAPI) and returns a SMALL, cleaned list:
name, price, currency, bedrooms/bathrooms, rating, review count, type,
and the real listing URL.

Needs RAPIDAPI_KEY in its environment -- the airbnb agent passes that in
when it spawns this file as a subprocess. Sign up free at rapidapi.com
and subscribe to the free tier of "Airbnb13" (by 3b-data).
"""

import os

import requests
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("airbnb-price-server")

HOST = "airbnb13.p.rapidapi.com"
SEARCH_URL = f"https://{HOST}/search-location"

# How many real listings to hand back -- capped so the payload (and the
# LLM's context/rate limit) stays sane; already sorted cheapest-first.
MAX_LISTINGS = 8


@mcp.tool()
def search_airbnb(location: str, checkin: str, checkout: str, adults: int = 2) -> dict:
    """
    Search REAL live Airbnb listings and prices for a location and date range.

    Args:
        location: city or area to search, e.g. "Lahore"
        checkin: check-in date in YYYY-MM-DD format
        checkout: check-out date in YYYY-MM-DD format
        adults: number of adult guests
    """
    api_key = os.environ.get("RAPIDAPI_KEY", "")
    if not api_key or api_key == "PUT_YOUR_RAPIDAPI_KEY_HERE":
        return {"ok": False, "error": "No RAPIDAPI_KEY configured -- set it in .env."}

    headers = {"x-rapidapi-host": HOST, "x-rapidapi-key": api_key}
    params = {
        "location": location,
        "checkin": checkin,
        "checkout": checkout,
        "adults": adults,
        "currency": "USD",
    }

    response = requests.get(SEARCH_URL, headers=headers, params=params, timeout=20)
    if response.status_code != 200:
        return {"ok": False, "error": f"Airbnb13 returned {response.status_code}: {response.text[:200]}"}

    raw_results = response.json().get("results") or []

    listings = []
    for r in raw_results:
        price = r.get("price") or {}
        listings.append({
            "name": r.get("name", "Unknown listing"),
            "price_per_night": price.get("rate"),
            "currency": price.get("currency", "USD"),
            "bedrooms": r.get("bedrooms"),
            "bathrooms": r.get("bathrooms"),
            "rating": r.get("rating"),
            "review_count": r.get("reviewsCount"),
            "type": r.get("type"),
            "url": r.get("url"),
        })
    listings.sort(key=lambda x: x["price_per_night"] if x["price_per_night"] is not None else float("inf"))

    return {
        "ok": True,
        "location": location,
        "check_in": checkin,
        "check_out": checkout,
        "total_found": len(listings),
        "listings": listings[:MAX_LISTINGS],
    }


if __name__ == "__main__":
    # Runs over stdio -- the airbnb agent launches this as a subprocess
    # and talks MCP to it, same pattern as flight_price_server.py.
    mcp.run()
