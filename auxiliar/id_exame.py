"""
Identificador único de exame (coluna `id_exame` da aba base_dados).

Um exame com vários procedimentos ocupa várias linhas na base; todas
elas repetem o mesmo `id_exame`. Assim, o total de exames é a
quantidade de IDs distintos.
"""

from __future__ import annotations

import re
import uuid

import pandas as pd


COLUNA_ID_EXAME = "id_exame"

# O prefixo impede que o Google Sheets (modo USER_ENTERED) interprete
# o ID como número (ex.: "12e45" viraria notação científica).
PREFIXO_ID_EXAME = "EX-"


def gerar_id_exame() -> str:
    """
    Gera um novo ID de exame, ex.: "EX-3f9a1c2b7d4e".
    """
    return f"{PREFIXO_ID_EXAME}{uuid.uuid4().hex[:12]}"


def _valor_numerico(valor) -> float:
    """
    Converte valores da planilha ("R$ 1.234,56", "700", 700.0, "")
    em float. Valores inválidos viram 0.
    """
    if valor is None:
        return 0.0

    if isinstance(valor, (int, float)):
        return 0.0 if pd.isna(valor) else float(valor)

    texto = re.sub(r"[^\d,.\-]", "", str(valor))

    if not texto:
        return 0.0

    if "," in texto:
        texto = texto.replace(".", "").replace(",", ".")

    try:
        return float(texto)
    except ValueError:
        return 0.0


def linha_inicia_exame(linha: pd.Series) -> bool:
    """
    Regra de reserva (usada quando a linha não tem ID): só a primeira
    linha de cada exame recebe valor do exame ou taxa do aparelho; as
    linhas extras de procedimento ficam zeradas.
    """
    return (
        _valor_numerico(linha.get("valor_exame")) > 0
        or _valor_numerico(linha.get("taxa_aparelho")) > 0
    )


def _texto(valor) -> str:
    if valor is None or (not isinstance(valor, str) and pd.isna(valor)):
        return ""
    return str(valor).strip()


def _chave_exame(linha: pd.Series) -> tuple[str, str, str]:
    return (
        _texto(linha.get("data")),
        _texto(linha.get("numero_atendimento")),
        _texto(linha.get("nome_exame")),
    )


def preencher_ids_exame(
    dataframe: pd.DataFrame,
) -> pd.DataFrame:
    """
    Devolve uma cópia do DataFrame com a coluna `id_exame` preenchida
    nas linhas que estiverem sem ID. Linhas que já têm ID não mudam.

    Para linhas sem ID:
    - linha com valor do exame ou taxa do aparelho > 0 inicia um
      exame novo (ID novo);
    - linha zerada é um procedimento extra: recebe o ID do exame
      anterior com mesma data, atendimento e nome do exame. Se não
      houver nenhum, vira um exame próprio.
    """
    dataframe = dataframe.copy()

    if COLUNA_ID_EXAME not in dataframe.columns:
        dataframe[COLUNA_ID_EXAME] = ""

    ids = [
        _texto(valor)
        for valor in dataframe[COLUNA_ID_EXAME].tolist()
    ]

    ultimo_id_por_chave: dict[tuple[str, str, str], str] = {}
    pendentes: list[tuple[int, tuple[str, str, str]]] = []

    for posicao, (_, linha) in enumerate(dataframe.iterrows()):
        chave = _chave_exame(linha)

        if ids[posicao]:
            ultimo_id_por_chave[chave] = ids[posicao]
            continue

        if linha_inicia_exame(linha):
            ids[posicao] = gerar_id_exame()
            ultimo_id_por_chave[chave] = ids[posicao]

        elif chave in ultimo_id_por_chave:
            ids[posicao] = ultimo_id_por_chave[chave]

        else:
            # O exame pode aparecer mais abaixo (ex.: linha nova
            # adicionada no fim do editor). Resolve depois.
            pendentes.append((posicao, chave))

    for posicao, chave in pendentes:
        if chave not in ultimo_id_por_chave:
            ultimo_id_por_chave[chave] = gerar_id_exame()

        ids[posicao] = ultimo_id_por_chave[chave]

    dataframe[COLUNA_ID_EXAME] = ids

    return dataframe


def contar_exames(
    dataframe: pd.DataFrame,
) -> int:
    """
    Total de exames = IDs distintos. Linhas sem ID (ex.: digitadas
    direto no Google Sheets) são contadas pela regra de reserva
    (valor do exame ou taxa do aparelho > 0).
    """
    if dataframe.empty:
        return 0

    if COLUNA_ID_EXAME in dataframe.columns:
        ids = dataframe[COLUNA_ID_EXAME].apply(_texto)
    else:
        ids = pd.Series("", index=dataframe.index)

    com_id = ids.ne("")

    total_com_id = int(ids[com_id].nunique())

    total_sem_id = int(
        dataframe.loc[~com_id]
        .apply(linha_inicia_exame, axis=1)
        .sum()
    ) if (~com_id).any() else 0

    return total_com_id + total_sem_id
