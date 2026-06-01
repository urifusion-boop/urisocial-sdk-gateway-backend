"""
Payment Service - Squad Payment Gateway Integration
Handles payment initialization, verification, and webhook processing
"""
import httpx
import hashlib
import hmac
from datetime import datetime, timezone
from typing import Optional, Dict
from app.core.config import get_settings
from app.models.billing import PaymentTransaction


class PaymentService:
    """Squad payment gateway integration for SDK Gateway billing"""

    def __init__(self):
        self.settings = get_settings()

        # Store all credentials (dynamic mode switching)
        self.sandbox_secret_key = self.settings.SQUAD_SANDBOX_SECRET_KEY or ""
        self.sandbox_public_key = self.settings.SQUAD_SANDBOX_PUBLIC_KEY or ""
        self.live_secret_key = self.settings.SQUAD_LIVE_SECRET_KEY or ""
        self.live_public_key = self.settings.SQUAD_LIVE_PUBLIC_KEY or ""

        # Default mode from environment
        self.default_mode = self.settings.SQUAD_MODE.lower() if self.settings.SQUAD_MODE else "sandbox"

        # Callback URL (where users return after payment)
        self.callback_url = self.settings.SQUAD_CALLBACK_URL or "https://gateway.urisocial.com/billing/callback"

        print(f"🔐 Squad Payment Gateway initialized (mode: {self.default_mode.upper()})")

    def _get_squad_credentials(self) -> Dict[str, str]:
        """Get Squad credentials based on current mode"""
        if self.default_mode == "live":
            return {
                "secret_key": self.live_secret_key,
                "public_key": self.live_public_key,
                "api_url": "https://api-d.squadco.com",
                "mode": "live"
            }
        else:
            return {
                "secret_key": self.sandbox_secret_key,
                "public_key": self.sandbox_public_key,
                "api_url": "https://sandbox-api-d.squadco.com",
                "mode": "sandbox"
            }

    async def initialize_payment(
        self,
        user_id: str,
        plan_tier: str,
        billing_interval: str,
        amount_ngn: float,
        user_email: str
    ) -> Dict:
        """
        Initialize Squad payment checkout

        Args:
            user_id: User making payment
            plan_tier: Subscription tier (starter, professional, enterprise)
            billing_interval: monthly or yearly
            amount_ngn: Payment amount in Nigerian Naira
            user_email: User's email address

        Returns:
            Dict with payment_url, transaction_ref, amount, public_key
        """
        # Generate unique transaction reference
        timestamp = int(datetime.now(timezone.utc).timestamp())
        transaction_ref = f"SDKGTW_{user_id[:8]}_{plan_tier.upper()}_{billing_interval.upper()}_{timestamp}"

        # Create pending payment transaction
        payment = PaymentTransaction(
            user_id=user_id,
            transaction_ref=transaction_ref,
            amount_ngn=amount_ngn,
            currency="NGN",
            status="pending",
            plan_tier=plan_tier,
            billing_interval=billing_interval,
            created_at=datetime.now(timezone.utc)
        )
        await payment.insert()

        # Get current Squad credentials
        creds = self._get_squad_credentials()
        print(f"💳 Initializing payment in {creds['mode'].upper()} mode: ₦{amount_ngn:,.2f}")

        try:
            async with httpx.AsyncClient() as client:
                headers = {
                    "Authorization": f"Bearer {creds['secret_key']}",
                    "Content-Type": "application/json"
                }

                # Squad API expects amount in Kobo (1 Naira = 100 Kobo)
                payload = {
                    "email": user_email,
                    "amount": int(amount_ngn * 100),  # Convert NGN to Kobo
                    "currency": "NGN",
                    "initiate_type": "inline",  # Opens payment modal
                    "transaction_ref": transaction_ref,
                    "callback_url": self.callback_url
                }

                response = await client.post(
                    f"{creds['api_url']}/transaction/initiate",
                    json=payload,
                    headers=headers,
                    timeout=30.0
                )

                response_data = response.json()

                if response.status_code == 200 and response_data.get("success"):
                    data = response_data.get("data", {})
                    checkout_url = data.get("checkout_url") or data.get("authorization_url")

                    if not checkout_url:
                        raise Exception(f"Squad response missing checkout_url: {response_data}")

                    return {
                        "payment_url": checkout_url,
                        "transaction_ref": transaction_ref,
                        "amount": amount_ngn,
                        "email": user_email,
                        "currency": "NGN",
                        "public_key": creds["public_key"]
                    }
                else:
                    # Mark payment as failed
                    await self._mark_payment_failed(transaction_ref, response_data)
                    raise Exception(f"Squad initialization failed: {response_data.get('message')}")

        except httpx.RequestError as e:
            await self._mark_payment_failed(transaction_ref, {"error": str(e)})
            raise Exception(f"Payment gateway connection failed: {str(e)}")

    async def verify_payment(self, transaction_ref: str) -> bool:
        """
        Verify payment status with Squad

        Args:
            transaction_ref: Squad transaction reference

        Returns:
            True if payment is verified and completed
        """
        # Get payment transaction
        payment = await PaymentTransaction.find_one(
            PaymentTransaction.transaction_ref == transaction_ref
        )

        if not payment:
            return False

        # If already completed, return true
        if payment.status == "completed":
            return True

        # Get current Squad credentials
        creds = self._get_squad_credentials()

        try:
            async with httpx.AsyncClient() as client:
                headers = {
                    "Authorization": f"Bearer {creds['secret_key']}"
                }

                response = await client.get(
                    f"{creds['api_url']}/transaction/verify/{transaction_ref}",
                    headers=headers,
                    timeout=30.0
                )

                response_data = response.json()

                if response.status_code == 200 and response_data.get("success"):
                    transaction_data = response_data.get("data", {})
                    gateway_status = transaction_data.get("transaction_status", "").lower()

                    if gateway_status == "success":
                        # Update payment as completed
                        payment.status = "completed"
                        payment.completed_at = datetime.now(timezone.utc)
                        payment.gateway_response = response_data
                        payment.gateway_transaction_id = transaction_data.get("transaction_ref")
                        payment.payment_method = transaction_data.get("payment_type")
                        await payment.save()

                        print(f"✅ Payment verified: {transaction_ref}")
                        return True

            return False

        except Exception as e:
            print(f"❌ Payment verification error: {str(e)}")
            return False

    async def handle_webhook(self, payload: Dict, signature: Optional[str]) -> bool:
        """
        Process Squad webhook callback

        Args:
            payload: Webhook payload from Squad
            signature: HMAC signature from X-Squad-Signature header

        Returns:
            True if webhook processed successfully
        """
        # Verify webhook signature
        if not self._verify_webhook_signature(payload, signature):
            print("❌ Invalid webhook signature")
            return False

        # Extract transaction reference
        transaction_ref = payload.get("Body", {}).get("transaction_ref") or payload.get("transaction_ref")

        if not transaction_ref:
            print("❌ Webhook missing transaction_ref")
            return False

        # Get payment transaction
        payment = await PaymentTransaction.find_one(
            PaymentTransaction.transaction_ref == transaction_ref
        )

        if not payment:
            print(f"❌ Payment not found: {transaction_ref}")
            return False

        # Update payment status based on webhook
        gateway_status = payload.get("Body", {}).get("transaction_status", "").lower()

        if gateway_status == "success":
            payment.status = "completed"
            payment.completed_at = datetime.now(timezone.utc)
            payment.gateway_response = payload
            await payment.save()

            print(f"✅ Webhook processed: {transaction_ref} - Payment successful")
            return True

        elif gateway_status == "failed":
            payment.status = "failed"
            payment.failed_at = datetime.now(timezone.utc)
            payment.gateway_response = payload
            await payment.save()

            print(f"⚠️ Webhook processed: {transaction_ref} - Payment failed")
            return True

        return False

    def _verify_webhook_signature(self, payload: Dict, signature: Optional[str]) -> bool:
        """
        Verify Squad webhook HMAC signature

        Args:
            payload: Webhook payload
            signature: Signature from header

        Returns:
            True if signature is valid
        """
        if not signature:
            # In development/sandbox, signature might be optional
            if self.default_mode == "sandbox":
                return True
            return False

        webhook_secret = self.settings.SQUAD_WEBHOOK_SECRET
        if not webhook_secret:
            print("⚠️ SQUAD_WEBHOOK_SECRET not configured")
            return True  # Allow in development

        # Squad uses HMAC-SHA512
        import json
        payload_string = json.dumps(payload, separators=(',', ':'))
        expected_signature = hmac.new(
            webhook_secret.encode(),
            payload_string.encode(),
            hashlib.sha512
        ).hexdigest()

        return hmac.compare_digest(expected_signature, signature)

    async def _mark_payment_failed(self, transaction_ref: str, error_data: Dict):
        """Mark payment transaction as failed"""
        payment = await PaymentTransaction.find_one(
            PaymentTransaction.transaction_ref == transaction_ref
        )

        if payment:
            payment.status = "failed"
            payment.failed_at = datetime.now(timezone.utc)
            payment.gateway_response = error_data
            await payment.save()

    async def refund_payment(self, transaction_ref: str) -> bool:
        """
        Process refund via Squad

        Args:
            transaction_ref: Transaction to refund

        Returns:
            True if refund successful
        """
        payment = await PaymentTransaction.find_one(
            PaymentTransaction.transaction_ref == transaction_ref
        )

        if not payment or payment.status != "completed":
            return False

        creds = self._get_squad_credentials()

        try:
            async with httpx.AsyncClient() as client:
                headers = {
                    "Authorization": f"Bearer {creds['secret_key']}",
                    "Content-Type": "application/json"
                }

                payload = {
                    "gateway_transaction_ref": payment.gateway_transaction_id or transaction_ref,
                    "refund_type": "Full",  # Full or Partial
                    "reason_for_refund": "Customer request"
                }

                response = await client.post(
                    f"{creds['api_url']}/transaction/refund",
                    json=payload,
                    headers=headers,
                    timeout=30.0
                )

                response_data = response.json()

                if response.status_code == 200 and response_data.get("success"):
                    payment.status = "refunded"
                    payment.gateway_response = response_data
                    await payment.save()

                    print(f"✅ Refund processed: {transaction_ref}")
                    return True

            return False

        except Exception as e:
            print(f"❌ Refund error: {str(e)}")
            return False


# Singleton instance
payment_service = PaymentService()
