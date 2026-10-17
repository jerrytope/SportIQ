"""Phase 4 adapters: federation registration systems and government identity verification.

Both are OFF unless configured, and identity verification must only be enabled where legally authorised
(blueprint Module 19). The sandbox provider returns deterministic test results so flows can be exercised
without touching any real government system. Every call is logged.
"""
import json
import urllib.parse
import urllib.request

from django.conf import settings

from .models import RegistryAdapterLog


class FederationRegistry:
    """Looks up a coach/official's registration with a federation registry (if a data-sharing agreement exists)."""

    name = "federation_registry"

    @property
    def enabled(self):
        return bool(settings.FEDERATION_REGISTRY_URL)

    def lookup(self, user, actor, registration_number=""):
        if not self.enabled:
            return {"status": "not_configured", "detail": "No federation registry is connected."}
        query = urllib.parse.urlencode({"email": user.email, "registration_number": registration_number})
        req = urllib.request.Request(f"{settings.FEDERATION_REGISTRY_URL.rstrip('/')}/lookup?{query}",
                                     headers={"Authorization": f"Bearer {settings.FEDERATION_REGISTRY_TOKEN}"})
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                data = json.loads(r.read())
            outcome = "found" if data.get("found") else "not_found"
        except Exception as exc:  # noqa: BLE001 - surfaced to staff, logged
            data, outcome = {"error": str(exc)[:200]}, "error"
        RegistryAdapterLog.objects.create(adapter=self.name, action="lookup", user=actor,
                                          request_summary=f"user={user.pk}", outcome=outcome)
        return {"status": outcome, "detail": data}


class IdentityVerification:
    """Checks a learner's identity (e.g. NIN) with an authorised provider. Sandbox by default."""

    name = "identity_verification"

    @property
    def enabled(self):
        return settings.IDENTITY_VERIFICATION_ENABLED

    def verify(self, user, id_number, actor):
        if not self.enabled:
            return {"status": "disabled", "detail": "Identity verification is not enabled for this deployment."}
        provider = settings.IDENTITY_VERIFICATION_PROVIDER
        if provider == "sandbox":
            # Deterministic test behaviour: 11-digit numbers ending in an even digit match.
            ok = id_number.isdigit() and len(id_number) == 11 and int(id_number[-1]) % 2 == 0
            outcome = "match" if ok else "no_match"
        else:
            outcome = "provider_not_implemented"
        RegistryAdapterLog.objects.create(adapter=self.name, action="verify", user=actor,
                                          request_summary=f"user={user.pk} id=***{id_number[-3:]}", outcome=outcome)
        return {"status": outcome, "provider": provider}
