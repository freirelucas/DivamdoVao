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
Forma — a periodicidade que está no texto, e a única coisa que autoriza
mexer em harmonia.

O PROBLEMA QUE ESTE MÓDULO EXISTE PARA RESOLVER
-----------------------------------------------
O aruz dá ritmo, e isso o projeto provou. Mas o aruz não diz NADA sobre
harmonia. A música clássica árabe e persa é modal; harmonia funcional é
importação europeia, e a cor Clube da Esquina é escolha do autor, não
propriedade da fonte. Um módulo chamado "harmonia derivada do poema" seria
fabricação — o mesmo erro que engine/filtros.py registra quatro vezes.

Então o que, na fonte, pode legitimamente governar harmonia? Uma coisa só:
PERIODICIDADE. A qasida e o gazal rimam na mesma sílaba do primeiro ao último
dístico. Isso não é interpretação, é contável no texto. E uma cadência é
exatamente isso — um ponto de retorno que volta sempre no mesmo lugar. Rima no
texto licencia rima na harmonia, e o lugar da cadência fica determinado pelo
lugar da rima.

É pouco, e é honesto. Tudo o mais na harmonia — quais acordes, qual cor, qual
tensão — continua autoral, e o projeto diz isso.

O QUE ESTE MÓDULO MEDE
----------------------
  qāfiya   a rima: o fim comum aos hemistíquios de fecho, com a cobertura
           medida (que fração dos dísticos de fato a compartilha)
  radīf    a palavra que se repete DEPOIS da rima. Recurso do gazal persa,
           turco e urdu — NÃO do árabe clássico. Onde existe, é refrão de uma
           palavra já dado pela fonte.
  taṣrīʿ   o dístico de abertura em que os DOIS hemistíquios rimam, o que
           marca a abertura formalmente.

Função pura, só stdlib, nenhuma rede. Serve ao corpus persa já colhido e ao
árabe indexado, porque mede o texto e não o metadado.
"""
from __future__ import annotations

import re
import unicodedata

# harakat árabes/persas, tatweel, e o que não conta para a rima
_MARCAS = "".join(chr(c) for c in range(0x064B, 0x0653)) + "ٰـْ"
_PONTUACAO = "،؛؟.,;:!?—–-–—«»\"'()[]{}*"

LIMIAR_COBERTURA = 0.70   # fração dos fechos que precisa compartilhar o fim
MAX_RIMA = 6              # maior rima considerada, em caracteres


def normalizar_fim(s: str) -> str:
    """Forma comparável de um fim de verso: sem vogais curtas nem pontuação.

    A rima árabe e persa se define por consoantes e vogais longas; as harakat
    são justamente o que a grafia costuma omitir. Comparar com elas faria a
    mesma rima parecer rimas diferentes.
    """
    s = unicodedata.normalize("NFC", s)
    s = "".join(c for c in s if c not in _MARCAS)
    s = "".join(c for c in s if c not in _PONTUACAO)
    s = re.sub("[آأإٱ]", "ا", s)
    s = s.replace("ى", "ي").replace("ك", "ک")
    return re.sub(r"\s+", " ", s).strip()


def _fechos(coplas: list[tuple[str, ...]]) -> list[str]:
    """Os hemistíquios que carregam a rima: o ʿajuz de cada dístico.

    No primeiro dístico com taṣrīʿ os dois rimam, mas o ʿajuz rima em todos —
    então é dele que se mede.
    """
    return [normalizar_fim(c[-1]) for c in coplas if c and c[-1].strip()]


def rima_do_poema(coplas: list[tuple[str, ...]],
                  limiar: float = LIMIAR_COBERTURA,
                  descontar_radif: bool = True) -> dict:
    """A qāfiya medida: o fim mais longo compartilhado por ao menos `limiar`
    dos dísticos.

    Devolve também a COBERTURA, porque monorrima é afirmação sobre o poema
    inteiro e um poema real pode ter um dístico fora (erro de digitação na
    fonte, verso interpolado). Afirmar monorrima sem dizer a cobertura seria
    esconder o quanto a afirmação vale.
    """
    fechos = _fechos(coplas)
    n = len(fechos)
    if n < 2:
        return {"rima": "", "n_caracteres": 0, "cobertura": 0.0,
                "n_dísticos": n, "monorrima": False, "radif_descontado": "",
                "por_que": "menos de dois dísticos: não há periodicidade a medir"}

    # A qāfiya é o que vem ANTES do radīf, não o fim cru do verso. Medir o fim
    # cru faz a rima englobar o radīf: num gazal que termina sempre em 'āyadat',
    # o fim comum sai 'ār āyadat' quando a rima é só 'ār'. Isso importa porque
    # as duas coisas licenciam coisas diferentes na música — a rima licencia
    # cadência, o radīf licencia refrão — e confundi-las apagaria a distinção.
    radif_fora = ""
    if descontar_radif:
        rd = radif_do_poema(coplas, limiar)
        if rd["tem_radif"]:
            radif_fora = rd["radif"]
            cortados = []
            for f in fechos:
                cortados.append(f[: -len(radif_fora)].strip()
                                if f.endswith(radif_fora) else f)
            fechos = [c for c in cortados if c]
            n = len(fechos) or n
    melhor = {"rima": "", "n_caracteres": 0, "cobertura": 0.0}
    for k in range(MAX_RIMA, 0, -1):
        contagem: dict[str, int] = {}
        for f in fechos:
            if len(f) >= k:
                contagem[f[-k:]] = contagem.get(f[-k:], 0) + 1
        if not contagem:
            continue
        fim, c = max(contagem.items(), key=lambda kv: kv[1])
        cob = c / n
        if cob >= limiar:
            melhor = {"rima": fim, "n_caracteres": k, "cobertura": round(cob, 3)}
            break
    return melhor | {
        "n_dísticos": n,
        "radif_descontado": radif_fora,
        "monorrima": melhor["n_caracteres"] > 0,
        "por_que": ("a rima é o fim mais longo que ao menos "
                    f"{int(limiar*100)}% dos dísticos compartilham"),
    }


def radif_do_poema(coplas: list[tuple[str, ...]],
                   limiar: float = LIMIAR_COBERTURA, max_palavras: int = 3) -> dict:
    """O radīf: a palavra (ou poucas) que se repete depois da rima.

    ATENÇÃO, e é correção de um erro meu: radīf-como-palavra-que-volta é
    recurso do gazal PERSA, turco e urdu, não do árabe clássico. Rodar isto
    sobre corpus árabe e achar pouco não é falha da medida — é a diferença
    entre as duas tradições. E a diferença importa para quem monta canção: o
    gazal persa entrega um refrão de uma palavra já pronto; a qasida árabe
    entrega só a rima, e o estribilho fica por conta do autor.
    """
    fechos = [f for f in _fechos(coplas) if f]
    n = len(fechos)
    if n < 2:
        return {"radif": "", "n_palavras": 0, "cobertura": 0.0, "tem_radif": False}
    melhor = {"radif": "", "n_palavras": 0, "cobertura": 0.0}
    for k in range(max_palavras, 0, -1):
        contagem: dict[str, int] = {}
        for f in fechos:
            ps = f.split()
            if len(ps) > k:                       # exige algo antes do radīf
                contagem[" ".join(ps[-k:])] = contagem.get(" ".join(ps[-k:]), 0) + 1
        if not contagem:
            continue
        exp, c = max(contagem.items(), key=lambda kv: kv[1])
        if c / n >= limiar:
            melhor = {"radif": exp, "n_palavras": k, "cobertura": round(c / n, 3)}
            break
    return melhor | {
        "tem_radif": melhor["n_palavras"] > 0,
        "nota": ("recurso do gazal persa/turco/urdu; o árabe clássico não o usa "
                 "como regra — ver data/pontes.json, ERRO_CORRIGIDO"),
    }


def tem_tasri(primeiro: tuple[str, ...], rima: str, radif: str = "") -> bool:
    """taṣrīʿ: no dístico de abertura, os DOIS hemistíquios rimam.

    Quando existe, a fonte está marcando a abertura como formalmente distinta
    — e é isso que licencia tratá-la como cabeça da canção, com cadência
    própria, em vez de como só o primeiro verso.
    """
    if not rima or len(primeiro) < 2:
        return False
    sadr, ajuz = normalizar_fim(primeiro[0]), normalizar_fim(primeiro[1])
    if radif:                       # o radīf vem depois da rima, nos dois lados
        sadr = sadr[: -len(radif)].strip() if sadr.endswith(radif) else sadr
        ajuz = ajuz[: -len(radif)].strip() if ajuz.endswith(radif) else ajuz
    return sadr.endswith(rima) and ajuz.endswith(rima)


def cadencias(coplas: list[tuple[str, ...]], rima: dict | None = None,
              radif: dict | None = None) -> dict:
    """Onde a harmonia pode cadenciar, e com que garantia.

    Esta é a única ponte entre texto e harmonia que o projeto pode afirmar. O
    lugar da cadência NÃO é escolha nossa: é o lugar da rima, que está no
    texto. Que acorde cadencia, com que cor, com que tensão — isso continua
    autoral, e a saída daqui diz isso em voz alta.
    """
    rima = rima if rima is not None else rima_do_poema(coplas)
    radif = radif if radif is not None else radif_do_poema(coplas)
    pontos = []
    for i, c in enumerate(coplas):
        if len(c) >= 2 and c[0].strip():
            pontos.append({"bayt": i + 1, "em": "fim do ṣadr",
                           "tipo": "meia cadência",
                           "por_que": "fim do primeiro hemistíquio: a frase abre e não fecha"})
        if c and c[-1].strip():
            pontos.append({"bayt": i + 1, "em": "fim do ʿajuz",
                           "tipo": "cadência",
                           "por_que": f"aqui cai a rima {rima['rima']!r}" if rima["rima"]
                                      else "fim do dístico"})
    abertura = (tem_tasri(coplas[0], rima["rima"], radif.get("radif", ""))
                if coplas else False)
    return {
        "rima": rima, "radif": radif, "tasri_na_abertura": abertura,
        "n_pontos": len(pontos), "pontos": pontos,
        "cabeca_separada": abertura,
        "refrao_dado_pela_fonte": bool(radif.get("tem_radif")),
        "_garantia": {
            "o_lugar_das_cadencias": ("DERIVADO: cai onde cai a rima, que é contável no "
                                      "texto e não depende de teoria harmônica nenhuma."),
            "quais_acordes": ("AUTORAL: o aruz não diz nada sobre harmonia, e a música "
                              "clássica árabe e persa é modal. A cor Clube da Esquina é "
                              "escolha do autor, e o projeto não a apresenta como derivada."),
            "a_cabeca_separada": ("DERIVADO quando há taṣrīʿ: a fonte marca a abertura "
                                  "com rima dupla. Sem taṣrīʿ, tratar a abertura como "
                                  "cabeça é escolha autoral."),
            "o_refrao": ("DERIVADO onde há radīf (gazal persa/urdu): é palavra que a "
                         "fonte repete. No árabe clássico não há radīf, então o "
                         "estribilho é invenção do autor — e isso muda o que se pode "
                         "afirmar sobre a canção."),
        },
    }


def analisar(coplas: list[tuple[str, ...]]) -> dict:
    """Tudo de uma vez, para um poema."""
    r = rima_do_poema(coplas)
    d = radif_do_poema(coplas)
    return {"n_disticos": len(coplas), "rima": r, "radif": d,
            "tasri": (tem_tasri(coplas[0], r["rima"], d.get("radif", ""))
                      if coplas else False),
            "cadencias": cadencias(coplas, r, d)}


if __name__ == "__main__":
    import json as _json
    import sys as _sys
    from pathlib import Path as _P
    _sys.path.insert(0, str(_P(__file__).resolve().parents[1]))
    corpus = _json.loads((_P(__file__).resolve().parents[1] /
                          "data/corpus_colhido.json").read_text(encoding="utf-8"))
    # reagrupa o corpus persa colhido em dísticos, por poema
    poemas: dict[str, dict[int, dict[int, str]]] = {}
    for v in corpus["versos"]:
        o = v["_origem"]
        poemas.setdefault(o["url"], {}).setdefault(o["copla"], {})[o["hemistiquio"]] = v["persa"]
    print(f"poemas persas: {len(poemas)}")
    com_rima = com_radif = com_tasri = 0
    for url, cops in poemas.items():
        coplas = [tuple(cops[k][m] for m in sorted(cops[k])) for k in sorted(cops)]
        a = analisar(coplas)
        com_rima += a["rima"]["monorrima"]
        com_radif += a["radif"]["tem_radif"]
        com_tasri += a["tasri"]
    n = len(poemas)
    print(f"  com monorrima medida : {com_rima:4d}  ({100*com_rima/n:.1f}%)")
    print(f"  com radīf            : {com_radif:4d}  ({100*com_radif/n:.1f}%)")
    print(f"  com taṣrīʿ           : {com_tasri:4d}  ({100*com_tasri/n:.1f}%)")
