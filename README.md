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

The pages show counts only: no owner names, phone numbers or street addresses.

## How it runs

- `tools/permits/build.py` downloads recent residential permits from each feed, sorts them into job types, and writes `permits/` and `sitemap.xml`. A metro whose feed fails keeps last week's numbers.
- `.github/workflows/refresh-permit-pages.yml` runs the build every Monday, commits any changes and notifies IndexNow (Bing and others) with `tools/permits/indexnow.py`. Start it by hand from the **Actions** tab with **Run workflow**.
- To turn the weekly refresh off, disable that workflow in the Actions tab.

Run it locally with Python 3.10 or newer, no packages needed:

```
python3 tools/permits/build.py
```
