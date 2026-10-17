from django.db.models import Count, Q

from apps.accounts.models import NIGERIAN_STATES, User

# Approximate geographic tile cartogram of the 36 states + FCT: (row, col)
TILES = {
    "Sokoto": (0, 1), "Zamfara": (0, 2), "Katsina": (0, 3), "Kano": (0, 4), "Jigawa": (0, 5), "Yobe": (0, 6), "Borno": (0, 7),
    "Kebbi": (1, 1), "Niger": (1, 2), "Kaduna": (1, 3), "Bauchi": (1, 4), "Gombe": (1, 5), "Adamawa": (1, 6),
    "Oyo": (2, 0), "Kwara": (2, 1), "Kogi": (2, 2), "FCT": (2, 3), "Nasarawa": (2, 4), "Plateau": (2, 5), "Taraba": (2, 6),
    "Ogun": (3, 0), "Osun": (3, 1), "Ekiti": (3, 2), "Edo": (3, 3), "Benue": (3, 4),
    "Lagos": (4, 0), "Ondo": (4, 1), "Delta": (4, 2), "Anambra": (4, 3), "Enugu": (4, 4), "Ebonyi": (4, 5), "Cross River": (4, 6),
    "Bayelsa": (5, 1), "Rivers": (5, 2), "Imo": (5, 3), "Abia": (5, 4), "Akwa Ibom": (5, 5),
}
SUPPRESS_BELOW = 3  # small counts hidden in aggregate views to protect individuals


def can_search(user):
    if not user.is_authenticated:
        return False
    if user.has_role("workforce_officer"):
        return True
    return user.memberships.filter(role="admin", institution__kind__in=["federation", "state_council", "employer", "nis"]).exists()


def directory(filters):
    qs = User.objects.filter(is_active=True, workforce_profile__listed=True).select_related("workforce_profile").prefetch_related("professions", "sports")
    if filters.get("profession"):
        qs = qs.filter(professions__slug=filters["profession"])
    if filters.get("sport"):
        qs = qs.filter(Q(sports__slug=filters["sport"]) | Q(experience__sport__slug=filters["sport"]))
    if filters.get("state"):
        qs = qs.filter(Q(state=filters["state"]) | Q(workforce_profile__preferred_states__icontains=filters["state"]))
    if filters.get("credential"):
        qs = qs.filter(credentials__credential_type__code=filters["credential"], credentials__status="active")
    if filters.get("level"):
        qs = qs.filter(workforce_profile__experience_levels__icontains=filters["level"])
    if filters.get("available"):
        qs = qs.exclude(workforce_profile__availability="not_looking")
    if filters.get("verified"):
        qs = qs.filter(is_verified_professional=True)
    return qs.distinct()


def skills_map(profession=None, sport=None, credential=None):
    """Per state: registered professionals, those holding a valid credential (of the chosen type), and the gap."""
    base = User.objects.filter(is_active=True, staff_roles=[])
    if profession:
        base = base.filter(professions__slug=profession)
    if sport:
        base = base.filter(Q(sports__slug=sport) | Q(experience__sport__slug=sport))
    cred_q = Q(credentials__status="active")
    if credential:
        cred_q &= Q(credentials__credential_type__code=credential)
    totals = dict(base.exclude(state="").values("state").annotate(n=Count("pk", distinct=True)).values_list("state", "n"))
    qualified = dict(base.filter(cred_q).exclude(state="").values("state").annotate(n=Count("pk", distinct=True)).values_list("state", "n"))
    peak = max(qualified.values() or [1]) or 1
    cells = []
    for st in NIGERIAN_STATES:
        t, q = totals.get(st, 0), qualified.get(st, 0)
        hidden = 0 < t < SUPPRESS_BELOW
        # A small qualified group, or a small unqualified remainder, would identify individuals: hide both and the rate.
        split_hidden = hidden or 0 < q < SUPPRESS_BELOW or 0 < t - q < SUPPRESS_BELOW
        row, col = TILES[st]
        cells.append({"state": st, "row": row + 1, "col": col + 1, "total": None if hidden else t,
                      "qualified": None if split_hidden else q,
                      "rate": None if split_hidden or not t else round(100 * q / t),
                      "shade": 0 if split_hidden else round(100 * q / peak)})
    gaps = sorted([c for c in cells if c["rate"] is not None], key=lambda c: (c["rate"], -c["total"]))[:8]
    return cells, gaps, sum(totals.values()), sum(qualified.values())
