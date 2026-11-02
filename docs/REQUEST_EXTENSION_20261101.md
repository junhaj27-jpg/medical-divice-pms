# MedWatch 추가 개발 및 사용 안내 (2026-11-01)

## 시작 상태와 요구사항 대조

실제 Git 루트와 manage.py는 지정 시작 폴더 아래 `work/medical-divice-pms`다. 브랜치는 `feature/pms-analysis-snapshots-20261101`, 시작 HEAD는 `f0812ed`다. 시작 git status는 깨끗했고 원격 origin은 기존 `junhaj27-jpg/medical-divice-pms.git`을 유지했다. 저장소 및 확인한 상위 경로에 AGENTS.md는 없었다. 자동 pull/reset/clean, 원격 변경, push, 배포, 실제 제출, 외부 AI 호출을 하지 않았다.

| 요청 | 시작 분류 / 기존 기능 | 이번 추가 및 최종 한계 |
|---|---|---|
| 3 안전 신호 조사·조치 | 부분 구현: 조사·담당·기한·불필요 판단·CAPA/리콜·효과성·중복 요청 보존 구현 | 필요/보류 판단 추가, 재검토 후 과거 무조치 판단 재사용 차단, 행정 증빙의 리콜 효과 근거 사용 차단, 조사 기한을 기존 업무 이력에 반영, 현재 조치 상태·평가 표시. 미완료 조치 종결 예외는 제공하지 않음 |
| 4 제출·보완 | 부분 구현: 불변 제출 버전, 승인 해시, 제출 확인, 접수/보완/처리 상태, 비공개 첨부 구현 | 사유 있는 접수번호 정정 이벤트와 담당자 검증, 보완 담당/기한/처리 의견 변경 작업 추가. 정정 범위는 접수번호이며 제출 내용은 재승인·새 버전. 승인 규칙 기반 후속 기한 자동 계산은 미구현; 사유 있는 수동 기한을 지원 |
| 5 내부 PMS 정기 검토 | 부분 구현: 발생 기간·직전 기간·출처별 근거·확정 스냅샷 구현 | 내부·CSV 접수일 별도 집계·중대/비중대·기한 초과 추가, 확정 PDF/해시 보존·다운로드, 목록 페이지네이션. 이전 확정본 PDF를 소급 생성하지 않음. 대량 근거 최적화는 후속 |
| 6 영향 분석 행 UI | 구현 완료 (기존) | 사건 검색·필터·20건 페이지·행별 관할/오프셋 포함 시각/사유·선택 사건 공통 적용·오래된 분석 차단을 재사용. 관련 회귀 실행. 중복 재개발 없음 |
| 7 화면 품질 | 부분 구현 | 추적 화면의 페이지네이션·중요 작업 확인·처리 중 버튼/중복 클릭 차단, 현재 조치 상태 및 효과성 표시. 모든 API/대량 근거 목록의 일괄 최적화까지 완료했다고 주장하지 않음 |

기존 0015~0018 모델과 서비스·승인 무결성·비공개 증빙을 재사용한다. 신규 스키마는 `0019_periodic_pdf_archive`의 nullable PDF 바이트와 해시 두 필드만 추가한다. 기존 두 0008 분기는 0011에서 병합되어 있으므로 이름/의존성을 바꾸지 않았다. 확정 PDF는 비공개 DB에 보존되고 역할 검증 및 해시 확인 후 다운로드된다. 업로드 파일은 기존 검사/비공개 경로를 계속 사용한다.

## 사용 순서

1. `/safety/` → 신호 상세 → 조사·조치 추적: 담당자 ID, 조사 기한, 의견·근거·검사 통과 첨부를 입력한다. 필요/불필요/보류 판단은 작성자와 사유를 추가 이력으로 보존한다. 조사 기한은 입력 사용자 시간대의 해당 날짜 23:59:59이며 연결 WorkTask와 기존 TaskHistory에도 반영한다. 법정 기한 계산이 아니다.
2. 기존 조치는 동일 신호 근거 사건·제품에 속해야 한다. CAPA 초안은 명시적 요청 확인을 요구한다. 같은 요청 UUID는 재시도 결과를 반환하고 다른 내용 재사용은 거부한다.
3. 종결에는 모든 연결 조치 완료, CAPA 최신 적합 평가와 증빙, 리콜 효과 확인이 필요하다. 연결 조치가 없다면 가장 최근 유효 판단이 조치 불필요여야 한다. 새 조사·재검토·보류·조치 필요 이후 과거 불필요 판단만으로 종결할 수 없다. ADMIN도 미완료 조치 예외 종결을 할 수 없다. 효과 미흡은 기존 근거를 보존하며 재검토한다.
4. `/reports/{id}/tracking/`: 제출 기관·경로 계획 저장 → 사건 승인 → 현재 내용 PDF 생성 → 최초/추가/최종 제출본 준비. 보고서 생성은 제출이 아니다. 실제 제출은 담당자 확인·제출자·시간대 있는 실제 일시로 기록한다.
5. `/submissions/{id}/`: 접수/보완에는 검사 통과 ADMIN 용도 첨부를 사용한다. 담당자 ID와 수동 기한/사유를 기록할 수 있다. 보완 요청 상태에서는 `보완 담당·기한·처리 의견 변경`으로 담당자·기한·설정 사유·의견을 새 이벤트에 보존한다. `접수번호 정정`은 원본 이벤트를 보존하고 정정 대상 이벤트 ID·사유·새 값을 추가하며 상태와 과거 승인을 유지한다. 기관/경로/제출 내용 정정은 재승인된 새 제출본으로 처리한다. 접수는 기관 승인이나 법적 적합성을 의미하지 않는다.
6. `/pms-reviews/`: 제품·기간·실제/예시를 선택해 초안 생성 → 근거 목록과 한계 검토 → 의견/확정 확인 → 새 확정 버전 및 PDF 생성. PDF 설정 실패 시 확정 트랜잭션이 롤백된다. 기존 PDF 없는 확정본은 그대로 보존하며 새 초안을 검토·확정한다. 다운로드 `/pms-reviews/{id}/pdf/`는 RA_QA/ADMIN만 허용한다.
7. `/rules/impacts/`: 기존 행 입력 사용. 분석 저장만으로 사건 기한이 바뀌지 않는다. 명시적 검토·재적용 절차를 따른다.

승인 대상은 `approval_integrity.FIELDS`의 내용과 제출 기관/경로다. 접수번호·접수 확인·제출 후 행정 증빙·후속 기한 이벤트는 과거 승인의 내용 대상에 포함하지 않는다. 내용 변경은 기존 재승인 체계를 따른다. 감사에는 원문 대신 ID·종류·해시만 기록한다.

## PowerShell: 격리 검증과 시연

```powershell
Set-Location 'C:\Users\정준하\Documents\Codex\2026-10-30\https-github-com-junhaj27-jpg-medical\work\medical-divice-pms'
$py = '.\.venv\Scripts\python.exe'
# 이 체크아웃은 .venv Python 3.12.14 + .deps 의존성을 사용한다.
$env:PYTHONPATH = "$PWD\.deps"
$env:DB_ENGINE = 'sqlite'
$env:PDF_KOREAN_FONT = 'C:\Windows\Fonts\malgun.ttf'
# 반드시 존재하지 않는 새 경로 사용. 원본 DB에는 migrate/seed 하지 않는다.
& $py scripts/validate_isolated.py work/my-validation
# 기존 스키마 전진 검증은 설치된 DB의 읽기 전용 backup 사본에서만 수행
& $py scripts/validate_isolated.py work/my-forward-validation --installed-db work/request-baseline18.sqlite3
$env:DEMO_PASSWORD = '직접-정한-격리-시연용-비밀번호'
& $py scripts/demo_tracking_review.py work/my-demo
$env:SQLITE_PATH = "$PWD\work\my-demo\demo.sqlite3"
$env:PRIVATE_MEDIA_ROOT = "$PWD\work\my-demo\media"
$env:STATIC_ROOT = "$PWD\work\my-demo\static"
$env:DEBUG = 'True'
& $py manage.py runserver 127.0.0.1:8879 --noreload
```

시연 계정은 `demo-staff`, `demo-raqa`, `demo-admin`이다. 모두 위 DEMO_PASSWORD를 사용한다. 새 시연 DB에만 생성하며 모든 사건은 예시다. 신호 조사·보류와 확정 PDF를 준비하고 경로를 출력한다. 검증 스크립트는 check, makemigrations --check --dry-run, showmigrations --plan, migrate --noinput, test --noinput, collectstatic --noinput, compileall -q pms config scripts를 실행하며 로그와 results.json을 남긴다. 별도로 `git diff --check`를 실행한다. 환경변수를 해제하거나 셸을 닫기 전 실제 DB 운영 명령을 혼용하지 않는다.

## 검증과 후속

실제 실행 결과는 VALIDATION_REPORT.md의 이번 요청 절을 따른다. SQLite 스레드 테스트 통과를 PostgreSQL 행 잠금 통과로 해석하지 않는다. 운영 파일 검사기는 모의 테스트와 구분한다. 규제 적합성·법정 기한·발생률·인과관계는 확정하지 않는다.
