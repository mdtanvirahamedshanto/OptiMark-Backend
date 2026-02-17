"""Subscription and payment endpoints."""

from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, Request, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import os

from app.database import get_db
from app.models import User, PendingPayment
from app.schemas import ManualPaymentSubmit
from app.dependencies import get_current_user
from app.config import get_settings
from pydantic import BaseModel

router = APIRouter(prefix="/subscription", tags=["subscription"])
settings = get_settings()

STRIPE_SECRET = os.environ.get("STRIPE_SECRET_KEY") or getattr(settings, "STRIPE_SECRET_KEY", None)
STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET") or getattr(settings, "STRIPE_WEBHOOK_SECRET", None)


@router.get("/plans")
async def get_plans():
    """Return available subscription plans and payment methods (bKash, Nagad, Send Money)."""
    return {
        "plans": [
            {"id": "1month", "name": "1 Month", "price": 500, "currency": "bdt", "duration_months": 1},
            {"id": "6month", "name": "6 Months", "price": 2500, "currency": "bdt", "duration_months": 6, "savings": "17%"},
            {"id": "1year", "name": "1 Year", "price": 4500, "currency": "bdt", "duration_months": 12, "savings": "25%"},
        ],
        "payment_methods": {
            "bkash": {
                "name": "bKash",
                "number": "01700000000",
                "instructions": "Send money to this bKash number. Use your transaction ID as reference.",
            },
            "nagad": {
                "name": "Nagad",
                "number": "01700000000",
                "instructions": "Send money to this Nagad number. Use your transaction ID as reference.",
            },
            "bank_transfer": {
                "name": "Send Money / Bank Transfer",
                "bank_name": "Your Bank Name",
                "account_name": "OptiMark",
                "account_number": "1234567890",
                "routing_number": "BRAC-0001",
                "instructions": "Send money to the above account. Include your transaction ID in the transfer note.",
            },
        },
    }


class CheckoutRequest(BaseModel):
    plan_id: str


@router.post("/create-checkout-session")
async def create_stripe_checkout(
    body: CheckoutRequest,
    current_user: User = Depends(get_current_user),
):
    """Create Stripe Checkout session (when Stripe is configured)."""
    plan_id = body.plan_id
    if not STRIPE_SECRET:
        raise HTTPException(
            status_code=501,
            detail="Online payment not configured. Use bKash, Nagad, or Bank Transfer.",
        )
    try:
        import stripe
        stripe.api_key = STRIPE_SECRET
        prices = {"1month": 500, "6month": 2500, "1year": 4500}
        amount = prices.get(plan_id, 500)
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[{
                "price_data": {
                    "currency": "bdt",
                    "product_data": {"name": f"OptiMark - {plan_id}", "description": "Subscription"},
                    "unit_amount": amount * 100,
                },
                "quantity": 1,
            }],
            mode="payment",
            success_url=os.environ.get("FRONTEND_URL", "http://localhost:3000") + "/subscription?success=1",
            cancel_url=os.environ.get("FRONTEND_URL", "http://localhost:3000") + "/subscription?canceled=1",
            metadata={"user_id": str(current_user.id), "plan_id": plan_id},
        )
        return {"url": session.url, "session_id": session.id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/manual-payment")
async def submit_manual_payment(
    data: ManualPaymentSubmit,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Submit manual payment (bKash, Nagad, Bank Transfer) for admin approval."""
    try:
        amount = float(data.amount)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid amount")

    payment = PendingPayment(
        user_id=current_user.id,
        plan_id=data.plan,
        amount=amount,
        payment_method=data.payment_method,
        transaction_id=data.transaction_id,
        sender_name=data.sender_name,
        sender_phone=data.sender_phone,
        sender_email=data.sender_email or current_user.email,
    )
    db.add(payment)
    await db.flush()
    return {
        "message": "Payment submitted successfully. Admin will verify and activate your subscription within 24 hours.",
        "payment_id": payment.id,
    }


@router.get("/my-payments")
async def get_my_payments(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Get current user's payment submissions and status."""
    result = await db.execute(
        select(PendingPayment)
        .where(PendingPayment.user_id == current_user.id)
        .order_by(PendingPayment.created_at.desc())
    )
    payments = result.scalars().all()
    return {
        "payments": [
            {
                "id": p.id,
                "plan_id": p.plan_id,
                "amount": p.amount,
                "payment_method": p.payment_method,
                "transaction_id": p.transaction_id,
                "status": p.status,
                "admin_notes": p.admin_notes,
                "created_at": p.created_at.isoformat() if p.created_at else None,
            }
            for p in payments
        ],
    }


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: str = Header(None, alias="Stripe-Signature"),
    db: AsyncSession = Depends(get_db),
):
    """Handle Stripe webhook for payment confirmation."""
    if not STRIPE_WEBHOOK_SECRET:
        return {"received": True}
    try:
        import stripe
        stripe.api_key = STRIPE_SECRET
        payload = await request.body()
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, STRIPE_WEBHOOK_SECRET
        )
        if event["type"] == "checkout.session.completed":
            session = event["data"]["object"]
            user_id = session.get("metadata", {}).get("user_id")
            plan_id = session.get("metadata", {}).get("plan_id", "1month")
            if user_id:
                result = await db.execute(select(User).where(User.id == int(user_id)))
                user = result.scalar_one_or_none()
                if user:
                    user.is_subscribed = True
                    user.subscription_plan = plan_id
                    await db.commit()
        return {"received": True}
    except Exception:
        return {"received": True}
