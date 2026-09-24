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
    """
    Greedy nearest-neighbour room allocation.

    Algorithm (explain this in viva):
      1. Compute compatibility for every pair up front.
      2. Go through students in order. If a student is not yet placed,
         start a new room for them, sized to THEIR preferred room size.
      3. Repeatedly pull in whichever unplaced student has the highest
         AVERAGE compatibility with everyone currently in that room,
         until the room reaches its target size.
      4. Repeat until every student has exactly one room.

    This guarantees:
      - Every student is allocated exactly once.
      - Rooms fill up favouring the most compatible available students
        first (mutual "preferred roommate" picks naturally win here
        because of the bonus score baked into compute_compatibility).
    """
    if not students:
        return []

    matrix = build_compatibility_matrix(students)
    students_by_id = {s["id"]: s for s in students}
    unplaced = [s["id"] for s in students]  # preserves registration order
    rooms = []

    while unplaced:
        seed_id = unplaced.pop(0)  # take the earliest-registered unplaced student
        seed = students_by_id[seed_id]
        try:
            target_size = int(seed["room_size"])
        except (ValueError, TypeError):
            target_size = 2  # safe fallback

        room_members = [seed_id]

        # Keep adding the best-matching remaining student until the room is full
        while len(room_members) < target_size and unplaced:
            best_candidate = max(
                unplaced,
                key=lambda cid: _avg_score_to_group(matrix, room_members, cid),
            )
            room_members.append(best_candidate)
            unplaced.remove(best_candidate)

        # Compute the room's overall compatibility (average of every pair inside it)
        pair_scores = [
            _pair_score(matrix, room_members[i], room_members[j])
            for i in range(len(room_members))
            for j in range(i + 1, len(room_members))
        ]
        avg_score = round(sum(pair_scores) / len(pair_scores)) if pair_scores else 100

        rooms.append({
            "members": [students_by_id[mid] for mid in room_members],
            "avg_compatibility": avg_score,
        })

    return rooms
