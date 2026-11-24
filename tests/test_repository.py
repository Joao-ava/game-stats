import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from cassandra.query import BatchType

from game_stats import repository


def _batch(session, call_index: int) -> list[str]:
    batch = session.execute.call_args_list[call_index].args[0]
    return [query for _, query, _ in batch._statements_and_parameters]


def make_player(username: str, email: str = "") -> dict:
    return {
        "player_id": uuid.uuid4(),
        "username": username,
        "email": email,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }


class TestPlayerQueries:
    def test_list_players_keeps_cassandra_order_without_python_sort(self, cassandra_session):
        cassandra_session.execute.return_value = [
            make_row(make_player("bruno")),
            make_row(make_player("Ana")),
            make_row(make_player("carlos")),
        ]

        names = [p["username"] for p in repository.list_players()]

        assert names == ["bruno", "Ana", "carlos"]

    def test_get_player_returns_none_when_missing(self, cassandra_session):
        cassandra_session.execute.return_value.one.return_value = None

        assert repository.get_player(uuid.uuid4()) is None

    def test_get_player_normalizes_null_email(self, cassandra_session):
        player = make_player("Ana")
        player["email"] = None
        cassandra_session.execute.return_value.one.return_value = make_row(player)

        assert repository.get_player(player["player_id"])["email"] == ""

    def test_create_player_inserts_row_with_generated_id(self, cassandra_session):
        repository.create_player("ana", "ana@example.com")

        query, params = cassandra_session.execute.call_args.args
        assert "INSERT INTO game_stats.players" in query
        assert params[1:3] == ("ana", "ana@example.com")
        assert isinstance(params[0], uuid.UUID)
        assert isinstance(params[3], datetime)

    def test_update_player_updates_username_and_email(self, cassandra_session):
        pid = uuid.uuid4()
        cassandra_session.execute.return_value.one.return_value.applied = True

        assert repository.update_player(pid, "ana.m", "ana@example.com") is True

        query, params = cassandra_session.execute.call_args.args
        assert "UPDATE game_stats.players" in query
        assert "IF EXISTS" in query
        assert params == ("ana.m", "ana@example.com", pid)

    def test_update_player_returns_false_when_missing(self, cassandra_session):
        cassandra_session.execute.return_value.one.return_value.applied = False

        assert repository.update_player(uuid.uuid4(), "ana", "") is False

    def test_delete_player_issues_delete(self, cassandra_session):
        pid = uuid.uuid4()
        cassandra_session.execute.return_value = []

        repository.delete_player(pid)

        query, params = cassandra_session.execute.call_args.args
        assert "DELETE FROM game_stats.players" in query
        assert params == [pid]

    def test_delete_player_with_matches_is_rejected(self, cassandra_session):
        pid = uuid.uuid4()
        cassandra_session.execute.return_value = [make_row({"match_date": None, "match_id": uuid.uuid4(), "score": 1, "result": "win"})]

        with pytest.raises(ValueError):
            repository.delete_player(pid)
        queries = [c.args[0] for c in cassandra_session.execute.call_args_list]
        assert not any("DELETE" in q for q in queries)


class TestMatchQueries:
    def test_list_player_matches_keeps_cassandra_order(self, cassandra_session):
        pid, old, new = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        cassandra_session.execute.return_value = [
            make_row({"match_date": datetime(2026, 2, 1).date(), "match_id": new, "score": 2, "result": "win"}),
            make_row({"match_date": datetime(2026, 1, 1).date(), "match_id": old, "score": 1, "result": "loss"}),
        ]

        matches = repository.list_player_matches(pid)

        assert [(m["player_id"], m["match_id"]) for m in matches] == [(pid, new), (pid, old)]
        query, params = cassandra_session.execute.call_args.args
        assert "FROM game_stats.matches_by_player WHERE player_id = %s" in query
        assert params == [pid]

    def test_create_match_writes_single_player_row_with_idempotency_check(self, cassandra_session):
        pid, mid = uuid.uuid4(), uuid.uuid4()
        cassandra_session.execute.return_value.one.return_value.applied = True

        assert repository.create_match(pid, 3, "win", mid) is True

        query, params = cassandra_session.execute.call_args_list[0].args
        assert "matches_by_player" in query
        assert "IF NOT EXISTS" in query
        assert params[0] == pid and params[2] == mid and params[4] == 3
        assert params[7] == "win"

    def test_create_match_is_skipped_when_match_id_already_exists(self, cassandra_session):
        cassandra_session.execute.return_value.one.return_value.applied = False

        assert repository.create_match(uuid.uuid4(), 3, "win", uuid.uuid4()) is False
        assert cassandra_session.execute.call_count == 1

    def test_create_match_updates_leaderboard_for_the_player_only(self, cassandra_session):
        pid = uuid.uuid4()
        applied = MagicMock()
        applied.one.return_value.applied = True
        cassandra_session.execute.side_effect = [
            applied,
            [],
            MagicMock(**{"one.return_value": make_row(make_player("Ana"))}),
            MagicMock(),
        ]

        repository.create_match(pid, 3, "win")

        batch_queries = _batch(cassandra_session, 3)
        assert len(batch_queries) == 1
        assert "INSERT INTO game_stats.leaderboard" in batch_queries[0]

    def test_create_match_loss_does_not_delete_leaderboard_row(self, cassandra_session):
        b = make_player("Bruno")
        applied = MagicMock()
        applied.one.return_value.applied = True
        leaderboard = [make_row({"player_id": b["player_id"], "score": 3, "victories": 1})]
        cassandra_session.execute.side_effect = [
            applied,
            leaderboard,
            MagicMock(**{"one.return_value": make_row(b)}),
            MagicMock(),
        ]

        repository.create_match(b["player_id"], 0, "loss")

        batch_queries = _batch(cassandra_session, 3)
        assert not any("DELETE" in q for q in batch_queries)
        assert sum("INSERT INTO game_stats.leaderboard" in q for q in batch_queries) == 1

    def test_create_match_rejects_negative_score(self, cassandra_session):
        with pytest.raises(ValueError):
            repository.create_match(uuid.uuid4(), -1, "win")
        cassandra_session.execute.assert_not_called()

    def test_create_match_rejects_invalid_result(self, cassandra_session):
        with pytest.raises(ValueError):
            repository.create_match(uuid.uuid4(), 1, "draw_maybe")
        cassandra_session.execute.assert_not_called()


class TestLeaderboardQueries:
    def test_list_leaderboard_reads_rows_in_stored_order(self, cassandra_session):
        ana, bruno = make_player("Ana"), make_player("Bruno")
        cassandra_session.execute.return_value = [
            make_row({"player_id": ana["player_id"], "username": "Ana", "score": 6, "victories": 2}),
            make_row({"player_id": bruno["player_id"], "username": "Bruno", "score": 1, "victories": 0}),
        ]

        leaderboard = repository.list_leaderboard()

        assert [(r["username"], r["points"], r["wins"]) for r in leaderboard] == [
            ("Ana", 6, 2),
            ("Bruno", 1, 0),
        ]
        query, params = cassandra_session.execute.call_args.args
        assert "FROM game_stats.leaderboard WHERE ranking_id = %s" in query
        assert params == [repository.RANKING_ID]

    def test_list_leaderboard_empty_when_no_rows(self, cassandra_session):
        cassandra_session.execute.return_value = []

        assert repository.list_leaderboard() == []
        assert cassandra_session.execute.call_count == 1


class TestSchema:
    def test_create_schema_creates_keyspace_and_tables(self, cassandra_session):
        repository.create_schema()

        statements = [c.args[0] for c in cassandra_session.execute.call_args_list]
        assert len(statements) == 4
        assert "CREATE KEYSPACE IF NOT EXISTS game_stats" in statements[0]
        assert "game_stats.players" in statements[1] and "username text" in statements[1]
        assert "player_id uuid PRIMARY KEY" in statements[1]
        assert "game_stats.matches_by_player" in statements[2]
        assert "PRIMARY KEY ((player_id), match_date, match_id)" in statements[2]
        assert "game_stats.leaderboard" in statements[3]
        assert "PRIMARY KEY ((ranking_id), score, player_id)" in statements[3]
        assert not any("game_stats.matches " in s or "player_stats" in s for s in statements)


def make_row(data: dict):
    class Row:
        pass

    row = Row()
    for key, value in data.items():
        setattr(row, key, value)
    return row
