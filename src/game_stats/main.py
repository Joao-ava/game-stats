import uuid
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from . import repository


app = FastAPI(title="Game Stats")
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


@app.on_event("startup")
def startup():
    """Criar keyspace e tabelas na inicialização."""
    repository.create_schema()


def parse_id(raw: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except ValueError:
        raise HTTPException(status_code=404, detail="Não encontrado")


def player_form_context(player: dict | None, action: str, error: str | None = None) -> dict:
    return {"player": player, "action": action, "error": error}


def match_form_context(error: str | None = None) -> dict:
    return {"players": repository.list_players(), "error": error}


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def index():
    return RedirectResponse("/players", status_code=303)


@app.get("/players", response_class=HTMLResponse)
def players_page(request: Request):
    return templates.TemplateResponse(
        request, "players.html", {"players": repository.list_players()}
    )


@app.get("/players/new", response_class=HTMLResponse)
def new_player_page(request: Request):
    return templates.TemplateResponse(
        request, "player_form.html", player_form_context(None, "/players")
    )


@app.post("/players")
def create_player(request: Request, name: str = Form(...), nickname: str = Form("")):
    name = name.strip()
    if not name:
        return templates.TemplateResponse(
            request,
            "player_form.html",
            player_form_context(None, "/players", "Informe o nome do jogador."),
            status_code=400,
        )
    repository.create_player(name, nickname.strip())
    return RedirectResponse("/players", status_code=303)


@app.get("/players/{player_id}/edit", response_class=HTMLResponse)
def edit_player_page(request: Request, player_id: str):
    pid = parse_id(player_id)
    player = repository.get_player(pid)
    if not player:
        raise HTTPException(status_code=404, detail="Jogador não encontrado")
    return templates.TemplateResponse(
        request,
        "player_form.html",
        player_form_context(player, f"/players/{pid}/edit"),
    )


@app.post("/players/{player_id}/edit")
def update_player(
    request: Request,
    player_id: str,
    name: str = Form(...),
    nickname: str = Form(""),
):
    pid = parse_id(player_id)
    player = repository.get_player(pid)
    if not player:
        raise HTTPException(status_code=404, detail="Jogador não encontrado")
    name = name.strip()
    if not name:
        return templates.TemplateResponse(
            request,
            "player_form.html",
            player_form_context(player, f"/players/{pid}/edit", "Informe o nome do jogador."),
            status_code=400,
        )
    repository.update_player(pid, name, nickname.strip())
    return RedirectResponse("/players", status_code=303)


@app.post("/players/{player_id}/delete")
def delete_player(player_id: str):
    repository.delete_player(parse_id(player_id))
    return RedirectResponse("/players", status_code=303)


@app.get("/matches", response_class=HTMLResponse)
def matches_page(request: Request):
    names = {p["player_id"]: p["name"] for p in repository.list_players()}
    return templates.TemplateResponse(
        request,
        "matches.html",
        {"matches": repository.list_matches(), "names": names},
    )


@app.get("/matches/new", response_class=HTMLResponse)
def new_match_page(request: Request):
    return templates.TemplateResponse(request, "match_form.html", match_form_context())


@app.post("/matches")
def create_match(
    request: Request,
    player_a: str = Form(...),
    player_b: str = Form(...),
    score_a: int = Form(...),
    score_b: int = Form(...),
):
    pa = parse_id(player_a)
    pb = parse_id(player_b)
    error = None
    if pa == pb:
        error = "Selecione dois jogadores diferentes."
    elif score_a < 0 or score_b < 0:
        error = "As pontuações não podem ser negativas."
    elif not repository.get_player(pa) or not repository.get_player(pb):
        error = "Jogador não encontrado."
    if error:
        return templates.TemplateResponse(
            request, "match_form.html", match_form_context(error), status_code=400
        )
    repository.create_match(pa, pb, score_a, score_b)
    return RedirectResponse("/matches", status_code=303)


@app.get("/ranking", response_class=HTMLResponse)
def ranking_page(request: Request):
    return templates.TemplateResponse(
        request, "ranking.html", {"ranking": repository.get_ranking()}
    )
