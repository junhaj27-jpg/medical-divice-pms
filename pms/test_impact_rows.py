from django.core import signing
from django.test import override_settings
from django.urls import reverse
from .tests import Base
from . import test_impact as fixtures
from .models import CustomerComplaint, RegulatoryImpact, Notification


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class ImpactRowTests(Base):
    def setUp(self):
        import uuid, shutil
        from pathlib import Path
        super().setUp()
        self.root=Path('.test-media')/uuid.uuid4().hex
        self.root.mkdir(parents=True);self.addCleanup(shutil.rmtree,self.root)
        media=override_settings(MEDIA_ROOT=self.root/'media');media.enable();self.addCleanup(media.disable)
        self.c=self.complaint();self.c.is_example=True;self.c.complaint_type='TEST_EVENT';self.c.save()
    document=fixtures.ImpactTests.document
    draft=fixtures.ImpactTests.draft
    pair=fixtures.ImpactTests.pair

    def post_data(self):
        old,new=self.pair();self.client.force_login(self.raqa)
        response=self.client.get(reverse('impact-list'))
        token=response.context['form'].initial['token']
        ids=[c.pk for c,_,_ in response.context['rows']]
        data={'old_rule':old.pk,'new_rule':new.pk,'token':token,'rows-TOTAL_FORMS':len(ids),'rows-INITIAL_FORMS':len(ids),'rows-MIN_NUM_FORMS':0,'rows-MAX_NUM_FORMS':20}
        for i,pk in enumerate(ids):
            data.update({f'rows-{i}-case_id':pk,f'rows-{i}-selected':'on',f'rows-{i}-jurisdiction':'TEST-REGION',f'rows-{i}-basis_at':f'{self.c.reported_on}T00:30:00+09:00',f'rows-{i}-reason':'공식 자료 확인'})
        return data

    def test_row_submission_utc_boundary_duplicate_and_stale(self):
        from .impact import stale_reason,process_review
        from django.core.exceptions import ValidationError
        data=self.post_data();before=(self.c.due_date,self.c.version)
        self.assertEqual(self.client.post(reverse('impact-list'),data).status_code,302)
        review=RegulatoryImpact.objects.get().reviews.get()
        self.assertTrue(review.snapshot['inputs']['basis_at'].endswith('+00:00'))
        self.assertEqual(review.snapshot['inputs']['reason'],'공식 자료 확인')
        self.c.refresh_from_db();self.assertEqual(before,(self.c.due_date,self.c.version))
        self.client.post(reverse('impact-list'),data)
        changed={**data,'rows-0-reason':'다른 확인 사유'}
        self.assertContains(self.client.post(reverse('impact-list'),changed),'이미 제출한 요청의 내용이 다릅니다')
        self.assertEqual(RegulatoryImpact.objects.count(),1);self.assertEqual(Notification.objects.filter(dedupe_key__startswith='impact:').count(),1)
        self.c.description='자료 정정';self.c.save()
        self.assertTrue(stale_reason(review,self.raqa))
        self.assertRaises(ValidationError,process_review,review,self.raqa,'EXCLUDED','검토')

    def test_missing_offset_reason_and_disallowed_case(self):
        data=self.post_data();data['rows-0-basis_at']=f'{self.c.reported_on}T10:00:00'
        response=self.client.post(reverse('impact-list'),data);self.assertContains(response,'UTC 오프셋')
        data['rows-0-basis_at']=f'{self.c.reported_on}T10:00:00+99:00'
        self.assertContains(self.client.post(reverse('impact-list'),data),'UTC 오프셋')
        data['rows-0-basis_at']='';data['rows-0-reason']=''
        self.assertContains(self.client.post(reverse('impact-list'),data),'필수 확인')
        data['rows-0-case_id']=999999
        self.assertContains(self.client.post(reverse('impact-list'),data),'허용되지 않은 사건')
        self.assertEqual(RegulatoryImpact.objects.count(),0)

    def test_bulk_requires_selection_and_confirmation(self):
        data=self.post_data();data.update(bulk_jurisdiction='TEST-REGION',bulk_basis_at=f'{self.c.reported_on}T10:00:00+09:00',bulk_reason='각 사건 근거 확인')
        self.assertContains(self.client.post(reverse('impact-list'),data),'명시적 확인이 필요')
        data['bulk_confirm']='on';data.pop('rows-0-selected')
        self.assertContains(self.client.post(reverse('impact-list'),data),'분석할 사건을 선택')
        data['rows-0-selected']='on';self.assertEqual(self.client.post(reverse('impact-list'),data).status_code,302)

    def test_search_filters_pagination_and_staff(self):
        self.client.force_login(self.raqa)
        for i in range(22): self.complaint(kind='TEST_EVENT')
        response=self.client.get(reverse('impact-list'),{'example':'0'})
        self.assertEqual(len(response.context['rows']),20)
        response=self.client.get(reverse('impact-list'),{'example':'0','page':2})
        self.assertEqual(len(response.context['rows']),2)
        self.assertContains(response,'example=0')
        response=self.client.get(reverse('impact-list'),{'q':f'CMP-{self.c.pk}','example':'1'})
        self.assertEqual(len(response.context['rows']),1)
        response=self.client.get(reverse('impact-list'),{'status':'CLOSED'})
        self.assertEqual(len(response.context['rows']),0)
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('impact-list')).status_code,403)
        self.assertEqual(self.client.post(reverse('impact-list'),{}).status_code,403)
