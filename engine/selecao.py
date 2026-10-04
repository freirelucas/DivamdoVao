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
Partida a frio: escolher o primeiro lote sem afirmar nada sobre o gosto.

O QUE ESTE MÓDULO PODE E NÃO PODE DIZER
---------------------------------------
Antes do primeiro julgamento do autor não existe verdade de referência neste
projeto (ver o registro dos quatro erros em engine/filtros.py). Então aqui não
há distribuição-alvo, nem limiar, nem norma importada. Só duas coisas:

1. **Cobertura** — `lote_inicial` escolhe candidatas que representam regiões
   densas do espaço de atributos, para que os primeiros julgamentos sejam o
   mais informativos possível. É afirmação sobre cobertura, não sobre
   qualidade, e foi medida (cobertura média ao vizinho mais próximo, menor é
   melhor, 1200 candidatas):

       lote   aleatório   k-center   medoides
          4      0,3171     0,4075     0,2581
          8      0,2727     0,3425     0,2242
         12      0,2445     0,3004     0,2050
         20      0,2186     0,2586     0,1830

   Medoides ganha em todos os tamanhos; k-center, que era a escolha "óbvia"
   para diversidade, perde feio porque prefere extremos e extremos cobrem mal
   o miolo da distribuição.

2. **Hipóteses rotuladas** — `HIPOTESES` são duas medidas derivadas do
   material que o projeto já declara (os pés de Rumi, os graus do modo, as
   sílabas longas). Elas VARIAM, logo dá para ordenar por elas. Mas que ordenar
   por elas produza música melhor é **hipótese, não fato**, e toda saída deste
   módulo as marca como tal. Os primeiros julgamentos do autor confirmam ou
   matam cada uma; se matarem, viram o quinto item do registro de erros.
"""
from __future__ import annotations

import math
import random

from engine.complexidade import (cantabilidade, aderencia_ao_metro, metricas_mir)
from engine.generative import Frase, LONGAS

# Faixas do perfil de saltos. Medir a PROPORÇÃO por faixa, e não o salto
# máximo, é a correção que o autor apontou: salto grande não é defeito, é raro
# — a forma da distribuição é que descreve a melodia, não o seu extremo.
FAIXAS_DE_SALTO = ((0, 0), (1, 2), (3, 4), (5, 7), (8, 99))

HIPOTESES = {
    "eco_entre_pes": {
        "hipotese": "uma melodia cujo pé 2 ecoa o contorno do pé 1 soa mais "
                    "coerente, porque trata o pé do aruz como unidade musical "
                    "— do mesmo modo que o ritmo já faz",
        "derivada_de": "os pés do metro, declarados em data/aruz_corpus.json",
        "medido": "o gerador atual produz eco em 5,81% dos casos contra 3,70% "
                  "por acaso: a melodia é praticamente cega aos pés que o "
                  "ritmo herda de Rumi",
        "confirmaria": "o autor preferir, em pares A/B, a candidata de eco alto",
        "estado": "não testada",
    },
    "estavel_em_longa": {
        "hipotese": "grau estável (tônica, terça ou quinta) caindo em sílaba "
                    "longa do aruz soa mais assentado",
        "derivada_de": "os modos e as sílabas longas, ambos declarados no corpus",
        "medido": "média 0,568 com desvio 0,170 no espaço atual — varia o "
                  "bastante para ordenar",
        "confirmaria": "o autor preferir a candidata de valor alto",
        "estado": "não testada",
    },
}


# ---------------------------------------------------------------------------
# Atributos
# ---------------------------------------------------------------------------

def perfil_de_saltos(frase: Frase) -> list[float]:
    """Proporção de intervalos em cada faixa de tamanho.

    A forma da distribuição, não o máximo. Um salto de nove semitons numa
    frase é material; nove saltos de nove semitons é outra coisa — e só o
    perfil distingue os dois casos.
    """
    alturas = [n.midi for n in frase.notas]
    saltos = [abs(b - a) for a, b in zip(alturas, alturas[1:])]
    if not saltos:
        return [0.0] * len(FAIXAS_DE_SALTO)
    return [sum(1 for s in saltos if lo <= s <= hi) / len(saltos)
            for lo, hi in FAIXAS_DE_SALTO]


def eco_entre_pes(frase: Frase, tamanho_do_pe: int = 4) -> float:
    """Quanto o contorno do pé seguinte repete o do primeiro. HIPÓTESE."""
    alturas = [n.midi for n in frase.notas]
    if len(alturas) < 2 * tamanho_do_pe:
        return 0.0
    def contorno(seq):
        return [(b > a) - (b < a) for a, b in zip(seq, seq[1:])]
    c1 = contorno(alturas[:tamanho_do_pe])
    c2 = contorno(alturas[tamanho_do_pe:2 * tamanho_do_pe])
    return sum(a == b for a, b in zip(c1, c2)) / len(c1) if c1 else 0.0


def estavel_em_longa(frase: Frase) -> float:
    """Fração das sílabas longas que recebem grau estável. HIPÓTESE."""
    longas = [n for n in frase.notas if n.aruz in LONGAS]
    if not longas:
        return 0.0
    return sum(1 for n in longas if n.grau_modal in (0, 2, 4)) / len(longas)


NOMES_DOS_ATRIBUTOS = (
    "entropia de altura", "extensão", "alturas usadas", "groove",
    "cantabilidade", "aderência ao metro",
    "notas repetidas", "passos de 1-2", "saltos de 3-4", "saltos de 5-7",
    "saltos de 8+",
    "eco entre pés (hipótese)", "estável em longa (hipótese)",
)


def atributos(frase: Frase, verso: dict, metros: dict,
              compasso: float = 4.0) -> list[float]:
    """Vetor de atributos, todos normalizados para [0, 1] aproximadamente.

    A ordem segue NOMES_DOS_ATRIBUTOS, e é ela que torna os pesos do
    ranqueador legíveis — ver engine/gosto.py.
    """
    m = metricas_mir(frase, compasso)
    ct = cantabilidade(frase)
    ad = aderencia_ao_metro(frase, verso, metros)
    return [
        m["entropia_de_altura"] / 3.0,
        m["extensao_semitons"] / 12.0,
        m["alturas_usadas"] / 7.0,
        m["consistencia_de_groove"],
        ct["cantabilidade"],
        ad["aderencia"] if ad.get("aderencia") is not None else 0.0,
        *perfil_de_saltos(frase),
        eco_entre_pes(frase),
        estavel_em_longa(frase),
    ]


# ---------------------------------------------------------------------------
# Lote inicial por medoides
# ---------------------------------------------------------------------------

def _distancia(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def lote_inicial(vetores: list[list[float]], k: int,
                 semente: int = 0, iteracoes: int = 12) -> list[int]:
    """Índices das k candidatas que melhor representam o espaço.

    k-means++ nos atributos e, para cada centro, a candidata REAL mais
    próxima — o autor tem de poder ouvir o que julga, e um centroide médio não
    é uma melodia.
    """
    if k <= 0 or not vetores:
        return []
    if k >= len(vetores):
        return list(range(len(vetores)))
    rng = random.Random(semente)

    centros = [vetores[rng.randrange(len(vetores))]]
    while len(centros) < k:                       # k-means++
        d2 = [min(_distancia(v, c) ** 2 for c in centros) for v in vetores]
        total = sum(d2)
        if total <= 0:
            centros.append(vetores[rng.randrange(len(vetores))])
            continue
        alvo, acumulado = rng.random() * total, 0.0
        for i, valor in enumerate(d2):
            acumulado += valor
            if acumulado >= alvo:
                centros.append(vetores[i])
                break

    for _ in range(iteracoes):                    # Lloyd
        grupos: list[list[list[float]]] = [[] for _ in centros]
        for v in vetores:
            j = min(range(len(centros)), key=lambda c: _distancia(v, centros[c]))
            grupos[j].append(v)
        centros = [[sum(col) / len(col) for col in zip(*g)] if g else c
                   for g, c in zip(grupos, centros)]

    escolhidos: list[int] = []
    for c in centros:                             # o ponto real mais próximo
        ordem = sorted(range(len(vetores)), key=lambda i: _distancia(vetores[i], c))
        for i in ordem:
            if i not in escolhidos:
                escolhidos.append(i)
                break
    return escolhidos


def cobertura(vetores: list[list[float]], escolhidos: list[int]) -> float:
    """Distância média de cada candidata à mais próxima do lote. Menor é
    melhor. É a métrica com que medoides foi comparado a aleatório e k-center."""
    if not escolhidos or not vetores:
        return float("inf")
    return sum(min(_distancia(v, vetores[i]) for i in escolhidos)
               for v in vetores) / len(vetores)


def rotular_hipoteses(frase: Frase) -> dict:
    """Os valores das medidas-hipótese, sempre acompanhados do rótulo.

    Devolver o número sozinho seria apresentá-lo como qualidade, que é
    exatamente o erro que este módulo existe para não repetir.
    """
    valores = {"eco_entre_pes": round(eco_entre_pes(frase), 4),
               "estavel_em_longa": round(estavel_em_longa(frase), 4)}
    return {nome: {"valor": valores[nome], **HIPOTESES[nome]}
            for nome in valores}
