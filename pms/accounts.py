"""PMS-local account lifecycle; credentials never enter sessions or audit payloads."""
import secrets
from datetime import timedelta
from urllib.parse import urlsplit
from django import forms
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.models import User
from django.contrib.auth.views import LoginView, LogoutView
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.cache import add_never_cache_headers
from django.views.decorators.debug import sensitive_post_parameters
from django.views.decorators.http import require_POST
from .models import Profile
from .services import audit, role


def safe_destination(value):
    value = value or ''
    try:
        parts = urlsplit(value)
    except ValueError:
        return reverse("dashboard")
    if (not value.startswith('/') or value.startswith('//') or '\\' in value
            or parts.scheme or parts.netloc or any(ord(c) < 32 for c in value)
            or parts.path.startswith(('/accounts/', '/admin/login', '/admin/logout'))):
        return reverse('dashboard')
    return value


class EmployeeAuthenticationForm(AuthenticationForm):
    username = forms.CharField(label='사원번호 / 기존 아이디', max_length=150,
        widget=forms.TextInput(attrs={'autocomplete': 'username', 'autofocus': True}))
    error_messages = {**AuthenticationForm.error_messages,
        'invalid_login': '사원번호 또는 비밀번호를 확인하세요.',
        'inactive': '사원번호 또는 비밀번호를 확인하세요.'}


class EmployeeLoginView(LoginView):
    authentication_form = EmployeeAuthenticationForm
    redirect_authenticated_user = True

    def get_success_url(self):
        if self.request.method == "GET" and self.request.user.is_authenticated:
            return reverse("dashboard")
        return safe_destination(self.request.POST.get('next') or self.request.GET.get('next'))

    def get_redirect_url(self):
        return self.get_success_url()


class EmployeeLogoutView(LogoutView):
    http_method_names = ['post', 'options']


def credential_state(user):
    profile = getattr(user, 'profile', None)
    if profile and profile.must_change_password:
        if not profile.temporary_password_expires_at or profile.temporary_password_expires_at <= timezone.now():
            return 'temporary_password_expired'
        return 'password_change_required'
    return None


class AccountGateMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        state = credential_state(request.user) if request.user.is_authenticated else None
        allowed = {reverse('password-change'), reverse('logout'), reverse('login')}
        if state and request.path not in allowed:
            if request.path.startswith('/api/'):
                response = JsonResponse({'success': False, 'error': {'code': state}}, status=403)
            else:
                request.session['password_change_next'] = safe_destination(request.get_full_path())
                response = redirect('password-change')
        else:
            response = self.get_response(request)
        if request.user.is_authenticated or request.path.startswith(('/accounts/', '/users/', '/admin/', '/api/')):
            add_never_cache_headers(response)
        return response


@sensitive_post_parameters()
@login_required
def password_change(request):
    state = credential_state(request.user)
    expired = state == 'temporary_password_expired'
    form = PasswordChangeForm(request.user, request.POST if request.method == 'POST' else None)
    if request.method == 'POST' and not expired and form.is_valid():
        if form.cleaned_data['old_password'] == form.cleaned_data['new_password1']:
            form.add_error('new_password1', '현재 비밀번호와 다른 비밀번호를 입력하세요.')
        else:
            with transaction.atomic():
                User.objects.select_for_update().get(pk=request.user.pk)
                # A concurrent administrator reset must not be overwritten.
                current = User.objects.get(pk=request.user.pk)
                if credential_state(current) == 'temporary_password_expired':
                    form.add_error(None, '임시 비밀번호가 만료되었습니다. 관리자에게 초기화를 요청하세요.')
                elif not current.check_password(form.cleaned_data['old_password']):
                    form.add_error('old_password', '현재 비밀번호를 다시 확인하세요.')
                else:
                    form.save()
                    Profile.objects.filter(user=request.user).update(must_change_password=False, temporary_password_expires_at=None)
                    audit(request.user, 'CREDENTIAL_CHANGED', request.user)
                    update_session_auth_hash(request, request.user)
                    return redirect(safe_destination(request.session.pop('password_change_next', '')))
    return render(request, 'registration/password_change.html', {'form': form, 'expired': expired, 'required': bool(state)})


class AccountForm(forms.Form):
    username = forms.RegexField(r'^[0-9]+$', label='사원번호', max_length=150,
        widget=forms.TextInput(attrs={'autocomplete': 'off'}))
    name = forms.CharField(label='이름', max_length=150)
    department = forms.CharField(label='부서', max_length=120, required=False)
    position = forms.CharField(label='직책', max_length=120, required=False)
    role = forms.ChoiceField(label='역할', choices=Profile.Role.choices)
    is_active = forms.BooleanField(label='활성', required=False, initial=True)


def issue_credential(user, profile):
    temporary = secrets.token_urlsafe(24)
    user.set_password(temporary)
    user.save(update_fields=['password'])
    profile.must_change_password = True
    profile.temporary_password_expires_at = timezone.now() + timedelta(hours=24)
    profile.save()
    return temporary


@login_required
def users(request):
    if role(request.user) != 'ADMIN':
        raise PermissionDenied
    form = AccountForm(request.POST if request.method == 'POST' else None)
    temporary = None
    if request.method == 'POST' and form.is_valid():
        data = form.cleaned_data
        if User.objects.filter(username=data['username']).exists():
            form.add_error('username', '이미 사용 중인 사원번호입니다.')
        else:
            with transaction.atomic():
                user = User.objects.create_user(username=data['username'], first_name=data['name'], is_active=data['is_active'])
                profile = Profile.objects.create(user=user, role=data['role'], department=data['department'], position=data['position'])
                temporary = issue_credential(user, profile)
                audit(request.user, 'ACCOUNT_ISSUED', user, after={'role': profile.role, 'active': user.is_active})
    return render(request, 'pms/users.html', {'form': form, 'items': Profile.objects.select_related('user'), 'temporary': temporary})


@login_required
@require_POST
@transaction.atomic
def user_update(request, pk):
    if role(request.user) != 'ADMIN':
        raise PermissionDenied
    # Serialize account administration, including competing last-admin removals.
    list(User.objects.select_for_update().order_by('pk').values_list('pk', flat=True))
    profile = get_object_or_404(Profile.objects.select_related('user'), pk=pk)
    user = profile.user
    requested = request.POST.get('role')
    active = request.POST.get('is_active') == 'on'
    removing = not active or (requested != 'ADMIN' and not user.is_superuser)
    admins = User.objects.filter(is_active=True).filter(Q(is_superuser=True) | Q(profile__role='ADMIN')).distinct()
    self_lock = user.pk == request.user.pk and (not active or requested != 'ADMIN')
    if requested not in Profile.Role.values or self_lock or (removing and admins.filter(pk=user.pk).exists() and admins.count() <= 1):
        return render(request, 'pms/account_error.html', {'error': '자기 잠금 또는 마지막 활성 관리자 해제는 허용되지 않습니다.'}, status=400)
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError
    timezone_name = request.POST.get('timezone_name', profile.timezone_name)
    try:
        ZoneInfo(timezone_name)
    except (ZoneInfoNotFoundError, ValueError):
        return render(request, 'pms/account_error.html', {'error': '유효한 IANA 시간대를 입력하세요.'}, status=400)
    profile.timezone_name = timezone_name
    before = {'role': profile.role, 'active': user.is_active}
    profile.role = requested
    for field in ('department', 'position'):
        setattr(profile, field, request.POST.get(field, getattr(profile, field))[:120])
    user.first_name = request.POST.get('name', user.first_name)[:150]
    user.is_active = active
    user.save(update_fields=['first_name', 'is_active'])
    profile.save()
    audit(request.user, 'ACCOUNT_UPDATED', user, before=before, after={'role': requested, 'active': active})
    return redirect('user-list')


@sensitive_post_parameters()
@login_required
@require_POST
@transaction.atomic
def reset_credential(request, pk):
    if role(request.user) != 'ADMIN':
        raise PermissionDenied
    user = get_object_or_404(User.objects.select_for_update(), profile__pk=pk)
    if user.pk == request.user.pk:
        return render(request, 'pms/account_error.html', {'error': '본인 비밀번호는 비밀번호 변경 메뉴에서 변경하세요.'}, status=400)
    reason = request.POST.get('reason', '').strip()
    if not reason or len(reason) > 500:
        return render(request, 'pms/account_error.html', {'error': '초기화 사유를 500자 이내로 입력하세요.'}, status=400)
    temporary = issue_credential(user, user.profile)
    # Reason is stored separately; never submit credentials in this field.
    audit(request.user, 'CREDENTIAL_RESET', user, after={'reason': reason})
    return render(request, 'pms/credential_issued.html', {'temporary': temporary})
