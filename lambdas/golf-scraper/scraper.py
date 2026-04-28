"""GolfBox HTTP client — login, session management, grid fetching."""

import logging
import requests

logger = logging.getLogger(__name__)

GOLFBOX_LOGIN_URL = "https://www.golfbox.no/login.asp"
GOLFBOX_GRID_BASE = (
    "https://www.golfbox.no/site/my_golfbox/ressources/booking/grid.asp"
)


def build_grid_url(resource_guid, club_guid, date_str):
    """Build a GolfBox grid URL for a given date.

    Args:
        resource_guid: Resource GUID from facility config.
        club_guid: Club GUID from facility config.
        date_str: Date in YYYY-MM-DD format.

    Returns:
        Full GolfBox grid URL.
    """
    date_compact = date_str.replace("-", "")
    return (
        f"{GOLFBOX_GRID_BASE}"
        f"?Ressource_GUID={{{resource_guid}}}"
        f"&Club_GUID={club_guid}"
        f"&Booking_Start={date_compact}T060000"
    )


class GolfBoxClient:
    """HTTP client for GolfBox with session management."""

    def __init__(self, username, password):
        self._username = username
        self._password = password
        self._session = requests.Session()
        self._logged_in = False

    def login(self):
        """Authenticate with GolfBox. Returns True on success."""
        # Clear any cookies from a previous (possibly stale) session — keeping
        # them around causes duplicate cookies (e.g. two ``logoutPage`` entries
        # on different paths) that make ``dict(session.cookies)`` blow up with
        # CookieConflictError when we try to cache the new session.
        self._session.cookies.clear()

        resp = self._session.post(
            GOLFBOX_LOGIN_URL,
            data={
                "loginform.submitted": "true",
                "loginform.username": self._username,
                "loginform.password": self._password,
                "command": "login",
                "redirect": "//www.norskgolf.no",
            },
            allow_redirects=False,
            timeout=10,
        )

        if resp.status_code == 302:
            self._logged_in = True
            logger.info("GolfBox login successful")
            return True

        logger.error("GolfBox login failed: status=%d", resp.status_code)
        self._logged_in = False
        return False

    def fetch_grid(self, resource_guid, club_guid, date_str):
        """Fetch a grid page HTML. Returns None on failure."""
        if not self._logged_in:
            logger.error("Cannot fetch grid — not logged in")
            return None

        url = build_grid_url(resource_guid, club_guid, date_str)
        try:
            resp = self._session.get(url, timeout=15)
        except requests.RequestException as e:
            logger.error("Grid fetch failed for %s: %s", date_str, e)
            return None

        if resp.status_code != 200:
            logger.error("Grid fetch non-200: status=%d url=%s", resp.status_code, url)
            return None

        # Detect logged-out response. GolfBox does not always redirect to
        # login.asp for a stale session — sometimes it returns a 200 with a
        # generic page that lacks the booking grid. The parser keys off the
        # bookingGridv3 div, so use its absence as the session-expiry signal.
        if "login.asp" in resp.url or "bookingGridv3" not in resp.text:
            logger.warning("Session expired or grid missing for %s", date_str)
            self._logged_in = False
            return None

        return resp.text

    @property
    def cookies_dict(self):
        """Return current session cookies as a dict (for caching)."""
        return dict(self._session.cookies)

    def restore_cookies(self, cookies):
        """Restore session cookies from a cached dict."""
        self._session.cookies.update(cookies)
        self._logged_in = True
