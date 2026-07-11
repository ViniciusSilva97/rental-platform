# Rental Platform

Plataforma web para gestão de aluguel de ferramentas, construída como um monólito modular
em Django. A primeira versão inclui organizações, usuários, categorias, modelos de
ferramentas e unidades físicas individualizadas.

## Requisitos

- Python 3.12 a 3.14
- `uv`
- Docker e Docker Compose, para executar com PostgreSQL

## Execução rápida sem Docker

No PowerShell:

```powershell
Copy-Item .env.example .env
uv sync --all-groups
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

No Linux ou macOS:

```bash
cp .env.example .env
uv sync --all-groups
uv run python manage.py migrate
uv run python manage.py createsuperuser
uv run python manage.py runserver
```

Sem `DATABASE_URL`, o ambiente local usa SQLite. Essa opção serve para desenvolvimento
rápido; o ambiente Docker e a produção usam PostgreSQL.

## Execução com Docker

```bash
cp .env.example .env
docker compose up --build
docker compose exec web uv run python manage.py migrate
docker compose exec web uv run python manage.py createsuperuser
```

A aplicação estará em `http://localhost:8000` e o painel administrativo em
`http://localhost:8000/admin/`.

## Qualidade

```bash
uv run ruff check .
uv run pytest
```

## Próximo incremento

O próximo módulo será o fluxo de clientes, reservas e disponibilidade por período.
