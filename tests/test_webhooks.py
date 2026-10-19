import asyncio
import hashlib
import hmac
from concurrent.futures import ThreadPoolExecutor
from itertools import product

import pytest
from fastapi.testclient import TestClient

from app.backend.main import create_app
from app.crud import PaymentCrud

STATES = ["pending", "succeeded", "failed", "refunded"]
ALLOWED = {("pending", "succeeded"), ("pending", "failed"), ("succeeded", "refunded")}


def reach_state(client, payment_id, state):
    steps = {
        "pending": [],
        "succeeded": ["succeeded"],
        "failed": ["failed"],
        "refunded": ["succeeded", "refunded"],
    }[state]
    for target in steps:
        response = client.post("/webhooks/bank", json={"payment_id": payment_id, "status": target})
        assert response.status_code == 200
        assert response.json() == {"result": "ok"}


@pytest.mark.parametrize("source,target", list(product(STATES, repeat=2)))
def test_every_status_transition(client, payload, source, target):
    payment = client.post("/payments", json=payload).json()
    reach_state(client, payment["id"], source)
    before = client.get(f"/payments/{payment['id']}").json()
    response = client.post("/webhooks/bank", json={"payment_id": payment["id"], "status": target})
    after = client.get(f"/payments/{payment['id']}").json()
    if (source, target) in ALLOWED:
        assert response.status_code == 200
        assert response.json() == {"result": "ok"}
        assert after == {**before, "status": target}
    else:
        assert response.status_code == 409
        assert response.json() == {"error": "invalid_transition"}
        assert after == before


@pytest.mark.parametrize("state", STATES)
def test_webhook_missing_payment(client, state):
    assert (
        client.post("/webhooks/bank", json={"payment_id": 999, "status": state}).status_code == 404
    )


@pytest.mark.parametrize(
    "body", [{"payment_id": 1, "status": "unknown"}, {"payment_id": True, "status": "failed"}]
)
def test_webhook_validation(client, body):
    response = client.post("/webhooks/bank", json=body)
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)


@pytest.mark.parametrize("targets", [["succeeded", "failed"], ["succeeded", "succeeded"]])
def test_concurrent_webhooks(client, payload, targets, monkeypatch):
    payment = client.post("/payments", json=payload).json()
    barrier = asyncio.Barrier(2)
    original_transition = PaymentCrud.transition

    async def synchronized_transition(self, *args, **kwargs):
        await asyncio.wait_for(barrier.wait(), timeout=10)
        return await original_transition(self, *args, **kwargs)

    def send(target):
        response = client.post(
            "/webhooks/bank", json={"payment_id": payment["id"], "status": target}
        )
        return target, response

    monkeypatch.setattr(PaymentCrud, "transition", synchronized_transition)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(send, targets))
    assert sorted(r.status_code for _, r in responses) == [200, 409]
    winner = next(target for target, r in responses if r.status_code == 200)
    loser = next(r for _, r in responses if r.status_code == 409)
    assert loser.json() == {"error": "invalid_transition"}
    assert client.get(f"/payments/{payment['id']}").json()["status"] == winner


def test_hmac_uses_exact_raw_body(db_url, payload):
    secret = "test-secret"
    with TestClient(create_app(db_url, webhook_secret=secret)) as client:
        payment = client.post("/payments", json=payload).json()
        raw = f'{{ "payment_id": {payment["id"]}, "status": "succeeded" }}'.encode()
        signature = hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
        headers = {"Content-Type": "application/json"}
        for invalid in (None, "bad", "0" * 64):
            attempt_headers = headers if invalid is None else {**headers, "X-Signature": invalid}
            response = client.post("/webhooks/bank", content=raw, headers=attempt_headers)
            assert response.status_code == 401
            assert client.get(f"/payments/{payment['id']}").json()["status"] == "pending"
        changed = raw.replace(b"succeeded", b"failed")
        response = client.post(
            "/webhooks/bank", content=changed, headers={**headers, "X-Signature": signature}
        )
        assert response.status_code == 401
        response = client.post(
            "/webhooks/bank", content=raw, headers={**headers, "X-Signature": signature}
        )
        assert response.status_code == 200
        assert response.json() == {"result": "ok"}
        assert client.get(f"/payments/{payment['id']}").json()["status"] == "succeeded"


def test_secret_from_environment(monkeypatch, db_url, payload):
    monkeypatch.setenv("WEBHOOK_SECRET", "from-environment")
    with TestClient(create_app(db_url)) as client:
        payment = client.post("/payments", json=payload).json()
        response = client.post(
            "/webhooks/bank", json={"payment_id": payment["id"], "status": "succeeded"}
        )
        assert response.status_code == 401
