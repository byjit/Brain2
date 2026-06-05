"""User upsert + implicit signup tests (M7 deliverables 1 & 5).

A new google_sub creates a users row AND its {user_id}.db (running the per-user schema);
a returning google_sub maps to the SAME user_id. user_id is a server-generated nanoid
(never client-supplied), so it is path-safe for {user_id}.db routing.
"""

from brain2.auth import users
from brain2.auth.store import open_auth_db
from brain2.db.connection import user_db_path


def test_first_auth_creates_user_and_their_db(tmp_path):
    data_dir = tmp_path / "users"
    with open_auth_db(tmp_path / "auth.db") as conn:
        user_id = users.upsert_by_google_sub(
            conn, google_sub="sub-1", email="a@b.com", data_dir=data_dir
        )
        assert user_id  # server-generated nanoid
        # The per-user DB now exists with the schema applied.
        assert user_db_path(user_id, data_dir).exists()
        row = conn.execute(
            "SELECT email FROM users WHERE user_id=?", (user_id,)
        ).fetchone()
        assert row["email"] == "a@b.com"


def test_returning_sub_maps_to_same_user(tmp_path):
    data_dir = tmp_path / "users"
    with open_auth_db(tmp_path / "auth.db") as conn:
        first = users.upsert_by_google_sub(
            conn, google_sub="sub-1", email="a@b.com", data_dir=data_dir
        )
        second = users.upsert_by_google_sub(
            conn, google_sub="sub-1", email="a@b.com", data_dir=data_dir
        )
        assert first == second
        count = conn.execute("SELECT COUNT(*) c FROM users").fetchone()["c"]
        assert count == 1


def test_distinct_subs_map_to_isolated_users(tmp_path):
    data_dir = tmp_path / "users"
    with open_auth_db(tmp_path / "auth.db") as conn:
        u1 = users.upsert_by_google_sub(
            conn, google_sub="sub-1", email="a@b.com", data_dir=data_dir
        )
        u2 = users.upsert_by_google_sub(
            conn, google_sub="sub-2", email="c@d.com", data_dir=data_dir
        )
        assert u1 != u2
        assert user_db_path(u1, data_dir) != user_db_path(u2, data_dir)


def test_user_id_is_path_safe(tmp_path):
    """The generated user_id must not contain path-traversal characters."""
    data_dir = tmp_path / "users"
    with open_auth_db(tmp_path / "auth.db") as conn:
        user_id = users.upsert_by_google_sub(
            conn, google_sub="sub-x", email="x@y.com", data_dir=data_dir
        )
        assert "/" not in user_id and "\\" not in user_id and ".." not in user_id


def test_get_user_returns_profile(tmp_path):
    data_dir = tmp_path / "users"
    with open_auth_db(tmp_path / "auth.db") as conn:
        user_id = users.upsert_by_google_sub(
            conn, google_sub="sub-1", email="a@b.com", data_dir=data_dir
        )
        profile = users.get_user(conn, user_id)
        assert profile["user_id"] == user_id
        assert profile["email"] == "a@b.com"
        assert users.get_user(conn, "missing") is None
