"""
Gera, fora do Streamlit, os mesmos arquivos que as páginas do app
produzem para um período fechado (padrão: mês anterior ao atual).

Roda o código das páginas sem alterações, apenas substituindo os
filtros (período / médico) e capturando os botões de download.

Uso (a partir da raiz do projeto):
    python testes/gerar_pdfs_teste.py            # mês passado
    python testes/gerar_pdfs_teste.py 2026 9     # setembro/2026
"""

from __future__ import annotations

import logging
import sys
import zipfile
from calendar import monthrange
from datetime import date
from io import BytesIO
from pathlib import Path

import streamlit as st

RAIZ = Path(__file__).resolve().parent.parent
PASTA_TESTES = Path(__file__).resolve().parent

sys.path.insert(0, str(RAIZ))
logging.getLogger("streamlit").setLevel(logging.ERROR)


class PararPagina(Exception):
    pass


def periodo_alvo() -> tuple[date, date]:
    if len(sys.argv) >= 3:
        ano, mes = int(sys.argv[1]), int(sys.argv[2])
    else:
        hoje = date.today()
        ano, mes = (
            (hoje.year - 1, 12) if hoje.month == 1
            else (hoje.year, hoje.month - 1)
        )
    return date(ano, mes, 1), date(ano, mes, monthrange(ano, mes)[1])


def executar_pagina(
    caminho: Path,
    data_inicial: date,
    data_final: date,
) -> dict[str, bytes]:
    downloads: dict[str, bytes] = {}

    def fake_date_input(*args, **kwargs):
        return (data_inicial, data_final)

    def fake_selectbox(label, options, *args, **kwargs):
        return list(options)[0]  # "Todos os médicos"

    def fake_download_button(label, data=b"", file_name="", **kwargs):
        if data:
            downloads[file_name] = data
        return False

    def fake_stop():
        raise PararPagina()

    def fake_mensagem(tipo):
        def _f(body, *args, **kwargs):
            print(f"  [{tipo}] {body}")
        return _f

    st.date_input = fake_date_input
    st.selectbox = fake_selectbox
    st.download_button = fake_download_button
    st.stop = fake_stop
    st.warning = fake_mensagem("aviso")
    st.error = fake_mensagem("erro")
    st.info = fake_mensagem("info")

    codigo = caminho.read_text(encoding="utf-8")
    try:
        exec(
            compile(codigo, str(caminho), "exec"),
            {"__name__": "__main__", "__file__": str(caminho)},
        )
    except PararPagina:
        pass

    return downloads


def main() -> None:
    data_inicial, data_final = periodo_alvo()
    pasta_saida = PASTA_TESTES / data_inicial.strftime("%Y-%m")
    pasta_saida.mkdir(parents=True, exist_ok=True)

    print(
        f"Período: {data_inicial:%d/%m/%Y} a {data_final:%d/%m/%Y}"
    )

    # Para gerar também os resumos por médico (ZIP + Excel),
    # inclua "controle_medico_page_com_pdf.py" nesta lista.
    paginas = [
        RAIZ / "views" / "download_planilha_page.py",
    ]

    for pagina in paginas:
        print(f"\n> {pagina.name}")
        downloads = executar_pagina(pagina, data_inicial, data_final)

        for nome, conteudo in downloads.items():
            if nome.endswith(".zip"):
                with zipfile.ZipFile(BytesIO(conteudo)) as zf:
                    zf.extractall(pasta_saida)
                    for item in zf.namelist():
                        print(f"  gerado: {item}")
            elif nome.startswith("controle_pagamento") and (
                pasta_saida / nome
            ).exists():
                continue  # já extraído do ZIP
            else:
                (pasta_saida / nome).write_bytes(conteudo)
                print(f"  gerado: {nome}")

    print(f"\nArquivos em: {pasta_saida}")


if __name__ == "__main__":
    main()
