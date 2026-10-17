# SportIQ — NIS Digital Sports Academy

SportIQ is a national sports education and professional development platform for the National Institute for
Sports (NIS), built by Made In Africa Sport from the *SportIQ Blueprint for Digital Sports Academy*.
It combines learning, assessment, verifiable credentials, practical labs, an AI study assistant, a library,
community and careers, a national workforce directory, research and impact evaluation, all on one learner
record. The public site follows the structure of talstack.com, re-skinned in Nigerian national colours.

Plans are in [`plans/`](plans/): `implementation_plan.md` (architecture, all 20 modules, build log) and `tasks.md`
(progress, item by item, with honest notes on anything partial).

## What's built (all four phases)

| Area | Highlights |
|---|---|
| **Public site** | Talstack-style landing page, catalogue, learning paths, credential verification, library (public items), opportunities board, observatory, confidential integrity reporting, blog/events/FAQs, PWA |
| **Learning** | Video lessons (adaptive HLS, captions, transcripts, audio-only, data saver), reading/download/quiz/practical/lab/live/SCORM/embedded lessons, notes, bookmarks, discussions, feedback, offline lesson packs |
| **Assessment** | Banks with topic blueprints, MCQ/multi/TF/short/essay/case/image/video items, timed exams with autosave and offline-safe answers, identity declaration, webcam invigilation (with accessible alternative), scheduled windows, moderation by a second marker, similarity checks, appeals/resits, item analysis (facility and discrimination), pre-tests |
| **Credentials** | Completion certificates (PDF + QR), NIS qualifications awarded automatically from courses + supervised practicals, CPD log and approval, renewals, recognition of prior learning, external qualifications, Open Badges 3.0 JSON, transcript, portfolio, CV |
| **Practical learning** | Portfolio tasks with rubrics, video evidence, external supervisor sign-off by secure link, simulators (refereeing, coaching, sports medicine for verified staff), match-analysis annotation, training-load lab, session designer, budget sandbox. All labelled *training exercises* |
| **Live academy** | Classes/webinars/masterclasses in embedded video rooms (Jitsi), attendance and CPD, polls, moderated Q&A, recordings with consent and retention, office-hour booking, in-person sessions with attendance register, co-teaching |
| **AI study assistant** | Answers only from approved content with citations; OpenAI (`OPENAI_MODEL`) when `OPENAI_API_KEY` is set (Anthropic optional), quoted passages otherwise; disabled during exams and refuses live exam items; study plans, revision from weak topics, practice questions, help-desk assistant with human escalation, instructor copilot (draft questions/objectives for expert review), rubric pre-feedback, learning-risk alerts |
| **Library** | Manuals, rules, policy, research, theses, case studies, video, datasets, 3D models; access levels, versions, licences/ownership, review dates, collections, reading lists, annotations, APA/Harvard/BibTeX export |
| **Community & careers** | Groups (sport, discipline, alumni, verified-only roundtables), moderated discussions, content reporting, mentorship matching, opportunities with approval, applications, public professional profiles (opt-in), experience record, challenges and optional leaderboards/team standings |
| **Workforce** | Consented directory listing, authorised and logged search for NIS/federations/state councils/employers, contact by request only, Nigeria skills map with small-number suppression and gap ranking |
| **Research & impact** | Proposals with ethics checklist and review, gated datasets, publications with peer review, evidence summaries, pre/post learning gain, delivery-mode and cohort comparisons, 6- and 12-month outcome surveys, public observatory, scheduled email reports |
| **Integrity** | Anonymous or named confidential reports, encrypted at rest, visible only to designated safeguarding officers (not even super admins), case notes, access log, status checks for reporters |
| **Back office** | Role-scoped portal for 17 staff roles + institution admins: studio with review/publish/versioning, scheduled publishing and external reviewers, assessment centre, practicals, appeals, registrar queues, live sessions, library, labs, moderation, research office, AI centre, integrations, impact, finance, support, comms, site content, audit log, data requests |
| **Integrations** | REST API with OpenAPI docs, scoped API keys, institution-scoped endpoints, signed webhooks, xAPI learning record store, SCORM 1.2/2004 player, LTI 1.3 tool, OpenID Connect SSO, full data export, federation registry and identity-verification adapters (off/sandbox by default) |
| **Languages** | Language switcher; draft Naijá, Yorùbá, Hausa and Igbo navigation (marked for expert review); expert-approved course/lesson translations shown to learners |

## Run it locally

Requirements: Python 3.12, and **ffmpeg** on PATH for video (optional).

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
copy .env.example .env            # optional
python manage.py migrate
python manage.py seed_demo        # demo data for every feature (~5 min with video; --no-video is faster)
python manage.py runserver
```

Open http://127.0.0.1:8000. Re-seed from scratch with `seed_demo --reset` (development only).

### Demo accounts (password for all: `SportIQ-demo-2026`)

| Email | Role | Try this |
|---|---|---|
| `learner@sportiq.test` | Coach (Amina Okafor) | Dashboard, Safeguarding course, AI assistant, labs, Level 1 qualification progress, CPD, community |
| `admin@sportiq.test` | Super administrator | Everything except confidential integrity cases |
| `nisadmin@sportiq.test` | NIS administrator | Users, institutions, all academic areas |
| `academic@sportiq.test` | Academic manager | Publish courses, cohorts, translations, challenges |
| `creator@sportiq.test` | Course creator + instructor | Studio, copilot, SCORM upload, practical tasks, labs |
| `reviewer@sportiq.test` | Academic reviewer | Review queue |
| `expert@sportiq.test` | External subject reviewer | Comment on the course assigned to them |
| `instructor@sportiq.test` | Instructor / examiner | Mark the waiting essay, assess practicals, appeals, live sessions, AI risk alerts |
| `registrar@sportiq.test` | Registrar | CPD approvals, renewals, prior-learning claims, external qualifications, credentials |
| `finance@sportiq.test` | Finance officer | Payments, refunds, scholarship codes |
| `support@sportiq.test` | Support agent | Tickets, help articles, service notices |
| `comms@sportiq.test` | Communications | Landing page content, announcements, campaigns |
| `analyst@sportiq.test` | Analyst | Analytics, impact, scheduled reports |
| `safeguarding@sportiq.test` | Safeguarding officer | Confidential integrity cases (submit one at `/integrity/report/` first) |
| `research@sportiq.test` | Research office | Ethics review, dataset requests, peer review |
| `moderator@sportiq.test` | Community moderator | Reports, opportunity approvals, mentor approvals |
| `librarian@sportiq.test` | Librarian | Library resources and reading lists |
| `workforce@sportiq.test` | Workforce unit | Directory search, skills map |
| `federation@sportiq.test` | Federation administrator | Institution portal, find professionals, skills map |
| `council@sportiq.test` | State council administrator | Institution portal |

Scholarship codes: `NFA-COACH-2026` (100%, Coaching Foundations) and `WELCOME20`.
Identity verification sandbox (set `IDENTITY_VERIFICATION_ENABLED=true`): 11-digit numbers ending in an even digit match.

## Configuration (`.env`)

Everything works without keys. These switch on real services:

| Variable | Effect |
|---|---|
| `OPENAI_API_KEY` (+ `OPENAI_MODEL`, default `gpt-4.1-mini`; use any chat model your account has) | AI-written, cited answers, study-plan narratives, copilot drafts, rubric feedback. Without it: quoted passages + rule-based drafts. (`AI_PROVIDER=anthropic` + `ANTHROPIC_API_KEY` is also supported) |
| `PAYSTACK_SECRET_KEY` | Real payments (otherwise a test-mode page) |
| `TERMII_API_KEY` | Real SMS |
| `EMAIL_BACKEND`, `EMAIL_HOST`… | Real email |
| `JITSI_DOMAIN` | Your own video server (default public `meet.jit.si`; self-host for production) |
| `INTEGRITY_ENCRYPTION_KEY` | Fernet key for integrity cases. **Set in production** (dev derives one from `SECRET_KEY`) |
| `OIDC_*` | Single sign-on for institutional users |
| `FEDERATION_REGISTRY_URL/TOKEN`, `IDENTITY_VERIFICATION_*` | Phase 4 adapters: only where legally authorised |
| `ANDROID_APP_PACKAGE`, `ANDROID_CERT_SHA256` | Digital Asset Links for an Android TWA wrapper of the PWA |
| `CELERY_BROKER_URL` | Background jobs (otherwise run inline) |

## Verify

```bash
pytest                         # 78 tests: journeys, permissions, workflows, payments, AI guardrails, labs, integrations, i18n
python manage.py crawl         # logs in as every role and follows every link; reports any error
python manage.py run_daily_jobs  # reminders, outcome surveys, scheduled publishing, AI re-index, risk scan, reports, snapshot
```

## Production

`docker compose up --build` (PostgreSQL, Redis, web, Celery worker and beat). Set `DEBUG=false`, `SECRET_KEY`,
`ALLOWED_HOSTS`, `SITE_URL`, `INTEGRITY_ENCRYPTION_KEY` and the integration keys. Rebuild translations after editing
them with `python locale/build_catalogs.py`. Run an independent security assessment before public launch.

## Layout

```
apps/   core accounts institutions catalog learning assessments credentials commerce support notifications analytics
        web backoffice practicals live library integrations careers ai labs community workforce research integrity
templates/  public/ app/ manage/ + one folder per app        static/  css, js (sportiq.js, offline.js, sw.js)
locale/     draft interface translations + build script       plans/   implementation plan and tasks
tests/      pytest suite
```
