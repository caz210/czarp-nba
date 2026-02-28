# -*- coding: utf-8 -*-
"""
nba_model.py
CZarp NBA/WNBA Game Projection Model

Architecture mirrors the CBB model (model.py) exactly:
  pace → PPP → adjusted possessions → base score → adjustments → final score

Key difference from CBB:
  PLAYER IMPACT LAYER between team efficiency and final score.
  Season-average team efficiency is adjusted by who is ACTUALLY playing tonight
  using on/off splits. A team missing their best player drops in both AdjOE and AdjDE.

Formula chain:
  1. Projected pace (same as CBB)
  2. Lineup-adjusted PPP  ← NEW vs CBB
     base_ppp = (AdjOE + opp_AdjDE) / 2 / 100
     lineup_adj = compute_lineup_efficiency_adjustment(team, active_players)
     adj_ppp = base_ppp + lineup_adj
  3. Four-factor possession adjustments (TO, REB — same averaged formulas as CBB)
  4. FT display only (same as CBB fix)
  5. HCA (NBA home court = 2.5 pts, smaller than CBB's 3.5)
  6. Final score = mround(adj_ppp * adj_poss, 0.5)
"""

import pandas as pd
import numpy as np
from typing import Optional


# ── Constants ─────────────────────────────────────────────────────────────
NBA_HCA   = 2.5    # NBA home court advantage (KenPom equivalent for NBA ≈ 2.5 pts)
WNBA_HCA  = 2.0    # WNBA is slightly smaller — shorter season, more road-neutral venues
MIN_THRESHOLD = 8  # Minimum minutes/game to include player in rotation profile


# ── Data Loader ──────────────────────────────────────────────────────────
def load_data(data_dir: str = "data", league: str = "NBA") -> dict:
    prefix = league.lower()
    data = {
        "ratings":       pd.read_csv(f"{data_dir}/{prefix}_ratings.csv"),
        "four_factors":  pd.read_csv(f"{data_dir}/{prefix}_four_factors.csv"),
    }
    # Player data — optional, model degrades gracefully to team-only if missing
    for key, fname in [
        ("rotations",    f"{prefix}_rotations.csv"),
        ("player_onoff", f"{prefix}_player_onoff.csv"),
        ("injuries",     f"{prefix}_injuries.csv"),
    ]:
        try:
            data[key] = pd.read_csv(f"{data_dir}/{fname}")
            print(f"    {fname} loaded ({len(data[key])} rows)")
        except FileNotFoundError:
            print(f"    {fname} not found — {key} layer will be skipped")
            data[key] = pd.DataFrame()

    return data


# ── Team lookup ────────────────────────────────────────────────────────────
NBA_NAME_MAP = {
    # Common abbreviation → full name mappings
    "GSW": "Golden State Warriors",
    "LAL": "Los Angeles Lakers",
    "LAC": "LA Clippers",
    "NYK": "New York Knicks",
    "BKN": "Brooklyn Nets",
    "NOP": "New Orleans Pelicans",
    "OKC": "Oklahoma City Thunder",
    "PHX": "Phoenix Suns",
    "SAS": "San Antonio Spurs",
    "UTA": "Utah Jazz",
    # WNBA
    "LV":  "Las Vegas Aces",
    "NY":  "New York Liberty",
    "SEA": "Seattle Storm",
    "CHI": "Chicago Sky",
    "CON": "Connecticut Sun",
    "DAL": "Dallas Wings",
    "IND": "Indiana Fever",
    "MIN": "Minnesota Lynx",
    "PHO": "Phoenix Mercury",
    "WAS": "Washington Mystics",
    "ATL": "Atlanta Dream",
    "GS":  "Golden State Valkyries",
}

def get_team(df: pd.DataFrame, team_name: str) -> pd.Series:
    """Match by TeamName or TeamAbbr, exact first then partial."""
    # Try exact TeamName match
    name_col = "TeamName" if "TeamName" in df.columns else "TEAM_NAME"
    abbr_col = "TeamAbbr" if "TeamAbbr" in df.columns else "TEAM_ABBREVIATION"

    # Try name map first
    lookup = NBA_NAME_MAP.get(team_name, team_name)

    if name_col in df.columns:
        exact = df[df[name_col].str.lower() == lookup.lower()]
        if not exact.empty:
            return exact.iloc[0]
        partial = df[df[name_col].str.contains(lookup, case=False, na=False)]
        if not partial.empty:
            return partial.iloc[0]

    # Try abbreviation
    if abbr_col in df.columns:
        exact = df[df[abbr_col].str.upper() == team_name.upper()]
        if not exact.empty:
            return exact.iloc[0]

    raise ValueError(f"Team not found: '{team_name}'. Check NBA team name or abbreviation.")


def get_team_rotation(rotations: pd.DataFrame, team_id: int) -> pd.DataFrame:
    """Returns rotation players for a team, sorted by minutes descending."""
    if rotations.empty:
        return pd.DataFrame()
    team_rot = rotations[rotations["TeamID"] == team_id].copy()
    return team_rot.sort_values("MIN", ascending=False)


# ── NCAA averages equivalent for NBA ─────────────────────────────────────
def compute_league_averages(ratings: pd.DataFrame, ff: pd.DataFrame) -> dict:
    return {
        "pace":     ratings["AdjTempo"].mean(),
        "to_pct":   ff["TO_Pct"].mean()   if "TO_Pct"  in ff.columns else 13.5,
        "dto_pct":  ff["DTO_Pct"].mean()  if "DTO_Pct" in ff.columns else 13.5,
        "or_pct":   ff["OR_Pct"].mean()   if "OR_Pct"  in ff.columns else 25.5,
        "dor_pct":  ff["DOR_Pct"].mean()  if "DOR_Pct" in ff.columns else 25.5,
        "ft_rate":  ff["FT_Rate"].mean()  if "FT_Rate" in ff.columns else 0.22,
        "dft_rate": ff["DFT_Rate"].mean() if "DFT_Rate" in ff.columns else 0.22,
        "n_teams":  len(ratings),
    }


# ── Team Percentile (identical formula to CBB) ────────────────────────────
def compute_team_percentile(team_name: str, ratings: pd.DataFrame) -> tuple[float, dict]:
    t       = get_team(ratings, team_name)
    n       = len(ratings)
    rank    = float(t["RankAdjEM"])
    pct     = (n - rank) / n
    return pct, {"rank": rank, "pct": pct, "n_teams": n}


def compute_game_adjustment(t1_pct: float, t2_pct: float) -> tuple[float, float]:
    """Quality-gap dampener — identical to CBB model."""
    return (t2_pct - t1_pct) * 0.5, (t1_pct - t2_pct) * 0.5


# ── ★ PLAYER IMPACT LAYER ★ ───────────────────────────────────────────────
def compute_lineup_efficiency_adjustment(
    team_id:    int,
    rotations:  pd.DataFrame,
    injuries:   pd.DataFrame,
    base_adj_oe: float,
    base_adj_de: float,
) -> tuple[float, float]:
    """
    Adjusts team AdjOE and AdjDE based on tonight's active lineup.

    Method:
      For each player in the rotation:
        1. Get their off_impact (effect on team OffRtg when on floor) from on/off splits
        2. Get their projected minutes share tonight (baseline = season average)
        3. If player is OUT: their minutes are redistributed to next-man-up
        4. Weighted adjustment = sum(off_impact * adjusted_min_share)

    The adjustment is then scaled:
      lineup_oe_adj = sum(player_off_impact * min_share) * IMPACT_SCALE
      lineup_de_adj = sum(player_def_impact * min_share) * IMPACT_SCALE

    IMPACT_SCALE calibration:
      An average starter with off_impact = +3.0 plays 38% of minutes.
      Expected team-level oe effect = 3.0 * 0.38 * scale
      We want a missing starter to shift the line ~4-5 pts → scale ≈ 0.8

    Returns (oe_adjustment, de_adjustment) in efficiency rating units.
    Positive oe_adjustment = team scores more than base efficiency.
    Negative de_adjustment = team defends better (lower DefRtg is better).
    """
    IMPACT_SCALE = 0.85   # Tuning knob — adjust as model is calibrated with results

    if rotations.empty:
        return 0.0, 0.0

    team_rot = rotations[rotations["TeamID"] == team_id].copy()
    if team_rot.empty:
        return 0.0, 0.0

    # Mark OUT players from injury report
    if not injuries.empty and "IsOut" in injuries.columns:
        out_players = set(injuries[injuries["IsOut"] == True]["PlayerName"].str.lower())
        team_rot["IsOut"] = team_rot["PlayerName"].str.lower().isin(out_players)
    else:
        team_rot["IsOut"] = False

    # GTD players: apply 50% probability of playing for QUESTIONABLE
    if not injuries.empty and "IsGTD" in injuries.columns:
        gtd_players = set(injuries[injuries["IsGTD"] == True]["PlayerName"].str.lower())
        team_rot["GTD_ProbOut"] = team_rot["PlayerName"].str.lower().isin(gtd_players).map(
            lambda x: 0.5 if x else 0.0
        )
    else:
        team_rot["GTD_ProbOut"] = 0.0

    # Effective minutes share: reduce OUT players to 0, redistribute
    team_rot["EffMinShare"] = team_rot.apply(
        lambda r: 0.0 if r["IsOut"]
                  else r["MinShare"] * (1 - r.get("GTD_ProbOut", 0.0)),
        axis=1
    )

    # Normalize so shares sum to 1.0
    total_share = team_rot["EffMinShare"].sum()
    if total_share > 0:
        team_rot["EffMinShare"] = team_rot["EffMinShare"] / total_share
    else:
        # Entire team is out somehow — return base efficiency
        return 0.0, 0.0

    # Compute weighted impact
    oe_adj = 0.0
    de_adj = 0.0

    if "off_impact" in team_rot.columns and "def_impact" in team_rot.columns:
        team_rot["off_impact"] = team_rot["off_impact"].fillna(0.0)
        team_rot["def_impact"] = team_rot["def_impact"].fillna(0.0)
        oe_adj = (team_rot["off_impact"] * team_rot["EffMinShare"]).sum() * IMPACT_SCALE
        de_adj = (team_rot["def_impact"] * team_rot["EffMinShare"]).sum() * IMPACT_SCALE
    else:
        # Fallback: use NET_RATING as proxy for impact
        if "NET_RATING" in team_rot.columns:
            team_rot["NET_RATING"] = team_rot["NET_RATING"].fillna(0.0)
            net_adj = (team_rot["NET_RATING"] * team_rot["EffMinShare"]).sum() * IMPACT_SCALE * 0.5
            oe_adj  =  net_adj * 0.6   # assume 60% offensive, 40% defensive contribution
            de_adj  = -net_adj * 0.4

    # Cap adjustments to prevent extreme swings (max ±8 points per team)
    oe_adj = max(-8.0, min(8.0, oe_adj))
    de_adj = max(-8.0, min(8.0, de_adj))

    return round(oe_adj, 3), round(de_adj, 3)


def get_active_players(
    team_id: int,
    rotations: pd.DataFrame,
    injuries: pd.DataFrame,
    top_n: int = 8,
) -> list[dict]:
    """Returns list of active players tonight with their impact metrics."""
    if rotations.empty:
        return []

    team_rot = rotations[rotations["TeamID"] == team_id].head(top_n).copy()

    out_names = set()
    gtd_names = set()
    if not injuries.empty:
        if "IsOut" in injuries.columns:
            out_names = set(injuries[injuries["IsOut"]]["PlayerName"].str.lower())
        if "IsGTD" in injuries.columns:
            gtd_names = set(injuries[injuries["IsGTD"]]["PlayerName"].str.lower())

    players = []
    for _, row in team_rot.iterrows():
        name = row.get("PlayerName", "")
        status = "OUT" if name.lower() in out_names else \
                 "GTD" if name.lower() in gtd_names else "ACTIVE"
        players.append({
            "name":        name,
            "status":      status,
            "minutes":     round(row.get("MIN", 0), 1),
            "min_share":   round(row.get("MinShare", 0), 3),
            "off_impact":  round(row.get("off_impact", 0), 2),
            "def_impact":  round(row.get("def_impact", 0), 2),
            "net_impact":  round(row.get("net_impact", 0), 2),
        })

    return players


# ── Core Formulas (identical to CBB model) ───────────────────────────────
def projected_pace(t1_tempo: float, t2_tempo: float, avg_pace: float) -> float:
    return avg_pace + (t1_tempo - avg_pace) + (t2_tempo - avg_pace)


def points_per_possession(adj_oe: float, opp_adj_de: float) -> float:
    return (adj_oe + opp_adj_de) / 2 / 100


def projected_turnovers(team_to: float, opp_dto: float, avg_to: float, avg_dto: float, adj: float) -> float:
    """Averaged two-term formula — same fix as CBB v1.2."""
    term1 = avg_to  - team_to
    term2 = avg_dto - opp_dto
    raw   = (term1 + term2) / 2
    return raw + abs(raw) * adj


def projected_rebounds(team_or: float, opp_dor: float, avg_or: float, avg_dor: float, adj: float) -> float:
    """Averaged two-term formula — same fix as CBB v1.3."""
    term1 = opp_dor - avg_dor
    term2 = team_or - avg_or
    raw   = (term1 + term2) / 2
    return raw + abs(raw) * adj


def adjusted_possessions(pace: float, proj_reb: float, proj_to: float) -> float:
    """No FT — same as CBB v1.1."""
    return pace + pace * (proj_reb * 0.01) + pace * (proj_to * 0.01)


def hca_adjustments(hca: float, team1_is_home) -> tuple[float, float]:
    if team1_is_home is None:
        return 0.0, 0.0
    return (hca * 0.5, -hca * 0.5) if team1_is_home else (-hca * 0.5, hca * 0.5)


def mround(value: float, multiple: float = 0.5) -> float:
    return round(value / multiple) * multiple


# ── Full Game Projection ───────────────────────────────────────────────────
def project_game(
    team1:         str,
    team2:         str,
    team1_is_home,
    data:          dict,
    league:        str = "NBA",
    game_time:     str = None,
) -> dict:
    """
    Project a single game. Returns same structure as CBB project_game()
    plus player_impact section.

    data dict keys:
      ratings, four_factors           — from nba_fetcher.fetch_all()
      rotations, injuries             — from player_fetcher.fetch_all_player_data()
    """
    ratings      = data["ratings"]
    ff           = data["four_factors"]
    rotations    = data.get("rotations",    pd.DataFrame())
    injuries     = data.get("injuries",     pd.DataFrame())

    avgs = compute_league_averages(ratings, ff)
    hca  = NBA_HCA if league == "NBA" else WNBA_HCA

    # Pull team rows
    t1_r  = get_team(ratings, team1)
    t2_r  = get_team(ratings, team2)
    t1_ff = get_team(ff,      team1)
    t2_ff = get_team(ff,      team2)

    t1_id = int(t1_r.get("TeamID", 0))
    t2_id = int(t2_r.get("TeamID", 0))

    # Team percentiles & quality adjustment
    t1_pct, _ = compute_team_percentile(team1, ratings)
    t2_pct, _ = compute_team_percentile(team2, ratings)
    adj1, adj2 = compute_game_adjustment(t1_pct, t2_pct)

    # ── Pace ──────────────────────────────────────────────────────────────
    pace = projected_pace(float(t1_r["AdjTempo"]), float(t2_r["AdjTempo"]), avgs["pace"])

    # ── Base PPP (season-average efficiency) ─────────────────────────────
    t1_base_ppp = points_per_possession(float(t1_r["AdjOE"]), float(t2_r["AdjDE"]))
    t2_base_ppp = points_per_possession(float(t2_r["AdjOE"]), float(t1_r["AdjDE"]))

    # ── ★ PLAYER IMPACT LAYER ★ ───────────────────────────────────────────
    # Compute lineup-adjusted OE/DE for each team based on tonight's active roster
    t1_oe_adj, t1_de_adj = compute_lineup_efficiency_adjustment(
        t1_id, rotations, injuries,
        float(t1_r["AdjOE"]), float(t1_r["AdjDE"])
    )
    t2_oe_adj, t2_de_adj = compute_lineup_efficiency_adjustment(
        t2_id, rotations, injuries,
        float(t2_r["AdjOE"]), float(t2_r["AdjDE"])
    )

    # Apply lineup adjustments to effective efficiency ratings
    t1_adj_oe = float(t1_r["AdjOE"]) + t1_oe_adj
    t1_adj_de = float(t1_r["AdjDE"]) + t1_de_adj
    t2_adj_oe = float(t2_r["AdjOE"]) + t2_oe_adj
    t2_adj_de = float(t2_r["AdjDE"]) + t2_de_adj

    # Lineup-adjusted PPP
    t1_ppp = points_per_possession(t1_adj_oe, t2_adj_de)
    t2_ppp = points_per_possession(t2_adj_oe, t1_adj_de)

    # ── Four Factors ──────────────────────────────────────────────────────
    t1_to  = projected_turnovers(
        float(t1_ff.get("TO_Pct",  avgs["to_pct"])),
        float(t2_ff.get("DTO_Pct", avgs["dto_pct"])),
        avgs["to_pct"], avgs["dto_pct"], adj1
    )
    t2_to  = projected_turnovers(
        float(t2_ff.get("TO_Pct",  avgs["to_pct"])),
        float(t1_ff.get("DTO_Pct", avgs["dto_pct"])),
        avgs["to_pct"], avgs["dto_pct"], adj2
    )
    t1_reb = projected_rebounds(
        float(t1_ff.get("OR_Pct",  avgs["or_pct"])),
        float(t2_ff.get("DOR_Pct", avgs["dor_pct"])),
        avgs["or_pct"], avgs["dor_pct"], adj1
    )
    t2_reb = projected_rebounds(
        float(t2_ff.get("OR_Pct",  avgs["or_pct"])),
        float(t1_ff.get("DOR_Pct", avgs["dor_pct"])),
        avgs["or_pct"], avgs["dor_pct"], adj2
    )

    # ── Possessions & Scores ──────────────────────────────────────────────
    t1_poss  = adjusted_possessions(pace, t1_reb, t1_to)
    t2_poss  = adjusted_possessions(pace, t2_reb, t2_to)
    t1_score = t1_ppp * t1_poss
    t2_score = t2_ppp * t2_poss

    # ── HCA ──────────────────────────────────────────────────────────────
    h1, h2   = hca_adjustments(hca, team1_is_home)
    t1_score += h1
    t2_score += h2

    # ── Round ─────────────────────────────────────────────────────────────
    t1_score = mround(t1_score, 0.5)
    t2_score = mround(t2_score, 0.5)

    # ── Active roster snapshots for display ──────────────────────────────
    t1_active = get_active_players(t1_id, rotations, injuries)
    t2_active = get_active_players(t2_id, rotations, injuries)

    return {
        "team1":             team1,
        "team2":             team2,
        "league":            league,
        "game_time":         game_time,
        "projected_pace":    round(pace, 1),
        "team1_score":       t1_score,
        "team2_score":       t2_score,
        "spread":            mround(t1_score - t2_score, 0.5),
        "total":             mround(t1_score + t2_score, 0.5),
        "team1_ppp":         round(t1_ppp, 4),
        "team2_ppp":         round(t2_ppp, 4),
        "team1_adj_metric":  round(adj1, 6),
        "team2_adj_metric":  round(adj2, 6),
        "location":          "home" if team1_is_home else ("away" if team1_is_home is False else "neutral"),

        # ── Player impact section (new vs CBB) ──────────────────────────
        "player_impact": {
            "t1_oe_adjustment":  t1_oe_adj,   # How much team1 AdjOE changed from lineup
            "t1_de_adjustment":  t1_de_adj,   # How much team1 AdjDE changed from lineup
            "t2_oe_adjustment":  t2_oe_adj,
            "t2_de_adjustment":  t2_de_adj,
            "t1_effective_oe":   round(t1_adj_oe, 2),
            "t1_effective_de":   round(t1_adj_de, 2),
            "t2_effective_oe":   round(t2_adj_oe, 2),
            "t2_effective_de":   round(t2_adj_de, 2),
            "t1_lineup":         t1_active,
            "t2_lineup":         t2_active,
            "t1_out":    [p for p in t1_active if p["status"] == "OUT"],
            "t2_out":    [p for p in t2_active if p["status"] == "OUT"],
            "t1_gtd":    [p for p in t1_active if p["status"] == "GTD"],
            "t2_gtd":    [p for p in t2_active if p["status"] == "GTD"],
        },

        # ── Full debug (mirrors CBB debug dict) ─────────────────────────
        "debug": {
            "avg_pace":       round(avgs["pace"], 2),
            "t1_tempo":       float(t1_r["AdjTempo"]),  "t2_tempo":  float(t2_r["AdjTempo"]),
            "t1_adjoe":       float(t1_r["AdjOE"]),     "t2_adjoe":  float(t2_r["AdjOE"]),
            "t1_adjde":       float(t1_r["AdjDE"]),     "t2_adjde":  float(t2_r["AdjDE"]),
            "t1_eff_adjoe":   round(t1_adj_oe, 2),      "t2_eff_adjoe": round(t2_adj_oe, 2),
            "t1_eff_adjde":   round(t1_adj_de, 2),      "t2_eff_adjde": round(t2_adj_de, 2),
            "t1_to":          round(t1_to, 4),           "t2_to":     round(t2_to, 4),
            "t1_reb":         round(t1_reb, 4),          "t2_reb":    round(t2_reb, 4),
            "t1_poss":        round(t1_poss, 4),         "t2_poss":   round(t2_poss, 4),
            "t1_base_ppp":    round(t1_base_ppp, 4),     "t2_base_ppp": round(t2_base_ppp, 4),
            "h1_adj":         round(h1, 2),              "h2_adj":    round(h2, 2),
        }
    }


# ── Quick test ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("NBA model loaded. Run via run_nba.py or import project_game().")
    print(f"NBA HCA: {NBA_HCA} pts  |  WNBA HCA: {WNBA_HCA} pts")
    print("Player impact layer: active when rotations + injuries CSVs are present.")
