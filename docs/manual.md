# Manual de uso

Este manual acompanha o fluxo realmente disponível na Rental Platform **v0.3.0**.
Ele serve tanto para o primeiro teste local quanto para a operação diária dos módulos
de ferramentas, orçamentos e reservas.

## Rotas rápidas

| Ação | Endereço local |
|---|---|
| Entrar no sistema | `http://localhost:8000/accounts/login/` |
| Área operacional | `http://localhost:8000/app/` |
| Ferramentas | `http://localhost:8000/app/ferramentas/` |
| Cadastrar ferramentas | `http://localhost:8000/app/ferramentas/cadastrar/` |
| Orçamentos | `http://localhost:8000/app/orcamentos/` |
| Disponibilidade | `http://localhost:8000/app/reservas/disponibilidade/` |
| Reservas | `http://localhost:8000/app/reservas/` |
| Administração técnica | `http://localhost:8000/admin/` |

## 1. Preparar uma máquina nova

### Criar a configuração do Docker

Na raiz do projeto, copie o modelo de ambiente:

=== "PowerShell"

    ```powershell
    Copy-Item .env.docker.example .env.docker
    ```

=== "Linux ou macOS"

    ```bash
    cp .env.docker.example .env.docker
    ```

O arquivo `.env.docker` é local e não deve ser enviado ao GitHub. Para desenvolvimento,
revise ao menos a chave do Django, hosts e credenciais do PostgreSQL antes de iniciar.

### Construir, migrar e criar o usuário

```powershell
docker compose up -d --build
docker compose exec web python manage.py migrate
docker compose exec web python manage.py createsuperuser
```

Em uma máquina nova, o banco e os volumes também são novos. Portanto, normalmente será
necessário criar o superusuário novamente. A senha digitada não aparece no terminal.

Abra `http://localhost:8000/accounts/login/` e entre com esse usuário.

## 2. Primeiro acesso e locadora ativa

Se o usuário autenticado ainda não possui uma organização, o sistema abre o onboarding.
Informe o nome da locadora e os dados da unidade matriz. Em uma única operação são
criados:

- a organização;
- o estabelecimento matriz;
- o vínculo do usuário como proprietário.

Depois disso, `request.organization` passa a representar a locadora ativa. Formulários
operacionais não aceitam um `organization_id` escolhido livremente: essa proteção evita
que uma locadora consulte ou modifique dados de outra.

## 3. Cadastrar um cliente

!!! warning "Fluxo técnico temporário"
    A v0.3.0 ainda não possui uma tela operacional de clientes. Use o Django Admin
    somente com um usuário autorizado e escolha manualmente a organização correta.

1. Acesse `http://localhost:8000/admin/`.
2. Entre em **Customers > Clientes**.
3. Clique em **Adicionar cliente**.
4. Selecione a mesma organização usada na área operacional.
5. Escolha pessoa física ou jurídica.
6. Informe nome, CPF ou CNPJ e os contatos desejados.
7. Salve o registro.

Documentos são armazenados sem máscara e precisam ser válidos para o tipo escolhido.
Dentro de uma organização, o mesmo documento não pode ser repetido.

O Admin não aplica automaticamente o contexto da locadora ativa. Não o disponibilize
como painel de uso comum para atendentes; ele é uma ferramenta administrativa.

## 4. Cadastrar ferramentas

Acesse **Ferramentas > Cadastrar ferramentas**. O fluxo assistido reúne quatro decisões:

1. **Modelo comercial:** nome, categoria, fabricante e descrição.
2. **Preço:** valor por hora, dia e/ou mês; ao menos uma tarifa é necessária quando a
   política for criada.
3. **Lote físico:** quantidade de 1 a 100 unidades e números de série opcionais.
4. **Patrimônio:** aquisição, custo, valor residual e entrada em operação, todos
   opcionais conforme o caso.

Ao confirmar, o sistema cria todo o lote em uma única transação. Os códigos internos
seguem a sequência da locadora, como `EQ-000001`, `EQ-000002` e `EQ-000003`. Se qualquer
registro for inválido, nada do lote é gravado e a sequência não avança.

### Condição operacional e agenda

São informações diferentes:

| Informação | Exemplo | Significado |
|---|---|---|
| Condição operacional | Disponível | A ferramenta está apta para locação |
| Agenda | Reservada de 10 a 12/09 | A unidade está ocupada naquele intervalo |

Por isso, uma unidade reservada pode continuar com condição **Disponível** na tela de
ferramentas. Isso não significa que sua agenda esteja livre. Consulte a disponibilidade
para o período desejado. Unidades em manutenção, aposentadas ou perdidas não podem ser
alocadas.

## 5. Criar um orçamento

1. Abra **Orçamentos > Novo orçamento**.
2. Escolha o cliente.
3. Informe início e fim do período.
4. Selecione o modelo e a quantidade.
5. Salve como rascunho.

O fim precisa ser posterior ao início. O sistema converte o período conforme a política
vigente e grava no item a tarifa, a quantidade exata, a quantidade cobrada, a política
utilizada e o total. Alterar preços no futuro não muda um orçamento histórico.

### Por que aparece “Item 1”?

Cada item representa **um produto diferente** no orçamento. A quantidade do mesmo
modelo deve ser informada na própria linha. O formulário começa apenas com o Item 1;
use **Adicionar outra ferramenta** somente quando o cliente quiser outro modelo.

Exemplo: três furadeiras e duas serras formam dois itens, não cinco:

| Item | Modelo | Quantidade |
|---|---|---:|
| 1 | Furadeira | 3 |
| 2 | Serra circular | 2 |

Enquanto estiver em rascunho, o orçamento pode ser editado e recalculado. Depois do
envio, seus itens e valores ficam imutáveis.

### Enviar ao cliente

O orçamento em rascunho não bloqueia estoque. Ao clicar em **Enviar**, o sistema exige
disponibilidade integral de todos os itens, no mesmo estabelecimento ativo, para o
período informado. Se faltarem unidades, o envio é recusado com uma mensagem clara.

Essa validação reduz propostas impossíveis, mas o bloqueio efetivo acontece somente na
confirmação da reserva. Outra operação concorrente ainda pode ocupar uma unidade entre
essas etapas; por isso a confirmação valida tudo novamente.

## 6. Consultar disponibilidade

Abra **Disponibilidade**, informe início, fim e estabelecimento. O resultado mostra os
modelos e quantidades livres naquele intervalo, considerando:

- condição operacional da unidade;
- estabelecimento escolhido;
- reservas e alocações ativas;
- quantidade física necessária.

Os períodos usam a regra `[início, fim)`: o instante final não pertence à reserva.
Assim, uma nova locação pode começar exatamente quando a anterior termina.

## 7. Confirmar uma reserva

1. Abra um orçamento com situação **Enviado**.
2. Clique em **Confirmar reserva**.
3. Revise estabelecimento, período, modelos e quantidades.
4. Confirme a operação.

O sistema seleciona unidades físicas aptas e cria as alocações em uma transação. Cada
orçamento gera no máximo uma reserva. No PostgreSQL, uma restrição adicional impede
sobreposição do mesmo equipamento mesmo sob concorrência.

Se não houver disponibilidade completa, nenhuma reserva parcial é criada.

## 8. Cancelar corretamente

O cancelamento da reserva libera suas alocações, mas preserva o histórico. Uma reserva
confirmada deve ser cancelada antes de cancelar ou expirar o orçamento relacionado.

Ordem recomendada:

1. abra a reserva;
2. clique em **Cancelar reserva**;
3. confirme que as alocações foram liberadas;
4. se necessário, volte ao orçamento e cancele-o.

## Situações disponíveis

### Orçamento

| Situação | Pode editar? | Pode gerar reserva? |
|---|---:|---:|
| Rascunho | Sim | Não |
| Enviado | Não | Sim |
| Expirado | Não | Não |
| Cancelado | Não | Não |

### Reserva

| Situação | Efeito na agenda |
|---|---|
| Confirmada | Mantém as unidades alocadas |
| Cancelada | Libera as unidades e preserva o histórico |

## Solução de problemas

### `.env.docker not found`

Crie o arquivo a partir do exemplo e reinicie:

```powershell
Copy-Item .env.docker.example .env.docker
docker compose up -d --build
```

### `relation "reservations_reservation" does not exist`

O código está mais novo que o banco. Aplique as migrations:

```powershell
docker compose exec web python manage.py migrate
```

Confira o estado, se necessário:

```powershell
docker compose exec web python manage.py showmigrations
```

### Não consigo entrar depois de mudar de máquina

Crie um usuário no banco novo:

```powershell
docker compose exec web python manage.py createsuperuser
```

### O cliente não aparece no orçamento

Confirme no Admin se ele está ativo e pertence à mesma organização do usuário.

### O orçamento não pode ser enviado

Consulte a disponibilidade para o mesmo período, estabelecimento e quantidades. Uma
ferramenta pode estar operacionalmente disponível e ainda assim ocupada na agenda.

### Não consigo cancelar um orçamento reservado

Cancele primeiro a reserva confirmada. Depois, cancele ou expire o orçamento.

## Segurança e limites

- mantenha `.env.docker` e chaves fora do Git;
- não exponha o Admin como interface comum;
- use PostgreSQL nos ambientes compartilhados e de produção;
- mantenha migrations aplicadas junto com cada atualização;
- confirme a organização ativa antes de operar dados sensíveis;
- não trate orçamento como contrato ou pagamento.

Contratos, retirada, devolução, inspeção, cobrança e pagamentos ainda não fazem parte da
v0.3.0. A interface tradicional continuará sendo a fonte operacional mesmo quando um
assistente de IA for adicionado futuramente.
