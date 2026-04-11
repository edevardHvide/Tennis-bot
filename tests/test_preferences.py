"""
Unit tests for the Preferences API Lambda handler.

Uses moto to mock DynamoDB — no real AWS calls are made.

Run with:
    pip install pytest moto[dynamodb] boto3
    pytest tests/test_preferences.py -v
"""

import importlib
import json
import os
import sys

import boto3
import pytest
from moto import mock_aws

# ---------------------------------------------------------------------------
# Ensure the handler module can be imported regardless of working directory
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

HANDLER_DIR = os.path.join(os.path.dirname(__file__), "..", "lambdas", "preferences")
if HANDLER_DIR not in sys.path:
    sys.path.insert(0, HANDLER_DIR)


# ---------------------------------------------------------------------------
# Constants shared across tests
# ---------------------------------------------------------------------------

REGION = "eu-north-1"
USERS_TABLE = "tennis-users"
PREFS_TABLE = "tennis-preferences"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def aws_env(monkeypatch):
    """Set environment variables before each test and unset after."""
    monkeypatch.setenv("AWS_DEFAULT_REGION", REGION)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("USERS_TABLE", USERS_TABLE)
    monkeypatch.setenv("PREFS_TABLE", PREFS_TABLE)


@pytest.fixture()
def dynamo():
    """Spin up a moto-mocked DynamoDB with both tables and yield the resource."""
    with mock_aws():
        client = boto3.client("dynamodb", region_name=REGION)

        client.create_table(
            TableName=USERS_TABLE,
            AttributeDefinitions=[{"AttributeName": "userId", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "userId", "KeyType": "HASH"}],
            BillingMode="PAY_PER_REQUEST",
        )

        client.create_table(
            TableName=PREFS_TABLE,
            AttributeDefinitions=[
                {"AttributeName": "userId", "AttributeType": "S"},
                {"AttributeName": "preferenceId", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "userId", "KeyType": "HASH"},
                {"AttributeName": "preferenceId", "KeyType": "RANGE"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # Re-import handler inside the moto context so its module-level
        # _dynamodb resource points at the mocked endpoint.
        import handler as h

        importlib.reload(h)
        # Reset the cached resource so it picks up the mocked endpoint.
        h._dynamodb = None

        yield boto3.resource("dynamodb", region_name=REGION)

        # Cleanup cached resource after test
        h._dynamodb = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _event(method, resource, body=None, path_params=None):
    return {
        "httpMethod": method,
        "resource": resource,
        "pathParameters": path_params or {},
        "body": json.dumps(body) if body is not None else None,
    }


def _body(response):
    return json.loads(response["body"])


def _register_user(user_id="alice@example.com", name="Alice"):
    import handler as h

    return h.lambda_handler(
        _event("POST", "/users", {"userId": user_id, "name": name}), None
    )


def _valid_pref_body():
    return {
        "facilityId": "frogner",
        "dates": ["monday", "sunday"],
        "timeFrom": "17:00",
        "timeTo": "22:00",
    }


# ---------------------------------------------------------------------------
# POST /users
# ---------------------------------------------------------------------------


class TestCreateUser:
    def test_creates_user_successfully(self, dynamo):
        import handler as h

        response = h.lambda_handler(
            _event("POST", "/users", {"userId": "alice@example.com", "name": "Alice"}),
            None,
        )
        assert response["statusCode"] == 201
        data = _body(response)["data"]
        assert data["userId"] == "alice@example.com"
        assert data["name"] == "Alice"
        assert "createdAt" in data

    def test_cors_header_present(self, dynamo):
        import handler as h

        response = h.lambda_handler(
            _event("POST", "/users", {"userId": "alice@example.com", "name": "Alice"}),
            None,
        )
        assert response["headers"]["Access-Control-Allow-Origin"] == "*"

    def test_duplicate_user_returns_409(self, dynamo):
        import handler as h

        _register_user()
        response = h.lambda_handler(
            _event("POST", "/users", {"userId": "alice@example.com", "name": "Alice"}),
            None,
        )
        assert response["statusCode"] == 409
        assert "already exists" in _body(response)["error"]

    def test_invalid_email_returns_400(self, dynamo):
        import handler as h

        response = h.lambda_handler(
            _event("POST", "/users", {"userId": "not-an-email", "name": "Alice"}),
            None,
        )
        assert response["statusCode"] == 400

    def test_missing_name_returns_400(self, dynamo):
        import handler as h

        response = h.lambda_handler(
            _event("POST", "/users", {"userId": "alice@example.com"}), None
        )
        assert response["statusCode"] == 400

    def test_missing_user_id_returns_400(self, dynamo):
        import handler as h

        response = h.lambda_handler(
            _event("POST", "/users", {"name": "Alice"}), None
        )
        assert response["statusCode"] == 400

    def test_invalid_json_body_returns_400(self, dynamo):
        import handler as h

        event = {
            "httpMethod": "POST",
            "resource": "/users",
            "pathParameters": {},
            "body": "not-json{{{",
        }
        response = h.lambda_handler(event, None)
        assert response["statusCode"] == 400


# ---------------------------------------------------------------------------
# GET /users/{userId}/preferences
# ---------------------------------------------------------------------------


class TestListPreferences:
    def test_empty_list_for_new_user(self, dynamo):
        import handler as h

        _register_user()
        response = h.lambda_handler(
            _event(
                "GET",
                "/users/{userId}/preferences",
                path_params={"userId": "alice@example.com"},
            ),
            None,
        )
        assert response["statusCode"] == 200
        assert _body(response)["data"] == []

    def test_lists_created_preferences(self, dynamo):
        import handler as h

        _register_user()
        h.lambda_handler(
            _event(
                "POST",
                "/users/{userId}/preferences",
                body=_valid_pref_body(),
                path_params={"userId": "alice@example.com"},
            ),
            None,
        )
        response = h.lambda_handler(
            _event(
                "GET",
                "/users/{userId}/preferences",
                path_params={"userId": "alice@example.com"},
            ),
            None,
        )
        assert response["statusCode"] == 200
        items = _body(response)["data"]
        assert len(items) == 1
        assert items[0]["facilityId"] == "frogner"

    def test_unknown_user_returns_404(self, dynamo):
        import handler as h

        response = h.lambda_handler(
            _event(
                "GET",
                "/users/{userId}/preferences",
                path_params={"userId": "ghost@example.com"},
            ),
            None,
        )
        assert response["statusCode"] == 404


# ---------------------------------------------------------------------------
# POST /users/{userId}/preferences
# ---------------------------------------------------------------------------


class TestCreatePreference:
    def test_creates_preference_successfully(self, dynamo):
        import handler as h

        _register_user()
        response = h.lambda_handler(
            _event(
                "POST",
                "/users/{userId}/preferences",
                body=_valid_pref_body(),
                path_params={"userId": "alice@example.com"},
            ),
            None,
        )
        assert response["statusCode"] == 201
        data = _body(response)["data"]
        assert data["facilityId"] == "frogner"
        assert data["dates"] == ["monday", "sunday"]
        assert data["timeFrom"] == "17:00"
        assert data["timeTo"] == "22:00"
        assert "preferenceId" in data
        assert "createdAt" in data
        assert "updatedAt" in data

    def test_unknown_user_returns_404(self, dynamo):
        import handler as h

        response = h.lambda_handler(
            _event(
                "POST",
                "/users/{userId}/preferences",
                body=_valid_pref_body(),
                path_params={"userId": "ghost@example.com"},
            ),
            None,
        )
        assert response["statusCode"] == 404

    def test_invalid_facility_returns_400(self, dynamo):
        import handler as h

        _register_user()
        body = {**_valid_pref_body(), "facilityId": "mars-base-1"}
        response = h.lambda_handler(
            _event(
                "POST",
                "/users/{userId}/preferences",
                body=body,
                path_params={"userId": "alice@example.com"},
            ),
            None,
        )
        assert response["statusCode"] == 400

    def test_invalid_day_name_returns_400(self, dynamo):
        import handler as h

        _register_user()
        body = {**_valid_pref_body(), "dates": ["funday"]}
        response = h.lambda_handler(
            _event(
                "POST",
                "/users/{userId}/preferences",
                body=body,
                path_params={"userId": "alice@example.com"},
            ),
            None,
        )
        assert response["statusCode"] == 400
        assert "Invalid day name" in _body(response)["error"]

    def test_old_date_format_returns_400(self, dynamo):
        """YYYY-MM-DD format should no longer be accepted."""
        import handler as h

        _register_user()
        body = {**_valid_pref_body(), "dates": ["2026-06-01"]}
        response = h.lambda_handler(
            _event(
                "POST",
                "/users/{userId}/preferences",
                body=body,
                path_params={"userId": "alice@example.com"},
            ),
            None,
        )
        assert response["statusCode"] == 400

    def test_valid_day_names_accepted(self, dynamo):
        """All seven day names should be accepted."""
        import handler as h

        _register_user()
        all_days = ["monday", "tuesday", "wednesday", "thursday",
                     "friday", "saturday", "sunday"]
        body = {**_valid_pref_body(), "dates": all_days}
        response = h.lambda_handler(
            _event(
                "POST",
                "/users/{userId}/preferences",
                body=body,
                path_params={"userId": "alice@example.com"},
            ),
            None,
        )
        assert response["statusCode"] == 201
        assert _body(response)["data"]["dates"] == all_days

    def test_day_names_stored_lowercase(self, dynamo):
        """Day names should be stored in lowercase regardless of input case."""
        import handler as h

        _register_user()
        body = {**_valid_pref_body(), "dates": ["Monday", "FRIDAY"]}
        response = h.lambda_handler(
            _event(
                "POST",
                "/users/{userId}/preferences",
                body=body,
                path_params={"userId": "alice@example.com"},
            ),
            None,
        )
        assert response["statusCode"] == 201
        assert _body(response)["data"]["dates"] == ["monday", "friday"]

    def test_timefrom_after_timeto_returns_400(self, dynamo):
        import handler as h

        _register_user()
        body = {**_valid_pref_body(), "timeFrom": "22:00", "timeTo": "17:00"}
        response = h.lambda_handler(
            _event(
                "POST",
                "/users/{userId}/preferences",
                body=body,
                path_params={"userId": "alice@example.com"},
            ),
            None,
        )
        assert response["statusCode"] == 400

    def test_equal_timefrom_timeto_returns_400(self, dynamo):
        import handler as h

        _register_user()
        body = {**_valid_pref_body(), "timeFrom": "17:00", "timeTo": "17:00"}
        response = h.lambda_handler(
            _event(
                "POST",
                "/users/{userId}/preferences",
                body=body,
                path_params={"userId": "alice@example.com"},
            ),
            None,
        )
        assert response["statusCode"] == 400

    def test_empty_dates_list_returns_400(self, dynamo):
        import handler as h

        _register_user()
        body = {**_valid_pref_body(), "dates": []}
        response = h.lambda_handler(
            _event(
                "POST",
                "/users/{userId}/preferences",
                body=body,
                path_params={"userId": "alice@example.com"},
            ),
            None,
        )
        assert response["statusCode"] == 400

    def test_missing_facility_returns_400(self, dynamo):
        import handler as h

        _register_user()
        body = {k: v for k, v in _valid_pref_body().items() if k != "facilityId"}
        response = h.lambda_handler(
            _event(
                "POST",
                "/users/{userId}/preferences",
                body=body,
                path_params={"userId": "alice@example.com"},
            ),
            None,
        )
        assert response["statusCode"] == 400

    def test_all_active_facilities_accepted(self, dynamo):
        import handler as h

        _register_user()
        for facility in ("frogner", "ota", "bergentennisarena"):
            body = {**_valid_pref_body(), "facilityId": facility}
            response = h.lambda_handler(
                _event(
                    "POST",
                    "/users/{userId}/preferences",
                    body=body,
                    path_params={"userId": "alice@example.com"},
                ),
                None,
            )
            assert response["statusCode"] == 201, f"Failed for facility: {facility}"


# ---------------------------------------------------------------------------
# Sport & courtType validation
# ---------------------------------------------------------------------------


class TestSportAndCourtType:
    def test_default_sport_is_tennis(self, dynamo):
        import handler as h

        _register_user()
        body = _valid_pref_body()  # no sport field
        response = h.lambda_handler(
            _event(
                "POST",
                "/users/{userId}/preferences",
                body=body,
                path_params={"userId": "alice@example.com"},
            ),
            None,
        )
        assert response["statusCode"] == 201
        data = _body(response)["data"]
        assert data["sport"] == "tennis"
        assert "courtType" not in data

    def test_explicit_tennis_sport_accepted(self, dynamo):
        import handler as h

        _register_user()
        body = {**_valid_pref_body(), "sport": "tennis"}
        response = h.lambda_handler(
            _event(
                "POST",
                "/users/{userId}/preferences",
                body=body,
                path_params={"userId": "alice@example.com"},
            ),
            None,
        )
        assert response["statusCode"] == 201
        assert _body(response)["data"]["sport"] == "tennis"

    def test_padel_at_ota_accepted(self, dynamo):
        import handler as h

        _register_user()
        body = {**_valid_pref_body(), "facilityId": "ota", "sport": "padel"}
        response = h.lambda_handler(
            _event(
                "POST",
                "/users/{userId}/preferences",
                body=body,
                path_params={"userId": "alice@example.com"},
            ),
            None,
        )
        assert response["statusCode"] == 201
        data = _body(response)["data"]
        assert data["sport"] == "padel"
        assert data["facilityId"] == "ota"

    def test_padel_at_frogner_rejected(self, dynamo):
        """Frogner only supports tennis, so padel should be rejected."""
        import handler as h

        _register_user()
        body = {**_valid_pref_body(), "facilityId": "frogner", "sport": "padel"}
        response = h.lambda_handler(
            _event(
                "POST",
                "/users/{userId}/preferences",
                body=body,
                path_params={"userId": "alice@example.com"},
            ),
            None,
        )
        assert response["statusCode"] == 400
        assert "does not support sport" in _body(response)["error"]

    def test_invalid_sport_rejected(self, dynamo):
        import handler as h

        _register_user()
        body = {**_valid_pref_body(), "sport": "golf"}
        response = h.lambda_handler(
            _event(
                "POST",
                "/users/{userId}/preferences",
                body=body,
                path_params={"userId": "alice@example.com"},
            ),
            None,
        )
        assert response["statusCode"] == 400
        assert "sport" in _body(response)["error"]

    def test_court_type_accepted_for_padel(self, dynamo):
        import handler as h

        _register_user()
        body = {
            **_valid_pref_body(),
            "facilityId": "ota",
            "sport": "padel",
            "courtType": "double",
        }
        response = h.lambda_handler(
            _event(
                "POST",
                "/users/{userId}/preferences",
                body=body,
                path_params={"userId": "alice@example.com"},
            ),
            None,
        )
        assert response["statusCode"] == 201
        data = _body(response)["data"]
        assert data["courtType"] == "double"
        assert data["sport"] == "padel"

    def test_court_type_single_accepted_for_padel(self, dynamo):
        import handler as h

        _register_user()
        body = {
            **_valid_pref_body(),
            "facilityId": "ota",
            "sport": "padel",
            "courtType": "single",
        }
        response = h.lambda_handler(
            _event(
                "POST",
                "/users/{userId}/preferences",
                body=body,
                path_params={"userId": "alice@example.com"},
            ),
            None,
        )
        assert response["statusCode"] == 201
        assert _body(response)["data"]["courtType"] == "single"

    def test_court_type_rejected_for_tennis(self, dynamo):
        """courtType is only valid for padel."""
        import handler as h

        _register_user()
        body = {**_valid_pref_body(), "sport": "tennis", "courtType": "double"}
        response = h.lambda_handler(
            _event(
                "POST",
                "/users/{userId}/preferences",
                body=body,
                path_params={"userId": "alice@example.com"},
            ),
            None,
        )
        assert response["statusCode"] == 400
        assert "courtType" in _body(response)["error"]

    def test_invalid_court_type_rejected(self, dynamo):
        import handler as h

        _register_user()
        body = {
            **_valid_pref_body(),
            "facilityId": "ota",
            "sport": "padel",
            "courtType": "triple",
        }
        response = h.lambda_handler(
            _event(
                "POST",
                "/users/{userId}/preferences",
                body=body,
                path_params={"userId": "alice@example.com"},
            ),
            None,
        )
        assert response["statusCode"] == 400
        assert "courtType" in _body(response)["error"]

    def test_padel_without_court_type_accepted(self, dynamo):
        """Omitting courtType for padel means 'any court type'."""
        import handler as h

        _register_user()
        body = {**_valid_pref_body(), "facilityId": "ota", "sport": "padel"}
        response = h.lambda_handler(
            _event(
                "POST",
                "/users/{userId}/preferences",
                body=body,
                path_params={"userId": "alice@example.com"},
            ),
            None,
        )
        assert response["statusCode"] == 201
        data = _body(response)["data"]
        assert data["sport"] == "padel"
        assert "courtType" not in data

    def test_update_with_sport_and_court_type(self, dynamo):
        """PUT should also store sport and courtType."""
        import handler as h

        _register_user()
        # Create with defaults
        create_resp = h.lambda_handler(
            _event(
                "POST",
                "/users/{userId}/preferences",
                body=_valid_pref_body(),
                path_params={"userId": "alice@example.com"},
            ),
            None,
        )
        pref_id = _body(create_resp)["data"]["preferenceId"]

        # Update to padel with courtType
        updated_body = {
            **_valid_pref_body(),
            "facilityId": "ota",
            "sport": "padel",
            "courtType": "single",
        }
        response = h.lambda_handler(
            _event(
                "PUT",
                "/users/{userId}/preferences/{preferenceId}",
                body=updated_body,
                path_params={
                    "userId": "alice@example.com",
                    "preferenceId": pref_id,
                },
            ),
            None,
        )
        assert response["statusCode"] == 200
        data = _body(response)["data"]
        assert data["sport"] == "padel"
        assert data["courtType"] == "single"


# ---------------------------------------------------------------------------
# PUT /users/{userId}/preferences/{preferenceId}
# ---------------------------------------------------------------------------


class TestUpdatePreference:
    def _create_pref(self, user_id="alice@example.com"):
        import handler as h

        _register_user(user_id)
        response = h.lambda_handler(
            _event(
                "POST",
                "/users/{userId}/preferences",
                body=_valid_pref_body(),
                path_params={"userId": user_id},
            ),
            None,
        )
        return _body(response)["data"]["preferenceId"]

    def test_updates_preference_successfully(self, dynamo):
        import handler as h

        pref_id = self._create_pref()
        updated_body = {
            "facilityId": "ota",
            "dates": ["wednesday"],
            "timeFrom": "09:00",
            "timeTo": "11:00",
        }
        response = h.lambda_handler(
            _event(
                "PUT",
                "/users/{userId}/preferences/{preferenceId}",
                body=updated_body,
                path_params={
                    "userId": "alice@example.com",
                    "preferenceId": pref_id,
                },
            ),
            None,
        )
        assert response["statusCode"] == 200
        data = _body(response)["data"]
        assert data["facilityId"] == "ota"
        assert data["dates"] == ["wednesday"]
        assert data["timeFrom"] == "09:00"
        assert data["timeTo"] == "11:00"

    def test_preserves_created_at(self, dynamo):
        import handler as h

        pref_id = self._create_pref()

        # Fetch createdAt from the initial creation
        list_resp = h.lambda_handler(
            _event(
                "GET",
                "/users/{userId}/preferences",
                path_params={"userId": "alice@example.com"},
            ),
            None,
        )
        original_created_at = _body(list_resp)["data"][0]["createdAt"]

        updated_body = {**_valid_pref_body(), "facilityId": "ota"}
        response = h.lambda_handler(
            _event(
                "PUT",
                "/users/{userId}/preferences/{preferenceId}",
                body=updated_body,
                path_params={
                    "userId": "alice@example.com",
                    "preferenceId": pref_id,
                },
            ),
            None,
        )
        assert _body(response)["data"]["createdAt"] == original_created_at

    def test_unknown_user_returns_404(self, dynamo):
        import handler as h

        response = h.lambda_handler(
            _event(
                "PUT",
                "/users/{userId}/preferences/{preferenceId}",
                body=_valid_pref_body(),
                path_params={
                    "userId": "ghost@example.com",
                    "preferenceId": "some-uuid",
                },
            ),
            None,
        )
        assert response["statusCode"] == 404

    def test_unknown_preference_returns_404(self, dynamo):
        import handler as h

        _register_user()
        response = h.lambda_handler(
            _event(
                "PUT",
                "/users/{userId}/preferences/{preferenceId}",
                body=_valid_pref_body(),
                path_params={
                    "userId": "alice@example.com",
                    "preferenceId": "00000000-0000-0000-0000-000000000000",
                },
            ),
            None,
        )
        assert response["statusCode"] == 404

    def test_invalid_body_returns_400(self, dynamo):
        import handler as h

        pref_id = self._create_pref()
        bad_body = {**_valid_pref_body(), "facilityId": "invalid-facility"}
        response = h.lambda_handler(
            _event(
                "PUT",
                "/users/{userId}/preferences/{preferenceId}",
                body=bad_body,
                path_params={
                    "userId": "alice@example.com",
                    "preferenceId": pref_id,
                },
            ),
            None,
        )
        assert response["statusCode"] == 400


# ---------------------------------------------------------------------------
# DELETE /users/{userId}/preferences/{preferenceId}
# ---------------------------------------------------------------------------


class TestDeletePreference:
    def _create_pref(self, user_id="alice@example.com"):
        import handler as h

        _register_user(user_id)
        response = h.lambda_handler(
            _event(
                "POST",
                "/users/{userId}/preferences",
                body=_valid_pref_body(),
                path_params={"userId": user_id},
            ),
            None,
        )
        return _body(response)["data"]["preferenceId"]

    def test_deletes_preference_successfully(self, dynamo):
        import handler as h

        pref_id = self._create_pref()
        response = h.lambda_handler(
            _event(
                "DELETE",
                "/users/{userId}/preferences/{preferenceId}",
                path_params={
                    "userId": "alice@example.com",
                    "preferenceId": pref_id,
                },
            ),
            None,
        )
        assert response["statusCode"] == 200
        assert _body(response)["data"]["deleted"] is True

    def test_preference_gone_after_delete(self, dynamo):
        import handler as h

        pref_id = self._create_pref()
        h.lambda_handler(
            _event(
                "DELETE",
                "/users/{userId}/preferences/{preferenceId}",
                path_params={
                    "userId": "alice@example.com",
                    "preferenceId": pref_id,
                },
            ),
            None,
        )
        list_response = h.lambda_handler(
            _event(
                "GET",
                "/users/{userId}/preferences",
                path_params={"userId": "alice@example.com"},
            ),
            None,
        )
        assert _body(list_response)["data"] == []

    def test_unknown_user_returns_404(self, dynamo):
        import handler as h

        response = h.lambda_handler(
            _event(
                "DELETE",
                "/users/{userId}/preferences/{preferenceId}",
                path_params={
                    "userId": "ghost@example.com",
                    "preferenceId": "some-pref-id",
                },
            ),
            None,
        )
        assert response["statusCode"] == 404

    def test_unknown_preference_returns_404(self, dynamo):
        import handler as h

        _register_user()
        response = h.lambda_handler(
            _event(
                "DELETE",
                "/users/{userId}/preferences/{preferenceId}",
                path_params={
                    "userId": "alice@example.com",
                    "preferenceId": "00000000-0000-0000-0000-000000000000",
                },
            ),
            None,
        )
        assert response["statusCode"] == 404


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------


class TestRouter:
    def test_unknown_route_returns_404(self, dynamo):
        import handler as h

        response = h.lambda_handler(
            {"httpMethod": "PATCH", "resource": "/unknown", "pathParameters": {}},
            None,
        )
        assert response["statusCode"] == 404


# ---------------------------------------------------------------------------
# Harvard preferences tests — PREF-01, PREF-03
# ---------------------------------------------------------------------------


class TestCreatePreferenceHarvard:
    """Tests verifying PREF-01 (harvard in VALID_FACILITY_IDS) and
    PREF-03 (preferences API accepts harvard+tennis)."""

    def test_harvard_in_valid_facility_ids(self):
        """PREF-01: VALID_FACILITY_IDS must include 'harvard'."""
        import importlib
        import handler as h

        assert "harvard" in h.VALID_FACILITY_IDS

    def test_create_preference_harvard_tennis_accepted(self, dynamo):
        """PREF-03: POST preference with facilityId=harvard sport=tennis returns 201."""
        import handler as h

        # Register user
        h.lambda_handler(
            _event("POST", "/users", {"userId": "test@harvard.edu", "name": "Test User"}),
            None,
        )

        # Create harvard+tennis preference
        resp = h.lambda_handler(
            _event(
                "POST",
                "/users/{userId}/preferences",
                body={
                    "facilityId": "harvard",
                    "sport": "tennis",
                    "dates": ["monday", "wednesday"],
                    "timeFrom": "09:00",
                    "timeTo": "11:00",
                },
                path_params={"userId": "test@harvard.edu"},
            ),
            None,
        )
        assert resp["statusCode"] == 201
        data = _body(resp)["data"]
        assert data["facilityId"] == "harvard"
        assert data["sport"] == "tennis"

    def test_create_preference_harvard_padel_rejected(self, dynamo):
        """Harvard only supports tennis — padel preference must return 400."""
        import handler as h

        h.lambda_handler(
            _event("POST", "/users", {"userId": "test2@harvard.edu", "name": "Test User 2"}),
            None,
        )

        resp = h.lambda_handler(
            _event(
                "POST",
                "/users/{userId}/preferences",
                body={
                    "facilityId": "harvard",
                    "sport": "padel",
                    "dates": ["monday"],
                    "timeFrom": "09:00",
                    "timeTo": "11:00",
                },
                path_params={"userId": "test2@harvard.edu"},
            ),
            None,
        )
        assert resp["statusCode"] == 400
        error = _body(resp)["error"]
        assert "padel" in error.lower() or "harvard" in error.lower()

    def test_create_preference_harvard_court_type_rejected(self, dynamo):
        """courtType is only valid for padel — tennis + courtType must return 400."""
        import handler as h

        h.lambda_handler(
            _event("POST", "/users", {"userId": "test3@harvard.edu", "name": "Test User 3"}),
            None,
        )

        resp = h.lambda_handler(
            _event(
                "POST",
                "/users/{userId}/preferences",
                body={
                    "facilityId": "harvard",
                    "sport": "tennis",
                    "courtType": "double",
                    "dates": ["monday"],
                    "timeFrom": "09:00",
                    "timeTo": "11:00",
                },
                path_params={"userId": "test3@harvard.edu"},
            ),
            None,
        )
        assert resp["statusCode"] == 400


# ---------------------------------------------------------------------------
# Golf preference validation
# ---------------------------------------------------------------------------


class TestGolfPreferences:
    def test_create_golf_preference_valid(self, dynamo):
        import handler as h

        _register_user("golfer@example.com", "Golfer")
        resp = h.lambda_handler(
            _event(
                "POST",
                "/users/{userId}/preferences",
                body={
                    "facilityId": "onsoy",
                    "sport": "golf",
                    "dates": ["saturday"],
                    "timeFrom": "07:00",
                    "timeTo": "12:00",
                    "minSpots": 2,
                },
                path_params={"userId": "golfer@example.com"},
            ),
            None,
        )
        assert resp["statusCode"] == 201
        data = _body(resp)["data"]
        assert data["sport"] == "golf"
        assert data["minSpots"] == 2

    def test_golf_preference_without_minSpots(self, dynamo):
        import handler as h

        _register_user("golfer2@example.com", "Golfer2")
        resp = h.lambda_handler(
            _event(
                "POST",
                "/users/{userId}/preferences",
                body={
                    "facilityId": "onsoy",
                    "sport": "golf",
                    "dates": ["sunday"],
                    "timeFrom": "08:00",
                    "timeTo": "14:00",
                },
                path_params={"userId": "golfer2@example.com"},
            ),
            None,
        )
        assert resp["statusCode"] == 201
        data = _body(resp)["data"]
        assert "minSpots" not in data

    def test_minSpots_rejected_for_tennis(self, dynamo):
        import handler as h

        _register_user("tennis@example.com", "Tennis")
        resp = h.lambda_handler(
            _event(
                "POST",
                "/users/{userId}/preferences",
                body={
                    "facilityId": "ota",
                    "sport": "tennis",
                    "dates": ["monday"],
                    "timeFrom": "17:00",
                    "timeTo": "20:00",
                    "minSpots": 2,
                },
                path_params={"userId": "tennis@example.com"},
            ),
            None,
        )
        assert resp["statusCode"] == 400
        assert "minSpots is only valid when sport is 'golf'" in _body(resp)["error"]

    def test_minSpots_invalid_value_zero(self, dynamo):
        import handler as h

        _register_user("golfer3@example.com", "Golfer3")
        resp = h.lambda_handler(
            _event(
                "POST",
                "/users/{userId}/preferences",
                body={
                    "facilityId": "onsoy",
                    "sport": "golf",
                    "dates": ["friday"],
                    "timeFrom": "09:00",
                    "timeTo": "11:00",
                    "minSpots": 0,
                },
                path_params={"userId": "golfer3@example.com"},
            ),
            None,
        )
        assert resp["statusCode"] == 400
        assert "minSpots must be an integer between 1 and 4" in _body(resp)["error"]

    def test_minSpots_invalid_value_five(self, dynamo):
        import handler as h

        _register_user("golfer4@example.com", "Golfer4")
        resp = h.lambda_handler(
            _event(
                "POST",
                "/users/{userId}/preferences",
                body={
                    "facilityId": "onsoy",
                    "sport": "golf",
                    "dates": ["friday"],
                    "timeFrom": "09:00",
                    "timeTo": "11:00",
                    "minSpots": 5,
                },
                path_params={"userId": "golfer4@example.com"},
            ),
            None,
        )
        assert resp["statusCode"] == 400
        assert "minSpots must be an integer between 1 and 4" in _body(resp)["error"]

    def test_golf_invalid_facility(self, dynamo):
        import handler as h

        _register_user("golfer5@example.com", "Golfer5")
        resp = h.lambda_handler(
            _event(
                "POST",
                "/users/{userId}/preferences",
                body={
                    "facilityId": "ota",
                    "sport": "golf",
                    "dates": ["monday"],
                    "timeFrom": "08:00",
                    "timeTo": "12:00",
                },
                path_params={"userId": "golfer5@example.com"},
            ),
            None,
        )
        assert resp["statusCode"] == 400
        assert "does not support sport" in _body(resp)["error"]
