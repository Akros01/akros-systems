#!/usr/bin/env python3
"""Rebuild the permit pages from the cities' open-data feeds.

    python3 tools/permits/build.py            fetch fresh data, then render
    python3 tools/permits/build.py --offline  render from permits/data/*.json

A metro whose feed fails keeps its last saved numbers, so a bad week never
publishes empty pages. Writes permits/**/index.html, permits/data/*.json,
permits/assets/permits.css and sitemap.xml.
"""
import collections
import datetime as dt
import json
import os
import shutil
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import render as R  # noqa: E402
import sources  # noqa: E402
from config import (ALMANAC_HOME, CATS, METROS, MIN_FOR_PAGE, PAGE_CATS, SITE, TIPOFF_HOME,  # noqa: E402
                    WEEKS_SHOWN, WINDOW_DAYS)

ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
OUT = os.path.join(ROOT, "permits")
DATA = os.path.join(OUT, "data")
DAY = dt.timedelta(days=1)
E = R.E


# ------------------------------------------------------------------ data
COMPLETE_SHARE = 0.8


def complete_end(recs, latest):
    """Latest date whose trailing week holds at least 80% of a normal week."""
    days = collections.Counter(r["issued"] for r in recs)

    def week(end):
        return sum(days.get((end - i * DAY).isoformat(), 0) for i in range(7))

    for back in range(36):
        end = latest - back * DAY
        base = statistics.median(week(end - 7 * k * DAY) for k in range(1, 7))
        if base == 0 or week(end) >= COMPLETE_SHARE * base:
            return end
    return latest - WINDOW_DAYS * DAY


def aggregate(metro, recs, today):
    seen, clean = set(), []
    for r in recs:
        if r["issued"] > today.isoformat() or r["id"] in seen:
            continue
        seen.add(r["id"])
        clean.append(r)
    latest = max(dt.date.fromisoformat(r["issued"]) for r in clean)
    end = complete_end(clean, latest)
    start = end - (WINDOW_DAYS - 1) * DAY
    pstart, pend = start - WINDOW_DAYS * DAY, start - DAY
    weeks = [(end - (7 * i + 6) * DAY, end - 7 * i * DAY) for i in reversed(range(WEEKS_SHOWN))]

    def blank():
        return {"cur": 0, "prev": 0, "weekly": [0] * WEEKS_SHOWN, "areas": collections.Counter(),
                "places": collections.defaultdict(collections.Counter), "values": [],
                "builders": collections.Counter()}

    cats = collections.defaultdict(blank)
    total = blank()
    for r in clean:
        day = dt.date.fromisoformat(r["issued"])
        targets = [cats[c] for c in r["cats"]] + [total]
        for i, (ws, we) in enumerate(weeks):
            if ws <= day <= we:
                for t in targets:
                    t["weekly"][i] += 1
        if start <= day <= end:
            for t in targets:
                t["cur"] += 1
                if r["area"]:
                    t["areas"][r["area"]] += 1
                    if r["place"]:
                        t["places"][r["area"]][r["place"]] += 1
                if r.get("builder"):
                    t["builders"][r["builder"]] += 1
            if r["value"]:
                for c in r["cats"]:
                    cats[c]["values"].append(r["value"])
        elif pstart <= day <= pend:
            for t in targets:
                t["prev"] += 1

    def finish(b):
        areas = [[a, (b["places"][a].most_common(1)[0][0] if b["places"][a] else None), n]
                 for a, n in b["areas"].most_common()]
        vals = sorted(b["values"])
        median = statistics.median(vals) if len(vals) >= 8 and len(vals) >= 0.5 * max(b["cur"], 1) else None
        # A builder is published only if the name reads as a business (2+ permits) or is on 3+ permits,
        # so an owner-builder's own name never appears.
        builders = [[name, n] for name, n in b["builders"].most_common()
                    if n >= 3 or (n >= 2 and sources.BUSINESS.search(name))][:10]
        return {"cur": b["cur"], "prev": b["prev"], "weekly": b["weekly"], "areas": areas,
                "median_value": median, "valued": len(vals), "builders": builders}

    return {
        "metro": metro,
        "built": today.isoformat(),
        "latest": latest.isoformat(),
        "end": end.isoformat(),
        "start": start.isoformat(),
        "weeks": [[a.isoformat(), b.isoformat()] for a, b in weeks],
        "total": finish(total),
        "cats": {c: finish(b) for c, b in cats.items()},
    }


def finished_counts(fetch, agg):
    """Permits whose final inspection passed inside the page window, by job type. Counts only:
    the detail records are read for the inspection date and then dropped."""
    try:
        recs = fetch(agg["start"], detail=True, finished=True)
    except Exception as err:  # the main numbers still publish
        print(f"finished-work fetch failed ({err!r})", file=sys.stderr)
        return {}
    out, seen = collections.Counter(), set()
    for r in recs:
        done = r["detail"].get("finished_date", "")
        if r["id"] in seen or not agg["start"] <= done <= agg["end"]:
            continue
        seen.add(r["id"])
        for c in r["cats"]:
            if c == "pools" and sources.EXISTING_POOL.search(r["detail"].get("description", "")):
                continue
            out[c] += 1
    return dict(out)


def load_dates(agg):
    agg = dict(agg)
    for k in ("end", "start", "latest", "built"):
        agg[k] = dt.date.fromisoformat(agg[k])
    agg["weeks"] = [(dt.date.fromisoformat(a), dt.date.fromisoformat(b)) for a, b in agg["weeks"]]
    return agg


def page_cats(agg):
    return [c for c in PAGE_CATS if c in agg["cats"] and agg["cats"][c]["cur"] >= MIN_FOR_PAGE]


# ----------------------------------------------------------------- pages
def write(rel, text):
    full = os.path.join(OUT, rel, "index.html") if rel else os.path.join(OUT, "index.html")
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        f.write(text)


def dataset_ld(name, description, canonical, metro, agg):
    return {
        "@context": "https://schema.org", "@type": "Dataset",
        "name": name, "description": description, "url": canonical,
        "creator": {"@type": "Organization", "name": "Akros Systems", "url": TIPOFF_HOME},
        "spatialCoverage": {"@type": "Place", "name": METROS[metro]["name"]},
        "temporalCoverage": f"{agg['start'].isoformat()}/{agg['end'].isoformat()}",
        "isBasedOn": METROS[metro]["source_url"],
        "dateModified": agg["built"].isoformat(),
        "isAccessibleForFree": True,
        "variableMeasured": "Residential building permits issued",
    }


def top_area_sentence(metro, areas):
    if not areas or areas[0][2] < 2:
        return ""
    area, place, n = areas[0]
    if len(areas) == 1:
        return f" All of them were in {R.area_name(metro, area, place)}."
    return f" {R.area_name(metro, area, place)} had the most, with {R.num(n)}."


def metro_page(metro, agg, all_aggs):
    m, t = METROS[metro], agg["total"]
    ok = not m.get("no_change")
    cats_sorted = sorted(agg["cats"].items(), key=lambda kv: (kv[0] not in PAGE_CATS, -kv[1]["cur"]))
    cats_sorted = [(c, b) for c, b in cats_sorted if c != "wildfire-rebuilds" or b["cur"]]
    pages = page_cats(agg)
    lead_cat, lead = max(((c, b) for c, b in agg["cats"].items() if c != "wildfire-rebuilds"),
                         key=lambda kv: kv[1]["cur"])
    title = f"{m['short']} residential building permits: last 4 weeks by job type and ZIP | Akros Systems"
    if m["area"] != "ZIP":
        title = f"{m['short']} residential building permits: last 4 weeks by job type and area | Akros Systems"
    desc = (f"{R.num(t['cur'])} residential permits issued in {m['name']} in the four weeks to "
            f"{R.fdate(agg['end'])}, by job type and {R.area_word(metro, 1)}. Rebuilt weekly from public records.")
    canonical = R.url(metro)
    rows = []
    for c, b in cats_sorted:
        label = E(CATS[c]["label"])
        if c in pages:
            label = f'<a href="{R.path(metro, c)}">{label}</a>'
        cmp_cells = (f'<td class="n">{R.num(b["prev"])}</td><td class="n">{R.change_text(b["cur"], b["prev"], ok)}</td>'
                     if ok else "")
        rows.append(f'<tr><th scope="row">{label}</th><td class="n">{R.num(b["cur"])}</td>{cmp_cells}</tr>')
    cmp_head = ('<th scope="col" class="n">Previous 4 weeks</th><th scope="col" class="n">Change</th>' if ok else "")
    caption = ("Permits by job type, last four weeks and the four weeks before" if ok
               else "Permits by job type, last four weeks")
    table = (f'<div class="table-wrap"><table><caption>{caption}</caption><thead><tr><th scope="col">Job type</th>'
             f'<th scope="col" class="n">Last 4 weeks</th>{cmp_head}</tr></thead>'
             f'<tbody>{"".join(rows)}</tbody></table></div>')
    page_links = "".join(f'<li><a href="{R.path(metro, c)}">{E(CATS[c]["title"])} in {E(m["short"])}</a> '
                         f'<span>{R.num(agg["cats"][c]["cur"])} in 4 weeks</span></li>' for c in pages)
    other = "".join(f'<li><a href="{R.path(k)}">{E(METROS[k]["name"])}</a></li>' for k in METROS if k != metro and k in all_aggs)
    body = f"""<section class="hero">
  <p class="category">{E(m['name'])} · Residential permits · Data through {E(R.fdate(agg['end']))}</p>
  <h1>Residential permits in {E(m['short'])}</h1>
  <p class="lede">{E(R.num(t['cur']))} residential permits in the job types we track were issued in {E(m['short'])} in the four weeks to {E(R.fdate(agg['end']))}. {E(CATS[lead_cat]['label'])} led with {R.num(lead['cur'])}.{R.change_sentence(t['cur'], t['prev'], ok)}</p>
  {R.stats([("Last 4 weeks", R.num(t['cur'])), ("Last 7 days", R.num(t['weekly'][-1])), (R.area_word(metro).capitalize(), R.num(len(t['areas'])))] + ([("vs. prior 4 weeks", R.change_text(t['cur'], t['prev'], ok))] if ok else []))}
</section>
<section class="block"><h2>By job type</h2>{table}
<ul class="page-links">{page_links}</ul></section>
<section class="block"><h2>Week by week</h2>{R.weekly_chart(agg['weeks'], t['weekly'], f"Residential permits per week in {m['short']}, all tracked job types")}</section>
<section class="block"><h2>Busiest {E(R.area_word(metro))}</h2>{R.area_table(metro, t['areas'], t['cur'], f"Tracked residential permits by {R.area_word(metro, 1)}, last four weeks", limit=15)}</section>
{R.cta_block(metro, None, f"{metro}-hub")}
{R.about_data(metro, agg)}
<nav class="related" aria-label="Other metros"><h2>Other metros</h2><ul>{other}</ul></nav>"""
    ld = dataset_ld(f"Residential building permits in {m['name']}", desc, canonical, metro, agg)
    crumbs = [("Permit activity", R.url()), (m["name"], canonical)]
    return R.page(title=title, description=desc, canonical=canonical, body=body, jsonld=ld, crumbs=crumbs)


def cat_page(metro, cat, agg, all_aggs):
    m, c, b = METROS[metro], CATS[cat], agg["cats"][cat]
    ok = not m.get("no_change")
    end = R.fdate(agg["end"])
    word = R.area_word(metro)
    title = f"{c['title']} in {m['short']}: last 4 weeks by {R.area_word(metro, 1)} | Akros Systems"
    desc = (f"{R.num(b['cur'])} {c['noun']} issued in {m['name']} in the four weeks to {end}, by "
            f"{R.area_word(metro, 1)}, with weekly counts. From public permit records.")
    if len(desc) > 165:
        desc = (f"{R.num(b['cur'])} {c['short']} issued in {m['name']} in the four weeks to {end}, "
                f"by {R.area_word(metro, 1)}. From public permit records.")
    canonical = R.url(metro, cat)
    verb = "was" if b["cur"] == 1 else "were"
    lede = (f"{R.num(b['cur'])} {c['noun']} {verb} issued in {m['short']} in the four weeks to {end}, across "
            f"{R.plural(len(b['areas']), R.area_word(metro, 1), word)}.{top_area_sentence(metro, b['areas'])}"
            f"{R.change_sentence(b['cur'], b['prev'], ok)}")
    stat_items = [("Last 4 weeks", R.num(b["cur"])), ("Last 7 days", R.num(b["weekly"][-1])),
                  (word.capitalize(), R.num(len(b["areas"])))]
    if ok:
        stat_items.append(("vs. prior 4 weeks", R.change_text(b["cur"], b["prev"], ok)))
    if b.get("median_value"):
        stat_items.append(("Median declared value", R.usd(b["median_value"])))
    done = agg.get("finished", {}).get(cat, 0)
    if done:
        stat_items.append(("Passed final inspection", R.num(done)))
    extra = ""
    if done:
        if cat == "pools":
            what = (f"{R.num(done)} new pools in {E(m['short'])} passed the city's final inspection, so their "
                    "owners are now choosing who looks after them")
        else:
            what = f"{R.num(done)} {E(c['short'])} in {E(m['short'])} passed the city's final inspection"
        extra = (f'<p class="note">In the same four weeks, {what}. <a href="{TIPOFF_HOME}#plans">Tipoff</a> '
                 'sends their addresses every week.</p>')
    if cat == "wildfire-rebuilds":
        nh = agg["cats"].get("new-homes", {}).get("cur", 0)
        extra += (f'<p class="note">This page counts new single-family and duplex permits whose filed scope of work '
                 f'describes a 2025 wildfire rebuild. They are {round(100 * b["cur"] / nh) if nh else 0}% of the '
                 f'{R.num(nh)} <a href="{R.path(metro, "new-homes")}">new-home permits</a> in {E(m["short"])} over the same four weeks.</p>')
    trades = "".join(f"<li>{E(x)}</li>" for x in c["trades"])
    siblings = "".join(f'<li><a href="{R.path(metro, k)}">{E(CATS[k]["title"])} in {E(m["short"])}</a></li>'
                       for k in page_cats(agg) if k != cat)
    same_cat = "".join(f'<li><a href="{R.path(k, cat)}">{E(c["title"])} in {E(METROS[k]["short"])}</a></li>'
                       for k, a in all_aggs.items() if k != metro and cat in page_cats(a))
    value_note = ""
    if b.get("median_value"):
        value_note = (f'<p class="note">Median declared value uses the {R.num(b["valued"])} permits in this window '
                      'that list a job value. Declared values are what the applicant wrote on the permit.</p>')
    body = f"""<section class="hero">
  <p class="category">{E(m['name'])} · {E(c['label'])} · Data through {E(end)}</p>
  <h1>{E(c['title'])} in {E(m['short'])}</h1>
  <p class="lede">{E(lede)}</p>
  {R.stats(stat_items)}
  {extra}
</section>
<section class="block"><h2>Week by week</h2>{R.weekly_chart(agg['weeks'], b['weekly'], f"{c['title']} per week in {m['short']}")}{value_note}</section>
<section class="block"><h2>By {E(R.area_word(metro, 1))}</h2>{R.area_table(metro, b['areas'], b['cur'], f"{c['title']} by {R.area_word(metro, 1)}, last four weeks")}</section>
{R.builders_block(metro, cat, b.get('builders', []), b['cur'], end)}
<section class="block trades"><h2>Who works from {E(c['short'])}</h2><p>{E(c['why'])} Trades that start after this permit:</p><ul class="chips">{trades}</ul></section>
{R.cta_block(metro, cat, f"{metro}-{cat}")}
{R.about_data(metro, agg)}
<nav class="related" aria-label="Related pages"><h2>Related</h2><ul>{siblings}{same_cat}<li><a href="{R.path(metro)}">All residential permits in {E(m['short'])}</a></li></ul></nav>"""
    ld = dataset_ld(f"{c['title']} in {m['name']}", desc, canonical, metro, agg)
    crumbs = [("Permit activity", R.url()), (m["name"], R.url(metro)), (c["title"], canonical)]
    return R.page(title=title, description=desc, canonical=canonical, body=body, jsonld=ld, crumbs=crumbs)


def index_page(all_aggs, today):
    rows = []
    for k, agg in all_aggs.items():
        m = METROS[k]

        def cell(cat):
            b = agg["cats"].get(cat)
            if not b or not b["cur"]:
                return '<td class="n">—</td>'
            inner = R.num(b["cur"])
            if cat in page_cats(agg):
                inner = f'<a href="{R.path(k, cat)}">{inner}</a>'
            return f'<td class="n">{inner}</td>'
        rows.append(f'<tr><th scope="row"><a href="{R.path(k)}">{E(m["name"])}</a></th>'
                    f'<td>{E(R.fdate(agg["end"]))}</td><td class="n">{R.num(agg["total"]["cur"])}</td>'
                    f'{cell("new-homes")}{cell("pools")}{cell("additions-remodels")}</tr>')
    table = ('<div class="table-wrap"><table><caption>Residential permits issued in the four weeks to each date'
             '</caption><thead><tr><th scope="col">Metro</th><th scope="col">Data through</th>'
             '<th scope="col" class="n">All tracked</th><th scope="col" class="n">New homes</th>'
             '<th scope="col" class="n">Pools</th><th scope="col" class="n">Additions and remodels</th></tr></thead>'
             f'<tbody>{"".join(rows)}</tbody></table></div>')
    total = sum(a["total"]["cur"] for a in all_aggs.values())
    title = "Residential building permits by metro and ZIP, updated weekly | Akros Systems"
    desc = (f"{R.num(total)} residential permits in the last four weeks across Austin, Collin County, Dallas, "
            "Los Angeles, Sacramento and Chicago, by job type and ZIP. From public records, rebuilt weekly.")
    canonical = R.url()
    links = "".join(f'<li><a href="{R.path(k, c)}">{E(CATS[c]["title"])} in {E(METROS[k]["short"])}</a> '
                    f'<span>{R.num(a["cats"][c]["cur"])}</span></li>'
                    for c in PAGE_CATS for k, a in all_aggs.items() if c in page_cats(a))
    body = f"""<section class="hero">
  <p class="category">Public permit records · Rebuilt every week · Updated {E(R.fdate(today))}</p>
  <h1>Residential permit activity in six metros</h1>
  <p class="lede">Weekly counts of residential building permits by job type and ZIP code, read from each city's own open-data feed. {R.num(total)} permits in the last four weeks. Built by Akros Systems, the makers of the Tipoff weekly brief and the Permit Almanac.</p>
</section>
<section class="block"><h2>Metros</h2>{table}</section>
<section class="block"><h2>By job type</h2><ul class="page-links">{links}</ul></section>
<section class="block"><h2>How contractors use permit data</h2>
<p>A residential permit is filed while a job is still being planned. For the trades that come after it, a new pool, a new house or an addition is a sign that an owner will soon be choosing pool service, security, landscaping, fencing, window coverings or HVAC work. These pages show where that activity is happening. The addresses themselves are in the paid products below.</p></section>
<div class="cta-grid">
<section class="cta"><p class="cta-kicker">Tipoff weekly brief</p><h2>New permits for your trade and ZIPs, every week.</h2><p>Covers Austin, Collin County, Dallas, Los Angeles and Sacramento. Report is $297 a month after a 14-day trial (card required).</p><p class="cta-actions"><a class="button" href="{R.TIPOFF_PLANS}">See Tipoff plans</a></p></section>
<section class="cta cta-alt"><p class="cta-kicker">Permit Almanac</p><h2>One metro, one month, every permit.</h2><p>Every residential permit for a month, one row each, by job type and ZIP. $29 per metro, $69 for any three, $129 for all six.</p><p class="cta-actions"><a class="button" href="{ALMANAC_HOME}">See the six reports</a> <a class="text-link" href="{R.ALMANAC_SAMPLE}">Free sample</a></p></section>
</div>"""
    ld = {"@context": "https://schema.org", "@type": "Dataset",
          "name": "Residential building permit activity in six US metros", "description": desc, "url": canonical,
          "creator": {"@type": "Organization", "name": "Akros Systems", "url": TIPOFF_HOME},
          "spatialCoverage": [{"@type": "Place", "name": METROS[k]["name"]} for k in all_aggs],
          "dateModified": today.isoformat(), "isAccessibleForFree": True}
    return R.page(title=title, description=desc, canonical=canonical, body=body, jsonld=ld,
                  crumbs=[("Permit activity", canonical)])


def about_page(all_aggs, today):
    srcs = "".join(f'<li><strong>{E(METROS[k]["name"])}</strong>: <a href="{E(METROS[k]["source_url"])}">'
                   f'{E(METROS[k]["source"])}</a>. {E(METROS[k]["scope"])}'
                   + (f' {E(METROS[k]["lag"])}' if METROS[k].get("lag") else "") + "</li>" for k in all_aggs)
    canonical = R.url("about")
    body = f"""<section class="hero"><p class="category">Method and sources</p><h1>How these pages are built</h1>
<p class="lede">Every number on these pages comes from a city or county open-data feed, read again each week. Nothing is estimated or modeled.</p></section>
<section class="block prose"><h2>Sources</h2><ul>{srcs}</ul>
<h2>Method</h2>
<p>Each week we download the last few months of residential permits from every feed and sort each permit into a job type, using the permit type and the scope of work the applicant filed: new homes, pools and spas, additions and remodels, ADUs, HVAC, solar, re-roofs and so on. Permits that don't fit a tracked job type are left out of the counts.</p>
<p>Some feeds arrive late. For each metro we use the latest date whose trailing week holds at least 60% of a normal week's records, and count the four weeks to that date. The previous four weeks are shown for comparison.</p>
<p>A permit is counted once, on its issue date. Supplemental and revision permits are left out where the feed marks them.</p>
<h2>What we don't publish</h2>
<p>These pages show counts by job type and ZIP code (or community area in Chicago), and the companies named on the most permits. A company is listed only when its name reads as a business or appears on three or more permits, so homeowners who pull their own permits never appear. The pages never show owner names, phone numbers or street addresses, even where the public record includes them.</p>
<h2>Corrections</h2>
<p>Spot a number that looks wrong? Email <a href="mailto:{R.CONTACT_EMAIL}">{R.CONTACT_EMAIL}</a>.</p></section>"""
    return R.page(title="How the permit pages are built: sources and method | Akros Systems",
                  description="Sources, method and privacy rules behind Akros Systems' weekly residential permit pages for six US metros.",
                  canonical=canonical, body=body, jsonld=None,
                  crumbs=[("Permit activity", R.url()), ("About this data", canonical)])


def sitemap(urls, today):
    items = "".join(f"<url><loc>{u}</loc><lastmod>{today.isoformat()}</lastmod></url>" for u in urls)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{items}</urlset>\n')


# ------------------------------------------------------------------ main
def main(offline=False):
    today = dt.date.today()
    since = (today - dt.timedelta(days=105)).isoformat()
    os.makedirs(DATA, exist_ok=True)
    all_aggs = {}
    for metro, fetch in sources.FETCHERS.items():
        saved = os.path.join(DATA, f"{metro}.json")
        agg = None
        if not offline:
            try:
                recs = fetch(since)
                if len(recs) < 50:
                    raise ValueError(f"only {len(recs)} records")
                agg = aggregate(metro, recs, today)
                if metro in sources.FINISHED:
                    agg["finished"] = finished_counts(fetch, agg)
                with open(saved, "w", encoding="utf-8") as f:
                    json.dump(agg, f, indent=1)
                print(f"{metro}: {agg['total']['cur']} permits, data through {agg['end']}")
            except Exception as err:  # keep last week's numbers
                print(f"{metro}: fetch failed ({err!r}); using saved data", file=sys.stderr)
        if agg is None and os.path.exists(saved):
            with open(saved, encoding="utf-8") as f:
                agg = json.load(f)
        if agg is not None:
            all_aggs[metro] = load_dates(agg)
    if not all_aggs:
        sys.exit("No data for any metro; nothing written.")

    # Rebuild the page tree from scratch so retired pages disappear.
    for name in os.listdir(OUT):
        full = os.path.join(OUT, name)
        if os.path.isdir(full) and name not in ("data", "assets"):
            shutil.rmtree(full)
    os.makedirs(os.path.join(OUT, "assets"), exist_ok=True)
    shutil.copyfile(os.path.join(HERE, "permits.css"), os.path.join(OUT, "assets", "permits.css"))

    urls = [R.url()]
    write("", index_page(all_aggs, today))
    write("about", about_page(all_aggs, today))
    urls.append(R.url("about"))
    for metro, agg in all_aggs.items():
        write(metro, metro_page(metro, agg, all_aggs))
        urls.append(R.url(metro))
        for cat in page_cats(agg):
            write(os.path.join(metro, cat), cat_page(metro, cat, agg, all_aggs))
            urls.append(R.url(metro, cat))
    with open(os.path.join(ROOT, "sitemap.xml"), "w", encoding="utf-8") as f:
        f.write(sitemap(urls, today))
    with open(os.path.join(DATA, "urls.json"), "w", encoding="utf-8") as f:
        json.dump(urls, f, indent=1)
    print(f"Wrote {len(urls)} pages.")


if __name__ == "__main__":
    main(offline="--offline" in sys.argv)
