import json
from decimal import Decimal

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.models import (
    AuditVerdict,
    CarrierCode,
    Case,
    CaseStatus,
    Dispute,
    DisputeStatus,
    Finding,
    FindingStatus,
    Invoice,
    InvoiceLine,
    RateCard,
    RefundLedger,
    RefundStatus,
    RejectedRow,
    Shipment,
    Tenant,
)
from app.schemas import (
    CaseDecision,
    CaseRead,
    DashboardSummary,
    DisputeRead,
    FindingRead,
    InvoiceRead,
    PdfConfirmRequest,
    PdfIngestResponse,
    RateCardRead,
    RefundLedgerRead,
    RejectedRowRead,
    ShipmentRead,
    UploadResponse,
)
from app.services.address_normalization import AddressNormalizationService
from app.services.anomaly import AnomalyDetectionService
from app.services.audit_engine import DeterministicAuditEngine
from app.services.case_builder import CaseBuilder
from app.services.data_cleanup import DataCleanupService
from app.services.dispute_adapters import DisputeOrchestrator
from app.services.ingestion import IngestionService
from app.services.ledger import RefundLedgerService
from app.services.rate_cards import RateCardCompiler, RateCardValidationError
from app.services.rule_repository import RuleRepository
from app.services.security import AuthService

router = APIRouter(prefix="/api")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "shipaudit"}


def default_tenant(db: Session) -> Tenant:
    tenant = db.scalar(select(Tenant).where(Tenant.slug == "demo-shipper"))
    if tenant:
        return tenant
    auth = AuthService(db)
    tenant, _, _ = auth.bootstrap_admin("Demo Shipper", "admin@shipaudit.local", "shipaudit-demo")
    return tenant


@router.post("/rules/seed")
def seed_rules(db: Session = Depends(get_db)) -> dict[str, int]:
    count = RuleRepository(db).load_seed_rules()
    return {"inserted": count}


@router.post("/ingest/invoices", response_model=UploadResponse)
async def upload_invoice(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> UploadResponse:
    tenant = default_tenant(db)
    content = await file.read()
    result = IngestionService(db).ingest_invoice_csv(
        tenant, file.filename or "invoice.csv", content, file.content_type or "text/csv"
    )
    return UploadResponse(
        invoice_id=result.invoice.id if result.invoice else None,
        line_count=result.accepted_rows,
        rejected_count=result.rejected_count,
        artifact_id=result.artifact.id if result.artifact else None,
    )


@router.post("/ingest/carrier-export", response_model=UploadResponse)
async def upload_carrier_export(
    file: UploadFile = File(...),
    carrier: str | None = Query(
        default=None,
        description="Optional carrier hint (UPS or FEDEX). If omitted, the format is auto-detected.",
    ),
    db: Session = Depends(get_db),
) -> UploadResponse:
    tenant = default_tenant(db)
    content = await file.read()
    results = IngestionService(db).ingest_carrier_export(
        tenant,
        file.filename or "carrier_export.csv",
        content,
        carrier_hint=carrier,
        content_type=file.content_type or "text/csv",
    )
    invoice_ids = [r.invoice.id for r in results if r.invoice]
    artifact = next((r.artifact for r in results if r.artifact), None)
    return UploadResponse(
        invoice_id=invoice_ids[0] if invoice_ids else None,
        invoice_count=len(invoice_ids),
        line_count=sum(r.accepted_rows for r in results),
        rejected_count=sum(r.rejected_count for r in results),
        artifact_id=artifact.id if artifact else None,
    )


@router.post("/ingest/pdf", response_model=PdfIngestResponse)
async def upload_pdf_invoice(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> PdfIngestResponse:
    tenant = default_tenant(db)
    content = await file.read()
    artifact, rejection = IngestionService(db).ingest_pdf(
        tenant, file.filename or "invoice.pdf", content
    )
    meta = artifact.metadata_json or {}
    unmappable = meta.get("status") == "unmappable"
    reason = "; ".join(rejection.failure_reasons) if rejection else None
    if unmappable and not reason:
        table_count = int(meta.get("extracted_table_count", 0))
        headers = list(meta.get("extracted_headers", []))
        header_hint = f" Columns found: {', '.join(headers[:8])}." if headers else ""
        reason = (
            f"OCR read the PDF ({meta.get('ocr_confidence')}) but found {table_count} table(s) "
            f"that do not match UPS/FedEx billing export headers.{header_hint} "
            "Download the CSV from UPS Billing Center or FedEx Billing Online instead."
        )
    return PdfIngestResponse(
        artifact_id=artifact.id,
        status=str(meta.get("status", "unknown")),
        ocr_confidence=meta.get("ocr_confidence"),
        min_confidence_required=meta.get("min_confidence_required"),
        rejected=rejection is not None or unmappable,
        reason=reason,
        candidate_invoice_count=int(meta.get("candidate_invoice_count", 0)),
        candidate_rows=list(meta.get("candidate_rows", [])),
        extracted_table_count=int(meta.get("extracted_table_count", 0)),
        extracted_headers=list(meta.get("extracted_headers", [])),
    )


@router.post("/ingest/pdf/confirm", response_model=UploadResponse)
async def confirm_pdf_invoice(
    payload: PdfConfirmRequest,
    db: Session = Depends(get_db),
) -> UploadResponse:
    tenant = default_tenant(db)
    try:
        results = IngestionService(db).confirm_pdf_extraction(
            tenant, payload.artifact_id, payload.rows
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    invoice_ids = [r.invoice.id for r in results if r.invoice]
    return UploadResponse(
        invoice_id=invoice_ids[0] if invoice_ids else None,
        invoice_count=len(invoice_ids),
        line_count=sum(r.accepted_rows for r in results),
        rejected_count=sum(r.rejected_count for r in results),
        artifact_id=payload.artifact_id,
    )


@router.post("/ingest/manifests", response_model=UploadResponse)
async def upload_manifest(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> UploadResponse:
    tenant = default_tenant(db)
    content = await file.read()
    result = IngestionService(db).ingest_manifest_csv(tenant, file.filename or "manifest.csv", content)
    return UploadResponse(
        shipment_count=result.accepted_rows,
        rejected_count=result.rejected_count,
        artifact_id=result.artifact.id if result.artifact else None,
    )


@router.post("/ingest/rate-cards", response_model=RateCardRead)
async def upload_rate_card(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> RateCard:
    tenant = default_tenant(db)
    content = await file.read()
    try:
        document = json.loads(content)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=422, detail=f"rate card is not valid JSON: {exc}") from exc
    ingestion = IngestionService(db)
    artifact = ingestion.store_artifact(
        tenant.id, "rate_card", file.filename or "rate_card.json", content, "application/json"
    )
    try:
        return RateCardCompiler(db).ingest_json(tenant, document, source_artifact_id=artifact.id)
    except RateCardValidationError as exc:
        raise HTTPException(status_code=422, detail={"failure_reasons": exc.reasons}) from exc


@router.get("/rate-cards", response_model=list[RateCardRead])
def list_rate_cards(db: Session = Depends(get_db)) -> list[RateCard]:
    tenant = default_tenant(db)
    return list(
        db.scalars(
            select(RateCard)
            .where(RateCard.tenant_id == tenant.id)
            .options(selectinload(RateCard.entries))
            .order_by(RateCard.carrier, RateCard.effective_start.desc())
        )
    )


@router.get("/rejected-rows", response_model=list[RejectedRowRead])
def list_rejected_rows(db: Session = Depends(get_db)) -> list[RejectedRow]:
    tenant = default_tenant(db)
    return list(
        db.scalars(
            select(RejectedRow)
            .where(RejectedRow.tenant_id == tenant.id)
            .order_by(RejectedRow.created_at.desc())
            .limit(500)
        )
    )


@router.delete("/invoices/{invoice_id}")
def delete_invoice(invoice_id: str, db: Session = Depends(get_db)) -> dict[str, int]:
    tenant = default_tenant(db)
    try:
        return DataCleanupService(db).delete_invoice(tenant.id, invoice_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/rejected-rows")
def clear_rejected_rows(db: Session = Depends(get_db)) -> dict[str, int]:
    tenant = default_tenant(db)
    removed = DataCleanupService(db).clear_rejected_rows(tenant.id)
    return {"removed": removed}


@router.post("/audit/invoices/{invoice_id}", response_model=list[FindingRead])
def audit_invoice(invoice_id: str, db: Session = Depends(get_db)) -> list[Finding]:
    invoice = db.get(Invoice, invoice_id)
    if not invoice:
        raise HTTPException(status_code=404, detail=f"invoice not found: {invoice_id}")
    AddressNormalizationService(db).normalize_all_for_tenant(invoice.tenant_id)
    findings = DeterministicAuditEngine(db).audit_invoice(invoice_id)
    AnomalyDetectionService(db).score_tenant(invoice.tenant_id)
    return findings


@router.post("/cases/build", response_model=list[CaseRead])
def build_cases(db: Session = Depends(get_db)) -> list[Case]:
    tenant = default_tenant(db)
    return CaseBuilder(db).build_cases_for_tenant(tenant.id)


@router.post("/cases/{case_id}/decision", response_model=CaseRead)
def decide_case(case_id: str, decision: CaseDecision, db: Session = Depends(get_db)) -> Case:
    try:
        return DisputeOrchestrator(db).approve_case(case_id, decision.approve, decision.reviewer_notes)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/disputes/submit-ready", response_model=list[DisputeRead])
def submit_ready(db: Session = Depends(get_db)) -> list[Dispute]:
    tenant = default_tenant(db)
    disputes = DisputeOrchestrator(db).submit_ready_cases(tenant.id)
    RefundLedgerService(db).create_expected_credits(tenant.id)
    return disputes


@router.get("/invoices", response_model=list[InvoiceRead])
def list_invoices(
    carrier: CarrierCode | None = None,
    db: Session = Depends(get_db),
) -> list[Invoice]:
    tenant = default_tenant(db)
    query = (
        select(Invoice)
        .where(Invoice.tenant_id == tenant.id)
        .options(selectinload(Invoice.lines))
        .order_by(Invoice.invoice_date.desc())
    )
    if carrier is not None:
        query = query.where(Invoice.carrier == carrier)
    return list(db.scalars(query))


@router.get("/shipments", response_model=list[ShipmentRead])
def list_shipments(db: Session = Depends(get_db)) -> list[Shipment]:
    tenant = default_tenant(db)
    return list(
        db.scalars(
            select(Shipment)
            .where(Shipment.tenant_id == tenant.id)
            .options(selectinload(Shipment.destination_address))
            .order_by(Shipment.ship_date.desc())
        )
    )


@router.get("/findings", response_model=list[FindingRead])
def list_findings(
    verdict: AuditVerdict | None = None,
    carrier: CarrierCode | None = None,
    invoice_id: str | None = None,
    db: Session = Depends(get_db),
) -> list[Finding]:
    tenant = default_tenant(db)
    query = select(Finding).where(Finding.tenant_id == tenant.id)
    if verdict is not None:
        query = query.where(Finding.verdict == verdict)
    if carrier is not None or invoice_id is not None:
        query = query.join(InvoiceLine, Finding.invoice_line_id == InvoiceLine.id).join(
            Invoice, InvoiceLine.invoice_id == Invoice.id
        )
        if carrier is not None:
            query = query.where(Invoice.carrier == carrier)
        if invoice_id is not None:
            query = query.where(Invoice.id == invoice_id)
    return list(db.scalars(query.order_by(Finding.created_at.desc()).limit(200)))


@router.get("/cases", response_model=list[CaseRead])
def list_cases(db: Session = Depends(get_db)) -> list[Case]:
    tenant = default_tenant(db)
    return list(db.scalars(select(Case).where(Case.tenant_id == tenant.id).order_by(Case.created_at.desc())))


@router.get("/disputes", response_model=list[DisputeRead])
def list_disputes(db: Session = Depends(get_db)) -> list[Dispute]:
    tenant = default_tenant(db)
    return list(db.scalars(select(Dispute).where(Dispute.tenant_id == tenant.id).order_by(Dispute.created_at.desc())))


@router.get("/refunds", response_model=list[RefundLedgerRead])
def list_refunds(db: Session = Depends(get_db)) -> list[RefundLedger]:
    tenant = default_tenant(db)
    return list(
        db.scalars(select(RefundLedger).where(RefundLedger.tenant_id == tenant.id).order_by(RefundLedger.created_at.desc()))
    )


@router.get("/dashboard", response_model=DashboardSummary)
def dashboard(db: Session = Depends(get_db)) -> DashboardSummary:
    tenant = default_tenant(db)
    expected = db.scalar(
        select(func.coalesce(func.sum(RefundLedger.expected_credit), 0)).where(RefundLedger.tenant_id == tenant.id)
    ) or Decimal("0.00")
    posted = db.scalar(
        select(func.coalesce(func.sum(RefundLedger.posted_credit), 0)).where(
            RefundLedger.tenant_id == tenant.id,
            RefundLedger.status == RefundStatus.MATCHED,
        )
    ) or Decimal("0.00")
    verdict_rows = db.execute(
        select(Finding.verdict, func.count(Finding.id), func.coalesce(func.sum(Finding.recoverable_amount), 0))
        .where(Finding.tenant_id == tenant.id)
        .group_by(Finding.verdict)
        .order_by(func.count(Finding.id).desc())
    ).all()
    mix_rows = db.execute(
        select(Finding.finding_type, func.count(Finding.id), func.coalesce(func.sum(Finding.recoverable_amount), 0))
        .where(Finding.tenant_id == tenant.id, Finding.verdict == AuditVerdict.DISCREPANCY)
        .group_by(Finding.finding_type)
        .order_by(func.count(Finding.id).desc())
    ).all()
    latest = list(
        db.scalars(
            select(Finding)
            .where(Finding.tenant_id == tenant.id)
            .order_by(Finding.created_at.desc())
            .limit(8)
        )
    )
    return DashboardSummary(
        invoices=db.scalar(select(func.count(Invoice.id)).where(Invoice.tenant_id == tenant.id)) or 0,
        invoice_lines=db.scalar(
            select(func.count(InvoiceLine.id)).join(Invoice).where(Invoice.tenant_id == tenant.id)
        )
        or 0,
        findings_open=db.scalar(
            select(func.count(Finding.id)).where(Finding.tenant_id == tenant.id, Finding.status == FindingStatus.OPEN)
        )
        or 0,
        findings_total=db.scalar(select(func.count(Finding.id)).where(Finding.tenant_id == tenant.id)) or 0,
        cases_needing_review=db.scalar(
            select(func.count(Case.id)).where(Case.tenant_id == tenant.id, Case.status == CaseStatus.NEEDS_REVIEW)
        )
        or 0,
        disputes_submitted=db.scalar(
            select(func.count(Dispute.id)).where(
                Dispute.tenant_id == tenant.id,
                Dispute.status.in_([DisputeStatus.SUBMITTED, DisputeStatus.APPROVED]),
            )
        )
        or 0,
        rejected_rows=db.scalar(
            select(func.count(RejectedRow.id)).where(RejectedRow.tenant_id == tenant.id)
        )
        or 0,
        expected_recovery=expected,
        posted_recovery=posted,
        recovery_rate=(posted / expected).quantize(Decimal("0.01")) if expected else Decimal("0.00"),
        verdict_breakdown=[
            {"verdict": row[0].value, "count": row[1], "recoverable": str(row[2])} for row in verdict_rows
        ],
        surcharge_mix=[
            {"type": row[0].value, "count": row[1], "recoverable": str(row[2])} for row in mix_rows
        ],
        latest_findings=latest,
    )
