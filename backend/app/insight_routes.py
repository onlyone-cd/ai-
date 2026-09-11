from flask import Blueprint, request

from .auth import login_required, roles_required
from .insight_service import (
    channel_effectiveness,
    funnel_analysis,
    interviewer_bias_analysis,
    offer_conversion_analysis,
    overall_insight_report,
    time_to_hire_analysis,
)
from .responses import ok


insight_api = Blueprint("insight_api", __name__)


def period_days(default):
    try:
        value = int(request.args.get("days", default))
    except (TypeError, ValueError):
        value = default
    return max(1, min(value, 365))


def force_refresh():
    return str(request.args.get("refresh", "")).strip().lower() in {"1", "true", "yes", "on"}


@insight_api.get("/insight/funnel")
@login_required
@roles_required("admin", "manager")
def insight_funnel(user):
    return ok(funnel_analysis(period_days(90)))


@insight_api.get("/insight/channels")
@login_required
@roles_required("admin", "manager")
def insight_channels(user):
    return ok(channel_effectiveness(period_days(90)))


@insight_api.get("/insight/time-to-hire")
@login_required
@roles_required("admin", "manager")
def insight_time_to_hire(user):
    return ok(time_to_hire_analysis(period_days(180)))


@insight_api.get("/insight/interviewer-bias")
@login_required
@roles_required("admin", "manager")
def insight_interviewer_bias(user):
    return ok(interviewer_bias_analysis(period_days(180)))


@insight_api.get("/insight/offer-conversion")
@login_required
@roles_required("admin", "manager")
def insight_offer_conversion(user):
    return ok(offer_conversion_analysis(period_days(180)))


@insight_api.get("/insight/report")
@login_required
@roles_required("admin", "manager")
def insight_full_report(user):
    return ok(overall_insight_report(period_days(90), force_refresh=force_refresh()))
