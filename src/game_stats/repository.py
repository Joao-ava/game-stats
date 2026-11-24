import uuid
from datetime import date, datetime, timezone

from cassandra.query import BatchStatement, BatchType

from .database import session

KEYSPACE = "game_stats"
RANKING_ID = 1

POINTS_WIN = 3
POINTS_DRAW = 1

RESULT_POINTS = {"win": POINTS_WIN, "draw": POINTS_DRAW, "loss": 0}


def create_schema() -> None:
    session.execute(
        f"CREATE KEYSPACE IF NOT EXISTS {KEYSPACE} "
        "WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}"
    )
    session.execute(f"""
        CREATE TABLE IF NOT EXISTS {KEYSPACE}.players (
            player_id uuid PRIMARY KEY,
            username text,
            email text,
            created_at timestamp
        )
    """)
    session.execute(f"""
        CREATE TABLE IF NOT EXISTS {KEYSPACE}.matches_by_player (
            player_id uuid,
            match_date date,
            match_id uuid,
            game_mode text,
            score int,
            kills int,
            deaths int,
            result text,
            PRIMARY KEY ((player_id), match_date, match_id)
        ) WITH CLUSTERING ORDER BY (
            match_date DESC,
            match_id ASC
        )
    """)
    session.execute(f"""
        CREATE TABLE IF NOT EXISTS {KEYSPACE}.leaderboard (
            ranking_id int,
            score int,
            player_id uuid,
            username text,
            victories int,
            PRIMARY KEY ((ranking_id), score, player_id)
        ) WITH CLUSTERING ORDER BY (
            score DESC,
            player_id ASC
        )
    """)


def _player_row(row) -> dict:
    return {
        "player_id": row.player_id,
        "username": row.username,
        "email": row.email or "",
        "created_at": row.created_at,
    }


def _match_row(row, player_id: uuid.UUID) -> dict:
    return {
        "player_id": player_id,
        "match_date": row.match_date,
        "match_id": row.match_id,
        "score": row.score,
        "result": row.result,
    }


def _player_match_rows(player_id: uuid.UUID) -> list:
    return list(
        session.execute(
            f"SELECT match_date, match_id, score, result FROM {KEYSPACE}.matches_by_player WHERE player_id = %s",
            [player_id],
        )
    )


def list_players() -> list[dict]:
    rows = session.execute(f"SELECT player_id, username, email, created_at FROM {KEYSPACE}.players")
    return [_player_row(r) for r in rows]


def get_player(player_id: uuid.UUID) -> dict | None:
    row = session.execute(
        f"SELECT player_id, username, email, created_at FROM {KEYSPACE}.players WHERE player_id = %s",
        [player_id],
    ).one()
    return _player_row(row) if row else None


def create_player(username: str, email: str) -> None:
    session.execute(
        f"INSERT INTO {KEYSPACE}.players (player_id, username, email, created_at) VALUES (%s, %s, %s, %s)",
        (uuid.uuid4(), username, email, datetime.now(timezone.utc)),
    )


def update_player(player_id: uuid.UUID, username: str, email: str) -> bool:
    row = session.execute(
        f"UPDATE {KEYSPACE}.players SET username = %s, email = %s WHERE player_id = %s IF EXISTS",
        (username, email, player_id),
    ).one()
    return bool(row.applied)


def delete_player(player_id: uuid.UUID) -> None:
    if _player_match_rows(player_id):
        raise ValueError("Jogador possui partidas registradas e não pode ser excluído.")
    session.execute(f"DELETE FROM {KEYSPACE}.players WHERE player_id = %s", [player_id])


def list_player_matches(player_id: uuid.UUID) -> list[dict]:
    return [_match_row(row, player_id) for row in _player_match_rows(player_id)]


def _leaderboard_standings() -> dict[uuid.UUID, tuple[int, int]]:
    rows = session.execute(
        f"SELECT player_id, score, victories FROM {KEYSPACE}.leaderboard WHERE ranking_id = %s",
        [RANKING_ID],
    )
    return {r.player_id: (r.score, r.victories) for r in rows}


def create_match(
    player_id: uuid.UUID,
    score: int,
    result: str,
    match_id: uuid.UUID | None = None,
    match_date: date | None = None,
    game_mode: str = "",
    kills: int = 0,
    deaths: int = 0,
) -> bool:
    if score < 0:
        raise ValueError("As pontuações não podem ser negativas.")
    if result not in RESULT_POINTS:
        raise ValueError("Resultado inválido.")
    if kills < 0 or deaths < 0:
        raise ValueError("Abates e mortes não podem ser negativos.")

    match_id = match_id or uuid.uuid4()
    match_date = match_date or datetime.now(timezone.utc).date()

    # Idempotência: o INSERT condicional só é aplicado uma vez para um mesmo match_id.
    applied = session.execute(
        f"INSERT INTO {KEYSPACE}.matches_by_player (player_id, match_date, match_id, game_mode, score, kills, deaths, result) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) IF NOT EXISTS",
        (player_id, match_date, match_id, game_mode, score, kills, deaths, result),
    ).one().applied
    if not applied:
        return False

    standings = _leaderboard_standings()
    player = get_player(player_id)
    points, wins = standings.get(player_id, (0, 0))
    batch = BatchStatement(batch_type=BatchType.LOGGED)
    # Derrota não muda a pontuação: DELETE e INSERT na mesma chave no mesmo batch
    # apagariam a linha, pois tombstone vence no mesmo timestamp.
    if player_id in standings and RESULT_POINTS[result] > 0:
        batch.add(
            f"DELETE FROM {KEYSPACE}.leaderboard WHERE ranking_id = %s AND score = %s AND player_id = %s",
            (RANKING_ID, points, player_id),
        )
    batch.add(
        f"INSERT INTO {KEYSPACE}.leaderboard (ranking_id, score, player_id, username, victories) "
        "VALUES (%s, %s, %s, %s, %s)",
        (
            RANKING_ID,
            points + RESULT_POINTS[result],
            player_id,
            player["username"],
            wins + (result == "win"),
        ),
    )
    session.execute(batch)
    return True


def list_leaderboard() -> list[dict]:
    rows = session.execute(
        f"SELECT player_id, username, score, victories FROM {KEYSPACE}.leaderboard WHERE ranking_id = %s",
        [RANKING_ID],
    )
    return [
        {
            "player_id": r.player_id,
            "username": r.username,
            "points": r.score,
            "wins": r.victories,
        }
        for r in rows
    ]
