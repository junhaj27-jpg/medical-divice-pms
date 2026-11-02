"""Prepare synthetic UI demo in a NEW directory, reusing existing regulatory fixture."""
import runpy
from pathlib import Path
state=runpy.run_path(str(Path(__file__).with_name('verify_impact.py')),run_name='__main__')
from pms.models import CustomerComplaint
for i in range(23):
    CustomerComplaint.objects.create(device=state['device'],udi=state['udi'],reporter=state['staff'],assignee=state['author'],
        title=f'TEST ONLY 분석 연결 {i+1}',description='합성 자료. 환자정보 없음.',complaint_type='TEST_EVENT',
        occurred_on=state['today'],is_example=True)
print('추가 합성 사건 23건. /rules/impacts/ 행 입력과 /analysis/internal/ 선택 미리보기를 시연하세요.')
