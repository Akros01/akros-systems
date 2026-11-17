"""Companies named on recent permits, ranked as Tipoff prospects.

  python3 tools/permits/prospects.py                 # every metro, last 90 days -> briefs/prospects/
  python3 tools/permits/prospects.py --metro san-diego-county --days 60

For each company: its metro, its trade (read from the job types it pulls permits for and from its
name), how many permits it pulled and where, and the Tipoff leads it would buy, with this month's
count of those leads in its metro. National chains and home builders are marked, since they rarely
buy local lead lists. The output is a private working list (briefs/ is not committed).
"""
import argparse
import collections
import csv
import datetime as dt
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from config import CATS, METROS  # noqa: E402
from sources import FETCHERS  # noqa: E402

DATA = os.path.join(HERE, "..", "..", "permits", "data")
NAME_TRADES = [
    ("roofing", r"roof"),
    ("fence", r"\bfenc"),
    ("outdoor living", r"landscap|outdoor|hardscape|lawn|patio|pergola|turf"),
    ("solar", r"solar|\bsun\w*|\benergy\b|photovolt"),
    ("pool", r"\bpools?\b|\bspas?\b|aquatic"),
    ("hvac", r"\bair\b|hvac|heating|cooling|comfort|mechanical|refrigeration|\ba/?c\b"),
    ("electrical", r"electric"),
    ("plumbing", r"plumb|rooter|drain"),
    ("windows", r"window|glass|\bdoors?\b"),
    ("insulation", r"insulat"),
    ("home builder", r"\bhomes?\b|homebuild|builders?\b|communities|development|residential|construction"),
]
JOB_TRADES = {
    "pools": "pool", "solar": "solar", "batteries": "solar", "ev-chargers": "electrical", "hvac": "hvac",
    "electrical-service": "electrical", "water-heaters": "plumbing", "irrigation": "outdoor living",
    "roofing": "roofing", "siding": "roofing", "windows-doors": "windows", "fences-patios": "fence",
    "porches-decks": "outdoor living", "new-homes": "home builder", "wildfire-rebuilds": "home builder",
    "additions-remodels": "remodeler", "adus": "remodeler", "repairs": "remodeler", "accessory": "remodeler",
    "garages": "remodeler", "seismic": "remodeler", "foundation": "foundation", "demolition": "demolition",
    "insulation": "insulation",
}
# The leads each trade would buy from Tipoff, best first. "storms" means storm reports.
# Not leads: new homes for solar (California new homes come with solar), and home batteries for
# trades other than solar (in Austin most are utility-program backup batteries installed by one company).
LEADS_FOR = {
    "solar": ["roofing", "ev-chargers", "electrical-service", "adus", "pools", "additions-remodels"],
    "electrical": ["pools", "adus", "accessory", "additions-remodels", "solar"],
    "fence": ["pools", "new-homes"],
    "outdoor living": ["pools", "new-homes", "accessory"],
    "pool": ["new-homes"],
    "pool service": ["pools"],
    "hvac": ["additions-remodels", "adus", "accessory", "solar", "ev-chargers", "electrical-service"],
    "roofing": ["storms"],
    "windows": ["storms", "new-homes", "additions-remodels"],
    "insulation": ["hvac", "additions-remodels", "adus"],
    "plumbing": ["pools", "adus", "additions-remodels"],
}
FIT = {"solar": 3, "outdoor living": 3, "fence": 3, "electrical": 2.5, "roofing": 2.5, "pool": 1.5, "hvac": 2,
       "windows": 2, "insulation": 2, "plumbing": 1}
NATIONAL = re.compile(
    r"sunrun|tesla|sunpower|freedom forever|sunnova|vivint|trinity solar|momentum solar|palmetto|ion solar|lgcy|"
    r"base power|"
    r"lennar|d\.?\s?r\.?\s?horton|kb home|pulte|meritage|taylor morrison|toll brothers|perry homes|highland homes|"
    r"trophy|david weekley|ashton woods|m/?i homes|tri pointe|centex|beazer|century communities|shea homes|"
    r"home depot|lowe'?s|sears|leaf home|power home|renewal by andersen|bath fitter|re-?bath|anthony & sylvan|"
    r"blue haven|premier pools|baker home energy|aps |comcast|at&t|verizon|spectrum|mill creek", re.I)


def trade_of(name, jobs):
    top_job = jobs.most_common(1)[0][0] if jobs else ""
    by_job = JOB_TRADES.get(top_job, "")
    for trade, rx in NAME_TRADES:
        if re.search(rx, name, re.I):
            if trade == "home builder" and by_job not in ("home builder", "remodeler"):
                return by_job  # "XYZ Construction" pulling solar permits is a solar company
            return trade
    return by_job


def monthly(metro):
    path = os.path.join(DATA, f"{metro}.json")
    if not os.path.exists(path):
        return {}, {}
    with open(path, encoding="utf-8") as f:
        agg = json.load(f)
    return {c: b["cur"] for c, b in agg["cats"].items()}, agg.get("finished", {})


def pitch(trade, metro, counts, finished, storms_by_state):
    parts = []
    for lead in LEADS_FOR.get(trade, []):
        if lead == "storms":
            n = storms_by_state.get(METROS[metro].get("state") or METROS[metro]["name"].split(", ")[-1], 0)
            parts.append(f"storm reports in the state: {n} in 30 days")
        elif counts.get(lead):
            label = CATS.get(lead, {}).get("label", lead).lower()
            done = f" ({finished[lead]} finished)" if finished.get(lead) else ""
            parts.append(f"{label}: {counts[lead]}{done}")
    return "; ".join(parts)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--metro", help="one metro (default: all that Tipoff covers)")
    ap.add_argument("--days", type=int, default=90)
    ap.add_argument("--out", default=os.path.join("briefs", "prospects"))
    a = ap.parse_args()
    metros = [a.metro] if a.metro else [m for m in FETCHERS if METROS[m]["tipoff"]]
    since = (dt.date.today() - dt.timedelta(days=a.days)).isoformat()
    storms_by_state = collections.Counter()
    storm_file = os.path.join(DATA, "storms.json")
    if os.path.exists(storm_file):
        with open(storm_file, encoding="utf-8") as f:
            for r in json.load(f)["reports"]:
                storms_by_state[r["state"]] += 1

    rows = []
    for metro in metros:
        try:
            recs = FETCHERS[metro](since)
        except Exception as err:
            print(f"{metro}: skipped ({err!r})", file=sys.stderr)
            continue
        counts, finished = monthly(metro)
        firms = collections.defaultdict(lambda: {"jobs": collections.Counter(), "zips": collections.Counter(), "last": ""})
        seen = set()
        for r in recs:
            if not r.get("builder") or r["id"] in seen:
                continue
            seen.add(r["id"])
            f = firms[r["builder"]]
            f["jobs"].update(r["cats"])
            if r["area"]:
                f["zips"][r["area"]] += 1
            f["last"] = max(f["last"], r["issued"])
        for name, f in firms.items():
            n = sum(f["jobs"].values())
            trade = trade_of(name, f["jobs"])
            if n < 2 or trade not in FIT:
                continue
            national = bool(NATIONAL.search(name))
            score = FIT[trade] * math.log2(1 + n) * (0.2 if national else 1)
            rows.append({
                "score": round(score, 2), "metro": METROS[metro]["name"], "metro_slug": metro, "company": name,
                "trade": trade, "permits": n,
                "job_types": "; ".join(f"{CATS.get(j, {}).get('label', j)} {k}" for j, k in f["jobs"].most_common(3)),
                "top_zips": " ".join(z for z, _ in f["zips"].most_common(5)), "last_permit": f["last"],
                "national": "yes" if national else "",
                "pitch": pitch(trade, metro, counts, finished, storms_by_state),
            })
        print(f"{metro}: {sum(1 for r in rows if r['metro_slug'] == metro)} prospects")
    rows.sort(key=lambda r: -r["score"])
    os.makedirs(a.out, exist_ok=True)
    path = os.path.join(a.out, f"prospects-{dt.date.today().isoformat()}.csv")
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]) if rows else ["company"])
        w.writeheader()
        w.writerows(rows)
    by_trade = collections.Counter(r["trade"] for r in rows)
    print(f"{len(rows)} prospects -> {path}\nby trade: {dict(by_trade.most_common())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
