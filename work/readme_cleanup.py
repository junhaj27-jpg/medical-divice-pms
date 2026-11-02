from pathlib import Path
p=Path('README.md');s=p.read_text(encoding='utf-8')
s=s.replace('현재 Django 테스트는 다음을 포함한 **113개 시나리오**를 제공합니다. SQLite에서는 PostgreSQL 전용 4개를 건너뛰며 실제 행 잠금 검증은 별도 PostgreSQL CI에서 실행합니다.','Django 테스트는 다음 시나리오를 포함합니다. 현재 테스트 수·skip 사유·실제 PostgreSQL 실행 여부는 [검증 보고서](VALIDATION_REPORT.md)에서 확인하세요.')
lines=s.splitlines()
for i,line in enumerate(lines):
    if line.startswith('테스트는 기존 28개와 신규 26개'): lines[i]='당시 workflow 확장에서는 권한·기한 경계·중복 알림·CAPA·회수·파일 차단·PDF 버전·격리 복구를 검사했습니다. 현재 결과는 VALIDATION_REPORT.md를 따릅니다.'
    if line.startswith('`python manage.py migrate`로 0007을 적용하세요. 신규 33개'): lines[i]='규정 관리의 사용 순서·권한·AI 설정·계산 가정·운영 제한은 [RA 규정 관리 안내](REGULATORY_GUIDE.md)를 참고하세요. 설치 시 번호를 지정하지 않고 의존성 그래프 전체를 migrate합니다.'
    if line.startswith('변경 전 101개 테스트:'): lines[i]='이하 안전 신호·RA 근거 도우미는 이전 개발 기록입니다. 당시 테스트 수·미검증 범위를 현재 실행 결과로 해석하지 마세요. 최신 결과는 VALIDATION_REPORT.md를 따릅니다.'
    if line.startswith('전체 `manage.py test`: 117개'): lines[i]='이 절의 검증은 이전 안전 신호 개발 당시 기록입니다. 최신 전체 검사·운영형 설정 검사·브라우저 검사·환경 제한은 [VALIDATION_REPORT.md](VALIDATION_REPORT.md)를 기준으로 확인하세요.'
    if line.startswith('이번 변경은 실제 하위 검증 에이전트가'): lines[i]='현재 개발은 이 채팅에서 수행했으며 별도 독립 검증 에이전트를 사용하지 않았습니다. README에 연결된 VALIDATION_REPORT.md가 시작 시 없어 이번 실제 실행 로그를 근거로 작성했습니다. 이전 독립 검증 완료 표현이나 과거 테스트 개수는 현재 검증 근거로 사용하지 않습니다.'
p.write_text('\n'.join(lines)+'\n',encoding='utf-8')
