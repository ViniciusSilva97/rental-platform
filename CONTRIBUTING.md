# Como contribuir

Este projeto usa um processo incremental para preservar regras de negócio, isolamento
entre locadoras e compatibilidade dos dados. O fluxo também foi escrito para quem está
aprendendo desenvolvimento profissional.

## Antes de começar

1. leia `README.md`, `AGENTS.md` e `docs/ai-context.md`;
2. escolha uma Issue aberta e confirme suas dependências;
3. verifique objetivo, escopo, critérios de aceite e itens fora do escopo;
4. atualize sua `main` local sem descartar mudanças próprias.

Nenhuma funcionalidade ou correção começa somente por uma conversa informal. A decisão
deve estar registrada em uma Issue para continuar compreensível no futuro.

## Branch

Crie a branch a partir da `main` atual:

```bash
git switch main
git pull --ff-only origin main
git switch -c agent/issue-6-github-workflow
```

O padrão é:

```text
agent/issue-{número}-{descrição-curta}
```

Não faça alterações diretamente na `main`.

## Implementação

- preserve o escopo da Issue;
- mantenha regras essenciais no domínio, não apenas na interface;
- valide relações por organização;
- use `Decimal` para dinheiro;
- acompanhe alterações de banco com migration;
- teste sucesso, rejeições, autorização e compatibilidade;
- atualize a documentação afetada.

Uma descoberta relevante fora do escopo deve ser registrada em outra Issue.

## Commit e Pull Request

Use mensagens curtas que descrevam o resultado, por exemplo:

```text
chore: establish GitHub review workflow
feat: add active organization context
fix: prevent overlapping reservations
```

Abra o Pull Request como rascunho e inclua:

```text
Closes #6
```

O vínculo fecha a Issue automaticamente somente depois do merge.

## Validação mínima

```bash
uv run ruff check .
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py check
uv run pytest
```

Alterações de configuração de produção também exigem `check --deploy`. Migrations e
recursos dependentes de PostgreSQL devem ser exercitados na CI.

## Code Review e teste funcional

O PR permanece em rascunho enquanto houver:

- CI pendente ou falhando;
- comentário de revisão não resolvido;
- critério de aceite sem evidência;
- documentação incompatível com o código;
- teste funcional ainda não realizado.

O autor faz a primeira revisão do próprio diff. O Code Review verifica domínio,
segurança, tenant, banco, concorrência, testes, documentação e impacto operacional.
Depois, o responsável pelo produto executa o roteiro funcional. Somente então o PR
pode ficar pronto para revisão e ser mesclado.

Detalhes estão em `docs/development-workflow.md`.
