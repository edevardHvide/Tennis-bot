"""GolfBox HTTP client — login, session management, grid fetching.

LIMITATION: When run from AWS Lambda (eu-north-1 / Stockholm exit IP),
GolfBox's load balancer routes us into the guest IIS app-pool, which
returns a stripped grid with wrong price tier (795,- guest rate vs 845,-
member rate) and tournament-blocked cells re-exposed as bookable.

The same code run from a Norwegian residential IP returns the member view
correctly. TLS impersonation via curl_cffi was tried as a workaround — it
did not change behavior, but we keep it because it doesn't hurt and may
help if GolfBox starts UA/TLS-gating in the future.
"""

import logging
from curl_cffi import requests
from curl_cffi.requests.exceptions import RequestException

logger = logging.getLogger(__name__)

GOLFBOX_LOGIN_URL = "https://www.golfbox.no/login.asp"
GOLFBOX_FRONTPAGE_URL = "https://www.golfbox.no/site/my_golfbox/myFrontPage.asp"
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
        # impersonate=chrome131 — match latest stable Chrome TLS+H2 fingerprint.
        # Without this, GolfBox serves the guest view (see module docstring).
        self._session = requests.Session(impersonate="chrome131")
        # GolfBox returns a stripped guest view to clients with the default
        # python-requests User-Agent (wrong price tier, tournament blocks shown
        # as bookable). Identify as a real browser.
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Accept-Language": "nb-NO,nb;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br, zstd",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
            "Sec-Fetch-User": "?1",
            "sec-ch-ua": '"Chromium";v="131", "Not_A Brand";v="24", "Google Chrome";v="131"',
            "sec-ch-ua-mobile": "?0",
            "sec-ch-ua-platform": '"macOS"',
        })
        self._logged_in = False

    def login(self):
        """Authenticate with GolfBox. Returns True on success.

        Browser-like flow:
        1. GET /login.asp to collect initial session cookies + Set-Cookie state
        2. POST credentials with allow_redirects=True so we follow the full
           302 chain and collect every Set-Cookie along the way (the booking
           grid requires the /site/my_golfbox/ path cookie that's only set
           on a later hop)
        3. GET /site/my_golfbox/myFrontPage.asp as a final warm-up to ensure
           the member-view session is fully primed (without this the grid
           sometimes returns the anonymous/guest view: wrong price tier and
           tournament blocks treated as bookable)
        """
        self._session.cookies.clear()
        self._session.cookies.set("cookiePolicy", "accepted", domain="www.golfbox.no", path="/")

        try:
            self._session.get(GOLFBOX_LOGIN_URL, timeout=10)
        except RequestException as e:
            logger.warning("Pre-login GET failed: %s", e)

        resp = self._session.post(
            GOLFBOX_LOGIN_URL,
            data={
                "loginform.submitted": "true",
                "loginform.username": self._username,
                "loginform.password": self._password,
                "command": "login",
                "redirect": "//www.norskgolf.no",
            },
            headers={
                "Origin": "https://www.golfbox.no",
                "Referer": "https://www.golfbox.no/login.asp",
                "Content-Type": "application/x-www-form-urlencoded",
                "Sec-Fetch-Site": "same-origin",
            },
            allow_redirects=True,
            timeout=15,
        )

        if resp.status_code >= 400:
            logger.error("GolfBox login failed: status=%d url=%s", resp.status_code, resp.url)
            self._logged_in = False
            return False

        if "login.asp" in resp.url.lower():
            logger.error("GolfBox login bounced back to login.asp — bad credentials?")
            self._logged_in = False
            return False

        try:
            self._session.get(GOLFBOX_FRONTPAGE_URL, timeout=10)
        except RequestException as e:
            logger.warning("Frontpage warm-up failed: %s", e)

        self._logged_in = True
        logger.info("GolfBox login successful, cookies=%d, final_url=%s",
                    len(self._session.cookies), resp.url)
        return True

    def fetch_grid(self, resource_guid, club_guid, date_str):
        """Fetch a grid page HTML. Returns None on failure."""
        if not self._logged_in:
            logger.error("Cannot fetch grid — not logged in")
            return None

        url = build_grid_url(resource_guid, club_guid, date_str)
        try:
            resp = self._session.get(url, timeout=15)
        except RequestException as e:
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
