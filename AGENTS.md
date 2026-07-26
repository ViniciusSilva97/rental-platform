# Guia de trabalho para pessoas e agentes de IA

Leia, nesta ordem, antes de alterar o projeto:

1. `README.md`;
2. `docs/ai-context.md`;
3. `docs/architecture.md`;
4. `docs/code-reference.md`;
5. `docs/versions/v0.1.0.md`.

## Regras do projeto

- Preserve o monólito modular; não crie microsserviços sem uma necessidade medida.
- Toda entidade pertencente ao negócio deve carregar `organization`.
- Toda unidade física (`ToolUnit`) deve carregar também `establishment`.
- Relacionamentos entre registros de organizações diferentes são inválidos.
- Valores monetários usam `DecimalField`; nunca use `float`.
- Novas regras essenciais devem existir no modelo ou serviço de domínio, não somente
  na interface administrativa.
- Alterações de banco precisam de migration e teste de compatibilidade.
- Produção deve falhar ao iniciar quando variáveis obrigatórias estiverem ausentes.
- Não integre diretamente com bancos. Pagamentos futuros devem usar checkout hospedado
  e webhooks idempotentes de um provedor.
- Recursos de IA são assistivos. Nenhuma resposta de modelo deve ser fonte autoritativa
  para preço, estoque, contrato ou lançamento financeiro.

## Critério mínimo de conclusão

Execute antes de considerar uma alteração pronta:

```bash
uv run ruff check .
uv run python manage.py makemigrations --check --dry-run
uv run python manage.py check
uv run pytest
```

Atualize a documentação da versão quando mudar domínio, arquitetura, operação,
variáveis de ambiente ou limitações conhecidas.
