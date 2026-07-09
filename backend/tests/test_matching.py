from app.matching import match_candidate, parse_skill_tags
from app.tag_library import rule_based_tags


def test_parse_skill_tags_supports_multiline_weights():
    tags = parse_skill_tags("Java 5\nSpring Boot 5\nMySQL 4\nRedis 4")

    assert tags == [
        {"tag": "Java", "weight": 5},
        {"tag": "Spring Boot", "weight": 5},
        {"tag": "MySQL", "weight": 4},
        {"tag": "Redis", "weight": 4},
    ]


def test_hr_process_tags_need_hr_context():
    jd = "招聘 5|面试安排 4|员工关系 2|绩效 2|薪酬 2"
    tags = [{"tag": "绩效", "score": 5, "category": "人力资源"}]

    tech = match_candidate(jd, tags, candidate_context="Java 开发 KPI绩效考核系统 HR追踪模块 熟悉人力资源模块")
    hr = match_candidate(jd, tags, candidate_context="招聘专员，熟悉薪酬绩效流程")

    assert tech["hits"] == []
    assert hr["hits"][0]["candidate_tag"] == "绩效"


def test_business_system_names_do_not_match_business_roles():
    tags = [{"tag": "采购", "score": 5, "category": "供应链/采购"}]

    tech = match_candidate("采购 5", tags, candidate_context="Java 开发采购平台和供应商系统")
    buyer = match_candidate("采购 5", tags, candidate_context="采购专员，负责采购和供应商管理")

    assert tech["hits"] == []
    assert buyer["hits"][0]["candidate_tag"] == "采购"


def test_finance_tools_do_not_related_match_general_finance_or_office_tags():
    tags = [
        {"tag": "Excel", "score": 5, "category": "工具"},
        {"tag": "纳税申报", "score": 5, "category": "财务/会计"},
    ]

    result = match_candidate("金蝶 5|用友 5", tags, candidate_context="总账会计，熟悉纳税申报、财务报表、Excel。")

    assert result["hits"] == []
    assert result["missing_tags"] == ["金蝶", "用友"]


def test_finance_system_tags_require_accounting_context_even_for_exact_match():
    tags = [{"tag": "金蝶", "score": 5, "category": "工具"}]

    developer = match_candidate("金蝶 5", tags, candidate_context="Java 开发工程师，负责金蝶接口、ERP系统集成和Spring Boot后端服务。")
    accountant = match_candidate("金蝶 5", tags, candidate_context="总账会计，负责财务核算、报表编制，熟悉金蝶KIS。")

    assert developer["hits"] == []
    assert accountant["hits"][0]["match_type"] == "exact"


def test_rule_based_tags_require_context_for_finance_system_tools():
    developer_tags = {item["tag"] for item in rule_based_tags("Java 开发工程师，负责金蝶接口、ERP系统集成和Spring Boot后端服务。")}
    accountant_tags = {item["tag"] for item in rule_based_tags("总账会计，负责财务核算、报表编制，熟悉金蝶KIS和用友U8。")}

    assert "金蝶" not in developer_tags
    assert {"金蝶", "用友"} <= accountant_tags
