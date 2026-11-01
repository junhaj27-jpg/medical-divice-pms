"""Private versioned analysis PDFs, following the case artifact storage pattern."""
import hashlib
import uuid
from django.core.files.base import ContentFile
from django.core.exceptions import ValidationError
from django.db import transaction
from django.core.serializers.json import DjangoJSONEncoder
import json
from .analysis import require_analyst, digest, analyze
from .analysis_models import AnalysisReport, AnalysisArtifact, AnalysisReview
from .analysis_reporting import analysis_pdf
from .services import audit


def serial(value):
    return json.loads(json.dumps(value,cls=DjangoJSONEncoder,ensure_ascii=False))


@transaction.atomic
def generate_analysis_report(user, filters):
    require_analyst(user)
    filters_snapshot=serial(filters)
    key=digest(filters_snapshot)
    report,_=AnalysisReport.objects.get_or_create(key=key,defaults={'number':'ANL-'+uuid.uuid4().hex})
    report=AnalysisReport.objects.select_for_update().get(pk=report.pk)
    result=analyze(filters)
    # Rows are immutable source snapshots in normal service paths. Preserve both periods.
    records=result['records']+result['previous_records']
    scope=[dict(id=r.pk,batch=r.batch_id,row=r.row_number,origin=r.origin,source_case=r.source_case_id,
                source_version=r.source_version,source_hash=r.source_hash,
                clean_hash=digest(serial({k:getattr(r,k) for k in ('source','record_id','device','manufacturer','model','occurred_on','reported_on','event_type','seriousness','narrative')})),
                raw_hash=digest(r.raw),original_sha256=r.batch.sha256) for r in records]
    reviews=[]
    for signal in result['signals']:
        review=signal['review']
        if review: review=AnalysisReview.objects.select_for_update().get(pk=review.pk)
        reviews.append(dict(key=signal['key'],snapshot=signal['snapshot'],status=review.status if review else 'NEW',
                            assignee_id=review.assignee_id if review else None,
                            history=list(review.history.order_by('pk').values('actor_id','assignee_id','before','after','note','created_at')) if review else []))
    version=(report.artifacts.order_by('-version').values_list('version',flat=True).first() or 0)+1
    snapshot=serial(dict(number=report.number,version=version,author_id=user.pk,generated_at=result['generated_at'],
        filters=filters_snapshot,previous_start=result['previous_start'],previous_end=result['previous_end'],
        counting='보고 건수 / 발생률 아님 / 내부 사건 최신 스냅샷만 기본 집계 / 양끝 포함',
        scope=scope,scope_hash=digest(scope),reviews=reviews,total=result['total'],previous_total=result['previous_total']))
    result['archive_snapshot']=snapshot
    content=analysis_pdf(filters,result)
    artifact=AnalysisArtifact(report=report,version=version,snapshot=snapshot,generated_by=user,sha256=hashlib.sha256(content).hexdigest())
    artifact.file.save(f'{report.number}-v{version}-{uuid.uuid4().hex}.pdf',ContentFile(content),save=False)
    try:
        artifact.save()
        audit(user,'ANALYSIS_PDF_GENERATE',artifact,after={'report_id':report.pk,'version':version,'sha256':artifact.sha256})
    except Exception:
        artifact.file.delete(save=False)
        raise
    return artifact


def analysis_artifact_bytes(user, artifact):
    require_analyst(user)
    with artifact.file.open('rb') as stream: content=stream.read()
    if hashlib.sha256(content).hexdigest()!=artifact.sha256: raise ValidationError('보관 파일 해시가 일치하지 않습니다.')
    audit(user,'ANALYSIS_PDF_DOWNLOAD',artifact,after={'version':artifact.version,'sha256':artifact.sha256})
    return content
