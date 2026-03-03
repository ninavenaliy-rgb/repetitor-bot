"""Robokassa payment service for СБП and card payments."""

from __future__ import annotations

import hashlib
import uuid
from urllib.parse import urlencode, quote

from loguru import logger

from config.settings import settings


class RobokassaService:
    """Robokassa payment processing — supports СБП, bank cards, etc."""

    BASE_URL = "https://auth.robokassa.ru/Merchant/Index.aspx"

    def generate_inv_id(self, transaction_id: uuid.UUID) -> int:
        """Generate a unique integer invoice ID from UUID.

        Robokassa requires a positive integer InvId.
        """
        return abs(int(str(transaction_id).replace("-", "")[:8], 16)) % 2_000_000_000

    def _md5(self, value: str) -> str:
        """Compute MD5 hash of a string."""
        return hashlib.md5(value.encode("utf-8")).hexdigest().upper()

    def _sign_payment(self, out_sum: str, inv_id: int) -> str:
        """Compute payment signature (MD5 of login:OutSum:InvId:password1)."""
        raw = f"{settings.robokassa_login}:{out_sum}:{inv_id}:{settings.robokassa_password1}"
        return self._md5(raw)

    def _sign_result(self, out_sum: str, inv_id: int) -> str:
        """Compute result signature (MD5 of OutSum:InvId:password2).

        Used to verify Robokassa webhook notifications.
        """
        raw = f"{out_sum}:{inv_id}:{settings.robokassa_password2}"
        return self._md5(raw)

    def create_payment_url(
        self,
        amount: float,
        inv_id: int,
        description: str,
        email: str = "",
        prefer_sbp: bool = True,
    ) -> str:
        """Generate Robokassa payment URL with СБП as preferred method.

        Args:
            amount: Payment amount in rubles (e.g. 990.00)
            inv_id: Unique integer invoice ID
            description: Payment description shown to user
            email: Payer email (optional, for receipts)
            prefer_sbp: If True, pre-selects СБП payment method

        Returns:
            Payment URL to open in browser
        """
        out_sum = f"{amount:.2f}"
        signature = self._sign_payment(out_sum, inv_id)

        params = {
            "MrchLogin": settings.robokassa_login,
            "OutSum": out_sum,
            "InvId": inv_id,
            "Description": description,
            "SignatureValue": signature,
            "Encoding": "utf-8",
        }

        if prefer_sbp:
            # Pre-select СБП (Система Быстрых Платежей)
            params["IncCurrLabel"] = "SBP"

        if email:
            params["Email"] = email

        if settings.robokassa_test_mode:
            params["IsTest"] = 1

        url = f"{self.BASE_URL}?{urlencode(params, quote_via=quote)}"
        logger.info(f"Robokassa URL generated: InvId={inv_id}, amount={out_sum}, sbp={prefer_sbp}")
        return url

    def verify_result_signature(
        self,
        out_sum: str,
        inv_id: int,
        signature: str,
    ) -> bool:
        """Verify webhook notification signature from Robokassa.

        Robokassa sends POST with OutSum, InvId, SignatureValue.
        We verify: MD5(OutSum:InvId:password2) == SignatureValue
        """
        expected = self._sign_result(out_sum, inv_id)
        received = signature.upper()
        is_valid = expected == received

        if not is_valid:
            logger.warning(
                f"Robokassa signature mismatch: expected={expected}, got={received}"
            )
        return is_valid
