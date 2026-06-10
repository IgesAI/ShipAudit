from datetime import date

from app.models import CarrierCode
from app.services.rule_repository import RuleRepository


def test_effective_area_rule_lookup(db):
    repo = RuleRepository(db)
    repo.load_seed_rules()

    result = repo.area_rule_for_zip(CarrierCode.UPS, "99501-1234", date(2026, 2, 1))

    assert result is not None
    assert result["finding_type"] == "REMOTE_AREA"
    assert result["tier"] == "remote"


def test_fuel_percent_lookup(db):
    repo = RuleRepository(db)
    repo.load_seed_rules()

    rule, percent = repo.fuel_percent(CarrierCode.FEDEX, date(2026, 2, 1))

    assert rule.rule_type == "FUEL_SCHEDULE"
    assert percent == 0.165
