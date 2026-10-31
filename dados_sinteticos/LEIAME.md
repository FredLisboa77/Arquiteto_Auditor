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
| `gabarito.json` | O que o software deve apontar (formato em [docs/esquemas](../docs/esquemas/)) |
| `especificacao.json` | A "verdade" do projeto fictício (terreno, edificação, parâmetros, erros injetados) |

## Conjuntos (Fase 3: só pranchas)
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
- Matrículas, escrituras, memoriais, leis e o projeto com revisões R00/R01 entram na Fase 4, junto com pranchas com texto como desenho (fonte SHX) e com texto em comentários.
