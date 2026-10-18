import csv
import io
import secrets

from django.contrib import messages
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.models import NIGERIAN_STATES, User
from apps.accounts.roles import STAFF_ROLES
from apps.accounts.views import clear_lockout
from apps.catalog.models import Course, Profession
from apps.core.audit import audit
from apps.core.models import AuditLog
from apps.credentials.models import MandatoryRequirement
from apps.institutions.models import Institution, Membership, institutions_admined_by
from apps.learning import services as learning
from apps.learning.models import Nomination
from apps.notifications.services import notify, send_email

from ..decorators import staff_required
from ..forms import InstitutionForm, UserAdminForm


@staff_required("nis_admin")
def users(request):
    qs = User.objects.annotate(n_enrol=Count("enrolments", distinct=True)).prefetch_related("professions")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q) | Q(phone__icontains=q))
    kind = request.GET.get("kind")
    if kind == "staff":
        qs = qs.exclude(staff_roles=[])
    elif kind == "learners":
        qs = qs.filter(staff_roles=[])
    elif kind == "inactive":
        qs = qs.filter(is_active=False)
    elif kind == "unverified":
        qs = qs.filter(is_verified_professional=False, staff_roles=[])
    if request.GET.get("state"):
        qs = qs.filter(state=request.GET["state"])
    if request.GET.get("profession"):
        qs = qs.filter(professions__slug=request.GET["profession"])
    page = Paginator(qs.order_by("-date_joined"), 25).get_page(request.GET.get("page"))
    return render(request, "manage/users/list.html", {"page": page, "q": q, "kind": kind, "states": NIGERIAN_STATES,
                                                      "professions": Profession.objects.all()})


@staff_required("nis_admin")
def users_import(request):
    """Bulk-create learner accounts from CSV: email, first_name, last_name, phone, state, profession, institution."""
    results = None
    if request.method == "POST" and request.FILES.get("file"):
        text = request.FILES["file"].read().decode("utf-8-sig", errors="replace")
        reader = csv.DictReader(io.StringIO(text))
        headers = {h.strip().lower().replace(" ", "_"): h for h in (reader.fieldnames or [])}
        results = {"created": 0, "existing": 0, "errors": []}
        for i, raw in enumerate(reader, start=2):
            row = {k: (raw.get(orig) or "").strip() for k, orig in headers.items()}
            email = row.get("email", "").lower()
            if "@" not in email:
                results["errors"].append(f"Row {i}: missing or invalid email")
                continue
            user = User.objects.filter(email__iexact=email).first()
            if user:
                results["existing"] += 1
            else:
                user = User.objects.create_user(email=email, password=secrets.token_urlsafe(16),
                                                first_name=row.get("first_name", ""), last_name=row.get("last_name", ""),
                                                phone=row.get("phone", ""),
                                                state=row.get("state", "") if row.get("state") in NIGERIAN_STATES else "")
                results["created"] += 1
                send_email(email, "Your SportIQ account is ready",
                           f"Hello {user.first_name},\n\nAn account was created for you on SportIQ, the NIS Digital Sports "
                           f"Academy. Set your password here: {request.build_absolute_uri('/account/password-reset/')}")
            if row.get("profession"):
                prof = Profession.objects.filter(Q(name__iexact=row["profession"]) | Q(slug=row["profession"].lower())).first()
                if prof:
                    user.professions.add(prof)
            if row.get("institution"):
                inst = Institution.objects.filter(name__iexact=row["institution"]).first()
                if inst:
                    Membership.objects.get_or_create(user=user, institution=inst, defaults={"role": "member"})
        audit(request.user, "users.imported", None, {k: v for k, v in results.items() if k != "errors"}, request)
        messages.success(request, f"Import finished: {results['created']} created, {results['existing']} already existed.")
    return render(request, "manage/users/import.html", {"results": results})


@staff_required("nis_admin")
def user_detail(request, pk):
    person = get_object_or_404(User, pk=pk)
    # Captured before is_valid(), which copies the submitted values onto `person`.
    before = {"roles": list(person.staff_roles), "active": person.is_active}
    form = UserAdminForm(request.POST or None, instance=person, initial={"staff_roles": person.staff_roles})
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "save" and form.is_valid():
            new_roles = form.cleaned_data["staff_roles"]
            if "super_admin" in new_roles and not request.user.has_role("super_admin"):
                messages.error(request, "Only a super administrator can grant super-admin.")
                return redirect("backoffice:user_detail", pk=pk)
            p = form.save(commit=False)
            p.staff_roles = new_roles
            p.is_staff = bool(new_roles)
            p.save()
            audit(request.user, "user.updated", p, {"before": before, "after": {"roles": p.staff_roles, "active": p.is_active}}, request)
            messages.success(request, "User updated.")
        elif action == "set_password":
            # Admin-assisted reset while self-service reset by email is switched off.
            pw1, pw2 = request.POST.get("new_password1", ""), request.POST.get("new_password2", "")
            try:
                if pw1 != pw2:
                    raise ValidationError("The two passwords don't match.")
                validate_password(pw1, person)
            except ValidationError as exc:
                messages.error(request, " ".join(exc.messages))
                return redirect("backoffice:user_detail", pk=pk)
            person.set_password(pw1)
            person.save(update_fields=["password"])
            clear_lockout(person.email)
            audit(request.user, "user.password_set_by_admin", person, request=request)
            messages.success(request, "New password set. Give it to the user privately; they can change it "
                                      "under Account settings after logging in.")
        elif action == "membership" and request.POST.get("institution"):
            inst = get_object_or_404(Institution, pk=request.POST["institution"])
            m, _ = Membership.objects.update_or_create(user=person, institution=inst,
                                                       defaults={"role": request.POST.get("role", "member"), "is_verified": True})
            audit(request.user, "membership.set", m, {"role": m.role}, request)
            messages.success(request, f"Linked to {inst.name} as {m.get_role_display().lower()}.")
        elif action == "remove_membership":
            Membership.objects.filter(pk=request.POST.get("membership"), user=person).delete()
            messages.success(request, "Membership removed.")
        elif action == "registry":
            from apps.integrations.registry import FederationRegistry

            result = FederationRegistry().lookup(person, request.user, request.POST.get("registration_number", ""))
            messages.info(request, f"Federation registry: {result['status']}. {result.get('detail', '')}")
        elif action == "enrol" and request.POST.get("course"):
            course = get_object_or_404(Course, pk=request.POST["course"])
            learning.enrol(person, course, source="admin")
            audit(request.user, "enrolment.admin_created", person, {"course": course.title}, request)
            messages.success(request, f"Enrolled in {course.title}.")
        return redirect("backoffice:user_detail", pk=pk)
    return render(request, "manage/users/detail.html", {
        "person": person, "form": form, "roles": STAFF_ROLES,
        "enrolments": person.enrolments.select_related("course"),
        "credentials": person.credentials.select_related("credential_type"),
        "memberships": person.memberships.select_related("institution"),
        "institutions": Institution.objects.filter(is_active=True), "courses": Course.objects.published(),
        "activity": AuditLog.objects.filter(Q(actor=person) | Q(object_type="accounts.User", object_id=str(person.pk)))[:15],
        "tickets": person.tickets.all()[:5], "orders": person.orders.select_related("course")[:5],
    })


@staff_required("nis_admin")
def institutions(request):
    form = InstitutionForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        inst = form.save()
        audit(request.user, "institution.created", inst, request=request)
        messages.success(request, f"{inst.name} created. Link an administrator from their user page or below.")
        return redirect("backoffice:institution_edit", pk=inst.pk)
    qs = Institution.objects.annotate(n=Count("memberships"))
    if request.GET.get("kind"):
        qs = qs.filter(kind=request.GET["kind"])
    return render(request, "manage/institutions/list.html", {"institutions": qs, "form": form, "kinds": Institution.KINDS})


@staff_required("nis_admin")
def institution_edit(request, pk):
    inst = get_object_or_404(Institution, pk=pk)
    form = InstitutionForm(request.POST or None, request.FILES or None, instance=inst)
    if request.method == "POST":
        if request.POST.get("action") == "add_member":
            user = User.objects.filter(email__iexact=request.POST.get("email", "").strip()).first()
            if not user:
                messages.error(request, "No account with that email.")
            else:
                Membership.objects.update_or_create(user=user, institution=inst,
                                                    defaults={"role": request.POST.get("role", "member"), "is_verified": True})
                audit(request.user, "membership.set", inst, {"user": user.email, "role": request.POST.get("role")}, request)
                messages.success(request, f"{user} added.")
            return redirect("backoffice:institution_edit", pk=pk)
        if form.is_valid():
            form.save()
            audit(request.user, "institution.updated", inst, {"fields": form.changed_data}, request)
            messages.success(request, "Institution saved.")
            return redirect("backoffice:institution_edit", pk=pk)
    return render(request, "manage/institutions/edit.html", {
        "inst": inst, "form": form, "members": inst.memberships.select_related("user"), "roles": Membership.ROLES,
    })


# --- Institution-admin portal (scoped: only their own members) --------------------------

def _org_for(request, slug):
    if request.user.has_role("nis_admin"):
        return get_object_or_404(Institution, slug=slug)
    inst = institutions_admined_by(request.user).filter(slug=slug).first()
    if not inst:
        raise Http404
    return inst


@staff_required()
def org(request, slug):
    inst = _org_for(request, slug)
    members = User.objects.filter(memberships__institution=inst).distinct()
    if request.method == "POST":
        action = request.POST.get("action")
        if action == "nominate":
            course = get_object_or_404(Course.objects.published(), pk=request.POST.get("course"))
            ids = request.POST.getlist("members")
            due = request.POST.get("due_date") or None
            count = 0
            for user in members.filter(pk__in=ids):
                Nomination.objects.get_or_create(institution=inst, user=user, course=course,
                                                 defaults={"nominated_by": request.user, "due_date": due, "status": "enrolled"})
                if course.is_free:
                    learning.enrol(user, course, source="nominated", due_date=due)
                notify(user, f"{inst.name} nominated you", f"Course: {course.title}", course.get_absolute_url())
                count += 1
            audit(request.user, "nomination.created", inst, {"course": course.title, "count": count}, request)
            messages.success(request, f"Nominated {count} member(s) for {course.title}."
                             + ("" if course.is_free else " Paid course: members will need a sponsor code to enrol."))
        elif action == "invite":
            email = request.POST.get("email", "").strip().lower()
            user = User.objects.filter(email__iexact=email).first()
            if user:
                Membership.objects.get_or_create(user=user, institution=inst, defaults={"role": "member", "is_verified": True})
                notify(user, f"You've been added to {inst.name}", "", "/account/profile/")
                messages.success(request, f"{user} added to {inst.name}.")
            elif "@" in email:
                from apps.institutions.models import Invitation

                Invitation.objects.create(institution=inst, email=email, invited_by=request.user)
                send_email(email, f"{inst.name} invites you to SportIQ",
                           f"Create your free account at {request.build_absolute_uri('/account/signup/')} using this email "
                           f"address and you'll be linked to {inst.name}.")
                messages.success(request, f"Invitation sent to {email}.")
        return redirect("backoffice:org", slug=slug)
    rows = []
    required = MandatoryRequirement.objects.select_related("course", "profession")
    for m in members.prefetch_related("professions", "enrolments__course", "credentials"):
        enrolments = list(m.enrolments.all())
        done_ids = {e.course_id for e in enrolments if e.status == "completed"}
        prof_ids = {p.pk for p in m.professions.all()}
        missing = [r.course.title for r in required if r.profession_id in prof_ids and r.course_id not in done_ids]
        rows.append({"user": m, "active": sum(e.status == "active" for e in enrolments), "completed": len(done_ids),
                     "credentials": sum(1 for c in m.credentials.all() if c.is_valid), "missing": missing})
    total = len(rows)
    return render(request, "manage/org.html", {
        "inst": inst, "rows": rows, "courses": Course.objects.published(),
        "nominations": inst.nominations.select_related("user", "course")[:20],
        "summary": {"members": total, "compliant": sum(1 for r in rows if not r["missing"]),
                    "completions": sum(r["completed"] for r in rows), "credentials": sum(r["credentials"] for r in rows)},
    })


@staff_required()
def org_member(request, slug, user_id):
    inst = _org_for(request, slug)
    member = get_object_or_404(User, pk=user_id, memberships__institution=inst)
    audit(request.user, "org.member_viewed", member, {"institution": inst.slug}, request)
    return render(request, "manage/org_member.html", {
        "inst": inst, "member": member, "enrolments": member.enrolments.select_related("course"),
        "credentials": member.credentials.select_related("credential_type"),
    })
