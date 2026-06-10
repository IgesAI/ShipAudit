# ShipAudit

**Stop overpaying your parcel carriers.** ShipAudit checks every line of your FedEx, UPS, and USPS invoices against your contract and the carriers' own published rules — then builds ready-to-file dispute packets for every charge it can prove is wrong.

It never guesses. Every claim is backed by exact math and a cited source, so disputes hold up when the carrier pushes back. If ShipAudit can't prove it, it tells you that instead.

---

## How to use the site

ShipAudit has three pages, all in the top navigation:

| Page | What it's for |
|------|---------------|
| **Dashboard** | See audit results: proven overcharges, recovery totals, dispute cases |
| **Upload & Audit** | Bring in your billing data and run audits |
| **Docs & Tutorial** | Full explanations of every concept, plus a step-by-step walkthrough |

### Your first audit (5 steps)

Everything happens on the **Upload & Audit** page, in order:

**1. Load carrier rules** — one click. This loads the carrier rule tables (surcharge ZIP lists, fuel schedules, dimensional-weight divisors) that audits are checked against.

**2. Upload your rate card** — a JSON file describing your negotiated contract: discounts, minimum charges, effective dates. Without it, ShipAudit can't verify rates — and it will say so rather than estimate.

**3. Upload an invoice** — a CSV export from UPS Billing Center or FedEx Billing Online. Every row is validated on the spot. You immediately see how many lines were accepted and how many were rejected (with the exact reason for each rejection).

**4. Run the audit** — each uploaded invoice gets a **Run audit** button. Every charge line gets exactly one verdict:

| Verdict | Meaning |
|---------|---------|
| **DISCREPANCY** | Proven overcharge — recoverable money, backed by math |
| **PASS** | Charge matches your contract and carrier rules |
| **NO CLAIM** | Charge is valid per the carrier's own published rules |
| **REVIEW** | Evidence conflicts — needs a human decision |
| **FAIL (missing source)** | Can't be verified — a required input (like a rate card) is missing |

**5. Build dispute cases** — one click turns every proven discrepancy into a dispute case with a filing deadline and a complete evidence packet.

### Reading the Dashboard

- **Proven Discrepancies** — count and dollar value of mathematically proven overcharges
- **Verdict Breakdown** — how every audited line resolved
- **Rejected Rows** — invoice lines that failed validation, with explicit reasons (fix your export and re-upload)
- **Dispute Cases** — each case shows its filing deadline; click **Evidence packet** to see the carrier-ready dispute document
- **Refund Ledger** — tracks expected credits against what the carrier actually posts

### Filing disputes

ShipAudit prepares the evidence; **you stay in control of submission**. FedEx and UPS disputes always require human approval — the system builds the packet, you file it in the carrier's billing portal. Nothing is ever auto-submitted to FedEx or UPS, by design.

Every evidence packet includes the exact rule version (hash-identified), the recomputed expected amount, and the provenance of the invoice line — so your dispute is defensible.

---

## Why "fail-closed" matters

Most audit tools flag anything that looks suspicious and leave you to sort it out. ShipAudit only claims what it can prove:

- A surcharge ZIP is checked against the **carrier's actual published list** — not a map
- Fuel charges are **recomputed** from your invoice's own base charge and the carrier's fuel schedule
- Residential surcharge disputes require a **validated address plus two independent commercial classifications**
- Anything ambiguous goes to a **Review queue** instead of becoming a false claim

That means fewer disputes rejected, less time wasted arguing, and claims you can stand behind.

---

## Running it

```bash
cp .env.example .env
docker compose up --build
```

Open **http://localhost:3000** — that's it. The API and interactive API docs live at http://localhost:8000/docs.

Full concept explanations and a guided tutorial are built into the site at **/docs**.
