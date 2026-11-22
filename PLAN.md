# SunPower: new project flow (build plan)

The plan is updated after every task: finished tasks move to **Done**, and **Remaining** always shows what's left.

## The flow we're building

```
Savings estimate → Survey request (preferred day + slot)
→ Sales calls and confirms the booking (project ID created, e.g. SP-26-00042)
→ Technician of that area assigned → survey on the customer's portal and the technician's list
→ Technician does the survey and builds the quote (catalogue prices; discount > 5% needs Sales/Admin approval)
→ Customer accepts the quote and picks a payment plan:
     Plan A: 30% advance now, rest after installation (before switch-on)
     Plan B: 100% upfront (2% off)
→ Warehouse reserves stock → packs → ships (customer sees Packed / Shipped / Delivered)
→ Installation technician (same or whoever is free nearby on delivery day)
→ Readings, defects, confirmation photo, customer signature → "Installed, waiting for payment"
→ 100% paid → technician switches on → system ACTIVE → warranties start (per product type)
→ On-grid: net metering → DISCOM inspection → subsidy filed → subsidy received
→ Repairs for life: warranty check → free, or visit fee → estimate → customer approves → repair
Admin: runs operations, sees every project end to end. Director: CEO charts (read-only).
```

## Decisions (defaults until you say otherwise)

| Question | Default used |
|---|---|
| Who builds the quote | The technician, after the survey. Prices come from the catalogue and can't be typed; a discount above 5% waits for Sales/Admin approval before the customer sees it. |
| Warranty terms | Set per product type in Settings: panels **15 years**, inverter **5 years**, battery **2 years** (off-grid / hybrid only; on-grid systems have no battery), workmanship **5 years**. All start on the **activation date**. |
| Switch-on rule | After installation the customer gets a pay-now link. Once 100% is paid the technician's "Switch on" unlocks. If not paid, the job shows "Awaiting final payment" and switch-on happens on a revisit. The technician never waits at the house. |
| Admin vs Director | **Admin** = operations (everything, users, settings). **Director** = read-only executive charts, with read-only click-through to a project. |
| Net metering and subsidy | Tracked steps after activation for on-grid systems, shown to the customer. |
| Navbar | The public "Quote" page becomes **Book a survey**. Navbar: How it works · Packages · Installations · Savings, plus a **Book a survey** button. The first three jump to sections of the home page. |

## Done
- **Task 1: Navbar and Book a survey** (checked in the browser)
  - Navbar: How it works · Packages · Installations (jump to home-page sections, also from other pages) · Savings, plus a **Book a survey** button; nothing is highlighted on pages outside the menu.
  - `/book-survey` (old `/quote` links redirect): preferred day (tomorrow to 30 days) + time slot (morning / afternoon / evening), required and checked on the server; the estimate still shows as "estimate only".
  - Survey requests store `preferred_date` / `preferred_slot` (Sales sees and can change them).
  - Home "How it works" steps rewritten for the new flow.
- **Task 2: Project ID, survey booking, technician areas** (checked in the browser; 38 tests pass)
  - Every enquiry gets a project ID `SP-YY-NNNNN` (older ones were filled in automatically). It's shown on the staff enquiry and order pages, the customer's portal cards and the quote PDF, and you can search by it.
  - Sales' **Confirm booking & assign** panel: shows the customer's preferred day and slot, lets Sales change them, and lists technicians best first: covers the customer's city/state, free in that slot (no survey or installation then), fewest open jobs. Booking records the confirmation time; past dates are refused.
  - The phone screening no longer blocks booking (the technician can complete it at the survey); only a grid marked "unsuitable" does.
  - Technicians have a **service area** (Settings → Users). The demo technicians each cover one city.
  - Customer tracker: Request received → **Booking confirmed** → **Technician assigned** (with date) → Survey done → Quotation; the waiting text shows their preferred day and slot.
  - The "Book a survey" navbar button shows only to visitors and customers.
  - _Note:_ your current database has no service areas yet; reset it (`backend\run.ps1 -Reset`) or type them in under Settings → Users.

- **Task 3: Technician quote and payment plans** (checked in the browser on a test copy of the data; 40 tests pass)
  - The survey page has **Build quote**: it marks the visit done if needed, approves the recommended size and creates the quote from the matching package at catalogue prices. Technicians see only quotes from their own surveys, can add lines and discounts, and can send; Sales confirms orders and records payments.
  - A discount above **5%** (Settings: `discount_approval_pct`) blocks sending, marks the quote "waiting for approval" and shows **Approve discount** to Sales and Admin. Technicians can go up to 15%, Sales up to 10%, the Director without limit; changing a discount needs approval again. Orders list: "Needs approval" filter.
  - The customer accepts by choosing a plan: **Advance now, rest later** (30%, balance before switch-on) or **Pay in full upfront** (2% off, Settings: `full_upfront_discount_pct`). Paying in full adds a "Paid in full upfront: 2% off" line so the total equals what was paid, and confirms the order. The staff order page shows the chosen plan.
- **Detailed site survey** (checked in the browser on a test copy of the data; 52 tests pass)
  - The technician's survey has tabs, one section at a time: Roof, Shade, Electrical, Cabling & mounting, Battery (off-grid only), Site & safety, Photos, Issues & summary. Each tab shows how many required items are still missing. Name, phone, email, address and bill come from the enquiry and aren't asked again.
  - **Submit visit** (formerly "Mark visited") and **Build quote** only work once every required field, the 5 required photos (whole roof, shadow-free area, meter, DB, inverter spot) and the result (feasible / with conditions / not feasible) are in. A "not feasible" survey can't be quoted.
  - **Parts follow the survey:** measured DC / AC runs longer than the package's cable, the earthing run, conduit, elevated or metal-roof mounting and anchor waterproofing become extra quote lines, so the warehouse delivery includes them. The survey page previews these parts. New catalogue items: `STR-ELV`, `CND-25`, `ERT-CBL`, `WPF-KIT`, `CLMP-MTL` (added to existing databases at start-up, stock 0).
- Staff sidebar and the site footer are black everywhere.

- **Warehouse inventory and survey demand** (checked in the browser on a test copy; 55 tests pass)
  - **Inventory** (Operations → Stock): the warehouse manager adds, edits, corrects and retires items. Each item's **code is its unique key** (e.g. `CBL-DC6`) and can't change; serial-numbered items (inverters, batteries, controllers) are tracked unit by unit, panels by batch. Items have a rack/bin location and unit. Stock corrections need a reason and are logged; a serial unit is removed one by one. Prices, cost, GST and warranty stay with the Director.
  - **Demand from surveys**: every visited survey (not yet a confirmed order) shows the parts it needs: the package for the recommended size plus what the survey measured (or the draft quote if one exists). Per item: on hand, reserved, awaiting payment, from surveys, and how much is **short**. The per-survey list is only shown to stock managers.
- **Survey → warranty flow, payment skipped for now** (setting `payment_required` = off; Director can switch it on in Settings)
  - Technician's **Build quote** sends the quote straight to the customer. It can still be changed until the customer accepts (a change takes it back to draft, to be re-sent).
  - Customer **accepts** → order confirmed → delivery goes to the warehouse (ready, no advance needed) and the installation job is created with **the surveying technician** assigned.
  - Warehouse ships with the **serial / batch number of every unit** recorded.
  - Installation can start **on its scheduled day** (Admin can move the date). The technician completes the checklist, kW, **photo** and customer signature, then finishes.
  - **Warranties start on the installation day** (no longer at dispatch).

- **Payments and invoices**
  - Razorpay checkout (advance, pay in full with 2% off, balance) was already built; added a **webhook** so a payment is confirmed even if the customer closes the window (signed with a webhook secret; repeats are harmless).
  - **GST invoice page** for every invoice (advance receipt, tax invoice, service invoice): seller GSTIN, bill-to, place of supply, **CGST + SGST** within Gujarat or **IGST** for other states, order lines with earlier invoices deducted, amount in words, paid / balance. Print or save as PDF.
  - Customers see their invoices on each order in **My account**, and get each one **by email** when it's issued or paid. Staff open them from the order page.
  - The **final invoice is issued automatically when the installation is completed**.

- **Review fixes**: GST on solar equipment 5% (since 22 Sep 2025; existing products and unaccepted quotes upgraded once, confirmed orders keep their rate); panel warranty 15 years; home page claims corrected; survey size limited to 1–5 kW and to what the roof fits; package parts can't be retired; installation needs the kit shipped; customer tracker hides the advance step while payment is off; invoice dates formatted; README updated; API docs can be switched off (`SUNPOWER_DOCS=0`).

## Remaining

### Payment gateway: what's left for you
- In Razorpay (test mode first): copy the key id + key secret into **Settings → Online payments**; add a webhook to the URL shown there (event `payment.captured`) with a secret, and paste that secret too. Then switch **Payment required** on and **Test payments** off.
- Emails (invoices, quotes) go out once SMTP is set in Settings.

### Task 4: Warehouse (left over)
- Supplier purchase orders for items that are short.

### Task 5: Installation, switch-on, warranties
- Installation technician picked from whoever is free in the area on the delivery day.
- Readings: generation (kW), DC/AC voltage, earthing resistance, inverter serial, defects found; confirmation photo; signature.
- "Installed, waiting for payment" → 100% paid → **Switch on** → Active.
- Warranties now start at installation; decide whether to move this to switch-on once payments are back.
- On-grid: net metering → DISCOM inspection → subsidy steps on the customer tracker.

### Task 6: Repair requests
- Automatic warranty check; technician may mark "not covered" (damage / flood / tampering) with a reason that Admin approves.
- Out of warranty: visit fee shown and accepted → diagnosis → estimate → customer approves in the portal → repair → payment → confirm.
- Response-time target (48 h) with an alert to Admin.

### Task 7: Admin and Director
- New **Admin** role (operations); the current Director's daily screens move to Admin.
- **Director**: read-only charts: installs and kW over time, revenue, collections, money owed, margin, enquiry→customer conversion, days per stage, stuck projects, subsidy pending, repairs per 100 installs, warranty cost, by city and by technician.
- One project timeline page (every step, dates, people) for Admin and Director.

### Task 8: Tests, demo data, check
- Back-end tests for every new rule; demo data updated so every stage has examples.
- Browser walk-through for each role on desktop and phone; update `docs/WORKFLOW.md`.
