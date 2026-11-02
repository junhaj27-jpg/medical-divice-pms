from pathlib import Path
p=Path('IMPACT_APPROVAL_GUIDE.md');s=p.read_text(encoding='utf-8').replace('CI의 별도 postgres 작업은 PostgreSQL 16을 띄워 전체 테스트와 독립 연결 `TransactionTestCase`를 실행한다. SQLite에서는 4개 PostgreSQL 전용 테스트가 명시적으로 skip된다.','CI의 별도 postgres 작업은 PostgreSQL 16에서 전체 테스트와 독립 연결 `TransactionTestCase`를 실행하도록 구성되어 있다. 이번 로컬에서 원격 CI 실행 성공은 확인하지 않았다. SQLite에서는 PostgreSQL 전용 6개를 명시적으로 skip하며 현재 실제 결과는 VALIDATION_REPORT.md를 따른다.');p.write_text(s,encoding='utf-8')
p=Path('docs/development-plan.md');s=p.read_text(encoding='utf-8').replace('우선 후속: (1) 기존 사건의 과거 기본 중대성 False를 재확인하는 이관 정책과 권한 보존 ETL, (2) 대용량 수집 비동기 처리·목록 페이지네이션, (3) 이미 구현된 프로세스 격리를 유지한 실제 승인 공급자별 연동 검증, (4) 분석 PDF 보관/서명 및 운영 권한·HTTPS·비밀키 설정.','갱신된 후속: (1) 명시적 중대성 확인·선택 스냅샷은 구현됨, 기관별 이관 정책 검토는 후속, (2) 영향 입력·내부 사건 선택 페이지네이션은 구현됨, 대용량 비동기 수집은 후속, (3) 이미 구현된 프로세스 격리를 유지한 실제 승인 공급자별 연동 검증, (4) 분석 PDF 보관은 구현됨, 전자서명은 이번 범위 제외, 운영 권한·HTTPS·비밀키 설정 실증은 후속.');p.write_text(s,encoding='utf-8')
p=Path('REGULATORY_GUIDE.md');s=p.read_text(encoding='utf-8');s+='''

## 2026-11-01 입력·분석 확장

규정 개정 영향 입력은 `/rules/impacts/`의 사건별 선택 행으로 제공한다. 관할·UTC 오프셋 포함 기준 시각·확인 사유를 확인하며 기존 날짜에서 인지 시각이나 관할을 자동 추정하지 않는다. 입력과 분석 생성은 실제 기한 변경이 아니며 기존 승인·시행·명시 재적용 검증을 유지한다.

내부 사건의 분석 가져오기와 중대성 확인은 `/analysis/internal/`에서 RA_QA·ADMIN만 수행한다. 중대성 확인은 의료적 인과관계나 법정 보고 의무의 확정이 아니다. 원본 bool False는 미상으로 시작하며 별도 근거·담당자·시각을 보존한다. 해당 확인 변경은 승인 무결성 검사와 재승인 절차에 포함한다. 분석 보고서는 보고 건수이며 분모 없는 발생률·위험도를 제공하지 않는다. 절차는 [격리 시연 안내](docs/analysis-extensions-demo.md)를 참조한다.
''';p.write_text(s,encoding='utf-8')
