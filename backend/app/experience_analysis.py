import re


def analyze_experience(text):
    lowered = text.lower()
    if any(word in text for word in ["在校", "在读", "学生", "实习生", "本科在读", "硕士在读"]):
        return {"level": "student", "label": "在校生", "years": 0, "basis": "文本包含在校/学生信号"}
    if any(word in text for word in ["应届", "毕业生", "校招"]):
        return {"level": "fresh", "label": "应届毕业", "years": 0, "basis": "文本包含应届/校招信号"}
    years = 0.0
    year_candidates = []
    for match in re.finditer(r"(\d+(?:\.\d+)?)\s*年(?:以上|\+)?(?:\s*(?:工作|开发|会计|销售|招聘|项目)?经验)?", text):
        value = float(match.group(1))
        if 0 < value <= 50:
            window = text[max(0, match.start() - 8) : match.end() + 12]
            if "经验" in window or "工作" in window or "开发" in window:
                year_candidates.append(value)
    if year_candidates:
        years = max(year_candidates)
    if not years:
        head = "\n".join(text.splitlines()[:10])
        for match in re.finditer(r"(?:^|[|｜,，\s])(\d+(?:\.\d+)?)\s*年(?:$|[|｜,，\s])", head):
            value = float(match.group(1))
            if 0 < value <= 50:
                years = max(years, value)
    month_match = re.search(r"(\d+)\s*个月", text)
    if not years and month_match:
        years = round(int(month_match.group(1)) / 12, 1)

    if years < 1:
        return {"level": "lt1", "label": "1 年以下", "years": years, "basis": "未识别到 1 年以上经验"}
    if years < 3:
        return {"level": "1-3", "label": "1-3 年", "years": years, "basis": "显式年限表达"}
    if years < 5:
        return {"level": "3-5", "label": "3-5 年", "years": years, "basis": "显式年限表达"}
    if years < 10:
        return {"level": "5-10", "label": "5-10 年", "years": years, "basis": "显式年限表达"}
    return {"level": "gt10", "label": "10 年以上", "years": years, "basis": "显式年限表达"}
