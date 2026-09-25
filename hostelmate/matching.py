"""
matching.py
------------
This is the "AI" core of HostelMate. It does two things:

1. compute_compatibility(a, b)  -> a 0-100 score for how well two students
   would get along as roommates, based on a WEIGHTED sum of how closely
   their preferences match.

2. allocate_rooms(students)     -> groups every student into rooms of their
   preferred size using a greedy nearest-neighbour clustering algorithm,
   making sure each student is placed in exactly one room.

Everything here is plain Python (no external ML library) so it's easy to
explain line-by-line in a viva.
"""

# ---------------------------------------------------------------------------
# 1. WEIGHTS: how much each parameter contributes to the final 0-100 score.
#    Feel free to tweak these numbers — they must add up to 100.
# ---------------------------------------------------------------------------
WEIGHTS = {
    "sleep_schedule": 15,
    "wake_schedule": 10,
    "cleanliness": 15,
    "noise_tolerance": 15,
    "study_habits": 10,
    "social_preference": 10,
    "guest_frequency": 10,
    "food_preference": 5,
    "study_hours": 5,
    "sleeping_environment": 5,
}

# Attributes that have a natural ORDER (e.g. Early < Moderate < Late).
# For these we give partial credit if they are "close" rather than an
# all-or-nothing match, because an Early sleeper and a Moderate sleeper
# clash less than an Early sleeper and a Late sleeper.
ORDINAL_SCALES = {
    "sleep_schedule": ["Early", "Moderate", "Late"],
    "wake_schedule": ["Early", "Moderate", "Late"],
    "cleanliness": ["Very tidy", "Moderate", "Relaxed"],
}

# Values that mean "I don't mind" — if EITHER student picked one of these,
# we treat that attribute as a full match (no reason to penalise flexible people).
NEUTRAL_VALUES = {"No preference", "Other", "Flexible", "Sometimes"}

# Bonus added when two students have explicitly picked each other as a
# preferred roommate (mutual pick). Capped so total score never exceeds 100.
MUTUAL_PREFERENCE_BONUS = 12


def _attribute_score(field, val_a, val_b):
    """Return a 0.0-1.0 score for how well two students match on one field."""
    if val_a == val_b:
        return 1.0
    if val_a in NEUTRAL_VALUES or val_b in NEUTRAL_VALUES:
        return 1.0

    if field in ORDINAL_SCALES:
        scale = ORDINAL_SCALES[field]
        try:
            dist = abs(scale.index(val_a) - scale.index(val_b))
            max_dist = len(scale) - 1
            # closer positions on the scale -> higher partial score
            return 1.0 - (dist / max_dist)
        except ValueError:
            return 0.0  # unrecognised value, treat as mismatch

    # Non-ordinal categorical attribute with no match -> no credit
    return 0.0


def compute_compatibility(a, b):
    """
    a, b: sqlite3.Row (or dict-like) objects representing two students.
    Returns an integer score from 0 to 100.
    """
    total = 0.0
    for field, weight in WEIGHTS.items():
        total += _attribute_score(field, a[field], b[field]) * weight

    # Mutual preferred-roommate bonus
    preferred_a = [x.strip() for x in (a["preferred_roommates"] or "").split(",") if x.strip()]
    preferred_b = [x.strip() for x in (b["preferred_roommates"] or "").split(",") if x.strip()]
    if str(b["id"]) in preferred_a and str(a["id"]) in preferred_b:
        total += MUTUAL_PREFERENCE_BONUS

    return round(min(total, 100))


def build_compatibility_matrix(students):
    """Pre-compute the score for every pair once, so allocate_rooms doesn't
    repeat the same calculation. Returns a dict keyed by (id_a, id_b)."""
    matrix = {}
    for i, a in enumerate(students):
        for b in students[i + 1:]:
            score = compute_compatibility(a, b)
            matrix[(a["id"], b["id"])] = score
            matrix[(b["id"], a["id"])] = score
    return matrix


def _pair_score(matrix, id_a, id_b):
    return matrix.get((id_a, id_b), 0)


def _avg_score_to_group(matrix, group_ids, candidate_id):
    """Average compatibility of a candidate student against everyone
    already placed in a room being built."""
    if not group_ids:
        return 0
    return sum(_pair_score(matrix, gid, candidate_id) for gid in group_ids) / len(group_ids)


def allocate_rooms(students):
    if not students:
        return []

    matrix = build_compatibility_matrix(students)

    # Separate students by their preferred room size
    students_by_size = {
        2: [],
        3: [],
        4: []
    }

    for student in students:
        try:
            size = int(student["room_size"])
        except (ValueError, TypeError):
            size = 2

        if size in students_by_size:
            students_by_size[size].append(student)

    rooms = []

    # Create the best compatible groups separately for each room size
    for room_size, group in students_by_size.items():

        while len(group) >= room_size:

            best_group = None
            best_score = -1

            # Start with every possible student as the first member
            for seed in group:

                candidates = [
                    s for s in group
                    if s["id"] != seed["id"]
                ]

                # Build a possible room around this student
                selected = [seed]

                while len(selected) < room_size and candidates:
                    best_candidate = max(
                        candidates,
                        key=lambda candidate: _avg_score_to_group(
                            matrix,
                            [s["id"] for s in selected],
                            candidate["id"]
                        )
                    )

                    selected.append(best_candidate)
                    candidates.remove(best_candidate)

                # Only score complete rooms
                if len(selected) == room_size:
                    pair_scores = [
                        _pair_score(
                            matrix,
                            selected[i]["id"],
                            selected[j]["id"]
                        )
                        for i in range(len(selected))
                        for j in range(i + 1, len(selected))
                    ]

                    avg_score = (
                        round(sum(pair_scores) / len(pair_scores))
                        if pair_scores else 100
                    )

                    if avg_score > best_score:
                        best_score = avg_score
                        best_group = selected

            # If no complete room can be created, stop
            if best_group is None:
                break

            # Add the best room
            rooms.append({
                "members": best_group,
                "avg_compatibility": best_score,
            })

            # Remove those students from the available pool
            used_ids = {s["id"] for s in best_group}
            group = [
                s for s in group
                if s["id"] not in used_ids
            ]

    return rooms
