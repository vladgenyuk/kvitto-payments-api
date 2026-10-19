import json

import pytest

from app.const import MAX_SQLITE_ID


@pytest.mark.parametrize(
    ("token", "expected_input"),
    [
        ("1e9999", "inf"),
        ("-1e9999", "-inf"),
        ("NaN", "nan"),
        ("Infinity", "inf"),
        ("-Infinity", "-inf"),
    ],
)
@pytest.mark.parametrize("field", ["tariff_id", "installment_months", "payment_id"])
def test_nonfinite_number_returns_validation_error(client, payload, token, expected_input, field):
    if field == "payment_id":
        path = "/webhooks/bank"
        body = {"payment_id": "NUMBER", "status": "succeeded"}
    else:
        path = "/payments"
        body = {**payload, "method": "installment", "installment_months": 3, field: "NUMBER"}
    raw = json.dumps(body).replace('"NUMBER"', token)

    response = client.post(path, content=raw, headers={"Content-Type": "application/json"})

    assert response.status_code == 422
    error = response.json()["detail"][0]
    assert error["type"] == "int_type"
    assert error["loc"] == ["body", field]
    assert error["input"] == expected_input
    assert client.get("/payments").json() == []


def test_finite_number_is_preserved_in_validation_error(client, payload):
    response = client.post("/payments", json={**payload, "tariff_id": 3.5})
    assert response.status_code == 422
    assert response.json()["detail"][0]["input"] == 3.5
    assert client.get("/payments").json() == []


@pytest.mark.parametrize("value", [2**63, 2**100])
@pytest.mark.parametrize("endpoint", ["payment_get", "payment_create", "webhook"])
def test_oversized_id_is_validation_error_not_server_error(client, payload, value, endpoint):
    if endpoint == "payment_get":
        response = client.get(f"/payments/{value}")
        location = ["path", "payment_id"]
    elif endpoint == "payment_create":
        response = client.post("/payments", json={**payload, "tariff_id": value})
        location = ["body", "tariff_id"]
    else:
        response = client.post("/webhooks/bank", json={"payment_id": value, "status": "succeeded"})
        location = ["body", "payment_id"]
    assert response.status_code == 422
    error = response.json()["detail"][0]
    assert error["loc"] == location
    assert error["type"] == "less_than_equal"
    assert client.get("/payments").json() == []


def test_largest_valid_ids_are_looked_up_normally(client, payload):
    assert client.get(f"/payments/{MAX_SQLITE_ID}").status_code == 404
    assert (
        client.post(
            "/webhooks/bank", json={"payment_id": MAX_SQLITE_ID, "status": "failed"}
        ).status_code
        == 404
    )
    response = client.post("/payments", json={**payload, "tariff_id": MAX_SQLITE_ID})
    assert response.status_code == 422
    assert response.json()["detail"][0]["msg"] == "Value error, unknown tariff"


@pytest.mark.parametrize("value", [0, -1, "not-an-integer"])
def test_invalid_path_ids(client, value):
    response = client.get(f"/payments/{value}")
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["path", "payment_id"]


@pytest.mark.parametrize("field", ["tariff_id", "email", "method"])
def test_missing_required_field_does_not_create_payment(client, payload, field):
    response = client.post(
        "/payments", json={key: value for key, value in payload.items() if key != field}
    )
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body", field]
    assert client.get("/payments").json() == []


def test_openapi_describes_idempotent_replay_and_conflict(client):
    schema = client.get("/openapi.json").json()
    responses = schema["paths"]["/payments"]["post"]["responses"]
    assert (
        responses["200"]["content"]["application/json"]["schema"]
        == responses["201"]["content"]["application/json"]["schema"]
    )
    responses = schema["paths"]["/webhooks/bank"]["post"]["responses"]
    assert {"200", "401", "404", "409", "422"} <= responses.keys()
    assert responses["409"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/TransitionError"
    )
