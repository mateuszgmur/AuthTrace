import os

import psycopg
from psycopg.types.json import Jsonb

DATABASE_URL = os.getenv("DATABASE_URL", "")

def db_connect(database_url):
    if not database_url:
        raise ValueError("DATABASE_URL nie może być pusty")
    return psycopg.connect(database_url)


def save_user(username):
    with db_connect(DATABASE_URL) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT user_id
                FROM users
                WHERE username = %s
                """,
                (username,),
            )
            row = cursor.fetchone()
            if row is not None:
                return row[0]

            cursor.execute(
                """
                INSERT INTO users (username)
                VALUES (%s)
                RETURNING user_id
                """,
                (username,),
            )
            return cursor.fetchone()[0]


def get_user_id(username):
    with db_connect(DATABASE_URL) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT user_id FROM users WHERE username = %s", (username,))
            row = cursor.fetchone()
            if row is None:
                raise ValueError(f"Nie znaleziono użytkownika: {username}")
            return row[0]


def get_usernames():
    with db_connect(DATABASE_URL) as conn:
        with conn.cursor() as cursor:
            cursor.execute("SELECT username FROM users ORDER BY username")
            return [row[0] for row in cursor.fetchall()]


def get_next_session_number(user_id):
    with db_connect(DATABASE_URL) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT COALESCE(MAX(session_number), 0) + 1
                FROM sessions
                WHERE user_id = %s
                """,
                (user_id,),
            )
            return cursor.fetchone()[0]


def save_session(user_id,session_number, raw_data, features_data):

    with db_connect(DATABASE_URL) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO sessions (
                    user_id,
                    session_number,
                    raw_json,
                    features_json
                )
                VALUES (%s, %s, %s, %s)
                RETURNING session_id
                """,
                (user_id, session_number, Jsonb(raw_data), Jsonb(features_data)),
            )
            return cursor.fetchone()[0]


def get_raw_data(user_id, session_id):
    with db_connect(DATABASE_URL) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                    SELECT raw_json FROM sessions
                    WHERE user_id = %s AND session_id = %s
                """,
                (user_id, session_id),
            )
            row = cursor.fetchone()
            if row is None:
                raise ValueError(f"Nie znaleziono sesji o id={session_id}")
            return row[0]


def get_features(user_id, session_id):
    with db_connect(DATABASE_URL) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT features_json
                FROM sessions
                WHERE user_id = %s AND session_id = %s
                """,
                (user_id, session_id),
            )
            row = cursor.fetchone()
            if row is None:
                raise ValueError(f"Nie znaleziono sesji o id={session_id}")
            if row[0] is None:
                raise ValueError(f"Sesja o id={session_id} nie ma cech")
            return row[0]


def get_session_ids(user_id):
    with db_connect(DATABASE_URL) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT session_id
                FROM sessions
                WHERE user_id = %s
                ORDER BY session_id
                """,
                (user_id,),
            )
            return [row[0] for row in cursor.fetchall()]


def get_all_features(user_id):
    with db_connect(DATABASE_URL) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT session_id, features_json
                FROM sessions
                WHERE user_id = %s AND features_json IS NOT NULL
                ORDER BY session_id
                """,
                (user_id,),
            )
            return cursor.fetchall()


def get_all_raw_data(user_id):
    with db_connect(DATABASE_URL) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT session_id, raw_json
                FROM sessions
                WHERE user_id = %s
                ORDER BY session_id
                """,
                (user_id,),
            )
            return cursor.fetchall()


def update_features(user_id, session_id, features_data):
    with db_connect(DATABASE_URL) as conn:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE sessions
                SET features_json = %s
                WHERE user_id = %s AND session_id = %s
                """,
                (Jsonb(features_data), user_id, session_id),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"Nie znaleziono sesji o id={session_id}")
