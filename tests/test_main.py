import uuid


def add_player(repo, username: str, email: str = "") -> uuid.UUID:
    repo.create_player(username, email)
    return next(p["player_id"] for p in repo.players.values() if p["username"] == username)


def test_health_check(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_redirects_to_players(client):
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/players"


def test_players_page_lists_players(client, fake_repo):
    add_player(fake_repo, "Ana", "ana@example.com")

    response = client.get("/players")

    assert response.status_code == 200
    assert "Ana" in response.text
    assert "ana@example.com" in response.text


def test_players_page_empty_message(client):
    response = client.get("/players")

    assert response.status_code == 200
    assert "Nenhum jogador cadastrado." in response.text


def test_new_player_form_renders(client):
    response = client.get("/players/new")

    assert response.status_code == 200
    assert "Novo jogador" in response.text
    assert 'name="username"' in response.text
    assert 'name="email"' in response.text


def test_create_player_redirects_and_stores_stripped_values(client, fake_repo):
    response = client.post(
        "/players", data={"username": "  Ana  ", "email": " ana@example.com "}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/players"
    stored = list(fake_repo.players.values())
    assert len(stored) == 1
    assert stored[0]["username"] == "Ana"
    assert stored[0]["email"] == "ana@example.com"


def test_create_player_without_username_returns_400(client, fake_repo):
    response = client.post("/players", data={"username": "   ", "email": "x"})

    assert response.status_code == 400
    assert "Informe o nome de usuário do jogador." in response.text
    assert fake_repo.players == {}


def test_edit_player_page_renders_existing_player(client, fake_repo):
    pid = add_player(fake_repo, "Ana", "ana@example.com")

    response = client.get(f"/players/{pid}/edit")

    assert response.status_code == 200
    assert "Editar jogador" in response.text
    assert 'value="Ana"' in response.text


def test_edit_player_page_unknown_id_returns_404(client):
    response = client.get(f"/players/{uuid.uuid4()}/edit")

    assert response.status_code == 404


def test_edit_player_page_invalid_id_returns_404(client):
    response = client.get("/players/not-a-uuid/edit")

    assert response.status_code == 404


def test_update_player_changes_values(client, fake_repo):
    pid = add_player(fake_repo, "Ana", "ana@example.com")

    response = client.post(
        f"/players/{pid}/edit",
        data={"username": "Ana Maria", "email": "am@example.com"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert fake_repo.players[pid]["username"] == "Ana Maria"
    assert fake_repo.players[pid]["email"] == "am@example.com"


def test_update_player_without_username_returns_400_and_keeps_data(client, fake_repo):
    pid = add_player(fake_repo, "Ana", "ana@example.com")

    response = client.post(f"/players/{pid}/edit", data={"username": " ", "email": "x"})

    assert response.status_code == 400
    assert fake_repo.players[pid]["username"] == "Ana"


def test_update_unknown_player_returns_404(client):
    response = client.post(
        f"/players/{uuid.uuid4()}/edit", data={"username": "Ana", "email": ""}
    )

    assert response.status_code == 404


def test_delete_player_removes_it(client, fake_repo):
    pid = add_player(fake_repo, "Ana")

    response = client.post(f"/players/{pid}/delete", follow_redirects=False)

    assert response.status_code == 303
    assert pid not in fake_repo.players


def test_delete_player_with_matches_returns_409(client, fake_repo):
    ana = add_player(fake_repo, "Ana")
    bruno = add_player(fake_repo, "Bruno")
    fake_repo.create_match(ana, 1, "win")

    response = client.post(f"/players/{ana}/delete", follow_redirects=False)

    assert response.status_code == 409
    assert ana in fake_repo.players


def test_delete_player_invalid_id_returns_404(client):
    response = client.post("/players/invalid/delete", follow_redirects=False)

    assert response.status_code == 404


def test_player_matches_page_shows_only_that_player(client, fake_repo):
    a = add_player(fake_repo, "Ana")
    b = add_player(fake_repo, "Bruno")
    fake_repo.create_match(a, 3, "win")
    fake_repo.create_match(b, 1, "loss")

    response = client.get(f"/players/{a}/matches")

    assert response.status_code == 200
    assert "Partidas de Ana" in response.text
    assert "win" in response.text
    assert "loss" not in response.text


def test_player_matches_page_empty_message(client, fake_repo):
    a = add_player(fake_repo, "Ana")

    response = client.get(f"/players/{a}/matches")

    assert response.status_code == 200
    assert "Nenhuma partida registrada." in response.text


def test_player_matches_page_unknown_player_returns_404(client):
    response = client.get(f"/players/{uuid.uuid4()}/matches")

    assert response.status_code == 404


def test_matches_list_route_is_removed(client):
    response = client.get("/matches")

    assert response.status_code == 405


def test_new_match_page_requires_a_player(client, fake_repo):
    response = client.get("/matches/new")

    assert response.status_code == 200
    assert "Cadastre pelo menos um jogador" in response.text


def test_new_match_page_lists_players(client, fake_repo):
    add_player(fake_repo, "Ana")
    add_player(fake_repo, "Bruno")

    response = client.get("/matches/new")

    assert response.status_code == 200
    assert "<select" in response.text
    assert "Ana" in response.text


def test_create_match_registers_one_player_result(client, fake_repo):
    a = add_player(fake_repo, "Ana")

    response = client.post(
        "/matches",
        data={
            "player_id": str(a),
            "score": 2,
            "result": "win",
            "match_date": "2026-11-24",
            "game_mode": "ranked",
            "kills": 1,
            "deaths": 0,
            "match_id": str(uuid.uuid4()),
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == f"/players/{a}/matches"
    assert len(fake_repo.matches) == 1
    assert fake_repo.matches[0]["player_id"] == a
    assert fake_repo.matches[0]["score"] == 2
    assert fake_repo.matches[0]["result"] == "win"


def test_create_match_resubmitted_with_same_id_is_not_duplicated(client, fake_repo):
    a = add_player(fake_repo, "Ana")
    data = {
        "player_id": str(a),
        "score": 2,
        "result": "win",
        "match_date": "2026-11-24",
        "game_mode": "ranked",
        "kills": 1,
        "deaths": 0,
        "match_id": str(uuid.uuid4()),
    }

    first = client.post("/matches", data=data, follow_redirects=False)
    second = client.post("/matches", data=data, follow_redirects=False)

    assert first.status_code == 303
    assert second.status_code == 303
    assert len(fake_repo.matches) == 1


def test_new_match_page_includes_match_id(client, fake_repo):
    add_player(fake_repo, "Ana")
    add_player(fake_repo, "Bruno")

    response = client.get("/matches/new")

    assert 'name="match_id"' in response.text




def test_create_match_negative_score_returns_400(client, fake_repo):
    a = add_player(fake_repo, "Ana")

    response = client.post(
        "/matches",
        data={
            "player_id": str(a),
            "score": -1,
            "result": "win",
            "match_date": "2026-11-24",
            "game_mode": "ranked",
            "kills": 1,
            "deaths": 0,
            "match_id": str(uuid.uuid4()),
        },
    )

    assert response.status_code == 400
    assert "As pontuações não podem ser negativas." in response.text
    assert fake_repo.matches == []


def test_create_match_unknown_player_returns_400(client, fake_repo):
    response = client.post(
        "/matches",
        data={
            "player_id": str(uuid.uuid4()),
            "score": 1,
            "result": "win",
            "match_date": "2026-11-24",
            "game_mode": "ranked",
            "kills": 1,
            "deaths": 0,
            "match_id": str(uuid.uuid4()),
        },
    )

    assert response.status_code == 400
    assert "Jogador não encontrado." in response.text


def test_create_match_non_numeric_score_returns_422(client, fake_repo):
    a = add_player(fake_repo, "Ana")

    response = client.post(
        "/matches",
        data={
            "player_id": str(a),
            "score": "x",
            "result": "win",
            "match_date": "2026-11-24",
            "game_mode": "ranked",
            "kills": 1,
            "deaths": 0,
            "match_id": str(uuid.uuid4()),
        },
    )

    assert response.status_code == 422


def test_leaderboard_page_shows_players(client, fake_repo):
    a = add_player(fake_repo, "Ana")
    b = add_player(fake_repo, "Bruno")
    fake_repo.create_match(a, 1, "win")
    fake_repo.create_match(b, 0, "loss")

    response = client.get("/leaderboard")

    assert response.status_code == 200
    assert "Ana" in response.text
    assert "Bruno" in response.text


def test_ranking_route_is_removed(client):
    response = client.get("/ranking")

    assert response.status_code == 404


def test_pages_include_theme_toggle(client):
    response = client.get("/leaderboard")

    assert response.status_code == 200
    assert 'id="theme-toggle"' in response.text
    assert "darkMode: 'class'" in response.text
