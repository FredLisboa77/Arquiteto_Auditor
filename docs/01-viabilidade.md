# 01 — Viabilidade técnica

> **Objetivo deste documento:** dizer com franqueza o que dá para fazer hoje, com ferramentas gratuitas, rodando só no seu notebook, e onde estão as dificuldades e os riscos.
>
> **Data:** 30/10/2026 · **Hardware de referência:** Intel Core i7-10750H, 16 GB de RAM, NVIDIA RTX 2060 com 6 GB de VRAM, Windows 11 64 bits.

---

## 1. Resumo em uma frase

**É viável.** O núcleo do sistema — ler PDFs vetoriais do AutoCAD, fazer OCR de matrícula e escritura digitadas, comparar números e gerar relatórios versionados — usa tecnologia madura, gratuita e local. As partes realmente difíceis são três: **(a)** entender o *significado* de cada número numa prancha sem padrão; **(b)** localizar, dentro de uma lei inteira, os parâmetros da zona certa; **(c)** reconstruir o estado atual do imóvel a partir das averbações. Nos três casos a estratégia é a mesma: o software propõe, mostra a evidência e destaca a dúvida, e **você confirma**.

---

## 2. Glossário rápido

| Termo | O que significa aqui |
|---|---|
| **PDF vetorial** | PDF gerado direto pelo AutoCAD. O texto é "de verdade" (dá para selecionar e copiar) e cada palavra tem coordenadas na página. |
| **PDF escaneado** | PDF que é só uma foto da página. Para ler o texto é preciso OCR. |
| **OCR** (*Optical Character Recognition*) | Programa que "lê" letras numa imagem e devolve texto. Também informa uma **confiança** (0–100%) para cada palavra. |
| **LLM** (*Large Language Model*) | Modelo de IA que entende e escreve texto (como o ChatGPT). Aqui usaremos um que roda **no seu computador**, via Ollama. |
| **Ollama** | Programa gratuito que baixa e executa LLMs localmente. **Já está instalado** no seu notebook. |
| **VRAM** | Memória da placa de vídeo. Define o tamanho máximo do modelo de IA que roda rápido. Você tem 6 GB. |
| **Quantização (q4, q8)** | Técnica que "comprime" o modelo de IA para caber em menos memória, com pequena perda de qualidade. `q4_K_M` ≈ 4 bits por parâmetro. |
| **7B, 14B** | Tamanho do modelo em bilhões de parâmetros. Maior = mais "inteligente" e mais pesado. |
| **Código determinístico** | Código comum (`if`, contas, comparações): mesma entrada, sempre a mesma saída. É o que faz os cálculos — nunca o LLM. |
| **Bounding box (bbox)** | Retângulo com as coordenadas (x, y) de uma palavra na página. É o que permite saber que "5,00" está ao lado de "RECUO FRONTAL". |
| **Evidência** | Registro de onde um valor veio: arquivo, página, trecho de texto e coordenadas. Todo valor do sistema carrega a sua. |

---

## 3. O que você já tem instalado (verificado em 30/10/2026)

| Ferramenta | Situação | Uso no projeto |
|---|---|---|
| Python 3.11.9 (e 3.13, 3.10, 3.9) | ✅ instalado; `.venv` do projeto já usa 3.11 | **Usaremos 3.11**: melhor compatibilidade com bibliotecas de OCR/IA e com o PyInstaller |
| Git 2.56 + GitHub CLI | ✅ logado como `FredLisboa77` | Versionamento e publicação |
| Driver NVIDIA 591.86 (CUDA 13.1) | ✅ | Ollama usa a GPU automaticamente; não é preciso instalar o CUDA Toolkit |
| Ollama 0.40 | ✅ com `qwen2.5:7b-instruct-q4_K_M` e `qwen2.5:3b` | LLM local |
| Tesseract OCR | ❌ **não instalado** | Instalar na Fase 1 (instruções em `03-arquitetura.md`) |
| `pip` → PyPI | ⚠️ **falha de certificado SSL** | Corrigir na Fase 1 (provável antivírus inspecionando HTTPS ou proxy) |
| Disco | C: 66 GB livres · **D: 1,5 TB livres** | Modelos e dados ficam no D: |

---

## 4. O que cabe nos 6 GB de VRAM

| Modelo / ferramenta | Memória aprox. | Roda bem? | Observação |
|---|---|---|---|
| **Qwen2.5 7B Instruct q4_K_M** (já instalado) | ~4,7 GB + contexto | ✅ **Sim**, até ~8 mil *tokens* de contexto | **Modelo principal.** Bom em português e em gerar JSON estruturado. ~20–40 palavras/s na RTX 2060. |
| Qwen2.5 3B (já instalado) | ~2 GB | ✅ Folgado | Reserva para tarefas simples (classificar tipo de documento) ou se a VRAM apertar. |
| Outros 7–9B em q4 (Llama 3.1 8B, Gemma, gerações mais novas do Qwen) | 4,5–6 GB | ✅/⚠️ no limite | Testaremos alternativas na fase de avaliação; a arquitetura permite trocar o modelo por configuração. |
| Modelos 13–14B em q4 | 8–9 GB | ❌ **Não cabem** na GPU | O Ollama joga parte para a CPU/RAM: funciona, mas **3–10× mais lento**. Não recomendado. |
| Modelos de visão (lêem imagem) 7B | 5–7 GB | ⚠️ No limite | **Fora do MVP.** Talvez útil no futuro para conferir OCR difícil. |
| Modelo de *embeddings* (busca por significado), ex.: `nomic-embed-text`, `bge-m3` | 0,3–1,2 GB | ✅ | Para achar trechos de lei relevantes. |
| **Tesseract 5** (OCR) | Usa só CPU, ~200 MB RAM | ✅ | Excelente para texto **digitado** (seu caso). ~2–6 s por página. |
| PaddleOCR / docTR (OCR com rede neural) | 1–2 GB VRAM | ✅ | Alternativa se o Tesseract falhar em páginas ruins. Fora do MVP. |

**Limites práticos:**
- **Um modelo pesado de cada vez na GPU.** O fluxo será sequencial (primeiro OCR, depois LLM). O Ollama descarrega o modelo após alguns minutos ociosos.
- **Contexto limitado (~8 mil *tokens* ≈ 20–25 páginas de texto).** O LLM nunca recebe uma lei inteira; recebe só os trechos pré-selecionados (ver risco R3).
- **16 GB de RAM** comportam tudo, desde que não se abra muitas outras aplicações pesadas ao mesmo tempo.
- **Tempo estimado por projeto:** 2–8 minutos (você aceitou "alguns minutos"). Resultados ficam em cache: reabrir um projeto é instantâneo.

---

## 5. O que é factível — e quão difícil

Escala: 🟢 fácil/maduro · 🟡 exige cuidado · 🔴 difícil (precisa de confirmação humana)

| # | Tarefa | Dificuldade | Por quê |
|---|---|---|---|
| 1 | Extrair texto + posição de PDFs do AutoCAD | 🟢 | PyMuPDF faz isso em milissegundos. **Ressalva:** fontes SHX (ver R1). |
| 2 | Detectar se um PDF/página é vetorial ou escaneado | 🟢 | Conta caracteres extraíveis vs. área de imagens na página. |
| 3 | Ler o **quadro de áreas** | 🟡 | É uma tabela, mas cada autor monta diferente (linhas desenhadas, texto solto, multicolunas). Detecção por palavras-chave + alinhamento de colunas. |
| 4 | Ler o **carimbo** (projeto, autor, CAU, revisão, prancha) | 🟡 | Posição varia; usaremos rótulos ("REV", "PRANCHA", "CAU", "RESP. TÉCNICO") e proximidade. |
| 5 | Associar **cotas** a recuos/testadas | 🔴 | O número "5,00" está perto de uma linha de cota, mas a qual divisa? Usaremos rótulos textuais próximos ("RECUO FRONTAL", "AFAST.") e o quadro de áreas. Você disse que a regra é lida pelas cotas e é clara — então priorizamos cotas **rotuladas**; cota sem rótulo → baixa confiança. |
| 6 | Identificar o **tipo de prancha** (situação, baixa, cortes…) | 🟢/🟡 | Título da prancha + palavras-chave; LLM pequeno como desempate. |
| 7 | OCR de matrícula/escritura **digitadas** | 🟢/🟡 | Tesseract vai muito bem em texto datilografado/impresso. Carimbos, selos e assinaturas sobrepostos derrubam a confiança **localmente** — exatamente o que queremos sinalizar. |
| 8 | Reconstruir o **estado atual** do imóvel pelas averbações | 🔴 | Exige ler a sequência R-1, AV-2, AV-3… e entender que "AV-5: retificação de área para 452,30 m²" substitui o valor original. Estratégia: regex separa os atos; LLM classifica cada ato e extrai valores; **código** aplica em ordem; você confirma. |
| 9 | Achar parâmetros dentro de **uma lei inteira** | 🔴 | Leis têm dezenas/centenas de páginas, tabelas em anexo, remissões ("conforme Anexo III"), exceções. Ver R3. |
| 10 | Comparar números, aplicar a hierarquia prefeitura > condomínio | 🟢 | Código determinístico puro. |
| 11 | Gerar sugestões quantificadas | 🟢 | O **número** (ex.: "reduzir 8 m²") vem do código; o LLM só redige a frase. Há texto-modelo de reserva se o LLM falhar. |
| 12 | Relatório em tela, PDF e DOCX | 🟢 | Bibliotecas maduras (ReportLab, python-docx). |
| 13 | Versões R00/R01 e comparação item a item | 🟢/🟡 | Lógica simples **se** cada item tiver uma "chave estável" (ex.: `TO_MAX`, `RECUO_FRONTAL`). Projetado desde o início. |
| 14 | Interface web local | 🟢 | NiceGUI (Python puro, sem precisar aprender JavaScript). |
| 15a | Detectar **cotas indefinidas** (dimensão essencial ausente ou só gráfica) | 🔴 | Exige saber o que *deveria* estar cotado. Para isso, a lista de requisitos e a detecção de linhas de cota sem texto associado. Provar uma ausência é mais difícil que achar um valor. Na dúvida, o item vai para confirmação. |
| 15b | Detectar **indicação do Norte** | 🟡 | Texto "N" ou "NORTE" junto a um símbolo vetorial. Se o símbolo for um bloco sem texto, é preciso reconhecer a forma (seta ou círculo), o que é heurístico. |
| 15c | **Assinaturas**: presença e integridade da assinatura digital | 🟢/🟡 | A assinatura digital é lida localmente com pyHanko. A validação da cadeia ICP-Brasil e da revogação depende de consulta *online*, que fica como orientação manual (LGPD). Para assinatura escaneada, só detectamos a presença. |
| 15d | **Identificação do proprietário** e **altura de muro** | 🟡 | O proprietário é um campo do carimbo ou memorial, comparado com a matrícula. A altura do muro aparece em cortes, fachadas ou memorial e entra como parâmetro do condomínio. |
| 16 | Executável Windows | 🟡 | PyInstaller funciona, mas Tesseract e Ollama são programas externos: distribuição em instalador (ver `03-arquitetura.md`). |

---

## 6. Principais riscos técnicos

| ID | Risco | Probabilidade | Impacto | Mitigação |
|---|---|---|---|---|
| **R1** | **Texto do AutoCAD exportado como geometria.** Fontes SHX (romans, simplex…) às vezes viram linhas no PDF, e o texto deixa de ser selecionável. | Média | Alto | Você informou que o texto é selecionável — ótimo. Mesmo assim, a Fase 3 terá um **diagnóstico** que mede, sem expor conteúdo, quanto texto é extraível de cada prancha real. Se houver pranchas assim, plano B: OCR da prancha renderizada em alta resolução (pior, mas funciona) e orientação ao autor (exportar com fontes TrueType). |
| **R2** | Associação errada de cota/rótulo (ex.: recuo lateral lido como frontal). | Alta | Alto | Nunca decidir sem rótulo; cruzar com quadro de áreas; associação incerta → item em amarelo para confirmação; a evidência mostra o recorte da prancha. |
| **R3** | **Lei inteira:** parâmetro da zona errada, tabela de anexo mal lida, exceção ignorada. | Alta | Alto | (1) Identificar a **zona** do lote (da consulta prévia, memorial ou prancha; senão, perguntar a você); (2) busca híbrida (palavras-chave + significado) só nas páginas candidatas; (3) LLM extrai em JSON **com citação literal**; (4) código confere que o trecho citado **existe** no documento e contém o número; (5) parâmetro sem citação conferida = descartado; ambíguo = você escolhe. |
| **R4** | **Alucinação do LLM** (inventar um número ou trecho). | Média | Alto | Regra de projeto: todo valor vindo do LLM precisa de trecho literal verificado por código no texto-fonte; números são relidos do trecho pelo código, não do LLM. |
| **R5** | OCR ruim em partes da matrícula (carimbos sobre texto). | Média | Médio | Pré-processamento (endireitar, limpar ruído, binarizar); confiança por palavra; valores com confiança < limiar viram "confirmar"; você vê o recorte da imagem. |
| **R6** | Averbações interpretadas na ordem errada ou não reconhecidas. | Média | Alto | Separação dos atos por regex (R-n / AV-n); lista cronológica exibida na tela; o "estado atual" mostra qual ato definiu cada valor. |
| **R7** | Fórmulas de TO/CA/permeabilidade variam por município. | Alta | Médio | Usar fórmula da lei quando encontrada; senão **fórmula padrão explícita** e marcada no relatório ("calculado com critério padrão: …"), ajustável por você. |
| **R8** | Overfitting à base sintética (funciona nos seus PDFs fictícios, falha nos reais). | Alta | Alto | Base sintética com layouts variados de propósito; validação final no gabarito real; métricas separadas (ver `05-avaliacao.md`). |
| **R9** | Vazamento de dados pessoais no GitHub. | Baixa | **Muito alto** | `.gitignore` em camadas, pasta `dados_privados/`, **verificação automática antes de cada commit** (gancho *pre-commit*, Fase 1), regra no `CLAUDE.md`. |
| **R10** | Falha de SSL do `pip` atrasar o início. | Certa | Baixo | Primeira tarefa da Fase 1. |
| **R11** | Tamanho/complexidade do executável (Tesseract + Ollama + modelos). | Média | Médio | Instalador que inclui Tesseract (~80 MB) e verifica/instala Ollama; modelos baixados no primeiro uso (ver `03-arquitetura.md`). |
| **R13** | **Omissões são difíceis de provar.** No conjunto real, 8 dos 11 erros são omissões ou indefinições (cotas, Norte, assinaturas, proprietário). Um falso "ausente" vira falso alarme; um falso "presente" deixa o erro passar. | Alta | Alto | Lista explícita de requisitos (`requisitos_apresentacao.toml`). Toda ausência detectada vem com a região examinada como evidência ("procurado em: prancha 01, planta de situação"). Ausência com baixa confiança vai para confirmação. Casos sintéticos específicos para cada omissão. |
| **R12** | Projeto grande para um iniciante solo. | Média | Médio | Fases curtas com critério de aceite; escopo do MVP enxuto; testes automáticos a partir da Fase 2 para não quebrar o que já funciona. |

---

## 6.1 Resultado do diagnóstico das pranchas reais (Fase 3, 30/10/2026)

`scripts/diagnosticar_pdfs.py` rodou nos 5 PDFs reais e mostrou só estatísticas. **O risco R1 se confirmou em parte:**

- Todos têm texto selecionável com fontes TrueType embutidas (Type0), entre 558 e 2.097 caracteres por folha, e 2 assinaturas digitais cada.
- Nas três pranchas A1, **96% a 99% dos elementos de desenho são traços com até 4 mm**, típicos de texto em fonte SHX convertido em linhas. São de 16 mil a 195 mil traços por folha.
- A quantidade de números como texto varia muito: 130 e 111 em duas pranchas e **apenas 6** em outra. Nesta última, as cotas estão quase certamente desenhadas como linhas.
- As pranchas do AutoCAD têm de 3 a 226 comentários do tipo "Square". Quando a opção correspondente está ligada na exportação, o AutoCAD guarda o texto SHX em comentários invisíveis. **Se for o caso, as cotas podem ser lidas com exatidão a partir deles, sem OCR.** A versão 3 do diagnóstico conta quantos comentários têm texto, para confirmar.

**Estratégia decorrente** (ordem de preferência):
1. Texto selecionável.
2. Texto dos comentários SHX, com a posição do comentário.
3. OCR da região renderizada em alta resolução, com confiança baixa e confirmação do revisor.
4. Se nada funcionar, item "não foi possível verificar", com orientação ao autor: exportar o PDF com fontes TrueType, ou com a opção do AutoCAD que inclui o texto SHX como comentário.

A base sintética passará a ter conjuntos com texto como desenho e com texto em comentários (Fase 4).

## 7. O que **não** é viável (ou não vale a pena) agora

- **Interpretar desenhos sem texto** (medir recuos na geometria, reconhecer paredes). Você confirmou que as medidas aparecem escritas — isso fica fora.
- **Manuscritos.** Você informou que não há; não investiremos nisso.
- **Análise jurídica**: fora do escopo por definição.
- **LLMs de 14B+ com velocidade aceitável** nesse hardware.
- **Ler DWG** diretamente: a entrada é sempre PDF.

---

## 8. Conclusão

O projeto é factível com 100% de ferramentas gratuitas e locais. O valor do software não estará em "acertar sozinho", mas em **fazer 80–90% da leitura automaticamente, mostrar onde está cada número e concentrar sua atenção nos 10–20% duvidosos** — e em nunca esquecer de comparar um valor com outro. As escolhas de arquitetura (`03-arquitetura.md`) e o plano de fases (`04-plano-de-fases.md`) atacam os riscos R1, R3 e R10 primeiro.
