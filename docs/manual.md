# Manual de uso

Este manual acompanha a Rental Platform **v0.3.0** e os incrementos já implementados
da **v0.4.0 em desenvolvimento**.
Ele serve tanto para o primeiro teste local quanto para a operação diária dos módulos
de ferramentas, orçamentos e reservas.

## Tecnologia e conhecimento para fortalecer o Brasil

A Rental Platform nasce com a preocupação de transformar desenvolvimento em
conhecimento útil. Por isso, registramos decisões, explicamos os fluxos e compartilhamos
publicamente parte do processo de construção da plataforma. Queremos ajudar estudantes,
profissionais e empreendedores a compreender como tecnologias modernas podem resolver
problemas reais e tornar pequenos e médios negócios mais organizados, seguros e
competitivos.

Nosso compromisso é evoluir com transparência, incentivar a aprendizagem e contribuir
para o fortalecimento da tecnologia e dos negócios no Brasil. Compartilhar conhecimento
não significa abrir mão da autoria ou das regras de uso do projeto: o código continua
sujeito aos termos do arquivo `LICENSE`, enquanto esta documentação busca ampliar o
acesso ao aprendizado gerado durante seu desenvolvimento.

## Rotas rápidas

| Ação | Endereço local |
|---|---|
| Entrar no sistema | `http://localhost:8000/accounts/login/` |
| Área operacional | `http://localhost:8000/app/` |
| Ferramentas | `http://localhost:8000/app/ferramentas/` |
| Cadastrar ferramentas | `http://localhost:8000/app/ferramentas/cadastrar/` |
| Adicionais | `http://localhost:8000/app/adicionais/` |
| Orçamentos | `http://localhost:8000/app/orcamentos/` |
| Disponibilidade | `http://localhost:8000/app/reservas/disponibilidade/` |
| Reservas | `http://localhost:8000/app/reservas/` |
| Contratos | `http://localhost:8000/app/contratos/` |
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

## 5. Cadastrar adicionais e configurações

Use **Adicionais** para transformar variações reais da locação em opções estruturadas.
Elas podem alterar preço, disponibilidade e estoque; observações livres permanecem
separadas e não produzem efeitos automáticos.

| Categoria | Exemplo | Controle operacional |
|---|---|---|
| Configuração | SSD ou memória instalada | pode usar unidade física e exigir preparação |
| Acessório retornável | transformador, bateria ou ponteira | exige código físico e devolução |
| Consumível | disco de corte ou combustível | usa saldo por estabelecimento |
| Serviço | instalação ou entrega | altera valor sem reservar equipamento |
| Remoção com desconto | retirar placa de vídeo | reduz o total por opção autorizada |

Quando a opção for física, cadastre primeiro seu modelo e suas unidades em
**Ferramentas**. Depois:

1. abra **Adicionais > Cadastrar adicional**;
2. informe nome, categoria, descrição e necessidade de preparação;
3. vincule o modelo físico, quando aplicável;
4. escolha os modelos principais compatíveis e a quantidade máxima por equipamento;
5. defina valor único ou preço por hora, dia e mês;
6. para consumível, informe estabelecimento e estoque inicial;
7. salve.

Compatibilidade é explícita: uma bateria de furadeira não aparece automaticamente em
uma serra. Na cobrança por período, a opção acompanha a unidade e a quantidade cobrada
do item principal. Remoções usam o mesmo cálculo como desconto, mas nunca podem tornar
o orçamento negativo.

!!! warning "Remoções precisam ser predefinidas"
    Cadastre somente remoções analisadas como técnica e comercialmente seguras. Não use
    observações livres como desconto. A futura inspeção de saída registrará a composição
    efetivamente entregue.

## 6. Criar um orçamento

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

### Configurar adicionais do item

Depois de salvar o rascunho, abra o orçamento e use **Configurar adicionais** na linha
do produto. Selecione opções compatíveis e informe a quantidade total. A tela separa
valor-base, acréscimos, descontos, total e observações livres.

Cada opção guarda nome, categoria, regra, tarifa, quantidade e total como snapshot.
Editar período ou produtos recalcula opções ainda compatíveis. Observações podem guardar
preferências do cliente, mas não alteram preço, estoque ou obrigação de devolução.

### Enviar ao cliente

O orçamento em rascunho não bloqueia estoque. Ao clicar em **Enviar**, o sistema exige
disponibilidade integral de todos os itens, no mesmo estabelecimento ativo, para o
período informado. Se faltarem unidades, o envio é recusado com uma mensagem clara.

Essa validação reduz propostas impossíveis, mas o bloqueio efetivo acontece somente na
confirmação da reserva. Outra operação concorrente ainda pode ocupar uma unidade entre
essas etapas; por isso a confirmação valida tudo novamente.

## 7. Consultar disponibilidade

Abra **Disponibilidade**, informe início, fim e estabelecimento. O resultado mostra os
modelos e quantidades livres naquele intervalo, considerando:

- condição operacional da unidade;
- estabelecimento escolhido;
- reservas e alocações ativas;
- quantidade física necessária.
- unidades físicas de configurações e acessórios retornáveis;
- saldo disponível dos consumíveis selecionados.

Os períodos usam a regra `[início, fim)`: o instante final não pertence à reserva.
Assim, uma nova locação pode começar exatamente quando a anterior termina.

## 8. Confirmar uma reserva

1. Abra um orçamento com situação **Enviado**.
2. Clique em **Confirmar reserva**.
3. Revise estabelecimento, período, modelos e quantidades.
4. Confirme a operação.

O sistema seleciona unidades físicas aptas e cria as alocações em uma transação. Cada
orçamento gera no máximo uma reserva. No PostgreSQL, uma restrição adicional impede
sobreposição do mesmo equipamento mesmo sob concorrência.

Se não houver disponibilidade completa, nenhuma reserva parcial é criada.
Acessórios retornáveis e configurações físicas recebem códigos específicos. Consumíveis
têm saldo reservado; serviços e remoções são preservados sem movimentar estoque.

## 9. Cancelar corretamente

O cancelamento da reserva libera suas alocações, mas preserva o histórico. Uma reserva
confirmada deve ser cancelada antes de cancelar ou expirar o orçamento relacionado.
Consumíveis reservados também voltam ao saldo disponível sem reduzir o estoque físico.

Ordem recomendada:

1. abra a reserva;
2. clique em **Cancelar reserva**;
3. confirme que as alocações foram liberadas;
4. se necessário, volte ao orçamento e cancele-o.

## 10. Contrato, retirada e devolução

!!! info "Incremento da v0.4.0 em desenvolvimento"
    O ciclo contratual é a primeira capacidade planejada após a v0.3.0. Ele preserva
    orçamento e reserva e não representa cobrança ou pagamento.

### Preparar o contrato

1. abra uma reserva confirmada;
2. clique em **Preparar contrato**;
3. confira cliente, documento, período, valor e equipamentos;
4. confirme que cada código físico corresponde ao que será entregue.

Cada reserva gera no máximo um contrato. O sistema grava snapshots do cliente, valor e
equipamentos para que futuras alterações cadastrais não reescrevam esse histórico.
Depois da criação do contrato, a reserva não pode mais ser cancelada.

### Registrar a retirada

Na página do contrato, clique em **Confirmar retirada**. Todos os equipamentos são
movimentados em uma única transação:

- o contrato passa de **Preparado** para **Em andamento**;
- cada item registra data, hora e usuário responsável;
- as unidades físicas passam para **Alugada**;
- qualquer erro desfaz a retirada inteira.

Na mesma transação, consumíveis são baixados do saldo e acessórios físicos passam para
**Alugada**. Esses acessórios aparecem entre os itens que precisam ser devolvidos.

### Registrar devoluções

Cada equipamento possui seu próprio formulário. Escolha a condição observada, registre
as observações necessárias e confirme a devolução daquela unidade.

| Condição | Efeito operacional |
|---|---|
| Apta para locação | volta a participar de novas consultas de disponibilidade |
| Em inspeção | aguarda uma verificação antes de nova locação |
| Em manutenção | fica indisponível até o reparo |
| Danificada | preserva a avaria como condição atual |
| Perdida | fica indisponível e registra a ocorrência no contrato |

A devolução parcial libera somente a unidade devolvida e mantém o contrato em andamento.
Quando o último equipamento retorna, o contrato é concluído automaticamente. As
alocações permanecem no histórico, com o instante em que foram liberadas.

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

### Contrato

| Situação | Significado |
|---|---|
| Preparado | aguarda conferência e retirada integral |
| Em andamento | equipamentos retirados; aceita devoluções parciais |
| Concluído | todas as unidades foram devolvidas |

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
Confira também acessórios físicos e saldo de consumíveis selecionados.

### Um adicional não aparece no orçamento

Confirme se está ativo, possui preço vigente, é compatível com o modelo principal e
respeita a quantidade máxima configurada.

### Não consigo cancelar um orçamento reservado

Cancele primeiro a reserva confirmada. Depois, cancele ou expire o orçamento.

## Segurança e limites

- mantenha `.env.docker` e chaves fora do Git;
- não exponha o Admin como interface comum;
- use PostgreSQL nos ambientes compartilhados e de produção;
- mantenha migrations aplicadas junto com cada atualização;
- confirme a organização ativa antes de operar dados sensíveis;
- não trate orçamento como contrato ou pagamento.
- não use observações para substituir opções com efeito financeiro ou de estoque;
- cadastre remoções somente após validar a configuração mínima funcional.

Inspeções detalhadas antes e depois da locação, evidências, cobrança, pagamentos,
assinatura eletrônica, renovação e cálculo automático de avarias ainda não fazem parte
deste incremento. A interface tradicional continuará sendo a fonte operacional mesmo
quando um assistente de IA for adicionado futuramente.
