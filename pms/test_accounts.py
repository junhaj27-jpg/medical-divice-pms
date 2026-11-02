import base64
from datetime import timedelta
from django.contrib.auth.models import User
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from .accounts import issue_credential, safe_destination
from .models import Profile, AuditLog


@override_settings(LOGIN_ATTEMPT_LIMIT=100)
class AccountLifecycleTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user('admin', password='Existing!Pass2026')
        Profile.objects.create(user=self.admin, role='ADMIN')
        self.user = User.objects.create_user('staff', password='Existing!Pass2026')
        self.profile = Profile.objects.create(user=self.user)

    def login(self, client=None, username='staff', password='Existing!Pass2026', **extra):
        return (client or self.client).post(reverse('login'), {'username': username, 'password': password, **extra})

    def test_legacy_accounts_and_destination(self):
        for username, role in [('staff', 'STAFF'), ('admin', 'ADMIN'), ('raqa', 'RA_QA')]:
            if username == 'raqa':
                user = User.objects.create_user(username, password='Existing!Pass2026')
                Profile.objects.create(user=user, role=role)
            c = Client()
            self.assertRedirects(self.login(c, username=username, next='https://evil.test'), '/', fetch_redirect_response=False)
            self.assertRedirects(c.get('/accounts/login/?next=/users/'), '/', fetch_redirect_response=False)
        for target in ['//evil.test', '/\\evil.test', '/accounts/login/', 'https://evil.test', '/accounts/logout/']:
            self.assertEqual(safe_destination(target), '/')

    def test_generic_failure_and_no_password_echo(self):
        a = self.login(password='SECRET-bad')
        b = self.login(username='missing', password='SECRET-bad')
        self.user.is_active = False
        self.user.save()
        c = self.login()
        for response in (a, b, c):
            self.assertContains(response, '사원번호 또는 비밀번호를 확인하세요.')
            self.assertNotContains(response, 'SECRET-bad')
            self.assertIn('no-store', response['Cache-Control'])

    @override_settings(LOGIN_ATTEMPT_LIMIT=2)
    def test_rate_limit_and_audit(self):
        self.login(password='wrong')
        self.login(password='wrong')
        self.assertEqual(self.login().status_code, 429)
        self.assertTrue(AuditLog.objects.filter(action='LOGIN_FAILED').exists())

    def test_issue_leading_zero_one_time_and_audit(self):
        self.client.force_login(self.admin)
        response = self.client.post('/users/', {'username': '001007', 'name': '테스터', 'department': '품질', 'position': '담당', 'role': 'STAFF', 'is_active': 'on'})
        temporary = response.context['temporary']
        user = User.objects.get(username='001007')
        self.assertTrue(user.check_password(temporary))
        self.assertNotEqual(user.password, temporary)
        self.assertTrue(user.profile.must_change_password)
        self.assertEqual(user.profile.department, '품질')
        self.assertIsNone(self.client.get('/users/').context['temporary'])
        self.assertNotIn(temporary, str(list(AuditLog.objects.values())))
        c = Client()
        self.assertEqual(self.login(c, username='001007', password=temporary).status_code, 302)

    def test_only_admin_and_self_lock(self):
        self.client.force_login(self.user)
        for path in ['/users/', f'/users/{self.profile.pk}/update/', f'/users/{self.profile.pk}/reset/']:
            self.assertEqual(self.client.post(path, {}).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.post(f'/users/{self.admin.profile.pk}/update/', {'role': 'STAFF'}).status_code, 400)
        self.admin.refresh_from_db()
        self.assertTrue(self.admin.is_active)
        self.assertEqual(self.admin.profile.role, 'ADMIN')

    def test_gate_change_expiry_and_basic_api(self):
        temporary = issue_credential(self.user, self.profile)
        self.login(password=temporary, next='/complaints/')
        for path in ['/', '/complaints/', '/admin/', '/admin/auth/user/']:
            self.assertRedirects(self.client.get(path), '/accounts/password-change/', fetch_redirect_response=False)
        response = self.client.get('/api/complaints/')
        self.assertEqual(response.json()['error']['code'], 'password_change_required')
        basic = Client().get('/api/complaints/', HTTP_AUTHORIZATION='Basic ' + base64.b64encode(f'staff:{temporary}'.encode()).decode())
        self.assertEqual(basic.status_code, 403)
        self.assertEqual(basic.json()['error']['code'], 'password_change_required')
        weak = self.client.post('/accounts/password-change/', {'old_password': temporary, 'new_password1': '123', 'new_password2': '123'})
        self.assertEqual(weak.status_code, 200)
        response = self.client.post('/accounts/password-change/', {'old_password': temporary, 'new_password1': 'Unique!Changed2026', 'new_password2': 'Unique!Changed2026'})
        self.assertEqual(response.status_code, 302)
        self.profile.refresh_from_db()
        self.assertFalse(self.profile.must_change_password)
        self.assertIsNone(self.profile.temporary_password_expires_at)
        self.assertEqual(self.client.get('/').status_code, 200)
        issue_credential(self.user, self.profile)
        self.profile.temporary_password_expires_at = timezone.now() - timedelta(seconds=1)
        self.profile.save()
        self.client.force_login(self.user)
        response = self.client.get('/api/complaints/')
        self.assertEqual(response.json()['error']['code'], 'temporary_password_expired')
        self.assertContains(self.client.get('/accounts/password-change/'), '만료되었습니다')
        self.user.refresh_from_db()
        old_hash = self.user.password
        self.client.post('/accounts/password-change/', {'old_password': 'wrong', 'new_password1': 'Unique!Changed2027', 'new_password2': 'Unique!Changed2027'})
        self.user.refresh_from_db()
        self.assertEqual(self.user.password, old_hash)

    def test_reset_invalidates_old_session_and_needs_reason(self):
        old = Client()
        self.login(old)
        self.client.force_login(self.admin)
        url = f'/users/{self.profile.pk}/reset/'
        self.assertEqual(self.client.post(url, {}).status_code, 400)
        response = self.client.post(url, {'reason': '사용자 요청'})
        temporary = response.context['temporary']
        self.assertEqual(old.get('/').status_code, 302)
        self.assertNotIn('_auth_user_id', old.session)
        self.assertNotIn(temporary, str(list(AuditLog.objects.values())))
        self.assertNotIn(temporary, str(dict(self.client.session)))
        again = self.client.post(url, {'reason': '재발급 요청'}).context['temporary']
        self.assertNotEqual(temporary, again)
        self.user.refresh_from_db()
        self.assertFalse(self.user.check_password(temporary))
        self.assertTrue(self.user.check_password(again))

    def test_logout_post_csrf_and_admin_bypass(self):
        c = Client(enforce_csrf_checks=True)
        c.force_login(self.user)
        self.assertEqual(c.get('/accounts/logout/').status_code, 405)
        self.assertEqual(c.post('/accounts/logout/').status_code, 403)
        c.get('/accounts/password-change/')
        token = c.cookies['csrftoken'].value
        self.assertEqual(c.post('/accounts/logout/', HTTP_X_CSRFTOKEN=token).status_code, 302)
        self.assertNotIn('_auth_user_id', c.session)
        self.admin.is_staff = True
        self.admin.is_superuser = True
        self.admin.save()
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get('/admin/auth/user/').status_code, 404)
        self.assertEqual(self.client.get('/admin/pms/profile/').status_code, 404)
