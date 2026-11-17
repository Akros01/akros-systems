"""Propose a feeds.json entry for a Socrata permit dataset, and show what it would produce.

    python3 tools/permits/discover.py cos-data.seattle.gov 76t5-zqzr seattle "Seattle, WA"

Prints the column mapping it picked, job-type counts for the last 28 days, the share it read as
residential, and sample rows per job type. A person checks the samples before the entry goes in
feeds.json; nothing is added automatically.
"""
import collections
import datetime as dt
import json
import re
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from registry import classify, fetcher, is_residential, text_of  # noqa: E402
from sources import http_json, socrata  # noqa: E402

PICK = {
    "date": [r"^issue_?date$", r"^issued_?date$", r"^issueddate$", r"^issuedate$", r"date_?issued", r"permit_?issued_?date",
             r"issuance_?date", r"^issued$", r"issue_?dt", r"issued_?on", r"final_?issue"],
    "id": [r"^permit_?num(ber)?$", r"^permitnum$", r"^permit_?no$", r"^permit_?id$", r"^permit$", r"^permit_$",
           r"record_?(id|number)", r"^job_?(number|filing_number)$", r"^application_?(number|no)$", r"case_?number", r"^id$"],
    "address": [r"original_?address1?$", r"^address$", r"street_?address", r"site_?address", r"location_?address",
                r"full_?address", r"property_?address", r"^address_?full", r"house_?no", r"address"],
    "zip": [r"original_?zip", r"^zip_?code$", r"^zipcode$", r"^zip$", r"postal", r"zip"],
    "desc": [r"^description$", r"work_?description", r"job_?description", r"project_?description", r"scope",
             r"permit_?description", r"description", r"work_?desc", r"comments?"],
    "value": [r"valuation", r"est(imated)?_?(project_?)?cost", r"job_?value", r"project_?value", r"declared", r"value", r"cost"],
    "contractor": [r"contractor_?company", r"contractor_?(business_?)?name", r"^contractor$", r"contractor", r"applicant_?business"],
    "status": [r"status_?current", r"current_?status", r"permit_?status", r"^status$"],
    "place": [r"original_?city", r"^city$", r"municipality", r"jurisdiction", r"community", r"neighborhood", r"town"],
}
TYPE_COLS = r"permit_?type|permittype|type_?desc|work_?type|worktype|permit_?class|class_?mapped|category|sub_?type|subtype|job_?type|use_?type|occupancy|work_?class|permit_?kind|record_?type|type"


def pick(cols, patterns):
    for p in patterns:
        for c in cols:
            if re.search(p, c, re.I):
                return c
    return None


def propose(domain, dataset, slug, name):
    meta = http_json(f"https://{domain}/api/views/{dataset}.json")
    cols = [c["fieldName"] for c in meta.get("columns", []) if not c["fieldName"].startswith(":@")]
    kinds = {c["fieldName"]: c.get("dataTypeName", "") for c in meta.get("columns", [])}
    date_cols = [c for c in cols if kinds.get(c) == "calendar_date"]
    feed = {"slug": slug, "name": name, "short": name.split(",")[0], "domain": domain, "dataset": dataset}
    feed["date"] = pick(date_cols, PICK["date"]) or pick(cols, PICK["date"])
    site = [c for c in cols if not re.search(r"owner|applicant|contractor|mail|billing|agent|engineer|architect", c, re.I)]
    for key in ("id", "address", "zip", "desc", "value", "contractor", "status", "place"):
        cands = site if key in ("address", "zip", "place") else cols
        if key == "value":
            cands = [c for c in cols if kinds.get(c) in ("number", "money", "text")]
        feed[key] = pick(cands, PICK[key])
    if not feed["address"] or re.search(r"house_?no|street_?name", " ".join(site)):
        parts = [pick(site, [r"house_?(no|num)", r"street_?(no|num)", r"^stno$"]), pick(site, [r"street_?name", r"^street$", r"stname"])]
        if all(parts):
            feed["address"] = parts
    feed["type"] = [c for c in cols if re.search(TYPE_COLS, c, re.I) and c not in (feed["desc"],)][:4]
    return feed, cols


def main():
    domain, dataset, slug, name = sys.argv[1:5]
    feed, cols = propose(domain, dataset, slug, name)
    print("proposed:", json.dumps(feed))
    if not all(feed.get(k) for k in ("date", "id", "zip", "desc")):
        print("Missing a required column; fill it in by hand.")
        return 1
    since = (dt.date.today() - dt.timedelta(days=27)).isoformat()
    raw = socrata(domain, dataset, f"{feed['date']} >= '{since}T00:00:00'",
                  ",".join(dict.fromkeys(c for c in [feed["date"], feed["id"], feed["zip"], feed["desc"]] + feed["type"] if c)))
    res = [r for r in raw if is_residential(r, feed)]
    print(f"last 28 days: {len(raw)} rows, {len(res)} read as residential")
    recs = fetcher(feed)(since, detail=True)
    by = collections.Counter(r["cats"][0] for r in recs)
    print("job types:", dict(by.most_common()))
    shown = collections.Counter()
    for r in recs:
        c = r["cats"][0]
        if shown[c] < 2:
            shown[c] += 1
            d = r["detail"]
            print(f"  {c:20s} {r['issued']} {r['area']} | {d['permit_type'][:40]} | {d['description'][:90]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
