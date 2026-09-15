#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Divã do Vão — ferramenta de co-produção musical a partir do aruz persa.
# Copyright (C) 2026  Divã do Vão
#
# Este programa é software livre: você pode redistribuí-lo e/ou modificá-lo
# sob os termos da GNU General Public License, versão 3, publicada pela Free
# Software Foundation. Ele é distribuído na esperança de ser útil, mas SEM
# NENHUMA GARANTIA. Veja o arquivo LICENSE.
#
"""
Gera os .html do projeto a partir dos .md — só com a stdlib.

Por que existe: HANDOUT.md/.html e PROCESSO_INTERFACE.md/.html eram mantidos à
mão, em paralelo. Dois arquivos com o mesmo conteúdo e nenhum vínculo divergem;
já tinham divergido. Agora o .md é a fonte e o .html é derivado.

    python3 docs/gerar_html.py            # regera os dois
    python3 docs/gerar_html.py --conferir # falha se algum estiver desatualizado (CI)
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
PARES = [
    (RAIZ / "handout/HANDOUT.md", RAIZ / "handout/HANDOUT.html",
     "Handout — Divã do Vão"),
    (RAIZ / "docs/PROCESSO_INTERFACE.md", RAIZ / "docs/PROCESSO_INTERFACE.html",
     "Processo da interface — Divã do Vão"),
]

ESTILO = """body{font-family:Georgia,serif;max-width:820px;margin:0 auto;padding:24px 18px 80px;
background:#12100c;color:#efe8da;font-size:17px;line-height:1.6}
h1,h2,h3{color:#d0a94b} h1{border-bottom:2px solid #332d22;padding-bottom:.2em}
h2{border-bottom:1px solid #332d22;padding-bottom:.2em;margin-top:1.8em}
code,pre{background:#0e0c08;color:#d0a94b;border:1px solid #332d22;border-radius:6px}
code{padding:1px 5px;font-size:.9em} pre{padding:12px;overflow-x:auto;font-size:.82rem;color:#b0a390}
table{border-collapse:collapse;width:100%;font-size:.9rem} th,td{border:1px solid #332d22;padding:7px 10px;text-align:left}
th{color:#c06a3c} a{color:#c06a3c} blockquote{border-left:3px solid #c06a3c;padding-left:14px;color:#b0a390;font-style:italic}
em{color:#b0a390} del{color:#6b6255} hr{border:none;border-top:1px solid #332d22;margin:2em 0}"""


def _inline(texto: str) -> str:
    """Formatação de linha: código, negrito, itálico, riscado e links."""
    partes = re.split(r"(`[^`]+`)", texto)
    saida = []
    for i, parte in enumerate(partes):
        if i % 2:                                   # dentro de crase: literal
            saida.append(f"<code>{html.escape(parte[1:-1])}</code>")
            continue
        p = html.escape(parte)
        p = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', p)
        p = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", p)
        p = re.sub(r"~~([^~]+)~~", r"<del>\1</del>", p)
        p = re.sub(r"(?<![*\w])\*([^*]+)\*(?!\*)", r"<em>\1</em>", p)
        saida.append(p)
    return "".join(saida)


def para_html(md: str, titulo: str) -> str:
    corpo, i, linhas = [], 0, md.split("\n")
    while i < len(linhas):
        linha = linhas[i]
        if linha.startswith("```"):                 # bloco de código
            i += 1
            bloco = []
            while i < len(linhas) and not linhas[i].startswith("```"):
                bloco.append(html.escape(linhas[i])); i += 1
            corpo.append("<pre>" + "\n".join(bloco) + "</pre>")
        elif linha.startswith("|"):                 # tabela
            tabela = []
            while i < len(linhas) and linhas[i].startswith("|"):
                tabela.append(linhas[i]); i += 1
            corpo.append(_tabela(tabela)); continue
        elif re.match(r"^\s*[-*] ", linha):         # lista não ordenada
            itens = []
            while i < len(linhas) and re.match(r"^\s*[-*] ", linhas[i]):
                texto = re.sub(r"^\s*[-*] ", "", linhas[i])
                itens.append("<li>" + _inline(texto) + "</li>")
                i += 1
            corpo.append("<ul>" + "".join(itens) + "</ul>"); continue
        elif re.match(r"^\d+\. ", linha):           # lista ordenada
            itens = []
            while i < len(linhas) and re.match(r"^\d+\. ", linhas[i]):
                texto = re.sub(r"^\d+\. ", "", linhas[i])
                itens.append("<li>" + _inline(texto) + "</li>")
                i += 1
            corpo.append("<ol>" + "".join(itens) + "</ol>"); continue
        elif linha.startswith("> "):
            corpo.append(f"<blockquote>{_inline(linha[2:])}</blockquote>")
        elif linha.startswith("#"):
            nivel = len(linha) - len(linha.lstrip("#"))
            corpo.append(f"<h{nivel}>{_inline(linha[nivel:].strip())}</h{nivel}>")
        elif linha.strip() in ("---", "***"):
            corpo.append("<hr>")
        elif linha.strip():
            # um parágrafo vai até a linha em branco: as quebras de linha do
            # .md são de largura de coluna, não de parágrafo
            paragrafo = []
            while (i < len(linhas) and linhas[i].strip()
                   and not linhas[i].startswith(("#", "|", ">", "```"))
                   and not re.match(r"^\s*[-*] |^\d+\. ", linhas[i])
                   and linhas[i].strip() not in ("---", "***")):
                paragrafo.append(linhas[i].strip())
                i += 1
            corpo.append("<p>" + _inline(" ".join(paragrafo)) + "</p>")
            continue
        i += 1
    return (f"<!DOCTYPE html><html lang=pt-BR><head><meta charset=utf-8>"
            f"<meta name=viewport content='width=device-width,initial-scale=1'>"
            f"<title>{html.escape(titulo)}</title><style>\n{ESTILO}\n</style></head>"
            f"<body>\n" + "\n".join(corpo) +
            "\n<hr><p><em>Gerado de " + "" +
            "</em></p></body></html>\n")


def _tabela(linhas: list[str]) -> str:
    def celulas(l):
        return [c.strip() for c in l.strip().strip("|").split("|")]
    cabecalho = celulas(linhas[0])
    corpo = [celulas(l) for l in linhas[2:]] if len(linhas) > 2 else []
    th = "".join(f"<th>{_inline(c)}</th>" for c in cabecalho)
    trs = "".join("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in linha) + "</tr>"
                  for linha in corpo)
    return f"<table><thead><tr>{th}</tr></thead><tbody>{trs}</tbody></table>"


def main(conferir: bool = False) -> int:
    desatualizados = []
    for origem, destino, titulo in PARES:
        gerado = para_html(origem.read_text(encoding="utf-8"), titulo).replace(
            "Gerado de </em>", f"Gerado de {origem.name} por docs/gerar_html.py</em>")
        atual = destino.read_text(encoding="utf-8") if destino.exists() else ""
        if conferir:
            if gerado != atual:
                desatualizados.append(destino.relative_to(RAIZ))
        else:
            destino.write_text(gerado, encoding="utf-8")
            print(f"gerado: {destino.relative_to(RAIZ)}")
    if desatualizados:
        print("HTML desatualizado (rode python3 docs/gerar_html.py):")
        for d in desatualizados:
            print("  ", d)
        return 1
    if conferir:
        print("HTML em dia com os .md")
    return 0


if __name__ == "__main__":
    sys.exit(main(conferir="--conferir" in sys.argv))
