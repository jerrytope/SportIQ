"""LTI 1.3 resource-link launches: verify the platform's id_token, map the user, find the target course."""
import json
import os

import jwt
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from django.conf import settings

from apps.accounts.models import User

LTI = "https://purl.imsglobal.org/spec/lti/claim/"


def _private_key():
    path = settings.LTI_PRIVATE_KEY_PATH
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        with open(path, "wb") as fh:
            fh.write(key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                       serialization.NoEncryption()))
    with open(path, "rb") as fh:
        return serialization.load_pem_private_key(fh.read(), password=None)


def public_jwks():
    pub = _private_key().public_key()
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(pub))
    jwk.update({"kid": "sportiq-lti-1", "alg": "RS256", "use": "sig"})
    return {"keys": [jwk]}


def decode_launch(id_token, platform, nonce):
    signing_key = jwt.PyJWKClient(platform.jwks_url).get_signing_key_from_jwt(id_token).key
    claims = jwt.decode(id_token, signing_key, algorithms=["RS256"], audience=platform.client_id, issuer=platform.issuer)
    if claims.get("nonce") != nonce:
        raise ValueError("nonce mismatch")
    if platform.deployment_id and claims.get(LTI + "deployment_id") != platform.deployment_id:
        raise ValueError("deployment mismatch")
    if claims.get(LTI + "message_type") != "LtiResourceLinkRequest":
        raise ValueError("unsupported message type")
    return claims


def user_for(claims, platform):
    from .models import ExternalIdentity

    provider = f"lti:{platform.pk}"
    ident = ExternalIdentity.objects.filter(provider=provider, subject=claims["sub"]).select_related("user").first()
    if ident:
        return ident.user
    email = (claims.get("email") or f"lti-{platform.pk}-{claims['sub']}@lti.sportiq.invalid").lower()
    user = User.objects.filter(email__iexact=email).first() or User.objects.create_user(
        email=email, password=None, first_name=claims.get("given_name", ""), last_name=claims.get("family_name", ""),
        email_verified=bool(claims.get("email")))
    ExternalIdentity.objects.create(user=user, provider=provider, subject=claims["sub"])
    if platform.institution_id:
        from apps.institutions.models import Membership

        Membership.objects.get_or_create(user=user, institution=platform.institution, defaults={"role": "member"})
    return user


def target_url(claims):
    """Custom parameter `course=<slug>` on the LMS link opens that SportIQ course."""
    custom = claims.get(LTI + "custom", {}) or {}
    slug = custom.get("course") or custom.get("sportiq_course")
    return f"/courses/{slug}/" if slug else None
