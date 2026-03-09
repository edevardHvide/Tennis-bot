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
        "dates": ["2026-06-01", "2026-06-07"],
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
        assert data["dates"] == ["2026-06-01", "2026-06-07"]
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

    def test_invalid_date_format_returns_400(self, dynamo):
        import handler as h

        _register_user()
        body = {**_valid_pref_body(), "dates": ["06/01/2026"]}
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
            "dates": ["2026-07-01"],
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
        assert data["dates"] == ["2026-07-01"]
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
