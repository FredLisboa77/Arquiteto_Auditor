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
