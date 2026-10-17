from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.utils import timezone

NIGERIAN_STATES = [
    "Abia", "Adamawa", "Akwa Ibom", "Anambra", "Bauchi", "Bayelsa", "Benue", "Borno", "Cross River", "Delta",
    "Ebonyi", "Edo", "Ekiti", "Enugu", "FCT", "Gombe", "Imo", "Jigawa", "Kaduna", "Kano", "Katsina", "Kebbi",
    "Kogi", "Kwara", "Lagos", "Nasarawa", "Niger", "Ogun", "Ondo", "Osun", "Oyo", "Plateau", "Rivers", "Sokoto",
    "Taraba", "Yobe", "Zamfara",
]
STATE_CHOICES = [(s, s) for s in NIGERIAN_STATES]


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("Email is required")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("email_verified", True)
        return self._create_user(email, password, **extra)


class User(AbstractUser):
    username = None
    email = models.EmailField(unique=True)
    email_verified = models.BooleanField(default=False)
    phone = models.CharField(max_length=20, blank=True)
    state = models.CharField(max_length=40, choices=STATE_CHOICES, blank=True)
    lga = models.CharField("LGA", max_length=80, blank=True)
    gender = models.CharField(
        max_length=20, blank=True,
        choices=[("female", "Female"), ("male", "Male"), ("prefer_not", "Prefer not to say")],
    )
    photo = models.ImageField(upload_to="avatars/", blank=True)
    bio = models.TextField(blank=True)
    languages = models.CharField(max_length=200, blank=True, help_text="Comma-separated, e.g. English, Yoruba")
    professions = models.ManyToManyField("catalog.Profession", blank=True, related_name="users")
    sports = models.ManyToManyField("catalog.Sport", blank=True, related_name="users")
    # Optional, consented, used only for aggregated inclusion reporting (blueprint §8).
    has_disability = models.BooleanField(null=True, blank=True)
    accessibility_needs = models.CharField(max_length=255, blank=True)
    # Preferences
    data_saver = models.BooleanField(default=False)
    notify_email = models.BooleanField(default=True)
    notify_sms = models.BooleanField(default=False)
    profile_public = models.BooleanField(default=False)
    is_verified_professional = models.BooleanField(default=False)
    staff_roles = models.JSONField(default=list, blank=True)
    deactivated_reason = models.CharField(max_length=255, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []
    objects = UserManager()

    class Meta:
        ordering = ["first_name", "last_name"]

    def __str__(self):
        return self.get_full_name() or self.email

    @property
    def initials(self):
        parts = [p for p in (self.first_name, self.last_name) if p]
        return "".join(p[0] for p in parts).upper() or self.email[:2].upper()

    def has_role(self, *roles):
        from .roles import user_has_role

        return user_has_role(self, *roles)

    @property
    def is_backoffice(self):
        from .roles import can_access_backoffice

        return can_access_backoffice(self)

    @property
    def role_labels(self):
        from .roles import ROLE_LABELS

        return [ROLE_LABELS.get(r, r) for r in (self.staff_roles or [])]


class Consent(models.Model):
    KINDS = [("terms", "Terms of use"), ("privacy", "Privacy notice"), ("marketing", "Marketing emails"),
             ("sensitive", "Sensitive data (disability) for inclusion reporting"),
             ("directory", "Listing in workforce directory")]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="consents")
    kind = models.CharField(max_length=20, choices=KINDS)
    version = models.CharField(max_length=20, default="2026-10")
    granted = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-created_at"]


class DataRequest(models.Model):
    """NDPA data-subject request (export, deletion or correction)."""

    KINDS = [("export", "Export my data"), ("delete", "Delete my account"), ("correct", "Correct my data")]
    STATUSES = [("open", "Open"), ("done", "Completed"), ("rejected", "Rejected")]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="data_requests")
    kind = models.CharField(max_length=10, choices=KINDS)
    details = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default="open")
    resolution_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
