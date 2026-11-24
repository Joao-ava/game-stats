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
        return list(self.players.values())

    def get_player(self, player_id: uuid.UUID) -> dict | None:
        return self.players.get(player_id)

    def create_player(self, username: str, email: str) -> None:
        pid = uuid.uuid4()
        self.players[pid] = {
            "player_id": pid,
            "username": username,
            "email": email,
            "created_at": None,
        }

    def update_player(self, player_id: uuid.UUID, username: str, email: str) -> bool:
        if player_id not in self.players:
            return False
        self.players[player_id].update(username=username, email=email)
        return True

    def delete_player(self, player_id: uuid.UUID) -> None:
        if any(m["player_id"] == player_id for m in self.matches):
            raise ValueError("Jogador possui partidas registradas e não pode ser excluído.")
        self.players.pop(player_id, None)

    def list_player_matches(self, player_id: uuid.UUID) -> list[dict]:
        return [m for m in self.matches if m["player_id"] == player_id]

    def create_match(
        self,
        player_id: uuid.UUID,
        score: int,
        result: str,
        match_id: uuid.UUID | None = None,
        match_date=None,
        game_mode: str = "",
        kills: int = 0,
        deaths: int = 0,
    ) -> bool:
        match_id = match_id or uuid.uuid4()
        if any(m["match_id"] == match_id for m in self.matches):
            return False
        self.matches.append(
            {
                "player_id": player_id,
                "match_date": match_date,
                "game_mode": game_mode,
                "kills": kills,
                "deaths": deaths,
                "match_id": match_id,
                "score": score,
                "result": result,
            }
        )
        return True

    def list_leaderboard(self) -> list[dict]:
        from game_stats import repository

        entries = []
        for pid, player in self.players.items():
            results = [m["result"] for m in self.matches if m["player_id"] == pid]
            entries.append(
                {
                    "player_id": pid,
                    "username": player["username"],
                    "points": sum(repository.RESULT_POINTS[r] for r in results),
                    "wins": results.count("win"),
                }
            )
        return sorted(entries, key=lambda e: -e["points"])


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
