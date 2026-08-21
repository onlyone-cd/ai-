"""
AI Deep Insight Service — 招聘深度洞察

分析招聘各环节数据，提供 AI 驱动洞察：
- 招聘漏斗瓶颈分析
- 渠道效果归因
- 招聘周期预测
- 面试官评分偏差
- 候选人流失原因
- Offer 转化率分析
"""

from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from statistics import mean, stdev

from flask import current_app
from sqlalchemy import func

from . import db
from .llm_client import LLMError, chat_json, llm_available
from .models import (
    Candidate,
    CandidateTag,
    EmployeeProfile,
    InterviewAssignment,
    InterviewFeedback,
    Job,
    Match,
    OfferRecord,
    PipelineStage,
    User,
    utcnow,
)


def funnel_analysis(days=90):
    """招聘漏斗分析：各阶段候选人数量、流失率、瓶颈环节"""
    since = utcnow() - timedelta(days=days)
    stages = ["pending", "ai_screen", "business_review", "interview_first", "interview_second", "interview_final", "offer", "onboarded", "rejected"]

    # 每个阶段进入过的候选人（去重）
    stage_counts = {}
    for stage in stages:
        count = (
            db.session.query(func.count(func.distinct(PipelineStage.candidate_id)))
            .filter(PipelineStage.stage == stage, PipelineStage.ts >= since)
            .scalar()
            or 0
        )
        stage_counts[stage] = count

    # 流失率计算：从上一阶段到本阶段的流失
    funnel = []
    prev_count = stage_counts.get(stages[0], 0)
    for stage in stages:
        current = stage_counts.get(stage, 0)
        drop_off = prev_count - current if prev_count > 0 else 0
        drop_rate = round(drop_off / prev_count * 100, 1) if prev_count > 0 else 0
        funnel.append({
            "stage": stage,
            "entered": current,
            "dropped_off": max(drop_off, 0),
            "drop_rate": drop_rate,
            "is_bottleneck": drop_rate > 40 and current > 0,
        })
        prev_count = current

    # 瓶颈识别
    bottlenecks = [s for s in funnel if s["is_bottleneck"]]
    bottleneck_analysis = ""
    if bottlenecks and llm_available():
        top = bottlenecks[:3]
        try:
            result = chat_json([
                {"role": "system", "content": "你是招聘数据分析专家。分析招聘漏斗瓶颈原因，给出优化建议。输出 JSON。"},
                {"role": "user", "content": f"以下阶段流失率超过40%: {[s['stage'] for s in top]}。平均流失率{sum(s['drop_rate'] for s in funnel)/len(funnel):.1f}%。请分析原因并给出建议。"},
            ], source="insight", tool_name="funnel_analysis")
            bottleneck_analysis = result.get("analysis", "")
        except (LLMError, Exception):
            bottleneck_analysis = "瓶颈环节需要人工复核具体原因。"

    return {
        "funnel": funnel,
        "bottlenecks": [s["stage"] for s in bottlenecks],
        "bottleneck_analysis": bottleneck_analysis,
    }


def channel_effectiveness(days=90):
    """渠道效果分析：各来源候选人的质量、转化率"""
    since = utcnow() - timedelta(days=days)
    candidates = Candidate.query.filter(Candidate.created_at >= since).all()
    if not candidates:
        return {"channels": [], "total": 0}

    source_map = defaultdict(lambda: {"total": 0, "onboarded": 0, "rejected": 0, "in_pipeline": 0, "avg_score": 0, "scores": []})
    for c in candidates:
        source = c.source or "unknown"
        source_map[source]["total"] += 1

        # 流程状态
        latest = PipelineStage.query.filter_by(candidate_id=c.id).order_by(PipelineStage.ts.desc()).first()
        if latest:
            if latest.stage == "onboarded":
                source_map[source]["onboarded"] += 1
            elif latest.stage == "rejected":
                source_map[source]["rejected"] += 1
            else:
                source_map[source]["in_pipeline"] += 1
        else:
            source_map[source]["in_pipeline"] += 1

        # 匹配分
        best = Match.query.filter_by(candidate_id=c.id).order_by(Match.score.desc()).first()
        if best:
            source_map[source]["scores"].append(best.score)

    channels = []
    for source, data in source_map.items():
        avg_score = round(mean(data["scores"]), 1) if data["scores"] else 0
        onboard_rate = round(data["onboarded"] / data["total"] * 100, 1) if data["total"] > 0 else 0
        channels.append({
            "source": source,
            "total": data["total"],
            "onboarded": data["onboarded"],
            "rejected": data["rejected"],
            "in_pipeline": data["in_pipeline"],
            "onboard_rate": onboard_rate,
            "avg_match_score": avg_score,
        })

    channels.sort(key=lambda x: x["onboard_rate"], reverse=True)
    return {"channels": channels, "total": len(candidates)}


def time_to_hire_analysis(days=180):
    """招聘周期分析：从创建到入职的平均天数"""
    since = utcnow() - timedelta(days=days)

    # 找到有入职记录且有时间线的候选人
    onboarded = (
        db.session.query(PipelineStage.candidate_id, func.min(PipelineStage.ts).label("first_ts"))
        .filter(PipelineStage.stage == "pending", PipelineStage.ts >= since)
        .group_by(PipelineStage.candidate_id)
        .subquery()
    )
    hired = (
        db.session.query(PipelineStage.candidate_id, func.min(PipelineStage.ts).label("hired_ts"))
        .filter(PipelineStage.stage == "onboarded", PipelineStage.ts >= since)
        .group_by(PipelineStage.candidate_id)
        .subquery()
    )
    result = (
        db.session.query(onboarded.c.first_ts, hired.c.hired_ts)
        .join(hired, onboarded.c.candidate_id == hired.c.candidate_id)
        .all()
    )

    days_list = [(r.hired_ts - r.first_ts).days for r in result if r.first_ts and r.hired_ts]
    if not days_list:
        return {"avg_days": 0, "median_days": 0, "min_days": 0, "max_days": 0, "samples": 0, "ai_analysis": ""}

    sorted_days = sorted(days_list)
    n = len(sorted_days)
    result_data = {
        "avg_days": round(mean(days_list), 1),
        "median_days": sorted_days[n // 2] if n % 2 else round((sorted_days[n // 2 - 1] + sorted_days[n // 2]) / 2, 1),
        "min_days": sorted_days[0],
        "max_days": sorted_days[-1],
        "samples": n,
    }

    if llm_available():
        try:
            ai = chat_json([
                {"role": "system", "content": "你是招聘数据分析专家。分析招聘周期数据，给出招聘效率评价和优化建议。输出JSON。"},
                {"role": "user", "content": f"招聘周期(天): 平均{result_data['avg_days']}, 中位数{result_data['median_days']}, 范围{result_data['min_days']}-{result_data['max_days']}, 样本{result_data['samples']}。请做出评价。"},
            ], source="insight", tool_name="time_to_hire")
            result_data["ai_analysis"] = ai.get("analysis", "")
        except (LLMError, Exception):
            result_data["ai_analysis"] = ""

    return result_data


def interviewer_bias_analysis(days=180):
    """面试官评分偏差分析"""
    since = utcnow() - timedelta(days=days)
    feedbacks = InterviewFeedback.query.filter(InterviewFeedback.created_at >= since).all()
    if not feedbacks:
        return {"interviewers": [], "total_feedbacks": 0}

    by_interviewer = defaultdict(list)
    for fb in feedbacks:
        assignment = db.session.get(InterviewAssignment, fb.assignment_id)
        if assignment:
            by_interviewer[assignment.interviewer_id].append(fb.rating)

    all_ratings = [fb.rating for fb in feedbacks if fb.rating]
    global_avg = mean(all_ratings) if all_ratings else 0
    global_std = stdev(all_ratings) if len(all_ratings) > 1 else 0

    interviewers = []
    for interviewer_id, ratings in by_interviewer.items():
        user = db.session.get(User, interviewer_id)
        avg = mean(ratings) if ratings else 0
        std = stdev(ratings) if len(ratings) > 1 else 0
        bias = round(avg - global_avg, 1) if global_avg else 0
        interviewers.append({
            "interviewer_id": interviewer_id,
            "interviewer_name": user.name if user else f"用户{interviewer_id}",
            "avg_rating": round(avg, 1),
            "std": round(std, 1),
            "count": len(ratings),
            "bias": bias,
            "bias_direction": "偏高" if bias > 1 else ("偏低" if bias < -1 else "正常"),
        })

    interviewers.sort(key=lambda x: abs(x["bias"]), reverse=True)
    return {
        "interviewers": interviewers,
        "global_avg_rating": round(global_avg, 1),
        "global_std": round(global_std, 1),
        "total_feedbacks": len(all_ratings),
    }


def offer_conversion_analysis(days=180):
    """Offer 转化分析"""
    since = utcnow() - timedelta(days=days)
    offers = OfferRecord.query.filter(OfferRecord.created_at >= since).all()
    if not offers:
        return {"total": 0, "accepted": 0, "declined": 0, "cancelled": 0, "acceptance_rate": 0, "avg_salary": {}}

    status_count = Counter(o.status for o in offers)
    accepted = [o for o in offers if o.status == "accepted"]
    declined = [o for o in offers if o.status == "declined"]

    salaries = []
    for o in accepted:
        if o.salary_min_k and o.salary_max_k:
            salaries.append((o.salary_min_k + o.salary_max_k) / 2)

    return {
        "total": len(offers),
        "accepted": status_count.get("accepted", 0),
        "declined": status_count.get("declined", 0),
        "cancelled": status_count.get("cancelled", 0),
        "sent": status_count.get("sent", 0),
        "draft": status_count.get("draft", 0),
        "acceptance_rate": round(status_count.get("accepted", 0) / max(len(offers), 1) * 100, 1),
        "avg_salary": round(mean(salaries), 1) if salaries else 0,
    }


def pipeline_bottleneck_analysis(days=90):
    """流程瓶颈深度分析 + AI 建议"""
    funnel = funnel_analysis(days)
    return {
        "funnel": funnel["funnel"],
        "bottlenecks": funnel["bottlenecks"],
        "ai_analysis": funnel["bottleneck_analysis"],
    }


def overall_insight_report(days=90):
    """综合洞察报告"""
    return {
        "period_days": days,
        "funnel": funnel_analysis(days),
        "channels": channel_effectiveness(days),
        "time_to_hire": time_to_hire_analysis(days),
        "interviewer_bias": interviewer_bias_analysis(days),
        "offer_conversion": offer_conversion_analysis(days),
        "generated_at": utcnow().isoformat(),
    }
