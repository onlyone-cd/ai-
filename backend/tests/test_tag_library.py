from app.tag_library import candidate_labels_for_text, normalize_llm_tags, rule_based_tags


def test_sales_tags_are_loaded_and_matched():
    text = "5 年 B2B 大客户销售经验，负责渠道销售、商务拓展、客户成功和跨部门协作。"

    labels = {label.tag for label in candidate_labels_for_text(text)}
    tags = {item["tag"] for item in rule_based_tags(text)}

    assert {"销售", "大客户销售", "渠道销售", "商务拓展", "客户成功"} <= labels
    assert {"销售", "大客户销售", "渠道销售", "商务拓展", "客户成功"} <= tags


def test_short_english_tags_need_word_boundaries():
    text = "熟悉 CRM 系统，负责客户开发和销售漏斗管理。"
    tags = {item["tag"] for item in rule_based_tags(text)}

    assert "C" not in tags
    assert "销售" in tags


def test_business_system_names_do_not_create_business_tags():
    tech_tags = {item["tag"] for item in rule_based_tags("Java 开发采购平台和绩效系统")}
    buyer_tags = {item["tag"] for item in rule_based_tags("采购专员，负责采购和供应商管理")}

    assert "采购" not in tech_tags
    assert "绩效" not in tech_tags
    assert "采购" in buyer_tags


def test_tag_scores_follow_evidence_context_not_frequency():
    repeated = next(item for item in rule_based_tags("Java Java Java Java 课程学习") if item["tag"] == "Java")
    delivered = next(item for item in rule_based_tags("负责 Java 核心开发，上线生产环境并完成性能优化") if item["tag"] == "Java")

    assert repeated["score"] <= 2
    assert delivered["score"] == 5


def test_mobile_tags_need_direct_development_evidence():
    text = "王成都 项目经理，负责业务需求、供应商协调，没有 iOS 和移动端开发经验。"
    tags = {item["tag"] for item in rule_based_tags(text)}

    assert {"iOS", "移动端开发", "Android", "Swift", "Kotlin"}.isdisjoint(tags)


def test_mobile_product_or_team_context_is_not_development_evidence():
    text = "负责 App 产品需求、移动端团队对接和验收，不参与 iOS 开发。"
    labels = {label.tag for label in candidate_labels_for_text(text)}
    tags = {item["tag"] for item in rule_based_tags(text)}

    assert {"iOS", "移动端开发", "Android"}.isdisjoint(labels)
    assert {"iOS", "移动端开发", "Android"}.isdisjoint(tags)


def test_mobile_development_evidence_is_kept():
    text = "3 年 iOS开发经验，使用 Swift、UIKit、Xcode 开发客户端。"
    tags = {item["tag"] for item in rule_based_tags(text)}

    assert {"iOS", "Swift", "移动端开发"} <= tags


def test_llm_tags_are_rejected_when_evidence_is_negative():
    text = "王成都 项目经理，负责业务需求、供应商协调，没有 iOS 和移动端开发经验。"

    tags = normalize_llm_tags([{"tag": "iOS", "score": 5, "evidence": "没有 iOS 经验"}], text)

    assert tags == []


def test_empty_text_does_not_create_fake_communication_tag():
    assert rule_based_tags("候选人姓名：张三") == []
