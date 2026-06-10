import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.neighbors import LocalOutlierFactor
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AccessorialType, InvoiceLine


class AnomalyDetectionService:
    """Analytics-only anomaly triage.

    Suspicion scores are stored on the invoice line for dashboards and
    exception review. They never create findings, never feed the dispute
    pipeline, and never override deterministic verdicts: the audit decision is
    made exclusively by the rule engine against carrier sources.
    """

    def __init__(self, db: Session) -> None:
        self.db = db

    def score_tenant(self, tenant_id: str) -> int:
        lines = list(
            self.db.scalars(
                select(InvoiceLine)
                .join(InvoiceLine.invoice)
                .where(InvoiceLine.invoice.has(tenant_id=tenant_id))
            )
        )
        if len(lines) < 5:
            return 0
        frame = self._feature_frame(lines)
        if frame.empty:
            return 0

        numeric = frame.drop(columns=["line_id"])
        isolation = IsolationForest(contamination=min(0.2, max(0.05, 2 / len(frame))), random_state=42)
        iso_scores = -isolation.fit_predict(numeric)
        if len(frame) > 20:
            lof = LocalOutlierFactor(n_neighbors=min(10, len(frame) - 1), contamination=0.1)
            lof_scores = -lof.fit_predict(numeric)
        else:
            lof_scores = [0 for _ in range(len(frame))]

        flagged = 0
        for idx, row in frame.iterrows():
            combined = int(iso_scores[idx]) + int(lof_scores[idx])
            line = next(item for item in lines if item.id == row["line_id"])
            line.suspicion_score = combined
            line.suspicion_detail = {
                "model": "IsolationForest+LOF",
                "combined_score": combined,
                "analytics_only": True,
                "note": "Suspicion flags prioritize human review; they are never dispute evidence.",
                "features": {k: float(v) for k, v in numeric.iloc[idx].to_dict().items()},
            }
            self.db.add(line)
            if combined >= 1:
                flagged += 1
        self.db.commit()
        return flagged

    def _feature_frame(self, lines: list[InvoiceLine]) -> pd.DataFrame:
        rows = []
        lane_medians: dict[tuple[str, str, str | None], object] = {}
        for line in lines:
            carrier = line.invoice.carrier.value
            key = (carrier, line.service_code, line.zone)
            lane_medians.setdefault(key, None)
        for key in lane_medians:
            amounts = sorted(
                line.amount
                for line in lines
                if (line.invoice.carrier.value, line.service_code, line.zone) == key
            )
            lane_medians[key] = amounts[len(amounts) // 2]
        for line in lines:
            shipment = line.shipment
            address = shipment.destination_address if shipment else None
            dims = [
                float(line.billed_length_in or 0),
                float(line.billed_width_in or 0),
                float(line.billed_height_in or 0),
            ]
            carrier = line.invoice.carrier.value
            key = (carrier, line.service_code, line.zone)
            median = lane_medians.get(key) or 0
            rows.append(
                {
                    "line_id": line.id,
                    "amount": float(line.amount),
                    "amount_vs_lane_median": float(line.amount) - float(median),
                    "billed_weight_lbs": float(line.billed_weight_lbs or 0),
                    "manifest_weight_lbs": float(shipment.manifest_weight_lbs if shipment else 0),
                    "weight_delta": float(line.billed_weight_lbs or 0)
                    - float(shipment.manifest_weight_lbs if shipment and shipment.manifest_weight_lbs else 0),
                    "dim_volume": dims[0] * dims[1] * dims[2],
                    "is_accessorial": 1.0 if line.charge_type != AccessorialType.BASE_RATE else 0.0,
                    "is_residential": 1.0 if address and address.is_residential else 0.0,
                    "has_rooftop_precision": 1.0
                    if address and address.geocode_precision == "rooftop"
                    else 0.0,
                    "quoted_amount": float(shipment.quoted_amount if shipment and shipment.quoted_amount else 0),
                }
            )
        return pd.DataFrame(rows)
