"""Field-level encryption for sensitive data (integrity reports, case notes)."""
import base64
import hashlib

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.db import models


def _fernet():
    key = getattr(settings, "INTEGRITY_ENCRYPTION_KEY", "")
    if not key:
        # Derive a stable development key from SECRET_KEY. Production must set INTEGRITY_ENCRYPTION_KEY.
        key = base64.urlsafe_b64encode(hashlib.sha256(("integrity:" + settings.SECRET_KEY).encode()).digest()).decode()
    return Fernet(key.encode() if isinstance(key, str) else key)


class EncryptedTextField(models.TextField):
    PREFIX = "enc::"

    def from_db_value(self, value, expression, connection):
        if not value or not value.startswith(self.PREFIX):
            return value
        try:
            return _fernet().decrypt(value[len(self.PREFIX):].encode()).decode()
        except InvalidToken:
            return "[unreadable: encryption key changed]"

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if not value or value.startswith(self.PREFIX):
            return value
        return self.PREFIX + _fernet().encrypt(value.encode()).decode()
