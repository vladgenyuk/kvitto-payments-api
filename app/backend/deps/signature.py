import hashlib
import hmac
from typing import Annotated

from fastapi import Header, HTTPException, Request


class WebhookSignatureVerifier:
    def __init__(self, secret: str) -> None:
        self._secret = secret

    async def __call__(
        self,
        request: Request,
        signature: Annotated[str | None, Header(alias="X-Signature")] = None,
    ) -> None:
        if not self._secret:
            return
        expected = hmac.new(self._secret.encode(), await request.body(), hashlib.sha256).hexdigest()
        if signature is None or not hmac.compare_digest(expected.encode(), signature.encode()):
            raise HTTPException(status_code=401, detail="Invalid webhook signature")
