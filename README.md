# CZarp NBA / WNBA Betting Model

Lineup-adjusted NBA and WNBA game projections with live injury data.
Sister repo to `czarp-cbb` — same core formulas, new player impact layer.

## What's Different from the CBB Model

| Feature | CBB (`czarp-cbb`) | NBA (`czarp-nba`) |
|---|---|---|
| Data source | KenPom (subscription) | NBA Stats API (free) |
| Player layer | None (team season avgs) | On/off splits + injury report |
| HCA | 3.5 pts | 2.5 pts |
| Schedule | KenPom fanmatch | NBA Stats scoreboardv2 |
| Leagues | NCAA D-I | NBA + WNBA |

## File Structure

```
czarp-nba/
  app_nba.py          ← Streamlit dashboard (this file is the entry point)
  nba_model.py        ← Core projection formulas + player impact layer
  nba_fetcher.py      ← Team ratings, four factors, schedule from NBA Stats API
  player_fetcher.py   ← On/off splits, player stats, injury report
  run_nba.py          ← CLI batch runner (optional — app handles fetching too)
  requirements.txt
  data/               ← Created automatically on first run
  outputs/            ← Projection CSVs saved here
```

## Quick Start (Local)

```bash
git clone https://github.com/YOUR_USERNAME/czarp-nba
cd czarp-nba
pip install -r requirements.txt
streamlit run app_nba.py
```

On first load, the app fetches all data automatically. Subsequent loads use
Streamlit's cache (1hr for team data, 5min for injuries).

## Deploy to Streamlit Cloud

1. Push this repo to GitHub
2. Go to [share.streamlit.io](https://share.streamlit.io)
3. New app → select your repo → **Main file: `app_nba.py`**
4. Deploy

No secrets or API keys needed — NBA Stats API is public.

## Data Sources

| Data | Source | Refresh Rate |
|---|---|---|
| Team efficiency (AdjOE, AdjDE, Pace) | `stats.nba.com/leaguedashteamstats` | Hourly |
| Four factors | `stats.nba.com/leaguedashteamstats` | Hourly |
| Player on/off splits | `stats.nba.com/leaguedashplayeronoffdetails` | Hourly |
| Player minutes/usage | `stats.nba.com/leaguedashplayerstats` | Hourly |
| Today's schedule | `stats.nba.com/scoreboardv2` | Every 15 min |
| Injury report | ESPN injury API | Every 5 min |
| Vegas lines | Your odds provider (configure in `odds_fetcher.py`) | Every 15 min |

## The Player Impact Layer

The key difference from the CBB model. Instead of using raw season-average
efficiency for each team, the model adjusts AdjOE and AdjDE based on tonight's
active lineup:

```
for each player in rotation:
    if player is OUT:    remove their minutes, redistribute to next-man-up
    if player is GTD:    apply 50% probability of playing
    
lineup_oe_adj = sum(player_off_impact × adjusted_min_share) × IMPACT_SCALE
effective_oe  = season_AdjOE + lineup_oe_adj
ppp           = (effective_oe + opp_effective_de) / 2 / 100
```

`off_impact` = the team's OffRtg when this player is on the floor minus when
they're off (on/off split from NBA Stats API).

`IMPACT_SCALE = 0.85` — tuning knob. A missing starter with `off_impact = +4.0`
and `min_share = 0.38` shifts the line approximately 1.3 pts per team side
(~2.6 pts total swing). Adjust this as you calibrate against results.

## WNBA Notes

- Switch league in the sidebar radio button: **NBA / WNBA**
- WNBA season: May–October (36 games, smaller sample)
- Data thins out early in the season — model is less reliable before ~game 10
- Edge threshold: consider raising to 8%+ for WNBA vs 5% for NBA

## Calibration Notes

The model systematically undershoots spread magnitude (same as CBB). This is
expected — Vegas prices in context the model doesn't have (travel, rest days,
rivalry, motivation). The model's job is direction + finding edge vs the line,
not replicating the exact number.

After 50+ games of results, re-tune `IMPACT_SCALE` in `nba_model.py` based on
how often large lineup adjustments correctly predicted the outcome direction.
