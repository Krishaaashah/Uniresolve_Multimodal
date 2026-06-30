# UniResolve — Business Value & Commercialization (Union Bank IDEA 2.0, PS5)

UniResolve turns customer grievance redressal from a reactive cost center into a
proactive, compliance-driven customer-intelligence layer.

> **Note on numbers:** Every figure below is a **transparent estimate built from a
> stated assumption**, not a measured result. The assumptions are shown so they can be
> challenged and re-run with the bank's real data. We have deliberately avoided quoting
> precise outcome metrics (e.g. "CSAT +35%") we cannot yet substantiate.

---

## 1. The Problem (and why it is a business problem, not just an IT one)

A single customer grievance — a failed UPI debit, a double-charged EMI — typically
arrives across multiple channels (email, app, social, branch, call), is handled by
different agents who can't see each other's work, and risks crossing RBI's 30-day
statutory resolution deadline. Past that point the customer can escalate directly to the
Banking Ombudsman.

This is expensive in three distinct ways the bank already measures:
1. **Agent cost** — manual triage, duplicate investigation, and reply drafting.
2. **Regulatory cost** — ombudsman escalations, compensation awards, and adverse mention
   in RBI's public complaint disclosures.
3. **Revenue cost** — an unresolved, badly-handled complaint is one of the strongest
   early signals that a customer is about to leave (deposits, not just goodwill).

UniResolve addresses all three.

---

## 2. What the Product Does (mapped to value, not features)

| Capability | What it replaces | Value lever |
| :--- | :--- | :--- |
| Unified multi-channel ingestion + dedup | Channel-siloed manual handling | Agent hours |
| LLM triage (category / severity / sentiment) | Manual reading + tagging | Agent hours |
| AI draft responses (incl. Hindi vernacular) | Agent writing every reply from scratch | Agent hours + reach |
| 30-day statutory RBI clock + ombudsman flag | Spreadsheet / memory tracking of ageing | Regulatory risk |
| CMS-shaped regulatory report + CSV export | Manual compilation for RBI filing | Compliance effort |
| Systemic-outage alert (cluster >= 5) | Discovering outages complaint-by-complaint | Faster root-cause |
| RBAC + tamper-evident audit trail | Single shared login, no accountability | Audit readiness |

---

## 3. ROI — a worked model (replace the assumption, get the bank's real number)

We model one mid-size processing unit. **Adjust the four inputs and the rest follows.**

**Stated assumptions (illustrative — to be validated with Union Bank data):**
- Complaints processed: **50,000 / month**
- Fully-loaded agent cost: **₹300 / hour**
- Manual handling time per complaint (read, tag, draft, log): **15 min**
- Share of first-pass work UniResolve automates (triage + draft + dedup): **40%**

**Agent-hour saving (the defensible lever):**
- Time handled manually today: 50,000 × 15 min = **12,500 hours / month**
- Automated first-pass at 40%: **5,000 hours / month saved**
- At ₹300/hour → **≈ ₹1.5 crore / month** in agent capacity freed
  *(Same math at a conservative 20% automation = ₹75 lakh/month. State the range.)*

**Regulatory lever (directional, not precise):**
- Fewer complaints crossing the 30-day clock → fewer ombudsman escalations → less
  compensation paid (RBI can award up to ₹30 lakh per consequential-loss case + ₹3 lakh
  for harassment) and fewer adverse mentions in RBI's public complaint disclosures.
- We do **not** claim a specific % reduction; we claim the mechanism: surfacing ageing
  complaints before day 30 is what reduces eligibility.

**Net effect:**
- The agent-hour lever is quantified and defensible today; the regulatory lever is a
  stated mechanism (surface ageing complaints before day 30, reduce ombudsman eligibility),
  not a fabricated percentage.

---

## 4. Market — why this is a company, not a one-bank tool

The problem is **regulation, not a Union Bank quirk** — so the same product serves every
RBI-regulated entity legally required to run complaint redressal under RB-IOS:

- 12 public sector banks, 21 private banks, 28 regional rural banks, 44 foreign banks,
  12 small finance banks, 6 payments banks
- ~1,450+ urban cooperative banks (plus state & district cooperative banks)
- thousands of registered NBFCs, plus payment aggregators and PPI issuers

**≈ 10,000+ regulated entities**, every one facing tighter timelines under RB-IOS 2026
(in force from 1 July 2026). The regulation creates the demand; we supply the upgrade.

---

## 5. Business Model & Go-to-Market

**Who buys:** the Principal Nodal Officer / Customer-Experience head / Compliance head —
the person personally accountable to RBI for the bank's complaint numbers.

**Pricing (two defensible options):**
- **Per-agent-seat SaaS** — simplest to forecast; scales with the support team.
- **Per-complaint-processed** — fairer to smaller co-op banks / NBFCs; scales with usage.

**Why we win (defensibility):**
1. **On-prem PII** — masking happens before any model call; customer data never leaves the
   bank's own infrastructure. Most GenAI entrants cannot say this.
2. **RBI reporting built in** — not an add-on; the statutory clock and CMS report are core.
3. **Switching cost** — once embedded in complaint operations and holding the bank's
   complaint history, replacement is painful.

**Go-to-market (land & expand):**
Pilot with one PSB (Union Bank) → expand to the regional rural banks it sponsors →
cooperative banks and NBFCs. Wedge = the RB-IOS 2026 deadline forcing every entity to
modernise complaint handling anyway.

---

## 6. Roadmap (next, beyond the hackathon build)

- Multi-tenant SaaS hardening for cross-entity deployment.
- Connector expansion to live email / social / IVR feeds.
