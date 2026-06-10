from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AccessorialType,
    CaseStatus,
    Dispute,
    DisputeStatus,
    FindingStatus,
    RefundLedger,
    RefundStatus,
)


class RefundLedgerService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def create_expected_credits(self, tenant_id: str) -> list[RefundLedger]:
        disputes = list(
            self.db.scalars(
                select(Dispute).where(
                    Dispute.tenant_id == tenant_id,
                    Dispute.status == DisputeStatus.SUBMITTED,
                )
            )
        )
        entries: list[RefundLedger] = []
        for dispute in disputes:
            finding = dispute.case.finding
            line = finding.invoice_line
            invoice = line.invoice
            existing = self.db.scalar(select(RefundLedger).where(RefundLedger.dispute_id == dispute.id))
            if existing:
                continue
            entry = RefundLedger(
                tenant_id=tenant_id,
                dispute_id=dispute.id,
                invoice_number=invoice.invoice_number,
                tracking_number=line.tracking_number,
                charge_type=finding.finding_type,
                expected_credit=finding.recoverable_amount,
                status=RefundStatus.EXPECTED,
            )
            self.db.add(entry)
            entries.append(entry)
        self.db.commit()
        return entries

    def post_credit(
        self,
        tenant_id: str,
        tracking_number: str,
        invoice_number: str,
        posted_credit: Decimal,
        credit_invoice_number: str,
        posted_at: date,
    ) -> RefundLedger:
        entry = self.db.scalar(
            select(RefundLedger).where(
                RefundLedger.tenant_id == tenant_id,
                RefundLedger.tracking_number == tracking_number,
                RefundLedger.invoice_number == invoice_number,
                RefundLedger.status == RefundStatus.EXPECTED,
            )
        )
        if not entry:
            entry = RefundLedger(
                tenant_id=tenant_id,
                invoice_number=invoice_number,
                tracking_number=tracking_number,
                charge_type=AccessorialType.OTHER,
                expected_credit=Decimal("0.00"),
                status=RefundStatus.UNMATCHED,
            )
            self.db.add(entry)
        entry.posted_credit = posted_credit
        entry.credit_invoice_number = credit_invoice_number
        entry.posted_at = posted_at
        entry.status = RefundStatus.MATCHED if posted_credit >= entry.expected_credit else RefundStatus.POSTED
        if entry.dispute and entry.status == RefundStatus.MATCHED:
            entry.dispute.status = DisputeStatus.APPROVED
            entry.dispute.case.status = CaseStatus.WON
            entry.dispute.case.finding.status = FindingStatus.CREDITED
        self.db.commit()
        self.db.refresh(entry)
        return entry

    def simulate_posted_credits(self, tenant_id: str) -> list[RefundLedger]:
        entries = list(
            self.db.scalars(
                select(RefundLedger).where(
                    RefundLedger.tenant_id == tenant_id,
                    RefundLedger.status == RefundStatus.EXPECTED,
                    RefundLedger.expected_credit > Decimal("0.00"),
                )
            )
        )
        for entry in entries:
            entry.posted_credit = entry.expected_credit
            entry.credit_invoice_number = f"CREDIT-{entry.invoice_number}"
            entry.posted_at = date.today()
            entry.status = RefundStatus.MATCHED
            if entry.dispute:
                entry.dispute.status = DisputeStatus.APPROVED
                entry.dispute.case.status = CaseStatus.WON
                entry.dispute.case.finding.status = FindingStatus.CREDITED
        self.db.commit()
        return entries
