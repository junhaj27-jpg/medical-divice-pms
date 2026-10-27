"""DB-backed shared account/IP counters, including Basic authentication."""
import base64
import hashlib
import math
from datetime import timedelta
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.http import HttpResponse
from django.utils import timezone
from .models import LoginBucket


class LoginRateLimitMiddleware:
    def __init__(self,get_response): self.get_response=get_response
    def __call__(self,request):
        username=None
        if request.method=="POST" and request.path.endswith("/login/"):
            username=request.POST.get("username","")
        elif request.headers.get("Authorization","").startswith("Basic "):
            try: username=base64.b64decode(request.headers["Authorization"][6:],validate=True).decode().split(":",1)[0]
            except (ValueError,UnicodeError): username="invalid-basic"
        if username is not None:
            now=timezone.now(); window=settings.LOGIN_WINDOW_SECONDS
            epoch=int(now.timestamp())//window
            keys=[hashlib.sha256(f"{kind}:{value}:{epoch}".encode()).hexdigest() for kind,value in (("account",username.strip().casefold()),("ip",request.META.get("REMOTE_ADDR","unknown")))]
            with transaction.atomic():
                # Atomic increments reserve attempts before authentication in every process.
                for key in sorted(keys):
                    bucket,_=LoginBucket.objects.get_or_create(key=key,defaults={"expires_at":now+timedelta(seconds=window*2)})
                    LoginBucket.objects.filter(pk=bucket.pk).update(count=F("count")+1)
                blocked=LoginBucket.objects.filter(key__in=keys,count__gt=settings.LOGIN_ATTEMPT_LIMIT).exists()
            if blocked:
                response=HttpResponse("로그인 시도가 너무 많습니다. 잠시 후 다시 시도하세요.",status=429)
                response["Retry-After"]=str(math.ceil(window-now.timestamp()%window)); return response
        return self.get_response(request)

class UserTimezoneMiddleware:
    def __init__(self,get_response): self.get_response=get_response
    def __call__(self,request):
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
        name=getattr(getattr(request.user,'profile',None),'timezone_name',settings.TIME_ZONE) if request.user.is_authenticated else settings.TIME_ZONE
        try: timezone.activate(ZoneInfo(name))
        except (ZoneInfoNotFoundError,ValueError): timezone.activate(ZoneInfo(settings.TIME_ZONE))
        try: return self.get_response(request)
        finally: timezone.deactivate()
