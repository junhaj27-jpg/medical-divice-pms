import csv
import io
from datetime import date
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from .analysis import HEADERS, AnalysisFilter, analyze, ingest, save_review
from .analysis_models import AnalysisImport, AnalysisRecord, AnalysisReview
from .models import Profile


@override_settings(PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class AnalysisTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user('analyst', password='test')
        Profile.objects.create(user=self.user, role='RA_QA')
        self.staff = User.objects.create_user('staff')
        self.client.force_login(self.user)

    def upload(self, rows, example=False):
        stream = io.StringIO(newline='')
        writer = csv.writer(stream)
        writer.writerow(HEADERS)
        for changes in rows:
            row = dict(source='DEMO', record_id='r1', device='샘플 기기', manufacturer='예시 제조사', model='M1', occurred_on='2026-10-02', reported_on='2026-10-03', event_type='고장', seriousness='', narrative='전원 중단 관찰')
            row.update(changes)
            writer.writerow([row[k] for k in HEADERS])
        return ingest(SimpleUploadedFile('../../data.csv', stream.getvalue().encode('utf-8-sig')), self.user, example)

    def filters(self, **changes):
        params = dict(basis='reported_on', start='2026-10-01', end='2026-10-28', example='real', minimum=1, threshold=100)
        params.update(changes)
        form = AnalysisFilter(params)
        self.assertTrue(form.is_valid(), form.errors)
        return form.cleaned_data

    def test_normal_raw_unknown_and_original(self):
        batch = self.upload([{}])
        row = batch.records.get()
        self.assertEqual(row.seriousness, 'UNKNOWN')
        self.assertEqual(row.raw['seriousness'], '')
        self.assertIn(b'record_id', bytes(batch.original))
        self.assertEqual(batch.filename, 'data.csv')
        self.assertEqual(batch.accepted, 1)

    def test_invalid_date_missing_required_and_types(self):
        batch = self.upload([{'reported_on':'2026-02-30'}, {'device':''}, {'seriousness':'mild'}, {'occurred_on':'2026-10-04'}])
        self.assertEqual(batch.accepted, 0)
        self.assertEqual([e['row'] for e in batch.errors], [2,3,4,5])
        self.assertIn('필수값', str(batch.errors))

    def test_deduplication_source_id_and_no_id(self):
        batch = self.upload([{}, {}, {'source':'OTHER'}, {'record_id':''}, {'record_id':''}])
        self.assertEqual(batch.accepted, 3)
        self.assertEqual(len(batch.errors), 2)
        self.assertEqual(self.upload([{}]).accepted, 0)
        self.assertEqual(self.upload([{}], example=True).accepted, 1)

    def test_empty_data_and_no_signals(self):
        batch = self.upload([])
        self.assertEqual(batch.accepted, 0)
        self.assertIn('데이터 행', str(batch.errors))
        self.assertEqual(analyze(self.filters())['total'], 0)
        self.assertContains(self.client.get(reverse('analysis')), '검색 결과가 없습니다')

    def test_zero_comparison_and_basis_separation(self):
        self.upload([{'occurred_on':'2026-09-30'}])
        result = analyze(self.filters())
        self.assertEqual(result['previous_total'], 0)
        self.assertIsNone(result['signals'][0]['group']['increase'])
        occurred = analyze(self.filters(basis='occurred_on'))
        self.assertEqual((occurred['total'], occurred['previous_total']), (0,1))
        self.assertEqual(occurred['signals'], [])

    def test_rules_boundaries_and_filters(self):
        self.upload([{'record_id':'old','occurred_on':'2026-09-20','reported_on':'2026-09-20'}, {}, {'record_id':'r2'}])
        data = self.filters()
        self.assertEqual(len(analyze(data)['signals']), 1)
        self.assertEqual(analyze(self.filters(minimum=3))['signals'], [])
        self.assertEqual(analyze(self.filters(threshold=101))['signals'], [])
        self.assertEqual(analyze(self.filters(manufacturer='없는 제조사'))['total'], 0)
        self.assertEqual(analyze(self.filters(seriousness='UNKNOWN'))['total'], 2)

    def test_review_persistence_history_and_permissions(self):
        self.upload([{}])
        signal = analyze(self.filters())['signals'][0]
        review = save_review(self.user, signal, 'REVIEW', self.user, '근거 확인')
        save_review(self.user, signal, 'ACTION', self.user, '추가 조사')
        reloaded = AnalysisReview.objects.get(pk=review.pk)
        self.assertEqual(reloaded.status, 'ACTION')
        self.assertEqual(reloaded.history.count(), 2)
        self.assertEqual(reloaded.history.order_by('pk').last().before, 'REVIEW')
        self.assertEqual(analyze(self.filters())['signals'][0]['review'].pk, review.pk)
        self.assertRaises(PermissionDenied, save_review, self.staff, signal, 'CLOSED', self.user, '우회')
        self.assertRaises(ValidationError, save_review, self.user, signal, 'CLOSED', self.staff, '잘못된 담당자')

    def test_csv_bom_formula_and_invalid_export(self):
        self.upload([{'device':'=SUM(A1)','narrative':'\t@evil'}])
        params = dict(self.filters())
        params['format'] = 'csv'
        response = self.client.get(reverse('analysis'), params)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b'\xef\xbb\xbf'))
        self.assertIn("'=SUM", response.content.decode('utf-8-sig'))
        self.assertIn("'@evil", response.content.decode('utf-8-sig'))
        self.assertEqual(self.client.get(reverse('analysis'), {'format':'csv'}).status_code, 400)

    def test_upload_limits_and_utf8(self):
        for upload in [SimpleUploadedFile('bad.exe', b'x'), SimpleUploadedFile('bad.csv', b'\xff'), SimpleUploadedFile('empty.csv', b'')]:
            self.assertRaises(ValidationError, ingest, upload, self.user)
        with override_settings(DATA_UPLOAD_MAX_MEMORY_SIZE=5):
            self.assertRaises(ValidationError, ingest, SimpleUploadedFile('x.csv', b'123456'), self.user)
        self.assertEqual(AnalysisImport.objects.count(), 0)

    def test_http_flow_report_and_csrf_permissions(self):
        batch = self.upload([{}])
        data = self.filters()
        response = self.client.get(reverse('analysis'), data)
        self.assertContains(response, '전원 중단 관찰')
        self.assertEqual(self.client.get(reverse('analysis-import', args=[batch.pk])).status_code, 200)
        signal = analyze(data)['signals'][0]
        import urllib.parse
        url = reverse('analysis-review') + '?' + urllib.parse.urlencode(data)
        response = self.client.post(url, {'key':signal['key'], 'status':'REVIEW', 'assignee':self.user.pk, 'note':'검토'})
        self.assertEqual(response.status_code, 302)
        self.assertContains(self.client.get(reverse('analysis'), {**data, 'format':'report'}), '검토')
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse('analysis')).status_code, 403)
        self.assertEqual(self.client.get(reverse('analysis-import', args=[batch.pk])).status_code, 403)
        self.assertEqual(self.client.post(url, {}).status_code, 403)

    def test_invalid_filter_and_missing_occurrence(self):
        self.assertFalse(AnalysisFilter({'start':'bad'}).is_valid())
        self.upload([{'occurred_on':''}])
        result = analyze(self.filters(basis='occurred_on'))
        self.assertEqual(result['missing_dates'], 1)
        self.assertEqual(result['total'], 0)


    def test_pdf_and_archived_review_snapshot(self):
        import os
        self.upload([{}])
        data = self.filters()
        signal = analyze(data)['signals'][0]
        review = save_review(self.user, signal, 'REVIEW', self.user, '담당자 확인')
        self.upload([{'record_id':'new'}])
        response = self.client.get(reverse('analysis-review-detail', args=[review.pk]))
        self.assertContains(response, '담당자 확인')
        self.assertEqual(review.snapshot['count'], 1)
        with override_settings(PDF_KOREAN_FONT=''):
            response = self.client.get(reverse('analysis'), {**data, 'format':'pdf'})
            self.assertContains(response, '한글 TTF')
        font = os.environ.get('PDF_KOREAN_FONT')
        if not font: self.skipTest('PDF_KOREAN_FONT 미설정')
        with override_settings(PDF_KOREAN_FONT=font):
            response = self.client.get(reverse('analysis'), {**data, 'format':'pdf'})
        self.assertEqual(response['Content-Type'], 'application/pdf')
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(response.content))
        self.assertIn('보고 건수', ''.join(p.extract_text() for p in reader.pages))

    def test_repository_sample_quality_results(self):
        from pathlib import Path
        from django.conf import settings
        content = (Path(settings.BASE_DIR) / 'samples/pms-analysis-demo.csv').read_bytes()
        batch = ingest(SimpleUploadedFile('sample.csv', content), self.user, True)
        self.assertEqual(batch.accepted, 3)
        self.assertEqual([e['row'] for e in batch.errors], [5, 6, 7])
        result = analyze(self.filters(example='sample', minimum=3))
        self.assertEqual(result['seriousness'], {'중대':1, '미상':1, '비중대':1})
        self.assertEqual(len(result['signals']), 1)
