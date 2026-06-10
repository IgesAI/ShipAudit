from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.models import (
    AccessorialType,
    AuditVerdict,
    CarrierCode,
    CaseStatus,
    ConfidenceClass,
    DisputeStatus,
    FindingStatus,
    RefundStatus,
    UserRole,
)


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class TenantRead(OrmModel):
    id: str
    name: str
    slug: str
    created_at: datetime


class UserRead(OrmModel):
    id: str
    tenant_id: str
    email: str
    role: UserRole
    is_active: bool


class AddressRead(OrmModel):
    id: str
    raw_line1: str
    raw_line2: str | None
    city: str
    state: str
    postal_code: str
    normalized_line1: str | None
    normalized_city: str | None
    normalized_state: str | None
    normalized_postal_code: str | None
    is_residential: bool | None
    validator: str | None
    validator_confidence: Decimal | None
    geocode_precision: str | None


class InvoiceLineRead(OrmModel):
    id: str
    shipment_id: str | None
    tracking_number: str
    service_code: str
    ship_date: date
    zone: str | None
    charge_code: str
    charge_type: AccessorialType
    description: str
    amount: Decimal
    billed_weight_lbs: Decimal | None
    provenance: dict[str, Any] = {}
    suspicion_score: int | None = None


class InvoiceRead(OrmModel):
    id: str
    carrier: CarrierCode
    invoice_number: str
    invoice_date: date
    account_number: str
    currency: str
    total_amount: Decimal
    status: str
    lines: list[InvoiceLineRead] = []


class ShipmentRead(OrmModel):
    id: str
    carrier: CarrierCode
    tracking_number: str
    service_code: str
    ship_date: date
    manifest_weight_lbs: Decimal | None
    quoted_amount: Decimal | None
    destination_address: AddressRead | None


class FindingRead(OrmModel):
    id: str
    invoice_line_id: str
    shipment_id: str | None
    finding_type: AccessorialType
    verdict: AuditVerdict
    confidence_class: ConfidenceClass
    status: FindingStatus
    severity: str
    confidence: Decimal
    billed_amount: Decimal
    expected_amount: Decimal | None
    recoverable_amount: Decimal
    explanation: str
    evidence: dict[str, Any]
    created_at: datetime


class CaseRead(OrmModel):
    id: str
    finding_id: str
    status: CaseStatus
    auto_dispute_eligible: bool
    dispute_deadline: date | None
    title: str
    summary: str
    evidence_packet: dict[str, Any]
    evidence_document: str | None
    reviewer_notes: str | None
    created_at: datetime
    updated_at: datetime


class RejectedRowRead(OrmModel):
    id: str
    raw_artifact_id: str | None
    ingest_stage: str
    row_index: int | None
    row_payload: dict[str, Any]
    failure_reasons: list[str]
    created_at: datetime


class RateCardEntryRead(OrmModel):
    id: str
    service_code: str
    discount_percent: Decimal
    discount_tier: str
    minimum_charge: Decimal
    rate_table: dict[str, Any]


class RateCardRead(OrmModel):
    id: str
    carrier: CarrierCode
    account_number: str
    name: str
    effective_start: date
    effective_end: date | None
    source_file_hash: str
    accessorial_schedule: dict[str, Any]
    entries: list[RateCardEntryRead] = []


class CaseDecision(BaseModel):
    approve: bool
    reviewer_notes: str | None = None


class DisputeRead(OrmModel):
    id: str
    case_id: str
    carrier: CarrierCode
    status: DisputeStatus
    submission_channel: str
    external_reference: str | None
    request_payload: dict[str, Any]
    response_payload: dict[str, Any]
    submitted_at: datetime | None


class RefundLedgerRead(OrmModel):
    id: str
    dispute_id: str | None
    invoice_number: str
    tracking_number: str
    charge_type: AccessorialType
    expected_credit: Decimal
    posted_credit: Decimal | None
    status: RefundStatus
    credit_invoice_number: str | None
    posted_at: date | None


class UploadResponse(BaseModel):
    invoice_id: str | None = None
    shipment_count: int = 0
    line_count: int = 0
    rejected_count: int = 0
    artifact_id: str | None = None


    rejected_rows: int


class DashboardSummary(BaseModel):
    invoices: int
    invoice_lines: int
    findings_open: int
    findings_total: int
    cases_needing_review: int
    disputes_submitted: int
    rejected_rows: int
    expected_recovery: Decimal
    posted_recovery: Decimal
    recovery_rate: Decimal
    verdict_breakdown: list[dict[str, Any]]
    surcharge_mix: list[dict[str, Any]]
    latest_findings: list[FindingRead]


class CredentialPayload(BaseModel):
    carrier: CarrierCode
    name: str
    payload: dict[str, str] = Field(default_factory=dict)
