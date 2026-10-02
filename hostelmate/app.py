"""
app.py
------
Main Flask application for HostelMate.

The application has two roles:

STUDENT
    - Home
    - Register / Edit Student Profile
    - All Students
    - Profile
    - Logout

ADMIN
    - Home
    - All Students
    - Allocate Rooms
    - Lock / Unlock Allocation
    - Logout

Authentication uses Flask sessions and hashed passwords.
"""

import os
from functools import wraps

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
)

from werkzeug.security import generate_password_hash, check_password_hash

import db
import matching


app = Flask(__name__)


# ============================================================
# APPLICATION SETTINGS
# ============================================================

# For a real deployment, set this as an environment variable.
# The fallback is convenient for your college demo.
app.secret_key = os.environ.get(
    "HOSTELMATE_SECRET_KEY",
    "hostelmate-demo-secret-change-later"
)

# Secret key required when creating an admin account.
# For the demo, you can use:
# HOSTELMATE2026
#
# Later we can move this completely into an environment variable.
ADMIN_REGISTRATION_KEY = os.environ.get(
    "HOSTELMATE_ADMIN_KEY",
    "HOSTELMATE2026"
)


# ============================================================
# FORM OPTIONS
# ============================================================

FORM_OPTIONS = {
    "sleep_schedule": ["Early", "Moderate", "Late"],
    "wake_schedule": ["Early", "Moderate", "Late"],
    "study_habits": ["Room", "Library", "Other"],
    "cleanliness": ["Very tidy", "Moderate", "Relaxed"],
    "noise_tolerance": ["Quiet", "Moderate", "No preference"],
    "social_preference": ["Private", "Balanced", "Social"],
    "guest_frequency": ["Never", "Sometimes", "Often"],
    "food_preference": [
        "Vegetarian",
        "Non-Vegetarian",
        "No preference"
    ],
    "study_hours": ["Morning", "Evening", "Late Night"],
    "sleeping_environment": [
        "Needs dark & silent",
        "Moderate",
        "Flexible"
    ],
    "room_size": ["2", "3", "4"],
}


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

@app.before_request
def ensure_db():
    """Make sure the database tables exist."""

    db.init_db()


# ============================================================
# AUTHENTICATION HELPERS
# ============================================================

def login_required(view):
    """
    Protect a route so only logged-in users can access it.
    """

    @wraps(view)
    def wrapped_view(*args, **kwargs):

        if "user_id" not in session:
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))

        return view(*args, **kwargs)

    return wrapped_view


def student_required(view):
    """
    Protect a route so only logged-in students can access it.
    """

    @wraps(view)
    def wrapped_view(*args, **kwargs):

        if "user_id" not in session:
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))

        if session.get("role") != "student":
            flash("Student access required.", "error")
            return redirect(url_for("admin_home"))

        return view(*args, **kwargs)

    return wrapped_view


def admin_required(view):
    """
    Protect a route so only logged-in administrators can access it.
    """

    @wraps(view)
    def wrapped_view(*args, **kwargs):

        if "user_id" not in session:
            flash("Please log in to continue.", "error")
            return redirect(url_for("login"))

        if session.get("role") != "admin":
            flash("Administrator access required.", "error")
            return redirect(url_for("student_profile"))

        return view(*args, **kwargs)

    return wrapped_view


# ============================================================
# LOGIN
# ============================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    """
    Common login page for students and admins.

    The user selects their role and enters username/password.
    """

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        role = request.form.get("role", "student")

        if not username or not password:
            return render_template(
                "login.html",
                error="Please enter your username and password."
            )

        user = db.get_user_by_username(username)

        if user is None:
            return render_template(
                "login.html",
                error="Invalid username or password."
            )

        # Make sure the selected role matches the account.
        if user["role"] != role:
            return render_template(
                "login.html",
                error="Incorrect account type selected."
            )

        if not check_password_hash(
            user["password_hash"],
            password
        ):
            return render_template(
                "login.html",
                error="Invalid username or password."
            )

        # Clear any old session information.
        session.clear()

        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["role"] = user["role"]

        if user["role"] == "admin":
            return redirect(url_for("admin_home"))

        return redirect(url_for("student_home"))

    return render_template(
        "login.html",
        error=None
    )


# ============================================================
# STUDENT ACCOUNT REGISTRATION
# ============================================================

@app.route("/student/register", methods=["GET", "POST"])
def student_account_register():
    """
    Creates a student login account.

    After creating the account, the student is logged in
    automatically and can complete their profile.
    """

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get(
            "confirm_password",
            ""
        )

        if not username or not password:
            return render_template(
                "student_register.html",
                error="Please fill in all fields."
            )

        if len(username) < 3:
            return render_template(
                "student_register.html",
                error="Username must be at least 3 characters."
            )

        if len(password) < 6:
            return render_template(
                "student_register.html",
                error="Password must be at least 6 characters."
            )

        if password != confirm_password:
            return render_template(
                "student_register.html",
                error="Passwords do not match."
            )

        existing_user = db.get_user_by_username(username)

        if existing_user:
            return render_template(
                "student_register.html",
                error="That username is already taken."
            )

        password_hash = generate_password_hash(password)

        user_id = db.create_user(
            username,
            password_hash,
            "student"
        )

        session.clear()

        session["user_id"] = user_id
        session["username"] = username
        session["role"] = "student"

        flash(
            "Account created. Now complete your student profile.",
            "success"
        )

        return redirect(url_for("register"))

    return render_template(
        "student_register.html",
        error=None
    )


# ============================================================
# ADMIN ACCOUNT REGISTRATION
# ============================================================

@app.route("/admin/register", methods=["GET", "POST"])
def admin_account_register():
    """
    Creates an administrator account.

    An admin registration key is required.
    """

    if request.method == "POST":

        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get(
            "confirm_password",
            ""
        )
        admin_key = request.form.get(
            "admin_key",
            ""
        )

        if not username or not password or not admin_key:
            return render_template(
                "admin_register.html",
                error="Please fill in all fields."
            )

        if admin_key != ADMIN_REGISTRATION_KEY:
            return render_template(
                "admin_register.html",
                error="Invalid admin registration key."
            )

        if len(username) < 3:
            return render_template(
                "admin_register.html",
                error="Username must be at least 3 characters."
            )

        if len(password) < 6:
            return render_template(
                "admin_register.html",
                error="Password must be at least 6 characters."
            )

        if password != confirm_password:
            return render_template(
                "admin_register.html",
                error="Passwords do not match."
            )

        existing_user = db.get_user_by_username(username)

        if existing_user:
            return render_template(
                "admin_register.html",
                error="That username is already taken."
            )

        password_hash = generate_password_hash(password)

        user_id = db.create_user(
            username,
            password_hash,
            "admin"
        )

        session.clear()

        session["user_id"] = user_id
        session["username"] = username
        session["role"] = "admin"

        flash(
            "Admin account created successfully.",
            "success"
        )

        return redirect(url_for("admin_home"))

    return render_template(
        "admin_register.html",
        error=None
    )


# ============================================================
# LOGOUT
# ============================================================

@app.route("/logout")
def logout():
    """Log out the current user."""

    session.clear()

    flash(
        "You have been logged out.",
        "success"
    )

    return redirect(url_for("login"))


# ============================================================
# HOME PAGES
# ============================================================

@app.route("/")
@login_required
def index():
    """
    Main entry point after login.

    Sends the user to the appropriate home page based
    on their role.
    """

    if session.get("role") == "admin":
        return redirect(url_for("admin_home"))

    return redirect(url_for("student_home"))


@app.route("/student/home")
@student_required
def student_home():
    """Student home page."""

    student = db.get_student_by_user_id(
        session["user_id"]
    )

    return render_template(
        "index.html",
        student=student,
        role="student"
    )


@app.route("/admin")
@admin_required
def admin_home():
    """Admin dashboard."""

    all_students = db.get_all_students()

    return render_template(
        "admin_home.html",
        students=all_students,
        allocation_locked=db.is_allocation_locked(),
        role="admin"
    )


# ============================================================
# STUDENT PROFILE / REGISTRATION
# ============================================================

@app.route("/register", methods=["GET", "POST"])
@student_required
def register():
    """
    Create or edit the currently logged-in student's profile.

    This is no longer account registration.

    Account registration happens at:
        /student/register

    This page handles the student's actual HostelMate profile.
    """

    current_student = db.get_student_by_user_id(
        session["user_id"]
    )

    # --------------------------------------------------------
    # Prevent changes after allocation is locked.
    # --------------------------------------------------------

    if db.is_allocation_locked():

        return render_template(
            "register.html",
            options=FORM_OPTIONS,
            students=db.get_all_students(),
            student=current_student,
            locked=True,
            error="Allocation is locked. Profile changes are no longer allowed."
        )

    if request.method == "POST":

        form = request.form

        preferred = ",".join(
            request.form.getlist(
                "preferred_roommates"
            )
        )

        data = {field: form.get(field) for field in FORM_OPTIONS}

        data["name"] = form.get("name", "").strip()
        data["age"] = form.get("age", "").strip()
        data["branch"] = form.get("branch", "").strip()
        data["phone"] = form.get("phone", "").strip()
        data["email"] = form.get("email", "").strip()

        data["preferred_roommates"] = preferred

        # Validate all required fields.
        if (
            not data["name"]
            or not data["age"]
            or not data["branch"]
            or not data["phone"]
            or not data["email"]
            or any(not data[field] for field in FORM_OPTIONS)
):
            return render_template(
                "register.html",
                options=FORM_OPTIONS,
                students=db.get_all_students(),
                student=current_student,
                locked=False,
                error="Please fill in every field before submitting."
            )

        # ----------------------------------------------------
        # Create profile if this is the student's first time.
        # Otherwise update the existing profile.
        # ----------------------------------------------------

        if current_student is None:
            db.add_student(data, user_id=session["user_id"])
            flash("Student profile saved successfully.", "success")
        else:
            db.update_student(current_student["id"], data)
            flash("Student profile updated successfully.", "success")

        db.clear_allocation()

        return redirect(url_for("student_profile"))

    return render_template(
        "register.html",
        options=FORM_OPTIONS,
        students=db.get_all_students(),
        student=current_student,
        locked=False,
        error=None
    )


# ============================================================
# STUDENT PROFILE PAGE
# ============================================================

@app.route("/profile")
@student_required
def student_profile():
    student = db.get_student_by_user_id(session["user_id"])

    preferred_students = []
    allocation = None

    if student:
        preferred_ids = [
            int(x)
            for x in (student["preferred_roommates"] or "").split(",")
            if x.strip().isdigit()
        ]

        for student_id in preferred_ids:
            preferred = db.get_student(student_id)
            if preferred:
                preferred_students.append(preferred)

        allocation = db.get_student_allocation(student["id"])

    return render_template(
        "profile.html",
        student=student,
        preferred_students=preferred_students,
        allocation=allocation,
        allocation_locked=db.is_allocation_locked()
    )
# ============================================================
# ALL STUDENTS
# ============================================================

@app.route("/students")
@login_required
def students():
    """
    Display registered students.

    Both students and admins can access this route,
    but the template can display different information
    depending on the role.
    """

    all_students = db.get_all_students()

    return render_template(
        "students.html",
        students=all_students,
        role=session.get("role")
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
        student=student
    )
@app.route("/student/view/<int:student_id>")
@student_required
def student_view_profile(student_id):
    student = db.get_student(student_id)

    if student is None:
        flash("Student not found.", "error")
        return redirect(url_for("students"))

    current_student = db.get_student_by_user_id(session["user_id"])

    compatibility = None

    if current_student and current_student["id"] != student["id"]:
        compatibility = matching.compute_compatibility(
            current_student,
            student
        )

    return render_template(
        "student_view_profile.html",
        student=student,
        compatibility=compatibility
    )

# ============================================================
# ADMIN STUDENT PROFILE
# ============================================================

@app.route("/allocate")
@admin_required
def allocate():
    all_students = db.get_all_students()
    allocation_locked = db.is_allocation_locked()

    rooms = db.get_allocation()

    allocated_ids = db.get_allocated_student_ids()

    waiting = [
        student
        for student in all_students
        if student["id"] not in allocated_ids
    ]

    return render_template(
        "allocate.html",
        rooms=rooms,
        waiting=waiting,
        warning=None,
        allocation_locked=allocation_locked
    )
# ============================================================
# ROOM ALLOCATION
# ============================================================

@app.route("/admin/generate-allocation", methods=["POST"])
@admin_required
def generate_allocation():
    if db.is_allocation_locked():
        flash(
            "Allocation is locked. Unlock it before generating a new allocation.",
            "error"
        )
        return redirect(url_for("allocate"))

    all_students = db.get_all_students()

    if len(all_students) < 2:
        flash(
            "Add at least 2 students before generating an allocation.",
            "error"
        )
        return redirect(url_for("allocate"))

    rooms = matching.allocate_rooms(all_students)

    db.save_allocation(rooms)

    flash(
        "Room allocation generated successfully. Review it before locking.",
        "success"
    )

    return redirect(url_for("allocate"))

# ============================================================
# LOCK / UNLOCK ALLOCATION
# ============================================================

@app.route("/admin/lock-allocation", methods=["POST"])
@admin_required
def lock_allocation():

    if not db.has_allocation():
        flash(
            "Generate an allocation before locking it.",
            "error"
        )
        return redirect(url_for("allocate"))

    db.set_allocation_locked(True)

    flash(
        "Allocation has been locked successfully.",
        "success"
    )

    return redirect(url_for("allocate"))

@app.route("/admin/unlock-allocation", methods=["POST"])
@admin_required
def unlock_allocation():
    """
    Unlock the allocation so changes can be made again.
    """

    db.set_allocation_locked(False)

    flash(
        "Allocation has been unlocked.",
        "success"
    )

    return redirect(
        url_for("allocate")
    )


# ============================================================
# APPLICATION START
# ============================================================

if __name__ == "__main__":

    db.init_db()

    app.run(
        debug=True
    )