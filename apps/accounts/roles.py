"""Staff roles for the back office. Institution-scoped roles live on institutions.Membership."""

SUPER_ADMIN = "super_admin"
NIS_ADMIN = "nis_admin"
ACADEMIC = "academic_manager"
CREATOR = "course_creator"
REVIEWER = "reviewer"
INSTRUCTOR = "instructor"
REGISTRAR = "registrar"
FINANCE = "finance_officer"
SUPPORT = "support_agent"
COMMS = "comms_officer"
ANALYST = "analyst"
EXTERNAL_REVIEWER = "external_reviewer"
SAFEGUARDING = "safeguarding_officer"
RESEARCH = "research_officer"
MODERATOR = "community_moderator"
WORKFORCE = "workforce_officer"
LIBRARIAN = "librarian"

STAFF_ROLES = [
    (SUPER_ADMIN, "Super administrator"),
    (NIS_ADMIN, "NIS administrator"),
    (ACADEMIC, "Academic manager"),
    (CREATOR, "Course creator"),
    (REVIEWER, "Academic reviewer"),
    (INSTRUCTOR, "Instructor / examiner"),
    (REGISTRAR, "Registrar (credentials)"),
    (FINANCE, "Finance officer"),
    (SUPPORT, "Support agent"),
    (COMMS, "Communications officer"),
    (ANALYST, "Analyst / leadership"),
    (EXTERNAL_REVIEWER, "External subject reviewer"),
    (SAFEGUARDING, "Safeguarding officer (restricted cases)"),
    (RESEARCH, "Research office"),
    (MODERATOR, "Community moderator"),
    (WORKFORCE, "Workforce unit"),
    (LIBRARIAN, "Librarian"),
]
# Roles that NIS administrators do NOT inherit: confidential safeguarding cases stay with designated officers.
RESTRICTED_ROLES = {SAFEGUARDING}
ROLE_LABELS = dict(STAFF_ROLES)


def user_has_role(user, *roles):
    if not user or not user.is_authenticated or not user.is_active:
        return False
    have = set(user.staff_roles or [])
    if set(roles) and set(roles) <= RESTRICTED_ROLES:
        return bool(have.intersection(roles))  # not even super admins see confidential cases by default
    if user.is_superuser or SUPER_ADMIN in have:
        return True
    if NIS_ADMIN in have and SUPER_ADMIN not in roles:
        # NIS administrators can do everything except super-admin-only settings.
        return True
    return bool(have.intersection(roles))


def is_institution_admin(user):
    return bool(
        user and user.is_authenticated
        and user.memberships.filter(role="admin", institution__is_active=True).exists()
    )


def can_access_backoffice(user):
    return bool(
        user and user.is_authenticated and user.is_active
        and (user.is_superuser or user.staff_roles or is_institution_admin(user))
    )


def users_with_role(role):
    """Active users holding a staff role (portable across SQLite and PostgreSQL JSON fields)."""
    from .models import User

    ids = [u.pk for u in User.objects.filter(is_active=True).exclude(staff_roles=[]).only("pk", "staff_roles") if role in (u.staff_roles or [])]
    return User.objects.filter(pk__in=ids)
