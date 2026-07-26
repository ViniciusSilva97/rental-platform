# Contexto compacto para IA

Projeto Django 5.2 chamado Rental Platform, versão `0.1.0`. Arquitetura: monólito
modular, PostgreSQL em produção/Docker/CI e SQLite opcional no desenvolvimento.

## Fonte de verdade

- `apps/accounts`: usuário interno.
- `apps/organizations`: organização, vínculo de acesso, matriz e filial.
- `apps/catalog`: categoria, modelo comercial e unidade física.
- `common`: UUID/timestamps, CNPJ e health checks.
- `config/settings`: ambientes.
- `docs/decisions.md`: decisões aceitas e planejadas.

## Invariantes que não podem ser quebradas

1. Dados de negócio pertencem a uma organização.
2. Relações de catálogo não atravessam organizações.
3. Toda unidade física tem estabelecimento.
4. CNPJ é opcional, único quando presente e armazenado normalizado.
5. Dinheiro usa decimal e não pode ser negativo.
6. Produção exige PostgreSQL, segredo e hosts.
7. IA não é fonte autoritativa de regra de negócio.
8. Pagamentos futuros não usam integração bancária direta.

## Próxima mudança recomendada

Implementar clientes e endereços em módulo próprio. Não implementar ainda reservas,
pagamento, depreciação ou uma API ampla no mesmo incremento.

## Como propor mudanças

- explique qual invariante ou caso de uso exige a mudança;
- preserve compatibilidade de dados com migration;
- teste sucesso, rejeições e isolamento por organização;
- atualize documentação e auditoria da versão;
- não crie abstrações para requisitos apenas imaginados.
