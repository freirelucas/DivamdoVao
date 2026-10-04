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
Colhedor do corpus — do Ganjoor para data/, em lote, com mínimo esforço humano.

POR QUE ISTO VIVE FORA DE engine/
---------------------------------
engine/ é offline e determinístico: mesma entrada, mesma saída, sempre. A rede
não é nada disso. Misturar as duas coisas faria o corpus mudar sozinho e
quebraria a reprodutibilidade que o projeto promete. Então a rede fica aqui, e
o que ela produz é um ARQUIVO, conferido e versionado, que o motor lê offline.

O ESFORÇO HUMANO, MEDIDO
------------------------
O humano não escande verso. O humano não confere poema. O humano decide, no
máximo, UM metro — e todos os poemas daquele metro herdam a decisão. Tudo o
mais é derivado de fonte publicada e conferido por fonte dupla em
engine/metrica.py: o vazn do Ganjoor dá os pés, a tabela de Elwell-Sutton
confirma o padrão, e o que não casar vai para quarentena nomeando o motivo.

POLIDEZ
-------
O robots.txt do Ganjoor (04/10/2026) bloqueia /User/, /Admin/ e as páginas de
login; páginas de poema são liberadas. Mesmo assim: cache em disco para nunca
pedir duas vezes a mesma página, espera entre pedidos, um pedido por vez, e
User-Agent que diz quem somos e para quê. Colher é pedir um favor a um acervo
mantido por voluntários.

LIMITE CONHECIDO
----------------
Medido contra o inventário completo do Ganjoor (212 fórmulas de vazn, o select
'v' de ganjoor.net/simi): só 18,4% das FÓRMULAS resolvem, porque a tabela
publicada que serve de segunda fonte traz 32 padrões — os frequentes. Mas a
cobertura por POEMA é muito maior, porque Rumi usa justamente os frequentes:
numa amostra aleatória de 70 gazais do Divã de Shams, 95,6% dos poemas
resolveram. Os dois números são verdadeiros e medem coisas diferentes. O
relatório da colheita imprime o segundo, que é o que decide se há corpus.
"""
from __future__ import annotations

import html as _html
import json
import re
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from engine.metrica import (  # noqa: E402
    carregar_arkan, carregar_publicados, id_do_metro, metro_para_corpus,
    resolver_vazn)

BASE = "https://ganjoor.net"
CACHE_PADRAO = RAIZ / ".cache_ganjoor"
AGENTE = ("DivaDoVao/0.1 (projeto de co-producao musical a partir do aruz persa; "
          "colhe metro e texto de dominio publico; contato pelo repositorio)")
ESPERA_PADRAO = 1.5        # segundos entre pedidos de rede
TENTATIVAS = 4             # com recuo exponencial 2s, 4s, 8s


# As ressalvas valem para TODO verso colhido, então vivem no cabeçalho do
# arquivo e cada verso aponta para elas por chave. Repeti-las em cada verso
# gastava 2,35 MB dos 5,21 MB de uma colheita de 150 gazais e deixava o arquivo
# ilegível para revisão — e o que importa é que a ressalva esteja escrita e
# ligada ao verso, não que esteja copiada.
PENDENCIAS_HUMANAS = {
 "translit_silabas": (
   "O Ganjoor não publica transliteração silabada. Sem ela, o rastro de auditoria "
   "rotula POSIÇÃO métrica ('·1', '·2'), não sílaba, e o relatório declara "
   "silabas_conferidas: false. Inventar sílaba aqui seria o erro nº 3 do registro "
   "em engine/filtros.py."),
 "superlongas": (
   "O metro fixa as posições métricas, não onde duas posições se fundem numa "
   "sílaba superlonga — isso depende das palavras. A duração total não muda; muda "
   "o agrupamento (uma nota de 1,5 em vez de duas de 1,0 e 0,5). Conferir exige o "
   "texto romanizado."),
 "glosa_e_imagem": (
   "glosa_pt e imagem são leitura do autor sobre o verso, não deriváveis da fonte. "
   "Ficam ausentes de propósito."),
}

EDICAO = (
 "Texto conforme a edição que o Ganjoor publica, que NÃO é a de todo verso do "
 "corpus feito à mão: a abertura do Masnavi aparece no Ganjoor como "
 "بشنو این نی چون شکایت e nos versos masnavi_1/masnavi_2 como بشنو از نی چون حکایت, "
 "a leitura de Nicholson. As duas são edições legítimas e escandem igual "
 "(–u–––u–––u–); a variante fica registrada, não harmonizada à força.")


# ---------------------------------------------------------------------------
# rede, com cache e polidez
# ---------------------------------------------------------------------------

def _nome_de_cache(url: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", url.replace(BASE, "")).strip("_")[:180] + ".html"


def pegar(url: str, cache: Path | None = None, espera: float = ESPERA_PADRAO,
          _estado: dict = {"ultimo": 0.0}) -> str:
    """Busca uma página, servindo do cache quando já foi buscada.

    O cache não é otimização: é o que permite rodar a ingestão de novo, mexer
    na tabela de pés e remedir, sem pedir nada ao servidor outra vez.
    """
    cache = Path(cache) if cache is not None else CACHE_PADRAO
    cache.mkdir(parents=True, exist_ok=True)
    arq = cache / _nome_de_cache(url)
    if arq.exists():
        return arq.read_text(encoding="utf-8")

    erro = None
    for tentativa in range(TENTATIVAS):
        espere = espera - (time.time() - _estado["ultimo"])
        if espere > 0:
            time.sleep(espere)
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": AGENTE, "Accept": "text/html,application/xhtml+xml"})
            with urllib.request.urlopen(req, timeout=60) as r:
                texto = r.read().decode("utf-8", "replace")
            _estado["ultimo"] = time.time()
            arq.write_text(texto, encoding="utf-8")
            return texto
        except (urllib.error.URLError, OSError) as e:
            _estado["ultimo"] = time.time()
            erro = e
            if tentativa < TENTATIVAS - 1:
                time.sleep(2 ** (tentativa + 1))
    raise RuntimeError(f"não consegui buscar {url}: {erro}")


# ---------------------------------------------------------------------------
# extração
# ---------------------------------------------------------------------------

def _texto(bruto: str) -> str:
    t = _html.unescape(re.sub(r"<[^>]+>", " ", bruto))
    t = t.replace("‌", "‌")                # ZWNJ é ortográfico, fica
    t = re.sub(r"[ \t ]+", " ", t)
    return unicodedata.normalize("NFC", t).strip()


def extrair_vazn(pagina: str) -> str:
    """Lê o vazn que o Ganjoor registra para o poema."""
    m = re.search(r"<td>\s*وزن:\s*</td>\s*<td>\s*<a[^>]*>(.*?)</a>", pagina, re.S)
    return _texto(m.group(1)) if m else ""


def extrair_coplas(pagina: str) -> list[dict]:
    """Extrai as coplas (beyt) e seus hemistíquios (mesraʿ).

    Cada hemistíquio é um verso para o projeto: o código Elwell-Sutton conta
    posições POR HEMISTÍQUIO, e é com um hemistíquio que o corpus já trabalha
    (masnavi_1 tem as 11 posições do Ramal 2.4.11).
    """
    # Não se casa div aninhado com regex: divide-se a página nos limites das
    # coplas e extrai-se os hemistíquios de cada pedaço.
    coplas = []
    partes = re.split(r'<div class="b2?"(?=[\s>])', pagina)[1:]
    for i, parte in enumerate(partes, 1):
        rotulo = re.match(r'[^>]*id="(bn\d+)"', parte)
        hemis = []
        for m in re.finditer(r'<div class="m([12])"[^>]*>(.*?)</div>', parte, re.S):
            texto = _texto(m.group(2))
            if texto:
                hemis.append(texto)
            if m.group(1) == "2":
                break                    # fim desta copla
        if hemis:
            coplas.append({"n": rotulo.group(1) if rotulo else f"b{i}",
                           "hemistiquios": hemis[:2]})
    return coplas


def extrair_poema(pagina: str, url: str) -> dict:
    """Tudo o que uma página de poema oferece ao projeto."""
    # o <title> traz a trilha inteira, que é a melhor procedência disponível:
    # "گنجور » مولانا » دیوان شمس » غزلیات » غزل شمارهٔ ۳۲۳". Tira-se só o nome
    # do site, que não é obra.
    tit = re.search(r"<title>(.*?)</title>", pagina, re.S)
    titulo = _texto(tit.group(1)) if tit else ""
    titulo = re.sub(r"^\s*گنجور\s*»\s*", "", titulo).strip()
    return {"url": url, "titulo": titulo,
            "vazn": extrair_vazn(pagina), "coplas": extrair_coplas(pagina)}


def listar_por_metro(vazn: str, autor: int = 5, paginas: int = 1,
                     cache: Path | None = None) -> list[str]:
    """Caminhos dos poemas que compartilham um metro, pelo índice /simi/.

    É este índice que torna o lote grande e barato: um vazn resolvido uma vez
    serve todos os poemas que ele lista. `autor` é o id do Ganjoor — 5 é
    مولانا (Rumi).
    """
    achados: list[str] = []
    for pag in range(1, paginas + 1):
        q = urllib.parse.urlencode({"v": vazn, "a": autor, "page": pag})
        pagina = pegar(f"{BASE}/simi/?{q}", cache)
        caminhos = [u for u in re.findall(r'href="(/[^"]+)"', pagina)
                    if re.search(r"/(sh|m|p)\d+$", u)]
        novos = [u for u in dict.fromkeys(caminhos) if u not in achados]
        if not novos:
            break
        achados += novos
    return achados


# ---------------------------------------------------------------------------
# ingestão
# ---------------------------------------------------------------------------

def _id_do_verso(url: str, n_copla: str, i_hemi: int) -> str:
    cauda = "_".join(p for p in url.strip("/").split("/")[-3:] if p)
    cauda = re.sub(r"[^A-Za-z0-9]+", "_", cauda).strip("_")
    return f"{cauda}_{n_copla}_m{i_hemi + 1}"


def versos_do_poema(poema: dict, resolucao: dict, id_metro: str) -> list[dict]:
    """Transforma um poema resolvido nas entradas de 'versos' do corpus.

    Cada hemistíquio vira um verso, com a escansão derivada do metro. NÃO
    inventa transliteração silabada, nem glosa, nem imagem: esses campos são
    trabalho humano, e o motor já sabe trabalhar sem eles
    (generative.silabas_do_verso).
    """
    versos = []
    for copla in poema["coplas"]:
        for i, hemi in enumerate(copla["hemistiquios"]):
            versos.append({
                "id": _id_do_verso(poema["url"], copla["n"], i),
                "obra": poema["titulo"] or poema["url"],
                "metro": id_metro,
                "persa": hemi,
                "escansao": list(resolucao["escansao"]),
                "dominio_publico": True,
                "metro_conferido": True,
                "_origem": {
                    "url": poema["url"],
                    "copla": copla["n"],
                    "hemistiquio": i + 1,
                    "vazn_registrado": resolucao["vazn"],
                    "colhido_por": "ferramentas/colher.py",
                    "edicao": "ver _edicao no cabeçalho do arquivo",
                },
                "_pendencias_humanas": sorted(PENDENCIAS_HUMANAS),
            })
    return versos


def colher(urls: list[str], cache: Path | None = None,
           espera: float = ESPERA_PADRAO) -> dict:
    """Colhe uma lista de poemas e separa o que entra do que fica em quarentena.

    Devolve {metros, versos, quarentena, relatorio}. Função com rede, mas sem
    efeito em disco além do cache — quem grava é gravar().
    """
    arkan, pub = carregar_arkan(), carregar_publicados()
    metros: dict[str, dict] = {}
    versos: list[dict] = []
    quarentena: list[dict] = []
    por_metro: dict[str, int] = {}
    pendentes: list[dict] = []

    for u in urls:
        url = u if u.startswith("http") else BASE + u
        try:
            poema = extrair_poema(pegar(url, cache, espera), url)
        except RuntimeError as e:
            quarentena.append({"url": url, "status": "rede", "motivo": str(e)})
            continue
        if not poema["vazn"]:
            quarentena.append({"url": url, "status": "sem_vazn",
                               "motivo": "o Ganjoor não registra vazn para este poema"})
            continue
        if not poema["coplas"]:
            quarentena.append({"url": url, "status": "sem_texto",
                               "motivo": "não extraí hemistíquios da página"})
            continue

        r = resolver_vazn(poema["vazn"], arkan, pub)
        if r["status"] != "resolvido":
            registro = {"url": url, "status": r["status"], "vazn": poema["vazn"],
                        "motivo": r.get("motivo", ""),
                        "n_coplas": len(poema["coplas"])}
            if r["status"] == "pendente":
                registro["leituras"] = r["leituras"]
                pendentes.append(registro)
            quarentena.append(registro)
            continue

        mid = id_do_metro(r)
        metros.setdefault(mid, metro_para_corpus(r, url))
        novos = versos_do_poema(poema, r, mid)
        versos += novos
        por_metro[mid] = por_metro.get(mid, 0) + len(novos)

    pedidos = len(urls)
    ok = pedidos - len(quarentena)
    return {
        "metros": metros, "versos": versos, "quarentena": quarentena,
        "relatorio": {
            "poemas_pedidos": pedidos,
            "poemas_ingeridos": ok,
            "poemas_em_quarentena": len(quarentena),
            "cobertura_por_poema": round(100 * ok / pedidos, 1) if pedidos else 0.0,
            "metros_distintos": len(metros),
            "versos_ingeridos": len(versos),
            "versos_por_metro": por_metro,
            "decisoes_humanas_pendentes": len(pendentes),
            "motivos_de_quarentena": _contar(q["status"] for q in quarentena),
        },
    }


def _contar(it) -> dict:
    d: dict[str, int] = {}
    for x in it:
        d[x] = d.get(x, 0) + 1
    return d


def gravar(colheita: dict, destino: Path, nome: str = "corpus_colhido") -> list[Path]:
    """Grava a colheita e a quarentena, prontas para conferência e versionamento."""
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    corpus = {
        "_sobre": ("Corpus colhido em lote do Ganjoor. O ritmo de cada verso deriva do "
                   "vazn PUBLICADO para o poema, conferido por fonte dupla (ver "
                   "engine/metrica.py). Nenhuma escansão foi feita à mão aqui, e "
                   "nenhuma sílaba foi inventada: sem transliteração, o rastro de "
                   "auditoria rotula posição métrica."),
        "_colhido_por": "ferramentas/colher.py",
        "_relatorio_da_colheita": colheita["relatorio"],
        "_pendencias_humanas": PENDENCIAS_HUMANAS,
        "_sobre_pendencias": (
            "Cada verso lista em _pendencias_humanas as CHAVES que se aplicam a ele; "
            "o texto de cada uma está aqui. Nada disso impede o motor de rodar; tudo "
            "isso muda o que o projeto pode AFIRMAR sobre o verso."),
        "_edicao": EDICAO,
        "metros": colheita["metros"],
        "versos": colheita["versos"],
    }
    escritos = []
    for arq, dados in ((destino / f"{nome}.json", corpus),
                       (destino / f"{nome}_quarentena.json",
                        {"_sobre": ("O que NÃO entrou no corpus, e por quê. Esta lista é "
                                    "o mapa do que falta para ampliar a cobertura: cada "
                                    "entrada nomeia o pé ou o padrão ausente."),
                         "itens": colheita["quarentena"]})):
        arq.write_text(json.dumps(dados, ensure_ascii=False, indent=1) + "\n",
                       encoding="utf-8")
        escritos.append(arq)
    return escritos


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _cli(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="Colhe corpus do Ganjoor em lote, com conferência de fonte dupla.",
        epilog="Exemplos:\n"
               "  %(prog)s --faixa /moulavi/shams/ghazalsh/sh 1 40\n"
               "  %(prog)s --metro 'مفتعلن مفاعلن مفتعلن مفاعلن (رجز مثمن مطوی مخبون)' --paginas 2\n"
               "  %(prog)s --url /moulavi/shams/ghazalsh/sh323 --seco",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--faixa", nargs=3, metavar=("PREFIXO", "DE", "ATE"),
                    help="colhe PREFIXO+n para n de DE a ATE")
    ap.add_argument("--metro", help="colhe pelo índice /simi/ os poemas deste vazn")
    ap.add_argument("--url", action="append", default=[], help="colhe um poema (repetível)")
    ap.add_argument("--autor", type=int, default=5, help="id do autor no Ganjoor (5 = Rumi)")
    ap.add_argument("--paginas", type=int, default=1, help="páginas do índice /simi/")
    ap.add_argument("--limite", type=int, default=0, help="teto de poemas a colher")
    ap.add_argument("--espera", type=float, default=ESPERA_PADRAO,
                    help="segundos entre pedidos de rede")
    ap.add_argument("--cache", default=str(CACHE_PADRAO))
    ap.add_argument("--destino", default=str(RAIZ / "data"))
    ap.add_argument("--nome", default="corpus_colhido")
    ap.add_argument("--seco", action="store_true", help="não grava, só relata")
    a = ap.parse_args(argv)

    urls: list[str] = list(a.url)
    if a.faixa:
        pref, de, ate = a.faixa[0], int(a.faixa[1]), int(a.faixa[2])
        urls += [f"{pref}{n}" for n in range(de, ate + 1)]
    if a.metro:
        urls += listar_por_metro(a.metro, a.autor, a.paginas, Path(a.cache))
    urls = list(dict.fromkeys(urls))
    if a.limite:
        urls = urls[:a.limite]
    if not urls:
        ap.error("nada a colher: use --faixa, --metro ou --url")

    print(f"colhendo {len(urls)} poemas (espera {a.espera}s, cache {a.cache})…")
    c = colher(urls, Path(a.cache), a.espera)
    r = c["relatorio"]
    print(f"\n  poemas pedidos      : {r['poemas_pedidos']}")
    print(f"  ingeridos           : {r['poemas_ingeridos']}  ({r['cobertura_por_poema']}%)")
    print(f"  em quarentena       : {r['poemas_em_quarentena']}  {r['motivos_de_quarentena']}")
    print(f"  metros distintos    : {r['metros_distintos']}")
    print(f"  versos ingeridos    : {r['versos_ingeridos']}")
    print(f"  decisões humanas    : {r['decisoes_humanas_pendentes']}")
    if r["versos_por_metro"]:
        print("\n  versos por metro:")
        for mid, n in sorted(r["versos_por_metro"].items(), key=lambda kv: -kv[1]):
            pub = c["metros"][mid]["_fonte"]["padrao_publicado"]
            print(f"    {n:5d}  {mid:18s} {pub['familia_arabe']} "
                  f"{pub['codigo_elwell_sutton']} ({pub['frequencia_no_corpus_persa']})")
    if c["quarentena"]:
        print("\n  quarentena (o mapa do que falta):")
        vistos = set()
        for q in c["quarentena"]:
            chave = (q.get("vazn", ""), q["status"])
            if chave in vistos:
                continue
            vistos.add(chave)
            print(f"    [{q['status']}] {q.get('vazn','')[:46]}  — {q.get('motivo','')[:60]}")
    if not a.seco:
        for p in gravar(c, Path(a.destino), a.nome):
            print(f"\ngravado: {p.relative_to(RAIZ)}")
    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
