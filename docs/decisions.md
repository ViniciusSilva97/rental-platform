# Registro de decisões arquiteturais

## ADR-001 — Monólito modular

**Status:** aceito.

**Decisão:** uma aplicação Django e um banco PostgreSQL, separados internamente por
módulos de domínio.

**Motivo:** é a alternativa com menor custo operacional e menor número de falhas
distribuídas para a equipe atual. Transações de reserva, estoque e contrato permanecem
simples.

**Alternativas:** microsserviços foram adiados; um único app Django sem módulos foi
rejeitado por misturar responsabilidades.

**Revisão:** considerar extração apenas quando houver escala, segurança, disponibilidade
ou autonomia de equipe que não possam ser atendidas dentro do monólito.

## ADR-002 — Tenant em schema compartilhado

**Status:** aceito com controles pendentes.

**Decisão:** registros de negócio carregam `organization_id` no mesmo schema.

**Motivo:** provisionamento e migrations são simples e econômicos. As constraints
compostas permitem unicidade por organização.

**Risco:** uma consulta sem filtro pode expor dados entre organizações.

**Controles:** validar relações cruzadas no domínio; adicionar escopo obrigatório aos
serviços e ao Admin antes do uso externo; criar testes de autorização na API futura.

## ADR-003 — CNPJ numérico e alfanumérico

**Status:** aceito.

**Decisão:** aceitar letras ou números nas 12 posições-base, números nas duas posições
verificadoras, armazenar sem máscara e exibir formatado.

**Motivo:** evita uma migração emergencial quando novos CNPJs alfanuméricos forem
emitidos e elimina duplicidade causada por máscara ou caixa.

**Alternativa:** aceitar somente o formato numérico foi rejeitado por produzir uma
restrição de domínio com prazo de validade.

## ADR-004 — Configuração separada por ambiente

**Status:** aceito.

**Decisão:** `base`, `development`, `test` e `production` compõem configurações
explícitas.

**Motivo:** padrões convenientes de desenvolvimento não podem vazar silenciosamente
para produção. Produção falha cedo sem segredo, hosts ou PostgreSQL.

**Consequência:** comandos operacionais precisam selecionar corretamente o módulo; WSGI
já seleciona produção e `manage.py` seleciona desenvolvimento.

## ADR-005 — Estabelecimento obrigatório no ativo

**Status:** aceito.

**Decisão:** toda `ToolUnit` pertence a um `Establishment`.

**Motivo:** disponibilidade, retirada, transferência, inventário e manutenção dependem
de saber onde o item está. `organization` identifica o tenant; `establishment` identifica
a responsabilidade física.

**Migração:** unidades antigas são vinculadas à matriz ativa, ao primeiro
estabelecimento existente ou a uma matriz criada pela própria migration.

## ADR-006 — Preço como política versionada

**Status:** aceito.

**Decisão:** hora, dia e mês são valores opcionais de `PricingPolicy`; ao menos um deve
existir. Cada versão possui `effective_from`, e a versão ativa mais recente já vigente
substitui implicitamente a anterior. Mês pode significar uma quantidade fixa de dias
ou mês-calendário. Frações são arredondadas para cima ou cobradas proporcionalmente.

**Motivo:** preços mudam, arredondamentos variam e contratos antigos precisam permanecer
reproduzíveis. Vigência definida somente pelo início evita intervalos sobrepostos e
simplifica agendamento e consulta.

**Migração:** a diária existente em `ToolModel` é transformada em uma política inicial
com a data de criação do modelo. O processo torna o campo antigo temporariamente
anulável, copia os valores e só então remove a coluna, permitindo reversão segura.

**Adiado:** o orçamento futuro converterá períodos reais em unidades e salvará um
snapshot da política, quantidades, tarifas e total. Descontos e combinações de unidades
não pertencem a esta versão.

## ADR-007 — Pagamento hospedado e IA assistiva

**Status:** planejado.

**Decisão:** usar checkout hospedado por provedor e webhooks idempotentes, sem integração
bancária direta. IA poderá classificar texto, sugerir respostas e auxiliar busca, mas
não decidirá preço, estoque, contrato ou finanças.

**Motivo:** reduz escopo de segurança, conformidade, custo operacional e risco de
respostas não determinísticas.

## ADR-008 — Cliente unificado e documento por organização

**Status:** aceito.

**Decisão:** `Customer` representa pessoa física e jurídica por meio de `kind`; um único
campo `document` armazena CPF ou CNPJ normalizado. A unicidade é composta por
organização e documento.

**Motivo:** os dois tipos compartilham identidade operacional, contatos, endereços e
futuras locações. Modelos separados duplicariam fluxos. A mesma pessoa pode negociar
com locadoras diferentes, por isso o documento não é globalmente único.

**Controles:** o tipo determina o algoritmo de validação; uma constraint confirma o
formato no banco; documentos só são mascarados na apresentação.

## ADR-009 — Endereço com tenant explícito

**Status:** aceito.

**Decisão:** `CustomerAddress` armazena `organization_id`, mesmo sendo possível chegar
à organização através do cliente.

**Motivo:** consultas operacionais podem ser escopadas diretamente pelo tenant e seguem
uma única regra de segurança para todas as entidades de negócio.

**Risco:** cliente e endereço poderiam apontar para organizações diferentes.

**Controle:** `clean()` rejeita a relação cruzada e o formset do Admin herda a
organização do cliente. Escritas em lote deverão preservar essa mesma invariante.

## ADR-010 — Perfil patrimonial separado e opcional

**Status:** aceito.

**Decisão:** `AssetProfile` estende `ToolUnit` por uma relação um para um e repete
`organization_id`. A unidade pode existir sem perfil, mas um perfil existente exige
aquisição, entrada em operação, custo, valor residual e vida útil.

**Motivo:** estoque operacional e mensuração patrimonial evoluem em ritmos diferentes.
Separar os módulos evita campos contábeis vazios em todas as unidades e prepara
depreciação sem fazer o catálogo assumir lançamentos ou relatórios contábeis.

**Controles:** perfil e unidade devem compartilhar tenant; residual não supera custo;
entrada em operação não antecede aquisição; vida útil é positiva. Constraints repetem
as regras determinísticas no banco.

**Adiado:** método de depreciação, competência mensal, valor acumulado, impairment,
revisão de estimativas e lançamentos pertencem à v0.5. O valor depreciável atual é
somente `custo - residual`.

## ADR-011 — Organização ativa derivada do usuário

**Status:** aceito.

**Decisão:** a área operacional resolve a locadora ativa a partir de vínculos ativos do
usuário. O UUID escolhido fica na sessão, mas é revalidado no banco a cada request. Um
único vínculo é automático; múltiplos exigem escolha explícita. Formulários futuros não
receberão `organization_id` como decisão livre do cliente.

**Motivo:** repetir `Organization` em todos os formulários expõe um conceito técnico,
prejudica a experiência e permite falhas de isolamento se um identificador manipulado
for aceito. O request autenticado deve ser a origem do escopo operacional.

**Onboarding:** locadora, matriz e vínculo de proprietário são criados em uma única
transação. Assim, uma falha no CNPJ ou na unidade não deixa um tenant incompleto.

**Limites:** o Admin permanece técnico e não herda automaticamente o contexto. Não há
cadastro público, assinatura do SaaS ou matriz detalhada de permissões nesta decisão.

## ADR-012 — Códigos internos por sequência transacional

**Status:** aceito.

**Decisão:** cada organização possui uma `AssetCodeSequence`. O cadastro em lote bloqueia
a linha da organização, reserva uma faixa numérica e cria códigos legíveis no formato
`EQ-000001`. Modelo, preço, equipamentos, perfis e avanço do contador compartilham a
mesma transação.

**Motivo:** calcular o próximo valor por contagem ou maior código sofre condição de
corrida. Uma sequência por tenant preserva legibilidade, permite lotes e tem baixo custo
operacional. Bloquear `Organization` resolve também a concorrência quando a sequência
ainda não existe.

**Controles:** `next_value` é positivo, existe uma sequência por organização e o código
continua único por tenant. A CI com PostgreSQL executa dois lotes simultâneos e exige
dez códigos distintos.

**Consequência:** rollback pode reutilizar uma faixa que nunca se tornou visível, pois
contador e lote voltam juntos. Lacunas futuras são aceitáveis; código interno identifica
o equipamento, mas não é numeração fiscal.

**Adiado:** prefixos configuráveis, importação, QR Code e etiquetas pertencem a Issues
futuras.
