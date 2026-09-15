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
Medida de complexidade e de encaixe — só com a stdlib.

DE ONDE VEM
-----------
Do working group do Santa Fe Institute *Complexity and the Structure of Music:
Universal Features and Evolutionary Perspectives Across Cultures* (2020), e do
que a bola de neve a partir dele alcança:

- **complexidade efetiva** (Gell-Mann & Lloyd, SFI): a complexidade de uma
  entidade é o comprimento de uma descrição comprimida das suas REGULARIDADES,
  excluída a parte aleatória;
- **redes rítmicas** (Buongiorno Nardelli, musicntwrk): sequências rítmicas
  representadas por vetor de duração, distância euclidiana entre vetores, rede
  por limiar;
- **métricas simbólicas de MIR** (muspy e afins): entropia de altura, extensão,
  consistência de escala, consistência de groove.

O PROBLEMA QUE ESTE MÓDULO RESOLVE — E O QUE ELE DESCOBRIU
-----------------------------------------------------------
O motor produz 11.818.152.720 canções distintas a partir de 21 segundos de
material de Rumi (âmbito 9, semente livre) — 3.229 anos de música. Medir
complexidade efetiva serve para responder "quanto disto é Rumi e quanto é o
sorteio", e essa é a pergunta central do projeto.

Mas ela NÃO serve para escolher. Como o ritmo vem inteiro do aruz, todas as
canções do espaço compartilham as mesmas regularidades e diferem só na parte
aleatória: pela definição de Gell-Mann e Lloyd, têm complexidade efetiva
praticamente idêntica. A medida que melhor descreve o projeto é cega dentro
dele.

Por isso há aqui duas famílias de medida — e cada uma ordena num eixo
diferente, o que foi medido e não suposto (300 melodias do mesmo verso e modo,
variando só a semente):

| Medida | valores distintos em 300 melodias | ordena o quê |
|---|---|---|
| `fracao_da_fonte` (decomposição) | **1** | nada: descreve o sistema |
| `ajuste_prosodico` | **1** | nada, entre melodias — mas separa LETRAS |
| `cantabilidade` | 10 | melodias |
| `aderencia_ao_metro` | muitos | melodias |

A decomposição é cega dentro do espaço porque todas as melodias compartilham as
mesmas regularidades. O ajuste prosódico é cego pelo mesmo motivo por outra via:
ele compara a letra contra o ARUZ, que vem de Rumi e não varia — por isso ele
ordena letras, que é exatamente o laço E→F→E da co-produção, e não melodias.
Quem ordena melodia é cantabilidade e aderência ao metro, porque medem a relação
do contorno com algo fora dele.

Dizer qual medida serve para quê é parte do trabalho: uma medida constante
apresentada como critério de escolha seria pior que medida nenhuma.

Filtrar não basta: cinco filtros básicos de sanidade reprovam 9 de cada 10
melodias e ainda deixam 285 anos de música. Gerar é de graça; julgar é caro.
"""
from __future__ import annotations

import math
import random
import zlib
from collections import Counter

from engine.generative import (DUR_ARUZ, LONGAS, MODOS, Frase, durar_por_aruz,
                               expandir_escansao, graus_no_ambito, _passear)
from engine.export import barrar

# passos que a regra de contorno de gerar_melodia pode sortear, por tipo de
# sílaba. Mantido em sincronia com gerar_melodia — o teste
# test_passos_em_sincronia trava isso.
PASSOS_POR_SIMBOLO = {
    "u": (-2, -1, 1, 2),
    "–": (-3, -2, -1, 0, 1, 2, 3),
    "=": (-3, -2, -1, 0, 1, 2, 3),
}

# vogais do português, para detectar sílaba tônica e fronteira de elisão
VOGAIS = "aeiouáàâãéêíóôõúüAEIOUÁÀÂÃÉÊÍÓÔÕÚÜ"


# ---------------------------------------------------------------------------
# 1. Decomposição: quanto é Rumi, quanto é o sorteio
# ---------------------------------------------------------------------------

def bits_de_rumi(verso: dict) -> float:
    """Conteúdo de informação da parte REGULAR: a escansão que veio da fonte.

    É a "descrição comprimida das regularidades" de Gell-Mann e Lloyd, medida
    no que o projeto de fato herda de Rumi — a sequência de quantidades
    silábicas. Usa a entropia empírica dos símbolos do próprio verso, que é o
    limite de compressão de uma fonte sem memória.
    """
    escansao = verso["escansao"]
    if not escansao:
        return 0.0
    n = len(escansao)
    freq = Counter(escansao)
    bits_por_simbolo = -sum((k / n) * math.log2(k / n) for k in freq.values())
    return bits_por_simbolo * n


def bits_de_acaso(verso: dict, modo: str = "dorico", ambito: int = 9) -> float:
    """Conteúdo de informação da parte ALEATÓRIA: o passeio melódico.

    Exato, não estimado: em cada posição, o log2 do número de graus distintos
    que o passeio pode alcançar dali. É a mesma contagem que dá o tamanho do
    espaço de melodias — `2**bits_de_acaso` é o número de melodias distintas
    que o motor pode gerar para este verso e modo.
    """
    graus = MODOS[modo]
    teto = graus_no_ambito(graus, ambito) - 1
    alcancaveis = {0: 1}          # distribuição de grau -> nº de caminhos
    total = 1
    for i, simbolo in enumerate(verso["escansao"]):
        passos = PASSOS_POR_SIMBOLO[simbolo]
        novo: dict[int, int] = {}
        for g, n in alcancaveis.items():
            for gp in {_passear(g, p, teto) for p in passos}:
                novo[gp] = novo.get(gp, 0) + n
        alcancaveis = novo
        if i == len(verso["escansao"]) - 2:
            total = sum(alcancaveis.values())
    # a última nota é sobrescrita pelo fecho: tônica, terça ou quinta do modo
    fechos = len({min(x, teto) for x in (0, 2, 4)})
    return math.log2(total * fechos) if total * fechos > 0 else 0.0


def decompor(frase: Frase, verso: dict, ambito: int = 9) -> dict:
    """Decomposição no espírito da complexidade efetiva: o que veio da fonte,
    o que veio do sorteio, e em que proporção.

    `fracao_da_fonte` é a resposta computável para "quanto desta canção é
    Rumi". Note que ela é praticamente constante dentro do espaço de um mesmo
    verso e modo — é justamente essa constância que motiva `medir_encaixe`.
    """
    rumi = bits_de_rumi(verso)
    acaso = bits_de_acaso(verso, frase.modo or "dorico", ambito)
    total = rumi + acaso
    return {
        "bits_de_rumi": round(rumi, 3),
        "bits_de_acaso": round(acaso, 3),
        "fracao_da_fonte": round(rumi / total, 4) if total else 0.0,
        "melodias_no_espaco": int(round(2 ** acaso)),
        "regra": "bits_de_rumi = entropia da escansão; "
                 "bits_de_acaso = log2 dos caminhos do passeio",
        "aviso": "a fração é quase constante dentro de um mesmo verso+modo: "
                 "todas as melodias do espaço compartilham as regularidades e "
                 "diferem só no sorteio. Para ordenar candidatas, ver "
                 "medir_encaixe().",
        "proxy_compressao": _proxy_compressao(frase),
    }


def _proxy_compressao(frase: Frase) -> dict:
    """Proxy de sofisticação por compressão.

    Sofisticação no sentido de Koppel é incomputável, e por isso a literatura
    usa compressão como proxy. Aqui ele é reportado COM a ressalva de que não
    discrimina nada neste comprimento: medi 22 bytes para a escansão real do
    Masnavi contra 22,2 para embaralhamentos dela. Fica registrado para não
    ser reimplementado por quem vier depois achando que resolve.
    """
    alturas = ",".join(str(n.midi) for n in frase.notas).encode()
    duracoes = ",".join(str(n.dur) for n in frase.notas).encode()
    return {
        "bytes_alturas": len(zlib.compress(alturas, 9)),
        "bytes_duracoes": len(zlib.compress(duracoes, 9)),
        "aviso": "proxy sem poder discriminante em sequências desta ordem "
                 "(~10-15 símbolos); não use para ordenar",
    }


# ---------------------------------------------------------------------------
# 2. Métricas simbólicas de MIR, para melodia monofônica
# ---------------------------------------------------------------------------

def _entropia(valores) -> float:
    valores = list(valores)
    if not valores:
        return 0.0
    n = len(valores)
    return -sum((k / n) * math.log2(k / n) for k in Counter(valores).values())


def metricas_mir(frase: Frase, compasso: float = 4.0) -> dict:
    """Métricas objetivas no padrão do MIR simbólico (muspy e afins),
    reimplementadas para melodia monofônica e sem dependência."""
    if not frase.notas:
        return {}
    alturas = [n.midi for n in frase.notas]
    graus = MODOS.get(frase.modo or "dorico", MODOS["dorico"])
    classes_do_modo = {(frase.tonica_midi + g) % 12 for g in graus}
    return {
        "entropia_de_altura": round(_entropia(alturas), 3),
        "entropia_de_classe_de_altura": round(_entropia(m % 12 for m in alturas), 3),
        "alturas_usadas": len(set(alturas)),
        "classes_usadas": len({m % 12 for m in alturas}),
        "extensao_semitons": max(alturas) - min(alturas),
        "consistencia_modal": round(
            sum(1 for m in alturas if m % 12 in classes_do_modo) / len(alturas), 4),
        "consistencia_de_groove": round(consistencia_de_groove(frase, compasso), 4),
    }


def consistencia_de_groove(frase: Frase, compasso: float = 4.0) -> float:
    """Distância de Hamming média entre os ataques de compassos consecutivos,
    invertida: 1.0 = compassos com o mesmo desenho de ataques.

    Reusa barrar() de engine/export.py, que já sabe dividir a frase em
    compassos e ligar o que atravessa a barra. Para um verso de aruz, a
    periodicidade do pé deve aparecer aqui.
    """
    compassos = barrar(frase.notas, compasso, frase.anacruse)
    # o último compasso é completado com pausa para fechar a barra (ver
    # barrar()); compará-lo com um compasso cheio mede o preenchimento, não o
    # groove. Fora, desde que sobrem dois para comparar.
    if len(compassos) > 2 and any(ev.pausa for ev in compassos[-1]):
        compassos = compassos[:-1]
    if len(compassos) < 2:
        return 1.0
    resolucao = 0.25                       # grade de semicolcheia
    n_casas = int(round(compasso / resolucao))

    grades = []
    for eventos in compassos:
        grade = [0] * n_casas
        pos = 0.0
        for ev in eventos:
            if not ev.pausa and not ev.tie_fim:
                casa = int(round(pos / resolucao))
                if 0 <= casa < n_casas:
                    grade[casa] = 1
            pos += ev.dur
        grades.append(grade)

    distancias = [
        sum(x != y for x, y in zip(a, b)) / n_casas
        for a, b in zip(grades, grades[1:])
    ]
    return 1.0 - sum(distancias) / len(distancias)


def compasso_natural(verso: dict, metros: dict) -> dict:
    """O compasso que o PÉ do metro pede, somando as durações do pé.

    Achado que motivou esta função: o pé do ramal (`fāʿilātun`, `–u––`) dura
    1.0+0.5+1.0+1.0 = **3.5 quarters**, ou seja sete colcheias — 7/8. Contra a
    barra de 4/4 que o exportador usa por padrão, o pé desliza, e a
    consistência de groove do Masnavi cai para 0.56, ABAIXO do acaso (0.76).
    Medido em 7/8, sobe para **1.0000**.

    Isto não é detalhe técnico: o HANDOUT §4 já listava 7/8 entre as "métricas
    que respiram" do Clube da Esquina. A métrica persa e a estética brasileira
    do projeto se encontram no mesmo compasso, e a medida acha isso sozinha.
    """
    metro = metros.get(verso.get("metro", ""), {})
    pes = metro.get("padrao_pes") or ([metro["padrao_pe"]] if metro.get("padrao_pe") else [])
    if not pes:
        return {"aplicavel": False, "motivo": "metro sem pé declarado"}
    duracoes = [sum(DUR_ARUZ[s] for s in pe) for pe in pes]
    return {
        "aplicavel": True,
        "duracao_do_pe": duracoes,
        "compasso_sugerido": duracoes[0] if len(set(duracoes)) == 1 else None,
        "em_colcheias": [int(d / 0.5) for d in duracoes],
        "nota": "compasso em quarterLength; 3.5 = 7/8, 3.0 = 3/4, 4.0 = 4/4",
    }


def melhor_compasso(frase: Frase,
                    candidatos: tuple[float, ...] = (1.5, 2.0, 3.0, 3.5, 4.0)) -> dict:
    """Procura, entre compassos candidatos, aquele em que o desenho rítmico
    mais se repete de barra em barra. Verificação empírica do que
    compasso_natural() deriva do pé."""
    escores = {c: round(consistencia_de_groove(frase, c), 4) for c in candidatos}
    melhor = max(escores, key=lambda c: escores[c])
    return {"escores": escores, "melhor": melhor, "consistencia": escores[melhor]}


# ---------------------------------------------------------------------------
# 3. Ritmo como vetor e como rede (Buongiorno Nardelli)
# ---------------------------------------------------------------------------

def vetor_duracao(frase: Frase) -> list[float]:
    """Vetor de duração: as razões relativas de duração da sequência.

    Por ser de RAZÕES e não de valores absolutos, é invariante sob aumentação
    e diminuição — duas leituras da mesma figura rítmica ficam à distância
    zero, que é o comportamento desejado.
    """
    durs = [n.dur for n in frase.notas]
    total = sum(durs)
    return [d / total for d in durs] if total else []


def distancia_ritmica(a: Frase, b: Frase) -> float:
    """Distância euclidiana entre os vetores de duração de duas frases.

    Frases de comprimentos diferentes são incomparáveis, e isso é recusado em
    vez de resolvido por preenchimento — comparar aruz de 11 sílabas com um de
    14 por zero-padding produziria um número sem significado.
    """
    va, vb = vetor_duracao(a), vetor_duracao(b)
    if len(va) != len(vb):
        raise ValueError(
            f"frases de comprimentos diferentes ({len(va)} x {len(vb)}) não são "
            "comparáveis por vetor de duração")
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(va, vb)))


def rede_ritmica(frases: dict[str, Frase], limiar: float = 0.05) -> dict:
    """Rede de sequências rítmicas: nós são frases, arestas ligam as que estão
    a distância menor ou igual ao limiar."""
    nomes = list(frases)
    arestas = []
    for i, a in enumerate(nomes):
        for b in nomes[i + 1:]:
            try:
                d = distancia_ritmica(frases[a], frases[b])
            except ValueError:
                continue
            if d <= limiar:
                arestas.append({"de": a, "para": b, "distancia": round(d, 6)})
    return {"nos": nomes, "limiar": limiar, "arestas": arestas}


# ---------------------------------------------------------------------------
# 4. Modelo nulo: a estrutura do aruz está acima do acaso?
# ---------------------------------------------------------------------------

def periodicidade(durs: list[float], periodo: int) -> float:
    """Fração de posições que se repetem com o período dado."""
    if periodo >= len(durs) or periodo < 1:
        return 0.0
    pares = list(zip(durs, durs[periodo:]))
    return sum(a == b for a, b in pares) / len(pares)


def periodicidade_vs_acaso(verso: dict, periodo: int = 4, n: int = 2000,
                           semente: int = 0) -> dict:
    """Compara a periodicidade do pé contra embaralhamentos das mesmas durações.

    O nulo preserva a entropia (são as mesmas durações) e destrói só a ordem,
    que é o que isola a contribuição do metro.

    ATENÇÃO AO PODER: com ~14 símbolos e três valores de duração, este teste
    não distingue hipóteses próximas. Medido: masnavi_1 e masnavi_2 dão p≈0,016
    (o pé do ramal aparece), mas divan_2214 dá p=0,072 na escansão atual e
    p=0,10 na proposta — ou seja, o teste não decide entre as duas. O campo
    'poder_suficiente' marca isso, e quem usar o resultado deve respeitá-lo.
    """
    durs = durar_por_aruz(verso["escansao"])
    real = periodicidade(durs, periodo)
    rng = random.Random(semente)
    amostras = []
    for _ in range(n):
        s = durs[:]
        rng.shuffle(s)
        amostras.append(periodicidade(s, periodo))
    media = sum(amostras) / len(amostras)
    desvio = math.sqrt(sum((x - media) ** 2 for x in amostras) / len(amostras))
    p = sum(1 for x in amostras if x >= real) / len(amostras)
    return {
        "periodo": periodo,
        "periodicidade_real": round(real, 4),
        "periodicidade_media_do_acaso": round(media, 4),
        "z": round((real - media) / desvio, 3) if desvio else None,
        "p": round(p, 4),
        "n_embaralhamentos": n,
        "poder_suficiente": len(durs) >= 24,
        "aviso": None if len(durs) >= 24 else
                 f"apenas {len(durs)} símbolos: o nulo por embaralhamento não "
                 "tem poder para distinguir hipóteses próximas neste "
                 "comprimento; trate o p como descritivo",
    }


# ---------------------------------------------------------------------------
# 5. Encaixe — a família que de fato ordena candidatas
# ---------------------------------------------------------------------------

ACENTUADAS = "áàâãéêíóôõúü"
# terminações que puxam a tonicidade para a última sílaba (regra do português)
FIM_OXITONA = ("i", "u", "l", "r", "z", "im", "um", "om", "ins", "uns", "ons")
# monossílabos átonos: artigos, preposições, conjunções e clíticos comuns
ATONOS = {"a", "o", "as", "os", "um", "uma", "de", "do", "da", "dos", "das",
          "em", "no", "na", "nos", "nas", "e", "ou", "que", "se", "com", "por",
          "ao", "aos", "à", "às", "me", "te", "lhe", "nos", "vos", "para"}


def separar_silabas_pt(letra: str) -> list[list[str]]:
    """Lê a letra na convenção da interface — sílabas separadas por hífen,
    palavras por espaço — e devolve uma lista de palavras silabadas.

    "Es-cu-ta o jun-co" -> [["Es","cu","ta"], ["o"], ["jun","co"]]
    """
    palavras = []
    for bruta in letra.replace(",", " ").replace(".", " ").split():
        silabas = [s for s in bruta.split("-") if s]
        if silabas:
            palavras.append(silabas)
    return palavras


def indices_tonicos(palavras: list[list[str]]) -> list[bool]:
    """Marca, sílaba a sílaba na sequência inteira, quais são tônicas.

    Aplica a regra padrão do português: vogal acentuada manda; senão, termina
    em i/u/l/r/z/im/um/om -> oxítona; caso contrário, paroxítona. Monossílabos
    de uma lista de átonos (artigos, preposições, clíticos) não contam como
    tônicos.

    É heurística declarada, não análise gramatical: sem dicionário ela erra
    proparoxítonas não acentuadas e palavras fora da regra. Serve para um
    escore de ajuste — nunca para afirmar que uma escansão está certa.
    """
    marcas = []
    for silabas in palavras:
        n = len(silabas)
        if n == 1:
            marcas.append(silabas[0].lower().strip("¿?!¡") not in ATONOS)
            continue
        alvo = None
        for i, s in enumerate(silabas):
            if any(v in s.lower() for v in ACENTUADAS):
                alvo = i
        if alvo is None:
            ultima = silabas[-1].lower().strip(",.;:!?\"'")
            # o -s de plural não muda a tonicidade: "depois" é oxítona porque
            # termina em -i, não paroxítona porque termina em -s
            nucleo = ultima[:-1] if ultima.endswith("s") and len(ultima) > 1 else ultima
            alvo = n - 1 if (ultima.endswith(FIM_OXITONA)
                             or nucleo.endswith(FIM_OXITONA)) else n - 2
        marcas.extend(i == alvo for i in range(n))
    return marcas


def ajuste_prosodico(frase: Frase, letra: str | list[str]) -> dict:
    """Mede se a sílaba tônica do português cai em nota longa do aruz.

    É o encaixe central da co-produção: a letra negocia com a métrica de Rumi
    até caber. Ao contrário do semáforo da interface, que é binário (casa ou
    não casa em número de sílabas), aqui o escore é contínuo — e é por isso
    que ele consegue ORDENAR candidatas, que é o que a decomposição de
    complexidade efetiva não faz.

    Aceita a letra na convenção da interface ("Es-cu-ta o jun-co") ou já
    silabada.
    """
    if not frase.notas:
        return {"aplicavel": False, "motivo": "frase vazia"}
    palavras = (separar_silabas_pt(letra) if isinstance(letra, str)
                else [[s] for s in letra])
    silabas = [s for palavra in palavras for s in palavra]
    if len(silabas) != len(frase.notas):
        return {
            "aplicavel": False,
            "motivo": f"{len(silabas)} sílabas para {len(frase.notas)} notas",
            "silabas_pt": len(silabas), "notas": len(frase.notas),
        }
    tonicas = indices_tonicos(palavras)
    longas = [n.aruz in LONGAS for n in frase.notas]
    # toda tônica deveria cair em sílaba longa do aruz; átona, em qualquer uma
    tonicas_em_longa = sum(1 for t, l in zip(tonicas, longas) if t and l)
    total_tonicas = sum(tonicas)
    tonicas_em_curta = [
        {"silaba": s, "aruz": n.aruz, "dur": n.dur}
        for s, t, n in zip(silabas, tonicas, frase.notas) if t and n.aruz not in LONGAS
    ]
    return {
        "aplicavel": True,
        "ajuste": round(tonicas_em_longa / total_tonicas, 4) if total_tonicas else 1.0,
        "tonicas": total_tonicas,
        "tonicas_em_longa": tonicas_em_longa,
        "choques": tonicas_em_curta,
        "regra": "sílaba tônica do português deve cair em sílaba longa do aruz",
        "aviso": "tonicidade por heurística (regra padrão do português, sem "
                 "dicionário); erra proparoxítonas não acentuadas",
    }


def cantabilidade(frase: Frase) -> dict:
    """O que uma voz humana sustenta: extensão, tamanho dos saltos, e saltos
    seguidos na mesma direção."""
    if len(frase.notas) < 2:
        return {"cantabilidade": 1.0}
    alturas = [n.midi for n in frase.notas]
    saltos = [b - a for a, b in zip(alturas, alturas[1:])]
    grandes = [s for s in saltos if abs(s) > 5]
    seguidos = sum(
        1 for a, b in zip(saltos, saltos[1:])
        if abs(a) > 2 and abs(b) > 2 and (a > 0) == (b > 0))
    extensao = max(alturas) - min(alturas)
    escore = 1.0
    escore -= 0.5 * len(grandes) / len(saltos)
    escore -= 0.3 * seguidos / len(saltos)
    escore -= 0.2 * max(0.0, (extensao - 12) / 12)
    return {
        "cantabilidade": round(max(0.0, min(1.0, escore)), 4),
        "extensao_semitons": extensao,
        "saltos_grandes": len(grandes),
        "saltos_seguidos_mesma_direcao": seguidos,
        "maior_salto": max(abs(s) for s in saltos),
    }


def aderencia_ao_metro(frase: Frase, verso: dict, metros: dict) -> dict:
    """Confronta o contorno melódico com a assinatura afetiva declarada do
    metro.

    O corpus declara `assinatura_afetiva` para cada metro ("movimento
    espiritual, giro, corrente" para o ramal; "ondulação, anseio, embalo" para
    o hazaj) desde o início, e nenhuma linha de código jamais a leu. Aqui ela
    vira critério: metro corrente pede contorno que ande, metro de embalo pede
    contorno que oscile em torno de um centro.
    """
    metro = metros.get(verso.get("metro", ""), {})
    assinatura = metro.get("assinatura_afetiva", "")
    if len(frase.notas) < 3:
        return {"aplicavel": False, "assinatura": assinatura}
    alturas = [n.midi for n in frase.notas]
    saltos = [b - a for a, b in zip(alturas, alturas[1:])]
    deriva = abs(alturas[-1] - alturas[0])
    movimento = sum(abs(s) for s in saltos)
    # 'corrente' = a melodia vai a algum lugar; 'embalo' = ela volta ao centro
    direcional = deriva / movimento if movimento else 0.0
    if "corrente" in assinatura or "giro" in assinatura:
        aderencia, esperado = direcional, "contorno que avança (corrente)"
    elif "embalo" in assinatura or "ondulação" in assinatura:
        aderencia, esperado = 1.0 - direcional, "contorno que oscila (embalo)"
    else:
        aderencia, esperado = None, "sem assinatura declarada"
    return {
        "aplicavel": aderencia is not None,
        "assinatura": assinatura,
        "esperado": esperado,
        "direcionalidade": round(direcional, 4),
        "aderencia": round(aderencia, 4) if aderencia is not None else None,
    }


def medir_encaixe(frase: Frase, verso: dict, metros: dict,
                  letra: str | list[str] | None = None) -> dict:
    """As medidas de relação entre a melodia e o que está fora dela.

    Cada uma ordena num eixo diferente, e o campo `ordena` diz qual — ver a
    tabela no topo do módulo:

    - `cantabilidade` e `aderencia_ao_metro` ordenam MELODIAS;
    - `ajuste_prosodico` ordena LETRAS (é constante entre melodias do mesmo
      verso, porque compara a letra contra o aruz, que não varia).
    """
    encaixe = {
        "cantabilidade": {**cantabilidade(frase), "ordena": "melodias"},
        "aderencia_ao_metro": {**aderencia_ao_metro(frase, verso, metros),
                               "ordena": "melodias"},
    }
    if letra is not None:
        encaixe["ajuste_prosodico"] = {**ajuste_prosodico(frase, letra),
                                       "ordena": "letras"}
    return encaixe


def relatorio(frase: Frase, verso: dict, metros: dict, ambito: int = 9,
              letra: str | list[str] | None = None) -> dict:
    """O relatório completo: o que descreve e o que ordena."""
    return {
        "decomposicao": decompor(frase, verso, ambito),
        "metricas_mir": metricas_mir(frase),
        "encaixe": medir_encaixe(frase, verso, metros, letra),
        "modelo_nulo": periodicidade_vs_acaso(verso),
        "compasso_natural": compasso_natural(verso, metros),
        "melhor_compasso": melhor_compasso(frase),
        "vetor_duracao": [round(x, 6) for x in vetor_duracao(frase)],
    }
