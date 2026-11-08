from datetime import datetime

from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.utils import timezone

from .market_i18n import label
from .market_models import LANGUAGES, CaseMarket, MarketEvidence, MarketTranslation, ProductMarket
from .market_service import allowed_markets, parse_source, scoped


class LocalizedForm:
    def __init__(self, *args, lang, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.label = label(name, lang)
            if isinstance(field, forms.ChoiceField) and not isinstance(field, forms.ModelChoiceField):
                field.choices = [(value, label(str(value), lang) if value else "—")
                                 for value, _ in field.choices]
            field.error_messages.update(
                required=label("required", lang),
                invalid=label("invalid", lang),
                invalid_choice=label("invalid", lang),
            )
            if isinstance(field, forms.DateField):
                field.widget = forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"})
                field.input_formats = ["%Y-%m-%d"]
        self.lang = lang

    def owners(self, actor, market):
        owners = get_user_model().objects.filter(is_active=True).filter(
            Q(is_superuser=True) | Q(profile__role__in=("ADMIN", "RA_QA"))
        ).select_related("profile", "market_access")
        self.fields["owner"].queryset = owners.filter(
            pk__in=[u.pk for u in owners if market in allowed_markets(u)]
        )


class RegistrationForm(LocalizedForm, forms.ModelForm):
    optional_fields = ("pathway", "classification", "identifier", "owner", "effective_on", "expires_on",
                       "submissions", "rationale", "authority", "submission_language")
    na_fields = forms.MultipleChoiceField(required=False, widget=forms.CheckboxSelectMultiple)

    class Meta:
        model = ProductMarket
        fields = ("status", "pathway", "classification", "identifier", "owner", "effective_on",
                  "expires_on", "submissions", "rationale", "authority", "submission_language",
                  "na_fields", "eu_assessment", "eu_rationale", "is_example")

    def __init__(self, *args, actor, eu, **kwargs):
        super().__init__(*args, **kwargs)
        self.owners(actor, self.instance.market)
        self.fields["na_fields"].choices = [(v, label(v, self.lang)) for v in self.optional_fields]
        self.fields["na_fields"].help_text = label("unconfirmed_fields", self.lang)
        if not eu:
            del self.fields["eu_assessment"]
            del self.fields["eu_rationale"]
        if scoped(actor) or self.instance.pk:
            self.fields["is_example"].disabled = True

    def clean(self):
        data = super().clean()
        for field in data.get("na_fields", []):
            if data.get(field):
                self.add_error(field, label("value_or_na", self.lang))
        if data.get("eu_assessment") in ("ALIGNED", "CONFLICT", "NA") and not data.get("eu_rationale", "").strip():
            self.add_error("eu_rationale", label("required", self.lang))
        if data.get("expires_on") and data.get("effective_on") and data["expires_on"] < data["effective_on"]:
            self.add_error("expires_on", label("date_order", self.lang))
        return data


class CaseMarketForm(LocalizedForm, forms.ModelForm):
    class Meta:
        model = CaseMarket
        fields = ("owner", "occurred_at_source", "reported_at_source", "aware_at_source", "custom_at_source",
                  "manual_decision", "manual_due_on", "reviewed", "rationale")

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        self.owners(actor, self.instance.market)
        for key in ("occurred_at_source", "reported_at_source", "aware_at_source", "custom_at_source"):
            self.fields[key].help_text = label("iso_input", self.lang)

    def clean(self):
        data = super().clean()
        for key in ("occurred_at_source", "reported_at_source", "aware_at_source", "custom_at_source"):
            raw = data.get(key)
            if raw:
                try:
                    stamp = parse_source(raw)
                except ValueError:
                    self.add_error(key, label("iso_input", self.lang))
                    continue
                if key in ("occurred_at_source", "reported_at_source"):
                    business_date = stamp.date() if isinstance(stamp, datetime) else stamp
                    if business_date != getattr(self.instance.complaint, key.split("_")[0] + "_on"):
                        self.add_error(key, label("date_mismatch", self.lang))
        if data.get("reviewed") and (data.get("manual_decision") == "HOLD" or not data.get("owner")):
            self.add_error("reviewed", label("review_requires_decision", self.lang))
        if data.get("manual_decision") in ("REPORT", "NO_REPORT") and not data.get("rationale", "").strip():
            self.add_error("rationale", label("required", self.lang))
        if data.get("manual_due_on") and data.get("manual_decision") != "REPORT":
            self.add_error("manual_due_on", label("deadline_requires_report", self.lang))
        return data


class EvidenceForm(LocalizedForm, forms.ModelForm):
    verified = forms.BooleanField(required=False)

    class Meta:
        model = MarketEvidence
        fields = ("regulation_document", "reference_key", "title", "clause", "language", "official_url", "excerpt",
                  "checked_on", "verified", "is_example")

    def __init__(self, *args, actor, **kwargs):
        super().__init__(*args, **kwargs)
        from .market_codes import market_code
        from .regulation_documents import documents_for
        docs = documents_for(actor).filter(is_example=self.instance.is_example, visibility="TEAM",
                                            review_status="REVIEWED").filter(
            Q(device_id=self.instance.device_id) | Q(device_id__isnull=True)
        )
        self.fields["regulation_document"].queryset = docs.filter(pk__in=[
            doc.pk for doc in docs if market_code(doc.jurisdiction) == self.instance.scope
        ])
        self.fields["is_example"].disabled = True

    def clean(self):
        data = super().clean()
        url = data.get("official_url", "")
        doc = data.get("regulation_document")
        if doc and url != doc.official_url:
            self.add_error("official_url", label("same_source_url", self.lang))
        if url and not url.startswith("https://"):
            self.add_error("official_url", label("https_only", self.lang))
        if data.get("verified") and not (data.get("checked_on") and data.get("clause") and
                                        (url or data.get("is_example"))):
            self.add_error("verified", label("verification_required", self.lang))
        if data.get("checked_on") and data["checked_on"] > timezone.localdate():
            self.add_error("checked_on", label("invalid", self.lang))
        return data


class TranslationForm(LocalizedForm, forms.ModelForm):
    verified = forms.BooleanField(required=False)

    class Meta:
        model = MarketTranslation
        fields = ("language", "text", "verified")


class LanguageForm(LocalizedForm, forms.Form):
    language = forms.ChoiceField(choices=LANGUAGES)
