"""Permit feeds beyond the six hand-built metros: one generic reader, configured per feed in feeds.json.

Each feed entry names the open-data dataset and which columns hold the issue date, permit number,
address, ZIP, type and description (plus value, contractor and status when the feed has them).
Job types come from the permit's type and description text with the patterns below, so a new city
needs only a feeds.json entry that `discover.py` proposes and a person checks.
"""
import datetime as dt
import html
import json
import os
import re

from sources import money, record, record_link, socrata, zip5

HERE = os.path.dirname(os.path.abspath(__file__))

# First match wins, so the specific job types come before the broad ones.
JOB_PATTERNS = [
    ("pools", r"swimming pool|\bpool\b(?! table)|\bspa\b|hot tub|plunge pool"),
    ("solar", r"\bsolar\b|photovoltaic|\bp\.?v\.? (system|array|panels?|modules?)|\bpv\b"),
    ("batteries", r"\bbatter(y|ies)\b|powerwall|energy storage|\bess\b"),
    ("ev-chargers", r"\bev\b|electric vehicle|evse|car charger|vehicle charg"),
    ("roofing", r"re-?\s?roof|roof (replacement|covering|repair)|roofing|shingle|tear[- ]?off"),
    ("siding", r"\bsiding\b"),
    ("windows-doors", r"\bwindows?\b|\bdoors? (replace|change)|sliding (glass )?door|patio door"),
    ("hvac", r"\bhvac\b|furnace|air[- ]condition|\ba/?c\b|heat pump|mini[- ]?split|condens(er|ing unit)|ductless"),
    ("water-heaters", r"water heater|tankless"),
    ("electrical-service", r"service (upgrade|change|replacement)|panel (upgrade|change|replace)|meter (base|upgrade)|\b(100|150|200|400)\s?a(mp)?\b"),
    ("adus", r"accessory dwelling|\bj?adu\b|\bdadu\b|granny|backyard cottage|garage conversion|secondary suite"),
    ("new-homes", r"new (one|two|1|2|single)[- ]?family|new (single[- ]?family|sfr|sfd|residence|dwelling|home|house|duplex|townhouse)"
                  r"|(construct|erect|build)\w* (a |an )?(new )?(one|two|single|1|2)[- ]family (dwelling|residence|home|house)"
                  r"|(single[- ]?family|sfr|sfd|townhouse|duplex) (dwelling|residence|home)?\s*[-:,]?\s*new\b"
                  r"|\bnew (sfr|sfd)\b|new residential construction"),
    ("demolition", r"demoli|\bwreck|\braze\b|tear down"),
    ("foundation", r"foundation (repair|stabiliz)|underpin|\bpiers?\b"),
    ("fences-patios", r"\bfence|\bpatio\b|pergola|\bdeck\b|gazebo|cabana|retaining wall|carport"),
    ("insulation", r"insulat|weatheriz"),
    ("additions-remodels", r"addition|remodel|renovat|alteration|kitchen|bath(room)?|interior|basement finish|finish basement"),
]
JOBS = [(name, re.compile(rx, re.I)) for name, rx in JOB_PATTERNS]
# A free-text description often lists several jobs ("addition, new siding and roof"): read it for the
# biggest one first. A permit-type column names one job, so it is read in the order above.
DESC_ORDER = ["pools", "adus", "new-homes", "solar", "batteries", "ev-chargers", "additions-remodels", "demolition",
              "roofing", "siding", "windows-doors", "hvac", "water-heaters", "electrical-service", "foundation",
              "fences-patios", "insulation"]
DESC_JOBS = sorted(JOBS, key=lambda j: DESC_ORDER.index(j[0]))
TRAILING_CITY = re.compile(r"^(.*?),\s*[^,]+,\s*[A-Z]{2}\s+\d{5}(-\d{4})?\s*$")
CITY_IN_ADDRESS = re.compile(r",\s*([A-Za-z .'-]+?),\s*[A-Z]{2}\s+\d{5}")
RESIDENTIAL = re.compile(r"resid|single[- ]?family|\bsfr\b|\bsfd\b|1[- ]?(or|&|and)?[- ]?2[- ]family|one[- ]family|two[- ]family|"
                         r"dwelling|duplex|townhouse|r-3|\br3\b", re.I)
NOT_HOMES = re.compile(r"non[- ]?resid|multi[- ]?family|apartment|condo(minium)? (building|complex)|mixed[- ]use|"
                       r"\b([3-9]|\d{2,})[- ]?(story|unit|units|family)\b", re.I)
COMMERCIAL = re.compile(r"commercial|multi[- ]?family|apartment|office|retail|industrial|hotel|restaurant|warehouse|"
                        r"tenant improvement|\bti\b|school|church|hospital", re.I)


def street_only(address, feed):
    """'50 MOUNTAIN LN, MILL VALLEY, CA 94941' -> '50 MOUNTAIN LN', so a postcard gets the street line alone."""
    address = re.sub(r"\s+", " ", address or "").strip()
    m = TRAILING_CITY.match(address)
    if m:
        return m.group(1)
    if feed.get("address_suffix"):
        return re.sub(feed["address_suffix"], "", address, flags=re.I).strip()
    return address


def clean_text(value, feed):
    text = html.unescape(str(value or "")).replace("\xa0", " ")
    if feed.get("desc_strip"):
        text = re.sub(feed["desc_strip"], "", text, flags=re.I)
    return re.sub(r"\s+", " ", text).strip()


def load_feeds(path=os.path.join(HERE, "feeds.json")):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def classify(text, jobs=JOBS):
    for name, rx in jobs:
        if rx.search(text):
            return name
    return None


def job_type(row, feed):
    types, desc = text_of(row, feed.get("type", [])), str(row.get(feed["desc"]) or "")
    if feed.get("classify") == "desc_first":
        return classify(desc, DESC_JOBS) or classify(types)
    return classify(types) or classify(desc, DESC_JOBS)


def text_of(row, cols):
    return " | ".join(str(row.get(c) or "") for c in cols)


def is_residential(row, feed):
    """Feeds without a residential filter in their query are sorted by the words in their type columns."""
    t = text_of(row, feed.get("type", []) + feed.get("class", []))
    d = str(row.get(feed.get("desc", ""), "") or "")
    if NOT_HOMES.search(t) or NOT_HOMES.search(d):
        return False
    if feed.get("all_residential"):
        return True
    if feed.get("residential_default"):
        return not (COMMERCIAL.search(t) or COMMERCIAL.search(d))
    if RESIDENTIAL.search(t):
        return True
    if COMMERCIAL.search(t):
        return False
    return bool(RESIDENTIAL.search(d))


def fetcher(feed):
    """A function with the same contract as the hand-built fetchers in sources.py."""
    def fetch(since, detail=False, finished=False):
        if finished:
            raise ValueError(f"{feed['slug']} has no finished-work data")
        cols = [feed["date"], feed["id"], feed.get("zip")] + feed.get("type", []) + feed.get("class", []) + [feed["desc"]]
        for key in ("value", "contractor", "place"):
            if feed.get(key):
                cols.append(feed[key])
        address_cols = feed["address"] if isinstance(feed["address"], list) else [feed["address"]]
        if detail or feed.get("zip_from_address") or feed.get("place_from_address"):
            cols += address_cols
        if detail and feed.get("status"):
            cols.append(feed["status"])
        cols = list(dict.fromkeys(c for c in cols if c))
        where = f"{feed['date']} >= '{since}T00:00:00'"
        if feed.get("where"):
            where += f" AND ({feed['where']})"
        rows = socrata(feed["domain"], feed["dataset"], where, ",".join(cols))
        out = []
        for r in rows:
            if not r.get(feed["date"]) or not is_residential(r, feed):
                continue
            cat = job_type(r, feed)
            if not cat:
                continue
            try:
                issued = dt.date.fromisoformat(str(r[feed["date"]])[:10])
            except ValueError:
                continue
            addr_text = " ".join(str(r.get(c) or "") for c in address_cols)
            zip_code = zip5(addr_text if feed.get("zip_from_address") else r.get(feed["zip"]))
            place = r.get(feed["place"]) if feed.get("place") else feed.get("default_place")
            if feed.get("place_from_address"):
                m = CITY_IN_ADDRESS.search(addr_text)
                place = m.group(1) if m else place
            out.append(record(
                r.get(feed["id"]) or f"{feed['slug']}-{len(out)}", issued, zip_code, place, [cat],
                money(r.get(feed["value"])) if feed.get("value") else None,
                dict(address=street_only(" ".join(str(r.get(c) or "").strip() for c in address_cols), feed),
                     description=clean_text(r.get(feed["desc"]), feed),
                     permit_type=text_of(r, feed.get("type", [])).strip(" |"),
                     contractor=r.get(feed["contractor"]) if feed.get("contractor") else "",
                     source_link=record_link(feed["domain"], feed["dataset"], feed["id"], r.get(feed["id"], "")),
                     finished_date="") if detail else None,
                builder=r.get(feed["contractor"]) if feed.get("contractor") else None))
        return out
    return fetch
