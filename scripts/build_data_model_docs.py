"""Regenerate physical documentation from Django's registered model metadata."""
import os
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
os.environ.setdefault('DJANGO_SETTINGS_MODULE','config.settings')
import django
django.setup()
from django.apps import apps
from django.db import connection
from django.db.models import NOT_PROVIDED

GROUPS=[
('사용자·역할·제품·UDI·LOT','User Group Permission Profile Manufacturer MedicalDevice UDI ProductLot'),
('불만·이상사례·익명 환자·위험평가','CustomerComplaint PatientAnonymousInfo AdverseEvent RiskAssessment RiskAssessmentHistory'),
('CAPA·효과성 평가·후속 조치','CAPA CAPAEvaluation WorkTask TaskHistory Attachment'),
('리콜·대상·거래처·회수 원장','Recall RecallTarget BusinessPartner RecallRecipient RecoveryEntry RecallContact'),
('규정·청크·규칙 버전·적용·개정 영향','RegulationDocument RegulationChunk ReportingRule RuleCitation RulePreview RuleChange RuleFamilyLock RuleApplication RegulatoryImpact ImpactReview'),
('승인·담당 업무·알림·감사','Approval WorkTask TaskHistory Notification AuditLog Profile LoginBucket AssistantConversation AssistantMessage'),
('분석 수집·레코드·안전 신호·검토','AnalysisImport AnalysisRecord AnalysisReview AnalysisReviewHistory SafetySignal SafetyReview'),
('제출·보고서·증빙 (구현 모델만)','RegulatoryReport RegulatoryReportHistory ReportArtifact Attachment'),
]
MODELS=list(apps.get_app_config('pms').get_models())
AUTH=[apps.get_model('auth',x) for x in ('User','Group','Permission')]
ALL={m.__name__:m for m in MODELS+AUTH}
PURPOSE=dict(zip('Profile Manufacturer MedicalDevice UDI ProductLot CustomerComplaint PatientAnonymousInfo AdverseEvent RiskAssessment CAPA Recall RecallTarget RegulatoryReport Attachment Approval AuditLog Notification AssistantConversation AssistantMessage WorkTask TaskHistory CAPAEvaluation BusinessPartner RecallRecipient RecoveryEntry RecallContact ReportingRule RuleApplication ReportArtifact LoginBucket RegulationDocument RegulationChunk RuleCitation RulePreview RuleChange RuleFamilyLock RegulatoryImpact ImpactReview AnalysisImport AnalysisRecord AnalysisReview AnalysisReviewHistory SafetySignal SafetyReview RiskAssessmentHistory RegulatoryReportHistory'.split(),['사용자 역할·시간대','제조사','제품','UDI 식별자','생산 LOT·일련번호','PMS 사건','사건별 익명 환자 정보','사건별 이상사례 판단','현재 위험평가','시정·예방 조치','회수 계획·상태','회수 대상 LOT','규제보고 판단·제출 상태','검사된 증빙 파일 참조','승인 요청·결정·무결성 스냅샷','행위 감사','사용자 알림','RA 상담 세션','상담 내용','사건 담당 업무','업무 변경 이력','CAPA 효과성 평가·증빙','거래처','거래처·LOT·단위별 회수 대상','추가 회수 원장','회수 연락 이력','규칙 버전','사건 규칙 적용 스냅샷','버전별 보고 PDF·묶음 해시','로그인 제한 버킷','규정 원본·검토','원문 청크','규칙 항목과 원문 인용','기한 미리보기','규칙 변경 이력','규칙 계열 직렬화 잠금','개정 영향 분석','사건별 영향 처리','분석 원본 CSV 수집','출처별 정규화 레코드','분석 신호 검토','분석 검토 이력','내부 사건 안전 신호','안전 신호 검토 이력','이번 추가: 실제 저장 시점 위험평가 변경 기록','이번 추가: 실제 저장 시점 규제보고 변경 기록']))
IMMUTABLE={'RiskAssessmentHistory','RegulatoryReportHistory','TaskHistory','CAPAEvaluation','RecoveryEntry','RecallContact','RuleApplication','ReportArtifact','RuleChange','SafetyReview','AnalysisReviewHistory'}
SENSITIVE={'PatientAnonymousInfo','AdverseEvent','CustomerComplaint','Attachment','RiskAssessment','RiskAssessmentHistory','RegulatoryReport','RegulatoryReportHistory','AnalysisImport','AnalysisRecord','AssistantMessage','ReportArtifact','SafetySignal','AnalysisReview'}
SERVICES={
 'CustomerComplaint':'model_integrity: 제품·UDI·LOT, 활성/역할 배정, 기존 리콜·규칙의 역방향 일치. services.TRANSITIONS: 상태 전이·승인 게이트.',
 'ProductLot':'모델 저장: UDI 제품 일치, 기존 항목 제품·UDI 재연결 금지.',
 'UDI':'모델 저장: 기존 제품 재연결 금지.',
 'AdverseEvent':'모델 저장 및 serializer: patient.complaint_id == complaint_id.',
 'PatientAnonymousInfo':'clean의 식별정보 키워드 검사는 완전한 개인정보 탐지가 아니다. 연결 이상사례 사건 일치.',
 'Recall':'모델 저장: 사건 제품 일치, 기존 대상과 제품 일치·목표 축소 검사.',
 'RecallTarget':'사건→리콜 잠금 후 LOT 제품 일치와 대상 수량 합계 검사.',
 'RecallRecipient':'모델 저장: LOT 제품 일치, 원장 키·목표·누적 값 직접 변경 금지. 서비스: 회수 예약과 원장 동시 저장.',
 'RecoveryEntry':'record_recovery만 추가 허용. 부모 잠금+조건부 F 업데이트+원장 insert를 한 트랜잭션으로 실행.',
 'WorkTask':'사건/조치 일치, 활성 담당자, STAFF 접수자 범위; save_task에서 권한·시각·변경 이력.',
 'CAPA':'종결 시 최신 PASS 평가와 결과·기준·예정일 일치; close_capa에서 연결 업무 완료.',
 'CAPAEvaluation':'평가 서비스는 미래일 차단, 동일 사건 PASSED 증빙만 연결. m2m pre_add도 동일 조건 검사. 본문 수정 금지, 최초 후속 업무 연결 허용.',
 'ReportingRule':'regulatory: 역할·분리 승인·원문 인용·시행일·범위 충돌·낙관적 토큰 및 계열 잠금. 직접 save는 제한.',
 'RuleApplication':'서비스는 시행 규칙·사건 조건·예시 분리·미리보기·직전 적용 토큰 검사. 재적용은 새 이력이다.',
 'ImpactReview':'서비스의 분석 토큰·사유·권한 검사; 모델은 업무·적용 사건·규칙 연결 검사.',
 'SafetySignal':'safety.detect: scope+필터+규칙 버전+제품·LOT로 key 해시. review_signal: 활성 전문 역할, 증거 사건에 속한 CAPA·리콜 연결.',
 'AnalysisRecord':'analysis.ingest: CSV·날짜·내용 검증, 실제/예시를 포함한 identity. unique 충돌은 행 오류로 보존.',
 'Approval':'services: 사건 잠금, 현재 대기 중복 차단, 처리 완료 불변, 해시 버전 2 재검증. content_type/object_id는 논리 참조로 DB FK가 아니다.',
}
def clean(v): return str(v).replace('|','\\|').replace('\n',' ')
def default(f):
 if f.auto_created and f.primary_key:return 'DB 자동 증가'
 if getattr(f,'auto_now_add',False):return '생성 시 now'
 if getattr(f,'auto_now',False):return '저장 시 now'
 if f.default is NOT_PROVIDED:return '없음'
 return getattr(f.default,'__name__',repr(f.default)) if callable(f.default) else repr(f.default)
def ftype(f):
 return f.get_internal_type()+(f'({f.max_length})' if getattr(f,'max_length',None) else '')

out=['# MedWatch PMS ERD','', '## 도메인 개요','', '사건은 제품·UDI·선택 LOT를 참조하며 위험평가, 이상사례, CAPA, 보고서, 리콜 및 업무를 모은다. 규칙은 원문 청크를 인용하는 버전으로 관리하고 사건 적용은 당시 스냅샷을 남긴다. 외부 CSV 분석 레코드는 제품 문자열을 사용하며 내부 제품 FK로 자동 연결하지 않는다.', '', '기존 구현: 아래 물리 관계 중 두 History 테이블을 제외한 모델. 이번 추가: RiskAssessmentHistory·RegulatoryReportHistory, 삭제 보호, 제약과 조회 인덱스. 향후 제안: 제출 접수증 전용 엔터티, 안전 신호의 JSON 증거·조치 연결을 명시적 FK 연결 테이블로 전환, 범용 승인 대상의 명시 FK 전환. 제안은 아래 ERD에 구현처럼 표시하지 않았다.', '', '## 물리 ERD 표기','', '`||` 필수 1, `o|` 선택 0..1, `o{` 선택 0..N. 자식의 FK null 여부가 부모 쪽 선택성을 결정한다. OneToOne은 자식 쪽 0..1이다. 모든 자식 FK 관계의 부모는 자식을 갖지 않을 수 있다. N:M은 실제 중간 테이블의 두 1:N 관계로 표시한다. 필드는 실제 DB column이며 PK/FK/UK를 표시한다. 타입은 Django 물리 필드 타입이며 DB별 SQL 매핑은 데이터 사전에 적었다. 반복 엔터티는 같은 테이블이다.', '', 'Approval.content_type/object_id, AuditLog.object_type/object_id, SafetyReview.links, 신호 snapshot의 evidence IDs는 논리 참조이며 FK 선을 그리지 않았다. family_key도 RuleFamilyLock.key에 대한 FK가 아니다. 제출은 RegulatoryReport.status=SUBMITTED일 뿐 별도 Submission 모델은 없다.']
for title,names in GROUPS:
 selected=[ALL[n] for n in names.split()]
 for m in list(selected):
  for f in m._meta.local_many_to_many:
   selected.append(f.remote_field.through)
 refs=[]
 for m in selected:
  for f in m._meta.local_fields:
   if f.is_relation and f.related_model not in selected and f.related_model not in refs: refs.append(f.related_model)
 out+=['',f'## {title}','','```mermaid','erDiagram']
 for m in selected+refs:
  out.append(f'    {m._meta.db_table} {{')
  for f in m._meta.local_fields:
   if m in refs and not f.primary_key: continue
   markers=[]
   if f.primary_key:markers.append('PK')
   if f.is_relation:markers.append('FK')
   if f.unique and not f.primary_key:markers.append('UK')
   out.append(f'        {f.get_internal_type()} {f.column}'+(' '+','.join(markers) if markers else ''))
  out.append('    }')
 for m in selected:
  for f in m._meta.local_fields:
   if f.is_relation:
    parent='|o' if f.null else '||';child='o|' if f.one_to_one else 'o{'
    out.append(f'    {f.related_model._meta.db_table} {parent}--{child} {m._meta.db_table} : "{f.column}"')
 out+=['```']
Path('docs/erd.md').write_text('\n'.join(out)+'\n',encoding='utf-8')

out=['# 데이터 사전','', 'scripts/build_data_model_docs.py로 실제 등록 모델 메타데이터에서 재생성한다. DB 필수는 NOT NULL 기준이며 blank=True(폼 선택)와 구분한다. 빈 문자열 허용은 NOT NULL과 별개다. 기본값은 Django 기본값이며 별도 DB default가 없다. BigAutoField는 기존 PK를 유지한다. FK/OneToOne은 기본 인덱스, unique는 고유 인덱스를 수반한다. PostgreSQL/SQLite의 SQL 타입은 다를 수 있다.', '', '개인정보 기준: 사용자 계정·이메일·IP는 개인정보, 익명 환자·사건 본문·증빙·분석 원문·스냅샷은 재식별 가능 민감 자료로 취급한다. FK actor/assignee/reporter 등도 계정 추적 정보다. 인증 password는 해시다. 원문 파일은 DB 경로와 저장소 객체를 별도 보존한다.', '', 'DB 보장과 서비스 검증은 각 모델에서 구분한다. QuerySet.update/bulk_create/raw SQL은 모델 save·clean·이력 생성을 우회한다. 운영 쓰기는 문서화한 서비스/폼/API만 허용한다. 일반 Django save가 full_clean을 호출한다고 가정하지 않으며 공통 save는 관계 검증을 명시 호출한다.']
throughs=[]
for model in MODELS+AUTH:
 for field in model._meta.local_many_to_many:
  if field.remote_field.through not in throughs: throughs.append(field.remote_field.through)
for m in MODELS+AUTH+throughs:
 out+=['',f'## {m.__name__} — `{m._meta.db_table}`','',PURPOSE.get(m.__name__,'Django 기본 인증·역할 권한 테이블')+'.', '', '민감도: '+('민감 자료 포함; 본문·JSON·파일 접근 제한 필요.' if m.__name__ in SENSITIVE else '계정 FK·연락처는 개인정보; 나머지는 업무 메타데이터.'), '', '변경/보존: '+('추가 이력으로 관리. 서비스는 덮어쓰지 않는다. DB 관리자·bulk SQL까지 불변을 강제하는 트리거는 없다.' if m.__name__ in IMMUTABLE else '현재 상태는 수정 가능. 위험평가·규제보고는 이번 추가 History, 그 밖의 업무 변경은 해당 이력/감사 서비스 참조. 자동으로 모든 쓰기 경로를 감사하지는 않는다.'), '', '| 필드(DB column) | Django 타입 / SQLite SQL 타입 | DB 필수 / 폼 blank | 기본값 | 관계 / on_delete |','|---|---|---|---|---|']
 for f in m._meta.local_fields:
  rel=(f'{f.related_model._meta.db_table}.{f.target_field.column} / {f.remote_field.on_delete.__name__}' if f.is_relation else '—')
  out.append('| '+ ' | '.join(map(clean,[f'{f.name} ({f.column})'+(' PK' if f.primary_key else ''),ftype(f)+' / '+str(f.db_type(connection)),'예' if not f.null else '아니오',default(f),rel])).replace('| 예 |','| 예 / '+str(f.blank)+' |').replace('| 아니오 |','| 아니오 / '+str(f.blank)+' |')+' |')
 for f in m._meta.local_many_to_many:
  out+=['',f'N:M `{f.name}` → `{f.related_model._meta.db_table}`, 실제 중간 테이블 `{f.remote_field.through._meta.db_table}`, 두 필수 FK 및 쌍 unique.']
 out+=['','DB 제약:', '']
 simple=[f.name for f in m._meta.local_fields if f.unique]
 out.append('- PK/필드 unique: '+(', '.join(simple) or 'PK 외 없음'))
 out.append('- unique_together: '+repr(m._meta.unique_together))
 positive=[f.name for f in m._meta.local_fields if f.get_internal_type().startswith('Positive')]
 if positive: out.append('- 타입의 암묵적 DB 비음수 CHECK: '+', '.join(positive))
 for c in m._meta.constraints:out.append('- '+clean(repr(c)))
 out+=['','명시 인덱스: '+('; '.join(f'{i.name}: {i.fields}' for i in m._meta.indexes) or '없음 (FK/unique 인덱스는 별도 존재)'), '', '앱/서비스 조건: '+SERVICES.get(m.__name__,'필드 validator/choices와 호출 서비스의 권한 검사. choices 자체는 별도 CheckConstraint가 없는 한 DB 제약이 아니다.')]
 for f in m._meta.local_fields:
  if f.choices:out.append(f'- `{f.name}` 허용값: '+', '.join(str(k) for k,v in f.choices))
Path('docs/data-dictionary.md').write_text('\n'.join(out)+'\n',encoding='utf-8')
print(f'Generated {len(MODELS)} PMS models, 8 physical diagrams, auth references.')
