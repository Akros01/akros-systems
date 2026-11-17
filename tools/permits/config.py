"""Metros, job types and links used by the permit pages."""

SITE = "https://akros01.github.io/akros-systems"
BASE_PATH = "/akros-systems"

TIPOFF_HOME = "https://tipoff-brief.github.io/"
TIPOFF_PLANS = "https://tipoff-brief.github.io/#plans"
CONTACT_EMAIL = "abdul321@gmail.com"
ALMANAC_HOME = "https://akros01.github.io/permit-sample/"
ALMANAC_SAMPLE = "https://akros01.github.io/permit-sample/sample.html"

METROS = {
    "austin": {
        "name": "Austin, TX", "short": "Austin", "area": "ZIP",
        "source": "City of Austin open data: Issued Construction Permits",
        "source_url": "https://data.austintexas.gov/d/3syk-w9eu",
        "almanac": "https://abdulicious38.gumroad.com/l/pqyewv",
        "tipoff": True,
        "scope": "City of Austin permits, including its extraterritorial jurisdiction, classed as residential.",
    },
    "collin-county": {
        "name": "Collin County, TX", "short": "Collin County", "area": "ZIP",
        "source": "Collin Central Appraisal District: Building Permits (data.texas.gov)",
        "source_url": "https://data.texas.gov/d/82ee-gbj5",
        "almanac": "https://abdulicious38.gumroad.com/l/maztsr",
        "tipoff": True,
        "scope": "Residential permits that Frisco, Allen, McKinney, Wylie, Prosper, Celina and the other Collin County cities report to the appraisal district.",
        "lag": "Cities report permits to the appraisal district in monthly batches, so the latest weeks fill in late and the counts here run low until they do. For that reason we don't compare them with the weeks before.",
        "no_change": True,
    },
    "dallas": {
        "name": "Dallas, TX", "short": "Dallas", "area": "ZIP",
        "source": "City of Dallas open data: Building Permits",
        "source_url": "https://www.dallasopendata.com/d/e7gq-4sah",
        "almanac": "https://abdulicious38.gumroad.com/l/csceeu",
        "tipoff": True,
        "scope": "City of Dallas residential permits.",
    },
    "los-angeles": {
        "name": "Los Angeles, CA", "short": "Los Angeles", "area": "ZIP",
        "source": "City of Los Angeles open data: Building Permits Issued from 2020 to Present",
        "source_url": "https://data.lacity.org/d/pi9x-tg5x",
        "almanac": "https://abdulicious38.gumroad.com/l/vxcli",
        "tipoff": True,
        "scope": "City of Los Angeles building permits for one- and two-family dwellings. Other cities in LA County are not included. Supplemental and revision permits are left out.",
    },
    "sacramento": {
        "name": "Sacramento, CA", "short": "Sacramento", "area": "ZIP",
        "source": "City of Sacramento open data: Building Permits Issued (current year)",
        "source_url": "https://data.cityofsacramento.org/",
        "almanac": "https://abdulicious38.gumroad.com/l/mpquikg",
        "tipoff": True,
        "scope": "City of Sacramento residential permits. Unincorporated Sacramento County is not included.",
        "lag": "The city publishes this feed with a delay of a few weeks.",
    },
    "chicago": {
        "name": "Chicago, IL", "short": "Chicago", "area": "Community area",
        "source": "City of Chicago open data: Building Permits",
        "source_url": "https://data.cityofchicago.org/d/ydr8-5enu",
        "almanac": "https://abdulicious38.gumroad.com/l/wnhxy",
        "tipoff": False,
        "scope": "City of Chicago permits whose descriptions identify residential work. Chicago records have no ZIP code, so areas are the city's 77 community areas.",
    },
}

# Job types with their own page come first, in this order.
CATS = {
    "new-homes": {
        "label": "New homes", "title": "New home permits",
        "noun": "new single-family and two-family home permits", "short": "new-home permits",
        "trades": ["Security", "Solar", "Landscaping", "Fencing", "Window coverings"],
        "why": "A new home is a house that will need security, landscaping, fencing and window coverings, and its owner is choosing them now.",
    },
    "pools": {
        "label": "Pools and spas", "title": "New pool permits",
        "noun": "residential pool and spa permits", "short": "pool and spa permits",
        "trades": ["Pool service", "Fencing", "Landscaping"],
        "why": "A new pool needs regular service once it is filled, and local codes require barriers or other safety features around residential pools.",
    },
    "additions-remodels": {
        "label": "Additions and remodels", "title": "Addition and remodel permits",
        "noun": "residential addition and remodel permits", "short": "addition and remodel permits",
        "trades": ["HVAC", "Electrical", "Insulation", "Window coverings"],
        "why": "Added or rebuilt rooms need heating and cooling, wiring, insulation and window coverings.",
    },
    "adus": {
        "label": "ADUs and garage conversions", "title": "ADU permits",
        "noun": "accessory dwelling unit (ADU) and garage-conversion permits", "short": "ADU permits",
        "trades": ["HVAC", "Solar", "Electrical", "Window coverings", "Landscaping"],
        "why": "Each ADU is a separate small home that needs its own heating and cooling, power and finishes.",
    },
    "wildfire-rebuilds": {
        "label": "Wildfire rebuilds", "title": "Wildfire rebuild permits",
        "noun": "new-home permits that the city records as 2025 wildfire rebuilds", "short": "wildfire rebuild permits",
        "trades": ["Security", "Solar", "Landscaping", "Fencing", "Window coverings"],
        "why": "Each rebuild is a whole new house going up on a cleared lot, so its owner needs every system and finish again.",
        "parent": "new-homes",
    },
    # Counted on metro pages only.
    "hvac": {"label": "HVAC"},
    "solar": {"label": "Solar"},
    "batteries": {"label": "Home batteries"},
    "roofing": {"label": "Re-roofs"},
    "repairs": {"label": "Repairs and replacements"},
    "windows-doors": {"label": "Windows and doors"},
    "electrical-service": {"label": "Electrical service upgrades"},
    "water-heaters": {"label": "Water heaters"},
    "irrigation": {"label": "Irrigation"},
    "foundation": {"label": "Foundation repairs"},
    "accessory": {"label": "Accessory buildings"},
    "fences-patios": {"label": "Fences, walls and patio covers"},
    "porches-decks": {"label": "Porches and decks"},
    "garages": {"label": "Detached garages"},
    "seismic": {"label": "Seismic retrofits"},
    "demolition": {"label": "Demolitions"},
}

PAGE_CATS = ["new-homes", "pools", "additions-remodels", "adus", "wildfire-rebuilds"]
MIN_FOR_PAGE = 10        # permits in the last four weeks
WINDOW_DAYS = 28
WEEKS_SHOWN = 8
INDEXNOW_KEY = "7b61600424cf228c334aea7889bc19ee"
