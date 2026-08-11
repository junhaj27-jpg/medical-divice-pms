from rest_framework.permissions import BasePermission, SAFE_METHODS
from .models import Profile
from .services import role
class IsRAQAOrAdmin(BasePermission):
    def has_permission(self,request,view): return request.user.is_authenticated and role(request.user) in (Profile.Role.RA_QA,Profile.Role.ADMIN)
class IsAdminRole(BasePermission):
    def has_permission(self,request,view): return request.user.is_authenticated and role(request.user)==Profile.Role.ADMIN
class RoleWritePermission(BasePermission):
    def has_permission(self,request,view):
        if request.method in SAFE_METHODS: return request.user.is_authenticated
        return request.user.is_authenticated and role(request.user) in (Profile.Role.RA_QA,Profile.Role.ADMIN)
