from app.matching import match_candidate, parse_skill_tags


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
