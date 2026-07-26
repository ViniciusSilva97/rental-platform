# Contexto compacto para IA

Projeto Django 5.2 chamado Rental Platform, versão `0.2.0`. Arquitetura: monólito
modular, PostgreSQL em produção/Docker/CI e SQLite opcional no desenvolvimento.

## Fonte de verdade

- `apps/accounts`: usuário interno.
- `apps/organizations`: organização, vínculo de acesso, matriz e filial.
- `apps/catalog`: categoria, modelo comercial e unidade física.
- `apps/customers`: pessoa física/jurídica, contatos e endereços.
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
8. Produção exige PostgreSQL, segredo e hosts.
9. IA não é fonte autoritativa de regra de negócio.
10. Pagamentos futuros não usam integração bancária direta.

## Próxima mudança recomendada

Implementar políticas versionadas de preço por hora, dia e mês. Definir arredondamento,
vigência e significado configurável de mês. Não implementar ainda reservas, pagamento,
depreciação ou uma API ampla no mesmo incremento.

## Como propor mudanças

- explique qual invariante ou caso de uso exige a mudança;
- preserve compatibilidade de dados com migration;
- teste sucesso, rejeições e isolamento por organização;
- atualize documentação e auditoria da versão;
- não crie abstrações para requisitos apenas imaginados.
