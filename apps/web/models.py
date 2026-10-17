from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from apps.core.models import TimeStampedModel


class PartnerLogo(models.Model):
    name = models.CharField(max_length=120)
    logo = models.ImageField(upload_to="partners/", blank=True)
    url = models.URLField(blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.name


class Testimonial(models.Model):
    name = models.CharField(max_length=120)
    role = models.CharField(max_length=160)
    quote = models.TextField()
    photo = models.ImageField(upload_to="testimonials/", blank=True)
    is_sample = models.BooleanField(default=False, help_text="Illustrative placeholder, labelled as such on the site")
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.name

    @property
    def initials(self):
        return "".join(p[0] for p in self.name.split()[:2]).upper()


class PressMention(models.Model):
    outlet = models.CharField(max_length=120)
    headline = models.CharField(max_length=255)
    url = models.URLField(blank=True)
    published_on = models.DateField(default=timezone.localdate)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-published_on"]

    def __str__(self):
        return self.headline


class ImpactStat(models.Model):
    label = models.CharField(max_length=80)
    value = models.CharField(max_length=20)
    is_illustrative = models.BooleanField(default=True, help_text="Shown with an 'illustrative' label until real data")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["order"]

    def __str__(self):
        return self.label


class BlogPost(TimeStampedModel):
    title = models.CharField(max_length=200)
    slug = models.SlugField(max_length=200, unique=True, blank=True)
    excerpt = models.CharField(max_length=300)
    body = models.TextField(help_text="Markdown")
    cover = models.ImageField(upload_to="blog/", blank=True)
    cover_color = models.CharField(max_length=7, default="#0B3D2E")
    kind = models.CharField(max_length=20, default="Article")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    published_at = models.DateTimeField(null=True, blank=True, help_text="Empty = draft")
    read_minutes = models.PositiveSmallIntegerField(default=5)

    class Meta:
        ordering = ["-published_at"]

    def __str__(self):
        return self.title

    def save(self, *a, **kw):
        self.slug = self.slug or slugify(self.title)[:200]
        super().save(*a, **kw)

    def get_absolute_url(self):
        return reverse("web:blog_detail", args=[self.slug])

    @classmethod
    def published(cls):
        return cls.objects.filter(published_at__isnull=False, published_at__lte=timezone.now())


class Event(TimeStampedModel):
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    starts_at = models.DateTimeField()
    location = models.CharField(max_length=200, default="Online")
    url = models.URLField(blank=True)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering = ["starts_at"]

    def __str__(self):
        return self.title


class NewsletterSubscriber(models.Model):
    email = models.EmailField(unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return self.email


class DemoRequest(TimeStampedModel):
    STATUSES = [("new", "New"), ("contacted", "Contacted"), ("closed", "Closed")]
    name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=30, blank=True)
    organisation = models.CharField(max_length=200)
    organisation_type = models.CharField(max_length=60, blank=True)
    learners_estimate = models.CharField(max_length=40, blank=True)
    message = models.TextField(blank=True)
    status = models.CharField(max_length=10, choices=STATUSES, default="new")

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.organisation} ({self.name})"
