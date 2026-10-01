"""
ShuttleIQ - data sanity checks on the ETL output. Read-only.
Usage:  python scripts/03_check_data.py
"""
import sys
from pathlib import Path
import pandas as pd

D = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "data"
stg = pd.read_csv(D / "staging" / "stg_matches.csv")
P = {n: pd.read_csv(D / "processed" / f"{n}.csv") for n in
     ["fact_match_result", "dim_team", "dim_player", "dim_country", "dim_event"]}
fact, team, player, country, event = (P[k] for k in
    ["fact_match_result", "dim_team", "dim_player", "dim_country", "dim_event"])
pd.set_option("display.width", 200, "display.max_colwidth", 60)

print("\n1) WINNER CONFLICTS (bold markup vs scores):")
c = stg[stg.winner_conflict == True]
print(c[["year", "event", "heading_path", "t1_raw", "t2_raw", "raw_scores"]].to_string() if len(c) else "  none")

print("\n2) SCORE CELLS WITH LETTERS (retired / walkover / odd text):")
o = stg[stg.raw_scores.fillna("").str.contains("[A-Za-z]")]
print(o[["year", "event", "raw_scores", "result_type"]].head(15).to_string() if len(o) else "  none")

print("\n3) MATCHES WITH FEWER THAN 2 GAMES OR ODD SCORES:")
g = fact[(fact.games_played < 2)].drop_duplicates("match_id")
print(g[["match_id", "games_played", "result_type"]].head(10).to_string() if len(g) else "  none")

print("\n4) SEEDED ROWS PER EVENT (expect ~16 seeds per event and year):")
ev = dict(zip(event.event_key, event.event_code))
s = fact.assign(ev=fact.event_key.map(ev), seeded=fact.team_seed.notna())
print(s.groupby(["tournament_key", "ev"]).seeded.sum().to_string())

print("\n5) TEAM / PLAYER SIZES:")
tt = team.merge(event, on="event_key")
print("  singles teams with size != 1:", int(((tt.discipline == "Singles") & (tt.team_size != 1)).sum()))
print("  doubles teams with size != 2:", int(((tt.discipline == "Doubles") & (tt.team_size != 2)).sum()))
bad = player[player.player_name.str.contains(r"\d|bye|tbd|\?", case=False, regex=True)]
print("  suspicious player names:", bad.player_name.tolist() or "none")
unk = country[country.ioc_code == "UNK"].country_key.iloc[0]
print("  players with UNK country:", int((player.country_key == unk).sum()))
odd = team.merge(event, on="event_key")
odd = odd[((odd.discipline == "Singles") & (odd.team_size != 1)) | ((odd.discipline == "Doubles") & (odd.team_size != 2))]
print("\n6) TEAMS WITH WRONG SIZE:")
print(odd[["event_code", "team_name", "team_size"]].to_string() if len(odd) else "  none")
print("\n7) PLAYERS WITH UNKNOWN COUNTRY (first 15):")
ux = player[player.country_key == unk].player_name.tolist()
print(" ", ux[:15] if ux else "none")
print("\n8) RESULT TYPES (matches):")
print(fact.drop_duplicates("match_id").result_type.value_counts().to_string())
print(f"  totals: {len(player)} players, {len(team)} teams, {len(fact)//2} matches")
