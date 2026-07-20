import re

from .tag_library import evidence_terms_for, has_category_context, label_map, term_contexts

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
GENERIC_OFFICE_TOOLS = {"Excel", "PowerPoint", "Word"}
ROLE_DOMAIN_CATEGORIES = {
    "财务/会计",
    "人力资源",
    "供应链/采购",
    "销售/商务",
    "客户服务",
    "运营/市场",
    "物流/仓储",
    "法务/合规",
    "行政/文秘",
    "生产制造",
    "质量/体系",
    "教育/培训",
    "医疗/护理",
    "建筑/地产",
    "餐饮/酒店",
    "零售/门店",
    "工程/制造",
    "设计/工程",
}

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


def jd_required_domains(jd_tags):
    labels = label_map()
    domains = []
    for item in jd_tags:
        label = labels.get(item.get("tag"))
        if label and label.category in ROLE_DOMAIN_CATEGORIES and label.category not in domains:
            domains.append(label.category)
    return domains


def has_any_required_domain(required_domains, candidate_context):
    return any(has_category_context(domain, candidate_context) for domain in required_domains)


def domain_sensitive_hit_allowed(required_tag, candidate_tag, required_domains, candidate_context):
    if not required_domains:
        return True
    labels = label_map()
    required_label = labels.get(required_tag)
    candidate_label = labels.get(candidate_tag)
    required_category = required_label.category if required_label else ""
    candidate_category = candidate_label.category if candidate_label else ""
    if required_category in required_domains or candidate_category in required_domains:
        return has_category_context(required_category or candidate_category, candidate_context)
    if required_tag in GENERIC_OFFICE_TOOLS or candidate_tag in GENERIC_OFFICE_TOOLS:
        return has_any_required_domain(required_domains, candidate_context)
    return True


DEFAULT_WEIGHTS = {
    "skill_match": 75,
    "capability": 25,
    "skill_overall": 85,
    "experience": 15,
}


def match_candidate(job_skill_tags, candidate_tags, years_required=None, candidate_years=None, candidate_context="", weights=None):
    weights = {**DEFAULT_WEIGHTS, **(weights or {})}
    jd_tags = parse_skill_tags(job_skill_tags)
    total_weight = sum(item["weight"] for item in jd_tags) or 1
    required_domains = jd_required_domains(jd_tags)
    matched_weight = 0.0
    capability_weight = 0.0
    hits = []
    missing = []
    domain_warnings = []
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
                domain_warnings.append(f"{required['tag']} / {candidate_tag['tag']} 缺少岗位领域上下文，已从规则命中剔除")
                continue
            if factor and not domain_sensitive_hit_allowed(required["tag"], candidate_tag["tag"], required_domains, candidate_context):
                domain_warnings.append(
                    f"{required['tag']} / {candidate_tag['tag']} 缺少 {', '.join(required_domains)} 场景证据，已从规则命中剔除"
                )
                continue
            evidence = tag_evidence(candidate_tag["tag"], candidate_context)
            if factor and not evidence:
                domain_warnings.append(f"{required['tag']} / {candidate_tag['tag']} 缺少简历原文证据，已从规则命中剔除")
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
                    "evidence": evidence,
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
    skill_score = round(match_rate * int(weights.get("skill_match", 75)) + capability_rate * int(weights.get("capability", 25)))
    experience_rate = None
    score = skill_score
    if years_required:
        candidate_years = float(candidate_years or 0)
        experience_rate = min(candidate_years / float(years_required), 1.0)
        score = round(skill_score * int(weights.get("skill_overall", 85)) / 100 + experience_rate * int(weights.get("experience", 15)))
    return {
        "score": max(0, min(100, score)),
        "hits": hits,
        "missing_tags": missing,
        "formula": f"skill_score=round(match_rate*{weights.get('skill_match', 75)} + capability_rate*{weights.get('capability', 25)}); final=skill_score*{weights.get('skill_overall', 85)}%+experience_fit*{weights.get('experience', 15)} when years_required exists",
        "weights": weights,
        "required_domains": required_domains,
        "domain_warnings": list(dict.fromkeys(domain_warnings))[:8],
        "match_rate": round(match_rate, 3),
        "capability_rate": round(capability_rate, 3),
        "skill_score": max(0, min(100, skill_score)),
        "experience_rate": None if experience_rate is None else round(experience_rate, 3),
    }


def tag_evidence(tag, text):
    labels = label_map()
    label = labels.get(tag)
    terms = evidence_terms_for(label) if label else (tag,)
    snippets = []
    for term in terms:
        for context in term_contexts(term, text, radius=54):
            cleaned = re.sub(r"\s+", " ", context).strip()
            if cleaned and cleaned not in snippets:
                snippets.append(cleaned)
            if len(snippets) >= 2:
                return snippets
    return snippets
