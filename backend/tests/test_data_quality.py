from app.services.address_normalization import AddressNormalizationService
from app.services.data_quality import DataQualityService
from app.services.ingestion import IngestionService, synthetic_manifest_csv
from app.services.rule_repository import RuleRepository
from app.services.security import AuthService


def test_data_quality_passes_for_seeded_demo(db):
    tenant, _, _ = AuthService(db).bootstrap_admin("Demo Shipper", "admin@example.com", "secret-pass")
    RuleRepository(db).load_seed_rules()
    IngestionService(db).ingest_manifest_csv(tenant, "manifest.csv", synthetic_manifest_csv())
    AddressNormalizationService(db).normalize_all_for_tenant(tenant.id)

    issues = DataQualityService(db).validate_all(tenant.id)

    assert issues == []
