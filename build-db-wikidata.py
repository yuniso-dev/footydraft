#!/usr/bin/env python3
"""
build-db-wikidata.py  —  Build a FOOTY VERSUS player database from Wikidata.

WHY THIS EXISTS
    The whole point: a player who appeared for several clubs must show up under
    EVERY one of them (spin Real Madrid -> Ronaldo; spin Juventus -> Ronaldo too).
    Wikidata's "member of sports team" (P54) records every club a player played
    for, so querying each club independently naturally lists a player under all
    of their clubs. Positions come from "position played on team" (P413).

WHAT IT PRODUCES
    football-players.txt   -> paste this into the app: gear -> Player database
                              -> Import / Export Players -> (Overwrite) -> Import
    football-db.json       -> same data as the internal DB shape, if you'd rather
                              hand it back to have it baked into the HTML file.

HOW TO RUN  (on any machine with normal internet — NOT inside Claude's sandbox,
             whose network policy blocks query.wikidata.org)
    python3 build-db-wikidata.py
    # options:
    python3 build-db-wikidata.py --per-club 90     # players per club (default 70)
    python3 build-db-wikidata.py --require-position # drop players with no position

    No third-party packages required (uses the standard library).

NOTES
    * Wikidata asks for a descriptive User-Agent; one is set below.
    * Be polite: there is a small delay between requests.
    * Players are ranked by number of Wikipedia editions (a fame proxy), so you
      get the notable names first and can cap the depth with --per-club.
"""

import argparse, json, sys, time, urllib.parse, urllib.request

SPARQL = "https://query.wikidata.org/sparql"
API    = "https://www.wikidata.org/w/api.php"
UA     = "FootyVersusDB/1.0 (personal fantasy drafting game; contact: local)"

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

# Optional: pre-resolved Wikidata QIDs. If a name resolves wrongly, pin it here.
QID_OVERRIDES = {
    # "Real Madrid": "Q8682",
}

# Wikidata position label (lowercased substring) -> app position codes.
# Ordered most-specific first; first match wins per label.
POS_MAP = [
    ("goalkeeper",            ["GK"]),
    ("centre-back",           ["CB"]),
    ("center-back",           ["CB"]),
    ("central defender",      ["CB"]),
    ("sweeper",               ["CB"]),
    ("left-back",             ["LB"]),
    ("left back",             ["LB"]),
    ("right-back",            ["RB"]),
    ("right back",            ["RB"]),
    ("wing-back",             ["LWB", "RWB"]),
    ("full-back",             ["LB", "RB"]),
    ("fullback",              ["LB", "RB"]),
    ("defensive midfield",    ["CDM"]),
    ("attacking midfield",    ["CAM"]),
    ("central midfield",      ["CM"]),
    ("centre midfield",       ["CM"]),
    ("left midfield",         ["LM"]),
    ("right midfield",        ["RM"]),
    ("left winger",           ["LW"]),
    ("left wing",             ["LW"]),
    ("right winger",          ["RW"]),
    ("right wing",            ["RW"]),
    ("winger",                ["LW", "RW"]),
    ("second striker",        ["CAM", "ST"]),
    ("centre-forward",        ["ST"]),
    ("center-forward",        ["ST"]),
    ("striker",               ["ST"]),
    ("forward",               ["ST"]),
    ("midfielder",            ["CM"]),
    ("midfield",              ["CM"]),
    ("defender",              ["CB"]),
]


def http_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=90) as r:
        return json.load(r)


def resolve_qid(name, hint):
    if name in QID_OVERRIDES:
        return QID_OVERRIDES[name]
    params = {"action": "wbsearchentities", "search": hint, "language": "en",
              "type": "item", "format": "json", "limit": 8}
    data = http_json(API + "?" + urllib.parse.urlencode(params))
    hits = data.get("search", [])
    # prefer an entity described as a football/soccer club
    for it in hits:
        d = (it.get("description") or "").lower()
        if "football club" in d or "soccer club" in d or "association football" in d:
            return it["id"]
    return hits[0]["id"] if hits else None


def query_club(qid, per_club):
    # Members of the club, their position labels, sitelink count, and whether the
    # membership is still open (no end date -> current squad -> tag with @).
    q = f"""
    SELECT ?p ?pLabel ?links
           (GROUP_CONCAT(DISTINCT ?posLabel; separator="||") AS ?positions)
           (MAX(?openFlag) AS ?current) WHERE {{
      ?p wdt:P54 wd:{qid} .
      ?p wdt:P106 wd:Q937857 .
      ?p wikibase:sitelinks ?links .
      OPTIONAL {{ ?p wdt:P413 ?pos . ?pos rdfs:label ?posLabel FILTER(LANG(?posLabel)="en") }}
      OPTIONAL {{
        ?p p:P54 ?stmt . ?stmt ps:P54 wd:{qid} .
        FILTER NOT EXISTS {{ ?stmt pq:P582 ?end }}
        BIND(1 AS ?openFlag)
      }}
      SERVICE wikibase:label {{ bd:serviceParam wikibase:language "en". }}
    }}
    GROUP BY ?p ?pLabel ?links
    ORDER BY DESC(?links)
    LIMIT {per_club}
    """
    url = SPARQL + "?" + urllib.parse.urlencode({"query": q, "format": "json"})
    return http_json(url)["results"]["bindings"]


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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--per-club", type=int, default=70, help="max players per club (by fame)")
    ap.add_argument("--require-position", action="store_true", help="drop players with no mapped position")
    ap.add_argument("--out-txt", default="football-players.txt")
    ap.add_argument("--out-json", default="football-db.json")
    args = ap.parse_args()

    db = {}
    for name, hint in CLUBS:
        try:
            qid = resolve_qid(name, hint)
        except Exception as e:
            print(f"! {name}: could not resolve QID ({e})", file=sys.stderr)
            continue
        if not qid:
            print(f"! {name}: no QID found for '{hint}'", file=sys.stderr)
            continue
        try:
            rows = query_club(qid, args.per_club)
        except Exception as e:
            print(f"! {name} ({qid}): query failed ({e})", file=sys.stderr)
            time.sleep(2)
            continue

        players = []
        for b in rows:
            pname = b.get("pLabel", {}).get("value", "").strip()
            if not pname or pname.startswith("Q"):   # unlabelled item -> skip
                continue
            raw = b.get("positions", {}).get("value", "")
            labels = [x for x in raw.split("||") if x]
            pos = map_positions(labels)
            if args.require_position and not pos:
                continue
            current = b.get("current", {}).get("value") in ("1", "true")
            players.append((("@" if current else "") + pname, pos))

        db[name] = players
        print(f"  {name:22s} {qid:10s} -> {len(players)} players", file=sys.stderr)
        time.sleep(1.0)   # be polite to the endpoint

    # write import-format text (# Club header, then "Name: POS, POS")
    with open(args.out_txt, "w", encoding="utf-8") as f:
        for name, _ in CLUBS:
            players = db.get(name)
            if not players:
                continue
            f.write(f"# {name}\n")
            for pname, pos in players:
                f.write(f"{pname}: {', '.join(pos)}\n" if pos else f"{pname}:\n")
            f.write("\n")

    # write JSON in the internal DB shape: {club: "Name:POS|@Name:POS"}
    js = {}
    for name, _ in CLUBS:
        players = db.get(name)
        if not players:
            continue
        js[name] = "|".join((p + ":" + ",".join(pos)) for p, pos in players)
    with open(args.out_json, "w", encoding="utf-8") as f:
        json.dump(js, f, ensure_ascii=False, indent=1)

    total = sum(len(v) for v in db.values())
    print(f"\nDone. {total} player-club rows across {len(db)} clubs.", file=sys.stderr)
    print(f"Wrote {args.out_txt} (paste into the app) and {args.out_json}.", file=sys.stderr)


if __name__ == "__main__":
    main()
