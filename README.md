# Rental Platform

Base técnica de uma plataforma para gestão de aluguel de ferramentas. O projeto usa
Python e Django em um monólito modular, com PostgreSQL nos ambientes compartilhados e
SQLite como alternativa de baixo atrito para desenvolvimento local.

A versão publicada `v0.3.0` cobre:

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
- orçamentos em rascunho com múltiplos modelos de ferramenta;
- conversão determinística do período em horas, dias ou meses;
- snapshot de tarifa, quantidade cobrada, regra de fração e total;
- envio condicionado à disponibilidade integral em pelo menos um estabelecimento;
- expiração e cancelamento sem alterar a memória de cálculo;
- consulta de disponibilidade por estabelecimento, modelo e período;
- listagem física com condição operacional separada da agenda de reservas;
- reservas confirmadas com equipamentos físicos específicos;
- prevenção de sobreposição, concorrência e acesso entre locadoras;
- cancelamento com liberação do período e preservação do histórico;
- painel administrativo, verificações de saúde e configuração por ambiente;
- testes automatizados e integração contínua com PostgreSQL.

Em desenvolvimento para a `v0.4.0`:

- contrato criado a partir de uma reserva confirmada;
- snapshots de cliente, valor e equipamentos contratados;
- retirada atômica com identificação do usuário responsável;
- devolução parcial por equipamento e condição observada;
- conclusão automática após a devolução integral.

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

A aplicação ficará em <http://localhost:8000>, a área da locadora em
<http://localhost:8000/app/> e o painel administrativo técnico em
<http://localhost:8000/admin/>.

## Área operacional

A área `/app/` exige autenticação. Um usuário sem vínculo passa por um onboarding que
cria, em uma única transação, sua locadora, a matriz e o vínculo de proprietário. Com
uma única locadora, o contexto é selecionado automaticamente; com várias, o usuário
faz uma escolha explícita. O Django Admin continua disponível apenas como ferramenta
técnica durante a construção dos cadastros assistidos.

Em `/app/ferramentas/`, o cadastro assistido cria categoria, modelo e até 100
equipamentos físicos em uma única operação. Códigos como `EQ-000001` são automáticos;
preços e dados patrimoniais são etapas opcionais e claramente separadas. A operação é
atômica: um erro não deixa modelos, equipamentos ou perfis parciais.

A listagem separa condição e agenda. `AVAILABLE` é apresentado como **Apta para
locação**, enquanto reservas atuais e futuras aparecem em uma coluna própria; assim,
uma reserva futura não altera permanentemente o estado físico do equipamento.

Em `/app/orcamentos/`, o usuário escolhe cliente, período, ferramentas, quantidades e
unidades de cobrança. O Django seleciona a política vigente no início da locação,
calcula o total e guarda um snapshot reproduzível. Somente rascunhos podem ser editados
ou recalculados. O envio exige que uma unidade ativa consiga atender integralmente as
quantidades no período; expirar ou cancelar preserva os valores já registrados.

Em `/app/reservas/`, a locadora consulta disponibilidade e confirma um orçamento
enviado em um estabelecimento. O sistema escolhe unidades físicas específicas e
protege o intervalo semiaberto `[início, fim)` contra sobreposição. Cancelar a reserva
libera o período sem apagar as alocações históricas.

Em `/app/contratos/`, uma reserva confirmada pode gerar um único contrato. A retirada
marca todas as unidades como alugadas; cada devolução registra usuário, horário,
condição e observações. Devoluções parciais mantêm o contrato aberto e a devolução
integral o conclui automaticamente.

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

- [Site público da documentação](https://viniciussilva97.github.io/rental-platform/)
- [Manual de uso](docs/manual.md)
- [Índice técnico](docs/index.md)
- [Como contribuir](CONTRIBUTING.md)
- [Fluxo de desenvolvimento e Code Review](docs/development-workflow.md)
- [Arquitetura](docs/architecture.md)
- [Referência de classes e funções](docs/code-reference.md)
- [Operação, Docker e testes](docs/operations.md)
- [Decisões arquiteturais](docs/decisions.md)
- [Auditoria da v0.1.0](docs/versions/v0.1.0.md)
- [Auditoria da v0.2.0](docs/versions/v0.2.0.md)
- [Auditoria da v0.2.1](docs/versions/v0.2.1.md)
- [Auditoria da v0.2.2](docs/versions/v0.2.2.md)
- [Auditoria e atualização da v0.3.0](docs/versions/v0.3.0.md)
- [Desenvolvimento da v0.4.0](docs/versions/v0.4.0.md)
- [Contexto compacto para IA](docs/ai-context.md)

## Próximo incremento

Depois do ciclo básico de contratos, a evolução prevista inclui renovação, inspeção
detalhada, cálculo de avarias e cobrança, cada capacidade em uma Issue independente.

## Licença

Este projeto é disponibilizado como código-fonte disponível (*source available*) exclusivamente para uso interno. Ele não é oferecido como software *open source*. Revenda, redistribuição, exploração comercial e oferta como SaaS ou serviço gerenciado são proibidas sem autorização prévia e escrita do titular.

Consulte o arquivo [LICENSE](LICENSE) para conhecer os termos completos. Componentes de terceiros permanecem sujeitos às suas próprias licenças.
