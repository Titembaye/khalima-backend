from rest_framework.permissions import BasePermission


class IsAnnotator(BasePermission):
    def has_permission(self, request, view):
        profile = getattr(request.user, 'userprofile', None)
        return profile is not None and profile.role in ('annotator', 'reviewer', 'admin')


class IsReviewer(BasePermission):
    def has_permission(self, request, view):
        profile = getattr(request.user, 'userprofile', None)
        return profile is not None and profile.role in ('reviewer', 'admin')


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        profile = getattr(request.user, 'userprofile', None)
        return profile is not None and profile.role == 'admin'
