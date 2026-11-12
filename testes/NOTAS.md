# Notas de trabalho

## Feito
- Relatório de atendimentos (`views/download_planilha_page.py`): o rodapé
  mostra "Total de exames" em vez de "Total de linhas".
  Regra: conta como exame a linha com valor do exame ou taxa do aparelho > 0
  (só a 1ª linha de cada exame recebe esses valores; as linhas extras de
  procedimento ficam zeradas). Setembro/2026: 361 linhas -> 353 exames.
- `testes/gerar_pdfs_teste.py`: gera o relatório fora do Streamlit para um mês.
  Uso: `python testes/gerar_pdfs_teste.py 2026 9`. Os PDFs gerados ficam fora
  do git (têm dados de pacientes).

## Próximo passo em discussão: ID único por exame
Coluna nova `id_exame` na `base_dados`, repetida nas linhas de procedimento do
mesmo exame. Total de exames = quantidade de IDs distintos.

Cuidados:
1. A tela de edição em "Download de Dados" regrava a aba com a lista fixa
   `COLUNAS_BASE_DADOS_EDITAVEL` — incluir `id_exame` nela, senão os IDs somem.
2. Linhas criadas fora de "Inserir Atendimentos" (tela de configuração ou
   digitação direta no Sheets) ficam sem ID — gerar lá também e manter a regra
   valor/taxa como reserva no relatório.
3. Dados antigos (1.521 linhas): backup da aba, preencher IDs uma vez com a
   regra valor/taxa, conferir que o total de exames por mês não mudou
   (jun 359, jul 374, ago 405, set 353).
4. Linha 137 (10/06/2026, atendimento 55163967, Colonoscopia R$ 700 sem taxa):
   conferir se é exame real ou erro de lançamento.

Ordem sugerida: backup -> código -> teste local -> preencher antigos -> conferir.
