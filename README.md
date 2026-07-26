# Rental Platform

Base técnica de uma plataforma para gestão de aluguel de ferramentas. O projeto usa
Python e Django em um monólito modular, com PostgreSQL nos ambientes compartilhados e
SQLite como alternativa de baixo atrito para desenvolvimento local.

A versão `0.2.2` cobre:

- usuários, organizações e vínculos de acesso;
- matriz e filiais com CNPJ numérico ou alfanumérico;
- categorias, modelos comerciais e unidades físicas de ferramentas;
- vínculo obrigatório de cada unidade ao estabelecimento responsável;
- clientes pessoa física ou jurídica, com CPF ou CNPJ;
- múltiplos endereços brasileiros por cliente;
- políticas versionadas de preço por hora, dia e mês;
- mês fixo ou calendário e cobrança de frações arredondada ou proporcional;
- perfil patrimonial opcional por unidade física;
- aquisição, entrada em operação, custo, valor residual e vida útil;
- painel administrativo, verificações de saúde e configuração por ambiente;
- testes automatizados e integração contínua com PostgreSQL.

## Requisitos

- Python 3.12 a 3.14;
- [uv](https://docs.astral.sh/uv/);
- Docker e Docker Compose, se a execução for conteinerizada.

## Execução local

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

Sem `DATABASE_URL`, o ambiente local usa `db.sqlite3`. Essa opção é destinada ao
aprendizado e ao desenvolvimento rápido; Docker, CI e produção usam PostgreSQL.

## Execução com Docker

No PowerShell:

```powershell
Copy-Item .env.docker.example .env.docker
docker compose up --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

No Linux ou macOS:

```bash
cp .env.docker.example .env.docker
docker compose up --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

A aplicação ficará em <http://localhost:8000> e o painel administrativo em
<http://localhost:8000/admin/>.

## Verificações

```bash
uv run ruff check .
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py check
uv run pytest
```

Os endpoints operacionais são:

- `GET /health/`: alias mantido por compatibilidade;
- `GET /health/live/`: confirma que o processo web responde;
- `GET /health/ready/`: confirma que a aplicação consegue consultar o banco.

## Configurações Django

| Ambiente | Módulo | Banco |
|---|---|---|
| Desenvolvimento | `config.settings.development` | SQLite ou `DATABASE_URL` |
| Testes | `config.settings.test` | SQLite em memória ou `DATABASE_URL` |
| Produção | `config.settings.production` | PostgreSQL obrigatório |

Em produção, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS` e `DATABASE_URL` são
obrigatórias. Consulte [docs/operations.md](docs/operations.md) para todas as variáveis.

## Documentação

- [Índice técnico](docs/index.md)
- [Arquitetura](docs/architecture.md)
- [Referência de classes e funções](docs/code-reference.md)
- [Operação, Docker e testes](docs/operations.md)
- [Decisões arquiteturais](docs/decisions.md)
- [Auditoria da v0.1.0](docs/versions/v0.1.0.md)
- [Auditoria da v0.2.0](docs/versions/v0.2.0.md)
- [Auditoria da v0.2.1](docs/versions/v0.2.1.md)
- [Auditoria da v0.2.2](docs/versions/v0.2.2.md)
- [Contexto compacto para IA](docs/ai-context.md)

## Próximo incremento

A versão `0.3.0` introduzirá orçamentos, reservas e disponibilidade por período,
consumindo clientes, unidades físicas e políticas de preço já estabilizados.
