"""Demo data for Phases 2-4. Called from seed_demo after the core data exists."""
import csv
import io
import random
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.utils import timezone
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

from apps.accounts.models import User
from apps.analytics.models import ScheduledReport
from apps.assessments.models import Choice, Exam, Question
from apps.careers.models import Challenge, Experience
from apps.catalog.models import Course, CourseTranslation, Lesson, LessonTemplate, Module, Profession, Sport, Track
from apps.community.models import Discussion, Group, GroupMember, MentorProfile, Opportunity, Reply
from apps.credentials.models import CPDActivity, CredentialType, ExternalQualification, Programme
from apps.institutions.models import Institution, Membership
from apps.labs.models import Scenario
from apps.learning.models import Cohort, Enrolment
from apps.library.models import Collection, Resource
from apps.live.models import LiveSession, OfficeHourSlot, Registration
from apps.practicals.models import PracticalTask, Submission
from apps.research.models import Dataset, OutcomeSurvey, Project, Publication
from apps.workforce.models import WorkforceProfile

NEW_STAFF = [
    ("safeguarding@sportiq.test", "Ifeoma", "Chukwu", ["safeguarding_officer"]),
    ("research@sportiq.test", "Prof. Yemi", "Adeleke", ["research_officer"]),
    ("moderator@sportiq.test", "Sadiq", "Umar", ["community_moderator"]),
    ("librarian@sportiq.test", "Joy", "Okon", ["librarian"]),
    ("workforce@sportiq.test", "Bashir", "Aliyu", ["workforce_officer"]),
    ("expert@sportiq.test", "Dr Kemi", "Olowu", ["external_reviewer"]),
]


def _pdf(title, paragraphs):
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title=title)
    ss = getSampleStyleSheet()
    story = [Paragraph(title, ss["Title"]), Paragraph("National Institute for Sports · SportIQ teaching resource (demo)", ss["Italic"]), Spacer(1, 12)]
    for p in paragraphs:
        story += [Paragraph(p, ss["Normal"]), Spacer(1, 8)]
    doc.build(story)
    return ContentFile(buf.getvalue())


def seed_phase2(cmd, password):
    if Programme.objects.exists():
        cmd.stdout.write("Phase 2-4 data already seeded; skipping.")
        return
    random.seed(7)
    now = timezone.now()
    users = {}
    for email, first, last, roles in NEW_STAFF:
        u, _ = User.objects.get_or_create(email=email, defaults={"first_name": first, "last_name": last, "email_verified": True,
                                                                 "staff_roles": roles, "is_staff": True, "state": "Lagos"})
        u.set_password(password)
        u.save()
        users[email] = u
    instructor = User.objects.get(email="instructor@sportiq.test")
    creator = User.objects.get(email="creator@sportiq.test")
    learner = User.objects.get(email="learner@sportiq.test")
    learners = list(User.objects.filter(staff_roles=[], email__endswith="@example.ng"))
    coach = Profession.objects.get(name="Coach")
    football = Sport.objects.get(name="Football")
    l1 = Course.objects.get(code="NIS-COA-101")
    saf = Course.objects.get(code="NIS-SAF-101")
    adp = Course.objects.get(code="NIS-ADP-101")
    event = Course.objects.get(code="NIS-BUS-210")

    # Credential types: renewal CPD requirements
    CredentialType.objects.filter(code__in=["safeguarding", "anti-doping"]).update(cpd_points_for_renewal=4)
    CredentialType.objects.filter(code="coaching-l1").update(cpd_points_for_renewal=12)

    # --- Practical tasks + programme ------------------------------------------------------------
    rubric = [{"title": "Clear, measurable session objective", "max": 5}, {"title": "Safe warm-up and risk assessment", "max": 5},
              {"title": "Progressive practices (STEP adaptations)", "max": 5}, {"title": "Questioning and feedback plan", "max": 5}]
    plan_task = PracticalTask.objects.create(course=l1, title="Design a 60-minute session plan", kind="session_plan", rubric=rubric, pass_mark=60,
                                             instructions="Using the NIS session plan template, plan a 60-minute session for 12-14-year-olds in your sport. "
                                                          "Include objective, timings, practices, safety checks and STEP adaptations.")
    deliver_task = PracticalTask.objects.create(course=l1, title="Deliver a coached session (observed)", kind="workplace", requires_supervisor=True,
                                                accepts_video=True, pass_mark=60, rubric=[{"title": "Organisation and safety", "max": 5},
                                                                                          {"title": "Communication and demonstration", "max": 5},
                                                                                          {"title": "Feedback and questioning", "max": 5}],
                                                instructions="Deliver your planned session to a real group while a qualified coach (Level 2 or above) observes. "
                                                             "Upload a short video clip or link, and name the supervising coach who will confirm it.")
    budget_task = PracticalTask.objects.create(course=event, title="Event budget and risk plan", kind="budget", pass_mark=60,
                                               rubric=[{"title": "Complete, realistic budget lines", "max": 10}, {"title": "Risk and safety plan", "max": 10}],
                                               instructions="Prepare a budget and risk plan for a one-day U-17 athletics meet for 300 athletes.")
    module = l1.modules.order_by("order").last()
    Lesson.objects.create(module=module, title="Practical: session plan", kind="practical", practical_task=plan_task, order=0,
                          body="Submit your session plan for assessment. An instructor will mark it against the rubric.")
    prog = Programme.objects.create(title="NIS Coaching Certificate, Level 1", slug="nis-coaching-certificate-level-1",
                                    summary="The entry-level NIS coaching qualification: safeguarding, clean sport, coaching foundations and an observed coaching session.",
                                    description="Awarded automatically when all required courses are complete and an observed session has been confirmed by a qualified supervisor. Valid for 3 years; renew with 12 CPD points.",
                                    credential_type=CredentialType.objects.get(code="coaching-l1"))
    prog.courses.set([saf, adp, l1])
    prog.practical_tasks.set([deliver_task])
    # Submissions
    for u in learners[:4]:
        Submission.objects.create(task=plan_task, user=u, text="Objective: improve passing accuracy.\nWarm-up 10 min: rondo.\nSkill 20 min: gates.\nGame 20 min: 5v5.\nCool-down 10 min: reflection.\nSafety: surface checked, water, first aid kit.",
                                  supervisor_name="", status="submitted")
    s = Submission.objects.create(task=deliver_task, user=learner, video_url="https://example.org/coaching-clip",
                                  text="Delivered to Surulere U-13s on Saturday.", supervisor_name="Coach Bayo Ogundipe",
                                  supervisor_email="instructor@sportiq.test", supervisor_role="NIS Level 2 coach", status="passed",
                                  score_percent=80, assessed_by=instructor, assessed_at=now, feedback="Well organised, clear demonstrations.")
    for u in learners[4:6]:
        Submission.objects.create(task=budget_task, user=u, text="Venue N400,000; medical N250,000; officials N300,000; contingency N150,000.")

    # Pre-test + practice questions (Safeguarding)
    bank = saf.question_banks.first()
    pre = Exam.objects.create(course=saf, bank=bank, title="Safeguarding: what do you already know?", is_pretest=True, is_published=True,
                              question_count=5, pass_mark=0, attempts_allowed=1, time_limit_minutes=10, auto_release=True,
                              instructions="Ungraded baseline: helps us measure what you learn.")
    for text, opts, exp in [("Who should you tell first about a safeguarding concern at your club?", ["* The designated safeguarding officer", "The child's friends", "Nobody"], "Report to the designated officer."),
                            ("Is it acceptable to message a 12-year-old player privately late at night?", ["Yes, if it's about training", "* No, keep communication transparent and include parents"], "Transparency protects everyone."),
                            ("What does STEP stand for in inclusive coaching?", ["* Space, Task, Equipment, People", "Speed, Time, Energy, Power"], "Space, Task, Equipment, People.")]:
        q = Question.objects.create(bank=bank, kind="mcq", text=text, explanation=exp, is_practice=True, topic="Practice")
        for i, o in enumerate(opts):
            Choice.objects.create(question=q, text=o.lstrip("* "), is_correct=o.startswith("*"), order=i)
    for u in learners[:25]:
        from apps.assessments.models import Attempt

        if Enrolment.objects.filter(user=u, course=saf, status="completed").exists():
            Attempt.objects.create(exam=pre, user=u, number=1, deadline=now, status="released", percent=random.choice([40, 50, 55, 60, 45]),
                                   passed=False, max_score=5, score=2, started_at=now - timedelta(days=60))

    # --- Live academy ---------------------------------------------------------------------------
    LiveSession.objects.create(title="Safeguarding Q&A with the NIS safeguarding lead", kind="webinar", host=instructor, course=saf, is_public=True,
                               starts_at=now + timedelta(days=3, hours=2), duration_minutes=60, cpd_points=1, record=True,
                               description="Bring your questions about safe practice, transport, social media and reporting.")
    live_now = LiveSession.objects.create(title="Coaching Foundations: live tutorial", kind="class", host=instructor, course=l1,
                                          starts_at=now - timedelta(minutes=5), duration_minutes=60, cpd_points=1,
                                          description="Session planning clinic: share your plan and get feedback.")
    past = LiveSession.objects.create(title="Masterclass: periodisation for youth athletes", kind="masterclass", host=instructor, is_public=True,
                                      guest_speaker="Dr Kemi Olowu (sports scientist)", starts_at=now - timedelta(days=12), duration_minutes=75,
                                      record=True, recording_url="https://example.org/recordings/periodisation", status="done",
                                      recording_available_until=(now + timedelta(days=180)).date())
    inperson = LiveSession.objects.create(title="Practical day: observed coaching sessions", kind="in_person", host=instructor, course=l1,
                                          location="National Stadium, Surulere, Lagos (Pitch 2)", starts_at=now + timedelta(days=10), duration_minutes=240,
                                          capacity=30, cpd_points=4, description="Bring your session plan. Observed assessments for the Level 1 qualification.")
    inperson.partner_institutions.add(Institution.objects.get(name__startswith="Lagos State"))
    for u in [learner] + learners[:8]:
        Registration.objects.get_or_create(session=live_now, user=u)
        Registration.objects.get_or_create(session=inperson, user=u)
    for u in learners[:12]:
        Registration.objects.create(session=past, user=u, attended=True, joined_at=past.starts_at)
    for d in range(1, 6):
        OfficeHourSlot.objects.create(host=instructor, course=l1, starts_at=(now + timedelta(days=d)).replace(hour=16, minute=0, second=0, microsecond=0))

    # --- Library --------------------------------------------------------------------------------
    track = {t.name.split(" ")[0]: t for t in Track.objects.all()}
    docs = [
        ("NIS Coaching Manual, Level 1 (extract)", "manual", "NIS Coaching Department", "Principles of athlete-centred coaching, session planning and safe practice for new coaches.", "coaching, session planning, youth", "Coaching", "learners"),
        ("Laws of the Game: referee quick reference", "rules", "NIS Officiating Unit", "A concise guide to positioning, signals and the key law changes for the current season.", "refereeing, laws, officiating", "Officiating", "public"),
        ("Safeguarding Policy for Sport (draft)", "policy", "National Institute for Sports", "Minimum safeguarding standards for clubs, academies and federations, including the four Rs and reporting routes.", "safeguarding, policy, child protection", "Integrity,", "public"),
        ("Training load and injury risk in adolescent footballers", "research", "A. Bello; T. Eze", "A teaching summary of evidence on acute:chronic workload ratios and injury risk in youth football.", "training load, ACWR, injury", "Sports", "learners"),
        ("Case study: organising the 2024 schools athletics championship", "case", "NIS Events Unit", "Budgeting, volunteers, medical cover and lessons learned from a state schools championship.", "event management, case study", "Sports", "learners"),
        ("Governance code for national sports federations (draft)", "legal", "NIS Governance Desk", "Draft standards for board composition, conflicts of interest and financial reporting.", "governance, federations", "Sports", "restricted"),
        ("History of Nigerian sport: 1960–1996", "history", "NIS Archives", "Key milestones in Nigerian sport from independence to Atlanta 1996.", "history, Nigeria", "Grassroots,", "public"),
    ]
    for title, kind, authors, abstract, tags, tkey, access in docs:
        r = Resource(title=title, kind=kind, authors=authors, abstract=abstract, tags=tags, access_level=access,
                     track=track.get(tkey.rstrip(",")), published_on=(now - timedelta(days=random.randint(30, 900))).date(),
                     owner="National Institute for Sports", editor=users["librarian@sportiq.test"], review_date=(now + timedelta(days=365)).date(),
                     cover_color=random.choice(["#0B3D2E", "#006B40", "#1F5F45", "#2C6E49"]))
        r.file.save(f"{r.title[:40]}.pdf".replace(" ", "-"), _pdf(title, [abstract, "This document is part of the SportIQ demo library and illustrates how NIS resources are organised, versioned and cited."]), save=False)
        r.save()
    Resource.objects.create(title="WADA anti-doping learning platform (ADEL)", kind="link", external_url="https://adel.wada-ama.org/",
                            abstract="Authorised external resource: WADA's official anti-doping education courses.", access_level="public", tags="anti-doping, WADA",
                            publisher="World Anti-Doping Agency", owner="WADA", published_on=now.date())
    rl = Collection.objects.create(user=instructor, name="Coaching Level 1 reading list", is_reading_list=True, course=l1)
    rl.resources.set(Resource.objects.filter(kind__in=["manual", "research"]))

    # --- Labs ------------------------------------------------------------------------------------
    Scenario.objects.create(title="Penalty-area incident: foul or fair challenge?", kind="refereeing", engine="branching", sport=football,
                            summary="Make the call on three match incidents and see the rule-based explanation.",
                            intro="You are refereeing an U-17 league match. Make each decision as you would on the pitch.",
                            data={"start": "a", "nodes": {
                                "a": {"text": "**Minute 23.** An attacker goes down in the box after contact on the heel from a defender who played the ball first, then caught the attacker's heel.",
                                      "options": [{"text": "Penalty kick", "score": 10, "next": "b", "feedback": "Correct: playing the ball first doesn't excuse a careless challenge that then trips the opponent."},
                                                  {"text": "Play on: he played the ball", "score": 2, "next": "b", "feedback": "Contact that trips an opponent after the ball is played can still be careless; this is a foul."},
                                                  {"text": "Yellow card for simulation", "score": 0, "next": "b", "feedback": "There was clear contact, so this isn't simulation."}]},
                                "b": {"text": "**Minute 51.** Players surround you after a free kick decision. The captain is calm, two others are shouting.",
                                      "options": [{"text": "Speak to the captain, use calm body language, caution persistent dissent", "score": 10, "next": "c", "feedback": "Good match control: work through the captain, stay calm and act on dissent."},
                                                  {"text": "Shout back to show authority", "score": 1, "next": "c", "feedback": "Raising your voice escalates confrontation."},
                                                  {"text": "Ignore them and restart quickly", "score": 5, "next": "c", "feedback": "Restarting can help, but dissent shouldn't go unaddressed."}]},
                                "c": {"text": "**Minute 88.** A defender handles the ball on the goal line, denying an obvious goal.",
                                      "options": [{"text": "Penalty and red card (denying an obvious goal-scoring opportunity by handball)", "score": 10, "next": None, "feedback": "Correct: deliberate handball denying a goal is a sending-off offence."},
                                                  {"text": "Penalty and yellow card", "score": 4, "next": None, "feedback": "A deliberate handball denying a goal requires a red card."}]}}})
    Scenario.objects.create(title="Your U-13 team is losing 3-0 at half-time", kind="coaching", engine="branching",
                            summary="Handle a tough match situation: team talk, substitutions and player welfare.",
                            data={"start": "a", "nodes": {
                                "a": {"text": "Half-time. The players look deflated. One parent is shouting at the referee from the sideline.",
                                      "options": [{"text": "Calmly ask the parent to stop, then give the team two simple focus points", "score": 10, "next": "b", "feedback": "You protect the environment and keep messages simple for young players."},
                                                  {"text": "Tell the team they were terrible and need to try harder", "score": 1, "next": "b", "feedback": "Criticism without guidance lowers confidence; give specific, positive instructions."},
                                                  {"text": "Ignore the parent; focus only on tactics", "score": 4, "next": "b", "feedback": "The sideline behaviour affects players and officials. Address it calmly."}]},
                                "b": {"text": "A player who has been on the bench all game asks to play.",
                                      "options": [{"text": "Give them meaningful minutes in the second half", "score": 10, "next": None, "feedback": "Equal playing time matters at this age; development first."},
                                                  {"text": "Keep the strongest players on to save face", "score": 2, "next": None, "feedback": "Winning at U-13 matters less than every child playing and developing."}]}}})
    Scenario.objects.create(title="Concussion on the touchline", kind="medicine", engine="branching", requires_qualified=True,
                            summary="Case study for registered medical staff: suspected concussion in a 16-year-old.",
                            data={"start": "a", "nodes": {"a": {"text": "A 16-year-old player is dazed after a head clash and asks to continue.",
                                                                  "options": [{"text": "Remove from play; follow recognise-and-remove protocol; no return the same day", "score": 10, "next": None, "feedback": "If in doubt, sit them out."},
                                                                              {"text": "Allow return if they feel fine after 5 minutes", "score": 0, "next": None, "feedback": "Never return a suspected concussion to play on the same day."}]}}})
    demo_video = Path(settings.MEDIA_ROOT) / "_seed" / "demo-lesson.mp4"
    ma = Scenario(title="Match analysis: pressing triggers", kind="match_analysis", engine="annotate", sport=football,
                  summary="Tag the key moments in the clip and write a short tactical report.",
                  intro="Watch the 20-second clip. Tag each moment when you see it, then summarise what you observed.",
                  data={"tags": ["Pressing trigger", "Turnover", "Counter-attack", "Defensive shape"],
                        "key_moments": [{"t": 4, "tag": "Pressing trigger", "tolerance": 3, "explain": "Back pass to the centre-back triggers the press."},
                                        {"t": 10, "tag": "Turnover", "tolerance": 3, "explain": "Ball won high up the pitch."},
                                        {"t": 15, "tag": "Counter-attack", "tolerance": 3, "explain": "Quick forward pass into space."}]})
    if demo_video.exists():
        ma.video.save("match-analysis.mp4", ContentFile(demo_video.read_bytes()), save=False)
    ma.save()
    Scenario.objects.create(title="Training load: who is at risk this week?", kind="performance", engine="load",
                            summary="Use the acute:chronic workload ratio to flag athletes at higher injury risk.",
                            data={"threshold": 1.5, "athletes": [
                                {"name": "Athlete A", "position": "Sprinter", "weeks": [900, 950, 920, 980, 1500]},
                                {"name": "Athlete B", "position": "Middle distance", "weeks": [1200, 1250, 1180, 1300, 1260]},
                                {"name": "Athlete C", "position": "Jumper", "weeks": [700, 720, 690, 710, 1150]},
                                {"name": "Athlete D", "position": "Thrower", "weeks": [800, 820, 780, 810, 860]}]})
    Scenario.objects.create(title="Design a 60-minute U-14 session", kind="session_designer", engine="designer",
                            summary="Choose and order drills to build a safe, progressive session.",
                            data={"target_minutes": 60, "drills": [
                                {"id": "w1", "name": "Dynamic warm-up and rondo", "phase": "warmup", "minutes": 10, "intensity": "low"},
                                {"id": "s1", "name": "Passing through gates", "phase": "skill", "minutes": 15, "intensity": "medium"},
                                {"id": "s2", "name": "Receiving on the half-turn", "phase": "skill", "minutes": 10, "intensity": "medium"},
                                {"id": "g1", "name": "5v5 two-touch game", "phase": "game", "minutes": 20, "intensity": "high"},
                                {"id": "g2", "name": "Shooting competition", "phase": "game", "minutes": 15, "intensity": "high"},
                                {"id": "g3", "name": "Sprint relays", "phase": "game", "minutes": 10, "intensity": "high"},
                                {"id": "c1", "name": "Cool-down and questions", "phase": "cooldown", "minutes": 5, "intensity": "low"}]})
    Scenario.objects.create(title="Budget a state schools athletics meet", kind="budget", engine="budget",
                            summary="Allocate N5,000,000 across budget lines for a one-day meet for 300 athletes.",
                            data={"total": 5000000, "lines": [
                                {"key": "venue", "label": "Venue & equipment", "min": 800000, "ideal": 1200000, "hint": "Track hire, hurdles, timing"},
                                {"key": "medical", "label": "Medical cover", "min": 400000, "ideal": 600000, "hint": "Ambulance, first aiders", "why": "Medical cover is a safety requirement."},
                                {"key": "officials", "label": "Technical officials", "min": 500000, "ideal": 800000, "hint": "Judges, starters, allowances"},
                                {"key": "transport", "label": "Athlete transport & meals", "min": 900000, "ideal": 1400000, "hint": "Buses, water, lunch"},
                                {"key": "medals", "label": "Medals & certificates", "min": 100000, "ideal": 300000, "hint": ""},
                                {"key": "contingency", "label": "Contingency", "min": 250000, "ideal": 400000, "hint": "5-10% recommended"}]})

    # --- Community, mentors, opportunities -----------------------------------------------------------
    groups = [Group.objects.create(name="Grassroots football coaches", kind="sport", sport=football, profession=coach,
                                   description="Share session ideas and challenges from community and school football."),
              Group.objects.create(name="Referees & technical officials network", kind="discipline", profession=Profession.objects.get(name__startswith="Referee"),
                                   description="Law changes, match control and fitness for officials."),
              Group.objects.create(name="Safeguarding Essentials alumni", kind="alumni", course=saf, description="For coaches who completed Safeguarding Essentials."),
              Group.objects.create(name="Sports science roundtable", kind="roundtable", verified_only=True, profession=Profession.objects.get(name="Sports scientist"),
                                   description="Expert discussion: only verified professionals post.")]
    GroupMember.objects.create(group=groups[0], user=learner)
    GroupMember.objects.create(group=groups[0], user=instructor, role="moderator")
    for u in learners[:20]:
        GroupMember.objects.get_or_create(group=random.choice(groups[:2]), user=u)
    d = Discussion.objects.create(group=groups[0], author=learners[0], title="Best small-sided games for 40 kids and 10 balls?",
                                  body="Our school team has 40 players and only 10 balls. What games keep everyone moving?")
    Reply.objects.create(discussion=d, author=instructor, body="Use 4 grids with 4v4+2 floaters; rotate every 6 minutes. Everyone gets touches.")
    Reply.objects.create(discussion=d, author=learner, body="We do relay dribbling races too. The kids love them.")
    MentorProfile.objects.create(user=instructor, headline="NIS Level 3 coach educator, 15 years in youth football", areas="session planning, coach education, talent ID",
                                 capacity=4, approved=True).sports.add(football)
    mp = MentorProfile.objects.create(user=users["expert@sportiq.test"], headline="Sports scientist, strength & conditioning",
                                      areas="load monitoring, S&C for young athletes", capacity=3, approved=True)
    mp.professions.add(Profession.objects.get(name="Sports scientist"))
    fed = Institution.objects.get(name__startswith="National Football")
    for kind, title, org, state, paid, cred in [("job", "Assistant coach, U-15 academy", "Surulere Youth Football Academy (demo)", "Lagos", True, "safeguarding"),
                                                ("volunteer", "Volunteer officials: state schools athletics", "Lagos State Sports Council (demo)", "Lagos", False, None),
                                                ("internship", "Sports science intern (6 months)", "Ibadan University Sports Science (demo)", "Oyo", True, None),
                                                ("apprenticeship", "Grassroots coach apprenticeship", "National Football Association (demo)", "Kano", True, "coaching-l1"),
                                                ("event", "Coach educators' conference", "NIS Coaching Department", "FCT", False, None)]:
        Opportunity.objects.create(kind=kind, title=title, organisation=org, state=state, paid=paid, status="open", posted_by=users["moderator@sportiq.test"],
                                   description=f"{title} with {org}. Apply through SportIQ with your verified credentials.",
                                   required_credential=CredentialType.objects.filter(code=cred).first(), closes_on=(now + timedelta(days=30)).date(),
                                   institution=fed if "Football" in org else None)
    Opportunity.objects.create(kind="job", title="Fitness coach (unverified posting)", organisation="Unknown club", description="Needs approval.",
                               status="pending", posted_by=learners[1])

    # --- Workforce & experience ------------------------------------------------------------------------
    levels = ["grassroots", "school", "club", "elite", "disability"]
    for u in [learner] + learners[:45]:
        WorkforceProfile.objects.update_or_create(user=u, defaults={"listed": True, "availability": random.choice(["open", "employed_open", "volunteer", "open"]),
                                                                    "years_experience": random.randint(1, 15), "experience_levels": random.sample(levels, 2),
                                                                    "preferred_states": [u.state] if u.state else []})
        Experience.objects.create(user=u, role=random.choice(["Assistant coach", "Head coach", "Referee", "Team manager", "PE teacher"]),
                                  organisation=random.choice(["Community FC", "Government Secondary School", "State athletics team", "University sports council"]),
                                  level=random.choice(levels), sport=random.choice(list(Sport.objects.all())), state=u.state,
                                  start_date=(now - timedelta(days=random.randint(400, 3000))).date())
    for u in learners[:15]:
        u.is_verified_professional = True
        u.save(update_fields=["is_verified_professional"])
    learner.profile_public = True
    learner.is_verified_professional = True
    learner.save(update_fields=["profile_public", "is_verified_professional"])

    # --- CPD, external qualifications, claims (registrar queues) -----------------------------------------
    CPDActivity.objects.create(user=learner, title="CAF grassroots coaching workshop", kind="external", provider="CAF", hours=6,
                               reflection="Learned new small-sided games for large groups.", date=(now - timedelta(days=20)).date())
    for u in learners[:5]:
        CPDActivity.objects.create(user=u, title="First aid in sport refresher", kind="event", provider="Red Cross Nigeria", hours=4,
                                   date=(now - timedelta(days=random.randint(5, 60))).date())
    ExternalQualification.objects.create(user=learner, title="CAF D Licence", awarding_body="Confederation of African Football", reference="CAF-D-2023-1187",
                                         awarded_on=(now - timedelta(days=500)).date(), evidence=ContentFile(b"demo evidence", name="caf-d.txt"))

    # --- Research ---------------------------------------------------------------------------------------
    rp = Project.objects.create(title="Training load and injury in Nigerian youth football academies", lead=users["research@sportiq.test"],
                                summary="A 12-month cohort study of training load and injuries in 6 academies.", research_question="Is a high acute:chronic workload ratio associated with injury risk in Nigerian U-17 players?",
                                methods="Prospective cohort; session-RPE load; injury surveillance.", status="active", ethics_reference="NIS-REC-2026-014",
                                involves_children=True, uses_athlete_data=True, recruiting=True, ethics_checklist={k: True for k in ["consent", "minimise", "anonymise", "storage", "medical", "withdraw", "ndpa"]})
    rp.members.add(users["research@sportiq.test"], users["expert@sportiq.test"])
    Project.objects.create(title="Barriers to girls' participation in school sport", lead=learners[2], summary="Survey of PE teachers in 4 states.",
                           research_question="What prevents girls from continuing school sport after age 13?", status="ethics")
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["athlete_id", "week", "session_rpe_load", "injured"])
    for a in range(1, 31):
        for wk in range(1, 9):
            w.writerow([f"A{a:03d}", wk, random.randint(600, 1600), int(random.random() < 0.06)])
    Dataset.objects.create(title="Teaching dataset: youth training load (synthetic)", description="Synthetic, anonymised weekly load and injury data for 30 athletes over 8 weeks. For teaching data literacy.",
                           access="open", is_anonymised=True, file=ContentFile(buf.getvalue().encode(), name="youth-training-load.csv"),
                           variables="athlete_id (pseudonym), week (1-8), session_rpe_load (AU), injured (0/1)")
    Dataset.objects.create(title="Academy injury surveillance 2026 (restricted)", description="Pseudonymised injury records from participating academies.",
                           access="approval", contains_personal_data=True, is_anonymised=False, project=rp,
                           file=ContentFile(b"athlete_id,injury_date,type\n", name="academy-injuries.csv"))
    Publication.objects.create(title="Evidence summary: preventing heat illness at school sports days", kind="brief", authors="NIS Research Office",
                               abstract="Five practical steps for schools: schedule, shade, water, acclimatisation and recognising heat illness.",
                               submitted_by=users["research@sportiq.test"], status="published", published_on=(now - timedelta(days=40)).date())
    Publication.objects.create(title="Coach education uptake after mandatory safeguarding training", kind="paper", authors="Adeleke Y., Olowu K.",
                               abstract="Early evaluation of SportIQ completion data.", submitted_by=users["expert@sportiq.test"], status="review", project=rp)

    # --- Longitudinal outcomes ----------------------------------------------------------------------------
    done = list(Enrolment.objects.filter(status="completed").select_related("user")[:40])
    for i, e in enumerate(done):
        s = OutcomeSurvey.objects.create(enrolment=e, wave=6)
        if i % 3 != 0:
            s.responded_at = now - timedelta(days=random.randint(1, 30))
            s.applied_learning = random.choice([3, 4, 4, 5, 5])
            s.role_change = random.choice(["none", "none", "new_role", "promotion", "new_qualification"])
            s.employed_in_sport = random.random() < 0.8
            s.consent_research = True
            s.save()
    OutcomeSurvey.objects.get_or_create(enrolment=Enrolment.objects.get(user=learner, course=adp), wave=6)

    # --- Engagement, translations, misc ----------------------------------------------------------------
    Challenge.objects.create(title="October learning sprint", description="Complete 10 lessons this month.", metric="lessons", target=10,
                             starts_on=now.date().replace(day=1), ends_on=(now + timedelta(days=20)).date(), show_leaderboard=True, team_mode=True)
    Challenge.objects.create(title="Five-day streak", description="Learn on five different days.", metric="days", target=5,
                             starts_on=now.date() - timedelta(days=3), ends_on=(now + timedelta(days=25)).date())
    CourseTranslation.objects.create(course=adp, language="pcm", title="Anti-Doping Essentials: Clean Sport (Pidgin)",
                                     summary="Learn the anti-doping rules, your rights, and how you fit protect yourself from mistake doping.",
                                     description="Clean sport dey protect athlete health and fair play. Always check the **current** Prohibited List before you take any medicine.",
                                     status="approved", reviewer=users["expert@sportiq.test"])
    CourseTranslation.objects.create(course=saf, language="yo", title="Ìpìlẹ̀ Ààbò fún Àwọn Olùkọ́ni", summary="Àkọsílẹ̀ àkọ́kọ́, tí ń dúró de àyẹ̀wò amòye.", status="draft")
    LessonTemplate.objects.create(name="Video lesson with text alternative", kind="video", body="## Key points\n\n- Point 1\n- Point 2\n\n## Try this\n\nOne practical task.")
    LessonTemplate.objects.create(name="Case study", kind="reading", body="## Case study\n\n**Situation.**\n\n**Reflect.**\n\n**Guidance.**")
    Course.objects.filter(status=Course.IN_REVIEW).first().external_reviewers.add(users["expert@sportiq.test"])
    ScheduledReport.objects.create(name="Monthly leadership summary", recipients="leadership@nis.example\nanalyst@sportiq.test", frequency="monthly")
    Cohort.objects.filter(course=l1).update(leaderboard_enabled=True)

    from apps.ai.services import rebuild_index, scan_risks

    cmd.stdout.write(f"Phase 2-4 demo data ready. AI index: {rebuild_index()} passages; {scan_risks()} learning-risk alerts.")
