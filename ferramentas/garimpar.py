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
Garimpo — achar canção dentro de 4,2 milhões de hemistíquios.

A PERGUNTA MUDOU
----------------
O colhedor pergunta "me dê versos deste metro". Esta ferramenta pergunta "onde
está o verso que fala do acampamento abandonado" — e é essa a pergunta da
canção. Quem procura canção procura assunto, imagem, afeto; o metro é o que
vem depois, de graça, porque a fonte já o declara.

COMO FUNCIONA
-------------
data/pontes.json liga um topos árabe a um registro da canção brasileira e traz
as palavras com que se garimpa. Esta ferramenta busca essas palavras no índice
(ferramentas/indexar_arabe.py) e devolve o BAYT inteiro — não o hemistíquio
solto, porque a copla é a unidade de sentido —, com poeta, era, metro, link
para a fonte, e a palavra que casou.

O ESTATUTO VIAJA COM O ACHADO
-----------------------------
Toda saída imprime o estatuto da ponte: fato_da_fonte, paralelo_formal_
observavel, comparacao_academica, genealogia_contestada ou leitura_autoral.
Isso não é enfeite. Sete das doze pontes são leitura do autor, uma é
genealogia CONTESTADA, e um achado bonito faz esquecer disso em dois minutos.
Se o estatuto não viajar com o verso, o projeto volta a confundir a leitura
dele com propriedade do corpus — que é o erro que engine/filtros.py registra
quatro vezes.

SEM ORDENAÇÃO POR QUALIDADE
---------------------------
A ordem padrão é aleatória com semente fixa. Não é preguiça: é que não existe
base para ranquear por qualidade antes de o autor julgar. Ordenar por
frequência da palavra, ou por fama do poeta, seria fabricar critério — e
engine/gosto.py existe justamente para aprender o critério de quem decide.
Aleatório com semente dá navegação sem viés e reprodutível.
"""
from __future__ import annotations

import argparse
import json
import random
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from ferramentas.indexar_arabe import sem_harakat  # noqa: E402

INDICE_PADRAO = RAIZ / ".cache_arabe/arabe.sqlite"
PONTES_PADRAO = RAIZ / "data/pontes.json"

MARCA = {
    "fato_da_fonte": "FATO DA FONTE",
    "paralelo_formal_observavel": "PARALELO FORMAL OBSERVÁVEL",
    "comparacao_academica": "COMPARAÇÃO ACADÊMICA (argumento publicado, não consenso)",
    "genealogia_contestada": "GENEALOGIA CONTESTADA — NÃO AFIRMAR DESCENDÊNCIA",
    "leitura_autoral": "LEITURA DO AUTOR — não é fato, é escolha",
}


def carregar_pontes(caminho: Path | str | None = None) -> dict:
    d = json.loads(Path(caminho or PONTES_PADRAO).read_text(encoding="utf-8"))
    return {p["id"]: p for p in d["pontes"]} | {"_meta": d}


def _frase_fts(termo: str) -> str:
    """Normaliza o termo como o índice foi normalizado, e cita para o FTS5.

    Sem isso a busca falha em silêncio: o índice guarda اطلال (alif simples) e
    quem digita أطلال (com hamza) não acha nada. Foi o primeiro erro aqui.
    """
    n = sem_harakat(termo)
    return " ".join(f'"{w}"' for w in n.split() if w)


def buscar_termo(con: sqlite3.Connection, termo: str, limite: int = 200,
                 metro: str = "", era: str = "",
                 so_dominio_publico: bool = True) -> list[dict]:
    """Hemistíquios que casam com um termo, já com a copla e a procedência."""
    sql = """
      SELECT h.id, h.poema_id, h.bayt, h.metade, h.texto,
             p.poeta, p.era, p.metro, p.metro_rom, p.tema, p.url, p.titulo,
             p.dominio_publico_provavel
        FROM fts JOIN hemistiquios h ON h.id = fts.rowid
                 JOIN poemas p ON p.id = h.poema_id
       WHERE fts MATCH ?
    """
    args: list = [_frase_fts(termo)]
    if so_dominio_publico:
        sql += " AND p.dominio_publico_provavel = 1"
    if metro:
        sql += " AND (p.metro = ? OR p.metro_rom = ?)"
        args += [metro, metro]
    if era:
        sql += " AND p.era LIKE ?"
        args.append(f"%{era}%")
    sql += " LIMIT ?"
    args.append(limite)

    saida = []
    for r in con.execute(sql, args).fetchall():
        (hid, pid, bayt, metade, texto, poeta, era_, metro_, mrom, tema, url,
         titulo, pub) = r
        # a copla inteira: a unidade de sentido é o bayt, não o hemistíquio
        par = con.execute(
            "SELECT metade, texto FROM hemistiquios WHERE poema_id=? AND bayt=?"
            " ORDER BY metade", (pid, bayt)).fetchall()
        saida.append({
            "hemistiquio_id": hid, "poema_id": pid, "bayt": bayt,
            "casou_na_metade": metade,
            "sadr": next((t for m, t in par if m == 1), ""),
            "ajuz": next((t for m, t in par if m == 2), ""),
            "termo_que_casou": termo,
            "poeta": poeta, "era": era_, "metro": metro_, "metro_rom": mrom,
            "tema": tema, "url": url, "titulo": titulo,
            "dominio_publico_provavel": bool(pub),
        })
    return saida


def garimpar(ponte_id: str, con: sqlite3.Connection, pontes: dict, *,
             por_termo: int = 60, metro: str = "", era: str = "",
             semente: str = "diva", limite: int = 12) -> dict:
    """Garimpa uma ponte: busca todos os seus termos e devolve candidatos.

    Deduplica por copla — a mesma copla pode casar em vários termos, e contá-la
    duas vezes inflaria a sensação de abundância.
    """
    ponte = pontes[ponte_id]
    achados: dict[tuple, dict] = {}
    por_termo_n: dict[str, int] = {}
    for termo in ponte["busca"]["palavras"]:
        rs = buscar_termo(con, termo, por_termo, metro, era)
        por_termo_n[termo] = len(rs)
        for r in rs:
            chave = (r["poema_id"], r["bayt"])
            if chave in achados:
                achados[chave]["termo_que_casou"] += f" + {termo}"
            else:
                achados[chave] = r
    todos = list(achados.values())
    random.Random(f"{semente}:{ponte_id}").shuffle(todos)
    return {
        "ponte": ponte_id,
        "topos": ponte["topos"]["nome"],
        "topos_arabe": ponte["topos"]["arabe"],
        "registro_brasileiro": ponte["registro_brasileiro"]["nome"],
        "estatuto": ponte["estatuto"],
        "aviso": MARCA[ponte["estatuto"]],
        "camada_que_autoriza": ponte["consequencia_musical"]["camada"],
        "garantia_musical": ponte["consequencia_musical"]["garantia"],
        "achados_por_termo": por_termo_n,
        "coplas_distintas": len(todos),
        "amostra": todos[:limite],
    }


def panorama(con: sqlite3.Connection, pontes: dict) -> list[dict]:
    """Quantas coplas cada ponte alcança. Serve para saber onde há material."""
    linhas = []
    for pid, p in pontes.items():
        if pid == "_meta":
            continue
        n = 0
        for termo in p["busca"]["palavras"]:
            n += con.execute("SELECT count(*) FROM fts WHERE fts MATCH ?",
                             (_frase_fts(termo),)).fetchone()[0]
        linhas.append({"ponte": pid, "arabe": p["topos"]["arabe"],
                       "registro": p["registro_brasileiro"]["nome"],
                       "estatuto": p["estatuto"], "hemistiquios": n,
                       "camada": p["consequencia_musical"]["camada"]})
    return sorted(linhas, key=lambda x: -x["hemistiquios"])


def _cli(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(
        description="Garimpa canção no corpus árabe, por ponte temática.",
        epilog="Exemplos:\n"
               "  %(prog)s --panorama\n"
               "  %(prog)s --ponte atlal_saudade_de_lugar\n"
               "  %(prog)s --ponte ghayth_a_chuva_que_salva --era الجاهلي --limite 6\n"
               "  %(prog)s --ponte qafiya_radif_refrao --json",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ponte", help="id da ponte em data/pontes.json")
    ap.add_argument("--panorama", action="store_true", help="material por ponte")
    ap.add_argument("--listar", action="store_true", help="lista as pontes")
    ap.add_argument("--termo", help="busca um termo solto, fora das pontes")
    ap.add_argument("--metro", default="", help="filtra por metro (árabe ou romanizado)")
    ap.add_argument("--era", default="", help="filtra por era (trecho do nome em árabe)")
    ap.add_argument("--limite", type=int, default=8)
    ap.add_argument("--semente", default="diva")
    ap.add_argument("--indice", default=str(INDICE_PADRAO))
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    pontes = carregar_pontes()
    if a.listar:
        for pid, p in pontes.items():
            if pid == "_meta":
                continue
            print(f"  {pid:34s} {p['topos']['arabe']:22s} -> {p['registro_brasileiro']['nome']}")
            print(f"  {'':34s} {MARCA[p['estatuto']]}")
        return 0

    idx = Path(a.indice)
    if not idx.exists():
        print(f"índice não encontrado em {idx}.\n"
              f"Monte com: python3 ferramentas/indexar_arabe.py <parquets do Ashaar>",
              file=sys.stderr)
        return 2
    con = sqlite3.connect(f"file:{idx}?mode=ro", uri=True)

    if a.panorama:
        linhas = panorama(con, pontes)
        if a.json:
            print(json.dumps(linhas, ensure_ascii=False, indent=1))
            return 0
        print(f"{'hemist.':>9}  {'ponte':34s} {'camada':22s} estatuto")
        print("-" * 108)
        for l in linhas:
            print(f"{l['hemistiquios']:9,d}  {l['ponte']:34s} {l['camada']:22s} {l['estatuto']}")
        print(f"\n{'':9}  (hemistíquios somados por termo; uma copla pode casar em vários)")
        return 0

    if a.termo:
        rs = buscar_termo(con, a.termo, a.limite, a.metro, a.era)
        print(f"termo '{a.termo}' (indexado como '{sem_harakat(a.termo)}'): {len(rs)} achados\n")
        for r in rs[:a.limite]:
            print(f"  {r['poeta']} · {r['era']} · {r['metro']}")
            print(f"    {r['sadr']}")
            print(f"    {r['ajuz']}")
            print(f"    {r['url']}\n")
        return 0

    if not a.ponte:
        ap.error("use --ponte, --panorama, --listar ou --termo")
    if a.ponte not in pontes:
        ap.error(f"ponte desconhecida. Veja --listar")

    r = garimpar(a.ponte, con, pontes, metro=a.metro, era=a.era,
                 semente=a.semente, limite=a.limite)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 0

    p = pontes[a.ponte]
    print(f"PONTE  {r['topos_arabe']}  ({r['topos']})  ->  {r['registro_brasileiro']}")
    print(f"ESTATUTO  {r['aviso']}")
    print(f"AUTORIZA  camada '{r['camada_que_autoriza']}' — garantia: {r['garantia_musical']}")
    print(f"\n{p['topos']['o_que_e']}")
    print(f"\nEm comum: {p['registro_brasileiro']['o_que_tem_em_comum']}")
    print(f"\nO que derrubaria: {p.get('o_que_derrubaria') or p.get('o_que_confirmaria','—')}")
    if "USO_PERMITIDO" in p:
        print(f"\n!! USO PERMITIDO: {p['USO_PERMITIDO']}")
    print(f"\ncoplas distintas encontradas: {r['coplas_distintas']:,}")
    print("achados por termo:", ", ".join(
        f"{t}={n}" for t, n in r["achados_por_termo"].items() if n))
    print(f"\n--- amostra (aleatória, semente '{a.semente}') ---")
    for i, c in enumerate(r["amostra"], 1):
        print(f"\n{i:2d}. {c['poeta']} · {c['era'] or 'era não dada'} · metro {c['metro']} ({c['metro_rom']})")
        print(f"    {c['sadr']}")
        if c["ajuz"]:
            print(f"    {c['ajuz']}")
        print(f"    casou em: {c['termo_que_casou']}   ·   {c['url']}")
    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
