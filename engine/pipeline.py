#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# Divã do Vão — ferramenta de co-produção musical a partir do aruz persa.
# Copyright (C) 2026  Divã do Vão
#
# Este programa é software livre: você pode redistribuí-lo e/ou modificá-lo
# sob os termos da GNU General Public License, versão 3, publicada pela Free
# Software Foundation. Ele é distribuído na esperança de ser útil, mas SEM
# NENHUMA GARANTIA. Veja o arquivo LICENSE, e LICENSE.historico para a nota
# sobre o licenciamento MIT anterior.
#
"""
O pipeline: do verso de Rumi à partitura, em dez estágios.

    0  FONTE        data/aruz_corpus.json        verso persa + escansão
    1  CONFERIR     conferir_metro()             a escansão casa com o metro?
    2  DURAR        durar_por_aruz()             escansão -> durações
    3  OPERAR       engine/ritmo.py              inversão, aumentação, síncope
    4  GERAR        gerar_melodia()              N candidatas
   ─────────────────────────────────────────────────────────  barato, automático
    5  PENEIRAR     engine/filtros.py            só o degenerado (~0,07%)
    6  MEDIR        engine/complexidade.py       decomposição, MIR, encaixe
    7  LOTE/ORDENAR engine/selecao.py, gosto.py  medoides, ou o gosto aprendido
   ─────────────────────────────────────────────────────────  caro: o tempo do autor
    8  JULGAR       comparação A/B               treina o gosto
    9  LETRAR       ajuste_prosodico()           letra PT contra o aruz
   10  EXPORTAR     engine/export.py             MusicXML + MIDI + auditoria

A linha divisória é o ponto do desenho: tudo à esquerda é barato e automático,
e o pipeline existe para empurrar o máximo de trabalho para lá, porque o que
custa é a escuta humana.

O QUE CADA ESTÁGIO PODE AFIRMAR
-------------------------------
0-4 derivam da fonte e são auditáveis nota a nota. 5 rejeita só o que não é
melodia. 6 descreve. 7 **ordena por cobertura enquanto não houver julgamento, e
por gosto aprendido depois** — e nunca apresenta hipótese como qualidade. 8 é a
única verdade de referência do projeto. Ver o registro dos quatro erros de
heurística em engine/filtros.py.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
if __name__ == "__main__" and str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from engine import filtros, gosto, selecao
from engine.complexidade import compasso_natural, relatorio as relatorio_complexidade
from engine.generative import (Frase, carregar_corpus, conferir_metro,
                               gerar_melodia, relatorio_auditoria, MODOS)
from engine.ritmo import OPERACOES


@dataclass
class Candidata:
    """Uma melodia atravessando o pipeline, com o rastro de cada estágio.

    Carregar o rastro junto é o que permite ao autor perguntar, na saída, por
    que esta candidata e não outra — do verso persa até o escore.
    """
    frase: Frase
    verso: dict
    semente: str
    veredito: filtros.Veredito | None = None
    atributos: list[float] = field(default_factory=list)
    medidas: dict = field(default_factory=dict)
    escore: float | None = None
    motivo_da_ordem: str = ""

    @property
    def passou(self) -> bool:
        return self.veredito is None or self.veredito.passou


# ---------------------------------------------------------------------------
# Estágios — cada um é função pura sobre a lista de candidatas
# ---------------------------------------------------------------------------

def gerar(verso: dict, modo: str, n: int, metros: dict, *,
          entropia: float = 0.4, ambito: int = 9, tonica: int = 62,
          operacao: str = "", motivico: bool = False,
          prefixo: str = "c") -> list[Candidata]:
    """Estágios 2-4: durações do aruz, operação rítmica, N melodias."""
    saida = []
    for i in range(n):
        semente = f"{prefixo}{i}"
        frase = gerar_melodia(verso, modo=modo, tonica_midi=tonica,
                              entropia=entropia, ambito=ambito, semente=semente,
                              motivico=motivico, metros=metros)
        if operacao:
            frase = OPERACOES[operacao](frase)
        saida.append(Candidata(frase=frase, verso=verso, semente=semente))
    return saida


def peneirar(candidatas: list[Candidata]) -> list[Candidata]:
    """Estágio 5. Marca todas e devolve só as aprovadas — a reprovação fica
    registrada em quem foi descartado, para o relatório poder contá-la."""
    for c in candidatas:
        c.veredito = filtros.peneirar(c.frase)
    return [c for c in candidatas if c.passou]


def medir(candidatas: list[Candidata], metros: dict, *,
          compasso: float | None = None, ambito: int = 9,
          letra: str | None = None) -> list[Candidata]:
    """Estágio 6: complexidade, métricas e atributos para a ordenação."""
    for c in candidatas:
        natural = compasso_natural(c.verso, metros)
        comp = compasso or natural.get("compasso_sugerido") or 4.0
        c.medidas = relatorio_complexidade(c.frase, c.verso, metros,
                                           ambito=ambito, letra=letra,
                                           compasso=comp)
        c.medidas["hipoteses"] = selecao.rotular_hipoteses(c.frase)
        c.atributos = selecao.atributos(c.frase, c.verso, metros, comp)
    return candidatas


def ordenar(candidatas: list[Candidata], k: int,
            julgamentos: list[dict] | None = None) -> list[Candidata]:
    """Estágio 7.

    Sem julgamentos, devolve o LOTE por medoides — afirmação sobre cobertura,
    não sobre qualidade. Com julgamentos, ordena pelo gosto aprendido. O campo
    `motivo_da_ordem` diz qual dos dois foi, para que a saída nunca deixe
    dúvida sobre o que está sendo afirmado.
    """
    if not candidatas:
        return []
    vetores = [c.atributos for c in candidatas]
    if julgamentos:
        pesos = gosto.treinar(julgamentos, len(vetores[0]))
        for c, v in zip(candidatas, vetores):
            c.escore = round(gosto.escore(pesos, v), 4)
            c.motivo_da_ordem = f"gosto aprendido em {len(julgamentos)} julgamentos"
        return sorted(candidatas, key=lambda c: -(c.escore or 0.0))[:k]
    indices = selecao.lote_inicial(vetores, k)
    for i in indices:
        candidatas[i].motivo_da_ordem = (
            "lote por medoides: cobre o espaço, não afirma qualidade "
            "(ainda não há julgamento)")
    return [candidatas[i] for i in indices]


def executar(verso: dict, metros: dict, *, modo: str = "dorico", n: int = 300,
             k: int = 8, julgamentos: list[dict] | None = None,
             **kwargs) -> dict:
    """O pipeline inteiro, 0 a 7. Devolve as escolhidas e o relatório."""
    conferencia = conferir_metro(verso, metros)
    letra = kwargs.pop("letra", None)
    compasso = kwargs.pop("compasso", None)
    ambito = kwargs.get("ambito", 9)
    todas = gerar(verso, modo, n, metros, **kwargs)
    aprovadas = peneirar(todas)
    medir(aprovadas, metros, compasso=compasso, ambito=ambito, letra=letra)
    escolhidas = ordenar(aprovadas, k, julgamentos)
    return {
        "verso": verso["id"],
        "modo": modo,
        "conferencia_metro": conferencia,
        "peneira": filtros.relatorio([c.frase for c in todas]),
        "geradas": len(todas),
        "aprovadas": len(aprovadas),
        "escolhidas": escolhidas,
        "ordenacao": escolhidas[0].motivo_da_ordem if escolhidas else "",
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _imprimir(res: dict) -> None:
    cm = res["conferencia_metro"]
    print(f"verso {res['verso']} · modo {res['modo']} · metro {cm['metro']} "
          f"confere: {cm['conforme']}")
    p = res["peneira"]
    print(f"geradas {res['geradas']} · peneira cortou {p['reprovadas']} "
          f"({p['taxa_de_corte']*100:.2f}%) · aprovadas {res['aprovadas']}")
    print(f"ordenação: {res['ordenacao']}\n")
    for i, c in enumerate(res["escolhidas"], 1):
        m = c.medidas["metricas_mir"]
        hip = c.medidas["hipoteses"]
        escore = f" escore={c.escore}" if c.escore is not None else ""
        print(f"  {i:2d}. semente={c.semente:8s}{escore} "
              f"alturas={[n.midi for n in c.frase.notas]}")
        print(f"      entropia={m['entropia_de_altura']} "
              f"extensão={m['extensao_semitons']} groove={m['consistencia_de_groove']}")
        print("      HIPÓTESES (não testadas, não são nota de qualidade): "
              + ", ".join(f"{k}={v['valor']}" for k, v in hip.items()))


def _julgar(corpus: dict, verso: dict, args) -> None:
    """Estágio 8 no terminal: compara pares e grava os julgamentos."""
    todas = gerar(verso, args.modo, args.n, corpus["metros"],
                  motivico=args.motivico, ambito=args.ambito)
    aprovadas = peneirar(todas)
    medir(aprovadas, corpus["metros"], ambito=args.ambito)
    vetores = [c.atributos for c in aprovadas]
    js = gosto.carregar()
    vistos: set[tuple[int, int]] = set()
    print(f"{len(aprovadas)} candidatas. {args.julgar} comparações — "
          f"'a', 'b' ou 'pular'. Ctrl-C grava e sai.\n")
    try:
        for t in range(args.julgar):
            pesos = gosto.treinar(js, len(vetores[0])) if len(js) >= 6 else [0.0]*len(vetores[0])
            if len(js) < 6:
                i, j = selecao.lote_inicial(vetores, 2, semente=t)
            else:
                i, j = gosto.proximo_par(vetores, pesos, vistos, semente=t)
            vistos.add((min(i, j), max(i, j)))
            a, b = aprovadas[i], aprovadas[j]
            print(f"[{t+1}/{args.julgar}] "
                  f"A={[n.midi for n in a.frase.notas]}\n"
                  f"          B={[n.midi for n in b.frase.notas]}")
            resposta = input("  preferida (a/b/pular): ").strip().lower()
            if resposta in ("a", "b"):
                js = gosto.registrar(js, a.atributos, b.atributos, resposta,
                                     contexto={"verso": verso["id"],
                                               "modo": args.modo,
                                               "a": a.semente, "b": b.semente})
    except (KeyboardInterrupt, EOFError):
        print("\ninterrompido")
    caminho = gosto.gravar(js)
    print(f"\n{len(js)} julgamentos em {caminho}")
    c = gosto.confianca(js)
    print("confiança:", c.get("aviso") or f"acurácia {c.get('acuracia')}")


def main(argv=None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--corpus", default=str(RAIZ / "data/aruz_corpus.json"))
    ap.add_argument("--verso", default="masnavi_1")
    ap.add_argument("--modo", default="dorico", choices=list(MODOS))
    ap.add_argument("--n", type=int, default=300, help="candidatas a gerar")
    ap.add_argument("--lote", type=int, default=8, help="quantas mostrar")
    ap.add_argument("--ambito", type=int, default=9)
    ap.add_argument("--operacao", default="", choices=["", *OPERACOES])
    ap.add_argument("--motivico", action="store_true",
                    help="melodia ciente dos pés do aruz")
    ap.add_argument("--julgar", type=int, default=0,
                    help="entra no laço de comparação A/B")
    ap.add_argument("--explicar-gosto", action="store_true")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--export", default="",
                    help="exporta as escolhidas: musicxml,midi")
    ap.add_argument("--out", default=str(RAIZ / "engine/saida"))
    args = ap.parse_args(argv)

    corpus = carregar_corpus(args.corpus)
    if args.explicar_gosto:
        js = gosto.carregar()
        e = gosto.explicar(gosto.treinar(js))
        print(e["texto"])
        if e["treinado"]:
            for nome, peso in e["ordenados"]:
                print(f"  {peso:+.4f}  {nome}")
        print("confiança:", gosto.confianca(js))
        return 0

    verso = next((v for v in corpus["versos"] if v["id"] == args.verso), None)
    if verso is None:
        print(f"verso inválido: {args.verso!r}; disponíveis: "
              f"{[v['id'] for v in corpus['versos']]}", file=sys.stderr)
        return 2

    if args.julgar:
        _julgar(corpus, verso, args)
        return 0

    res = executar(verso, corpus["metros"], modo=args.modo, n=args.n,
                   k=args.lote, julgamentos=gosto.carregar(),
                   ambito=args.ambito, operacao=args.operacao,
                   motivico=args.motivico)
    if args.json:
        print(json.dumps({
            "verso": res["verso"], "modo": res["modo"],
            "peneira": res["peneira"], "ordenacao": res["ordenacao"],
            "escolhidas": [{
                "semente": c.semente,
                "alturas": [n.midi for n in c.frase.notas],
                "escore": c.escore,
                "hipoteses": c.medidas["hipoteses"],
                "metricas": c.medidas["metricas_mir"],
            } for c in res["escolhidas"]],
        }, ensure_ascii=False, indent=2))
    else:
        _imprimir(res)

    if args.export:                         # estágio 10
        from engine.export import escrever
        formatos = [f.strip() for f in args.export.split(",") if f.strip()]
        natural = compasso_natural(verso, corpus["metros"])
        comp = natural.get("compasso_sugerido") or 4.0
        for posicao, c in enumerate(res["escolhidas"], 1):
            rel = relatorio_auditoria(c.frase, verso, corpus["metros"])
            rel["complexidade"] = c.medidas
            # o rastro da seleção viaja junto: por que esta candidata saiu
            rel["selecao"] = {
                "posicao": posicao, "semente": c.semente,
                "escore": c.escore, "motivo_da_ordem": c.motivo_da_ordem,
                "peneira": {"passou": c.passou, "filtro": c.veredito.filtro},
                "geradas": res["geradas"], "aprovadas": res["aprovadas"],
            }
            for alvo_arq in escrever(c.frase, rel, args.out,
                                     f"{verso['id']}_{posicao:02d}_{c.semente}",
                                     formatos, titulo=verso.get("obra", ""),
                                     compasso=comp):
                print("escrito:", alvo_arq)
    return 0


if __name__ == "__main__":
    sys.exit(main())
