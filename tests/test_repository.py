import uuid
from datetime import datetime, timezone

from game_stats import repository


def make_player(name: str, nickname: str = "") -> dict:
    return {
        "player_id": uuid.uuid4(),
        "name": name,
        "nickname": nickname,
        "created_at": datetime(2026, 1, 1, tzinfo=timezone.utc),
    }


def make_match(player_a, player_b, score_a: int, score_b: int, played_at=None) -> dict:
    return {
        "match_id": uuid.uuid4(),
        "played_at": played_at or datetime(2026, 1, 1, tzinfo=timezone.utc),
        "player_a": player_a,
        "player_b": player_b,
        "score_a": score_a,
        "score_b": score_b,
    }


class TestComputeRanking:
    def test_empty_inputs_return_empty_ranking(self):
        assert repository.compute_ranking([], []) == []

    def test_players_without_matches_have_zero_stats(self):
        ana = make_player("Ana")

        ranking = repository.compute_ranking([ana], [])

        assert ranking == [
            {
                "player_id": ana["player_id"],
                "name": "Ana",
                "nickname": "",
                "played": 0,
                "wins": 0,
                "draws": 0,
                "losses": 0,
                "points": 0,
            }
        ]

    def test_win_gives_three_points_and_loss_gives_none(self):
        ana, bruno = make_player("Ana"), make_player("Bruno")
        matches = [make_match(ana["player_id"], bruno["player_id"], 2, 1)]

        ranking = {r["name"]: r for r in repository.compute_ranking([ana, bruno], matches)}

        assert ranking["Ana"]["wins"] == 1
        assert ranking["Ana"]["points"] == repository.POINTS_WIN == 3
        assert ranking["Bruno"]["losses"] == 1
        assert ranking["Bruno"]["points"] == 0

    def test_draw_gives_one_point_to_each_player(self):
        ana, bruno = make_player("Ana"), make_player("Bruno")
        matches = [make_match(ana["player_id"], bruno["player_id"], 0, 0)]

        ranking = {r["name"]: r for r in repository.compute_ranking([ana, bruno], matches)}

        assert ranking["Ana"]["draws"] == 1
        assert ranking["Ana"]["points"] == repository.POINTS_DRAW == 1
        assert ranking["Bruno"]["draws"] == 1
        assert ranking["Bruno"]["points"] == 1

    def test_second_player_wins_when_score_b_is_higher(self):
        ana, bruno = make_player("Ana"), make_player("Bruno")
        matches = [make_match(ana["player_id"], bruno["player_id"], 1, 4)]

        ranking = {r["name"]: r for r in repository.compute_ranking([ana, bruno], matches)}

        assert ranking["Bruno"]["wins"] == 1
        assert ranking["Bruno"]["points"] == 3
        assert ranking["Ana"]["losses"] == 1
        assert ranking["Ana"]["points"] == 0

    def test_accumulates_played_wins_draws_losses_and_points(self):
        ana, bruno, carlos = make_player("Ana"), make_player("Bruno"), make_player("Carlos")
        a, b, c = ana["player_id"], bruno["player_id"], carlos["player_id"]
        matches = [
            make_match(a, b, 2, 1),  # Ana vence
            make_match(b, c, 0, 0),  # empate
            make_match(c, a, 3, 0),  # Carlos vence
        ]

        ranking = {
            r["name"]: r
            for r in repository.compute_ranking([ana, bruno, carlos], matches)
        }

        assert ranking["Ana"]["played"] == 2
        assert ranking["Ana"]["wins"] == 1
        assert ranking["Ana"]["draws"] == 0
        assert ranking["Ana"]["losses"] == 1
        assert ranking["Ana"]["points"] == 3
        assert ranking["Bruno"]["played"] == 2
        assert ranking["Bruno"]["draws"] == 1
        assert ranking["Bruno"]["losses"] == 1
        assert ranking["Bruno"]["points"] == 1
        assert ranking["Carlos"]["played"] == 2
        assert ranking["Carlos"]["wins"] == 1
        assert ranking["Carlos"]["draws"] == 1
        assert ranking["Carlos"]["losses"] == 0
        assert ranking["Carlos"]["points"] == 4

    def test_matches_with_unknown_players_are_ignored(self):
        ana = make_player("Ana")
        ghost = uuid.uuid4()
        matches = [make_match(ana["player_id"], ghost, 5, 0)]

        ranking = repository.compute_ranking([ana], matches)

        assert len(ranking) == 1
        assert ranking[0]["played"] == 1
        assert ranking[0]["points"] == 3

    def test_sorted_by_points_then_wins_then_name(self):
        ana, bruno, carlos, diana = (
            make_player("Ana"),
            make_player("Bruno"),
            make_player("carlos"),
            make_player("Diana"),
        )
        a, b, c, d = (p["player_id"] for p in (ana, bruno, carlos, diana))
        matches = [
            make_match(a, b, 1, 0),  # Ana 3 pts, 1 vitória
            make_match(c, d, 1, 0),  # Carlos 3 pts, 1 vitória
            make_match(b, d, 0, 0),  # Bruno e Diana 1 pt cada
        ]

        names = [r["name"] for r in repository.compute_ranking([diana, carlos, bruno, ana], matches)]

        assert names == ["Ana", "carlos", "Bruno", "Diana"]

    def test_tie_on_points_is_broken_by_wins(self):
        ana, zeca, carlos = make_player("Ana"), make_player("Zeca"), make_player("Carlos")
        a, z, c = ana["player_id"], zeca["player_id"], carlos["player_id"]
        matches = [
            make_match(z, c, 1, 0),  # Zeca 3 pts (1 vitória)
            make_match(a, c, 0, 0),  # Ana 1 pt
            make_match(a, c, 0, 0),  # Ana 2 pts
            make_match(a, c, 0, 0),  # Ana 3 pts (0 vitórias)
        ]
        ranking = repository.compute_ranking([ana, zeca, carlos], matches)

        assert [r["name"] for r in ranking][:2] == ["Zeca", "Ana"]


class TestPlayerQueries:
    def test_list_players_sorted_case_insensitive_by_name(self, cassandra_session):
        cassandra_session.execute.return_value = [
            make_row(make_player("bruno")),
            make_row(make_player("Ana")),
            make_row(make_player("carlos")),
        ]

        names = [p["name"] for p in repository.list_players()]

        assert names == ["Ana", "bruno", "carlos"]

    def test_get_player_returns_none_when_missing(self, cassandra_session):
        cassandra_session.execute.return_value.one.return_value = None

        assert repository.get_player(uuid.uuid4()) is None

    def test_get_player_normalizes_null_nickname(self, cassandra_session):
        player = make_player("Ana")
        player["nickname"] = None
        cassandra_session.execute.return_value.one.return_value = make_row(player)

        assert repository.get_player(player["player_id"])["nickname"] == ""

    def test_create_player_inserts_row_with_generated_id(self, cassandra_session):
        repository.create_player("Ana", "ana")

        query, params = cassandra_session.execute.call_args.args
        assert "INSERT INTO game_stats.players" in query
        assert params[1:3] == ("Ana", "ana")
        assert isinstance(params[0], uuid.UUID)

    def test_update_player_updates_name_and_nickname(self, cassandra_session):
        pid = uuid.uuid4()

        repository.update_player(pid, "Ana Maria", "ana")

        query, params = cassandra_session.execute.call_args.args
        assert "UPDATE game_stats.players" in query
        assert params == ("Ana Maria", "ana", pid)

    def test_delete_player_issues_delete(self, cassandra_session):
        pid = uuid.uuid4()

        repository.delete_player(pid)

        query, params = cassandra_session.execute.call_args.args
        assert "DELETE FROM game_stats.players" in query
        assert params == [pid]


class TestMatchQueries:
    def test_list_matches_sorted_most_recent_first(self, cassandra_session):
        old = make_match(uuid.uuid4(), uuid.uuid4(), 1, 0, datetime(2026, 1, 1, tzinfo=timezone.utc))
        new = make_match(uuid.uuid4(), uuid.uuid4(), 1, 0, datetime(2026, 2, 1, tzinfo=timezone.utc))
        cassandra_session.execute.return_value = [make_row(old), make_row(new)]

        matches = repository.list_matches()

        assert [m["match_id"] for m in matches] == [new["match_id"], old["match_id"]]

    def test_create_match_inserts_scores_and_players(self, cassandra_session):
        a, b = uuid.uuid4(), uuid.uuid4()

        repository.create_match(a, b, 3, 2)

        query, params = cassandra_session.execute.call_args.args
        assert "INSERT INTO game_stats.matches" in query
        assert params[2:] == (a, b, 3, 2)
        assert isinstance(params[0], uuid.UUID)
        assert isinstance(params[1], datetime)


class TestSchema:
    def test_create_schema_creates_keyspace_and_both_tables(self, cassandra_session):
        repository.create_schema()

        statements = [c.args[0] for c in cassandra_session.execute.call_args_list]
        assert len(statements) == 3
        assert "CREATE KEYSPACE IF NOT EXISTS game_stats" in statements[0]
        assert "game_stats.players" in statements[1]
        assert "game_stats.matches" in statements[2]


def make_row(data: dict):
    class Row:
        pass

    row = Row()
    for key, value in data.items():
        setattr(row, key, value)
    return row
