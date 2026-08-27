# Contexto compacto para IA

Projeto Django 5.2 chamado Rental Platform. Última versão publicada: `0.3.0`.
Arquitetura: monólito modular, PostgreSQL em produção/Docker/CI e SQLite opcional no
desenvolvimento.

## Fonte de verdade

- `apps/accounts`: usuário interno.
- `apps/organizations`: organização, vínculo de acesso, matriz e filial.
- `apps/catalog`: categoria, modelo comercial e unidade física.
- `apps/customers`: pessoa física/jurídica, contatos e endereços.
- `apps/pricing`: políticas versionadas e cálculo elementar de preço.
- `apps/assets`: perfil patrimonial opcional da unidade física.
- `apps/quotations`: orçamento, conversão do período, snapshots e estados.
- `apps/reservations`: disponibilidade, confirmação, alocações físicas e cancelamento.
- `common`: UUID/timestamps, CPF, CNPJ, CEP e health checks.
- `config/settings`: ambientes.
- `docs/decisions.md`: decisões aceitas e planejadas.

## Invariantes que não podem ser quebradas

1. Dados de negócio pertencem a uma organização.
2. Relações de catálogo não atravessam organizações.
3. Toda unidade física tem estabelecimento.
4. CNPJ é opcional, único quando presente e armazenado normalizado.
5. O documento de cliente é único por organização e deve corresponder ao seu tipo.
6. Endereço e cliente pertencem à mesma organização.
7. Dinheiro usa decimal e não pode ser negativo.
8. Política de preço e modelo pertencem à mesma organização.
9. Cada política possui ao menos um valor por hora, dia ou mês.
10. Perfil patrimonial e unidade pertencem à mesma organização.
11. Valor residual não supera o custo e entrada em operação não antecede aquisição.
12. Produção exige PostgreSQL, segredo e hosts.
13. IA não é fonte autoritativa de regra de negócio.
14. Pagamentos futuros não usam integração bancária direta.
15. O tenant operacional vem de `request.organization`, nunca de um ID livre do cliente.
16. Sessão, vínculo e organização devem estar ativos antes de liberar o contexto.
17. Códigos `EQ-NNNNNN` são reservados por `AssetCodeSequence` dentro da transação.
18. Lotes usam `create_tool_batch()`; nunca calcule código por contagem ou maior valor.
19. Todo queryset da área operacional deve usar `request.organization`.
20. Orçamento, cliente, itens, modelos e políticas compartilham a organização ativa.
21. O intervalo de orçamento é `[início, fim)`, com fim obrigatoriamente posterior.
22. Snapshots guardam tarifa, quantidade exata, quantidade cobrada, política e total.
23. Somente `DRAFT` pode ser editado ou recalculado.
24. Orçamento não reserva equipamentos nem altera o estado físico da unidade.
25. `DRAFT → SENT` exige disponibilidade integral em um único estabelecimento ativo.
26. Somente orçamento `SENT` gera uma reserva e cada orçamento gera no máximo uma.
27. Reserva e alocações copiam o intervalo `[início, fim)` do orçamento.
28. Alocações ativas da mesma unidade não podem se sobrepor no PostgreSQL.
29. Cancelar libera alocações sem apagar o histórico.
30. `ToolUnit.status` representa condição operacional; agenda é derivada das alocações.
31. Reserva confirmada deve ser cancelada antes de expirar ou cancelar o orçamento.
32. A UI nunca deve apresentar `AVAILABLE` sozinho como prova de agenda livre.

## Próxima mudança recomendada

Evoluir reservas confirmadas para contratos, retirada, devolução e inspeção sem alterar
snapshots históricos.

## Como propor mudanças

- explique qual invariante ou caso de uso exige a mudança;
- preserve compatibilidade de dados com migration;
- teste sucesso, rejeições e isolamento por organização;
- atualize documentação e auditoria da versão;
- não crie abstrações para requisitos apenas imaginados.

## Fluxo obrigatório no GitHub

- nenhuma mudança começa sem Issue aceita;
- branches usam `agent/issue-{número}-{descrição}`;
- Pull Requests começam como rascunho e contêm `Closes #N`;
- CI, autorrevisão, Code Review e teste funcional precedem o merge;
- mudanças fora do escopo viram outra Issue;
- a `main` não recebe alterações diretas.
