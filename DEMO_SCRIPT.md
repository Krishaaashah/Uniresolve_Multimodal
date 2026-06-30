# UniResolve — Hackathon Demo Script (PS5)

This script documents the exact click path and validation steps to demonstrate UniResolve's pillars of excellence to Union Bank judges.

---

## Step 1: Secure Enterprise Login (Authentication & RBAC)
1. Open the dashboard in your browser (`http://localhost:8000` or double-click the web app).
2. The portal will prompt you with a secure login overlay.
3. Log in as the **Admin**:
   - **Username**: `admin`
   - **Password**: `admin123`
4. Notice that the top-right header now displays your role: **admin (ADMIN)** and a **Logout** option is active.
5. Press `Ctrl + Shift + D` to trigger a clean database reseed using the admin authentication context.

---

## Step 2: Dual-Engine Triage & Multilingual Verification (Vernacular Support)
1. Locate the seeded complaint cards in the main feed.
2. Select the complaint with the **Hindi** badge:
   > *"मेरा यूपीआई ट्रांसफर फेल हो गया है लेकिन मेरे बैंक खाते से..."*
3. Open the detail view. Note:
   - The detected language is recognized as **Hindi** under the Overview.
   - Check the **History** tab: the suggested draft reply from the LLM is written in **Hindi** to correspond to the customer's language.
4. Select the complaint with the **Marathi** badge:
   > *"माझ्या खात्यातून गृहकर्जाचे ईएमआय दोनदा..."*
5. Open the detail view. Verify:
   - Under the Overview, the detected language is shown as **Marathi**.
   - Check the **History** tab: the suggested draft reply from the LLM is written in **Marathi**.

---

## Step 3: Hybrid PII Scrubbing & Security Audit
1. Open the dense PII card:
   > *"Dear Union Bank, this is Aarav Sharma..."*
2. Look at the **Masked Text** panel. Observe that:
   - The name *"Aarav Sharma"* is scrubbed to `[NAME_XXXX]` using spaCy NER.
   - The card number, Aadhaar number, and mobile number are replaced with masks (e.g. `[CARD_XXXX]`).
3. Click the **Audit Trail** tab inside the details panel:
   - This records all actions, state transitions, and escalations, showing who did what, their role, and the exact timestamp.
4. Try to escalate a ticket to **L4 Regulatory** while logged in as a normal agent (to test, logout and log back in as `agent`/`agent123`). The system will raise a `403 Forbidden` restriction.

---

## Step 4: 30-Day Statutory RBI Clock
1. Look at the cards in the SLA / main feed.
2. Verify the statutory clock indicator pills:
   - Complaints <= 20 days old show a green badge: **RBI: within**.
   - Complaints between 21 and 30 days old show a warning: **RBI: approaching**.
   - Seeded complaints 31+ days old show a red alert badge: **RBI: ombudsman_eligible** (meaning the complaint has exceeded the statutory period and the customer is now eligible to escalate directly to the Banking Ombudsman).

---

## Step 5: CMS-Formatted Regulatory Filings
1. Click **Regulatory Report** in the sidebar.
2. The page fetches data from `/reports/regulatory` and displays standard **CMS Ledger Metrics**:
   - **Opening Balance**
   - **Received (New)**
   - **Disposed (Total)**
   - **Closing Balance**
   - **Disposed Rate %**
3. Verify that the **CMS Disposal Indicators** list exact counts of complaints disposed within vs beyond 30 days.
4. Click the blue **Download CSV (RBI filing)** button. Verify that the CSV downloads instantly and corresponds to the official RBI regulatory ledger layout.
