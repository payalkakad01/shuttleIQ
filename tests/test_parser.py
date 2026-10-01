import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from parse_wikitext import extract_brackets, parse_bracket, parse_seed_list

text = (Path(__file__).parent / "fixture_sample.wikitext").read_text(encoding="utf-8")
print("seed list:", parse_seed_list(text))
brs = extract_brackets(text)
print("brackets found:", [(b["template"], b["heading_path"]) for b in brs])
for b in brs:
    for m in parse_bracket(b):
        t1, t2 = m["team1"], m["team2"]
        print(f"[{m['heading_path'][:28]:<28}] stage={m['stage_from_final']} "
              f"{'/'.join(t1['players'])}({t1['country']},s{t1['seed']}) vs "
              f"{'/'.join(t2['players'])}({t2['country']},s{t2['seed']}) "
              f"games={m['games']} win={m['winner']} type={m['result_type']} conflict={m['winner_conflict']}")
