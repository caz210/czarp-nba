# -*- coding: utf-8 -*-
"""
nba_fetcher.py
Pulls team-level efficiency, four factors, and pace from the NBA Stats API.
No API key required — NBA Stats API is public. Headers are required to avoid 403.

Endpoints used:
  leaguedashteamstats  → AdjOE proxy, pace, four factors (eFG%, TOV%, ORB%, FT/FGA)
  leaguedashteamstats  → Defensive four factors (opponent stats)

Run standalone:  python nba_fetcher.py [--league NBA|WNBA] [--season 2024-25]
Output:          data/nba_ratings.csv, data/nba_four_factors.csv
"""

import requests
import pandas as pd
import json
import time
import argparse
from pathlib import Path

# ── NBA Stats API config ────────────────────────────────────────────────────
BASE_URL = "https://stats.nba.com/stats"

# These headers are REQUIRED — NBA Stats returns 403 without Referer + User-Agent
HEADERS = {
    "Accept":          "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Connection":      "keep-alive",
    "Host":            "stats.nba.com",
    "Origin":          "https://www.nba.com",
    "Referer":         "https://www.nba.com/",
    "User-Agent":      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "x-nba-stats-origin": "stats",
    "x-nba-stats-token":  "true",
}

LEAGUE_ID_MAP = {
    "NBA":  "00",
    "WNBA": "10",
}

# Current season strings
CURRENT_NBA_SEASON  = "2024-25"
CURRENT_WNBA_SEASON = "2024"

# ── Low-level requester ────────────────────────────────────────────────────
def _get(endpoint: str, params: dict, retries: int = 3) -> dict:
    """GET with retry logic and polite rate limiting."""
    url = f"{BASE_URL}/{endpoint}"
    for attempt in range(retries):
        try:
            time.sleep(0.6)   # NBA Stats rate limit — don't remove this
            r = requests.get(url, headers=HEADERS, params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except requests.exceptions.HTTPError as e:
            if r.status_code == 429:
                print(f"  Rate limited, waiting 10s... (attempt {attempt+1})")
                time.sleep(10)
            else:
                raise
        except requests.exceptions.RequestException as e:
            if attempt < retries - 1:
                print(f"  Request failed ({e}), retrying...")
                time.sleep(3)
            else:
                raise
    raise RuntimeError(f"Failed to fetch {endpoint} after {retries} attempts")


def _parse_response(data: dict) -> pd.DataFrame:
    """Convert NBA Stats API resultSets format to DataFrame."""
    result_set = data["resultSets"][0]
    headers    = result_set["headers"]
    rows       = result_set["rowSet"]
    return pd.DataFrame(rows, columns=headers)


# ── Team Ratings (Offensive / Defensive Efficiency + Pace) ────────────────
def fetch_team_ratings(league: str = "NBA", season: str = CURRENT_NBA_SEASON) -> pd.DataFrame:
    """
    Fetches per-100-possession offensive and defensive ratings for all teams.

    NBA Stats endpoint: leaguedashteamstats
    MeasureType=Advanced → gives OffRtg, DefRtg, Pace, NetRtg

    Returns DataFrame with columns:
      TeamID, TeamName, GP, W, L, WinPct,
      OffRtg, DefRtg, NetRtg, Pace, PacePerPoss,
      ASTRatio, TOVRatio,
      -- mapped to CZarp model fields:
      AdjOE  = OffRtg (not opponent-adjusted, but sufficient proxy)
      AdjDE  = DefRtg
      AdjTempo = Pace
    """
    print(f"  Fetching {league} team ratings ({season})...")
    data = _get("leaguedashteamstats", {
        "MeasureType":      "Advanced",
        "PerMode":          "PerGame",
        "PlusMinus":        "N",
        "PaceAdjust":       "N",
        "Rank":             "N",
        "LeagueID":         LEAGUE_ID_MAP[league],
        "Season":           season,
        "SeasonType":       "Regular Season",
        "PORound":          "0",
        "Outcome":          "",
        "Location":         "",
        "Month":            "0",
        "SeasonSegment":    "",
        "DateFrom":         "",
        "DateTo":           "",
        "OpponentTeamID":   "0",
        "VsConference":     "",
        "VsDivision":       "",
        "GameSegment":      "",
        "Period":           "0",
        "ShotClockRange":   "",
        "LastNGames":       "0",
        "GameScope":        "",
        "PlayerExperience": "",
        "PlayerPosition":   "",
        "StarterBench":     "",
        "TwoWay":           "0",
    })

    df = _parse_response(data)

    # Rename to CZarp model field names
    df = df.rename(columns={
        "TEAM_NAME": "TeamName",
        "TEAM_ID":   "TeamID",
        "OFF_RATING": "AdjOE",
        "DEF_RATING": "AdjDE",
        "NET_RATING": "NetRtg",
        "PACE":       "AdjTempo",
        "W_PCT":      "WinPct",
    })

    # Rank by NetRtg (descending = best team = rank 1)
    df = df.sort_values("NetRtg", ascending=False).reset_index(drop=True)
    df["RankAdjEM"] = df.index + 1   # Mirrors KenPom RankAdjEM usage

    print(f"  → {len(df)} teams loaded")
    return df[[
        "TeamID", "TeamName", "RankAdjEM", "AdjOE", "AdjDE", "NetRtg",
        "AdjTempo", "WinPct", "GP", "W", "L"
    ]]


# ── Four Factors ──────────────────────────────────────────────────────────
def fetch_four_factors(league: str = "NBA", season: str = CURRENT_NBA_SEASON) -> pd.DataFrame:
    """
    Fetches offensive and defensive four factors for all teams.

    NBA Stats endpoint: leaguedashteamstats with MeasureType=Four Factors

    Four Factors (Dean Oliver):
      EFG_PCT    = Effective FG%   (accounts for 3pt value)
      TOV_PCT    = Turnover %      (turnovers per 100 plays)
      OREB_PCT   = Offensive Rebound %
      FTA_RATE   = FT Rate         (FTA/FGA)

    Defensive equivalents are opponent's four factors against this team.

    Returns merged offense + defense four factors.
    """
    print(f"  Fetching {league} offensive four factors...")
    off_data = _get("leaguedashteamstats", {
        "MeasureType":   "Four Factors",
        "PerMode":       "PerGame",
        "LeagueID":      LEAGUE_ID_MAP[league],
        "Season":        season,
        "SeasonType":    "Regular Season",
        "PORound":       "0",
        "PaceAdjust":    "N",
        "PlusMinus":     "N",
        "Rank":          "N",
        "Outcome": "", "Location": "", "Month": "0", "SeasonSegment": "",
        "DateFrom": "", "DateTo": "", "OpponentTeamID": "0",
        "VsConference": "", "VsDivision": "", "GameSegment": "",
        "Period": "0", "ShotClockRange": "", "LastNGames": "0",
    })
    off_df = _parse_response(off_data)

    print(f"  Fetching {league} defensive four factors (opponent stats)...")
    def_data = _get("leaguedashteamstats", {
        "MeasureType":   "Four Factors",
        "PerMode":       "PerGame",
        "LeagueID":      LEAGUE_ID_MAP[league],
        "Season":        season,
        "SeasonType":    "Regular Season",
        "PORound":       "0",
        "PaceAdjust":    "N",
        "PlusMinus":     "N",
        "Rank":          "N",
        "VsConference": "", "VsDivision": "", "GameSegment": "",
        "Outcome": "L",   # ← trick: use opponent view via L/W split is NOT available
        # Instead we use LeagueID opponent data endpoint below
        "Location": "", "Month": "0", "SeasonSegment": "",
        "DateFrom": "", "DateTo": "", "OpponentTeamID": "0",
        "Period": "0", "ShotClockRange": "", "LastNGames": "0",
    })
    # NOTE: NBA Stats doesn't have a single "opponent four factors" endpoint.
    # Best approach: use leaguedashteamstats with MeasureType=Opponent
    opp_data = _get("leaguedashteamstats", {
        "MeasureType":   "Opponent",
        "PerMode":       "Per100Possessions",
        "LeagueID":      LEAGUE_ID_MAP[league],
        "Season":        season,
        "SeasonType":    "Regular Season",
        "PORound":       "0",
        "PaceAdjust":    "N",
        "PlusMinus":     "N",
        "Rank":          "N",
        "Outcome": "", "Location": "", "Month": "0", "SeasonSegment": "",
        "DateFrom": "", "DateTo": "", "OpponentTeamID": "0",
        "VsConference": "", "VsDivision": "", "GameSegment": "",
        "Period": "0", "ShotClockRange": "", "LastNGames": "0",
    })
    opp_df = _parse_response(opp_data)

    # Rename offense columns to CZarp field names
    off_df = off_df.rename(columns={
        "TEAM_NAME": "TeamName",
        "TEAM_ID":   "TeamID",
        "EFG_PCT":   "EFG_Pct",       # Effective FG% offense
        "TOV_PCT":   "TO_Pct",         # Turnover % offense  (maps to CBB TO_Pct)
        "OREB_PCT":  "OR_Pct",         # Offensive rebound %  (maps to CBB OR_Pct)
        "FTA_RATE":  "FT_Rate",        # FT rate offense      (maps to CBB FT_Rate)
    })

    # Rename opponent/defense columns
    opp_df = opp_df.rename(columns={
        "TEAM_ID":    "TeamID",
        "OPP_EFG_PCT": "DEFG_Pct",    # Opponent eFG% allowed
        "OPP_TOV_PCT": "DTO_Pct",     # Opponent TO% forced   (maps to CBB DTO_Pct)
        "OPP_OREB_PCT": "DOR_Pct",    # Opp OReb% allowed     (maps to CBB DOR_Pct)
        "OPP_FTA_RATE": "DFT_Rate",   # Opp FT rate allowed   (maps to CBB DFT_Rate)
    })

    # Merge on TeamID
    cols_off = ["TeamID", "TeamName", "EFG_Pct", "TO_Pct", "OR_Pct", "FT_Rate"]
    cols_def = ["TeamID", "DEFG_Pct", "DTO_Pct", "DOR_Pct", "DFT_Rate"]

    # Filter to available columns (column names vary by season/endpoint version)
    cols_off = [c for c in cols_off if c in off_df.columns]
    cols_def = [c for c in cols_def if c in opp_df.columns]

    merged = off_df[cols_off].merge(opp_df[cols_def], on="TeamID", how="left")
    print(f"  → Four factors loaded for {len(merged)} teams")
    return merged


# ── Schedule (Today's Games) ───────────────────────────────────────────────
def fetch_todays_games(league: str = "NBA", date_str: str = None) -> list[dict]:
    """
    Fetches today's scheduled games.
    date_str: "MM/DD/YYYY" format, defaults to today.

    Returns list of dicts:
      { team1, team2, team1_id, team2_id, game_id, game_time, neutral_site }
    """
    from datetime import date
    if date_str is None:
        date_str = date.today().strftime("%m/%d/%Y")

    print(f"  Fetching {league} schedule for {date_str}...")
    data = _get("scoreboardv2", {
        "GameDate":  date_str,
        "LeagueID":  LEAGUE_ID_MAP[league],
        "DayOffset": "0",
    })

    games = []
    try:
        # scoreboardv2 has multiple resultSets; GameHeader is index 0
        game_header = data["resultSets"][0]
        headers = game_header["headers"]
        rows    = game_header["rowSet"]
        df      = pd.DataFrame(rows, columns=headers)

        for _, row in df.iterrows():
            games.append({
                "game_id":      row.get("GAME_ID"),
                "game_time":    row.get("GAME_STATUS_TEXT", ""),
                "team1":        row.get("HOME_TEAM_ABBREVIATION", ""),
                "team2":        row.get("VISITOR_TEAM_ABBREVIATION", ""),
                "team1_id":     row.get("HOME_TEAM_ID"),
                "team2_id":     row.get("VISITOR_TEAM_ID"),
                "neutral_site": False,  # NBA rarely plays neutrals (all-star, etc.)
                "arena":        row.get("ARENA_NAME", ""),
                "city":         row.get("ARENA_CITY", ""),
            })
    except (KeyError, IndexError) as e:
        print(f"  Warning: Could not parse schedule ({e})")

    print(f"  → {len(games)} games found for {date_str}")
    return games


# ── Main ────────────────────────────────────────────────────────────────────
def fetch_all(league: str = "NBA", season: str = None, data_dir: str = "data") -> dict:
    """
    Fetch all team data needed for the model. Saves CSVs and returns DataFrames.
    """
    if season is None:
        season = CURRENT_NBA_SEASON if league == "NBA" else CURRENT_WNBA_SEASON

    Path(data_dir).mkdir(parents=True, exist_ok=True)
    prefix = league.lower()

    print(f"\nFetching {league} data for {season}...")

    ratings = fetch_team_ratings(league, season)
    ratings.to_csv(f"{data_dir}/{prefix}_ratings.csv", index=False)
    print(f"  Saved {data_dir}/{prefix}_ratings.csv")

    time.sleep(1)

    ff = fetch_four_factors(league, season)
    ff.to_csv(f"{data_dir}/{prefix}_four_factors.csv", index=False)
    print(f"  Saved {data_dir}/{prefix}_four_factors.csv")

    return {"ratings": ratings, "four_factors": ff}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--league",  default="NBA",     choices=["NBA", "WNBA"])
    parser.add_argument("--season",  default=None)
    parser.add_argument("--data_dir", default="data")
    args = parser.parse_args()

    fetch_all(args.league, args.season, args.data_dir)
    print("\nDone.")
