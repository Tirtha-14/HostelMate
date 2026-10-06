"""
matching.py
-----------
The matching engine of HostelMate. It does three things:

1. compute_compatibility(a, b)  -> 0-100 score for two students, a WEIGHTED
   sum of how closely their ten lifestyle preferences match.

2. score_breakdown(a, b)        -> the same score, explained field by field
   (used by the UI so every number can be justified).

3. allocate_rooms(students)     -> groups students into rooms of the size
   they asked for.

Allocation priority
    1. Place the maximum number of students.
    2. Among those allocations, maximise total pairwise compatibility.

Small groups are solved EXACTLY (dynamic programming with memoisation).
Large groups switch automatically to a fast greedy + swap-improvement method,
because the exact search grows exponentially (a 4-sharing group of 20 students
took about 28 seconds in testing).

Plain Python only, no external ML library, so it is easy to explain.
"""

from itertools import combinations
from functools import lru_cache


# ---------------------------------------------------------------------------
# 1. WEIGHTS: how much each parameter contributes. They must add up to 100.
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

assert sum(WEIGHTS.values()) == 100, "WEIGHTS must add up to 100"

# Friendly names, used by the web pages.
FIELD_LABELS = {
    "sleep_schedule": "Sleep schedule",
    "wake_schedule": "Wake-up time",
    "cleanliness": "Cleanliness",
    "noise_tolerance": "Noise tolerance",
    "study_habits": "Where they study",
    "social_preference": "Social style",
    "guest_frequency": "Guests",
    "food_preference": "Food",
    "study_hours": "Study hours",
    "sleeping_environment": "Sleeping environment",
}

# Attributes with a natural ORDER. Neighbouring values earn partial credit.
ORDINAL_SCALES = {
    "sleep_schedule": ["Early", "Moderate", "Late"],
    "wake_schedule": ["Early", "Moderate", "Late"],
    "cleanliness": ["Very tidy", "Moderate", "Relaxed"],
    "social_preference": ["Private", "Balanced", "Social"],
    "guest_frequency": ["Never", "Sometimes", "Often"],
    "study_hours": ["Morning", "Evening", "Late Night"],
    # "Loud" is not on the form yet; it keeps Quiet/Moderate as neighbours.
    "noise_tolerance": ["Quiet", "Moderate", "Loud"],
    "sleeping_environment": ["Needs dark & silent", "Moderate", "Flexible"],
}

# Values that mean "I don't mind": they match anything.
NEUTRAL_VALUES = {"No preference", "Other", "Flexible"}

# Bonus when two students have explicitly picked each other.
MUTUAL_PREFERENCE_BONUS = 12

# Largest group size solved exactly, per room size.
EXACT_LIMITS = {2: 20, 3: 16, 4: 14}


# ---------------------------------------------------------------------------
# 2. PAIR SCORING
# ---------------------------------------------------------------------------

def _attribute_score(field, val_a, val_b):
    """Return 0.0-1.0 for how well two students match on one field."""

    if val_a == val_b:
        return 1.0

    if val_a in NEUTRAL_VALUES or val_b in NEUTRAL_VALUES:
        return 1.0

    scale = ORDINAL_SCALES.get(field)
    if scale:
        try:
            distance = abs(scale.index(val_a) - scale.index(val_b))
            return 1.0 - distance / (len(scale) - 1)
        except ValueError:
            return 0.0

    return 0.0


def _preferred_ids(student):
    raw = student["preferred_roommates"] or ""
    return {x.strip() for x in raw.split(",") if x.strip()}


def is_mutual_preference(a, b):
    """True if each student listed the other as a preferred roommate."""
    return str(b["id"]) in _preferred_ids(a) and str(a["id"]) in _preferred_ids(b)


def score_breakdown(a, b):
    """
    Explain a compatibility score.

    Returns {"rows": [...], "bonus": int, "total": int}. Each row holds the
    field, both students' answers, the weight and the points earned.
    """
    rows = []
    total = 0.0

    for field, weight in WEIGHTS.items():
        ratio = _attribute_score(field, a[field], b[field])
        points = ratio * weight
        total += points
        rows.append({
            "field": field,
            "label": FIELD_LABELS[field],
            "mine": a[field],
            "theirs": b[field],
            "weight": weight,
            "points": round(points, 1),
            "ratio": ratio,
        })

    bonus = MUTUAL_PREFERENCE_BONUS if is_mutual_preference(a, b) else 0

    return {
        "rows": rows,
        "bonus": bonus,
        "total": round(min(total + bonus, 100)),
    }


def compute_compatibility(a, b):
    """a, b: sqlite3.Row or dict. Returns an integer from 0 to 100."""
    total = sum(
        _attribute_score(field, a[field], b[field]) * weight
        for field, weight in WEIGHTS.items()
    )

    if is_mutual_preference(a, b):
        total += MUTUAL_PREFERENCE_BONUS

    return round(min(total, 100))


def build_compatibility_matrix(students):
    """Score every pair once. Returns {(id_a, id_b): score}."""
    matrix = {}

    for i, a in enumerate(students):
        for b in students[i + 1:]:
            score = compute_compatibility(a, b)
            matrix[(a["id"], b["id"])] = score
            matrix[(b["id"], a["id"])] = score

    return matrix


def _pair_score(matrix, id_a, id_b):
    return matrix.get((id_a, id_b), 0)


# ---------------------------------------------------------------------------
# 3. ROOM SCORING
# ---------------------------------------------------------------------------

def _pair_scores(matrix, ids):
    return [
        _pair_score(matrix, ids[i], ids[j])
        for i in range(len(ids))
        for j in range(i + 1, len(ids))
    ]


def _room_score(matrix, ids):
    """Total pairwise compatibility inside a room (A-B + A-C + B-C ...)."""
    return sum(_pair_scores(matrix, ids))


def _room_average(matrix, ids):
    """Average pairwise compatibility, shown on the room card."""
    scores = _pair_scores(matrix, ids)
    return round(sum(scores) / len(scores)) if scores else 100


# ---------------------------------------------------------------------------
# 4. EXACT OPTIMISATION (small groups)
# ---------------------------------------------------------------------------

def _exact_search(ids, room_size, matrix):
    """Best allocation by exploring every combination, with memoisation."""

    @lru_cache(maxsize=None)
    def search(remaining):
        # Returns (students placed, total compatibility, rooms as id tuples)
        if not remaining:
            return 0, 0, ()

        first, rest = remaining[0], remaining[1:]

        # Option 1: this student stays on the waiting list.
        best_placed, best_score, best_rooms = search(rest)

        # Option 2: this student joins a room with (room_size - 1) others.
        if len(remaining) >= room_size:
            for combo in combinations(rest, room_size - 1):
                room = (first,) + combo
                leftover = tuple(i for i in rest if i not in combo)

                placed, score, rooms = search(leftover)
                placed += room_size
                score += _room_score(matrix, room)

                if placed > best_placed or (
                    placed == best_placed and score > best_score
                ):
                    best_placed, best_score = placed, score
                    best_rooms = (room,) + rooms

        return best_placed, best_score, best_rooms

    return [list(room) for room in search(tuple(ids))[2]]


# ---------------------------------------------------------------------------
# 5. FAST OPTIMISATION (large groups): greedy build + swap improvement
# ---------------------------------------------------------------------------

def _heuristic_search(ids, room_size, matrix):
    """
    1. Greedy: seed each room with the best remaining pair, then keep adding
       the student who fits the current members best.
    2. Improve: swap students between rooms (or with the waiting list)
       whenever a swap raises the total score.

    Places the same number of students as the exact method:
    floor(n / room_size) full rooms.
    """
    pool = set(ids)
    rooms = []

    while len(pool) >= room_size:
        _, a, b = max(
            (_pair_score(matrix, x, y), x, y)
            for x, y in combinations(sorted(pool), 2)
        )
        room = [a, b]
        pool -= {a, b}

        while len(room) < room_size:
            nxt = max(
                sorted(pool),
                key=lambda c: sum(_pair_score(matrix, c, m) for m in room),
            )
            room.append(nxt)
            pool.discard(nxt)

        rooms.append(room)

    waiting = sorted(pool)

    def score(room):
        return _room_score(matrix, room)

    for _ in range(50):  # safety cap on improvement rounds
        improved = False

        # Swap two students that live in different rooms.
        for x in range(len(rooms)):
            for y in range(x + 1, len(rooms)):
                for i in range(room_size):
                    for j in range(room_size):
                        before = score(rooms[x]) + score(rooms[y])
                        rooms[x][i], rooms[y][j] = rooms[y][j], rooms[x][i]
                        if score(rooms[x]) + score(rooms[y]) > before:
                            improved = True
                        else:
                            rooms[x][i], rooms[y][j] = rooms[y][j], rooms[x][i]

        # Swap a roomed student with someone on the waiting list.
        for x in range(len(rooms)):
            for i in range(room_size):
                for w in range(len(waiting)):
                    before = score(rooms[x])
                    rooms[x][i], waiting[w] = waiting[w], rooms[x][i]
                    if score(rooms[x]) > before:
                        improved = True
                    else:
                        rooms[x][i], waiting[w] = waiting[w], rooms[x][i]

        if not improved:
            break

    return rooms


# ---------------------------------------------------------------------------
# 6. PUBLIC ALLOCATION FUNCTIONS
# ---------------------------------------------------------------------------

def _optimize_group(group, room_size, matrix):
    """Allocate one room-size category, choosing exact or fast automatically."""

    by_id = {s["id"]: s for s in group}
    ids = [s["id"] for s in group]

    if len(ids) <= EXACT_LIMITS.get(room_size, 14):
        id_rooms = _exact_search(ids, room_size, matrix)
    else:
        id_rooms = _heuristic_search(ids, room_size, matrix)

    return [
        {
            "members": [by_id[i] for i in room],
            "avg_compatibility": _room_average(matrix, room),
        }
        for room in id_rooms
    ]


def allocate_rooms(students):
    """
    Group students by preferred room size (2, 3 or 4) and optimise each group.
    Students who cannot complete a room stay on the waiting list.
    """
    if not students:
        return []

    matrix = build_compatibility_matrix(students)

    by_size = {2: [], 3: [], 4: []}

    for student in students:
        try:
            size = int(student["room_size"])
        except (ValueError, TypeError):
            size = 2
        if size in by_size:
            by_size[size].append(student)

    rooms = []
    for room_size, group in by_size.items():
        if len(group) >= room_size:
            rooms.extend(_optimize_group(group, room_size, matrix))

    return rooms