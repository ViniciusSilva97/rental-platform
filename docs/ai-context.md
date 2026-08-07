# Contexto compacto para IA

Projeto Django 5.2 chamado Rental Platform, versão `0.2.2`. Arquitetura: monólito
modular, PostgreSQL em produção/Docker/CI e SQLite opcional no desenvolvimento.

## Fonte de verdade

- `apps/accounts`: usuário interno.
- `apps/organizations`: organização, vínculo de acesso, matriz e filial.
- `apps/catalog`: categoria, modelo comercial e unidade física.
- `apps/customers`: pessoa física/jurídica, contatos e endereços.
- `apps/pricing`: políticas versionadas e cálculo elementar de preço.
- `apps/assets`: perfil patrimonial opcional da unidade física.
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

## Próxima mudança recomendada

Executar a v0.3.0 na ordem das dependências: contexto automático da locadora, cadastro
assistido, orçamento reproduzível e reserva sem sobreposição. Não iniciar reservas antes
de existir isolamento de tenant na camada de aplicação.

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
