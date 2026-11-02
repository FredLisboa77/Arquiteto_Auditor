# 04 — Plano de fases

> Cada **sessão** ≈ 2 horas de trabalho (você + Claude Code). As estimativas são aproximadas; o que manda é o **critério de aceite**.
>
> **Regra:** só avançamos de fase com **sua aprovação explícita**. No fim de cada fase eu apresento: o que foi feito, como testar (passo a passo) e o resultado dos testes.

---

## Visão geral

| Fase | Nome | Sessões | Entregável principal |
|---|---|---|---|
| 0 | Planejamento | — | Estes documentos, `CLAUDE.md`, `.gitignore`, pastas ✅ |
| 1 | Ambiente e proteção | 1–2 | `pip` funcionando, Tesseract, esqueleto do projeto, anti-vazamento, repositório no GitHub ✅ (30/10/2026) |
| 2 | Modelo de dados e gabarito | 2–3 | Classes de domínio + formato JSON do gabarito + normalizador de números ✅ (30/10/2026) |
| 3 | Base sintética I — pranchas | 3–4 | Gerador de pranchas vetoriais variadas + diagnóstico dos PDFs reais ✅ (30/10/2026) |
| 4 | Base sintética II — escaneados, memoriais, leis, revisões | 3–4 | Matrículas/escrituras "escaneadas", memoriais, leis, normas, conjunto R00/R01 ✅ (31/10/2026) |
| 5 | Ingestão e OCR | 2–3 | Qualquer PDF → páginas com palavras, coordenadas e confiança |
| 6 | Extração das pranchas | 4–6 | Carimbo, quadro de áreas, recuos rotulados, identificação |
| 7 | Extração de matrícula, escritura e memorial | 3–5 | Estado atual do imóvel com averbações; dados do memorial |
| 8 | Extração de parâmetros (LLM) | 4–6 | Parâmetros da zona com trecho e página, hierarquia prefeitura > condomínio |
| 9 | Motor de verificação | 2–3 | Itens classificados com margem e quantidade sugerida |
| 10 | Interface I — análise e confirmação | 3–4 | Upload, progresso, pendências com recorte da página |
| 11 | Relatório (tela, PDF, DOCX) | 3–4 | Relatório R00 exportável |
| 12 | Versionamento R00 → R01 | 2–3 | Mesmo projeto, comparação, histórico |
| 13 | Avaliação e ajuste fino | 2–4 | Métricas na base sintética e no gabarito real |
| 14 | Empacotamento (executável + instalador) | 2–4 | `ArquitetoAuditor-Setup.exe` |
| | **Total estimado** | **~36–55 sessões** | ≈ 2 a 3 meses a 2 h/dia útil |

A base sintética vem **cedo (fases 3–4)** porque todo o resto é testado contra ela. Os testes automáticos rodam desde a Fase 2.

---

## Fase 1 — Ambiente e proteção
**Objetivo:** ter um ambiente que funciona e que é impossível vazar dados por engano.

**Tarefas**
1. Diagnosticar e corrigir o erro SSL do `pip`.
2. Instalar Tesseract com português; mover modelos do Ollama para o D: (opcional, recomendado).
3. Criar `pyproject.toml`, pacote `src/arquiteto_auditor/` vazio, `config.exemplo.toml`, `README.md`.
4. Configurar `pytest` e `ruff`; um teste "olá mundo" passa.
5. Configurar **pre-commit** com verificação anti-vazamento (bloqueia PDF/imagem/DOCX fora de `dados_sinteticos/` e `tests/fixtures/`, arquivos > 5 MB, padrões de CPF, qualquer coisa em `dados_privados/`).
6. Script `scripts/verificar_ambiente.py`: confere Python, Tesseract (`por`), Ollama e modelo, GPU.
7. Primeiro commit e criação do repositório público no GitHub (**com sua confirmação**).

**Critérios de aceite** — concluída em 30/10/2026
- [x] `pip install` funciona sem flags especiais (pip 26 usa os certificados do Windows; causa do erro: Norton 360).
- [x] O Tesseract lista `por` (em `modelos/tessdata/`).
- [x] `python scripts/verificar_ambiente.py` mostra tudo verde.
- [x] `pytest` passa (10 testes).
- [x] **Teste de vazamento:** PDFs falsos em `dados_privados/` e na raiz, forçados com `git add -f` → commit **bloqueado** com mensagem clara.
- [x] O repositório `FredLisboa77/Arquiteto_Auditor` contém apenas os 20 arquivos esperados.

---

## Fase 2 — Modelo de dados, gabarito e números brasileiros
**Objetivo:** definir a "linguagem comum" de todo o sistema.

**Tarefas**
1. Classes de domínio (`Evidencia`, `ValorExtraido`, `Parametro`, `ItemVerificacao`, `Rodada`, `Relatorio`…) com Pydantic.
2. Catálogo de chaves de verificação (tabela da `02-mvp.md` §4) em arquivo.
3. Esquema JSON do **gabarito** (erros esperados por conjunto) + validador.
4. Normalizador de números/unidades brasileiros.

**Critérios de aceite**
- [x] ≥ 40 testes do normalizador passam (68 testes, em `tests/test_numeros.py`).
- [x] Um gabarito de exemplo valida; um gabarito com erro de formato é rejeitado com mensagem compreensível.
- [x] Você revisa e aprova a lista de chaves (`src/arquiteto_auditor/dominio/catalogo.toml`) e o formato do gabarito (`docs/esquemas/exemplo_gabarito.json`).

---

## Fase 3 — Base sintética I: pranchas vetoriais
**Objetivo:** pranchas fictícias realistas e variadas, com gabarito.

**Tarefas**
1. Gerador de prancha com componentes intercambiáveis: ≥ 4 estilos de carimbo, ≥ 4 estilos de quadro de áreas (tabela com linhas, texto solto, colunas invertidas, unidades no cabeçalho), cotas com e sem rótulo, tamanhos A1/A2/A3, rotação de texto, camadas que imitam a saída do AutoCAD (e variações "estilo Revit/ArchiCAD/LayOut").
2. Plantas de situação/localização simplificadas com cotas de recuo e testadas.
3. Injeção de erros configurável (ex.: área do quadro ≠ soma dos pavimentos; revisão diferente numa prancha; matrícula errada no carimbo). Também **omissões**: cota essencial ausente ou só gráfica, Norte ausente, proprietário ausente no carimbo, campo de assinatura vazio, PDF com assinatura digital íntegra e PDF com assinatura digital "quebrada" (alterado após assinar), e altura de muro acima do limite.
4. Gera `gabarito.json` junto.
5. **Diagnóstico dos PDFs reais** (`scripts/diagnosticar_pdfs.py`): roda na sua máquina e mostra **apenas estatísticas** (nº de páginas, % de texto extraível, fontes usadas, se há texto como geometria) — sem conteúdo. Mitiga o risco R1.

**Critérios de aceite**
- [x] ≥ 6 conjuntos de pranchas com layouts visivelmente diferentes (8 gerados, conferidos pelo usuário; realismo ampliado após a crítica dele: paredes, esquadrias, escada, cobertura, passeio, cotas encadeadas, distrações numéricas).
- [x] O texto das pranchas é selecionável e os acentos e o "m²" saem corretos (fonte TrueType embutida, verificado por teste).
- [x] Cada conjunto tem gabarito válido (verificado por teste).
- [x] Diagnóstico dos reais executado. O R1 se confirmou em parte: há texto SHX em traços, mas recuperável pelos comentários do PDF (docs/01-viabilidade.md §6.1).
- [x] Extra: mascaramento (`scripts/mascarar_pdf.py`) e calibração com 2 exemplos reais (docs/06-calibracao-exemplos-reais.md).

---

## Fase 4 — Base sintética II: escaneados, memoriais, leis e revisões
**Tarefas**
1. Matrículas fictícias com abertura + 2 a 6 atos (R-1 venda, AV-2 retificação de área, AV-3 construção…), renderizadas como imagem com fonte de máquina de escrever, ruído, inclinação (±3°), carimbos, selos e "assinaturas" sobrepostos (Augraphy), em 3 níveis de qualidade.
2. Escrituras fictícias no mesmo padrão.
3. Memoriais (texto selecionável **e** versão escaneada).
4. ≥ 2 "leis municipais" fictícias completas (20–60 páginas, com zonas, tabela de parâmetros em anexo, exceções) e ≥ 2 regulamentos de condomínio, com valores conflitantes de propósito.
5. **Projeto com R00 e R01** (R01 corrige parte dos erros, mantém outros e introduz 1 novo).
6. Pelo menos 1 conjunto "limpo" (sem erros) para medir falsos alarmes.
7. Variações vindas da calibração com exemplos reais (docs/06-calibracao-exemplos-reais.md §4):
   - texto em comentários (SHX) e texto como traços;
   - carimbo e quadro de áreas com valores em comentários e rótulos quebrados;
   - ponto decimal, notação `A=`/`H=`/`C=` e códigos `%%%`;
   - recuos sem rótulo;
   - `MURO H=`;
   - lotes vizinhos com área;
   - rosa dos ventos girada, com "E";
   - folha "N de M";
   - capa e folhas sem texto;
   - revisão em branco.

**Critérios de aceite** — concluída em 31/10/2026
- [x] ≥ 8 conjuntos completos, todos com gabarito válido (16 conjuntos: pranchas, matrícula, escritura, memorial, lei municipal e norma do condomínio; sint-009 → sint-010 em R00 → R01; 4 reservados para avaliação; calibração com 7 documentos reais vistos só mascarados — docs/06).
- [x] Nenhum dado real: nomes/números gerados pelo Faker; `scripts/verificar_base_sintetica.py` confirma que nenhum CPF ou CNPJ válido aparece (texto, comentários dos PDFs e texto dos escaneados).
- [x] Você aprova a "cara" dos escaneados (aprovada após recalibração com uma escritura e uma certidão de inteiro teor reais, vistas só em versão mascarada — `scripts/mascarar_escaneado.py`, docs/06 §5).

---

## Fase 5 — Ingestão e OCR
**Critérios de aceite** — concluída em 01/11/2026 (`scripts/avaliar_ingestao.py`, conjuntos de desenvolvimento)
- [x] Classifica vetorial × escaneado corretamente em 100% das páginas sintéticas (405/405).
- [x] Classifica o tipo de documento corretamente em ≥ 95% dos sintéticos (83/83).
- [x] OCR das matrículas sintéticas de qualidade média com taxa de erro de caracteres (CER) ≤ 3%: 1,4% de "texto errado" (critério definido pelo usuário — docs/05 §3.3); o CER bruto (7,5%) inclui carimbos, selo e "CÓPIA", que a verdade exclui.
- [x] Cada palavra tem bbox e confiança; resultados em cache (segunda execução < 2 s: lei de 23 páginas em ~1 s).
- Limitação conhecida: matrícula de qualidade "ruim" com 41% de texto errado (meta de ≤ 8% fica para a Fase 13); a confiança baixa a manda para "pendente".

## Fase 6 — Extração das pranchas
**Critérios de aceite** — concluída em 01/11/2026 (`scripts/avaliar_pranchas.py`, conjuntos de desenvolvimento)
- [x] Na base sintética: ≥ 95% dos campos de identificação e ≥ 90% dos campos numéricos corretos (identificação 155/156 = 99,4%; numéricos 197/204 = 96,6%, nenhum errado ou inventado).
- [x] Todo valor tem evidência com página e bbox; recorte da evidência gerado em imagem (684/684).
- [x] Associação incerta → marcada como pendente (cotas sem rótulo e muro: 43 pendentes, todos certos).
- [x] Completude: cotas indefinidas, Norte, proprietário e assinaturas detectados em ≥ 90% dos casos sintéticos com omissão, e **zero** falsos "ausente" no conjunto completo (8/8, zero falsos "ausente" em todos os conjuntos).
- [x] Assinatura digital: os sintéticos íntegro e alterado são distinguidos em 100% dos casos (pyHanko, offline; 12/12).
- Limitações conhecidas: cotas com setas não reconhecidas; altura só em cota sem rótulo e cadeia de cotas incompleta não são extraídas ("não encontrado"); sem raízes ICP-Brasil locais, a cadeia de confiança não é verificada; o sint-002 tem o cartório cortado na borda da folha (defeito do gerador). Conjuntos reservados ficam para a Fase 13.

## Fase 7 — Matrícula, escritura e memorial
**Critérios de aceite** — concluída em 01/11/2026 (`scripts/avaliar_registro.py` e `scripts/avaliar_memorial.py`, conjuntos de desenvolvimento)
- [x] Atos separados corretamente em ≥ 95% dos sintéticos (38/39 = 97,4%; nenhum ato a mais).
- [x] Estado atual correto (com retificações) em ≥ 90%; cada campo aponta o ato de origem (33/36 = 91,7%; 36/36 com ato de origem).
- [x] Valores de OCR com baixa confiança aparecem como pendentes (em todos os leitores; limite configurável em `ocr.limiar_confianca`).
- Além dos critérios: escritura 36/36; memorial com identificação 57/60 e numéricos 195/204; nenhum valor errado sem pendência.
- Limitações conhecidas: na matrícula "ruim" um ato fica ilegível (vira pendência e deixa o estado pendente); erros de OCR restantes aparecem como pendentes, não são corrigidos; a área da escritura é a da data da venda (a atual vale pela matrícula). Conjuntos reservados ficam para a Fase 13.

## Fase 8 — Parâmetros (prefeitura e condomínio)
**Critérios de aceite** — concluída em 02/11/2026 (`scripts/avaliar_parametros.py` e `scripts/avaliar_alucinacao.py`, conjuntos de desenvolvimento)
- [x] Zona identificada ou perguntada; nunca presumida (12/12, pelo nome do condomínio no perímetro das zonas; sem menção → perguntar; OCR fraco → pendente).
- [x] ≥ 90% dos parâmetros sintéticos corretos; 100% com trecho literal verificado (prefeitura 121/132 = 91,7%; condomínio 38/38; evidências 203/203; nenhum valor errado sem pendência).
- [x] Teste de alucinação: com a lei sem o parâmetro, o sistema responde "não encontrado" (0 inventados, inclusive no modo forçado com valores de outras zonas como isca).
- [x] Conflito prefeitura × condomínio → adota o da prefeitura e registra observação com o valor do condomínio. Parâmetro só do condomínio (ex.: altura de muro) → usa o do condomínio (139 adotados certos, 8 conflitos registrados).
- Como funciona: tabelas lidas pelo código (zona × parâmetro, faixa de área do lote); texto corrido pelo LLM local com citação conferida pelo código; sem Ollama, só as tabelas.
- Limitações conhecidas: tabela de lei escaneada não é lida (zona ilegível no OCR) → "não encontrado"/pendente; parâmetro típico da lei achado só no condomínio fica pendente; muro com valor único (sem altura por posição); na análise real a área do lote virá da matrícula. Conjuntos reservados ficam para a Fase 13.

## Fase 9 — Motor de verificação
**Critérios de aceite** — concluída em 02/11/2026 (`tests/test_verificacao.py`, `tests/test_motor.py` e `scripts/avaliar_verificacao.py`, conjuntos de desenvolvimento)
- [x] Testes unitários para cada regra, incluindo valores exatamente no limite (no limite, atende).
- [x] Margens e quantidades sugeridas corretas (ex.: TO 62% / 60% num terreno de 400 m² → reduzir 8,0 m²).
- [x] Nenhuma chamada ao LLM dentro do motor (verificado por teste: o motor não importa o LLM nem rede).
- Análise completa (todos os leitores + motor): revocação 28/29 apontados + 1 marcado para confirmação; falso "atende" 0; falsos alarmes 0; classificação 95,7%; 100% com evidência. Sem Ollama: 24/29 + 5 marcados, falso "atende" 0, classificação 90,6%.
- Decisões: com a matrícula, a área da escritura vira observação; diferença com leitura incerta → "não foi possível verificar"; aritmética no quadro de áreas da prancha; valor ausente na prancha → o do memorial, com baixa confiança; ausência só vira "não atende" com a evidência de onde se procurou.
- Limitações conhecidas: dado presente em um documento só → "não foi possível verificar"; com a lei não lida (escaneada), o limite do condomínio é usado com baixa confiança; muro por posição e consulta prévia ficam para depois.

## Fase 10 — Interface I
**Critérios de aceite**
- [ ] Do upload à lista de itens sem usar o terminal.
- [ ] Tela de pendências mostra valor, origem, confiança e recorte da página; confirmar/corrigir funciona e é salvo.
- [ ] Interface acessível só em `127.0.0.1`.

## Fase 11 — Relatório
**Critérios de aceite**
- [ ] PDF e DOCX com o mesmo conteúdo; cabeçalho completo; aviso de responsabilidade técnica.
- [ ] Observações editadas na tela aparecem nos arquivos.
- [ ] Nenhum dado pessoal desnecessário (teste automático procura CPF/RG no relatório).
- [ ] Você lê um relatório sintético e aprova o tom e a clareza.

## Fase 12 — Versionamento
**Critérios de aceite**
- [ ] No projeto sintético R00→R01: "mesmo projeto" sugerido; 100% dos itens classificados corretamente em resolvido/pendente/novo.
- [ ] R00 emitido permanece idêntico após gerar R01.
- [ ] Histórico lista todas as rodadas com data e revisão do projeto.

## Fase 13 — Avaliação e ajuste fino
**Critérios de aceite**
- [ ] Metas da `05-avaliacao.md` atingidas na base sintética.
- [ ] Validação no **gabarito real**: resultado registrado (só números agregados) e discutido com você.

## Fase 14 — Empacotamento
**Critérios de aceite**
- [ ] Instalador roda num Windows "limpo" (ou numa nova conta de usuário) e a aplicação abre no navegador.
- [ ] Tesseract embutido funciona; ausência do Ollama é detectada com orientação clara; modo degradado funciona.
- [ ] Histórico do usuário preservado ao reinstalar.

---

## Como cada fase termina
1. Eu rodo todos os testes e a verificação anti-vazamento, e mostro a saída.
2. Escrevo um resumo: o que mudou, como testar, limitações conhecidas.
3. Você testa e aprova (ou pede ajustes).
4. Commit + push (com sua autorização) e marcamos a fase como concluída neste documento.
