# dados_privados/ — NUNCA versionar

Esta pasta existe só na sua máquina. Tudo aqui dentro (exceto este LEIAME) é ignorado pelo Git.

| Subpasta | Conteúdo |
|---|---|
| `documentos_reais/` | PDFs reais de projetos (pranchas, matrículas, escrituras, memoriais, leis) |
| `desenvolvimento/` | Exemplos reais usados só para **calibrar** a leitura (sem gabarito). Examinados apenas pela versão mascarada (`scripts/mascarar_pdf.py`) |
| `gabarito_real/` | Arquivo JSON com os erros conhecidos do conjunto real (gabarito de validação final) |
| `historico/` | Banco de dados local (SQLite) com projetos, extrações e versões de relatórios |
| `relatorios/` | Relatórios exportados (PDF/DOCX) |
| `cache/` | Imagens de páginas, resultados de OCR e outros arquivos temporários |

Contém dados pessoais (LGPD). Faça backup apenas em mídia sua (HD externo, nuvem particular criptografada), nunca no GitHub.
