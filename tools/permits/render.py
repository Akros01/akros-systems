"""HTML for the permit pages. Plain templates, no JavaScript."""
import html
import json
import urllib.parse

from config import (ALMANAC_HOME, ALMANAC_SAMPLE, BASE_PATH, CATS, CONTACT_EMAIL, METROS, SITE,
                    TIPOFF_HOME, TIPOFF_PLANS)

E = html.escape


def fdate(d):
    return f"{d:%b} {d.day}, {d.year}"


def sdate(d):
    return f"{d:%b} {d.day}"


def num(n):
    return f"{n:,}"


def plural(n, one, many):
    return f"{num(n)} {one if n == 1 else many}"


def usd(v):
    return f"${v:,.0f}"


def path(*parts):
    return BASE_PATH + "/permits/" + "".join(p.strip("/") + "/" for p in parts if p)


def url(*parts):
    return SITE + "/permits/" + "".join(p.strip("/") + "/" for p in parts if p)


def area_word(metro, n=2):
    if METROS[metro]["area"] == "ZIP":
        return "ZIP code" if n == 1 else "ZIP codes"
    return "community area" if n == 1 else "community areas"


def area_name(metro, area, place):
    if METROS[metro]["area"] == "ZIP":
        return f"{place} ({area})" if place else f"ZIP {area}"
    return place or f"Area {area}"


def sample_mailto(metro_name, trade_hint=""):
    body = f"Trade: {trade_hint}\nZIP codes: \nMetro: {metro_name}\n"
    return (f"mailto:{CONTACT_EMAIL}?subject=" + urllib.parse.quote("Tipoff sample request")
            + "&body=" + urllib.parse.quote(body))


def gumroad(link, campaign):
    return link + "?" + urllib.parse.urlencode({"utm_source": "akros-permit-pages", "utm_medium": "referral",
                                                "utm_campaign": campaign})


BRAND_SVG = ('<svg class="brand-mark" viewBox="0 0 40 40" aria-hidden="true" focusable="false">'
             '<rect width="40" height="40" fill="#0d2635"/><path d="M7 29 20 9l13 20" fill="none" '
             'stroke="#f05a28" stroke-width="3.2"/><path d="M13 29h14" stroke="#f7fbfc" stroke-width="2.6"/></svg>')

ICON = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 64 64'%3E%3Crect width='64' "
        "height='64' fill='%230d2635'/%3E%3Cpath d='M13 45 32 17l19 28' fill='none' stroke='%23f05a28' "
        "stroke-width='5'/%3E%3Cpath d='M22 45h20' stroke='%23f7fbfc' stroke-width='4'/%3E%3C/svg%3E")


def page(*, title, description, canonical, body, jsonld, crumbs):
    crumb_ld = {
        "@context": "https://schema.org", "@type": "BreadcrumbList",
        "itemListElement": [{"@type": "ListItem", "position": i + 1, "name": n, "item": u}
                            for i, (n, u) in enumerate(crumbs)],
    }
    blocks = "".join(f'<script type="application/ld+json">{json.dumps(b, ensure_ascii=False)}</script>\n'
                     for b in [jsonld, crumb_ld] if b)
    sep = ' <span aria-hidden="true">/</span> '
    links = [f'<a href="{E(u.replace(SITE, BASE_PATH))}">{E(n)}</a>' for n, u in crumbs[:-1]]
    crumb_html = sep.join(links + [f'<span aria-current="page">{E(crumbs[-1][0])}</span>'])
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{E(title)}</title>
<meta name="description" content="{E(description)}">
<link rel="canonical" href="{E(canonical)}">
<meta name="theme-color" content="#0d2635">
<meta property="og:type" content="website">
<meta property="og:title" content="{E(title)}">
<meta property="og:description" content="{E(description)}">
<meta property="og:url" content="{E(canonical)}">
<meta name="twitter:card" content="summary">
<link rel="icon" href="{ICON}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@600;700&family=Barlow:wght@400;500;600&display=swap" rel="stylesheet">
<link rel="stylesheet" href="{BASE_PATH}/permits/assets/permits.css">
{blocks}</head>
<body>
<a class="skip-link" href="#main">Skip to content</a>
<header class="site-header">
  <div class="wrap header-inner">
    <a class="brand" href="{path()}" aria-label="Akros Systems permit data home">{BRAND_SVG}<span class="brand-name">Akros Systems<span>Permit activity / public record</span></span></a>
    <nav class="site-nav" aria-label="Main">
      <a href="{path()}">All metros</a>
      <a href="{ALMANAC_HOME}">$29 reports</a>
      <a class="nav-cta" href="{TIPOFF_HOME}">Tipoff weekly brief</a>
    </nav>
  </div>
</header>
<main id="main" class="wrap">
<p class="crumbs">{crumb_html}</p>
{body}
</main>
<footer class="site-footer">
  <div class="wrap footer-inner">
    <p><strong>Akros Systems</strong> · Massachusetts, USA. Counts come from public open-data permit feeds and are rebuilt every week. These pages publish no owner names, phone numbers or street addresses.</p>
    <p><a href="{path('about')}">About this data</a> · <a href="{TIPOFF_HOME}">Tipoff</a> · <a href="{ALMANAC_HOME}">Permit Almanac</a> · <a href="mailto:{CONTACT_EMAIL}">{CONTACT_EMAIL}</a></p>
  </div>
</footer>
</body>
</html>
"""


def stats(items):
    cells = "".join(f'<div class="stat"><dt>{E(k)}</dt><dd>{v}</dd></div>' for k, v in items)
    return f'<dl class="stats">{cells}</dl>'


def weekly_chart(weeks, counts, caption):
    top = max(counts) or 1
    cols = []
    for i, ((_, wk_end), c) in enumerate(zip(weeks, counts)):
        h = max(2, round(100 * c / top))
        latest = " latest" if i == len(counts) - 1 else ""
        cols.append(f'<div class="bar-col{latest}"><span class="bar-val">{num(c)}</span>'
                    f'<span class="bar" style="height:{h}%"></span><span class="bar-lbl">{E(sdate(wk_end))}</span></div>')
    label = "; ".join(f"week ending {sdate(w[1])}: {c}" for w, c in zip(weeks, counts))
    return (f'<figure class="weekly"><div class="bars" role="img" aria-label="{E(caption)}. {E(label)}">'
            + "".join(cols) + f'</div><figcaption>{E(caption)}. Each bar is a week ending on the date shown.</figcaption></figure>')


def change_text(cur, prev, valid):
    if not valid or prev < 10:
        return "—"
    pct = round(100 * (cur - prev) / prev)
    return "about even" if pct == 0 else (f"+{pct}%" if pct > 0 else f"−{abs(pct)}%")


def change_sentence(cur, prev, valid):
    if not valid or prev < 10:
        return ""
    pct = round(100 * (cur - prev) / prev)
    if pct == 0:
        return " That is about the same as the four weeks before."
    return f" That is {abs(pct)}% {'more' if pct > 0 else 'fewer'} than in the four weeks before."


def cta_block(metro, cat=None, campaign=""):
    m = METROS[metro]
    pool_note = " Pool service is available on the Report plan." if cat == "pools" else ""
    trade_hint = ", ".join(CATS[cat]["trades"][:1]) if cat and CATS[cat].get("trades") else ""
    almanac_line = ("lists every residential permit for one month in "
                    f"{E(m['short'])}, one row per permit with its address, job type and ZIP")
    if cat == "pools":
        almanac_line += ", and prints every pool and spa address"
    parts = []
    if m["tipoff"]:
        parts.append(f"""<section class="cta" aria-labelledby="cta-tipoff-{E(metro)}">
  <p class="cta-kicker">Tipoff weekly brief</p>
  <h2 id="cta-tipoff-{E(metro)}">Get these permits every week, filtered to your ZIP codes.</h2>
  <p>Tipoff sends the newest matching residential permits for your trade and ZIP codes every week, with the job and property details from the public record. Report is $297 a month after a 14-day trial (card required) and is shared with up to 3 contractors in your trade and ZIP.{pool_note}</p>
  <p class="cta-actions"><a class="button" href="{TIPOFF_PLANS}">See Tipoff plans</a> <a class="text-link" href="{E(sample_mailto(m['name'], trade_hint))}">Email your trade and ZIPs for a free sample</a></p>
</section>""")
    parts.append(f"""<section class="cta cta-alt" aria-labelledby="cta-almanac-{E(metro)}">
  <p class="cta-kicker">Permit Almanac</p>
  <h2 id="cta-almanac-{E(metro)}">Want the addresses now?</h2>
  <p>The {E(m['short'])} report {almanac_line}. $29, one-time; $69 for any three metros.</p>
  <p class="cta-actions"><a class="button" href="{E(gumroad(m['almanac'], campaign))}">Buy the {E(m['short'])} report, $29</a> <a class="text-link" href="{ALMANAC_SAMPLE}">See a free sample first</a></p>
</section>""")
    if not m["tipoff"]:
        parts.append(f'<p class="note">Tipoff\'s weekly brief does not cover {E(m["short"])} yet. '
                     f'<a href="mailto:{CONTACT_EMAIL}?subject={urllib.parse.quote("Tipoff in " + m["short"])}">Email us</a> if you want it here.</p>')
    return '<div class="cta-grid">' + "".join(parts) + "</div>"


def about_data(metro, agg):
    m = METROS[metro]
    lag = f" {E(m['lag'])}" if m.get("lag") else ""
    return f"""<section class="about" aria-labelledby="about-{E(metro)}">
  <h2 id="about-{E(metro)}">About these numbers</h2>
  <p>Source: <a href="{E(m['source_url'])}">{E(m['source'])}</a>. {E(m['scope'])}{lag}</p>
  <p>Counts run through {E(fdate(agg['end']))}, the latest date with a full week of records in the feed. We sort each permit into a job type from its permit type and filed scope of work. A permit is counted once, on its issue date. Cities revise records after they publish them, and a permit is not a guarantee of a job.</p>
  <p>These pages show counts only. They do not list owner names, phone numbers or street addresses. <a href="{path('about')}">How we build these pages</a>.</p>
</section>"""


def area_table(metro, rows, total, caption, limit=40):
    word = METROS[metro]["area"]
    body = []
    for area, place, n in rows[:limit]:
        share = f"{round(100 * n / total)}%" if total else "—"
        label = area if word == "ZIP" else (place or area)
        place_cell = E(place or "") if word == "ZIP" else ""
        body.append(f'<tr><th scope="row">{E(label)}</th>' + (f"<td>{place_cell}</td>" if word == "ZIP" else "")
                    + f'<td class="n">{num(n)}</td><td class="n">{share}</td></tr>')
    more = ""
    if len(rows) > limit:
        rest = sum(n for _, _, n in rows[limit:])
        more = f'<p class="note">Plus {plural(len(rows) - limit, area_word(metro, 1), area_word(metro))} with {num(rest)} more.</p>'
    head = (f'<tr><th scope="col">{E(word)}</th>' + ('<th scope="col">Place</th>' if word == "ZIP" else "")
            + '<th scope="col" class="n">Permits</th><th scope="col" class="n">Share</th></tr>')
    return (f'<div class="table-wrap"><table><caption>{E(caption)}</caption><thead>{head}</thead>'
            f'<tbody>{"".join(body)}</tbody></table></div>{more}')
