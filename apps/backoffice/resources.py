"""Generic back-office CRUD registry for straightforward records (no developer needed to manage them)."""
from apps.analytics.models import ScheduledReport
from apps.careers.models import Challenge
from apps.catalog.models import CourseTranslation, LessonTemplate, LessonTranslation
from apps.community.models import Group
from apps.credentials.models import Programme
from apps.integrations.models import LtiPlatform, Webhook
from apps.labs.models import Scenario
from apps.library.models import Collection, Resource
from apps.live.models import LiveSession, OfficeHourSlot
from apps.practicals.models import PracticalTask
from apps.research.models import Dataset

# key: (model, fields, label, roles, columns, help)
RESOURCES = {
    "programmes": (Programme, ["title", "slug", "summary", "description", "credential_type", "courses", "practical_tasks",
                               "requires_application", "is_published"], "Qualifications (programmes)", ("academic_manager", "registrar"),
                   ["title", "credential_type", "is_published"], "A qualification is awarded automatically when all its courses and supervised practicals are complete."),
    "practical-tasks": (PracticalTask, ["course", "title", "kind", "instructions", "template_file", "rubric", "pass_mark",
                                        "requires_supervisor", "accepts_video"], "Practical tasks", ("academic_manager", "course_creator"),
                        ["title", "course", "kind", "requires_supervisor"], 'Rubric example: [{"title": "Clear objective", "max": 5}, {"title": "Safety", "max": 5}]'),
    "live-sessions": (LiveSession, ["title", "kind", "description", "course", "cohort", "host", "co_hosts", "partner_institutions",
                                    "guest_speaker", "starts_at", "duration_minutes", "location", "capacity", "is_public", "cpd_points",
                                    "record", "recording_url", "recording_available_until", "status"], "Live sessions",
                      ("academic_manager", "instructor"), ["title", "kind", "starts_at", "status"], "Online sessions get a video room automatically."),
    "office-hours": (OfficeHourSlot, ["host", "course", "starts_at", "duration_minutes"], "Office-hour slots",
                     ("academic_manager", "instructor"), ["host", "starts_at", "booked_by"], ""),
    "library": (Resource, ["title", "kind", "authors", "publisher", "abstract", "file", "external_url", "cover_color", "tags", "sports",
                           "track", "published_on", "version", "licence", "owner", "access_level", "review_date", "is_published",
                           "ai_indexable"], "Library resources", ("librarian", "academic_manager"),
                ["title", "kind", "access_level", "is_published"], "Record ownership and licence for every item. Restricted items need individual access grants."),
    "reading-lists": (Collection, ["user", "name", "is_reading_list", "course", "resources"], "Reading lists",
                      ("librarian", "instructor"), ["name", "course", "is_reading_list"], ""),
    "labs": (Scenario, ["title", "kind", "engine", "summary", "intro", "video", "data", "sport", "professions", "requires_qualified",
                        "is_published"], "Practical labs & simulators", ("academic_manager", "course_creator"),
             ["title", "kind", "engine", "is_published"], "The data field holds the scenario (JSON). See the seeded labs for the structure of each engine."),
    "groups": (Group, ["name", "kind", "description", "sport", "profession", "course", "is_private", "verified_only"],
               "Community groups", ("community_moderator",), ["name", "kind", "is_private"], ""),
    "challenges": (Challenge, ["title", "description", "metric", "target", "starts_on", "ends_on", "cohort", "team_mode",
                               "show_leaderboard", "is_active"], "Challenges", ("academic_manager", "comms_officer"),
                   ["title", "metric", "ends_on", "is_active"], "Leaderboards are optional; leave them off unless the cohort wants them."),
    "datasets": (Dataset, ["title", "description", "file", "access", "contains_personal_data", "is_anonymised", "licence", "project",
                           "variables"], "Research datasets", ("research_officer",), ["title", "access", "contains_personal_data"], ""),
    "lesson-templates": (LessonTemplate, ["name", "kind", "body", "duration_minutes"], "Lesson templates",
                         ("academic_manager", "course_creator"), ["name", "kind"], ""),
    "translations": (CourseTranslation, ["course", "language", "title", "summary", "description", "status", "reviewer"],
                     "Course translations", ("academic_manager",), ["course", "language", "status"],
                     "Translations show to learners only when an expert reviewer marks them Approved."),
    "lesson-translations": (LessonTranslation, ["lesson", "language", "title", "body", "transcript", "subtitles", "status"],
                            "Lesson translations", ("academic_manager",), ["lesson", "language", "status"], ""),
    "scheduled-reports": (ScheduledReport, ["name", "recipients", "frequency", "state", "profession", "is_active"],
                          "Scheduled reports", ("analyst",), ["name", "frequency", "is_active"],
                          "Emails a CSV of headline metrics with their definitions."),
    "webhooks": (Webhook, ["url", "events", "institution", "is_active"], "Webhooks", ("super_admin",), ["url", "is_active"],
                 'Events, e.g. ["credential.issued", "enrolment.completed"]. Deliveries are signed with HMAC-SHA256 (X-SportIQ-Signature).'),
    "lti-platforms": (LtiPlatform, ["name", "issuer", "client_id", "deployment_id", "auth_login_url", "jwks_url", "institution",
                                    "is_active"], "LTI 1.3 platforms", ("super_admin",), ["name", "issuer", "is_active"],
                      "Tool URLs: login /lti/login/, launch /lti/launch/, JWKS /lti/jwks.json. Add a custom parameter course=<slug>."),
}
