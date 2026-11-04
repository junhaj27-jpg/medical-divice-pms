"""Versioned approval scope. Only hashes of narrative content are retained."""
import hashlib
import json
from django.core.serializers.json import DjangoJSONEncoder


def digest(value):
    return hashlib.sha256(json.dumps(value, cls=DjangoJSONEncoder, sort_keys=True,
                                     separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()


# Explicit allowlist: timestamps, display order and patient records are not approval inputs.
FIELDS = {
    'case': 'id device_id udi_id lot_id serial_number complaint_type title description occurred_on reported_on due_date is_example',
    'risk_assessment': 'id severity probability score level capa_review_required rationale assessed_by_id',
    'adverse_event': 'id event_type outcome serious narrative',
    'capas': 'id title root_cause corrective_action preventive_action owner_id due_date status action_result evaluation_criteria evaluation_due',
    'reports': 'id document_number required checklist investigation_result status author_id reviewer_id approved_by_id approved_at',
    'recalls': 'id title reason risk_level device_id distributed_quantity target_quantity recovered_quantity start_date expected_end_date owner_id approval_status decision_reason progress_status closure_report',
    'attachments': 'id sha256 scan_status detected_type file',
    'rule_applications': 'id rule_id snapshot previous_snapshot due_at',
}


def row(obj, fields):
    return {key: getattr(obj, key) for key in fields.split()}


def approval_snapshot(case):
    from .models import RecoveryEntry, RecallContact, RiskAssessmentHistory, RegulatoryReportHistory
    scopes = {'case': digest(row(case, FIELDS['case']))}
    for name, fields in FIELDS.items():
        if name == 'case':
            continue
        if name in ('risk_assessment', 'adverse_event'):
            obj = getattr(case, name, None)
            values = row(obj, fields) if obj else None
        else:
            values = []
            for obj in getattr(case, name).order_by('pk'):
                value = row(obj, fields)
                if name == 'attachments':
                    value['file'] = str(value['file'])
                if name == 'capas':
                    value['evaluations'] = [dict(row(ev, 'id action_result criteria scheduled_on evaluated_on verdict rationale evaluator_id followup_id'),
                                                followup_status=ev.followup.status if ev.followup_id else None,
                                                evidence=list(ev.evidence.order_by('pk').values_list('pk', flat=True)))
                                            for ev in obj.evaluations.order_by('pk')]
                if name == 'recalls':
                    value['targets'] = list(obj.targets.order_by('pk').values('id', 'lot_id', 'serial_number', 'target_quantity'))
                    value['recoveries'] = list(RecoveryEntry.objects.filter(recipient__recall=obj).order_by('pk').values('id','recipient_id','quantity','recovered_on','actor_id','request_key'))
                    value['contacts'] = list(RecallContact.objects.filter(recipient__recall=obj).order_by('pk').values('id','recipient_id','contacted_at','method','note','actor_id'))
                    value['recipients'] = list(obj.recipients.order_by('pk').values('id', 'lot_id', 'partner_id', 'unit', 'target_quantity', 'recovered_total', 'reply_status', 'unrecovered_reason', 'notified_on', 'replied_on'))
                values.append(value)
        scopes[name] = digest(values)
    if case.device.product_type == 'SOFTWARE':
        scopes['software_versions'] = digest({
            'intake': case.intake_release_id,
            'affected': list(case.affected_releases.order_by('pk').values_list('pk', flat=True)),
            'rationale': case.impact_rationale,
            'verified': list(case.capas.filter(evaluations__fixed_release__isnull=False)
                             .order_by('evaluations__pk').values_list('evaluations__pk', 'evaluations__fixed_release_id')),
        })
    for label,model in [('risk_history',RiskAssessmentHistory),('report_history',RegulatoryReportHistory)]:
        scopes[label]=digest(list(model.objects.filter(parent__complaint=case).order_by('pk').values()))
    return {'schema': 2, 'version': case.version, 'device': str(case.device),
            'scopes': scopes, 'hash': digest(scopes)}


def approval_invalid_reason(approval, case):
    if not approval or approval.snapshot.get('schema') != 2:
        return '검증 가능한 승인 스냅샷이 없습니다. 재승인이 필요합니다.'
    current = approval_snapshot(case)
    if approval.snapshot.get('hash') != current['hash']:
        changed = [k for k, v in current['scopes'].items() if approval.snapshot.get('scopes', {}).get(k) != v]
        return '승인 대상 자료 변경: ' + ', '.join(changed) + '. 재승인이 필요합니다.'
    return ''
