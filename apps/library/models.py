"""Digital library and sports knowledge centre (blueprint Module 9)."""
from django.conf import settings
from django.db import models
from django.urls import reverse

from apps.catalog.models import unique_slug
from apps.core.models import TimeStampedModel


class Resource(TimeStampedModel):
    KINDS = [("manual", "Coaching manual / technical guide"), ("rules", "Rules & regulations"),
             ("policy", "Policy / governance document"), ("legal", "Legal document"), ("research", "Research paper"),
             ("thesis", "Thesis / dissertation"), ("report", "NIS publication / report"), ("case", "Case study"),
             ("video", "Video"), ("dataset", "Teaching dataset"), ("history", "Historical record"),
             ("model3d", "3D model"), ("link", "External resource")]
    ACCESS = [("public", "Public"), ("learners", "Registered learners"), ("restricted", "Restricted (staff & approved)")]
    title = models.CharField(max_length=255)
    slug = models.SlugField(max_length=255, unique=True, blank=True)
    kind = models.CharField(max_length=10, choices=KINDS)
    authors = models.CharField(max_length=255, blank=True)
    publisher = models.CharField(max_length=200, default="National Institute for Sports")
    abstract = models.TextField(blank=True)
    file = models.FileField(upload_to="library/", blank=True)
    external_url = models.URLField(blank=True)
    cover_color = models.CharField(max_length=7, default="#0B3D2E")
    tags = models.CharField(max_length=255, blank=True, help_text="Comma-separated")
    sports = models.ManyToManyField("catalog.Sport", blank=True)
    track = models.ForeignKey("catalog.Track", null=True, blank=True, on_delete=models.SET_NULL)
    published_on = models.DateField(null=True, blank=True)
    version = models.CharField(max_length=20, default="1.0")
    licence = models.CharField(max_length=120, default="© National Institute for Sports. For educational use.")
    owner = models.CharField(max_length=200, blank=True, help_text="Documented ownership / rights holder")
    access_level = models.CharField(max_length=10, choices=ACCESS, default="learners")
    review_date = models.DateField(null=True, blank=True)
    editor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    is_published = models.BooleanField(default=True)
    ai_indexable = models.BooleanField(default=True, help_text="Approved as a source for the AI study assistant")
    downloads = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-published_on", "title"]

    def __str__(self):
        return self.title

    def save(self, *a, **kw):
        if not self.slug:
            self.slug = unique_slug(self, self.title, max_length=255)
        super().save(*a, **kw)

    def get_absolute_url(self):
        return reverse("library:detail", args=[self.slug])

    @property
    def tag_list(self):
        return [t.strip() for t in self.tags.split(",") if t.strip()]

    @property
    def year(self):
        return self.published_on.year if self.published_on else "n.d."

    def visible_to(self, user):
        if self.access_level == "public":
            return True
        if self.access_level == "learners":
            return user.is_authenticated
        return user.is_authenticated and (user.is_backoffice or self.access_grants.filter(user=user).exists())

    def citation(self, style="apa"):
        authors = self.authors or self.publisher
        if style == "harvard":
            return f"{authors} ({self.year}) {self.title}. {self.publisher}."
        if style == "bibtex":
            key = (self.authors.split(",")[0].split()[-1] if self.authors else "nis") + str(self.year)
            return (f"@misc{{{key.lower()},\n  title = {{{self.title}}},\n  author = {{{authors}}},\n"
                    f"  year = {{{self.year}}},\n  publisher = {{{self.publisher}}}\n}}")
        return f"{authors}. ({self.year}). *{self.title}*. {self.publisher}."


class ResourceVersion(models.Model):
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name="versions")
    version = models.CharField(max_length=20)
    file = models.FileField(upload_to="library/versions/", blank=True)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]


class AccessGrant(models.Model):
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name="access_grants")
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)


class Collection(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="collections")
    name = models.CharField(max_length=120)
    is_reading_list = models.BooleanField(default=False, help_text="Instructor reading list (shareable)")
    course = models.ForeignKey("catalog.Course", null=True, blank=True, on_delete=models.SET_NULL)
    resources = models.ManyToManyField(Resource, blank=True, related_name="collections")

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Annotation(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="annotations")
    resource = models.ForeignKey(Resource, on_delete=models.CASCADE, related_name="annotations")
    page = models.CharField(max_length=20, blank=True)
    note = models.TextField()

    class Meta:
        ordering = ["-created_at"]
