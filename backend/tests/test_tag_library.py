from app.tag_library import candidate_labels_for_text, rule_based_tags


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
