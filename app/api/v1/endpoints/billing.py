"""
Billing API Endpoints
Handles subscription management, payments, usage tracking, and invoices
"""
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from typing import Optional, List
from pydantic import BaseModel, Field
from app.api.deps import get_current_developer
from app.models.developer import Developer
from app.services.payment_service import payment_service
from app.services.subscription_service import subscription_service
from app.services.usage_service import usage_service
from app.services.invoice_service import invoice_service
from app.core.pricing import PRICING_TIERS, PlanTier, BillingInterval

router = APIRouter(prefix="/billing", tags=["Billing"])


# Helper function to convert Developer to user dict
def developer_to_user_dict(developer: Developer) -> dict:
    """Convert Developer model to user dict for service functions"""
    return {
        "user_id": str(developer.id),
        "email": developer.email,
        "name": developer.name or "",
        "workspace_id": developer.workspace_id
    }


# ==================== Request/Response Models ====================

class InitializePaymentRequest(BaseModel):
    """Request to initialize payment"""
    plan_tier: str = Field(..., description="starter, professional, or enterprise")
    billing_interval: str = Field(default="monthly", description="monthly or yearly")


class VerifyPaymentRequest(BaseModel):
    """Request to verify payment"""
    transaction_ref: str = Field(..., description="Squad transaction reference")


class UpgradeSubscriptionRequest(BaseModel):
    """Request to upgrade subscription"""
    new_tier: str = Field(..., description="New plan tier")
    new_interval: str = Field(default="monthly", description="New billing interval")


# ==================== Pricing & Plans ====================

@router.get("/plans")
async def get_pricing_plans():
    """
    Get all available pricing plans

    Returns all subscription tiers with pricing in NGN
    """
    plans = []

    for tier, plan in PRICING_TIERS.items():
        plans.append({
            "tier": tier.value,
            "name": plan.name,
            "description": plan.description,
            "pricing": {
                "monthly_ngn": plan.monthly_price_ngn,
                "yearly_ngn": plan.yearly_price_ngn,
                "currency": "NGN",
                "yearly_discount": "20%"
            },
            "quotas": {
                "monthly_requests": plan.monthly_requests,
                "hourly_rate_limit": plan.hourly_rate_limit,
                "daily_rate_limit": plan.daily_rate_limit,
                "max_api_keys": plan.max_api_keys
            },
            "overage": {
                "rate_per_1k_ngn": plan.overage_rate_per_1k_ngn,
                "allowed": tier != PlanTier.FREE
            },
            "features": {
                "ip_whitelisting": plan.ip_whitelisting,
                "custom_rate_limits": plan.custom_rate_limits,
                "webhook_notifications": plan.webhook_notifications,
                "priority_support": plan.priority_support,
                "sla_guarantee": f"{plan.sla_guarantee}%" if plan.sla_guarantee else None,
                "dedicated_infrastructure": plan.dedicated_infrastructure,
                "custom_integrations": plan.custom_integrations,
                "audit_logs": plan.audit_logs,
                "sso_enabled": plan.sso_enabled
            }
        })

    return {
        "success": True,
        "data": plans
    }


# ==================== Payment Flow ====================

@router.post("/initialize-payment")
async def initialize_payment(
    body: InitializePaymentRequest,
    developer: Developer = Depends(get_current_developer)
):
    """
    Initialize Squad payment checkout

    Steps:
    1. Calculate price based on tier and interval
    2. Create pending transaction
    3. Initialize Squad checkout
    4. Return payment URL and public key for inline modal
    """
    try:
        print(f"🔵 Initialize payment request - User: {developer.email}, Tier: {body.plan_tier}, Interval: {body.billing_interval}")

        user_id = str(developer.id)
        user_email = developer.email

        # Validate tier
        if body.plan_tier not in ["starter", "professional", "enterprise"]:
            raise HTTPException(
                status_code=400,
                detail="Invalid plan tier. Must be starter, professional, or enterprise"
            )

        # Get plan pricing
        plan_enum = PlanTier(body.plan_tier)
        plan = PRICING_TIERS[plan_enum]

        if body.billing_interval == "yearly":
            amount_ngn = plan.yearly_price_ngn
        else:
            amount_ngn = plan.monthly_price_ngn

        print(f"💰 Amount calculated: ₦{amount_ngn:,.2f}")

        # Initialize payment
        result = await payment_service.initialize_payment(
            user_id=user_id,
            plan_tier=body.plan_tier,
            billing_interval=body.billing_interval,
            amount_ngn=amount_ngn,
            user_email=user_email
        )

        print(f"✅ Payment initialized successfully: {result.get('transaction_ref', 'N/A')}")

        return {
            "success": True,
            "data": result
        }

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"❌ Payment initialization error: {str(e)}")
        print(f"📋 Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e) or "Payment initialization failed")


@router.post("/verify-payment")
async def verify_payment(
    body: VerifyPaymentRequest,
    developer: Developer = Depends(get_current_developer)
):
    """
    Verify payment status with Squad

    Called by frontend after payment redirect
    """
    try:
        verified = await payment_service.verify_payment(body.transaction_ref)

        if verified:
            # Get payment transaction
            from app.models.billing import PaymentTransaction
            payment = await PaymentTransaction.find_one(
                PaymentTransaction.transaction_ref == body.transaction_ref
            )

            if payment and payment.status == "completed":
                # Create or update subscription
                subscription = await subscription_service.create_subscription(
                    user_id=payment.user_id,
                    plan_tier=payment.plan_tier,
                    billing_interval=payment.billing_interval,
                    payment_ref=payment.transaction_ref
                )

                return {
                    "success": True,
                    "verified": True,
                    "data": {
                        "subscription_id": str(subscription.id),
                        "plan_tier": subscription.plan_tier,
                        "status": subscription.status
                    }
                }

        return {
            "success": False,
            "verified": False,
            "message": "Payment not verified yet"
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/webhook")
async def squad_webhook(
    request: Request,
    x_squad_signature: Optional[str] = Header(None)
):
    """
    Squad webhook callback (NO authentication required)

    Processes payment notifications from Squad
    """
    try:
        payload = await request.json()

        success = await payment_service.handle_webhook(
            payload=payload,
            signature=x_squad_signature
        )

        if success:
            # Extract transaction ref and create subscription
            transaction_ref = payload.get("Body", {}).get("transaction_ref") or payload.get("transaction_ref")

            if transaction_ref:
                from app.models.billing import PaymentTransaction
                payment = await PaymentTransaction.find_one(
                    PaymentTransaction.transaction_ref == transaction_ref
                )

                if payment and payment.status == "completed" and not payment.subscription_id:
                    # Create subscription
                    subscription = await subscription_service.create_subscription(
                        user_id=payment.user_id,
                        plan_tier=payment.plan_tier,
                        billing_interval=payment.billing_interval,
                        payment_ref=transaction_ref
                    )

                    # Link subscription to payment
                    payment.subscription_id = str(subscription.id)
                    await payment.save()

            return {"success": True, "message": "Webhook processed"}

        return {"success": False, "message": "Webhook processing failed"}

    except Exception as e:
        print(f"❌ Webhook error: {str(e)}")
        return {"success": False, "message": str(e)}


# ==================== Subscription Management ====================

@router.get("/subscription")
async def get_subscription(developer: Developer = Depends(get_current_developer)):
    """Get current subscription details"""
    try:
        user_id = str(developer.id)
        print(f"📊 Getting subscription for user: {user_id}")
        status = await subscription_service.check_subscription_status(user_id)
        print(f"✅ Subscription status: {status}")

        return {
            "success": True,
            "data": status
        }

    except Exception as e:
        import traceback
        print(f"❌ Subscription error: {str(e)}")
        print(f"📋 Traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/subscription/upgrade")
async def upgrade_subscription(
    body: UpgradeSubscriptionRequest,
    developer: Developer = Depends(get_current_developer)
):
    """
    Calculate upgrade cost with proration

    Returns amount to charge for upgrade
    """
    try:
        user_id = str(developer.id)

        upgrade_details = await subscription_service.upgrade_subscription(
            user_id=user_id,
            new_tier=body.new_tier,
            new_interval=body.new_interval
        )

        return {
            "success": True,
            "data": upgrade_details
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/subscription/cancel")
async def cancel_subscription(developer: Developer = Depends(get_current_developer)):
    """
    Cancel subscription at end of billing period
    """
    try:
        user_id = str(developer.id)

        result = await subscription_service.cancel_subscription(
            user_id=user_id,
            immediate=False
        )

        return {
            "success": True,
            "data": result
        }

    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Usage Tracking ====================

@router.get("/usage")
async def get_usage(developer: Developer = Depends(get_current_developer)):
    """Get current billing period usage"""
    try:
        user_id = str(developer.id)
        usage = await usage_service.get_current_usage(user_id)

        return {
            "success": True,
            "data": usage
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/usage/breakdown")
async def get_usage_breakdown(developer: Developer = Depends(get_current_developer)):
    """Get endpoint-level usage analytics"""
    try:
        user_id = str(developer.id)
        breakdown = await usage_service.get_usage_breakdown(user_id)

        return {
            "success": True,
            "data": breakdown
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Invoices ====================

@router.get("/invoices")
async def get_invoices(
    limit: int = 20,
    status: Optional[str] = None,
    developer: Developer = Depends(get_current_developer)
):
    """Get user's invoices"""
    try:
        user_id = str(developer.id)
        invoices = await invoice_service.get_user_invoices(
            user_id=user_id,
            limit=limit,
            status=status
        )

        invoice_list = []
        for invoice in invoices:
            invoice_list.append({
                "id": str(invoice.id),
                "invoice_number": invoice.invoice_number,
                "period_start": invoice.period_start.isoformat(),
                "period_end": invoice.period_end.isoformat(),
                "subscription_charge_ngn": invoice.subscription_charge_ngn,
                "overage_charge_ngn": invoice.overage_charge_ngn,
                "total_ngn": invoice.total_ngn,
                "currency": invoice.currency,
                "status": invoice.status,
                "issued_at": invoice.issued_at.isoformat() if invoice.issued_at else None,
                "paid_at": invoice.paid_at.isoformat() if invoice.paid_at else None,
                "due_date": invoice.due_date.isoformat() if invoice.due_date else None
            })

        return {
            "success": True,
            "data": invoice_list
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/invoices/{invoice_id}")
async def get_invoice(
    invoice_id: str,
    developer: Developer = Depends(get_current_developer)
):
    """Get invoice details"""
    try:
        from app.models.billing import Invoice

        invoice = await Invoice.get(invoice_id)

        if not invoice or invoice.user_id != str(developer.id):
            raise HTTPException(status_code=404, detail="Invoice not found")

        return {
            "success": True,
            "data": {
                "id": str(invoice.id),
                "invoice_number": invoice.invoice_number,
                "period_start": invoice.period_start.isoformat(),
                "period_end": invoice.period_end.isoformat(),
                "line_items": invoice.line_items,
                "subscription_charge_ngn": invoice.subscription_charge_ngn,
                "overage_charge_ngn": invoice.overage_charge_ngn,
                "discount_ngn": invoice.discount_ngn,
                "tax_ngn": invoice.tax_ngn,
                "total_ngn": invoice.total_ngn,
                "currency": invoice.currency,
                "status": invoice.status,
                "issued_at": invoice.issued_at.isoformat() if invoice.issued_at else None,
                "paid_at": invoice.paid_at.isoformat() if invoice.paid_at else None,
                "due_date": invoice.due_date.isoformat() if invoice.due_date else None
            }
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ==================== Payment History ====================

@router.get("/payments")
async def get_payment_history(
    limit: int = 20,
    developer: Developer = Depends(get_current_developer)
):
    """Get payment transaction history"""
    try:
        from app.models.billing import PaymentTransaction

        user_id = str(developer.id)

        payments = await PaymentTransaction.find(
            PaymentTransaction.user_id == user_id
        ).sort("-created_at").limit(limit).to_list()

        payment_list = []
        for payment in payments:
            payment_list.append({
                "id": str(payment.id),
                "transaction_ref": payment.transaction_ref,
                "amount_ngn": payment.amount_ngn,
                "currency": payment.currency,
                "status": payment.status,
                "plan_tier": payment.plan_tier,
                "billing_interval": payment.billing_interval,
                "payment_method": payment.payment_method,
                "created_at": payment.created_at.isoformat(),
                "completed_at": payment.completed_at.isoformat() if payment.completed_at else None
            })

        return {
            "success": True,
            "data": payment_list
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
