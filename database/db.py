import os
import sqlite3
from flask import current_app, has_app_context


base_dir = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

db_file = os.path.join(
    base_dir,
    "database",
    "assurex.db"
)

schema_file = os.path.join(
    base_dir,
    "database",
    "schema.sql"
)


def get_db():
    path = current_app.config.get("DATABASE_FILE", db_file) if has_app_context() else db_file
    db = sqlite3.connect(path, timeout=15)

    db.row_factory = sqlite3.Row

    db.execute("PRAGMA foreign_keys = ON")

    return db


def init_db():
    try:
        db = get_db()

        with open(schema_file, "r", encoding="utf-8") as file:
            sql = file.read()

        db.executescript(sql)
        db.commit()
        db.close()

        print("database ready")

    except Exception as e:
        print("database error:", e)


def check_db():
    try:
        db = get_db()

        rows = db.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table'
            ORDER BY name
            """
        ).fetchall()

        db.close()

        return rows

    except Exception as e:
        print("database check error:", e)
        return []


if __name__ == "__main__":
    init_db()

    rows = check_db()

    print("tables:")

    for row in rows:
        print(row["name"])
