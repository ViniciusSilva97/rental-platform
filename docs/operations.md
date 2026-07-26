# Operação, Docker e testes

## Variáveis de ambiente

| Variável | Desenvolvimento | Produção |
|---|---|---|
| `DJANGO_SETTINGS_MODULE` | padrão `config.settings.development` | WSGI usa `config.settings.production` |
| `DJANGO_SECRET_KEY` | opcional, com fallback inseguro | obrigatória |
| `DJANGO_DEBUG` | padrão verdadeiro | ignorada; produção é sempre falsa |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | obrigatória, separada por vírgulas |
| `DATABASE_URL` | opcional; ausência seleciona SQLite | URL PostgreSQL obrigatória |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | normalmente vazia | origens HTTPS separadas por vírgulas |
| `DJANGO_SECURE_SSL_REDIRECT` | cookies seguros desativados | verdadeiro por padrão |
| `DJANGO_SECURE_HSTS_SECONDS` | não aplicado | 3600 por padrão |
| `DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS` | não aplicado | falso até todos os subdomínios estarem prontos |
| `DJANGO_SECURE_HSTS_PRELOAD` | não aplicado | falso até decisão operacional |

Não armazene arquivos `.env` no Git. Os exemplos versionados não contêm segredos.

## Execução sem Docker

O arquivo `.env.example` é apropriado para o host local. Sem `DATABASE_URL`, Django
cria `db.sqlite3`. Instale dependências com `uv sync --all-groups`, execute migrations e
inicie `python manage.py runserver`.

## Execução com Docker

O arquivo `.env.docker.example` usa o hostname `db`, resolvido pela rede interna do
Compose. Ele não serve para executar Django diretamente no host.

O ambiente virtual da imagem fica em `/opt/venv`. Essa posição é intencional: o volume
de desenvolvimento monta o código em `/app`; uma `.venv` criada dentro de `/app` seria
ocultada pelo bind mount.

Fluxo de inicialização:

1. `db` inicia PostgreSQL e passa no `pg_isready`;
2. `web` inicia o servidor de desenvolvimento;
3. o healthcheck de `web` consulta `/health/ready/`.

Migrations continuam sendo uma ação explícita:

```bash
docker compose exec web python manage.py migrate
```

Em uma plataforma gerenciada, execute migrations como job de release único antes de
trocar o tráfego. Não faça cada réplica executar migrations simultaneamente.

## Imagem de produção

O `Dockerfile`:

- instala dependências travadas por `uv.lock`;
- mantém o ambiente em `/opt/venv`;
- coleta arquivos estáticos;
- executa como usuário sem privilégios;
- inicia Gunicorn com dois workers e quatro threads por worker.

Workers e threads são um ponto de partida econômico, não um valor universal. Ajuste-os
com métricas de memória, latência e CPU da hospedagem real.

WhiteNoise entrega arquivos estáticos da própria aplicação. Uploads futuros de fotos,
documentos e contratos devem usar armazenamento de objetos persistente; o filesystem
do contêiner é descartável.

## Saúde

Liveness e readiness têm finalidades diferentes:

- falha de `/health/live/` justifica reiniciar o processo;
- falha de `/health/ready/` retira a instância do tráfego enquanto o banco está
  indisponível, sem presumir que reiniciar resolverá o banco.

O alias `/health/` evita quebrar consumidores da primeira versão.

## Qualidade e CI

Execução local:

```bash
uv run ruff check .
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py check
uv run pytest
```

O workflow do GitHub Actions sobe PostgreSQL 17, aplica migrations, executa lint e
testes e valida as configurações de produção com `check --deploy`. Isso encontra
diferenças que uma suíte exclusivamente SQLite poderia esconder.

Os testes atuais cobrem CPF, CNPJ, CEP, clientes, endereços, invariantes multi-tenant,
valores monetários, estados iniciais e endpoints operacionais. A migration que torna
o estabelecimento obrigatório também é exercitada sobre uma base anterior ao release.

## Recuperação e backup

A v0.1.0 ainda não automatiza backup. Antes de armazenar dados reais:

- configure backups do PostgreSQL com retenção;
- teste uma restauração completa;
- registre RPO e RTO aceitáveis;
- proteja segredos fora do repositório;
- centralize logs sem incluir CNPJ, e-mail ou documentos desnecessariamente.
