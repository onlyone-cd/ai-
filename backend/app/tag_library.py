import csv
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DOMAIN_SIGNALS = {
    "财务/会计": ["会计经验", "总账会计", "财务会计", "成本会计", "出纳", "负责账务", "纳税申报", "报税", "审计底稿", "账务处理"],
    "人力资源": ["招聘经验", "负责招聘", "招聘专员", "招聘经理", "人力资源专员", "人力资源经理", "员工关系", "面试安排", "负责薪酬", "负责绩效"],
    "销售/商务": ["销售经验", "客户开发", "销售经理", "大客户销售", "电话销售", "渠道销售", "商务拓展", "售前支持"],
    "客户服务": ["客服经验", "在线客服", "电话客服", "售后服务", "客户成功", "投诉处理"],
    "运营/市场": ["运营经验", "内容运营", "用户运营", "活动运营", "新媒体运营", "电商运营", "品牌营销", "广告投放"],
    "供应链/采购": ["采购经验", "负责采购", "采购专员", "供应商开发", "负责供应商管理", "寻源", "招投标", "负责库存管理"],
    "物流/仓储": ["负责仓库管理", "物流经验", "运输配送", "WMS操作"],
    "法务/合规": ["法务经验", "合同审核", "合同管理", "劳动合同", "用工风险", "知识产权"],
    "行政/文秘": ["行政经验", "行政管理", "前台接待", "秘书", "档案管理", "会议组织"],
    "生产制造": ["生产管理", "生产计划", "车间管理", "设备维护", "安全生产"],
    "质量/体系": ["质量管理", "质检", "质量体系", "体系审核", "ISO9001"],
    "教育/培训": ["教师", "授课", "教学", "课程设计", "教务", "班主任"],
    "医疗/护理": ["医生", "护士", "临床", "护理", "药师", "医学检验"],
    "建筑/地产": ["建筑设计", "施工管理", "工程造价", "工程监理", "物业管理", "房地产销售"],
    "餐饮/酒店": ["餐饮服务", "厨师", "酒店前台", "客房管理"],
    "零售/门店": ["门店管理", "店长", "收银", "导购", "商品陈列"],
    "工程/制造": ["机械设计", "机械工程", "结构设计", "零部件", "图纸", "制图", "工艺", "公差", "设备", "制造"],
    "设计/工程": ["机械设计", "机械工程", "结构设计", "三维建模", "图纸", "制图", "CAD", "AutoCAD", "SolidWorks"],
    "编程语言": [
        "开发",
        "后端",
        "前端",
        "工程师",
        "程序",
        "系统",
        "接口",
        "项目",
        "代码",
        "服务",
        "学习",
        "课程",
        "培训",
        "development",
        "developer",
        "backend",
        "frontend",
        "engineer",
        "programming",
        "code",
        "project",
        "experience",
    ],
}

LABEL_CONTEXT_REQUIREMENTS = {
    "金蝶": ["会计", "财务", "总账", "账务", "税务", "纳税", "报税", "出纳", "审计", "报表", "核算", "成本"],
    "用友": ["会计", "财务", "总账", "账务", "税务", "纳税", "报税", "出纳", "审计", "报表", "核算", "成本"],
    "SAP": ["会计", "财务", "总账", "账务", "税务", "纳税", "报表", "核算", "成本", "ERP", "供应链", "采购", "库存"],
    "ERP财务": ["会计", "财务", "总账", "账务", "税务", "纳税", "报表", "核算", "成本"],
    "项目管理": ["项目经理", "项目负责人", "进度管理", "风险管理", "交付管理", "里程碑", "项目计划", "统筹项目", "项目管理经验", "负责项目管理"],
    "跨部门协作": ["跨部门", "协同", "沟通协调", "协调", "对接", "联动"],
    "沟通": ["沟通能力", "沟通协调", "客户沟通", "跨部门沟通", "需求沟通", "表达能力", "汇报"],
    "执行": ["执行力", "推动落地", "落地执行", "推进", "跟进", "闭环"],
    "监理": ["工程", "施工", "土建", "建筑", "工地", "房建", "市政", "监理员", "监理工程师"],
    "机械设计": ["机械设计", "机械工程", "结构设计", "零部件", "图纸", "制图", "三维建模", "设备"],
    "CAD": ["CAD", "AutoCAD", "制图", "工程图", "图纸", "机械设计", "结构设计"],
    "SolidWorks": ["SolidWorks", "三维建模", "机械设计", "结构设计", "工程图"],
    "AutoCAD": ["AutoCAD", "CAD", "制图", "工程图", "图纸"],
}

TAG_SCORE_CAPS = {
    "沟通": 3,
    "执行": 3,
    "跨部门协作": 3,
    "项目管理": 4,
    "需求分析": 4,
    "数据分析": 4,
    "监理": 4,
}

EXTRA_EVIDENCE_TERMS = {
    "跨部门协作": ("跨部门协调", "跨部门对接", "跨部门联动"),
    "执行": ("推动事项闭环", "事项闭环", "推进落地", "推动落地"),
}

SYSTEM_REFERENCE_WORDS = ("系统", "平台", "模块", "接口", "看板", "软件", "应用")
ROLE_EVIDENCE_TERMS = {
    "监理": ("监理员", "监理工程师", "工程监理经验", "施工现场", "工地", "房建", "市政", "土建", "负责监理"),
    "项目管理": ("项目经理", "项目负责人", "进度管理", "风险管理", "交付管理", "项目管理经验", "负责项目管理", "统筹项目"),
}


@dataclass(frozen=True)
class SkillLabel:
    tag: str
    category: str
    aliases: tuple[str, ...]

    @property
    def evidence_terms(self):
        return (self.tag, *self.aliases)


@lru_cache(maxsize=1)
def load_labels():
    path = Path(__file__).resolve().parents[2] / "base_agent" / "all_labels.csv"
    labels = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle)
        next(reader, None)
        for row in reader:
            if len(row) < 2:
                continue
            tag = row[0].strip()
            category = row[1].strip()
            aliases_raw = "|".join(part.strip() for part in row[2:] if part.strip())
            aliases = tuple(item.strip() for item in aliases_raw.split("|") if item.strip())
            if tag and category:
                labels.append(SkillLabel(tag=tag, category=category, aliases=aliases))
    return labels


def label_map():
    return {label.tag: label for label in load_labels()}


def candidate_labels_for_text(text, limit=120):
    hits = []
    for label in load_labels():
        matched_terms = [term for term in evidence_terms_for(label) if term and term_in_text(term, text)]
        if matched_terms and label_has_required_context(label, text, matched_terms):
            hits.append(label)
    return hits[:limit]


def rule_based_tags(text, limit=50):
    tags = []
    for label in load_labels():
        if not has_category_context(label.category, text):
            continue
        matched_terms = [term for term in evidence_terms_for(label) if term and term_in_text(term, text)]
        if not matched_terms:
            continue
        if not label_has_required_context(label, text, matched_terms):
            continue
        score = capped_score(label, evidence_score(matched_terms, text), text, matched_terms)
        tags.append({"tag": label.tag, "score": score, "category": label.category})
    return dedupe_tags(tags)[:limit] or [{"tag": "沟通", "score": 2, "category": "通用能力"}]


def normalize_llm_tags(items, text, min_score=2, limit=50):
    labels = label_map()
    normalized = []
    for item in items or []:
        tag = str(item.get("tag", "")).strip()
        if tag not in labels:
            continue
        label = labels[tag]
        evidence = str(item.get("evidence", "")).strip()
        has_evidence = evidence and evidence.lower() in text.lower()
        if not has_evidence:
            has_evidence = any(term and term_in_text(term, text) for term in evidence_terms_for(label))
        if not has_evidence:
            continue
        matched_terms = [term for term in evidence_terms_for(label) if term and term_in_text(term, text)]
        if evidence and evidence.lower() in text.lower():
            matched_terms.append(evidence)
        if not label_has_required_context(label, text, matched_terms):
            continue
        if not has_category_context(label.category, text):
            continue
        try:
            score = int(item.get("score", 3))
        except (TypeError, ValueError):
            score = 3
        if score < min_score:
            continue
        score = capped_score(label, max(1, min(5, score)), text, matched_terms)
        normalized.append({"tag": tag, "score": score, "category": label.category})
    return dedupe_tags(normalized)[:limit]


def dedupe_tags(items):
    best = {}
    for item in items:
        current = best.get(item["tag"])
        if current is None or item["score"] > current["score"]:
            best[item["tag"]] = item
    return sorted(best.values(), key=lambda item: (-item["score"], item["tag"]))


def term_in_text(term, text):
    if not term:
        return False
    value = str(term).strip()
    if not value:
        return False
    if re.fullmatch(r"[A-Za-z0-9+#.]{1,3}", value):
        return bool(re.search(rf"(?<![A-Za-z0-9+#.]){re.escape(value)}(?![A-Za-z0-9+#.])", text, re.I))
    return value.lower() in text.lower()


def evidence_terms_for(label):
    return (*label.evidence_terms, *EXTRA_EVIDENCE_TERMS.get(label.tag, ()))


def label_has_required_context(label, text, matched_terms):
    required_terms = LABEL_CONTEXT_REQUIREMENTS.get(label.tag)
    if not required_terms:
        return True
    contexts = []
    for term in matched_terms:
        contexts.extend(term_contexts(term, text, radius=80))
    normalized_context = "\n".join(contexts).lower()
    if is_system_reference(label.tag, normalized_context):
        return False
    return any(term.lower() in normalized_context for term in required_terms)


def is_system_reference(tag, context):
    role_terms = ROLE_EVIDENCE_TERMS.get(tag)
    if not role_terms:
        return False
    if not has_any(context, SYSTEM_REFERENCE_WORDS):
        return False
    return not has_any(context, role_terms)


def capped_score(label, score, text, matched_terms):
    score = max(1, min(5, int(score or 1)))
    base_cap = TAG_SCORE_CAPS.get(label.tag)
    if not base_cap:
        return score
    contexts = []
    for term in matched_terms:
        contexts.extend(term_contexts(term, text, radius=90))
    context = "\n".join(contexts)
    cap = base_cap
    if label.tag in {"沟通", "执行", "跨部门协作"} and has_any(context, ["主导", "统筹", "推动", "跨部门", "协调", "客户", "汇报", "闭环", "落地"]):
        cap = 4
    if label.tag == "项目管理":
        cap = 5 if has_any(context, ["PMP", "项目经理", "项目负责人", "总负责人", "大型项目"]) else 4
    if label.tag == "监理":
        cap = 5 if has_any(context, ["注册监理工程师", "总监理工程师"]) else 4
    return min(score, cap)


def has_any(text, words):
    lowered = str(text or "").lower()
    return any(str(word).lower() in lowered for word in words)


def evidence_score(terms, text):
    scores = []
    for term in terms:
        for context in term_contexts(term, text):
            scores.append(score_context(context))
    return max(scores or [3])


def term_contexts(term, text, radius=42):
    pattern = term_pattern(term)
    if not pattern:
        return []
    contexts = []
    for match in re.finditer(pattern, text, re.I):
        start = max(0, match.start() - radius)
        end = min(len(text), match.end() + radius)
        contexts.append(text[start:end])
    return contexts


def term_pattern(term):
    value = str(term or "").strip()
    if not value:
        return ""
    escaped = re.escape(value)
    if re.fullmatch(r"[A-Za-z0-9+#.]{1,3}", value):
        return rf"(?<![A-Za-z0-9+#.]){escaped}(?![A-Za-z0-9+#.])"
    return escaped


def score_context(context):
    value = str(context or "").lower()
    if any(word in value for word in ["精通", "专家", "主导", "负责人", "架构", "核心开发", "性能优化", "落地", "上线", "生产环境"]):
        return 5
    if any(word in value for word in ["负责", "熟练", "熟悉", "掌握", "开发", "实现", "使用", "建设", "维护", "独立", "参与"]):
        return 4
    if any(word in value for word in ["了解", "学习", "课程", "培训", "接触", "自学"]):
        return 2
    return 3


def has_category_context(category, text):
    signals = DOMAIN_SIGNALS.get(category)
    if not signals:
        return True
    return any(signal.lower() in str(text or "").lower() for signal in signals)
