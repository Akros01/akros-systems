"""Fetch residential permits from six public open-data feeds and sort them
into job types.

By default every record that leaves this module carries only: permit id,
issue date, ZIP (or Chicago community area), a place label, job types and
declared value. That is all the public pages ever see.

Records also carry the builder: the company named on the permit, where the
feed has one. The pages publish a builder only when the name reads as a
business or appears on several permits, so an owner-builder's own name never
shows.

With detail=True (used only by brief.py, for private customer lists and
samples that are never committed or published) each record also carries the
property address, the filed description, the permit type, the contractor named
on the permit and a link to the source record. Owner names, owner phone numbers
and applicant contacts are never requested from any feed.
"""
import datetime as dt
import json
import re
import time
import urllib.parse
import urllib.request

UA = "akros-permit-pages/1.0 (+https://akros01.github.io/akros-systems/permits/)"


def http_json(url, retries=4, timeout=150):
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as err:  # network hiccups, 5xx, throttling
            last = err
            time.sleep(4 * (attempt + 1))
    raise last


def socrata(domain, dataset, where, select, page=50000):
    rows, offset = [], 0
    while True:
        params = {"$where": where, "$select": select, "$limit": page, "$offset": offset, "$order": ":id"}
        batch = http_json(f"https://{domain}/resource/{dataset}.json?" + urllib.parse.urlencode(params))
        rows.extend(batch)
        if len(batch) < page:
            return rows
        offset += page


def zip5(value):
    m = re.search(r"\d{5}", str(value or ""))
    return m.group(0) if m else None


def money(value):
    """Declared job value, or None. Feeds use $0 and $1 as placeholders."""
    try:
        v = float(str(value).replace(",", "").replace("$", ""))
    except (TypeError, ValueError):
        return None
    return v if v >= 100 else None


def iso_date(value):
    return dt.date.fromisoformat(str(value)[:10])


def months_back(today, n):
    """(month, year) pairs for this month and the n-1 before it."""
    out, y, m = [], today.year, today.month
    for _ in range(n):
        out.append((m, y))
        m -= 1
        if m == 0:
            m, y = 12, y - 1
    return out


def place_name(value):
    """'MCKINNEY' -> 'McKinney', 'NORTH NATOMAS' -> 'North Natomas'."""
    text = re.sub(r"\s+", " ", str(value or "")).strip().title()
    return re.sub(r"\bMc([a-z])", lambda m: "Mc" + m.group(1).upper(), text) or None


BUSINESS = re.compile(
    r"\b(LLC|L\.L\.C|INC|CORP|CORPORATION|CO|COMPANY|LTD|LP|PLLC|POOLS?|SPAS?|HOMES?|HOMEBUILDERS?|BUILDERS?|"
    r"BUILDING|CONSTRUCTION|CONTRACTING|CONTRACTORS?|REMODEL\w*|RENOVATIONS?|SOLAR|ENERGY|ELECTRIC\w*|PLUMBING|"
    r"MECHANICAL|AIR|HVAC|HEATING|COOLING|ROOFING|EXTERIORS?|OUTDOOR\w*|LANDSCAP\w*|DESIGNS?|GROUP|SERVICES?|"
    r"ENTERPRISES?|DEVELOPMENT|PROPERTIES|PARTNERS|SYSTEMS|FENCE|FENCING|DECKS?|COMMUNITIES|RESIDENTIAL|"
    r"INDUSTRIES|SOLUTIONS|OASIS|CUSTOM)\b", re.I)
NOT_A_NAME = {"NOT GIVEN", "NONE", "N/A", "NA", "OWNER", "HOMEOWNER", "OWNER BUILDER", "SELF", "UNKNOWN", "TBD"}
UPPER_WORDS = {"Llc": "LLC", "Lp": "LP", "Pllc": "PLLC", "Dfw": "DFW", "Atx": "ATX", "Ii": "II", "Iii": "III",
               "Usa": "USA", "Hvac": "HVAC", "Tx": "TX", "Ca": "CA"}
# Work on a pool that is already there: not a new pool, so kept out of finished-pool counts and lists.
EXISTING_POOL = re.compile(r"existing (swimming )?pool|re-?plaster|resurfac|pool (remodel|renovation|repair)"
                           r"|(remodel|renovat\w*|repair\w*) (of )?(the |an )?(existing )?(swimming )?pool", re.I)


def builder_name(value):
    """The company named on a permit, tidied: 'CODY POOLS, INC. **MAIN' -> 'Cody Pools, Inc.'."""
    text = re.sub(r"\*+\s*main\b\s*\**|\*+|\(\s*main\s*\)", "", str(value or ""), flags=re.I)
    text = re.sub(r"\s*#.*$", "", text)  # Collin CAD appends job codes: 'TROPHY #WIMBLEDON-4095-Q'
    text = re.sub(r"\s+", " ", text).strip(" ,.-/")
    if not text or text.upper() in NOT_A_NAME:
        return None
    name = re.sub(r"\bMc([a-z])", lambda m: "Mc" + m.group(1).upper(), text.title())
    name = re.sub(r"[A-Za-z]+", lambda m: UPPER_WORDS.get(m.group(0), m.group(0)), name)
    return re.sub(r"'S\b", "'s", name)


def record(pid, issued, area, place, cats, value=None, detail=None, *, builder=None):
    rec = {"id": str(pid), "issued": issued.isoformat(), "area": area, "place": place_name(place),
           "cats": cats, "value": value, "builder": builder_name(builder)}
    if detail is not None:
        rec["detail"] = {k: re.sub(r"\s+", " ", str(v)).strip() if v not in (None, "") else ""
                         for k, v in detail.items()}
    return rec


def record_link(domain, dataset, field, value):
    """A link to one permit in the city's feed, keyed on its permit number (stable across re-publishes)."""
    return f"https://{domain}/resource/{dataset}.json?" + urllib.parse.urlencode({field: str(value)})


def link_url(value):
    """Socrata URL columns arrive as {'url': ...}; plain strings pass through."""
    return value.get("url", "") if isinstance(value, dict) else (value or "")


POOL = re.compile(r"\b(pool|spa|swimming)\b", re.I)
SOLAR = re.compile(r"\b(solar|photovoltaic|pv)\b", re.I)
BATTERY = re.compile(r"batter|powerwall|energy storage|\bess\b", re.I)
REROOF = re.compile(r"re-?\s?roof|roof covering|tear[- ]?off|roof replace", re.I)
HVAC = re.compile(r"\b(hvac|a/c|air condition|heat pump|furnace|condenser|mini[- ]split)\b", re.I)
ADU = re.compile(r"accessory dwelling|\bj?adu\b|junior accessory", re.I)


# ---------------------------------------------------------------- Austin
def austin(since, detail=False, finished=False):
    """finished=True: permits whose final inspection passed on or after `since` (any issue date)."""
    when = (f"statusdate >= '{since}T00:00:00' AND status_current = 'Final'" if finished
            else f"issue_date >= '{since}T00:00:00'")
    rows = socrata(
        "data.austintexas.gov", "3syk-w9eu",
        f"{when} AND permit_class_mapped = 'Residential'",
        "permit_number,permittype,work_class,permit_class,description,issue_date,original_zip,original_city,total_job_valuation,"
        "contractor_company_name"
        + (",permit_type_desc,original_address1,link,status_current,statusdate" if detail else ""))
    out = []
    for r in rows:
        pt, wc = r.get("permittype", ""), r.get("work_class", "")
        pc, d = r.get("permit_class", ""), r.get("description", "") or ""
        cat = None
        if pt == "BP":
            if wc == "New" and pc.startswith(("R- 101", "R- 102", "R- 103")):
                cat = "new-homes"
            elif pc.startswith("R- 329") and POOL.search(d):
                cat = "pools"
            elif wc in ("Addition and Remodel", "Remodel"):
                cat = "additions-remodels"
            elif wc in ("Demolition", "Demo") or pc.startswith("R- 64"):
                cat = "demolition"
            elif pc.startswith("R- 330") or pc.startswith("R- 438 Residential Garage"):
                cat = "accessory"
            elif wc == "Repair":
                cat = "repairs"
        elif pt == "MP" and wc == "Change Out":
            cat = "hvac"
        elif pt == "EP" and wc == "Auxiliary Power":
            cat = "solar" if SOLAR.search(d) else ("batteries" if BATTERY.search(d) else None)
        elif pt == "EP" and wc == "Upgrade":
            cat = "electrical-service"
        elif pt == "PP" and wc == "Irrigation":
            cat = "irrigation"
        elif pt == "PP" and wc == "Change Out":
            cat = "water-heaters"
        if not cat or not r.get("issue_date"):
            continue
        place = (r.get("original_city") or "").title() or None
        out.append(record(r["permit_number"], iso_date(r["issue_date"]), zip5(r.get("original_zip")),
                          place, [cat], money(r.get("total_job_valuation")),
                          dict(address=r.get("original_address1"), description=d,
                               permit_type=" / ".join(x for x in (r.get("permit_type_desc") or pt, pc, wc) if x),
                               contractor=r.get("contractor_company_name"),
                               source_link=link_url(r.get("link")),
                               finished_date=(r.get("statusdate") or "")[:10]
                               if r.get("status_current") == "Final" else "") if detail else None,
                          builder=r.get("contractor_company_name")))
    return out


# --------------------------------------------------------- Collin County
COLLIN_TYPES = {
    "New Construction": "new-homes",
    "Pool": "pools",
    "Pool & Spa": "pools",
    "Addition to Existing Structure": "additions-remodels",
    "Remodeling of Existing Structure": "additions-remodels",
    "Solar Energy Device": "solar",
    "Roof/Re-Roof": "roofing",
    "Accessory Building": "accessory",
    "Demolition of Structure": "demolition",
}


def collin(since, detail=False):
    rows = socrata(
        "data.texas.gov", "82ee-gbj5",
        f"permitissueddate >= '{since}T00:00:00' AND proprescom = 'Residential'",
        "permitid,permittypedescr,permitissueddate,permitcomments,situscity,situszip,permitvalue,permitbuildername"
        + (",situsconcatshort" if detail else ""))
    out = []
    for r in rows:
        t, c = r.get("permittypedescr", ""), (r.get("permitcomments") or "").upper()
        cat = COLLIN_TYPES.get(t)
        if t == "Miscellaneous":
            if "FENCE" in c or re.search(r"PATIO|PERGOLA|ARBOR|GAZEBO|CABANA", c):
                cat = "fences-patios"
            elif re.search(r"FOUNDATION|PIER", c):
                cat = "foundation"
        if not cat or not r.get("permitissueddate"):
            continue
        out.append(record(r["permitid"], iso_date(r["permitissueddate"]), zip5(r.get("situszip")),
                          (r.get("situscity") or "").title() or None, [cat], money(r.get("permitvalue")),
                          dict(address=r.get("situsconcatshort"), description=r.get("permitcomments"),
                               permit_type=t, contractor=r.get("permitbuildername"),
                               source_link=record_link("data.texas.gov", "82ee-gbj5", "permitid", r["permitid"]))
                          if detail else None, builder=r.get("permitbuildername")))
    return out


# ---------------------------------------------------------------- Dallas
DALLAS_TYPES = {
    "Residential New Construction Permit": "new-homes",
    "Residential Pool/Spa Permit": "pools",
    "Residential Alteration Addition Permit": "additions-remodels",
    "Residential Solar/PV Permit": "solar",
    "Residential Roofing Permit": "roofing",
    "Residential Mechanical Permit": "hvac",
    "Residential Foundation Repair": "foundation",
    "Residential Accessory Structure Permit": "accessory",
    "Residential Demolition Permit": "demolition",
}


def dallas(since, detail=False):
    today = dt.date.today()
    months = months_back(today, 4)
    likes = " OR ".join(f"issued_date like '{m:02d}/%/{y % 100:02d}'" for m, y in months)
    rows = socrata("www.dallasopendata.com", "e7gq-4sah", f"({likes})",
                   "permit_number,permit_type,issued_date,zip_code,value,contractor"
                   + (",street_address,work_description" if detail else ""))
    out = []
    for r in rows:
        cat = DALLAS_TYPES.get(r.get("permit_type", ""))
        if not cat:
            continue
        try:
            issued = dt.datetime.strptime(r["issued_date"], "%m/%d/%y").date()
        except (KeyError, ValueError):
            continue
        if issued.isoformat() < since:
            continue
        street = re.sub(r",\s*Dallas,\s*TX\s*$", "", r.get("street_address") or "", flags=re.I)
        out.append(record(r["permit_number"], issued, zip5(r.get("zip_code")), None, [cat], money(r.get("value")),
                          dict(address=street, description=r.get("work_description"),
                               permit_type=r.get("permit_type"), contractor=r.get("contractor"),
                               source_link=record_link("www.dallasopendata.com", "e7gq-4sah", "permit_number", r["permit_number"]))
                          if detail else None, builder=r.get("contractor")))
    return out


# ----------------------------------------------------------- Los Angeles
LA_SUPPLEMENT = re.compile(r"SUPPL|^\s*REVIS|TO REVISE|CHANGE (OF )?CONTRACTOR|OWNER[- ]BUILDER|\bREVISION\b", re.I)
LA_WINDOWS = re.compile(r"(WINDOW|DOOR)S?\b[^.]{0,60}(CHANGE[- ]?OUT|REPLACE)|(CHANGE[- ]?OUT|REPLAC\w*)[^.]{0,60}\b(WINDOW|DOOR)", re.I)
LA_SEISMIC = re.compile(r"SEISMIC|RETROFIT|SOFT[- ]STORY|FOUNDATION BOLT", re.I)
LA_REMODEL = re.compile(r"REMODEL|KITCHEN|BATH|ALTERATION|INTERIOR|RENOVAT|ADDITION|CONVERT|NEW (BED)?ROOM", re.I)
LA_WILDFIRE = re.compile(r"WILDFIRE|FIRE REBUILD|REBUILD[^.]{0,40}FIRE", re.I)


def los_angeles(since, detail=False, finished=False):
    """finished=True: permits finaled on or after `since` (any issue date)."""
    when = (f"status_date >= '{since}T00:00:00' AND status_desc = 'Permit Finaled'" if finished
            else f"issue_date >= '{since}T00:00:00'")
    rows = socrata(
        "data.lacity.org", "pi9x-tg5x",
        f"{when} AND permit_sub_type = '1 or 2 Family Dwelling'",
        "permit_nbr,zip_code,cpa,permit_type,use_desc,work_desc,issue_date,valuation,status_desc"
        + (",primary_address,status_date" if detail else ""))
    out = []
    for r in rows:
        wd, pt, use = r.get("work_desc", "") or "", r.get("permit_type", ""), r.get("use_desc", "")
        if LA_SUPPLEMENT.search(wd) or r.get("status_desc") in ("Refund in Progress", "Intent to Revoke"):
            continue
        cats = []
        if pt == "Swimming-Pool/Spa":
            cats = ["pools"]
        elif use == "Accessory Dwelling Unit" or (ADU.search(wd) and pt.startswith("Bldg-")):
            cats = ["adus"]
        elif pt == "Bldg-New" and use in ("Dwelling - Single Family", "Duplex"):
            cats = ["new-homes"] + (["wildfire-rebuilds"] if LA_WILDFIRE.search(wd) else [])
        elif pt == "Bldg-Demolition":
            cats = ["demolition"]
        elif pt == "Bldg-Addition":
            cats = ["additions-remodels"]
        elif pt == "Bldg-Alter/Repair":
            if REROOF.search(wd):
                cats = ["roofing"]
            elif LA_WINDOWS.search(wd):
                cats = ["windows-doors"]
            elif LA_SEISMIC.search(wd):
                cats = ["seismic"]
            elif LA_REMODEL.search(wd):
                cats = ["additions-remodels"]
        elif pt == "Nonbldg-New" and use in ("Fence Wall", "Patio Cover", "Retaining Wall"):
            cats = ["fences-patios"]
        if not cats or not r.get("issue_date"):
            continue
        out.append(record(r["permit_nbr"], iso_date(r["issue_date"]), zip5(r.get("zip_code")),
                          r.get("cpa") or None, cats, money(r.get("valuation")),
                          dict(address=r.get("primary_address"), description=wd,
                               permit_type=" / ".join(x for x in (pt, use) if x), contractor="",
                               source_link=record_link("data.lacity.org", "pi9x-tg5x", "permit_nbr", r["permit_nbr"]),
                               finished_date=(r.get("status_date") or "")[:10]
                               if r.get("status_desc") == "Permit Finaled" else "")
                          if detail else None))
    return out


# --------------------------------------------------------------- Chicago
CHI_WORK = {
    "Small-Scale Solar PV System": "solar",
    "Reroofing": "roofing",
    "Porch,Deck,Balcony,or Fire Escape": "porches-decks",
    "Detached Frame Garage": "garages",
    "Fence or Trash Enclosure": "fences-patios",
    "Exterior Windows/Doors Replacement": "windows-doors",
}
CHI_RES = re.compile(r"SINGLE[- ]FAMILY|\bS\.?F\.?R\b|RESIDEN|DWELLING|\bD\.?\s?U\.?\b|\bFLAT\b|BUNGALOW|TOWN ?HO(USE|ME)|GREYSTONE|COACH HOUSE", re.I)
CHI_COMM = re.compile(r"OFFICE|RESTAURANT|RETAIL|STORE|COMMERCIAL|HOTEL|SCHOOL|CHURCH|WAREHOUSE|TENANT|SUITE|MERCANTILE|\bBANK\b|CLINIC|HOSPITAL|PARKING|INDUSTRIAL|THEATER|\bBAR\b|\bGYM\b|SALON|DAY ?CARE|FACTORY|MIXED[- ]USE", re.I)
CHI_BIG = re.compile(r"\b(\d{2,}|[4-9])\s*(TOTAL\s+)?(RESIDENTIAL\s+)?(DWELLING\s+)?(UNITS?|D\.?\s?U\.?)\b", re.I)
CHI_SMALL = re.compile(r"SINGLE[- ]FAMILY|\bS\.?F\.?R\b|\b(1|2|3|ONE|TWO|THREE)[- ,]*(DWELLING|D\.?\s?U\.?|UNIT)|\b(2|3|TWO|THREE)[- ]FLAT", re.I)


def chicago_areas():
    rows = http_json("https://data.cityofchicago.org/resource/igwz-8jzy.json?$select=area_numbe,community&$limit=200")
    return {str(int(float(r["area_numbe"]))): r["community"].title() for r in rows}


CHI_CONTACTS = ",".join(f"contact_{n}_type,contact_{n}_name" for n in range(1, 6))


def chicago_contractor(r):
    """First contact the feed labels as a contractor; owners are skipped."""
    for n in range(1, 6):
        if "CONTRACTOR" in (r.get(f"contact_{n}_type") or "").upper():
            return r.get(f"contact_{n}_name") or ""
    return ""


def chicago(since, detail=False):
    names = chicago_areas()
    rows = socrata(
        "data.cityofchicago.org", "ydr8-5enu", f"issue_date >= '{since}T00:00:00'",
        "id,permit_type,work_type,work_description,issue_date,community_area,reported_cost"
        + (",permit_,street_number,street_direction,street_name," + CHI_CONTACTS if detail else ""))
    out = []
    for r in rows:
        pt, wt, d = r.get("permit_type", ""), r.get("work_type", ""), r.get("work_description", "") or ""
        cat = CHI_WORK.get(wt)
        if not cat:
            if pt == "PERMIT - NEW CONSTRUCTION" and CHI_SMALL.search(d) and not CHI_BIG.search(d) \
                    and not CHI_COMM.search(d) and "FOUNDATION ONLY" not in d.upper():
                cat = "new-homes"
            elif pt == "PERMIT - RENOVATION/ALTERATION" and CHI_RES.search(d) and not CHI_COMM.search(d):
                cat = "additions-remodels"
            elif pt == "PERMIT - WRECKING/DEMOLITION" and CHI_RES.search(d) and not CHI_COMM.search(d):
                cat = "demolition"
        if not cat or not r.get("issue_date"):
            continue
        ca = r.get("community_area")
        area = str(int(float(ca))) if ca else None
        out.append(record(r["id"], iso_date(r["issue_date"]), area, names.get(area) if area else None,
                          [cat], money(r.get("reported_cost")),
                          dict(permit_number=r.get("permit_"),
                               address=" ".join(x for x in (r.get("street_number"), r.get("street_direction"),
                                                            r.get("street_name")) if x),
                               description=d, permit_type=" / ".join(x for x in (pt, wt) if x),
                               contractor=chicago_contractor(r),
                               source_link=f"https://data.cityofchicago.org/resource/ydr8-5enu.json?id={r['id']}")
                          if detail else None))
    return out


# ------------------------------------------------------------ Sacramento
SAC_URL = ("https://services5.arcgis.com/54falWtcpty3V47Z/ArcGIS/rest/services/"
           "BldgPermitIssued_CurrentYear/FeatureServer/0/query")
SAC_HOMES = ("Single Family", "Duplex", "Half Plex")


def sacramento(since, detail=False):
    today = dt.date.today()
    likes = " OR ".join(f"Status_Date LIKE '{m:02d}/%/{y}'" for m, y in months_back(today, 4))
    fields = "OBJECTID,Application,Type,Sub_Type,Category,Status_Date,Current_Status,ZIP,Comm_Plan_Area,Activity_Code,Work_Desc,Valuation"
    fields += ",Contractor"
    if detail:
        fields += ",Address"
    rows, offset = [], 0
    while True:
        params = {"where": f"Type = 'Residential' AND ({likes})", "outFields": fields, "f": "json",
                  "orderByFields": "OBJECTID", "resultOffset": offset, "resultRecordCount": 2000}
        page = http_json(SAC_URL + "?" + urllib.parse.urlencode(params))
        feats = [f["attributes"] for f in page.get("features", [])]
        rows.extend(feats)
        offset += len(feats)
        if len(feats) < 2000 or not page.get("exceededTransferLimit", len(feats) == 2000):
            break
    out = []
    for r in rows:
        if r.get("Current_Status") in ("Withdrawn", "Void"):
            continue
        st, ac, cat_ = r.get("Sub_Type") or "", r.get("Activity_Code") or "", r.get("Category") or ""
        wd = r.get("Work_Desc") or ""
        cat = None
        if st == "Pool" or ac.startswith("J1"):
            cat = "pools"
        elif st in ("New Building", "Production Permit") and cat_ in SAC_HOMES:
            cat = "new-homes"
        elif ac.startswith("I3") or ADU.search(wd):
            cat = "adus"
        elif st in ("Addition", "Remodel") or ac.startswith(("A1", "I1")):
            cat = "additions-remodels"
        elif st in ("Demolition", "Housing-Demo") or ac.startswith("W1"):
            cat = "demolition"
        elif ac.startswith("M1") or HVAC.search(wd):
            cat = "hvac"
        elif SOLAR.search(wd):
            cat = "solar"
        elif REROOF.search(wd):
            cat = "roofing"
        elif ac.startswith(("D3", "D1")):
            cat = "fences-patios"
        if not cat:
            continue
        try:
            issued = dt.datetime.strptime(r["Status_Date"], "%m/%d/%Y").date()
        except (KeyError, TypeError, ValueError):
            continue
        if issued.isoformat() < since:
            continue
        place = (r.get("Comm_Plan_Area") or "").strip().title() or None
        out.append(record(r.get("Application") or r["OBJECTID"], issued, zip5(r.get("ZIP")), place, [cat],
                          money(r.get("Valuation")),
                          dict(address=r.get("Address"), description=wd,
                               permit_type=" / ".join(x for x in (st, cat_) if x), contractor=r.get("Contractor"),
                               source_link="") if detail else None, builder=r.get("Contractor")))
    return out


# Feeds that say when work passed its final inspection (brief.py --stage finished).
FINISHED = {"austin", "los-angeles"}

FETCHERS = {
    "austin": austin,
    "collin-county": collin,
    "dallas": dallas,
    "los-angeles": los_angeles,
    "chicago": chicago,
    "sacramento": sacramento,
}
