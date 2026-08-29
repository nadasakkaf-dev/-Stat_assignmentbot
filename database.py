import sqlite3
import os

DB_PATH = os.getenv("DB_PATH", "submissions.db")
STUDENTS_FILE = os.getenv("STUDENTS_FILE", "students.txt")


def connect():
    return sqlite3.connect(DB_PATH)


def init_db():
    with connect() as con:
        con.execute("""
            CREATE TABLE IF NOT EXISTS submissions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_name TEXT NOT NULL,
                telegram_user_id INTEGER NOT NULL,
                file_name TEXT NOT NULL,
                file_id TEXT NOT NULL,
                submitted_at TEXT NOT NULL
            )
        """)

        con.commit()


def add_submission(
    student_name,
    telegram_user_id,
    file_name,
    file_id,
    submitted_at
):
    with connect() as con:

        cursor = con.execute("""
            INSERT INTO submissions
            (
                student_name,
                telegram_user_id,
                file_name,
                file_id,
                submitted_at
            )
            VALUES (?, ?, ?, ?, ?)
        """, (
            student_name,
            telegram_user_id,
            file_name,
            file_id,
            submitted_at
        ))

        con.commit()

        return cursor.lastrowid


def get_stats():

    with connect() as con:

        total = con.execute(
            "SELECT COUNT(*) FROM submissions"
        ).fetchone()[0]

        students = con.execute(
            "SELECT COUNT(DISTINCT telegram_user_id) "
            "FROM submissions"
        ).fetchone()[0]

        return total, students


def get_submissions():

    with connect() as con:

        return con.execute("""
            SELECT
                id,
                student_name,
                file_name,
                submitted_at
            FROM submissions
            ORDER BY id DESC
        """).fetchall()


def get_missing_students():

    if not os.path.exists(STUDENTS_FILE):
        return []

    with open(
        STUDENTS_FILE,
        "r",
        encoding="utf-8"
    ) as file:

        students = [
            line.strip()
            for line in file
            if line.strip()
            and not line.strip().startswith("#")
        ]

    with connect() as con:

        submitted = {
            row[0].strip()
            for row in con.execute(
                "SELECT DISTINCT student_name "
                "FROM submissions"
            ).fetchall()
        }

    return [
        name
        for name in students
        if name not in submitted
    ]
