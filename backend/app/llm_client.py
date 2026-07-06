import json
import time
import urllib.error
import urllib.request

from flask import current_app, g, has_request_context


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
    for attempt in range(max_retries + 1):
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = json.loads(response.read().decode("utf-8"))
            current_app.logger.info(
                "LLM call succeeded provider=%s model=%s attempt=%s duration_ms=%s request_id=%s",
                current_app.config.get("LLM_PROVIDER"),
                current_app.config.get("LLM_MODEL"),
                attempt + 1,
                int((time.monotonic() - started_at) * 1000),
                request_id,
            )
            break
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
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
            raise LLMError(f"LLM 调用失败: {last_error}") from exc
        except Exception as exc:
            raise LLMError(f"LLM 调用失败: {exc}") from exc

    try:
        content = body["choices"][0]["message"]["content"]
        return json.loads(content)
    except Exception as exc:
        raise LLMError("LLM 返回内容不是合法 JSON") from exc
