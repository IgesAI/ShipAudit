import csv
import io
from decimal import Decimal

import pytest

from app.models import (
    AccessorialType,
    AuditVerdict,
    ConfidenceClass,
    StandardizationStatus,
)
from app.services.address_normalization import AddressNormalizationService
from app.services.audit_engine import DeterministicAuditEngine
from app.services.ingestion import (
    DEMO_FEDEX_TRACKING_1,
    DEMO_FEDEX_TRACKING_2,
    IngestionService,
    synthetic_invoice_csv,
    synthetic_manifest_csv,
)
from app.services.rate_cards import RateCardCompiler, synthetic_rate_card
from app.services.rule_repository import RuleRepository
from app.services.security import AuthService


def _csv(rows: list[dict]) -> bytes:
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
    writer.writeheader()
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def _fuel_invoice(invoice_number: str, fuel_amount: str, tracking: str = DEMO_FEDEX_TRACKING_1) -> bytes:
    base = {
        "carrier": "FEDEX",
        "invoice_number": invoice_number,
        "invoice_date": "2026-02-28",
        "account_number": "ACCT-001",
        "currency": "USD",
        "tracking_number": tracking,
        "service_code": "GROUND",
        "ship_date": "2026-02-10",
        "zone": "5",
        "charge_code": "FRT",
        "description": "Freight",
        "amount": "16.50",
        "billed_weight_lbs": "5",
        "invoice_subtotal": str(Decimal("16.50") + Decimal(fuel_amount)),
    }
    fuel = {**base, "charge_code": "FUEL", "description": "Fuel", "amount": fuel_amount}
    return _csv([base, fuel])


@pytest.fixture()
def setup(db):
    tenant, _, _ = AuthService(db).bootstrap_admin("Verdicts Co", "verdicts@example.com", "secret-pass")
    RuleRepository(db).load_seed_rules()
    RateCardCompiler(db).ingest_json(tenant, synthetic_rate_card())
    ingestion = IngestionService(db)
    ingestion.ingest_manifest_csv(tenant, "manifest.csv", synthetic_manifest_csv())
    AddressNormalizationService(db).normalize_all_for_tenant(tenant.id)
    return tenant, ingestion


def _findings_by(findings, finding_type, tracking=None):
    return [
        f
        for f in findings
        if f.finding_type == finding_type
        and (tracking is None or f.invoice_line.tracking_number == tracking)
    ]


def test_demo_invoice_verdict_taxonomy(db, setup):
    tenant, ingestion = setup
    result = ingestion.ingest_invoice_csv(tenant, "fedex.csv", synthetic_invoice_csv("FEDEX"))
    findings = DeterministicAuditEngine(db).audit_invoice(result.invoice.id)

    # Unlisted ZIP 59068 -> proven discrepancy, full claim, rule hash in evidence.
    das_unlisted = _findings_by(findings, AccessorialType.DELIVERY_AREA, DEMO_FEDEX_TRACKING_1)
    assert len(das_unlisted) == 1
    assert das_unlisted[0].verdict == AuditVerdict.DISCREPANCY
    assert das_unlisted[0].confidence_class == ConfidenceClass.PROVEN
    assert das_unlisted[0].recoverable_amount == Decimal("7.95")
    assert das_unlisted[0].evidence["rule_source_hash"]
    assert das_unlisted[0].evidence["line_provenance"]["source_sha256"]

    # Listed ZIP 80435 at the table amount -> NO_CLAIM even though it looks urban.
    das_listed = _findings_by(findings, AccessorialType.DELIVERY_AREA, DEMO_FEDEX_TRACKING_2)
    assert len(das_listed) == 1
    assert das_listed[0].verdict == AuditVerdict.NO_CLAIM
    assert das_listed[0].recoverable_amount == Decimal("0.00")

    # Fuel: 16.50 base * 16.5% = 2.72 expected vs 4.00 billed.
    fuel = _findings_by(findings, AccessorialType.FUEL)
    assert len(fuel) == 1
    assert fuel[0].verdict == AuditVerdict.DISCREPANCY
    assert fuel[0].expected_amount == Decimal("2.72")
    assert fuel[0].recoverable_amount == Decimal("1.28")

    # Contract discount: list 20.00 * 0.75 = 15.00 expected vs 16.50 billed.
    discount = _findings_by(findings, AccessorialType.CONTRACT_DISCOUNT)
    assert len(discount) == 1
    assert discount[0].verdict == AuditVerdict.DISCREPANCY
    assert discount[0].recoverable_amount == Decimal("1.50")
    assert discount[0].evidence["rate_card_hash"]

    # Duplicate RES charge -> proven duplicate discrepancy.
    duplicates = _findings_by(findings, AccessorialType.DUPLICATE_CHARGE)
    assert len(duplicates) == 1
    assert duplicates[0].verdict == AuditVerdict.DISCREPANCY
    assert duplicates[0].recoverable_amount == Decimal("5.25")

    # First RES on a 2-validator business consensus address -> STRONG discrepancy.
    residential = _findings_by(findings, AccessorialType.RESIDENTIAL)
    assert len(residential) == 1
    assert residential[0].verdict == AuditVerdict.DISCREPANCY
    assert residential[0].confidence_class == ConfidenceClass.STRONG

    # Dimensional weight inflation is REVIEW, never an auto-claim.
    dim = _findings_by(findings, AccessorialType.DIMENSIONAL_WEIGHT)
    assert dim
    assert all(f.verdict == AuditVerdict.REVIEW for f in dim)
    assert all(f.recoverable_amount == Decimal("0.00") for f in dim)


def test_missing_manifest_fails_closed(db, setup):
    tenant, ingestion = setup
    rows = [
        {
            "carrier": "FEDEX",
            "invoice_number": "INV-NOMANIFEST",
            "invoice_date": "2026-02-28",
            "account_number": "ACCT-001",
            "tracking_number": "794699999990",
            "service_code": "GROUND",
            "ship_date": "2026-02-10",
            "zone": "5",
            "charge_code": "DAS",
            "amount": "6.00",
            "invoice_subtotal": "6.00",
        }
    ]
    result = ingestion.ingest_invoice_csv(tenant, "orphan.csv", _csv(rows))
    findings = DeterministicAuditEngine(db).audit_invoice(result.invoice.id)

    assert len(findings) == 1
    assert findings[0].verdict == AuditVerdict.FAIL_MISSING_SOURCE
    assert findings[0].confidence_class == ConfidenceClass.INSUFFICIENT
    assert findings[0].recoverable_amount == Decimal("0.00")
    assert findings[0].evidence["missing_source"] == "shipment_manifest"


def test_base_rate_without_rate_card_fails_closed(db):
    tenant, _, _ = AuthService(db).bootstrap_admin("NoCard Co", "nocard@example.com", "secret-pass")
    RuleRepository(db).load_seed_rules()
    ingestion = IngestionService(db)
    ingestion.ingest_manifest_csv(tenant, "manifest.csv", synthetic_manifest_csv())
    AddressNormalizationService(db).normalize_all_for_tenant(tenant.id)
    rows = [
        {
            "carrier": "FEDEX",
            "invoice_number": "INV-NOCARD",
            "invoice_date": "2026-02-28",
            "account_number": "ACCT-001",
            "tracking_number": DEMO_FEDEX_TRACKING_1,
            "service_code": "GROUND",
            "ship_date": "2026-02-10",
            "zone": "5",
            "charge_code": "FRT",
            "amount": "16.50",
            "billed_weight_lbs": "5",
            "invoice_subtotal": "16.50",
        }
    ]
    result = ingestion.ingest_invoice_csv(tenant, "nocard.csv", _csv(rows))
    findings = DeterministicAuditEngine(db).audit_invoice(result.invoice.id)

    contract = [f for f in findings if f.finding_type == AccessorialType.CONTRACT_DISCOUNT]
    assert len(contract) == 1
    assert contract[0].verdict == AuditVerdict.FAIL_MISSING_SOURCE
    assert contract[0].evidence["missing_source"] == "rate_card"


def test_fuel_tolerance_boundary(db, setup):
    tenant, ingestion = setup
    # Expected fuel: 16.50 * 0.165 = 2.7225 -> 2.72. Billed 2.73 is within +/-0.01.
    within = ingestion.ingest_invoice_csv(tenant, "fuel_ok.csv", _fuel_invoice("INV-FUEL-OK", "2.73"))
    findings = DeterministicAuditEngine(db).audit_invoice(within.invoice.id)
    fuel = [f for f in findings if f.finding_type == AccessorialType.FUEL]
    assert len(fuel) == 1
    assert fuel[0].verdict == AuditVerdict.PASS

    # Different tracking so the duplicate-charge check does not short-circuit.
    over = ingestion.ingest_invoice_csv(
        tenant, "fuel_bad.csv", _fuel_invoice("INV-FUEL-BAD", "2.74", tracking=DEMO_FEDEX_TRACKING_2)
    )
    findings = DeterministicAuditEngine(db).audit_invoice(over.invoice.id)
    fuel = [f for f in findings if f.finding_type == AccessorialType.FUEL]
    assert len(fuel) == 1
    assert fuel[0].verdict == AuditVerdict.DISCREPANCY
    assert fuel[0].recoverable_amount == Decimal("0.02")


def test_validator_conflict_routes_residential_to_review(db, setup):
    tenant, ingestion = setup
    result = ingestion.ingest_invoice_csv(tenant, "ups.csv", synthetic_invoice_csv("UPS"))
    line = next(
        item for item in result.invoice.lines if item.charge_type == AccessorialType.RESIDENTIAL
    )
    address = line.shipment.destination_address
    address.standardization_status = StandardizationStatus.STANDARDIZED
    address.dpv_confirmed = True
    address.validator_results = [
        {"validator": "a", "is_residential": False},
        {"validator": "b", "is_residential": True},
    ]
    db.commit()

    findings = DeterministicAuditEngine(db).audit_invoice(result.invoice.id)
    residential = [f for f in findings if f.finding_type == AccessorialType.RESIDENTIAL]
    assert len(residential) == 1
    assert residential[0].verdict == AuditVerdict.REVIEW
    assert residential[0].confidence_class == ConfidenceClass.CONFLICTED
    assert residential[0].recoverable_amount == Decimal("0.00")
