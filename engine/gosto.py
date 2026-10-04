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
O gosto do autor, aprendido por comparação — a única verdade de referência
que este projeto pode ter.

POR QUE COMPARAÇÃO E NÃO NOTA
-----------------------------
Gente é ruim em escala absoluta e boa em "esta ou aquela". O modelo é
Bradley-Terry: a probabilidade de A ser preferida a B depende da diferença
entre os escores das duas.

POR QUE LINEAR
--------------
Um ranqueador opaco contradiria a tese do projeto, que é auditabilidade de
ponta a ponta. Linear sobre os atributos de engine/selecao.py, os pesos são
legíveis: `explicar()` devolve "você prefere aderência ao metro e penaliza
saltos seguidos na mesma direção" em vez de um vetor mudo.

O QUE ESPERAR, MEDIDO EM SIMULAÇÃO
----------------------------------
Contra um gosto sintético linear, com ruído de julgamento de ~15%:

    julgamentos   aleatório   ativo
             10       0,521   0,606
             20       0,536   0,638
             40       0,751   0,816
             80       0,743   0,782
            160       0,743   0,788   (tau de Kendall)

Duas leituras importam. A amostragem ativa ganha mais no orçamento baixo, que
é o regime que interessa porque o gargalo é o tempo do autor. E **as duas
curvas estacionam a partir de ~40 julgamentos**: o teto é a inconsistência do
julgamento humano, não a falta de dados. Pedir 160 comparações desperdiçaria
o tempo dele sem melhorar a ordenação.

A simulação assume que o gosto é linear nestes atributos. Se não for, o teto
real é menor — e é `confianca()` que denuncia isso, em vez de o modelo
ranquear com segurança fingida.
"""
from __future__ import annotations

import json
import math
import random
from pathlib import Path

from engine.selecao import NOMES_DOS_ATRIBUTOS

CAMINHO_PADRAO = Path(__file__).resolve().parents[1] / "data/julgamentos.json"


def _sigmoide(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, x))))


def escore(pesos: list[float], atributos: list[float]) -> float:
    return sum(p * a for p, a in zip(pesos, atributos))


def probabilidade(pesos: list[float], a: list[float], b: list[float]) -> float:
    """Probabilidade de o autor preferir A a B, segundo o modelo."""
    return _sigmoide(escore(pesos, [x - y for x, y in zip(a, b)]))


# ---------------------------------------------------------------------------
# Treino
# ---------------------------------------------------------------------------

def treinar(julgamentos: list[dict], n_atributos: int | None = None,
            epocas: int = 300, taxa: float = 0.5,
            regularizacao: float = 0.01) -> list[float]:
    """Descida de gradiente sobre a verossimilhança de Bradley-Terry.

    Cada julgamento é {"a": [...], "b": [...], "preferida": "a"|"b"}.
    A regularização evita que um atributo domine quando há poucos dados — com
    20 comparações e 13 atributos, o risco é real.
    """
    if not julgamentos:
        return [0.0] * (n_atributos or len(NOMES_DOS_ATRIBUTOS))
    d = n_atributos or len(julgamentos[0]["a"])
    pesos = [0.0] * d
    for _ in range(epocas):
        for j in julgamentos:
            diferenca = [x - y for x, y in zip(j["a"], j["b"])]
            alvo = 1.0 if j["preferida"] == "a" else 0.0
            erro = alvo - _sigmoide(escore(pesos, diferenca))
            pesos = [p + taxa * (erro * dif - regularizacao * p)
                     for p, dif in zip(pesos, diferenca)]
    return pesos


def confianca(julgamentos: list[dict], particoes: int = 4) -> dict:
    """Acurácia em comparações retidas, por validação cruzada.

    Se estacionar baixa, o gosto do autor usa algo que os atributos não medem.
    Dizer isso é mais útil que ranquear com confiança fingida — e é o mesmo
    princípio que já vale para `fracao_da_fonte` em engine/complexidade.py.
    """
    if len(julgamentos) < particoes * 2:
        return {"suficiente": False, "n": len(julgamentos),
                "aviso": f"{len(julgamentos)} julgamentos: poucos para estimar "
                         "confiança; siga julgando"}
    acertos = total = 0
    for p in range(particoes):
        teste = julgamentos[p::particoes]
        treino = [j for i, j in enumerate(julgamentos) if i % particoes != p]
        if not treino:
            continue
        pesos = treinar(treino)
        for j in teste:
            prev = "a" if probabilidade(pesos, j["a"], j["b"]) >= 0.5 else "b"
            acertos += prev == j["preferida"]
            total += 1
    taxa = acertos / total if total else 0.0
    return {
        "suficiente": True, "n": len(julgamentos),
        "acuracia": round(taxa, 4),
        "aviso": None if taxa >= 0.65 else
                 f"acurácia de {taxa:.0%} em comparações retidas: o gosto "
                 "parece usar algo que os atributos medidos não capturam. "
                 "Trate a ordenação como fraca.",
    }


def explicar(pesos: list[float], nomes: tuple[str, ...] = NOMES_DOS_ATRIBUTOS,
             limite: int = 5) -> dict:
    """Os pesos em português, do mais influente ao menos.

    É isto que mantém o ranqueador compatível com a tese do projeto: o autor
    pode discordar do modelo lendo o que ele aprendeu.
    """
    if not pesos or all(p == 0 for p in pesos):
        return {"treinado": False,
                "texto": "sem julgamentos ainda: o gosto não foi aprendido"}
    pares = sorted(zip(nomes, pesos), key=lambda x: -abs(x[1]))
    favorece = [f"{n} ({p:+.2f})" for n, p in pares[:limite] if p > 0]
    penaliza = [f"{n} ({p:+.2f})" for n, p in pares[:limite] if p < 0]
    partes = []
    if favorece:
        partes.append("prefere " + ", ".join(favorece))
    if penaliza:
        partes.append("penaliza " + ", ".join(penaliza))
    return {
        "treinado": True,
        "pesos": {n: round(p, 4) for n, p in zip(nomes, pesos)},
        "ordenados": [(n, round(p, 4)) for n, p in pares],
        "texto": "Pelo que você julgou até agora, você " + "; ".join(partes) + ".",
    }


# ---------------------------------------------------------------------------
# Qual par mostrar em seguida
# ---------------------------------------------------------------------------

def proximo_par(vetores: list[list[float]], pesos: list[float],
                ja_vistos: set[tuple[int, int]] | None = None,
                semente: int = 0, tentativas: int = 60) -> tuple[int, int]:
    """Par incerto E distante.

    Incerteza sozinha escolhe pares quase idênticos — o modelo fica em dúvida
    justamente porque os dois são iguais, e o julgamento não informa nada. O
    produto por distância corrige isso.
    """
    if len(vetores) < 2:
        raise ValueError("preciso de ao menos duas candidatas")
    ja_vistos = ja_vistos or set()
    rng = random.Random(semente)
    melhor, melhor_escore = None, -1.0
    for _ in range(tentativas):
        i, j = rng.sample(range(len(vetores)), 2)
        if (min(i, j), max(i, j)) in ja_vistos:
            continue
        p = probabilidade(pesos, vetores[i], vetores[j])
        incerteza = 1.0 - abs(p - 0.5) * 2.0
        distancia = math.sqrt(sum((x - y) ** 2
                                  for x, y in zip(vetores[i], vetores[j])))
        valor = incerteza * distancia
        if valor > melhor_escore:
            melhor, melhor_escore = (i, j), valor
    if melhor is None:                      # tudo já visto: sorteia
        i, j = rng.sample(range(len(vetores)), 2)
        melhor = (i, j)
    return melhor


def ordenar(vetores: list[list[float]], pesos: list[float]) -> list[int]:
    """Índices ordenados do mais para o menos preferido pelo modelo."""
    return sorted(range(len(vetores)), key=lambda i: -escore(pesos, vetores[i]))


# ---------------------------------------------------------------------------
# Memória
# ---------------------------------------------------------------------------

def carregar(caminho: str | Path = CAMINHO_PADRAO) -> list[dict]:
    """Os julgamentos gravados. É a única memória real do projeto: sem isso,
    cada sessão recomeça do zero."""
    p = Path(caminho)
    if not p.exists():
        return []
    dados = json.loads(p.read_text(encoding="utf-8"))
    return dados.get("julgamentos", [])


def gravar(julgamentos: list[dict], caminho: str | Path = CAMINHO_PADRAO) -> Path:
    p = Path(caminho)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "_sobre": "Comparações A/B feitas pelo autor. Cada entrada guarda os "
                  "atributos das duas candidatas e qual foi preferida. É a "
                  "partir daqui que engine/gosto.py aprende a ordenar — e é a "
                  "única verdade de referência que este projeto tem.",
        "atributos": list(NOMES_DOS_ATRIBUTOS),
        "n": len(julgamentos),
        "julgamentos": julgamentos,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def registrar(julgamentos: list[dict], a: list[float], b: list[float],
              preferida: str, contexto: dict | None = None) -> list[dict]:
    """Acrescenta um julgamento. Não muta a lista recebida."""
    if preferida not in ("a", "b"):
        raise ValueError(f"preferida deve ser 'a' ou 'b', recebi {preferida!r}")
    return julgamentos + [{"a": list(a), "b": list(b), "preferida": preferida,
                           **({"contexto": contexto} if contexto else {})}]
