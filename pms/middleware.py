from .services import audit
class AuditLoginMiddleware:
    def __init__(self,get_response): self.get_response=get_response
    def __call__(self,request):
        was=bool(request.user.is_authenticated) if hasattr(request,"user") else False; response=self.get_response(request)
        if request.path.endswith("/login/") and request.method=="POST": audit(request.user,"LOGIN_SUCCESS" if getattr(request.user,"is_authenticated",False) else "LOGIN_FAILED",ip=request.META.get("REMOTE_ADDR"))
        return response
