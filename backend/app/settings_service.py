from flask import current_app

from . import db
from .models import SystemSetting


AI_SETTING_KEY = "ai_config"
MATCHING_SETTING_KEY = "matching_weights"

DEFAULT_MATCHING_WEIGHTS = {
    "skill_match": 75,
    "capability": 25,
    "skill_overall": 85,
    "experience": 15,
    "rule": 35,
    "ai": 65,
    "pending_rule": 35,
}


def default_ai_config():
    return {
        "mode": "ai" if current_app.config.get("LLM_ENABLED") else "local_rules",
        "provider": current_app.config.get("LLM_PROVIDER") or "deepseek",
        "base_url": current_app.config.get("LLM_API_URL") or "https://api.deepseek.com/v1/chat/completions",
        "model": current_app.config.get("LLM_MODEL") or "deepseek-chat",
        "temperature": 0.1,
        "api_key": current_app.config.get("DEEPSEEK_API_KEY") or "",
    }


def public_ai_config(value=None):
    data = {**default_ai_config(), **(value or {})}
    api_key = str(data.pop("api_key", "") or "")
    data["api_key_configured"] = bool(api_key)
    data["api_key_masked"] = mask_secret(api_key)
    return data


def get_setting_value(key, fallback):
    setting = db.session.get(SystemSetting, key)
    return {**fallback, **((setting.value if setting else None) or {})}


def save_setting_value(key, group, value, user=None):
    setting = db.session.get(SystemSetting, key)
    if not setting:
        setting = SystemSetting(key=key, group=group, value={})
        db.session.add(setting)
    setting.group = group
    setting.value = value
    setting.updated_by = user.id if user else None
    return setting


def get_ai_config(public=False):
    value = get_setting_value(AI_SETTING_KEY, default_ai_config())
    return public_ai_config(value) if public else value


def save_ai_config(payload, user=None):
    current = get_ai_config(public=False)
    existing = db.session.get(SystemSetting, AI_SETTING_KEY)
    existing_value = (existing.value if existing else None) or {}
    next_value = {
        "mode": str(payload.get("mode") or current.get("mode") or "ai"),
        "provider": str(payload.get("provider") or current.get("provider") or "deepseek"),
        "base_url": str(payload.get("base_url") or current.get("base_url") or "").strip(),
        "model": str(payload.get("model") or current.get("model") or "").strip(),
        "temperature": clamp_float(payload.get("temperature", current.get("temperature", 0.1)), 0, 2),
    }
    if existing_value.get("api_key"):
        next_value["api_key"] = existing_value["api_key"]
    api_key = str(payload.get("api_key") or "").strip()
    if api_key and not api_key.startswith("***"):
        next_value["api_key"] = api_key
    setting = save_setting_value(AI_SETTING_KEY, "ai", next_value, user)
    return public_ai_config(setting.value)


def get_matching_weights():
    return normalize_matching_weights(get_setting_value(MATCHING_SETTING_KEY, DEFAULT_MATCHING_WEIGHTS))


def save_matching_weights(payload, user=None):
    setting = save_setting_value(MATCHING_SETTING_KEY, "matching", normalize_matching_weights(payload or {}), user)
    return setting.value


def auto_matching_weights(profile="balanced"):
    presets = {
        "strict": {"skill_match": 82, "capability": 18, "skill_overall": 88, "experience": 12, "rule": 30, "ai": 70, "pending_rule": 30},
        "balanced": DEFAULT_MATCHING_WEIGHTS,
        "growth": {"skill_match": 62, "capability": 38, "skill_overall": 75, "experience": 25, "rule": 40, "ai": 60, "pending_rule": 40},
    }
    return dict(presets.get(str(profile or "balanced"), DEFAULT_MATCHING_WEIGHTS))


def normalize_matching_weights(payload):
    data = {**DEFAULT_MATCHING_WEIGHTS, **(payload or {})}
    skill_match, capability = normalize_pair(data.get("skill_match"), data.get("capability"), 75, 25)
    skill_overall, experience = normalize_pair(data.get("skill_overall"), data.get("experience"), 85, 15)
    rule, ai = normalize_pair(data.get("rule"), data.get("ai"), 35, 65)
    pending_rule = clamp_int(data.get("pending_rule", rule), 0, 100)
    return {
        "skill_match": skill_match,
        "capability": capability,
        "skill_overall": skill_overall,
        "experience": experience,
        "rule": rule,
        "ai": ai,
        "pending_rule": pending_rule,
    }


def ai_runtime_config():
    config = get_ai_config(public=False)
    enabled = config.get("mode") != "local_rules" and bool(config.get("api_key"))
    return {
        "enabled": enabled,
        "provider": config.get("provider") or current_app.config.get("LLM_PROVIDER"),
        "model": config.get("model") or current_app.config.get("LLM_MODEL"),
        "api_url": config.get("base_url") or current_app.config.get("LLM_API_URL"),
        "api_key": config.get("api_key") or current_app.config.get("DEEPSEEK_API_KEY"),
        "temperature": clamp_float(config.get("temperature", 0.1), 0, 2),
    }


def normalize_pair(left, right, default_left, default_right):
    left = clamp_int(left, 0, 100)
    right = clamp_int(right, 0, 100)
    total = left + right
    if total <= 0:
        return default_left, default_right
    normalized_left = round(left / total * 100)
    return normalized_left, 100 - normalized_left


def clamp_int(value, minimum, maximum):
    try:
        number = int(round(float(value)))
    except (TypeError, ValueError):
        number = minimum
    return max(minimum, min(maximum, number))


def clamp_float(value, minimum, maximum):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = minimum
    return max(minimum, min(maximum, number))


def mask_secret(value):
    text = str(value or "")
    if not text:
        return ""
    if len(text) <= 8:
        return "***"
    return f"{text[:3]}***{text[-4:]}"
