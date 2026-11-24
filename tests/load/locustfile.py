import random
import re
import uuid
from datetime import date

from faker import Faker
from locust import HttpUser, between, task

fake = Faker("pt_BR")

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
            data={
                "username": f"{fake.user_name()}_{uuid.uuid4().hex[:6]}",
                "email": fake.email(),
            },
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
    def view_leaderboard(self):
        self.client.get("/leaderboard", name="/leaderboard")

    @task(2)
    def list_matches(self):
        if not self.player_ids:
            self.refresh_players()
            return
        pid = random.choice(self.player_ids)
        self.client.get(f"/players/{pid}/matches", name="/players/[id]/matches [GET]")

    @task(3)
    def register_match(self):
        if not self.player_ids:
            self.refresh_players()
            return
        self.client.post(
            "/matches",
            data={
                "player_id": random.choice(self.player_ids),
                "score": random.randint(0, 5),
                "result": random.choice(["win", "draw", "loss"]),
                "match_date": date.today().isoformat(),
                "game_mode": "ranked",
                "kills": random.randint(0, 10),
                "deaths": random.randint(0, 10),
                "match_id": str(uuid.uuid4()),
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
