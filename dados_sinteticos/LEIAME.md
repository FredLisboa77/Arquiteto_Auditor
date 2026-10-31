# Base sintética

Documentos **fictícios** para desenvolver e testar o Arquiteto Auditor. Não há dados pessoais reais aqui. Nomes, endereços, municípios e números são gerados pelo Faker (`pt_BR`), e todas as folhas trazem a marca "DOCUMENTO FICTÍCIO".

## Como regerar
```powershell
.venv\Scripts\python -m dados_sinteticos.geradores.gerar_base            # todos os conjuntos
.venv\Scripts\python -m dados_sinteticos.geradores.gerar_base sint-003   # um só
```
As assinaturas digitais usam certificados fictícios gerados na hora. Por isso, regerar muda os bytes dos PDFs, mas não o conteúdo. Regere só quando a especificação ou o desenho mudarem.

## Estrutura de cada conjunto (`projetos/sint-NNN/`)
| Arquivo | Conteúdo |
|---|---|
| `pranchas.pdf` ou `prancha_01..03.pdf` | 01 situação + localização + quadro de áreas · 02 plantas baixas · 03 corte e fachada |
| `matricula.pdf` | Matrícula **escaneada** (só imagem): certidão de inteiro teor moderna ou ficha antiga datilografada |
| `escritura.pdf` | Escritura de compra e venda **escaneada**, em papel de segurança |
| `memorial.pdf` | Memorial descritivo: digitado (texto selecionável, assinado digitalmente) ou impresso, assinado à caneta e escaneado |
| `lei_municipal.pdf` | Lei de uso e ocupação do solo do município fictício (20 a 23 páginas, texto selecionável) |
| `norma_condominio.pdf` | Regulamento de obras do condomínio (texto ou escaneado) |
| `gabarito.json` | O que o software deve apontar (formato em [docs/esquemas](../docs/esquemas/)) |
| `especificacao.json` | A "verdade" do projeto fictício (terreno, edificação, parâmetros, erros injetados e resumo da matrícula e da escritura) |
| `verdade_ocr.json` | Texto impresso de cada página escaneada (sem carimbos, selos e assinaturas), para medir o OCR |

## Conjuntos
| Conjunto | Carimbo | Quadro | Folha | Erros injetados |
|---|---|---|---|---|
| sint-001 | 0 tabela | 0 tabela com linhas | A1 | nenhum (conjunto limpo, mede falsos alarmes) |
| sint-002 | 1 coluna lateral | 1 texto com pontilhado | A2 | área do terreno divergente; matrícula divergente (cotas com ponto decimal) |
| sint-003 | 2 faixa inferior | 2 colunas, unidade no cabeçalho | A3 | cotas omitidas (recuo de fundos, altura total); sem Norte (cotas sem rótulo) |
| sint-004 | 3 nomes alternativos + revisões | 3 valor antes do rótulo | A1 | sem assinatura do proprietário; proprietário omitido; muro acima do limite |
| sint-005 | 0 | 2 | A2 | assinatura alterada após assinar; soma das áreas errada; revisão divergente (caixa mista) |
| sint-006 | 1 | 3 | A3 | TO excedida; recuo frontal insuficiente; altura excedida |
| sint-007 🔒 | 2 | 0 | A2 | área divergente; testada sem cota; sem Norte; sem assinatura do autor |
| sint-008 🔒 | 3 | 1 | A3 | TO declarada errada; matrícula divergente; muro acima do limite |
| sint-009 (R00) | 1 | 0 | A2 | matrícula divergente; TO excedida; área total do memorial diferente do quadro; muro acima do limite |
| sint-010 (R01) | 1 | 0 | A2 | revisão da sint-009: TO excedida e muro (mantidos); cota de altura omitida (novo) |

### Matrícula, escritura, memorial, lei e norma (Fase 4)
| Conjunto | Matrícula (estilo, qualidade) | Escritura | Memorial | Lei (modelo, zona) | Norma do condomínio | Particularidade |
|---|---|---|---|---|---|---|
| sint-001 | certidão, boa | boa | texto | A, ZR-2 | texto | escritura com a área anterior à retificação |
| sint-002 | ficha, média | boa | texto | B, ZR-2 | escaneada, média | alienação fiduciária ainda ativa (ônus) |
| sint-003 | certidão, média | média | escaneado, média | A, ZR-3 | texto | só um ato (venda) |
| sint-004 | certidão, boa | ruim | texto | B, ZR-3 | texto | 5 atos |
| sint-005 | ficha, ruim | boa | texto | A, ZR-1 | escaneada, boa | — |
| sint-006 | certidão, boa | média | escaneado, boa | B, ZR-1 | texto | 6 atos |
| sint-007 🔒 | certidão, média | boa | texto | A, ZR-2 | escaneada, ruim | escritura com a área anterior à retificação |
| sint-008 🔒 | ficha, boa | média | escaneado, ruim | B, ZR-1 | texto | escritura com a área anterior à retificação |
| sint-009 / sint-010 | certidão, boa | boa | texto | A, ZR-2 | texto | mesmo projeto em duas revisões (documentos registrais idênticos) |

Qualidades do escaneamento: **boa** = escaneamento de mesa limpo (300 dpi, colorido, quase sem inclinação), o caso típico dos exemplos reais; **média** e **ruim** = testes de resistência do OCR (inclinação de até 3°, desbotamento, sujeira, baixa resolução).

### Revisões R00 → R01 (sint-009 → sint-010)
Mesmo projeto (mesma matrícula, lote, quadra, condomínio e título), reapresentado corrigido. A revisão aparece nas pranchas e no memorial. O gabarito da R01 informa `conjunto_anterior: "sint-009"` e a comparação esperada, item a item:

| Item | R00 | R01 | Comparação |
|---|---|---|---|
| `ID_MATRICULA` | divergente | atende | resolvido |
| `AREA_CONSTR_TOTAL` (memorial × quadro) | divergente | atende | resolvido |
| `TO_MAX` | não atende | não atende | pendente |
| `MURO_ALTURA_MAX` | não atende | não atende | pendente |
| `COTA_INDEFINIDA` (altura total) | — | não atende | novo |
| `ALTURA_MAX` | atende | não verificável | não verificável agora |

🔒 **Reservados para avaliação** (`reservado_avaliacao: true`): não use estes conjuntos ao desenvolver ou ajustar regras de extração. Eles servem para medir se as regras generalizam (docs/05-avaliacao.md §4).

## Convenções da verdade sintética
- O projeto base sempre atende a todos os parâmetros; cada erro injetado produz exatamente um item "não atende" ou "divergente".
- Pranchas e memorial (documentos do autor) mostram os mesmos valores. Matrícula e escritura mostram a verdade registral.
- Índices declarados (TO, CA, TP) são calculados com os valores impressos na própria prancha.
- Hierarquia: a prefeitura prevalece sobre o condomínio. A altura de muro é definida só pelo condomínio.
- Uma cota omitida torna "não verificável" o parâmetro que dependia dela (ex.: sem cota de fundos → `RECUO_FUNDOS` não verificável).
- As pranchas trazem de propósito muitos números que **não** são os procurados, para testar se a extração distingue o que importa: cotas internas e encadeadas, níveis, áreas de ambientes, dimensões de esquadrias, largura do passeio, beiral e inclinações.
- O carimbo traz um escritório fictício. No estilo 3, traz também o CPF do proprietário, **sempre com dígitos verificadores inválidos**: a verificação anti-vazamento bloqueia CPF válido. O relatório do software nunca deve reproduzir esse CPF.
- O Norte aparece como seta ou como rosa dos ventos (N, S, L, O).
- A **matrícula** mostra a verdade registral atual (área e proprietário). Ela pode trazer de propósito valores antigos mudados por atos posteriores: área corrigida por retificação, primeiro comprador que já vendeu, ônus registrado e cancelado.
- A **escritura** é a da venda ao proprietário atual e é coerente com o registro (partes, CPFs, valor, livro e folhas). Ela descreve o imóvel na data da venda: se a retificação veio depois, mostra a área antiga.
- Matrículas e escrituras imitam o estilo dos exemplos reais (docs/06-calibracao-exemplos-reais.md §5): papel de segurança, brasão fictício, carimbo "CÓPIA", rubricas, selo com QR code. Todo CPF e CNPJ tem dígitos verificadores inválidos.
- O **memorial** é documento do autor: repete os valores das pranchas, inclusive erros e omissões (cota omitida na prancha também não aparece no memorial) e as assinaturas presentes ou ausentes. Traz especificações técnicas com números que não são procurados (fck, pé-direito, caixa d'água, inclinação do telhado, piscina). O erro `memorial_area_divergente` (área total do memorial ≠ quadro) existe, mas ainda não foi usado em nenhum conjunto.
- A **lei municipal** traz os parâmetros da prefeitura para a zona do lote, no meio de 8 zonas com valores diferentes. A zona do lote é identificável pelo Anexo I (o perímetro dela cita o condomínio) e vai no campo `zona` do gabarito. Modelo **A**: parâmetros num anexo em tabela (uma linha por zona). Modelo **B**: parâmetros em artigos por zona, tabela invertida e um artigo com **redação alterada**, que cita o valor antigo do recuo frontal (armadilha: vale o novo). Há exceções que não se aplicam ao lote (esquina, testada < 10 m, edícula, prédios acima de 2 pavimentos), definições das fórmulas de TO, CA e TP e muitos números de distração (multas, prazos, vias, vagas, ruído).
- A **norma do condomínio** define a altura do muro (só ela define) e às vezes repete ou endurece parâmetros da prefeitura. Quando a TO do condomínio é menor que a da lei, há **conflito de propósito**: vale a prefeitura e o valor do condomínio vira observação. Distrações: gradil de 1,20 m, tapume de 2,20 m, calçada de 1,50 m, horário e prazo de obra.
- As variações de prancha do doc 06 §4 ainda serão acrescentadas na Fase 4.
- Os documentos sem assinatura digital têm bytes reprodutíveis: regerar a base só muda os arquivos assinados (pranchas e memoriais digitados), porque os certificados fictícios são criados na hora.
