from django.db import models


class MetricDefinition(models.Model):
    """Every dashboard figure has a written definition (blueprint Module 18)."""

    code = models.SlugField(unique=True)
    name = models.CharField(max_length=120)
    definition = models.TextField()
    group = models.CharField(max_length=40, default="Learners")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["group", "order"]

    def __str__(self):
        return self.name


class MetricSnapshot(models.Model):
    date = models.DateField(db_index=True)
    code = models.SlugField()
    value = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        unique_together = [("date", "code")]
        ordering = ["date"]


class ScheduledReport(models.Model):
    FREQ = [("weekly", "Weekly (Mondays)"), ("monthly", "Monthly (1st)")]
    name = models.CharField(max_length=120)
    recipients = models.TextField(help_text="Email addresses, one per line")
    frequency = models.CharField(max_length=8, choices=FREQ, default="monthly")
    state = models.CharField(max_length=40, blank=True)
    profession = models.CharField(max_length=60, blank=True, help_text="Profession slug (optional)")
    is_active = models.BooleanField(default=True)
    last_sent = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.name
