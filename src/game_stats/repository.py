import uuid
from datetime import datetime, timezone

from .database import session

KEYSPACE = "game_stats"

POINTS_WIN = 3
POINTS_DRAW = 1


def create_schema() -> None:
    session.execute(
        f"CREATE KEYSPACE IF NOT EXISTS {KEYSPACE} "
        "WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}"
    )
    session.execute(f"""
        CREATE TABLE IF NOT EXISTS {KEYSPACE}.players (
            player_id uuid PRIMARY KEY,
            name text,
            nickname text,
            created_at timestamp
        )
    """)
    session.execute(f"""
        CREATE TABLE IF NOT EXISTS {KEYSPACE}.matches (
            match_id uuid PRIMARY KEY,
            played_at timestamp,
            player_a uuid,
            player_b uuid,
            score_a int,
            score_b int
        )
    """)


def _player_row(row) -> dict:
    return {
        "player_id": row.player_id,
        "name": row.name,
        "nickname": row.nickname or "",
        "created_at": row.created_at,
    }


def _match_row(row) -> dict:
    return {
        "match_id": row.match_id,
        "played_at": row.played_at,
        "player_a": row.player_a,
        "player_b": row.player_b,
        "score_a": row.score_a,
        "score_b": row.score_b,
    }


def list_players() -> list[dict]:
    rows = session.execute(
        f"SELECT player_id, name, nickname, created_at FROM {KEYSPACE}.players"
    )
    return sorted((_player_row(r) for r in rows), key=lambda p: p["name"].lower())


def get_player(player_id: uuid.UUID) -> dict | None:
    row = session.execute(
        f"SELECT player_id, name, nickname, created_at FROM {KEYSPACE}.players WHERE player_id = %s",
        [player_id],
    ).one()
    return _player_row(row) if row else None


def create_player(name: str, nickname: str) -> None:
    session.execute(
        f"INSERT INTO {KEYSPACE}.players (player_id, name, nickname, created_at) VALUES (%s, %s, %s, %s)",
        (uuid.uuid4(), name, nickname, datetime.now(timezone.utc)),
    )


def update_player(player_id: uuid.UUID, name: str, nickname: str) -> None:
    session.execute(
        f"UPDATE {KEYSPACE}.players SET name = %s, nickname = %s WHERE player_id = %s",
        (name, nickname, player_id),
    )


def delete_player(player_id: uuid.UUID) -> None:
    session.execute(f"DELETE FROM {KEYSPACE}.players WHERE player_id = %s", [player_id])


def list_matches() -> list[dict]:
    rows = session.execute(
        f"SELECT match_id, played_at, player_a, player_b, score_a, score_b FROM {KEYSPACE}.matches"
    )
    return sorted((_match_row(r) for r in rows), key=lambda m: m["played_at"], reverse=True)


def create_match(player_a: uuid.UUID, player_b: uuid.UUID, score_a: int, score_b: int) -> None:
    session.execute(
        f"INSERT INTO {KEYSPACE}.matches (match_id, played_at, player_a, player_b, score_a, score_b) "
        "VALUES (%s, %s, %s, %s, %s, %s)",
        (uuid.uuid4(), datetime.now(timezone.utc), player_a, player_b, score_a, score_b),
    )


def compute_ranking(players: list[dict], matches: list[dict]) -> list[dict]:
    stats = {
        p["player_id"]: {
            "player_id": p["player_id"],
            "name": p["name"],
            "nickname": p["nickname"],
            "played": 0,
            "wins": 0,
            "draws": 0,
            "losses": 0,
            "points": 0,
        }
        for p in players
    }

    for match in matches:
        if match["score_a"] > match["score_b"]:
            results = {match["player_a"]: "win", match["player_b"]: "loss"}
        elif match["score_a"] < match["score_b"]:
            results = {match["player_a"]: "loss", match["player_b"]: "win"}
        else:
            results = {match["player_a"]: "draw", match["player_b"]: "draw"}

        for player_id, result in results.items():
            entry = stats.get(player_id)
            if entry is None:
                continue
            entry["played"] += 1
            if result == "win":
                entry["wins"] += 1
                entry["points"] += POINTS_WIN
            elif result == "draw":
                entry["draws"] += 1
                entry["points"] += POINTS_DRAW
            else:
                entry["losses"] += 1

    return sorted(stats.values(), key=lambda s: (-s["points"], -s["wins"], s["name"].lower()))


def get_ranking() -> list[dict]:
    return compute_ranking(list_players(), list_matches())
