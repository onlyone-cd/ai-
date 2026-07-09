from .llm_client import LLMError, chat_json, llm_available
from .tag_library import candidate_labels_for_text, normalize_llm_tags


def parse_resume_with_deepseek(raw_text):
    if not llm_available():
        return None

    candidates = candidate_labels_for_text(raw_text)
    if not candidates:
        candidates = candidate_labels_for_text(raw_text + " 沟通 执行 Excel SQL Python 会计 招聘 销售 客服", limit=80)

    allowed_tags = [{"tag": item.tag, "category": item.category, "aliases": list(item.aliases)} for item in candidates]
    messages = [
        {
            "role": "system",
            "content": (
                "你是招聘系统的简历解析器。必须只从 allowed_tags 里选择技能标签，不允许创造新标签。"
                "每个标签必须有简历原文证据，证据必须能直接证明候选人本人具备该技能/经验。"
                "如果标签只出现在网页导航、岗位推荐、聊天记录、职位名称、旁栏菜单或与候选人经历无关的上下文中，必须忽略。"
                "财务软件类标签如金蝶、用友、SAP 必须同时有财务/会计/税务/报表/核算等上下文，不能因为开发过相关系统就标为财务从业技能。"
                "输出 JSON，不要输出 Markdown。"
            ),
        },
        {
            "role": "user",
            "content": (
                "请从简历中提取基础信息、结构化经历和技能标签。不要把求职意向当姓名；没有证据的字段留空。\n"
                "JSON 格式：{\"profile\":{\"name\":\"\",\"gender\":\"\",\"phone\":\"\",\"email\":\"\",\"city\":\"\",\"title\":\"\",\"summary\":\"\"},"
                "\"education\":[{\"school\":\"\",\"degree\":\"\",\"major\":\"\",\"period\":\"\",\"description\":\"\"}],"
                "\"experience\":[{\"company\":\"\",\"title\":\"\",\"period\":\"\",\"description\":\"\"}],"
                "\"projects\":[{\"name\":\"\",\"role\":\"\",\"period\":\"\",\"description\":\"\"}],"
                "\"certifications\":[],"
                "\"tags\":[{\"tag\":\"\",\"score\":1-5,\"evidence\":\"原文短证据\"}]}\n"
                "经历和项目要按原简历段落归纳，不要整篇原文复制。score 含义：2 轻度接触，3 可独立使用，4 熟练，5 专家级。低于 2 不要返回。\n"
                f"allowed_tags={allowed_tags}\n"
                f"resume_text={raw_text[:7000]}"
            ),
        },
    ]
    try:
        parsed = chat_json(messages, source="resume_parse", tool_name="deepseek_resume_parser")
    except LLMError:
        return None

    parsed["tags"] = normalize_llm_tags(parsed.get("tags", []), raw_text)
    return parsed
