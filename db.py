"""
db.py
------
Handles all database access for HostelMate using SQLite.

Database structure:
    users       -> login accounts and roles
    students    -> student profiles and preferences
    app_settings -> application-wide settings
    allocation_results -> saved room allocation results
"""

import sqlite3
import os


# =============================================================
# DATABASE LOCATION
# =============================================================

DB_NAME = os.path.join(
    os.path.dirname(__file__),
    "hostelmate.db"
)


# =============================================================
# DATABASE CONNECTION
# =============================================================

def get_connection():
    """Open a new SQLite connection."""

    conn = sqlite3.connect(DB_NAME)

    conn.row_factory = sqlite3.Row

    # Enable foreign-key support.
    conn.execute("PRAGMA foreign_keys = ON")

    return conn


# =============================================================
# DATABASE INITIALIZATION
# =============================================================

def init_db():
    """Create tables and safely migrate older HostelMate databases."""

    conn = get_connection()

    # ---------------------------------------------------------
    # USERS TABLE
    # ---------------------------------------------------------

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL
                CHECK(role IN ('student', 'admin'))
        )
        """
    )

    # ---------------------------------------------------------
    # STUDENTS TABLE
    # ---------------------------------------------------------
    #
    # user_id connects the student profile with the login account.
    #

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            user_id INTEGER,

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

            language_preference TEXT,
            mother_tongue TEXT,
            religion TEXT,

            FOREIGN KEY (user_id)
                REFERENCES users(id)
                ON DELETE CASCADE
        )
        """
    )

    # ---------------------------------------------------------
    # MIGRATION FOR OLD DATABASES
    # ---------------------------------------------------------
    #
    # Your existing hostelmate.db may have been created before
    # user_id, age, branch, phone and email were added.
    #
    # Therefore we check which columns already exist and add
    # only the missing ones.
    #

    existing_columns = {
        row["name"]
        for row in conn.execute(
            "PRAGMA table_info(students)"
        ).fetchall()
    }

    migrations = {
        "user_id":
            "ALTER TABLE students ADD COLUMN user_id INTEGER",

        "age":
            "ALTER TABLE students ADD COLUMN age INTEGER",

        "branch":
            "ALTER TABLE students ADD COLUMN branch TEXT",

        "phone":
            "ALTER TABLE students ADD COLUMN phone TEXT",

        "email":
            "ALTER TABLE students ADD COLUMN email TEXT",

        "preferred_roommates":
            "ALTER TABLE students ADD COLUMN preferred_roommates TEXT DEFAULT ''",

        # Added later: language / background details. Nullable on purpose,
        # so students registered before this update keep working (NULL).
        "language_preference":
            "ALTER TABLE students ADD COLUMN language_preference TEXT",

        "mother_tongue":
            "ALTER TABLE students ADD COLUMN mother_tongue TEXT",

        "religion":
            "ALTER TABLE students ADD COLUMN religion TEXT"
    }

    for column, sql in migrations.items():

        if column not in existing_columns:

            conn.execute(sql)

    # ---------------------------------------------------------
    # UNIQUE USER -> STUDENT PROFILE
    # ---------------------------------------------------------
    #
    # One student login should have only one student profile.
    #

    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS
        idx_students_user_id
        ON students(user_id)
        WHERE user_id IS NOT NULL
        """
    )

    # ---------------------------------------------------------
    # APPLICATION SETTINGS
    # ---------------------------------------------------------

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            setting_name TEXT PRIMARY KEY,
            setting_value TEXT NOT NULL
        )
        """
    )

    # Allocation starts unlocked.

    conn.execute(
        """
        INSERT OR IGNORE INTO app_settings
        (setting_name, setting_value)
        VALUES ('allocation_locked', '0')
        """
    )

    # ---------------------------------------------------------
    # ALLOCATION RESULTS
    # ---------------------------------------------------------

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS allocation_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,

            room_number INTEGER NOT NULL,

            room_size TEXT NOT NULL,

            avg_compatibility INTEGER NOT NULL,

            student_id INTEGER NOT NULL,

            FOREIGN KEY (student_id)
                REFERENCES students(id)
                ON DELETE CASCADE
        )
        """
    )

    conn.commit()

    conn.close()


# =============================================================
# USER / ACCOUNT FUNCTIONS
# =============================================================

def create_user(username, password_hash, role):
    """Create a new user account.

    Returns:
        Newly created user ID.
    """

    conn = get_connection()

    cursor = conn.execute(
        """
        INSERT INTO users (
            username,
            password_hash,
            role
        )
        VALUES (?, ?, ?)
        """,
        (
            username,
            password_hash,
            role
        )
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
    """Find a user by ID."""

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
            preferred_roommates,

            language_preference,
            mother_tongue,
            religion

        )
        VALUES (
            ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?
        )
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

            data.get("language_preference"),
            data.get("mother_tongue"),
            data.get("religion")
        )
    )

    conn.commit()

    student_id = cursor.lastrowid

    conn.close()

    return student_id


def get_all_students():
    """Return all registered students."""

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
    """Return one student by ID."""

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
    """Return the student profile belonging to a login account."""

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
            preferred_roommates = ?,

            language_preference = ?,
            mother_tongue = ?,
            religion = ?

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

            data.get("language_preference"),
            data.get("mother_tongue"),
            data.get("religion"),

            student_id
        )
    )

    conn.commit()

    conn.close()


# =============================================================
# ALLOCATION LOCK
# =============================================================

def is_allocation_locked():
    """Return True if allocation is locked."""

    conn = get_connection()

    row = conn.execute(
        """
        SELECT setting_value
        FROM app_settings
        WHERE setting_name = 'allocation_locked'
        """
    ).fetchone()

    conn.close()

    if row is None:
        return False

    return row["setting_value"] == "1"


def set_allocation_locked(locked):
    """Lock or unlock room allocation."""

    conn = get_connection()

    conn.execute(
        """
        UPDATE app_settings
        SET setting_value = ?
        WHERE setting_name = 'allocation_locked'
        """,
        (
            "1" if locked else "0",
        )
    )

    conn.commit()

    conn.close()


# =============================================================
# DELETE / RESET FUNCTIONS
# =============================================================

def delete_student(student_id):
    """Delete one student profile."""

    conn = get_connection()

    conn.execute(
        """
        DELETE FROM students
        WHERE id = ?
        """,
        (student_id,)
    )

    # Also remove this student from everyone else's "preferred roommates",
    # so no one is left pointing at a student who no longer exists.
    removed = str(student_id)

    rows = conn.execute(
        """
        SELECT id, preferred_roommates
        FROM students
        WHERE preferred_roommates IS NOT NULL
          AND preferred_roommates != ''
        """
    ).fetchall()

    for row in rows:
        ids = [
            x.strip()
            for x in row["preferred_roommates"].split(",")
            if x.strip()
        ]

        if removed in ids:
            kept = [x for x in ids if x != removed]

            conn.execute(
                "UPDATE students SET preferred_roommates = ? WHERE id = ?",
                (",".join(kept), row["id"])
            )

    conn.commit()

    conn.close()


def clear_all_students():
    """Delete all student profiles."""

    conn = get_connection()

    conn.execute(
        "DELETE FROM students"
    )

    conn.commit()

    conn.close()


# =============================================================
# ALLOCATION RESULT FUNCTIONS
# =============================================================

def clear_allocation():
    """Delete all saved allocation results."""

    conn = get_connection()

    conn.execute(
        "DELETE FROM allocation_results"
    )

    conn.commit()

    conn.close()


def save_allocation(rooms):
    """Save generated room allocation."""

    conn = get_connection()

    # Remove previous allocation.

    conn.execute(
        "DELETE FROM allocation_results"
    )

    for room_number, room in enumerate(
        rooms,
        start=1
    ):

        room_size = str(
            len(room["members"])
        )

        avg_compatibility = int(
            room["avg_compatibility"]
        )

        for member in room["members"]:

            conn.execute(
                """
                INSERT INTO allocation_results (
                    room_number,
                    room_size,
                    avg_compatibility,
                    student_id
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    room_number,
                    room_size,
                    avg_compatibility,
                    member["id"]
                )
            )

    conn.commit()

    conn.close()


def has_allocation():
    """Return True if an allocation exists."""

    conn = get_connection()

    row = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM allocation_results
        """
    ).fetchone()

    conn.close()

    return row["count"] > 0


def get_allocation():
    """Return the complete saved allocation."""

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT
            ar.room_number,
            ar.room_size AS allocated_room_size,
            ar.avg_compatibility,
            s.*
        FROM allocation_results ar

        JOIN students s
            ON s.id = ar.student_id

        ORDER BY
            ar.room_number,
            s.id
        """
    ).fetchall()

    conn.close()

    rooms = {}

    for row in rows:

        room_number = row["room_number"]

        if room_number not in rooms:

            rooms[room_number] = {
                "room_number": room_number,
                "room_size": row["allocated_room_size"],
                "avg_compatibility": row["avg_compatibility"],
                "members": []
            }

        rooms[room_number]["members"].append(
            row
        )

    return list(
        rooms.values()
    )


def get_student_allocation(student_id):
    """Return the allocation for one student."""

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

        JOIN students s
            ON s.id = ar.student_id

        WHERE
            ar.room_number = ?
            AND ar.student_id != ?

        ORDER BY s.id
        """,
        (
            row["room_number"],
            student_id
        )
    ).fetchall()

    conn.close()

    return {
        "room_number":
            row["room_number"],

        "room_size":
            row["room_size"],

        "avg_compatibility":
            row["avg_compatibility"],

        "roommates":
            roommates
    }


def get_allocated_student_ids():
    """Return IDs of students already allocated."""

    conn = get_connection()

    rows = conn.execute(
        """
        SELECT DISTINCT student_id
        FROM allocation_results
        """
    ).fetchall()

    conn.close()

    return {
        row["student_id"]
        for row in rows
    }