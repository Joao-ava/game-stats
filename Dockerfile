FROM ghcr.io/astral-sh/uv:python3.12-alpine

WORKDIR /app

# Dependências de build para o cassandra-driver (compila extensões C com gcc)
RUN apk add --no-cache build-base libev-dev linux-headers

# Copiar apenas o pyproject para instalar dependências primeiro (cache do Docker)
COPY pyproject.toml ./
# COPY uv.lock ./
COPY README.md ./

COPY src/game_stats/__init__.py ./src/game_stats/__init__.py

# Instalar as dependências do projeto
RUN uv sync

# Expõe os executáveis do venv criado pelo uv sync (ex.: uvicorn) no PATH
ENV PATH="/app/.venv/bin:$PATH"

# Copiar o restante do código
COPY src/ ./src/

EXPOSE 8000

CMD ["uvicorn", "game_stats.main:app", "--host", "0.0.0.0", "--port", "8000"]
