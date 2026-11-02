from pathlib import Path
p=Path('pms/analysis_views.py');s=p.read_text(encoding='utf-8').replace('            content = analysis_pdf(form.cleaned_data, result)', '''            from .analysis_archive import generate_analysis_report, analysis_artifact_bytes
            artifact = generate_analysis_report(request.user, form.cleaned_data)
            content = analysis_artifact_bytes(request.user, artifact)''').replace("            response['Content-Disposition'] = 'attachment; filename=\"pms-analysis.pdf\"'", "            response['Content-Disposition'] = f'attachment; filename=\"{artifact.report.number}-v{artifact.version}.pdf\"'\n            response['Cache-Control'] = 'private, no-store'")
p.write_text(s,encoding='utf-8')
# Keep scratch material out of the deliverable source tree.
p=Path('.gitignore');s=p.read_text(encoding='utf-8');s+='\n# Isolated local validation databases, logs, static and media\nwork/\n';p.write_text(s,encoding='utf-8')
