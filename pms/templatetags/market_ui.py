from datetime import date, datetime

from django import template
from django.utils.formats import localize, number_format

from pms.market_codes import market_code
from pms.market_i18n import DEFAULT, label

register = template.Library()


@register.simple_tag(takes_context=True)
def ui(context, key):
    return label(key, context.get("output_language") or context.get("ui_language", DEFAULT))


@register.filter
def market_datetime(raw):
    try:
        # Keep the stored offset; do not convert this clock to the user's timezone.
        return localize(date.fromisoformat(raw) if len(raw) == 10 else datetime.fromisoformat(raw))
    except (ValueError, TypeError):
        return raw



@register.filter
def market_number(value):
    return number_format(value, force_grouping=True)


@register.filter
def sales_market(jurisdiction):
    return market_code(jurisdiction)
