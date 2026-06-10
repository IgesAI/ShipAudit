export type DocSection = {
  id: string;
  title: string;
  subtitle: string;
  icon: "book" | "shield" | "upload" | "scale" | "map" | "gavel" | "play" | "layers";
  content: string;
};

export const DOC_SECTIONS: DocSection[] = [
  {
    id: "getting-started",
    title: "Getting Started",
    subtitle: "What ShipAudit is and how to run your first audit",
    icon: "book",
    content: `
## Welcome to ShipAudit

ShipAudit is a **fail-closed parcel invoice audit platform**. It ingests carrier invoices, normalizes every charge line, and compares billed amounts against **machine-readable facts** — effective-dated rate cards, carrier surcharge ZIP lists, and fuel tables.

The system never guesses. If a required source is missing, the line receives \`FAIL_MISSING_SOURCE\` and no dispute case is created.

### Quick start (local)

1. Start the stack: \`docker compose up --build\`
2. Open the dashboard at \`http://localhost:3000\`
3. Go to **Upload & Audit** and load the carrier rule tables
4. Upload your rate card (JSON) and carrier invoice export (CSV)
5. Run the audit, then review findings by verdict, rejected rows, and dispute cases

### What you need before auditing real invoices

| Input | Purpose |
|-------|---------|
| Invoice file (CSV/PDF) | Source billing data with tracking numbers |
| Rate card (JSON) | Contract discounts, minimums, service rates |
| Carrier rule tables | ZIP lists, fuel %, surcharge amounts |
| Address validators (optional) | Residential vs commercial consensus |

Without these inputs, ShipAudit refuses to act rather than inventing numbers.
`,
  },
  {
    id: "fail-closed",
    title: "Fail-Closed Architecture",
    subtitle: "Prove overbilling or refuse to act — no AI guessing",
    icon: "shield",
    content: `
## The fail-closed principle

Traditional audit tools often flag anomalies and let humans sort them out. ShipAudit inverts that model:

> **Every finding must cite an exact, versioned source.** If the source does not exist, the system stops.

### What "fail-closed" means in practice

- **Missing rate card** → \`FAIL_MISSING_SOURCE\`, not an estimated rate
- **ZIP not in carrier list** → \`NO_CLAIM\` (carrier says it's not rural), even if a map looks urban
- **OCR confidence below threshold** → row rejected at ingestion, never silently parsed
- **Conflicting address validators** → \`REVIEW\`, not auto-dispute
- **Anomaly scores** → analytics flags on invoice lines only; they never create findings

### Confidence classes

| Class | Meaning |
|-------|---------|
| \`DETERMINISTIC\` | Math proof from cited sources (discount mismatch, fuel recalc) |
| \`RULE_BASED\` | Carrier rule table match (ZIP membership, duplicate charge) |
| \`CONSENSUS\` | Multiple validators agree (residential dispute) |
| \`HUMAN_REQUIRED\` | Needs reviewer before any carrier submission |

Only \`DISCREPANCY\` findings with sufficient confidence become dispute cases.
`,
  },
  {
    id: "ingestion",
    title: "Ingestion & Rejection",
    subtitle: "Strict invoice compiler — every row validated or rejected",
    icon: "upload",
    content: `
## Invoice ingestion pipeline

Ingestion is a **compiler**, not a parser that silently fills gaps. Each row passes through hard gates:

### Required fields per line

- Tracking number (carrier-specific regex)
- Service type / charge code (mapped, never silently defaulted to OTHER)
- Billed amount and currency
- Ship date within invoice billing period
- Origin and destination postal codes

### Reconciliation gates

- Invoice subtotal must reconcile to line sums within **±$0.05**
- Duplicate tracking + charge code combinations are flagged
- OCR confidence must exceed the configured threshold

### Rejection outcomes

Rejected rows land in the **Rejected Rows** panel with:

- \`ingest_stage\` — where validation failed
- \`row_index\` — source row number
- \`failure_reasons\` — explicit, machine-readable causes

**Nothing rejected is audited.** Fix the source file and re-ingest.

### Example rejection reasons

\`\`\`
tracking_number: does not match FedEx pattern (^[0-9]{12,22}$)
charge_code: unmapped carrier code "FUEL_ADJ" — add mapping or reject
subtotal_reconciliation: header $1,240.00 vs lines $1,239.92 (delta $0.08)
\`\`\`
`,
  },
  {
    id: "rate-cards",
    title: "Rate Cards & Contracts",
    subtitle: "Effective-dated contract rates with hard-fail validation",
    icon: "layers",
    content: `
## Rate card compiler

Rate cards encode your **negotiated contract** with a carrier. ShipAudit compiles them with strict validation:

### Required structure

\`\`\`json
{
  "carrier": "FEDEX",
  "account_number": "123456789",
  "effective_from": "2025-01-01",
  "effective_to": "2025-12-31",
  "entries": [
    {
      "service": "FEDEX_GROUND",
      "zone": "2",
      "weight_lb": 5,
      "rate": 8.42,
      "discount_pct": 0.32
    }
  ]
}
\`\`\`

### Compiler rules

- Effective dates must not overlap for the same carrier + account
- Every entry needs service, zone, weight breakpoint, and rate
- Source file is hashed (\`source_file_hash\`) for audit trail
- Lookup is by carrier + account + service + ship date + zone + weight

### Missing rate card behavior

If no compiled rate card covers the invoice's billing period:

- Contract discount checks → \`FAIL_MISSING_SOURCE\`
- Minimum charge checks → \`FAIL_MISSING_SOURCE\`
- Published rate comparison → \`FAIL_MISSING_SOURCE\`

Upload on the **Upload & Audit** page or via \`POST /api/ingest/rate-cards\`.
`,
  },
  {
    id: "verdicts",
    title: "Verdict Taxonomy",
    subtitle: "Every audited line resolves to exactly one verdict",
    icon: "scale",
    content: `
## Verdict types

Every invoice line that passes ingestion receives exactly one audit verdict:

| Verdict | Meaning | Creates case? |
|---------|---------|---------------|
| \`PASS\` | Billed amount matches cited sources | No |
| \`DISCREPANCY\` | Proven overbilling with recoverable amount | **Yes** |
| \`FAIL_MISSING_SOURCE\` | Required input absent — cannot audit | No |
| \`REVIEW\` | Ambiguous — human decision needed | No |
| \`NO_CLAIM\` | Carrier rules say charge is valid | No |

### Common DISCREPANCY types

- **FUEL_OVERCHARGE** — billed fuel ≠ base × effective fuel %
- **DISCOUNT_MISMATCH** — applied discount ≠ contract rate card
- **DUPLICATE_CHARGE** — same tracking + charge billed twice
- **RESIDENTIAL_SURCHARGE** — DPV + 2 validators agree address is commercial

### Always REVIEW (never auto-dispute)

- Dim weight disputes (requires manifest comparison)
- Mixed-use / PO box addresses
- Validator conflicts
- Quote delta comparisons (informational only → \`NO_CLAIM\`)

### Tolerance boundaries

- Fuel recalc: ±$0.01
- Subtotal reconciliation: ±$0.05
- Discount comparison: exact match to rate card entry
`,
  },
  {
    id: "area-surcharges",
    title: "Area Surcharge Rules",
    subtitle: "Carrier ZIP lists are billing truth — not maps",
    icon: "map",
    content: `
## Rural / delivery area surcharges

A common mistake in parcel auditing is using GIS or map APIs to decide if an address is "rural." **Carriers bill by ZIP list membership**, not geography.

### ShipAudit policy

1. Load the carrier's effective-dated ZIP list (DAS, EDAS, Remote, etc.)
2. Check if the destination ZIP is **listed**
3. If listed → surcharge is valid → \`NO_CLAIM\`
4. If not listed but billed → \`DISCREPANCY\`

### Example

\`\`\`
Destination ZIP: 59718 (Belgrade, MT)
FedEx DAS ZIP list: does NOT contain 59718
Invoice line: DAS surcharge $4.20
Verdict: DISCREPANCY — ZIP not in carrier list
\`\`\`

Even if Belgrade appears rural on a map, if the carrier's published list excludes that ZIP, the surcharge is disputable.

### Rule versioning

Each ZIP list carries:

- \`effective_from\` / \`effective_to\`
- \`rule_hash\` — SHA-256 of normalized list content
- \`parsed_by\` / \`approved_by\` — human approval chain

Evidence packets cite the exact rule hash used in the determination.
`,
  },
  {
    id: "address-validation",
    title: "Address Validation",
    subtitle: "Multi-validator consensus for residential disputes",
    icon: "map",
    content: `
## Address normalization & consensus

Residential surcharges are among the most disputed charge types. ShipAudit requires **strong evidence** before filing:

### Standardization pipeline

1. Parse and normalize the delivery address
2. Run DPV (Delivery Point Validation) confirmation
3. Query multiple address classifiers (commercial/residential)
4. Apply consensus policy

### When a residential DISCREPANCY is allowed

All conditions must be true:

- Address is **DPV-confirmed** (deliverable, standardized)
- **Two or more validators** classify the address as commercial/business
- No validator conflict or mixed-use flag
- Invoice applied a residential surcharge

### When it becomes REVIEW

- Validators disagree (one residential, one commercial)
- PO box or mixed-use detected
- Address could not be standardized
- Only one validator available

### Why consensus matters

Carriers reject residential disputes without standardized address proof. ShipAudit front-loads that evidence into the case packet so filings are defensible.
`,
  },
  {
    id: "disputes",
    title: "Disputes & Evidence",
    subtitle: "Cases from DISCREPANCY only, with versioned evidence packets",
    icon: "gavel",
    content: `
## Dispute workflow

### Case creation rules

- Cases are built **only** from \`DISCREPANCY\` findings
- Each case includes a filing deadline from carrier dispute policy
- Evidence document cites rule hashes, rate card entries, and line provenance

### Evidence packet contents

\`\`\`
CASE: Fuel Overcharge — INV-100 Line 14
CARRIER: FEDEX
TRACKING: 7489 1234 5678

FINDING: FUEL_OVERCHARGE
BILLED: $3.42  EXPECTED: $2.89  RECOVERABLE: $0.53

SOURCES:
  fuel_table: fedex_fuel_2025_w24 (hash: a3f8...)
  base_line: tracking 748912345678 transport $18.40
  effective_pct: 15.75%

PROVENANCE:
  invoice_line_id: 42
  source_file_hash: b7c2...
  ingest_timestamp: 2025-06-10T14:22:00Z
\`\`\`

### Carrier submission policy

| Carrier | Submission |
|---------|------------|
| FedEx | Human-in-loop only — adapter prepares packet, human submits |
| UPS | Human-in-loop only |
| USPS | API adapter interface (when configured) |

The system **cannot** auto-submit FedEx or UPS disputes. A defensive guard blocks programmatic submission.

### Refund ledger

Posted credits are tracked against expected recovery. Statuses: EXPECTED → POSTED → MATCHED.
`,
  },
  {
    id: "tutorial",
    title: "Tutorial: First Audit",
    subtitle: "Step-by-step walkthrough with your own billing data",
    icon: "play",
    content: `
## Tutorial — Audit your own invoices

Everything happens on the **Upload & Audit** page. The order matters: the audit engine refuses to act without its sources.

### Step 1 — Load carrier rule tables

Click **Load carrier rules**. This compiles the bundled FedEx / UPS / USPS rule pack: area-surcharge ZIP lists, fuel schedules, dim-weight divisors, and dispute filing policies. Without rules, every check returns \`FAIL_MISSING_SOURCE\`.

### Step 2 — Upload your rate card

Upload your negotiated contract as JSON. Required fields per entry: service, discount or rate, and effective dates. The compiler hard-fails on overlapping date ranges or missing terms — fix and re-upload.

Without a rate card, discount and minimum-charge checks return \`FAIL_MISSING_SOURCE\` by design. They never estimate.

### Step 3 — Upload an invoice CSV

Export billing data from UPS Billing Center or FedEx Billing Online and upload it. Each row is validated:

- Tracking number must match the carrier's format
- Charge codes must map — no silent \`OTHER\` defaults
- Line amounts must reconcile to the invoice subtotal (±$0.05)

You'll see accepted line count and rejected count immediately. Rejected rows appear on the dashboard with explicit failure reasons — fix the export and re-upload.

### Step 4 — Run the audit

Each ingested invoice appears in the table with a **Run audit** button. Every line resolves to exactly one verdict: \`PASS\`, \`DISCREPANCY\`, \`FAIL_MISSING_SOURCE\`, \`REVIEW\`, or \`NO_CLAIM\`.

### Step 5 — Build dispute cases

Click **Build dispute cases**. Cases are created **only** from proven \`DISCREPANCY\` findings, each with a filing deadline and a hash-identified evidence packet.

### Step 6 — Review on the dashboard

- **Verdict Breakdown** — outcomes across all audited lines
- **Rejected Rows** — inputs that failed closed at ingestion
- **Dispute Cases** — evidence packets ready for carrier submission (FedEx/UPS require human approval; nothing auto-submits)

### API equivalent

\`\`\`bash
# Load carrier rules
curl -X POST http://localhost:8000/api/rules/seed

# Upload rate card and invoice
curl -X POST http://localhost:8000/api/ingest/rate-cards -F "file=@rate_card.json"
curl -X POST http://localhost:8000/api/ingest/invoices -F "file=@ups_invoice.csv"

# Audit an invoice, then build cases
curl -X POST http://localhost:8000/api/audit/invoices/{invoice_id}
curl -X POST http://localhost:8000/api/cases/build

# Inspect results
curl "http://localhost:8000/api/findings?verdict=DISCREPANCY"
curl http://localhost:8000/api/rejected-rows
\`\`\`

### Production checklist

1. Carrier rule tables loaded and current for your accounts
2. Rate card compiled covering the invoice billing period
3. Address validators configured (defaults are mock — fine for ZIP/fuel/discount checks, required for residential disputes)
4. Review the \`REVIEW\` queue before submitting any dispute
`,
  },
];

export function getDocSection(id: string): DocSection | undefined {
  return DOC_SECTIONS.find((s) => s.id === id);
}
