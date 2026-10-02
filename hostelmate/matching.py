"""
matching.py
------------
This is the "AI" core of HostelMate. It does two things:

1. compute_compatibility(a, b)  -> a 0-100 score for how well two students
   would get along as roommates, based on a WEIGHTED sum of how closely
   their preferences match.

2. allocate_rooms(students)     -> finds a globally optimized allocation
   of students into rooms of their preferred size.

The allocation prioritizes:
    1. Maximum number of students placed.
    2. Highest overall compatibility among those allocations.

Everything here is plain Python (no external ML library) so it's easy to
explain line-by-line in a viva.
"""

from itertools import combinations
from functools import lru_cache


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
ORDINAL_SCALES = {
    "sleep_schedule": ["Early", "Moderate", "Late"],
    "wake_schedule": ["Early", "Moderate", "Late"],
    "cleanliness": ["Very tidy", "Moderate", "Relaxed"],
}


# Values that mean "I don't mind".
NEUTRAL_VALUES = {
    "No preference",
    "Other",
    "Flexible",
    "Sometimes"
}


# Bonus added when two students have explicitly picked each other.
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

            # Closer positions on the scale -> higher partial score
            return 1.0 - (dist / max_dist)

        except ValueError:
            return 0.0

    # Non-ordinal categorical attribute with no match
    return 0.0


def compute_compatibility(a, b):
    """
    a, b: sqlite3.Row (or dict-like) objects representing two students.

    Returns an integer score from 0 to 100.
    """

    total = 0.0

    for field, weight in WEIGHTS.items():
        total += _attribute_score(
            field,
            a[field],
            b[field]
        ) * weight

    # Mutual preferred-roommate bonus
    preferred_a = [
        x.strip()
        for x in (a["preferred_roommates"] or "").split(",")
        if x.strip()
    ]

    preferred_b = [
        x.strip()
        for x in (b["preferred_roommates"] or "").split(",")
        if x.strip()
    ]

    if str(b["id"]) in preferred_a and str(a["id"]) in preferred_b:
        total += MUTUAL_PREFERENCE_BONUS

    return round(min(total, 100))


def build_compatibility_matrix(students):
    """
    Pre-compute the score for every pair once.

    Returns a dictionary keyed by (id_a, id_b).
    """

    matrix = {}

    for i, a in enumerate(students):

        for b in students[i + 1:]:

            score = compute_compatibility(a, b)

            matrix[(a["id"], b["id"])] = score
            matrix[(b["id"], a["id"])] = score

    return matrix


def _pair_score(matrix, id_a, id_b):
    """Return compatibility score between two students."""

    return matrix.get((id_a, id_b), 0)


# ---------------------------------------------------------------------------
# ROOM SCORING
# ---------------------------------------------------------------------------

def _room_score(matrix, group):
    """
    Calculate TOTAL pairwise compatibility inside a room.

    Example for a 3-person room:

        A-B
        A-C
        B-C

    The three scores are added together.
    """

    pair_scores = [
        _pair_score(
            matrix,
            group[i]["id"],
            group[j]["id"]
        )
        for i in range(len(group))
        for j in range(i + 1, len(group))
    ]

    return sum(pair_scores)


def _room_average(matrix, group):
    """
    Calculate average compatibility inside a room.

    This is used for displaying the room score.
    """

    pair_scores = [
        _pair_score(
            matrix,
            group[i]["id"],
            group[j]["id"]
        )
        for i in range(len(group))
        for j in range(i + 1, len(group))
    ]

    if not pair_scores:
        return 100

    return round(sum(pair_scores) / len(pair_scores))


# ---------------------------------------------------------------------------
# GLOBAL OPTIMIZATION
# ---------------------------------------------------------------------------

def _optimize_group(group, room_size, matrix):
    """
    Find the globally best allocation for one room-size category.

    Priority:
        1. Place the maximum possible number of students.
        2. Among those allocations, maximize total compatibility.

    Unlike the old greedy algorithm, this does not permanently choose
    the first "best" room. It explores different possible combinations.

    Memoization is used so the same remaining-student situation does not
    have to be calculated repeatedly.
    """

    students = tuple(group)

    # Quickly access student objects using their IDs.
    student_by_id = {
        student["id"]: student
        for student in students
    }

    all_ids = tuple(
        student["id"]
        for student in students
    )

    @lru_cache(maxsize=None)
    def search(remaining_ids):
        """
        Returns:

        (
            number_of_students_placed,
            total_compatibility,
            selected_rooms
        )
        """

        # No students left.
        if not remaining_ids:
            return 0, 0, ()

        # Take the first remaining student.
        first_id = remaining_ids[0]

        remaining_without_first = remaining_ids[1:]

        # ---------------------------------------------------------------
        # OPTION 1:
        # Leave this student waiting.
        # ---------------------------------------------------------------

        best_placed, best_score, best_rooms = search(
            remaining_without_first
        )

        # ---------------------------------------------------------------
        # OPTION 2:
        # Put this student into a room.
        # ---------------------------------------------------------------

        if len(remaining_ids) >= room_size:

            # Choose the remaining students needed to complete the room.
            other_ids = remaining_without_first

            for combination in combinations(
                other_ids,
                room_size - 1
            ):

                room_ids = (first_id,) + combination

                room = [
                    student_by_id[student_id]
                    for student_id in room_ids
                ]

                # Compatibility of this possible room
                room_score = _room_score(
                    matrix,
                    room
                )

                # Remove everyone in this room from the remaining pool.
                new_remaining = tuple(
                    student_id
                    for student_id in remaining_without_first
                    if student_id not in combination
                )

                # Find the best allocation for everyone else.
                placed, score, rooms = search(
                    new_remaining
                )

                # Add this room to that result.
                placed += room_size
                score += room_score

                # -------------------------------------------------------
                # Compare this allocation with the current best.
                #
                # FIRST: maximum number of students.
                # SECOND: maximum compatibility.
                # -------------------------------------------------------

                if (
                    placed > best_placed
                    or (
                        placed == best_placed
                        and score > best_score
                    )
                ):
                    best_placed = placed
                    best_score = score
                    best_rooms = (
                        (room_ids,) + rooms
                    )

        return best_placed, best_score, best_rooms

    # Run the optimization.
    placed, score, room_ids_list = search(all_ids)

    rooms = []

    for room_ids in room_ids_list:

        members = [
            student_by_id[student_id]
            for student_id in room_ids
        ]

        rooms.append({
            "members": members,
            "avg_compatibility": _room_average(
                matrix,
                members
            ),
        })

    return rooms


# ---------------------------------------------------------------------------
# MAIN ROOM ALLOCATION
# ---------------------------------------------------------------------------

def allocate_rooms(students):
    """
    Globally optimize room allocation.

    Students are separated according to their preferred room size.

    2-sharing students are optimized separately.
    3-sharing students are optimized separately.
    4-sharing students are optimized separately.

    Priority:
        1. Maximum number of students placed.
        2. Maximum overall compatibility.

    Students who cannot form a complete room remain waiting.
    """

    if not students:
        return []

    matrix = build_compatibility_matrix(students)

    # Separate students by preferred room size.
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

    # Optimize each room-size category separately.
    for room_size, group in students_by_size.items():

        if len(group) < room_size:
            continue

        optimized_rooms = _optimize_group(
            group,
            room_size,
            matrix
        )

        rooms.extend(optimized_rooms)

    return rooms