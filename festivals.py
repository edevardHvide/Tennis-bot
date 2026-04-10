"""
Festival ticket monitoring configuration.

Analogous to facilities.py for the tennis/padel pipeline, but completely
isolated.  Used by the festival-preferences Lambda and the
festival_monitor.py cron script.
"""

FESTIVALS = {
    "vinjerock-2026": {
        "name": "Vinjerock 2026",
        "url": "https://www.ticketmaster.no/event/vinjerock-2026-billetter/1742328414",
        "platform": "ticketmaster",
        "dates": "16–19 July 2026",
        "location": "Eidsbugarden, Vang i Valdres",
    },
}


def get_festival(festival_id: str):
    """Return festival config or None if not found."""
    return FESTIVALS.get(festival_id)


def get_all_festival_ids() -> list[str]:
    """Return list of all festival IDs."""
    return list(FESTIVALS.keys())
