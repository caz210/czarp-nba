# -*- coding: utf-8 -*-
"""
player_fetcher.py
Pulls player-level data needed for the CZarp NBA player impact layer.

Data sources:
  1. NBA Stats API  — on/off splits (NetRtg on vs off floor), minutes, lineup data
  2. NBA Stats API  — player general stats (usage, points, etc.)
  3. Official NBA Injury Report (PDF → parsed)  — who is OUT/QUESTIONABLE today

The player impact layer answers: given who is ACTUALLY playing tonight,
what is each team's projected offensive and defensive efficiency?

Run standalone:  python player_fetcher.py [--league NBA|WNBA] [--season 2024-25]
Output:
  data/nba_player_onoff.csv     — on/off splits per player
  data/nba_player_stats.csv     — per-game stats + minutes + usage
  data/nba_injuries.csv         — today's injury report
"""

import requests
import pandas as pd
import json
import time
import re
from pathlib import Path
from datetime import date, datetime

# Reuse headers from nba_fetcher
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

BASE_URL  = "https://stats.nba.com/stats"
LEAGUE_ID_MAP = {"NBA": "00", "WNBA": "10"}


def _get(endpoint: str, params: dict) -> dict:
    url = f"{BASE_URL}/{endpoint}"
    time.sleep(0.6)
    r = requests.get(url, headers=HEADERS, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def _parse(data: dict, result_set_idx: int = 0) -> pd.DataFrame:
    rs = data["resultSets"][result_set_idx]
    return pd.DataFrame(rs["rowSet"], columns=rs["headers"])


# ── 1. On/Off Splits ──────────────────────────────────────────────────────
def fetch_player_onoff(league: str = "NBA", season: str = "2024-25") -> pd.DataFrame:
    """
    Fetches each player's team offensive/defensive rating WITH them on vs off the floor.
    This is the core of the player impact layer.

    Endpoint: leaguedashplayeronoffdetails
    Key fields per player:
      ON_COURT_PLUS_MINUS     — NetRtg when this player is ON
      OFF_COURT_PLUS_MINUS    — NetRtg when this player is OFF
      ON_COURT_OFF_RATING     — Team OffRtg with player on floor
      ON_COURT_DEF_RATING     — Team DefRtg with player on floor
      OFF_COURT_OFF_RATING    — Team OffRtg with player off floor
      OFF_COURT_DEF_RATING    — Team DefRtg with player off floor
      MINUTES                 — minutes played (used for min_threshold filtering)

    The impact metric we derive:
      off_impact = ON_COURT_OFF_RATING - OFF_COURT_OFF_RATING
      def_impact = ON_COURT_DEF_RATING - OFF_COURT_DEF_RATING  (negative = better D)
      net_impact = on_plus_minus - off_plus_minus  (how much better team is WITH them)
    """
    print(f"  Fetching {league} on/off splits ({season})...")
    data = _get("leaguedashplayeronoffdetails", {
        "LeagueID":   LEAGUE_ID_MAP[league],
        "Season":     season,
        "SeasonType": "Regular Season",
        "PerMode":    "Per100Possessions",
        "PORound":    "0",
        "MeasureType": "Advanced",
        "PlusMinus":   "N",
        "PaceAdjust":  "N",
        "Rank":        "N",
        "Outcome": "", "Location": "", "Month": "0", "SeasonSegment": "",
        "DateFrom": "", "DateTo": "", "OpponentTeamID": "0",
        "VsConference": "", "VsDivision": "", "GameSegment": "",
        "Period": "0", "ShotClockRange": "", "LastNGames": "0",
    })

    on_df  = _parse(data, 0)   # "On Court"
    off_df = _parse(data, 1)   # "Off Court"

    # Merge on PlayerID + TeamID
    on_df  = on_df.rename(columns=lambda c: f"ON_{c}" if c not in ["PLAYER_ID", "TEAM_ID", "PLAYER_NAME", "TEAM_ABBREVIATION", "GP", "MIN"] else c)
    off_df = off_df.rename(columns=lambda c: f"OFF_{c}" if c not in ["PLAYER_ID", "TEAM_ID"] else c)

    merged = on_df.merge(off_df, on=["PLAYER_ID", "TEAM_ID"], how="inner")

    # Derive impact metrics
    if "ON_OFF_RATING" in merged.columns and "OFF_OFF_RATING" in merged.columns:
        merged["off_impact"]  = merged["ON_OFF_RATING"]  - merged["OFF_OFF_RATING"]
        merged["def_impact"]  = merged["ON_DEF_RATING"]  - merged["OFF_DEF_RATING"]
        merged["net_impact"]  = merged["ON_NET_RATING"]  - merged["OFF_NET_RATING"]

    merged = merged.rename(columns={
        "PLAYER_NAME":       "PlayerName",
        "PLAYER_ID":         "PlayerID",
        "TEAM_ID":           "TeamID",
        "TEAM_ABBREVIATION": "TeamAbbr",
        "MIN":               "Minutes",
    })

    # Filter to players with meaningful minutes (avoids noise from garbage time players)
    if "Minutes" in merged.columns:
        merged = merged[merged["Minutes"] >= 8.0]

    print(f"  → On/off data for {len(merged)} players")
    return merged


# ── 2. Player General Stats (Minutes + Usage) ─────────────────────────────
def fetch_player_stats(league: str = "NBA", season: str = "2024-25") -> pd.DataFrame:
    """
    Per-game stats including minutes, usage rate, and efficiency metrics.
    Used to:
      (a) Determine each player's typical minutes share
      (b) Build rotation depth profiles per team
      (c) Project lineup changes from injuries

    Endpoint: leaguedashplayerstats
    Key fields:
      MIN         — average minutes per game
      USG_PCT     — usage rate (% of team possessions used when on floor)
      PIE         — Player Impact Estimate (NBA's composite metric)
      NET_RATING  — team net rating when player is on floor
    """
    print(f"  Fetching {league} player stats ({season})...")
    data = _get("leaguedashplayerstats", {
        "LeagueID":    LEAGUE_ID_MAP[league],
        "Season":      season,
        "SeasonType":  "Regular Season",
        "PerMode":     "PerGame",
        "MeasureType": "Advanced",
        "PlusMinus":   "N",
        "PaceAdjust":  "N",
        "Rank":        "N",
        "PORound": "0",
        "Outcome": "", "Location": "", "Month": "0", "SeasonSegment": "",
        "DateFrom": "", "DateTo": "", "OpponentTeamID": "0",
        "VsConference": "", "VsDivision": "", "GameSegment": "",
        "Period": "0", "ShotClockRange": "", "LastNGames": "0",
        "TwoWay": "0",
    })

    df = _parse(data)
    df = df.rename(columns={
        "PLAYER_NAME":       "PlayerName",
        "PLAYER_ID":         "PlayerID",
        "TEAM_ID":           "TeamID",
        "TEAM_ABBREVIATION": "TeamAbbr",
    })

    # Keep only relevant columns
    keep = ["PlayerID", "PlayerName", "TeamID", "TeamAbbr",
            "GP", "MIN", "USG_PCT", "NET_RATING", "PIE",
            "OFF_RATING", "DEF_RATING"]
    keep = [c for c in keep if c in df.columns]
    df   = df[keep]

    # Compute minutes share per team (what % of available minutes does each player get)
    team_total = df.groupby("TeamID")["MIN"].sum().rename("TeamTotalMIN")
    df = df.merge(team_total, on="TeamID")
    df["MinShare"] = df["MIN"] / df["TeamTotalMIN"]   # 0-1, sums to 1.0 per team

    print(f"  → Stats loaded for {len(df)} players")
    return df


# ── 3. Injury Report Parser ───────────────────────────────────────────────
def fetch_injury_report(league: str = "NBA") -> pd.DataFrame:
    """
    Scrapes the official NBA injury report.

    Source:
      NBA: https://ak-static.cms.nba.com/referee/injury/Injury-Report_{date}_{time}.pdf
           The latest report is always linked at:
           https://www.nba.com/news/injury-report

    WNBA: https://stats.wnba.com/js/data/playermovement/WNBA_Player_Movement.json
          (player movement / injury data)

    Returns DataFrame:
      PlayerName, TeamAbbr, Status, Reason, GameDate, ReportTime
      Status values: OUT | QUESTIONABLE | PROBABLE | AVAILABLE | GTD (game-time decision)

    NOTE: The PDF parsing requires pdfplumber or pypdf2. For simplicity, this
    implementation fetches the JSON injury feed that ESPN and others expose.
    A more robust implementation would parse the official PDF directly.
    """
    print(f"  Fetching {league} injury report...")

    if league == "WNBA":
        return _fetch_wnba_injuries()

    # NBA: use ESPN injury API (more reliable than NBA's PDF)
    # ESPN injury endpoint - returns structured JSON
    try:
        r = requests.get(
            "https://site.api.espn.com/apis/site/v2/sports/basketball/nba/injuries",
            timeout=15
        )
        r.raise_for_status()
        data = r.json()

        injuries = []
        for team_entry in data.get("injuries", []):
            team_abbr = team_entry.get("team", {}).get("abbreviation", "")
            for player in team_entry.get("injuries", []):
                injuries.append({
                    "PlayerName": player.get("athlete", {}).get("displayName", ""),
                    "PlayerID":   player.get("athlete", {}).get("id", ""),
                    "TeamAbbr":   team_abbr,
                    "Status":     player.get("status", ""),
                    "Reason":     player.get("longComment", player.get("shortComment", "")),
                    "ReportDate": date.today().isoformat(),
                })

        df = pd.DataFrame(injuries)
        if not df.empty:
            # Normalize status field
            df["Status"] = df["Status"].str.upper()
            # Flag as definitely out vs uncertain
            df["IsOut"]   = df["Status"].isin(["OUT", "INACTIVE", "SUSPENDED"])
            df["IsGTD"]   = df["Status"].isin(["QUESTIONABLE", "GTD", "GAME TIME DECISION", "PROBABLE"])
        print(f"  → {len(df)} injury entries")
        return df

    except Exception as e:
        print(f"  Warning: Could not fetch injury report ({e})")
        return pd.DataFrame(columns=["PlayerName", "PlayerID", "TeamAbbr", "Status", "Reason", "IsOut", "IsGTD"])


def _fetch_wnba_injuries() -> pd.DataFrame:
    """WNBA injury data via stats.wnba.com player movement feed."""
    try:
        r = requests.get(
            "https://stats.wnba.com/js/data/playermovement/WNBA_Player_Movement.json",
            headers={**HEADERS, "Host": "stats.wnba.com", "Referer": "https://www.wnba.com/"},
            timeout=15
        )
        r.raise_for_status()
        data = r.json()
        # Parse WNBA injury entries — structure varies, extract what's available
        entries = data.get("InjuryData", data.get("rows", []))
        df = pd.DataFrame(entries)
        if not df.empty:
            df["IsOut"] = df.get("Status", pd.Series()).str.upper().isin(["OUT", "INACTIVE"])
            df["IsGTD"] = df.get("Status", pd.Series()).str.upper().isin(["QUESTIONABLE", "GTD"])
        return df
    except Exception as e:
        print(f"  Warning: WNBA injury fetch failed ({e})")
        return pd.DataFrame(columns=["PlayerName", "TeamAbbr", "Status", "IsOut", "IsGTD"])


# ── 4. Build Team Rotation Profile ───────────────────────────────────────
def build_rotation_profiles(
    player_stats: pd.DataFrame,
    player_onoff: pd.DataFrame,
    injuries: pd.DataFrame,
    min_threshold: float = 8.0,
) -> pd.DataFrame:
    """
    Combines player stats + on/off + injuries into a rotation profile per team.

    For each team, returns:
      - Top 8 players by minutes (standard NBA rotation)
      - Each player's MinShare (projected minutes % tonight)
      - Each player's off_impact / def_impact from on/off splits
      - IsOut / IsGTD flag from injury report

    This is the input to compute_lineup_efficiency().
    """
    # Start with players above minutes threshold
    rotations = player_stats[player_stats["MIN"] >= min_threshold].copy()

    # Merge on/off impact data
    if not player_onoff.empty and "PlayerID" in player_onoff.columns:
        impact_cols = ["PlayerID", "TeamID"]
        for col in ["off_impact", "def_impact", "net_impact"]:
            if col in player_onoff.columns:
                impact_cols.append(col)
        rotations = rotations.merge(player_onoff[impact_cols], on=["PlayerID", "TeamID"], how="left")

    # Merge injury status
    if not injuries.empty and "PlayerName" in injuries.columns:
        injury_cols = ["PlayerName", "TeamAbbr", "Status", "IsOut", "IsGTD"]
        injury_cols = [c for c in injury_cols if c in injuries.columns]
        rotations = rotations.merge(
            injuries[injury_cols],
            on=["PlayerName", "TeamAbbr"] if "TeamAbbr" in rotations.columns else ["PlayerName"],
            how="left"
        )
    else:
        rotations["IsOut"] = False
        rotations["IsGTD"] = False

    rotations["IsOut"] = rotations["IsOut"].fillna(False)
    rotations["IsGTD"] = rotations["IsGTD"].fillna(False)

    # Sort by minutes descending within each team
    rotations = rotations.sort_values(["TeamID", "MIN"], ascending=[True, False])

    print(f"  Built rotation profiles for {rotations['TeamID'].nunique()} teams")
    return rotations


# ── Main ───────────────────────────────────────────────────────────────────
def fetch_all_player_data(
    league: str = "NBA",
    season: str = "2024-25",
    data_dir: str = "data",
) -> dict:
    """Fetch and save all player data. Returns dict of DataFrames."""
    Path(data_dir).mkdir(parents=True, exist_ok=True)
    prefix = league.lower()

    print(f"\nFetching {league} player data for {season}...")

    onoff    = fetch_player_onoff(league, season)
    time.sleep(1)
    stats    = fetch_player_stats(league, season)
    time.sleep(1)
    injuries = fetch_injury_report(league)

    onoff.to_csv(   f"{data_dir}/{prefix}_player_onoff.csv",  index=False)
    stats.to_csv(   f"{data_dir}/{prefix}_player_stats.csv",  index=False)
    injuries.to_csv(f"{data_dir}/{prefix}_injuries.csv",      index=False)
    print(f"  Saved all player data to {data_dir}/")

    rotations = build_rotation_profiles(stats, onoff, injuries)
    rotations.to_csv(f"{data_dir}/{prefix}_rotations.csv", index=False)

    return {
        "player_onoff":  onoff,
        "player_stats":  stats,
        "injuries":      injuries,
        "rotations":     rotations,
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--league",  default="NBA",    choices=["NBA", "WNBA"])
    parser.add_argument("--season",  default="2024-25")
    parser.add_argument("--data_dir", default="data")
    args = parser.parse_args()
    fetch_all_player_data(args.league, args.season, args.data_dir)
    print("\nDone.")
