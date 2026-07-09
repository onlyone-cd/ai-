import argparse
import hashlib
import re
import sys
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app import create_app, db  # noqa: E402
from app.models import (  # noqa: E402
    BossDraft,
    Candidate,
    CandidateTag,
    EmployeeProfile,
    EmployeeRecommendation,
    InterviewAssignment,
    Match,
    OfferRecord,
    PipelineStage,
    ResumeAttachment,
)


def normalize_text(value):
    return re.sub(r"\s+", "", str(value or "")).lower()


def raw_fingerprint(value):
    normalized = normalize_text(value)
    if len(normalized) < 80:
        return ""
    return hashlib.sha1(normalized.encode("utf-8", errors="ignore")).hexdigest()


def duplicate_keys(candidate):
    keys = []
    if candidate.phone_masked:
        keys.append(("phone", candidate.phone_masked.strip()))
    if candidate.email_masked:
        keys.append(("email", candidate.email_masked.strip().lower()))
    raw_hash = raw_fingerprint(candidate.raw_text)
    if raw_hash:
        keys.append(("raw", raw_hash))
    return keys


def linked_count(candidate_id):
    return sum(
        [
            Match.query.filter_by(candidate_id=candidate_id).count(),
            PipelineStage.query.filter_by(candidate_id=candidate_id).count(),
            InterviewAssignment.query.filter_by(candidate_id=candidate_id).count(),
            OfferRecord.query.filter_by(candidate_id=candidate_id).count(),
            BossDraft.query.filter_by(candidate_id=candidate_id).count(),
            EmployeeProfile.query.filter_by(candidate_id=candidate_id).count(),
            EmployeeRecommendation.query.filter_by(candidate_id=candidate_id).count(),
            ResumeAttachment.query.filter_by(candidate_id=candidate_id).count(),
        ]
    )


def content_score(candidate):
    return (
        len(candidate.raw_text or ""),
        CandidateTag.query.filter_by(candidate_id=candidate.id).count(),
        1 if candidate.parse_status == "ok" else 0,
        len(str(candidate.resume_json or {})),
    )


def keeper_for(group):
    def created_ts(item):
        return item.created_at.timestamp() if item.created_at else 0

    return sorted(
        group,
        key=lambda item: (
            linked_count(item.id),
            *content_score(item),
            created_ts(item),
            -item.id,
        ),
        reverse=True,
    )[0]


def discover_duplicate_groups():
    candidates = Candidate.query.order_by(Candidate.id.asc()).all()
    key_map = defaultdict(list)
    for candidate in candidates:
        for key in duplicate_keys(candidate):
            key_map[key].append(candidate)

    parent = {candidate.id: candidate.id for candidate in candidates}
    by_id = {candidate.id: candidate for candidate in candidates}
    group_keys = defaultdict(list)

    def find(value):
        while parent[value] != value:
            parent[value] = parent[parent[value]]
            value = parent[value]
        return value

    def union(left, right):
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parent[right_root] = left_root

    for key, items in key_map.items():
        if len(items) < 2:
            continue
        first = items[0].id
        for item in items[1:]:
            union(first, item.id)
        for item in items:
            group_keys[find(first)].append(key)

    components = defaultdict(list)
    for candidate in candidates:
        components[find(candidate.id)].append(candidate)

    groups = []
    for root, items in components.items():
        if len(items) < 2:
            continue
        keys = sorted({key for item in items for key in duplicate_keys(item)})
        duplicate_keys_in_group = [key for key in keys if len(key_map.get(key, [])) > 1]
        if duplicate_keys_in_group:
            groups.append({"key": duplicate_keys_in_group[0], "keys": duplicate_keys_in_group, "items": sorted(items, key=lambda item: item.id)})
    return groups


def merge_candidate_tags(keeper_id, loser_id):
    best = {}
    for tag in CandidateTag.query.filter(CandidateTag.candidate_id.in_([keeper_id, loser_id])).all():
        current = best.get(tag.tag)
        if current is None or tag.score > current.score:
            best[tag.tag] = tag
    CandidateTag.query.filter_by(candidate_id=keeper_id).delete()
    CandidateTag.query.filter_by(candidate_id=loser_id).delete()
    for tag in best.values():
        db.session.add(CandidateTag(candidate_id=keeper_id, tag=tag.tag, score=tag.score, category=tag.category))


def copy_better_content(keeper, loser):
    if content_score(loser) <= content_score(keeper):
        return
    keeper.upload_batch_id = loser.upload_batch_id or keeper.upload_batch_id
    keeper.name_masked = loser.name_masked or keeper.name_masked
    keeper.email_masked = loser.email_masked or keeper.email_masked
    keeper.phone_masked = loser.phone_masked or keeper.phone_masked
    keeper.title = loser.title or keeper.title
    keeper.source = loser.source or keeper.source
    keeper.city = loser.city or keeper.city
    keeper.resume_json = loser.resume_json or keeper.resume_json
    keeper.raw_text = loser.raw_text or keeper.raw_text
    keeper.parse_status = loser.parse_status or keeper.parse_status
    keeper.parse_error = loser.parse_error


def reassign_references(keeper_id, loser_id):
    Match.query.filter_by(candidate_id=loser_id).update({"candidate_id": keeper_id})
    PipelineStage.query.filter_by(candidate_id=loser_id).update({"candidate_id": keeper_id})
    InterviewAssignment.query.filter_by(candidate_id=loser_id).update({"candidate_id": keeper_id})
    OfferRecord.query.filter_by(candidate_id=loser_id).update({"candidate_id": keeper_id})
    BossDraft.query.filter_by(candidate_id=loser_id).update({"candidate_id": keeper_id})
    EmployeeRecommendation.query.filter_by(candidate_id=loser_id).update({"candidate_id": keeper_id})
    ResumeAttachment.query.filter_by(candidate_id=loser_id).update({"candidate_id": keeper_id})
    for employee in EmployeeProfile.query.filter_by(candidate_id=loser_id).all():
        if EmployeeProfile.query.filter_by(candidate_id=keeper_id).first():
            employee.candidate_id = None
        else:
            employee.candidate_id = keeper_id


def merge_group(group, dry_run=True):
    keeper = keeper_for(group["items"])
    losers = [item for item in group["items"] if item.id != keeper.id]
    result = {
        "key": f"{group['key'][0]}:{group['key'][1]}",
        "keys": [f"{key[0]}:{key[1]}" for key in group.get("keys", [group["key"]])],
        "keeper_id": keeper.id,
        "keeper_name": keeper.name_masked,
        "loser_ids": [item.id for item in losers],
        "loser_names": [item.name_masked for item in losers],
    }
    if dry_run:
        return result
    for loser in losers:
        copy_better_content(keeper, loser)
        reassign_references(keeper.id, loser.id)
        merge_candidate_tags(keeper.id, loser.id)
        db.session.delete(loser)
    return result


def main():
    parser = argparse.ArgumentParser(description="Merge duplicate candidate resumes safely.")
    parser.add_argument("--apply", action="store_true", help="Apply changes. Default is dry-run.")
    args = parser.parse_args()

    app = create_app()
    with app.app_context():
        before = Candidate.query.count()
        groups = discover_duplicate_groups()
        results = [merge_group(group, dry_run=not args.apply) for group in groups]
        if args.apply:
            db.session.commit()
        after = Candidate.query.count()
        print({"mode": "apply" if args.apply else "dry-run", "groups": len(results), "before": before, "after": after})
        for item in results:
            print(item)


if __name__ == "__main__":
    main()
