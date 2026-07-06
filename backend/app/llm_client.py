import json
import urllib.error
import urllib.request

from flask import current_app


class LLMError(RuntimeError):
    pass


def llm_available():
    return bool(current_app.config.get("LLM_ENABLED") and current_app.config.get("DEEPSEEK_API_KEY"))


def chat_json(messages, temperature=0.1, timeout=45):
    if not llm_available():
        raise LLMError("LLM 未启用或缺少 API Key")

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
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise LLMError(f"LLM HTTP {exc.code}: {detail[:300]}") from exc
    except Exception as exc:
        raise LLMError(f"LLM 调用失败: {exc}") from exc

    try:
        content = body["choices"][0]["message"]["content"]
        return json.loads(content)
    except Exception as exc:
        raise LLMError("LLM 返回内容不是合法 JSON") from exc
