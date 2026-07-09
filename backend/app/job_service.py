import re

from . import db
from .llm_client import LLMError, chat_json, llm_available
from .matching import match_candidate, parse_skill_tags
from .models import Candidate, Match

SKILL_KEYWORDS = [
    "总账会计",
    "财务核算",
    "财务报表",
    "纳税申报",
    "税务",
    "审计",
    "Excel",
    "金蝶",
    "用友",
    "Python",
    "Java",
    "JavaScript",
    "TypeScript",
    "React",
    "Vue",
    "Flask",
    "FastAPI",
    "Django",
    "SQL",
    "MySQL",
    "PostgreSQL",
    "Redis",
    "Docker",
    "招聘",
    "面试安排",
    "员工关系",
    "绩效",
    "薪酬",
    "采购",
    "供应商",
    "库存",
    "供应链",
]

IMPORTANT_WORDS = ["必须", "精通", "熟练", "负责", "核心", "必备", "要求"]
NICE_TO_HAVE_WORDS = ["优先", "加分", "了解", "熟悉"]


def build_jd_structured(jd_text, skill_tags_raw=None):
    raw = skill_tags_raw or infer_skills_from_text(jd_text)
    skills = parse_skill_tags(raw)
    return {
        "skill_tags_raw": raw,
        "skills": skills,
        "years_required": infer_years_required(jd_text),
        "salary_range": infer_salary_range(jd_text),
        "education": infer_education(jd_text),
        "must_have": infer_requirement_lines(jd_text, IMPORTANT_WORDS),
        "nice_to_have": infer_requirement_lines(jd_text, NICE_TO_HAVE_WORDS),
    }


def ensure_jd_structured(job):
    structured = job.jd_structured or {}
    if structured.get("skills") and "years_required" in structured:
        return structured
    return build_jd_structured(job.jd_text, structured.get("skill_tags_raw"))


def infer_skills_from_text(text):
    tags = []
    lowered = text.lower()
    for keyword in SKILL_KEYWORDS:
        if keyword.lower() in lowered:
            tags.append(f"{keyword} {infer_weight(text, keyword)}")
    return "|".join(tags) or "沟通 3|执行 3"


def infer_weight(text, keyword):
    index = text.lower().find(keyword.lower())
    window = text[max(0, index - 24) : index + len(keyword) + 24] if index >= 0 else text
    if any(word in window for word in IMPORTANT_WORDS):
        return 5
    if any(word in window for word in NICE_TO_HAVE_WORDS):
        return 2
    return 3


def infer_years_required(text):
    match = re.search(r"(\d+)\s*年(?:以上|\+)?", text)
    return int(match.group(1)) if match else None


def infer_salary_range(text):
    standard_match = re.search(r"(\d+(?:\.\d+)?)\s*[kK万]?\s*[-~至到]\s*(\d+(?:\.\d+)?)\s*[kK万]", text)
    if standard_match:
        low, high = standard_match.groups()
        return {"min_k": float(low), "max_k": float(high)}
    match = re.search(r"(\d+(?:\.\d+)?)\s*[kK千]\s*[-~至]\s*(\d+(?:\.\d+)?)\s*[kK千]", text)
    if not match:
        return None
    low, high = match.groups()
    return {"min_k": float(low), "max_k": float(high)}


def infer_education(text):
    for value in ["博士", "硕士", "本科", "大专", "高中"]:
        if value in text:
            return value
    return None


def infer_requirement_lines(text, markers):
    lines = [line.strip(" -•\t") for line in re.split(r"[\n。；;]", text) if line.strip()]
    return [line for line in lines if any(marker in line for marker in markers)][:8]


def preview_matches(job, limit=None):
    results = []
    structured = ensure_jd_structured(job)
    for candidate in Candidate.query.all():
        reason = match_candidate(
            structured.get("skill_tags_raw"),
            [tag.to_dict() for tag in candidate.tags],
            years_required=structured.get("years_required"),
            candidate_years=(candidate.resume_json or {}).get("experience_analysis", {}).get("years"),
            candidate_context=" ".join([candidate.title or "", candidate.raw_text or ""]),
        )
        reason["rule_score"] = reason["score"]
        reason["final_score"] = reason["score"]
        reason["score_formula"] = "preview=rule_score; persisted_match=rule_score*45%+ai_score*55% when AI review succeeds"
        results.append(
            {
                "job_id": job.id,
                "candidate_id": candidate.id,
                "candidate": candidate.to_dict(),
                "score": reason["score"],
                "reason": reason,
            }
        )
    results.sort(key=lambda item: item["score"], reverse=True)
    return results[:limit] if limit else results


DEFAULT_AI_REVIEW_LIMIT = 3
DEFAULT_MATCH_LIMIT = 50


def persist_matches(db, job, ai_review_limit=DEFAULT_AI_REVIEW_LIMIT, match_limit=DEFAULT_MATCH_LIMIT):
    results = []
    Match.query.filter_by(job_id=job.id).delete()
    preview_items = preview_matches(job, limit=match_limit)
    reviewed_items = ai_review_matches(job, preview_items, limit=ai_review_limit)
    for item in reviewed_items:
        match = Match(job_id=job.id, candidate_id=item["candidate_id"], score=item["score"], reason=item["reason"])
        db.session.add(match)
        db.session.flush()
        results.append(match.to_dict())
    db.session.commit()
    results.sort(key=lambda item: item["score"], reverse=True)
    return results


def ai_review_matches(job, items, limit=None):
    if not llm_available():
        for item in items:
            item["reason"]["ai_review"] = {"source": "disabled", "summary": "AI 未启用，当前为规则匹配分。"}
        return items

    review_limit = len(items) if limit is None else max(0, min(int(limit), len(items)))
    reviewed = []
    for index, item in enumerate(items):
        if index >= review_limit:
            item["reason"]["ai_review"] = {
                "source": "rule_pending",
                "summary": f"规则初排保留，AI 已优先复核前 {review_limit} 位候选人，避免单次请求阻塞系统。",
            }
            item["reason"]["ai_score"] = None
            item["reason"]["final_score"] = item["reason"].get("rule_score", item["score"])
            reviewed.append(item)
            continue
        candidate = db_candidate(item["candidate_id"])
        if not candidate:
            reviewed.append(item)
            continue
        reviewed.append(apply_ai_review(job, candidate, item))
    return reviewed


def db_candidate(candidate_id):
    return db.session.get(Candidate, candidate_id)


def apply_ai_review(job, candidate, item):
    reason = item["reason"]
    rule_score = int(item["score"])
    try:
        review = request_ai_match_review(job, candidate, reason)
        ai_score = clamp_score(review.get("score"), rule_score)
        final_score = round(rule_score * 0.35 + ai_score * 0.65)
        review["source"] = "deepseek"
        reason["ai_review"] = normalize_ai_review(review)
        reason["ai_score"] = ai_score
        reason["final_score"] = final_score
        reason["rule_score"] = rule_score
        reason["score_formula"] = "final_score=round(rule_score*35% + ai_score*65%); no pre-filter before AI review"
        item["score"] = final_score
    except LLMError as exc:
        reason["ai_review"] = {"source": "failed", "summary": "AI 复核失败，已保留规则匹配分。", "error": str(exc)[:300]}
        reason["ai_score"] = None
        reason["final_score"] = rule_score
        reason["rule_score"] = rule_score
    return item


def request_ai_match_review(job, candidate, rule_reason):
    structured = ensure_jd_structured(job)
    candidate_tags = [tag.to_dict() for tag in candidate.tags]
    messages = [
        {
            "role": "system",
            "content": (
                "你是资深招聘匹配评估官。请同时阅读岗位 JD、候选人完整简历、规则标签命中结果，"
                "判断候选人是否适合该岗位。不能只按关键词，必须结合项目经历、业务场景、职责深度、年限和风险。"
                "如果规则命中的标签在简历原文中没有直接证据，或只是同名系统、网页噪音、岗位推荐、聊天记录、无关菜单，必须判定为规则误判并降低分数。"
                "如果候选人职业方向与 JD 明显不一致，例如 Java 开发候选人匹配财务会计岗位，不能因为出现 Excel、金蝶、用友等词就给高分。"
                "输出 JSON：{\"score\":0-100,\"recommendation\":\"强烈推荐/推荐/可考虑/不推荐\","
                "\"summary\":\"\",\"strengths\":[\"\"],\"risks\":[\"\"],\"interview_focus\":[\"\"],\"evidence\":[\"\"],\"rule_corrections\":[\"\"]}。"
            ),
        },
        {
            "role": "user",
            "content": (
                f"岗位名称：{job.title}\n"
                f"城市：{job.city or ''}\n"
                f"部门：{job.department or ''}\n"
                f"岗位 JD：\n{truncate_text(job.jd_text, 5000)}\n\n"
                f"JD 结构化要求：{structured}\n\n"
                f"候选人：{candidate.name_masked} / {candidate.title} / {candidate.city}\n"
                f"候选人标签：{candidate_tags}\n"
                f"规则匹配结果：{rule_reason}\n\n"
                f"候选人完整简历：\n{truncate_text(candidate.raw_text or '', 8000)}"
            ),
        },
    ]
    return chat_json(messages, temperature=0.1, timeout=8, source="job_match", tool_name="ai_match_review")


def normalize_ai_review(review):
    return {
        "source": review.get("source") or "deepseek",
        "score": clamp_score(review.get("score"), 0),
        "recommendation": str(review.get("recommendation") or ""),
        "summary": str(review.get("summary") or ""),
        "strengths": list_of_text(review.get("strengths"))[:5],
        "risks": list_of_text(review.get("risks"))[:5],
        "interview_focus": list_of_text(review.get("interview_focus"))[:5],
        "evidence": list_of_text(review.get("evidence"))[:5],
        "rule_corrections": list_of_text(review.get("rule_corrections"))[:5],
    }


def list_of_text(value):
    if isinstance(value, list):
        return [str(item) for item in value if str(item).strip()]
    if value:
        return [str(value)]
    return []


def clamp_score(value, fallback):
    try:
        return max(0, min(100, int(round(float(value)))))
    except (TypeError, ValueError):
        return max(0, min(100, int(fallback or 0)))


def truncate_text(text, limit):
    value = str(text or "")
    return value if len(value) <= limit else value[:limit] + "\n...[内容已截断]"
