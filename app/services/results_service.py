from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.constants import ROUND_ONE, ROUND_TWO
from app.models import Annotation, AnnotationRound, Note, Progress, User


def _percent(value: int, denominator: int) -> float | None:
    return round(value * 100 / denominator, 2) if denominator else None


@dataclass(frozen=True)
class MetricSummary:
    comparable_notes: int
    agreements: int
    disagreements: int
    agreement_percent: float | None


@dataclass(frozen=True)
class PairwiseSummary:
    total_pairs: int
    agreements: int
    disagreements: int
    agreement_percent: float | None


@dataclass(frozen=True)
class DisagreementRow:
    external_id: str
    title: str
    position: int
    labels: dict[str, bool | None]


@dataclass(frozen=True)
class ChangeSummary:
    true_to_false: int
    false_to_true: int
    unchanged: int
    comparable_labels: int
    missing_excluded: int
    changed_rows: tuple[dict[str, object], ...] = ()


@dataclass(frozen=True)
class RoundResults:
    status: str
    answered_notes: int
    unanswered_notes: int
    unanimity: MetricSummary
    pairwise: PairwiseSummary
    disagreements: tuple[DisagreementRow, ...]
    per_user: dict[str, int]
    distribution: dict[str, dict[str, int]]


@dataclass(frozen=True)
class StudyResults:
    round_one: RoundResults
    round_two: RoundResults
    changes: ChangeSummary
    overall_status: str


def _assemble_round_results(
    users: Sequence[User],
    notes: Sequence[Note],
    annotations: Sequence[Annotation],
    completed_user_ids: set[int],
) -> RoundResults:
    by_note: dict[int, list[tuple[User, bool]]] = {note.id: [] for note in notes}
    by_user = {user.id: 0 for user in users}
    by_distribution = {user.id: {"true": 0, "false": 0} for user in users}
    user_by_id = {user.id: user for user in users}

    for annotation in annotations:
        user = user_by_id.get(annotation.user_id)
        if user is None:
            continue
        value = bool(annotation.value)
        by_note[annotation.note_id].append((user, value))
        by_user[user.id] += 1
        by_distribution[user.id]["true" if value else "false"] += 1

    answered_notes = sum(bool(values) for values in by_note.values())
    comparable = agreements = disagreements = 0
    total_pairs = pair_agreements = pair_disagreements = 0
    disagreement_rows: list[DisagreementRow] = []

    for note in notes:
        values = by_note[note.id]
        if not values:
            continue
        distinct = {value for _, value in values}
        if len(values) >= 2:
            comparable += 1
            if len(distinct) == 1:
                agreements += 1
            else:
                disagreements += 1
        for left, right in combinations(values, 2):
            total_pairs += 1
            if left[1] == right[1]:
                pair_agreements += 1
            else:
                pair_disagreements += 1
        if len(distinct) > 1:
            labels = {user.display_name: None for user in users}
            labels.update({user.display_name: value for user, value in values})
            disagreement_rows.append(
                DisagreementRow(note.external_id, note.title, note.position, labels)
            )

    completed_all = bool(users) and completed_user_ids.issuperset(user_by_id)
    per_user = {
        user_by_id[user_id].display_name: count for user_id, count in by_user.items()
    }
    distribution = {
        user_by_id[user_id].display_name: {
            "true": counts["true"],
            "false": counts["false"],
            "answered": counts["true"] + counts["false"],
        }
        for user_id, counts in by_distribution.items()
    }
    return RoundResults(
        "DEFINITIVO" if completed_all else "PARCIAL",
        answered_notes,
        len(notes) - answered_notes,
        MetricSummary(
            comparable,
            agreements,
            disagreements,
            _percent(agreements, comparable),
        ),
        PairwiseSummary(
            total_pairs,
            pair_agreements,
            pair_disagreements,
            _percent(pair_agreements, total_pairs),
        ),
        tuple(disagreement_rows),
        per_user,
        distribution,
    )


def build_round_results(
    db: Session,
    dataset_id: int,
    round_id: int,
    annotator_ids: Sequence[int],
) -> RoundResults:
    requested_ids = list(dict.fromkeys(annotator_ids))
    users = (
        list(
            db.scalars(
                select(User)
                .where(User.id.in_(requested_ids), User.active.is_(True))
                .order_by(User.id)
            ).all()
        )
        if requested_ids
        else []
    )
    user_ids = [user.id for user in users]
    notes = list(
        db.scalars(
            select(Note)
            .where(Note.dataset_id == dataset_id, Note.deleted_at.is_(None))
            .order_by(Note.position, Note.id)
        ).all()
    )
    note_ids = [note.id for note in notes]
    annotations = (
        list(
            db.scalars(
                select(Annotation).where(
                    Annotation.round_id == round_id,
                    Annotation.user_id.in_(user_ids),
                    Annotation.note_id.in_(note_ids),
                )
            ).all()
        )
        if note_ids and user_ids
        else []
    )
    completed_user_ids = (
        set(
            db.scalars(
                select(Progress.user_id).where(
                    Progress.round_id == round_id,
                    Progress.user_id.in_(user_ids),
                    Progress.completed_at.is_not(None),
                )
            ).all()
        )
        if user_ids
        else set()
    )
    return _assemble_round_results(users, notes, annotations, completed_user_ids)


def build_study_results(
    db: Session,
    dataset_id: int,
    annotator_ids: Sequence[int],
) -> StudyResults:
    rounds = {
        round_.round_number: round_
        for round_ in db.scalars(
            select(AnnotationRound).where(AnnotationRound.dataset_id == dataset_id)
        ).all()
    }
    round_ids = [rounds[ROUND_ONE].id, rounds[ROUND_TWO].id]
    requested_ids = list(dict.fromkeys(annotator_ids))
    users = (
        list(
            db.scalars(
                select(User)
                .where(User.id.in_(requested_ids), User.active.is_(True))
                .order_by(User.id)
            ).all()
        )
        if requested_ids
        else []
    )
    user_ids = [user.id for user in users]
    notes = list(
        db.scalars(
            select(Note)
            .where(Note.dataset_id == dataset_id, Note.deleted_at.is_(None))
            .order_by(Note.position, Note.id)
        ).all()
    )
    note_ids = [note.id for note in notes]
    annotations = (
        list(
            db.scalars(
                select(Annotation).where(
                    Annotation.round_id.in_(round_ids),
                    Annotation.user_id.in_(user_ids),
                    Annotation.note_id.in_(note_ids),
                )
            ).all()
        )
        if user_ids and note_ids
        else []
    )
    annotations_by_round: dict[int, list[Annotation]] = {
        round_id: [] for round_id in round_ids
    }
    for annotation in annotations:
        annotations_by_round[annotation.round_id].append(annotation)

    completed_by_round: dict[int, set[int]] = {
        round_id: set() for round_id in round_ids
    }
    if user_ids:
        for user_id, round_id in db.execute(
            select(Progress.user_id, Progress.round_id).where(
                Progress.round_id.in_(round_ids),
                Progress.user_id.in_(user_ids),
                Progress.completed_at.is_not(None),
            )
        ):
            completed_by_round[round_id].add(user_id)

    first_round_id, second_round_id = round_ids
    round_one = _assemble_round_results(
        users,
        notes,
        annotations_by_round[first_round_id],
        completed_by_round[first_round_id],
    )
    round_two = _assemble_round_results(
        users,
        notes,
        annotations_by_round[second_round_id],
        completed_by_round[second_round_id],
    )
    first = {
        (annotation.user_id, annotation.note_id): bool(annotation.value)
        for annotation in annotations_by_round[first_round_id]
    }
    second = {
        (annotation.user_id, annotation.note_id): bool(annotation.value)
        for annotation in annotations_by_round[second_round_id]
    }

    true_to_false = false_to_true = unchanged = comparable = 0
    changed_rows: list[dict[str, object]] = []
    for user_id in user_ids:
        for note in notes:
            before = first.get((user_id, note.id))
            after = second.get((user_id, note.id))
            if before is None or after is None:
                continue
            comparable += 1
            if before == after:
                unchanged += 1
            elif before and not after:
                true_to_false += 1
                changed_rows.append(
                    {
                        "user_id": user_id,
                        "note": note.external_id,
                        "title": note.title,
                        "from_value": before,
                        "to_value": after,
                    }
                )
            else:
                false_to_true += 1
                changed_rows.append(
                    {
                        "user_id": user_id,
                        "note": note.external_id,
                        "title": note.title,
                        "from_value": before,
                        "to_value": after,
                    }
                )

    missing = len(user_ids) * len(notes) - comparable
    changes = ChangeSummary(
        true_to_false,
        false_to_true,
        unchanged,
        comparable,
        missing,
        tuple(changed_rows),
    )
    overall = (
        "DEFINITIVO"
        if round_one.status == "DEFINITIVO" and round_two.status == "DEFINITIVO"
        else "PARCIAL"
    )
    return StudyResults(round_one, round_two, changes, overall)
