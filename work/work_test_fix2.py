from pathlib import Path
p=Path('pms/test_analysis_extensions.py');s=p.read_text(encoding='utf-8').replace('with tempfile.TemporaryDirectory() as root, override_settings(MEDIA_ROOT=root):',"Path('.test-media').mkdir(exist_ok=True)\n        with tempfile.TemporaryDirectory(dir='.test-media') as root, override_settings(MEDIA_ROOT=root):");p.write_text(s,encoding='utf-8')
# Include saved review state in archived PDF, so the file and saved metadata use the same snapshot.
p=Path('pms/analysis_reporting.py');s=p.read_text(encoding='utf-8');s=s.replace("    for signal in result['signals']:", "    if archive:\n        for saved in archive['reviews']:\n            text(f\"보관 검토 상태: {saved['status']} / 담당자 ID: {saved['assignee_id']}\")\n            for h in saved['history']:\n                text(f\"{h['created_at']} / 작성자 ID {h['actor_id']} / {h['before']} → {h['after']} / {h['note']}\")\n    for signal in result['signals']:")
s=s.replace("        review = signal['review']", "        review = None if archive else signal['review']")
s=s.replace("        text(f\"상태: {review.get_status_display() if review else '신규'} / 담당자: {review.assignee.username if review else '미지정'}\")", "        if not archive: text(f\"상태: {review.get_status_display() if review else '신규'} / 담당자: {review.assignee.username if review else '미지정'}\")")
p.write_text(s,encoding='utf-8')
