import uuid


def add_player(repo, name: str, nickname: str = "") -> uuid.UUID:
    repo.create_player(name, nickname)
    return next(p["player_id"] for p in repo.players.values() if p["name"] == name)


def test_health_check(client):
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_redirects_to_players(client):
    response = client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/players"


def test_players_page_lists_players(client, fake_repo):
    add_player(fake_repo, "Ana", "ana")

    response = client.get("/players")

    assert response.status_code == 200
    assert "Ana" in response.text
    assert "ana" in response.text


def test_players_page_empty_message(client):
    response = client.get("/players")

    assert response.status_code == 200
    assert "Nenhum jogador cadastrado." in response.text


def test_new_player_form_renders(client):
    response = client.get("/players/new")

    assert response.status_code == 200
    assert "Novo jogador" in response.text


def test_create_player_redirects_and_stores_stripped_values(client, fake_repo):
    response = client.post(
        "/players", data={"name": "  Ana  ", "nickname": " ana "}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/players"
    stored = list(fake_repo.players.values())
    assert len(stored) == 1
    assert stored[0]["name"] == "Ana"
    assert stored[0]["nickname"] == "ana"


def test_create_player_without_name_returns_400(client, fake_repo):
    response = client.post("/players", data={"name": "   ", "nickname": "x"})

    assert response.status_code == 400
    assert "Informe o nome do jogador." in response.text
    assert fake_repo.players == {}


def test_edit_player_page_renders_existing_player(client, fake_repo):
    pid = add_player(fake_repo, "Ana", "ana")

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
    pid = add_player(fake_repo, "Ana", "ana")

    response = client.post(
        f"/players/{pid}/edit",
        data={"name": "Ana Maria", "nickname": "am"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert fake_repo.players[pid]["name"] == "Ana Maria"
    assert fake_repo.players[pid]["nickname"] == "am"


def test_update_player_without_name_returns_400_and_keeps_data(client, fake_repo):
    pid = add_player(fake_repo, "Ana", "ana")

    response = client.post(f"/players/{pid}/edit", data={"name": " ", "nickname": "x"})

    assert response.status_code == 400
    assert fake_repo.players[pid]["name"] == "Ana"


def test_update_unknown_player_returns_404(client):
    response = client.post(
        f"/players/{uuid.uuid4()}/edit", data={"name": "Ana", "nickname": ""}
    )

    assert response.status_code == 404


def test_delete_player_removes_it(client, fake_repo):
    pid = add_player(fake_repo, "Ana")

    response = client.post(f"/players/{pid}/delete", follow_redirects=False)

    assert response.status_code == 303
    assert pid not in fake_repo.players


def test_delete_player_invalid_id_returns_404(client):
    response = client.post("/players/invalid/delete", follow_redirects=False)

    assert response.status_code == 404


def test_matches_page_shows_names_and_scores(client, fake_repo):
    a = add_player(fake_repo, "Ana")
    b = add_player(fake_repo, "Bruno")
    fake_repo.create_match(a, b, 3, 1)

    response = client.get("/matches")

    assert response.status_code == 200
    assert "Ana" in response.text
    assert "Bruno" in response.text
    assert "3 x 1" in response.text


def test_matches_page_empty_message(client):
    response = client.get("/matches")

    assert response.status_code == 200
    assert "Nenhuma partida registrada." in response.text


def test_new_match_page_requires_two_players(client, fake_repo):
    add_player(fake_repo, "Ana")

    response = client.get("/matches/new")

    assert response.status_code == 200
    assert "Cadastre pelo menos dois jogadores" in response.text


def test_new_match_page_lists_players(client, fake_repo):
    add_player(fake_repo, "Ana")
    add_player(fake_repo, "Bruno")

    response = client.get("/matches/new")

    assert response.status_code == 200
    assert "<select" in response.text
    assert "Ana" in response.text


def test_create_match_registers_result(client, fake_repo):
    a = add_player(fake_repo, "Ana")
    b = add_player(fake_repo, "Bruno")

    response = client.post(
        "/matches",
        data={"player_a": str(a), "player_b": str(b), "score_a": 2, "score_b": 0},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/matches"
    assert len(fake_repo.matches) == 1
    assert fake_repo.matches[0]["score_a"] == 2


def test_create_match_same_player_returns_400(client, fake_repo):
    a = add_player(fake_repo, "Ana")

    response = client.post(
        "/matches",
        data={"player_a": str(a), "player_b": str(a), "score_a": 1, "score_b": 0},
    )

    assert response.status_code == 400
    assert "Selecione dois jogadores diferentes." in response.text
    assert fake_repo.matches == []


def test_create_match_negative_score_returns_400(client, fake_repo):
    a = add_player(fake_repo, "Ana")
    b = add_player(fake_repo, "Bruno")

    response = client.post(
        "/matches",
        data={"player_a": str(a), "player_b": str(b), "score_a": -1, "score_b": 0},
    )

    assert response.status_code == 400
    assert "As pontuações não podem ser negativas." in response.text
    assert fake_repo.matches == []


def test_create_match_unknown_player_returns_400(client, fake_repo):
    a = add_player(fake_repo, "Ana")

    response = client.post(
        "/matches",
        data={"player_a": str(a), "player_b": str(uuid.uuid4()), "score_a": 1, "score_b": 0},
    )

    assert response.status_code == 400
    assert "Jogador não encontrado." in response.text


def test_create_match_non_numeric_score_returns_422(client, fake_repo):
    a = add_player(fake_repo, "Ana")
    b = add_player(fake_repo, "Bruno")

    response = client.post(
        "/matches",
        data={"player_a": str(a), "player_b": str(b), "score_a": "x", "score_b": 0},
    )

    assert response.status_code == 422


def test_ranking_page_shows_points(client, fake_repo):
    a = add_player(fake_repo, "Ana")
    b = add_player(fake_repo, "Bruno")
    fake_repo.create_match(a, b, 1, 0)

    response = client.get("/ranking")

    assert response.status_code == 200
    assert "Ana" in response.text
    assert "Bruno" in response.text


def test_pages_include_theme_toggle(client):
    response = client.get("/ranking")

    assert response.status_code == 200
    assert 'id="theme-toggle"' in response.text
    assert "darkMode: 'class'" in response.text
