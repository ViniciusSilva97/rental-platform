# Documentação técnica

Esta documentação acompanha o código por versão. Ela serve como material de estudo,
referência de manutenção e contexto confiável para ferramentas de IA.

| Documento | Conteúdo |
|---|---|
| [architecture.md](architecture.md) | limites, dependências e fluxos da aplicação |
| [code-reference.md](code-reference.md) | classes, funções, validações e responsabilidades |
| [operations.md](operations.md) | execução local, Docker, produção, CI e observabilidade |
| [decisions.md](decisions.md) | decisões arquiteturais e seus motivos |
| [versions/v0.1.0.md](versions/v0.1.0.md) | escopo, auditoria e pendências da versão |
| [versions/v0.2.0.md](versions/v0.2.0.md) | clientes, endereços e auditoria do incremento |
| [versions/v0.2.1.md](versions/v0.2.1.md) | preços versionados e migração da diária legada |
| [versions/v0.2.2.md](versions/v0.2.2.md) | base patrimonial por unidade física |
| [ai-context.md](ai-context.md) | contexto compacto e regras para assistência por IA |

## Política de documentação por versão

Ao fechar uma versão:

1. registre o comportamento entregue e as migrations;
2. atualize a referência das classes e funções modificadas;
3. registre decisões novas e alternativas descartadas;
4. liste limitações e correções candidatas, sem escondê-las;
5. execute e anote as verificações automatizadas;
6. defina o próximo incremento sem misturá-lo à versão encerrada.

Documentos descrevem o comportamento esperado, mas o código e os testes são a
referência executável. Divergências devem ser tratadas como defeitos.
