# SportIQ — Implementation Plan

**Product:** SportIQ, the NIS Digital Sports Academy (`sportiq.edu.ng`)
**Prepared by:** Made In Africa Sport · 2026-10-15
**Source of truth:** `SportIQ Blueprint for Digital Sports Academy.pdf` (20 modules, 12 roles, 4 phases)
**Landing page reference:** https://www.talstack.com/ — same structure and feel, re-skinned in Nigerian national colours.

---

## 1. Context

SportIQ is a national sports education and workforce platform for the National Institute for Sports (NIS). It is not
"just an LMS": it combines learning, certification, assessment, a knowledge library, research, a national workforce
database, a professional community and institutional administration — all on **one learner record**.

The blueprint's own recommendation is followed: **build a credible, fully working core first (Phase 1), but design the
data model and architecture for the whole ecosystem from day one**, then add Phases 2–4 module by module. Every module
in the blueprint is covered in this plan; the phasing only decides order.

Every part of the system has three faces:
1. **Public site** — landing page, catalogue, credential verification, library preview, blog.
2. **Learner / professional self-service** — dashboard, learning, profile, CPD, certificates, settings, privacy.
3. **Staff & institutional admin portal** — a complete custom back office (NIS, instructors, federations, state
   councils, employers), so nothing ever needs a developer or raw Django admin.

### Assumptions (open decisions in blueprint §10 — confirm with NIS)
| Decision | Assumption used for the build | Why it is safe |
|---|---|---|
| Ownership | NIS-owned, operated by Made In Africa Sport under a managed service | Data export + documented APIs avoid lock-in either way |
| Audience | National sports workforce **plus** free public introductory courses | Course visibility flag lets NIS restrict later |
| Delivery | Online + hybrid (in-person practical sessions at designated centres) | Practical assessment model supports both |
| Certification | Completion certificates **and** NIS-approved qualifications; external credentials later | Credential *type* field keeps them distinct |
| Funding | Mixed: sponsored/free enrolments + paid courses | Payments are optional per course |

---

## 2. Tech stack

| Layer | Choice | Reason |
|---|---|---|
| Backend | **Django 5.x** (Python 3.12), modular apps | Admin/records-heavy domain; matches the team's other projects |
| API | Django REST Framework + drf-spectacular (OpenAPI docs) | Blueprint Module 19: documented APIs |
| Frontend | Django templates + **HTMX** + Alpine.js + **Tailwind CSS** | Light pages for low bandwidth; no SPA bundle |
| Database | **PostgreSQL 16** + `pgvector` | Relational records + AI retrieval in one DB |
| Async / jobs | Celery + Redis (+ celery-beat) | Video transcoding, reminders, renewals, reports, AI indexing |
| Media | S3-compatible object storage (django-storages) + CDN; local disk in dev | Blueprint §4 content delivery |
| Video | ffmpeg → HLS at 240p/360p/720p + audio-only track | Low-bandwidth / adjustable quality / audio-only lessons |
| Live classes | Jitsi (self-hostable) via integration interface; Zoom adapter optional | Module 8; avoids hard vendor lock |
| AI | Anthropic Claude API (retrieval-grounded), pgvector embeddings | Module 4; cites sources, no training on learner data |
| Search | Postgres full-text search (upgradeable to Meilisearch) | Catalogue, library, transcripts |
| Auth | django-allauth (email + password, Google), TOTP 2FA (django-otp) **required for staff** | §4 security: MFA for privileged accounts |
| Payments | Paystack (primary) + Flutterwave adapter | Nigerian payments, Module 17 |
| SMS / email | Termii (SMS) + SMTP/Amazon SES | Notifications, reminders, OTP |
| PDFs | WeasyPrint | Certificates, transcripts, reports |
| PWA / offline | Service worker (Workbox) + IndexedDB queue | Module 7 offline lessons & queued exam submissions |
| Interop | SCORM 1.2/2004 player, xAPI statements (LRS tables), LTI 1.3 tool, Open Badges 3.0 | Module 1/5/19 |
| Tests / QA | pytest-django, factory_boy, Playwright (E2E), axe-core (accessibility) | §4 quality assurance |
| Deploy | Docker Compose (web, worker, beat, postgres, redis, nginx); staging + production | §4 reliability |

---

## 3. Landing page & design system ("Talstack, in Nigerian colours")

### 3.1 Design tokens (Talstack structure → SportIQ palette)
Talstack uses a near-black navy primary (`#1a182b`), orange accent (`#ef5a3c`), light surfaces (`#f8fafb`), borders
`#eceff3`, a sans + serif font pairing, and radii 8px (buttons) / 10px (inputs) / 16px (images) / 20px (cards) /
24px (banners) / 80px (pills). We keep the spacing, radii and composition and swap the colours:

| Token | Talstack | SportIQ (Nigeria) |
|---|---|---|
| `--primary` (headings, dark sections) | `#1a182b` | **`#0B3D2E`** deep Nigerian green |
| `--brand` (buttons, links) | — | **`#008751`** Nigeria flag green |
| `--brand-hover` | — | `#006B40` |
| `--accent` (highlights, badges, eyebrows) | `#ef5a3c` | **`#F2C230`** gold (Super Eagles / medals) |
| `--surface` | `#f8fafb` | `#F6FAF7` (green-tinted white) |
| `--tint` (soft cards) | `#fff6d7` | `#E6F4EC` (pale green) |
| `--white` | white | `#FFFFFF` (flag white) |
| `--border` | `#eceff3` | `#E3EBE6` |
| `--text` / `--muted` | `#36394a` / `#818898` | `#2B3530` / `#6B7A72` |
| Fonts | Messina Sans / Messina Serif | **Instrument Sans** (body/UI) + **Fraunces** (display headings) — free Google Fonts with the same sans + serif feel |

Dark mode tokens are defined too (dark green surfaces). Green-white-green appears as a thin tricolour stripe in the
announcement bar and footer. Contrast is checked to WCAG AA (gold is only used on dark green or as a fill behind
dark text, never as text on white).

### 3.2 Landing page sections (mirrors Talstack top to bottom)
1. **Announcement bar** — "Now enrolling: Safeguarding & Anti-Doping essentials — free for registered coaches → Learn more".
2. **Navbar** — logo · Home · Academy ▾ (mega-menu: Course catalogue, Learning paths, Live academy, Practical labs,
   Certifications, Sports library, AI study assistant, Careers & community, Research & insights) · About · Resources ▾
   (FAQs, Blog, Events) · For institutions · **Verify a certificate** · Sign up · Log in · **[Request a demo]** button.
   Mobile: logo + hamburger → full-screen drawer with accordions.
3. **Hero** — eyebrow pill "New"; headline *"Learn the game. Prove your skill. Grow Nigerian sport."*; subtext about the
   national academy for coaches, officials, administrators, scientists and athletes; CTAs **Start learning** /
   **Request a demo**; animated product mockup (dashboard + phone).
4. **Trust strip** — "In partnership with Nigeria's sports community": NIS, Federal Ministry of Sports, federations,
   state sports councils, universities (placeholder logos until permission is granted).
5. **Course showcase** — "Upskill coaches, officials and administrators with expert-led courses"; 3×3 grid of course
   tiles pulled live from the catalogue; *View course catalogue* / *Get started*.
6. **Feature bento grid** — "Create, organise and manage sports education with ease": large card **Learning paths**
   (beginner → specialist), plus small cards **Practical labs**, **AI study assistant**, **Analytics for decision-makers**.
7. **Credentials section** — "Qualifications anyone can verify": three stacked cards — **Earn certificates**,
   **Track CPD & renewals**, **Verify instantly (QR)** — with screenshots.
8. **For every sports profession** — role tabs/cards (Coaches, Referees, Administrators, Sports scientists, Athletes,
   Journalists, PE teachers, Students).
9. **National impact stats** — counters (learners, states reached, certificates verified) — clearly labelled
   "illustrative" until real data exists (blueprint Module 18 rule).
10. **Testimonials** — "Our learners say it better than us" — marquee carousel of cards (headshot, quote, name, role).
11. **In the news** — press logos/cards (CMS-managed).
12. **Recent posts** — 3 latest blog articles (CMS).
13. **Final CTA** — "Ready to raise the standard of Nigerian sport?" — *Start for free* / *Request a demo*.
14. **Footer** — logo + tagline, contact email/phone, newsletter signup, columns (Academy, Resources, Institutions,
    Company), legal (Terms, Privacy/NDPA notice, Accessibility), socials, tricolour stripe.

All landing content (banner, hero copy, logos, testimonials, press, stats, FAQs) is editable from the admin portal's
**Site content** section — no code changes needed.

### 3.3 App UI
The learner and admin apps reuse the same tokens: left sidebar navigation (blueprint §6 menu), white cards on green-tinted
surface, gold for achievements/badges, green for primary actions. Mobile: bottom tab bar (Home, Learn, Live, Library, Me).

---

## 4. Architecture

### 4.1 Django apps (each owns its models, services, views, API, admin-portal screens)
| App | Blueprint module(s) | Responsibility |
|---|---|---|
| `core` | — | Base models (UUID, timestamps, soft delete), settings, site content CMS, audit log |
| `accounts` | 2, 17, 20 | User, profiles, roles & permissions, 2FA, consent, data-subject requests |
| `institutions` | 17 | NIS departments, federations, state councils, universities, training centres, employers; memberships |
| `catalog` | 1, 2 | Sports, professions, subjects, qualification levels, curriculum tracks, courses, learning paths |
| `studio` | 16 | Course builder, versions, review & approval workflow, templates |
| `learning` | 1, 15 | Enrolments, cohorts, progress, notes, bookmarks, reminders, forums, feedback, gamification |
| `media` | 1, 7 | Video upload/transcode/HLS, transcripts, subtitles, downloads |
| `assessments` | 6 | Question banks, blueprints, exams, attempts, marking, rubrics, moderation, resits, appeals, item analysis |
| `practicals` | 3 | Simulators, labs, scenarios, portfolio submissions, supervisor sign-off |
| `credentials` | 5 | Credential types, issuance, QR verification, badges, CPD, renewals, revocation, transcripts |
| `live` | 8 | Live sessions, webinars, attendance, recordings, office hours |
| `library` | 9 | Resources, collections, metadata, versions, licences, citations |
| `ai` | 4 | Document chunks/embeddings, tutor chat, study plans, instructor copilot, risk alerts |
| `community` | 10 | Groups, discussions, mentorship, opportunities (jobs/internships), moderation & reports |
| `workforce` | 11 | Workforce directory, availability, authorised search, skills map |
| `research` | 12 | Projects, datasets, publications, peer review, M&E |
| `integrity` | 13 | Mandatory learning rules, confidential reporting, restricted case management |
| `commerce` | 17 | Fees, invoices, Paystack payments, refunds, scholarships, sponsored seats |
| `analytics` | 18 | Metric definitions, snapshots, dashboards, scheduled reports |
| `integrations` | 19 | SSO, SCORM/xAPI/LTI, webhooks, public API keys, export |
| `support` | 20 | Help centre, FAQs, tickets, complaints, status announcements |
| `notifications` | cross | Email/SMS/in-app, preferences, templates |
| `web` | §3 landing | Public site, blog, press, newsletter, demo requests |

### 4.2 Key data model (core entities)
- **User** (email login) → **Profile** (name, phone, state, LGA, gender, disability (optional, consented), languages,
  photo, bio) → **ProfessionalProfile** (professions, sports, specialisations, experience, availability, visibility).
- **Role / Permission:** Django groups + object-level scoping via **Membership(user, institution, role)**. A federation
  admin can only see records of learners linked to *their* institution (blueprint §2).
- **Course** → **CourseVersion** (immutable once published; learner records point at the version they took) →
  **Module** → **Lesson** (video, reading, interactive, SCORM, quiz, practical, live) ; **LearningPath** → ordered courses;
  **Prerequisite**; **Programme/Qualification** (rules: required courses + assessments + practicals).
- **Enrolment** (user, course version, cohort, source: self/nominated/sponsored/paid, status) → **LessonProgress**,
  **Note**, **Bookmark**, **xAPIStatement**.
- **QuestionBank → Question (types: MCQ, multi-select, T/F, short, essay, case, image, video) → ExamBlueprint → Exam →
  Attempt → Response → Mark**; **Rubric**; **Moderation**; **Appeal**; **Resit**.
- **PracticalTask → Submission (files/video) → SupervisorSignOff**; **SimulationScenario → SimulationRun**.
- **CredentialType** (*completion certificate / assessed competence / professional qualification / licence (external)*)
  — kept distinct everywhere (blueprint Module 5 rule) → **Credential** (UUID, code, QR, issued/expiry, status:
  active/expired/suspended/revoked, audit trail) ; **Badge**; **CPDActivity** (points only where approved);
  **RenewalCycle**.
- **AuditLog** (actor, action, object, before/after, IP, timestamp) written for approvals, grades, credentials,
  permissions, exports and admin actions.

### 4.3 Cross-cutting rules from the blueprint (enforced in code)
- Completion ≠ competence ≠ qualification ≠ licence: separate credential types, labels on certificates and verification page.
- Simulated results always labelled "Training exercise".
- AI never gives exam answers: the tutor is disabled inside active exam attempts and refuses item content from question banks.
- AI cites sources and states uncertainty; instructors keep control of consequential grades (AI feedback = draft only).
- Unverified profiles never shown as proof of competence; workforce search only for authorised roles; personal data minimised.
- Medical/performance/research data stored in separate restricted tables, not mixed with learning records.
- Leaderboards optional and disable-able per course/cohort.
- Dashboard metrics carry definitions; registrations vs active learners vs completions vs verified credentials are separate figures.
- NDPA 2023: consent records, privacy notice, retention schedules, data export & deletion requests.

---

## 5. Portals and navigation

### 5.1 Public (no login)
Landing · Course catalogue & course pages · Learning paths · Certifications info · **Verify a credential** (code or QR)
· Library preview (public items) · Professional public profiles (opt-in) · Opportunities board (public listings) · Blog ·
Events · FAQs/help centre · About · For institutions (demo request form) · Legal pages.

### 5.2 Learner / professional self-service (blueprint §6 navigation)
- **Home** — dashboard: continue learning, deadlines, upcoming live classes, renewals due, recommendations, announcements, streak.
- **Explore courses** — search/filter by sport, profession, level, subject, duration, language, format.
- **My learning** — enrolled courses, lesson player (resume, speed, subtitles, transcripts, notes, bookmarks, downloads),
  assessments, results, appeals.
- **Live academy** — schedule, join, recordings, office-hour booking.
- **Practical labs** — simulators, case studies, portfolio submissions, feedback.
- **Sports library** — search, read/download, collections, annotations, citations.
- **AI study assistant** — chat with citations, study plan, practice questions, revision.
- **Professional profile** — qualifications, credentials wallet, CPD log, transcript download, portfolio, visibility.
- **Careers & community** — groups, discussions, mentorship, jobs/internships, applications.
- **Research & insights** — projects, datasets, publications (for researcher role).
- **Help & support** — help centre, tickets, complaints, accessibility requests.
- **Account settings** — personal info, password, 2FA, notifications (email/SMS/in-app), data saver, language,
  offline downloads, privacy & consent, download my data, delete account request, payment history/receipts.

### 5.3 Staff & institutional admin portal (`/manage/`) — separate portal, role-scoped
| Area | Who | What |
|---|---|---|
| Overview dashboard | All staff | KPIs for their scope, tasks waiting (approvals, marking, tickets) |
| Users & roles | NIS super admin, NIS admin | Search/create/suspend users, assign roles, verify professionals, impersonation (audited), bulk import CSV |
| Institutions | NIS admin | Create federations/state councils/universities/centres, assign institution admins |
| Admissions | NIS academic | Applications, eligibility checks, documents, admit/reject, cohort allocation |
| Academic catalogue | NIS academic | Subjects, tracks, levels, programmes, qualification rules, terms, grading rules |
| Content studio | Course creators, reviewers | Course builder, versions, review queue, approve/publish/retire |
| Cohorts & enrolments | Academic, institution admin | Cohorts, calendars, nominations (federations), bulk enrol, attendance |
| Assessment centre | Instructors, examiners, moderators | Question banks, exams, scheduling, marking queue, moderation, results release, resits, appeals, item analysis |
| Practicals | Instructors, supervisors | Submission review, sign-offs, in-person session records |
| Credentials | Registrar | Issue, bulk issue, renewals, CPD approval, suspend/revoke, corrections, verification log |
| Live academy | Instructors | Schedule sessions, guest lecturers, recordings |
| Library | Librarian | Upload resources, metadata, versions, licences, access levels, review dates |
| Community moderation | Moderators | Reports, removals, user warnings, group management, opportunity approval |
| Workforce | NIS workforce unit, authorised employers | Directory search, skills map, gap analysis |
| Research | Research office | Projects, datasets access approvals, peer review, publications |
| Integrity cases | Restricted safeguarding officers only | Confidential reports, case management |
| Finance | Finance officer | Fees, invoices, payments, reconciliation, refunds, scholarships, sponsored seats |
| Communications | Comms | Announcements, email/SMS campaigns, notification templates |
| Support desk | Support agents | Tickets, SLAs, help-centre articles, FAQs, status/maintenance notices |
| Site content | Comms | Landing page sections, blog, press, testimonials, partner logos, newsletter subscribers, demo requests |
| Analytics & reports | Leadership, managers | Executive dashboards, filters, exports (CSV/XLSX/PDF), scheduled reports |
| Settings & security | Super admin | Integrations/API keys, SSO, payment keys, retention, feature flags (e.g. leaderboards), audit log viewer, data-subject requests |

Institution admins (federation / state council / employer) see a scoped version: their members, nominations,
staff qualifications, training needs, and verification of their staff — nothing from other organisations.

---

## 6. Module-by-module build scope

Each module below lists **what gets built**; phase in brackets.

1. **LMS core** [P1] — dashboard, catalogue + filters, programme → course → module → lesson, video player (HLS, speed,
   subtitles, transcript, resume), downloads, learning paths, prerequisites, reminders, notes, forums & Q&A,
   feedback surveys & ratings, cohorts/attendance/completion rules [P1]; RPL & equivalency, SCORM/xAPI [P2].
2. **Curriculum** [P1 seed → P2 expand] — taxonomy of 7 tracks + additional tracks; P1 ships seed courses in Coaching,
   Administration, Safeguarding, Anti-doping; mapping to standards (framework reference field per course).
3. **Practical labs** [P3, portfolio in P2] — portfolio submissions + supervisor sign-off [P2]; scenario engine
   (branching decisions, scored), refereeing video-incident simulator, coaching session designer, match-analysis
   annotator (timestamped tags on footage), admin/event budget sandbox, performance-load lab with sample data [P3];
   3D/advanced labs [P4].
4. **AI assistant** [P3; transcription in P2] — RAG over approved content with citations, study plans, adaptive
   revision, practice questions, instructor copilot (drafts for review), rubric pre-feedback, learning-risk alerts,
   recommendations; multilingual [P4].
5. **Credentials** [P1 completion + verify → P2 full lifecycle] — PDF certificate with QR + unique code, public
   verification page [P1]; applications, qualifications, CPD, expiry/renewal reminders, badges (Open Badges), RPL,
   appeals/holds/revocation, transcripts, portfolio export [P2].
6. **Assessment engine** [P1 core → P2 advanced] — banks, randomisation, timed exams, auto-marking, rubrics [P1];
   video/image questions, oral/live exams, video evidence, moderation, resits, appeals, plagiarism check (similarity
   across submissions), item analysis (difficulty/discrimination), proctoring-lite (webcam snapshots, opt-in with
   accessible alternative) [P2].
7. **Mobile & offline** [P1 responsive/low-bandwidth → P2 offline] — PWA, data-saver mode, audio-only, text
   alternatives [P1]; offline lesson packs, queued exam submissions with integrity hash, resumable downloads [P2];
   native apps only if justified [P4].
8. **Virtual classrooms** [P2] — scheduling, Jitsi rooms, attendance, polls/Q&A, recordings (consent), office hours,
   guest lecturers, co-teaching across institutions, blended in-person sessions.
9. **Digital library** [P2] — resources with metadata, versions, licences, access levels, collections, annotations,
   citation export (APA/Harvard/BibTeX), external links (IOC/WADA).
10. **Community** [P3] — verified profiles, groups by sport/discipline, moderated discussions, alumni, mentorship
    matching & booking, opportunities board (jobs/internships/volunteering), conduct rules, report button.
11. **Workforce database** [P3] — directory built from verified credentials + profile, availability/preferences,
    authorised search, aggregated skills map by state & sport (choropleth of Nigeria's 36 states + FCT).
12. **Research centre** [P3] — projects, proposals & ethics checklist, datasets with access approval, peer review,
    publications, M&E of NIS programmes, institutional dashboards.
13. **Integrity & safeguarding** [P1 courses → P3 reporting] — mandatory course rules per role (e.g. coaches must hold
    current safeguarding cert) [P1]; confidential reporting form + restricted case management [P3].
14. **Business & careers** [P2] — curriculum track + practical project templates (business plan, sponsorship proposal,
    event budget) graded with rubrics; CV builder from profile.
15. **Gamification** [P1 basic → P2] — progress bars, streaks, badges, milestones [P1]; optional leaderboards,
    challenges, team competitions, configurable/disabled per cohort [P2].
16. **Content studio** [P1 basic → P2 full] — course builder, uploads, question banks, approval workflow, versions [P1];
    templates, external reviewers, scheduled publishing, AI drafting, course performance reports [P2].
17. **Institutional admin** [P1] — institutions, admissions, calendars, instructors, fees/payments, comms, audit,
    granular permissions (academic vs finance vs institutional).
18. **Analytics** [P1 basic → P3 observatory] — learner/learning/qualification/reach/quality dashboards with metric
    definitions and filters, CSV/PDF export [P1]; scheduled reports, cohort comparisons, impact & longitudinal,
    national observatory [P3].
19. **Integrations** [P1 email/SMS/payment → P2+] — SMTP, Termii, Paystack [P1]; SSO (OIDC/SAML), LTI, SCORM/xAPI,
    Open Badges, webhooks, public REST API with keys, bulk export/migration [P2]; federation registries, government
    ID verification (only if authorised) [P4].
20. **Helpdesk** [P1] — help centre & FAQs, tickets (priority/owner/status/SLA), account recovery, maintenance
    notices, complaints, accessibility requests; AI first-line support with human escalation [P3].

---

## 7. Delivery phases (build order)

### Phase 0 — Foundations (week 1–2)
Repo, Docker, settings (dev/staging/prod), Postgres, Redis, Celery, Tailwind build, design tokens, base templates,
auth + 2FA, roles/permissions framework, audit log, CI (lint + tests), seed command.

### Phase 1 — Institutional foundation (MVP) (≈ weeks 3–12)
Landing page (full Talstack-style), public catalogue, accounts & self-service, institutions & memberships, content
studio (basic + approval), LMS core with video pipeline, assessments (core), progress, completion certificates +
public verification, gamification basics, notifications, payments (Paystack), helpdesk, institutional admin portal,
basic analytics, PWA + data saver, seed curriculum (coaching, administration, safeguarding, anti-doping).
**Exit criteria:** a learner can sign up → enrol → watch → pass exam → receive a QR certificate that verifies publicly;
NIS staff can build, approve and publish a course and see dashboards; federation admin sees only their staff.

### Phase 2 — Professional development (≈ weeks 13–22)
Qualifications & programmes, full credential lifecycle (CPD, renewals, badges, revocation, appeals), advanced
assessment, practical portfolio + supervisor sign-off, live classrooms, digital library, full studio, offline packs,
SCORM/xAPI/LTI/SSO, business & careers track, transcription/subtitles.

### Phase 3 — Intelligence & automation (≈ weeks 23–32)
AI study assistant + instructor copilot + risk alerts, simulators & labs, workforce directory & skills map,
community/mentorship/opportunities, research centre, integrity reporting & case management, observatory analytics,
AI first-line support.

### Phase 4 — National & international expansion (≈ weeks 33+)
Additional languages (Pidgin, Yoruba, Hausa, Igbo) with reviewed translations, external qualification recognition,
advanced/3D labs, federation registry & ID integrations, native apps if justified, longitudinal evaluation.

(Durations are build estimates for planning; the blueprint requires stakeholder validation and a pilot before dates are committed.)

---

## 8. Security, privacy, reliability
- HTTPS everywhere, HSTS, secure cookies, CSRF, CSP; encryption at rest for media bucket and DB volume; field-level
  encryption for sensitive fields (disability, medical, integrity cases).
- MFA mandatory for all staff roles; login rate limiting & lockout; password + account recovery via email/SMS OTP.
- Least privilege: object-level permission checks in a single `permissions` service used by views, API and exports;
  tests assert cross-institution isolation.
- Audit log for every consequential action; immutable, viewable in admin.
- NDPA 2023: privacy notice, consent capture & withdrawal, retention jobs, data export/deletion request workflow, DPO contact.
- Backups: nightly Postgres dumps + media versioning; documented and **tested** restore; monitoring (Sentry +
  uptime) and incident runbook.
- Pre-launch independent security assessment (blueprint §4).

---

## 9. Verification (how each phase is proven)
- **Automated:** pytest unit/service tests per app; permission-isolation tests; API contract tests; Playwright E2E
  journeys; axe accessibility checks on key pages; Lighthouse performance budget (landing < 1.5 MB, LCP < 2.5s on
  throttled 3G for lesson pages).
- **Run it for real (required before handing over):** start the stack, load every page over HTTP, click through:
  1. Landing page at mobile + desktop widths, light + dark, compared side by side with talstack.com.
  2. Sign up → verify email → complete profile → enrol → watch lesson (resume works) → take exam → certificate PDF →
     scan/enter code on public verification page.
  3. Course creator drafts course → reviewer approves → published → appears in catalogue.
  4. Federation admin nominates staff, sees only their progress; tries another org's record → 403.
  5. Paid course via Paystack test mode → receipt → enrolment; refund from finance portal.
  6. Support ticket raised by learner, answered by agent.
- **Seed data:** `python manage.py seed_demo` creates realistic institutions, users per role, courses, exams and
  certificates so every screen can be demoed.
- **README** with setup, env vars, demo accounts per role and the walkthrough above.

---

## 10. Project structure
```
SportIQ/
  plans/                    implementation_plan.md, tasks.md
  sportiq/                  Django project (settings/base.py, dev.py, prod.py, urls, celery.py)
  apps/                     core, accounts, institutions, catalog, studio, learning, media, assessments,
                            practicals, credentials, live, library, ai, community, workforce, research,
                            integrity, commerce, analytics, integrations, support, notifications, web
  templates/                base, public/, learner/, manage/, components/
  static/src/               tailwind.css (tokens), js (htmx, alpine, player, offline sw)
  docker/, docker-compose.yml, .env.example, README.md
  tests/e2e/                Playwright journeys
```

---

## 11. Build log and decisions

**2026-10-15: Phase 0 and Phase 1 built.** Changes from §2, made during the build:
- **Front end:** a hand-written design system (`static/css/sportiq.css`, CSS tokens) and a small vanilla JS file
  instead of Tailwind + HTMX + Alpine, so there is no Node build step. Talstack's radii and spacing scale are reproduced
  exactly, with fonts Instrument Sans + Fraunces.
- **Auth:** our own email login, verification, lockout and password reset on Django auth (no django-allauth yet);
  TOTP two-factor via django-otp, enforced for back-office staff when `DEBUG=false`.
- **PDFs:** ReportLab instead of WeasyPrint (WeasyPrint needs GTK on Windows).
- **Dev database:** SQLite by default; PostgreSQL via `DATABASE_URL` (docker-compose). pgvector is deferred to Phase 3 (AI).
- **Results release:** examiner-marked answers are never auto-released, even when an exam has auto-release on.
  Only fully auto-marked attempts release immediately.
- **Demo content honesty:** sample testimonials carry an "Illustrative" label, and press mentions are left empty
  until real coverage exists.

**2026-10-15: Phases 2–4 built.** New apps: practicals, live, library, integrations, careers, ai, labs,
community, workforce, research, integrity. Decisions:
- **AI retrieval:** BM25 over approved-content chunks in the database instead of pgvector embeddings (simpler, no
  embedding service, fast enough for the NIS corpus; can be swapped later). Generation uses Claude `claude-opus-5-5`
  with server-side refusal fallbacks; without a key the assistant quotes approved passages with citations.
- **Integrity cases** are encrypted at rest (Fernet) and restricted to safeguarding officers; super admins don't
  inherit access.
- **Labs** are generic engines (branching, annotate, load, designer, budget) driven by JSON scenarios that staff
  manage in the back office.
- **Phase 4 adapters** (federation registry, identity verification) ship disabled with a sandbox; enable only with
  legal authority and data-sharing agreements.
- **Not built:** speech-to-text transcription, native apps, 3D/VR simulations, real connections to LTI/SSO/identity
  providers (code exists but is unverified against real systems), reviewed translations.
