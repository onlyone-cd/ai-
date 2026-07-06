import json
import time
import urllib.error
import urllib.request

from flask import current_app, g, has_request_context
from sqlalchemy.orm import Session


class LLMError(RuntimeError):
    pass


def llm_available():
    return bool(current_app.config.get("LLM_ENABLED") and current_app.config.get("DEEPSEEK_API_KEY"))


def llm_status():
    return {
        "enabled": bool(current_app.config.get("LLM_ENABLED")),
        "available": llm_available(),
        "provider": current_app.config.get("LLM_PROVIDER"),
        "model": current_app.config.get("LLM_MODEL"),
        "api_url": current_app.config.get("LLM_API_URL"),
        "timeout_seconds": int(current_app.config.get("LLM_TIMEOUT_SECONDS", 45)),
        "max_retries": int(current_app.config.get("LLM_MAX_RETRIES", 1)),
    }


def chat_json(messages, temperature=0.1, timeout=None):
    if not llm_available():
        raise LLMError("LLM 未启用或缺少 API Key")

    timeout = int(timeout or current_app.config.get("LLM_TIMEOUT_SECONDS", 45))
    max_retries = max(0, int(current_app.config.get("LLM_MAX_RETRIES", 1)))
    backoff = max(0.0, float(current_app.config.get("LLM_RETRY_BACKOFF_SECONDS", 0.5)))
    started_at = time.monotonic()
    request_id = getattr(g, "request_id", "") if has_request_context() else ""
    payload = {
        "model": current_app.config["LLM_MODEL"],
        "messages": messages,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    request = urllib.request.Request(
        current_app.config["LLM_API_URL"],
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {current_app.config['DEEPSEEK_API_KEY']}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    last_error = None
    body = None
    successful_attempt = 1
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
            duration_ms = int((time.monotonic() - started_at) * 1000)
            successful_attempt = attempt + 1
            current_app.logger.info(
                "LLM call succeeded provider=%s model=%s attempt=%s duration_ms=%s request_id=%s",
                current_app.config.get("LLM_PROVIDER"),
                current_app.config.get("LLM_MODEL"),
                attempt + 1,
                duration_ms,
                request_id,
            )
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            duration_ms = int((time.monotonic() - started_at) * 1000)
            record_llm_usage(messages, None, False, duration_ms, attempt + 1, status_code=exc.code, error_text=detail)
            current_app.logger.warning("LLM HTTP error code=%s request_id=%s detail=%s", exc.code, request_id, detail[:200])
            raise LLMError(f"LLM HTTP {exc.code}: {detail[:300]}") from exc
        except (TimeoutError, urllib.error.URLError, OSError) as exc:
            last_error = exc
            current_app.logger.warning(
                "LLM call failed attempt=%s/%s request_id=%s error=%s",
                attempt + 1,
                max_retries + 1,
                request_id,
                exc,
            )
            if attempt < max_retries:
                time.sleep(backoff * (attempt + 1))
                continue
            duration_ms = int((time.monotonic() - started_at) * 1000)
            record_llm_usage(messages, None, False, duration_ms, attempt + 1, error_text=str(last_error))
            raise LLMError(f"LLM 调用失败: {last_error}") from exc
        except Exception as exc:
            duration_ms = int((time.monotonic() - started_at) * 1000)
            record_llm_usage(messages, None, False, duration_ms, attempt + 1, error_text=str(exc))
            raise LLMError(f"LLM 调用失败: {exc}") from exc

    try:
        content = body["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        record_llm_usage(messages, body, True, int((time.monotonic() - started_at) * 1000), successful_attempt)
        return parsed
    except Exception as exc:
        record_llm_usage(messages, body, False, int((time.monotonic() - started_at) * 1000), successful_attempt, error_text=str(exc))
        raise LLMError("LLM 返回内容不是合法 JSON") from exc


def record_llm_usage(messages, response_body, success, duration_ms, attempts, status_code=None, error_text=""):
    if not current_app.config.get("LLM_USAGE_LOG_ENABLED", True):
        return
    try:
        from . import db
        from .models import LLMUsage

        usage = extract_usage(messages, response_body)
        record = LLMUsage(
            provider=str(current_app.config.get("LLM_PROVIDER") or ""),
            model=str(current_app.config.get("LLM_MODEL") or ""),
            endpoint=str(current_app.config.get("LLM_API_URL") or "")[:255],
            request_id=getattr(g, "request_id", "") if has_request_context() else "",
            success=bool(success),
            status_code=status_code,
            error=(error_text or "")[:500] or None,
            prompt_tokens=usage["prompt_tokens"],
            completion_tokens=usage["completion_tokens"],
            total_tokens=usage["total_tokens"],
            estimated=usage["estimated"],
            cost_usd=estimate_cost_usd(usage["prompt_tokens"], usage["completion_tokens"]),
            duration_ms=max(0, int(duration_ms or 0)),
            attempts=max(1, int(attempts or 1)),
        )
        with Session(db.engine) as session:
            session.add(record)
            session.commit()
    except Exception as exc:
        current_app.logger.warning("LLM usage log failed: %s", exc)


def extract_usage(messages, response_body):
    usage = (response_body or {}).get("usage") or {}
    prompt_tokens = int(usage.get("prompt_tokens") or 0)
    completion_tokens = int(usage.get("completion_tokens") or 0)
    total_tokens = int(usage.get("total_tokens") or 0)
    estimated = False
    if not total_tokens:
        estimated = True
        prompt_tokens = estimate_tokens(json.dumps(messages, ensure_ascii=False))
        content = ""
        try:
            content = (response_body or {})["choices"][0]["message"]["content"]
        except Exception:
            content = ""
        completion_tokens = estimate_tokens(content)
        total_tokens = prompt_tokens + completion_tokens
    return {
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "estimated": estimated,
    }


def estimate_tokens(text):
    return max(1, int(len(text or "") / 4))


def estimate_cost_usd(prompt_tokens, completion_tokens):
    prompt_price = float(current_app.config.get("LLM_PROMPT_PRICE_PER_1M_TOKENS_USD", 0) or 0)
    completion_price = float(current_app.config.get("LLM_COMPLETION_PRICE_PER_1M_TOKENS_USD", 0) or 0)
    return (prompt_tokens / 1_000_000 * prompt_price) + (completion_tokens / 1_000_000 * completion_price)
