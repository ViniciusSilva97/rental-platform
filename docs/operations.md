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

## Autenticação e área da locadora

- `/accounts/login/`: autenticação do usuário interno;
- `/app/`: entrada da área operacional;
- `/app/onboarding/`: criação inicial da locadora e matriz;
- `/app/selecionar-locadora/`: escolha para usuários com múltiplos vínculos;
- `/app/ferramentas/`: equipamentos da locadora ativa;
- `/app/ferramentas/cadastrar/`: cadastro assistido em lote;
- `/app/orcamentos/`: lista de orçamentos da locadora ativa;
- `/app/orcamentos/novo/`: criação assistida com um ou mais modelos;
- `/app/reservas/`: reservas confirmadas da locadora ativa;
- `/app/reservas/disponibilidade/`: consulta por filial, modelo e período;
- `/app/contratos/`: contratos, retiradas e devoluções da locadora ativa;
- `/admin/`: administração técnica, não destinada à operação normal.

Ainda não há cadastro público. Crie o primeiro usuário com `createsuperuser` ou pelo
Admin. Depois do login, o onboarding cria a locadora, a matriz e o vínculo de
proprietário sem exigir slug ou identificador de organização.

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

Os testes atuais cobrem CPF, CNPJ, CEP, clientes, endereços, políticas e cálculos de
preço, perfis patrimoniais, onboarding transacional, sessão adulterada, seleção de
locadora, cadastro assistido, rollback de lote, concorrência de códigos, orçamentos,
conversões de hora/dia/mês, snapshots, estados comerciais, disponibilidade,
alocações físicas, cancelamento, exclusão temporal e concorrência de reservas, vínculos
inativos, invariantes multi-tenant, valores monetários, estados
iniciais e endpoints operacionais. Os fluxos inline com pai ainda não salvo também são
exercitados. As migrations de estabelecimento e de conversão da diária legada são
testadas sobre estados anteriores ao release.

O teste concorrente de códigos exige PostgreSQL e é ignorado quando a suíte usa SQLite.
Isso é intencional: `select_for_update()` só pode ser validado em um banco com bloqueio
de linha real, e a CI executa obrigatoriamente com PostgreSQL 17.

Os testes de exclusão e confirmação simultânea de reservas também exigem PostgreSQL.
A migration habilita `btree_gist` e cria a constraint temporal somente nesse banco;
SQLite valida o fluxo funcional, mas não deve ser usado como evidência de concorrência.

## Roteiro funcional de orçamento

Para validar o fluxo publicado na v0.3.0:

1. atualize a branch e execute `python manage.py migrate`;
2. entre em `/app/` e confirme que existe cliente ativo e ferramenta com preço;
3. abra **Criar orçamento**;
4. selecione cliente, início, fim, modelo, quantidade e cobrança por dia;
5. use **Adicionar outra ferramenta** e inclua um segundo modelo, se disponível;
6. salve e confira código, período, memória de cálculo e total;
7. edite o rascunho e confirme que o total é recalculado;
8. altere a política no Admin e verifique que o snapshot antigo não muda sozinho;
9. clique em **Recalcular preços** e confirme que apenas o rascunho recebe o novo valor;
10. marque como enviado e confirme que edição e recálculo deixam de ser permitidos;
11. marque como expirado ou, em outro orçamento, teste cancelamento;
12. confirme que nenhum equipamento mudou para reservado.

Teste também um fim anterior ao início, uma unidade sem tarifa configurada e um preço
com vigência futura. A interface deve recusar os três casos sem criar registros parciais.

## Roteiro funcional de disponibilidade e reservas

Para validar o fluxo publicado na v0.3.0:

1. atualize a branch, reconstrua os contêineres e execute `python manage.py migrate`;
2. crie um orçamento sem quantidade disponível e confirme que ele permanece em
   rascunho ao tentar marcá-lo como enviado;
3. confirme que existe um orçamento viável e equipamentos `AVAILABLE` na mesma filial;
4. marque o orçamento como enviado;
5. abra **Reservas → Consultar disponibilidade** e pesquise modelo, filial e período;
6. confira que os códigos físicos disponíveis aparecem, não apenas uma quantidade;
7. abra o orçamento enviado e clique em **Confirmar reserva**;
8. confirme que somente filiais capazes de atender todo o orçamento são oferecidas;
9. escolha o estabelecimento e confirme que a reserva mostra unidades específicas;
10. abra **Ferramentas** e confirme que a unidade continua **Apta para locação**, mas a
    agenda mostra **Reservado agora** ou a próxima reserva;
11. tente confirmar outro orçamento sobreposto com quantidade superior ao saldo e
   confirme que a operação é recusada sem criar reserva parcial;
12. use um período que começa exatamente quando a primeira reserva termina e confirme
   que a unidade volta a ser elegível;
13. tente expirar ou cancelar o orçamento reservado e confirme a orientação para
   cancelar primeiro a reserva;
14. cancele a reserva e confirme que as alocações aparecem como liberadas;
15. consulte novamente o mesmo período e confirme que os equipamentos voltaram;
16. volte à listagem e confirme que a agenda deixou de indicar a reserva cancelada;
17. depois do cancelamento da reserva, encerre o orçamento normalmente.

Teste também uma ferramenta em manutenção e uma filial diferente. A primeira não pode
aparecer como disponível; a segunda não pode acessar equipamentos de outra filial ou
organização.

## Roteiro funcional de contratos

1. confirme uma reserva com dois equipamentos;
2. abra a reserva e clique em **Preparar contrato**;
3. confira snapshots, estabelecimento, período, valor e códigos físicos;
4. confirme a retirada e verifique que todas as unidades ficaram **Alugadas**;
5. devolva somente a primeira como **Em manutenção** e registre uma observação;
6. confirme que o contrato continua **Em andamento** e a segunda unidade, **Alugada**;
7. devolva a segunda como **Apta para locação**;
8. confirme que o contrato foi concluído e que cada item mostra usuário e horário;
9. consulte a agenda e confirme que as alocações foram liberadas sem desaparecer;
10. tente cancelar a reserva contratada e confirme que a operação é recusada.

Teste também acesso por outra organização, retirada repetida, devolução repetida e
condição **Perdida**. Nenhum desses caminhos pode criar movimentação parcial ou cruzar
dados entre locadoras.

## Documentação e GitHub Pages

O site público usa Material for MkDocs. Para instalar todas as dependências do projeto
e abrir uma prévia local:

```bash
uv sync --frozen --all-groups
uv run --no-sync mkdocs serve
```

Acesse `http://127.0.0.1:8000/rental-platform/`. Antes de publicar, valide em modo
estrito:

```bash
uv run --no-sync mkdocs build --strict
```

O workflow `Documentation` compila o site em Pull Requests. Após um push na `main`, o
mesmo artefato é implantado em
`https://viniciussilva97.github.io/rental-platform/` com permissões restritas a Pages.
O GitHub Pages hospeda somente a documentação estática; ele não executa Django nem
substitui a implantação da aplicação.

## Recuperação e backup

O projeto ainda não automatiza backup. Antes de armazenar dados reais:

- configure backups do PostgreSQL com retenção;
- teste uma restauração completa;
- registre RPO e RTO aceitáveis;
- proteja segredos fora do repositório;
- centralize logs sem incluir CNPJ, e-mail ou documentos desnecessariamente.
