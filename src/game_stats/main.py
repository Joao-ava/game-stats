from fastapi import FastAPI

from .database import session


app = FastAPI(title="Game Stats API")


@app.on_event("startup")
def startup():
    """Criar keyspace e tabela na inicialização."""
    session.execute("""
        CREATE KEYSPACE IF NOT EXISTS game_stats
        WITH replication = {'class': 'SimpleStrategy', 'replication_factor': 1}
    """)
    # TODO tabelas do sistema


@app.get("/health")
def health_check():
    return {"status": "ok"}

