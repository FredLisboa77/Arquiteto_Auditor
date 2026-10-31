# 03 — Arquitetura

> Componentes, fluxo dos dados e tecnologias, com o porquê de cada escolha. Os critérios de escolha foram: **gratuito e de código aberto**, **roda localmente** no seu hardware, **compatível com PyInstaller** (executável Windows), **maduro e bem documentado** (você vai aprender com ele) e **licença compatível com AGPL-3.0**.

---

## 1. Visão geral

```
 ┌────────────────────────────── Navegador (http://localhost:8080) ──────────────────────────────┐
 │  Interface web local (NiceGUI): upload · pendências de confirmação · itens · relatório · versões │
 └──────────────────────────────────────────────┬───────────────────────────────────────────────┘
                                                │ chama
 ┌──────────────────────────────────────────────▼───────────────────────────────────────────────┐
 │                         SERVIÇOS DA APLICAÇÃO (orquestram o fluxo)                             │
 │   AnaliseService · RevisaoService · RelatorioService · VersaoService                           │
 └───┬───────────┬──────────────┬───────────────┬───────────────┬───────────────┬────────────────┘
     │           │              │               │               │               │
 ┌───▼───┐  ┌────▼────┐  ┌──────▼──────┐  ┌─────▼──────┐  ┌─────▼──────┐  ┌─────▼──────┐
 │Ingestão│  │   OCR   │  │  Extração   │  │Verificação │  │Versionamento│ │ Relatório  │
 │(PDF,   │  │Tesseract│  │ pranchas,   │  │ (regras,   │  │ (R00→R01:  │  │(tela, PDF, │
 │tipo,   │  │+OpenCV  │  │ matrícula,  │  │ fórmulas,  │  │ resolvido/ │  │ DOCX)      │
 │vetorial│  │         │  │ memorial,   │  │ tolerância)│  │ pendente/  │  │            │
 │/scan)  │  │         │  │ parâmetros  │  │ DETERMINÍS-│  │ novo)      │  │            │
 └───┬────┘  └────┬────┘  └──────┬──────┘  │ TICO       │  └─────┬──────┘  └─────┬──────┘
     │            │              │ usa     └─────┬──────┘        │               │
     │            │        ┌─────▼──────┐         │               │               │
     │            │        │ Adaptador  │◄────────┼── só p/ redigir sugestões ────┘
     │            │        │ LLM(Ollama)│         │
     │            │        └────────────┘         │
 ┌───▼────────────▼──────────────────────────────▼───────────────▼──────────────────────────────┐
 │                MODELO DE DOMÍNIO (dados com Evidência e Confiança em tudo)                     │
 └───────────────────────────────────────────────┬───────────────────────────────────────────────┘
                                                 │
 ┌───────────────────────────────────────────────▼───────────────────────────────────────────────┐
 │   Persistência local: SQLite (dados_privados/historico/) + arquivos (cache de páginas/OCR)    │
 └────────────────────────────────────────────────────────────────────────────────────────────────┘
```

**Arquitetura em camadas:** a interface só conversa com os *serviços*; os serviços usam os módulos de domínio; nada do núcleo depende da interface. Isso permite, no futuro, trocar a interface ou colocar o núcleo num servidor para vários escritórios sem reescrever a lógica.

---

## 2. Fluxo dos dados (uma análise)

```
 PDFs ──► [1 Ingestão] ──► Documento + Páginas (texto c/ coordenadas OU imagem)
              │                 │
              │                 └─► página escaneada? ─► [2 OCR] ─► palavras + confiança + bbox
              ▼
        [3 Classificação] prancha | matrícula | escritura | memorial | lei | norma condomínio
              ▼
        [4 Extração especializada por tipo]
              │  regras + regex + geometria do texto (primeiro)
              │  LLM local só para "o que significa este texto?" (depois), sempre com citação
              ▼
        ValoresExtraídos (valor, unidade, Evidência[arquivo, página, bbox, trecho], confiança, origem)
              ▼
        [5 Consolidação] estado atual da matrícula (aplica averbações em ordem)
                         zona do lote → parâmetros aplicáveis; prefeitura prevalece sobre condomínio
              ▼
        [6 Revisão humana] pendências (baixa confiança / ambíguo / não encontrado) → você confirma
              ▼
        [7 Verificação determinística] consistência + parâmetros + aritmética → ItensDeVerificação
              ▼
        [8 Redação] sugestões (números do código; frase pelo LLM ou texto-modelo)
              ▼
        [9 Versionamento] compara com rodada anterior pela chave estável → resolvido/pendente/novo
              ▼
        [10 Relatório] tela ──(você revisa)──► emitir R0n ──► PDF + DOCX + congela no histórico
```

### 2.1 O papel exato do LLM (e o que ele **não** faz)

| O LLM **faz** | O LLM **não faz** |
|---|---|
| Classificar um documento em caso de dúvida | Calcular TO, CA, áreas, margens |
| Dizer qual rótulo de carimbo/quadro corresponde a qual campo, quando as regras não bastarem | Comparar valores ou decidir "atende / não atende" |
| Classificar cada ato da matrícula (retificação, venda, hipoteca…) | Inventar valores: todo número é **relido pelo código** do trecho citado |
| Extrair parâmetros de trechos de lei, **com citação literal** | Receber documentos inteiros (só trechos pré-selecionados) |
| Redigir a explicação e a sugestão a partir de números prontos | Enviar dados para fora (roda via Ollama em `localhost`) |

**Validação de citação (anti-alucinação):** toda resposta do LLM é um JSON validado por esquema. Cada valor vem com `trecho`. O código verifica: (1) o trecho existe (com tolerância a espaços/hífens) no texto da página indicada; (2) o número informado aparece no trecho. Se falhar → valor descartado ou marcado para confirmação.

---

## 3. Tecnologias escolhidas

| Necessidade | Escolha | Licença | Por quê | Alternativas consideradas |
|---|---|---|---|---|
| Linguagem | **Python 3.11** | PSF | Já instalado no `.venv`; melhor compatibilidade com OCR/IA/PyInstaller que o 3.13. | 3.13 (algumas bibliotecas ainda atrasadas) |
| Leitura de PDF vetorial | **PyMuPDF** (`fitz`) | AGPL-3.0 | Mais rápida e completa: texto com bbox por palavra, desenhos vetoriais, tabelas (`find_tables`), renderização de páginas em imagem para OCR e recortes de evidência. A AGPL combina com a licença do projeto. | `pdfplumber` (MIT, mais lento; bom plano B se um dia precisar de licença permissiva), `pypdfium2` |
| Detecção vetorial × escaneado | PyMuPDF (regra própria) | — | Razão "caracteres extraíveis / área de imagens" por página. | — |
| OCR | **Tesseract 5** + `pytesseract` | Apache-2.0 | Padrão do mercado, excelente em texto impresso/datilografado, modelo `por` oficial, roda na CPU (deixa a GPU para o LLM), confiança por palavra (`image_to_data`). | PaddleOCR, docTR, EasyOCR (melhores em casos difíceis, porém mais pesados; futuros) |
| Pré-processamento de imagem | **OpenCV** (`opencv-python-headless`) + **Pillow** | Apache-2.0 / HPND | Endireitar (*deskew*), remover ruído, binarizar, atenuar carimbos coloridos. | scikit-image |
| LLM local | **Ollama** + modelo **Qwen2.5 7B Instruct q4_K_M** | MIT / Apache-2.0 | Já instalado; cabe em 6 GB; bom português; suporta **saída estruturada** (JSON com esquema). Temperatura 0 para reprodutibilidade. | llama.cpp direto (mais trabalho), LM Studio (não é código aberto) |
| Cliente do LLM | pacote `ollama` (Python) atrás de um **adaptador** próprio | MIT | O adaptador isola o resto do código: trocar de modelo/servidor = mudar configuração. | `httpx` direto |
| Busca em leis | **BM25** (`rank-bm25`) + *embeddings* locais via Ollama (`nomic-embed-text` ou `bge-m3`) + dicionário de sinônimos ("taxa de ocupação", "TO", "T.O.", "índice de ocupação") | Apache-2.0 | Busca híbrida: palavras exatas + significado. Seleciona as poucas páginas que vão para o LLM. | Bancos vetoriais (Chroma, Qdrant) — desnecessários nesse volume |
| Assinatura digital em PDF | **pyHanko** | MIT | Lê os campos de assinatura, verifica a integridade e identifica o certificado, tudo offline. Os certificados-raiz da ICP-Brasil podem ser guardados localmente. A consulta de revogação (*online*) não é feita automaticamente (LGPD); fica como orientação no relatório. | PyMuPDF (só detecta o campo) |
| Comparação aproximada de textos | `rapidfuzz` | MIT | Comparar nomes de condomínio/endereço com variações de grafia. | — |
| Modelos de dados e validação | **Pydantic v2** | MIT | Define a "forma" de cada dado (Evidência, Valor, Item) e valida JSON do LLM. | dataclasses |
| Banco de dados local | **SQLite** + **SQLModel** | Domínio público / MIT | SQLite é um arquivo único, sem servidor, ideal para uso pessoal e para o executável. SQLModel une Pydantic e SQLAlchemy (didático). Migrações com Alembic quando o esquema estabilizar. | PostgreSQL (futuro multiusuário — a camada de persistência permite trocar) |
| Interface web local | **NiceGUI** | MIT | Interface no navegador escrita **só em Python** (sem HTML/JS); tabelas editáveis, upload, visualização de imagens; roda em `localhost`; tem guia oficial de empacotamento com PyInstaller (`nicegui-pack`). | Streamlit (empacotamento difícil, modelo de "re-executar tudo" atrapalha edição), Flask/FastAPI + HTMX (exige HTML/JS), Gradio |
| Relatório PDF | **ReportLab** | BSD | Puro Python (sem dependências do sistema → empacota fácil), tabelas, cabeçalho/rodapé, numeração. | WeasyPrint (precisa de GTK no Windows — ruim para o executável) |
| Relatório DOCX | **python-docx** | MIT | Padrão para gerar Word editável (o autor pode responder no próprio documento). | docxtpl |
| Modelo único do relatório | estrutura de dados `Relatorio` → dois "renderizadores" (PDF e DOCX) | — | O conteúdo é montado uma vez; os dois formatos nunca divergem. | — |
| Testes automáticos | **pytest** | MIT | Padrão do Python. | unittest |
| Qualidade de código | **ruff** (estilo/erros) | MIT | Um só programa, rápido. | flake8 + black |
| Proteção anti-vazamento | **pre-commit** + verificação própria | MIT | Roda automaticamente antes de cada `git commit` e bloqueia PDFs/imagens/DOCX fora de `dados_sinteticos/`, arquivos grandes, CPF e padrões de matrícula reais. | Só `.gitignore` (insuficiente: `git add -f` passa por cima) |
| Base sintética — pranchas | **ReportLab** (PDF vetorial) e/ou **ezdxf** (DXF → PDF) | BSD / MIT | Desenhar linhas, cotas, carimbos e quadros com texto real e coordenadas controladas. | — |
| Base sintética — escaneados | **Pillow** + **Augraphy** + OpenCV | MIT | Augraphy simula degradação de documento (ruído, manchas, inclinação, carimbos, sombra de digitalização). | — |
| Base sintética — dados fictícios | **Faker** (`pt_BR`) | MIT | Nomes, endereços e números fictícios realistas. | — |
| Empacotamento | **PyInstaller** (modo pasta, `--onedir`) + **Inno Setup** (instalador) | GPL c/ exceção / gratuito | PyInstaller é o mais usado e tem suporte do NiceGUI; Inno Setup gera um `setup.exe` profissional e grátis. | Nuitka (compila, mais lento de configurar), Briefcase |

> **Nada pago é necessário.** Se um dia o software for vendido com código fechado, PyMuPDF exigiria licença comercial — mas com AGPL (sua escolha) isso não se aplica. O Qwen2.5 **7B** é Apache-2.0; o Qwen2.5 **3B** tem licença de pesquisa (não comercial): no uso profissional futuro, prefira o 7B ou outro modelo de licença aberta.

---

## 4. Componentes (módulos Python)

Pacote: `src/arquiteto_auditor/`

| Módulo | Responsabilidade |
|---|---|
| `dominio/` | Classes de dados: `Projeto`, `Rodada` (cada análise R0n), `Documento`, `Pagina`, `Evidencia`, `ValorExtraido`, `Parametro`, `ItemVerificacao`, `Relatorio`. Enums de status e de origem. **Sem dependências externas.** |
| `ingestao/` | Abrir PDF, calcular *hash*, separar páginas, detectar vetorial/escaneado, classificar tipo de documento. |
| `ocr/` | Renderizar página → pré-processar → Tesseract → palavras com bbox e confiança; cache em disco. |
| `extracao/pranchas/` | Carimbo, quadro de áreas, rótulos e cotas, título/tipo de prancha. |
| `extracao/registro/` | Matrícula e escritura: cabeçalho, descrição do imóvel, atos R-n/AV-n, estado atual. |
| `extracao/memorial/` | Campos de identificação e numéricos do memorial. |
| `extracao/parametros/` | Zona do lote, busca de trechos na lei/norma, extração com citação, normalização de unidades. |
| `llm/` | Adaptador Ollama, *prompts* versionados (arquivos de texto), esquemas JSON, validação de citação, *fallback* sem LLM. |
| `verificacao/` | Catálogo de regras (chaves estáveis), fórmulas (padrão + configuráveis), tolerâncias, hierarquia prefeitura > condomínio, cálculo de margem e da quantidade sugerida (ex.: m² a reduzir). |
| `versionamento/` | Identificação de "mesmo projeto", comparação entre rodadas, congelamento de relatório emitido. |
| `relatorio/` | Montagem do `Relatorio`; renderizadores PDF e DOCX; textos-modelo; aviso de responsabilidade. |
| `persistencia/` | Repositório SQLite (salvar/carregar tudo acima); caminhos de dados. |
| `servicos/` | Orquestração dos passos do fluxo (o que a interface chama). |
| `interface/` | Páginas NiceGUI. |
| `config.py` | Leitura de `config.toml` (revisor, modelo, limiares, tolerâncias, pastas). |

Fora do pacote: `dados_sinteticos/geradores/` (scripts que criam a base sintética), `tests/`, `scripts/` (avaliação, verificação anti-vazamento, diagnóstico de PDFs reais).

---

## 5. Decisões de projeto importantes

### 5.1 Evidência e confiança em todo valor
```text
ValorExtraido
  campo        = "TERRENO_AREA"
  valor        = 450.00   unidade = "m2"
  origem       = vetorial | ocr | llm | revisor | calculado
  confianca    = 0.0 – 1.0
  evidencias   = [ Evidencia(documento, pagina/prancha, bbox, trecho="ÁREA DO TERRENO: 450,00 m²") ]
  status_conf  = automatico | pendente_confirmacao | confirmado | corrigido_pelo_revisor
```
A confiança combina: origem (vetorial > OCR), confiança do OCR das palavras, qualidade da associação rótulo↔valor, concordância entre fontes. **Limiares configuráveis**; abaixo do limiar → vai para a tela de confirmação.

### 5.2 Números brasileiros
Normalizador único para "1.234,56", "1234,56 m²", "5,00m", "60%", "0,6", "2 (dois) pavimentos" — testado exaustivamente. Unidades internas: m, m², %, adimensional.

### 5.3 Estado atual da matrícula
Lista cronológica de atos → aplicados em ordem; cada campo do "estado atual" aponta o ato que o definiu ("área 452,30 m² — AV-5, fl. 2"). Atos não compreendidos → pendência.

### 5.4 Parâmetros em lei inteira
1. Identificar a **zona** (consulta prévia, certidão de uso do solo, memorial ou prancha; se não houver, perguntar).
2. Recortar a lei em trechos (artigos, parágrafos, linhas de tabela).
3. Busca híbrida pelos trechos que citam a zona **e** o parâmetro.
4. LLM extrai `{parametro, valor, unidade, condicao, trecho, pagina}`.
5. Código valida a citação e normaliza o número.
6. Conflito/ambiguidade (dois valores para a mesma zona, exceções) → você escolhe.
7. Hierarquia: **a prefeitura prevalece sobre o condomínio**. Parâmetro definido só por um dos dois → usa esse. Definido pelos dois com valores diferentes → adota o da prefeitura e registra observação no item, com o valor e o trecho do condomínio.

### 5.5 Fórmulas
Arquivo `formulas.toml` com a fórmula padrão de cada índice (ex.: TO = projeção da edificação ÷ área do terreno) e as exclusões consideradas. Quando a lei define a fórmula, o sistema registra o trecho e você confirma qual usar. O relatório sempre diz qual critério foi usado.

### 5.6 Chave estável e versionamento
Cada item = `chave` (ex.: `RECUO_FRONTAL`) + `escopo` (ex.: `pavimento=1`). Comparação de rodadas:

| Rodada anterior | Rodada atual | Resultado |
|---|---|---|
| problema | atende | **resolvido** |
| problema | problema | **pendente** (mostra se o valor mudou) |
| atende / inexistente | problema | **novo** |
| problema | não verificável | **não verificável nesta rodada** |

"Problema" = não atende **ou** divergente. Relatórios emitidos ficam **congelados** (não mudam se o código evoluir).

### 5.7 Mesmo projeto
Pontuação por matrícula + lote/quadra + condomínio + título + autor (comparação aproximada). Acima do limiar → sugestão "parece ser o projeto X (R00 em dd/mm)"; você confirma.

### 5.8 Privacidade (LGPD)
- Processamento 100% local; Ollama em `127.0.0.1`; interface só em `127.0.0.1` (não exposta na rede).
- O relatório inclui só dados do imóvel e do projeto + nome/registro do autor. Dados de proprietários (CPF, RG, estado civil, filiação) **não são extraídos** para o relatório.
- Logs não gravam conteúdo de documentos.

---

## 6. Instalação do que falta (Fase 1)

### 6.1 Corrigir o `pip` (erro de certificado SSL)
**Resolvido na Fase 1 (30/10/2026).** A causa é o **Norton 360**, que inspeciona conexões HTTPS: ele troca o certificado dos sites por um próprio ("Norton Web/Mail Shield Root"). O `pip` 24.0 do `.venv` não confiava nesse certificado. A partir da versão 24.2, o `pip` passa a usar o **repositório de certificados do Windows**, que já confia no Norton. A correção foi atualizar o `pip` do `.venv` para a versão 26, sem desligar nenhuma verificação de segurança:
```powershell
py -3.13 -m pip download --no-deps --only-binary=:all: -d %TEMP%\pipwheel pip
.venv\Scripts\python -m pip install --no-index %TEMP%\pipwheel\pip-*.whl
```
O `winget` também falha na fonte `msstore` pelo mesmo motivo. Para contornar, use `--source winget`.

### 6.2 Tesseract (OCR)
**Instalado na Fase 1:** Tesseract 5.4.0, em `C:\Program Files\Tesseract-OCR`.
```powershell
winget install --id UB-Mannheim.TesseractOCR -e --source winget
```
A instalação silenciosa não inclui o português. Os modelos de idioma ficam em `modelos/tessdata/` (fora do Git): `por.traineddata` da coleção `tessdata_best`, que é a mais precisa, mais `eng` e `osd` copiados da instalação. O código sempre passa `--tessdata-dir modelos/tessdata`. É o mesmo arranjo do executável futuro e não exige permissão de administrador.
```powershell
curl.exe -sSL -o modelos\tessdata\por.traineddata https://github.com/tesseract-ocr/tessdata_best/raw/main/por.traineddata
```
Verificação: `.venv\Scripts\python scripts\verificar_ambiente.py`.

### 6.3 Modelos do Ollama no disco D:
O C: tem só 66 GB livres. **Já configurado neste notebook:** a variável de ambiente de usuário `OLLAMA_MODELS = D:\dev\ollama-models` (6,2 GB em 30/10/2026). Em outra máquina, defina a mesma variável e reinicie o Ollama. Modelos adicionais a baixar quando chegar a fase correspondente:
```powershell
ollama pull nomic-embed-text      # ~275 MB, embeddings para busca em leis
```

### 6.4 Bibliotecas Python
Declaradas em `pyproject.toml` (arquivo de configuração padrão de projetos Python) e instaladas no `.venv` com `pip install -e .[dev]`.

---

## 7. Empacotamento e distribuição dos modelos

**Formato:** PyInstaller em modo **pasta** (`--onedir`) — inicia mais rápido e é mais estável que arquivo único — embrulhado num instalador **Inno Setup** (`ArquitetoAuditor-Setup.exe`).

| Componente | Tamanho aprox. | Como é distribuído |
|---|---|---|
| Aplicação Python + bibliotecas (PyMuPDF, OpenCV, NiceGUI, ReportLab…) | 150–300 MB | Dentro do instalador |
| Tesseract + `por.traineddata` | ~80–120 MB | **Dentro do instalador** (pasta `tesseract/` ao lado do executável; o código aponta para ela) |
| Ollama | ~1 GB instalado | **Pré-requisito separado.** O instalador verifica se existe; se não, abre o instalador oficial (gratuito). Motivo: o Ollama é um serviço com atualizações próprias e drivers de GPU; empacotá-lo tornaria o executável enorme e frágil. |
| Modelo LLM (Qwen2.5 7B q4) | ~4,7 GB | **Baixado no primeiro uso** pela própria aplicação (tela de progresso). Opção *offline*: copiar a pasta de modelos de outra máquina. |
| Modelo de embeddings | ~0,3 GB | Idem |

**Modo degradado:** se o Ollama não estiver disponível, a aplicação funciona com regras e regex apenas; o que depender do LLM vira "não foi possível verificar" ou "confirmar manualmente", e as sugestões usam textos-modelo. Assim o executável nunca fica "inútil".

**Dados do usuário no executável:** pasta configurável (padrão `Documentos\ArquitetoAuditor\`), fora da pasta do programa — atualizar a aplicação não apaga o histórico.

---

## 8. Caminho para uso profissional (sem refazer o núcleo)

- Núcleo (domínio, extração, verificação, versionamento, relatório) independente da interface → pode virar serviço.
- Persistência atrás de um "repositório" → trocar SQLite por PostgreSQL.
- Adaptador de LLM → trocar Ollama por servidor de inferência local do escritório.
- Configurações por escritório (logotipo, revisor, textos-modelo, fórmulas por município).
- Licença AGPL: escritórios podem usar livremente; quem oferecer o software modificado como serviço precisa abrir as modificações. Se no futuro você quiser licenciar comercialmente, mantenha a autoria do código (contribuições externas com termo de cessão).
