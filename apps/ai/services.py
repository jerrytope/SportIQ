"""AI study assistant (blueprint Module 4).

Retrieval-grounded: answers come only from APPROVED NIS content (published lessons, transcripts, library resources
flagged as AI-indexable, help articles). With an AI provider configured (OpenAI by default, or Anthropic), the model
writes the answer from the retrieved passages and cites them; otherwise the assistant returns the most relevant
passages verbatim with citations.

Guardrails: never during an open exam attempt; never answers questions that match live exam items; cites sources;
says when the approved material doesn't cover the question. Learner data is not sent for model training.
"""
import logging
import math
import re
from collections import Counter
from functools import lru_cache

from django.conf import settings
from django.db.models import Q
from django.utils import timezone

from .models import Chunk

log = logging.getLogger("apps.ai")

STOP = set("""a an and are as at be but by can do does for from has have how i if in into is it its me my of on or our
should so than that the their them then there these they this to was we what when where which who why will with would
you your about also any been being more most not only other some such very just like""".split())


def terms(text):
    return [w for w in re.findall(r"[a-z0-9]+", (text or "").lower()) if len(w) > 2 and w not in STOP]


# --- Index --------------------------------------------------------------------------------------

def _split(text, size=110):
    words = text.split()
    for i in range(0, len(words), size - 20):
        piece = " ".join(words[i:i + size])
        if len(piece) > 60:
            yield piece


def rebuild_index():
    """Index approved content. Run after publishing (and nightly)."""
    from apps.catalog.models import Course, Lesson
    from apps.library.models import Resource
    from apps.support.models import HelpArticle

    Chunk.objects.all().delete()
    rows = []
    for lesson in Lesson.objects.filter(module__course__status=Course.PUBLISHED).select_related("module__course"):
        course = lesson.module.course
        title = f"{course.title} › {lesson.title}"
        url = lesson.get_absolute_url()
        for text in _split(re.sub(r"[#*>`_]", " ", lesson.body)):
            rows.append(Chunk(source_type="lesson", source_id=lesson.pk, title=title, url=url, text=text,
                              version=f"v{course.version}", tokens=terms(text + " " + title)))
        for text in _split(lesson.transcript):
            rows.append(Chunk(source_type="transcript", source_id=lesson.pk, title=title + " (transcript)", url=url,
                              text=text, version=f"v{course.version}", tokens=terms(text + " " + title)))
    for course in Course.objects.published():
        text = f"{course.summary} {course.description} Objectives: {course.objectives} Assessment: {course.assessment_criteria}"
        for piece in _split(re.sub(r"[#*>`_]", " ", text)):
            rows.append(Chunk(source_type="course", source_id=course.pk, title=course.title, url=course.get_absolute_url(),
                              text=piece, version=f"v{course.version}", tokens=terms(piece + " " + course.title)))
    for r in Resource.objects.filter(is_published=True, ai_indexable=True).exclude(access_level="restricted"):
        for piece in _split(f"{r.title}. {r.abstract}"):
            rows.append(Chunk(source_type="library", source_id=r.pk, title=r.title, url=r.get_absolute_url(), text=piece,
                              version=r.version, tokens=terms(piece + " " + r.title + " " + r.tags)))
    for a in HelpArticle.objects.filter(is_published=True):
        for piece in _split(re.sub(r"[#*>`_]", " ", a.body)):
            rows.append(Chunk(source_type="help", source_id=a.pk, title=a.title, url=f"/help/articles/{a.slug}/",
                              text=piece, tokens=terms(piece + " " + a.title)))
    Chunk.objects.bulk_create(rows, batch_size=500)
    _index.cache_clear()
    return len(rows)


@lru_cache(maxsize=1)
def _index():
    chunks = list(Chunk.objects.values("id", "source_type", "source_id", "title", "url", "text", "version", "tokens"))
    df = Counter()
    for c in chunks:
        df.update(set(c["tokens"]))
    avg = sum(len(c["tokens"]) for c in chunks) / len(chunks) if chunks else 1
    return chunks, df, avg


def search(query, k=5, source_types=None, course_id=None):
    """BM25 ranking over approved chunks."""
    chunks, df, avg = _index()
    if not chunks:
        rebuild_index()
        chunks, df, avg = _index()
    q = terms(query)
    if not q:
        return []
    n = len(chunks)
    scored = []
    for c in chunks:
        if source_types and c["source_type"] not in source_types:
            continue
        tf = Counter(c["tokens"])
        score = 0.0
        for t in q:
            if t in tf:
                idf = math.log(1 + (n - df[t] + 0.5) / (df[t] + 0.5))
                f = tf[t]
                score += idf * f * 2.2 / (f + 1.2 * (0.25 + 0.75 * len(c["tokens"]) / avg))
        if score > 0:
            weight = {"lesson": 1.0, "transcript": 0.9, "library": 0.9, "help": 0.9, "course": 0.5}.get(c["source_type"], 1.0)
            scored.append((score * weight, c))
    scored.sort(key=lambda x: -x[0])
    out, seen = [], set()
    for score, c in scored:
        key = (c["source_type"], c["source_id"], c["text"][:40])
        if key in seen:
            continue
        seen.add(key)
        out.append({**c, "score": round(score, 2)})
        if len(out) >= k:
            break
    return out


# --- Guardrails -----------------------------------------------------------------------------------

def open_attempt(user):
    from apps.assessments.models import Attempt

    return next((a for a in Attempt.objects.filter(user=user, status=Attempt.IN_PROGRESS).select_related("exam") if a.is_open), None)


def looks_like_exam_item(text):
    """True if the question closely matches a live graded exam question (protects assessment integrity)."""
    from apps.assessments.models import Question

    qt = set(terms(text))
    if len(qt) < 6:
        return False  # short concept questions ("what is strict liability?") are legitimate study questions
    for item in Question.objects.filter(is_active=True, is_practice=False, bank__exams__is_published=True).values_list("text", flat=True).distinct():
        it = set(terms(item))
        if len(it) >= 6 and len(qt & it) / len(qt | it) >= 0.8:  # near-verbatim copy of a live item
            return True
    return False


_ANSWER_WORDS = r"(?:answers?|solutions?|answer\s*key|marking\s*scheme|memo|correct\s+options?|cheat)"
_ASSESSMENT_WORDS = r"(?:exams?|examinations?|tests?|quiz(?:zes)?|assessments?|finals?)"
_ANSWER_REQUEST = re.compile(
    rf"\b{_ANSWER_WORDS}\b[^.?!]{{0,80}}\b{_ASSESSMENT_WORDS}\b|\b{_ASSESSMENT_WORDS}\b[^.?!]{{0,80}}\b{_ANSWER_WORDS}\b"
    rf"|\b(?:do|take|sit|pass|write)\s+(?:my|the)\s+{_ASSESSMENT_WORDS}\s+for\s+me\b",
    re.IGNORECASE,
)


def asks_for_assessment_answers(text):
    """True for requests to hand over assessment answers ("give me the answers to the final exam")."""
    if re.search(r"\bpractis?c?e\b", text or "", re.IGNORECASE):
        return False  # practice questions are fair game
    return bool(_ANSWER_REQUEST.search(text or ""))


def _stem(word):
    for suffix in ("ing", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def relevant_hits(question, hits):
    """Keep passages that cover enough of the question's key terms, so off-topic questions get no answer."""
    q = {_stem(t) for t in terms(question)}
    if not q:
        return []
    need = 0.5 if len(q) <= 4 else 0.4
    keep = []
    for h in hits:
        have = {_stem(t) for t in h["tokens"]} | {_stem(t) for t in terms(h["title"])}
        if len(q & have) / len(q) >= need:
            keep.append(h)
    return keep


SYSTEM_PROMPT = """You are the SportIQ study assistant for the National Institute for Sports (Nigeria).
Answer ONLY from the numbered SOURCES provided. Cite sources inline like [1] or [2]. If the sources do not cover the
question, say so plainly and suggest which course or the help centre might help; do not fill gaps from general knowledge.
Help the learner understand: explain, give examples, check understanding. Never give answers to assessment or exam
questions; if asked, explain the concept instead and suggest revisiting the lesson. For medical, safeguarding or
anti-doping matters, remind the learner that course material does not replace qualified professionals or official
procedures. Be concise (under 220 words), warm and practical. Use British English."""


def ai_enabled():
    if settings.AI_PROVIDER == "openai":
        return bool(settings.OPENAI_API_KEY)
    if settings.AI_PROVIDER == "anthropic":
        return bool(settings.ANTHROPIC_API_KEY)
    return False


def ai_model():
    return settings.OPENAI_MODEL if settings.AI_PROVIDER == "openai" else settings.AI_MODEL


def _llm(system, messages, max_tokens=1200, effort="medium"):
    """Generate with the configured provider. Returns (text, model) or (None, reason)."""
    if settings.AI_PROVIDER == "openai":
        return _openai(system, messages, max_tokens)
    if settings.AI_PROVIDER == "anthropic":
        return _claude(system, messages, max_tokens, effort)
    return None, "disabled"


def _openai(system, messages, max_tokens=1200):
    import openai

    client = openai.OpenAI(api_key=settings.OPENAI_API_KEY)
    try:
        response = client.chat.completions.create(
            model=settings.OPENAI_MODEL, max_completion_tokens=max_tokens,
            messages=[{"role": "system", "content": system}] + messages,
        )
    except openai.RateLimitError:
        return None, "busy"
    except openai.APIStatusError as exc:
        log.warning("OpenAI API error %s: %s", exc.status_code, exc.message)
        return None, "error"
    except openai.APIConnectionError:
        return None, "offline"
    choice = response.choices[0]
    if getattr(choice.message, "refusal", None) or choice.finish_reason == "content_filter":
        return None, "refused"
    return (choice.message.content or "").strip() or None, response.model


def _claude(system, messages, max_tokens=1200, effort="medium"):
    """Call Claude with server-side refusal fallbacks. Returns (text, model) or (None, reason)."""
    import anthropic

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    try:
        response = client.beta.messages.create(
            model=settings.AI_MODEL, max_tokens=max_tokens, system=system, messages=messages,
            output_config={"effort": effort}, betas=["server-side-fallback-2026-07-01"], fallbacks="default",
        )
    except anthropic.RateLimitError:
        return None, "busy"
    except anthropic.APIStatusError as exc:
        log.warning("Claude API error %s: %s", exc.status_code, exc.message)
        return None, "error"
    except anthropic.APIConnectionError:
        return None, "offline"
    if response.stop_reason == "refusal":
        return None, "refused"
    text = "".join(b.text for b in response.content if b.type == "text").strip()
    return text, response.model


def answer(user, question, history=None, course=None, mode="tutor"):
    """Returns dict(content, citations, engine, refused)."""
    if mode == "tutor":
        att = open_attempt(user)
        if att:
            return {"content": f"The study assistant is switched off while your assessment “{att.exam.title}” is in "
                               "progress. Finish and submit it first. Good luck!", "citations": [], "engine": "guardrail", "refused": True}
        if looks_like_exam_item(question):
            return {"content": "That looks like an assessment question, so I can't give you the answer. I can explain the "
                               "underlying idea though. Tell me which part of the topic is unclear, or reopen the related lesson.",
                    "citations": [], "engine": "guardrail", "refused": True}
        if asks_for_assessment_answers(question):
            return {"content": "I can't give you answers to assessments or exams. That would undermine your qualification. "
                               "I can explain any topic the assessment covers, or you can try the practice questions under "
                               "Revise & practise.",
                    "citations": [], "engine": "guardrail", "refused": True}
    types = ["help"] if mode == "support" else None
    hits = relevant_hits(question, search(question, k=5, source_types=types))
    if course and mode == "tutor":
        boosted = [h for h in hits if h["source_type"] in ("lesson", "transcript", "course")]
        hits = boosted + [h for h in hits if h not in boosted]
    citations = [{"n": i + 1, "title": h["title"], "url": h["url"], "version": h["version"], "type": h["source_type"]}
                 for i, h in enumerate(hits)]
    if not hits:
        msg = ("I can only answer from approved SportIQ course and library material, and I couldn't find this there. "
               "Try rephrasing, browse the course catalogue, or ask your instructor in the course discussion.")
        if mode == "support":
            msg = "I couldn't find a help article for that. I can pass this to our support team. Use “Talk to a person”."
        return {"content": msg, "citations": [], "engine": "retrieval", "refused": False}
    if ai_enabled():
        sources = "\n\n".join(f"[{i + 1}] {h['title']} ({h['version'] or 'current'}):\n{h['text']}" for i, h in enumerate(hits))
        msgs = []
        for m in (history or [])[-6:]:
            msgs.append({"role": m["role"], "content": m["content"]})
        msgs.append({"role": "user", "content": f"SOURCES:\n{sources}\n\nQUESTION: {question}"})
        text, engine = _llm(SYSTEM_PROMPT, msgs)
        if text:
            return {"content": text, "citations": citations, "engine": engine, "refused": False}
    # Extractive fallback (no key, or the model was unavailable)
    lines = ["Here is what the approved SportIQ material says:"]
    for i, h in enumerate(hits[:3]):
        snippet = h["text"][:420].rsplit(" ", 1)[0]
        lines.append(f"\n**[{i + 1}] {h['title']}**: {snippet}…")
    lines.append("\nOpen the sources below to read more.")
    return {"content": "\n".join(lines), "citations": citations[:3], "engine": "retrieval", "refused": False}


# --- Study plans, revision, practice -----------------------------------------------------------------

def weak_topics(user, limit=5):
    """Topics where the learner lost marks in released attempts."""
    from apps.assessments.models import Response

    misses = Counter()
    for r in Response.objects.filter(attempt__user=user, attempt__status="released", score__isnull=False).select_related("question"):
        if r.score < r.question.points and r.question.topic:
            misses[(r.question.bank.course_id, r.question.topic)] += 1
    return misses.most_common(limit)


def revision_for(user):
    """Remedial lessons for weak topics, found by retrieval within the same course."""
    from apps.catalog.models import Course, Lesson

    out = []
    for (course_id, topic), n in weak_topics(user):
        course = Course.objects.filter(pk=course_id).first()
        if not course:
            continue
        hits = [h for h in search(f"{topic} {course.title}", k=6, source_types=["lesson", "transcript"])
                if Lesson.objects.filter(pk=h["source_id"], module__course=course).exists()][:2]
        out.append({"topic": topic, "course": course, "missed": n, "lessons": hits})
    return out


def build_study_plan(user, goal, hours_per_week):
    """Rule-based weekly plan from the learner's active courses, mandatory training and recommendations."""
    from apps.catalog.models import Course
    from apps.credentials.models import MandatoryRequirement

    queue = []
    done = set(user.enrolments.filter(status="completed").values_list("course_id", flat=True))
    for e in user.enrolments.filter(status="active").select_related("course"):
        progress = set(e.lesson_progress.filter(completed=True).values_list("lesson_id", flat=True))
        queue += [(e.course, l) for l in e.course.lessons() if l.pk not in progress]
    required = MandatoryRequirement.objects.filter(profession__in=user.professions.all()).exclude(course_id__in=done)
    enrolled = set(user.enrolments.values_list("course_id", flat=True))
    extra = [r.course for r in required if r.course_id not in enrolled]
    if not queue and not extra:
        goal_hits = search(goal, k=5, source_types=["course"])
        extra = [c for c in Course.objects.published().filter(pk__in=[h["source_id"] for h in goal_hits]) if c.pk not in enrolled][:2]
    for c in extra:
        queue += [(c, l) for l in c.lessons()]
    budget = max(30, hours_per_week * 60)
    weeks, current, used = [], [], 0
    for course, lesson in queue:
        mins = lesson.duration_minutes or 10
        if used + mins > budget and current:
            weeks.append(current)
            current, used = [], 0
        current.append({"course": course.title, "course_slug": course.slug, "lesson": lesson.title,
                        "lesson_id": lesson.pk, "minutes": mins, "enrolled": course.pk in enrolled})
        used += mins
        if len(weeks) >= 12:
            break
    if current and len(weeks) < 12:
        weeks.append(current)
    plan = [{"week": i + 1, "items": w, "minutes": sum(x["minutes"] for x in w)} for i, w in enumerate(weeks)]
    narrative = ""
    if ai_enabled() and plan:
        summary = "; ".join(f"week {p['week']}: " + ", ".join(sorted({x['course'] for x in p['items']})) for p in plan[:6])
        narrative, _ = _llm("You are a supportive study coach for Nigerian sports professionals. Write 3 short "
                               "encouraging sentences explaining how this plan serves their goal. No new facts.",
                               [{"role": "user", "content": f"Goal: {goal}. {hours_per_week} h/week. Plan: {summary}"}],
                               max_tokens=400, effort="low")
    if not narrative:
        narrative = (f"{len(plan)} week{'s' if len(plan) != 1 else ''} at about {hours_per_week} hours a week. "
                     "Mandatory training for your role comes first, then the courses you've started.")
    return plan, narrative or ""


def practice_questions(user, course, n=5):
    """Practice items from the course bank marked practice-only (never graded exam items)."""
    from apps.assessments.models import Question

    qs = list(Question.objects.filter(bank__course=course, is_practice=True, is_active=True).prefetch_related("choices").order_by("?")[:n])
    return qs


# --- Instructor copilot ---------------------------------------------------------------------------

def draft_questions(course, lesson_text, n=5, actor=None):
    """Draft practice/assessment questions for expert review. Saved inactive + ai_draft=True."""
    from apps.assessments.models import Choice, Question, QuestionBank

    bank, _ = QuestionBank.objects.get_or_create(course=course, defaults={"title": f"{course.title} question bank"})
    created = []
    if ai_enabled():
        import json

        prompt = (f"From the lesson text below, write {n} multiple-choice questions for sports professionals in Nigeria. "
                  "Each must be answerable from the text alone. Return JSON only: a list of objects with keys "
                  "'question', 'options' (4 strings), 'correct' (index 0-3), 'explanation', 'topic'.\n\nLESSON:\n" + lesson_text[:12000])
        text, _ = _llm("You write clear, fair assessment items. Output valid JSON only.", [{"role": "user", "content": prompt}],
                          max_tokens=4000, effort="medium")
        try:
            items = json.loads(text[text.index("["): text.rindex("]") + 1]) if text else []
        except ValueError:
            items = []
        for it in items[:n]:
            q = Question.objects.create(bank=bank, kind="mcq", text=str(it.get("question", ""))[:2000], topic=str(it.get("topic", ""))[:80],
                                        explanation=str(it.get("explanation", ""))[:2000], is_active=False, ai_draft=True)
            for i, opt in enumerate(it.get("options", [])[:4]):
                Choice.objects.create(question=q, text=str(opt)[:300], is_correct=(i == it.get("correct")), order=i)
            created.append(q)
    if not created:
        # Offline drafting: cloze (fill-the-gap) items built from key sentences. Always reviewed by an expert.
        sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", re.sub(r"[#*>`_]", "", lesson_text)) if 40 < len(s.strip()) < 220]
        vocab = Counter(t for s in sentences for t in terms(s))
        for s in sentences[: n * 3]:
            key_terms = sorted(set(terms(s)), key=lambda t: (-len(t), vocab[t]))
            if not key_terms:
                continue
            answer = key_terms[0]
            distractors = [t for t, _ in vocab.most_common(40) if t != answer and len(t) > 4][:3]
            if len(distractors) < 3:
                continue
            q = Question.objects.create(bank=bank, kind="mcq", ai_draft=True, is_active=False, topic="Draft",
                                        text="Complete the statement: " + re.sub(rf"\b{re.escape(answer)}\b", "_____", s, flags=re.I),
                                        explanation=s)
            for i, opt in enumerate(sorted([answer] + distractors)):
                Choice.objects.create(question=q, text=opt, is_correct=(opt == answer), order=i)
            created.append(q)
            if len(created) >= n:
                break
    return created


def draft_objectives(course):
    text = " ".join(l.body for l in course.lessons()[:20])
    if ai_enabled() and text.strip():
        out, _ = _llm("Write 4-6 measurable learning objectives (one per line, starting with a verb) for this course. "
                         "Only use what the content covers.", [{"role": "user", "content": text[:15000]}], max_tokens=600, effort="low")
        if out:
            return out
    heads = re.findall(r"^#+\s*(.+)$", text, flags=re.M)
    return "\n".join(f"Explain {h.strip().rstrip('.').lower()}" for h in heads[:6]) or "Describe the key ideas of each module"


def preliminary_feedback(rubric, model_answer, text):
    """Draft feedback for an assessor (never a grade). Keyword coverage when no AI key."""
    if ai_enabled() and text.strip():
        crit = "\n".join(f"- {c.get('title')} (max {c.get('max')})" for c in rubric) or "Holistic quality"
        out, _ = _llm("You help a sports assessor. Give brief, specific preliminary feedback against the rubric: strengths, "
                         "gaps, one improvement per criterion. Do NOT give a score or pass/fail; the assessor decides.",
                         [{"role": "user", "content": f"RUBRIC:\n{crit}\n\nGUIDANCE:\n{model_answer}\n\nSUBMISSION:\n{text[:12000]}"}],
                         max_tokens=900, effort="low")
        if out:
            return out
    want = set(terms(model_answer + " " + " ".join(c.get("title", "") for c in rubric)))
    have = set(terms(text))
    if not want:
        return ""
    covered = sorted(want & have)
    missing = sorted(want - have)[:12]
    return (f"Automatic coverage check (draft, not a grade): {round(100 * len(covered) / len(want))}% of key terms present.\n"
            f"Mentioned: {', '.join(covered[:15]) or 'none'}.\nPossibly missing: {', '.join(missing) or 'nothing obvious'}.")


# --- Learning-risk alerts -----------------------------------------------------------------------------

def scan_risks():
    from apps.assessments.models import Attempt
    from apps.learning.models import Enrolment

    from .models import RiskAlert

    now = timezone.now()
    n = 0
    for e in Enrolment.objects.filter(status="active").select_related("course", "user"):
        found = []
        if e.last_activity_at and e.last_activity_at < now - timezone.timedelta(days=14):
            found.append(("inactive", f"No activity since {e.last_activity_at:%d %b}"))
        fails = Attempt.objects.filter(user=e.user, exam__course=e.course, status="released", passed=False).count()
        if fails >= 2:
            found.append(("repeat_fail", f"{fails} failed attempts"))
        if e.due_date and e.due_date <= timezone.localdate() + timezone.timedelta(days=7) and e.progress < 50:
            found.append(("stalled", f"{e.progress}% done, due {e.due_date:%d %b}"))
        for kind, detail in found:
            _, created = RiskAlert.objects.get_or_create(enrolment=e, kind=kind, resolved=False, defaults={"detail": detail})
            n += int(created)
    return n
