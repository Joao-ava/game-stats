import random
import re
import uuid

from locust import HttpUser, between, task

PLAYER_ID_RE = re.compile(r"/players/([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/edit")


class GameStatsUser(HttpUser):
    wait_time = between(0.5, 2)

    def on_start(self):
        self.player_ids: list[str] = []
        for _ in range(2):
            self.create_player()
        self.refresh_players()

    def create_player(self):
        self.client.post(
            "/players",
            data={"name": f"Jogador {uuid.uuid4().hex[:8]}", "nickname": "load"},
            name="/players [POST]",
        )

    def refresh_players(self):
        response = self.client.get("/players", name="/players [GET]")
        if response.ok:
            self.player_ids = PLAYER_ID_RE.findall(response.text)

    @task(3)
    def list_players(self):
        self.refresh_players()

    @task(2)
    def view_ranking(self):
        self.client.get("/ranking", name="/ranking")

    @task(2)
    def list_matches(self):
        self.client.get("/matches", name="/matches [GET]")

    @task(3)
    def register_match(self):
        if len(self.player_ids) < 2:
            self.refresh_players()
            return
        a, b = random.sample(self.player_ids, 2)
        self.client.post(
            "/matches",
            data={
                "player_a": a,
                "player_b": b,
                "score_a": random.randint(0, 5),
                "score_b": random.randint(0, 5),
            },
            name="/matches [POST]",
        )

    @task(1)
    def create_player_task(self):
        self.create_player()
        self.refresh_players()

    @task(1)
    def health(self):
        self.client.get("/health", name="/health")
