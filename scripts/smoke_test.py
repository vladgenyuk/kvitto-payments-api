"""Check a running API over HTTP. Creates one payment; use a disposable database."""

import argparse
import hashlib
import hmac
import json
import os
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4


def smoke_test(base_url: str) -> None:
    secret = os.environ.get("WEBHOOK_SECRET", "")
    key = f"smoke-{uuid4()}"

    def request(
        method: str, path: str, body: dict[str, Any] | None = None, *, bad_signature: bool = False
    ) -> tuple[int, Any]:
        raw = None if body is None else json.dumps(body, separators=(",", ":")).encode()
        headers = {"Content-Type": "application/json", "Idempotency-Key": key}
        if raw is not None and path == "/webhooks/bank" and secret:
            headers["X-Signature"] = (
                "0" * 64
                if bad_signature
                else hmac.new(secret.encode(), raw, hashlib.sha256).hexdigest()
            )
        req = Request(base_url.rstrip("/") + path, data=raw, headers=headers, method=method)
        try:
            with urlopen(req, timeout=5) as response:
                return response.status, json.load(response)
        except HTTPError as error:
            with error:
                return error.code, json.load(error)

    deadline = time.monotonic() + 30
    while True:
        try:
            code, tariffs = request("GET", "/tariffs")
            if code == 200:
                break
        except (URLError, TimeoutError, ConnectionError):
            pass
        if time.monotonic() >= deadline:
            raise RuntimeError("API did not become ready within 30 seconds")
        time.sleep(0.25)

    assert [(t["title"], t["price"]) for t in tariffs] == [
        ("basic", 990_000),
        ("standard", 1_990_000),
        ("premium", 2_990_000),
    ], tariffs
    tariff_id = next(t["id"] for t in tariffs if t["title"] == "standard")
    body = {
        "tariff_id": tariff_id,
        "email": f"{uuid4()}@example.com",
        "method": "installment",
        "installment_months": 3,
        "promo_code": "kvitto10",
    }
    code, payment = request("POST", "/payments", body)
    assert code == 201, (code, payment)
    assert payment["amount"] == 1_791_000 and payment["discount"] == 199_000, payment
    assert payment["schedule"] == [597_000] * 3 and payment["status"] == "pending", payment
    assert request("POST", "/payments", body) == (200, payment)
    assert request("GET", f"/payments/{payment['id']}") == (200, payment)
    assert request("GET", "/payments/9223372036854775808")[0] == 422
    assert request("POST", "/payments", {**body, "promo_code": "wrong"})[0] == 422
    assert request("GET", "/payments/9223372036854775807")[0] == 404

    webhook = {"payment_id": payment["id"], "status": "succeeded"}
    if secret:
        assert request("POST", "/webhooks/bank", webhook, bad_signature=True)[0] == 401
        assert request("GET", f"/payments/{payment['id']}") == (200, payment)
    assert request("POST", "/webhooks/bank", webhook) == (200, {"result": "ok"})
    assert request("POST", "/webhooks/bank", webhook) == (409, {"error": "invalid_transition"})
    code, updated = request("GET", f"/payments/{payment['id']}")
    assert (code, updated) == (200, {**payment, "status": "succeeded"})
    query = urlencode({"email": body["email"], "status": "succeeded"})
    assert request("GET", f"/payments?{query}") == (200, [updated])
    assert request("POST", "/webhooks/bank", {**webhook, "status": "refunded"}) == (
        200,
        {"result": "ok"},
    )
    print(f"HTTP smoke test passed (HMAC {'enabled' if secret else 'disabled'})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    smoke_test(args.url)
