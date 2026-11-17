# Akros Systems

Akros Systems makes [Tipoff](https://tipoff-brief.github.io/), a weekly brief of new residential building permits for home-service contractors, and the [Permit Almanac](https://akros01.github.io/permit-sample/), one-time residential permit reports for six US metros.

## Residential permit activity, updated weekly

Counts of residential building permits by job type and ZIP code, read from each city's open-data feed and rebuilt every Monday:

- [All six metros](https://akros01.github.io/akros-systems/permits/)
- [Austin, TX](https://akros01.github.io/akros-systems/permits/austin/): [new homes](https://akros01.github.io/akros-systems/permits/austin/new-homes/), [pools](https://akros01.github.io/akros-systems/permits/austin/pools/), [additions and remodels](https://akros01.github.io/akros-systems/permits/austin/additions-remodels/)
- [Collin County, TX](https://akros01.github.io/akros-systems/permits/collin-county/): [new homes](https://akros01.github.io/akros-systems/permits/collin-county/new-homes/), [pools](https://akros01.github.io/akros-systems/permits/collin-county/pools/)
- [Dallas, TX](https://akros01.github.io/akros-systems/permits/dallas/): [new homes](https://akros01.github.io/akros-systems/permits/dallas/new-homes/), [pools](https://akros01.github.io/akros-systems/permits/dallas/pools/), [additions and remodels](https://akros01.github.io/akros-systems/permits/dallas/additions-remodels/)
- [Los Angeles, CA](https://akros01.github.io/akros-systems/permits/los-angeles/): [ADUs](https://akros01.github.io/akros-systems/permits/los-angeles/adus/), [pools](https://akros01.github.io/akros-systems/permits/los-angeles/pools/), [new homes](https://akros01.github.io/akros-systems/permits/los-angeles/new-homes/), [wildfire rebuilds](https://akros01.github.io/akros-systems/permits/los-angeles/wildfire-rebuilds/)
- [Sacramento, CA](https://akros01.github.io/akros-systems/permits/sacramento/)
- [Chicago, IL](https://akros01.github.io/akros-systems/permits/chicago/)
- [Sources and method](https://akros01.github.io/akros-systems/permits/about/)

The pages show counts and the builders named on the most permits (companies only): no owner names, phone numbers or street addresses.

## How it runs

- `tools/permits/build.py` downloads recent residential permits from each feed, sorts them into job types, and writes `permits/` and `sitemap.xml`. A metro whose feed fails keeps last week's numbers.
- `.github/workflows/refresh-permit-pages.yml` runs the build every Monday (and right after the page code changes), commits any changes, asks GitHub Pages to publish them and notifies IndexNow (Bing and others) with `tools/permits/indexnow.py`. Start it by hand from the **Actions** tab with **Run workflow**.
- To turn the weekly refresh off, disable that workflow in the Actions tab.

Run it locally with Python 3.10 or newer, no packages needed:

```
python3 tools/permits/build.py
```

## Customer lists and free samples

`tools/permits/brief.py` uses the same feeds and job types to write one customer's list: every matching permit with the address, filed scope, permit type and contractor (owner names are never collected). It writes a spreadsheet and a short text summary to `briefs/`, which git ignores. These lists are private: send each one only to the customer it was made for, and never commit or publish them.

```
# Free sample: every pool permit in Collin County over four weeks
python3 tools/permits/brief.py --metro collin-county --cats pools --since 2026-10-13 --until 2026-11-09

# A customer's Monday list: pools and new homes in three Dallas ZIPs, last 7 days
python3 tools/permits/brief.py --metro dallas --cats pools,new-homes --zips 75214,75218,75230 --days 7 --name "Customer Name"

# Job types each metro supports
python3 tools/permits/brief.py --list

# Pools that just passed final inspection (Austin and Los Angeles report it)
python3 tools/permits/brief.py --metro austin --cats pools --stage finished --days 7
```

## Territory postcards

Territory customers ($1,000 a month) get a postcard with their name and offer mailed to every new matching homeowner in their ZIP group, up to 300 a month. `tools/permits/postcards.py` does it through [PostGrid](https://www.postgrid.com/):

1. Copy `tools/permits/postcard-customer.example.json` to `briefs/customers/<name>.json` and fill it in (company, phone, offer, ZIPs, return address).
2. `python3 tools/permits/postcards.py --customer briefs/customers/<name>.json --preview` writes the card images and the list of who would get one. Send the images to the customer.
3. Once they approve, set `"approved": true` and run it with `--send` and `POSTGRID_API_KEY` set. A PostGrid test key creates the orders without printing; a live key mails and charges.

Cards go to "Current Resident"; owner names are never used. Each run sends finished-work cards first, skips any address that customer has already mailed, and stops at the monthly allowance. Customer files and send logs hold addresses, so they stay in `briefs/` and are never committed.
