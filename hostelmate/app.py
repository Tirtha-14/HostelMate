"""
app.py
-------
Entry point for HostelMate. A small Flask app with four pages:

  /            -> project landing page / abstract
  /register    -> form to add a student profile
  /students    -> list of all registered students (with delete option)
  /allocate    -> runs the matching engine and shows the room allocation

Run with:  python app.py
"""

from flask import Flask, render_template, request, redirect, url_for
import db
import matching

app = Flask(__name__)

# Options shown in the registration form dropdowns.
# Keeping them in one place makes the form and the matching logic consistent.
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
}


@app.before_request
def ensure_db():
    # init_db() uses "CREATE TABLE IF NOT EXISTS", so this is cheap to call
    # on every request and guarantees the table exists even on first run.
    db.init_db()


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        form = request.form
        # preferred_roommates comes in as a list from a multi-select box;
        # we store it as a comma-separated string for simplicity in SQLite.
        preferred = ",".join(request.form.getlist("preferred_roommates"))

        data = {field: form.get(field) for field in FORM_OPTIONS}
        data["name"] = form.get("name", "").strip()
        data["preferred_roommates"] = preferred

        # Basic validation: every field is required except preferred_roommates
        if not data["name"] or any(not data[f] for f in FORM_OPTIONS):
            existing_students = db.get_all_students()
            return render_template(
                "register.html", options=FORM_OPTIONS, students=existing_students,
                error="Please fill in every field before submitting."
            )

        db.add_student(data)
        return redirect(url_for("students"))

    existing_students = db.get_all_students()
    return render_template("register.html", options=FORM_OPTIONS, students=existing_students, error=None)


@app.route("/students")
def students():
    all_students = db.get_all_students()
    return render_template("students.html", students=all_students)


@app.route("/students/delete/<int:student_id>", methods=["POST"])
def delete_student(student_id):
    db.delete_student(student_id)
    return redirect(url_for("students"))


@app.route("/reset", methods=["POST"])
def reset():
    db.clear_all_students()
    return redirect(url_for("students"))


@app.route("/allocate")
def allocate():
    all_students = db.get_all_students()
    if len(all_students) < 2:
        return render_template("allocate.html", rooms=None,
                                warning="Add at least 2 students before running allocation.")
    rooms = matching.allocate_rooms(all_students)
    return render_template("allocate.html", rooms=rooms, warning=None)


if __name__ == "__main__":
    db.init_db()
    app.run(debug=True)
