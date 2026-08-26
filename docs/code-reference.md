# Referência de classes e funções

## `common`

### `TimeStampedModel`

Modelo abstrato herdado pelas entidades de domínio.

| Campo | Função |
|---|---|
| `id` | UUID gerado na aplicação e usado como chave primária |
| `created_at` | data imutável de criação |
| `updated_at` | data atualizada a cada `save()` |

Como é abstrato, não cria uma tabela própria. Os timestamps não constituem trilha de
auditoria: versões futuras ainda precisarão registrar quem realizou alterações críticas.

### Funções de CPF e CNPJ em `common.documents`

| Função | Contrato |
|---|---|
| `normalize_cpf(value)` | remove máscara e espaços do CPF |
| `_calculate_cpf_digit(characters, weights)` | aplica pesos e módulo 11 a um dígito do CPF |
| `calculate_cpf_check_digits(value)` | recebe nove números e devolve os dois verificadores |
| `validate_cpf(value)` | valida formato, repetição e verificadores do CPF |
| `format_cpf(value)` | aplica a máscara visual do CPF |
| `normalize_cnpj(value)` | remove `.`, `-`, `/` e espaços; converte letras para maiúsculas |
| `_calculate_check_digit(characters, weights)` | aplica pesos e módulo 11 a uma sequência já validada |
| `calculate_cnpj_check_digits(value)` | recebe exatamente as 12 posições-base e devolve dois dígitos |
| `validate_cnpj(value)` | aceita vazio; nos demais casos valida formato, repetição e dígitos |
| `format_cnpj(value)` | aplica máscara visual a 14 posições; valores de outro tamanho são devolvidos normalizados |

Nas 12 primeiras posições, letras são convertidas pelo valor `ord(caractere) - 48`;
as duas últimas posições são obrigatoriamente numéricas. O modelo guarda a forma
normalizada para que máscara e diferenças de caixa não criem duplicatas.

### Funções de CEP em `common.locations`

| Função | Contrato |
|---|---|
| `normalize_brazilian_postal_code(value)` | remove hífen e espaços |
| `validate_brazilian_postal_code(value)` | exige exatamente oito números |
| `format_brazilian_postal_code(value)` | apresenta o CEP no formato `00000-000` |

O primeiro incremento de endereços é brasileiro. A função está nomeada explicitamente
para não tratar o formato de CEP como uma regra postal universal.

### Views operacionais em `common.views`

| Função | Resultado |
|---|---|
| `home(request)` | renderiza `templates/home.html` |
| `health_check(request)` | alias compatível que delega para liveness |
| `health_live(request)` | `200 {"status":"ok"}` se o processo Django responde |
| `health_ready(request)` | executa `SELECT 1`; retorna 200 quando pronto ou 503 sem banco |

Os endpoints de saúde aceitam apenas `GET`. Eles não expõem exceções ou credenciais.

## `accounts`

### `User`

Estende `django.contrib.auth.models.AbstractUser`, preservando username, senha,
permissões e integração com o Admin. O campo `email` é obrigatório no banco e único.
`__str__()` prefere o nome completo e usa o username como fallback.

Decisão: manter o `AbstractUser` reduz risco e custo nesta fase. Autenticação por e-mail
poderá ser adotada depois, mas exige manager, backend e migração cuidadosamente testados.

## `organizations`

### `Organization`

Representa o tenant contratante.

| Campo/método | Responsabilidade |
|---|---|
| `name` | nome exibido |
| `slug` | identificador textual único |
| `active` | desativação lógica |
| `__str__()` | devolve o nome |

Desativar não bloqueia operações automaticamente; os futuros serviços de aplicação
deverão rejeitar organizações inativas.

### `Membership`

Relaciona um usuário a uma organização. A constraint
`unique_organization_membership` impede vínculos duplicados.

Papéis atuais:

- `OWNER`: proprietário;
- `MANAGER`: gerente;
- `ATTENDANT`: atendente padrão.

`active` permite suspender acesso sem apagar histórico. Os papéis ainda não estão
ligados a uma matriz formal de permissões; isso é obrigatório antes da interface
multiusuário.

### `Establishment`

Representa matriz ou filial da organização.

| Elemento | Comportamento |
|---|---|
| `cnpj` | opcional, globalmente único e armazenado normalizado |
| `kind` | `HEADQUARTERS` ou `BRANCH` |
| `active` | controla operação sem apagar o registro |
| `clean()` | normaliza o CNPJ durante validação |
| `save()` | normaliza, chama `full_clean()` e persiste |
| `formatted_cnpj` | devolve apresentação mascarada |
| `__str__()` | combina estabelecimento e organização |

Constraints garantem nome único dentro da organização, formato normalizado e no máximo
uma matriz ativa. Uma organização pode existir tecnicamente sem matriz, mas o
onboarding operacional cria ambas em uma única transação.

### Serviços de contexto e onboarding

| Elemento | Contrato |
|---|---|
| `available_memberships(user)` | retorna somente vínculos e organizações ativos |
| `resolve_active_organization(request)` | valida a sessão e seleciona automaticamente o único vínculo |
| `set_active_organization(request, organization)` | grava o contexto apenas após confirmar acesso |
| `clear_active_organization(request)` | remove da sessão um contexto inválido ou antigo |
| `create_organization_for_owner(...)` | cria locadora, matriz e proprietário atomicamente |
| `ACTIVE_ORGANIZATION_SESSION_KEY` | chave única usada para persistir o UUID na sessão |

O slug é interno e gerado a partir do nome, recebendo sufixo quando necessário. O CNPJ
continua pertencendo à matriz. Uma falha de validação na matriz desfaz também a
organização e o vínculo.

### Formulários, middleware e views operacionais

| Elemento | Responsabilidade |
|---|---|
| `OrganizationOnboardingForm` | coleta nomes amigáveis e CNPJ opcional, sem expor slug ou tenant |
| `OrganizationSelectionForm` | oferece apenas locadoras acessíveis ao usuário |
| `ActiveOrganizationMiddleware` | disponibiliza o contexto validado em `request.organization` |
| `workspace_home()` | exige autenticação e direciona onboarding, seleção ou painel |
| `onboarding()` | impede duplicidade e executa a criação transacional |
| `select_organization()` | exige escolha quando há vários vínculos e rejeita IDs externos |

As rotas operacionais ficam sob `/app/`; login e logout usam as views autenticadas do
Django em `/accounts/`. Não existe cadastro público de usuário nesta versão.

## `customers`

### `Customer`

Representa uma pessoa física ou jurídica atendida por uma organização.

| Elemento | Comportamento |
|---|---|
| `kind` | `INDIVIDUAL` para pessoa física ou `COMPANY` para jurídica |
| `name` | nome completo ou razão social |
| `trade_name` | nome fantasia opcional |
| `document` | CPF ou CNPJ obrigatório, armazenado sem máscara |
| `email`, `phone` | contatos opcionais |
| `notes` | observações internas |
| `active` | desativação lógica sem apagar histórico |
| `clean()` | normaliza e valida o documento de acordo com o tipo |
| `save()` | executa `full_clean()` antes da escrita |
| `formatted_document` | escolhe a máscara de CPF ou CNPJ |
| `__str__()` | devolve o nome do cliente |

`unique_customer_document_per_organization` impede duplicidade dentro da locadora, mas
permite que a mesma pessoa seja cliente de organizações diferentes. A constraint
`customer_document_matches_kind` protege o formato normalizado no banco.

### `CustomerAddress`

Representa um endereço brasileiro vinculado ao cliente.

| Elemento | Comportamento |
|---|---|
| `kind` | principal, cobrança, entrega ou outro |
| `postal_code` | CEP normalizado com oito números |
| `street`, `number`, `complement`, `district` | componentes do logradouro |
| `city`, `state`, `country` | localidade; UF e país são armazenados em maiúsculas |
| `active` | permite desativar sem apagar |
| `clean()` | normaliza localidade e impede relacionamento entre organizações |
| `save()` | normaliza e valida antes da escrita |
| `formatted_postal_code` | apresenta o CEP com máscara |
| `__str__()` | resume logradouro, cidade e UF |

Cada endereço repete `organization_id` de propósito. Isso permite escopo direto por
tenant e segue a regra geral dos dados de negócio. A constraint
`unique_active_main_address_per_customer` permite apenas um endereço principal ativo.

## `catalog`

### `Category`

Classifica modelos de ferramentas dentro de uma organização. Nome é único por
organização e `active` permite retirada de uso sem apagar referências.

### `ToolModel`

Define o produto comercial compartilhado por várias unidades físicas.

| Elemento | Comportamento |
|---|---|
| `category` | categoria protegida contra exclusão enquanto utilizada |
| `name`, `brand`, `model_number` | identidade comercial |
| `description` | texto livre opcional |
| `deposit_amount` | caução não negativa |
| `clean()` | rejeita categoria de outra organização |
| `save()` | chama `full_clean()` antes de persistir |
| `__str__()` | combina marca, nome e modelo, omitindo partes vazias |

A unicidade composta evita duplicar a mesma combinação de nome, marca e modelo na
organização. Preços pertencem ao módulo `pricing`; o catálogo não decide mais uma
diária diretamente.

### `AssetCodeSequence`

Mantém o próximo número interno de cada organização. A relação um para um impede duas
sequências para o mesmo tenant e a constraint exige `next_value >= 1`. A classe não é
um contador global: cada locadora começa em `EQ-000001`.

### `ToolUnit`

Representa um ativo físico individual que pode ser reservado, alugado, inspecionado ou
mantido.

| Elemento | Comportamento |
|---|---|
| `tool_model` | modelo comercial; exclusão protegida |
| `establishment` | responsável atual pelo estoque; obrigatório e protegido |
| `asset_code` | código patrimonial único por organização |
| `serial_number` | número do fabricante opcional |
| `status` | estado operacional da unidade |
| `location` | posição textual dentro do estabelecimento |
| `notes` | observações livres |
| `clean()` | rejeita modelo ou estabelecimento de outra organização |
| `save()` | valida antes de persistir |
| `__str__()` | combina código patrimonial e modelo |

Estados existentes: `AVAILABLE`, `RESERVED`, `RENTED`, `INSPECTION`, `MAINTENANCE`,
`DAMAGED` e `INACTIVE`. A enumeração limita valores, mas ainda não controla transições.
Quando locações forem implementadas, mudanças de estado deverão passar por um serviço
transacional com regras explícitas e histórico.

### Serviços do cadastro assistido

| Elemento | Contrato |
|---|---|
| `PricingConfiguration` | dados imutáveis da política opcional criada com o modelo |
| `AssetConfiguration` | dados comuns, por equipamento, que serão copiados para o lote |
| `ToolBatchResult` | categoria, modelo, unidades, política e perfis efetivamente criados |
| `_normalize_serial_numbers(...)` | alinha uma posição por equipamento e rejeita repetições no lote |
| `_allocate_asset_codes(...)` | reserva uma faixa contínua e avança a sequência transacional |
| `create_tool_batch(...)` | valida tenant e cria o lote completo dentro de `transaction.atomic` |

O limite atual é 100 equipamentos por operação. `create_tool_batch()` bloqueia a
organização antes de tocar a sequência; por isso `max(asset_code) + 1` e
`ToolUnit.objects.count()` nunca devem ser usados para gerar códigos.

### Formulário e views operacionais

| Elemento | Responsabilidade |
|---|---|
| `AssistedToolRegistrationForm` | filtra relacionamentos pelo tenant e organiza as quatro etapas |
| `assisted_registration()` | usa somente `request.organization` e reporta rollback/conflitos |
| `equipment_list()` | lista exclusivamente equipamentos da locadora ativa |

As etapas visuais são modelo, equipamentos, preços e aquisição. Preço e perfil
patrimonial são opcionais. A confirmação patrimonial é obrigatória antes de copiar
custo, datas, vida útil, fornecedor e documento para todos os equipamentos.

## `pricing`

### `BillingUnit`

Enumeração de unidades aceitas pelo cálculo elementar: `HOUR`, `DAY` e `MONTH`.

### `PricingPolicy`

Representa uma versão de preço para um modelo de ferramenta.

| Elemento | Comportamento |
|---|---|
| `organization` | tenant explícito da política |
| `tool_model` | modelo comercial precificado |
| `effective_from` | primeiro dia da vigência; versão posterior substitui a anterior |
| `hourly_rate`, `daily_rate`, `monthly_rate` | valores opcionais e não negativos |
| `partial_unit_rounding` | arredonda fração para cima ou cobra proporcionalmente |
| `month_definition` | mês com dias fixos ou mês-calendário |
| `fixed_month_days` | quantidade entre 1 e 366; vazia para mês-calendário |
| `active` | permite retirar uma versão da seleção sem apagá-la |
| `clean()` | valida tenant, ao menos um valor e definição de mês |
| `save()` | executa `full_clean()` antes da escrita |

Existe uma única versão por combinação de modelo e data. Não há `valid_until`: para uma
data de referência, a política ativa com maior `effective_from` é a vigente. Isso evita
intervalos sobrepostos e permite agendar uma mudança futura com um novo registro.

### Serviços de preço

| Função/classe | Contrato |
|---|---|
| `select_effective_policy(...)` | seleciona a versão ativa mais recente já vigente |
| `calculate_billable_quantity(...)` | aplica somente a regra de fração à quantidade positiva |
| `calculate_charge(...)` | multiplica a tarifa pela quantidade e retorna duas casas decimais |
| `PricingUnavailable` | informa que a unidade solicitada não possui tarifa |

`calculate_charge()` recebe quantidade já expressa na unidade. Com arredondamento `UP`,
qualquer fração iniciada vira uma unidade inteira; com `PROPORTIONAL`, a fração é
preservada. As funções rejeitam `float`, quantidade não positiva e unidade desconhecida.
Converter datas reais em horas, dias ou meses pertence ao módulo de orçamentos.

## `quotations`

### `Quotation`

Representa o cabeçalho e o ciclo de vida comercial de um orçamento.

| Elemento | Comportamento |
|---|---|
| `organization` | tenant explícito e obrigatório |
| `customer` | cliente protegido contra exclusão enquanto referenciado |
| `starts_at`, `ends_at` | intervalo `[início, fim)`, com duração positiva |
| `status` | `DRAFT`, `SENT`, `EXPIRED` ou `CANCELLED` |
| `total_amount` | soma decimal dos snapshots dos itens |
| `sent_at`, `expired_at`, `cancelled_at` | instante da transição correspondente |
| `display_code` | código amigável `ORC-XXXXXXXX` derivado do UUID |
| `clean()` | rejeita cliente de outro tenant e período inválido |
| `save()` | executa validação do modelo antes de persistir |

O código amigável não é numeração fiscal ou sequência comercial. O UUID continua sendo
a identidade persistente. O orçamento não representa reserva e não altera equipamentos.

### `QuotationItem`

Cada item relaciona um modelo comercial a uma política e preserva o cálculo usado.

| Campo | Snapshot preservado |
|---|---|
| `equipment_quantity` | número de equipamentos iguais solicitado |
| `billing_unit` | hora, dia ou mês escolhido |
| `period_quantity` | quantidade exata convertida a partir do intervalo |
| `billed_quantity` | quantidade após arredondamento da política |
| `unit_rate` | tarifa da unidade no momento do cálculo |
| `line_total` | tarifa × quantidade cobrada × equipamentos |
| `policy_effective_from` | início da vigência selecionada |
| `partial_unit_rounding` | arredondamento para cima ou proporcional |
| `month_definition`, `fixed_month_days` | definição de mês usada |
| `calculation_summary` | memória de cálculo legível para a interface |

O item repete `organization_id` para permitir escopo direto. `clean()` confirma tenant,
modelo e política; constraints exigem quantidades positivas, valores não negativos e
uma única linha por orçamento, modelo e unidade de cobrança.

### Serviços de orçamento

| Elemento | Contrato |
|---|---|
| `QuotationLineInput` | entrada imutável com modelo, quantidade e unidade |
| `PeriodCalculation` | quantidade exata e quantidade efetivamente cobrada |
| `calculate_period(...)` | converte o intervalo para hora, dia, mês fixo ou mês-calendário |
| `save_draft_quotation(...)` | cria/substitui rascunho e snapshots em uma transação |
| `recalculate_draft_quotation(...)` | refaz snapshots existentes somente em `DRAFT` |
| `transition_quotation(...)` | valida disponibilidade no envio, aplica o estado e registra o horário |

`save_draft_quotation()` consulta novamente cliente e modelos dentro do tenant, bloqueia
a política escolhida e substitui os itens somente depois de calcular todas as linhas.
Qualquer erro desfaz cabeçalho, itens e total. A seleção usa a data local do início da
locação; políticas futuras, inativas ou sem a unidade escolhida são recusadas.

Transições permitidas:

- `DRAFT → SENT` ou `DRAFT → CANCELLED`;
- `SENT → EXPIRED` ou `SENT → CANCELLED`;
- `EXPIRED` e `CANCELLED` são terminais neste incremento.

`DRAFT → SENT` só ocorre quando um estabelecimento ativo pode atender, sozinho, todas
as quantidades no período. Essa validação consulta a agenda, mas não bloqueia unidades;
a alocação concorrente definitiva pertence à confirmação da reserva.

### Formulários e views operacionais

| Elemento | Responsabilidade |
|---|---|
| `QuotationForm` | oferece somente clientes ativos da locadora e valida o período |
| `QuotationItemForm` | oferece somente modelos ativos da locadora |
| `QuotationItemFormSet` | aceita de 1 a 20 linhas, inclusive inclusão dinâmica na tela |
| `quotation_list()` | lista somente orçamentos da organização ativa |
| `quotation_create()` / `quotation_edit()` | criam ou substituem apenas rascunhos |
| `quotation_detail()` | apresenta snapshots e memória de cálculo |
| `quotation_recalculate()` | atualiza preços somente enquanto rascunho |
| `quotation_transition()` | executa ações POST explícitas de estado |

Todas as URLs ficam sob `/app/orcamentos/`. Nenhum formulário recebe
`organization_id`; o tenant vem exclusivamente de `request.organization`.

## `reservations`

### `Reservation`

Representa o compromisso temporal confirmado a partir de um orçamento enviado.

| Elemento | Comportamento |
|---|---|
| `organization` | tenant explícito da reserva |
| `quotation` | relação um para um; um orçamento não gera duas reservas |
| `establishment` | unidade responsável por todos os equipamentos separados |
| `starts_at`, `ends_at` | cópia imutável do intervalo `[início, fim)` do orçamento |
| `status` | `CONFIRMED` ou `CANCELLED` |
| `confirmed_at`, `cancelled_at` | instantes das transições |
| `display_code` | código amigável `RES-XXXXXXXX` derivado do UUID |
| `clean()` | valida tenant, período e igualdade com o orçamento |

Uma reserva é persistida somente durante a confirmação transacional. Não existe rascunho
de reserva: o orçamento continua sendo o documento preparatório.

### `ReservationAllocation`

Registra qual unidade física atende qual item do orçamento durante o período reservado.

| Elemento | Comportamento |
|---|---|
| `reservation` | cabeçalho confirmado |
| `quotation_item` | item que solicitou o modelo e a quantidade |
| `tool_unit` | equipamento físico específico alocado |
| `starts_at`, `ends_at` | período repetido para consulta e constraint direta |
| `released_at` | nulo enquanto bloqueia; preenchido no cancelamento |
| `active` | verdadeiro enquanto `released_at` estiver vazio |
| `clean()` | valida tenant, orçamento, modelo, estabelecimento e período |

`unique_tool_unit_per_reservation` impede repetir a unidade dentro da mesma reserva. No
PostgreSQL, `prevent_overlapping_active_reservations` exclui sobreposições da mesma
unidade usando GiST e `TSTZRANGE(..., '[)')`; a condição ignora alocações liberadas.

### Serviços de disponibilidade e reserva

| Elemento | Contrato |
|---|---|
| `ReservationUnavailable` | conflito ou quantidade insuficiente com mensagem operacional |
| `available_units(...)` | filtra tenant, estabelecimento, modelo, estado e sobreposição |
| `available_establishments_for_quotation(...)` | encontra filiais que atendem o orçamento completo |
| `confirm_reservation(...)` | bloqueia, seleciona unidades e grava tudo atomicamente |
| `cancel_reservation(...)` | aplica `CONFIRMED → CANCELLED` e libera alocações |

Disponibilidade considera somente `ToolUnit.status == AVAILABLE`. A confirmação não
muda esse campo, pois a agenda permite períodos futuros não sobrepostos. Uma violação
da exclusão PostgreSQL é traduzida em mensagem para repetir a consulta.

### Formulários e views operacionais

| Elemento | Responsabilidade |
|---|---|
| `AvailabilityForm` | filtra estabelecimento e modelo pelo tenant e valida o período |
| `ReservationConfirmationForm` | oferece estabelecimentos ativos da locadora |
| `reservation_list()` | lista somente reservas da organização ativa |
| `availability_lookup()` | apresenta equipamentos específicos disponíveis |
| `reservation_create()` | confirma orçamento enviado pelo serviço de domínio |
| `reservation_detail()` | apresenta período, filial e equipamentos alocados |
| `reservation_cancel()` | ação POST que libera o período sem apagar histórico |

As URLs ficam sob `/app/reservas/`. O tenant sempre vem de `request.organization`.
Enquanto uma reserva estiver confirmada, `transition_quotation()` rejeita expiração ou
cancelamento do orçamento e orienta a liberar primeiro a reserva.

## `assets`

### `AssetProfile`

Complementa uma unidade física com os dados necessários para gestão patrimonial.
A relação é opcional para manter compatibilidade com unidades já cadastradas, mas,
quando o perfil existe, seus dados essenciais são obrigatórios.

| Elemento | Comportamento |
|---|---|
| `organization` | tenant explícito do perfil |
| `tool_unit` | unidade física associada; relação um para um |
| `acquisition_date` | data de aquisição do ativo |
| `placed_in_service_date` | início da disponibilidade operacional |
| `acquisition_cost` | custo de aquisição não negativo |
| `residual_value` | valor residual não negativo e limitado ao custo |
| `useful_life_months` | estimativa de vida útil positiva, em meses |
| `supplier_name`, `invoice_number`, `notes` | dados complementares opcionais |
| `clean()` | valida tenant, datas e relação entre custo e residual |
| `save()` | executa `full_clean()` antes da escrita |
| `depreciable_amount` | retorna `acquisition_cost - residual_value` |
| `__str__()` | identifica o perfil pelo código patrimonial da unidade |

Constraints de banco repetem as regras numéricas e cronológicas determinísticas.
`depreciable_amount` é somente a base depreciável; não representa uma parcela ou
lançamento de depreciação.

## Administração

As classes de Admin configuram colunas, filtros e pesquisas dos módulos.
`EstablishmentInline` permite editar unidades organizacionais na tela da organização.
`CustomerAddressInline` permite registrar endereços dentro do cliente e seu formset
preenche automaticamente a organização correta. `PricingPolicyInline` permite criar
versões dentro do modelo de ferramenta e também herda a organização.
`AssetProfileInline` permite registrar o perfil patrimonial dentro da unidade física;
seu formset preserva o pai ainda não salvo e atribui o tenant. Os métodos
`display_cnpj()`, `display_document()` e `display_postal_code()` formatam dados sem
mudar a persistência. Orçamentos e itens são somente leitura no Admin: alterações de
período, snapshots e estados devem passar pelos serviços e telas operacionais. Reservas
e alocações também são somente leitura; confirmação e cancelamento pertencem aos
serviços transacionais.

O Admin acelera validação do domínio, mas não é a interface final e ainda não aplica
escopo por organização ao usuário conectado.

## Configuração

`config.settings.base` oferece:

| Função | Responsabilidade |
|---|---|
| `env_bool(name, default)` | converte `1`, `true`, `yes` e `on` em verdadeiro |
| `env_int(name, default)` | lê inteiro e falha com erro de configuração se inválido |
| `env_list(name, default)` | transforma lista separada por vírgulas |
| `required_env(name)` | falha cedo quando a variável está vazia |
| `database_config(...)` | interpreta URL PostgreSQL ou cria configuração SQLite local |

`development` aceita padrões inseguros apenas para a máquina do desenvolvedor. `test`
usa hash de senha rápido e permite PostgreSQL via `DATABASE_URL`. `production` exige
segredo, hosts e PostgreSQL e habilita proteções de HTTPS. `django.contrib.postgres`
fornece a expressão temporal e a constraint usada pelo módulo de reservas.
