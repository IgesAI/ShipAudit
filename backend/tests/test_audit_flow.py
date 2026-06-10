from decimal import Decimal

from sqlalchemy import select

from app.models import (
    AuditVerdict,
    Case,
    CaseStatus,
    Dispute,
    RefundLedger,
    Shipment,
)
from app.services.address_normalization import AddressNormalizationService
from app.services.audit_engine import DeterministicAuditEngine
from app.services.case_builder import CaseBuilder
from app.services.dispute_adapters import DisputeOrchestrator
from app.services.ingestion import IngestionService, synthetic_invoice_csv, synthetic_manifest_csv
from app.services.ledger import RefundLedgerService
from app.services.rate_cards import RateCardCompiler, synthetic_rate_card
from app.services.rule_repository import RuleRepository
from app.services.security import AuthService


def test_end_to_end_audit_flow(db):
    tenant, _, _ = AuthService(db).bootstrap_admin("Demo Shipper", "admin@example.com", "secret-pass")
    assert RuleRepository(db).load_seed_rules() > 0
    RateCardCompiler(db).ingest_json(tenant, synthetic_rate_card())

    ingestion = IngestionService(db)
    manifest_result = ingestion.ingest_manifest_csv(tenant, "manifest.csv", synthetic_manifest_csv())
    assert manifest_result.accepted_rows == 3
    assert manifest_result.rejected_count == 0

    invoice_result = ingestion.ingest_invoice_csv(tenant, "fedex.csv", synthetic_invoice_csv("FEDEX"))
    assert invoice_result.invoice is not None
    assert invoice_result.accepted_rows == 7
    assert invoice_result.rejected_count == 1  # the missing-tracking row fails closed

    assert db.scalar(select(Shipment).where(Shipment.tenant_id == tenant.id)) is not None
    assert AddressNormalizationService(db).normalize_all_for_tenant(tenant.id) == 6

    findings = DeterministicAuditEngine(db).audit_invoice(invoice_result.invoice.id)
    assert findings
    discrepancies = [f for f in findings if f.verdict == AuditVerdict.DISCREPANCY]
    assert discrepancies
    assert all(f.recoverable_amount > Decimal("0") for f in discrepancies)

    cases = CaseBuilder(db).build_cases_for_tenant(tenant.id)
    assert cases
    # FedEx cases must always require human approval before submission.
    assert all(case.status == CaseStatus.NEEDS_REVIEW for case in cases)
    assert all(case.dispute_deadline is not None for case in cases)
    assert all(case.evidence_document for case in cases)

    orchestrator = DisputeOrchestrator(db)
    # Without approval, nothing submits for FedEx.
    assert orchestrator.submit_ready_cases(tenant.id) == []
    for case in db.scalars(select(Case).where(Case.tenant_id == tenant.id)):
        orchestrator.approve_case(case.id, approve=True, notes="reviewed")
    disputes = orchestrator.submit_ready_cases(tenant.id)
    assert disputes
    assert all(d.submission_channel == "human_in_loop" for d in disputes)
    assert db.scalar(select(Dispute).where(Dispute.tenant_id == tenant.id)) is not None

    ledger = RefundLedgerService(db)
    entries = ledger.create_expected_credits(tenant.id)
    assert entries
    posted = ledger.simulate_posted_credits(tenant.id)
    assert posted
    assert db.scalar(select(RefundLedger).where(RefundLedger.tenant_id == tenant.id)).posted_credit is not None
