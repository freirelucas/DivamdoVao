#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Operações rítmicas sobre o material do aruz — HANDOUT §3.

O aruz dá o material; a co-produção o explora. Este módulo implementa as
cinco operações previstas no handout (a primeira já estava no motor):

    derivação direta   durar_por_aruz() em engine/generative.py
    inversão métrica   trocar longas<->curtas: a mesma frase "ao contrário"
    aumentação/dim.    multiplicar todas as durações
    deslocamento       empurrar a frase contra o tempo forte (síncope)
    sobreposição       o mesmo metro em duas vozes defasadas (hoquetus)

COMO ISSO CONTINUA AUDITÁVEL
----------------------------
A promessa do projeto é que nenhum valor rítmico é inventado. Uma operação
que transformasse as durações e apagasse o rastro quebraria exatamente isso.
Então cada operação:

  - preserva `NotaTrace.dur_base`, a duração que veio do aruz, intacta;
  - escreve seu nome e seus parâmetros em `Frase.operacoes`;
  - é uma função PURA: devolve uma frase nova, não muta a que recebeu.

Com isso o relatório de auditoria exibe a cadeia inteira e reproduzível:

    sílaba -> aruz -> dur_base -> [operações] -> dur

A duração final não é um palpite: é o resultado de uma função declarada
aplicada a um valor que veio de Rumi.
"""
from __future__ import annotations

from engine.generative import DUR_ARUZ, LONGAS, Frase, durar_por_aruz

# A inversão troca as duas quantidades primitivas do aruz. A superlonga '='
# é composta (longa + curta: contém as duas), então é o seu próprio espelho
# — e é essa escolha que faz da inversão uma involução: aplicá-la duas vezes
# devolve a escansão original, o que os testes verificam.
INVERSAO = {"u": "–", "–": "u", "=": "="}


def inverter_escansao(escansao: list[str]) -> list[str]:
    """Espelho métrico da escansão: longa <-> curta. Pura e involutiva."""
    return [INVERSAO[s] for s in escansao]


def escalar(durs: list[float], fator: float) -> list[float]:
    """Multiplica as durações por um fator. Pura."""
    if fator <= 0:
        raise ValueError(f"fator deve ser positivo, recebi {fator}")
    return [d * fator for d in durs]


# ---------------------------------------------------------------------------
# Aplicadores sobre Frase — devolvem uma frase nova e registram a operação
# ---------------------------------------------------------------------------

def inversao_metrica(frase: Frase) -> Frase:
    """A mesma frase "ao contrário": longas viram curtas e vice-versa.

    Útil para pontes e contracantos (HANDOUT §3). As alturas não mudam — a
    operação é rítmica.

    A regra do fim de hemistíquio (última sílaba conta como longa) é da obra,
    não da operação, então continua valendo depois da inversão. Por isso a
    última nota pode não mudar de duração: a involução vale para a escansão,
    não necessariamente para as durações finais.
    """
    nova = frase.copia()
    invertida = inverter_escansao([n.aruz for n in nova.notas])
    for nota, dur in zip(nova.notas, durar_por_aruz(invertida)):
        nota.dur = dur
    nova.operacoes.append("inversao_metrica")
    return nova


def aumentacao(frase: Frase, fator: float = 2.0) -> Frase:
    """Multiplica as durações — x2 para clímax lento (HANDOUT §3)."""
    nova = frase.copia()
    for nota, dur in zip(nova.notas, escalar([n.dur for n in nova.notas], fator)):
        nota.dur = dur
    nova.anacruse *= fator
    nova.operacoes.append(f"aumentacao(fator={fator})")
    return nova


def diminuicao(frase: Frase, fator: float = 2.0) -> Frase:
    """Divide as durações — /2 para transe (HANDOUT §3)."""
    if fator <= 0:
        raise ValueError(f"fator deve ser positivo, recebi {fator}")
    nova = aumentacao(frase, 1.0 / fator)
    nova.operacoes[-1] = f"diminuicao(fator={fator})"
    return nova


def deslocamento(frase: Frase, offset: float = 0.5) -> Frase:
    """Empurra a frase inteira contra o tempo forte — a síncope que aproxima
    do partido-alto (HANDOUT §3).

    O deslocamento é uma anacruse: cada nota mantém a duração que veio da
    sua própria sílaba, e é a frase que entra fora do tempo. A alternativa
    seria rotacionar a lista de durações, mas aí a duração de uma sílaba
    passaria a vir de outra sílaba — o vínculo 1:1 sílaba<->duração, que é o
    compromisso central do projeto, se perderia.
    """
    if offset < 0:
        raise ValueError(f"offset não pode ser negativo, recebi {offset}")
    nova = frase.copia()
    nova.anacruse += offset
    nova.operacoes.append(f"deslocamento(offset={offset})")
    return nova


def sobreposicao(frase: Frase, defasagem: float = 1.0) -> tuple[Frase, Frase]:
    """O mesmo metro em duas vozes defasadas — hoquetus, o coro dervixe
    (HANDOUT §3).

    Devolve (voz1, voz2): a primeira intacta, a segunda deslocada pela
    defasagem. As duas carregam o mesmo rastro de aruz, o que é o ponto:
    a textura nasce de uma única escansão de Rumi lida em dois tempos.
    """
    voz1 = frase.copia()
    voz1.operacoes.append(f"sobreposicao(voz=1, defasagem={defasagem})")
    voz2 = deslocamento(frase, defasagem)
    voz2.operacoes[-1] = f"sobreposicao(voz=2, defasagem={defasagem})"
    return voz1, voz2


OPERACOES = {
    "inversao": inversao_metrica,
    "aumentacao": aumentacao,
    "diminuicao": diminuicao,
    "deslocamento": deslocamento,
}


def conferir_rastro(frase: Frase) -> dict:
    """Verifica que dur_base ainda é a duração que veio do aruz, mesmo depois
    das operações. É o que mantém "nenhum valor rítmico é inventado"
    verificável sob transformação — usado pelos testes e pelo relatório."""
    esperado = durar_por_aruz([n.aruz for n in frase.notas])
    divergencias = [
        {"silaba": n.silaba, "aruz": n.aruz, "dur_base": n.dur_base, "esperado": e}
        for n, e in zip(frase.notas, esperado) if n.dur_base != e
    ]
    return {
        "operacoes": list(frase.operacoes),
        "anacruse": frase.anacruse,
        "rastro_intacto": not divergencias,
        "divergencias": divergencias,
    }
