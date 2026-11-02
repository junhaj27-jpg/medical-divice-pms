from pathlib import Path
p=Path('README.md');s=p.read_text(encoding='utf-8');s=s.replace('최종 로컬 전체 검사: 171개 중 167개 통과, PostgreSQL 전용 4개 skip. 마지막 재승인 수정 후 검증은 에이전트 사용량 한도로 총괄이 수행했습니다. 상세 결과와 한계는 검증 보고서에 기록했습니다.','이 절은 2026-10-30 작업 기록입니다. 최신 실행 결과·skip·미검증 항목은 [VALIDATION_REPORT.md](VALIDATION_REPORT.md)를 기준으로 확인하세요.');s=s.replace('| 자동화 검증 | Django 테스트 113개 (SQLite에서 PostgreSQL 전용 4개 제외), system check, 마이그레이션 검사 |','| 자동화 검증 | 실제 실행 결과와 환경별 skip은 [검증 보고서](VALIDATION_REPORT.md) 참조 |');s=s.replace('설치 시 `python manage.py migrate`로 0008을 적용하세요.','설치 시 백업 후 `python manage.py migrate`로 의존성 그래프의 최종 leaf까지 적용하세요.');s='''# 2026-11-01 분석·규정 영향 입력 확장

- `/rules/impacts/`: 사건별 행 입력, 관할·오프셋 포함 기준 시각·확인 사유, 검색·필터·20건 페이지, 명시적 공통 값 적용 확인과 중복 제출 방지. 분석만으로 기한은 바뀌지 않습니다.
- `/analysis/internal/`: RA_QA·ADMIN 선택 사건 미리보기 후 최소 필드 스냅샷 가져오기. 출처 구분·원본 내용 해시·버전·담당자·시각·정정 연결을 보존하며 기본 집계는 최신 내부 버전만 사용합니다. CSV와 자동 병합하지 않습니다.
- 기존 `AdverseEvent.serious=False`는 비중대로 확정하지 않습니다. 별도 중대성 확인 이력과 승인 무결성 검사를 추가했습니다.
- `/analysis/`: 비공개 서버 PDF 버전 보관, 생성 조건·비교 기간·원본/정제 범위 내용 해시·생성 시점 검토 이력, 권한 검사·다운로드 감사. SHA-256은 내용 비교용이며 전자서명이 아닙니다.
- 기존 AI 프로세스 격리(`ai_boundary.py`, `ai_worker.py`)는 이미 구현되어 있습니다. 외부 AI 연결은 필수가 아닙니다.

최신 [실제 검증 결과](VALIDATION_REPORT.md), [PowerShell 설치·실행·격리 시연](docs/analysis-extensions-demo.md), [운영 절차](OPERATIONS.md)를 확인하세요. 버전별 과거 테스트 수를 현재 검증 완료 근거로 사용하지 않습니다.

'''+s;p.write_text(s,encoding='utf-8')
p=Path('docs/development-plan.md');s=p.read_text(encoding='utf-8');s=s.replace('프로세스 격리 timeout은 후속이다.','프로세스 격리 timeout은 pms/ai_boundary.py와 pms/ai_worker.py에 이미 구현되어 있다.');s=s.replace('(3) AI 어댑터 프로세스 격리 timeout 및 실제 승인된 공급자별 연동 검증','(3) 이미 구현된 프로세스 격리를 유지한 실제 승인 공급자별 연동 검증');s=s.replace('기존 사건을 분석 코호트로 연결하는 권한 보존 ETL, 대용량 비동기 수집, 분석 PDF의 서버 보관·서명, 운영 개인정보 정책과 기관별 규제 검증은 후속.','내부 사건 선택 스냅샷과 분석 PDF 서버 버전 보관은 2026-11-01에 추가했다. 대용량 비동기 수집, 운영 개인정보 정책과 기관별 규제 검증은 후속이며 전자서명은 이번 범위에서 제외한다.');s='''# 2026-11-01 구현 현황 갱신

지정 폴더 아래 work/medical-divice-pms 저장소를 확인했다. 시작 HEAD는 14f4390이며 README·모델·서비스·workflow·테스트와 0011/0012 등 기존 미커밋 변경을 보존했다. 별도 feature/pms-analysis-snapshots-20261101 브랜치에서 확장한다. AGENTS.md는 확인한 저장소·작업 상위 경로에서 발견되지 않았다.

| 항목 | 결과 | 구현 |
|---|---|---|
| AI 프로세스 격리 | 기존 구현 유지 | ai_boundary.py가 ai_worker 프로세스 종료·timeout·입출력 제한 적용 |
| 영향 분석 서비스·승인 무결성 | 기존 구현 유지·확장 | 오래된 분석 차단, 적용/제외 사유, 연결 업무·알림 dedupe, 승인 내용 해시 |
| 영향 분석 행 입력 | 추가 | impact_views.py, impact_list.html: 검색·필터·20건 페이지·행 검증·공통 값 명시 확인·UTC 저장·제출키 |
| 내부 사건 코호트 | 추가 | internal_cohort.py: 미리보기 해시 검증, 원본 사건 잠금, 출처 분리, 최소 필드·확인 중대성·정정 체인·최신 집계 |
| 분석 PDF 버전 보관 | 추가 | analysis_archive.py: 기존 사건 PDF의 비공개 FileField·내용 snapshot·행 잠금 버전·감사 패턴 사용 |
| 마이그레이션 | 추가만 | 두 0008 분기는 기존 0011에서 병합, 0012 뒤 0013·0014 추가. 기존 파일 이름·의존성 변경 없음 |
| 회귀·동시성 | 확장 | test_analysis_extensions.py, test_impact_rows.py, test_concurrency.py. 실행 결과는 ../VALIDATION_REPORT.md |
| 재현 가능한 검증·시연 | 추가 | scripts/validate_isolated.py, demo_analysis_extensions.py, analysis-extensions-demo.md |

남은 범위: 실제 PostgreSQL 동시성 실행, 대용량 비동기 작업, 운영 ClamAV·TLS·백업복원 실증, 승인된 외부 AI 공급자 연동 검증. 전자서명·외부 불변 저장소는 미구현이며 이번 범위 제외. 법정 기한·인과관계·규제 적합성을 확정하지 않는다.

아래는 당시 작업 기록이며 최신 테스트 수와 구현 상태는 위 표 및 VALIDATION_REPORT.md를 우선한다.

---

'''+s;p.write_text(s,encoding='utf-8')
p=Path('OPERATIONS.md');s=p.read_text(encoding='utf-8');s+='''

## 2026-11-01 분석 스냅샷·PDF 운영

적용 전 DB와 PRIVATE_MEDIA_ROOT를 함께 백업한다. 기존 0008 두 분기는 0011에서 합류하며 번호가 같다는 이유로 변경하지 않는다. 추가 0013은 분석 원본 연결·정정 체인·중대성 확인·PDF 보관 테이블과 유일 제약, 0014는 영향 분석 제출키를 추가한다. 기존 사건·CSV·승인·파일을 삭제하지 않는다. 검증은 원본 DB를 읽기 전용으로 복사한 격리 DB와 별도 미디어에서만 수행한다.

내부 사건 가져오기는 RA_QA·ADMIN만 수행하며 대상·필드·건수를 확인한 서명 토큰은 30분간 유효하다. 원본이 바뀌면 다시 미리보기 한다. 원문·환자정보를 복제하지 않는다. 명시적 중대성 확인은 사유·담당자·시각을 append-only 이력으로 보존하며 승인 판단 자료에 포함된다. 확인 사유에 환자정보나 원문을 복사하지 않는다. 과거 승인·검토는 덮어쓰지 않고 재승인을 요청한다.

내부 스냅샷은 source_case/source_hash 유일 제약과 사건 행 잠금으로 중복을 막는다. 정정본은 supersedes로 연결하고 기본 집계는 최신 버전만 사용한다. 직접 SQL·bulk 쓰기는 이 규약과 승인 자료 잠금 규약을 따라야 한다. 동일 원본 버전 재실행은 새 파일·행을 만들지 않는다. CSV와 내부 출처는 별도 namespace이고 자동 사건 병합은 없다.

PDF는 기존 사건 보고서와 동일한 비공개 MEDIA_ROOT 아래 analysis-reports에 보관한다. 웹서버에서 media alias를 제공하지 않는다. 같은 정규화 필터는 같은 보고서 ID를 사용하고 재생성마다 다음 버전을 생성한다. 파일·생성 당시 검토·필터·비교 기간·집계 기준·원본/정제 범위 해시를 보존한다. 권한 검사 후 내용 해시를 확인하고 다운로드 감사 기록을 남긴다. 기존 format=pdf URL도 보관 버전을 생성한다. 새로운 화면은 CSRF 보호 POST 버튼을 사용한다.

한글 TTF 미설정·파일 불일치 오류는 안내하고 분석 조회를 유지한다. SHA-256은 DB 안 내용 비교 수단이며 전자서명·DB 관리자 변조 방지·외부 불변 보증이 아니다. 보관 파일과 DB는 함께 백업한다. STATIC_ROOT를 별도로 지정할 수 있으며 검증 시 공개 정적 파일 경로까지 격리한다.

설치·실행·운영형 check --deploy·PostgreSQL 전용 검증 명령은 [격리 시연 안내](docs/analysis-extensions-demo.md), 실제 실행 범위는 [VALIDATION_REPORT.md](VALIDATION_REPORT.md)를 따른다. CI 파일 존재를 실행 성공으로 기록하지 않는다.
''';p.write_text(s,encoding='utf-8')
p=Path('IMPACT_APPROVAL_GUIDE.md');s=p.read_text(encoding='utf-8').replace('입력 UI는 사건번호별 JSON이며 대량 사건은 페이지네이션·비동기 분석 확장이 필요하다.','입력 UI는 2026-11-01부터 사건별 행 폼이며 검색·필터·페이지네이션을 제공한다. 대량 비동기 분석은 후속이다.');s+='''

## 행 입력 화면과 중대성 확인 확장 (2026-11-01)

`/rules/impacts/`는 현재 페이지의 선택 사건만 분석한다. 사건번호·제목·제품·최근 적용 규칙·현재 기한을 확인하고 관할·UTC 오프셋 포함 기준 일시·확인 사유를 직접 입력한다. 공통 값은 대상 선택과 명시적 확인 체크 후 적용한다. 기존 날짜에서 인지 시각이나 관할을 추정하지 않는다. 사용자 표시 시간대와 UTC 저장 기준을 구분하고 규칙 시간대의 날짜 경계를 검증한다. 입력 오류는 해당 사건 행에 표시한다. 분석 저장은 적용이 아니며 기존 분석 상세의 명시 재적용·적용 제외 절차를 유지한다.

분석용 중대성 확인은 별도 이력으로 저장하며 원본 AdverseEvent.serious를 변경하지 않는다. 승인 snapshot의 seriousness_confirmation 범위가 바뀌면 기존 대기/완료 승인 사용을 차단하고 기존 재승인 절차를 따른다. 기존 확인 이력이 없는 사건의 승인 해시는 그대로 유지한다. 법정 중대성이나 의료적 인과관계를 시스템이 확정하지 않는다.
''';p.write_text(s,encoding='utf-8')
