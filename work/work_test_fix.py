from pathlib import Path
p=Path('pms/test_impact_rows.py');s=p.read_text(encoding='utf-8').replace('    setUp=fixtures.ImpactTests.setUp', '''    def setUp(self):
        import uuid, shutil
        from pathlib import Path
        super().setUp()
        self.root=Path('.test-media')/uuid.uuid4().hex
        self.root.mkdir(parents=True);self.addCleanup(shutil.rmtree,self.root)
        media=override_settings(MEDIA_ROOT=self.root/'media');media.enable();self.addCleanup(media.disable)
        self.c=self.complaint();self.c.is_example=True;self.c.complaint_type='TEST_EVENT';self.c.save()''');p.write_text(s,encoding='utf-8')
p=Path('pms/test_analysis_extensions.py');s=p.read_text(encoding='utf-8').replace("self.assertEqual(analyze(self.filters())['total'],0) # CSV date outside current default period", "self.assertEqual(AnalysisRecord.objects.filter(origin='INTERNAL',is_current=True,batch__is_example=False).count(),0)");p.write_text(s,encoding='utf-8')
