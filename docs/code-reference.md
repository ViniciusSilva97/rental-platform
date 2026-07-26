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
uma matriz ativa. Uma organização pode existir temporariamente sem matriz; a camada de
onboarding deverá criar ambas em uma única transação.

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
| `daily_rate` | diária não negativa da fase inicial |
| `deposit_amount` | caução não negativa |
| `clean()` | rejeita categoria de outra organização |
| `save()` | chama `full_clean()` antes de persistir |
| `__str__()` | combina marca, nome e modelo, omitindo partes vazias |

A unicidade composta evita duplicar a mesma combinação de nome, marca e modelo na
organização. `daily_rate` é provisório; a versão de preços migrará esse valor para uma
política versionada sem perder dados.

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

## Administração

As classes de Admin configuram colunas, filtros e pesquisas dos módulos.
`EstablishmentInline` permite editar unidades organizacionais na tela da organização.
`CustomerAddressInline` permite registrar endereços dentro do cliente e seu formset
preenche automaticamente a organização correta. Os métodos `display_cnpj()`,
`display_document()` e `display_postal_code()` formatam dados sem mudar a persistência.

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
segredo, hosts e PostgreSQL e habilita proteções de HTTPS.
