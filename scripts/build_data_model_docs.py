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
("RA 1단계: 규제 프로필·요구사항·인허가·갱신·제출 패키지", "RegulatoryProfile RARequirement MarketingAuthorization AuthorizationEvent SubmissionPackage"),
("RA 2단계: 제품 변경·제품 버전·통제 문서·라벨", "ProductRevision ProductChange ControlledDocument LabelVersion"),
("RA 3단계: 제품 위험관리·안전 정보·현장 조치·공급자", "RiskCriteria ProductRisk SafetyInformation FieldSafetyAction FieldActionRecipient FieldActionContact FieldActionEvaluation SupplierRecord SupplierMaterial"),
("RA 4단계: 교육·감사·정기 검토·보존 정책", "TrainingRequirement TrainingAssignment AuditPlan AuditFinding AuditPackage ManagementReview ManagementDecision RetentionPolicy"),
 ('RA 실무 1: GMP 문서 계층·양식·정정', 'QualityDocument QualityRecord'),
 ('RA 실무 2: 품질시스템 밸리데이션', 'QualityValidation ValidationRequirement ValidationCase ValidationRun'),
 ('RA 실무 3: 회의록 후보·DHF', 'DHFProject MeetingSource MeetingCandidate DesignTrace DHFBaseline'),
 ('RA 실무 4: 소프트웨어 변경심사', 'SoftwareChangeReview TechnicalSection ReviewResponse'),
 ('RA 실무 5: 사이버보안', 'SecurityInventory SecurityFinding SecurityReview'),
]
MODELS=list(apps.get_app_config('pms').get_models())
AUTH=[apps.get_model('auth',x) for x in ('User','Group','Permission')]
ALL={m.__name__:m for m in MODELS+AUTH}
PURPOSE=dict(zip('Profile Manufacturer MedicalDevice UDI ProductLot CustomerComplaint PatientAnonymousInfo AdverseEvent RiskAssessment CAPA Recall RecallTarget RegulatoryReport Attachment Approval AuditLog Notification AssistantConversation AssistantMessage WorkTask TaskHistory CAPAEvaluation BusinessPartner RecallRecipient RecoveryEntry RecallContact ReportingRule RuleApplication ReportArtifact LoginBucket RegulationDocument RegulationChunk RuleCitation RulePreview RuleChange RuleFamilyLock RegulatoryImpact ImpactReview AnalysisImport AnalysisRecord AnalysisReview AnalysisReviewHistory SafetySignal SafetyReview RiskAssessmentHistory RegulatoryReportHistory'.split(),['사용자 역할·시간대','제조사','제품','UDI 식별자','생산 LOT·일련번호','PMS 사건','사건별 익명 환자 정보','사건별 이상사례 판단','현재 위험평가','시정·예방 조치','회수 계획·상태','회수 대상 LOT','규제보고 판단·제출 상태','검사된 증빙 파일 참조','승인 요청·결정·무결성 스냅샷','행위 감사','사용자 알림','RA 상담 세션','상담 내용','사건 담당 업무','업무 변경 이력','CAPA 효과성 평가·증빙','거래처','거래처·LOT·단위별 회수 대상','추가 회수 원장','회수 연락 이력','규칙 버전','사건 규칙 적용 스냅샷','버전별 보고 PDF·묶음 해시','로그인 제한 버킷','규정 원본·검토','원문 청크','규칙 항목과 원문 인용','기한 미리보기','규칙 변경 이력','규칙 계열 직렬화 잠금','개정 영향 분석','사건별 영향 처리','분석 원본 CSV 수집','출처별 정규화 레코드','분석 신호 검토','분석 검토 이력','내부 사건 안전 신호','안전 신호 검토 이력','이번 추가: 실제 저장 시점 위험평가 변경 기록','이번 추가: 실제 저장 시점 규제보고 변경 기록']))
PURPOSE.update({
 'RegulatoryProfile':'제품·관할·조직 역할의 적용 범위와 근거',
 'RARequirement':'근거 조항·활동·증빙·충족 및 정기 검토 매트릭스',
 'MarketingAuthorization':'수동 확인 인허가·갱신과 외부 상태 기록',
 'AuthorizationEvent':'허가 신청·보완·승인 등 실제 기록 시점의 상태 이력',
 'SubmissionPackage':'허가별 제출 파일·접수 증빙·제품 버전의 승인 스냅샷',
 'ProductRevision':'제품 구성 버전과 이전 버전 관계',
 'ProductChange':'제품 변경 전후·영향 평가·추가 제출 판단·시행 확인',
 'ControlledDocument':'SOP 등 내부 통제 문서의 개정·시행본',
 'LabelVersion':'제품·관할·언어별 라벨/설명서와 번역 검토',
 'RiskCriteria':'제품별 위험 추정·수용 기준 버전',
 'ProductRisk':'위해·통제 검증·잔여위험·편익 위험 판단',
 'SafetyInformation':'외부 안전성 정보 수동 수집·연관성 및 보고 검토',
 'FieldSafetyAction':'승인 안내문 기반 고객 안내·현장 수정·기존 리콜 연결',
 'FieldActionRecipient':'비회수 조치의 거래처·LOT 대상과 완료 수량',
 'FieldActionContact':'현장 조치의 수동 후속 연락 사실',
 'FieldActionEvaluation':'현장 조치 효과·근거의 추가 평가 기록',
 'SupplierRecord':'기존 거래처의 공급자·제조소·위탁 범위 및 조직 평가 기준',
 'SupplierMaterial':'공급자 문서 버전·유효기간·미비·변경 영향',
 'TrainingRequirement':'시행 문서 버전별 역할 교육과 명시적 승인 제한',
 'TrainingAssignment':'대상자별 교육 시도·수료 증빙·효과 판단',
 'AuditPlan':'업무 감사·실사 일정·범위·기준; 시스템 AuditLog와 별도',
 'AuditFinding':'관찰·지적 분류·답변·CAPA·효과 확인',
 'AuditPackage':'감사별 수동 제출 자료 버전과 승인 스냅샷',
 'ManagementReview':'기간 보고 건수와 캡처 시점 RA/PMS 현황 스냅샷',
 'ManagementDecision':'경영 검토 결정·담당·후속 기한 및 결과',
 'RetentionPolicy':'조직의 근거 기반 보존·파기 검토 설정; 자동 삭제 없음',
})
PURPOSE.update({
 'QualityDocument':'시행 통제 문서의 품질매뉴얼·절차·지침·양식 계층 및 템플릿 정의',
 'QualityRecord':'정확한 양식 버전의 입력 값·기한과 원기록 정정 연결',
 'QualityValidation':'품질경영용 시스템 버전의 영향·밸리데이션 계획·보고·재검토',
 'ValidationRequirement':'품질시스템 사용자 요구사항과 위험·통제',
 'ValidationCase':'승인 및 실행에 고정된 시험 케이스 버전',
 'ValidationRun':'실행 결과·일탈·면제·재시험과 검사된 증빙',
 'DHFProject':'규제 프로필의 제품 출시 버전별 설계 프로젝트',
 'MeetingSource':'검사된 회의록 파일과 프로젝트',
 'MeetingCandidate':'원문 위치·발췌·문서/파일 후보와 확인한 추적 행',
 'DesignTrace':'요구사항·설계 출력·제품 위험·검증 문서·변경·출시 연결',
 'DHFBaseline':'DHF 기준 시점의 연결·검토 스냅샷',
 'SoftwareChangeReview':'담당자 변경 분류와 기능·알고리즘·사용 목적 비교',
 'TechnicalSection':'기술문서 목차별 준비 상태·담당자·증빙',
 'ReviewResponse':'심사 질의·답변·이전 답변과 수동 제출 패키지',
 'SecurityInventory':'출시 버전의 자산·외부 인터페이스·수동 SBOM 목록',
 'SecurityFinding':'출처·확인일·영향·조치·잔여위험 근거',
 'SecurityReview':'출시 버전 보안 시험·증빙·미해결 항목·담당자 승인',
})

IMMUTABLE={'RiskAssessmentHistory','RegulatoryReportHistory','TaskHistory','CAPAEvaluation','RecoveryEntry','RecallContact','RuleApplication','ReportArtifact','RuleChange','SafetyReview','AnalysisReviewHistory','AuthorizationEvent','FieldActionContact','FieldActionEvaluation'}
SENSITIVE={'PatientAnonymousInfo','AdverseEvent','CustomerComplaint','Attachment','RiskAssessment','RiskAssessmentHistory','RegulatoryReport','RegulatoryReportHistory','AnalysisImport','AnalysisRecord','AssistantMessage','ReportArtifact','SafetySignal','AnalysisReview'}
SENSITIVE.update(m.__name__ for m in MODELS if m.__module__ in ('pms.ra_models','pms.ra_operations_models'))
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
 'WorkTask':'사건 또는 RA 프로필 중 정확히 하나. 사건/조치 일치, 활성 담당자, STAFF 사건 접수자 또는 본인 배정 RA 업무만. RA 범위 재이동 금지. save_task에서 권한·시각·이력.',
 'CAPA':'종결 시 최신 PASS 평가와 결과·기준·예정일 일치; close_capa에서 연결 업무 완료.',
 'CAPAEvaluation':'평가 서비스는 미래일 차단, 동일 사건 PASSED 증빙만 연결. m2m pre_add도 동일 조건 검사. 본문 수정 금지, 최초 후속 업무 연결 허용.',
 'ReportingRule':'regulatory: 역할·분리 승인·원문 인용·시행일·범위 충돌·낙관적 토큰 및 계열 잠금. 직접 save는 제한.',
 'RuleApplication':'서비스는 시행 규칙·사건 조건·예시 분리·미리보기·직전 적용 토큰 검사. 재적용은 새 이력이다.',
 'ImpactReview':'서비스의 분석 토큰·사유·권한 검사; 모델은 업무·적용 사건·규칙 연결 검사.',
 'SafetySignal':'safety.detect: scope+필터+규칙 버전+제품·LOT로 key 해시. review_signal: 활성 전문 역할, 증거 사건에 속한 CAPA·리콜 연결.',
 'AnalysisRecord':'analysis.ingest: CSV·날짜·내용 검증, 실제/예시를 포함한 identity. unique 충돌은 행 오류로 보존.',
 'Approval':'services: 사건 잠금, 현재 대기 중복 차단, 처리 완료 불변, 해시 버전 2 재검증. content_type/object_id는 논리 참조로 DB FK가 아니다.',
}
SERVICES.update({
 'Attachment':'사건 또는 RA 프로필 하나만 지정. RA 증빙은 범위·파일 덮어쓰기 금지. 기존 검사·파일 해시·비공개 다운로드 재사용.',
 'RegulatoryProfile':'범위는 변경 불가. 적용·비적용은 출처·확인자·확인일·사유 요구. 법적 판단은 담당자 입력.',
 'RARequirement':'원문·청크 버전 일치, 실제/예시 분리, 적용·충족 사유와 검토일 검증.',
 'MarketingAuthorization':'승인 기록은 번호·기관·확인일·출처 필요. 상태 변경은 AuthorizationEvent. 만료일이나 갱신주기 자동 추정 없음.',
 'SubmissionPackage':'프로필·허가·제품 버전·변경·파일 일치, 승인 목록/해시 고정. ZIP 다운로드 시 해시 재검증.',
 'ProductRevision':'같은 프로필의 제품 버전·이전 버전. 승인된 내용은 서비스에서 수정 금지.',
 'ProductChange':'전후 제품 버전, LOT, 6개 영역 영향 판단, 제출 판단 근거, 승인 해시·업무 완료 검증 후 실제 시행 기록.',
 'ControlledDocument':'본문 또는 검사 통과 파일, 버전 계열, 시행일·대체 버전·현재 시행본 검사. 승인 후 새 개정 필요.',
 'LabelVersion':'제품·UDI·LOT·문서 버전·현장 조치 범위 일치. 담당 번역 검토와 표시 체크리스트 없으면 승인 차단.',
 'RiskCriteria':'제품별 수용 기준의 담당자 승인, 사건 위험 점수 자동 적용 없음.',
 'ProductRisk':'승인된 수용 기준, 잔여위험·편익 판단·검증 파일. PMS 관계의 제품/예시 범위 검사.',
 'SafetyInformation':'URL/외부 식별자 중복 방지. 보고·연관성 수동 판단과 이유 보존.',
 'FieldSafetyAction':'승인된 안내문·효과 기준, 회수는 기존 원장. 최신 효과 평가·대상·업무 검토 후 종결.',
 'FieldActionRecipient':'회수 조치는 금지. 승인된 대상 계획 고정, 시행 중 완료일·근거와 완료 누계를 기록.',
 'FieldActionContact':'시행 중 비회수 조치의 수동 연락만 기록.',
 'FieldActionEvaluation':'시행 중 승인 조치에 검사 통과 증빙과 판정·근거를 추가.',
 'SupplierRecord':'기존 BusinessPartner/CAPA 재사용. 조직 기준과 명시 기한을 적용.',
 'SupplierMaterial':'자료 원본 증빙을 승인에 요구. 만료·재검토 일수 자동 생성 없음.',
 'TrainingRequirement':'시행 문서·역할. 승인 제한은 명시적으로 켠 신규 RA 승인에만 적용.',
 'TrainingAssignment':'수료일·검사 증빙·효과 PASS·다른 담당자 판단을 기록. 동일 기준의 재교육 시도 계보.',
 'AuditPlan':'업무 감사 일정과 종결. 모든 연결 지적 종결 필요.',
 'AuditFinding':'응답·효과 근거·기존 CAPA 종결을 확인하고 종결. 변경 전후 AuditLog.',
 'AuditPackage':'감사 범위 일치와 버전별 승인 파일 목록 보존, 외부 전송 없음.',
 'ManagementReview':'현재 캡처 상태와 기간 신규 보고 수 비교. 발생률 미산정·과거 상태 복원 없음.',
 'ManagementDecision':'실제 후속 결과·연결 업무 완료 후 종결.',
 'RetentionPolicy':'조직별 근거와 기간. 자동 삭제는 DB CHECK로 항상 비활성.',
})

SERVICES.update({
 'QualityDocument':'통제 문서 버전당 하나의 계층 정의. 상위 문서 수준과 프로필 검사. 승인된 템플릿에서 초안 생성.',
 'QualityRecord':'신규 작성은 시행 양식만 허용. 필수 값 누락 차단. 승인된 원기록 정정은 원래 양식과 별도 행에 기록.',
 'QualityValidation':'최신 시험 버전의 실행·증빙·승인 또는 사유가 있는 승인 면제 검증. 승인 당시 요구사항 추적 보존.',
 'ValidationCase':'요구사항별 버전 고유. 승인된 케이스에 실행 FK 고정.',
 'ValidationRun':'결과·케이스·일탈 변경 차단. 재시험은 새 실행. 면제 사유와 분리 승인.',
 'MeetingSource':'검사 통과 UTF-8 회의록. 프로젝트·첨부 unique. 같은 해시의 원본 중복 추출 차단.',
 'MeetingCandidate':'원문 행·발췌 보존. 승인 후보만 연결. 원본 행별 unique 및 확인 재요청 중복 방지.',
 'DesignTrace':'같은 프로필의 문서·위험·변경 및 동일 출시 버전 연결. 구버전 표시.',
 'DHFBaseline':'캡처 시점·연결·검토 상태를 저장하고 승인. CSV/PDF 내보내기.',
 'SoftwareChangeReview':'담당자 분류·근거, 준비된 시행 문서 및 동일 변경/출시 승인 패키지 요구. 제출 목록과 해시 보존.',
 'TechnicalSection':'변경심사별 목차 고유. 동일 프로필 문서·증빙 연결.',
 'SecurityInventory':'검사된 로컬 CSV 가져오기. 보안 적합성 판정 없음.',
 'SecurityFinding':'수동 점수 출처·버전과 확인일. 제품 범위 검사. 조치 검증 증빙과 잔여위험 판단.',
 'SecurityReview':'구성 목록·시험 결과·증빙·잔여위험 담당자 검토. 미해결 항목 조치 기록.',
})

def clean(v): return str(v).replace('|','\\|').replace('\n',' ')
def default(f):
 if f.auto_created and f.primary_key:return 'DB 자동 증가'
 if getattr(f,'auto_now_add',False):return '생성 시 now'
 if getattr(f,'auto_now',False):return '저장 시 now'
 if f.default is NOT_PROVIDED:return '없음'
 return getattr(f.default,'__name__',repr(f.default)) if callable(f.default) else repr(f.default)
def ftype(f):
 return f.get_internal_type()+(f'({f.max_length})' if getattr(f,'max_length',None) else '')

out=['# MedWatch PMS ERD','', '## 도메인 개요','', '사건은 제품·UDI·선택 LOT를 참조하며 위험평가, 이상사례, CAPA, 보고서, 리콜 및 업무를 모은다. 규칙은 원문 청크를 인용하는 버전으로 관리하고 사건 적용은 당시 스냅샷을 남긴다. 외부 CSV 분석 레코드는 제품 문자열을 사용하며 내부 제품 FK로 자동 연결하지 않는다.', '', '기존 구현: 아래 물리 관계 중 두 History 테이블을 제외한 모델. 이번 추가: RiskAssessmentHistory·RegulatoryReportHistory, 삭제 보호, 제약과 조회 인덱스. RA 확장: 1~4단계의 26개 기반 모델과 실무 추적 모델 17개, 기존 WorkTask·Attachment의 사건/RA 프로필 중 하나를 택하는 문맥, 프로필·국가·조직·버전·업무·증빙의 명시 관계. 각 영역의 구현 상태는 [RA 요구사항 매트릭스](ra-requirements-matrix.md) 참조. 향후 제안: 안전 신호의 JSON 증거·조치 연결을 명시적 FK 연결 테이블로 전환, 범용 승인 대상의 명시 FK 전환. 제안은 아래 ERD에 구현처럼 표시하지 않았다.', '', '## 물리 ERD 표기','', '`||` 필수 1, `o|` 선택 0..1, `o{` 선택 0..N. 자식의 FK null 여부가 부모 쪽 선택성을 결정한다. OneToOne은 자식 쪽 0..1이다. 모든 자식 FK 관계의 부모는 자식을 갖지 않을 수 있다. N:M은 실제 중간 테이블의 두 1:N 관계로 표시한다. 필드는 실제 DB column이며 PK/FK/UK를 표시한다. 타입은 Django 물리 필드 타입이며 DB별 SQL 매핑은 데이터 사전에 적었다. 반복 엔터티는 같은 테이블이다.', '', 'Approval.content_type/object_id, AuditLog.object_type/object_id, SafetyReview.links, 신호 snapshot의 evidence IDs는 논리 참조이며 FK 선을 그리지 않았다. family_key도 RuleFamilyLock.key에 대한 FK가 아니다. 기존 PMS 제출 상태와 별도로 RA 인허가에는 수동 기록 SubmissionPackage 버전이 있다. 외부 자동 제출 기능은 없다.']
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
print(f'Generated {len(MODELS)} PMS models, {len(GROUPS)} physical diagrams, auth references.')
