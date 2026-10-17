"""Create realistic demo data so every screen can be exercised.

    python manage.py seed_demo            # add demo data (idempotent for fixed records)
    python manage.py seed_demo --reset    # wipe the database first (dev only!)
"""
import random
import shutil
import subprocess
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.conf import settings
from django.core.files import File
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import NIGERIAN_STATES, Consent, User
from apps.assessments.models import Attempt, Choice, Exam, Question, QuestionBank, Response
from apps.catalog.models import Course, LearningPath, LearningPathItem, Lesson, Module, Profession, Sport, Subject, Track
from apps.commerce.models import Order, Voucher
from apps.core.models import SiteSettings
from apps.credentials.models import CredentialType, MandatoryRequirement
from apps.institutions.models import Institution, Membership
from apps.learning import services as learning
from apps.learning.models import ActivityDay, Application, Cohort, CourseFeedback, Enrolment, LessonProgress, Post, Thread
from apps.notifications.models import Announcement
from apps.support.models import HelpArticle, HelpCategory, Ticket, TicketMessage
from apps.web.models import BlogPost, DemoRequest, Event, ImpactStat, NewsletterSubscriber, PartnerLogo, Testimonial

from . import seed_content as C

PASSWORD = "SportIQ-demo-2026"
FIRST = ["Amina", "Chidi", "Tunde", "Ngozi", "Ibrahim", "Funke", "Emeka", "Halima", "Segun", "Bisi", "Yusuf", "Ifeoma",
         "Musa", "Kemi", "Obinna", "Zainab", "Femi", "Chiamaka", "Aliyu", "Bukola", "Uche", "Hadiza", "Dayo", "Nkechi",
         "Sani", "Folake", "Ikenna", "Aisha", "Gbenga", "Ebere"]
LAST = ["Okafor", "Adeyemi", "Bello", "Eze", "Abubakar", "Ogunleye", "Nwachukwu", "Mohammed", "Balogun", "Okonkwo",
        "Danjuma", "Ajayi", "Ibrahim", "Uzor", "Olatunji", "Garba", "Okeke", "Adebayo", "Yakubu", "Chukwu"]
WEIGHTED_STATES = ["Lagos"] * 8 + ["FCT"] * 4 + ["Kano"] * 4 + ["Oyo"] * 3 + ["Rivers"] * 3 + ["Kaduna"] * 3 + \
                  ["Enugu"] * 2 + ["Anambra"] * 2 + ["Delta"] * 2 + ["Edo"] * 2 + NIGERIAN_STATES

STAFF = [
    ("admin@sportiq.test", "Adaobi", "Nnamdi", ["super_admin"]),
    ("nisadmin@sportiq.test", "Garba", "Lawal", ["nis_admin"]),
    ("academic@sportiq.test", "Folasade", "Akinola", ["academic_manager"]),
    ("creator@sportiq.test", "Kelechi", "Amadi", ["course_creator", "instructor"]),
    ("reviewer@sportiq.test", "Dr Rakiya", "Usman", ["reviewer"]),
    ("instructor@sportiq.test", "Coach Bayo", "Ogundipe", ["instructor"]),
    ("registrar@sportiq.test", "Patience", "Etim", ["registrar"]),
    ("finance@sportiq.test", "Olumide", "Fashola", ["finance_officer"]),
    ("support@sportiq.test", "Grace", "Ekpo", ["support_agent"]),
    ("comms@sportiq.test", "Tobi", "Alade", ["comms_officer"]),
    ("analyst@sportiq.test", "Hassan", "Bala", ["analyst"]),
]


class Command(BaseCommand):
    help = "Seed SportIQ with realistic demo data."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Flush the database first (destroys all data).")
        parser.add_argument("--learners", type=int, default=80)
        parser.add_argument("--no-video", action="store_true", help="Skip generating and transcoding demo video.")

    def handle(self, *args, **opts):
        random.seed(2026)
        settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"  # don't print hundreds of emails
        if opts["reset"]:
            if not settings.DEBUG:
                self.stderr.write("Refusing to reset when DEBUG is off.")
                return
            call_command("flush", interactive=False, verbosity=0)
            shutil.rmtree(Path(settings.MEDIA_ROOT), ignore_errors=True)
        self.video = None if opts["no_video"] else self.make_demo_video()
        with transaction.atomic():
            self.taxonomy()
            self.credential_types()
            self.institutions_()
            self.staff()
            self.courses()
            self.paths()
            self.site_content()
            self.help_centre()
        self.learners(opts["learners"])
        self.transcode()
        from .seed_phase2 import seed_phase2

        seed_phase2(self, PASSWORD)
        self.stdout.write(self.style.SUCCESS(f"Demo data ready. All demo accounts use the password: {PASSWORD}"))

    # --- reference data -----------------------------------------------------------------
    def taxonomy(self):
        for i, (name, plural, icon, desc) in enumerate(C.PROFESSIONS):
            Profession.objects.update_or_create(name=name, defaults={"plural": plural, "icon": icon, "description": desc, "order": i})
        for s in C.SPORTS:
            Sport.objects.get_or_create(name=s)
        for i, (name, subjects) in enumerate(C.TRACKS):
            t, _ = Track.objects.update_or_create(name=name, defaults={"order": i})
            for s in subjects:
                Subject.objects.get_or_create(track=t, name=s)

    def credential_types(self):
        types = [
            ("course-completion", "Certificate of Completion", "completion", None),
            ("safeguarding", "Safeguarding Certificate", "completion", 24),
            ("anti-doping", "Clean Sport Certificate", "completion", 24),
            ("coaching-l1", "NIS Coaching Certificate, Level 1", "qualification", 36),
            ("first-aid", "First Aid in Sport: Assessed Competence", "competence", 24),
        ]
        for code, name, kind, months in types:
            CredentialType.objects.update_or_create(code=code, defaults={"name": name, "kind": kind, "validity_months": months})

    def institutions_(self):
        football = Sport.objects.get(name="Football")
        athletics = Sport.objects.get(name="Athletics")
        rows = [
            ("NIS Coaching Department", "nis", "Lagos", None),
            ("NIS Sports Medicine Unit", "nis", "Lagos", None),
            ("National Football Association (demo)", "federation", "FCT", football),
            ("National Athletics Association (demo)", "federation", "FCT", athletics),
            ("Lagos State Sports Council (demo)", "state_council", "Lagos", None),
            ("Kano State Sports Council (demo)", "state_council", "Kano", None),
            ("Ibadan University Sports Science (demo)", "university", "Oyo", None),
            ("Surulere Youth Football Academy (demo)", "employer", "Lagos", football),
        ]
        for name, kind, state, sport in rows:
            Institution.objects.update_or_create(name=name, defaults={"kind": kind, "state": state, "sport": sport})

    def user(self, email, first, last, **extra):
        u, created = User.objects.get_or_create(email=email, defaults={"first_name": first, "last_name": last,
                                                                       "email_verified": True, **extra})
        if created:
            u.set_password(PASSWORD)
            u.save()
            Consent.objects.create(user=u, kind="terms")
            Consent.objects.create(user=u, kind="privacy")
        return u

    def staff(self):
        for email, first, last, roles in STAFF:
            u = self.user(email, first, last, state="Lagos")
            u.staff_roles, u.is_staff = roles, True
            if "super_admin" in roles:
                u.is_superuser = True
            u.save()
        fed = Institution.objects.get(name__startswith="National Football")
        council = Institution.objects.get(name__startswith="Lagos State")
        for email, first, last, inst in [("federation@sportiq.test", "Mohammed", "Sanusi", fed),
                                         ("council@sportiq.test", "Ronke", "Adewale", council)]:
            u = self.user(email, first, last, state=inst.state)
            Membership.objects.update_or_create(user=u, institution=inst, defaults={"role": "admin", "is_verified": True,
                                                                                    "job_title": "Education officer"})

    # --- courses ----------------------------------------------------------------------
    def course(self, spec, owner, light=False):
        track = Track.objects.get(name=spec["track"])
        ctype = CredentialType.objects.filter(code=spec.get("credential", "course-completion")).first()
        today = timezone.localdate()
        course, created = Course.objects.update_or_create(code=spec["code"], defaults={
            "title": spec["title"], "summary": spec["summary"], "description": spec.get("description", spec["summary"]),
            "track": track, "level": spec["level"], "price_kobo": spec["price"], "duration_hours": Decimal(str(spec["hours"])),
            "cover_color": spec["color"], "featured": spec.get("featured", False), "objectives": spec["objectives"],
            "audience": spec.get("audience", "Sports professionals in Nigeria."),
            "assessment_criteria": spec.get("assessment", "Online assessment. Pass mark 70%. Three attempts."),
            "references": spec.get("references", "NIS course manual"), "framework_mapping": spec.get("framework", ""),
            "revision_date": today - timedelta(days=60), "review_due": today + timedelta(days=300),
            "credential_type": ctype, "owner": owner, "created_by": owner, "status": Course.PUBLISHED,
            "version": 1, "published_at": timezone.now() - timedelta(days=random.randint(120, 330)),
            "institution": Institution.objects.get(name="NIS Coaching Department"),
            "language": "en", "delivery_format": spec.get("format", "self_paced"),
        })
        if not created:
            return course
        course.professions.set(Profession.objects.filter(name__in=spec["professions"]))
        course.instructors.add(User.objects.get(email="instructor@sportiq.test"), owner)
        bank = QuestionBank.objects.create(course=course, title=f"{course.title} question bank")
        for q in spec["questions"]:
            kind, text, choices = q[0], q[1], q[2]
            explanation = q[3] if len(q) > 3 else ""
            topic = q[4] if len(q) > 4 else ""
            question = Question.objects.create(bank=bank, kind=kind, text=text, explanation=explanation, topic=topic,
                                               points=5 if kind == "essay" else 1,
                                               model_answer="Look for: calm response, no promises of secrecy, accurate record, prompt referral to the designated officer." if kind == "essay" else "")
            for i, c in enumerate(choices):
                Choice.objects.create(question=question, text=c.lstrip("* ").strip(), is_correct=c.startswith("*"), order=i)
        exam_cfg = spec.get("exam", {"count": len(spec["questions"]), "pass": 70})
        exam = Exam.objects.create(course=course, bank=bank, title=f"{course.title}: final assessment", is_final=True,
                                   is_published=True, question_count=exam_cfg["count"], pass_mark=exam_cfg["pass"],
                                   time_limit_minutes=20, instructions="Answer every question. You can change answers until you submit.")
        for mi, (mtitle, lessons) in enumerate(spec["modules"], start=1):
            module = Module.objects.create(course=course, title=mtitle, order=mi)
            for li, lesson in enumerate(lessons, start=1):
                title, kind, body, preview = lesson
                l = Lesson.objects.create(module=module, title=title, kind=kind, body=body, order=li, is_preview=preview,
                                          duration_minutes=12 if kind == "video" else 8, exam=exam if kind == "quiz" else None,
                                          transcript=body.replace("**", "") if kind == "video" else "")
                if kind == "video" and self.video:
                    with open(self.video, "rb") as fh:
                        l.video.save(f"{course.code.lower()}-{mi}-{li}.mp4", File(fh), save=True)
                    vtt = Path(settings.MEDIA_ROOT) / "lessons" / "subtitles" / f"lesson-{l.pk}.vtt"
                    vtt.parent.mkdir(parents=True, exist_ok=True)
                    vtt.write_text("WEBVTT\n\n00:00.000 --> 00:06.000\n" + title + "\n\n00:06.000 --> 00:20.000\n"
                                   "SportIQ: the digital academy for Nigerian sport\n", encoding="utf-8")
                    l.subtitles.name = f"lessons/subtitles/lesson-{l.pk}.vtt"
                    l.media_status = "processing"
                    l.save()
                if kind == "download":
                    path = Path(settings.MEDIA_ROOT) / "lessons" / "files" / "nis-session-plan-template.txt"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_text("NIS SESSION PLAN TEMPLATE\n\nCoach:\nDate:\nGroup / age:\nLearning objective:\n\n"
                                    "Warm-up (10 min):\nSkill development (20 min):\nGame-related practice (20 min):\n"
                                    "Cool-down & review (10 min):\n\nSafety checks:\nAdaptations (STEP):\n", encoding="utf-8")
                    l.attachment.name = "lessons/files/nis-session-plan-template.txt"
                    l.save()
        for name in spec.get("mandatory_for", []):
            MandatoryRequirement.objects.get_or_create(profession=Profession.objects.get(name=name), course=course)
        return course

    def light_spec(self, row):
        title, code, track, level, price, hours, color, profs, summary, objectives, modules, questions = row
        mods = []
        for mtitle, lessons in modules:
            items = []
            for i, lt in enumerate(lessons):
                if lt == "Assessment":
                    items.append(("Final assessment", "quiz", "Answer the questions to complete the course.", False))
                else:
                    kind = "video" if i == 0 and len(mods) == 0 else "reading"
                    body = (f"## {lt}\n\n{summary}\n\nIn this lesson you will:\n\n" +
                            "\n".join(f"- {o}" for o in objectives) +
                            "\n\n> Apply what you learn in your next session and note one thing to improve.")
                    items.append((lt, kind, body, i == 0 and len(mods) == 0))
            mods.append((mtitle, items))
        return {"title": title, "code": code, "track": track, "level": level, "price": price, "hours": hours,
                "color": color, "professions": profs, "summary": summary, "objectives": "\n".join(objectives),
                "modules": mods, "questions": [(k, t, ch, "", "") for k, t, ch in questions],
                "exam": {"count": len(questions), "pass": 60}}

    def courses(self):
        creator = User.objects.get(email="creator@sportiq.test")
        for spec in C.COURSES:
            self.course(spec, creator)
        for row in C.LIGHT_COURSES:
            self.course(self.light_spec(row), creator)
        # Prerequisite and an application-only programme
        l1 = Course.objects.get(code="NIS-COA-101")
        grassroots = Course.objects.get(code="NIS-FBL-120")
        grassroots.prerequisites.add(Course.objects.get(code="NIS-SAF-101"))
        grassroots.sports.add(Sport.objects.get(name="Football"))
        gov = Course.objects.get(code="NIS-ADM-201")
        gov.requires_application = True
        gov.prerequisites_text = "At least one year working in a federation, state council or club administration."
        gov.save()
        # Studio examples: one draft and one awaiting review
        for title, status in [("First Aid in Sport", Course.DRAFT), ("Talent Identification in Athletics", Course.IN_REVIEW)]:
            c, created = Course.objects.get_or_create(title=title, defaults={
                "code": "NIS-DRAFT-" + str(len(title)), "summary": f"{title}: course in development.",
                "track": Track.objects.get(name="Sports science, medicine & performance" if "Aid" in title else "Coaching & technical development"),
                "owner": creator, "created_by": creator, "status": status, "price_kobo": 500000,
                "objectives": "Draft objective" if status == Course.IN_REVIEW else "",
            })
            if created:
                m = Module.objects.create(course=c, title="Introduction", order=1)
                Lesson.objects.create(module=m, title="Welcome", kind="reading", body="Draft content.", order=1)
        self.l1 = l1

    def paths(self):
        coach, _ = LearningPath.objects.get_or_create(title="Become a qualified coach", defaults={
            "summary": "From safeguarding essentials to NIS Coaching Level 1 and sport-specific coaching.",
            "profession": Profession.objects.get(name="Coach"), "description": "The recommended route for new and volunteer coaches.",
        })
        if not coach.items.exists():
            for i, (code, stage) in enumerate([("NIS-SAF-101", "intro"), ("NIS-ADP-101", "intro"), ("NIS-COA-101", "beginner"),
                                               ("NIS-FBL-120", "intermediate"), ("NIS-SCI-150", "advanced")]):
                LearningPathItem.objects.create(path=coach, course=Course.objects.get(code=code), stage=stage, order=i)
        ath, _ = LearningPath.objects.get_or_create(title="The professional athlete", defaults={
            "summary": "Clean sport, nutrition, money and career planning for athletes.",
            "profession": Profession.objects.get(name="Athlete"), "cover_color": "#006B40",
        })
        if not ath.items.exists():
            for i, (code, stage) in enumerate([("NIS-ADP-101", "intro"), ("NIS-NUT-101", "beginner"), ("NIS-CAR-101", "beginner"),
                                               ("NIS-SCI-150", "intermediate")]):
                LearningPathItem.objects.create(path=ath, course=Course.objects.get(code=code), stage=stage, order=i)
        adm, _ = LearningPath.objects.get_or_create(title="Sports administration leader", defaults={
            "summary": "Governance, events and finance for federation and club administrators.",
            "profession": Profession.objects.get(name="Sports administrator"), "cover_color": "#0E4A37",
        })
        if not adm.items.exists():
            for i, (code, stage) in enumerate([("NIS-SAF-101", "intro"), ("NIS-BUS-210", "intermediate"), ("NIS-ADM-201", "advanced")]):
                LearningPathItem.objects.create(path=adm, course=Course.objects.get(code=code), stage=stage, order=i)

    # --- site content ---------------------------------------------------------------------
    def site_content(self):
        SiteSettings.load()
        if not PartnerLogo.objects.exists():
            for i, n in enumerate(["National Institute for Sports", "Sports federations", "State sports councils",
                                   "Universities", "Clubs & academies", "Made In Africa Sport"]):
                PartnerLogo.objects.create(name=n, order=i)
        if not Testimonial.objects.exists():
            for i, (name, role, quote) in enumerate(C.TESTIMONIALS):
                Testimonial.objects.create(name=name, role=role, quote=quote, order=i, is_sample=True)
        if not ImpactStat.objects.exists():
            for i, (label, value) in enumerate([("Sports professionals trained (target, year 1)", "10,000+"),
                                                ("States + FCT reached", "37"), ("Sports professions served", "12"),
                                                ("Courses at launch", "25+")]):
                ImpactStat.objects.create(label=label, value=value, order=i)
        # Press mentions are left empty: they must only ever list real coverage.
        if not BlogPost.objects.exists():
            author = User.objects.get(email="comms@sportiq.test")
            for i, (title, excerpt, mins, color) in enumerate(C.BLOG):
                BlogPost.objects.create(title=title, excerpt=excerpt, read_minutes=mins, cover_color=color, author=author,
                                        published_at=timezone.now() - timedelta(days=3 + i * 9),
                                        body=f"{excerpt}\n\n## What you need to know\n\nSportIQ brings structured, verifiable learning to every sports profession in Nigeria. "
                                             "This article explains the key ideas in plain language and points you to the courses that go deeper.\n\n"
                                             "- Learn at your own pace on any phone\n- Earn a certificate employers can verify\n- Keep your skills current with CPD\n\n"
                                             "Ready to start? [Browse the course catalogue](/courses/).")
        if not Event.objects.exists():
            for title, days, loc in [("Safeguarding in Sport: live Q&A", 6, "Online"), ("Coach educators' masterclass", 20, "National Stadium, Surulere, Lagos"),
                                     ("Clean Sport Day for athletes", 35, "Package B, Moshood Abiola Stadium, Abuja"), ("Sports data storytelling workshop", -14, "Online")]:
                Event.objects.create(title=title, starts_at=timezone.now() + timedelta(days=days, hours=10),
                                     location=loc, description="Free for registered SportIQ learners. Certificates of attendance count towards CPD.")
        if not Announcement.objects.exists():
            Announcement.objects.create(title="Safeguarding certificate now mandatory for coaches",
                                        body="All registered coaches must hold a current Safeguarding Certificate. The course is free and takes about three hours.",
                                        audience="profession", profession=Profession.objects.get(name="Coach"))
            Announcement.objects.create(title="Welcome to SportIQ", body="Explore the free essentials courses and install SportIQ on your phone for quick access.", audience="all")
        if not DemoRequest.objects.exists():
            DemoRequest.objects.create(name="Bola Ahmed", email="bola@example.org", organisation="Ogun State Sports Council (demo)",
                                       organisation_type="State sports council", learners_estimate="251-1000",
                                       message="We want to train all our coaches in safeguarding before the school games.")
        for e in ["fan1@example.org", "fan2@example.org", "coachnews@example.org"]:
            NewsletterSubscriber.objects.get_or_create(email=e)
        Voucher.objects.get_or_create(code="NFA-COACH-2026", defaults={
            "course": self.l1, "discount_percent": 100, "max_uses": 50,
            "sponsor": Institution.objects.get(name__startswith="National Football")})
        Voucher.objects.get_or_create(code="WELCOME20", defaults={"discount_percent": 20, "max_uses": 500})

    def help_centre(self):
        for i, (cat, articles) in enumerate(C.HELP.items()):
            c, _ = HelpCategory.objects.get_or_create(name=cat, defaults={"order": i})
            for j, (title, body, faq) in enumerate(articles):
                HelpArticle.objects.get_or_create(title=title, defaults={"category": c, "body": body, "is_faq": faq, "order": j})

    # --- learners & activity ------------------------------------------------------------------
    def learners(self, n):
        if User.objects.filter(email="learner@sportiq.test").exists():
            self.stdout.write("Learners already seeded; skipping.")
            return
        now = timezone.now()
        professions = list(Profession.objects.all())
        courses = list(Course.objects.published())
        fed = Institution.objects.get(name__startswith="National Football")
        council = Institution.objects.get(name__startswith="Lagos State")
        demo = self.user("learner@sportiq.test", "Amina", "Okafor", state="Lagos", lga="Surulere", phone="+2348012345678",
                         gender="female", languages="English, Igbo", bio="Grassroots football coach working with U-15 girls.")
        demo.date_joined = now - timedelta(days=75)
        demo.save()
        demo.professions.set(Profession.objects.filter(name__in=["Coach"]))
        demo.sports.set(Sport.objects.filter(name="Football"))
        Membership.objects.get_or_create(user=demo, institution=fed, defaults={"role": "member", "is_verified": True})
        users = [demo]
        for i in range(n):
            first, last = random.choice(FIRST), random.choice(LAST)
            u = self.user(f"{first.lower()}.{last.lower()}{i}@example.ng", first, last, state=random.choice(WEIGHTED_STATES),
                          gender=random.choice(["female", "male"]))
            u.date_joined = now - timedelta(days=random.randint(1, 360))
            u.save()
            u.professions.set(random.sample(professions, k=random.choice([1, 1, 2])))
            if random.random() < 0.25:
                Membership.objects.get_or_create(user=u, institution=random.choice([fed, council]), defaults={"role": "member"})
            users.append(u)
        safeguarding = Course.objects.get(code="NIS-SAF-101")
        antidoping = Course.objects.get(code="NIS-ADP-101")
        for u in users:
            picks = random.sample(courses, k=random.randint(1, 4))
            if u == demo:
                picks = [antidoping, safeguarding, self.l1]
            for c in picks:
                started = max(u.date_joined, now - timedelta(days=300)) + timedelta(days=random.randint(0, 20))
                if started > now:
                    started = now - timedelta(days=1)
                if c.price_kobo:
                    o = Order.objects.create(user=u, course=c, list_price_kobo=c.price_kobo, amount_kobo=c.price_kobo,
                                             status="paid", paid_at=started, provider_payload={"simulated": True},
                                             reconciled=random.random() < 0.6)
                    Order.objects.filter(pk=o.pk).update(created_at=started)
                enr = Enrolment.objects.create(user=u, course=c, source="paid" if c.price_kobo else "self",
                                               course_version=1, last_activity_at=started)
                Enrolment.objects.filter(pk=enr.pk).update(created_at=started)
                lessons = list(c.lessons())
                if u == demo:
                    target = {antidoping.pk: 1.0, safeguarding.pk: 0.6, self.l1.pk: 0.2}[c.pk]
                else:
                    target = random.choice([0.2, 0.5, 0.8, 1.0, 1.0])
                done = lessons[: max(1, int(len(lessons) * target))] if target < 1 else lessons
                for k, lesson in enumerate(done):
                    if lesson.kind == "quiz":
                        continue
                    LessonProgress.objects.create(enrolment=enr, lesson=lesson, completed=True,
                                                  completed_at=started + timedelta(days=k))
                    ActivityDay.objects.get_or_create(user=u, date=(started + timedelta(days=k)).date(),
                                                      defaults={"lessons_completed": 1})
                if target >= 1:
                    self.pass_exam(u, c, started + timedelta(days=len(done)))
                    quiz = [l for l in lessons if l.kind == "quiz"]
                    for lesson in quiz:
                        LessonProgress.objects.get_or_create(enrolment=enr, lesson=lesson, defaults={"completed": True})
                    enr.refresh_from_db()
                    learning.check_completion(enr)
                    enr.refresh_from_db()
                    when = started + timedelta(days=len(done) + 1)
                    Enrolment.objects.filter(pk=enr.pk).update(completed_at=min(when, now), last_activity_at=min(when, now))
                    u.credentials.filter(course=c).update(issued_at=min(when, now))
                    if random.random() < 0.7:
                        CourseFeedback.objects.create(enrolment=enr, course_rating=random.choice([4, 5, 5, 4, 3]),
                                                      instructor_rating=random.choice([4, 5]), relevance_rating=5,
                                                      comment=random.choice(["Very practical.", "Loved the case studies.", "", "More videos please."]))
                else:
                    enr.recompute_progress()
                    enr.last_lesson = done[-1] if done else None
                    enr.save(update_fields=["progress", "last_lesson"])
        # Streak + recent activity for the demo learner
        for d in range(4):
            ActivityDay.objects.get_or_create(user=demo, date=timezone.localdate() - timedelta(days=d), defaults={"lessons_completed": 1})
        # A pending written-answer attempt for the marking queue (Coaching L1)
        marker_target = next((u for u in users[1:] if not u.enrolments.filter(course=self.l1).exists()), users[1])
        Enrolment.objects.get_or_create(user=marker_target, course=self.l1, defaults={"source": "paid"})
        self.written_attempt(marker_target, self.l1)
        # Applications, cohort, discussion, tickets
        gov = Course.objects.get(code="NIS-ADM-201")
        for u in users[2:5]:
            Application.objects.get_or_create(user=u, course=gov, defaults={"statement": "I have worked as secretary of my state handball association for three years and want to strengthen our governance and budgeting."})
        cohort, _ = Cohort.objects.get_or_create(course=self.l1, name="Lagos coaches, Q4 2026", defaults={
            "institution": council, "starts_on": timezone.localdate() - timedelta(days=20), "ends_on": timezone.localdate() + timedelta(days=40),
            "capacity": 40, "instructor": User.objects.get(email="instructor@sportiq.test")})
        Enrolment.objects.filter(course=self.l1, user__state="Lagos").update(cohort=cohort)
        t = Thread.objects.create(course=safeguarding, author=users[3], title="Travelling to away games with U-13s",
                                  body="What's the best practice for transport when parents can't come?")
        Post.objects.create(thread=t, author=User.objects.get(email="instructor@sportiq.test"), is_instructor_answer=True,
                            body="Always have at least two adults, get written parental consent, and never travel alone with one child. Share the itinerary with parents in advance.")
        t.is_answered = True
        t.save()
        Thread.objects.create(course=safeguarding, author=demo, title="Photographing players for our club page",
                              body="Do we need consent from parents before posting team photos?")
        tk = Ticket.objects.create(user=demo, category="technical", subject="Video keeps buffering on my phone")
        TicketMessage.objects.create(ticket=tk, author=demo, body="The lesson videos keep stopping when I'm on mobile data.")
        tk2 = Ticket.objects.create(user=users[6], category="certificate", subject="Spelling of my name on certificate")
        TicketMessage.objects.create(ticket=tk2, author=users[6], body="My surname is spelt wrongly on my anti-doping certificate.")
        self.stdout.write(f"Seeded {len(users)} learners.")

    def pass_exam(self, user, course, when):
        exam = course.final_exam()
        if not exam:
            return
        qs = list(exam.bank.questions.filter(kind__in=["mcq", "multi", "tf"])[: exam.question_count])
        att = Attempt.objects.create(exam=exam, user=user, number=1, started_at=when, deadline=when + timedelta(minutes=20),
                                     submitted_at=when + timedelta(minutes=12), max_score=len(qs))
        score = 0
        for i, q in enumerate(qs):
            right = random.random() < 0.88
            r = Response.objects.create(attempt=att, question=q, order=i, score=1 if right else 0, marked_at=when)
            if right:
                r.selected.set(q.choices.filter(is_correct=True))
                score += 1
            else:
                r.selected.set(q.choices.filter(is_correct=False)[:1])
        pct = round(Decimal(100) * score / max(len(qs), 1), 1)
        if pct < exam.pass_mark:
            pct, score = Decimal(exam.pass_mark + 5), len(qs)
        Attempt.objects.filter(pk=att.pk).update(score=score, percent=pct, passed=True, status="released", released_at=when)

    def written_attempt(self, user, course):
        exam = course.final_exam()
        essay = exam.bank.questions.filter(kind="essay").first()
        objective = list(exam.bank.questions.filter(kind="mcq")[:4])
        now = timezone.now() - timedelta(hours=5)
        att = Attempt.objects.create(exam=exam, user=user, number=1, started_at=now, deadline=now + timedelta(minutes=20),
                                     submitted_at=now + timedelta(minutes=18), status="submitted",
                                     max_score=len(objective) + (essay.points if essay else 0), integrity_flags=["left exam tab"])
        for i, q in enumerate(objective):
            r = Response.objects.create(attempt=att, question=q, order=i, score=1, marked_at=now)
            r.selected.set(q.choices.filter(is_correct=True))
        if essay:
            Response.objects.create(attempt=att, question=essay, order=len(objective),
                                    text="Objective: improve short passing accuracy for 14-year-olds.\n\nWarm-up (10 min): dynamic stretches and rondo 4v1.\n"
                                         "Skill (20 min): pairs passing through gates, progress to one-touch.\nGame (20 min): 5v5 with two-touch limit.\n"
                                         "Cool-down (10 min): light jog, questions: 'When should you play one-touch?'\nSafety: check surface, water breaks, first-aid kit.\n"
                                         "Adaptations: bigger gates for beginners, smaller for advanced (STEP).")

    # --- media ---------------------------------------------------------------------------
    def make_demo_video(self):
        ffmpeg = shutil.which(settings.FFMPEG_BINARY)
        if not ffmpeg:
            self.stdout.write("ffmpeg not found: video lessons will use text alternatives only.")
            return None
        out = Path(settings.BASE_DIR) / "media" / "_seed" / "demo-lesson.mp4"
        if out.exists():
            return out
        out.parent.mkdir(parents=True, exist_ok=True)
        cmd = [ffmpeg, "-y", "-f", "lavfi", "-i", "color=c=0x0B3D2E:s=1280x720:d=20:r=25",
               "-f", "lavfi", "-i", "sine=frequency=220:duration=20",
               "-vf", "drawbox=x=0:y=0:w=427:h=720:color=0x008751:t=fill,drawbox=x=853:y=0:w=427:h=720:color=0x008751:t=fill,"
                      "drawbox=x='540+80*sin(2*PI*t/5)':y=300:w=200:h=120:color=0xF2C230:t=fill",
               "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "veryfast", "-c:a", "aac", "-shortest", str(out)]
        try:
            subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=120)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            self.stdout.write(f"Could not generate demo video ({exc}); continuing without video.")
            return None
        return out

    def transcode(self):
        from apps.catalog.tasks import transcode_lesson

        pending = list(Lesson.objects.filter(media_status="processing").values_list("pk", flat=True))
        if not pending:
            return
        # Every demo lesson uses the same clip: transcode once, then copy the renditions.
        first = pending[0]
        transcode_lesson(first)
        src = Lesson.objects.get(pk=first)
        media = Path(settings.MEDIA_ROOT)
        if src.media_status == "ready":
            for pk in pending[1:]:
                shutil.copytree(media / "hls" / f"lesson-{first}", media / "hls" / f"lesson-{pk}", dirs_exist_ok=True)
                for folder, ext in (("audio", "m4a"), ("posters", "jpg")):
                    shutil.copyfile(media / "lessons" / folder / f"lesson-{first}.{ext}", media / "lessons" / folder / f"lesson-{pk}.{ext}")
                Lesson.objects.filter(pk=pk).update(
                    hls_playlist=f"hls/lesson-{pk}/master.m3u8", audio=f"lessons/audio/lesson-{pk}.m4a",
                    poster=f"lessons/posters/lesson-{pk}.jpg", media_status="ready")
        if pending:
            ready = Lesson.objects.filter(pk__in=pending, media_status="ready").count()
            self.stdout.write(f"Transcoded {ready}/{len(pending)} video lessons to HLS + audio-only.")
