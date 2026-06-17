"""Tenant-scoped data removal for demo / workspace hygiene."""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from app.models import Case, Dispute, Finding, Invoice, InvoiceLine, RefundLedger, RejectedRow


class DataCleanupService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def delete_invoice(self, tenant_id: str, invoice_id: str) -> dict[str, int]:
        invoice = self.db.scalar(
            select(Invoice)
            .where(Invoice.id == invoice_id, Invoice.tenant_id == tenant_id)
            .options(selectinload(Invoice.lines))
        )
        if not invoice:
            raise LookupError(f"invoice not found: {invoice_id}")

        line_ids = [line.id for line in invoice.lines]
        removed = {"findings": 0, "cases": 0, "disputes": 0, "refunds": 0, "lines": len(line_ids)}

        if line_ids:
            finding_ids = list(
                self.db.scalars(select(Finding.id).where(Finding.invoice_line_id.in_(line_ids)))
            )
            if finding_ids:
                case_ids = list(self.db.scalars(select(Case.id).where(Case.finding_id.in_(finding_ids))))
                if case_ids:
                    dispute_ids = list(
                        self.db.scalars(select(Dispute.id).where(Dispute.case_id.in_(case_ids)))
                    )
                    if dispute_ids:
                        refund_result = self.db.execute(
                            delete(RefundLedger).where(RefundLedger.dispute_id.in_(dispute_ids))
                        )
                        removed["refunds"] = refund_result.rowcount or 0
                        dispute_result = self.db.execute(delete(Dispute).where(Dispute.id.in_(dispute_ids)))
                        removed["disputes"] = dispute_result.rowcount or 0
                    case_result = self.db.execute(delete(Case).where(Case.id.in_(case_ids)))
                    removed["cases"] = case_result.rowcount or 0
                finding_result = self.db.execute(delete(Finding).where(Finding.id.in_(finding_ids)))
                removed["findings"] = finding_result.rowcount or 0

        self.db.delete(invoice)
        self.db.commit()
        removed["invoices"] = 1
        return removed

    def clear_rejected_rows(self, tenant_id: str) -> int:
        result = self.db.execute(delete(RejectedRow).where(RejectedRow.tenant_id == tenant_id))
        self.db.commit()
        return result.rowcount or 0
