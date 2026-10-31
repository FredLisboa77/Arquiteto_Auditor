# 06 — Calibração com exemplos reais

> Achados **estruturais** tirados de documentos reais, examinados apenas em versão mascarada (`scripts/mascarar_pdf.py`) e conferidos pelo usuário antes do compartilhamento. Este documento não contém dados pessoais nem valores que identifiquem imóveis.
>
> Fontes: diagnóstico estatístico do conjunto original (5 PDFs) e versão mascarada de dois exemplos de calibração (uma planta baixa; um projeto executivo de 11 folhas). Registro de 30/10/2026.

---

## 1. Onde está o texto

| Achado | Consequência para o software |
|---|---|
| Parte do texto está em fonte TrueType (selecionável) e parte em **fonte SHX convertida em traços**; nas pranchas A1, de 96% a 99% dos elementos de desenho são traços com até 4 mm. | A leitura não pode depender só do texto selecionável. |
| O AutoCAD gravou o texto SHX também como **comentários invisíveis do tipo "Square"**, com o texto e o retângulo de posição: até 226 comentários e 99 números por folha. | **Fonte de texto nº 2:** juntar o texto selecionável com os comentários, cada um com sua posição, numa única lista de "palavras" da página. O OCR fica como último recurso. |
| O **carimbo** tem os rótulos em texto ("PROPRIETÁRIO", "RESPONSÁVEL PELO PROJETO", "FOLHA", "DATA", "REVISÃO") e os **valores em comentários** (nome do projeto, endereço, condomínio, lote/quadra, CAU, data). | A associação rótulo → valor precisa considerar as duas fontes juntas, pela posição. |
| O **quadro de áreas** pode estar inteiro em comentários, com rótulos quebrados em duas linhas ("COEFICIENTE DE" / "APROVEITAMENTO"; "TAXA DE" / "PERMEABILIDADE"). | Juntar linhas próximas antes de interpretar rótulos. |
| Há folhas **sem nenhum texto** (perspectivas e imagens) e uma **capa** com dados de identificação em texto corrido. | Classificar as folhas. A capa é uma boa fonte de identificação, mas é texto livre. |

## 2. Formatos de número e notação

| Achado | Exemplo (formato) | Consequência |
|---|---|---|
| **Ponto decimal** em todo o desenho | `204.11 m²`, `+0.40`, `3.00` | O normalizador já aceita ponto com 2 casas. "1.000" continua ambíguo. |
| Valor com **prefixo de letra e "="** | `A=31.15m²`, `C=0.95`, `H=9.14m`, `I=12%` | Reconhecer `A=` (área), `C=` (coeficiente), `H=` (altura), `i=`/`I=` (inclinação). |
| **Códigos de controle do AutoCAD** no texto | `56.10%%%` (porcentagem), possivelmente `%%c` (diâmetro), `%%d` (grau), `%%p` (±) | **O normalizador precisa traduzir `%%%` → `%`** e os demais códigos antes de ler o número. |
| Esquadrias como dimensão composta | `0.80x2.10/1.10` (largura × altura / peitoril) | Distração: não confundir com cotas de recuo. |
| Desigualdade em rampas | `i ≤ 8,33 %`, `<9%` | Distração. |
| Escala no título da folha | `ESCALA 1:50`, `ESCALA 1:250` | A escala está no título do desenho, não no carimbo. |
| Folha "N de M" como **dois números grandes** empilhados | `01` acima de `07` | Associar ao rótulo "FOLHA" por posição. |

## 3. Conteúdo das folhas

| Achado | Consequência |
|---|---|
| **Recuos não têm rótulo** ("RECUO" não aparece). São cotas soltas entre a divisa e a edificação. | Confirma o risco R2. O recuo é obtido pela **geometria** (cota entre a linha do lote e a projeção) ou proposto ao revisor para confirmação; não por palavra-chave. |
| **Muros com altura escrita** e alturas diferentes no mesmo projeto | `MURO H=0.80m`, `MURO H=2.20m`, `MURO DE DIVISA H=2.50m` | `MURO_ALTURA_MAX` é verificado **para cada muro** encontrado (frente e divisa podem ter limites diferentes). |
| A **planta de localização lista os lotes vizinhos com área**, inclusive o lote do projeto | `LOTE 6 … 200.16 m²` | Distração forte para `TERRENO_AREA`: escolher o valor associado ao lote do projeto. |
| O **quadro de áreas** inclui itens que mexem nos índices: área coberta, área da piscina, área permeável, altura | `ÁREA DA PISCINA A=9.00m²` | As fórmulas por município (piscina conta ou não na TO/permeabilidade) ganham importância. |
| **Norte em rosa dos ventos girada** (não aponta para cima), com letras N, E, O, S. "E" de Este, não "L" de Leste. As letras podem estar em comentários. | Aceitar E ou L. O ângulo da rosa é uma informação útil, mas não é exigido. |
| As áreas de ambiente vêm com o nível ao lado | `A = 38.15m²` + `+0.30` | Distração. |
| Os **cortes** trazem alturas sem rótulo (`9.14`, `2.40`); a altura total coincide com `H=9.14m` do quadro. | A altura da edificação vem preferencialmente do quadro de áreas, conferida com o corte. |
| Campo "REVISÃO" presente, mas aparentemente **sem valor**. | `ID_REVISAO` precisa tratar "revisão não informada" (pendência), não só divergência. |

## 4. O que muda no plano

- **Fase 4 (base sintética):** os itens acima entram como variações dos conjuntos sintéticos:
  - texto em comentários (SHX) e texto como traços;
  - carimbo com valores em comentários;
  - quadro de áreas em comentários, com rótulos quebrados;
  - ponto decimal e notação `A=` / `H=` / `C=`;
  - códigos `%%%`;
  - recuos sem rótulo;
  - muros com `MURO H=`;
  - localização com lotes vizinhos e suas áreas;
  - rosa dos ventos girada, com "E";
  - folha "N de M" em dois números;
  - capa;
  - folhas sem texto;
  - revisão em branco.
- **Fase 5 (ingestão):** uma lista única de palavras por página, juntando texto selecionável, comentários e OCR, com origem e posição.
- **Fase 6 (pranchas):** recuos por geometria, com confirmação do revisor. Quadro de áreas com rótulos em várias linhas. Carimbo com rótulos em texto e valores em comentários.
- **Normalizador de números:** traduzir os códigos de controle do AutoCAD (`%%%`, `%%c`, `%%d`, `%%p`).

---

## 5. Documentos registrais escaneados (escritura e certidão de inteiro teor)

> Registro de 31/10/2026. Fontes: uma escritura (4 páginas) e uma certidão de inteiro teor da matrícula (4 páginas), examinadas só por **estatísticas da imagem** e por uma **versão mascarada** (`scripts/mascarar_escaneado.py`: cada palavra vira uma barra), conferida pelo usuário antes de ser vista. Nenhum dado foi lido.

### 5.1 Digitalização
| Achado | Consequência |
|---|---|
| Todas as páginas são **imagem** (sem texto selecionável), JPEG colorido a **300 dpi**, de 1,6 a 2,4 MB por página. | A ingestão (Fase 5) precisa do OCR para esses documentos. Arquivos reais têm de 7 a 9 MB. |
| Folha **Carta** (216 × 279 mm), não A4. | Os sintéticos alternam Carta e A4. |
| Inclinação quase nula (0 a 0,5°) e ruído baixo: **escaneamento de mesa limpo**. | O caso típico é a qualidade "boa". "Média" e "ruim" ficam como testes de resistência do OCR. |

### 5.2 Papel de segurança
| Achado | Consequência |
|---|---|
| Escritura: **brasão grande amarelo-claro** como marca-d'água no centro de todas as páginas, sob o texto, e **fibras coloridas** espalhadas. Papel branco em umas páginas, amarelado em outras. | O OCR precisa tolerar fundo colorido sob o texto. A binarização não pode apagar o texto que passa por cima da marca-d'água. |
| Certidão: papel branco-azulado com **faixas de segurança nas bordas** (uma escura à esquerda, com emblema; uma de padrão verde à direita), só na frente da folha. | Ignorar as faixas das bordas (não são texto). |
| Certidão: **carimbo "CÓPIA" repetido** várias vezes, de tamanhos diferentes, por cima e ao lado do texto. Ele avisa que a certidão é cópia da original. | A palavra "CÓPIA" aparece no OCR misturada ao texto e deve ser descartada. |
| Versos quase vazios, com o texto da frente **transparecendo** fraco. | Página quase vazia não é erro: classificar como "verso". |

### 5.3 Diagramação
| Achado | Consequência |
|---|---|
| **Impressão a laser** (não datilografada), texto justificado e denso, de margem a margem. Escritura: ~30 linhas por página, entrelinha de 5,0 mm. Certidão: entrelinha de 4,3 mm. | O estilo "laser" é o padrão; a máquina de escrever fica para matrículas antigas. |
| Cabeçalho centralizado: título em letras grandes, brasão redondo, linhas do cartório/tabelionato. Na escritura, a 1ª página traz uma faixa no topo e **duas caixas com moldura** (tipo do ato, livro e folha). | Os dados do ato (livro, folha, data) ficam no cabeçalho: boa âncora para a extração (Fase 7). |
| Certidão: **rótulos em negrito e maiores** no início dos trechos (abertura e atos). | Âncora para separar os atos (R-1, AV-2…). |
| **Rubrica na margem direita** de cada página da escritura. | Distração para o OCR (rabisco na margem). |
| **Espaço em branco anulado com riscos diagonais** depois do fim do texto. | Distração: não interpretar os riscos como desenho ou texto. |
| Fecho: data e local centralizados, assinaturas azuis, carimbos (retangular e redondo, girados) e **selo com QR code** e texto ao lado. | O selo é uma área à parte; o QR code não é lido. |
