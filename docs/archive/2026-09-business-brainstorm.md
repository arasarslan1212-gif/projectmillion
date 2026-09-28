# Project Million: Problem → Solution Brainstorm

*Written September 2026. Market claims are backed by the sources listed at the end. Anything marked "assumption" is a guess to test, not a fact.*

---

## TL;DR

1. I listed the painful, recurring problems of **18 different kinds of people** (below).
2. Looking across them, the problems worth building on share one shape: **a person goes through a stressful, high-stakes process once in their life, while the other side (landlord, insurer, state agency, client, school district) handles it every day.**
3. **Reality check for 2026:** the obvious "upload a document and AI explains it" idea is already taken in almost every niche I checked, often by free tools. That kind of product alone is no longer a business.
4. The ideas that still work pair AI with something hard to copy: **actually doing the work** (filing, mailing, calling, a human who reviews everything), **charging for results**, **owning a channel**, or **deep rules for each state**.
5. **Top pick: "Lookback"**, a service that gets a parent's long-term-care Medicaid application approved. It serves adult children whose parent is entering a nursing home or needs care at home. The stakes are very high (a private nursing-home room has a median cost of about $10.8k a month), people already pay for help, and AI can cut the hardest part (reading 5 years of bank statements) from days to hours.
6. **Runner-up, easiest for one person to build: "PaidUp"**, a contract and payment-enforcement tool for freelancers. It builds on new state laws (New York statewide in 2024, California in 2025) that give freelancers **double damages** when clients pay late.

---

## Part 1: Who has which problems

| Who | Their painful problems | What they do today |
|---|---|---|
| **Adult children of aging parents** ("sandwich generation") | Managing a parent's bills, medicines and appointments, often from far away; dividing the work between siblings; choosing a care facility; **paying for care**; scammers targeting the parent | Group texts, spreadsheets, cutting back at work; paying planners, elder-law attorneys and placement agencies |
| **Seniors (70+)** | Phone and text scams; confusing technology; loneliness; choosing a Medicare plan every fall; home repairs they can no longer do | Depend on their kids; fall for scams; use brokers who are paid by insurers |
| **Parents of young kids** | Flood of messages from school and activities; covering summer and childcare; daycare waitlists; one parent carrying most of the mental load | Shared calendars, spreadsheets, missed deadlines |
| **Parents of kids with disabilities** | IEP/504 meetings that feel like them against the school; long waits for evaluations; access to therapy; legal changes when the child turns 18 (guardianship, SSI) | Paid advocates, Facebook groups, Wrightslaw |
| **Renters** | Security deposit withheld; ignored repair requests; hidden fees; listing scams; no way to check a landlord's history | Letter templates, Reddit, often giving up |
| **Homeowners** | Can't tell if a quote is fair or a contractor is legitimate; insurance premiums rising or policies not renewed; property tax set too high; forgetting maintenance | Angi, getting three quotes, asking ChatGPT |
| **Small landlords (1–10 units)** | Rules that differ by city (registration, notices, deposit interest); screening tenants; coordinating repairs | TurboTenant/Avail; call a lawyer after something goes wrong |
| **Freelancers & creators** | **Late or missing payments**; work growing beyond what was agreed; uneven income; quarterly taxes; working without a contract | Invoicing tools; writing off unpaid work |
| **Tradespeople / home-service businesses** | Missing calls while on a job; writing quotes; getting paid; licenses and insurance certificates for every city; hiring | AI receptionists, Jobber, Housecall Pro |
| **Gig workers** | Deactivated by an app with no appeal; tracking income across several apps; mileage and taxes | Driver forums |
| **Patients / people with chronic illness** | Insurance denials and prior authorizations; billing errors; finding an in-network specialist who can see them soon; getting records between doctors | Hours on hold; paid patient advocates |
| **Immigrants & expats** | Official forms and deadlines in a second language; no US credit history; not understanding official letters | Their kids translate; notarios (some are frauds); lawyers |
| **People who were laid off** | COBRA or marketplace insurance; filing for unemployment; negotiating severance; rolling over a 401k | Google, HR |
| **Executors after a death** | Hundreds of admin tasks; closing accounts; probate; finding all the assets | Empathy, lawyers |
| **Disaster survivors** | Listing every item they owned for the insurer; fighting lowball settlements; not enough contractors | Public adjusters (10%+ of the claim), Bevel |
| **Adults with ADHD or who are overwhelmed** | Stuck on "life admin": late fees, missed return windows, unused FSA money, forgotten subscriptions | Rocket Money, body doubling, personal assistants |
| **People with old criminal records** | Records block jobs and housing; expungement rules differ by state | Legal aid, Clear My Record, paid services |
| **Nonprofits & volunteers** | Writing grants; coordinating volunteers; managing donors | Instrumentl, SignUpGenius |

---

## Part 2: The problems behind the problems

Six patterns repeat across that table:

1. **Paperwork with deadlines and penalties.** Missing a date costs real money: a Medicaid request for more information, an appeal window, a deposit deadline, a claim cutoff.
2. **"Too small for a lawyer, too big to ignore."** A $1,200 deposit, a $3,000 unpaid invoice or a $900 billing error is too small for a lawyer to take and too big to shrug off. Hiring a collector costs 40–50% of a small-claims judgment ([Nolo](https://www.nolo.com/legal-encyclopedia/free-books/small-claims-book/chapter24-2.html)).
3. **One person against a repeat player.** The landlord, insurer, school district or client knows the rules. The individual meets them for the first time.
4. **Once-in-a-lifetime, high-stakes events.** A parent going into a nursing home, a death, a fire. **You can't get good at something you do once**, so you need someone who does it every day. This is the most important pattern here.
5. **Coordination among many people.** Siblings sharing a parent's care, parents juggling kids' schedules.
6. **Trust gaps.** "Is this contractor, facility or landlord legitimate?"

The best opportunities combine **#3 and #4**: a stressed person doing something once while facing an experienced institution, with a lot of money at stake.

---

## Part 3: The 2026 reality check (what's already taken)

AI has made reading and writing documents almost free. That created the opportunity, and it also means anyone can build a wrapper around a language model in a weekend. I checked the obvious ideas:

| Idea | Already exists (examples) | Verdict |
|---|---|---|
| AI IEP helper for special-ed parents | My IEP Hero, EveryIEP, IEP Desk, Kidvokit, IEP Compass, Expert IEP, Undivided's assistant | Crowded |
| "Is this contractor quote fair?" checker | QuoteCheck, QuoteChecker.ai, GreatBuildz BidCompareAI | Crowded, mostly free |
| Assisted-living inspection reports in plain English | The Care Audit (all 50 states, free) | Taken |
| Renter move-in/move-out photo reports | RentCheck, Rentproof, MoveSnap, Tenant Inspect | Crowded |
| Deposit demand-letter generators | Many free templates, plus Security Deposit Refund Watchdog | Commoditized |
| Home inventory after a disaster | Bevel (free, built by LA-fire survivors) | Taken |
| Medicaid tools *for professionals* | Medicaidsoft, ElderDocx, Relaw | Exists (but see Part 5) |
| Senior-living placement | A Place for Mom (paid a referral fee of thousands of dollars per move-in) | Dominated |

**Lesson:** "AI explains your document" is now a feature, not a company. What still works:

- **Do the work instead of giving advice.** File it, mail it, call them, and have a human who checks every case.
- **Charge for results**, or at least tie the price to them.
- **Own the channel**: be where the customer is at the moment of pain (hospital discharge planners, facility business offices, professional associations).
- **Deep rules for each state.** Fifty different rulebooks with 50 different sets of forms are boring, which is exactly why they protect you.
- **Build up data** from every case: which documents cause delays, how long each office takes.

---

## Part 4: Shortlist and scores

Scores are gut-feel ratings from 1 to 5 (5 is best). **Openness** means how uncrowded the space is.

| # | Idea | Pain | Money at stake | People already pay? | Hard to copy | Solo-buildable | Openness | Total |
|---|---|---|---|---|---|---|---|---|
| 1 | **Lookback**: Medicaid long-term-care application service | 5 | 5 | 5 | 4 | 2 | 4 | **25** |
| 2 | Estate cleanout / downsizing coordinator (local service plus software) | 5 | 4 | 5 | 4 | 1 | 3 | 22 |
| 3 | **PaidUp**: freelancer contracts and payment enforcement | 4 | 3 | 3 | 3 | 5 | 3 | **21** |
| 4 | "Win *and* collect": small claims plus judgment collection | 4 | 3 | 4 | 3 | 3 | 3 | 20 |
| 5 | Trade-license exam prep (electrician, HVAC, CDL), with state-specific AI tutoring | 3 | 3 | 4 | 2 | 5 | 3 | 20 |
| 6 | Renter's advocate (deposit, repairs, landlord history) | 4 | 3 | 3 | 2 | 5 | 2 | 19 |
| 7 | Sibling caregiving coordination hub | 5 | 2 | 2 | 2 | 4 | 2 | 17 |
| 8 | IEP copilot | 5 | 2 | 4 | 1 | 4 | 1 | 17 |
| 9 | Contractor quote checker | 4 | 3 | 2 | 1 | 5 | 1 | 16 |
| 10 | Family inbox that turns school messages into a calendar | 4 | 1 | 2 | 2 | 4 | 1 | 14 |

---

## Part 5: Deep dive on the top pick, **Lookback**

> *"Mom needs a nursing home. We have 3 weeks. Lookback gets her Medicaid approved."*

### The moment of pain
A parent is hospitalized, goes to rehab, and Medicare's short-term skilled-nursing coverage runs out (at most 100 days, with a daily copay after day 20). The family now faces:

- **About $10,798 a month**, the national median for a private nursing-home room in 2025 ([CareScout/Genworth](https://investor.genworth.com/news-events/press-releases/detail/1054/carescout-releases-2025-cost-of-care-survey-results)).
- A Medicaid application that asks for **5 years of statements from every account**, an explanation for every large withdrawal or transfer, state-specific forms, and follow-up requests with short deadlines.
- A long wait: states are supposed to decide in 45 days, but many take about 3 months ([MedicaidLongTermCare.org](https://www.medicaidlongtermcare.org/how-to-apply/medicaid-pending/)), and the facility is waiting to be paid the whole time.

This is common. **Medicaid is the main payer for 63% of nursing-home residents** ([KFF](https://www.kff.org/medicaid/5-key-facts-about-nursing-facilities-and-medicaid/)). The adult child handling it has usually never done it before and never will again (pattern #4).

### What families use today
- The facility's business office: overloaded, and working in the facility's interest.
- Medicaid planners: some are free, others charge hundreds of dollars an hour ([MedicaidPlanningAssistance.org](https://www.medicaidplanningassistance.org/)).
- Elder-law attorneys: needed for *asset planning*, but overkill for routine paperwork.
- Professional software (Medicaidsoft, ElderDocx, Relaw) serves those professionals. **I didn't find a tech-enabled, fixed-price service that families can go to directly.** That is the gap.

### The product
1. **Free eligibility check (10 minutes).** Answers based on your state's rules: "likely eligible now", "eligible after spend-down", or "talk to an elder-law attorney first" (for example after large gifts, a house transfer, or a spouse still living at home). The last group gets referred out, which builds goodwill with attorneys who refer back paperwork-only cases.
2. **Statement reader.** Upload or connect 60 months of statements. AI builds a single ledger, finds missing months, flags transactions that need an explanation, and drafts those explanation letters.
3. **Application builder.** Pre-filled state forms, a checklist, and submission through the state portal where one exists, otherwise tracked mail.
4. **Case tracker.** Every follow-up request gets a countdown, plus a caseworker call log, appeal deadlines, and a family dashboard that siblings can share (pattern #5).
5. **A human caseworker reviews every application.** This is where the trust comes from, and it's what makes Lookback a service rather than a document reader.

### How it makes money
- **Families:** a flat fee of about $995–$1,995 depending on complexity, with a refund if an application is denied because of our mistake. That compares with hundreds of dollars an hour for planners and much more for attorneys.
- **Facilities (second step):** a per-application or monthly contract with nursing homes and assisted-living operators. Pending applications tie up their cash, and denials become bad debt.
- **Path to $1M a year:** about 60 applications a month at an average of ~$1,500 is about $1.08M. *Assumption to test:* AI plus a good process lets one caseworker handle 15–20 cases a month, so 3–4 caseworkers.

### Go-to-market
- **Start in ONE state**, ideally the one you live in. Each state's rules and forms are a separate product.
- Channels, in order: hospital discharge planners and social workers, nursing-home business offices and admissions staff, independent senior-placement advisors, and elder-law attorneys (two-way referrals).
- Content: search-optimized guides like "how to apply for nursing-home Medicaid in [state/county]", plus caregiver communities (r/AgingParents, Facebook caregiver groups).

### Why it's hard to copy
State rulebooks and form libraries; data from every case (which documents trigger follow-up requests, how long each county office takes); relationships with referral partners; and a human team. A model-wrapper startup can't copy that in a weekend.

### Risks, stated plainly
- **Unauthorized practice of law:** asset-protection strategy is legal advice, so refer it to attorneys. Lookback prepares and tracks applications only. Check your state's rules first.
- **The customers are vulnerable:** transparent fixed prices, no upselling, and a refund guarantee.
- **Sensitive data:** SSNs, bank statements and health information. Build strong security from day one, and sign a HIPAA business associate agreement if you work with facilities.
- **Rules keep changing:** federal and state Medicaid changes (2025–2028) increase confusion, which means more demand, but the rulebook has to be kept up to date.
- **It's a service business:** margins are lower than pure software, and it needs people who are good with frightened families.

### Validate in 2–3 weeks, for under $500
1. Interview 10 families who have been through it (Reddit and Facebook caregiver groups), 5 nursing-home business-office managers, and 3 elder-law attorneys. Ask: *what took the longest, what got denied, what would you have paid?*
2. Publish one excellent state-specific guide plus a waitlist, and see whether it gets signups.
3. Do 2–3 applications **by hand** (with an experienced planner as partner if needed) before writing much code. The software should automate what those cases show takes the most time.

---

## Part 6: Runner-up, **PaidUp** (best if you want to code it alone)

> *"Get paid on time, and when a client is late, the law is on your side."*

### Why now
- **New York's Freelance Isn't Free Act** went statewide on Aug 28, 2024. It requires written contracts for work worth $800 or more and allows **double damages plus attorney's fees** when a client pays late.
- **California's Freelance Worker Protection Act** (SB 988), in effect since Jan 1, 2025, requires contracts for work worth $250 or more and allows up to double damages.
- Other states and cities have similar rules (for example Illinois, Los Angeles and Seattle). Check the current list before building the rules engine.
- Most freelancers have never heard of these laws, and most clients don't know they're exposed.

### The product
1. **A free contract generator that meets each jurisdiction's legal requirements.** It brings in users and records the legal payment deadline from the start.
2. **An invoice tracker that knows the legal deadlines.**
3. **An escalation ladder:** friendly reminder, then firm reminder, then a **formal notice** citing the statute and the double-damages exposure (sent by email and certified mail, with the freelancer as sender), then help filing a state agency complaint, then an attorney directory. Because the losing side pays attorney's fees, these cases are worth a lawyer's time.
4. The "good cop" effect: the formal step looks procedural rather than personal, so the freelancer keeps the relationship.

### How it makes money
Free contracts; **Pro at about $12 a month** for tracking and escalations; or about $29 for each formal notice. **Path to $1M a year:** about 7,000 Pro subscribers. Keep attorney referrals to a flat-fee directory listing, because splitting fees with lawyers isn't allowed.

### Risks
State debt-collection licensing (stay a software tool, with the freelancer as the sender); defamation if you ever build a "client reputation" feature (only aggregate verified facts such as court judgments); invoicing incumbents (Bonsai, HoneyBook, Indy) could add this feature; and freelancers may be reluctant to escalate at all.

### Validate
Launch the contract generator first. If people sign up, offer the $29 notice to anyone who has an overdue invoice and measure how many buy.

---

## Part 7: Other ideas worth keeping

- **Estate cleanout / downsizing coordinator:** after a move to assisted living or a death, a house has to be emptied in weeks. Photograph the items, AI estimates resale value and sends each one to the best channel (auction, consignment, donation with a tax receipt, junk removal), and one coordinator books the pickups. Large tickets and desperate customers, but it's a local operations business.
- **"Win *and* collect":** plenty of people win in small claims and never get paid. The service would guide filing, service of process, and then the steps to collect (wage garnishment, bank levy, property lien). Collectors charge 40–50% today. The legal and regulatory work is heavy.
- **Trade-license exam prep:** a boring but profitable niche. Pass rates matter, prep is state-specific, and passing brings a raise, so people have a reason to pay. It grows mostly through search traffic.

---

## Which one fits you?

- **Healthcare, social work or eldercare background, or a family who went through this, and willing to run a service:** go with **Lookback**.
- **A developer who wants pure software and can reach freelancers:** go with **PaidUp**.
- **Enjoy operations and local business:** the **estate cleanout coordinator**.

Your skills, connections and available time will narrow this faster than any more research.

---

## Sources

- CareScout 2025 Cost of Care Survey (private nursing-home room median $10,798/month): https://investor.genworth.com/news-events/press-releases/detail/1054/carescout-releases-2025-cost-of-care-survey-results
- KFF, 5 Key Facts About Nursing Facilities and Medicaid (Medicaid is primary payer for 63%): https://www.kff.org/medicaid/5-key-facts-about-nursing-facilities-and-medicaid/
- Medicaid Pending timelines: https://www.medicaidlongtermcare.org/how-to-apply/medicaid-pending/
- Medicaid planner costs: https://www.medicaidplanningassistance.org/
- Medicaid software for professionals: https://www.medicaidsoft.com/, https://www.relaw.ai/blog/best-elder-law-tools-2025
- A Place for Mom referral model: https://www.whereassistedliving.com/blog/how-a-place-for-mom-makes-money/
- Small-claims collection contingency fees (40–50%): https://www.nolo.com/legal-encyclopedia/free-books/small-claims-book/chapter24-2.html
- NY Freelance Isn't Free Act: https://freelancersunion.org/advocacy/freelance-isnt-free/, https://www.nyc.gov/site/dca/about/freelance-isnt-free-act.page
- CA SB 988 and state guide: https://sd11.senate.ca.gov/node/1230, https://www.wingspan.app/articles/nyc-freelancing-isnt-free-act-is-leveling-the-playing-field-for-freelancers
- Special education enrollment (15% of public-school students): https://www.pewresearch.org/short-reads/2023/07/24/what-federal-education-data-shows-about-students-with-disabilities-in-the-us/
- Security deposits (about 1 in 4 renters don't get theirs back): https://www.yahoo.com/news/2013-01-29-security-deposit-refund.html
- IEP tool examples: https://myiephero.app/, https://www.everyiep.com/, https://iepdesk.com/, https://kidvokit.com/, https://iepadvocate.ai/
- Quote-checker examples: https://quotecheckus.com/, https://quotechecker.ai/
- Assisted-living inspections: https://www.thecareaudit.com/
- Renter inspection apps: https://www.getrentproof.app/, https://movesnap.app/, https://www.getrentcheck.com/reporting-data
- Disaster inventory: https://abc7.com/post/artificial-intelligence-driven-inventory-tool-bevelmade-serves-solution-california-wildfire-victims-document-belongings/17882452/
