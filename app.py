"""
app.py
------
Flask application for HostelMate.

STUDENT: home, edit preferences, my profile (room + roommates), all students,
         compatibility with any other student.
ADMIN:   dashboard, all students, generate / lock / unlock / export the room
         allocation, remove a student.

Security notes
    * Passwords are hashed (werkzeug).
    * Secrets come from environment variables, never from the source code.
    * Every POST form carries a CSRF token.
    * Profile input is validated on the server, not only in the browser.
    * Repeated wrong passwords or admin keys are temporarily blocked.
"""

import csv
import hmac
import io
import os
import re
import secrets
import time
from collections import Counter
from functools import wraps

from flask import (
    Flask, Response, abort, flash, redirect, render_template,
    request, session, url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash

import db
import matching


app = Flask(__name__)

# ============================================================
# SETTINGS
# ============================================================

# Secret key used to sign login sessions and CSRF tokens.
#   1. If HOSTELMATE_SECRET_KEY is set, that is used (best for production).
#   2. Otherwise a random key is created ONCE and saved in ".secret_key" next
#      to this file, so restarts (and the debug auto-reloader) no longer log
#      everyone out or cause "That form expired" errors.
# Do not share or commit the ".secret_key" file.
def _load_secret_key():
    env_key = os.environ.get("HOSTELMATE_SECRET_KEY")
    if env_key:
        return env_key

    key_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".secret_key")
    try:
        with open(key_file, "r", encoding="utf-8") as f:
            saved = f.read().strip()
            if saved:
                return saved
    except OSError:
        pass

    new_key = secrets.token_hex(32)
    try:
        with open(key_file, "w", encoding="utf-8") as f:
            f.write(new_key)
        os.chmod(key_file, 0o600)
    except OSError:
        pass  # read-only folder: fall back to a key that lasts for this run
    return new_key


app.secret_key = _load_secret_key()
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"

# Fixed key required to create an admin account.
ADMIN_REGISTRATION_KEY = "HOSTELMATE2026"

# Choices for the three background fields (shown as dropdowns).
LANGUAGES = [
    "English", "Hindi", "Marathi", "Gujarati", "Bengali", "Punjabi",
    "Urdu", "Tamil", "Telugu", "Kannada", "Malayalam", "Odia",
    "Assamese", "Konkani", "Sindhi", "Other",
]
RELIGIONS = [
    "Hinduism", "Islam", "Christianity", "Sikhism", "Buddhism",
    "Jainism", "Zoroastrianism", "Other", "Prefer not to say",
]

FORM_OPTIONS = {
    "sleep_schedule": ["Early", "Moderate", "Late"],
    "wake_schedule": ["Early", "Moderate", "Late"],
    "study_habits": ["Room", "Library", "Other"],
    "cleanliness": ["Very tidy", "Moderate", "Relaxed"],
    "noise_tolerance": ["Quiet", "Moderate", "No preference"],
    "social_preference": ["Private", "Balanced", "Social"],
    "guest_frequency": ["Never", "Sometimes", "Often"],
    "food_preference": ["Vegetarian", "Non-Vegetarian", "No preference"],
    "study_hours": ["Morning", "Evening", "Late Night"],
    "sleeping_environment": ["Needs dark & silent", "Moderate", "Flexible"],
    "room_size": ["2", "3", "4"],

    # Background details. Collected and stored only; not used in scoring yet.
    "language_preference": LANGUAGES,
    "mother_tongue": LANGUAGES,
    "religion": RELIGIONS,
}

FIELD_LABELS = dict(
    matching.FIELD_LABELS,
    room_size="Room sharing",
    language_preference="Language preference",
    mother_tongue="Mother tongue",
    religion="Religion",
)

EMAIL_PATTERN = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
PHONE_PATTERN = re.compile(r"\+?\d[\d\s-]{8,14}\d")


# ============================================================
# STARTUP, CSRF, TEMPLATE HELPERS
# ============================================================

# Create / upgrade the tables once, when the app starts.
db.init_db()


def get_csrf_token():
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_hex(16)
    return session["_csrf"]


app.jinja_env.globals["csrf_token"] = get_csrf_token


@app.context_processor
def inject_globals():
    # "Pending" = the allocation is locked, but it has been cleared because a
    # new student registered afterwards. The admin must generate a new one.
    pending = db.is_allocation_locked() and not db.has_allocation()
    return {"labels": FIELD_LABELS, "allocation_pending": pending}


@app.template_filter("initials")
def initials(name):
    parts = (name or "?").split()
    return "".join(p[0] for p in parts[:2]).upper()


@app.before_request
def csrf_protect():
    """Reject any POST that does not carry this session's token."""
    if request.method == "POST":
        sent = request.form.get("_csrf", "")
        expected = session.get("_csrf", "")
        if not expected or not hmac.compare_digest(sent, expected):
            abort(400)


@app.errorhandler(400)
def bad_request(_):
    return render_template(
        "error.html", code=400,
        message="That form expired or was not valid. Go back, refresh the page and try again.",
    ), 400


@app.errorhandler(404)
def not_found(_):
    return render_template(
        "error.html", code=404, message="We could not find that page."
    ), 404


@app.errorhandler(500)
def server_error(_):
    return render_template(
        "error.html", code=500,
        message="The server hit an unexpected problem. The exact error is "
                "printed in the terminal window where HostelMate is running.",
    ), 500


# Every template the app needs. If one is missing from the "templates" folder
# the matching page crashes with a 500 error, so we check at start-up and say
# exactly which file is missing.
REQUIRED_TEMPLATES = [
    "base.html", "_macros.html", "_prefs.html", "error.html",
    "login.html", "student_register.html", "admin_register.html",
    "index.html", "register.html", "profile.html", "students.html",
    "student_view_profile.html", "admin_home.html",
    "admin_student_profile.html", "allocate.html",
]


def _check_templates():
    folder = os.path.join(app.root_path, app.template_folder or "templates")
    missing = [
        name for name in REQUIRED_TEMPLATES
        if not os.path.exists(os.path.join(folder, name))
    ]
    if missing and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        print("\n  !! MISSING TEMPLATE FILES in " + folder)
        for name in missing:
            print("     - " + name)
        print("  Copy them into that folder, then restart. "
              "Pages that use them will show a 500 error until then.\n")


_check_templates()


# ============================================================
# LOGIN THROTTLING (in memory, fine for a single-process demo)
# ============================================================

MAX_ATTEMPTS = 5
LOCKOUT_SECONDS = 300
_failures = {}


def _locked_out(key):
    entry = _failures.get(key)
    if not entry:
        return False
    count, last = entry
    if time.time() - last > LOCKOUT_SECONDS:
        _failures.pop(key, None)
        return False
    return count >= MAX_ATTEMPTS


def _record_failure(key):
    count, _ = _failures.get(key, (0, 0))
    _failures[key] = (count + 1, time.time())


# ============================================================
# ACCESS CONTROL
# ============================================================

def _role_required(role):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if "user_id" not in session:
                flash("Please log in to continue.", "error")
                return redirect(url_for("login"))
            if session.get("role") != role:
                flash(f"{role.title()} access required.", "error")
                return redirect(url_for("index"))
            return view(*args, **kwargs)
        return wrapped
    return decorator


student_required = _role_required("student")
admin_required = _role_required("admin")


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def _start_session(user_id, username, role):
    session.clear()
    session["user_id"] = user_id
    session["username"] = username
    session["role"] = role


# ============================================================
# SMALL HELPERS
# ============================================================

def ranked_matches(me, others):
    """[(student, score)] for everyone except `me`, best match first."""
    scored = [
        (s, matching.compute_compatibility(me, s))
        for s in others if s["id"] != me["id"]
    ]
    return sorted(scored, key=lambda pair: -pair[1])


def preferred_students_of(student):
    ids = [
        int(x) for x in (student["preferred_roommates"] or "").split(",")
        if x.strip().isdigit()
    ]
    return [s for s in (db.get_student(i) for i in ids) if s]


def build_stats(students):
    allocated = db.get_allocated_student_ids()
    sizes = Counter(s["room_size"] for s in students)
    return {
        "total": len(students),
        "allocated": len(allocated),
        "waiting": len(students) - len(allocated),
        "by_size": {size: sizes.get(size, 0) for size in ("2", "3", "4")},
    }


def validate_profile(form, own_id):
    """Return (clean_data, error_message). error_message is None when valid."""

    data = {field: form.get(field, "").strip() for field in FORM_OPTIONS}
    for field in ("name", "age", "branch", "phone", "email"):
        data[field] = form.get(field, "").strip()

    chosen = [x for x in form.getlist("preferred_roommates") if x.strip()]
    data["preferred_roommates"] = ",".join(chosen)

    if not 2 <= len(data["name"]) <= 60:
        return data, "Enter your full name (2 to 60 characters)."

    if not data["age"].isdigit() or not 16 <= int(data["age"]) <= 40:
        return data, "Enter your age as a number between 16 and 40."

    if not data["branch"]:
        return data, "Enter your branch or course."

    if not PHONE_PATTERN.fullmatch(data["phone"]):
        return data, "Enter a valid phone number (9 to 15 digits)."

    if not EMAIL_PATTERN.fullmatch(data["email"]):
        return data, "Enter a valid email address."

    for field, options in FORM_OPTIONS.items():
        if data[field] not in options:
            return data, f"Choose an option for \"{FIELD_LABELS[field]}\"."

    valid_ids = {str(s["id"]) for s in db.get_all_students() if s["id"] != own_id}
    if len(set(chosen)) != len(chosen) or any(c not in valid_ids for c in chosen):
        return data, "One of the preferred roommates is not valid."

    limit = int(data["room_size"]) - 1
    if len(chosen) > limit:
        return data, (
            f"A {data['room_size']}-sharing room has {limit} roommate"
            f"{'s' if limit > 1 else ''}. Pick at most {limit}."
        )

    return data, None


# ============================================================
# AUTHENTICATION
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "student")

        if not username or not password:
            return render_template("login.html", error="Enter your username and password.")

        key = f"login|{request.remote_addr}|{username.lower()}"
        if _locked_out(key):
            return render_template(
                "login.html",
                error="Too many failed attempts. Wait 5 minutes and try again.",
            )

        user = db.get_user_by_username(username)

        if user is None or not check_password_hash(user["password_hash"], password):
            _record_failure(key)
            return render_template("login.html", error="Invalid username or password.")

        if user["role"] != role:
            return render_template(
                "login.html",
                error=f"This is a {user['role']} account. Switch the account type above.",
            )

        _failures.pop(key, None)
        _start_session(user["id"], user["username"], user["role"])
        return redirect(url_for("index"))

    return render_template("login.html", error=None)


def _register_account(role, template):
    """Shared sign-up logic for students and admins."""

    if request.method == "GET":
        return render_template(template, error=None)

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    confirm = request.form.get("confirm_password", "")

    def fail(message):
        return render_template(template, error=message)

    if role == "admin":
        key = f"adminkey|{request.remote_addr}"
        if _locked_out(key):
            return fail("Too many wrong keys. Wait 5 minutes and try again.")
        sent_key = request.form.get("admin_key", "")
        if not hmac.compare_digest(sent_key, ADMIN_REGISTRATION_KEY):
            _record_failure(key)
            return fail("That admin registration key is not correct.")

    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,30}", username):
        return fail("Username must be 3 to 30 letters, numbers, dots, dashes or underscores.")
    if len(password) < 6:
        return fail("Password must be at least 6 characters.")
    if password != confirm:
        return fail("The two passwords do not match.")
    if db.get_user_by_username(username):
        return fail("That username is already taken.")

    user_id = db.create_user(username, generate_password_hash(password), role)
    _start_session(user_id, username, role)

    if role == "admin":
        flash("Admin account created.", "success")
        return redirect(url_for("admin_home"))

    flash("Account created. Now fill in your preferences.", "success")
    return redirect(url_for("register"))


@app.route("/student/register", methods=["GET", "POST"])
def student_account_register():
    return _register_account("student", "student_register.html")


@app.route("/admin/register", methods=["GET", "POST"])
def admin_account_register():
    return _register_account("admin", "admin_register.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


# ============================================================
# HOME PAGES
# ============================================================

@app.route("/")
@login_required
def index():
    if session.get("role") == "admin":
        return redirect(url_for("admin_home"))
    return redirect(url_for("student_home"))


@app.route("/student/home")
@student_required
def student_home():
    student = db.get_student_by_user_id(session["user_id"])
    allocation = db.get_student_allocation(student["id"]) if student else None
    top_matches = []

    if student:
        top_matches = ranked_matches(student, db.get_all_students())[:3]

    return render_template(
        "index.html",
        student=student,
        allocation=allocation,
        locked=db.is_allocation_locked(),
        top_matches=top_matches,
    )


@app.route("/admin")
@admin_required
def admin_home():
    students = db.get_all_students()
    return render_template(
        "admin_home.html",
        students=students,
        stats=build_stats(students),
        allocation_locked=db.is_allocation_locked(),
        has_allocation=db.has_allocation(),
    )


# ============================================================
# STUDENT PROFILE
# ============================================================

@app.route("/register", methods=["GET", "POST"])
@student_required
def register():
    """Create or edit the logged-in student's profile and preferences."""

    current = db.get_student_by_user_id(session["user_id"])
    own_id = current["id"] if current else None
    others = [s for s in db.get_all_students() if s["id"] != own_id]

    def page(values, error=None, locked=False):
        return render_template(
            "register.html",
            options=FORM_OPTIONS,
            students=others,
            student=current,
            v=values,
            locked=locked,
            late_join=db.is_allocation_locked() and current is None,
            error=error,
        )

    # The lock freezes profiles that ALREADY exist. A brand-new student (no
    # profile yet) may always create theirs, even while the allocation is locked.
    if db.is_allocation_locked() and current is not None:
        return page(dict(current), locked=True)

    if request.method == "POST":
        data, error = validate_profile(request.form, own_id)
        if error:
            return page(data, error=error)

        if current is None:
            was_locked = db.is_allocation_locked()
            db.add_student(data, user_id=session["user_id"])
            if was_locked:
                flash("Profile saved. You are in the matching pool. "
                      "The admin will generate a new allocation that includes you.",
                      "success")
            else:
                flash("Profile saved. You are in the matching pool.", "success")
        else:
            db.update_student(current["id"], data)
            flash("Preferences updated.", "success")

        # The old allocation no longer reflects the data, so discard it. If the
        # lock was on, it stays on (existing students stay frozen) and the admin
        # sees "new allocation needed" until they generate again.
        db.clear_allocation()
        return redirect(url_for("student_profile"))

    return page(dict(current) if current else {})


@app.route("/profile")
@student_required
def student_profile():
    student = db.get_student_by_user_id(session["user_id"])
    allocation = None
    roommate_scores = {}
    preferred = []

    if student:
        preferred = preferred_students_of(student)
        allocation = db.get_student_allocation(student["id"])
        if allocation:
            roommate_scores = {
                r["id"]: matching.compute_compatibility(student, r)
                for r in allocation["roommates"]
            }

    return render_template(
        "profile.html",
        student=student,
        preferred_students=preferred,
        allocation=allocation,
        roommate_scores=roommate_scores,
        allocation_locked=db.is_allocation_locked(),
    )


# ============================================================
# BROWSING STUDENTS
# ============================================================

@app.route("/students")
@login_required
def students():
    all_students = db.get_all_students()
    me = None
    scores = {}

    if session.get("role") == "student":
        me = db.get_student_by_user_id(session["user_id"])
        if me:
            scores = {s["id"]: score for s, score in ranked_matches(me, all_students)}

    return render_template(
        "students.html",
        students=all_students,
        scores=scores,
        my_id=me["id"] if me else None,
        has_profile=me is not None,
    )


@app.route("/student/view/<int:student_id>")
@student_required
def student_view_profile(student_id):
    student = db.get_student(student_id)
    if student is None:
        flash("Student not found.", "error")
        return redirect(url_for("students"))

    me = db.get_student_by_user_id(session["user_id"])
    if me and me["id"] == student["id"]:
        return redirect(url_for("student_profile"))

    breakdown = matching.score_breakdown(me, student) if me else None

    return render_template(
        "student_view_profile.html",
        student=student,
        me=me,
        breakdown=breakdown,
        mutual=bool(me) and matching.is_mutual_preference(me, student),
    )


@app.route("/admin/student/<int:student_id>")
@admin_required
def admin_student_profile(student_id):
    student = db.get_student(student_id)
    if student is None:
        flash("Student not found.", "error")
        return redirect(url_for("students"))

    return render_template(
        "admin_student_profile.html",
        student=student,
        preferred_students=preferred_students_of(student),
        allocation=db.get_student_allocation(student["id"]),
        allocation_locked=db.is_allocation_locked(),
    )


@app.route("/admin/delete-student/<int:student_id>", methods=["POST"])
@admin_required
def delete_student(student_id):
    if db.is_allocation_locked():
        flash("Unlock the allocation before removing a student.", "error")
        return redirect(url_for("admin_student_profile", student_id=student_id))

    if db.get_student(student_id) is None:
        flash("Student not found.", "error")
        return redirect(url_for("students"))

    db.delete_student(student_id)
    db.clear_allocation()  # rooms changed, so the old allocation is stale
    flash("Student removed. Generate the allocation again.", "success")
    return redirect(url_for("students"))


# ============================================================
# ROOM ALLOCATION
# ============================================================

@app.route("/allocate")
@admin_required
def allocate():
    all_students = db.get_all_students()
    allocated_ids = db.get_allocated_student_ids()

    return render_template(
        "allocate.html",
        rooms=db.get_allocation(),
        waiting=[s for s in all_students if s["id"] not in allocated_ids],
        stats=build_stats(all_students),
        allocation_locked=db.is_allocation_locked(),
    )


@app.route("/admin/generate-allocation", methods=["POST"])
@admin_required
def generate_allocation():

    # A globally locked allocation cannot be regenerated.
    if db.is_allocation_locked():
        flash(
            "Allocation is globally locked. Unlock it before generating a new one.",
            "error"
        )
        return redirect(url_for("allocate"))

    all_students = db.get_all_students()

    if len(all_students) < 2:
        flash(
            "At least 2 students must register first.",
            "error"
        )
        return redirect(url_for("allocate"))

    # Students already in locked rooms must stay there.
    locked_student_ids = db.get_locked_student_ids()

    # Only students who are NOT in locked rooms are sent
    # to the matching algorithm.
    available_students = [
        student
        for student in all_students
        if student["id"] not in locked_student_ids
    ]

    rooms = matching.allocate_rooms(available_students)

    # db.save_allocation() will later be updated to preserve
    # the already-locked rooms and replace only unlocked rooms.
    db.save_allocation(rooms)

    if locked_student_ids:
        flash(
            "New allocation generated. Students in locked rooms "
            "were kept unchanged.",
            "success"
        )
    else:
        flash(
            "Allocation generated. Review it, then lock rooms or "
            "the full allocation.",
            "success"
        )
    return redirect(url_for("allocate"))

@app.route("/admin/lock-allocation", methods=["POST"])
@admin_required
def lock_allocation():
    if not db.has_allocation():
        flash("Generate an allocation before locking it.", "error")
        return redirect(url_for("allocate"))

    db.set_allocation_locked(True)
    flash("Allocation locked. Students can no longer edit their profiles.", "success")
    return redirect(url_for("allocate"))

@app.route("/admin/lock-room/<int:room_number>", methods=["POST"])
@admin_required
def lock_room(room_number):

    if db.is_allocation_locked():
        flash(
            "The full allocation is already locked.",
            "error"
        )
        return redirect(url_for("allocate"))

    if not db.room_exists(room_number):
        flash(
            "Room not found.",
            "error"
        )
        return redirect(url_for("allocate"))

    db.lock_room(room_number)

    flash(
        f"Room {room_number} has been locked. "
        "Its students will not be included in the next allocation.",
        "success"
    )

    return redirect(url_for("allocate"))


@app.route("/admin/unlock-room/<int:room_number>", methods=["POST"])
@admin_required
def unlock_room(room_number):

    if db.is_allocation_locked():
        flash(
            "Unlock the full allocation before unlocking an individual room.",
            "error"
        )
        return redirect(url_for("allocate"))

    if not db.room_exists(room_number):
        flash(
            "Room not found.",
            "error"
        )
        return redirect(url_for("allocate"))

    db.unlock_room(room_number)

    flash(
        f"Room {room_number} has been unlocked.",
        "success"
    )

    return redirect(url_for("allocate"))

@app.route("/admin/unlock-allocation", methods=["POST"])
@admin_required
def unlock_allocation():
    db.set_allocation_locked(False)
    flash("Allocation unlocked.", "success")
    return redirect(url_for("allocate"))


@app.route("/admin/export-allocation")
@admin_required
def export_allocation():
    """Download the allocation as a CSV file."""
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Room", "Room size", "Room compatibility %",
                     "Student ID", "Name", "Branch", "Phone", "Email"])

    for room in db.get_allocation():
        for m in room["members"]:
            writer.writerow([
                room["room_number"], room["room_size"], room["avg_compatibility"],
                m["id"], m["name"], m["branch"], m["phone"], m["email"],
            ])

    return Response(
        out.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=hostelmate_allocation.csv"},
    )


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    app.run(debug=os.environ.get("HOSTELMATE_DEBUG") == "1")