import re

from .tag_library import has_category_context, label_map

RELATED_SETS = [
    ({"会计", "总账会计", "财务核算", "财务报表"}, 0.85),
    ({"税务", "纳税申报"}, 0.85),
    ({"Python", "Flask", "Django", "FastAPI"}, 0.75),
    ({"Java", "Spring", "Spring Boot", "Spring Cloud", "MyBatis"}, 0.78),
    ({"JavaScript", "TypeScript", "React", "Vue"}, 0.75),
    ({"SQL", "MySQL", "PostgreSQL", "Oracle", "SQL Server"}, 0.72),
    ({"Docker", "Kubernetes"}, 0.65),
    ({"采购", "供应商", "供应链"}, 0.75),
]

EXACT_ONLY_TAGS = {"Excel", "PowerPoint", "Word", "金蝶", "用友", "SAP"}
FINANCE_SYSTEM_TAGS = {"金蝶", "用友", "ERP财务"}

ALIASES = {
    "js": "javascript",
    "ts": "typescript",
    "py": "python",
    "nodejs": "node.js",
    "node js": "node.js",
    "k8s": "kubernetes",
}


def normalize(tag):
    value = re.sub(r"\s+", "", str(tag or "")).lower()
    return ALIASES.get(value, value)


def parse_skill_tags(raw):
    if isinstance(raw, list):
        return [{"tag": item.get("tag"), "weight": int(item.get("weight", 3))} for item in raw if item.get("tag")]
    if not raw:
        return []
    result = []
    for part in re.split(r"[|\r\n,;，；、]+", str(raw)):
        part = part.strip()
        if not part:
            continue
        match = re.match(r"(.+?)(?:\s+|:|,|%>)([1-5])$", part)
        if match:
            tag, weight = match.group(1).strip(), int(match.group(2))
        else:
            tag, weight = part, 3
        result.append({"tag": tag, "weight": max(1, min(5, weight))})
    return result


def relation_factor(jd_tag, candidate_tag):
    if normalize(jd_tag) == normalize(candidate_tag):
        return 1.0, "exact"
    jd_norm = normalize(jd_tag)
    candidate_norm = normalize(candidate_tag)
    exact_only = {normalize(item) for item in EXACT_ONLY_TAGS}
    if jd_norm in exact_only or candidate_norm in exact_only:
        return 0.0, "missing"
    for group, factor in RELATED_SETS:
        normalized_group = {normalize(item) for item in group}
        if jd_norm in normalized_group and candidate_norm in normalized_group:
            return factor, "related"
    return 0.0, "missing"


def has_domain_context(jd_tag, candidate_tag, candidate_context):
    finance_system_tags = {normalize(item) for item in FINANCE_SYSTEM_TAGS}
    if normalize(jd_tag) in finance_system_tags or normalize(candidate_tag) in finance_system_tags:
        return has_category_context("财务/会计", candidate_context)
    labels = label_map()
    category = labels.get(candidate_tag).category if candidate_tag in labels else ""
    return has_category_context(category, candidate_context)


def match_candidate(job_skill_tags, candidate_tags, years_required=None, candidate_years=None, candidate_context=""):
    jd_tags = parse_skill_tags(job_skill_tags)
    total_weight = sum(item["weight"] for item in jd_tags) or 1
    matched_weight = 0.0
    capability_weight = 0.0
    hits = []
    missing = []
    used_candidate_indexes = set()

    for required in jd_tags:
        best = None
        for index, candidate_tag in enumerate(candidate_tags):
            if index in used_candidate_indexes:
                continue
            score = int(candidate_tag.get("score", 0))
            if score < 2:
                continue
            factor, match_type = relation_factor(required["tag"], candidate_tag["tag"])
            if factor and not has_domain_context(required["tag"], candidate_tag["tag"], candidate_context):
                continue
            if factor and (best is None or factor * score > best["factor"] * best["candidate_score"]):
                best = {
                    "candidate_index": index,
                    "jd_tag": required["tag"],
                    "job_weight": required["weight"],
                    "candidate_tag": candidate_tag["tag"],
                    "candidate_score": score,
                    "factor": factor,
                    "match_type": match_type,
                }
        if best:
            used_candidate_indexes.add(best.pop("candidate_index"))
            matched_weight += required["weight"] * best["factor"]
            capability_weight += required["weight"] * best["factor"] * best["candidate_score"] / 5
            hits.append(best)
        else:
            missing.append(required["tag"])

    match_rate = matched_weight / total_weight
    capability_rate = capability_weight / total_weight
    skill_score = round(match_rate * 75 + capability_rate * 25)
    experience_rate = None
    score = skill_score
    if years_required:
        candidate_years = float(candidate_years or 0)
        experience_rate = min(candidate_years / float(years_required), 1.0)
        score = round(skill_score * 0.85 + experience_rate * 15)
    return {
        "score": max(0, min(100, score)),
        "hits": hits,
        "missing_tags": missing,
        "formula": "skill_score=round(match_rate * 75 + capability_rate * 25); final=skill_score*0.85+experience_fit*15 when years_required exists",
        "match_rate": round(match_rate, 3),
        "capability_rate": round(capability_rate, 3),
        "skill_score": max(0, min(100, skill_score)),
        "experience_rate": None if experience_rate is None else round(experience_rate, 3),
    }
