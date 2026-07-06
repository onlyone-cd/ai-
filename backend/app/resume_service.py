import re
import uuid
import zipfile
from pathlib import Path
from xml.etree import ElementTree

from flask import current_app
from werkzeug.datastructures import FileStorage
from werkzeug.utils import secure_filename

from . import db
from .deepseek_resume_parser import parse_resume_with_deepseek
from .experience_analysis import analyze_experience
from .models import Candidate, CandidateTag, UploadBatch
from .tag_library import dedupe_tags, rule_based_tags

ALLOWED_EXTENSIONS = {".txt", ".md", ".docx", ".pdf"}
ARCHIVE_EXTENSIONS = {".zip"}

def parse_and_save_resume(file: FileStorage, owner):
    extension = Path(file.filename or "").suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError("仅支持 TXT、MD、DOCX、PDF 简历")

    batch_id = uuid.uuid4().hex[:12]
    upload_dir = resume_upload_dir()
    safe_name = secure_filename(file.filename or f"resume{extension}") or f"resume{extension}"
    stored_path = upload_dir / f"{batch_id}_{safe_name}"
    file.save(stored_path)
    return parse_stored_resume(stored_path, file.filename or safe_name, owner, batch_id=batch_id)


def parse_and_save_archive(file: FileStorage, owner):
    extension = Path(file.filename or "").suffix.lower()
    if extension not in ARCHIVE_EXTENSIONS:
        raise ValueError("仅支持 ZIP 压缩包")
    upload_dir = resume_upload_dir()
    candidates = []
    batches = []
    errors = []
    max_file_size = current_app.config.get("MAX_CONTENT_LENGTH", 16 * 1024 * 1024)
    max_files = current_app.config.get("MAX_ARCHIVE_FILES", 50)
    max_total_size = current_app.config.get("MAX_ARCHIVE_UNCOMPRESSED_SIZE", 64 * 1024 * 1024)
    max_ratio = current_app.config.get("MAX_ARCHIVE_COMPRESSION_RATIO", 100)
    try:
        with zipfile.ZipFile(file.stream) as archive:
            members = [item for item in archive.infolist() if not item.is_dir()]
            if len(members) > max_files:
                raise ValueError(f"压缩包内文件数量超过限制：最多 {max_files} 个")
            total_size = sum(item.file_size for item in members)
            if total_size > max_total_size:
                raise ValueError("压缩包解压后体积过大")
            for info in members:
                if is_unsafe_archive_member(info):
                    errors.append({"filename": info.filename, "error": "压缩包路径不安全，已跳过"})
                    continue
                if info.compress_size and info.file_size / max(info.compress_size, 1) > max_ratio:
                    errors.append({"filename": info.filename, "error": "压缩比异常，疑似恶意压缩包"})
                    continue
                filename = Path(info.filename).name
                extension = Path(filename).suffix.lower()
                if extension not in ALLOWED_EXTENSIONS:
                    continue
                if info.file_size > max_file_size:
                    errors.append({"filename": filename, "error": "文件过大"})
                    continue
                batch_id = uuid.uuid4().hex[:12]
                safe_name = secure_filename(filename) or f"resume{extension}"
                stored_path = upload_dir / f"{batch_id}_{safe_name}"
                stored_path.write_bytes(archive.read(info))
                try:
                    batch, candidate = parse_stored_resume(stored_path, filename, owner, batch_id=batch_id)
                    batches.append(batch)
                    candidates.append(candidate)
                except Exception as exc:
                    errors.append({"filename": filename, "error": str(exc)})
    except zipfile.BadZipFile as exc:
        raise ValueError("ZIP 压缩包格式无效") from exc
    if not candidates and not errors:
        raise ValueError("压缩包中未找到 TXT、MD、DOCX、PDF 简历")
    return batches, candidates, errors


def is_unsafe_archive_member(info):
    name = str(info.filename or "").replace("\\", "/")
    parts = [part for part in name.split("/") if part]
    return name.startswith("/") or ".." in parts


def resume_upload_dir():
    upload_dir = Path(current_app.config["UPLOAD_FOLDER"])
    if not upload_dir.is_absolute():
        upload_dir = Path(current_app.instance_path) / upload_dir
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def parse_stored_resume(stored_path: Path, filename: str, owner, batch_id=None):
    extension = stored_path.suffix.lower()
    batch_id = batch_id or uuid.uuid4().hex[:12]
    batch = UploadBatch(id=batch_id, owner_hr_id=owner.id, source="upload", filename=filename)
    db.session.add(batch)
    db.session.flush()

    try:
        raw_text = extract_text(stored_path, extension)
        if not raw_text.strip():
            raise ValueError("未能从简历中提取到文本")
        llm_result = parse_resume_with_deepseek(raw_text)
        candidate = upsert_candidate(build_candidate(raw_text, batch_id, owner.id, llm_result=llm_result), infer_tags(raw_text, llm_result=llm_result))
        batch.success_count = 1
        batch.status = "ok"
        db.session.commit()
        return batch, candidate
    except Exception as exc:
        batch.status = "failed"
        batch.failed_count = 1
        batch.error = str(exc)
        db.session.commit()
        raise


def parse_and_save_text(raw_text: str, owner, source="boss", filename="boss-screen-resume.txt"):
    raw_text = normalize_resume_text(raw_text)
    if len(raw_text) < 30:
        raise ValueError("采集到的简历文本过短")
    batch_id = uuid.uuid4().hex[:12]
    batch = UploadBatch(id=batch_id, owner_hr_id=owner.id, source=source, filename=filename)
    db.session.add(batch)
    db.session.flush()
    candidate = build_candidate(raw_text, batch_id, owner.id)
    candidate.source = source
    candidate = upsert_candidate(candidate, infer_tags(raw_text))
    batch.success_count = 1
    batch.status = "ok"
    db.session.commit()
    return batch, candidate


def upsert_candidate(candidate, tags):
    existing = find_duplicate_candidate(candidate)
    target = existing or candidate
    if existing:
        existing.owner_hr_id = candidate.owner_hr_id
        existing.upload_batch_id = candidate.upload_batch_id
        existing.name_masked = candidate.name_masked
        existing.email_masked = candidate.email_masked
        existing.phone_masked = candidate.phone_masked
        existing.title = candidate.title
        existing.source = candidate.source
        existing.city = candidate.city
        existing.raw_text = candidate.raw_text
        existing.resume_json = candidate.resume_json
        existing.parse_status = "ok"
        existing.parse_error = None
        CandidateTag.query.filter_by(candidate_id=existing.id).delete()
    else:
        db.session.add(candidate)
        db.session.flush()
    for tag in tags:
        db.session.add(CandidateTag(candidate_id=target.id, **tag))
    return target


def find_duplicate_candidate(candidate):
    if candidate.phone_masked:
        existing = Candidate.query.filter_by(phone_masked=candidate.phone_masked).first()
        if existing:
            return existing
    if candidate.email_masked:
        return Candidate.query.filter_by(email_masked=candidate.email_masked).first()
    return None


def reparse_candidate(candidate):
    llm_result = parse_resume_with_deepseek(candidate.raw_text)
    parsed = build_candidate(candidate.raw_text, candidate.upload_batch_id, candidate.owner_hr_id, llm_result=llm_result)
    candidate.name_masked = parsed.name_masked
    candidate.email_masked = parsed.email_masked
    candidate.phone_masked = parsed.phone_masked
    candidate.title = parsed.title
    candidate.city = parsed.city
    candidate.resume_json = parsed.resume_json
    candidate.parse_status = "ok"
    candidate.parse_error = None
    CandidateTag.query.filter_by(candidate_id=candidate.id).delete()
    db.session.flush()
    for tag in infer_tags(candidate.raw_text, llm_result=llm_result):
        db.session.add(CandidateTag(candidate_id=candidate.id, **tag))
    return candidate


def extract_text(path: Path, extension: str):
    if extension in {".txt", ".md"}:
        return normalize_resume_text(path.read_text(encoding="utf-8", errors="ignore"))
    if extension == ".docx":
        return normalize_resume_text(extract_docx_text(path))
    if extension == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise ValueError("PDF 解析依赖未安装，请先上传 TXT/DOCX 或安装 pypdf") from exc
        reader = PdfReader(str(path))
        return normalize_resume_text("\n".join(page.extract_text() or "" for page in reader.pages))
    raise ValueError("不支持的文件类型")


def extract_docx_text(path: Path):
    ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    with zipfile.ZipFile(path) as archive:
        document = archive.read("word/document.xml")
    root = ElementTree.fromstring(document)
    parts = []
    for paragraph in root.iter("{%s}p" % ns["w"]):
        line = "".join(text_node.text or "" for text_node in paragraph.iter("{%s}t" % ns["w"])).strip()
        if line:
            parts.append(line)
    return "\n".join(parts)


def normalize_resume_text(text: str):
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n").replace("\u3000", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def build_candidate(raw_text: str, batch_id: str, owner_hr_id: int, llm_result=None):
    extracted = extract_profile(raw_text)
    llm_result = llm_result or {}
    llm_profile = (llm_result or {}).get("profile") or {}
    extracted = merge_profile(extracted, llm_profile)
    experience_analysis = analyze_experience(raw_text)
    sections = fallback_resume_sections(raw_text)
    summary = str(llm_profile.get("summary") or "").strip() or summarize(raw_text)
    education = clean_section_items(llm_result.get("education")) or sections["education"]
    experience = clean_section_items(llm_result.get("experience")) or sections["experience"] or [{"description": summarize(raw_text, 500)}]
    projects = clean_section_items(llm_result.get("projects")) or sections["projects"]
    return Candidate(
        owner_hr_id=owner_hr_id,
        upload_batch_id=batch_id,
        name_masked=extracted["name"],
        email_masked=extracted["email"],
        phone_masked=extracted["phone"],
        title=extracted["title"],
        source="upload",
        city=extracted["city"],
        raw_text=raw_text,
        parse_status="ok",
        resume_json={
            "name": extracted["name"],
            "gender": extracted["gender"],
            "email": extracted["email"],
            "phone": extracted["phone"],
            "summary": summary,
            "intent_city": extracted["city"],
            "education": education,
            "experience": experience,
            "projects": projects,
            "certifications": clean_section_items(llm_result.get("certifications")),
            "languages": [],
            "additional_info": {},
            "experience_analysis": experience_analysis,
            "llm_provider": "deepseek" if llm_result else "rules",
        },
    )


def merge_profile(rule_profile, llm_profile):
    merged = dict(rule_profile)
    for key in ["name", "gender", "email", "phone", "city", "title"]:
        value = str(llm_profile.get(key, "")).strip()
        if key == "name" and (not is_probable_name(value) or merged.get("name") != "候选人"):
            continue
        if value and (key != "name" or value != "候选人"):
            merged[key] = value
    return merged


def extract_profile(text: str):
    email = first_match(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+", text)
    phone = first_match(r"1[3-9]\d{9}", re.sub(r"[\s-]", "", text))
    name = extract_name(text)
    gender = extract_gender(text)
    city = first_match(r"(?:城市|期望城市|所在地)[:：\s]*([\u4e00-\u9fa5A-Za-z]{2,20})", text) or "未知"
    title = infer_title(text)
    return {"name": name, "gender": gender, "email": email, "phone": phone, "city": city, "title": title}


def first_match(pattern: str, text: str):
    match = re.search(pattern, text, re.I)
    if not match:
        return ""
    return match.group(1) if match.lastindex else match.group(0)


def normalize_gender(value: str):
    normalized = (value or "").strip().lower()
    if normalized in {"男", "男性", "male", "m"}:
        return "男"
    if normalized in {"女", "女性", "female", "f"}:
        return "女"
    return ""


def extract_gender(text: str):
    explicit = first_match(r"(?:性别|Gender)[:：\s]*(男|女|男性|女性|male|female|m|f)\b", text)
    if explicit:
        return normalize_gender(explicit)
    head = "\n".join(text.splitlines()[:8])
    standalone = first_match(r"(?:^|[\s|,，/])([男女])(?:$|[\s|,，/])", head)
    return normalize_gender(standalone)


def extract_name(text: str):
    explicit = first_match(r"(?:姓名|Name)[:：\s]*([\u4e00-\u9fa5A-Za-z]{2,20})", text)
    if explicit:
        return explicit

    head_lines = [line.strip() for line in text.splitlines()[:12] if line.strip()]
    for line in head_lines:
        cleaned = re.sub(r"(?:男|女|男性|女性|male|female|\d{1,2}\s*岁|1[3-9]\d{9}|[\w.+-]+@[\w-]+(?:\.[\w-]+)+)", " ", line, flags=re.I)
        cleaned = re.sub(r"[|,，/：:\-_\s]+", " ", cleaned).strip()
        if is_probable_name(cleaned):
            return cleaned
    return "候选人"


def is_probable_name(value: str):
    if not value:
        return False
    blocked = ["求职", "意向", "岗位", "简历", "经验", "技能", "项目", "教育", "课程", "电话", "手机", "邮箱", "城市", "工作", "期望"]
    if any(word in value for word in blocked):
        return False
    return bool(re.fullmatch(r"[\u4e00-\u9fa5]{2,4}|[A-Za-z][A-Za-z\s]{1,30}", value))


def infer_title(text: str):
    explicit = first_match(r"(?:求职意向|应聘岗位|目标岗位|期望职位|应聘职位)[:：\s]*([^\n，,；;。]{2,40})", text)
    if explicit:
        return re.sub(r"[()（）|/]+", " ", explicit).strip()
    title_keywords = [
        "总账会计",
        "会计",
        "Python 后端工程师",
        "后端工程师",
        "Java开发",
        "前端开发",
        "招聘专员",
        "人力资源",
        "采购",
        "数据分析",
        "Java 开发工程师",
        "销售",
        "客服",
        "产品经理",
        "UI设计",
        "教师",
        "护士",
    ]
    lowered = text.lower()
    for keyword in title_keywords:
        if keyword.lower() in lowered:
            return keyword
    return "候选人"


def infer_tags(text: str, llm_result=None):
    tags = rule_based_tags(text)
    if llm_result and llm_result.get("tags"):
        tags = [*tags, *llm_result["tags"]]
    return dedupe_tags(tags)[:50]


def clean_section_items(items):
    cleaned = []
    for item in items or []:
        if isinstance(item, str):
            value = item.strip()
            if value:
                cleaned.append({"description": value[:1200]})
            continue
        if not isinstance(item, dict):
            continue
        entry = {str(key): stringify(value)[:1200] for key, value in item.items() if stringify(value)}
        if entry:
            cleaned.append(entry)
    return cleaned[:12]


def stringify(value):
    if value is None:
        return ""
    if isinstance(value, list):
        return "；".join(stringify(item) for item in value if stringify(item))
    return str(value).strip()


def fallback_resume_sections(text: str):
    buckets = {"education": [], "experience": [], "projects": []}
    current = None
    heading_map = {
        "education": ["教育经历", "教育背景", "教育信息"],
        "experience": ["工作经历", "工作经验", "实习经历"],
        "projects": ["项目经历", "项目经验"],
    }
    for line in [line.strip(" \t-•") for line in text.splitlines()]:
        if not line:
            continue
        matched = next((key for key, names in heading_map.items() if any(name in line for name in names)), None)
        if matched:
            current = matched
            continue
        if current:
            buckets[current].append(line)
    return {key: section_lines_to_items(lines, key) for key, lines in buckets.items()}


def section_lines_to_items(lines, kind):
    if not lines:
        return []
    text = "\n".join(lines)
    parts = [part.strip() for part in re.split(r"\n(?=.*(?:\d{4}[./年-]|至今|公司|大学|学院|项目))", text) if part.strip()]
    items = []
    for part in (parts or [text])[:8]:
        item = {"description": part[:1200]}
        first = part.splitlines()[0]
        if kind == "education":
            item["school"] = first
        elif kind == "experience":
            item["company"] = first
        elif kind == "projects":
            item["name"] = first
        period = first_match(r"(\d{4}[./年-]\d{0,2}.*?(?:至今|\d{4}[./年-]\d{0,2}))", part)
        if period:
            item["period"] = period
        items.append(item)
    return items


def summarize(text: str, limit: int = 180):
    text = re.sub(r"(?:电话|手机|邮箱|微信)[:：]?\s*[\w@.+（）() -]+", "", text)
    return re.sub(r"\s+", " ", text).strip()[:limit]
