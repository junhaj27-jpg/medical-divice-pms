from datetime import timedelta

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from pms import foreign
from pms.file_security import scan_attachment
from pms.foreign_models import ForeignApplication
from pms.models import Attachment, BusinessPartner, MedicalDevice, RegulatoryProfile
from pms.ra_services import save_record


class Command(BaseCommand):
    help = "격리 DB에 가상의 미국·EU 해외 인허가 신청을 생성합니다."

    def add_arguments(self, parser):
        parser.add_argument("--prepare-only", action="store_true", help="증빙 검사기 없이 준비 단계만 생성")

    def handle(self, *args, **options):
        user_model = get_user_model()
        try:
            reviewer = user_model.objects.get(username="raqa")
            admin = user_model.objects.get(username="admin")
            software = MedicalDevice.objects.get(model_number="EEG-SW-DEMO")
        except (user_model.DoesNotExist, MedicalDevice.DoesNotExist) as exc:
            raise CommandError("격리 DB에서 seed_demo를 먼저 실행하세요.") from exc
        foreign.require_ra(reviewer)
        foreign.require_admin(admin)
        files = []
        try:
            with transaction.atomic():
                organization, _ = BusinessPartner.objects.get_or_create(name="가상 해외 인허가 시연 조직")
                hardware, _ = MedicalDevice.objects.get_or_create(
                    manufacturer=software.manufacturer, model_number="EEG-HW-DEMO",
                    defaults={"name": "뇌파계 (가상)", "product_type": "HARDWARE"},
                )
                today = timezone.localdate()
                for market in ("US", "EU"):
                    self.profile(hardware, market, organization, reviewer)
                    profile = self.profile(software, market, organization, reviewer)
                    RegulatoryProfile.objects.select_for_update().get(pk=profile.pk)
                    title = f"[가상] 뇌파분석 소프트웨어 {market} 신규 신청"
                    case = ForeignApplication.objects.filter(profile=profile, title=title, is_example=True).first()
                    if not case:
                        case = foreign.save_application(reviewer, dict(
                            profile=profile, market=market, title=title, kind="NEW", previous=None,
                            model_scope=software.model_number, release=software.software_releases.get(version="v1.2.1"),
                            intended_use="가상 사용목적. 검토자에게 뇌파 분석 결과를 표시합니다.",
                            classification="", pathway="",
                            rationale=f"가상 {market} 분류·경로 후보와 적용 범위를 내부 검토 중입니다.",
                            owner=reviewer, target_on=today + timedelta(days=30), is_example=True,
                        ))
                    if market == "EU" and not case.documents.exclude(applicability="UNVERIFIED").exists():
                        item = case.documents.get(title="EU 기술문서 범위 검토")
                        self.update_document(case, item, reviewer, "APPLIES", "가상 기술문서 범위를 검토 중입니다.")
                    if market == "US" and not options["prepare_only"] and case.stage == foreign.STAGE.PREPARATION:
                        if not settings.ANTIVIRUS_COMMAND:
                            raise CommandError("전체 시연에는 ANTIVIRUS_COMMAND가 필요합니다. 준비만 하려면 --prepare-only를 사용하세요.")
                        self.complete_us(case, reviewer, admin, today, files)
                    self.stdout.write(f"{market}: /foreign/{case.pk}/ · 가상 시연 데이터")
        except Exception:
            for file in files:
                file.delete(save=False)
            raise

    def profile(self, device, market, organization, reviewer):
        existing = RegulatoryProfile.objects.filter(
            device=device, jurisdiction=market, organization=organization,
            organization_role="MANUFACTURER", is_example=True,
        ).first()
        return existing or save_record(RegulatoryProfile(), reviewer, dict(
            device=device, jurisdiction=market, organization=organization, organization_role="MANUFACTURER",
            title=f"{device.name} {market} 시연 범위", owner=reviewer, is_example=True,
        ), "가상 해외 인허가 시연 프로필")

    def proof(self, case, reviewer, name, text, files):
        attachment = Attachment(ra_profile=case.profile, uploaded_by=reviewer, original_name=name)
        attachment.file.save(name, ContentFile(("가상 시연 데이터\n" + text).encode()), save=False)
        files.append(attachment.file)
        attachment.full_clean()
        attachment.save()
        scan_attachment(attachment, reviewer)
        if attachment.scan_status != "PASSED":
            raise CommandError("가상 시연 증빙 검사가 통과하지 않았습니다.")
        return attachment

    def update_document(self, case, item, reviewer, applicability, rationale, proof=None):
        foreign.save_document(reviewer, case.pk, dict(
            title=item.title, version="DEMO-1" if proof else "", owner=reviewer,
            applicability=applicability, rationale=rationale, status="READY" if proof else "DRAFT", evidence=proof,
        ), item.pk)

    def complete_us(self, case, reviewer, admin, today, files):
        for index, item in enumerate(case.documents.order_by("pk"), 1):
            proof = self.proof(case, reviewer, f"demo-us-document-{index}.txt", item.title, files)
            self.update_document(case, item, reviewer, "APPLIES", "가상 제출 범위에 포함합니다.", proof)
        foreign.operate(reviewer, case.pk, "review", {})
        foreign.operate(admin, case.pk, "approve", {})
        receipt = self.proof(case, reviewer, "demo-us-receipt.txt", "실제 기관 전송이 없는 가상 접수증", files)
        foreign.operate(reviewer, case.pk, "submit", dict(submitted_on=today, reference="FICTIONAL-US-001", evidence=receipt))
        foreign.operate(reviewer, case.pk, "supplement", dict(
            requested_on=today, due_on=today + timedelta(days=2), owner=reviewer,
            basis="가상 검토자가 결과 표시 검증 조건을 문의함. 실습 회신 기한을 내부에서 2일로 지정.",
        ))
        reply = self.proof(case, reviewer, "demo-us-reply.txt", "가상 답변. 검증 환경과 표시 지연 측정 조건을 설명함.", files)
        foreign.operate(reviewer, case.pk, "respond", dict(
            supplement_id=case.supplements.get().pk, response=reply, responded_on=today,
        ))
        foreign.operate(reviewer, case.pk, "supplement", dict(
            requested_on=today, due_on=today + timedelta(days=1), owner=reviewer,
            basis="가상 후속 문의. 라벨 초안 비교 자료를 정리할 실습 기한을 내부에서 지정.",
        ))

