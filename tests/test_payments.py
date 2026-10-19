import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from sqlite3 import IntegrityError as SQLiteIntegrityError

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select

from app.backend.main import create_app
from app.crud import PaymentCrud
from app.models import Payment


def test_tariffs(client):
    response = client.get("/tariffs")
    assert response.status_code == 200
    assert response.json() == [
        {"id": 1, "title": "basic", "price": 990_000},
        {"id": 2, "title": "standard", "price": 1_990_000},
        {"id": 3, "title": "premium", "price": 2_990_000},
    ]


@pytest.mark.parametrize("tariff_id,price", [(1, 990_000), (2, 1_990_000), (3, 2_990_000)])
@pytest.mark.parametrize("promo", [None, "KVITTO10", "kvitto10", "KvItTo10"])
def test_money_and_response_contract(client, payload, tariff_id, price, promo):
    response = client.post(
        "/payments", json={**payload, "tariff_id": tariff_id, "promo_code": promo}
    )
    assert response.status_code == 201
    payment = response.json()
    assert set(payment) == {
        "id",
        "status",
        "tariff_id",
        "amount",
        "discount",
        "method",
        "installment_months",
        "schedule",
        "email",
        "created_at",
    }
    expected_discount = 0 if promo is None else price // 10
    assert payment["discount"] == expected_discount
    assert payment["amount"] == price - expected_discount
    assert type(payment["amount"]) is int
    assert type(payment["discount"]) is int
    assert payment["status"] == "pending"
    assert payment["tariff_id"] == tariff_id
    assert payment["email"] == payload["email"]
    assert payment["method"] == "card"
    assert payment["schedule"] is None
    assert payment["installment_months"] is None
    assert datetime.fromisoformat(payment["created_at"]).utcoffset().total_seconds() == 0
    fetched = client.get(f"/payments/{payment['id']}")
    assert fetched.status_code == 200
    assert fetched.json() == payment


@pytest.mark.parametrize("tariff_id", [1, 2, 3])
@pytest.mark.parametrize("months", [3, 6, 12])
@pytest.mark.parametrize("promo", [None, "kvitto10"])
def test_installment_schedule(client, payload, tariff_id, months, promo):
    response = client.post(
        "/payments",
        json={
            **payload,
            "tariff_id": tariff_id,
            "method": "installment",
            "installment_months": months,
            "promo_code": promo,
        },
    )
    assert response.status_code == 201
    payment = response.json()
    schedule = payment["schedule"]
    assert len(schedule) == months
    assert payment["installment_months"] == months
    assert sum(schedule) == payment["amount"]
    assert all(type(value) is int for value in schedule)
    assert max(schedule) - min(schedule) <= 1
    assert schedule == sorted(schedule, reverse=True)
    if tariff_id == 2 and months == 3 and promo is None:
        assert schedule == [663334, 663333, 663333]


def test_sbp(client, payload):
    response = client.post("/payments", json={**payload, "method": "sbp"})
    assert response.status_code == 201
    assert response.json()["method"] == "sbp"
    assert response.json()["schedule"] is None


@pytest.mark.parametrize(
    "change",
    [
        {"promo_code": "UNKNOWN"},
        {"promo_code": ""},
        {"email": "broken"},
        {"method": "cash"},
        {"tariff_id": 999},
        {"tariff_id": 0},
        {"tariff_id": True},
        {"tariff_id": 2.0},
        {"tariff_id": "2"},
        {"method": "installment"},
        {"method": "installment", "installment_months": None},
        {"method": "installment", "installment_months": 4},
        {"method": "installment", "installment_months": 3.0},
        {"method": "installment", "installment_months": "3"},
        {"method": "installment", "installment_months": True},
        {"method": "card", "installment_months": 3},
        {"method": "sbp", "installment_months": 6},
    ],
)
def test_invalid_payment_returns_standard_422_without_insert(client, payload, change):
    response = client.post("/payments", json={**payload, **change})
    assert response.status_code == 422
    assert isinstance(response.json()["detail"], list)
    assert client.get("/payments").json() == []


def test_idempotency_returns_original_even_with_different_valid_body(client, payload):
    headers = {"Idempotency-Key": "order-123"}
    first = client.post("/payments", json=payload, headers=headers)
    second = client.post(
        "/payments", json={**payload, "tariff_id": 1, "method": "sbp"}, headers=headers
    )
    assert first.status_code == 201
    assert second.status_code == 200
    assert second.json() == first.json()

    async def count_rows():
        async with client.app.state.database.session() as session:
            return await session.scalar(select(func.count()).select_from(Payment))

    assert client.portal.call(count_rows) == 1


def test_replay_returns_current_status(client, payload):
    headers = {"Idempotency-Key": "status-replay"}
    payment = client.post("/payments", json=payload, headers=headers).json()
    assert (
        client.post(
            "/webhooks/bank", json={"payment_id": payment["id"], "status": "succeeded"}
        ).status_code
        == 200
    )
    replay = client.post("/payments", json=payload, headers=headers)
    assert replay.status_code == 200
    assert replay.json()["id"] == payment["id"]
    assert replay.json()["status"] == "succeeded"


def test_without_key_creates_independent_payments(client, payload):
    first = client.post("/payments", json=payload)
    second = client.post("/payments", json=payload)
    assert first.status_code == second.status_code == 201
    assert first.json()["id"] != second.json()["id"]


def test_different_keys_create_independent_payments(client, payload):
    responses = [
        client.post("/payments", json=payload, headers={"Idempotency-Key": key})
        for key in ("key-A", "key-a")
    ]
    assert [r.status_code for r in responses] == [201, 201]
    assert responses[0].json()["id"] != responses[1].json()["id"]


@pytest.mark.parametrize("key", ["", "x" * 201])
def test_invalid_idempotency_key(client, payload, key):
    assert (
        client.post("/payments", json=payload, headers={"Idempotency-Key": key}).status_code == 422
    )


def test_concurrent_idempotency(client, payload, monkeypatch):
    workers = 8
    barrier = asyncio.Barrier(workers)
    engine = client.app.state.database.engine.sync_engine
    collisions = []
    original_create = PaymentCrud.create

    async def synchronized_create(self, *args, **kwargs):
        # All initial lookups complete before any INSERT; never block the event loop.
        await asyncio.wait_for(barrier.wait(), timeout=10)
        return await original_create(self, *args, **kwargs)

    def record_collision(context):
        if isinstance(context.original_exception, SQLiteIntegrityError):
            collisions.append(context.original_exception)

    def send(index):
        return client.post(
            "/payments",
            json={**payload, "tariff_id": index % 3 + 1},
            headers={"Idempotency-Key": "parallel-order"},
        )

    monkeypatch.setattr(PaymentCrud, "create", synchronized_create)
    event.listen(engine, "handle_error", record_collision)
    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            responses = list(pool.map(send, range(workers)))
    finally:
        event.remove(engine, "handle_error", record_collision)
    assert sorted(r.status_code for r in responses) == [200] * 7 + [201]
    winner = next(r.json() for r in responses if r.status_code == 201)
    assert all(r.json() == winner for r in responses)
    assert len(collisions) == workers - 1

    async def count_rows():
        async with client.app.state.database.session() as session:
            return await session.scalar(select(func.count()).select_from(Payment))

    assert client.portal.call(count_rows) == 1


def test_missing_payment(client):
    response = client.get("/payments/999")
    assert response.status_code == 404


def test_persistence_and_seed_on_restart(db_url, payload):
    with TestClient(create_app(db_url, webhook_secret="")) as first:
        payment = first.post(
            "/payments", json=payload, headers={"Idempotency-Key": "persistent"}
        ).json()
    with TestClient(create_app(db_url, webhook_secret="")) as second:
        assert len(second.get("/tariffs").json()) == 3
        assert second.get(f"/payments/{payment['id']}").json() == payment
        replay = second.post("/payments", json=payload, headers={"Idempotency-Key": "persistent"})
        assert replay.status_code == 200
        assert replay.json() == payment


def test_payment_filters(client, payload):
    a = client.post("/payments", json=payload).json()
    b = client.post("/payments", json={**payload, "email": "other@example.com"}).json()
    c = client.post("/payments", json=payload).json()
    assert (
        client.post(
            "/webhooks/bank", json={"payment_id": c["id"], "status": "succeeded"}
        ).status_code
        == 200
    )
    assert [p["id"] for p in client.get("/payments").json()] == [a["id"], b["id"], c["id"]]
    assert [
        p["id"] for p in client.get("/payments", params={"email": payload["email"]}).json()
    ] == [a["id"], c["id"]]
    assert [p["id"] for p in client.get("/payments", params={"status": "pending"}).json()] == [
        a["id"],
        b["id"],
    ]
    assert [
        p["id"]
        for p in client.get(
            "/payments", params={"email": payload["email"], "status": "succeeded"}
        ).json()
    ] == [c["id"]]
    assert client.get("/payments", params={"status": "refunded"}).json() == []
    assert client.get("/payments", params={"status": "bad"}).status_code == 422
    assert client.get("/payments", params={"email": "bad"}).status_code == 422
