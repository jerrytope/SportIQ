from django import forms

from apps.accounts.models import User
from apps.accounts.roles import STAFF_ROLES
from apps.assessments.models import Exam, Question
from apps.catalog.models import Course, Lesson, Module
from apps.commerce.models import Voucher
from apps.core.models import SiteSettings
from apps.credentials.models import CredentialType
from apps.institutions.models import Institution
from apps.learning.models import AcademicTerm, Cohort
from apps.notifications.models import Announcement, Campaign
from apps.support.models import HelpArticle, StatusNotice
from apps.web.models import BlogPost, Event, ImpactStat, PartnerLogo, PressMention, Testimonial

DATE = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
DATETIME = forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")


class CourseForm(forms.ModelForm):
    price_naira = forms.DecimalField(label="Price (₦)", min_value=0, decimal_places=2, initial=0,
                                     help_text="0 = free")

    class Meta:
        model = Course
        fields = ["title", "code", "summary", "description", "track", "subject", "level", "language",
                  "delivery_format", "duration_hours", "thumbnail", "cover_color", "is_public", "requires_application",
                  "featured", "professions", "sports", "prerequisites", "institution", "instructors", "objectives",
                  "audience", "prerequisites_text", "assessment_criteria", "references", "framework_mapping",
                  "revision_date", "review_due", "completion_requires_exam", "issues_certificate", "credential_type",
                  "publish_at", "external_reviewers"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 6}), "objectives": forms.Textarea(attrs={"rows": 4}),
            "audience": forms.Textarea(attrs={"rows": 3}), "prerequisites_text": forms.Textarea(attrs={"rows": 3}),
            "assessment_criteria": forms.Textarea(attrs={"rows": 3}), "references": forms.Textarea(attrs={"rows": 3}),
            "revision_date": DATE, "review_due": DATE, "cover_color": forms.TextInput(attrs={"type": "color"}),
            "professions": forms.CheckboxSelectMultiple, "sports": forms.CheckboxSelectMultiple,
            "prerequisites": forms.SelectMultiple(attrs={"size": 5}), "instructors": forms.SelectMultiple(attrs={"size": 5}),
            "publish_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "external_reviewers": forms.SelectMultiple(attrs={"size": 4}),
        }

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["instructors"].queryset = User.objects.exclude(staff_roles=[])
        self.fields["external_reviewers"].queryset = User.objects.exclude(staff_roles=[])
        self.fields["prerequisites"].queryset = Course.objects.exclude(pk=self.instance.pk or 0)
        if self.instance.pk:
            self.fields["price_naira"].initial = self.instance.price_kobo / 100

    def save(self, commit=True):
        course = super().save(commit=False)
        course.price_kobo = int(self.cleaned_data["price_naira"] * 100)
        if commit:
            course.save()
            self.save_m2m()
        return course


class ModuleForm(forms.ModelForm):
    class Meta:
        model = Module
        fields = ["title", "summary", "order"]
        widgets = {"summary": forms.Textarea(attrs={"rows": 2})}


class LessonForm(forms.ModelForm):
    class Meta:
        model = Lesson
        fields = ["title", "kind", "order", "duration_minutes", "is_preview", "body", "video", "audio", "subtitles",
                  "transcript", "attachment", "exam", "practical_task", "lab", "live_session", "embed_url"]
        widgets = {"body": forms.Textarea(attrs={"rows": 10}), "transcript": forms.Textarea(attrs={"rows": 5})}
        help_texts = {"video": "MP4/MOV. It is converted automatically to adaptive low-bandwidth streams and an audio-only track.",
                      "exam": "For quiz lessons: the assessment learners take here."}

    def __init__(self, *a, course=None, **kw):
        super().__init__(*a, **kw)
        self.fields["exam"].queryset = Exam.objects.filter(course=course) if course else Exam.objects.none()
        from apps.live.models import LiveSession
        from apps.practicals.models import PracticalTask

        self.fields["practical_task"].queryset = PracticalTask.objects.filter(course=course) if course else PracticalTask.objects.none()
        self.fields["live_session"].queryset = LiveSession.objects.filter(course=course) if course else LiveSession.objects.none()


class QuestionForm(forms.ModelForm):
    choices_text = forms.CharField(
        widget=forms.Textarea(attrs={"rows": 5}), required=False, label="Answer options",
        help_text="One option per line. Start correct options with an asterisk, e.g. <code>* Prohibited at all times</code>. "
                  "For true/false write <code>* True</code> and <code>False</code>.",
    )

    class Meta:
        model = Question
        fields = ["kind", "case_text", "text", "image", "video", "topic", "difficulty", "points", "explanation", "model_answer",
                  "is_active", "is_practice"]
        widgets = {"text": forms.Textarea(attrs={"rows": 3}), "case_text": forms.Textarea(attrs={"rows": 3}),
                   "explanation": forms.Textarea(attrs={"rows": 2}),
                   "model_answer": forms.Textarea(attrs={"rows": 2})}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        if self.instance.pk:
            self.fields["choices_text"].initial = "\n".join(
                f"{'* ' if c.is_correct else ''}{c.text}" for c in self.instance.choices.all())

    def clean(self):
        data = super().clean()
        kind = data.get("kind")
        if kind in Question.AUTO_MARKED:
            lines = [ln.strip() for ln in (data.get("choices_text") or "").splitlines() if ln.strip()]
            if len(lines) < 2:
                self.add_error("choices_text", "Give at least two options.")
            correct = [ln for ln in lines if ln.startswith("*")]
            if not correct:
                self.add_error("choices_text", "Mark at least one correct option with *.")
            if kind in (Question.MCQ, Question.TF) and len(correct) > 1:
                self.add_error("choices_text", "Single-answer questions need exactly one correct option.")
            data["parsed_choices"] = [(ln.lstrip("* ").strip(), ln.startswith("*")) for ln in lines]
        return data

    def save(self, commit=True):
        q = super().save(commit=commit)
        if commit and "parsed_choices" in self.cleaned_data:
            q.choices.all().delete()
            for i, (text, ok) in enumerate(self.cleaned_data["parsed_choices"]):
                q.choices.create(text=text[:300], is_correct=ok, order=i)
        return q


class ExamForm(forms.ModelForm):
    class Meta:
        model = Exam
        fields = ["title", "instructions", "time_limit_minutes", "pass_mark", "attempts_allowed", "question_count",
                  "blueprint", "shuffle", "is_final", "is_pretest", "auto_release", "requires_moderation", "opens_at", "closes_at",
                  "identity_declaration", "webcam_invigilation", "is_published"]
        widgets = {"instructions": forms.Textarea(attrs={"rows": 3}), "blueprint": forms.Textarea(attrs={"rows": 2}),
                   "opens_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
                   "closes_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M")}


class InstitutionForm(forms.ModelForm):
    class Meta:
        model = Institution
        fields = ["name", "kind", "state", "sport", "description", "logo", "website", "contact_email", "is_active"]
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


class UserAdminForm(forms.ModelForm):
    staff_roles = forms.MultipleChoiceField(choices=STAFF_ROLES, required=False, widget=forms.CheckboxSelectMultiple,
                                            label="Back-office roles")

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "phone", "state", "is_active", "is_verified_professional",
                  "deactivated_reason", "staff_roles"]


class CohortForm(forms.ModelForm):
    class Meta:
        model = Cohort
        fields = ["course", "name", "term", "institution", "starts_on", "ends_on", "capacity", "instructor",
                  "leaderboard_enabled"]
        widgets = {"starts_on": DATE, "ends_on": DATE}

    def __init__(self, *a, **kw):
        super().__init__(*a, **kw)
        self.fields["instructor"].queryset = User.objects.exclude(staff_roles=[])


class TermForm(forms.ModelForm):
    class Meta:
        model = AcademicTerm
        fields = ["name", "starts_on", "ends_on"]
        widgets = {"starts_on": DATE, "ends_on": DATE}


class CredentialTypeForm(forms.ModelForm):
    class Meta:
        model = CredentialType
        fields = ["code", "name", "kind", "description", "validity_months", "issuer_name"]
        widgets = {"description": forms.Textarea(attrs={"rows": 2})}


class IssueCredentialForm(forms.Form):
    email = forms.EmailField(label="Holder's email")
    credential_type = forms.ModelChoiceField(queryset=CredentialType.objects.all())
    title = forms.CharField(max_length=200)
    course = forms.ModelChoiceField(queryset=Course.objects.all(), required=False)
    grade = forms.CharField(max_length=40, required=False)

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        try:
            self.cleaned_data["user"] = User.objects.get(email__iexact=email)
        except User.DoesNotExist:
            raise forms.ValidationError("No SportIQ account uses this email.")
        return email


class VoucherForm(forms.ModelForm):
    class Meta:
        model = Voucher
        fields = ["code", "course", "discount_percent", "max_uses", "sponsor", "expires_on", "is_active"]
        widgets = {"expires_on": DATE}


class AnnouncementForm(forms.ModelForm):
    class Meta:
        model = Announcement
        fields = ["title", "body", "audience", "profession", "institution", "course", "is_active"]
        widgets = {"body": forms.Textarea(attrs={"rows": 3})}


class CampaignForm(forms.ModelForm):
    class Meta:
        model = Campaign
        fields = ["channel", "subject", "body", "audience", "profession", "institution", "course"]
        widgets = {"body": forms.Textarea(attrs={"rows": 4})}


class HelpArticleForm(forms.ModelForm):
    class Meta:
        model = HelpArticle
        fields = ["category", "title", "body", "is_faq", "is_published", "order"]
        widgets = {"body": forms.Textarea(attrs={"rows": 10})}


class StatusNoticeForm(forms.ModelForm):
    class Meta:
        model = StatusNotice
        fields = ["message", "level", "starts_at", "ends_at", "is_active"]
        widgets = {"starts_at": DATETIME, "ends_at": DATETIME}


class SiteSettingsForm(forms.ModelForm):
    class Meta:
        model = SiteSettings
        fields = ["announcement_text", "announcement_link", "hero_eyebrow", "hero_title", "hero_subtitle",
                  "contact_email", "contact_phone", "address", "support_hours", "linkedin_url", "instagram_url",
                  "x_url", "youtube_url"]
        widgets = {"hero_subtitle": forms.Textarea(attrs={"rows": 3})}


class PlatformSettingsForm(forms.ModelForm):
    class Meta:
        model = SiteSettings
        fields = ["public_registration_open", "leaderboards_enabled"]


SITE_CONTENT = {
    "partners": (PartnerLogo, ["name", "logo", "url", "order", "is_active"], "Partner logos"),
    "testimonials": (Testimonial, ["name", "role", "quote", "photo", "is_sample", "order", "is_active"], "Testimonials"),
    "press": (PressMention, ["outlet", "headline", "url", "published_on", "is_active"], "Press mentions"),
    "stats": (ImpactStat, ["label", "value", "is_illustrative", "order"], "Impact statistics"),
    "blog": (BlogPost, ["title", "excerpt", "body", "cover", "cover_color", "kind", "read_minutes", "published_at"], "Blog posts"),
    "events": (Event, ["title", "description", "starts_at", "location", "url", "is_published"], "Events"),
}


def site_form_class(kind):
    model, fields, _ = SITE_CONTENT[kind]
    widgets = {}
    for f in fields:
        field = model._meta.get_field(f)
        if field.get_internal_type() == "DateTimeField":
            widgets[f] = DATETIME
        elif field.get_internal_type() == "DateField":
            widgets[f] = DATE
        elif field.get_internal_type() == "TextField":
            widgets[f] = forms.Textarea(attrs={"rows": 8 if f == "body" else 3})
    return forms.modelform_factory(model, fields=fields, widgets=widgets)
