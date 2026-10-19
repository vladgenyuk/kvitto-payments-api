import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.backend.main import create_app


def test_application_instances_have_independent_storage_and_webhook_secrets(tmp_path, payload):
    first = create_app(
        f"sqlite+aiosqlite:///{tmp_path / 'first.db'}", webhook_secret="first-secret"
    )
    second = create_app(f"sqlite:///{tmp_path / 'second.db'}", webhook_secret="")
    headers = {"Idempotency-Key": "same-key-in-different-apps"}
    with TestClient(first) as a, TestClient(second) as b:
        response_a = a.post("/payments", json=payload, headers=headers)
        response_b = b.post("/payments", json={**payload, "tariff_id": 1}, headers=headers)
        assert response_a.status_code == response_b.status_code == 201
        payment_a, payment_b = response_a.json(), response_b.json()
        assert payment_a["amount"] == 1_990_000
        assert payment_b["amount"] == 990_000
        webhook_a = {"payment_id": payment_a["id"], "status": "succeeded"}
        webhook_b = {"payment_id": payment_b["id"], "status": "succeeded"}
        assert a.post("/webhooks/bank", json=webhook_a).status_code == 401
        assert b.post("/webhooks/bank", json=webhook_b).status_code == 200
        assert a.get(f"/payments/{payment_a['id']}").json()["status"] == "pending"
        assert b.get(f"/payments/{payment_b['id']}").json()["status"] == "succeeded"


@pytest.mark.parametrize("error_type", [OperationalError, IntegrityError])
def test_commit_failure_propagates_and_rolls_back_before_response(
    client, payload, monkeypatch, error_type
):
    original_commit = AsyncSession.commit
    fail_once = True

    async def failing_commit(session):
        nonlocal fail_once
        if fail_once:
            fail_once = False
            # CRUD has already flushed INSERT; no success may escape a failed COMMIT.
            raise error_type("COMMIT", None, RuntimeError("simulated commit failure"))
        await original_commit(session)

    monkeypatch.setattr(AsyncSession, "commit", failing_commit)
    headers = {"Idempotency-Key": "retry-after-failed-commit"}
    with pytest.raises(error_type, match="simulated commit failure"):
        client.post("/payments", json=payload, headers=headers)
    assert client.get("/payments").json() == []
    retry = client.post("/payments", json=payload, headers=headers)
    assert retry.status_code == 201
    assert retry.json()["amount"] == 1_990_000
    assert len(client.get("/payments").json()) == 1


@pytest.mark.parametrize("error_type", [OperationalError, IntegrityError])
def test_webhook_commit_failure_rolls_back_status_before_response(
    client, payload, monkeypatch, error_type
):
    payment = client.post("/payments", json=payload).json()
    original_commit = AsyncSession.commit
    fail_once = True

    async def failing_commit(session):
        nonlocal fail_once
        if fail_once:
            fail_once = False
            raise error_type("COMMIT", None, RuntimeError("simulated webhook commit failure"))
        await original_commit(session)

    monkeypatch.setattr(AsyncSession, "commit", failing_commit)
    webhook = {"payment_id": payment["id"], "status": "succeeded"}

    with pytest.raises(error_type, match="simulated webhook commit failure"):
        client.post("/webhooks/bank", json=webhook)

    assert client.get(f"/payments/{payment['id']}").json() == payment
    assert client.post("/webhooks/bank", json=webhook).status_code == 200
    assert client.get(f"/payments/{payment['id']}").json() == {**payment, "status": "succeeded"}
