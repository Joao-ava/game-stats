import uuid
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path

from fastapi import FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from . import repository


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Criar keyspace e tabelas na inicialização."""
    repository.create_schema()
    yield


app = FastAPI(title="Game Stats", lifespan=lifespan)
templates = Jinja2Templates(directory=Path(__file__).parent / "templates")


def parse_id(raw: str) -> uuid.UUID:
    try:
        return uuid.UUID(raw)
    except ValueError:
        raise HTTPException(status_code=404, detail="Não encontrado")


def player_form_context(player: dict | None, action: str, error: str | None = None) -> dict:
    return {"player": player, "action": action, "error": error}


def match_form_context(match_id: uuid.UUID, error: str | None = None) -> dict:
    return {
        "players": repository.list_players(),
        "match_id": match_id,
        "error": error,
        "today": date.today().isoformat(),
    }


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
def create_player(request: Request, username: str = Form(...), email: str = Form("")):
    username = username.strip()
    if not username:
        return templates.TemplateResponse(
            request,
            "player_form.html",
            player_form_context(None, "/players", "Informe o nome de usuário do jogador."),
            status_code=400,
        )
    repository.create_player(username, email.strip())
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
    username: str = Form(...),
    email: str = Form(""),
):
    pid = parse_id(player_id)
    player = repository.get_player(pid)
    if not player:
        raise HTTPException(status_code=404, detail="Jogador não encontrado")
    username = username.strip()
    if not username:
        return templates.TemplateResponse(
            request,
            "player_form.html",
            player_form_context(player, f"/players/{pid}/edit", "Informe o nome de usuário do jogador."),
            status_code=400,
        )
    repository.update_player(pid, username, email.strip())
    return RedirectResponse("/players", status_code=303)


@app.post("/players/{player_id}/delete")
def delete_player(player_id: str):
    try:
        repository.delete_player(parse_id(player_id))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return RedirectResponse("/players", status_code=303)


@app.get("/players/{player_id}/matches", response_class=HTMLResponse)
def player_matches_page(request: Request, player_id: str):
    pid = parse_id(player_id)
    player = repository.get_player(pid)
    if not player:
        raise HTTPException(status_code=404, detail="Jogador não encontrado")
    return templates.TemplateResponse(
        request,
        "matches.html",
        {"player": player, "matches": repository.list_player_matches(pid)},
    )


@app.get("/matches/new", response_class=HTMLResponse)
def new_match_page(request: Request):
    return templates.TemplateResponse(
        request, "match_form.html", match_form_context(uuid.uuid4())
    )


@app.post("/matches")
def create_match(
    request: Request,
    player_id: str = Form(...),
    match_date: date = Form(...),
    game_mode: str = Form(...),
    score: int = Form(...),
    kills: int = Form(...),
    deaths: int = Form(...),
    result: str = Form(...),
    match_id: str = Form(...),
):
    mid = parse_id(match_id)
    pid = parse_id(player_id)
    game_mode = game_mode.strip()
    error = None
    if not game_mode:
        error = "Informe o modo de jogo."
    elif score < 0:
        error = "As pontuações não podem ser negativas."
    elif kills < 0 or deaths < 0:
        error = "Abates e mortes não podem ser negativos."
    elif result not in ("win", "draw", "loss"):
        error = "Selecione um resultado válido."
    elif not repository.get_player(pid):
        error = "Jogador não encontrado."
    if error:
        return templates.TemplateResponse(
            request, "match_form.html", match_form_context(mid, error), status_code=400
        )
    repository.create_match(
        pid,
        score,
        result,
        mid,
        match_date=match_date,
        game_mode=game_mode,
        kills=kills,
        deaths=deaths,
    )
    return RedirectResponse(f"/players/{pid}/matches", status_code=303)


@app.get("/leaderboard", response_class=HTMLResponse)
def leaderboard_page(request: Request):
    return templates.TemplateResponse(
        request, "leaderboard.html", {"leaderboard": repository.list_leaderboard()}
    )
