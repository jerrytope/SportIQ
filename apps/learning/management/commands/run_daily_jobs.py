from django.core.management.base import BaseCommand

from apps.learning.tasks import run_all


class Command(BaseCommand):
    help = "Send reminders (inactivity, deadlines, renewals) and store the nightly metrics snapshot."

    def handle(self, *args, **options):
        self.stdout.write(str(run_all()))
