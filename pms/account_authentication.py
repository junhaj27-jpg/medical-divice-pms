from rest_framework.authentication import BasicAuthentication, SessionAuthentication
from rest_framework.exceptions import PermissionDenied
from .accounts import credential_state


class CredentialGateMixin:
    def authenticate(self, request):
        result = super().authenticate(request)
        if result:
            state = credential_state(result[0])
            if state:
                raise PermissionDenied('비밀번호 변경 또는 관리자 초기화가 필요합니다.', code=state)
        return result


class GatedSessionAuthentication(CredentialGateMixin, SessionAuthentication):
    pass


class GatedBasicAuthentication(CredentialGateMixin, BasicAuthentication):
    pass
