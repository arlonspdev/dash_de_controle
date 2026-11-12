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

- ID único por exame (`auxiliar/id_exame.py`): coluna `id_exame` (coluna M
  da `base_dados`), formato `EX-` + 12 hex, repetida nas linhas de
  procedimento do mesmo exame. Total de exames = IDs distintos; linhas sem ID
  (digitadas direto no Sheets) contam pela regra valor/taxa > 0.
  - Gerado em: Inserir Atendimentos (1 ID por exame), editor "Editar dados"
    do Download de Dados (coluna oculta, preservada; linhas novas recebem ID
    ao salvar) e Configuração > Base de dados (ao salvar).
  - Linha zerada sem ID herda o ID do exame com mesma data + atendimento +
    nome do exame; se não houver, vira exame próprio.
  - Dados antigos preenchidos em 12/11/2026 (1.521 linhas). Backup na aba
    `base_dados_backup_2026-11-12`. Totais conferidos: jun 359, jul 374,
    ago 405, set 353 (iguais à regra antiga).

## Pendente
- Linha 137 (10/06/2026, atendimento 55163967, Colonoscopia R$ 700 sem taxa):
  conferir se é exame real ou erro de lançamento. Conta como exame nas duas
  regras.
- Apagar a aba `base_dados_backup_2026-11-12` quando tudo estiver ok.
