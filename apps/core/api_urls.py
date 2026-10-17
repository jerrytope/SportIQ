"""Public REST API (blueprint Module 19): documented at /api/docs/."""
from django.urls import include, path
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import extend_schema
from rest_framework import permissions, routers, serializers, viewsets
from rest_framework.decorators import api_view, permission_classes
from rest_framework.response import Response

from apps.catalog.models import Course
from apps.credentials.models import Credential
from apps.learning.models import Enrolment


class CourseSerializer(serializers.ModelSerializer):
    track = serializers.CharField(source="track.name")
    level = serializers.CharField(source="get_level_display")
    url = serializers.SerializerMethodField()

    class Meta:
        model = Course
        fields = ["slug", "code", "title", "summary", "track", "level", "language", "delivery_format",
                  "duration_hours", "price_kobo", "url"]

    def get_url(self, obj) -> str:
        return self.context["request"].build_absolute_uri(obj.get_absolute_url())


class CourseViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = CourseSerializer
    lookup_field = "slug"
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        return Course.objects.visible_to(self.request.user).select_related("track")


class EnrolmentSerializer(serializers.ModelSerializer):
    course = serializers.CharField(source="course.title")

    class Meta:
        model = Enrolment
        fields = ["course", "status", "progress", "created_at", "completed_at"]


class MyEnrolmentViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = EnrolmentSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        if getattr(self, "swagger_fake_view", False):  # schema generation
            return Enrolment.objects.none()
        return self.request.user.enrolments.select_related("course")


@extend_schema(responses=OpenApiTypes.OBJECT)
@api_view(["GET"])
@permission_classes([permissions.AllowAny])
def verify_credential(request, code):
    """Check a credential by its verification code."""
    cred = Credential.objects.select_related("credential_type").filter(code=code.upper()).first()
    if not cred:
        return Response({"found": False}, status=404)
    return Response({
        "found": True, "code": cred.code, "status": cred.effective_status, "holder": cred.holder_name,
        "title": cred.title, "type": cred.credential_type.name, "kind": cred.credential_type.kind,
        "issuer": cred.credential_type.issuer_name, "issued_at": cred.issued_at, "expires_at": cred.expires_at,
    })


router = routers.DefaultRouter()
router.register("courses", CourseViewSet, basename="api-course")
router.register("me/enrolments", MyEnrolmentViewSet, basename="api-enrolment")

urlpatterns = [
    path("v1/", include(router.urls)),
    path("v1/credentials/verify/<str:code>/", verify_credential, name="api-verify"),
]
