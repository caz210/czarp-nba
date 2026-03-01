# -*- coding: utf-8 -*-
"""
odds_fetcher.py  —  CZarp NBA/WNBA Vegas Lines
=================================================
Drop-in replacement for the CBB odds_fetcher.py, adapted for NBA.

CURRENT STATUS: Stub — returns empty DataFrame.
To activate, replace _fetch_lines_from_source() with your odds provider.

Supported providers (pick one):
  Option A — The Odds API (free tier: 500 requests/month)
             https://the-odds-api.com  — ~$5/mo for daily use
             Set env var: ODDS_API_KEY=your_key

  Option B — DraftKings/FanDuel scraper (see commented code below)

  Option C — Copy your CBB odds_fetcher.py here and adapt team names

The match_vegas_to_game() function below is what app_nba.py calls.
It joins by team name using the NBA_TO_ODDS mapping at the bottom of this file.
"""

import os
import time
import requests
import pandas as pd
from datetime import date, datetime


# ── Config ────────────────────────────────────────────────────────────────────
ODDS_API_KEY  = os.environ.get("ODDS_API_KEY", "")   # Set in Streamlit secrets or .env
ODDS_API_BASE = "https://api.the-odds-api.com/v4"
SPORT_NBA     = "basketball_nba"
SPORT_WNBA    = "basketball_wnba"

# Cache last fetch time
_last_fetched: str = ""


def get_odds_last_fetched() -> str:
    return _last_fetched


# ── Main fetch ────────────────────────────────────────────────────────────────
def fetch_vegas_lines(sport: str = SPORT_NBA) -> pd.DataFrame:
    """
    Fetch today's NBA Vegas lines.
    Returns DataFrame with columns: team1, team2, spread, total, fav

    To activate: set ODDS_API_KEY environment variable.
    Free at https://the-odds-api.com — 500 req/month is enough for daily use.
    """
    global _last_fetched

    if not ODDS_API_KEY:
        # No key set — return empty. App still runs, just without edge scoring.
        print("  odds_fetcher: ODDS_API_KEY not set — returning empty lines")
        return pd.DataFrame(columns=["team1", "team2", "spread", "total", "fav"])

    try:
        lines = _fetch_from_odds_api(sport)
        _last_fetched = datetime.now().strftime("%I:%M %p")
        print(f"  Fetched {len(lines)} {sport} lines from The Odds API")
        return pd.DataFrame(lines) if lines else pd.DataFrame(columns=["team1", "team2", "spread", "total", "fav"])
    except Exception as e:
        print(f"  odds_fetcher error: {e}")
        return pd.DataFrame(columns=["team1", "team2", "spread", "total", "fav"])


def _fetch_from_odds_api(sport: str) -> list[dict]:
    """
    Calls The Odds API for NBA spreads and totals.
    Docs: https://the-odds-api.com/liveapi/guides/v4/#get-odds
    """
    url = f"{ODDS_API_BASE}/sports/{sport}/odds"
    params = {
        "apiKey":   ODDS_API_KEY,
        "regions":  "us",
        "markets":  "spreads,totals",
        "oddsFormat": "american",
        "dateFormat": "iso",
    }
    r = requests.get(url, params=params, timeout=15)
    r.raise_for_status()

    data   = r.json()
    lines  = []
    today  = date.today().isoformat()

    for event in data:
        # Filter to today's games
        commence = event.get("commence_time", "")
        if today not in commence:
            continue

        home  = event.get("home_team", "")
        away  = event.get("away_team", "")
        spread = None
        total  = None
        fav    = None

        # Parse bookmaker lines (use first available book — DraftKings preferred)
        preferred_books = ["draftkings", "fanduel", "betmgm", "pointsbet"]
        books = event.get("bookmakers", [])
        books_sorted = sorted(books, key=lambda b: preferred_books.index(b["key"]) if b["key"] in preferred_books else 99)

        for book in books_sorted:
            for market in book.get("markets", []):
                if market["key"] == "spreads" and spread is None:
                    for outcome in market.get("outcomes", []):
                        if outcome["name"] == home:
                            spread = outcome.get("point", 0)   # home spread (negative = home fav)
                            fav    = home if spread < 0 else away
                            break
                if market["key"] == "totals" and total is None:
                    if market.get("outcomes"):
                        total = market["outcomes"][0].get("point")
            if spread is not None and total is not None:
                break

        if spread is not None:
            lines.append({
                "team1":  _normalize_nba_name(home),   # home
                "team2":  _normalize_nba_name(away),   # away
                "spread": spread,
                "total":  total,
                "fav":    _normalize_nba_name(fav) if fav else None,
            })

    return lines


# ── Vegas ↔ Model team name matching ─────────────────────────────────────────
def match_vegas_to_game(r: dict, vegas_df: pd.DataFrame) -> dict:
    """
    Left-join Vegas spread to a project_game() result dict.
    Tries exact match first, then partial match via NBA_TO_ODDS map.
    """
    r.setdefault("vegas_spread", None)
    r.setdefault("vegas_total",  None)
    r.setdefault("vegas_fav",    None)
    r.setdefault("edge_score",   None)
    r.setdefault("spread_edge",  None)
    r.setdefault("sides_agree",  None)

    if vegas_df is None or vegas_df.empty:
        return r

    t1 = r["team1"].lower()
    t2 = r["team2"].lower()

    # Try to find a matching row
    matched = None
    for _, row in vegas_df.iterrows():
        v1 = str(row.get("team1", "")).lower()
        v2 = str(row.get("team2", "")).lower()

        # Exact or substring match
        if (t1 in v1 or v1 in t1) and (t2 in v2 or v2 in t2):
            matched = row
            break
        if (t2 in v1 or v1 in t2) and (t1 in v2 or v2 in t1):
            # Flipped — home/away reversed
            matched = row
            break

    if matched is None:
        return r

    vs = matched.get("spread")
    vt = matched.get("total")

    r["vegas_spread"] = vs
    r["vegas_total"]  = vt
    r["vegas_fav"]    = matched.get("fav")

    if vs is not None:
        spread_edge        = r["spread"] - vs
        r["spread_edge"]   = round(spread_edge, 2)
        r["edge_score"]    = round(abs(spread_edge) / 10, 4)
        my_fav             = r["team1"] if r["spread"] > 0 else r["team2"]
        r["sides_agree"]   = (my_fav == r["vegas_fav"])

    return r


# ── Name normalization ────────────────────────────────────────────────────────
# Maps odds-provider team names → model team names
# Extend this as needed based on what your odds source returns
NBA_TO_ODDS = {
    "Atlanta Hawks":          "Atlanta Hawks",
    "Boston Celtics":         "Boston Celtics",
    "Brooklyn Nets":          "Brooklyn Nets",
    "Charlotte Hornets":      "Charlotte Hornets",
    "Chicago Bulls":          "Chicago Bulls",
    "Cleveland Cavaliers":    "Cleveland Cavaliers",
    "Dallas Mavericks":       "Dallas Mavericks",
    "Denver Nuggets":         "Denver Nuggets",
    "Detroit Pistons":        "Detroit Pistons",
    "Golden State Warriors":  "Golden State Warriors",
    "Houston Rockets":        "Houston Rockets",
    "Indiana Pacers":         "Indiana Pacers",
    "LA Clippers":            "LA Clippers",
    "Los Angeles Lakers":     "Los Angeles Lakers",
    "Memphis Grizzlies":      "Memphis Grizzlies",
    "Miami Heat":             "Miami Heat",
    "Milwaukee Bucks":        "Milwaukee Bucks",
    "Minnesota Timberwolves": "Minnesota Timberwolves",
    "New Orleans Pelicans":   "New Orleans Pelicans",
    "New York Knicks":        "New York Knicks",
    "Oklahoma City Thunder":  "Oklahoma City Thunder",
    "Orlando Magic":          "Orlando Magic",
    "Philadelphia 76ers":     "Philadelphia 76ers",
    "Phoenix Suns":           "Phoenix Suns",
    "Portland Trail Blazers": "Portland Trail Blazers",
    "Sacramento Kings":       "Sacramento Kings",
    "San Antonio Spurs":      "San Antonio Spurs",
    "Toronto Raptors":        "Toronto Raptors",
    "Utah Jazz":              "Utah Jazz",
    "Washington Wizards":     "Washington Wizards",
    # WNBA
    "Las Vegas Aces":         "Las Vegas Aces",
    "New York Liberty":       "New York Liberty",
    "Seattle Storm":          "Seattle Storm",
    "Chicago Sky":            "Chicago Sky",
    "Connecticut Sun":        "Connecticut Sun",
    "Dallas Wings":           "Dallas Wings",
    "Indiana Fever":          "Indiana Fever",
    "Minnesota Lynx":         "Minnesota Lynx",
    "Phoenix Mercury":        "Phoenix Mercury",
    "Washington Mystics":     "Washington Mystics",
    "Atlanta Dream":          "Atlanta Dream",
    "Golden State Valkyries": "Golden State Valkyries",
}


def _normalize_nba_name(name: str) -> str:
    """Map odds-provider team name back to model name."""
    if not name:
        return name
    # Direct lookup
    if name in NBA_TO_ODDS:
        return NBA_TO_ODDS[name]
    # Partial match (odds APIs sometimes use city only: "Los Angeles" → "Los Angeles Lakers")
    name_lower = name.lower()
    for odds_name, model_name in NBA_TO_ODDS.items():
        if name_lower in odds_name.lower() or odds_name.lower() in name_lower:
            return model_name
    return name  # Return as-is if no match found
