"""
人才画像构建服务 — Talent Profile Builder

基于候选人简历数据，构建 360° 人才画像：
- 能力标签（技能矩阵 + 熟练度）
- 项目亮点 & 职业轨迹
- 风险提示（跳槽频率、空窗期、薪资预期偏离）
- 胜任力模型映射
"""

from collections import Counter, defaultdict
from datetime import datetime, timezone
from statistics import mean

from flask import current_app

from . import db
from .llm_client import LLMError, chat_json, llm_available
from .models import Candidate, CandidateTag, EmployeeProfile, Job, Match, utcnow
from .tag_library import label_map


def build_talent_profile(candidate_or_employee, is_employee=False):
    """构建 360° 人才画像"""
    if is_employee:
        profile = candidate_or_employee
        raw_text = profile.raw_text or ""
        resume_json = profile.resume_json or {}
        tags = []
        source = "internal"
        name = profile.name
        title = profile.current_title or ""
    else:
        profile = candidate_or_employee
        raw_text = profile.raw_text or ""
        resume_json = profile.resume_json or {}
        tags = CandidateTag.query.filter_by(candidate_id=profile.id).all()
        source = profile.source or "unknown"
        name = profile.name_masked or ""
        title = profile.title or ""

    # 基础信息
    basic = extract_basic_info(profile, resume_json, name, title, source)

    # 技能矩阵
    skill_matrix = build_skill_matrix(tags, resume_json)

    # 职业轨迹
    career_timeline = extract_career_timeline(resume_json, raw_text)

    # 项目亮点
    project_highlights = extract_project_highlights(resume_json)

    # 风险提示
    risk_flags = assess_risks(profile, resume_json, career_timeline, is_employee)

    # 胜任力维度
    competency = infer_competency_dimensions(tags, skill_matrix, title)

    # 综合分析（AI 增强）
    ai_analysis = ""
    if llm_available():
        try:
            ai_analysis = request_ai_profile_analysis(name, title, skill_matrix, career_timeline, risk_flags, raw_text[:2000])
        except (LLMError, Exception):
            ai_analysis = ""

    return {
        "basic": basic,
        "skill_matrix": skill_matrix,
        "career_timeline": career_timeline,
        "project_highlights": project_highlights,
        "risk_flags": risk_flags,
        "competency": competency,
        "ai_analysis": ai_analysis,
        "generated_at": utcnow().isoformat(),
    }


def extract_basic_info(profile, resume_json, name, title, source):
    """提取基础信息"""
    edu = resume_json.get("education", [])
    highest_edu = ""
    if edu:
        degrees = {"博士": 5, "硕士": 4, "本科": 3, "大专": 2, "高中": 1}
        highest_edu = max(edu, key=lambda e: degrees.get(e.get("degree", ""), 0)).get("degree", "")
    return {
        "name": name,
        "title": title,
        "source": source,
        "gender": resume_json.get("gender", ""),
        "city": getattr(profile, "city", "") or "",
        "phone": getattr(profile, "phone_masked", "") or "",
        "email": getattr(profile, "email_masked", "") or "",
        "highest_education": highest_edu,
        "experience_years": resume_json.get("experience_analysis", {}).get("years", 0),
        "experience_level": resume_json.get("experience_analysis", {}).get("level", ""),
    }


def build_skill_matrix(tags, resume_json):
    """构建技能矩阵（按类别分组 + 熟练度）"""
    categories = defaultdict(list)
    for tag in tags:
        tag_name = tag.tag if hasattr(tag, "tag") else tag.get("tag", "")
        score = tag.score if hasattr(tag, "score") else tag.get("score", 0)
        category = tag.category if hasattr(tag, "category") else tag.get("category", "未分类")
        categories[category].append({
            "name": tag_name,
            "proficiency": score,
            "level": proficiency_label(score),
        })
    return dict(categories)


def proficiency_label(score):
    if score >= 5:
        return "专家"
    if score >= 4:
        return "熟练"
    if score >= 3:
        return "掌握"
    if score >= 2:
        return "了解"
    return "入门"


def extract_career_timeline(resume_json, raw_text):
    """提取职业轨迹"""
    experience = resume_json.get("experience", [])
    if not experience:
        return []

    timeline = []
    for exp in experience:
        company = exp.get("company", "")
        title = exp.get("title", "")
        period = exp.get("period", "")
        desc = (exp.get("description", "") or "")[:120]
        timeline.append({
            "company": company,
            "title": title,
            "period": period,
            "description": desc,
            "duration_months": estimate_duration_months(period),
        })

    timeline.sort(key=lambda x: x["duration_months"] or 0, reverse=True)
    return timeline


def extract_project_highlights(resume_json):
    """提取项目亮点"""
    projects = resume_json.get("projects", [])
    if not projects:
        return []
    highlights = []
    for p in projects[:6]:
        name = p.get("name", "")
        role = p.get("role", "")
        desc = (p.get("description", "") or "")[:150]
        if name or desc:
            highlights.append({"name": name, "role": role, "description": desc})
    return highlights


def assess_risks(profile, resume_json, career_timeline, is_employee):
    """评估风险点"""
    risks = []
    raw_text = (profile.raw_text or "") if not is_employee else (profile.raw_text or "")

    # 跳槽频率
    if len(career_timeline) >= 4:
        avg_months = mean(t.get("duration_months", 0) or 0 for t in career_timeline if t.get("duration_months"))
        if avg_months < 18:
            risks.append({
                "type": "high_turnover",
                "label": "跳槽频繁",
                "detail": f"平均每段工作 {avg_months:.0f} 个月，建议关注稳定性",
                "severity": "warning",
            })

    # 空窗期
    if "空窗" in raw_text or "待业" in raw_text or "gap" in raw_text.lower():
        risks.append({
            "type": "career_gap",
            "label": "存在职业空窗期",
            "detail": "简历中出现空窗/待业记录，建议面试中了解具体原因",
            "severity": "info",
        })

    # 薪资预期偏离（仅员工）
    if is_employee:
        comp = profile.compensation if hasattr(profile, "compensation") else None
        if comp and comp.salary_monthly_k:
            risks.append({
                "type": "salary_data_available",
                "label": "薪资信息已记录",
                "detail": f"月薪 {comp.salary_monthly_k}K",
                "severity": "info",
            })

    # 简历完整度
    text_len = len(raw_text.strip())
    if text_len < 200:
        risks.append({
            "type": "incomplete_resume",
            "label": "简历内容不完整",
            "detail": "简历篇幅较短，建议补充更多项目经历和技能描述",
            "severity": "warning",
        })
    elif text_len > 5000:
        risks.append({
            "type": "verbose_resume",
            "label": "简历过于冗长",
            "detail": "简历篇幅较长，建议精简至关键信息",
            "severity": "info",
        })

    return risks


def infer_competency_dimensions(tags, skill_matrix, title):
    """推断胜任力维度"""
    dimensions = {
        "专业能力": {"score": 0, "tags": []},
        "工具技能": {"score": 0, "tags": []},
        "软技能": {"score": 0, "tags": []},
        "行业经验": {"score": 0, "tags": []},
    }

    for category, skills in skill_matrix.items():
        avg_score = mean(s["proficiency"] for s in skills) if skills else 0
        if category in {"编程语言", "框架", "数据库", "技术方向"}:
            dimensions["专业能力"]["score"] = max(dimensions["专业能力"]["score"], avg_score)
            dimensions["专业能力"]["tags"].extend(s["name"] for s in skills[:3])
        elif category in {"设计工具", "办公工具", "工程工具"}:
            dimensions["工具技能"]["score"] = max(dimensions["工具技能"]["score"], avg_score)
            dimensions["工具技能"]["tags"].extend(s["name"] for s in skills[:3])
        elif category in {"软技能", "管理能力", "沟通能力"}:
            dimensions["软技能"]["score"] = max(dimensions["软技能"]["score"], avg_score)
            dimensions["软技能"]["tags"].extend(s["name"] for s in skills[:3])
        else:
            dimensions["行业经验"]["score"] = max(dimensions["行业经验"]["score"], avg_score)
            dimensions["行业经验"]["tags"].extend(s["name"] for s in skills[:3])

    for dim in dimensions.values():
        dim["score"] = round(min(dim["score"], 5), 1)
        dim["level"] = proficiency_label(dim["score"])

    return dimensions


def estimate_duration_months(period):
    """估算工作持续月数"""
    if not period:
        return None
    import re
    nums = re.findall(r"\d+", period)
    if len(nums) >= 2:
        try:
            start_y, start_m = int(nums[0]), int(nums[1]) if len(nums) > 1 else 1
            end_y, end_m = int(nums[-2]), int(nums[-1])
            return (end_y - start_y) * 12 + (end_m - start_m)
        except (ValueError, IndexError):
            pass
    return None


def request_ai_profile_analysis(name, title, skill_matrix, career_timeline, risk_flags, raw_text_sample):
    """AI 深度分析人才画像"""
    top_skills = []
    for cat, skills in skill_matrix.items():
        top_skills.extend(s["name"] for s in skills[:3])
    top_skills = top_skills[:8]

    companies = [t["company"] for t in career_timeline[:4] if t["company"]]
    risks = [r["label"] for r in risk_flags]

    prompt = (
        f"分析以下人才画像，输出核心优势、待发展项、推荐岗位类型、发展建议。\n"
        f"姓名：{name}\n职位：{title}\n"
        f"核心技能：{', '.join(top_skills)}\n"
        f"经历公司：{', '.join(companies)}\n"
        f"风险提示：{', '.join(risks)}\n"
        f"简历样本：{raw_text_sample[:800]}\n"
        "输出 JSON：{\"strengths\":[], \"growth_areas\":[], \"recommended_roles\":[], \"development_advice\":\"\"}"
    )
    result = chat_json([
        {"role": "system", "content": "你是资深 HR 人才分析师。基于简历数据输出客观的人才评价。输出 JSON。"},
        {"role": "user", "content": prompt},
    ], source="talent_profile", tool_name="profile_analysis")
    return result


def batch_talent_profiles(candidate_ids=None, employee_ids=None, limit=10):
    """批量构建人才画像"""
    results = []
    if candidate_ids:
        candidates = Candidate.query.filter(Candidate.id.in_(candidate_ids)).limit(limit).all()
        for c in candidates:
            results.append({"id": c.id, "type": "candidate", "profile": build_talent_profile(c)})
    if employee_ids:
        employees = EmployeeProfile.query.filter(EmployeeProfile.id.in_(employee_ids)).limit(limit).all()
        for e in employees:
            results.append({"id": e.id, "type": "employee", "profile": build_talent_profile(e, is_employee=True)})
    return results
