"""Smoke-test: log in as each role and follow every same-site link, reporting errors.

    python manage.py crawl                     # all demo roles
    python manage.py crawl learner@sportiq.test
"""
import re
import urllib.parse

from django.core.management.base import BaseCommand
from django.test import Client
from django.test.utils import override_settings

from apps.accounts.models import User

ROLES = [None, "learner@sportiq.test", "admin@sportiq.test", "nisadmin@sportiq.test", "academic@sportiq.test", "creator@sportiq.test",
         "reviewer@sportiq.test", "instructor@sportiq.test", "registrar@sportiq.test", "finance@sportiq.test", "support@sportiq.test",
         "comms@sportiq.test", "analyst@sportiq.test", "federation@sportiq.test", "council@sportiq.test", "safeguarding@sportiq.test",
         "research@sportiq.test", "moderator@sportiq.test", "librarian@sportiq.test", "workforce@sportiq.test", "expert@sportiq.test"]
SKIP = re.compile(r"(logout|\.pdf$|\.zip$|\.csv$|/media/|/static/|export|transcript|/delete|/django-admin|/api/schema|mailto:|tel:|#|"
                  r"clear/|/sw\.js|/download/|/cite/|/sso/|/lti/|/i18n/|https?://(?!testserver))")


class Command(BaseCommand):
    help = "Crawl the site as each demo role and report any 4xx/5xx (except intentional 403/404)."

    def add_arguments(self, parser):
        parser.add_argument("emails", nargs="*")
        parser.add_argument("--limit", type=int, default=450)

    @override_settings(ALLOWED_HOSTS=["testserver", "localhost"], DEBUG=False)
    def handle(self, *args, **opts):
        roles = opts["emails"] or ROLES
        total = 0
        for email in roles:
            client = Client(raise_request_exception=False)
            if email and email != "anon":
                client.force_login(User.objects.get(email=email))
            start = ["/"] if not email or email == "anon" else ["/learn/", "/manage/"]
            seen, queue, bad = set(), list(start), []
            while queue and len(seen) < opts["limit"]:
                url = queue.pop(0)
                if url in seen:
                    continue
                seen.add(url)
                try:
                    r = client.get(url)
                except Exception as exc:  # noqa: BLE001
                    bad.append((url, repr(exc)[:200]))
                    continue
                if r.status_code >= 500 or r.status_code in (400, 405):
                    bad.append((url, r.status_code))
                    continue
                if r.status_code in (301, 302):
                    loc = r.headers.get("Location", "")
                    if loc.startswith("/") and loc not in seen:
                        queue.append(loc)
                    continue
                if "text/html" not in r.headers.get("Content-Type", ""):
                    continue
                for href in re.findall(r'href="([^"]+)"', r.content.decode("utf-8", "ignore")):
                    href = urllib.parse.urljoin(url, href.replace("&amp;", "&")).replace("http://testserver", "")
                    if not href.startswith("/") or SKIP.search(href):
                        continue
                    base = href.split("?")[0]
                    if "?" in href and sum(1 for s in seen if s.startswith(base + "?")) > 4:
                        continue
                    if href not in seen:
                        queue.append(href)
            total += len(bad)
            self.stdout.write(f"{email or 'anonymous'}: {len(seen)} pages, {len(bad)} problems")
            for b in bad[:20]:
                self.stdout.write(f"    {b}")
        self.stdout.write(self.style.SUCCESS("No problems found.") if not total else self.style.ERROR(f"{total} problems."))
