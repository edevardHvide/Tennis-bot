"""Tests for the MCP path of golf-scraper (mcp_to_slots + mcp_client)."""
import importlib
import json
import os
import sys
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_GOLF_SCRAPER_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "lambdas",
    "golf-scraper",
)
sys.path.insert(0, _GOLF_SCRAPER_DIR)


def _load_golf_handler():
    """Force-load the golf-scraper handler module.

    Multiple lambdas have a top-level handler.py; pytest's shared module cache
    means whichever test file imports `handler` first wins. Pop and reload so
    we always get the golf one when this test file runs.
    """
    for mod in ("handler", "parser", "scraper", "mcp_client", "mcp_to_slots"):
        sys.modules.pop(mod, None)
    if _GOLF_SCRAPER_DIR not in sys.path:
        sys.path.insert(0, _GOLF_SCRAPER_DIR)
    elif sys.path[0] != _GOLF_SCRAPER_DIR:
        sys.path.remove(_GOLF_SCRAPER_DIR)
        sys.path.insert(0, _GOLF_SCRAPER_DIR)
    return importlib.import_module("handler")


# --- mcp_to_slots tests ----------------------------------------------------


class TestExtractTimeKey:
    def test_basic_iso(self):
        from mcp_to_slots import _extract_time_key
        assert _extract_time_key("2026-05-25T07:09:00") == "07:09"

    def test_late_hour(self):
        from mcp_to_slots import _extract_time_key
        assert _extract_time_key("2026-05-25T23:59:00") == "23:59"

    def test_none_input(self):
        from mcp_to_slots import _extract_time_key
        assert _extract_time_key(None) is None

    def test_no_t_separator(self):
        from mcp_to_slots import _extract_time_key
        assert _extract_time_key("2026-05-25 07:09:00") is None

    def test_malformed_short(self):
        from mcp_to_slots import _extract_time_key
        assert _extract_time_key("2026-05-25T07") is None

    def test_missing_colon(self):
        from mcp_to_slots import _extract_time_key
        assert _extract_time_key("2026-05-25T0709:00") is None


class TestExtractPrice:
    def test_handicap_merged_price(self):
        from mcp_to_slots import _extract_price
        # ",N(NNN)" — last digit before is single handicap decimal
        assert _extract_price("Spiller A hcp:21,7845,-") == "845,-"

    def test_handicap_merged_price_four_digit(self):
        from mcp_to_slots import _extract_price
        assert _extract_price("Spiller A hcp:21,71095,-") == "1095,-"

    def test_bare_three_digit_price(self):
        from mcp_to_slots import _extract_price
        assert _extract_price("845,-") == "845,-"

    def test_bare_four_digit_price(self):
        from mcp_to_slots import _extract_price
        assert _extract_price("1095,-") == "1095,-"

    def test_five_digit_merged_hhmm_plus_three(self):
        from mcp_to_slots import _extract_price
        # "07:00845" → time + 3-digit price
        assert _extract_price("07:00845") == "845,-"

    def test_six_digit_merged_hhmm_plus_four(self):
        from mcp_to_slots import _extract_price
        # "07:001095" → time + 4-digit price
        assert _extract_price("07:001095") == "1095,-"

    def test_six_digit_leading_zero_rejected(self):
        from mcp_to_slots import _extract_price
        # last4 starts with 0 → reject
        assert _extract_price("07:000845") is None

    def test_empty_label(self):
        from mcp_to_slots import _extract_price
        assert _extract_price("") is None

    def test_none_label(self):
        from mcp_to_slots import _extract_price
        assert _extract_price(None) is None

    def test_no_digits(self):
        from mcp_to_slots import _extract_price
        assert _extract_price("Spiller A") is None


class TestSpotsAvailable:
    def test_free_returns_full_capacity(self):
        from mcp_to_slots import _spots_available, TEE_CAPACITY
        assert _spots_available({"status": "free"}) == TEE_CAPACITY

    def test_full_returns_zero(self):
        from mcp_to_slots import _spots_available
        assert _spots_available({"status": "full"}) == 0

    def test_tournament_returns_zero(self):
        from mcp_to_slots import _spots_available
        assert _spots_available({"status": "tournament"}) == 0

    def test_partial_with_booked(self):
        from mcp_to_slots import _spots_available
        assert _spots_available({"status": "partial", "capacity": 4, "booked": 1}) == 3

    def test_partial_full_capacity(self):
        from mcp_to_slots import _spots_available
        assert _spots_available({"status": "partial", "capacity": 4, "booked": 4}) == 0

    def test_partial_default_capacity(self):
        from mcp_to_slots import _spots_available
        assert _spots_available({"status": "partial", "booked": 2}) == 2

    def test_partial_no_booked_falls_back_to_players(self):
        from mcp_to_slots import _spots_available
        slot = {"status": "partial", "capacity": 4, "players": [{"n": "A"}, {"n": "B"}]}
        assert _spots_available(slot) == 2

    def test_partial_no_booked_no_players_defaults_to_one_booked(self):
        from mcp_to_slots import _spots_available
        assert _spots_available({"status": "partial", "capacity": 4}) == 3


class TestMcpSlotsToDict:
    def test_free_slot_full_capacity(self):
        from mcp_to_slots import mcp_slots_to_dict
        slots = [{
            "start": "2026-05-25T07:00:00",
            "status": "free",
            "raw_label": "07:00845,-",
        }]
        result = mcp_slots_to_dict(slots)
        assert result == {"07:00": ["4 spots (845,-)"]}

    def test_partial_with_booked(self):
        from mcp_to_slots import mcp_slots_to_dict
        slots = [{
            "start": "2026-05-25T07:09:00",
            "status": "partial",
            "capacity": 4,
            "booked": 3,
            "raw_label": "07:09845,-",
        }]
        result = mcp_slots_to_dict(slots)
        assert result == {"07:09": ["1 spot (845,-)"]}

    def test_blocked_skipped(self):
        from mcp_to_slots import mcp_slots_to_dict
        slots = [
            {"start": "2026-05-25T07:00:00", "status": "tournament", "raw_label": "x"},
            {"start": "2026-05-25T07:09:00", "status": "closed", "raw_label": "x"},
            {"start": "2026-05-25T07:18:00", "status": "blocked", "raw_label": "x"},
            {"start": "2026-05-25T07:27:00", "status": "expired", "raw_label": "x"},
            {"start": "2026-05-25T07:36:00", "status": "too_far_ahead", "raw_label": "x"},
            {"start": "2026-05-25T07:45:00", "status": "full", "raw_label": "x"},
        ]
        assert mcp_slots_to_dict(slots) == {}

    def test_multiple_slots_same_time_combined(self):
        from mcp_to_slots import mcp_slots_to_dict
        slots = [
            {
                "start": "2026-05-25T07:00:00",
                "status": "free",
                "raw_label": "07:00845,-",
            },
            {
                "start": "2026-05-25T07:00:00",
                "status": "partial",
                "capacity": 4,
                "booked": 2,
                "raw_label": "07:00845,-",
            },
        ]
        result = mcp_slots_to_dict(slots)
        assert sorted(result["07:00"]) == sorted(["4 spots (845,-)", "2 spots (845,-)"])

    def test_partial_with_zero_spots_dropped(self):
        from mcp_to_slots import mcp_slots_to_dict
        slots = [{
            "start": "2026-05-25T07:00:00",
            "status": "partial",
            "capacity": 4,
            "booked": 4,
            "raw_label": "07:00845,-",
        }]
        assert mcp_slots_to_dict(slots) == {}

    def test_price_missing_uses_count_only(self):
        from mcp_to_slots import mcp_slots_to_dict
        slots = [{
            "start": "2026-05-25T07:00:00",
            "status": "free",
            "raw_label": "garbage",
        }]
        result = mcp_slots_to_dict(slots)
        assert result == {"07:00": ["4 spots"]}

    def test_singular_spot_grammar(self):
        from mcp_to_slots import mcp_slots_to_dict
        slots = [{
            "start": "2026-05-25T07:00:00",
            "status": "partial",
            "capacity": 4,
            "booked": 3,
            "raw_label": "07:00845,-",
        }]
        result = mcp_slots_to_dict(slots)
        assert result == {"07:00": ["1 spot (845,-)"]}

    def test_unparseable_time_skipped(self):
        from mcp_to_slots import mcp_slots_to_dict
        slots = [{"start": "garbage", "status": "free", "raw_label": "07:00845"}]
        assert mcp_slots_to_dict(slots) == {}


# --- mcp_client tests ------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_mcp_client():
    """Clear module-level cache between tests."""
    import mcp_client
    mcp_client.reset_for_tests()
    yield
    mcp_client.reset_for_tests()


def _mock_urlopen_response(body, headers=None, content_type="application/json"):
    """Build a context-manager-compatible mock response.

    Real dicts already have .get(); no need to wrap headers further.
    """
    resp = MagicMock()
    resp.read.return_value = body.encode() if isinstance(body, str) else body
    resp.headers = headers if headers is not None else {"Content-Type": content_type}
    resp.__enter__ = lambda self: self
    resp.__exit__ = lambda *a: None
    return resp


class TestRefreshAccessToken:
    def test_refresh_caches_token(self):
        import mcp_client

        creds = {"client_id": "c1", "refresh_token": "rt1"}
        with patch.object(mcp_client, "_load_credentials", return_value=creds), \
             patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value = _mock_urlopen_response(
                json.dumps({"access_token": "at1", "expires_in": 3600}),
            )
            mcp_client._refresh_access_token()

        assert mcp_client._access_token == "at1"
        assert mcp_client._access_expires_at > 0

    def test_refresh_rotates_persisted_refresh_token(self):
        import mcp_client

        creds = {"client_id": "c1", "refresh_token": "rt1"}
        with patch.object(mcp_client, "_load_credentials", return_value=creds), \
             patch.object(mcp_client, "_persist_refresh_token") as mock_persist, \
             patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value = _mock_urlopen_response(
                json.dumps({
                    "access_token": "at1",
                    "expires_in": 3600,
                    "refresh_token": "rt2",
                }),
            )
            mcp_client._refresh_access_token()

        mock_persist.assert_called_once_with("rt2")

    def test_refresh_no_rotation_no_persist(self):
        import mcp_client

        creds = {"client_id": "c1", "refresh_token": "rt1"}
        with patch.object(mcp_client, "_load_credentials", return_value=creds), \
             patch.object(mcp_client, "_persist_refresh_token") as mock_persist, \
             patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value = _mock_urlopen_response(
                json.dumps({
                    "access_token": "at1",
                    "expires_in": 3600,
                    "refresh_token": "rt1",
                }),
            )
            mcp_client._refresh_access_token()

        mock_persist.assert_not_called()

    def test_refresh_no_access_token_raises_auth_error(self):
        import mcp_client

        creds = {"client_id": "c1", "refresh_token": "rt1"}
        with patch.object(mcp_client, "_load_credentials", return_value=creds), \
             patch("urllib.request.urlopen") as mock_open:
            mock_open.return_value = _mock_urlopen_response(
                json.dumps({"error": "invalid_grant"}),
            )
            with pytest.raises(mcp_client.MCPAuthError):
                mcp_client._refresh_access_token()

    def test_refresh_http_error_raises_auth_error(self):
        import urllib.error
        import mcp_client

        creds = {"client_id": "c1", "refresh_token": "rt1"}
        err = urllib.error.HTTPError("u", 400, "Bad", {}, None)
        err.read = lambda: b'{"error":"invalid_grant"}'
        with patch.object(mcp_client, "_load_credentials", return_value=creds), \
             patch("urllib.request.urlopen", side_effect=err):
            with pytest.raises(mcp_client.MCPAuthError):
                mcp_client._refresh_access_token()


class TestEnsureAccessToken:
    def test_warm_token_reused(self):
        import time as _time
        import mcp_client

        mcp_client._access_token = "warm"
        mcp_client._access_expires_at = int(_time.time()) + 600

        with patch.object(mcp_client, "_refresh_access_token") as mock_refresh:
            token = mcp_client._ensure_access_token()

        assert token == "warm"
        mock_refresh.assert_not_called()

    def test_expired_token_triggers_refresh(self):
        import mcp_client

        mcp_client._access_token = "old"
        mcp_client._access_expires_at = 0

        def fake_refresh():
            mcp_client._access_token = "new"
            mcp_client._access_expires_at = 10**12

        with patch.object(mcp_client, "_refresh_access_token", side_effect=fake_refresh):
            token = mcp_client._ensure_access_token()

        assert token == "new"


class TestPostJsonRpc:
    def test_session_id_captured_from_header(self):
        import mcp_client

        mcp_client._access_token = "at"
        mcp_client._access_expires_at = 10**12

        resp = _mock_urlopen_response(
            json.dumps({"jsonrpc": "2.0", "id": 1, "result": {}}),
            headers={
                "Content-Type": "application/json",
                "Mcp-Session-Id": "sess-123",
            },
        )
        with patch("urllib.request.urlopen", return_value=resp):
            mcp_client._post_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "ping"})

        assert mcp_client._session_id == "sess-123"

    def test_sse_response_parsed(self):
        import mcp_client

        mcp_client._access_token = "at"
        mcp_client._access_expires_at = 10**12

        sse_body = (
            "event: message\n"
            'data: {"jsonrpc":"2.0","id":1,"result":{"ok":true}}\n\n'
        )
        resp = _mock_urlopen_response(
            sse_body, headers={"Content-Type": "text/event-stream"},
        )
        with patch("urllib.request.urlopen", return_value=resp):
            data = mcp_client._post_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "x"})

        assert data["result"] == {"ok": True}

    def test_401_raises_auth_error(self):
        import urllib.error
        import mcp_client

        mcp_client._access_token = "at"
        mcp_client._access_expires_at = 10**12

        err = urllib.error.HTTPError("u", 401, "Unauth", {}, None)
        err.read = lambda: b'{"error":"invalid_token"}'
        with patch("urllib.request.urlopen", side_effect=err):
            with pytest.raises(mcp_client.MCPAuthError):
                mcp_client._post_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "x"})


class TestSearchTeeTimes:
    def test_calls_initialize_then_tool(self):
        import mcp_client

        mcp_client._access_token = "at"
        mcp_client._access_expires_at = 10**12

        # Three sequential urlopen calls: initialize, notifications/initialized,
        # tools/call. The notifications call has expect_response=False so we
        # don't strictly need to parse its body, but the handler still reads
        # one response per urlopen — return empty JSON for it.
        responses = [
            _mock_urlopen_response(json.dumps({
                "jsonrpc": "2.0", "id": 1,
                "result": {"protocolVersion": "2025-03-26", "capabilities": {}},
            })),
            _mock_urlopen_response(json.dumps({})),
            _mock_urlopen_response(json.dumps({
                "jsonrpc": "2.0", "id": 99,
                "result": {"content": [{"text": json.dumps([
                    {"start": "2026-05-25T07:00:00", "status": "free",
                     "raw_label": "07:00845,-"},
                ])}]},
            })),
        ]
        with patch("urllib.request.urlopen", side_effect=responses):
            slots = mcp_client.search_tee_times("onsoy_gk", "2026-05-25")

        assert slots == [
            {"start": "2026-05-25T07:00:00", "status": "free",
             "raw_label": "07:00845,-"},
        ]

    def test_401_triggers_refresh_and_retry(self):
        import urllib.error
        import mcp_client

        mcp_client._access_token = "at"
        mcp_client._access_expires_at = 10**12
        mcp_client._initialized = True  # skip initialize on first attempt

        err_401 = urllib.error.HTTPError("u", 401, "Unauth", {}, None)
        err_401.read = lambda: b'{"error":"expired"}'

        retry_responses = [
            _mock_urlopen_response(json.dumps({
                "jsonrpc": "2.0", "id": 1,
                "result": {"protocolVersion": "2025-03-26", "capabilities": {}},
            })),
            _mock_urlopen_response(json.dumps({})),
            _mock_urlopen_response(json.dumps({
                "jsonrpc": "2.0", "id": 99,
                "result": {"content": [{"text": json.dumps([])}]},
            })),
        ]

        creds = {"client_id": "c1", "refresh_token": "rt1"}
        with patch.object(mcp_client, "_load_credentials", return_value=creds), \
             patch("urllib.request.urlopen") as mock_open:
            mock_open.side_effect = [
                err_401,  # first tool call → 401
                _mock_urlopen_response(json.dumps({
                    "access_token": "at2", "expires_in": 3600,
                })),  # refresh
                *retry_responses,  # initialize + initialized + tool
            ]
            slots = mcp_client.search_tee_times("onsoy_gk", "2026-05-25")

        assert slots == []
        assert mcp_client._access_token == "at2"

    def test_auth_error_propagates_after_failed_refresh(self):
        import urllib.error
        import mcp_client

        mcp_client._access_token = "at"
        mcp_client._access_expires_at = 10**12
        mcp_client._initialized = True

        err_401 = urllib.error.HTTPError("u", 401, "Unauth", {}, None)
        err_401.read = lambda: b'x'
        refresh_err = urllib.error.HTTPError("u", 400, "Bad", {}, None)
        refresh_err.read = lambda: b'x'

        creds = {"client_id": "c1", "refresh_token": "rt1"}
        with patch.object(mcp_client, "_load_credentials", return_value=creds), \
             patch("urllib.request.urlopen") as mock_open:
            mock_open.side_effect = [err_401, refresh_err]
            with pytest.raises(mcp_client.MCPAuthError):
                mcp_client.search_tee_times("onsoy_gk", "2026-05-25")


# --- handler helper tests (data-source switch) -----------------------------


class TestFetchSlotsViaMcp:
    def test_returns_none_when_facility_lacks_slug(self):
        handler = _load_golf_handler()
        result = handler._fetch_slots_via_mcp({"resource_guid": "x"}, "2026-05-25")
        assert result is None

    def test_calls_search_tee_times_with_slug(self):
        handler = _load_golf_handler()

        with patch("mcp_client.search_tee_times") as mock_search:
            mock_search.return_value = [{
                "start": "2026-05-25T07:00:00",
                "status": "free",
                "raw_label": "07:00845,-",
            }]
            result = handler._fetch_slots_via_mcp(
                {"mcp_slug": "onsoy_gk"}, "2026-05-25",
            )

        mock_search.assert_called_once_with("onsoy_gk", "2026-05-25", only_free=True)
        assert result == {"07:00": ["4 spots (845,-)"]}

    def test_auth_error_propagates_to_caller(self):
        """Handler relies on this exception to bump auth_failures."""
        handler = _load_golf_handler()
        import mcp_client

        with patch(
            "mcp_client.search_tee_times",
            side_effect=mcp_client.MCPAuthError("boom"),
        ):
            with pytest.raises(mcp_client.MCPAuthError):
                handler._fetch_slots_via_mcp({"mcp_slug": "x"}, "2026-05-25")


class TestFetchSlotsViaScrape:
    def test_returns_parsed_slots_on_success(self):
        handler = _load_golf_handler()

        client = MagicMock()
        client.fetch_grid.return_value = (
            "<table><tr><td><span class='time'>07:00</span>Available</td></tr></table>"
        )
        client._logged_in = True

        with patch("parser.parse_grid_html", return_value={"07:00": ["x"]}):
            result = handler._fetch_slots_via_scrape(
                client,
                {"resource_guid": "r", "club_guid": "c"},
                "2026-05-25",
                lambda _: None,
            )
        assert result == {"07:00": ["x"]}

    def test_session_expiry_triggers_relogin_and_retry(self):
        handler = _load_golf_handler()

        client = MagicMock()
        # First fetch fails AND _logged_in is False → triggers re-login path.
        client.fetch_grid.side_effect = [None, "<html/>"]
        client._logged_in = False
        client.login.return_value = True
        client.cookies_dict = {"k": "v"}

        cache_calls = []
        with patch("parser.parse_grid_html", return_value={"07:00": []}):
            result = handler._fetch_slots_via_scrape(
                client,
                {"resource_guid": "r", "club_guid": "c"},
                "2026-05-25",
                lambda c: cache_calls.append(c),
            )

        assert result == {"07:00": []}
        client.login.assert_called_once()
        assert cache_calls == [{"k": "v"}]

    def test_returns_none_when_relogin_fails(self):
        handler = _load_golf_handler()

        client = MagicMock()
        client.fetch_grid.return_value = None
        client._logged_in = False
        client.login.return_value = False

        result = handler._fetch_slots_via_scrape(
            client,
            {"resource_guid": "r", "club_guid": "c"},
            "2026-05-25",
            lambda _: None,
        )
        assert result is None


class TestMcpAuthCircuitBreaker:
    """Regression for the 2026-05-21 incident: a broken OAuth chain must not
    retry every facility+date and hammer the token endpoint into 429s."""

    def _run_with_failing_mcp(self, n_facilities, limit):
        import facilities as facilities_mod
        handler = _load_golf_handler()
        import mcp_client

        handler.GOLF_DATA_SOURCE = "mcp"
        handler.MCP_AUTH_FAILURE_LIMIT = limit
        handler.DAYS_AHEAD = 14  # 14 dates per facility → 14*n potential calls

        facs = {f"club{i}": {"sports": ["golf"]} for i in range(n_facilities)}
        calls = {"n": 0}

        def always_auth_fail(cfg, date_str):
            calls["n"] += 1
            raise mcp_client.MCPAuthError("simulated invalid_grant")

        with patch.object(facilities_mod, "get_facilities_for_sport", return_value=facs), \
             patch.object(facilities_mod, "get_golfbox_config",
                          return_value={"mcp_slug": "x"}), \
             patch.object(handler, "_get_dynamodb", return_value=MagicMock()), \
             patch.object(handler, "_load_previous_snapshot", return_value={}), \
             patch.object(handler, "_save_snapshot"), \
             patch.object(handler, "_invoke_notifications"), \
             patch.object(handler, "_fetch_slots_via_mcp", side_effect=always_auth_fail):
            resp = handler.lambda_handler({}, None)
        return calls["n"], resp

    def test_aborts_after_limit_not_all_dates(self):
        # 3 facilities * 14 dates = 42 potential calls; breaker must stop at 3.
        n_calls, resp = self._run_with_failing_mcp(n_facilities=3, limit=3)
        assert n_calls == 3
        body = json.loads(resp["body"])
        assert body["authAborted"] is True
        assert body["authFailures"] == 3
        assert body["totalSlots"] == 0

    def test_limit_of_one_aborts_immediately(self):
        n_calls, resp = self._run_with_failing_mcp(n_facilities=2, limit=1)
        assert n_calls == 1
        body = json.loads(resp["body"])
        assert body["authAborted"] is True
