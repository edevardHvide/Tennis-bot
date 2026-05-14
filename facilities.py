"""
Facilities Configuration for the Availability Monitor.

This module contains facility definitions for the Matchi booking system,
including which sports each facility supports.

Facilities are split into two categories:
- Active: Currently monitored for available courts
- Inactive: Temporarily disabled (e.g., winter closures, maintenance)

To temporarily disable a facility (e.g., for winter):
1. Move the entry from 'facilities' to 'inactive_facilities'
2. Add a comment explaining why (e.g., "Winter closure")

To re-enable a facility:
1. Move the entry from 'inactive_facilities' back to 'facilities'
2. Remove or update the comment
"""

# Matchi sport code mapping
SPORT_CODES = {"tennis": 1, "padel": 5}

# Weather regions — coords used to fetch yr.no forecasts.
# Facilities are grouped by region (not per-facility coords) because:
#   - yr.no resolution is ~1km; within-city precision is overkill
#   - One fetch per region keeps API usage minimal (MET fair-use)
# Centroids are official city centers (Oslo, Bergen, Fredrikstad).
WEATHER_REGIONS: dict[str, tuple[float, float]] = {
    "oslo": (59.9139, 10.7522),
    "bergen": (60.3913, 5.3221),
    "fredrikstad": (59.2189, 10.9298),
}

# Active facilities that are currently monitored
facilities = {
    "ota": {
        "matchi_id": 1779,
        "display_name": "OTA",
        "sports": ["tennis", "padel"],
        "weather_region": "oslo",
    },
    "bergentennisarena": {
        "matchi_id": 301,
        "display_name": "Bergen Tennis Arena",
        "sports": ["tennis"],
        "weather_region": "bergen",
    },
    "furuset": {
        "matchi_id": 542,
        "display_name": "Furuset",
        "sports": ["tennis", "padel"],
        "weather_region": "oslo",
    },
    "interpadel": {
        "matchi_id": 872,
        "display_name": "InterPadel Oslo",
        "sports": ["padel"],
        "weather_region": "oslo",
    },
    "nordicpadel": {
        "matchi_id": 811,
        "display_name": "Nordic Padel",
        "sports": ["padel"],
        "weather_region": "oslo",
    },
    "nordstrand": {
        "matchi_id": 178,
        "display_name": "Nordstrand Tennisklubb",
        "sports": ["tennis"],
        "weather_region": "oslo",
    },
    "voldslokka": {
        "matchi_id": 642,
        "display_name": "Voldsløkka",
        "sports": ["tennis"],
        "weather_region": "oslo",
    },
    "frogner": {
        "matchi_id": 2259,
        "display_name": "Frogner",
        "sports": ["tennis"],
        "weather_region": "oslo",
    },
    "bergenpadelklubb": {
        "matchi_id": 1659,
        "display_name": "Bergen Padelklubb",
        "sports": ["padel"],
        "weather_region": "bergen",
    },
    "interpadelbergen": {
        "matchi_id": 948,
        "display_name": "InterPadel Bergen (Sandsli)",
        "sports": ["padel"],
        "weather_region": "bergen",
    },
    "harvard": {
        "matchi_id": None,  # Harvard uses Innosoft Fusion, not matchi.se — no matchi_id
        "display_name": "Harvard Recreation",
        "sports": ["tennis"],
        # No weather_region — US facility, skipped from yr.no fetcher
    },
    "onsoy": {
        "matchi_id": None,  # GolfBox platform, not matchi.se
        "display_name": "Onsøy Golf",
        "sports": ["golf"],
        "weather_region": "fredrikstad",
        "golfbox": {
            "resource_guid": "884D570B-7F66-4ECD-88E2-215E3B386422",
            "club_guid": "A85DA1E0-B469-4702-BDBC-4E8972EC50A9",
        },
    },
    "haga": {
        "matchi_id": None,
        "display_name": "Haga GK",
        "sports": ["golf"],
        "weather_region": "oslo",
        "golfbox": {
            "resource_guid": "E95F6988-C683-43F8-919C-7F835DBFAF27",
            "club_guid": "E0105CD4-744F-4323-9B70-426E833E2EE6",
        },
    },
    "grini": {
        "matchi_id": None,
        "display_name": "Grini GK",
        "sports": ["golf"],
        "weather_region": "oslo",
        "golfbox": {
            "resource_guid": "1BEE50FC-669C-4383-A47E-5354F7AC08EC",
            "club_guid": "EE00C492-7F02-4C2C-851B-8CDDC89181DB",
        },
    },
    "losby": {
        "matchi_id": None,
        "display_name": "Losby Golfklubb",
        "sports": ["golf"],
        "weather_region": "oslo",
        "golfbox": {
            "resource_guid": "3C44C599-4A4C-40D9-8AF7-9F3CDB9EDD7F",
            "club_guid": "90FA30D3-FF9D-4C3E-92C9-115B01A8D7BD",
        },
    },
    "rivertz": {
        "matchi_id": None,  # Oslo kommune booking platform, not matchi.se
        "display_name": "Padelbane Arkitekt Rivertz' plass",
        "sports": ["padel"],
        "weather_region": "oslo",
        "oslobooking": {
            # booking.oslo.kommune.no — single public padel court in Sagene
            "bookable_asset_id": "7ad1690a-e5d3-4ec2-885b-54c27d3d2741",
            "court_name": "Padelbane",
            # Kommune caps at 7 days ahead; further dates always return []
            "days_ahead": 7,
            # Deep link into the booking UI (used by email CTA)
            "booking_url": "https://booking.oslo.kommune.no/ressurs?ressurs=7ad1690a-e5d3-4ec2-885b-54c27d3d2741",
        },
    },
}

# Inactive facilities — temporarily disabled to reduce scrape time
inactive_facilities = {
    "ullern": {
        "matchi_id": 219,
        "display_name": "Ullern Tennisklubb",
        "sports": ["tennis"],
    },
    "heming": {
        "matchi_id": 2144,
        "display_name": "Heming Tennis og Padel",
        "sports": ["tennis", "padel"],
    },
    "holmenkollen": {
        "matchi_id": 452,
        "display_name": "Holmenkollen Tennisklubb",
        "sports": ["tennis"],
    },
}


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def get_matchi_id(facility_key: str) -> int:
    """Return the Matchi integer ID for a facility."""
    return facilities[facility_key]["matchi_id"]


def get_display_name(facility_key: str) -> str:
    """Return the human-readable display name for a facility."""
    return facilities[facility_key]["display_name"]


def get_sports(facility_key: str) -> list[str]:
    """Return the list of sports supported by a facility."""
    return facilities[facility_key]["sports"]


def get_facilities_for_sport(sport: str) -> dict[str, dict]:
    """Return all active facilities that support the given sport."""
    return {
        key: config
        for key, config in facilities.items()
        if sport in config["sports"]
    }


def get_golfbox_config(facility_key: str):
    """Return GolfBox config dict for a facility, or None if not a GolfBox facility."""
    facility = facilities.get(facility_key)
    if facility is None:
        return None
    return facility.get("golfbox")


def get_oslobooking_config(facility_key: str):
    """Return Oslo kommune booking config for a facility, or None if not on that platform."""
    facility = facilities.get(facility_key)
    if facility is None:
        return None
    return facility.get("oslobooking")


def get_weather_region(facility_key: str) -> str | None:
    """Return the weather region key for a facility, or None if no forecast applies."""
    facility = facilities.get(facility_key)
    if facility is None:
        return None
    return facility.get("weather_region")
