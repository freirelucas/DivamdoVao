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
O vazn vira escansão — ingestão de metro com fonte dupla.

O PROBLEMA QUE ESTE MÓDULO RESOLVE
----------------------------------
Escandir verso a verso é o gargalo de qualquer corpus de poesia quantitativa:
é trabalho filológico, caro, e o projeto tinha três versos. Mas a medição
mostrou algo que dispensa esse trabalho quase todo — nos três versos do corpus,
a escansão declarada é EXATAMENTE o metro reescrito, posição por posição. Zero
informação nova por verso. Logo, saber o metro é saber a escansão.

E o metro é publicado. O Ganjoor registra, para cada poema, um vazn como

    مفتعلن مفاعلن مفتعلن مفاعلن (رجز مثمن مطوی مخبون)

que não é um rótulo opaco: é uma sequência de nomes de PÉS (arkān), e cada pé
é uma palavra-mnemônica cuja própria quantidade silábica É o padrão que ela
nomeia (moftaʿelon = mof·ta·ʿe·lon = – u u –). O vazn parseia por composição.
Conferir ~17 pés uma vez serve milhares de poemas.

POR QUE FONTE DUPLA
-------------------
Ler a quantidade da palavra-mnemônica tem ambiguidade real: sem diacríticos,
فعلن é faʿlon (– –) ou faʿalon (u u –), e as duas existem como pé final de
metros reais. Resolver isso por intuição seria repetir o erro que
engine/filtros.py registra — ancorar heurística em autoridade inventada.

Então não se resolve por intuição. A escansão derivada do vazn só é aceita se
casar com um padrão de data/metros_publicados.json (Elwell-Sutton, via a
tabela de frequência do artigo de referência). Quando duas leituras casam, o
metro fica PENDENTE para decisão humana — uma decisão por metro, não por
poema. Quando nenhuma casa, fica em QUARENTENA e não entra no corpus.

Medido numa amostra aleatória de 70 gazais do Divã de Shams (68 com vazn
registrado, 21 metros distintos): 65 poemas (95,6%) resolvidos por fonte
dupla sem intervenção humana, 0 pendentes, 3 poemas em quarentena (os metros
raros مفاعلن فعلاتن... de 16 posições e متفاعلن متفاعلن, ausentes da tabela
publicada). A quarentena funcionando é o resultado desejado, não uma falha.

O QUE A INGESTÃO EM LOTE NÃO PODE AFIRMAR
-----------------------------------------
O metro fixa as POSIÇÕES métricas; não fixa onde duas posições se fundem numa
sílaba superlonga, porque isso depende das palavras do verso. O divan_2214
mostra o caso: o corpus traz 14 sílabas (–uu–u–u–=u=–u–, com superlonga em
yār e xār) e o vazn dá 16 símbolos simples. Expandidos, são as MESMAS 16
posições, e a duração total é idêntica (= vale 1,5, igual a – mais u). O que
muda é o agrupamento: uma nota de 1,5 ou duas de 1,0 e 0,5.

Então a escansão derivada do vazn vem com 'segmentacao_silabica':
'posicional' — cada posição é uma sílaba, que é o padrão quando não há
superlonga, e é explicitamente provisório onde houver. Conferir a superlonga
exige o texto romanizado, que o Ganjoor não publica. Verso ingerido em lote
sai com superlongas_conferidas=False, e o rastro de auditoria diz isso.

Só stdlib. Nenhuma rede aqui: a rede está em ferramentas/colher.py.
"""
from __future__ import annotations

import itertools
import json
import re
import unicodedata
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
ARKAN_PADRAO = RAIZ / "data/arkan.json"
PUBLICADOS_PADRAO = RAIZ / "data/metros_publicados.json"

# tatweel e juntadores que aparecem na grafia do Ganjoor e não mudam o pé
_LIXO = "ـ‌‍‎‏"

# teto de leituras a testar, para que um vazn com muitos pés ambíguos não
# vire explosão combinatória silenciosa
MAX_LEITURAS = 256


def carregar_arkan(caminho: Path | str | None = None) -> dict:
    """Carrega a tabela de pés, indexada pelo nome persa."""
    dados = json.loads(Path(caminho or ARKAN_PADRAO).read_text(encoding="utf-8"))
    return {e["nome_persa"]: e for e in dados["arkan"]} | {"_meta": dados}


def carregar_publicados(caminho: Path | str | None = None) -> dict:
    """Carrega os padrões métricos publicados (a segunda fonte)."""
    return json.loads(Path(caminho or PUBLICADOS_PADRAO).read_text(encoding="utf-8"))


def normalizar_pe(token: str) -> str:
    """Tira tatweel, juntadores e diacríticos da grafia de um nome de pé."""
    t = unicodedata.normalize("NFC", token)
    t = "".join(c for c in t if c not in _LIXO)
    # As marcas de vocalização FICAM. Apagá-las parecia inofensivo porque a
    # amostra de gazais não as usava, mas o inventário completo do Ganjoor tem
    # فاعلُ (fāʿelo, – u u) ao lado de فاعل: a damma é o que distingue os dois
    # pés, e apagá-la confundiria um com o outro silenciosamente.
    return t.strip()


def partir_vazn(vazn: str) -> tuple[list[str], str]:
    """Separa o vazn em nomes de pés e no nome persa do metro (o parêntese).

    'مفتعلن مفاعلن (رجز مثمن مطوی مخبون)' -> (['مفتعلن','مفاعلن'], 'رجز مثمن مطوی مخبون')
    """
    m = re.search(r"\((.*)\)\s*$", vazn.strip(), re.S)
    nome = m.group(1).strip() if m else ""
    corpo = vazn[: m.start()] if m else vazn
    pes = [p for p in (normalizar_pe(t) for t in corpo.split()) if p]
    return pes, nome


def leituras_do_pe(entrada: dict) -> list[dict]:
    """Todas as leituras declaradas de um pé: a principal e as alternativas."""
    leituras = [{"romanizacao": entrada["romanizacao"],
                 "padrao_silabas": entrada["padrao_silabas"],
                 "padrao_posicoes": entrada["padrao_posicoes"]}]
    for alt in entrada.get("leituras_alternativas", []):
        leituras.append({"romanizacao": alt["romanizacao"],
                         "padrao_silabas": alt["padrao_silabas"],
                         "padrao_posicoes": alt["padrao_posicoes"]})
    return leituras


def casa_padrao(posicoes: list[str], padrao: str) -> bool:
    """Compara posições métricas com um padrão publicado. 'x' é anceps."""
    return len(posicoes) == len(padrao) and all(
        a == b or b in "xX" for a, b in zip(posicoes, padrao))


def _publicados_que_casam(posicoes: list[str], publicados: dict) -> list[dict]:
    casados = []
    for p in publicados["padroes"]:
        if casa_padrao(posicoes, p["padrao"]):
            casados.append(p | {"_casou_em": "verso inteiro"})
        elif p.get("meio_verso") and casa_padrao(posicoes, p["meio_verso"]):
            casados.append(p | {"_casou_em": "meio verso"})
    return casados


def candidatos_do_vazn(vazn: str, arkan: dict) -> tuple[list[dict], list[str]]:
    """Todas as leituras possíveis do vazn, e os pés que a tabela não conhece.

    Cada candidato traz a escansão em SÍLABAS (com '=' na superlonga, que é a
    forma gravada no corpus) e em POSIÇÕES (a forma comparada com a literatura
    e fatiada pelo motor).
    """
    pes, _ = partir_vazn(vazn)
    if not pes:
        return [], []
    faltam = [p for p in pes if p not in arkan]
    if faltam:
        return [], faltam

    opcoes = [leituras_do_pe(arkan[p]) for p in pes]
    total = 1
    for o in opcoes:
        total *= len(o)
    if total > MAX_LEITURAS:
        raise ValueError(
            f"vazn com {total} leituras possíveis, acima do teto {MAX_LEITURAS}: {vazn!r}")

    candidatos = []
    for combo in itertools.product(*opcoes):
        escansao, posicoes, pes_pos, pes_sil = [], [], [], []
        for leitura in combo:
            escansao += leitura["padrao_silabas"]
            posicoes += leitura["padrao_posicoes"]
            pes_pos.append(list(leitura["padrao_posicoes"]))
            pes_sil.append(list(leitura["padrao_silabas"]))
        candidatos.append({
            "escansao": escansao,
            "posicoes": posicoes,
            "padrao_pes": pes_pos,
            "padrao_pes_silabas": pes_sil,
            "romanizacao": " ".join(l["romanizacao"] for l in combo),
            "pes_persa": pes,
        })
    return candidatos, []


def resolver_vazn(vazn: str, arkan: dict | None = None,
                  publicados: dict | None = None) -> dict:
    """Resolve um vazn do Ganjoor em escansão conferida por fonte dupla.

    Devolve sempre um dict com 'status':

      'resolvido'      uma única leitura casa com a tabela publicada. A
                       escansão pode entrar no corpus, com metro_conferido.
      'pendente'       mais de uma leitura casa. UMA decisão humana por metro
                       resolve, e todos os poemas desse metro vêm com ela.
      'quarentena'     nenhuma leitura casa, ou um pé é desconhecido. Não
                       entra no corpus — o projeto não adivinha metro.

    Função pura.
    """
    arkan = arkan if arkan is not None else carregar_arkan()
    publicados = publicados if publicados is not None else carregar_publicados()
    _, nome_persa = partir_vazn(vazn)

    base = {"vazn": vazn.strip(), "nome_persa": nome_persa}
    try:
        candidatos, faltam = candidatos_do_vazn(vazn, arkan)
    except ValueError as e:
        return base | {"status": "quarentena", "motivo": str(e)}

    if faltam:
        return base | {"status": "quarentena",
                       "motivo": "pé fora da tabela de arkān: " + ", ".join(faltam),
                       "pes_desconhecidos": faltam}
    if not candidatos:
        return base | {"status": "quarentena", "motivo": "vazn sem nenhum pé legível"}

    casados = {}
    for c in candidatos:
        pp = _publicados_que_casam(c["posicoes"], publicados)
        if pp:
            casados["".join(c["posicoes"])] = (c, pp)

    if not casados:
        return base | {
            "status": "quarentena",
            "motivo": "nenhuma leitura casa com a tabela de metros publicados",
            "leituras_testadas": ["".join(c["posicoes"]) for c in candidatos],
        }
    if len(casados) > 1:
        return base | {
            "status": "pendente",
            "motivo": ("mais de uma leitura do vazn casa com a literatura; "
                       "a decisão é humana, uma por metro"),
            "leituras": [
                {"posicoes": k,
                 "escansao": c["escansao"],
                 "romanizacao": c["romanizacao"],
                 "publicados": [{"familia_arabe": p["familia_arabe"],
                                 "codigo_elwell_sutton": p["codigo_elwell_sutton"],
                                 "frequencia_no_corpus_persa": p["frequencia_no_corpus_persa"]}
                                for p in pp]}
                for k, (c, pp) in sorted(casados.items())],
        }

    cand, pub = next(iter(casados.values()))
    return base | {
        "status": "resolvido",
        "escansao": cand["escansao"],
        "posicoes": cand["posicoes"],
        "padrao_pes": cand["padrao_pes"],
        "romanizacao": cand["romanizacao"],
        "n_silabas": len(cand["escansao"]),
        "n_posicoes": len(cand["posicoes"]),
        "segmentacao_silabica": "posicional",
        "superlongas_conferidas": False,
        "_ressalva_segmentacao": (
            "O metro fixa as posições métricas, não onde duas posições se fundem "
            "numa sílaba superlonga — isso depende das palavras. A escansão vai "
            "com uma sílaba por posição; onde o verso real tiver superlonga, a "
            "duração total não muda, muda o agrupamento (uma nota de 1,5 em vez "
            "de duas de 1,0 e 0,5). Conferir exige o texto romanizado."),
        "publicados": [{"familia_arabe": p["familia_arabe"],
                        "codigo_elwell_sutton": p["codigo_elwell_sutton"],
                        "frequencia_no_corpus_persa": p["frequencia_no_corpus_persa"],
                        "casou_em": p["_casou_em"]} for p in pub],
    }


def _ascii(s: str) -> str:
    """Romanização crua para montar identificador: 'Mojtass' -> 'mojtass'."""
    s = unicodedata.normalize("NFD", s)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^A-Za-z0-9]+", "_", s).strip("_").lower()
    return s or "metro"


def id_do_metro(resolucao: dict) -> str:
    """Identificador estável do metro: família árabe + código Elwell-Sutton.

    'Mojtass' + '4.1.15' -> 'mojtass_4_1_15'. Vem da fonte, não de apelido
    nosso, e por isso dois poemas do mesmo metro caem no mesmo identificador.
    """
    if resolucao.get("status") != "resolvido":
        raise ValueError(f"metro não resolvido: {resolucao.get('status')}")
    p = resolucao["publicados"][0]
    cod = re.split(r"\s*=\s*", p["codigo_elwell_sutton"])[0]
    cod = re.sub(r"\(.*?\)", "", cod).strip()
    return f"{_ascii(p['familia_arabe'])}_{_ascii(cod)}"


def metro_para_corpus(resolucao: dict, fonte_url: str = "") -> dict:
    """Monta a entrada de 'metros' do corpus a partir de uma resolução.

    NÃO preenche 'assinatura_afetiva': essa é leitura do autor sobre o caráter
    do metro, não fato derivável da fonte. Fica ausente para ele escrever.
    """
    if resolucao.get("status") != "resolvido":
        raise ValueError(f"metro não resolvido: {resolucao.get('status')}")
    pes = resolucao["padrao_pes"]
    unico = all(p == pes[0] for p in pes)
    entrada = {
        "pe": resolucao["romanizacao"],
        "nome_persa": resolucao["nome_persa"],
        "vazn": resolucao["vazn"],
    }
    if unico:
        entrada["padrao_pe"] = pes[0]
    else:
        entrada["padrao_pes"] = pes
    pub = resolucao["publicados"][0]
    entrada["_fonte"] = {
        "vazn_registrado_em": fonte_url or "ganjoor.net",
        "padrao_publicado": {
            "familia_arabe": pub["familia_arabe"],
            "codigo_elwell_sutton": pub["codigo_elwell_sutton"],
            "frequencia_no_corpus_persa": pub["frequencia_no_corpus_persa"],
        },
        "conferencia": ("escansão derivada dos arkān do vazn (data/arkan.json) e "
                        "casada com data/metros_publicados.json — fonte dupla"),
    }
    return entrada


def _cli(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="Resolve um vazn do Ganjoor em escansão conferida por fonte dupla.")
    ap.add_argument("vazn", nargs="?", help="o vazn, ex.: 'مفتعلن مفاعلن مفتعلن مفاعلن'")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--listar-arkan", action="store_true")
    a = ap.parse_args(argv)

    arkan = carregar_arkan()
    if a.listar_arkan:
        print(f"{'pé':10s} {'romanização':14s} {'sílabas':12s} posições")
        for nome, e in arkan.items():
            if nome == "_meta":
                continue
            for l in leituras_do_pe(e):
                print(f"{nome:10s} {l['romanizacao']:14s} "
                      f"{''.join(l['padrao_silabas']):12s} {''.join(l['padrao_posicoes'])}")
        return 0
    if not a.vazn:
        ap.error("informe o vazn ou use --listar-arkan")

    r = resolver_vazn(a.vazn, arkan)
    if a.json:
        print(json.dumps(r, ensure_ascii=False, indent=1))
        return 0 if r["status"] == "resolvido" else 1

    print(f"vazn      : {r['vazn']}")
    print(f"nome persa: {r['nome_persa'] or '—'}")
    print(f"status    : {r['status'].upper()}")
    if r["status"] == "resolvido":
        print(f"romanização: {r['romanizacao']}")
        print(f"escansão   : {''.join(r['escansao'])}   ({r['n_silabas']} sílabas)")
        print(f"posições   : {''.join(r['posicoes'])}   ({r['n_posicoes']} posições)")
        print(f"id do metro: {id_do_metro(r)}")
        print(f"segmentação: {r['segmentacao_silabica']} "
              f"(superlongas conferidas: {r['superlongas_conferidas']})")
        for p in r["publicados"]:
            print(f"publicado  : {p['familia_arabe']} {p['codigo_elwell_sutton']} "
                  f"({p['frequencia_no_corpus_persa']} do corpus persa, casou em {p['casou_em']})")
    else:
        print(f"motivo     : {r['motivo']}")
        for l in r.get("leituras", []):
            print(f"  leitura {l['posicoes']}  {l['romanizacao']}")
        for l in r.get("leituras_testadas", []):
            print(f"  testada  {l}")
    return 0 if r["status"] == "resolvido" else 1


if __name__ == "__main__":
    import sys
    sys.exit(_cli(sys.argv[1:]))
