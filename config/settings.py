import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
SECRET_KEY = os.getenv("SECRET_KEY", "unsafe-development-only-change-me")
DEBUG = os.getenv("DEBUG", "False").lower() == "true"
ALLOWED_HOSTS = [x.strip() for x in os.getenv("ALLOWED_HOSTS", "localhost,127.0.0.1,testserver").split(",")]
INSTALLED_APPS = ["django.contrib.admin","django.contrib.auth","django.contrib.contenttypes","django.contrib.sessions","django.contrib.messages","django.contrib.staticfiles","rest_framework","django_filters","drf_spectacular","pms"]
MIDDLEWARE = ["django.middleware.security.SecurityMiddleware","django.contrib.sessions.middleware.SessionMiddleware","django.middleware.common.CommonMiddleware","django.middleware.csrf.CsrfViewMiddleware","django.contrib.auth.middleware.AuthenticationMiddleware","django.contrib.messages.middleware.MessageMiddleware","django.middleware.clickjacking.XFrameOptionsMiddleware","pms.middleware.AuditLoginMiddleware"]
ROOT_URLCONF = "config.urls"
TEMPLATES = [{"BACKEND":"django.template.backends.django.DjangoTemplates","DIRS":[BASE_DIR/"templates"],"APP_DIRS":True,"OPTIONS":{"context_processors":["django.template.context_processors.request","django.contrib.auth.context_processors.auth","django.contrib.messages.context_processors.messages"]}}]
WSGI_APPLICATION = "config.wsgi.application"
if os.getenv("DB_ENGINE") == "postgresql":
    DATABASES={"default":{"ENGINE":"django.db.backends.postgresql","NAME":os.getenv("DB_NAME","pms"),"USER":os.getenv("DB_USER","pms"),"PASSWORD":os.getenv("DB_PASSWORD","pms"),"HOST":os.getenv("DB_HOST","db"),"PORT":os.getenv("DB_PORT","5432")}}
else: DATABASES={"default":{"ENGINE":"django.db.backends.sqlite3","NAME":BASE_DIR/"db.sqlite3"}}
AUTH_PASSWORD_VALIDATORS=[{"NAME":"django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},{"NAME":"django.contrib.auth.password_validation.MinimumLengthValidator"},{"NAME":"django.contrib.auth.password_validation.CommonPasswordValidator"}]
LANGUAGE_CODE="ko-kr"; TIME_ZONE="Asia/Seoul"; USE_I18N=True; USE_TZ=True
STATIC_URL="static/"; STATIC_ROOT=BASE_DIR/"staticfiles"; STATICFILES_DIRS=[BASE_DIR/"static"]
MEDIA_URL="media/"; MEDIA_ROOT=BASE_DIR/"media"; DEFAULT_AUTO_FIELD="django.db.models.BigAutoField"
LOGIN_REDIRECT_URL="dashboard"; LOGOUT_REDIRECT_URL="login"
SESSION_COOKIE_SECURE=os.getenv("SECURE_COOKIES","False").lower()=="true"; CSRF_COOKIE_SECURE=SESSION_COOKIE_SECURE
SECURE_SSL_REDIRECT=os.getenv("SECURE_SSL_REDIRECT","False").lower()=="true"; X_FRAME_OPTIONS="DENY"
SECURE_HSTS_SECONDS=int(os.getenv("SECURE_HSTS_SECONDS","0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS=SECURE_HSTS_SECONDS>0
SECURE_HSTS_PRELOAD=os.getenv("SECURE_HSTS_PRELOAD","False").lower()=="true"
DATA_UPLOAD_MAX_MEMORY_SIZE=int(os.getenv("MAX_UPLOAD_BYTES","5242880")); FILE_UPLOAD_MAX_MEMORY_SIZE=DATA_UPLOAD_MAX_MEMORY_SIZE
REST_FRAMEWORK={"DEFAULT_AUTHENTICATION_CLASSES":["rest_framework.authentication.SessionAuthentication","rest_framework.authentication.BasicAuthentication"],"DEFAULT_PERMISSION_CLASSES":["rest_framework.permissions.IsAuthenticated"],"DEFAULT_PAGINATION_CLASS":"rest_framework.pagination.PageNumberPagination","PAGE_SIZE":20,"DEFAULT_FILTER_BACKENDS":["django_filters.rest_framework.DjangoFilterBackend","rest_framework.filters.SearchFilter","rest_framework.filters.OrderingFilter"],"DEFAULT_SCHEMA_CLASS":"drf_spectacular.openapi.AutoSchema","EXCEPTION_HANDLER":"pms.api.custom_exception_handler"}
SPECTACULAR_SETTINGS={"TITLE":"의료기기 PMS·리콜 API","DESCRIPTION":"포트폴리오용 데모 API","VERSION":"1.0.0"}
PMS_RULES={"LOT_WINDOW_DAYS":int(os.getenv("LOT_WINDOW_DAYS","30")),"LOT_THRESHOLD":int(os.getenv("LOT_THRESHOLD","3")),"DEVICE_WINDOW_DAYS":int(os.getenv("DEVICE_WINDOW_DAYS","90")),"DEVICE_THRESHOLD":int(os.getenv("DEVICE_THRESHOLD","5"))}
