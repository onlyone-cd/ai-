from . import db
from .auth import hash_password
from .experience_analysis import analyze_experience
from .models import Candidate, CandidateTag, Job, PipelineStage, User
from .resume_service import extract_profile, is_probable_name


def seed_demo_data():
    if User.query.first():
        return

    admin = User(username="admin", name="管理员", role="admin", password_hash=hash_password("admin123"))
    manager = User(username="manager", name="招聘经理", role="manager", password_hash=hash_password("admin123"))
    recruiter = User(username="recruiter", name="HR Alice", role="recruiter", password_hash=hash_password("admin123"))
    db.session.add_all([admin, manager, recruiter])
    db.session.flush()

    candidates = [
        {
            "owner_hr_id": recruiter.id,
            "name_masked": "李华",
            "email_masked": "lihua@example.com",
            "phone_masked": "13812342301",
            "title": "总账会计",
            "source": "boss",
            "city": "上海",
            "raw_text": "5 年总账会计经验，熟悉财务核算、纳税申报、财务报表、Excel、金蝶，用友系统。",
            "tags": [("总账会计", 5, "财务/会计"), ("财务核算", 4, "财务/会计"), ("纳税申报", 4, "财务/会计"), ("财务报表", 4, "财务/会计"), ("Excel", 5, "工具"), ("金蝶", 3, "工具")],
        },
        {
            "owner_hr_id": recruiter.id,
            "name_masked": "王强",
            "email_masked": "wangqiang@example.com",
            "phone_masked": "13688888820",
            "title": "Python 后端工程师",
            "source": "upload",
            "city": "杭州",
            "raw_text": "4 年 Python 后端开发经验，使用 Flask、FastAPI、SQL、Redis、Docker，负责招聘系统服务端开发。",
            "tags": [("Python", 5, "编程语言"), ("Flask", 4, "框架工具"), ("FastAPI", 4, "框架工具"), ("SQL", 4, "数据库"), ("Redis", 3, "数据库"), ("Docker", 3, "工具")],
        },
        {
            "owner_hr_id": manager.id,
            "name_masked": "陈敏",
            "email_masked": "chenmin@example.com",
            "phone_masked": "13955226172",
            "title": "招聘专员",
            "source": "upload",
            "city": "苏州",
            "raw_text": "2 年招聘经验，负责简历筛选、面试安排、员工关系基础支持，熟悉绩效和薪酬流程。",
            "tags": [("招聘", 4, "人力资源"), ("面试安排", 3, "人力资源"), ("员工关系", 2, "人力资源"), ("绩效", 2, "人力资源"), ("薪酬", 2, "人力资源")],
        },
        {
            "owner_hr_id": recruiter.id,
            "name_masked": "赵晴",
            "email_masked": "zhaoqing@example.com",
            "phone_masked": "13766669921",
            "title": "应届前端开发",
            "source": "boss",
            "city": "南京",
            "raw_text": "应届毕业生，校招方向，熟悉 React、TypeScript、Vite、JavaScript，有实习项目经验。",
            "tags": [("React", 3, "框架工具"), ("TypeScript", 3, "编程语言"), ("Vite", 2, "框架工具"), ("JavaScript", 3, "编程语言")],
        },
    ]

    created_candidates = []
    for payload in candidates:
        tags = payload.pop("tags")
        analysis = analyze_experience(payload["raw_text"])
        candidate = Candidate(
            **payload,
            resume_json={
                "name": payload["name_masked"],
                "email": payload["email_masked"],
                "phone": payload["phone_masked"],
                "gender": infer_demo_gender(payload["name_masked"]),
                "summary": payload["raw_text"],
                "experience_analysis": analysis,
                "education": [],
                "experience": [{"company": "Demo 公司", "description": payload["raw_text"]}],
                "projects": [],
            },
        )
        db.session.add(candidate)
        db.session.flush()
        for tag, score, category in tags:
            db.session.add(CandidateTag(candidate_id=candidate.id, tag=tag, score=score, category=category))
        created_candidates.append(candidate)

    jobs = [
        Job(
            owner_hr_id=manager.id,
            title="财务会计主管",
            city="上海",
            department="财务部",
            job_code="FIN-001",
            jd_text="需要 3 年以上会计经验，熟悉总账会计、财务报表、纳税申报、Excel、金蝶。",
            jd_structured={"skill_tags_raw": "总账会计 5|财务报表 4|纳税申报 4|Excel 3|金蝶 2"},
        ),
        Job(
            owner_hr_id=manager.id,
            title="Python 后端工程师",
            city="杭州",
            department="研发部",
            job_code="RD-001",
            jd_text="负责 Flask/FastAPI 服务开发，需要 Python、SQL、Redis、Docker 经验。",
            jd_structured={"skill_tags_raw": "Python 5|Flask 4|SQL 4|Redis 3|Docker 2"},
        ),
        Job(
            owner_hr_id=manager.id,
            title="招聘专员",
            city="苏州",
            department="人力资源部",
            job_code="HR-001",
            jd_text="负责招聘、简历筛选、面试安排，了解员工关系、绩效和薪酬流程优先。",
            jd_structured={"skill_tags_raw": "招聘 5|面试安排 4|员工关系 2|绩效 2|薪酬 2"},
        ),
    ]
    db.session.add_all(jobs)
    db.session.flush()

    db.session.add_all(
        [
            PipelineStage(candidate_id=created_candidates[0].id, job_id=jobs[0].id, stage="business_review", updated_by=manager.id, note="会计岗位高匹配"),
            PipelineStage(candidate_id=created_candidates[1].id, job_id=jobs[1].id, stage="interview_first", updated_by=manager.id, note="安排一面"),
            PipelineStage(candidate_id=created_candidates[2].id, job_id=jobs[2].id, stage="pending", updated_by=recruiter.id, note="待 HR 初筛"),
        ]
    )
    db.session.commit()


def sync_plain_profile_fields():
    demo_profiles_by_name = {
        "李**": {"name": "李华", "email": "lihua@example.com", "phone": "13812342301", "gender": "男"},
        "王**": {"name": "王强", "email": "wangqiang@example.com", "phone": "13688888820", "gender": "男"},
        "陈**": {"name": "陈敏", "email": "chenmin@example.com", "phone": "13955226172", "gender": "女"},
        "赵**": {"name": "赵晴", "email": "zhaoqing@example.com", "phone": "13766669921", "gender": "女"},
    }
    demo_profiles_by_phone = {profile["phone"]: profile for profile in demo_profiles_by_name.values()}
    changed = False
    for candidate in Candidate.query.all():
        profile = demo_profiles_by_name.get(candidate.name_masked) or demo_profiles_by_phone.get(candidate.phone_masked)
        if profile:
            candidate.name_masked = profile["name"]
            candidate.email_masked = profile["email"]
            candidate.phone_masked = profile["phone"]
            candidate.resume_json = {**(candidate.resume_json or {}), **profile}
            changed = True
            continue

        profile = candidate.resume_json or {}
        if candidate.raw_text:
            extracted = extract_profile(candidate.raw_text)
            extracted_profile = {key: value for key, value in extracted.items() if value and key in {"email", "phone", "gender"}}
            if extracted.get("name") and extracted["name"] != "候选人":
                extracted_profile["name"] = extracted["name"]
            profile = {
                **profile,
                **extracted_profile,
            }
        if profile.get("name") and candidate.name_masked != profile["name"]:
            candidate.name_masked = profile["name"]
            changed = True
        elif not profile.get("name") and not is_probable_name(candidate.name_masked):
            candidate.name_masked = "候选人"
            changed = True
        if profile.get("email") and candidate.email_masked != profile["email"]:
            candidate.email_masked = profile["email"]
            changed = True
        if profile.get("phone") and candidate.phone_masked != profile["phone"]:
            candidate.phone_masked = profile["phone"]
            changed = True
        profile_payload = {key: profile[key] for key in ("name", "email", "phone", "gender") if profile.get(key)}
        if profile_payload and any((candidate.resume_json or {}).get(key) != value for key, value in profile_payload.items()):
            candidate.resume_json = {**(candidate.resume_json or {}), **profile_payload}
            changed = True
    if changed:
        db.session.commit()


def infer_demo_gender(name):
    return {"李华": "男", "王强": "男", "陈敏": "女", "赵晴": "女"}.get(name, "")
