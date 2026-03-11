"""
Unit tests for the Feedback Lambda handler.

Uses moto to mock DynamoDB — no real AWS calls are made.
GitHub API calls are mocked with unittest.mock.

Run with:
    pip install pytest moto[dynamodb] boto3
    pytest tests/test_feedback.py -v
"""

import importlib
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

import boto3
import pytest
from moto import mock_aws

# ---------------------------------------------------------------------------
# Ensure the handler module can be imported regardless of working directory
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

HANDLER_DIR = os.path.join(os.path.dirname(__file__), "..", "lambdas", "feedback")
if HANDLER_DIR not in sys.path:
    sys.path.insert(0, HANDLER_DIR)


# ---------------------------------------------------------------------------
# Constants shared across tests
# ---------------------------------------------------------------------------

REGION = "eu-north-1"
USERS_TABLE = "tennis-users"
FEEDBACK_TABLE = "tennis-feedback"


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
    monkeypatch.setenv("FEEDBACK_TABLE", FEEDBACK_TABLE)
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_test_token_123")
    monkeypatch.setenv("GITHUB_REPO", "edevardHvide/Tennis-bot")


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
            TableName=FEEDBACK_TABLE,
            AttributeDefinitions=[{"AttributeName": "feedbackId", "AttributeType": "S"}],
            KeySchema=[{"AttributeName": "feedbackId", "KeyType": "HASH"}],
            BillingMode="PAY_PER_REQUEST",
        )

        # Remove cached handler so we import from the correct Lambda directory
        sys.modules.pop("handler", None)
        # Ensure feedback handler dir is first in path
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


def _valid_feedback():
    return {
        "userId": "alice@example.com",
        "title": "Add dark mode",
        "description": "It would be great to have a dark mode option for the dashboard.",
    }


def _mock_github_success():
    mock_resp = MagicMock()
    mock_resp.status_code = 201
    mock_resp.json.return_value = {"html_url": "https://github.com/edevardHvide/Tennis-bot/issues/42"}
    return mock_resp


def _mock_github_failure():
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"
    return mock_resp


# ---------------------------------------------------------------------------
# POST /feedback
# ---------------------------------------------------------------------------


class TestCreateFeedback:
    @patch("handler.http_requests.post", return_value=_mock_github_success())
    def test_creates_feedback_successfully(self, mock_post, dynamo):
        import handler as h

        _seed_user(dynamo)
        response = h.lambda_handler(_event("POST", "/feedback", _valid_feedback()), None)
        assert response["statusCode"] == 201
        data = _body(response)["data"]
        assert "feedbackId" in data
        assert data["message"] == "Feature request submitted successfully"

    @patch("handler.http_requests.post", return_value=_mock_github_success())
    def test_returns_github_issue_url(self, mock_post, dynamo):
        import handler as h

        _seed_user(dynamo)
        response = h.lambda_handler(_event("POST", "/feedback", _valid_feedback()), None)
        data = _body(response)["data"]
        assert data["githubIssueUrl"] == "https://github.com/edevardHvide/Tennis-bot/issues/42"

    @patch("handler.http_requests.post", return_value=_mock_github_success())
    def test_stores_feedback_in_dynamodb(self, mock_post, dynamo):
        import handler as h

        _seed_user(dynamo)
        response = h.lambda_handler(_event("POST", "/feedback", _valid_feedback()), None)
        feedback_id = _body(response)["data"]["feedbackId"]

        table = dynamo.Table(FEEDBACK_TABLE)
        item = table.get_item(Key={"feedbackId": feedback_id})["Item"]
        assert item["title"] == "Add dark mode"
        assert item["userId"] == "alice@example.com"

    @patch("handler.http_requests.post", return_value=_mock_github_success())
    def test_github_api_called_with_correct_payload(self, mock_post, dynamo):
        import handler as h

        _seed_user(dynamo)
        h.lambda_handler(_event("POST", "/feedback", _valid_feedback()), None)

        mock_post.assert_called_once()
        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert payload["title"] == "Add dark mode"
        assert "feature-request" in payload["labels"]
        assert "alice@example.com" in payload["body"]

    def test_missing_title_returns_400(self, dynamo):
        import handler as h

        _seed_user(dynamo)
        body = {**_valid_feedback(), "title": ""}
        response = h.lambda_handler(_event("POST", "/feedback", body), None)
        assert response["statusCode"] == 400
        assert "title" in _body(response)["error"]

    def test_missing_description_returns_400(self, dynamo):
        import handler as h

        _seed_user(dynamo)
        body = {**_valid_feedback(), "description": ""}
        response = h.lambda_handler(_event("POST", "/feedback", body), None)
        assert response["statusCode"] == 400
        assert "description" in _body(response)["error"]

    def test_missing_user_id_returns_400(self, dynamo):
        import handler as h

        body = {**_valid_feedback(), "userId": ""}
        response = h.lambda_handler(_event("POST", "/feedback", body), None)
        assert response["statusCode"] == 400

    def test_title_too_long_returns_400(self, dynamo):
        import handler as h

        _seed_user(dynamo)
        body = {**_valid_feedback(), "title": "x" * 201}
        response = h.lambda_handler(_event("POST", "/feedback", body), None)
        assert response["statusCode"] == 400

    def test_description_too_long_returns_400(self, dynamo):
        import handler as h

        _seed_user(dynamo)
        body = {**_valid_feedback(), "description": "x" * 2001}
        response = h.lambda_handler(_event("POST", "/feedback", body), None)
        assert response["statusCode"] == 400

    def test_unknown_user_returns_404(self, dynamo):
        import handler as h

        response = h.lambda_handler(_event("POST", "/feedback", _valid_feedback()), None)
        assert response["statusCode"] == 404

    @patch("handler.http_requests.post", return_value=_mock_github_success())
    def test_rate_limited_returns_429(self, mock_post, dynamo):
        import handler as h

        _seed_user(dynamo)
        # First request should succeed
        resp1 = h.lambda_handler(_event("POST", "/feedback", _valid_feedback()), None)
        assert resp1["statusCode"] == 201

        # Second request within 5 minutes should be rate limited
        resp2 = h.lambda_handler(_event("POST", "/feedback", _valid_feedback()), None)
        assert resp2["statusCode"] == 429
        assert "wait" in _body(resp2)["error"].lower()

    @patch("handler.http_requests.post", return_value=_mock_github_failure())
    def test_github_api_failure_still_returns_success(self, mock_post, dynamo):
        import handler as h

        _seed_user(dynamo)
        response = h.lambda_handler(_event("POST", "/feedback", _valid_feedback()), None)
        assert response["statusCode"] == 201
        data = _body(response)["data"]
        assert data["githubIssueUrl"] is None

    @patch("handler.http_requests.post", return_value=_mock_github_success())
    def test_cors_header_present(self, mock_post, dynamo):
        import handler as h

        _seed_user(dynamo)
        response = h.lambda_handler(_event("POST", "/feedback", _valid_feedback()), None)
        assert response["headers"]["Access-Control-Allow-Origin"] == "*"

    def test_invalid_json_body_returns_400(self, dynamo):
        import handler as h

        event = {
            "httpMethod": "POST",
            "resource": "/feedback",
            "pathParameters": {},
            "body": "not-json{{{",
        }
        response = h.lambda_handler(event, None)
        assert response["statusCode"] == 400


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

    def test_get_method_returns_404(self, dynamo):
        import handler as h

        response = h.lambda_handler(
            {"httpMethod": "GET", "resource": "/feedback", "pathParameters": {}},
            None,
        )
        assert response["statusCode"] == 404

    def test_options_returns_200(self, dynamo):
        import handler as h

        response = h.lambda_handler(
            {"httpMethod": "OPTIONS", "resource": "/feedback", "pathParameters": {}},
            None,
        )
        assert response["statusCode"] == 200
