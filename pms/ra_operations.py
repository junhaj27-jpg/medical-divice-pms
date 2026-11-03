"""Local-only parsers and approval gates for operational RA work."""
import csv
import io
import re
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone
from . import ra_operations_models as o
from . import ra_models as ra
from .file_security import safe_attachment_bytes
from .services import audit

KINDS = {
    'quality-documents': (o.QualityDocument, 'GMP 문서 계층·템플릿'),
    'quality-records': (o.QualityRecord, 'GMP 양식 작성 기록'),
    'quality-validation': (o.QualityValidation, '품질경영용 소프트웨어 밸리데이션'),
    'validation-requirements': (o.ValidationRequirement, '사용자 요구사항·위험'),
    'validation-cases': (o.ValidationCase, '시험 케이스 버전'),
    'validation-runs': (o.ValidationRun, '실행·일탈·재시험'),
    'dhf-projects': (o.DHFProject, 'DHF 프로젝트'),
    'design-traces': (o.DesignTrace, 'DHF 설계 추적'),
    'meeting-sources': (o.MeetingSource, '회의록 원문'),
    'meeting-candidates': (o.MeetingCandidate, '회의록 연결 후보'),
    'dhf-baselines': (o.DHFBaseline, 'DHF 기준 스냅샷'),
    'software-reviews': (o.SoftwareChangeReview, '소프트웨어 변경심사'),
    'technical-sections': (o.TechnicalSection, '기술문서 목차·준비 상태'),
    'review-responses': (o.ReviewResponse, '심사 질의·보완 답변'),
    'security-inventories': (o.SecurityInventory, '자산·구성요소·SBOM'),
    'security-findings': (o.SecurityFinding, '위협·취약점·조치'),
    'security-reviews': (o.SecurityReview, '출시 보안 검토'),
}
from . import ra_services as service

OPERATION_MODELS = {model for model, _ in KINDS.values()}
APPROVED = {'APPROVED', 'EFFECTIVE'}

def validate(obj):
    if type(obj) not in OPERATION_MODELS:
        return
    for field in obj._meta.fields:
        if not field.is_relation or not getattr(obj, field.attname):
            continue
        if field.name in service.SYSTEM_FIELDS:
            continue
        # Form instances can predate a document retirement or file rescan.
        linked = field.related_model._default_manager.get(pk=getattr(obj,field.attname))
        setattr(obj,field.name,linked)
        if isinstance(linked, ra.ScopedRecord) and linked.profile_id != obj.profile_id:
            raise ValidationError('연결 기록은 동일한 제품 규제 프로필이어야 합니다.')
        if field.name in ('minutes', 'sbom', 'mentioned_file'):
            service.validate_evidence(obj, [linked])
        if field.name == 'lot' and linked.device_id != obj.profile.device_id:
            raise ValidationError('LOT 제품을 확인하세요.')
        if field.name == 'capa':
            case = linked.complaint
            if case.device_id != obj.profile.device_id or case.is_example != obj.is_example:
                raise ValidationError('CAPA 제품·예시 범위를 확인하세요.')
    if isinstance(obj, o.QualityDocument):
        levels = ['MANUAL','PROCEDURE','INSTRUCTION','FORM']
        index = levels.index(obj.level)
        if (index == 0 and obj.parent_id) or (index and (not obj.parent_id or obj.parent.level != levels[index-1])):
            raise ValidationError('매뉴얼 → 절차서 → 작업지침 → 양식 순서로 연결하세요.')
        if not isinstance(obj.required_fields, list) or any(not isinstance(k,str) or not k.strip() for k in obj.required_fields):
            raise ValidationError('필수 항목은 이름의 JSON 배열입니다.')
    if isinstance(obj, o.QualityRecord):
        form = obj.form_version
        if form.level != 'FORM' or form.state not in APPROVED:
            raise ValidationError('승인된 양식 정의를 선택하세요.')
        if not isinstance(obj.values, dict):
            raise ValidationError('작성 값은 JSON 객체입니다.')
        if obj.corrects_id:
            if obj.corrects.state not in APPROVED or obj.corrects.form_version_id != form.pk:
                raise ValidationError('정정은 승인된 원기록과 같은 양식 버전을 참조해야 합니다.')
        elif form.document.state != 'EFFECTIVE':
            raise ValidationError('신규 기록에는 현행 시행 양식만 사용할 수 있습니다.')
    if isinstance(obj,o.QualityValidation) and obj.previous_id and not obj.revalidation_reason.strip():
        raise ValidationError('변경 후 재밸리데이션 검토 근거를 기록하세요.')
    if isinstance(obj, o.ValidationCase) and obj.version < 1:
        raise ValidationError('시험 버전은 1 이상이어야 합니다.')
    if isinstance(obj, o.ValidationCase) and obj.previous_id:
        if obj.previous.requirement_id != obj.requirement_id or obj.version <= obj.previous.version:
            raise ValidationError('동일 요구사항의 이전 시험 버전보다 높은 번호를 사용하세요.')
    if isinstance(obj, o.ValidationRun):
        if obj.case.state not in APPROVED or obj.case.requirement.state not in APPROVED:
            raise ValidationError('승인된 요구사항과 시험 버전에만 실행을 기록하세요.')
        if obj.outcome in ('FAIL','WAIVED') and not obj.deviation.strip():
            raise ValidationError('실패·면제 사유를 기록하세요.')
        if obj.retest_of_id and obj.retest_of.case.requirement_id != obj.case.requirement_id:
            raise ValidationError('같은 요구사항의 이전 실행을 선택하세요.')
    if isinstance(obj, o.MeetingCandidate):
        lines = source_text(obj.meeting.minutes).splitlines()
        if not 1 <= obj.line_number <= len(lines) or lines[obj.line_number-1][:4000] != obj.excerpt:
            raise ValidationError('후보가 원문 행과 일치하지 않습니다.')
    if isinstance(obj, o.DesignTrace):
        if obj.release_review_id and obj.release_review_id != obj.project.release_id:
            raise ValidationError('출시 검토 버전이 프로젝트와 일치해야 합니다.')
        if obj.change_id and obj.change.to_revision_id != obj.project.release_id:
            raise ValidationError('변경 후 버전이 프로젝트와 일치해야 합니다.')
    if isinstance(obj,o.ReviewResponse) and obj.previous_id and obj.previous.review_id!=obj.review_id:
        raise ValidationError('같은 변경심사의 이전 답변을 선택하세요.')
    if isinstance(obj,o.ReviewResponse) and obj.package_id and obj.package.change_id!=obj.review.change_id:
        raise ValidationError('답변 제출본의 변경 요청이 일치해야 합니다.')
    if isinstance(obj, o.SoftwareChangeReview) and obj.project.release_id != obj.change.to_revision_id:
        raise ValidationError('DHF 프로젝트는 변경 후 제품 버전과 일치해야 합니다.')
    if isinstance(obj,o.SecurityFinding) and obj.checked_on and obj.checked_on>timezone.localdate():
        raise ValidationError('취약점 확인일을 확인하세요.')
    if isinstance(obj, o.SecurityFinding) and obj.score_as_reported and not obj.score_source_version:
        raise ValidationError('입력 점수의 출처와 버전을 기록하세요.')

def section_ready(row):
    if row.readiness!='READY' or not row.document_id or row.document.state!='EFFECTIVE':
        return False
    if row.document.primary_file_id and row.document.primary_file.scan_status!='PASSED':
        return False
    return not row.evidence.exclude(scan_status='PASSED').exists() and not row.document.evidence.exclude(scan_status='PASSED').exists()


def missing_required_fields(record):
    missing = []
    for key in record.form_version.required_fields:
        value = record.values.get(key)
        if value is None or value in ([], {}) or isinstance(value, str) and not value.strip():
            missing.append(key)
    return missing


def evidence_links(target):
    rows = list(target.evidence.order_by('pk').values('id', 'sha256', 'scan_status'))
    if isinstance(target, ra.ControlledDocument) and target.primary_file_id:
        primary = target.primary_file
        if not any(row['id'] == primary.pk for row in rows):
            rows.append({'id': primary.pk, 'sha256': primary.sha256, 'scan_status': primary.scan_status})
    return rows


def approval_gate(obj):
    if isinstance(obj, o.QualityDocument) and obj.document.state != 'EFFECTIVE':
        raise ValidationError('시행된 통제 문서를 연결하세요.')
    if isinstance(obj, o.QualityRecord):
        missing = missing_required_fields(obj)
        if missing:
            raise ValidationError('필수 항목 누락: '+', '.join(missing))
    if isinstance(obj, o.ValidationRun) and obj.outcome != 'WAIVED' and not obj.evidence.exists():
        raise ValidationError('실행 증빙을 연결하세요.')
    if isinstance(obj, o.QualityValidation):
        requirements = validation_requirement_rows(obj)
        if not obj.report.strip() or not obj.internal_confirmation.strip() or not requirements:
            raise ValidationError('내부 확인과 결과 보고서 및 요구사항이 필요합니다.')
        for requirement in requirements:
            cases = o.ValidationCase.objects.filter(requirement=requirement).order_by('-version','-pk')
            latest = cases.first()
            result = o.ValidationRun.objects.filter(case=latest).order_by('-pk').first() if latest else None
            if not latest or latest.state not in APPROVED or not result or result.state not in APPROVED or result.outcome not in ('PASS','WAIVED'):
                raise ValidationError('미실행·실패·미승인 시험이 남아 있습니다.')
    if isinstance(obj,o.ReviewResponse):
        if not obj.response.strip() or not obj.package_id or obj.package.state not in APPROVED:
            raise ValidationError('답변 내용과 승인된 제출 버전을 연결하세요.')
        service.verify_approval(obj.package)
    if isinstance(obj, o.SoftwareChangeReview):
        sections = list(o.TechnicalSection.objects.filter(review=obj).select_related('document'))
        if obj.classification == '확인 필요' or not obj.classification_basis.strip() or not sections:
            raise ValidationError('담당자 변경 분류·근거 및 기술문서 목차가 필요합니다.')
        if any(not section_ready(section) for section in sections):
            raise ValidationError('미충족 기술문서 항목을 확인하세요.')
        if not obj.package_id or obj.package.state not in APPROVED or obj.package.change_id != obj.change_id or obj.package.product_revision_id != obj.project.release_id:
            raise ValidationError('동일 변경·출시 버전의 승인된 제출 패키지를 연결하세요.')
        service.verify_approval(obj.package)
        for row in sections:
            files=list(row.evidence.all())+list(row.document.evidence.all())
            if row.document.primary_file_id:
                files.append(row.document.primary_file)
            service.validate_evidence(obj,files)
        obj.submission_manifest = {
            'package': obj.package_id,
            'package_hash': obj.package.approval_snapshot['hash'],
            'sections': [{'section': row.section, 'document':row.document_id,
                          'version':row.document.version, 'hash':row.document.approval_snapshot.get('hash')}
                         for row in sections],
            'matrix': matrix(obj.project),
        }
    if isinstance(obj, o.SecurityReview):
        if o.SecurityFinding.objects.filter(inventory=obj.inventory).exclude(state__in=APPROVED).exists() and not obj.open_items.strip():
            raise ValidationError('미해결 취약점의 조치 계획을 기록하세요.')
        if obj.inventory.state not in APPROVED:
            raise ValidationError('검토된 구성 목록을 연결하세요.')
        if not obj.test_results.strip() or not obj.residual_decision.strip() or not obj.evidence.exists():
            raise ValidationError('보안 시험 결과·증빙과 담당자 잔여위험 판단이 필요합니다.')
    if isinstance(obj, o.SecurityFinding) and (not obj.residual.strip() or not obj.evidence.exists()):
        raise ValidationError('잔여위험 판단과 조치 검증 증빙을 연결하세요.')
    if isinstance(obj, o.DHFBaseline) and not obj.baseline:
        raise ValidationError('기준 스냅샷을 먼저 캡처하세요.')

def validation_requirement_rows(obj):
    return list(o.ValidationRequirement.objects.filter(validation=obj).order_by('pk'))

def source_text(attachment):
    try:
        return safe_attachment_bytes(attachment).decode('utf-8-sig')
    except UnicodeDecodeError as error:
        raise ValidationError('UTF-8 텍스트 원본을 선택하세요.') from error

@transaction.atomic
def extract(meeting, user):
    service.require_ra(user)
    meeting = service.locked(meeting)
    service.validate_evidence(meeting, [meeting.minutes])
    from .models import Attachment
    documents = list(ra.ControlledDocument.objects.filter(profile=meeting.profile))
    attachments = list(Attachment.objects.filter(ra_profile=meeting.profile,scan_status='PASSED').exclude(original_name=''))
    if o.MeetingSource.objects.filter(profile=meeting.profile, project=meeting.project, minutes__sha256=meeting.minutes.sha256,pk__lt=meeting.pk).exists():
        raise ValidationError('동일 해시 회의록의 기존 등록을 사용하세요.')
    created = 0
    for number, line in enumerate(source_text(meeting.minutes).splitlines()[:5000], 1):
        matches = [doc for doc in documents if doc.number and re.search(r'(?<![\w-])'+re.escape(doc.number)+r'(?![\w-])', line)]
        category = next((word for word in ('설계 입력','설계 출력','설계 검토','검증','밸리데이션','위험','변경','결정','미해결','후속') if word in line), '')
        version = re.search(r'(?i)(?:\bv|버전\s*)(\d{1,9})\b',line)
        if version:
            matches = [doc for doc in matches if doc.version==int(version.group(1))]
        files = [file for file in attachments if file.original_name in line]
        if not category and not matches and not files:
            continue
        if o.MeetingCandidate.objects.filter(meeting=meeting,line_number=number).exists():
            continue
        due = re.search(r'\b\d{4}-\d{2}-\d{2}\b', line)
        owner = re.search(r'담당\s*[:：]\s*([^,;|]{1,120})',line)
        candidate=o.MeetingCandidate(created_by=user,
            profile=meeting.profile,is_example=meeting.is_example, title=f'회의록 {number}행',
            owner=meeting.owner,reviewer=meeting.reviewer,meeting=meeting,line_number=number,
            excerpt=line[:4000],category=category or '문서·첨부 언급',document=matches[0] if len(matches)==1 else None,
            mentioned_file=files[0] if len(files)==1 else None,
            suggested_owner=owner.group(1).strip() if owner else '',suggested_due=due.group() if due else '',
            uncertainty='원문과 연결 근거를 담당자가 확인하세요.' if len(matches)==1 else '문서 번호·버전 또는 파일 미확인',
        )
        service.persist(candidate)
        audit(user,'RA_MEETING_EXTRACT',candidate,after={'line':number,'source_sha256':meeting.minutes.sha256})
        created += 1
    return created

@transaction.atomic
def confirm(candidate, user, reason):
    service.require_ra(user)
    candidate = service.locked(candidate)
    if candidate.confirmed_trace_id:
        return candidate.confirmed_trace
    if candidate.state not in APPROVED:
        raise ValidationError('원문 후보를 검토·승인한 뒤 연결하세요.')
    service.verify_approval(candidate)
    service.validate_evidence(candidate,[candidate.meeting.minutes])
    trace = service.save_record(o.DesignTrace(),user,dict(
        profile=candidate.profile,is_example=candidate.is_example,title=candidate.title,
        owner=candidate.owner,reviewer=candidate.reviewer,project=candidate.meeting.project,
        output=candidate.document if candidate.category=='설계 출력' else None,
    ),reason,links={'evidence':[candidate.mentioned_file] if candidate.mentioned_file_id else []})
    candidate.confirmed_trace=trace
    candidate.revision+=1
    service.persist(candidate)
    audit(user,'RA_DHF_CONFIRM',candidate,after={'trace':trace.pk,'reason':reason})
    return trace

def matrix(project):
    kinds = {'requirement':'requirements','output':'documents','risk':'product-risks','verification':'documents','change':'changes','release_review':'product-versions'}
    fields = ('requirement','output','risk','verification','change','release_review')
    rows = []
    for trace in o.DesignTrace.objects.filter(project=project).order_by('pk'):
        links = {}
        for field in fields:
            target = getattr(trace,field)
            links[field] = {'id':target.pk,'title':target.title,'revision':target.revision,'version':getattr(target,'version',None),'state':target.state,
                            'hash':target.approval_snapshot.get('hash',''),
                            'url':f'/ra/{kinds[field]}/{target.pk}/',
                            'evidence':evidence_links(target),
                            'obsolete':target.state=='RETIRED' or isinstance(target,ra.ControlledDocument) and ra.ControlledDocument.objects.filter(profile=target.profile,number=target.number,state='EFFECTIVE',version__gt=target.version).exists()} if target else None
        rows.append({'id':trace.pk,'title':trace.title,'links':links,
                     'missing':[key for key,value in links.items() if not value],
                     'needs_review':[key for key,value in links.items() if value and (value['state'] not in APPROVED or any(file['scan_status']!='PASSED' for file in value['evidence']))],
                     'obsolete':[key for key,value in links.items() if value and value['obsolete']]})
    return {'project':project.pk,'release':project.release_id,'release_version':project.release.version,'rows':rows}

@transaction.atomic
def capture(obj,user,reason):
    service.require_ra(user)
    obj=service.locked(obj)
    if obj.state!='DRAFT' or not reason.strip():
        raise ValidationError('초안과 캡처 사유가 필요합니다.')
    obj.baseline={**matrix(obj.project),'captured_at':timezone.now().isoformat()}
    obj.revision+=1
    service.persist(obj)
    audit(user,'RA_DHF_BASELINE',obj,after={'hash':service.digest(obj.baseline),'reason':reason})

@transaction.atomic
def import_sbom(obj,user,reason):
    service.require_ra(user)
    obj=service.locked(obj)
    if obj.state!='DRAFT' or not obj.sbom_id or not reason.strip():
        raise ValidationError('초안, 검사 통과 CSV 및 가져오기 사유가 필요합니다.')
    service.validate_evidence(obj,[obj.sbom])
    reader=csv.DictReader(io.StringIO(source_text(obj.sbom)))
    if reader.fieldnames != ['name','version','source']:
        raise ValidationError('CSV 열은 name,version,source 순서여야 합니다.')
    rows=[]
    for row in reader:
        if len(rows)>=5000 or any(not value or len(value)>500 for value in row.values() if isinstance(value,str)) or set(row)!={'name','version','source'} or any(value is None for value in row.values()):
            raise ValidationError('구성요소 행 형식 또는 최대 5,000개 제한을 확인하세요.')
        rows.append(row)
    if not rows:
        raise ValidationError('구성요소가 없습니다.')
    obj.components=rows
    obj.revision+=1
    service.persist(obj)
    audit(user,'RA_SBOM_IMPORT',obj,after={'count':len(rows),'sha256':obj.sbom.sha256,'reason':reason})


@transaction.atomic
def template_draft(template,user,number,reason):
    service.require_ra(user)
    template=service.locked(template)
    if not template.template_approved or template.state not in APPROVED or template.document.state!='EFFECTIVE':
        raise ValidationError('승인된 현행 템플릿을 선택하세요.')
    service.verify_approval(template)
    document=template.document
    draft=service.save_record(ra.ControlledDocument(),user,{
        'profile':template.profile,'is_example':template.is_example,'title':document.title,
        'owner':user,'reviewer':template.reviewer,'category':document.category,
        'number':number.strip(),'version':1,'body':document.body,'primary_file':document.primary_file,
        'change_reason':reason,
    },reason,links={'evidence':document.evidence.all()})
    service.save_record(o.QualityDocument(),user,{
        'profile':template.profile,'is_example':template.is_example,'title':draft.title,
        'owner':user,'reviewer':template.reviewer,'document':draft,'parent':template.parent,
        'department':template.department,'level':template.level,
        'required_fields':template.required_fields,'template_source':document,
    },reason,links={'requirements':template.requirements.all()})
    return draft


def dashboard_context(obj):
    if isinstance(obj,o.DHFProject):
        return {'matrix':matrix(obj)}
    if isinstance(obj,o.DHFBaseline):
        return {'matrix':obj.baseline}
    if isinstance(obj,o.DesignTrace):
        return {'source_candidate':o.MeetingCandidate.objects.filter(confirmed_trace=obj).first()}
    if isinstance(obj,o.SoftwareChangeReview):
        sections=list(o.TechnicalSection.objects.filter(review=obj).select_related('document').order_by('section'))
        return {'sections':sections,'not_ready':[row.section for row in sections if not section_ready(row)],
                'responses':o.ReviewResponse.objects.filter(review=obj).order_by('pk')}
    if isinstance(obj,o.QualityRecord):
        return {'missing_fields':missing_required_fields(obj),
                'duplicate_hint':o.QualityRecord.objects.filter(profile=obj.profile,form_version=obj.form_version,lot=obj.lot,change=obj.change,corrects__isnull=True).exclude(pk=obj.pk).exists()}
    if isinstance(obj,o.SecurityReview):
        return {'security_findings':o.SecurityFinding.objects.filter(inventory=obj.inventory).order_by('due_on','pk')}
    if isinstance(obj,o.QualityValidation):
        rows=[]
        for requirement in validation_requirement_rows(obj):
            case=o.ValidationCase.objects.filter(requirement=requirement).order_by('-version','-pk').first()
            runs=o.ValidationRun.objects.filter(case=case).order_by('-pk') if case else []
            rows.append((requirement,case,runs))
        return {'validation_rows':rows}
    return {}


def approval_context(obj):
    if isinstance(obj,o.QualityValidation):
        result=[]
        for requirement in validation_requirement_rows(obj):
            cases=[]
            for case in o.ValidationCase.objects.filter(requirement=requirement).order_by('version','pk'):
                runs=list(o.ValidationRun.objects.filter(case=case).order_by('pk').values('id','revision','state','outcome','approval_snapshot'))
                cases.append({'id':case.pk,'version':case.version,'approval':case.approval_snapshot,'runs':runs})
            result.append({'id':requirement.pk,'approval':requirement.approval_snapshot,'cases':cases})
        return {'requirement_trace':result}
    if isinstance(obj,o.SecurityReview):
        findings=list(o.SecurityFinding.objects.filter(inventory=obj.inventory).order_by('pk').values('id','revision','state','identifier','approval_snapshot'))
        return {'finding_register':findings}
    return {}
