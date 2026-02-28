# -*- coding: utf-8 -*-
"""
app_nba.py  —  CZarp NBA / WNBA Betting Model  —  Streamlit Dashboard
Mirror of CBB app.py, extended with player impact panel.
"""

import os
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from datetime import date, datetime, timedelta

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

st.set_page_config(
    page_title="CZarp NBA Model",
    page_icon="🏆",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── CSS (same design language as CBB app) ────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Bebas+Neue&family=DM+Sans:wght@300;400;500;600&display=swap');
html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }
.stApp { background: #0b1630; color: #e8e8e8; }
h1, h2, h3 { font-family: 'Bebas Neue', sans-serif; letter-spacing: 2px; }
[data-testid="metric-container"] { background: #152348; border: 1px solid #1e3a6e; border-radius: 10px; padding: 14px !important; }
[data-testid="stSidebar"] { background: #091228; border-right: 2px solid #1e3a6e; }
.game-card { background: #152348; border: 1px solid #1e3a6e; border-radius: 12px; padding: 16px 20px; margin-bottom: 12px; position: relative; }
.game-card:hover { border-color: #f0b429; transition: border-color 0.2s; }
.game-time { font-size: 0.72rem; color: #f0b429; font-weight: 600; letter-spacing: 1px; margin-bottom: 8px; }
.team-row { display: flex; justify-content: space-between; align-items: center; padding: 5px 0; }
.team-name { font-size: 1.05rem; font-weight: 600; }
.team-label { color: #4a6fa5; font-size: 0.68rem; margin-left: 6px; letter-spacing: 0.5px; }
.team-score { font-family: 'Bebas Neue', sans-serif; font-size: 1.9rem; color: #6688bb; letter-spacing: 1px; min-width: 50px; text-align: right; }
.team-score-winner { color: #f0b429; }
.game-meta { margin-top: 10px; padding-top: 10px; border-top: 1px solid #1e3a6e; display: flex; flex-wrap: wrap; gap: 16px; }
.meta-item { display: flex; flex-direction: column; gap: 2px; }
.meta-label { font-size: 0.65rem; color: #4a6fa5; letter-spacing: 0.5px; text-transform: uppercase; }
.meta-val { color: #ddd; font-weight: 600; font-size: 0.85rem; }
.meta-val-hot { color: #f0b429; font-weight: 700; }
.meta-val-differ { color: #e05c5c; font-weight: 700; }
.edge-badge { display: inline-block; padding: 3px 10px; border-radius: 20px; font-size: 0.68rem; font-weight: 700; letter-spacing: 0.5px; }
.edge-hot  { background: #f0b42922; color: #f0b429; border: 1px solid #f0b42955; }
.edge-good { background: #27a14822; color: #5ddc7a; border: 1px solid #27a14855; }
.edge-low  { background: #1e3a6e33; color: #6688bb; border: 1px solid #1e3a6e; }
.edge-diff { background: #e05c5c22; color: #e05c5c; border: 1px solid #e05c5c55; }
.divider { border: none; border-top: 1px solid #1e3a6e; margin: 20px 0; }
.section-title { font-family: 'Bebas Neue', sans-serif; font-size: 1.3rem; letter-spacing: 2px; color: #f0b429; margin: 24px 0 12px 0; }
/* Player status badges */
.player-out { color: #e05c5c; font-weight: 700; font-size: 0.72rem; }
.player-gtd { color: #f0a429; font-weight: 600; font-size: 0.72rem; }
.player-active { color: #5ddc7a; font-size: 0.72rem; }
.lineup-panel { background: #0d1a35; border: 1px solid #1e3a6e; border-radius: 8px; padding: 12px 14px; margin-top: 8px; }
.lineup-title { font-size: 0.65rem; color: #f0b429; letter-spacing: 1.5px; font-weight: 700; margin-bottom: 6px; text-transform: uppercase; }
.impact-positive { color: #5ddc7a; }
.impact-negative { color: #e05c5c; }
/* Tab styling */
.stTabs [data-baseweb="tab-list"] { background: #091228; border-bottom: 2px solid #1e3a6e; gap: 4px; }
.stTabs [data-baseweb="tab"] { background: #0d1a35; color: #4a6fa5 !important; border-radius: 6px 6px 0 0; padding: 8px 20px; font-family: 'Bebas Neue', sans-serif; font-size: 1rem; letter-spacing: 1.5px; border: 1px solid #1e3a6e; border-bottom: none; }
.stTabs [aria-selected="true"] { background: #152348 !important; color: #f0b429 !important; border-color: #f0b429 !important; }
.stTabs [data-baseweb="tab"]:hover { color: #f0b429 !important; }
.stTabs [data-baseweb="tab-panel"] { background: #0b1630; padding-top: 16px; }
.stButton>button { background: #152348; color: #f0b429; border: 1px solid #f0b429; font-family: 'Bebas Neue', sans-serif; letter-spacing: 1.5px; font-size: 1rem; }
.stButton>button:hover { background: #f0b429; color: #0b1630; }
[data-testid="metric-container"] label { color: #4a6fa5 !important; }
[data-testid="metric-container"] [data-testid="metric-value"] { color: #f0b429 !important; }
</style>
""", unsafe_allow_html=True)

# ── Module imports ──────────────────────────────────────────────────────────
try:
    from nba_fetcher    import fetch_all as fetch_nba_data, fetch_todays_games
    from player_fetcher import fetch_all_player_data, fetch_injury_report
    from nba_model      import load_data, project_game
    MODULES_OK = True
except ImportError as e:
    MODULES_OK = False
    st.error(f"Import error: {e}. Make sure nba_fetcher.py, player_fetcher.py, and nba_model.py are in the same directory.")

# ── Vegas lines — optional, app runs fine without it ────────────────────────
try:
    from odds_fetcher import fetch_vegas_lines, match_vegas_to_game
    ODDS_OK = True
except ImportError:
    ODDS_OK = False
    def fetch_vegas_lines():
        return __import__("pandas").DataFrame()
    def match_vegas_to_game(r: dict, vegas_df) -> dict:
        """Passthrough stub — no Vegas lines available until odds_fetcher.py is added."""
        r.setdefault("vegas_spread", None)
        r.setdefault("vegas_total",  None)
        r.setdefault("vegas_fav",    None)
        r.setdefault("edge_score",   None)
        r.setdefault("spread_edge",  None)
        r.setdefault("sides_agree",  None)
        return r

CENTRAL = ZoneInfo("America/Chicago")


# ── Helpers ───────────────────────────────────────────────────────────────────
def _fmt_spread(val):
    """Format a spread value as +/- string."""
    if val is None: return "—"
    return f"+{val:.1f}" if val >= 0 else f"{val:.1f}"

def _fmt_pct(val):
    if val is None: return "—"
    return f"{val*100:.1f}%" if val < 5 else f"{val:.1f}%"

def _player_status_html(status: str) -> str:
    if status == "OUT":
        return "<span class='player-out'>● OUT</span>"
    elif status == "GTD":
        return "<span class='player-gtd'>◐ GTD</span>"
    return "<span class='player-active'>● ACT</span>"

def _impact_html(val: float) -> str:
    if val is None: return ""
    cls = "impact-positive" if val > 0 else "impact-negative"
    sign = "+" if val > 0 else ""
    return f"<span class='{cls}'>{sign}{val:.2f}</span>"


# ── Prediction blurb (NBA-aware) ─────────────────────────────────────────────
def generate_prediction_blurb(r: dict, home_name: str, away_name: str) -> str:
    s1 = r.get("team1_score", 0)
    s2 = r.get("team2_score", 0)
    h_score, a_score = s1, s2
    h_ppp = r.get("team1_ppp", 0)
    a_ppp = r.get("team2_ppp", 0)
    d  = r.get("debug", {})
    pi = r.get("player_impact", {})
    h_reb  = d.get("t1_reb", 0) or 0
    a_reb  = d.get("t2_reb", 0) or 0
    h_to   = d.get("t1_to",  0) or 0
    a_to   = d.get("t2_to",  0) or 0
    h_poss = d.get("t1_poss", 0) or 0
    a_poss = d.get("t2_poss", 0) or 0
    loc    = r.get("location", "neutral")
    league = r.get("league", "NBA")

    spread = abs(h_score - a_score)
    winner_is_home = h_score >= a_score
    winner = home_name if winner_is_home else away_name
    loser  = away_name if winner_is_home else home_name
    w_score, l_score = (h_score, a_score) if winner_is_home else (a_score, h_score)
    w_ppp,   l_ppp   = (h_ppp,   a_ppp)   if winner_is_home else (a_ppp,   h_ppp)
    w_reb,   l_reb   = (h_reb,   a_reb)   if winner_is_home else (a_reb,   h_reb)
    w_to,    l_to    = (h_to,    a_to)    if winner_is_home else (a_to,    h_to)
    w_poss,  l_poss  = (h_poss,  a_poss)  if winner_is_home else (a_poss,  h_poss)

    loc_phrase = ""
    if loc == "home" and winner_is_home:      loc_phrase = "at home"
    elif loc == "away" and not winner_is_home: loc_phrase = "on the road"
    elif loc == "neutral":                     loc_phrase = "on a neutral floor"

    advantages = []
    if (w_ppp - l_ppp) > 0.003:              advantages.append("offensive efficiency")
    if w_reb > 0.3:                           advantages.append("offensive rebounding")
    if w_to  > 0.3:                           advantages.append("turnover margin")
    if w_poss > l_poss + 0.5:                advantages.append("extra possessions")
    if not advantages:                        advantages = ["a small overall model edge"]

    confidence = "comfortably" if spread >= 10 else \
                 "by a solid margin" if spread >= 6 else \
                 "in a competitive game" if spread >= 3 else \
                 "in what projects as a tight battle"

    adv_text = advantages[0] if len(advantages) == 1 else \
               f"{advantages[0]} and {advantages[1]}" if len(advantages) == 2 else \
               ", ".join(advantages[:-1]) + f", and {advantages[-1]}"

    loc_suffix = f" {loc_phrase}" if loc_phrase else ""
    headline   = f"<b>{winner}</b> ({w_score:.0f}) over <b>{loser}</b> ({l_score:.0f}){loc_suffix}, {confidence}."
    body       = f"The model projects <b>{winner}</b> to win on {adv_text}."

    # Injury context
    t1_out = pi.get("t1_out", [])
    t2_out = pi.get("t2_out", [])
    all_out = [(home_name,  p) for p in t1_out] + [(away_name, p) for p in t2_out]
    injury_note = ""
    if all_out:
        out_strs = [f"<b>{name}</b> ({p['name']})" for name, p in all_out]
        injury_note = f"<div style='color:#e05c5c;margin-top:8px;font-size:0.82em;'>⚠️ Lineup note: {', '.join(out_strs)} are OUT. Lineup adjustment applied.</div>"

    # Lineup adjustment summary
    oe_adj_h = pi.get("t1_oe_adjustment", 0) or 0
    oe_adj_a = pi.get("t2_oe_adjustment", 0) or 0
    lineup_note = ""
    if abs(oe_adj_h) > 0.5 or abs(oe_adj_a) > 0.5:
        lineup_note = (
            f"<div style='color:#4a6fa5;margin-top:6px;font-size:0.8em;'>"
            f"Lineup adj: {home_name} OE {'+' if oe_adj_h>=0 else ''}{oe_adj_h:.1f} pts/100 | "
            f"{away_name} OE {'+' if oe_adj_a>=0 else ''}{oe_adj_a:.1f} pts/100</div>"
        )

    score_line = (
        f"<b>Projected Final:</b> {away_name} {a_score:.0f} – {home_name} {h_score:.0f}"
        f" &nbsp;|&nbsp; <b>Spread:</b> {winner} -{spread:.1f}"
        f" &nbsp;|&nbsp; <b>Total:</b> {h_score + a_score:.0f}"
        f" &nbsp;|&nbsp; <b>Pace:</b> {r.get('projected_pace', 0):.0f} poss"
    )

    return f"""
<div style="
  background: linear-gradient(135deg, #0f1923 0%, #152348 100%);
  border-left: 4px solid #f0b429;
  border-radius: 8px;
  padding: 18px 22px;
  font-family: 'DM Sans', 'Inter', sans-serif;
  color: #e8e8e8;
  line-height: 1.75;
">
  <div style="font-size:0.75rem;font-weight:700;color:#f0b429;letter-spacing:2px;margin-bottom:10px;">
    🔮 MODEL PREDICTION — {league}
  </div>
  <div style="font-size:1.05em;margin-bottom:10px;">{headline}</div>
  <div style="font-size:0.9em;color:#c8d8e8;margin-bottom:8px;">{body}</div>
  {injury_note}
  {lineup_note}
  <div style="font-size:0.82em;color:#4a6fa5;border-top:1px solid #1e3a6e;padding-top:10px;margin-top:10px;">
    {score_line}
  </div>
</div>"""


# ── Cached data fetchers ──────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def get_nba_team_data(league: str):
    """Fetch + cache team ratings and four factors. Re-fetches hourly."""
    fetch_nba_data(league=league, data_dir="data")
    return load_data("data", league)


@st.cache_data(ttl=600, show_spinner=False)
def get_player_data(league: str):
    """On/off splits + rotation profiles. Cached 10 min (heavy call)."""
    try:
        fetch_all_player_data(league=league, data_dir="data")
        prefix = league.lower()
        return {
            "rotations": pd.read_csv(f"data/{prefix}_rotations.csv"),
            "injuries":  pd.read_csv(f"data/{prefix}_injuries.csv"),
        }
    except Exception as e:
        st.warning(f"Player data unavailable: {e}. Running team-only model.")
        return {"rotations": pd.DataFrame(), "injuries": pd.DataFrame()}


@st.cache_data(ttl=300, show_spinner=False)
def get_todays_injuries(league: str):
    """Injury report refreshed every 5 minutes — most volatile data."""
    try:
        return fetch_injury_report(league)
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=3600, show_spinner=False)
def get_vegas_lines_nba():
    try:
        return fetch_vegas_lines()
    except Exception:
        return pd.DataFrame()


@st.cache_data(ttl=900, show_spinner=False)
def get_schedule(league: str, date_str: str):
    """Today's schedule from NBA Stats API."""
    from datetime import datetime as dt
    date_formatted = dt.strptime(date_str, "%Y-%m-%d").strftime("%m/%d/%Y")
    try:
        return fetch_todays_games(league=league, date_str=date_formatted)
    except Exception as e:
        st.warning(f"Schedule unavailable: {e}")
        return []


@st.cache_data(ttl=3600, show_spinner=False)
def run_base_projections(league: str, date_str: str):
    """Run projections — cached 1hr. Vegas matching done live so it can update."""
    data       = get_nba_team_data(league)
    player_d   = get_player_data(league)
    injuries   = get_todays_injuries(league)  # Always fresh injuries

    # Merge fresh injuries into the data dict
    data["rotations"] = player_d.get("rotations", pd.DataFrame())
    data["injuries"]  = injuries if not injuries.empty else player_d.get("injuries", pd.DataFrame())

    games = get_schedule(league, date_str)
    if not games:
        return []

    results, errors = [], []
    for g in games:
        try:
            r = project_game(
                team1         = g["team1"],
                team2         = g["team2"],
                team1_is_home = True,
                data          = data,
                league        = league,
                game_time     = g.get("game_time"),
            )
            r["arena"] = g.get("arena", "")
            r["city"]  = g.get("city", "")
            results.append(r)
        except Exception as e:
            errors.append(f"{g.get('team1','?')} vs {g.get('team2','?')}: {e}")

    if errors:
        with st.sidebar:
            st.warning(f"{len(errors)} game(s) failed projection")
    return results


def run_projections(league: str, date_str: str):
    results = run_base_projections(league, date_str)
    if not results:
        return []
    try:
        vegas_df = get_vegas_lines_nba()
    except Exception:
        vegas_df = pd.DataFrame()
    return [match_vegas_to_game(r, vegas_df) for r in results]


# ── Lineup panel HTML builder ─────────────────────────────────────────────────
def build_lineup_html(lineup: list, team_name: str, oe_adj: float, de_adj: float) -> str:
    if not lineup:
        return ""

    rows = ""
    for p in lineup[:8]:
        status_html = _player_status_html(p.get("status", "ACTIVE"))
        ni  = _impact_html(p.get("net_impact"))
        oi  = _impact_html(p.get("off_impact"))
        min_s = f"{p.get('minutes', 0):.0f} min"
        name = p.get("name", "")[:22]
        rows += f"""
          <tr>
            <td style='padding:2px 6px;color:#e8e8e8;font-size:0.75rem;'>{name}</td>
            <td style='padding:2px 6px;text-align:center;'>{status_html}</td>
            <td style='padding:2px 6px;text-align:center;color:#4a6fa5;font-size:0.72rem;'>{min_s}</td>
            <td style='padding:2px 6px;text-align:center;font-size:0.72rem;'>{oi}</td>
            <td style='padding:2px 6px;text-align:center;font-size:0.72rem;'>{ni}</td>
          </tr>"""

    oe_cls  = "impact-positive" if oe_adj > 0 else "impact-negative"
    de_cls  = "impact-positive" if de_adj < 0 else "impact-negative"  # lower DE = better
    oe_sign = "+" if oe_adj >= 0 else ""
    de_sign = "+" if de_adj >= 0 else ""

    return f"""
    <div style='background:#0d1a35;border:1px solid #1e3a6e;border-radius:8px;padding:10px 12px;margin-top:6px;'>
      <div style='font-size:0.65rem;color:#f0b429;letter-spacing:1.5px;font-weight:700;margin-bottom:6px;'>
        {team_name.upper()} ROTATION
        &nbsp;·&nbsp;
        <span class='{oe_cls}' style='font-size:0.65rem;'>OE adj {oe_sign}{oe_adj:.1f}</span>
        &nbsp;·&nbsp;
        <span class='{de_cls}' style='font-size:0.65rem;'>DE adj {de_sign}{de_adj:.1f}</span>
      </div>
      <table style='width:100%;border-collapse:collapse;'>
        <tr style='border-bottom:1px solid #1e3a6e;'>
          <th style='text-align:left;font-size:0.65rem;color:#4a6fa5;padding:2px 6px;font-weight:600;'>PLAYER</th>
          <th style='font-size:0.65rem;color:#4a6fa5;padding:2px 6px;font-weight:600;text-align:center;'>STATUS</th>
          <th style='font-size:0.65rem;color:#4a6fa5;padding:2px 6px;font-weight:600;text-align:center;'>MIN</th>
          <th style='font-size:0.65rem;color:#4a6fa5;padding:2px 6px;font-weight:600;text-align:center;'>OFF±</th>
          <th style='font-size:0.65rem;color:#4a6fa5;padding:2px 6px;font-weight:600;text-align:center;'>NET±</th>
        </tr>
        {rows}
      </table>
    </div>"""


# ── Breakdown table builder ───────────────────────────────────────────────────
def build_breakdown_table(r: dict, home_name: str, away_name: str) -> str:
    hk, ak = "t1", "t2"
    d  = r.get("debug", {})
    pi = r.get("player_impact", {})

    h_rank  = d.get(f"{hk}_rank");         a_rank  = d.get(f"{ak}_rank")

    # Season average efficiency
    h_adjoe_base = d.get(f"{hk}_adjoe");   a_adjoe_base = d.get(f"{ak}_adjoe")
    h_adjde_base = d.get(f"{hk}_adjde");   a_adjde_base = d.get(f"{ak}_adjde")

    # Lineup-adjusted effective efficiency (the values actually used in projection)
    h_eff_oe = d.get(f"{hk}_eff_adjoe");   a_eff_oe = d.get(f"{ak}_eff_adjoe")
    h_eff_de = d.get(f"{hk}_eff_adjde");   a_eff_de = d.get(f"{ak}_eff_adjde")

    h_tempo = d.get(f"{hk}_tempo");         a_tempo = d.get(f"{ak}_tempo")
    h_poss  = d.get(f"{hk}_poss");          a_poss  = d.get(f"{ak}_poss")
    h_ppp   = r.get("team1_ppp", 0);       a_ppp   = r.get("team2_ppp", 0)
    h_to    = d.get(f"{hk}_to");           a_to    = d.get(f"{ak}_to")
    h_reb   = d.get(f"{hk}_reb");          a_reb   = d.get(f"{ak}_reb")
    h_oe_adj = pi.get("t1_oe_adjustment", 0) or 0
    a_oe_adj = pi.get("t2_oe_adjustment", 0) or 0
    h_de_adj = pi.get("t1_de_adjustment", 0) or 0
    a_de_adj = pi.get("t2_de_adjustment", 0) or 0
    h_hca   = d.get("h1_adj", 0) or 0
    avg_pace = d.get("avg_pace", 0)

    # Four factors
    h_to_pct  = d.get(f"{hk}_to_pct");    a_to_pct  = d.get(f"{ak}_to_pct")
    h_or_pct  = d.get(f"{hk}_or_pct");    a_or_pct  = d.get(f"{ak}_or_pct")
    h_ft_rate = d.get(f"{hk}_ft_rate");   a_ft_rate = d.get(f"{ak}_ft_rate")
    h_dto_pct = d.get(f"{hk}_dto_pct");   a_dto_pct = d.get(f"{ak}_dto_pct")
    h_dor_pct = d.get(f"{hk}_dor_pct");   a_dor_pct = d.get(f"{ak}_dor_pct")
    h_dft_rt  = d.get(f"{hk}_dft_rate");  a_dft_rt  = d.get(f"{ak}_dft_rate")

    def _c(val, opp, hib=True):
        if val is None or opp is None: return "#6688bb"
        return "#f0b429" if (val > opp) == hib else "#6688bb"

    def _f(v, fmt=".1f"):
        return f"{v:{fmt}}" if v is not None else "—"

    def _p(v):
        if v is None: return "—"
        return f"{v*100:.1f}%" if v < 5 else f"{v:.1f}%"

    def sr(label, hv, av, hib=True, fmt=".1f", pct=False):
        hclr = _c(hv, av, hib); aclr = _c(av, hv, hib)
        hd = _p(hv) if pct else _f(hv, fmt)
        ad = _p(av) if pct else _f(av, fmt)
        return (f"<tr><td style='color:{aclr};text-align:right;font-weight:600;padding:3px 10px;'>{ad}</td>"
                f"<td style='color:#4a6fa5;font-size:0.72rem;text-align:center;padding:3px 6px;white-space:nowrap;'>{label}</td>"
                f"<td style='color:{hclr};text-align:left;font-weight:600;padding:3px 10px;'>{hd}</td></tr>")

    def sh(label):
        return f"<tr><td colspan='3' style='color:#f0b429;font-size:0.68rem;letter-spacing:2px;padding:8px 10px 3px;font-weight:700;'>{label}</td></tr>"

    # Lineup adjustment rows
    oe_adj_row = sr("⭐ Lineup OE Adjustment", h_oe_adj, a_oe_adj, hib=True, fmt="+.2f") if (abs(h_oe_adj) > 0 or abs(a_oe_adj) > 0) else ""
    de_adj_row = sr("⭐ Lineup DE Adjustment", h_de_adj, a_de_adj, hib=False, fmt="+.2f") if (abs(h_de_adj) > 0 or abs(a_de_adj) > 0) else ""

    return f"""
<table style='width:100%;border-collapse:collapse;font-family:Inter,sans-serif;font-size:0.82rem;'>
  <tr>
    <th style='color:#f0b429;text-align:right;padding:5px 10px;font-size:0.82rem;'>{away_name}</th>
    <th style='width:200px'></th>
    <th style='color:#f0b429;text-align:left;padding:5px 10px;font-size:0.82rem;'>{home_name}</th>
  </tr>
  {sh("RANKINGS & EFFICIENCY")}
  {sr("NBA Efficiency Rank", h_rank, a_rank, hib=False, fmt=".0f")}
  {sr("Season AdjOE (per 100 poss)", h_adjoe_base, a_adjoe_base)}
  {sr("Season AdjDE (per 100 poss)", h_adjde_base, a_adjde_base, hib=False)}
  {sh("★ LINEUP-ADJUSTED EFFICIENCY (Tonight)")}
  {sr("Effective OE (lineup-adjusted)", h_eff_oe, a_eff_oe)}
  {sr("Effective DE (lineup-adjusted)", h_eff_de, a_eff_de, hib=False)}
  {oe_adj_row}
  {de_adj_row}
  {sr("PPP (projected tonight)", h_ppp, a_ppp, fmt=".4f")}
  {sh("PACE & POSSESSIONS")}
  {sr("Season Avg Tempo (poss/game)", h_tempo, a_tempo)}
  {sr(f"League Avg Tempo", avg_pace, avg_pace, fmt=".1f")}
  {sr("Projected Possessions (this game)", h_poss, a_poss)}
  {sh("FOUR FACTORS — OFFENSE")}
  {sr("Effective FG% (or TOV%)", h_to_pct, a_to_pct, hib=False, pct=True)}
  {sr("Off Rebound %", h_or_pct, a_or_pct, pct=True)}
  {sr("FT Rate (FTA/FGA)", h_ft_rate, a_ft_rate, pct=True)}
  {sr("Proj TO Advantage", h_to, a_to)}
  {sr("Proj Reb Advantage", h_reb, a_reb)}
  {sh("FOUR FACTORS — DEFENSE")}
  {sr("TOs Forced on Opponent %", h_dto_pct, a_dto_pct, hib=True, pct=True)}
  {sr("Opp Off Reb % Allowed (lower = better)", h_dor_pct, a_dor_pct, hib=False, pct=True)}
  {sr("FT Rate Allowed (lower = better)", h_dft_rt, a_dft_rt, hib=False, pct=True)}
</table>
{"<p style='font-size:0.72rem;color:#4a6fa5;margin:6px 0 0 10px;'>🏠 HCA applied: <b style='color:#f0b429'>+" + f"{abs(h_hca):.1f} pts</b> to {home_name}</p>" if h_hca else ""}
"""


# ═══════════════════════════════════════════════════════════════════════════════
#  SIDEBAR
# ═══════════════════════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("<div style='padding:10px 0 4px 0;'><span style='font-family:Bebas Neue;font-size:1.8rem;letter-spacing:3px;color:#f0b429;'>CZARP</span><span style='font-family:Bebas Neue;font-size:1.0rem;letter-spacing:2px;color:#4a6fa5;'> ANALYTICS</span></div>", unsafe_allow_html=True)
    st.markdown("<hr style='border-color:#1e3a6e; margin: 0 0 12px 0;'>", unsafe_allow_html=True)

    league = st.radio("League", ["NBA", "WNBA"], horizontal=True, key="sb_league")
    st.markdown(f"<span style='font-family:Bebas Neue;font-size:0.9rem;letter-spacing:2px;color:#4a6fa5;'>{'2024-25' if league == 'NBA' else '2024'} SEASON</span>", unsafe_allow_html=True)
    st.markdown("---")

    sort_by = st.selectbox("Sort games by", ["Edge Score", "Total", "Spread (biggest fav)", "Team Name A-Z"], key="sb_sort")
    min_edge_raw = st.slider("Min Edge Score (0–10+)", 0, 10, 0, 1, key="sb_edge")
    min_edge = min_edge_raw / 100

    show_only_vegas  = st.checkbox("Only games with Vegas lines", value=False, key="sb_vegas")
    show_only_differ = st.checkbox("Only SIDES DIFFER games",    value=False, key="sb_differ")
    show_only_dawgs  = st.checkbox("🐶 Only Dawgs (+ points)",   value=False, key="sb_dawgs")
    show_only_favs   = st.checkbox("⭐ Only Favorites (- points)",value=False, key="sb_favs")
    show_only_outs   = st.checkbox("🚑 Games with key OUT players",value=False, key="sb_outs")

    st.markdown("---")
    _ct      = datetime.now(CENTRAL)
    _today   = _ct.date()
    selected_date = st.date_input(
        "Game Date",
        value=_today,
        min_value=_today - timedelta(days=7),
        max_value=_today + timedelta(days=1),
        key="sb_date"
    )
    today_str = str(selected_date)
    st.markdown("---")

    if st.button("🔄 Refresh Data", use_container_width=True, key="sb_refresh"):
        st.cache_data.clear()
        st.rerun()

    if st.button("💊 Refresh Injuries Only", use_container_width=True, key="sb_refresh_inj"):
        # Only clear the injury cache — keeps heavier data cached
        get_todays_injuries.clear()
        get_player_data.clear()
        run_base_projections.clear()
        st.rerun()

    st.markdown("---")
    if not ODDS_OK:
        st.markdown(
            "<span style='font-size:0.72rem;color:#f0a429;'>📡 <b>Vegas lines:</b> not connected — "
            "add <code>odds_fetcher.py</code> to enable edge scoring</span>",
            unsafe_allow_html=True
        )
    else:
        st.markdown("<span style='font-size:0.72rem;color:#5ddc7a;'>📡 Vegas lines: connected</span>", unsafe_allow_html=True)
    st.markdown("<span style='font-size:0.72rem;color:#4a6fa5;'>Player data: on/off splits + live injury report<br>Lineup adjustments applied automatically</span>", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════════
#  HEADER
# ═══════════════════════════════════════════════════════════════════════════════
st.markdown(
    f"<h1 style='color:#f0b429;margin-bottom:2px;margin-top:0;'>CZARP {league} MODEL</h1>",
    unsafe_allow_html=True
)
st.markdown(
    f"<p style='color:#4a6fa5;margin-top:0;'>{selected_date.strftime('%A, %B %d, %Y')}"
    f" &nbsp;·&nbsp; Lineup-adjusted projections with live injury data</p>",
    unsafe_allow_html=True
)

if not MODULES_OK:
    st.stop()

# ── Load projections ──────────────────────────────────────────────────────────
with st.spinner(f"Loading {league} projections..."):
    try:
        results = run_projections(league, today_str)
        if not results:
            st.cache_data.clear()
            results = run_projections(league, today_str)
    except Exception as e:
        st.error(f"Error loading {league} projections for {today_str}: {e}")
        st.stop()

if not results:
    st.warning(f"No {league} games found for {today_str}. Try a different date or hit Refresh Data.")
    st.stop()


# ═══════════════════════════════════════════════════════════════════════════════
#  TABS
# ═══════════════════════════════════════════════════════════════════════════════
tab1, tab2, tab3 = st.tabs([f"🏆 {league} Daily Projections", "🚑 Injury Report", "🔬 Simulator"])


# ─────────────────────────────────────────────────────────────────────────────
#  TAB 1 — DAILY PROJECTIONS
# ─────────────────────────────────────────────────────────────────────────────
with tab1:
    # ── Metrics row ────────────────────────────────────────────────────────────
    games_with_vegas = [r for r in results if r.get("vegas_spread") is not None]
    high_edge        = [r for r in results if (r.get("edge_score") or 0) >= 0.05]
    avg_total        = round(sum(r["total"] for r in results) / len(results), 1)
    valid_edges      = [r.get("edge_score") for r in results if r.get("edge_score") is not None]
    avg_edge         = round(sum(valid_edges) / len(valid_edges) * 100, 2) if valid_edges else 0.0

    # Count games with at least one OUT player
    games_with_outs  = [r for r in results if r.get("player_impact", {}).get("t1_out") or r.get("player_impact", {}).get("t2_out")]

    c1, c2, c3, c4, c5, c6 = st.columns(6)
    c1.metric(f"{league} Games", len(results))
    c2.metric("With Vegas Lines", len(games_with_vegas))
    with c3:
        if st.button(f"🔥 High Edge (≥5%)\n{len(high_edge)} games", key="btn_high_edge", use_container_width=True):
            st.session_state["sb_edge"] = 5
            st.rerun()
        st.markdown("<div style='font-size:0.7rem;color:#4a6fa5;margin-top:-8px;text-align:center;'>click to filter</div>", unsafe_allow_html=True)
    c4.metric("Avg Edge Score", f"{avg_edge:.2f}")
    c5.metric("Avg Total", avg_total)
    c6.metric("🚑 Games w/ OUTs", len(games_with_outs))

    st.markdown("<hr class='divider'>", unsafe_allow_html=True)

    # ── Sort & Filter ──────────────────────────────────────────────────────────
    team_search = st.session_state.get("team_search_nba", "").strip().lower()

    if sort_by == "Edge Score":
        results = sorted(results, key=lambda r: r.get("edge_score") or 0, reverse=True)
    elif sort_by == "Total":
        results = sorted(results, key=lambda r: r["total"], reverse=True)
    elif sort_by == "Spread (biggest fav)":
        results = sorted(results, key=lambda r: abs(r["spread"]), reverse=True)
    else:
        results = sorted(results, key=lambda r: r["team1"])

    if show_only_vegas:
        results = [r for r in results if r.get("vegas_spread") is not None]
    if min_edge > 0:
        results = [r for r in results if (r.get("edge_score") or 0) >= min_edge]
    if show_only_differ:
        results = [r for r in results if r.get("sides_agree") is False]
    if show_only_outs:
        results = [r for r in results if
                   r.get("player_impact", {}).get("t1_out") or
                   r.get("player_impact", {}).get("t2_out")]
    if show_only_dawgs:
        def _is_dawg(r):
            vs, vf, my_s = r.get("vegas_spread"), r.get("vegas_fav"), r.get("spread", 0)
            if vs is None or vf is None: return False
            return (vf == r.get("team1") and my_s < 0) or (vf == r.get("team2") and my_s > 0)
        results = [r for r in results if _is_dawg(r)]
    if show_only_favs:
        def _is_fav(r):
            vs, vf, my_s = r.get("vegas_spread"), r.get("vegas_fav"), r.get("spread", 0)
            if vs is None or vf is None: return False
            return (vf == r.get("team1") and my_s > 0) or (vf == r.get("team2") and my_s < 0)
        results = [r for r in results if _is_fav(r)]
    if team_search:
        results = [r for r in results if
                   team_search in r["team1"].lower() or team_search in r["team2"].lower()]

    # ── Game Cards ──────────────────────────────────────────────────────────────
    st.markdown("<div class='section-title'>TODAY'S PROJECTIONS</div>", unsafe_allow_html=True)
    st.text_input("", placeholder=f"🔍 Search {league} team name — filters as you type",
                  key="team_search_nba", label_visibility="collapsed")

    if not results:
        st.info("No games match your filters.")
    else:
        for r in results:
            edge     = r.get("edge_score")
            disagree = r.get("sides_agree") is False
            pi       = r.get("player_impact", {})
            t1_out   = pi.get("t1_out", [])
            t2_out   = pi.get("t2_out", [])
            t1_gtd   = pi.get("t1_gtd", [])
            t2_gtd   = pi.get("t2_gtd", [])

            home_name = r["team1"]
            away_name = r["team2"]
            h_score   = r["team1_score"]
            a_score   = r["team2_score"]
            h_wins    = h_score >= a_score

            epct = f"{edge*100:.2f}%" if edge else ""
            if disagree and edge and edge >= 0.05:
                badge_cls, badge_txt = "edge-diff", f"SIDES DIFFER  {epct}"
            elif edge and edge >= 0.07:
                badge_cls, badge_txt = "edge-hot",  f"HOT EDGE  {epct}"
            elif edge and edge >= 0.05:
                badge_cls, badge_txt = "edge-good", f"EDGE  {epct}"
            elif edge and edge > 0:
                badge_cls, badge_txt = "edge-low",  f"EDGE {epct}"
            else:
                badge_cls, badge_txt = "edge-low",  "NO LINE"

            # CZarp side label
            s = r["spread"]
            if s > 0:   czarp_side = f"{home_name} -{abs(s):.1f}"
            elif s < 0: czarp_side = f"{away_name} -{abs(s):.1f}"
            else:       czarp_side = "EVEN"

            vs  = r.get("vegas_spread")
            vf  = r.get("vegas_fav") or "—"
            vt  = r.get("vegas_total")
            se  = r.get("spread_edge")
            gt  = r.get("game_time") or ""
            loc = r.get("location", "")
            arena = r.get("arena") or ""
            arena_txt = f" · {arena}" if arena else ""

            # OUT/GTD summary for card header
            out_strs, gtd_strs = [], []
            for p in t1_out: out_strs.append(f"{home_name[:3].upper()} {p['name'].split()[-1]}")
            for p in t2_out: out_strs.append(f"{away_name[:3].upper()} {p['name'].split()[-1]}")
            for p in t1_gtd: gtd_strs.append(f"{home_name[:3].upper()} {p['name'].split()[-1]}")
            for p in t2_gtd: gtd_strs.append(f"{away_name[:3].upper()} {p['name'].split()[-1]}")
            injury_line = ""
            if out_strs:  injury_line += f"<span style='color:#e05c5c;font-size:0.68rem;font-weight:600;'>🚫 OUT: {', '.join(out_strs)}</span>  "
            if gtd_strs:  injury_line += f"<span style='color:#f0a429;font-size:0.68rem;'>❓ GTD: {', '.join(gtd_strs)}</span>"

            card_html = f"""
<div class='game-card'>
  <div style='display:flex;justify-content:space-between;align-items:flex-start;'>
    <div>
      <div class='game-time'>{gt}{arena_txt}</div>
      {f"<div style='margin-bottom:4px;'>{injury_line}</div>" if injury_line else ""}
      <div class='team-row'>
        <span class='team-name'>{away_name}<span class='team-label'>AWAY</span></span>
        <span class='team-score {'team-score-winner' if not h_wins else ''}'>{a_score:.0f}</span>
      </div>
      <div class='team-row'>
        <span class='team-name'>{home_name}<span class='team-label'>HOME</span></span>
        <span class='team-score {'team-score-winner' if h_wins else ''}'>{h_score:.0f}</span>
      </div>
    </div>
    <div style='text-align:right;padding-top:4px;'>
      <span class='edge-badge {badge_cls}'>{badge_txt}</span>
    </div>
  </div>
  <div class='game-meta'>
    <div class='meta-item'><span class='meta-label'>CZarp Side</span><span class='meta-val-spread'>{czarp_side}</span></div>
    <div class='meta-item'><span class='meta-label'>CZarp Total</span><span class='meta-val'>{r['total']:.0f}</span></div>
    <div class='meta-item'><span class='meta-label'>Vegas Spread</span><span class='meta-val'>{_fmt_spread(vs)} ({vf})</span></div>
    <div class='meta-item'><span class='meta-label'>Vegas Total</span><span class='meta-val'>{f'{vt:.1f}' if vt else '—'}</span></div>
    <div class='meta-item'><span class='meta-label'>Swing</span><span class='meta-val {'meta-val-hot' if se and abs(se)>=5 else ''}'>{_fmt_spread(se) if se else '—'}</span></div>
    <div class='meta-item'><span class='meta-label'>Pace</span><span class='meta-val'>{r.get('projected_pace', 0):.0f} poss</span></div>
    <div class='meta-item'><span class='meta-label'>Location</span><span class='meta-val'>{loc.upper()}</span></div>
  </div>
</div>"""
            st.markdown(card_html, unsafe_allow_html=True)

            with st.expander("Full Breakdown", expanded=False):
                _tab_breakdown, _tab_lineup, _tab_prediction = st.tabs(["📊 Breakdown", "👥 Lineups", "🔮 Prediction"])

                with _tab_breakdown:
                    table_html = build_breakdown_table(r, home_name, away_name)
                    components.html(f"""
<html><head><style>
  body{{margin:0;padding:0;font-family:'Inter',sans-serif;background:#0f1e3d;}}
  table{{width:100%;border-collapse:collapse;color:#e8e8e8;}}
  tr:hover td{{background:rgba(255,255,255,0.04);}}
</style></head>
<body style="background:#0f1e3d;padding:12px;border-radius:10px;border:1px solid #1e3a6e;">
  {table_html}
</body></html>""", height=580, scrolling=False)

                with _tab_lineup:
                    t1_lineup = pi.get("t1_lineup", [])
                    t2_lineup = pi.get("t2_lineup", [])
                    t1_oe_adj = pi.get("t1_oe_adjustment", 0) or 0
                    t2_oe_adj = pi.get("t2_oe_adjustment", 0) or 0
                    t1_de_adj = pi.get("t1_de_adjustment", 0) or 0
                    t2_de_adj = pi.get("t2_de_adjustment", 0) or 0

                    if t1_lineup or t2_lineup:
                        lc1, lc2 = st.columns(2)
                        with lc1:
                            if t1_lineup:
                                components.html(f"""
<html><head><style>
  body{{margin:0;padding:8px;background:#0f1e3d;font-family:'Inter',sans-serif;color:#e8e8e8;}}
  .player-out{{color:#e05c5c;font-weight:700;font-size:0.72rem;}}
  .player-gtd{{color:#f0a429;font-weight:600;font-size:0.72rem;}}
  .player-active{{color:#5ddc7a;font-size:0.72rem;}}
  .impact-positive{{color:#5ddc7a;}}
  .impact-negative{{color:#e05c5c;}}
</style></head>
<body>{build_lineup_html(t1_lineup, home_name, t1_oe_adj, t1_de_adj)}</body></html>""",
                                height=280, scrolling=True)
                        with lc2:
                            if t2_lineup:
                                components.html(f"""
<html><head><style>
  body{{margin:0;padding:8px;background:#0f1e3d;font-family:'Inter',sans-serif;color:#e8e8e8;}}
  .player-out{{color:#e05c5c;font-weight:700;font-size:0.72rem;}}
  .player-gtd{{color:#f0a429;font-weight:600;font-size:0.72rem;}}
  .player-active{{color:#5ddc7a;font-size:0.72rem;}}
  .impact-positive{{color:#5ddc7a;}}
  .impact-negative{{color:#e05c5c;}}
</style></head>
<body>{build_lineup_html(t2_lineup, away_name, t2_oe_adj, t2_de_adj)}</body></html>""",
                                height=280, scrolling=True)
                    else:
                        st.info("Player data not loaded. Click 'Refresh Data' to fetch on/off splits and injury report.")

                with _tab_prediction:
                    blurb = generate_prediction_blurb(r, home_name=home_name, away_name=away_name)
                    st.markdown(blurb, unsafe_allow_html=True)

    # ── Full Table ──────────────────────────────────────────────────────────────
    st.markdown("<div class='section-title'>FULL TABLE</div>", unsafe_allow_html=True)
    table_rows = []
    for r in results:
        s    = r["spread"]
        pi_r = r.get("player_impact", {})
        czarp_t = f"{(r['team1'] if s>0 else r['team2'])[:18]} {-abs(s):+.1f}" if s != 0 else "EVEN"
        vs   = r.get("vegas_spread")
        vfav = r.get("vegas_fav")
        vtxt = f"{vfav[:18]} {-abs(vs):+.1f}" if (vs and vs != 0 and vfav) else ("EVEN" if vs == 0 else "—")
        outs = ", ".join(p["name"] for p in pi_r.get("t1_out", []) + pi_r.get("t2_out", []))
        table_rows.append({
            "Time":         r.get("game_time") or "",
            "Away":         r["team2"],
            "Home":         r["team1"],
            "Away Score":   r["team2_score"],
            "Home Score":   r["team1_score"],
            "CZarp Spread": czarp_t,
            "CZarp Total":  r["total"],
            "Vegas Spread": vtxt,
            "Vegas Total":  r.get("vegas_total") or "",
            "Swing":        r.get("spread_edge") or "",
            "Edge":         round(r.get("edge_score") or 0, 4),
            "Differ":       "YES" if r.get("sides_agree") is False else "",
            "Key OUTs":     outs,
        })
    st.dataframe(pd.DataFrame(table_rows), use_container_width=True, hide_index=True)
    st.markdown(
        f"<div style='margin-top:40px;padding-top:20px;border-top:1px solid #1e3a6e;font-size:0.75rem;color:#2e4a7a;text-align:center;'>"
        f"CZarp {league} Model &nbsp;·&nbsp; Last updated {datetime.now().strftime('%I:%M %p')}</div>",
        unsafe_allow_html=True
    )


# ─────────────────────────────────────────────────────────────────────────────
#  TAB 2 — INJURY REPORT
# ─────────────────────────────────────────────────────────────────────────────
with tab2:
    st.markdown(f"<div class='section-title'>TODAY'S {league} INJURY REPORT</div>", unsafe_allow_html=True)
    st.markdown(f"<p style='color:#4a6fa5;font-size:0.85rem;margin-top:-8px;'>Live data — refreshes every 5 minutes. Use '💊 Refresh Injuries Only' in sidebar for immediate update.</p>", unsafe_allow_html=True)

    injuries = get_todays_injuries(league)

    if injuries.empty:
        st.info(f"No injury data loaded. Click 'Refresh Data' in the sidebar to fetch the {league} injury report.")
    else:
        # Filter controls
        ic1, ic2 = st.columns(2)
        with ic1:
            status_filter = st.multiselect(
                "Filter by Status",
                options=["OUT", "QUESTIONABLE", "GTD", "PROBABLE", "AVAILABLE"],
                default=["OUT", "QUESTIONABLE", "GTD"],
                key="inj_status_filter"
            )
        with ic2:
            team_inj_filter = st.text_input("Filter by Team", placeholder="e.g. Lakers", key="inj_team_filter")

        df_inj = injuries.copy()
        if status_filter and "Status" in df_inj.columns:
            df_inj = df_inj[df_inj["Status"].str.upper().isin([s.upper() for s in status_filter])]
        if team_inj_filter and "TeamAbbr" in df_inj.columns:
            df_inj = df_inj[df_inj["TeamAbbr"].str.contains(team_inj_filter, case=False, na=False)]

        # Sort by: OUT first, then GTD, then rest
        if "Status" in df_inj.columns:
            status_order = {"OUT": 0, "QUESTIONABLE": 1, "GTD": 1, "PROBABLE": 2, "AVAILABLE": 3}
            df_inj["_sort"] = df_inj["Status"].str.upper().map(status_order).fillna(9)
            df_inj = df_inj.sort_values(["_sort", "TeamAbbr"]).drop(columns=["_sort"])

        # Show relevant columns
        show_cols = [c for c in ["PlayerName", "TeamAbbr", "Status", "Reason", "ReportDate"] if c in df_inj.columns]
        st.dataframe(df_inj[show_cols].reset_index(drop=True), use_container_width=True, hide_index=True)
        st.markdown(f"<p style='font-size:0.75rem;color:#4a6fa5;margin-top:8px;'>{len(df_inj)} players listed</p>", unsafe_allow_html=True)

        # Impact summary — show which projected games are affected
        st.markdown("<div class='section-title'>PROJECTED GAME IMPACT</div>", unsafe_allow_html=True)
        if results:
            impact_rows = []
            for r in results:
                pi_r   = r.get("player_impact", {})
                t1_out = pi_r.get("t1_out", [])
                t2_out = pi_r.get("t2_out", [])
                t1_gtd = pi_r.get("t1_gtd", [])
                t2_gtd = pi_r.get("t2_gtd", [])
                if not t1_out and not t2_out and not t1_gtd and not t2_gtd:
                    continue
                impact_rows.append({
                    "Matchup": f"{r['team2']} @ {r['team1']}",
                    "OUTs":    ", ".join(f"{r['team1'][:3]}: {p['name']}" for p in t1_out) +
                               ("  " if t1_out and t2_out else "") +
                               ", ".join(f"{r['team2'][:3]}: {p['name']}" for p in t2_out),
                    "GTDs":    ", ".join(f"{r['team1'][:3]}: {p['name']}" for p in t1_gtd) +
                               ("  " if t1_gtd and t2_gtd else "") +
                               ", ".join(f"{r['team2'][:3]}: {p['name']}" for p in t2_gtd),
                    "H OE Adj": f"{pi_r.get('t1_oe_adjustment', 0):+.2f}",
                    "A OE Adj": f"{pi_r.get('t2_oe_adjustment', 0):+.2f}",
                    "CZarp Spread": f"{r['spread']:+.1f}",
                    "Vegas Spread": _fmt_spread(r.get("vegas_spread")),
                })
            if impact_rows:
                st.dataframe(pd.DataFrame(impact_rows), use_container_width=True, hide_index=True)
            else:
                st.info("No active lineup adjustments found for today's games.")


# ─────────────────────────────────────────────────────────────────────────────
#  TAB 3 — SIMULATOR
# ─────────────────────────────────────────────────────────────────────────────
with tab3:
    st.markdown("<div class='section-title'>GAME SIMULATOR</div>", unsafe_allow_html=True)
    st.markdown("<p style='color:#4a6fa5;font-size:0.85rem;margin-top:-8px;'>Project any matchup using lineup-adjusted efficiency ratings</p>", unsafe_allow_html=True)

    try:
        sim_data = get_nba_team_data(league)
        name_col = "TeamName" if "TeamName" in sim_data["ratings"].columns else "TEAM_NAME"
        team_list = sorted(sim_data["ratings"][name_col].dropna().tolist())
    except Exception as e:
        st.error(f"Could not load {league} team list: {e}")
        team_list = []

    if team_list:
        st.markdown("<hr class='divider'>", unsafe_allow_html=True)

        with st.form("sim_form"):
            sc1, sc2, sc3 = st.columns([2, 2, 1])
            with sc1:
                away_team = st.selectbox("Away Team", team_list, index=min(1, len(team_list)-1), key="sim_away")
            with sc2:
                home_team = st.selectbox("Home Team", team_list, index=0, key="sim_home")
            with sc3:
                site = st.selectbox("Site", ["Home/Away", "Neutral"], index=0, key="sim_site")

            submitted = st.form_submit_button("▶ Run Projection", use_container_width=True, type="primary")

        if submitted:
            if home_team == away_team:
                st.warning("Please select two different teams.")
            else:
                try:
                    sim_full_data = get_nba_team_data(league)
                    player_d      = get_player_data(league)
                    injuries_sim  = get_todays_injuries(league)
                    sim_full_data["rotations"] = player_d.get("rotations", pd.DataFrame())
                    sim_full_data["injuries"]  = injuries_sim if not injuries_sim.empty else player_d.get("injuries", pd.DataFrame())

                    team1_is_home = None if site == "Neutral" else True
                    sim_r = project_game(
                        team1         = home_team,
                        team2         = away_team,
                        team1_is_home = team1_is_home,
                        data          = sim_full_data,
                        league        = league,
                    )

                    # Result cards
                    st.markdown("<hr class='divider'>", unsafe_allow_html=True)
                    h_s = sim_r["team1_score"]; a_s = sim_r["team2_score"]
                    spread = sim_r["spread"]
                    if spread > 0:   winner_txt = f"{home_team} -{abs(spread):.1f}"
                    elif spread < 0: winner_txt = f"{away_team} -{abs(spread):.1f}"
                    else:            winner_txt = "EVEN"

                    rc1, rc2, rc3, rc4 = st.columns(4)
                    rc1.metric(f"{away_team}", f"{a_s:.0f}")
                    rc2.metric(f"{home_team}", f"{h_s:.0f}")
                    rc3.metric("CZarp Spread", winner_txt)
                    rc4.metric("CZarp Total", f"{sim_r['total']:.0f}")

                    # Player impact summary
                    pi_sim = sim_r.get("player_impact", {})
                    if pi_sim.get("t1_out") or pi_sim.get("t2_out"):
                        all_outs = [(home_team, p) for p in pi_sim.get("t1_out", [])] + \
                                   [(away_team, p) for p in pi_sim.get("t2_out", [])]
                        out_parts = [f"**{tn}**: {p['name']}" for tn, p in all_outs]
                        st.warning(f"⚠️ Lineup adjustment applied — Players OUT: {' · '.join(out_parts)}")

                    # Breakdown + Lineup tabs
                    _sb1, _sb2, _sb3 = st.tabs(["📊 Breakdown", "👥 Lineups", "🔮 Prediction"])

                    with _sb1:
                        tbl = build_breakdown_table(sim_r, home_team, away_team)
                        components.html(f"""
<html><head><style>
  body{{margin:0;padding:0;font-family:'Inter',sans-serif;background:#0f1e3d;}}
  table{{width:100%;border-collapse:collapse;color:#e8e8e8;}}
  tr:hover td{{background:rgba(255,255,255,0.04);}}
</style></head>
<body style="background:#0f1e3d;padding:12px;border-radius:10px;border:1px solid #1e3a6e;">
  {tbl}
</body></html>""", height=600, scrolling=True)

                    with _sb2:
                        t1_lu = pi_sim.get("t1_lineup", [])
                        t2_lu = pi_sim.get("t2_lineup", [])
                        if t1_lu or t2_lu:
                            lc1, lc2 = st.columns(2)
                            css_inj = "<style>.player-out{color:#e05c5c;font-weight:700;font-size:.72rem;}.player-gtd{color:#f0a429;font-weight:600;font-size:.72rem;}.player-active{color:#5ddc7a;font-size:.72rem;}.impact-positive{color:#5ddc7a;}.impact-negative{color:#e05c5c;}</style>"
                            with lc1:
                                if t1_lu:
                                    h_html = build_lineup_html(t1_lu, home_team, pi_sim.get("t1_oe_adjustment",0), pi_sim.get("t1_de_adjustment",0))
                                    components.html(f"<html><head>{css_inj}</head><body style='margin:0;padding:8px;background:#0f1e3d;color:#e8e8e8;font-family:Inter,sans-serif;'>{h_html}</body></html>", height=260, scrolling=True)
                            with lc2:
                                if t2_lu:
                                    a_html = build_lineup_html(t2_lu, away_team, pi_sim.get("t2_oe_adjustment",0), pi_sim.get("t2_de_adjustment",0))
                                    components.html(f"<html><head>{css_inj}</head><body style='margin:0;padding:8px;background:#0f1e3d;color:#e8e8e8;font-family:Inter,sans-serif;'>{a_html}</body></html>", height=260, scrolling=True)
                        else:
                            st.info("Player data not available. Click Refresh Data to load on/off splits.")

                    with _sb3:
                        blurb = generate_prediction_blurb(sim_r, home_name=home_team, away_name=away_team)
                        st.markdown(blurb, unsafe_allow_html=True)

                except Exception as e:
                    st.error(f"Projection failed: {e}")
