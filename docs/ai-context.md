# Contexto compacto para IA

Projeto Django 5.2 chamado Rental Platform, versão `0.2.1`. Arquitetura: monólito
modular, PostgreSQL em produção/Docker/CI e SQLite opcional no desenvolvimento.

## Fonte de verdade

- `apps/accounts`: usuário interno.
- `apps/organizations`: organização, vínculo de acesso, matriz e filial.
- `apps/catalog`: categoria, modelo comercial e unidade física.
- `apps/customers`: pessoa física/jurídica, contatos e endereços.
- `apps/pricing`: políticas versionadas e cálculo elementar de preço.
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
10. Produção exige PostgreSQL, segredo e hosts.
11. IA não é fonte autoritativa de regra de negócio.
12. Pagamentos futuros não usam integração bancária direta.

## Próxima mudança recomendada

Adicionar a base patrimonial das unidades: data e custo de aquisição, valor residual,
vida útil e dados necessários para depreciação futura. Não calcular depreciação, criar
reservas, integrar pagamentos ou ampliar a API no mesmo incremento.

## Como propor mudanças

- explique qual invariante ou caso de uso exige a mudança;
- preserve compatibilidade de dados com migration;
- teste sucesso, rejeições e isolamento por organização;
- atualize documentação e auditoria da versão;
- não crie abstrações para requisitos apenas imaginados.
