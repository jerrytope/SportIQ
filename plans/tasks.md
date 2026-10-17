# SportIQ — Tasks

Companion to `implementation_plan.md`. Tick tasks as they are completed. `[Mn]` = blueprint module number.
A task is only "done" when it has been run and exercised in the browser, not just tested.
`[x]` done · `[~]` partly done · `[ ]` not started.

**Status 2026-10-15:** All four phases built and verified (76 tests; every page crawled as 21 roles). Items marked [~] or [ ] have notes explaining what remains.

---

## Phase 0 — Foundations

### 0.1 Project setup
- [x] Create Django project `sportiq` with split settings (base/dev/prod) and `.env` handling
- [~] Docker Compose written (web, postgres, redis, worker, beat); **not yet built/run**; nginx + pgvector not added (pgvector needed in Phase 3)
- [x] Create all Django apps under `apps/` (core … web) with empty urls/admin/services
- [x] ~~Tailwind + HTMX + Alpine~~ → hand-written token-based CSS (`static/css/sportiq.css`) + small vanilla JS; no build step needed (decision 2026-10-15)
- [ ] CI: ruff, pytest, migrations check (pytest suite exists, 40 tests; no CI pipeline yet)
- [x] `README.md` skeleton (setup, run, demo accounts)

### 0.2 Design system
- [x] Define tokens in `tailwind.css`: Nigerian green `#008751`, deep green `#0B3D2E`, gold `#F2C230`, surfaces, borders, text
- [x] Dark-mode tokens
- [x] Fonts: Instrument Sans + Fraunces (Google Fonts)
- [x] Radii/spacing tokens copied from Talstack scale (8/10/16/20/24/80px)
- [x] Component partials: button, pill/eyebrow, card, bento card, input, select, table, tabs, modal, toast, empty state, badge, progress bar, stat tile
- [x] Base layouts: public, learner (sidebar + mobile bottom bar), manage (admin sidebar)
- [~] Contrast checked by eye in light/dark; formal WCAG audit (axe) still to run

### 0.3 Core platform
- [x] `core`: base model (UUID pk, timestamps, soft delete), `AuditLog` model + `audit()` service
- [x] `accounts`: custom User (email login) with profile fields, email verification (own implementation instead of django-allauth; Google sign-in not added)
- [x] TOTP 2FA (django-otp); enforce for staff roles
- [x] Roles & permissions framework: groups + `Membership(user, institution, role)` + central `permissions` service
- [x] Rate limiting on login/OTP; account lockout
- [x] `notifications`: email (SMTP/SES), SMS (Termii) adapter, in-app notifications, templates, user preferences
- [x] `seed_demo` management command scaffold

---

## Phase 1 — Institutional foundation (MVP)

### 1.1 Landing page & public site (Talstack-style)
- [x] Announcement bar (CMS-editable) with tricolour stripe
- [x] Navbar with Academy mega-menu, Resources dropdown, Verify, Sign up, Log in, Request a demo
- [x] Mobile navbar: hamburger → full-screen drawer with accordions
- [x] Hero: eyebrow, headline, subtext, two CTAs, animated product mockup
- [x] Partner logo strip
- [x] Course showcase 3×3 grid from live catalogue + CTAs
- [x] Feature bento grid (Learning paths large card + Practical labs, AI assistant, Analytics)
- [x] Credentials section (3 stacked cards with screenshots)
- [x] "For every sports profession" role tabs
- [x] Impact stats counters (labelled illustrative)
- [x] Testimonials marquee carousel
- [x] "In the news" press section
- [x] Recent posts (3 latest blog articles)
- [x] Final CTA section
- [x] Footer: tagline, contacts, newsletter form, link columns, legal, socials
- [x] Pages: About, For institutions (demo request form), FAQs, Blog list/detail, Events, Terms, Privacy (NDPA), Accessibility
- [x] Site content models (banner, hero, logos, testimonials, press, stats, FAQs, blog posts) editable in admin
- [x] Newsletter subscribers + demo requests stored and visible in admin
- [x] SEO: meta tags, OpenGraph, sitemap, robots
- [x] Visual check at 390px and 1440px (light + dark) against the Talstack section structure

### 1.2 Accounts & self-service [M2, M20]
- [x] Sign up (role/profession selection, state/LGA), login, logout, email verify
- [x] Password reset + SMS OTP recovery
- [x] Profile edit: personal info, photo, languages, sports, professions
- [x] Settings: password, 2FA, notification preferences, data saver, language
- [x] Privacy: consent records, download my data (JSON/ZIP), delete account request
- [x] Payment history & receipts page

### 1.3 Institutions [M17]
- [x] Models: Institution (type: NIS dept, federation, state council, university, centre, employer), Membership
- [x] Admin: create institutions, assign institution admins
- [x] Institution admin portal: members list, invite/link staff, staff progress (scoped)
- [x] Federation nominations of learners into cohorts
- [x] Permission-isolation tests (cross-institution access → 403)

### 1.4 Catalogue & curriculum [M1, M2]
- [x] Taxonomy: Sport, Profession, Subject, Track, Level, Language, Delivery format
- [x] Course, CourseVersion, Module, Lesson (video/reading/download/quiz), Prerequisite, LearningPath
- [x] Public catalogue with search + filters; course detail page
- [x] Learning paths page (beginner → specialist)
- [x] Course metadata required: owner, objectives, audience, prerequisites, assessment criteria, references, revision date, review schedule

### 1.5 Content studio (basic) [M16]
- [x] Course builder: modules/lessons drag-order, lesson editor (rich text), file/video upload
- [x] Workflow: draft → in review → approved → published → retired; reviewer comments
- [x] Versioning: publish creates immutable CourseVersion; learners keep their version
- [x] Question bank editor (for assessments)

### 1.6 Media pipeline [M1, M7]
- [x] Upload to local media storage (S3/CDN via django-storages still to configure for production)
- [x] Celery ffmpeg job → HLS 240p/360p/720p + audio-only track + thumbnail
- [x] Player: HLS.js, speed control, quality selector, subtitles (VTT upload), transcript panel, resume position
- [x] Downloadable PDFs/workbooks per lesson

### 1.7 Learning experience [M1, M15]
- [x] Enrolment (free, paid, nominated, sponsored) with completion rules
- [x] Learner dashboard: continue learning, deadlines, live, renewals, recommendations, announcements
- [x] Lesson player page with progress tracking, notes, bookmarks
- [x] Course discussion forum + moderated Q&A
- [x] Course feedback survey + instructor rating on completion
- [x] Cohorts, learning calendar, attendance
- [x] Reminders (Celery beat): inactivity, deadlines
- [x] Gamification basics: progress bars, streaks, badges, milestones

### 1.8 Assessments (core) [M6]
- [x] Question types: MCQ, multi-select, true/false, short answer, essay
- [x] Exam: time limit, randomised from bank by topic/difficulty blueprint, attempts allowed, pass mark
- [x] Exam taking UI with autosave + timer
- [x] Auto-marking for objective items; marking queue + rubric for written items
- [x] Results release; learner results page
- [x] AI tutor disabled during attempts (hook for Phase 3)

### 1.9 Certificates & verification [M5]
- [x] CredentialType (completion / competence / qualification / licence) with distinct labels
- [x] Auto-issue completion certificate when rules met
- [x] Certificate PDF (ReportLab instead of WeasyPrint: no GTK dependency on Windows) with QR code, unique code, issue/expiry date, NIS branding
- [x] Public verification page (enter code or scan QR) showing status + credential type
- [x] Verification log; revoke/suspend from admin with audit trail
- [x] Learner credentials wallet

### 1.10 Commerce [M17]
- [x] Course pricing (free/paid), scholarships & sponsored seats (voucher codes)
- [x] Paystack checkout + webhook verification → enrolment
- [x] Invoices/receipts PDF; finance portal: payments list, reconciliation, refunds

### 1.11 Helpdesk [M20]
- [x] Help centre articles + FAQs (searchable)
- [x] Support tickets: category (technical/academic/complaint/accessibility), priority, owner, status, SLA timer
- [x] Agent queue in admin; learner ticket view and replies
- [x] Maintenance/status announcements banner

### 1.12 Staff admin portal (`/manage/`) [M17]
- [x] Admin layout + role-scoped sidebar
- [x] Overview dashboard with "waiting for me" tasks
- [x] Users: search, edit roles, suspend, verify, bulk CSV import
- [ ] Audited impersonation (deliberately not built yet; needs a security decision)
- [x] Admissions: applications, eligibility, documents, decision
- [x] Academic settings: terms, grading rules, completion rules
- [x] Instructor management: credentials, assignments, workload
- [x] Communications: announcements, email/SMS campaigns
- [x] Site content editor (landing page sections, blog, press, testimonials)
- [x] Settings & security: integration keys, feature flags, audit log viewer, data-subject requests

### 1.13 Analytics (basic) [M18]
- [x] Metric definitions registry (each metric has a description)
- [x] Nightly snapshot job
- [x] Executive dashboard: registrations vs active learners, completions, certificates issued vs verified, reach by state/sport/profession
- [x] Instructor view: assessment centre queues + item analysis (dedicated per-course progress dashboard still to add)
- [x] Institution dashboard (scoped)
- [x] Filters + CSV/PDF export

### 1.14 Mobile & low bandwidth [M7]
- [x] PWA manifest, installable, service worker caching shell
- [x] Data-saver mode (no autoplay, low quality default, audio-only option, images lazy/low-res)
- [x] Mobile bottom navigation; test on 375px
- [x] Accessibility: keyboard nav, focus states, captions, screen-reader labels, axe checks

### 1.15 Seed content & mandatory learning [M2, M13]
- [x] Seed courses: Coaching foundations, Sports administration, Safeguarding essentials, Anti-doping essentials
- [x] Mandatory learning rules per role (e.g. coaches need current safeguarding certificate)
- [x] `seed_demo`: institutions, users for every role, courses, exams, enrolments, certificates

### 1.16 Phase 1 verification
- [x] Ran the server; crawled ~1,800 pages across 9 roles with no errors; walked learner → exam → examiner release → certificate → public verification in the browser; payments, refunds, workflow and isolation covered by tests
- [x] End-to-end journey covered by pytest (HTTP level) + browser walkthrough; committed Playwright suite still to write
- [ ] Lighthouse/throttled-3G check on landing + lesson pages
- [x] README updated with demo accounts and walkthrough

---

## Phase 2 — Professional development  *(built 2026-10-15)*

### 2.1 Qualifications & credential lifecycle [M5]
- [x] Programmes/qualifications with rules (courses + supervised practicals), awarded automatically
- [x] Online applications for qualifications with document upload; registrar admission queue
- [x] CPD log (automatic for courses, live sessions, practicals; external CPD with evidence) + approval queue
- [x] Expiry, renewal requests checked against CPD points per cycle, reminders (60/30/7 days)
- [x] Open Badges 3.0 JSON-LD per credential (unsigned; verification through the hosted URL)
- [x] Recognition of prior learning (evidence + approval → completion + RPL credential)
- [x] Appeals, resits, access requests, reassessment (re-marking), corrections, suspend/revoke with audit trail
- [x] Digital transcript + professional portfolio PDFs

### 2.2 Advanced assessment [M6]
- [x] Image, video and case-study questions
- [~] Oral/live assessment: run as an in-person/live session + supervisor-signed practical; no dedicated oral-exam scoring screen
- [x] Video evidence submissions + external supervisor sign-off (secure link, no account needed)
- [x] Moderation by a different examiner before release; resit allowances; appeals
- [x] Similarity check across learners' written answers (5-word shingles)
- [x] Item analysis: facility + discrimination index
- [x] Scheduled exam windows, identity declaration, optional webcam snapshots with accessible alternative

### 2.3 Practical portfolio [M3]
- [x] Task types (session/tactical/event/business plans, budgets, video, workplace, oral) with rubric grading and feedback
- [x] Supervisor sign-off; in-person session attendance register

### 2.4 Live academy [M8]
- [x] Scheduling, embedded Jitsi rooms, join from dashboard
- [x] Attendance + CPD, polls, moderated Q&A
- [x] Recordings with consent prompt + retention date
- [x] Office hours booking; guest lecturers; co-teaching institutions
- [~] Uses public meet.jit.si by default: **self-host Jitsi before production**; breakout rooms rely on Jitsi's own controls

### 2.5 Digital library [M9]
- [x] Resources with metadata, versions, licence/ownership, access levels, review dates, editors
- [x] Search + filters; download counts
- [x] Collections, instructor reading lists, annotations
- [x] Citation export (APA, Harvard, BibTeX)
- [x] External authorised links (e.g. WADA ADEL)

### 2.6 Full content studio [M16]
- [x] Lesson templates, embedded interactive content (H5P/simulation URL), SCORM packages
- [x] External reviewer role (comment-only on assigned courses); scheduled publishing
- [x] Course performance via analytics + item analysis; full data export
- [ ] Automatic speech-to-text transcription. Not built (needs a speech service); subtitles/transcripts are uploaded

### 2.7 Offline [M7]
- [x] "Save offline" lesson packs (page + audio + downloads + subtitles) served by the service worker
- [x] Exam answers kept on the device when the connection drops and synced on reconnect (flagged for examiners)
- [x] Offline copies cleared on logout (shared-device privacy)
- [~] Fully offline exam *submission* is not supported (by design: timed exams need the server)

### 2.8 Integrations [M19]
- [x] SCORM 1.2/2004 player + xAPI statement store (LRS endpoint)
- [~] LTI 1.3 tool (login, launch with JWT validation, JWKS): built, **not yet tested against a real LMS**
- [~] OpenID Connect SSO: built, **not yet tested against a real identity provider**
- [x] Scoped API keys, institution-scoped endpoints, signed webhooks with delivery log, OpenAPI docs
- [x] Bulk data export (ZIP of JSON per app)

### 2.9 Business & careers [M14], engagement [M15]
- [x] Business/event practical tasks graded by rubric; CV builder (PDF) from verified records
- [x] Optional leaderboards, challenges, team (institution) standings; per-cohort switch

### 2.10 Phase 2 verification
- [x] Tests: qualification award, CPD/renewal, RPL, appeals, moderation, similarity, schedule, SCORM, xAPI, live CPD
- [x] Crawled every page as 21 roles with no errors; screenshots reviewed

---

## Phase 3 — Intelligence & automation  *(built 2026-10-15)*

### 3.1 AI study assistant [M4]
- [x] Index of approved content (lessons, transcripts, course overviews, library, help); BM25 retrieval (no pgvector needed at this scale)
- [x] Chat with citations; Claude `claude-opus-5-5` with server-side refusal fallbacks when a key is set, quoted passages otherwise
- [x] Guardrails: off during exams, refuses near-verbatim live exam items, no learner data for training, daily limit
- [x] Study plans; revision from weak topics; practice questions (practice-only items)
- [x] Instructor copilot: draft questions/objectives saved inactive for expert approval
- [x] Rubric-based preliminary feedback (draft, never a grade)
- [x] Learning-risk alerts (inactivity, repeated failure, stalled before deadline)
- [x] Recommendations from approved pathways (dashboard, study plan)
- [x] Help-desk assistant with escalation to a human ticket
- [~] AI provider switched to OpenAI (2026-10-15; Anthropic still selectable). Tested with a mocked client only. **Run a live check with the real OPENAI_API_KEY**

### 3.2 Practical labs & simulators [M3]
- [x] Branching scenario engine (refereeing, coaching, medicine for verified professionals), labelled training exercises
- [x] Match-analysis lab (timestamped tags on video + report)
- [x] Coaching session designer; budget/event sandbox; training-load (ACWR) lab with sample data

### 3.3 Community [M10]
- [x] Verified profiles (opt-in public), groups by sport/discipline, alumni, verified-only roundtables
- [x] Mentorship (NIS-approved mentors, capacity, requests)
- [x] Opportunities board with moderation; applications sharing verified credentials
- [x] Report button, moderation queue

### 3.4 Workforce database [M11]
- [x] Consented listing, availability, preferences, experience levels
- [x] Authorised, logged search; contact by request only
- [x] Nigeria skills map (tile cartogram, small-number suppression) + gap ranking

### 3.5 Research centre [M12]
- [x] Proposals with ethics checklist and approval
- [x] Datasets: open teaching data and approval-gated restricted data (12-month access)
- [x] Publications, peer review, evidence summaries
- [x] M&E: pre/post learning gain, delivery-mode and cohort comparisons

### 3.6 Integrity reporting [M13]
- [x] Confidential reporting (anonymous option, reference + access code)
- [x] Restricted case management: encrypted fields, safeguarding officers only (super admins excluded), access log

### 3.7 Observatory analytics [M18]
- [x] Scheduled email reports; cohort/delivery comparisons; impact dashboard
- [x] Public national sports education observatory with suppression of small groups

---

## Phase 4 — National & international expansion  *(groundwork built 2026-10-15)*
- [~] Languages: switcher + **draft** Naijá/Yorùbá/Hausa/Igbo navigation; translation workflow for course/lesson content (only expert-approved versions shown). **Needs qualified translators before launch**; most page text is still English
- [x] External qualification recognition (registrar verification; recorded, not re-issued)
- [~] Advanced labs: 3D model viewer in the library; no 3D/VR simulations built
- [~] Federation registry + government identity adapters: built with sandbox mode and audit log; **no real provider connected** (needs agreements/legal authority)
- [~] Native apps: PWA is installable; Android Trusted Web Activity link file provided; no native app built
- [x] Longitudinal evaluation: automatic 6- and 12-month outcome surveys + reporting

---

## Go-live (any phase release)
- [ ] Staging deploy, smoke tests
- [ ] Backups configured + restore tested
- [ ] Sentry + uptime monitoring; incident runbook
- [ ] Independent security assessment (before first public launch)
- [ ] NDPA compliance review (privacy notice, retention, DPO contact)
