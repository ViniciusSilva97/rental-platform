# Guia de trabalho para pessoas e agentes de IA

Leia, nesta ordem, antes de alterar o projeto:

1. `README.md`;
2. `CONTRIBUTING.md`;
3. `docs/development-workflow.md`;
4. `docs/ai-context.md`;
5. `docs/architecture.md`;
6. `docs/code-reference.md`;
7. `docs/versions/v0.3.0.md`.
8. `docs/manual.md`, quando a mudança afetar o uso do sistema.

## Fluxo obrigatório de mudança

1. confirme uma Issue aberta com objetivo, escopo e critérios de aceite;
2. trabalhe em uma branch `agent/issue-{número}-{descrição}`;
3. mantenha commits pequenos, intencionais e vinculados ao escopo;
4. abra o Pull Request como rascunho e inclua `Closes #N`;
5. execute CI, autorrevisão e Code Review;
6. aguarde o teste funcional antes de marcar o PR como pronto;
7. faça merge somente após atender todos os critérios.

Não altere a `main` diretamente e não amplie silenciosamente o escopo da Issue.
Descobertas fora do escopo devem virar uma nova Issue.

## Regras do projeto

- Preserve o monólito modular; não crie microsserviços sem uma necessidade medida.
- Toda entidade pertencente ao negócio deve carregar `organization`.
- A organização operacional vem de `request.organization`, validada contra um vínculo
  ativo; nunca aceite o tenant enviado livremente pelo formulário ou pela URL.
- Toda consulta operacional deve ser filtrada pela organização ativa.
- Códigos de equipamentos são alocados por `create_tool_batch()`; nunca calcule o
  próximo código com `count()`, `max()` ou na interface.
- Cadastros em lote devem ser atômicos e bloquear a sequência dentro da organização.
- Clientes podem ser pessoas físicas ou jurídicas; documentos são armazenados sem máscara.
- Endereços de clientes e seus clientes devem pertencer à mesma organização.
- Políticas de preço pertencem à mesma organização do modelo de ferramenta.
- Perfis patrimoniais pertencem à mesma organização da unidade física.
- O valor residual não pode superar o custo de aquisição.
- A entrada em operação não pode anteceder a aquisição.
- A versão vigente é a política ativa mais recente cuja data já começou.
- Orçamentos são criados ou recalculados somente por `save_draft_quotation()`.
- Itens de orçamento preservam política, tarifa, quantidades e total como snapshot.
- Somente rascunhos podem mudar; envio, expiração e cancelamento preservam os itens.
- Um orçamento não reserva estoque nem altera o estado de `ToolUnit`.
- Somente orçamento `SENT` pode gerar uma reserva; cada orçamento gera no máximo uma.
- Reservas e alocações preservam o intervalo `[início, fim)` do orçamento.
- Disponibilidade deriva de alocações ativas e do estado operacional da `ToolUnit`.
- Confirmações usam `confirm_reservation()` e cancelamentos usam `cancel_reservation()`.
- Cancelar marca as alocações como liberadas; histórico de equipamento não é apagado.
- Uma reserva confirmada deve ser cancelada antes de encerrar seu orçamento.
- PostgreSQL impede sobreposição por equipamento; SQLite depende do serviço e não
  substitui a validação concorrente da CI.
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

Mudanças em `docs/`, `mkdocs.yml` ou no workflow de Pages também exigem:

```bash
uv run mkdocs build --strict
```

Atualize a documentação da versão quando mudar domínio, arquitetura, operação,
variáveis de ambiente ou limitações conhecidas.
