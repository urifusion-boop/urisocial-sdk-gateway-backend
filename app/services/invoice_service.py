"""
Invoice Service
Generates and manages invoices for subscriptions and overage charges
"""
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict
from app.models.billing import Invoice, Subscription
from app.services.usage_service import usage_service


class InvoiceService:
    """Invoice generation and management"""

    async def generate_invoice(
        self,
        user_id: str,
        period_start: datetime,
        period_end: datetime,
        subscription_id: Optional[str] = None
    ) -> Invoice:
        """
        Generate invoice for billing period

        Args:
            user_id: User ID
            period_start: Billing period start
            period_end: Billing period end
            subscription_id: Subscription ID

        Returns:
            Generated invoice
        """
        # Generate invoice number
        invoice_number = await self._generate_invoice_number()

        # Get usage for period (billed in the developer's own subscription
        # currency — see usage_service.get_current_usage)
        usage = await usage_service.get_current_usage(user_id)
        currency = usage["currency"]

        # Get subscription charge
        from app.services.subscription_service import subscription_service
        subscription = await subscription_service.get_subscription(user_id)

        if subscription:
            subscription_charge = subscription.base_price_usd if currency == "USD" else subscription.base_price_ngn
            subscription_charge = subscription_charge or 0.0
        else:
            subscription_charge = 0.0

        # Calculate overage
        overage_charge = usage["overage_cost"]

        # Calculate total
        total = subscription_charge + overage_charge

        currency_symbol = "$" if currency == "USD" else "₦"

        # Build line items
        line_items = []

        if subscription_charge > 0:
            line_items.append({
                "description": f"{subscription.plan_tier.title()} Plan - {subscription.billing_interval.title()}",
                "quantity": 1,
                "unit_price": subscription_charge,
                "total": subscription_charge
            })

        if overage_charge > 0:
            overage_credits = usage["overage_credits"]
            line_items.append({
                "description": f"Additional AI-Generation Credits ({overage_credits:,} credits)",
                "quantity": overage_credits,
                "unit_price": overage_charge / overage_credits if overage_credits > 0 else 0,
                "total": overage_charge
            })

        # Create invoice
        invoice = Invoice(
            user_id=user_id,
            subscription_id=subscription_id,
            invoice_number=invoice_number,
            period_start=period_start,
            period_end=period_end,
            subscription_charge_ngn=subscription_charge,
            overage_charge_ngn=overage_charge,
            discount_ngn=0.0,
            tax_ngn=0.0,
            total_ngn=total,
            currency=currency,
            line_items=line_items,
            status="issued",
            issued_at=datetime.now(timezone.utc),
            due_date=datetime.now(timezone.utc) + timedelta(days=7),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc)
        )

        await invoice.insert()

        print(f"✅ Invoice generated: {invoice_number} - {currency_symbol}{total:,.2f} {currency}")
        return invoice

    async def _generate_invoice_number(self) -> str:
        """Generate unique invoice number"""
        now = datetime.now(timezone.utc)
        year = now.year
        month = now.strftime("%m")

        # Count invoices this month
        count = await Invoice.find(
            Invoice.invoice_number.regex(f"^INV-{year}-{month}")
        ).count()

        return f"INV-{year}-{month}-{count + 1:04d}"

    async def mark_invoice_paid(
        self,
        invoice_id: str,
        payment_transaction_id: str
    ) -> Invoice:
        """
        Mark invoice as paid

        Args:
            invoice_id: Invoice ID
            payment_transaction_id: Payment transaction ID

        Returns:
            Updated invoice
        """
        invoice = await Invoice.get(invoice_id)

        if not invoice:
            raise ValueError("Invoice not found")

        invoice.status = "paid"
        invoice.paid_at = datetime.now(timezone.utc)
        invoice.payment_transaction_id = payment_transaction_id
        invoice.updated_at = datetime.now(timezone.utc)

        await invoice.save()

        print(f"✅ Invoice marked paid: {invoice.invoice_number}")
        return invoice

    async def get_user_invoices(
        self,
        user_id: str,
        limit: int = 20,
        status: Optional[str] = None
    ) -> List[Invoice]:
        """
        Get user's invoices

        Args:
            user_id: User ID
            limit: Maximum number of invoices
            status: Filter by status (optional)

        Returns:
            List of invoices
        """
        query = Invoice.find(Invoice.user_id == user_id)

        if status:
            query = query.find(Invoice.status == status)

        invoices = await query.sort("-created_at").limit(limit).to_list()
        return invoices

    async def void_invoice(self, invoice_id: str, reason: str) -> Invoice:
        """
        Void an invoice

        Args:
            invoice_id: Invoice ID
            reason: Reason for voiding

        Returns:
            Voided invoice
        """
        invoice = await Invoice.get(invoice_id)

        if not invoice:
            raise ValueError("Invoice not found")

        invoice.status = "void"
        invoice.void_reason = reason
        invoice.updated_at = datetime.now(timezone.utc)

        await invoice.save()

        print(f"⚠️ Invoice voided: {invoice.invoice_number} - {reason}")
        return invoice

    async def get_invoice_pdf_data(self, invoice_id: str) -> Dict:
        """
        Get invoice data for PDF generation

        Args:
            invoice_id: Invoice ID

        Returns:
            Dict with invoice data for PDF template
        """
        invoice = await Invoice.get(invoice_id)

        if not invoice:
            raise ValueError("Invoice not found")

        symbol = "$" if invoice.currency == "USD" else "₦"

        return {
            "invoice_number": invoice.invoice_number,
            "invoice_date": invoice.issued_at.strftime("%B %d, %Y") if invoice.issued_at else "",
            "due_date": invoice.due_date.strftime("%B %d, %Y") if invoice.due_date else "",
            "period_start": invoice.period_start.strftime("%B %d, %Y"),
            "period_end": invoice.period_end.strftime("%B %d, %Y"),
            "currency": invoice.currency,
            "line_items": invoice.line_items,
            "subscription_charge": f"{symbol}{invoice.subscription_charge_ngn:,.2f}",
            "overage_charge": f"{symbol}{invoice.overage_charge_ngn:,.2f}",
            "discount": f"{symbol}{invoice.discount_ngn:,.2f}",
            "tax": f"{symbol}{invoice.tax_ngn:,.2f}",
            "total": f"{symbol}{invoice.total_ngn:,.2f}",
            "status": invoice.status.upper(),
            "paid_at": invoice.paid_at.strftime("%B %d, %Y") if invoice.paid_at else None
        }


# Singleton instance
invoice_service = InvoiceService()
