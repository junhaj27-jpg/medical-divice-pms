from drf_spectacular.authentication import BasicScheme
from rest_framework.authentication import BasicAuthentication
from rest_framework.exceptions import PermissionDenied

from .market_service import scoped


class WorkspaceBasicAuthentication(BasicAuthentication):
    def authenticate_credentials(self, userid, password, request=None):
        user, auth = super().authenticate_credentials(userid, password, request)
        if scoped(user):
            raise PermissionDenied("Use the market workspace.")
        return user, auth



class WorkspaceBasicScheme(BasicScheme):
    target_class = "pms.market_api.WorkspaceBasicAuthentication"
