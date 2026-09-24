# HostelMate – Smart Roommate Matching System

A minimal, dependency-light Flask web app that matches hostel students into
compatible roommate groups using a weighted compatibility score and a greedy
allocation algorithm.

## Project structure
```
hostelmate/
├── app.py            # Flask routes (register, list, allocate)
├── db.py              # SQLite schema + CRUD helpers
├── matching.py         # Compatibility scoring + room allocation algorithm
├── requirements.txt
├── static/style.css
└── templates/
    ├── base.html
    ├── index.html
    ├── register.html
    ├── students.html
    └── allocate.html
```

## Setup & Run

1. **Install Python 3.9+** (check with `python --version`).

2. **Create a virtual environment (recommended)**
   ```bash
   python -m venv venv
   source venv/bin/activate      # Windows: venv\Scripts\activate
   ```

3. **Install the one dependency**
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the app**
   ```bash
   python app.py
   ```
   This also creates `hostelmate.db` (SQLite file) automatically on first run.

5. **Open in browser**
   ```
   http://127.0.0.1:5000
   ```

6. **Demo flow**
   - Go to **Register Student** and add at least 4–6 students with a mix of
     room sizes (2/3/4) and varied preferences.
   - Go to **All Students** to review/delete entries.
   - Go to **Allocate Rooms** to run the matching engine and see the
     generated rooms with compatibility percentages.

## How the matching engine works (for viva)

**1. Weighted compatibility score (`matching.py → compute_compatibility`)**
   Each preference field has a weight (they sum to 100):
   `sleep_schedule=15, wake_schedule=10, cleanliness=15, noise_tolerance=15,
   study_habits=10, social_preference=10, guest_frequency=10,
   food_preference=5, study_hours=5, sleeping_environment=5`.

   - Exact match on a field → full marks for that field.
   - "No preference" / "Flexible" / "Other" on either side → treated as a
     full match (a flexible student doesn't penalise anyone).
   - Ordered fields (sleep schedule, wake schedule, cleanliness) give
     **partial credit** based on how close the two values are on the scale
     (e.g. Early vs Moderate scores higher than Early vs Late).
   - If both students picked each other under "Preferred Roommate", a bonus
     (+12, capped at 100) is added.

**2. Room allocation (`matching.py → allocate_rooms`)**
   A greedy nearest-neighbour clustering algorithm:
   1. Pre-compute compatibility for every pair of students.
   2. Take the next unplaced student and open a new room sized to their
      preferred room size (2/3/4).
   3. Repeatedly add whichever *remaining* unplaced student has the highest
      **average** compatibility with everyone already in that room, until
      the room is full.
   4. Repeat until every student belongs to exactly one room.

   This guarantees every student is placed exactly once and rooms are
   filled by pulling in the best available match at each step.

## Possible extensions (mention if asked "what would you improve?")
- Replace greedy allocation with a global optimization (e.g. Hungarian
  algorithm / integer programming) for a mathematically optimal grouping.
- Add an admin login and a fixed number of physical rooms with capacity
  limits instead of unlimited rooms.
- Export the final allocation to a downloadable PDF/Excel sheet.
- Move from SQLite to a hosted DB for a multi-user deployment.
