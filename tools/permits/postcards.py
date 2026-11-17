"""Postcards for Tipoff Territory customers: one card for each new matching homeowner, through PostGrid.

Customer files, previews and send logs hold street addresses, so they live under briefs/, which git
ignores. Never commit them. Cards go to "Current Resident": owner names are never used.

  # 1. Copy tools/permits/postcard-customer.example.json to briefs/customers/<name>.json and fill it in.
  # 2. Preview: writes the card images and the list of who would get one. Nothing is sent.
  python3 tools/permits/postcards.py --customer briefs/customers/acme.json --preview
  # 3. After the customer approves the design, set "approved": true in their file, then:
  POSTGRID_API_KEY=test_sk_... python3 tools/permits/postcards.py --customer briefs/customers/acme.json --send
  #    A PostGrid test key creates the orders without printing or charging. A live key mails and charges.

Each run looks back "days" days (default 7), sends finished-work cards first where the city reports
final inspections, skips any address this customer has already mailed, and stops at the monthly
allowance ("monthly_cards", default 300).
"""
import argparse
import base64
import csv
import datetime as dt
import hashlib
import html
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from brief import collect, slug  # noqa: E402
from config import METROS, TERRITORY_CARDS  # noqa: E402
from sources import FINISHED  # noqa: E402

API = "https://api.postgrid.com/print-mail/v1/postcards"
STATE = {"austin": "TX", "collin-county": "TX", "dallas": "TX", "los-angeles": "CA", "chicago": "IL",
         "sacramento": "CA"}
# Where the feed's place label is not a mailing city (LA plan areas, Chicago community areas), use the city.
MAIL_CITY = {"dallas": "Dallas", "los-angeles": "Los Angeles", "chicago": "Chicago", "sacramento": "Sacramento"}
HEADLINES = {
    ("pools", "finished"): "Your new pool is finished. Let's keep it that way.",
    ("pools", "issued"): "Building a pool? Line up its care now.",
    ("new-homes", "finished"): "Welcome home.",
    ("new-homes", "issued"): "Building a new home?",
}
LOG_FIELDS = ["sent_at", "stage", "permit_number", "address", "zip", "code", "postgrid_id", "live"]
E = html.escape


def card_code(customer, address, zip_code):
    """A short code printed on the card, so the customer can tell which calls came from it."""
    digest = hashlib.sha1(f"{customer}|{address.upper()}|{zip_code}".encode()).digest()
    return "T" + base64.b32encode(digest)[:5].decode()


def front_html(c, stage, cat):
    headline = c.get("headlines", {}).get(stage) or HEADLINES.get((cat, stage)) or c.get("headline") or c["company"]
    color = c.get("color", "#164b63")
    return f"""<html><head><style>
  @page {{ size: 6.25in 4.25in; margin: 0; }}
  body {{ margin: 0; width: 6.25in; height: 4.25in; background: {E(color)}; color: #fff;
         font-family: Helvetica, Arial, sans-serif; }}
  .safe {{ position: absolute; top: .3in; left: .35in; right: .35in; bottom: .3in; }}
  h1 {{ margin: .2in 0 0; font-size: 30pt; line-height: 1.05; font-weight: 800; }}
  .who {{ position: absolute; bottom: 0; left: 0; font-size: 15pt; font-weight: 700; }}
  .phone {{ position: absolute; bottom: 0; right: 0; font-size: 15pt; font-weight: 700; }}
</style></head><body><div class="safe">
  <h1>{E(headline)}</h1>
  <div class="who">{E(c['company'])}</div><div class="phone">{E(c['phone'])}</div>
</div></body></html>"""


def back_html(c, code):
    offer = E(c["offer"]).replace("{code}", f"<b>{E(code)}</b>")
    return f"""<html><head><style>
  @page {{ size: 6.25in 4.25in; margin: 0; }}
  body {{ margin: 0; width: 6.25in; height: 4.25in; background: #fff; color: #0d2635;
         font-family: Helvetica, Arial, sans-serif; }}
  .msg {{ position: absolute; top: .35in; left: .35in; width: 2.75in; bottom: .35in; }}
  h2 {{ margin: 0 0 .1in; font-size: 15pt; }}
  p {{ margin: 0 0 .1in; font-size: 10.5pt; line-height: 1.3; }}
  .fine {{ position: absolute; bottom: 0; font-size: 7pt; color: #555; }}
</style></head><body><div class="msg">
  <h2>{E(c['company'])}</h2>
  <p>{offer}</p>
  <p><b>{E(c['phone'])}</b><br>{E(c.get('website', ''))}</p>
  <p class="fine">Sent to homes with new {E(c.get('reason', 'pool'))} permits in your area. Code {E(code)}.</p>
</div></body></html>"""


def load_log(path):
    if not os.path.exists(path):
        return []
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def post_card(key, c, row, city, state, front, back, code, slug_):
    fields = {
        "to[firstName]": "Current", "to[lastName]": "Resident",
        "to[addressLine1]": row["address"].title(), "to[city]": city, "to[provinceOrState]": state,
        "to[postalOrZip]": row["zip"], "to[countryCode]": "US",
        "frontHTML": front, "backHTML": back, "size": "6x4",
        "description": f"Tipoff {slug_} {row['permit_number']} {code}",
    }
    for k, v in (c.get("from") or {}).items():
        fields[f"from[{k}]"] = v
    if c.get("from"):
        fields.setdefault("from[countryCode]", "US")
    req = urllib.request.Request(API, data=urllib.parse.urlencode(fields).encode(), method="POST",
                                 headers={"x-api-key": key, "Accept": "application/json",
                                          "Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return json.loads(resp.read().decode())


def render_png(html_path, png_path):
    """Optional: a picture of the card for the customer to approve (needs Playwright and Chrome)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return False
    chrome = next((p for p in ("/usr/bin/google-chrome", "/usr/bin/chromium") if os.path.exists(p)), None)
    with sync_playwright() as p:
        b = p.chromium.launch(**({"executable_path": chrome} if chrome else {}), args=["--no-sandbox"])
        pg = b.new_page(viewport={"width": 600, "height": 408}, device_scale_factor=2)
        pg.goto("file://" + os.path.abspath(html_path))
        pg.screenshot(path=png_path)
        b.close()
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--customer", required=True, help="the customer's JSON file (keep it under briefs/)")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--preview", action="store_true", help="write card images and the mailing list; send nothing")
    mode.add_argument("--send", action="store_true", help="create the postcards in PostGrid (POSTGRID_API_KEY)")
    ap.add_argument("--today", help="run as if today were YYYY-MM-DD (for testing)")
    a = ap.parse_args()

    with open(a.customer, encoding="utf-8") as f:
        c = json.load(f)
    for field in ("company", "phone", "offer", "metro", "cats", "zips"):
        if not c.get(field):
            sys.exit(f"{a.customer} is missing {field!r}.")
    if a.send and not c.get("approved"):
        sys.exit("The customer has not approved the card yet. Send them the preview, then set \"approved\": true.")
    key = os.environ.get("POSTGRID_API_KEY", "")
    if a.send and not key:
        sys.exit("Set POSTGRID_API_KEY (a test key first: test_sk_...).")

    name = slug(c["company"])
    work = os.path.join("briefs", "mail", name)
    os.makedirs(work, exist_ok=True)
    log_path = os.path.join(work, "sent.csv")
    log = load_log(log_path)
    today = dt.date.fromisoformat(a.today) if a.today else dt.date.today()
    since = today - dt.timedelta(days=int(c.get("days", 7)) - 1)
    month = today.strftime("%Y-%m")
    allowance = int(c.get("monthly_cards", TERRITORY_CARDS)) - sum(1 for r in log if r["sent_at"].startswith(month))
    done = {(r["address"].upper(), r["zip"]) for r in log}
    stages = [s for s in c.get("stages", ["finished", "issued"]) if s != "finished" or c["metro"] in FINISHED]

    queue = []
    for stage in stages:
        rows, _ = collect(c["metro"], c["cats"], set(c["zips"]), since, today, stage)
        for row in rows:
            k = (row["address"].upper(), row["zip"])
            if row["address"] and k not in done:
                done.add(k)
                queue.append((stage, row))
    held = max(0, len(queue) - max(allowance, 0))
    queue = queue[:max(allowance, 0)]

    state = STATE.get(c["metro"]) or METROS[c["metro"]].get("state", "")
    cat = c["cats"][0]
    plan_path = os.path.join(work, f"{'preview' if a.preview else 'sent'}-{today.isoformat()}.csv")
    with open(plan_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["stage", "permit_number", "address", "city", "zip", "code"])
        for stage, row in queue:
            city = MAIL_CITY.get(c["metro"]) or row["city_or_area"] or c.get("city", "")
            w.writerow([stage, row["permit_number"], row["address"].title(), city, row["zip"],
                        card_code(name, row["address"], row["zip"])])

    if a.preview:
        shown = set()
        for stage, row in queue or [("finished" if "finished" in stages else "issued", {"address": "", "zip": ""})]:
            if stage in shown:
                continue
            shown.add(stage)
            code = card_code(name, row["address"], row["zip"]) if row["address"] else "T00000"
            for side, page in (("front", front_html(c, stage, cat)), ("back", back_html(c, code))):
                p = os.path.join(work, f"card-{stage}-{side}.html")
                with open(p, "w", encoding="utf-8") as f:
                    f.write(page)
                render_png(p, p[:-5] + ".png")
        print(f"{len(queue)} cards would go out ({held} more held for next month's allowance). "
              f"List: {plan_path}. Card designs: {work}/card-*.png")
        return 0

    new_log = not os.path.exists(log_path)
    sent = 0
    with open(log_path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=LOG_FIELDS)
        if new_log:
            w.writeheader()
        for stage, row in queue:
            city = MAIL_CITY.get(c["metro"]) or row["city_or_area"] or c.get("city", "")
            code = card_code(name, row["address"], row["zip"])
            try:
                res = post_card(key, c, row, city, state, front_html(c, stage, cat), back_html(c, code), code, name)
            except urllib.error.HTTPError as err:
                print(f"PostGrid refused the card for {row['address'].title()}: {err.code} "
                      f"{err.read().decode()[:300]}. Stopped; {sent} sent.", file=sys.stderr)
                return 1
            w.writerow({"sent_at": dt.datetime.now().isoformat(timespec="seconds"), "stage": stage,
                        "permit_number": row["permit_number"], "address": row["address"], "zip": row["zip"],
                        "code": code, "postgrid_id": res.get("id", ""), "live": res.get("live", "")})
            sent += 1
    print(f"{sent} postcards created in PostGrid ({held} held for next month's allowance). Log: {log_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
