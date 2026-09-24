"""
db.py
------
Handles all database access for HostelMate using SQLite (built into Python,
so no extra dependency is needed). One table, `students`, stores every
profile a student fills in through the registration form.
"""

import sqlite3

DB_NAME = "hostelmate.db"


def get_connection():
    """Open a new connection. sqlite3 connections are cheap, so we open
    one per request instead of keeping a single long-lived connection."""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row  # lets us access columns by name, e.g. row["name"]
    return conn


def init_db():
    """Create the students table if it doesn't already exist.
    Called once when the app starts."""
    conn = get_connection()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
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
            room_size TEXT NOT NULL,            -- '2', '3', or '4'
            preferred_roommates TEXT DEFAULT ''  -- comma-separated student ids
        )
        """
    )
    conn.commit()
    conn.close()


def add_student(data: dict):
    """Insert one student profile. `data` keys must match the form field names."""
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO students (
            name, sleep_schedule, wake_schedule, study_habits, cleanliness,
            noise_tolerance, social_preference, guest_frequency, food_preference,
            study_hours, sleeping_environment, room_size, preferred_roommates
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data["name"], data["sleep_schedule"], data["wake_schedule"],
            data["study_habits"], data["cleanliness"], data["noise_tolerance"],
            data["social_preference"], data["guest_frequency"], data["food_preference"],
            data["study_hours"], data["sleeping_environment"], data["room_size"],
            data.get("preferred_roommates", ""),
        ),
    )
    conn.commit()
    conn.close()


def get_all_students():
    """Return every registered student as a list of sqlite3.Row objects."""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM students").fetchall()
    conn.close()
    return rows


def get_student(student_id):
    conn = get_connection()
    row = conn.execute("SELECT * FROM students WHERE id = ?", (student_id,)).fetchone()
    conn.close()
    return row


def delete_student(student_id):
    conn = get_connection()
    conn.execute("DELETE FROM students WHERE id = ?", (student_id,))
    conn.commit()
    conn.close()


def clear_all_students():
    """Wipe all data — handy for resetting the demo before a fresh run."""
    conn = get_connection()
    conn.execute("DELETE FROM students")
    conn.commit()
    conn.close()
