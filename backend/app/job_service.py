import re

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
        if reason["score"] < 50:
            continue
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


def persist_matches(db, job):
    results = []
    Match.query.filter_by(job_id=job.id).delete()
    for item in preview_matches(job):
        match = Match(job_id=job.id, candidate_id=item["candidate_id"], score=item["score"], reason=item["reason"])
        db.session.add(match)
        db.session.flush()
        results.append(match.to_dict())
    db.session.commit()
    results.sort(key=lambda item: item["score"], reverse=True)
    return results
