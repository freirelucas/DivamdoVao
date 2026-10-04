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
Índice do corpus árabe — para EXPLORAR por tema e conceito, não só para colher.

POR QUE UM ÍNDICE, E NÃO MAIS UM COLHEDOR
-----------------------------------------
O colhedor persa (ferramentas/colher.py) responde "me dê versos deste metro".
Boa pergunta para quem precisa de ritmo. Pergunta errada para quem está
procurando CANÇÃO. A pergunta da canção é temática: onde está o verso que fala
do acampamento abandonado, da travessia, da separação, do vinho da madrugada.

E aqui está o limite que a medição mostrou: o corpus traz rótulo de tema, mas
ele é fino e em parte administrativo. Em 212.499 poemas do Ashaar, 71% não têm
tema, e os dois maiores rótulos são "poema curto" (40%) e "poema geral" (28%),
que não são temas. Os temas de verdade cobrem ~19 mil poemas.

Logo: o acesso temático não pode confiar no rótulo. Tem de vir do TEXTO. Por
isso este módulo constrói um índice de busca textual (FTS5, que vem na stdlib
via sqlite3) sobre os hemistíquios, e é por palavra-motivo que se garimpa.
Cada achado cita a palavra que casou — busca auditável, não recomendação opaca.

O QUE NÃO ENTRA
---------------
O corpus vai do período pré-islâmico ao moderno. Poeta moderno tem direitos
vivos. O campo poet_era é um proxy grosseiro de data de morte, e é o que a
fonte dá: por padrão o índice marca cada verso com `dominio_publico_provavel`
e exclui as eras modernas da busca, mas guarda a linha para que a decisão seja
revisável em vez de invisível. Nada aqui substitui conferir o poeta.

Também não entram as colunas poem_description (HTML da página, aninhado em
dezenas de níveis) nem text (serialização para treino de modelo): não são
fonte, são embalagem.

Requer pyarrow para ler o parquet. É ferramenta de ingestão, não o motor:
engine/ continua só com a stdlib.
"""
from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

FONTE = {
    "dataset": "arbml/Ashaar_dataset",
    "url": "https://huggingface.co/datasets/arbml/Ashaar_dataset",
    "artigo": ("Alyafeai et al., Ashaar: Automatic Analysis and Generation of "
               "Arabic Poetry Using Deep Learning Approaches, arXiv:2307.06218"),
    "licenca_declarada_no_artigo": "CC BY 4.0",
    "licenca_no_cartao_do_dataset": None,
    "ressalva_de_licenca": (
        "O artigo declara CC BY 4.0; o cartão do dataset no Hugging Face não traz "
        "campo de licença. A discrepância fica registrada em vez de assumida. Os "
        "POEMAS em si são, na maioria esmagadora, de domínio público (pré-islâmico "
        "ao otomano); a compilação é que tem estatuto incerto. Atribuição ao Ashaar "
        "e a aldiwan.net é devida de todo modo."),
    "origem_dos_poemas": "aldiwan.net (e, para poesia moderna, adab e a enciclopédia de Abu Dhabi)",
}

# os 17 rótulos de metro do Ashaar, na ordem do ClassLabel
METROS = ["البسيط", "الخفيف", "الرجز", "الرمل", "السريع", "الطويل", "الكامل",
          "المتدارك", "المتقارب", "المجتث", "المديد", "المضارع", "المقتضب",
          "المنسرح", "النثر", "الهزج", "الوافر"]
ROMANIZA = {"البسيط": "basit", "الخفيف": "khafif", "الرجز": "rajaz", "الرمل": "ramal",
            "السريع": "sari", "الطويل": "tawil", "الكامل": "kamil",
            "المتدارك": "mutadarik", "المتقارب": "mutaqarib", "المجتث": "mujtath",
            "المديد": "madid", "المضارع": "mudari", "المقتضب": "muqtadab",
            "المنسرح": "munsarih", "النثر": "nathr", "الهزج": "hazaj", "الوافر": "wafir"}

# eras que o corpus nomeia e que NÃO são domínio público seguro
ERAS_MODERNAS = {"العصر الحديث", "المعاصر", "العصر المعاصر"}

# diacríticos árabes (harakat). Guardamos o verso COM eles — é o que torna a
# escansão árabe derivável por regra, ao contrário do persa — e indexamos a
# forma SEM eles, para que a busca por motivo não dependa de vocalização.
HARAKAT = "".join(chr(c) for c in range(0x064B, 0x0653)) + "ٰـ"


def sem_harakat(s: str) -> str:
    """Forma de busca: sem vogais curtas, sem tatweel, alif normalizado."""
    s = unicodedata.normalize("NFC", s)
    s = "".join(c for c in s if c not in HARAKAT)
    s = re.sub("[آأإٱ]", "ا", s)   # آ أ إ ٱ -> ا
    s = s.replace("ى", "ي").replace("ة", "ه")  # ى->ي  ة->ه
    return re.sub(r"\s+", " ", s).strip()


ESQUEMA = """
CREATE TABLE IF NOT EXISTS poemas (
  id INTEGER PRIMARY KEY,
  titulo TEXT, metro TEXT, metro_rom TEXT, tema TEXT, url TEXT,
  poeta TEXT, era TEXT, local TEXT, n_hemistiquios INTEGER,
  dominio_publico_provavel INTEGER
);
CREATE TABLE IF NOT EXISTS hemistiquios (
  id INTEGER PRIMARY KEY,
  poema_id INTEGER NOT NULL REFERENCES poemas(id),
  bayt INTEGER NOT NULL,       -- nº da copla (1-based)
  metade INTEGER NOT NULL,     -- 1 = sadr, 2 = ʿajuz
  texto TEXT NOT NULL,         -- COM harakat: é daqui que a escansão sai
  busca TEXT NOT NULL          -- sem harakat: é por aqui que se garimpa
);
CREATE INDEX IF NOT EXISTS ix_hemi_poema ON hemistiquios(poema_id);
CREATE VIRTUAL TABLE IF NOT EXISTS fts USING fts5(
  busca, content='hemistiquios', content_rowid='id', tokenize='unicode61'
);
CREATE TABLE IF NOT EXISTS fonte (chave TEXT PRIMARY KEY, valor TEXT);
"""


def indexar(parquets: list[Path], destino: Path, incluir_modernos: bool = False,
            limite: int = 0) -> dict:
    import pyarrow.parquet as pq

    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists():
        destino.unlink()
    con = sqlite3.connect(destino)
    con.executescript(ESQUEMA)
    for k, v in FONTE.items():
        con.execute("INSERT OR REPLACE INTO fonte VALUES (?,?)",
                    (k, json.dumps(v, ensure_ascii=False)))

    colunas = ["poem_title", "poem_meter", "poem_verses", "poem_theme", "poem_url",
               "poet_name", "poet_era", "poet_location"]
    pid = hid = 0
    pulados_modernos = pulados_vazios = 0
    por_metro: dict[str, int] = {}
    por_era: dict[str, int] = {}
    por_tema: dict[str, int] = {}

    for arq in parquets:
        tabela = pq.read_table(arq, columns=colunas)
        for lote in tabela.to_batches(max_chunksize=5000):
            poemas, hemis = [], []
            for linha in lote.to_pylist():
                versos = [v for v in (linha.get("poem_verses") or []) if v and v.strip()]
                if not versos:
                    pulados_vazios += 1
                    continue
                era = (linha.get("poet_era") or "").strip()
                publico = era not in ERAS_MODERNAS
                if not publico and not incluir_modernos:
                    pulados_modernos += 1
                    continue
                pid += 1
                im = linha.get("poem_meter")
                metro = METROS[im] if isinstance(im, int) and 0 <= im < len(METROS) else ""
                tema = (linha.get("poem_theme") or "").strip()
                poemas.append((pid, (linha.get("poem_title") or "").strip(), metro,
                               ROMANIZA.get(metro, ""), tema,
                               (linha.get("poem_url") or "").strip(),
                               (linha.get("poet_name") or "").strip(), era,
                               (linha.get("poet_location") or "").strip() or None,
                               len(versos), int(publico)))
                por_metro[metro] = por_metro.get(metro, 0) + 1
                por_era[era] = por_era.get(era, 0) + 1
                if tema:
                    por_tema[tema] = por_tema.get(tema, 0) + 1
                for i, v in enumerate(versos):
                    hid += 1
                    hemis.append((hid, pid, i // 2 + 1, i % 2 + 1, v.strip(),
                                  sem_harakat(v)))
            con.executemany("INSERT INTO poemas VALUES (?,?,?,?,?,?,?,?,?,?,?)", poemas)
            con.executemany("INSERT INTO hemistiquios VALUES (?,?,?,?,?,?)", hemis)
            if limite and pid >= limite:
                break
        con.commit()
        if limite and pid >= limite:
            break

    con.execute("INSERT INTO fts(fts) VALUES('rebuild')")
    con.commit()
    con.execute("ANALYZE")
    con.commit()
    resumo = {
        "poemas": pid, "hemistiquios": hid,
        "pulados_por_era_moderna": pulados_modernos,
        "pulados_sem_verso": pulados_vazios,
        "metros": dict(sorted(por_metro.items(), key=lambda kv: -kv[1])),
        "eras": dict(sorted(por_era.items(), key=lambda kv: -kv[1])),
        "temas": dict(sorted(por_tema.items(), key=lambda kv: -kv[1])),
        "arquivo": str(destino), "tamanho_mb": round(destino.stat().st_size / 1e6, 1),
    }
    con.execute("INSERT OR REPLACE INTO fonte VALUES (?,?)",
                ("resumo_da_indexacao", json.dumps(resumo, ensure_ascii=False)))
    con.commit()
    con.close()
    return resumo


def _cli(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("parquet", nargs="+", help="arquivos parquet do Ashaar")
    ap.add_argument("--destino", default=str(RAIZ / ".cache_arabe/arabe.sqlite"))
    ap.add_argument("--incluir-modernos", action="store_true",
                    help="inclui eras com direitos possivelmente vivos (não recomendado)")
    ap.add_argument("--limite", type=int, default=0, help="teto de poemas, para testar")
    ap.add_argument("--mapa", default="", help="grava o mapa temático medido neste JSON")
    a = ap.parse_args(argv)

    r = indexar([Path(p) for p in a.parquet], Path(a.destino),
                a.incluir_modernos, a.limite)
    print(f"poemas indexados     : {r['poemas']:,}")
    print(f"hemistíquios         : {r['hemistiquios']:,}")
    print(f"pulados (era moderna): {r['pulados_por_era_moderna']:,}")
    print(f"pulados (sem verso)  : {r['pulados_sem_verso']:,}")
    print(f"índice               : {r['arquivo']}  ({r['tamanho_mb']} MB)")
    print("\nmetros (top 8):")
    for m, n in list(r["metros"].items())[:8]:
        print(f"  {n:7,d}  {m}  {ROMANIZA.get(m,'')}")
    print("\neras:")
    for e, n in list(r["eras"].items())[:12]:
        print(f"  {n:7,d}  {e or '(sem era)'}")
    if a.mapa:
        Path(a.mapa).write_text(
            json.dumps({"_fonte": FONTE, "_sobre": (
                "Mapa temático MEDIDO do corpus. Serve para saber onde há material "
                "antes de garimpar, e para registrar que o rótulo de tema do corpus "
                "é fino: a maioria dos poemas não tem tema, e os maiores rótulos são "
                "administrativos ('poema curto', 'poema geral'), não temáticos."),
                **r}, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"\nmapa gravado: {a.mapa}")
    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
