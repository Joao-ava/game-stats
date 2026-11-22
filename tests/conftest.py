import importlib
import sys
import types
import uuid
from unittest.mock import MagicMock

import pytest

fake_database = types.ModuleType("game_stats.database")
fake_database.session = MagicMock(name="cassandra_session")
sys.modules["game_stats.database"] = fake_database


class FakeRepository:
    """Repositório em memória com a mesma interface de game_stats.repository."""

    def __init__(self) -> None:
        self.players: dict[uuid.UUID, dict] = {}
        self.matches: list[dict] = []

    def create_schema(self) -> None:
        pass

    def list_players(self) -> list[dict]:
        return sorted(self.players.values(), key=lambda p: p["name"].lower())

    def get_player(self, player_id: uuid.UUID) -> dict | None:
        return self.players.get(player_id)

    def create_player(self, name: str, nickname: str) -> None:
        pid = uuid.uuid4()
        self.players[pid] = {
            "player_id": pid,
            "name": name,
            "nickname": nickname,
            "created_at": None,
        }

    def update_player(self, player_id: uuid.UUID, name: str, nickname: str) -> None:
        self.players[player_id].update(name=name, nickname=nickname)

    def delete_player(self, player_id: uuid.UUID) -> None:
        self.players.pop(player_id, None)

    def list_matches(self) -> list[dict]:
        return list(self.matches)

    def create_match(self, player_a, player_b, score_a: int, score_b: int) -> None:
        self.matches.append(
            {
                "match_id": uuid.uuid4(),
                "played_at": None,
                "player_a": player_a,
                "player_b": player_b,
                "score_a": score_a,
                "score_b": score_b,
            }
        )

    def get_ranking(self) -> list[dict]:
        from game_stats import repository

        return repository.compute_ranking(self.list_players(), self.list_matches())


@pytest.fixture
def fake_repo(monkeypatch):
    main_module = importlib.import_module("game_stats.main")

    repo = FakeRepository()
    monkeypatch.setattr(main_module, "repository", repo)
    return repo


@pytest.fixture
def client(fake_repo):
    from fastapi.testclient import TestClient

    from game_stats.main import app

    return TestClient(app)


@pytest.fixture
def cassandra_session(monkeypatch):
    from game_stats import repository

    session = MagicMock(name="session")
    monkeypatch.setattr(repository, "session", session)
    return session
