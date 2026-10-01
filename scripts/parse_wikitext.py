"""
ShuttleIQ - wikitext bracket parser (pure Python, no database).

Turns the raw Wikipedia bracket templates ({{16TeamBracket-Tennis3 ...}}) into
one dict per match. Works for every bracket variant seen on the pages
(4TeamBracket-Tennis3, 16TeamBracket-Tennis3, 16TeamBracket-Tennis3-Byes) because
it reads the numbered slots (RD<r>-team<n>, RD<r>-seed<n>, RD<r>-score<n>-<g>)
generically; slots (2k-1, 2k) of a round form match k.
"""
import re
from collections import Counter

RE_PARAM = re.compile(r"^\|\s*([A-Za-z0-9_\-]+)\s*=\s*(.*?)\s*$")
RE_HEADING = re.compile(r"^(=+)\s*(.*?)\s*\1\s*$")
RE_LINK = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]*))?\]\]")
RE_FLAG = re.compile(r"\{\{\s*flag(?:icon|country)?\s*\|\s*([A-Za-z]{2,4})", re.I)
RE_SEEDLINE = re.compile(r"^\{\{\s*seeds\s*\|\s*(\d+)\s*\|[^}]*\}\}\s*(.*)$")


# ---------------------------------------------------------------- helpers
def canonical_name(target):
    """'Lin Chun-yi (badminton)' -> 'Lin Chun-yi'"""
    t = target.replace("_", " ").strip()
    return re.sub(r"\s*\([^)]*\)\s*$", "", t).strip()


def parse_team(value):
    """Raw team cell -> dict(players, plain, country, bold, is_bye, raw).
    A doubles cell holds two players separated by <br/>. Linked players give their full
    canonical name; players written as plain text (no wiki page, often abbreviated like
    'N G Chan') are kept and listed in `plain` so the ETL can try to resolve them."""
    raw = value or ""
    bold = "'''" in raw
    names, plain = [], []
    for part in re.split(r"<br\s*/?>", raw, flags=re.I):
        links = [t for t, _d in RE_LINK.findall(part)
                 if not re.match(r"(?i)^(file|image|category|wikipedia):", t.strip())]
        if links:
            names += [canonical_name(t) for t in links]
            continue
        txt = re.sub(r"\{\{.*?\}\}", "", part)
        txt = re.sub(r"'+|&nbsp;|\[\[|\]\]", "", txt)
        for piece in re.split(r"\s+/\s+", txt):
            piece = piece.strip()
            if piece:
                names.append(piece)
                plain.append(piece)
    flags = [f.upper() for f in RE_FLAG.findall(raw)]
    country = Counter(flags).most_common(1)[0][0] if flags else None
    low = re.sub(r"[^a-z]", "", raw.lower())
    is_bye = (not names) or low in ("bye", "nan")
    return {"players": names, "plain": plain, "country": country, "bold": bold,
            "is_bye": is_bye, "raw": raw.strip()}


def parse_score(value):
    """-> (points|None, flag|None, text).
    flag 'R' = this side retired (score written like 7<sup>r</sup> or '7r').
    text = any non-numeric remainder (e.g. 'w', '/', 'o' = one third of 'w/o', or 'Ret.')."""
    raw = value or ""
    sup_r = bool(re.search(r"<sup>\s*r\s*</sup>", raw, re.I))
    s = re.sub(r"<[^>]+>|'+|&nbsp;", "", raw).strip()
    if s == "":
        return None, None, ""
    m = re.fullmatch(r"(\d+)\s*(r|ret\.?)?", s, re.I)
    if m:
        return int(m.group(1)), ("R" if (m.group(2) or sup_r) else None), ""
    return None, None, s


def parse_seed(value):
    s = re.sub(r"'+|&nbsp;", "", value or "").strip()
    return int(s) if s.isdigit() else None


def stage_of(label):
    l = (label or "").lower()
    if "semi" in l:
        return 2
    if "quarter" in l:
        return 3
    if "final" in l:
        return 1
    m = re.search(r"round of (\d+)", l)
    return {16: 4, 32: 5, 64: 6}.get(int(m.group(1))) if m else None


# ------------------------------------------------------------- extraction
def _headings(text):
    out, pos = [], 0
    for line in text.splitlines(keepends=True):
        m = RE_HEADING.match(line.strip())
        if m:
            out.append((pos, len(m.group(1)), m.group(2)))
        pos += len(line)
    return out


def extract_brackets(text):
    """Return [{'template','heading_path','body','index'}] for every bracket template."""
    heads = _headings(text)
    out = []
    for m in re.finditer(r"\{\{\s*(\d+TeamBracket[^\s|{}]*)", text):
        start, depth, i = m.start(), 0, m.start()
        while i < len(text):
            if text.startswith("{{", i):
                depth += 1
                i += 2
            elif text.startswith("}}", i):
                depth -= 1
                i += 2
                if depth == 0:
                    break
            else:
                i += 1
        path = {}
        for pos, lvl, title in heads:
            if pos < start:
                path[lvl] = title
                for deeper in [k for k in path if k > lvl]:
                    del path[deeper]
        hp = " > ".join(path[k] for k in sorted(path) if k >= 3)
        out.append({"template": m.group(1), "heading_path": hp,
                    "body": text[start:i], "index": len(out) + 1})
    return out


def parse_seed_list(text):
    """The '{{seeds|N|x}} {{flagicon|X}} [[Name]] ''(exit round)''' lines."""
    out = []
    for line in text.splitlines():
        m = RE_SEEDLINE.match(line.strip())
        if not m:
            continue
        team = parse_team(m.group(2))
        exit_m = re.search(r"''\(([^)]*)\)''", m.group(2))
        out.append({"seed": int(m.group(1)), "players": team["players"],
                    "country": team["country"],
                    "exit_round": exit_m.group(1).strip() if exit_m else None})
    return out


# ---------------------------------------------------------------- matches
def parse_bracket(br):
    params = {}
    for line in br["body"].splitlines():
        m = RE_PARAM.match(line.strip())
        if m:
            params[m.group(1)] = m.group(2)

    labels, teams, seeds, scores = {}, {}, {}, {}
    for k, v in params.items():
        if re.fullmatch(r"RD\d+", k):
            labels[int(k[2:])] = v.strip()
            continue
        m = re.fullmatch(r"RD(\d+)-team(\d+)", k)
        if m:
            teams[(int(m.group(1)), int(m.group(2)))] = v
            continue
        m = re.fullmatch(r"RD(\d+)-seed(\d+)", k)
        if m:
            seeds[(int(m.group(1)), int(m.group(2)))] = v
            continue
        m = re.fullmatch(r"RD(\d+)-score(\d+)-(\d+)", k)
        if m:
            scores[(int(m.group(1)), int(m.group(2)), int(m.group(3)))] = v

    rds = sorted({r for r, _ in teams} | set(labels))
    anchor = next(((r, stage_of(labels.get(r))) for r in sorted(rds, reverse=True)
                   if stage_of(labels.get(r))), None)
    if anchor is None and rds:
        anchor = (rds[-1], 3)        # last column of a section = quarter-final

    matches = []
    for r in rds:
        slots = sorted({n for (rr, n) in teams if rr == r})
        for k in sorted({(n + 1) // 2 for n in slots}):
            n1, n2 = 2 * k - 1, 2 * k
            if (r, n1) not in teams or (r, n2) not in teams:
                continue
            t1, t2 = parse_team(teams[(r, n1)]), parse_team(teams[(r, n2)])
            if t1["is_bye"] or t2["is_bye"]:
                continue
            t1["seed"] = parse_seed(seeds.get((r, n1)))
            t2["seed"] = parse_seed(seeds.get((r, n2)))
            games, raw_scores, partial = [], [], None
            retired, text = set(), {1: "", 2: ""}
            gnums = sorted({g for (rr, n, g) in scores if rr == r and n in (n1, n2)})
            for g in gnums:
                a_raw, b_raw = scores.get((r, n1, g), ""), scores.get((r, n2, g), "")
                a, fa, ta = parse_score(a_raw)
                b, fb, tb = parse_score(b_raw)
                raw_scores.append(f"{a_raw.strip()}-{b_raw.strip()}")
                text[1] += ta
                text[2] += tb
                if fa == "R":
                    retired.add(1)
                if fb == "R":
                    retired.add(2)
                if a is not None and b is not None:
                    if fa == "R" or fb == "R":
                        partial = (a, b)          # game stopped by the retirement
                    else:
                        games.append((a, b))
            walkover = set()
            for side in (1, 2):
                t = re.sub(r"[^a-z]", "", text[side].lower())
                if t in ("wo", "walkover"):
                    walkover.add(side)
                elif t.startswith("ret"):
                    retired.add(side)
            gw1 = sum(1 for x, y in games if x > y)
            gw2 = sum(1 for x, y in games if y > x)
            bold_winner = 1 if t1["bold"] and not t2["bold"] else 2 if t2["bold"] and not t1["bold"] else None

            if walkover:
                rtype = "Walkover"
            elif retired:
                rtype = "Retired"
            elif games:
                rtype = "Completed"
            elif bold_winner:
                rtype = "NoScore"
            else:
                rtype = "Unplayed"

            winner = None
            if rtype == "Walkover":
                winner = bold_winner or (3 - next(iter(walkover)) if len(walkover) == 1 else None)
            elif rtype == "Retired":
                winner = 3 - next(iter(retired)) if len(retired) == 1 else bold_winner
            elif rtype == "NoScore":
                winner = bold_winner
            elif rtype == "Completed":
                winner = 1 if gw1 > gw2 else 2 if gw2 > gw1 else bold_winner
            conflict = bool(winner and bold_winner and winner != bold_winner)
            if rtype != "Unplayed" and winner is None:
                rtype = "Unresolved"

            stage = None
            if anchor:
                stage = anchor[1] + (anchor[0] - r)
            matches.append({
                "template": br["template"], "bracket_index": br["index"],
                "heading_path": br["heading_path"], "rd": r,
                "round_label": labels.get(r), "stage_from_final": stage,
                "match_no": k, "team1": t1, "team2": t2, "games": games, "partial_game": partial,
                "gw1": gw1, "gw2": gw2,
                "raw_scores": " | ".join(raw_scores), "winner": winner,
                "bold_winner": bold_winner, "winner_conflict": conflict,
                "result_type": rtype,
            })
    return matches
