#!/usr/bin/env python3
"""
build-db-wikidata.py  —  Build a FOOTY VERSUS player database from Wikidata.

WHY THIS EXISTS
    A player who appeared for several clubs must show up under EVERY one of them
    (spin Real Madrid -> Ronaldo; spin Juventus -> Ronaldo too). Wikidata's
    "member of sports team" (P54) records every club a player played for, so
    querying each club independently lists a player under all of their clubs.
    Positions come from "position played on team" (P413).

WHAT IT PRODUCES
    football-players.txt   -> paste into the app: gear -> Player database ->
                              Import / Export Players -> (Overwrite) -> Import
    football-db.json       -> the same data in the internal DB shape.

HOW TO RUN  (on any machine with normal internet)
    python builddbwikidata.py                     # default endpoint (Wikidata)
    python builddbwikidata.py --endpoint qlever   # fast mirror, avoids WDQS outages
    python builddbwikidata.py --per-club 100      # deeper rosters (default 70)
    python builddbwikidata.py --require-position  # drop players with no position

    No third-party packages required (standard library only).

OUTAGES / RATE LIMITING
    Wikidata's own query service (query.wikidata.org) sometimes goes into an
    outage and throttles everyone to ~1 request/minute (HTTP 429). This script:
      * retries automatically, honouring the server's Retry-After delay;
      * writes results after EACH club and can RESUME — just run it again and it
        skips clubs already saved in football-db.json;
      * supports --endpoint qlever, a fast community mirror that is usually
        unaffected by WDQS outages. Try that first if you hit 429s.
"""

import argparse, json, os, sys, time, urllib.parse, urllib.request, urllib.error

ENDPOINTS = {
    "wikidata": "https://query.wikidata.org/sparql",
    "qlever":   "https://qlever.cs.uni-freiburg.de/api/wikidata",
}
API = "https://www.wikidata.org/w/api.php"
UA  = "FootyVersusDB/1.1 (personal fantasy drafting game)"

# (canonical app club name, search hint used to resolve the Wikidata item)
CLUBS = [
    ("Liverpool",            "Liverpool F.C."),
    ("Manchester City",      "Manchester City F.C."),
    ("Arsenal",              "Arsenal F.C."),
    ("Chelsea",              "Chelsea F.C."),
    ("Manchester United",    "Manchester United F.C."),
    ("Newcastle United",     "Newcastle United F.C."),
    ("Tottenham",            "Tottenham Hotspur F.C."),
    ("Aston Villa",          "Aston Villa F.C."),
    ("Real Madrid",          "Real Madrid CF"),
    ("Barcelona",            "FC Barcelona"),
    ("Atlético Madrid",      "Atlético Madrid"),
    ("Villarreal",           "Villarreal CF"),
    ("Sevilla",              "Sevilla FC"),
    ("Athletic Bilbao",      "Athletic Bilbao"),
    ("Real Sociedad",        "Real Sociedad"),
    ("Inter Milan",          "Inter Milan"),
    ("Juventus",             "Juventus FC"),
    ("Napoli",               "SSC Napoli"),
    ("AC Milan",             "AC Milan"),
    ("Roma",                 "AS Roma"),
    ("Lazio",                "SS Lazio"),
    ("Bayern Munich",        "FC Bayern Munich"),
    ("Borussia Dortmund",    "Borussia Dortmund"),
    ("Bayer Leverkusen",     "Bayer 04 Leverkusen"),
    ("RB Leipzig",           "RB Leipzig"),
    ("PSG",                  "Paris Saint-Germain F.C."),
    ("Marseille",            "Olympique de Marseille"),
    ("Monaco",               "AS Monaco FC"),
    ("Benfica",              "S.L. Benfica"),
    ("Sporting CP",          "Sporting CP"),
    ("Porto",                "FC Porto"),
    ("Ajax",                 "AFC Ajax"),
]

# Known Wikidata QIDs (skip the resolve step + avoid mismatches). Missing ones
# fall back to the search API.
QIDS = {
    "Liverpool": "Q1130849", "Manchester City": "Q50602", "Arsenal": "Q9617",
    "Real Madrid": "Q8682", "Barcelona": "Q7156", "Bayern Munich": "Q15789",
    "Juventus": "Q1422", "AC Milan": "Q1543", "Inter Milan": "Q631",
    "PSG": "Q483020",
}

# Wikidata position label (lowercased substring) -> app position codes.
POS_MAP = [
    ("goalkeeper", ["GK"]),
    ("centre-back", ["CB"]), ("center-back", ["CB"]), ("central defender", ["CB"]),
    ("sweeper", ["CB"]),
    ("left-back", ["LB"]), ("left back", ["LB"]),
    ("right-back", ["RB"]), ("right back", ["RB"]),
    ("wing-back", ["LWB", "RWB"]),
    ("full-back", ["LB", "RB"]), ("fullback", ["LB", "RB"]),
    ("defensive midfield", ["CDM"]),
    ("attacking midfield", ["CAM"]),
    ("central midfield", ["CM"]), ("centre midfield", ["CM"]),
    ("left midfield", ["LM"]), ("right midfield", ["RM"]),
    ("left winger", ["LW"]), ("left wing", ["LW"]),
    ("right winger", ["RW"]), ("right wing", ["RW"]),
    ("winger", ["LW", "RW"]),
    ("second striker", ["CAM", "ST"]),
    ("centre-forward", ["ST"]), ("center-forward", ["ST"]),
    ("striker", ["ST"]), ("forward", ["ST"]),
    ("midfielder", ["CM"]), ("midfield", ["CM"]),
    ("defender", ["CB"]),
]

TXT = "football-players.txt"
JSON = "football-db.json"


def http_get(url, accept="application/json", tries=6):
    """GET with retry that honours Retry-After on 429/503."""
    for attempt in range(tries):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": accept})
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 503) and attempt < tries - 1:
                ra = e.headers.get("Retry-After")
                wait = int(ra) if (ra and ra.isdigit()) else 62
                print(f"    rate-limited ({e.code}); waiting {wait}s "
                      f"(attempt {attempt + 1}/{tries})...", file=sys.stderr)
                time.sleep(wait + 1)
                continue
            raise
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt < tries - 1:
                wait = 5 * (attempt + 1)
                print(f"    connection issue ({e}); retrying in {wait}s...", file=sys.stderr)
                time.sleep(wait)
                continue
            raise
    raise RuntimeError("exhausted retries")


def resolve_qid(name, hint):
    if name in QIDS:
        return QIDS[name]
    params = {"action": "wbsearchentities", "search": hint, "language": "en",
              "type": "item", "format": "json", "limit": 8}
    data = http_get(API + "?" + urllib.parse.urlencode(params))
    hits = data.get("search", [])
    for it in hits:
        d = (it.get("description") or "").lower()
        if "football club" in d or "soccer club" in d or "association football" in d:
            return it["id"]
    return hits[0]["id"] if hits else None


def build_query(qid, per_club):
    # Uses only standard SPARQL + rdfs:label + wikibase:sitelinks, so it runs on
    # both the official endpoint and the QLever mirror (no WDQS label service).
    return f"""PREFIX wd: <http://www.wikidata.org/entity/>
PREFIX wdt: <http://www.wikidata.org/prop/direct/>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>
PREFIX wikibase: <http://wikiba.se/ontology#>
SELECT ?p ?pLabel ?links (GROUP_CONCAT(DISTINCT ?posLabel; SEPARATOR="||") AS ?positions) WHERE {{
  ?p wdt:P54 wd:{qid} .
  ?p wdt:P106 wd:Q937857 .
  ?p rdfs:label ?pLabel . FILTER(LANG(?pLabel) = "en")
  OPTIONAL {{ ?p wikibase:sitelinks ?links }}
  OPTIONAL {{ ?p wdt:P413 ?pos . ?pos rdfs:label ?posLabel . FILTER(LANG(?posLabel) = "en") }}
}}
GROUP BY ?p ?pLabel ?links
ORDER BY DESC(?links)
LIMIT {per_club}"""


def query_club(endpoint, qid, per_club):
    q = build_query(qid, per_club)
    url = endpoint + "?" + urllib.parse.urlencode({"query": q, "format": "json"})
    data = http_get(url, accept="application/sparql-results+json")
    return data["results"]["bindings"]


def map_positions(raw_labels):
    out = []
    for lab in raw_labels:
        l = lab.lower()
        for key, codes in POS_MAP:
            if key in l:
                for c in codes:
                    if c not in out:
                        out.append(c)
                break
    return out


def write_outputs(db):
    with open(TXT, "w", encoding="utf-8") as f:
        for name, _ in CLUBS:
            players = db.get(name)
            if not players:
                continue
            f.write(f"# {name}\n")
            for pname, pos in players:
                f.write(f"{pname}: {', '.join(pos)}\n" if pos else f"{pname}:\n")
            f.write("\n")
    js = {name: "|".join(p + ":" + ",".join(pos) for p, pos in db[name])
          for name, _ in CLUBS if db.get(name)}
    with open(JSON, "w", encoding="utf-8") as f:
        json.dump(js, f, ensure_ascii=False, indent=1)


def load_resume():
    """Reload any previous run so we can skip finished clubs."""
    if not os.path.exists(JSON):
        return {}
    try:
        with open(JSON, encoding="utf-8") as f:
            raw = json.load(f)
    except Exception:
        return {}
    db = {}
    for club, s in raw.items():
        players = []
        for tok in s.split("|"):
            tok = tok.strip()
            if not tok:
                continue
            i = tok.rfind(":")
            nm = tok[:i] if i >= 0 else tok
            pos = [x for x in tok[i + 1:].split(",") if x] if i >= 0 else []
            players.append((nm, pos))
        db[club] = players
    return db


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--endpoint", choices=list(ENDPOINTS), default="wikidata")
    ap.add_argument("--per-club", type=int, default=70)
    ap.add_argument("--require-position", action="store_true")
    ap.add_argument("--fresh", action="store_true", help="ignore any previous run")
    args = ap.parse_args()

    endpoint = ENDPOINTS[args.endpoint]
    db = {} if args.fresh else load_resume()
    if db:
        print(f"Resuming: {len(db)} club(s) already done, will be skipped.", file=sys.stderr)
    print(f"Endpoint: {endpoint}\n", file=sys.stderr)

    for name, hint in CLUBS:
        if db.get(name):
            continue
        try:
            qid = resolve_qid(name, hint)
        except Exception as e:
            print(f"! {name}: could not resolve QID ({e})", file=sys.stderr)
            continue
        if not qid:
            print(f"! {name}: no QID found", file=sys.stderr)
            continue
        try:
            rows = query_club(endpoint, qid, args.per_club)
        except Exception as e:
            print(f"! {name} ({qid}): query failed ({e}) — re-run later to resume.",
                  file=sys.stderr)
            continue

        players = []
        for b in rows:
            pname = b.get("pLabel", {}).get("value", "").strip()
            if not pname or (pname.startswith("Q") and pname[1:].isdigit()):
                continue
            labels = [x for x in b.get("positions", {}).get("value", "").split("||") if x]
            pos = map_positions(labels)
            if args.require_position and not pos:
                continue
            players.append((pname, pos))

        db[name] = players
        write_outputs(db)   # save after every club so progress is never lost
        print(f"  {name:22s} {qid:10s} -> {len(players):3d} players "
              f"({len(db)}/{len(CLUBS)} clubs)", file=sys.stderr)
        time.sleep(2)       # be polite between clubs

    total = sum(len(v) for v in db.values())
    print(f"\nDone. {total} player-club rows across {len(db)}/{len(CLUBS)} clubs.",
          file=sys.stderr)
    print(f"Wrote {TXT} (paste into the app) and {JSON}.", file=sys.stderr)


if __name__ == "__main__":
    main()
