"""
Unit tests for the Highscores Lambda handler.

Uses moto to mock DynamoDB — no real AWS calls are made.

Run with:
    pip install pytest moto[dynamodb] boto3
    pytest tests/test_highscores.py -v
"""

import importlib
import json
import os
import sys
from datetime import datetime, timezone, timedelta

import boto3
import pytest
from moto import mock_aws

# ---------------------------------------------------------------------------
# Ensure the handler module can be imported regardless of working directory
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

HANDLER_DIR = os.path.join(os.path.dirname(__file__), "..", "lambdas", "highscores")
if HANDLER_DIR not in sys.path:
    sys.path.insert(0, HANDLER_DIR)


# ---------------------------------------------------------------------------
# Constants shared across tests
# ---------------------------------------------------------------------------

REGION = "eu-north-1"
USERS_TABLE = "tennis-users"
HIGHSCORES_TABLE = "tennis-highscores"


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
    monkeypatch.setenv("HIGHSCORES_TABLE", HIGHSCORES_TABLE)


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
            TableName=HIGHSCORES_TABLE,
            AttributeDefinitions=[
                {"AttributeName": "leaderboard", "AttributeType": "S"},
                {"AttributeName": "scoreId", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "leaderboard", "KeyType": "HASH"},
                {"AttributeName": "scoreId", "KeyType": "RANGE"},
            ],
            BillingMode="PAY_PER_REQUEST",
        )

        # Remove cached handler so we import from the correct Lambda directory
        sys.modules.pop("handler", None)
        # Ensure highscores handler dir is first in path
        if sys.path[0] != HANDLER_DIR:
            sys.path.insert(0, HANDLER_DIR)

        import handler as h

        h._dynamodb_resource = None

        yield boto3.resource("dynamodb", region_name=REGION)

        h._dynamodb_resource = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _event(method, resource, body=None):
    return {
        "httpMethod": method,
        "resource": resource,
        "pathParameters": {},
        "body": json.dumps(body) if body is not None else None,
    }


def _body(response):
    return json.loads(response["body"])


def _seed_user(dynamo, user_id="alice@example.com", name="Alice"):
    table = dynamo.Table(USERS_TABLE)
    table.put_item(Item={
        "userId": user_id,
        "name": name,
        "createdAt": datetime.now(timezone.utc).isoformat(),
    })


def _valid_score():
    return {
        "userId": "alice@example.com",
        "playerName": "Alice",
        "score": 42,
    }


# ---------------------------------------------------------------------------
# POST /highscores
# ---------------------------------------------------------------------------


class TestSubmitScore:
    def test_submits_score_successfully(self, dynamo):
        import handler as h

        _seed_user(dynamo)
        response = h.lambda_handler(_event("POST", "/highscores", _valid_score()), None)
        assert response["statusCode"] == 201
        data = _body(response)["data"]
        assert "scoreId" in data
        assert data["message"] == "Score submitted successfully"

    def test_stores_score_in_dynamodb(self, dynamo):
        import handler as h

        _seed_user(dynamo)
        response = h.lambda_handler(_event("POST", "/highscores", _valid_score()), None)
        score_id = _body(response)["data"]["scoreId"]

        table = dynamo.Table(HIGHSCORES_TABLE)
        item = table.get_item(Key={"leaderboard": "GLOBAL", "scoreId": score_id})["Item"]
        assert int(item["score"]) == 42
        assert item["userId"] == "alice@example.com"
        assert item["playerName"] == "Alice"

    def test_missing_user_id_returns_400(self, dynamo):
        import handler as h

        body = {**_valid_score(), "userId": ""}
        response = h.lambda_handler(_event("POST", "/highscores", body), None)
        assert response["statusCode"] == 400
        assert "userId" in _body(response)["error"]

    def test_missing_player_name_returns_400(self, dynamo):
        import handler as h

        _seed_user(dynamo)
        body = {**_valid_score(), "playerName": ""}
        response = h.lambda_handler(_event("POST", "/highscores", body), None)
        assert response["statusCode"] == 400
        assert "playerName" in _body(response)["error"]

    def test_missing_score_returns_400(self, dynamo):
        import handler as h

        _seed_user(dynamo)
        body = {"userId": "alice@example.com", "playerName": "Alice"}
        response = h.lambda_handler(_event("POST", "/highscores", body), None)
        assert response["statusCode"] == 400
        assert "score" in _body(response)["error"]

    def test_unknown_user_returns_404(self, dynamo):
        import handler as h

        response = h.lambda_handler(_event("POST", "/highscores", _valid_score()), None)
        assert response["statusCode"] == 404

    def test_score_capped_at_999(self, dynamo):
        import handler as h

        _seed_user(dynamo)
        body = {**_valid_score(), "score": 5000}
        response = h.lambda_handler(_event("POST", "/highscores", body), None)
        assert response["statusCode"] == 201
        score_id = _body(response)["data"]["scoreId"]

        table = dynamo.Table(HIGHSCORES_TABLE)
        item = table.get_item(Key={"leaderboard": "GLOBAL", "scoreId": score_id})["Item"]
        assert int(item["score"]) == 999

    def test_rate_limited_returns_429(self, dynamo):
        import handler as h

        _seed_user(dynamo)
        # First request should succeed
        resp1 = h.lambda_handler(_event("POST", "/highscores", _valid_score()), None)
        assert resp1["statusCode"] == 201

        # Second request within 10 seconds should be rate limited
        resp2 = h.lambda_handler(_event("POST", "/highscores", _valid_score()), None)
        assert resp2["statusCode"] == 429
        assert "wait" in _body(resp2)["error"].lower()

    def test_invalid_json_body_returns_400(self, dynamo):
        import handler as h

        event = {
            "httpMethod": "POST",
            "resource": "/highscores",
            "pathParameters": {},
            "body": "not-json{{{",
        }
        response = h.lambda_handler(event, None)
        assert response["statusCode"] == 400

    def test_cors_header_present(self, dynamo):
        import handler as h

        _seed_user(dynamo)
        response = h.lambda_handler(_event("POST", "/highscores", _valid_score()), None)
        assert response["headers"]["Access-Control-Allow-Origin"] == "*"


# ---------------------------------------------------------------------------
# GET /highscores
# ---------------------------------------------------------------------------


class TestGetHighscores:
    def test_returns_empty_list_when_no_scores(self, dynamo):
        import handler as h

        response = h.lambda_handler(_event("GET", "/highscores"), None)
        assert response["statusCode"] == 200
        data = _body(response)["data"]
        assert data == []

    def test_returns_scores_sorted_descending(self, dynamo):
        import handler as h

        _seed_user(dynamo)
        _seed_user(dynamo, user_id="bob@example.com", name="Bob")

        # Submit multiple scores
        h.lambda_handler(_event("POST", "/highscores", {
            "userId": "alice@example.com", "playerName": "Alice", "score": 10,
        }), None)
        h.lambda_handler(_event("POST", "/highscores", {
            "userId": "bob@example.com", "playerName": "Bob", "score": 50,
        }), None)

        response = h.lambda_handler(_event("GET", "/highscores"), None)
        assert response["statusCode"] == 200
        data = _body(response)["data"]
        assert len(data) == 2
        assert data[0]["score"] == 50
        assert data[0]["playerName"] == "Bob"
        assert data[1]["score"] == 10
        assert data[1]["playerName"] == "Alice"

    def test_cors_header_present_on_get(self, dynamo):
        import handler as h

        response = h.lambda_handler(_event("GET", "/highscores"), None)
        assert response["headers"]["Access-Control-Allow-Origin"] == "*"


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

    def test_options_returns_200(self, dynamo):
        import handler as h

        response = h.lambda_handler(
            {"httpMethod": "OPTIONS", "resource": "/highscores", "pathParameters": {}},
            None,
        )
        assert response["statusCode"] == 200

    def test_delete_method_returns_404(self, dynamo):
        import handler as h

        response = h.lambda_handler(
            {"httpMethod": "DELETE", "resource": "/highscores", "pathParameters": {}},
            None,
        )
        assert response["statusCode"] == 404
