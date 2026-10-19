# HostelMate – Smart Roommate Matching System

A small Flask + SQLite web app that groups hostel students into compatible
roommate groups. Students fill in their lifestyle preferences, the app scores
every pair of students out of 100, and the warden generates the room allocation.

## Project structure
```
hostelmate/
├── app.py              # Flask routes, login, validation, CSRF protection
├── db.py               # SQLite schema + database helper functions
├── matching.py         # Compatibility scoring + room allocation algorithm
├── requirements.txt
├── static/style.css    # All styling
└── templates/
    ├── base.html                 # Layout, navbar, flash messages
    ├── _macros.html, _prefs.html # Small reusable pieces
    ├── login.html, student_register.html, admin_register.html
    ├── index.html                # Student home
    ├── register.html             # Profile / preferences form
    ├── profile.html              # Student's own profile + room
    ├── students.html             # All students (search + sort)
    ├── student_view_profile.html # Compatibility breakdown with one student
    ├── admin_home.html           # Admin dashboard
    ├── admin_student_profile.html
    ├── allocate.html             # Generate / lock / export allocation
    └── error.html
```

## Setup & run
1. Install Python 3.9+ (`python --version`).
2. (Recommended) create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate        # Windows: venv\Scripts\activate
   ```
3. Install the dependency: `pip install -r requirements.txt`
4. Start the app: `python app.py`
5. Open http://127.0.0.1:5000

The database (`hostelmate.db`) and a `.secret_key` file are created on first
run. Keep `.secret_key` private and do not commit it to Git.

### Admin account
The terminal prints an **Admin registration key** when the app starts. Use it on
the *Admin sign-up* page. The key stays the same between restarts. To choose
your own, set the environment variable before running:
```bash
export HOSTELMATE_ADMIN_KEY=yourkey        # Windows: set HOSTELMATE_ADMIN_KEY=yourkey
```

### Optional settings (environment variables)
| Variable | What it does |
|---|---|
| `HOSTELMATE_SECRET_KEY` | Signs login sessions. If unset, one is created and saved in `.secret_key`. |
| `HOSTELMATE_ADMIN_KEY` | Key needed to create an admin account. If unset, one is derived from the secret key. |
| `HOSTELMATE_DEBUG=1` | Turns on Flask debug mode (auto-reload). Use only while developing. |

### Demo flow
1. Create 6+ student accounts (*Create an account*) and fill each profile.
2. Create an admin account, open **Allocate rooms**, press **Generate allocation**.
3. Review rooms and the waiting list, then **Lock** to freeze profiles.
4. Log in as a student to see your room, roommates and top matches.

### Troubleshooting
- **"Internal Server Error" (500):** look at the terminal where `python app.py`
  is running; the last lines name the problem. The most common cause is a
  missing file in `templates/` (it must contain all 15 `.html` files, including
  `_macros.html` and `_prefs.html`). The app also prints any missing template
  names when it starts.
- **"That form expired" (400):** open the page fresh (`Ctrl + Shift + R`) and
  try again; make sure you use one address (`127.0.0.1` *or* `localhost`).

## How the matching engine works

**1. Compatibility score (`compute_compatibility`)** – 0 to 100 for any two students.
Each of 10 preferences has a weight (they add up to 100):
sleep schedule 15, wake-up time 10, cleanliness 15, noise tolerance 15,
where they study 10, social style 10, guests 10, food 5, study hours 5,
sleeping environment 5.

- Same answer → full points for that field.
- "No preference" / "Flexible" / "Other" on either side → full points.
- Ordered fields (e.g. Early / Moderate / Late) → **partial credit** by distance,
  so Early vs Moderate scores higher than Early vs Late.
- If two students picked each other as preferred roommates → **+12 bonus** (max 100).
- `score_breakdown` explains the score field by field (shown on the compatibility page).

**2. Room allocation (`allocate_rooms`)** – students are grouped by the room size
they asked for (2, 3 or 4) and each group is solved separately.
Priority: **(1)** place as many students as possible, **(2)** among those,
maximise total pairwise compatibility.

- **Small groups** (up to 20 for 2-sharing, 16 for 3, 14 for 4) are solved
  **exactly** with dynamic programming + memoisation (about 0.3 s at the limit).
- **Larger groups** use a fast **greedy + swap improvement** method.
- Students who cannot complete a full room stay on the **waiting list**.

## Possible extensions
- Fixed physical rooms with capacity limits.
- Admin-editable weights.
- Downloadable PDF allocation sheet.
- Hosted database for multi-user deployment.