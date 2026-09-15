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
Motor de música generativa do Divã do Vão.

PRINCÍPIO DE AUDITABILIDADE
---------------------------
Nenhum valor rítmico é inventado. O ritmo da melodia DERIVA da escansão do
aruz persa (sílabas longas/curtas do original de Rumi). Cada nota gerada
carrega, no seu 'trace', a sílaba e o símbolo métrico que a originaram.

A auditoria cobre três camadas, de cima para baixo:

  1. METRO -> ESCANSÃO   conferir_metro() verifica que a escansão declarada no
     corpus realmente se decompõe nos pés do metro declarado (aceitando pé
     final truncado e anceps inicial). Sem isso, "o ritmo vem do aruz" seria
     uma afirmação sobre um aruz que ninguém conferiu.
  2. ESCANSÃO -> DURAÇÃO  durar_por_aruz(): dur = DUR_ARUZ[símbolo], com a
     regra de que a sílaba final do hemistíquio conta como longa.
  3. GRAU -> ALTURA       toda nota emitida satisfaz
     midi == tonica_midi + MODOS[modo][grau_modal] + 12*oitava.
     O passeio melódico é limitado em espaço de GRAU (não de semitom) e
     REFLETIDO nas bordas, e é isso que garante a igualdade acima: a altura
     nunca é recortada para um valor que não seja grau do modo.

PIPELINE
--------
1. Escansão do verso (data/aruz_corpus.json) -> sequência de durações.
2. Geração da melodia por prescrição afetiva sobre um modo (Clube da Esquina):
   as alturas seguem um contorno controlado por parâmetros (entropia, âmbito),
   mas as DURAÇÕES vêm do aruz. Semente fixa => reprodutível.
3. Operações rítmicas opcionais (engine/ritmo.py), que preservam dur_base.
4. Exportação (engine/export.py): MusicXML e MIDI só com a stdlib, sempre
   acompanhados do relatório de auditoria (JSON) que liga cada nota à sílaba
   persa de origem.

Este módulo é puro (sem efeitos colaterais além de escrever arquivos quando
chamado via CLI). Ver tests/ para verificação dos invariantes.
"""
from __future__ import annotations
import json, random, hashlib
from dataclasses import dataclass, field, replace
from pathlib import Path

# duração musical por símbolo do aruz (em quarterLength, base 4/4)
DUR_ARUZ = {"u": 0.5, "–": 1.0, "=": 1.5}

# símbolos que contam como longa para a regra do fim de hemistíquio
LONGAS = ("–", "=")

# modos "Clube da Esquina": graus a partir da tônica (em semitons)
MODOS = {
    "dorico":   [0, 2, 3, 5, 7, 9, 10],   # menor com 6ª maior — cor mineira
    "eolio":    [0, 2, 3, 5, 7, 8, 10],
    "lidio":    [0, 2, 4, 6, 7, 9, 11],   # 4ª aumentada — brilho
    "mixolidio":[0, 2, 4, 5, 7, 9, 10],
}

@dataclass
class NotaTrace:
    """Uma nota com sua trilha de auditoria.

    dur_base guarda a duração vinda do aruz ANTES de qualquer operação
    rítmica; dur é o valor final. Enquanto dur_base espelha DUR_ARUZ e as
    operações aplicadas ficam registradas em Frase.operacoes, a afirmação
    "nenhum valor rítmico é inventado" continua verificável.
    """
    midi: int
    dur: float
    silaba: str
    aruz: str          # '–', 'u' ou '='
    grau_modal: int    # índice em MODOS[modo]
    oitava: int        # quantas oitavas acima da tônica
    origem_verso: str
    dur_base: float = 0.0

    def __post_init__(self):
        if not self.dur_base:
            self.dur_base = self.dur

@dataclass
class Frase:
    notas: list[NotaTrace] = field(default_factory=list)
    metro: str = ""
    modo: str = ""
    tonica_midi: int = 62  # D4
    operacoes: list[str] = field(default_factory=list)
    anacruse: float = 0.0  # deslocamento da frase contra o tempo forte, em quarters

    def duracao_total(self) -> float:
        return sum(n.dur for n in self.notas)

    def copia(self) -> "Frase":
        """Cópia profunda — as operações rítmicas são puras e não mutam a
        frase que recebem."""
        return Frase(notas=[replace(n) for n in self.notas], metro=self.metro,
                     modo=self.modo, tonica_midi=self.tonica_midi,
                     operacoes=list(self.operacoes), anacruse=self.anacruse)


def carregar_corpus(caminho: str | Path) -> dict:
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


def durar_por_aruz(escansao: list[str], final_longa: bool = True) -> list[float]:
    """Converte a escansão do aruz em durações. Aplica a regra: a última
    sílaba do hemistíquio conta como longa."""
    durs = [DUR_ARUZ[s] for s in escansao]
    if final_longa and durs:
        durs[-1] = max(durs[-1], DUR_ARUZ["–"])
    return durs


# ---------------------------------------------------------------------------
# Camada 1 da auditoria: o metro declarado gera mesmo a escansão declarada?
# ---------------------------------------------------------------------------

# expansão de cada símbolo nas posições métricas que ele ocupa. A superlonga
# vale por duas — é a definição que o próprio corpus declara ("= longa+curta")
# — e sem expandir não há como casar uma escansão que a use contra o padrão do
# metro, porque símbolo e posição métrica deixam de ser a mesma coisa.
EXPANSAO = {"u": ["u"], "–": ["–"], "=": ["–", "u"]}


def expandir_escansao(escansao: list[str]) -> list[tuple[str, int]]:
    """Expande a escansão em posições métricas.

    Devolve [(símbolo_da_posição, índice_da_sílaba)], de modo que cada posição
    saiba de que sílaba veio — é isso que permite relatar a divergência
    apontando a sílaba, e não um número solto.
    """
    posicoes = []
    for i, simbolo in enumerate(escansao):
        if simbolo not in EXPANSAO:
            raise ValueError(f"símbolo de escansão desconhecido: {simbolo!r}")
        for p in EXPANSAO[simbolo]:
            posicoes.append((p, i))
    return posicoes


def _pes_do_metro(metro: dict, n_posicoes: int) -> list[tuple[list[str], int, int]]:
    """Fatia as posições métricas nos pés do metro, ciclando o padrão.

    `padrao_pes` (lista de pés) cobre os metros de pés alternados, como o rajaz
    mosamman matvi makhbun (mofta'elon mafā'elon, repetidos), em que um único
    pé repetido não descreve o verso. `padrao_pe` segue valendo para os metros
    de pé único já no corpus.
    """
    pes = metro.get("padrao_pes") or [metro.get("padrao_pe")]
    if not pes or not pes[0]:
        raise ValueError("metro sem 'padrao_pe' nem 'padrao_pes'")
    fatias, pos, i = [], 0, 0
    while pos < n_posicoes:
        pe = pes[i % len(pes)]
        fatias.append((pe, pos, min(pos + len(pe), n_posicoes)))
        pos += len(pe)
        i += 1
    return fatias


def conferir_metro(verso: dict, metros: dict) -> dict:
    """Decompõe a escansão do verso nos pés do metro declarado e relata as
    divergências.

    A escansão é primeiro expandida em posições métricas (ver
    expandir_escansao), porque a superlonga ocupa duas.

    Três licenças da prosódia persa são aceitas:

    - **pé final truncado** (mahzuf/catalético): o último pé pode ser mais
      curto que o padrão — é o que faz de `fāʿilātun fāʿilātun fāʿilun` o
      metro do Masnavi;
    - **anceps inicial**: a primeira posição do verso admite longa ou breve;
    - **fim de hemistíquio**: a última sílaba conta sempre como longa, regra
      que o próprio corpus declara.

    Devolve {metro, conforme, pes, divergencias, n_posicoes}. Função pura.
    """
    nome = verso.get("metro", "")
    metro = metros.get(nome)
    if metro is None:
        return {"metro": nome, "conforme": False, "pes": [], "n_posicoes": 0,
                "divergencias": [f"metro '{nome}' não declarado no corpus"]}

    silabas = verso.get("translit_silabas", [])
    posicoes = expandir_escansao(verso["escansao"])
    fatias = _pes_do_metro(metro, len(posicoes))
    pes, divergencias = [], []

    for n_pe, (padrao, ini, fim) in enumerate(fatias):
        trecho = posicoes[ini:fim]
        ultimo_pe = n_pe == len(fatias) - 1
        divs_pe = []
        for j, (simbolo, i_silaba) in enumerate(trecho):
            esperado = padrao[j]
            if simbolo == esperado:
                continue
            if n_pe == 0 and j == 0:
                continue                                   # anceps inicial
            if ultimo_pe and ini + j == len(posicoes) - 1 and (
                    simbolo in LONGAS or verso["escansao"][i_silaba] in LONGAS):
                continue                                   # fim de hemistíquio
            divs_pe.append({
                "posicao": j + 1,
                "silaba": silabas[i_silaba] if i_silaba < len(silabas) else "?",
                "encontrado": simbolo, "esperado": esperado})
        pes.append({
            "n": n_pe + 1,
            "escansao": "".join(s for s, _ in trecho),
            "esperado": "".join(padrao[:len(trecho)]),
            "silabas": [silabas[i] for i in dict.fromkeys(i for _, i in trecho)
                        if i < len(silabas)],
            "truncado": len(trecho) < len(padrao),
            "conforme": not divs_pe,
        })
        for d in divs_pe:
            divergencias.append(
                f"pé {n_pe + 1}, posição {d['posicao']} (sílaba '{d['silaba']}'): "
                f"encontrado '{d['encontrado']}', esperado '{d['esperado']}'")

    return {"metro": nome, "conforme": not divergencias, "pes": pes,
            "n_posicoes": len(posicoes), "divergencias": divergencias}


# ---------------------------------------------------------------------------
# Camada 3 da auditoria: limitar em espaço de GRAU e refletir nas bordas
# ---------------------------------------------------------------------------

def graus_no_ambito(graus: list[int], ambito: int) -> int:
    """Quantos índices de grau (contando oitavas) cabem dentro do âmbito.

    O índice i vale MODOS[modo][i % 7] + 12*(i // 7) semitons acima da
    tônica; a sequência é estritamente crescente, então basta subir até
    estourar o âmbito. Devolve a contagem: os índices válidos são 0..n-1.
    """
    n = 0
    while True:
        oitava, dentro = divmod(n, len(graus))
        if graus[dentro] + 12 * oitava > ambito:
            return n
        n += 1


def refletir(idx: int, teto: int) -> int:
    """Dobra o índice para dentro de [0, teto], espelhando nas bordas.

    Refletir em vez de travar (o velho `min`/`max`) tem duas consequências
    que importam para o projeto: o contorno não cria platôs de notas
    repetidas ao encostar na borda, e o resultado é sempre um grau legítimo
    do modo — o que mantém o relatório de auditoria capaz de explicar a
    altura emitida.
    """
    if teto <= 0:
        return 0
    span = 2 * teto
    idx %= span                      # Python: resultado não-negativo
    return idx if idx <= teto else span - idx


def _passear(grau_idx: int, passo: int, teto: int) -> int:
    """Aplica um passo ao índice de grau, refletindo nas bordas do âmbito.

    Detalhe que importa: a reflexão pura tem pontos fixos. Como a tônica fica
    no piso do âmbito (grau 0), um passo de -2 a partir do grau 1 reflete de
    volta para o grau 1 — e uma sequência de passos descendentes na borda
    produziria justamente o platô de notas repetidas que a reflexão existe
    para evitar. Quando isso acontece, o passo é espelhado (sobe o que ia
    descer), de modo que todo passo não-nulo realmente se mova. Assim as
    únicas notas repetidas que sobram são as intencionais: o passo 0 da regra
    de contorno, o repouso da sílaba longa.
    """
    novo = refletir(grau_idx + passo, teto)
    if passo and novo == grau_idx:
        novo = refletir(grau_idx - passo, teto)
    return novo


def _semente(*partes) -> random.Random:
    """RNG determinística a partir de uma semente textual — reprodutibilidade
    é requisito de auditabilidade."""
    h = hashlib.sha256("::".join(map(str, partes)).encode()).hexdigest()
    return random.Random(int(h[:16], 16))


def gerar_melodia(verso: dict, modo: str = "dorico", tonica_midi: int = 62,
                  entropia: float = 0.4, ambito: int = 9,
                  semente: str = "diva") -> Frase:
    """
    Gera a melodia de UM verso.
    - DURAÇÕES: 100% do aruz (auditável).
    - ALTURAS: passeio pelos graus do modo; 'entropia' controla a
      probabilidade de salto vs. grau conjunto; 'ambito' limita a extensão
      em semitons, cortando em espaço de grau (ver graus_no_ambito).

    Toda nota devolvida satisfaz
    midi == tonica_midi + MODOS[modo][grau_modal] + 12*oitava.
    """
    if modo not in MODOS:
        raise ValueError(f"modo desconhecido: {modo!r}; use um de {sorted(MODOS)}")
    escansao = verso["escansao"]
    silabas = verso["translit_silabas"]
    if len(escansao) != len(silabas):
        raise ValueError(
            f"Verso {verso['id']}: {len(silabas)} sílabas x {len(escansao)} símbolos")

    durs = durar_por_aruz(escansao)
    graus = MODOS[modo]
    teto = graus_no_ambito(graus, ambito) - 1
    if teto < 0:
        raise ValueError(f"âmbito {ambito} não acomoda nenhum grau de {modo}")
    rng = _semente(semente, verso["id"], modo, entropia)

    frase = Frase(metro=verso.get("metro",""), modo=modo, tonica_midi=tonica_midi)
    grau_idx = 0  # começa na tônica
    for silaba, simb, dur in zip(silabas, escansao, durs):
        # regra de contorno: sílaba longa tende a subir/repousar; curta, a mover
        if simb == "u":
            passo = rng.choice([-2, -1, 1, 2]) if rng.random() < 0.5 + entropia/2 else rng.choice([-1, 1])
        else:
            passo = rng.choice([-1, 0, 0, 1]) if rng.random() > entropia else rng.choice([-3, -2, 2, 3])
        grau_idx = _passear(grau_idx, passo, teto)
        oitava, dentro = divmod(grau_idx, len(graus))
        frase.notas.append(NotaTrace(
            midi=tonica_midi + graus[dentro] + 12*oitava, dur=dur,
            silaba=silaba, aruz=simb, grau_modal=dentro, oitava=oitava,
            origem_verso=verso["id"]))
    # a última nota repousa em tônica, terça ou quinta DO MODO (fechamento de
    # frase). Os graus saem de MODOS, e não de um intervalo fixo, senão o
    # repouso cairia fora do modo em lídio e mixolídio (terça maior).
    if frase.notas:
        fecho = min(rng.choice([0, 2, 4]), teto)
        ult = frase.notas[-1]
        ult.grau_modal, ult.oitava = fecho, 0
        ult.midi = tonica_midi + graus[fecho]
    return frase


def relatorio_auditoria(frase: Frase, verso: dict, metros: dict | None = None) -> dict:
    """Prova de que cada duração veio do aruz e cada altura, de um grau do
    modo. É o artefato de auditabilidade.

    Passando `metros`, o relatório inclui também a conferência metro↔escansão
    (camada 1), fechando a cadeia de cima a baixo.
    """
    linhas = []
    for n in frase.notas:
        linhas.append({
            "silaba": n.silaba, "aruz": n.aruz,
            "dur_base_quarter": n.dur_base, "dur_quarter": n.dur,
            "midi": n.midi, "grau_modal": n.grau_modal, "oitava": n.oitava
        })
    rel = {
        "verso_id": verso["id"],
        "obra": verso.get("obra",""),
        "metro": frase.metro,
        "modo": frase.modo,
        "tonica_midi": frase.tonica_midi,
        "regra_duracao": "dur_base = DUR_ARUZ[aruz]; última sílaba = longa",
        "regra_altura": "midi = tonica_midi + MODOS[modo][grau_modal] + 12*oitava",
        "operacoes_ritmicas": list(frase.operacoes),
        "duracao_total_quarters": frase.duracao_total(),
        "mapa_silaba_para_nota": linhas,
        "conferencia": {
            "n_silabas": len(verso["translit_silabas"]),
            "n_notas": len(frase.notas),
            "alinhado": len(verso["translit_silabas"]) == len(frase.notas),
            "metro_conferido": verso.get("metro_conferido"),
        }
    }
    # compatibilidade: o nome antigo do campo continua disponível
    rel["regra"] = rel["regra_duracao"]
    if metros is not None:
        rel["conferencia_metro"] = conferir_metro(verso, metros)
    return rel


if __name__ == "__main__":
    import argparse, sys
    # rodando como script, sys.path[0] é engine/; a raiz precisa entrar para
    # que os módulos irmãos (engine.ritmo, engine.export) sejam importáveis.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    ap = argparse.ArgumentParser(description="Gera melodia a partir do aruz.")
    ap.add_argument("--verso", default="masnavi_1")
    ap.add_argument("--modo", default="dorico", choices=list(MODOS))
    ap.add_argument("--corpus", default="data/aruz_corpus.json")
    ap.add_argument("--out", default="engine/saida")
    ap.add_argument("--tonica", type=int, default=62,
                    help="nota MIDI da tônica (62 = D4)")
    ap.add_argument("--ambito", type=int, default=9,
                    help="extensão máxima da melodia, em semitons acima da tônica")
    ap.add_argument("--entropia", type=float, default=0.4,
                    help="0 = grau conjunto, 1 = muitos saltos")
    ap.add_argument("--semente", default="diva")
    ap.add_argument("--export", default="",
                    help="formatos a exportar, separados por vírgula: musicxml,midi")
    ap.add_argument("--compasso", type=float, default=None,
                    help="compasso em quarterLength (3.5 = 7/8, 4.0 = 4/4). "
                         "Por padrão usa o que o pé do metro pede — o ramal "
                         "pede 3.5, e em 4/4 o pé desliza contra a barra")
    ap.add_argument("--complexidade", action="store_true",
                    help="mede complexidade, encaixe e compasso natural")
    ap.add_argument("--letra", default="",
                    help="letra em português, sílabas separadas por hífen, "
                         "para medir o ajuste prosódico contra o aruz")
    ap.add_argument("--operacao", default="", choices=["", "inversao", "aumentacao",
                                                      "diminuicao", "deslocamento"],
                    help="operação rítmica a aplicar (ver engine/ritmo.py)")
    args = ap.parse_args()

    corpus = carregar_corpus(args.corpus)
    verso = next(v for v in corpus["versos"] if v["id"] == args.verso)
    frase = gerar_melodia(verso, modo=args.modo, tonica_midi=args.tonica,
                          entropia=args.entropia, ambito=args.ambito,
                          semente=args.semente)
    if args.operacao:
        from engine.ritmo import OPERACOES
        frase = OPERACOES[args.operacao](frase)
    rel = relatorio_auditoria(frase, verso, corpus["metros"])

    # o compasso que o pé do metro pede, salvo escolha explícita
    from engine.complexidade import compasso_natural
    natural = compasso_natural(verso, corpus["metros"])
    compasso = args.compasso or natural.get("compasso_sugerido") or 4.0

    if args.complexidade or args.letra:
        from engine.complexidade import relatorio as relatorio_complexidade
        rel["complexidade"] = relatorio_complexidade(
            frase, verso, corpus["metros"], ambito=args.ambito,
            letra=args.letra or None, compasso=compasso)

    if args.export:
        from engine.export import escrever
        formatos = [f.strip() for f in args.export.split(",") if f.strip()]
        for alvo in escrever(frase, rel, args.out, args.verso, formatos,
                             titulo=verso.get("obra", args.verso),
                             compasso=compasso):
            print("escrito:", alvo)
    else:
        Path(args.out).mkdir(parents=True, exist_ok=True)
        Path(f"{args.out}/{args.verso}_auditoria.json").write_text(
            json.dumps(rel, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Melodia gerada para {args.verso}: {len(frase.notas)} notas, "
          f"{frase.duracao_total()} quarters. Auditoria salva.")
    if frase.operacoes:
        print("Operações rítmicas:", ", ".join(frase.operacoes))
    print("Alinhamento sílaba↔nota:", rel["conferencia"]["alinhado"])
    cm = rel["conferencia_metro"]
    print(f"Metro {cm['metro']} confere com a escansão:", cm["conforme"])
    for d in cm["divergencias"]:
        print("  divergência:", d)
    from engine.export import assinatura_de_compasso
    batidas, figura = assinatura_de_compasso(compasso)
    print(f"Compasso: {batidas}/{figura} ({compasso} quarters)"
          + (f" — o pé do metro pede {natural['compasso_sugerido']}"
             if natural.get("compasso_sugerido") else ""))

    if "complexidade" in rel:
        cx = rel["complexidade"]
        d = cx["decomposicao"]
        print(f"\nCOMPLEXIDADE")
        print(f"  de Rumi : {d['bits_de_rumi']:7.2f} bits   "
              f"({d['fracao_da_fonte']*100:.1f}% da canção)")
        print(f"  do acaso: {d['bits_de_acaso']:7.2f} bits   "
              f"({d['melodias_no_espaco']:,} melodias neste espaço)")
        print(f"  {d['aviso']}")
        m = cx["metricas_mir"]
        print(f"  entropia de altura {m['entropia_de_altura']} · "
              f"consistência modal {m['consistencia_modal']} · "
              f"groove {m['consistencia_de_groove']}")
        mc = cx["melhor_compasso"]
        print(f"  groove por compasso: {mc['escores']} → melhor {mc['melhor']}")
        print(f"\nENCAIXE (o que ordena candidatas)")
        for nome, bloco in cx["encaixe"].items():
            if bloco.get("aplicavel") is False:
                print(f"  {nome}: não aplicável — {bloco.get('motivo', '')}")
                continue
            valor = bloco.get("cantabilidade", bloco.get("aderencia",
                                                          bloco.get("ajuste")))
            print(f"  {nome}: {valor}   (ordena {bloco['ordena']})")
            for choque in bloco.get("choques", []):
                print(f"     choque: tônica '{choque['silaba']}' em sílaba "
                      f"curta do aruz (dur {choque['dur']})")
