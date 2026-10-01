"""
ShuttleIQ - ETL: RAW wikitext  ->  STAGING  ->  CLEAN dimensional model  ->  MySQL

  extract   data/raw/wikipedia/wikitext/*.wikitext          (untouched raw pages)
  stage     data/staging/stg_matches.csv                    (one parsed row per bracket match, raw strings kept)
  transform data/processed/*.csv                            (dimension + fact tables, surrogate keys)
  load      MySQL database `shuttleiq` (sql/schema.sql)

Usage (from project root):
    python scripts/02_etl_load.py --no-db      # build CSVs + data-quality report only
    python scripts/02_etl_load.py              # also load MySQL (asks for the password)
Environment variables (optional): MYSQL_HOST, MYSQL_PORT, MYSQL_USER, MYSQL_PASSWORD
"""
import argparse
import getpass
import os
import re
import sys
from collections import Counter
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from parse_wikitext import extract_brackets, parse_bracket, parse_seed_list  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent

FILE_RE = re.compile(r"^(\d{4})_BWF_World_Championships_(Men_s|Women_s|Mixed)_(singles|doubles)\.wikitext$")
EVENTS = {
    ("Men_s", "singles"): ("MS", "Men's singles", "Singles", "Men"),
    ("Women_s", "singles"): ("WS", "Women's singles", "Singles", "Women"),
    ("Men_s", "doubles"): ("MD", "Men's doubles", "Doubles", "Men"),
    ("Women_s", "doubles"): ("WD", "Women's doubles", "Doubles", "Women"),
    ("Mixed", "doubles"): ("XD", "Mixed doubles", "Doubles", "Mixed"),
}
TOURNAMENTS = {
    2025: ("TotalEnergies BWF World Championships 2025", "Paris", "France", "2025-08-25", "2025-08-31"),
    2026: ("BWF World Championships 2026", "New Delhi", "India", "2026-08-17", "2026-08-23"),
}
ROUNDS = {1: "Final", 2: "Semi-finals", 3: "Quarter-finals", 4: "Round of 16",
          5: "Round of 32", 6: "Round of 64"}
COUNTRIES = {  # ioc: (name, continent) - codes exactly as used by the {{flagicon}} template
    "CHN": ("China", "Asia"), "JPN": ("Japan", "Asia"), "KOR": ("South Korea", "Asia"),
    "INA": ("Indonesia", "Asia"), "MAS": ("Malaysia", "Asia"), "THA": ("Thailand", "Asia"),
    "IND": ("India", "Asia"), "TPE": ("Chinese Taipei", "Asia"), "HKG": ("Hong Kong", "Asia"),
    "SIN": ("Singapore", "Asia"), "VIE": ("Vietnam", "Asia"), "PHI": ("Philippines", "Asia"),
    "MAC": ("Macau", "Asia"), "SRI": ("Sri Lanka", "Asia"), "PAK": ("Pakistan", "Asia"),
    "NEP": ("Nepal", "Asia"), "KAZ": ("Kazakhstan", "Asia"), "UAE": ("United Arab Emirates", "Asia"),
    "AZE": ("Azerbaijan", "Europe"), "DEN": ("Denmark", "Europe"), "FRA": ("France", "Europe"),
    "GER": ("Germany", "Europe"), "ENG": ("England", "Europe"), "SCO": ("Scotland", "Europe"),
    "WAL": ("Wales", "Europe"), "NED": ("Netherlands", "Europe"), "ESP": ("Spain", "Europe"),
    "ITA": ("Italy", "Europe"), "BUL": ("Bulgaria", "Europe"), "UKR": ("Ukraine", "Europe"),
    "IRL": ("Ireland", "Europe"), "SUI": ("Switzerland", "Europe"), "POL": ("Poland", "Europe"),
    "CZE": ("Czech Republic", "Europe"), "TUR": ("Turkey", "Europe"), "AUT": ("Austria", "Europe"),
    "BEL": ("Belgium", "Europe"), "SWE": ("Sweden", "Europe"), "FIN": ("Finland", "Europe"),
    "NOR": ("Norway", "Europe"), "EST": ("Estonia", "Europe"), "LTU": ("Lithuania", "Europe"),
    "LAT": ("Latvia", "Europe"), "POR": ("Portugal", "Europe"), "SLO": ("Slovenia", "Europe"),
    "CRO": ("Croatia", "Europe"), "HUN": ("Hungary", "Europe"), "ISL": ("Iceland", "Europe"),
    "CAN": ("Canada", "North America"), "USA": ("United States", "North America"),
    "MEX": ("Mexico", "North America"), "GUA": ("Guatemala", "North America"),
    "BRA": ("Brazil", "South America"), "PER": ("Peru", "South America"),
    "AUS": ("Australia", "Oceania"), "NZL": ("New Zealand", "Oceania"),
    "EGY": ("Egypt", "Africa"), "RSA": ("South Africa", "Africa"), "UGA": ("Uganda", "Africa"),
    "NGR": ("Nigeria", "Africa"), "ALG": ("Algeria", "Africa"), "MRI": ("Mauritius", "Africa"),
    "ESA": ("El Salvador", "North America"), "ISR": ("Israel", "Asia"),
    "SRB": ("Serbia", "Europe"), "MYA": ("Myanmar", "Asia"),
    "AIN": ("Individual Neutral Athletes", "Neutral"),
    "UNK": ("Unknown", "Unknown"),
}
# Wikipedia uses several codes for the same country -> merge to one canonical code
CODE_ALIASES = {"SGP": "SIN", "IRE": "IRL", "SWI": "SUI"}


def extract_and_stage(wiki_dir):
    """Parse every wikitext page -> staging rows + seed maps."""
    stg, seed_map, seed_rows = [], {}, []
    files = sorted(p for p in Path(wiki_dir).glob("*.wikitext") if FILE_RE.match(p.name))
    if not files:
        sys.exit(f"No event wikitext files found in {wiki_dir}. Run scripts/01b_fetch_wikipedia.py first.")
    for path in files:
        year, gender, disc = FILE_RE.match(path.name).groups()
        year = int(year)
        code = EVENTS[(gender, disc)][0]
        text = path.read_text(encoding="utf-8")
        for s in parse_seed_list(text):
            seed_map[(year, code, tuple(sorted(s["players"])))] = s["seed"]
            seed_rows.append({"year": year, "event": code, **s, "players": " / ".join(s["players"])})
        for br in extract_brackets(text):
            for m in parse_bracket(br):
                stg.append({
                    "year": year, "event": code, "source_file": path.name,
                    "bracket_index": m["bracket_index"], "heading_path": m["heading_path"],
                    "template": m["template"], "round_label": m["round_label"],
                    "stage_from_final": m["stage_from_final"], "match_no": m["match_no"],
                    "t1_raw": m["team1"]["raw"], "t2_raw": m["team2"]["raw"],
                    "raw_scores": m["raw_scores"], "result_type": m["result_type"],
                    "winner_conflict": m["winner_conflict"], "winner": m["winner"],
                    "_m": m,
                })
    return stg, seed_map, pd.DataFrame(seed_rows)


def resolve_plain_names(stg):
    """Plain-text players (no wiki link, e.g. 'N G Chan') -> full name of a linked player of the
    same country when initials + surname match exactly one candidate. Returns #resolved."""
    known = {}
    for row in stg:
        for t in (row["_m"]["team1"], row["_m"]["team2"]):
            for n in t["players"]:
                if n not in t["plain"]:
                    known.setdefault(t["country"], set()).add(n)
    resolved = 0
    for row in stg:
        for t in (row["_m"]["team1"], row["_m"]["team2"]):
            if not t["plain"]:
                continue
            out = []
            for n in t["players"]:
                if n in t["plain"]:
                    toks = n.replace("-", " ").split()
                    cands = []
                    if len(toks) >= 2:
                        sur, ini = toks[-1].lower(), [x[0].lower() for x in toks[:-1]]
                        for full in known.get(t["country"], ()):
                            ft = full.replace("-", " ").split()
                            if ft[-1].lower() == sur and [x[0].lower() for x in ft[:-1]][:len(ini)] == ini:
                                cands.append(full)
                    if len(cands) == 1:
                        n = cands[0]
                        resolved += 1
                out.append(n)
            t["players"] = out
    return resolved


def transform(stg, seed_map):
    country_keys = {c: i for i, c in enumerate(COUNTRIES, 1)}
    dim_country = pd.DataFrame(
        [(country_keys[c], c, n, k) for c, (n, k) in COUNTRIES.items()],
        columns=["country_key", "ioc_code", "country_name", "continent"])
    dim_tournament = pd.DataFrame(
        [(i, *TOURNAMENTS[y][:1], y, *TOURNAMENTS[y][1:]) for i, y in enumerate(sorted(TOURNAMENTS), 1)],
        columns=["tournament_key", "tournament_name", "edition_year", "host_city",
                 "host_country", "start_date", "end_date"])
    t_key = {y: i for i, y in enumerate(sorted(TOURNAMENTS), 1)}
    dim_event = pd.DataFrame(
        [(i, *v) for i, v in enumerate(EVENTS.values(), 1)],
        columns=["event_key", "event_code", "event_name", "discipline", "gender_category"])
    e_key = dict(zip(dim_event.event_code, dim_event.event_key))
    dim_round = pd.DataFrame(
        [(s, s, n, "Business end" if s <= 3 else "Early rounds") for s, n in ROUNDS.items()],
        columns=["round_key", "stage_from_final", "round_name", "round_group"])

    players, teams, bridge, facts, rejects = {}, {}, set(), [], []
    unknown_codes = Counter()

    def cty(code):
        code = CODE_ALIASES.get(code or "UNK", code or "UNK")
        if code not in country_keys:
            unknown_codes[code] += 1
            code = "UNK"
        return country_keys[code]

    def team_key(event, team):
        names = tuple(sorted(team["players"]))
        ck = cty(team["country"])
        key = (event, names)
        if key not in teams:
            teams[key] = {"team_key": len(teams) + 1, "event_key": e_key[event],
                          "team_name": " / ".join(team["players"]), "team_size": len(names),
                          "country_key": ck}
            for n in names:
                pk = (n, ck)
                if pk not in players:
                    players[pk] = {"player_key": len(players) + 1, "player_name": n, "country_key": ck}
                bridge.add((teams[key]["team_key"], players[pk]["player_key"]))
        return teams[key]["team_key"], names

    for row in stg:
        m, year, event = row["_m"], row["year"], row["event"]
        if m["result_type"] in ("Unplayed", "Unresolved") or m["winner"] is None:
            rejects.append({**{k: v for k, v in row.items() if k != "_m"}, "reason": m["result_type"]})
            continue
        if m["stage_from_final"] not in ROUNDS:
            rejects.append({**{k: v for k, v in row.items() if k != "_m"}, "reason": "unknown round stage"})
            continue
        sides = []
        for t in (m["team1"], m["team2"]):
            tk, names = team_key(event, t)
            seed = t["seed"] if t["seed"] is not None else seed_map.get((year, event, names))
            sides.append((tk, seed))
        pts = list(m["games"])                       # completed games
        allpts = pts + ([m["partial_game"]] if m["partial_game"] else [])   # + game stopped by retirement
        gw = [m["gw1"], m["gw2"]]
        pw = [sum(a for a, _ in allpts), sum(b for _, b in allpts)]
        deuce = sum(1 for a, b in pts if max(a, b) > 21)
        w = m["winner"] - 1
        rank = [s if s is not None else 99 for _, s in sides]
        upset = int(rank[w] > rank[1 - w] and rank[1 - w] < 99)
        match_id = f"{year}-{event}-B{m['bracket_index']:02d}-S{m['stage_from_final']}-M{m['match_no']:02d}"
        for i in (0, 1):
            j = 1 - i
            facts.append({
                "match_id": match_id, "tournament_key": t_key[year], "event_key": e_key[event],
                "round_key": m["stage_from_final"], "team_key": sides[i][0],
                "opponent_team_key": sides[j][0], "team_seed": sides[i][1],
                "opponent_seed": sides[j][1], "is_winner": int(i == w),
                "games_won": gw[i], "games_lost": gw[j], "points_won": pw[i], "points_lost": pw[j],
                "games_played": len(allpts), "deciding_game_played": int(len(allpts) == 3),
                "deuce_games": deuce, "is_upset": upset, "result_type": m["result_type"],
                "bracket_section": m["heading_path"][:60],
            })
    fact = pd.DataFrame(facts)
    fact.insert(0, "result_key", range(1, len(fact) + 1))
    for c in ("team_seed", "opponent_seed"):
        fact[c] = fact[c].astype("Int64")
    return {
        "dim_country": dim_country, "dim_tournament": dim_tournament, "dim_event": dim_event,
        "dim_round": dim_round,
        "dim_player": pd.DataFrame(players.values()),
        "dim_team": pd.DataFrame(teams.values()),
        "bridge_team_player": pd.DataFrame(sorted(bridge), columns=["team_key", "player_key"]),
        "fact_match_result": fact,
    }, pd.DataFrame(rejects), unknown_codes


def dq_report(stg, tables, rejects, unknown_codes, seeds_df):
    f = tables["fact_match_result"]
    lines = ["ShuttleIQ - DATA QUALITY REPORT", "=" * 60,
             f"Matches parsed from raw brackets : {len(stg)}",
             f"Matches loaded to fact table      : {len(f) // 2}  ({len(f)} rows, 2 per match)",
             f"Rejected (unplayed/unresolved)    : {len(rejects)}",
             f"Winner disagrees with bold markup : {sum(1 for r in stg if r['winner_conflict'])}",
             f"Retirements / walkovers           : {int((f.result_type.isin(['Retired', 'Walkover'])).sum() // 2)}",
             f"Unknown country codes (-> UNK)    : {dict(unknown_codes) or 'none'}",
             f"Rows with no seed info            : {int(f.team_seed.isna().sum())} of {len(f)}",
             "", "Matches per event and edition (singles full draw = 63):"]
    cnt = f.groupby(["tournament_key", "event_key"]).size().div(2).astype(int)
    ev = dict(zip(tables["dim_event"].event_key, tables["dim_event"].event_code))
    yr = dict(zip(tables["dim_tournament"].tournament_key, tables["dim_tournament"].edition_year))
    for (t, e), n in cnt.items():
        lines.append(f"  {yr[t]} {ev[e]}: {n}")
    return "\n".join(lines)


def load_mysql(tables, args):
    from sqlalchemy import create_engine, text
    host = args.host or os.getenv("MYSQL_HOST", "localhost")
    port = args.port or os.getenv("MYSQL_PORT", "3306")
    user = args.user or os.getenv("MYSQL_USER", "root")
    pw = os.getenv("MYSQL_PASSWORD") or getpass.getpass(f"MySQL password for {user}@{host}: ")
    url = f"mysql+pymysql://{user}:{pw.replace('@', '%40')}@{host}:{port}"
    ddl = (ROOT / "sql" / "schema.sql").read_text(encoding="utf-8")
    ddl = "\n".join(l for l in ddl.splitlines() if not l.strip().startswith("--"))
    with create_engine(url).begin() as conn:
        for stmt in [s.strip() for s in ddl.split(";") if s.strip()]:
            conn.execute(text(stmt))
    eng = create_engine(url + "/shuttleiq")
    order = ["dim_country", "dim_tournament", "dim_event", "dim_round", "dim_player",
             "dim_team", "bridge_team_player", "fact_match_result"]
    with eng.begin() as conn:
        for name in order:
            tables[name].to_sql(name, conn, if_exists="append", index=False, chunksize=500)
            print(f"  loaded {name:<20} {len(tables[name]):>6} rows")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wiki-dir", default=str(ROOT / "data" / "raw" / "wikipedia" / "wikitext"))
    ap.add_argument("--out-dir", default=str(ROOT / "data"))
    ap.add_argument("--no-db", action="store_true")
    ap.add_argument("--host"), ap.add_argument("--port"), ap.add_argument("--user")
    args = ap.parse_args()

    out = Path(args.out_dir)
    (out / "staging").mkdir(parents=True, exist_ok=True)
    (out / "processed").mkdir(parents=True, exist_ok=True)

    print("1/4 Extract + parse raw wikitext ...")
    stg, seed_map, seeds_df = extract_and_stage(args.wiki_dir)
    pd.DataFrame([{k: v for k, v in r.items() if k != "_m"} for r in stg]).to_csv(
        out / "staging" / "stg_matches.csv", index=False, encoding="utf-8-sig")
    seeds_df.to_csv(out / "staging" / "stg_seed_lists.csv", index=False, encoding="utf-8-sig")

    print("2/4 Transform into dimensional model ...")
    print(f"    resolved {resolve_plain_names(stg)} abbreviated plain-text player names to full names")
    tables, rejects, unknown = transform(stg, seed_map)
    for name, df in tables.items():
        df.to_csv(out / "processed" / f"{name}.csv", index=False, encoding="utf-8-sig")
    rejects.to_csv(out / "processed" / "rejected_matches.csv", index=False, encoding="utf-8-sig")

    print("3/4 Data-quality report ...")
    report = dq_report(stg, tables, rejects, unknown, seeds_df)
    (out / "processed" / "dq_report.txt").write_text(report, encoding="utf-8")
    print(report)

    if args.no_db:
        print("\n4/4 Skipped MySQL load (--no-db). CSVs are in data/processed/")
    else:
        print("\n4/4 Loading MySQL ...")
        load_mysql(tables, args)
        print("Done. Database `shuttleiq` is ready.")


if __name__ == "__main__":
    main()
