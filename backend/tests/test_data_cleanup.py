from sqlalchemy import select

from app.models import Finding, Invoice, RejectedRow
from app.services.data_cleanup import DataCleanupService
from app.services.ingestion import IngestionService, synthetic_invoice_csv
from app.services.security import AuthService


def test_delete_invoice_removes_findings(db):
    tenant, _, _ = AuthService(db).bootstrap_admin("Cleanup Co", "cleanup@example.com", "secret-pass")
    result = IngestionService(db).ingest_invoice_csv(tenant, "inv.csv", synthetic_invoice_csv("UPS"))
    invoice_id = result.invoice.id

    from app.services.audit_engine import DeterministicAuditEngine

    DeterministicAuditEngine(db).audit_invoice(invoice_id)
    assert db.scalars(select(Finding)).all()

    removed = DataCleanupService(db).delete_invoice(tenant.id, invoice_id)
    assert removed["invoices"] == 1
    assert removed["findings"] >= 1
    assert db.get(Invoice, invoice_id) is None
    assert not db.scalars(select(Finding)).all()


def test_clear_rejected_rows(db):
    tenant, _, _ = AuthService(db).bootstrap_admin("Reject Co", "reject@example.com", "secret-pass")
    IngestionService(db).ingest_carrier_export(tenant, "bad.csv", b"foo,bar\n1,2\n")
    assert db.scalars(select(RejectedRow).where(RejectedRow.tenant_id == tenant.id)).all()

    removed = DataCleanupService(db).clear_rejected_rows(tenant.id)
    assert removed >= 1
    assert not db.scalars(select(RejectedRow).where(RejectedRow.tenant_id == tenant.id)).all()
