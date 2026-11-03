"""Frozen 0012/0013 preflight. Do not change after deployment; add a new version instead."""
from django.db.models import F, Q, Count, Sum


def violations(apps, alias):
    issues=[]
    def rows(model, qs, rule):
        for pk in qs.order_by('pk').values_list('pk',flat=True).iterator():
            issues.append({'model':model,'pk':pk,'rule':rule})
    def model(name): return apps.get_model('pms',name).objects.using(alias)
    for name in ('ProductLot','CustomerComplaint'):
        rows(name,model(name).exclude(device_id=F('udi__device_id')),'device_udi_match')
    rows('CustomerComplaint',model('CustomerComplaint').filter(lot__isnull=False).exclude(lot__udi_id=F('udi_id')),'case_lot_udi_match')
    rows('AdverseEvent',model('AdverseEvent').filter(patient__isnull=False).exclude(patient__complaint_id=F('complaint_id')),'patient_case_match')
    rows('Recall',model('Recall').filter(complaint__isnull=False).exclude(device_id=F('complaint__device_id')),'recall_case_device')
    rows('Recall',model('Recall').filter(Q(target_quantity__gt=F('distributed_quantity'))|Q(recovered_quantity__gt=F('target_quantity'))),'recall_quantity_bounds')
    for name in ('RecallTarget','RecallRecipient'):
        rows(name,model(name).exclude(lot__device_id=F('recall__device_id')),'recall_lot_device')
    rows('RecallTarget',model('RecallTarget').filter(target_quantity__lt=1),'positive_recall_target')
    duplicates=model('RecallTarget').values('recall_id','lot_id','serial_number').annotate(n=Count('pk')).filter(n__gt=1)
    for group in duplicates:
        rows('RecallTarget',model('RecallTarget').filter(**{k:v for k,v in group.items() if k!='n'}),'unique_recall_target')
    for recall in model('Recall').annotate(total=Sum('targets__target_quantity')).filter(total__gt=F('target_quantity')):
        issues.append({'model':'Recall','pk':recall.pk,'rule':'target_sum_overflow'})
    for recipient in model('RecallRecipient').annotate(total=Sum('recoveries__quantity')):
        if recipient.recovered_total != (recipient.total or 0):
            issues.append({'model':'RecallRecipient','pk':recipient.pk,'rule':'ledger_counter_mismatch'})
    rows('RiskAssessment',model('RiskAssessment').exclude(severity__range=(1,5),probability__range=(1,5)),'risk_values_range')
    rows('RiskAssessment',model('RiskAssessment').exclude(score=F('severity')*F('probability')),'risk_score_product')
    rows('WorkTask',model('WorkTask').filter(capa__isnull=False,recall__isnull=False),'task_one_action_parent')
    for parent in ('capa','recall'):
        rows('WorkTask',model('WorkTask').filter(**{parent+'__isnull':False}).exclude(**{parent+'__complaint_id':F('complaint_id')}),'task_parent_case')
    for name,fields in {'CustomerComplaint':['status'],'CAPA':['status'],'Recall':['approval_status','progress_status'],'Approval':['decision'],'WorkTask':['status'],'RegulatoryReport':['status'],'ImpactReview':['status'],'SafetySignal':['status'],'AnalysisRecord':['seriousness']}.items():
        cls=apps.get_model('pms',name)
        for field in fields:
            allowed=[k for k,v in cls._meta.get_field(field).choices]
            rows(name,model(name).exclude(**{field+'__in':allowed}),field+'_domain')
    for name in ('CustomerComplaint','WorkTask'):
        rows(name,model(name).filter(assignee__is_active=False),'inactive_assignee')
        rows(name,model(name).filter(assignee__is_superuser=False,assignee__profile__role='STAFF').exclude(**({'assignee_id':F('reporter_id')} if name=='CustomerComplaint' else {'assignee_id':F('complaint__reporter_id')})),'staff_assignment_scope')
    for name,keys,rule in [('AnalysisRecord',['batch_id','row_number'],'unique_import_row')]:
        for group in model(name).values(*keys).annotate(n=Count('pk')).filter(n__gt=1):
            rows(name,model(name).filter(**{k:v for k,v in group.items() if k!='n'}),rule)
    rows('RuleApplication',model('RuleApplication').filter(rule__is_example=True,complaint__is_example=False),'example_rule_real_case')
    rows('RuleApplication',model('RuleApplication').filter(rule__device__isnull=False).exclude(rule__device_id=F('complaint__device_id')),'rule_case_device')
    return issues


def require_valid(apps,schema_editor):
    issues=violations(apps,schema_editor.connection.alias)
    if issues:
        import json
        raise RuntimeError('PMS integrity preflight blocked; no rows repaired/deleted. Run audit_data_integrity and review docs/data-integrity.md. '+json.dumps(issues,ensure_ascii=False))
