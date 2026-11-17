"""Storm reports for roofing, siding, gutter and window companies, anywhere in the US.

Reads the NOAA Storm Prediction Center's daily storm reports (hail of 1 inch or more, damaging wind,
tornadoes), tags each with the nearest ZIP code (Census ZIP centroids, zcta.csv), and writes:

  * public pages: permits/storms/ (the whole country) and permits/storms/<state>/   (build.py calls build())
  * a customer's list:  python3 tools/permits/storms.py --state TX --counties Collin,Denton --days 7
                        python3 tools/permits/storms.py --zips 75009,75078 --radius 10 --days 7

Reports come from spotters, emergency managers and the public, so they mark where a storm was seen,
not every street it hit. Times are UTC; a storm day runs from 12:00 UTC to 12:00 UTC the next day.
"""
import argparse
import collections
import csv
import datetime as dt
import json
import math
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
SPC = "https://www.spc.noaa.gov/climo/reports/{d:%y%m%d}_rpts_{kind}.csv"
KINDS = {"hail": "Hail", "wind": "Wind", "torn": "Tornado"}
DIRECTION = __import__("re").compile(r"\b(N|S|E|W|Ne|Nw|Se|Sw|Nne|Ene|Ese|Sse|Ssw|Wsw|Wnw|Nnw)\b")
STATES = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas", "CA": "California", "CO": "Colorado",
    "CT": "Connecticut", "DE": "Delaware", "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia",
    "HI": "Hawaii", "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland", "MA": "Massachusetts",
    "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi", "MO": "Missouri", "MT": "Montana",
    "NE": "Nebraska", "NV": "Nevada", "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico",
    "NY": "New York", "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina", "SD": "South Dakota",
    "TN": "Tennessee", "TX": "Texas", "UT": "Utah", "VT": "Vermont", "VA": "Virginia", "WA": "Washington",
    "WV": "West Virginia", "WI": "Wisconsin", "WY": "Wyoming", "PR": "Puerto Rico",
}


def fetch_day(day, kind):
    url = SPC.format(d=day, kind=kind)
    req = urllib.request.Request(url, headers={"User-Agent": "akros-permit-pages/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            text = r.read().decode("utf-8", "replace")
    except Exception:  # a missing day is skipped, not fatal
        return []
    out = []
    for row in csv.DictReader(text.splitlines()):
        try:
            lat, lon = float(row["Lat"]), float(row["Lon"])
        except (KeyError, TypeError, ValueError):
            continue
        measure = row.get("Size") or row.get("Speed") or row.get("F_Scale") or ""
        out.append({"day": day.isoformat(), "time": (row.get("Time") or "").zfill(4), "kind": kind,
                    "measure": measure.strip(), "location": DIRECTION.sub(lambda m: m.group(0).upper(),
                                                                       (row.get("Location") or "").strip().title()),
                    "county": (row.get("County") or "").strip().title(), "state": (row.get("State") or "").strip(),
                    "lat": lat, "lon": lon, "comments": (row.get("Comments") or "").strip()})
    return out


class Zips:
    """Nearest ZIP code by centroid, from the Census ZIP Code Tabulation Areas."""
    def __init__(self, path=os.path.join(HERE, "zcta.csv")):
        self.grid = collections.defaultdict(list)
        with open(path, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                lat, lon = float(r["lat"]), float(r["lon"])
                self.grid[(int(lat * 2), int(lon * 2))].append((r["zip"], lat, lon))
        self.points = {z: (la, lo) for cell in self.grid.values() for z, la, lo in cell}

    @staticmethod
    def miles(a, b, c, d):
        p = math.pi / 180
        h = (math.sin((c - a) * p / 2) ** 2 + math.cos(a * p) * math.cos(c * p) * math.sin((d - b) * p / 2) ** 2)
        return 7917.6 * math.asin(math.sqrt(h))

    def nearest(self, lat, lon):
        best = None
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                for z, la, lo in self.grid.get((int(lat * 2) + dy, int(lon * 2) + dx), ()):
                    dist = self.miles(lat, lon, la, lo)
                    if best is None or dist < best[1]:
                        best = (z, dist)
        return best[0] if best else ""


def label(r):
    if r["kind"] == "hail":
        try:
            return f'{int(r["measure"]) / 100:.2f}" hail'
        except ValueError:
            return "Hail"
    if r["kind"] == "wind":
        return f'{r["measure"]} mph wind' if r["measure"].isdigit() else "Damaging wind"
    return f"Tornado ({r['measure']})" if r["measure"] and r["measure"] != "UNK" else "Tornado"


def collect(today, days, zips=None):
    reports = []
    for i in range(1, days + 1):
        day = today - dt.timedelta(days=i)
        for kind in KINDS:
            reports.extend(fetch_day(day, kind))
    zips = zips or Zips()
    for r in reports:
        r["zip"] = zips.nearest(r["lat"], r["lon"])
        r["what"] = label(r)
    reports.sort(key=lambda r: (r["day"], r["time"]), reverse=True)
    return reports


# ------------------------------------------------------------------ pages
def build(today, out_dir, write, R, offline=False):
    """Write the storm pages; return their URLs. Called by build.py. Offline, re-renders the saved reports."""
    saved = os.path.join(out_dir, "data", "storms.json")
    if offline and os.path.exists(saved):
        with open(saved, encoding="utf-8") as f:
            data = json.load(f)
        today, reports = dt.date.fromisoformat(data["built"]), data["reports"]
    else:
        reports = collect(today, 30)
        with open(saved, "w", encoding="utf-8") as f:
            json.dump({"built": today.isoformat(), "reports": reports}, f)
    start = today - dt.timedelta(days=30)
    end = today - dt.timedelta(days=1)
    by_state = collections.defaultdict(list)
    for r in reports:
        if r["state"] in STATES:
            by_state[r["state"]].append(r)
    urls = []
    rows = "".join(
        f'<tr><th scope="row"><a href="{R.path("storms", st.lower())}">{R.E(STATES[st])}</a></th>'
        f'<td class="n">{R.num(sum(1 for r in rs if r["kind"] == "hail"))}</td>'
        f'<td class="n">{R.num(sum(1 for r in rs if r["kind"] == "wind"))}</td>'
        f'<td class="n">{R.num(sum(1 for r in rs if r["kind"] == "torn"))}</td></tr>'
        for st, rs in sorted(by_state.items(), key=lambda kv: -len(kv[1])))
    hail = [r for r in reports if r["kind"] == "hail"]
    biggest = sorted(hail, key=lambda r: -int(r["measure"]) if r["measure"].isdigit() else 0)[:12]
    big_rows = "".join(f'<tr><td>{R.E(R.sdate(dt.date.fromisoformat(r["day"])))}</td><td>{R.E(r["what"])}</td>'
                       f'<td>{R.E(r["location"])}, {R.E(r["county"])} County, {R.E(r["state"])}</td>'
                       f'<td>{R.E(r["zip"])}</td></tr>' for r in biggest)
    cta = storm_cta(R)
    body = f"""<section class="hero">
  <p class="category">NOAA storm reports · Last 30 days · Updated {R.E(R.fdate(today))}</p>
  <h1>Hail and wind reports by state</h1>
  <p class="lede">{R.num(len(hail))} hail reports of an inch or more, {R.num(sum(1 for r in reports if r['kind'] == 'wind'))} damaging-wind reports and {R.num(sum(1 for r in reports if r['kind'] == 'torn'))} tornado reports across {R.num(len(by_state))} states from {R.E(R.fdate(start))} to {R.E(R.fdate(end))}, each tagged with the nearest ZIP code.</p>
</section>
<section class="block"><h2>By state</h2><div class="table-wrap"><table><caption>Storm reports in the last 30 days</caption><thead><tr><th scope="col">State</th><th scope="col" class="n">Hail</th><th scope="col" class="n">Wind</th><th scope="col" class="n">Tornado</th></tr></thead><tbody>{rows or '<tr><td colspan="4">No reports in this window.</td></tr>'}</tbody></table></div></section>
<section class="block"><h2>Largest hail</h2><div class="table-wrap"><table><caption>Largest hail reports in the last 30 days</caption><thead><tr><th scope="col">Day</th><th scope="col">Report</th><th scope="col">Where</th><th scope="col">Nearest ZIP</th></tr></thead><tbody>{big_rows or '<tr><td colspan="4">No hail reports in this window.</td></tr>'}</tbody></table></div></section>
{cta}
{about(R)}"""
    write("storms", R.page(title="Hail and wind reports by state, last 30 days | Akros Systems",
                           description=f"{len(hail)} hail and {sum(1 for r in reports if r['kind'] == 'wind')} damaging-wind reports in the last 30 days by state, county and nearest ZIP. From NOAA storm reports, updated weekly.",
                           canonical=R.url("storms"), body=body, jsonld=dataset_ld(R, "US storm reports, last 30 days", today),
                           crumbs=[("Permit activity", R.url()), ("Storm reports", R.url("storms"))]))
    urls.append(R.url("storms"))
    for st, rs in by_state.items():
        counties = collections.Counter(r["county"] for r in rs)
        crow = "".join(f'<tr><th scope="row">{R.E(c)}</th><td class="n">{R.num(n)}</td></tr>' for c, n in counties.most_common(25))
        lrow = "".join(f'<tr><td>{R.E(R.sdate(dt.date.fromisoformat(r["day"])))}</td><td>{R.E(r["what"])}</td><td>{R.E(r["location"])}</td>'
                       f'<td>{R.E(r["county"])}</td><td>{R.E(r["zip"])}</td></tr>' for r in rs[:60])
        name = STATES[st]
        body = f"""<section class="hero">
  <p class="category">NOAA storm reports · {R.E(name)} · Last 30 days</p>
  <h1>Hail and wind reports in {R.E(name)}</h1>
  <p class="lede">{R.num(sum(1 for r in rs if r['kind'] == 'hail'))} hail reports of an inch or more, {R.num(sum(1 for r in rs if r['kind'] == 'wind'))} damaging-wind reports and {R.num(sum(1 for r in rs if r['kind'] == 'torn'))} tornado reports in {R.E(name)} from {R.E(R.fdate(start))} to {R.E(R.fdate(end))}.</p>
</section>
<section class="block"><h2>By county</h2><div class="table-wrap"><table><caption>Storm reports by county, last 30 days</caption><thead><tr><th scope="col">County</th><th scope="col" class="n">Reports</th></tr></thead><tbody>{crow}</tbody></table></div></section>
<section class="block"><h2>Every report, newest first</h2><div class="table-wrap"><table><caption>Storm reports in {R.E(name)}</caption><thead><tr><th scope="col">Day</th><th scope="col">Report</th><th scope="col">Place</th><th scope="col">County</th><th scope="col">Nearest ZIP</th></tr></thead><tbody>{lrow}</tbody></table></div></section>
{cta}
{about(R)}"""
        write(os.path.join("storms", st.lower()), R.page(
            title=f"Hail and wind reports in {name}, last 30 days | Akros Systems",
            description=f"Hail, damaging-wind and tornado reports in {name} for the last 30 days, by county and nearest ZIP code. From NOAA storm reports.",
            canonical=R.url("storms", st.lower()), body=body, jsonld=dataset_ld(R, f"Storm reports in {name}", today),
            crumbs=[("Permit activity", R.url()), ("Storm reports", R.url("storms")), (name, R.url("storms", st.lower()))]))
        urls.append(R.url("storms", st.lower()))
    return urls


def storm_cta(R):
    return f"""<div class="cta-grid"><section class="cta"><p class="cta-kicker">Tipoff storm alerts</p>
  <h2>Know where hail hit before your competitors do.</h2>
  <p>Roofing, siding, gutter and window companies: Tipoff sends every hail, wind and tornado report in your counties each week, with the nearest ZIP code, and adds the new permits we track where we cover your city. A Territory gives one company per trade each group of counties.</p>
  <p class="cta-actions"><a class="button" href="{R.E(R.territory_mailto('Storm alerts', 'Roofing'))}">Check if your counties are open</a> <a class="text-link" href="{R.TIPOFF_PLANS}">See plans</a></p>
</section></div>"""


def about(R):
    return """<section class="about"><h2>About these reports</h2>
  <p>Source: <a href="https://www.spc.noaa.gov/climo/reports/">NOAA Storm Prediction Center storm reports</a>. Spotters, emergency managers and the public report hail of an inch or more, damaging wind and tornadoes; a report marks where a storm was seen, not every street it hit. Reports are preliminary and can be revised. A storm day runs from 12:00 UTC to 12:00 UTC the next day. Each report is tagged with the ZIP code whose center is nearest, from the Census Bureau's ZIP Code Tabulation Areas.</p>
</section>"""


def dataset_ld(R, name, today):
    return {"@context": "https://schema.org", "@type": "Dataset", "name": name,
            "description": "Hail, damaging-wind and tornado reports from the NOAA Storm Prediction Center, tagged with the nearest ZIP code.",
            "creator": {"@type": "Organization", "name": "Akros Systems", "url": R.TIPOFF_HOME},
            "isBasedOn": "https://www.spc.noaa.gov/climo/reports/", "dateModified": today.isoformat(),
            "isAccessibleForFree": True}


# ------------------------------------------------------------------ customer list
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--state", help="two-letter state, with --counties")
    ap.add_argument("--counties", default="", help="comma-separated county names (as NOAA writes them)")
    ap.add_argument("--zips", default="", help="comma-separated ZIP codes; reports within --radius miles of any")
    ap.add_argument("--radius", type=float, default=10.0)
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--kinds", default="hail,wind,torn")
    ap.add_argument("--out", default="briefs")
    a = ap.parse_args()
    today = dt.date.today()
    zipdb = Zips()
    reports = collect(today, a.days, zipdb)
    kinds = set(a.kinds.split(","))
    counties = {c.strip().lower() for c in a.counties.split(",") if c.strip()}
    targets = [zipdb.points[z] for z in (x.strip() for x in a.zips.split(",")) if z in zipdb.points]
    keep = []
    for r in reports:
        if r["kind"] not in kinds:
            continue
        if a.state and r["state"] != a.state.upper():
            continue
        if counties and r["county"].lower() not in counties:
            continue
        if targets and min(Zips.miles(r["lat"], r["lon"], la, lo) for la, lo in targets) > a.radius:
            continue
        keep.append(r)
    os.makedirs(a.out, exist_ok=True)
    stem = os.path.join(a.out, f"storms-{(a.state or 'zips').lower()}-{today.isoformat()}")
    with open(stem + ".csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["day", "time_utc", "report", "place", "county", "state", "nearest_zip", "lat", "lon", "comments"])
        for r in keep:
            w.writerow([r["day"], r["time"], r["what"], r["location"], r["county"], r["state"], r["zip"],
                        r["lat"], r["lon"], r["comments"]])
    print(f"{len(keep)} storm reports -> {stem}.csv")
    return 0


if __name__ == "__main__":
    sys.exit(main())
