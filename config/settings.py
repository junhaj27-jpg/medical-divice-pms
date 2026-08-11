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
REST_FRAMEWORK={"DEFAULT_AUTHENTICATION_CLASSES":["rest_framework.authentication.SessionAuthentication","rest_framework.authentication.BasicAuthentication"],"DEFAULT_PERMISSION_CLASSES":["rest_framework.permissions.IsAuthenticategmüçkh‘éì¶»§q«^v%$T¤T5DTB"¢FVbFW7EöVF—E÷&VF7G5÷6Vç6—F—fR‡6VÆb“ ¢ÆösÖVF—B‡6VÆbç7FfbÂ%UDDR"Ç6VÆbæBÆgFW#×²'77v÷&B#¢'6V7&WB"Â&æÖR#¢&ö²'Ò“²6VÆbæ76W'Dæ÷D–â‚'77v÷&B"ÆÆörægFW"“²6VÆbæ76W'DWVÂ†ÆörægFW%²&æÖR%ÒÂ&ö²"¢FVbFW7EöGF6†ÖVçE÷fÆ–FF–öâ‡6VÆb“ ¢3×6VÆbæ6ö×Æ–çB‚“²&CÔGF6†ÖVçB†6ö×Æ–çCÖ2Æf–ÆSÕ6–×ÆUWÆöFVDf–ÆR‚&&BæW†R"Æ"'‚"’ÇWÆöFVEö'“×6VÆbç7Ffb“²6VÆbæ76W'E&—6W2…fÆ–FF–öäW'&÷"Æ&BægVÆÅö6ÆVâ¢FVbFW7E÷F–VçEöæöç–Ö÷W5ööæÇ’‡6VÆb“ ¢ÕF–VçDæöç–Ö÷W4–æfò†6ö×Æ–çC×6VÆbæ6ö×Æ–çB‚’Ææöç–Ö÷W5ö6öFSÒ$äôâÓ"Ææ÷FW3Ò.ÊNÙ™BÊÉêR"“²6VÆbæ76W'E&—6W2…fÆ–FF–öäW'&÷"ÇægVÆÅö6ÆVâ¦6Æ72vV$•FW7G2„&6R“ ¢FVbFW7EöÆöv–åöæE÷&öÆU÷vW2‡6VÆb“ ¢6VÆbæ6Æ–VçBæÆöv–â‡W6W&æÖSÒ'7Ffb"Ç77v÷&CÒ'FW7B×77v÷&BÓ#2"“²6VÆbæ76W'DWVÂ‡6VÆbæ6Æ–VçBævWB‡&WfW'6R‚&F6†&ö&B"’’ç7FGW5ö6öFRÃ#“²6VÆbæ76W'DWVÂ‡6VÆbæ6Æ–VçBævWB‡&WfW'6R‚&VF—BÖÆ—7B"’’ç7FGW5ö6öFRÃC2¢FVbFW7Eö÷F†W%÷W6W'5ö66Uö†–FFVâ‡6VÆb“ ¢3×6VÆbæ6ö×Æ–çB‡6VÆbæ÷F†W"“²6VÆbæ6Æ–VçBæÆöv–â‡W6W&æÖSÒ'7Ffb"Ç77v÷&CÒ'FW7B×77v÷&BÓ#2"“²6VÆbæ76W'DWVÂ‡6VÆbæ6Æ–VçBævWB‡&WfW'6R‚&6ö×Æ–çBÖFWF–Â"Æ&w3Õ¶2çµÒ’’ç7FGW5ö6öFRÃCB¢FVbFW7Eö•öWF…öf–ÇW&R‡6VÆb“¢6VÆbæ76W'D–â„”6Æ–VçB‚’ævWB‚"ö’ö6ö×Æ–çG2ò"’ç7FGW5ö6öFRÂƒCÃC2’¢FVbFW7E÷7Ffeö•ö7&VFUöæE÷66÷–ær‡6VÆb“ ¢f÷&V–vã×6VÆbæ6ö×Æ–çB‡6VÆbæ÷F†W"“²“Ô”6Æ–VçB‚“²’æÆöv–â‡W6W&æÖSÒ'7Ffb"Ç77v÷&CÒ'FW7B×77v÷&BÓ#2"“²&W7öç6SÖ’ævWB‚"ö’ö6ö×Æ–çG2ò"“²6VÆbæ76W'Dæ÷D6öçF–ç2‡&W7öç6RÇ7G"†f÷&V–vâç²’