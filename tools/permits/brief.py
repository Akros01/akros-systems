"""Private permit lists for Tipoff customers and free samples.

The output has property addresses, so it is for one customer at a time:
never commit it and never publish it (briefs/ is in .gitignore). Owner names
are never collected.

Examples
  # A free sample: every pool permit in Collin County over four weeks
  python3 tools/permits/brief.py --metro collin-county --cats pools --since 2026-10-13 --until 2026-11-09

  # A weekly brief for one customer: pools and new homes in three ZIPs, last 7 days
  python3 tools/permits/brief.py --metro dallas --cats pools,new-homes --zips 75214,75218,75230 --days 7 --name "Swim Solutions"

  # Pools that passed final inspection in the last 7 days (Austin and Los Angeles feeds say when)
  python3 tools/permits/brief.py --metro austin --cats pools --stage finished --days 7

Job types (--cats) depend on the feed; run with --list to see what each metro has.
Writes briefs/<name-or-metro>-<cats>-<start>-to-<end>.csv and a .txt summary to paste into an email.
"""
import argparse
import collections
import csv
import datetime as dt
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import CATS, METROS  # noqa: E402
from sources import EXISTING_POOL, FETCHERS, FINISHED  # noqa: E402

COLUMNS = ["issued_date", "permit_number", "job_type", "address", "zip", "city_or_area", "description",
           "permit_type", "contractor", "declared_value", "source_link", "finished_date"]
# "Cody Pools, Inc. **MAIN", "Denali Pools LLC***Main***" -> the company name alone.
BRANCH_TAG = re.compile(r"\*+\s*main\b\s*\**|\*+", re.I)
NO_NAME = {"", "Not Given", "None", "N/A", "Na", "Owner", "Homeowner", "Owner Builder"}
JOB_TYPES = {
    "austin": "new-homes pools additions-remodels demolition accessory repairs hvac solar batteries "
              "electrical-service ev-chargers irrigation water-heaters",
    "collin-county": "new-homes pools additions-remodels solar roofing accessory demolition fences-patios foundation",
    "dallas": "new-homes pools additions-remodels solar roofing hvac foundation accessory demolition",
    "los-angeles": "pools adus new-homes wildfire-rebuilds demolition additions-remodels roofing windows-doors "
                   "seismic fences-patios",
    "chicago": "solar roofing porches-decks garages fences-patios windows-doors new-homes additions-remodels demolition",
    "sacramento": "pools new-homes adus additions-remodels demolition hvac solar roofing fences-patios",
}


def collect(metro, cats, zips, since, until, stage="issued", include_existing=False):
    """Matching permits as brief rows, newest first, plus how many existing-pool jobs were left out."""
    finished = stage == "finished"
    recs = (FETCHERS[metro](since.isoformat(), detail=True, finished=True) if finished
            else FETCHERS[metro](since.isoformat(), detail=True))
    seen, rows, existing = set(), [], 0
    for r in recs:
        if r["id"] in seen or not set(r["cats"]) & set(cats):
            continue
        d = r.get("detail", {})
        when = d.get("finished_date", "") if finished else r["issued"]
        if not when or not since.isoformat() <= when <= until.isoformat():
            continue
        if zips and (r["area"] or "") not in zips:
            continue
        if finished and "pools" in r["cats"] and not include_existing and EXISTING_POOL.search(d.get("description", "")):
            existing += 1
            continue
        seen.add(r["id"])
        rows.append({
            "issued_date": r["issued"],
            "permit_number": d.get("permit_number") or r["id"],
            "job_type": "+".join(c for c in r["cats"] if c in cats),
            "address": d.get("address", ""),
            "zip": r["area"] or "",
            "city_or_area": r["place"] or "",
            "description": d.get("description", ""),
            "permit_type": d.get("permit_type", ""),
            "contractor": d.get("contractor", ""),
            "declared_value": f"{r['value']:.0f}" if r["value"] else "",
            "source_link": d.get("source_link", ""),
            "finished_date": d.get("finished_date", ""),
        })
    key = "finished_date" if finished else "issued_date"
    rows.sort(key=lambda x: (x[key], x["zip"], x["address"]), reverse=True)
    return rows, existing


for _m in FETCHERS:
    JOB_TYPES.setdefault(_m, "new-homes pools additions-remodels adus solar batteries ev-chargers roofing siding "
                             "windows-doors hvac water-heaters electrical-service demolition foundation fences-patios insulation")


def slug(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def write_brief(metro_slug, cats, zips, since, until, stage="issued", include_existing=False, name="",
                out="briefs"):
    """Write the CSV and the .txt summary for one list; return (rows, csv_path, txt_path)."""
    finished = stage == "finished"
    rows, existing = collect(metro_slug, cats, zips, since, until, stage, include_existing)

    os.makedirs(out, exist_ok=True)
    stem = "-".join(x for x in (slug(name) or metro_slug, slug("-".join(cats)), "finished" if finished else "",
                                f"{since.isoformat()}-to-{until.isoformat()}") if x)
    csv_path = os.path.join(out, stem + ".csv")
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        w.writerows(rows)

    metro = METROS[metro_slug]
    by_zip = collections.Counter((x["zip"], x["city_or_area"]) for x in rows)
    names = (CATS.get(c, {}).get("label", c) for c in cats)
    label = ", ".join(n if n[:2].isupper() else n[:1].lower() + n[1:] for n in names)
    what = "passed final inspection" if finished else "issued"
    lines = [
        f"{metro['name']}: {label} permits that {what} {since:%b} {since.day} to {until:%b} {until.day}, {until.year}"
        if finished else
        f"{metro['name']}: {label} permits issued {since:%b} {since.day} to {until:%b} {until.day}, {until.year}",
        f"{len(rows)} permit{'s' if len(rows) != 1 else ''}" + (f" in ZIP {', '.join(sorted(zips))}" if zips else "")
        + (f" ({existing} more were work on a pool that already existed, left out)" if existing else ""),
        "",
        "By ZIP:" if metro_slug != "chicago" else "By community area:",
    ]
    for (z, place), n in sorted(by_zip.items(), key=lambda kv: (-kv[1], kv[0][0])):
        lines.append(f"  {z or 'unknown'}{' ' + place if place else ''}: {n}")
    builders = collections.Counter(b for b in (BRANCH_TAG.sub("", x["contractor"]).strip().title() for x in rows)
                                   if b not in NO_NAME)
    if rows and sum(builders.values()) >= len(rows) / 2:
        lines += ["", "Companies named on the most of these permits:"]
        lines += [f"  {b}: {n}" for b, n in builders.most_common(5)]
    lines += ["", "Newest first:"]
    for x in rows[:15]:
        who = f" ({BRANCH_TAG.sub('', x['contractor']).strip().title()})" if x["contractor"] else ""
        day = x["finished_date"] if finished else x["issued_date"]
        lines.append(f"  {day}  {x['address'].title()}, {x['zip']}  {x['description'][:70]}{who}")
    if len(rows) > 15:
        lines.append(f"  ...and {len(rows) - 15} more in the attached spreadsheet.")
    lines += ["", f"Source: {metro['source']} ({metro['source_url']}). Public records; may be incomplete or delayed."]
    txt_path = os.path.join(out, stem + ".txt")
    with open(txt_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return rows, csv_path, txt_path


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--metro", choices=sorted(FETCHERS))
    ap.add_argument("--cats", default="pools", help="comma-separated job types (default: pools)")
    ap.add_argument("--zips", default="", help="comma-separated ZIP codes (Chicago: community area numbers)")
    ap.add_argument("--days", type=int, default=7, help="days back from --until (default 7)")
    ap.add_argument("--since", help="first issue date, YYYY-MM-DD (overrides --days)")
    ap.add_argument("--until", help="last issue date, YYYY-MM-DD (default today)")
    ap.add_argument("--stage", choices=["issued", "finished"], default="issued",
                    help="issued: permits issued in the window (default). finished: work that passed its final "
                         "inspection in the window (" + ", ".join(sorted(FINISHED)) + " only)")
    ap.add_argument("--include-existing", action="store_true",
                    help="with --stage finished and pools: keep work on pools that already existed")
    ap.add_argument("--name", default="", help="customer or prospect name, used in the file name")
    ap.add_argument("--out", default="briefs")
    ap.add_argument("--list", action="store_true", help="show the job types each metro supports")
    a = ap.parse_args()

    if a.list or not a.metro:
        for m, cats in JOB_TYPES.items():
            print(f"{m:14s} {cats}")
        return 0 if a.list else 2

    until = dt.date.fromisoformat(a.until) if a.until else dt.date.today()
    since = dt.date.fromisoformat(a.since) if a.since else until - dt.timedelta(days=a.days - 1)
    cats = [c.strip() for c in a.cats.split(",") if c.strip()]
    unknown = [c for c in cats if c not in JOB_TYPES[a.metro].split()]
    if unknown:
        print(f"{a.metro} has no job type {', '.join(unknown)}. Choose from: {JOB_TYPES[a.metro]}")
        return 2
    zips = {z.strip() for z in a.zips.split(",") if z.strip()}
    finished = a.stage == "finished"
    if finished and a.metro not in FINISHED:
        print(f"The {a.metro} feed does not say when work passed final inspection. "
              f"--stage finished works for: {', '.join(sorted(FINISHED))}")
        return 2

    rows, csv_path, txt_path = write_brief(a.metro, cats, zips, since, until, a.stage, a.include_existing,
                                           a.name, a.out)
    print(f"{len(rows)} permits -> {csv_path}\nsummary -> {txt_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
