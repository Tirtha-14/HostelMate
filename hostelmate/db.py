"""
db.py
------
Handles all database access for HostelMate using SQLite.

Database structure:
    users       -> login accounts and roles
    students    -> student profiles and preferences
    app_settings -> application-wide settings such as allocation lock status
"""

import sqlite3
import os


# Always use the database located next to this db.py file.
DB_NAME = os.path.join(os.path.dirname(__file__), "hostelmate.db")


def get_connection():
    """Open a new SQLite connection."""

    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row

    # Allows foreign-key relationships to work correctly.
    conn.execute("PRAGMA foreign_keys = ON")

    return conn


def init_db():
    """Create all required tables if they do not already exist."""

    conn = get_connection()

    # ---------------------------------------------------------
    # USERS
    # ---------------------------------------------------------
    #
    # Stores login information.
    #
    # role can be:
    #     student
    #     admin
    #
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL CHECK(role IN ('student', 'admin'))
        )
        """
    )
        # Add personal-detail columns to older databases if they are missing
    existing_columns = [
        row["name"]
        for row in conn.execute("PRAGMA table_info(students)").fetchall()
    ]

    if "age" not in existing_columns:
        conn.execute("ALTER TABLE students ADD COLUMN age INTEGER")

    if "branch" not in existing_columns:
        conn.execute("ALTER TABLE students ADD COLUMN branch TEXT")

    if "phone" not in existing_columns:
        conn.execute("ALTER TABLE students ADD COLUMN phone TEXT")

    if "email" not in existing_columns:
        conn.execute("ALTER TABLE students ADD COLUMN email TEXT")
    # ---------------------------------------------------------
    # STUDENTS
    # ---------------------------------------------------------
    #
    # Stores the actual student profile and preferences.
    #
    # user_id connects the profile to the student's login account.
    #
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id INTEGER UNIQUE,

            name TEXT NOT NULL,
            age INTEGER,
            branch TEXT,
            phone TEXT,
            email TEXT,
            sleep_schedule TEXT NOT NULL,
            wake_schedule TEXT NOT NULL,
            study_habits TEXT NOT NULL,
            cleanliness TEXT NOT NULL,
            noise_tolerance TEXT NOT NULL,
            social_preference TEXT NOT NULL,
            guest_frequency TEXT NOT NULL,
            food_preference TEXT NOT NULL,
            study_hours TEXT NOT NULL,
            sleeping_environment TEXT NOT NULL,

            room_size TEXT NOT NULL,

            preferred_roommates TEXT DEFAULT '',

            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE
        )
        """
    )

    # ---------------------------------------------------------
    # APPLICATION SETTINGS
    # ---------------------------------------------------------
    #
    # Stores settings that apply to the whole application.
    #
    # We use this for allocation locking.
    #
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            setting_name TEXT PRIMARY KEY,
            setting_value TEXT NOT NULL
        )
        """
    )

    # Make sure the allocation starts unlocked.
    conn.execute(
        """
        INSERT OR IGNORE INTO app_settings
        (setting_name, setting_value)
        VALUES ('allocation_locked', '0')
        """
    )
    conn.execute("""
        CREATE TABLE IF NOT EXISTS allocation_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_number INTEGER NOT NULL,
            room_size TEXT NOT NULL,
            avg_compatibility INTEGER NOT NULL,
            student_id INTEGER NOT NULL,
            FOREIGN KEY (student_id) REFERENCES students(id) ON DELETE CASCADE
        )
    """)
    
    conn.commit()
    conn.close()


# =============================================================
# USER / ACCOUNT FUNCTIONS
# =============================================================

def create_user(username, password_hash, role):
    """Create a new login account.

    Returns the newly created user's ID.
    """

    conn = get_connection()

    cursor = conn.execute(
        """
        INSERT INTO users (username, password_hash, role)
        VALUES (?, ?, ?)
        """,
        (username, password_hash, role)
    )

    conn.commit()

    user_id = cursor.lastrowid

    conn.close()

    return user_id


def get_user_by_username(username):
    """Find a user by username."""

    conn = get_connection()

    row = conn.execute(
        """
        SELECT *
        FROM users
        WHERE username = ?
        """,
        (username,)
    ).fetchone()

    conn.close()

    return row


def get_user_by_id(user_id):
    """Find a user by their ID."""

    conn = get_connection()

    row = conn.execute(
        """
        SELECT *
        FROM users
        WHERE id = ?
        """,
        (user_id,)
    ).fetchone()

    conn.close()

    return row


# =============================================================
# STUDENT FUNCTIONS
# =============================================================

def add_student(data, user_id=None):
    """Insert a student profile.

    user_id connects the profile to the student's login account.
    """

    conn = get_connection()

    cursor = conn.execute(
        """
        INSERT INTO students (
            user_id,
            name,
            age,
            branch,
            phone,
            email,
            sleep_schedule,
            wake_schedule,
            study_habits,
            cleanliness,
            noise_tolerance,
            social_preference,
            guest_frequency,
            food_preference,
            study_hours,
            sleeping_environment,
            room_size,
            preferred_roommates
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            user_id,
            data["name"],
            data.get("age"),
            data.get("branch"),
            data.get("phone"),
            data.get("email"),
            data["sleep_schedule"],
            data["wake_schedule"],
            data["study_habits"],
            data["cleanliness"],
            data["noise_tolerance"],
            data["social_preference"],
            data["guest_frequency"],
            data["food_preference"],
            data["study_hours"],
            data["sleeping_environment"],
            data["room_size"],
            data.get("preferred_roommates", ""),
        )
    )

    conn.commit()

    student_id = cursor.lastrowid

    conn.close()

    return student_id


def get_all_students():
    """Return every registered student."""

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT *
        FROM students
        ORDER BY id
        """
    ).fetchall()

    conn.close()

    return rows


def get_student(student_id):
    """Return a student by student ID."""

    conn = get_connection()

    row = conn.execute(
        """
        SELECT *
        FROM students
        WHERE id = ?
        """,
        (student_id,)
    ).fetchone()

    conn.close()

    return row


def get_student_by_user_id(user_id):
    """Find the student profile belonging to a login account."""

    conn = get_connection()

    row = conn.execute(
        """
        SELECT *
        FROM students
        WHERE user_id = ?
        """,
        (user_id,)
    ).fetchone()

    conn.close()

    return row


def update_student(student_id, data):
    """Update an existing student profile."""

    conn = get_connection()

    conn.execute(
        """
        UPDATE students
        SET
            name = ?,
            age = ?,
            branch = ?,
            phone = ?,
            email = ?,
            sleep_schedule = ?,
            wake_schedule = ?,
            study_habits = ?,
            cleanliness = ?,
            noise_tolerance = ?,
            social_preference = ?,
            guest_frequency = ?,
            food_preference = ?,
            study_hours = ?,
            sleeping_environment = ?,
            room_size = ?,
            preferred_roommates = ?
        WHERE id = ?
        """,
        (
            data["name"],
            data.get("age"),
            data.get("branch"),
            data.get("phone"),
            data.get("email"),
            data["sleep_schedule"],
            data["wake_schedule"],
            data["study_habits"],
            data["cleanliness"],
            data["noise_tolerance"],
            data["social_preference"],
            data["guest_frequency"],
            data["food_preference"],
            data["study_hours"],
            data["sleeping_environment"],
            data["room_size"],
            data.get("preferred_roommates", ""),
            student_id,
        )
    )

    conn.commit()
    conn.close()


# =============================================================
# ALLOCATION LOCK
# =============================================================

def is_allocation_locked():
    """Return True if the admin has locked the allocation."""

    conn = get_connection()

    row = conn.execute(
        """
        SELECT setting_value
        FROM app_settings
        WHERE setting_name = 'allocation_locked'
        """
    ).fetchone()

    conn.close()

    return row is not None and row["setting_value"] == "1"


def set_allocation_locked(locked):
    """Lock or unlock the allocation."""

    conn = get_connection()

    conn.execute(
        """
        UPDATE app_settings
        SET setting_value = ?
        WHERE setting_name = 'allocation_locked'
        """,
        ("1" if locked else "0",)
    )

    conn.commit()
    conn.close()


# =============================================================
# OLD DEMO / RESET FUNCTIONS
# =============================================================

def delete_student(student_id):
    """Delete a student profile."""

    conn = get_connection()

    conn.execute(
        """
        DELETE FROM students
        WHERE id = ?
        """,
        (student_id,)
    )

    conn.commit()
    conn.close()


def clear_all_students():
    """Wipe all student profiles.

    Useful for resetting the demo database.
    """

    conn = get_connection()

    conn.execute("DELETE FROM students")

    conn.commit()
    conn.close()

def clear_allocation():
    conn = get_connection()
    conn.execute("DELETE FROM allocation_results")
    conn.commit()
    conn.close()


def save_allocation(rooms):
    conn = get_connection()

    conn.execute("DELETE FROM allocation_results")

    for room_number, room in enumerate(rooms, start=1):
        room_size = str(len(room["members"]))
        avg_compatibility = int(room["avg_compatibility"])

        for member in room["members"]:
            conn.execute(
                """
                INSERT INTO allocation_results
                (room_number, room_size, avg_compatibility, student_id)
                VALUES (?, ?, ?, ?)
                """,
                (
                    room_number,
                    room_size,
                    avg_compatibility,
                    member["id"],
                )
            )

    conn.commit()
    conn.close()


def has_allocation():
    conn = get_connection()

    row = conn.execute(
        "SELECT COUNT(*) AS count FROM allocation_results"
    ).fetchone()

    conn.close()

    return row["count"] > 0


def get_allocation():
    conn = get_connection()

    rows = conn.execute(
        """
        SELECT
            ar.room_number,
            ar.room_size,
            ar.avg_compatibility,
            s.*
        FROM allocation_results ar
        JOIN students s ON s.id = ar.student_id
        ORDER BY ar.room_number, s.id
        """
    ).fetchall()

    conn.close()

    rooms = {}

    for row in rows:
        room_number = row["room_number"]

        if room_number not in rooms:
            rooms[room_number] = {
                "room_number": room_number,
                "room_size": row["room_size"],
                "avg_compatibility": row["avg_compatibility"],
                "members": []
            }

        rooms[room_number]["members"].append(row)

    return list(rooms.values())


def get_student_allocation(student_id):
    conn = get_connection()

    row = conn.execute(
        """
        SELECT
            ar.room_number,
            ar.room_size,
            ar.avg_compatibility
        FROM allocation_results ar
        WHERE ar.student_id = ?
        """,
        (student_id,)
    ).fetchone()

    if row is None:
        conn.close()
        return None

    roommates = conn.execute(
        """
        SELECT s.*
        FROM allocation_results ar
        JOIN students s ON s.id = ar.student_id
        WHERE ar.room_number = ?
          AND ar.student_id != ?
        ORDER BY s.id
        """,
        (row["room_number"], student_id)
    ).fetchall()

    conn.close()

    return {
        "room_number": row["room_number"],
        "room_size": row["room_size"],
        "avg_compatibility": row["avg_compatibility"],
        "roommates": roommates
    }


def get_allocated_student_ids():
    conn = get_connection()

    rows = conn.execute(
        """
        SELECT DISTINCT student_id
        FROM allocation_results
        """
    ).fetchall()

    conn.close()

    return {row["student_id"] for row in rows}