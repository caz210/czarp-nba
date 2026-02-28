# -*- coding: utf-8 -*-
"""
run_nba.py
Daily batch runner for the CZarp NBA/WNBA model.

Usage:
  python run_nba.py                      # NBA, today
  python run_nba.py --league WNBA        # WNBA, today
  python run_nba.py --date 2025-04-01    # Specific date (backtest)
  python run_nba.py --no-player-data     # Skip player layer (faster, team-only)
  python run_nba.py --team "Lakers"      # Filter output to one team

Outputs:
  outputs/nba_projections_{date}.csv     — full projections with edge scores
  outputs/nba_debug_{date}.xlsx          — detailed breakdown per game
  Terminal: sorted edge report
"""

import argparse
import json
import pandas as pd
from datetime import date, datetime
from pathlib import Path

from nba_fetcher   import fetch_all as fetch_team_data
from nba_fetcher   import fetch_todays_games
from player_fetcher import fetch_all_player_data
from nba_model     import load_data, project_game


# ── Vegas matching (reuse same structure as CBB) ───────────────────────────
def match_vegas(result: dict, vegas_lines: list[dict]) -> dict:
    """
    Attach Vegas spread/total to a projection result.
    vegas_lines: list of dicts with keys team1, team2, spread, total
    Returns result dict enriched with vegas fields.
    """
    t1 = result["team1"].lower()
    t2 = result["team2"].lower()
    result["vegas_spread"] = None
    result["vegas_total"]  = None
    result["vegas_fav"]    = None
    result["edge_score"]   = None
    result["sides_agree"]  = None

    for line in vegas_lines:
        v1 = line.get("team1", "").lower()
        v2 = line.get("team2", "").lower()
        if (t1 in v1 or v1 in t1) and (t2 in v2 or v2 in t2):
            vs = line.get("spread")
            vt = line.get("total")
            result["vegas_spread"] = vs
            result["vegas_total"]  = vt
            if vs is not None:
                result["vegas_fav"]   = result["team1"] if vs > 0 else result["team2"]
                spread_edge           = result["spread"] - vs
                result["spread_edge"] = round(spread_edge, 2)
                result["edge_score"]  = round(abs(spread_edge) / 10, 4)
                my_fav                = result["team1"] if result["spread"] > 0 else result["team2"]
                result["sides_agree"] = (my_fav == result["vegas_fav"])
            break

    return result


# ── Projection runner ─────────────────────────────────────────────────────
def run_projections(
    league:          str  = "NBA",
    game_date:       str  = None,
    data_dir:        str  = "data",
    outputs_dir:     str  = "outputs",
    refresh_data:    bool = False,
    skip_player:     bool = False,
    vegas_lines:     list = None,
) -> list[dict]:
    """
    Full pipeline: fetch data → project all games → attach Vegas → save outputs.
    Returns list of result dicts sorted by edge score descending.
    """
    if game_date is None:
        game_date = date.today().isoformat()

    Path(data_dir).mkdir(exist_ok=True)
    Path(outputs_dir).mkdir(exist_ok=True)

    prefix = league.lower()

    # ── 1. Fetch / load team data ─────────────────────────────────────────
    ratings_path = Path(data_dir) / f"{prefix}_ratings.csv"
    if refresh_data or not ratings_path.exists():
        print(f"\n[1/4] Fetching {league} team data...")
        fetch_team_data(league=league, data_dir=data_dir)
    else:
        print(f"\n[1/4] Using cached {league} team data (pass --refresh to update)")

    # ── 2. Fetch / load player data ───────────────────────────────────────
    rotations_path = Path(data_dir) / f"{prefix}_rotations.csv"
    if not skip_player and (refresh_data or not rotations_path.exists()):
        print(f"\n[2/4] Fetching {league} player data (on/off splits, injuries)...")
        fetch_all_player_data(league=league, data_dir=data_dir)
    elif skip_player:
        print(f"\n[2/4] Skipping player layer (--no-player-data)")
    else:
        print(f"\n[2/4] Using cached player data (injuries are re-fetched daily)")
        # Always re-fetch injuries — they change daily
        from player_fetcher import fetch_injury_report
        injuries = fetch_injury_report(league)
        injuries.to_csv(f"{data_dir}/{prefix}_injuries.csv", index=False)
        print(f"  Injury report refreshed: {len(injuries)} entries")

    # ── 3. Load data into model ───────────────────────────────────────────
    print(f"\n[3/4] Loading data and running projections...")
    data = load_data(data_dir, league)

    # ── 4. Get today's schedule ───────────────────────────────────────────
    from datetime import datetime
    date_str = datetime.strptime(game_date, "%Y-%m-%d").strftime("%m/%d/%Y")
    games    = fetch_todays_games(league=league, date_str=date_str)

    if not games:
        print(f"  No {league} games found for {game_date}")
        return []

    # ── 5. Project each game ──────────────────────────────────────────────
    results = []
    for g in games:
        try:
            result = project_game(
                team1         = g["team1"],
                team2         = g["team2"],
                team1_is_home = True,    # team1 = home in NBA scoreboardv2
                data          = data,
                league        = league,
                game_time     = g.get("game_time"),
            )
            result["arena"] = g.get("arena", "")
            result["city"]  = g.get("city", "")

            # Attach Vegas
            if vegas_lines:
                result = match_vegas(result, vegas_lines)

            results.append(result)

        except Exception as e:
            print(f"  Warning: Could not project {g['team1']} vs {g['team2']}: {e}")

    # ── 6. Sort by edge score ─────────────────────────────────────────────
    results.sort(key=lambda r: r.get("edge_score") or 0, reverse=True)

    # ── 7. Save outputs ───────────────────────────────────────────────────
    ts  = datetime.now().strftime("%H%M")
    out = Path(outputs_dir) / f"{prefix}_projections_{game_date}_{ts}.csv"

    flat_rows = []
    for r in results:
        row = {k: v for k, v in r.items() if k not in ("debug", "player_impact")}
        # Flatten player impact summary
        pi = r.get("player_impact", {})
        row["t1_oe_adj"]      = pi.get("t1_oe_adjustment", 0)
        row["t1_de_adj"]      = pi.get("t1_de_adjustment", 0)
        row["t2_oe_adj"]      = pi.get("t2_oe_adjustment", 0)
        row["t2_de_adj"]      = pi.get("t2_de_adjustment", 0)
        row["t1_eff_oe"]      = pi.get("t1_effective_oe")
        row["t2_eff_oe"]      = pi.get("t2_effective_oe")
        row["t1_out_players"] = ", ".join(p["name"] for p in pi.get("t1_out", []))
        row["t2_out_players"] = ", ".join(p["name"] for p in pi.get("t2_out", []))
        flat_rows.append(row)

    pd.DataFrame(flat_rows).to_csv(out, index=False)
    print(f"\n[4/4] Saved {len(results)} projections → {out}")

    # ── 8. Print edge report ──────────────────────────────────────────────
    print(f"\n{'='*70}")
    print(f"  {league} EDGE REPORT — {game_date}")
    print(f"{'='*70}")
    for r in results:
        spread_str = f"{r['spread']:+.1f}"
        vs_str     = f"Vegas {r.get('vegas_spread', '--'):+}" if r.get("vegas_spread") else "no line"
        edge_str   = f"Edge {r.get('edge_score', 0)*10:.1f}" if r.get("edge_score") else ""
        agree_str  = "✓" if r.get("sides_agree") else ("✗ SIDES DIFFER" if r.get("sides_agree") is False else "")
        outs_t1    = ", ".join(p["name"] for p in r.get("player_impact", {}).get("t1_out", []))
        outs_t2    = ", ".join(p["name"] for p in r.get("player_impact", {}).get("t2_out", []))
        outs_str   = ""
        if outs_t1: outs_str += f" [OUT: {outs_t1}]"
        if outs_t2: outs_str += f" [OUT: {outs_t2}]"

        print(f"  {r['team2']:22} @ {r['team1']:22} "
              f"CZarp {r['team1']} {spread_str:>6}  {vs_str:>16}  {edge_str:>10}  {agree_str}{outs_str}")

    return results


# ── CLI ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CZarp NBA/WNBA Daily Model Runner")
    parser.add_argument("--league",          default="NBA",   choices=["NBA", "WNBA"])
    parser.add_argument("--date",            default=None,    help="YYYY-MM-DD (default: today)")
    parser.add_argument("--refresh",         action="store_true", help="Re-fetch all data even if cached")
    parser.add_argument("--no-player-data",  action="store_true", help="Skip player impact layer")
    parser.add_argument("--team",            default=None,    help="Filter to games involving this team")
    parser.add_argument("--data-dir",        default="data")
    parser.add_argument("--output-dir",      default="outputs")
    args = parser.parse_args()

    results = run_projections(
        league       = args.league,
        game_date    = args.date,
        data_dir     = args.data_dir,
        outputs_dir  = args.output_dir,
        refresh_data = args.refresh,
        skip_player  = args.no_player_data,
    )

    if args.team and results:
        team_results = [r for r in results
                        if args.team.lower() in r["team1"].lower()
                        or args.team.lower() in r["team2"].lower()]
        if team_results:
            print(f"\n  Filtered to '{args.team}': {len(team_results)} game(s)")
            for r in team_results:
                print(json.dumps({
                    k: v for k, v in r.items()
                    if k not in ("debug",)
                }, indent=2, default=str))
