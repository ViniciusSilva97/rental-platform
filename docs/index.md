# Rental Platform

<div class="hero" markdown>

## Gestão de locações com regras claras e histórico preservado

A versão **0.3.0** reúne cadastro assistido de equipamentos, preços versionados,
orçamentos reproduzíveis, disponibilidade por período e reservas sem conflito.

[Começar pelo manual](manual.md){ .md-button .md-button--primary }
[Ver no GitHub](https://github.com/ViniciusSilva97/rental-platform){ .md-button }

</div>

!!! info "GitHub Pages publica a documentação"
    Este endereço não executa o sistema Django. Para utilizar a aplicação, siga a
    instalação local ou implante o backend, o PostgreSQL e os arquivos estáticos em
    uma infraestrutura apropriada.

## Fluxo principal

<div class="feature-grid" markdown>

<div class="feature-card" markdown>

### 1. Prepare a locadora

No primeiro acesso, crie a organização e sua matriz. A organização ativa delimita
todos os dados operacionais.

</div>

<div class="feature-card" markdown>

### 2. Cadastre ferramentas

Crie modelo, preço e várias unidades físicas de uma vez. Os códigos `EQ-000001` são
gerados automaticamente.

</div>

<div class="feature-card" markdown>

### 3. Monte o orçamento

Escolha cliente, período, ferramentas e quantidades. Tarifas e cálculo ficam gravados
como snapshot histórico.

</div>

<div class="feature-card" markdown>

### 4. Confirme a reserva

O envio valida disponibilidade integral. A confirmação aloca as unidades sem permitir
sobreposição de agenda.

</div>

</div>

## Encontre o que precisa

| Necessidade | Documento |
|---|---|
| Instalar e operar o sistema | [Manual de uso](manual.md) |
| Configurar Docker e produção | [Operação e implantação](operations.md) |
| Entender módulos e limites | [Arquitetura](architecture.md) |
| Localizar serviços e modelos | [Referência do código](code-reference.md) |
| Conhecer as decisões técnicas | [Decisões](decisions.md) |
| Contribuir com segurança | [Fluxo de desenvolvimento](development-workflow.md) |
| Conferir o escopo publicado | [Versão 0.3.0](versions/v0.3.0.md) |

## O que a v0.3.0 já faz

- isola os registros por locadora e organização ativa;
- cadastra lotes de equipamentos de forma atômica;
- mantém políticas de preço versionadas;
- cria orçamentos com cálculo por hora, dia ou mês;
- bloqueia o envio quando não há disponibilidade integral;
- confirma reservas com equipamentos físicos específicos;
- libera a agenda ao cancelar, sem apagar o histórico;
- diferencia condição operacional da agenda de locação.

## Em desenvolvimento para a v0.4.0

- prepara contratos a partir de reservas confirmadas;
- registra a retirada de todos os equipamentos de forma atômica;
- permite devoluções parciais, com condição individual por equipamento.

## Limites desta versão

A v0.3.0 ainda não possui telas operacionais para cadastro de clientes, contratos,
retirada, devolução, inspeção ou pagamentos. O cadastro de clientes é feito pelo Admin
técnico. O [manual](manual.md) deixa esses limites explícitos para não confundir funções
atuais com funcionalidades planejadas.

## Documentação como parte do produto

Toda mudança de domínio, operação ou arquitetura deve atualizar estes documentos no
mesmo Pull Request. O site é compilado em modo estrito pela CI e publicado
automaticamente após o merge na `main`.

O código-fonte está disponível sob os termos descritos no arquivo `LICENSE` do
repositório.
