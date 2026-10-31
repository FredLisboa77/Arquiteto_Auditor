# CLAUDE.md — Regras permanentes do projeto Arquiteto Auditor

Software local de apoio à conferência de projetos arquitetônicos (casas de até 2 pavimentos em condomínio horizontal, Brasil). Lê PDFs (pranchas, matrícula, escritura, memorial, leis, normas de condomínio), compara valores e gera relatório versionado (R00, R01…) para o autor do projeto.

Documentação de referência: `docs/01-viabilidade.md` · `docs/02-mvp.md` · `docs/03-arquitetura.md` · `docs/04-plano-de-fases.md` · `docs/05-avaliacao.md`.

---

## 1. Forma de trabalho (obrigatória)

- **Só avançar de fase com aprovação explícita do usuário.** Ao fim de cada fase: mostrar o que foi feito, como testar (passo a passo), saída dos testes, limitações conhecidas — e **parar e esperar**.
- Não começar tarefas de uma fase futura "para adiantar".
- O usuário é **iniciante** em programação e IA: escrever tudo em **português do Brasil**, explicar termos técnicos na primeira vez em que aparecem, preferir soluções simples e legíveis a soluções "espertas".
- Sessões de ~2 h: dividir o trabalho em passos pequenos, cada um terminando num estado que funciona e com testes passando.
- Commit e push **só com autorização** do usuário. Mensagens de commit em português.
- Ao concluir uma fase, marcar no `docs/04-plano-de-fases.md`.

## 2. Privacidade e dados pessoais (LGPD) — regra mais importante

- **Documentos reais nunca entram no repositório** (público). Eles ficam em `dados_privados/` (ignorada pelo Git).
- **Antes de CADA commit:** rodar `git status` e `git diff --cached --name-only`, conferir a lista e confirmar que não há PDF/imagem/DOCX fora de `dados_sinteticos/` ou `tests/fixtures/`, nada de `dados_privados/`, nenhum `.db`/`.sqlite`, nenhum arquivo grande. O gancho *pre-commit* (Fase 1) faz isso automaticamente — **nunca** usar `--no-verify` nem `git add -f` em arquivos ignorados.
- Não ler o conteúdo de `dados_privados/` sem pedido explícito do usuário. Para documentos reais, preferir scripts que mostram **apenas estatísticas agregadas**.
- Nunca copiar trechos de documentos reais para código, testes, *prompts*, documentação, mensagens de commit ou issues.
- Todo processamento é **local**: nenhuma chamada a APIs/serviços externos com conteúdo de documentos. Ollama só em `127.0.0.1`. Interface só em `127.0.0.1`.
- Logs não gravam conteúdo de documentos.
- O relatório contém apenas os dados necessários para identificar imóvel e projeto (nunca CPF, RG, estado civil, filiação de proprietários).
- Base sintética: apenas dados fictícios (Faker `pt_BR`); nunca derivar dados sintéticos de documentos reais.

## 3. Princípios técnicos

1. **Ferramenta de apoio:** a responsabilidade técnica é dos profissionais (RRT/CAU). Todo relatório exibe esse aviso.
2. **Cálculos e comparações são código determinístico.** O LLM nunca calcula, compara ou decide "atende/não atende". O LLM só: classifica/interpreta texto, extrai com **citação literal**, redige explicações a partir de números já calculados.
3. **Nenhuma conclusão sem evidência rastreável:** todo valor carrega `Evidencia` (arquivo, página/prancha, bbox, trecho) e `confianca`. Item sem evidência → "não foi possível verificar".
4. **Anti-alucinação:** saída do LLM sempre em JSON validado por esquema; o código confere que o trecho citado existe no texto-fonte e contém o número; números são relidos do trecho pelo código. Falhou → descarta ou marca pendente.
5. **Baixa confiança é visível:** OCR com baixa confiança, associação incerta, parâmetro ambíguo e dado não encontrado vão para a tela de confirmação antes do relatório final.
6. **Na dúvida, não afirmar:** preferir "pendente de confirmação" / "não foi possível verificar" a um falso "atende".
7. **Prefeitura × condomínio:** adotar o mais restritivo e sinalizar.
8. **Fórmulas:** usar a da lei quando encontrada; senão a padrão de `formulas.toml`, declarada no relatório.
9. **O software nunca altera documentos de entrada.**
10. **Ferramentas gratuitas e de código aberto**; algo pago só com justificativa e alternativa gratuita ao lado. Licença do projeto: **AGPL-3.0** — dependências precisam ser compatíveis.
11. Tudo precisa caber no hardware: RTX 2060 6 GB VRAM, 16 GB RAM. LLM padrão: `qwen2.5:7b-instruct-q4_K_M` via Ollama, temperatura 0.
12. Escolhas compatíveis com **PyInstaller** (evitar dependências que exigem bibliotecas de sistema, ex.: GTK).
13. Chaves estáveis de itens de verificação (`RECUO_FRONTAL`, `TO_MAX`…) — **não renomear** sem migração, pois o versionamento R00→R01 depende delas.
14. Relatórios emitidos são imutáveis.

## 4. Código

- Python **3.11**, ambiente virtual `.venv` na raiz. Código em `src/arquiteto_auditor/`, testes em `tests/`.
- Nomes de módulos, classes e variáveis do domínio em **português** (sem acentos em identificadores); comentários em português.
- Arquitetura em camadas (ver `docs/03-arquitetura.md`): a interface só chama `servicos/`; `dominio/` não depende de nada externo.
- Todo código novo vem com testes (`pytest`). Rodar `pytest` e `ruff check` antes de declarar algo pronto e mostrar a saída.
- Regras de extração não podem "decorar" valores de conjuntos sintéticos específicos; conjuntos reservados para avaliação não são usados no desenvolvimento.
- *Prompts* do LLM ficam em arquivos versionados em `src/arquiteto_auditor/llm/prompts/`, nunca espalhados no código.
- Números brasileiros ("1.234,56") sempre pelo normalizador único.

## 5. Estrutura de pastas

```
.
├── CLAUDE.md, README.md, LICENSE (AGPL-3.0), .gitignore
├── docs/                     documentação do projeto
├── src/arquiteto_auditor/    código da aplicação
├── tests/                    testes automáticos (fixtures só sintéticas)
├── dados_sinteticos/         base fictícia — PODE ir para o Git
│   ├── geradores/            scripts que geram a base
│   └── projetos/             conjuntos gerados + gabarito.json
├── scripts/                  utilitários (avaliação, anti-vazamento, diagnóstico)
├── modelos/                  modelos de IA/OCR — NÃO vai para o Git
└── dados_privados/           documentos reais, gabarito real, histórico, relatórios — NUNCA vai para o Git
```
