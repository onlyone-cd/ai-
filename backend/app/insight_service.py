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
from threading import Lock
from time import monotonic

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


_report_cache = {}
_report_cache_lock = Lock()
FUNNEL_STAGES = [
    "pending",
    "ai_screen",
    "business_review",
    "interview_first",
    "interview_second",
    "interview_final",
    "offer",
    "onboarded",
]


def funnel_analysis(days=90, use_ai=True):
    """按统计期内新进入流程的候选人-岗位组合计算招聘漏斗。

    候选人可能跳过中间阶段或回退，因此以其最高到达阶段推断已通过的前置
    阶段，保证漏斗人数单调递减。淘汰是退出结果，不作为入职后的漏斗阶段。
    """
    since = utcnow() - timedelta(days=days)
    now = utcnow()
    first_events = (
        db.session.query(
            PipelineStage.candidate_id.label("candidate_id"),
            PipelineStage.job_id.label("job_id"),
            func.min(PipelineStage.ts).label("first_ts"),
        )
        .group_by(PipelineStage.candidate_id, PipelineStage.job_id)
        .having(func.min(PipelineStage.ts) >= since)
        .subquery()
    )
    rows = (
        db.session.query(
            PipelineStage.candidate_id,
            PipelineStage.job_id,
            PipelineStage.stage,
            PipelineStage.ts,
            PipelineStage.id,
        )
        .join(
            first_events,
            (first_events.c.candidate_id == PipelineStage.candidate_id)
            & (first_events.c.job_id == PipelineStage.job_id),
        )
        .filter(PipelineStage.ts <= now)
        .order_by(PipelineStage.candidate_id, PipelineStage.job_id, PipelineStage.ts, PipelineStage.id)
        .all()
    )

    stage_index = {stage: index for index, stage in enumerate(FUNNEL_STAGES)}
    highest_stage = {}
    latest_stage = {}
    for candidate_id, job_id, stage, _, _ in rows:
        application = (candidate_id, job_id)
        latest_stage[application] = stage
        if stage in stage_index:
            highest_stage[application] = max(highest_stage.get(application, -1), stage_index[stage])

    stage_counts = {
        stage: sum(highest >= index for highest in highest_stage.values())
        for index, stage in enumerate(FUNNEL_STAGES)
    }

    funnel = []
    for index, stage in enumerate(FUNNEL_STAGES):
        current = stage_counts.get(stage, 0)
        next_count = stage_counts.get(FUNNEL_STAGES[index + 1], current) if index + 1 < len(FUNNEL_STAGES) else current
        drop_off = max(current - next_count, 0)
        drop_rate = round(drop_off / current * 100, 1) if current else 0
        funnel.append({
            "stage": stage,
            "entered": current,
            "dropped_off": drop_off,
            "drop_rate": drop_rate,
            "is_bottleneck": drop_rate > 40 and drop_off > 0,
        })

    # 瓶颈识别
    bottlenecks = [s for s in funnel if s["is_bottleneck"]]
    bottleneck_analysis = ""
    if bottlenecks and use_ai and llm_available():
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
        "cohort_size": len(highest_stage),
        "rejected": sum(stage == "rejected" for stage in latest_stage.values()),
    }


def channel_effectiveness(days=90):
    """渠道效果分析：各来源候选人的质量、转化率"""
    since = utcnow() - timedelta(days=days)
    candidates = Candidate.query.filter(Candidate.created_at >= since).all()
    if not candidates:
        return {"channels": [], "total": 0}

    candidate_ids = [candidate.id for candidate in candidates]
    latest_stages = {}
    for candidate_id, stage in (
        db.session.query(PipelineStage.candidate_id, PipelineStage.stage)
        .filter(PipelineStage.candidate_id.in_(candidate_ids))
        .order_by(PipelineStage.candidate_id, PipelineStage.ts.desc(), PipelineStage.id.desc())
        .all()
    ):
        latest_stages.setdefault(candidate_id, stage)

    best_scores = dict(
        db.session.query(Match.candidate_id, func.max(Match.score))
        .filter(Match.candidate_id.in_(candidate_ids))
        .group_by(Match.candidate_id)
        .all()
    )

    source_map = defaultdict(lambda: {"total": 0, "onboarded": 0, "rejected": 0, "in_pipeline": 0, "scores": []})
    for c in candidates:
        source = c.source or "unknown"
        source_map[source]["total"] += 1

        # 流程状态
        latest_stage = latest_stages.get(c.id)
        if latest_stage:
            if latest_stage == "onboarded":
                source_map[source]["onboarded"] += 1
            elif latest_stage == "rejected":
                source_map[source]["rejected"] += 1
            else:
                source_map[source]["in_pipeline"] += 1
        else:
            source_map[source]["in_pipeline"] += 1

        # 匹配分
        best_score = best_scores.get(c.id)
        if best_score is not None:
            source_map[source]["scores"].append(best_score)

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


def time_to_hire_analysis(days=180, use_ai=True):
    """招聘周期分析：从创建到入职的平均天数"""
    since = utcnow() - timedelta(days=days)

    # 以候选人-岗位为一次招聘流程，避免同一候选人的不同岗位时间线相互串联。
    applications = (
        db.session.query(
            PipelineStage.candidate_id.label("candidate_id"),
            PipelineStage.job_id.label("job_id"),
            func.min(PipelineStage.ts).label("first_ts"),
        )
        .group_by(PipelineStage.candidate_id, PipelineStage.job_id)
        .having(func.min(PipelineStage.ts) >= since)
        .subquery()
    )
    hired = (
        db.session.query(
            PipelineStage.candidate_id.label("candidate_id"),
            PipelineStage.job_id.label("job_id"),
            func.min(PipelineStage.ts).label("hired_ts"),
        )
        .filter(PipelineStage.stage == "onboarded")
        .group_by(PipelineStage.candidate_id, PipelineStage.job_id)
        .subquery()
    )
    result = (
        db.session.query(applications.c.first_ts, hired.c.hired_ts)
        .join(
            hired,
            (applications.c.candidate_id == hired.c.candidate_id)
            & (applications.c.job_id == hired.c.job_id),
        )
        .all()
    )

    days_list = [
        max((row.hired_ts - row.first_ts).days, 0)
        for row in result
        if row.first_ts and row.hired_ts and row.hired_ts >= row.first_ts
    ]
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

    if use_ai and llm_available():
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
    feedback_rows = (
        db.session.query(
            InterviewFeedback.rating,
            InterviewAssignment.interviewer_id,
            User.name,
        )
        .join(InterviewAssignment, InterviewAssignment.id == InterviewFeedback.assignment_id)
        .outerjoin(User, User.id == InterviewAssignment.interviewer_id)
        .filter(InterviewFeedback.created_at >= since)
        .all()
    )
    if not feedback_rows:
        return {
            "interviewers": [],
            "global_avg_rating": 0,
            "global_std": 0,
            "total_feedbacks": 0,
        }

    by_interviewer = defaultdict(list)
    interviewer_names = {}
    for rating, interviewer_id, interviewer_name in feedback_rows:
        if rating is not None:
            by_interviewer[interviewer_id].append(rating)
        interviewer_names[interviewer_id] = interviewer_name or f"用户{interviewer_id}"

    all_ratings = [rating for rating, _, _ in feedback_rows if rating is not None]
    global_avg = mean(all_ratings) if all_ratings else 0
    global_std = stdev(all_ratings) if len(all_ratings) > 1 else 0

    interviewers = []
    for interviewer_id, ratings in by_interviewer.items():
        avg = mean(ratings) if ratings else 0
        std = stdev(ratings) if len(ratings) > 1 else 0
        bias = round(avg - global_avg, 1) if global_avg else 0
        interviewers.append({
            "interviewer_id": interviewer_id,
            "interviewer_name": interviewer_names[interviewer_id],
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
        return {
            "total": 0,
            "accepted": 0,
            "declined": 0,
            "cancelled": 0,
            "sent": 0,
            "draft": 0,
            "acceptance_rate": 0,
            "avg_salary": 0,
        }

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


def overall_insight_report(days=90, force_refresh=False):
    """综合洞察报告。

    页面首屏使用数据库规则分析，避免等待外部大模型；单项深度分析仍可使用 AI。
    同一进程内短时缓存报告，减少频繁切换页面造成的重复聚合查询。
    """
    cache_seconds = max(float(current_app.config.get("INSIGHT_REPORT_CACHE_SECONDS", 60)), 0)
    cache_key = int(days)
    now = monotonic()
    if force_refresh:
        with _report_cache_lock:
            _report_cache.pop(cache_key, None)
    if cache_seconds > 0:
        with _report_cache_lock:
            cached = _report_cache.get(cache_key)
            if cached and now - cached[0] < cache_seconds:
                return cached[1]

    report = {
        "period_days": days,
        "funnel": funnel_analysis(days, use_ai=False),
        "channels": channel_effectiveness(days),
        "time_to_hire": time_to_hire_analysis(days, use_ai=False),
        "interviewer_bias": interviewer_bias_analysis(days),
        "offer_conversion": offer_conversion_analysis(days),
        "generated_at": utcnow().isoformat(),
    }
    if cache_seconds > 0:
        with _report_cache_lock:
            _report_cache[cache_key] = (now, report)
            expired = [key for key, value in _report_cache.items() if now - value[0] >= cache_seconds]
            for key in expired:
                _report_cache.pop(key, None)
    return report
