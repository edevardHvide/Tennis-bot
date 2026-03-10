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

# Active facilities that are currently monitored
facilities = {
    "frogner": {
        "matchi_id": 2259,
        "display_name": "Frogner",
        "sports": ["tennis"],
    },
    "ota": {
        "matchi_id": 1779,
        "display_name": "OTA",
        "sports": ["tennis", "padel"],
    },
    "bergentennisarena": {
        "matchi_id": 301,
        "display_name": "Bergen Tennis Arena",
        "sports": ["tennis"],
    },
}

# Inactive facilities (e.g., winter closures, maintenance)
# These are preserved for reference but not monitored
inactive_facilities = {
    "voldsløkka": {
        "matchi_id": 642,
        "display_name": "Voldsløkka",
        "sports": ["tennis"],
    },  # Winter closure (vinterstengt)
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
