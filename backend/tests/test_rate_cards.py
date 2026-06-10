from datetime import date
from decimal import Decimal

import pytest

from app.models import CarrierCode
from app.services.rate_cards import RateCardCompiler, RateCardValidationError, synthetic_rate_card
from app.services.security import AuthService


@pytest.fixture()
def tenant(db):
    tenant, _, _ = AuthService(db).bootstrap_admin("Rates Co", "rates@example.com", "secret-pass")
    return tenant


def test_rate_card_missing_effective_date_hard_fails(db, tenant):
    document = synthetic_rate_card()
    document["effective_start"] = None

    with pytest.raises(RateCardValidationError) as exc:
        RateCardCompiler(db).ingest_json(tenant, document)
    assert any("effective_start" in reason for reason in exc.value.reasons)


def test_rate_card_missing_minimum_charge_hard_fails(db, tenant):
    document = synthetic_rate_card()
    del document["services"][0]["minimum_charge"]

    with pytest.raises(RateCardValidationError) as exc:
        RateCardCompiler(db).ingest_json(tenant, document)
    assert any("minimum_charge" in reason for reason in exc.value.reasons)


def test_effective_entry_lookup_by_date(db, tenant):
    compiler = RateCardCompiler(db)
    compiler.ingest_json(tenant, synthetic_rate_card())

    hit = compiler.effective_entry(
        tenant.id, CarrierCode.FEDEX, "ACCT-001", "GROUND", date(2026, 2, 10)
    )
    assert hit is not None
    card, entry = hit
    assert entry.discount_percent == Decimal("0.25")
    assert entry.minimum_charge == Decimal("9.50")

    miss_before = compiler.effective_entry(
        tenant.id, CarrierCode.FEDEX, "ACCT-001", "GROUND", date(2025, 12, 31)
    )
    assert miss_before is None

    miss_account = compiler.effective_entry(
        tenant.id, CarrierCode.FEDEX, "OTHER-ACCT", "GROUND", date(2026, 2, 10)
    )
    assert miss_account is None


def test_list_rate_exact_cell_lookup(db, tenant):
    compiler = RateCardCompiler(db)
    card = compiler.ingest_json(tenant, synthetic_rate_card())
    entry = card.entries[0]

    assert RateCardCompiler.list_rate(entry, "5", Decimal("5")) == Decimal("20.00")
    assert RateCardCompiler.list_rate(entry, "5", Decimal("99")) is None
    assert RateCardCompiler.list_rate(entry, "9", Decimal("5")) is None


def test_duplicate_ingest_is_idempotent(db, tenant):
    compiler = RateCardCompiler(db)
    first = compiler.ingest_json(tenant, synthetic_rate_card())
    second = compiler.ingest_json(tenant, synthetic_rate_card())
    assert first.id == second.id
