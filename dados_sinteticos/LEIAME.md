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

### Matrícula e escritura (Fase 4)
| Conjunto | Matrícula (estilo, qualidade) | Escritura | Particularidade |
|---|---|---|---|
| sint-001 | certidão, boa | boa | escritura com a área anterior à retificação |
| sint-002 | ficha, média | boa | alienação fiduciária ainda ativa (ônus) |
| sint-003 | certidão, média | média | só um ato (venda) |
| sint-004 | certidão, boa | ruim | 5 atos |
| sint-005 | ficha, ruim | boa | — |
| sint-006 | certidão, boa | média | 6 atos |
| sint-007 🔒 | certidão, média | boa | escritura com a área anterior à retificação |
| sint-008 🔒 | ficha, boa | média | escritura com a área anterior à retificação |

Qualidades do escaneamento: **boa** = escaneamento de mesa limpo (300 dpi, colorido, quase sem inclinação), o caso típico dos exemplos reais; **média** e **ruim** = testes de resistência do OCR (inclinação de até 3°, desbotamento, sujeira, baixa resolução).

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
- Memoriais, leis, normas de condomínio, o projeto com revisões R00/R01 e as variações de prancha do doc 06 §4 ainda serão acrescentados na Fase 4.
