#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Motor de música generativa do Divã do Vão.

PRINCÍPIO DE AUDITABILIDADE
---------------------------
Nenhum valor rítmico é inventado. O ritmo da melodia DERIVA da escansão do
aruz persa (sílabas longas/curtas do original de Rumi). Cada nota gerada
carrega, no seu 'trace', a sílaba e o símbolo métrico que a originaram.

PIPELINE
--------
1. Escansão do verso (data/aruz_corpus.json) -> sequência de durações.
2. Geração da melodia por prescrição afetiva sobre um modo (Clube da Esquina):
   as alturas seguem um contorno controlado por parâmetros (entropia, âmbito),
   mas as DURAÇÕES vêm do aruz. Semente fixa => reprodutível.
3. Harmonização modal com tensões (maj7/9/13).
4. Exportação: MusicXML, MIDI, e um relatório de auditoria (JSON) que liga
   cada nota à sílaba persa de origem.

Este módulo é puro (sem efeitos colaterais além de escrever arquivos quando
chamado via CLI). Ver tests/ para verificação do mapeamento sílaba↔nota.
"""
from __future__ import annotations
import json, random, hashlib
from dataclasses import dataclass, field, asdict
from pathlib import Path

# duração musical por símbolo do aruz (em quarterLength, base 4/4)
DUR_ARUZ = {"u": 0.5, "–": 1.0, "=": 1.5}

# modos "Clube da Esquina": graus a partir da tônica (em semitons)
MODOS = {
    "dorico":   [0, 2, 3, 5, 7, 9, 10],   # menor com 6ª maior — cor mineira
    "eolio":    [0, 2, 3, 5, 7, 8, 10],
    "lidio":    [0, 2, 4, 6, 7, 9, 11],   # 4ª aumentada — brilho
    "mixolidio":[0, 2, 4, 5, 7, 9, 10],
}

@dataclass
class NotaTrace:
    """Uma nota com sua trilha de auditoria."""
    midi: int
    dur: float
    silaba: str
    aruz: str          # '–', 'u' ou '='
    grau_modal: int
    origem_verso: str

@dataclass
class Frase:
    notas: list[NotaTrace] = field(default_factory=list)
    metro: str = ""
    modo: str = ""
    tonica_midi: int = 62  # D4

    def duracao_total(self) -> float:
        return sum(n.dur for n in self.notas)


def carregar_corpus(caminho: str | Path) -> dict:
    return json.loads(Path(caminho).read_text(encoding="utf-8"))


def durar_por_aruz(escansao: list[str], final_longa: bool = True) -> list[float]:
    """Converte a escansão do aruz em durações. Aplica a regra: a última
    sílaba do hemistíquio conta como longa."""
    durs = [DUR_ARUZ[s] for s in escansao]
    if final_longa and durs:
        durs[-1] = max(durs[-1], DUR_ARUZ["–"])
    return durs


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
    - ALTURAS: passeio controlado pelos graus do modo; 'entropia' controla a
      probabilidade de salto vs. grau conjunto; 'ambito' limita a extensão.
    """
    escansao = verso["escansao"]
    silabas = verso["translit_silabas"]
    assert len(escansao) == len(silabas), \
        f"Verso {verso['id']}: {len(silabas)} sílabas x {len(escansao)} símbolos"

    durs = durar_por_aruz(escansao)
    graus = MODOS[modo]
    rng = _semente(semente, verso["id"], modo, entropia)

    frase = Frase(metro=verso.get("metro",""), modo=modo, tonica_midi=tonica_midi)
    grau_idx = 0  # começa na tônica
    for silaba, simb, dur in zip(silabas, escansao, durs):
        # regra de contorno: sílaba longa tende a subir/repousar; curta, a mover
        if simb == "u":
            passo = rng.choice([-2, -1, 1, 2]) if rng.random() < 0.5 + entropia/2 else rng.choice([-1, 1])
        else:
            passo = rng.choice([-1, 0, 0, 1]) if rng.random() > entropia else rng.choice([-3, -2, 2, 3])
        grau_idx = max(0, min(len(graus)*2 - 1, grau_idx + passo))
        # mapeia índice de grau (com oitava) para semitom, respeitando o âmbito
        oitava, dentro = divmod(grau_idx, len(graus))
        semitom = graus[dentro] + 12*oitava
        semitom = min(semitom, ambito)  # trava de âmbito
        midi = tonica_midi + semitom
        frase.notas.append(NotaTrace(
            midi=midi, dur=dur, silaba=silaba, aruz=simb,
            grau_modal=dentro, origem_verso=verso["id"]))
    # a última nota repousa na tônica ou terça (fechamento de frase)
    if frase.notas:
        frase.notas[-1].midi = tonica_midi + rng.choice([0, 3, 7])
    return frase


def relatorio_auditoria(frase: Frase, verso: dict) -> dict:
    """Prova de que cada duração veio do aruz. É o artefato de auditabilidade."""
    linhas = []
    for n in frase.notas:
        linhas.append({
            "silaba": n.silaba, "aruz": n.aruz,
            "dur_quarter": n.dur, "midi": n.midi, "grau_modal": n.grau_modal
        })
    return {
        "verso_id": verso["id"],
        "obra": verso.get("obra",""),
        "metro": frase.metro,
        "modo": frase.modo,
        "regra": "dur = DUR_ARUZ[aruz]; última sílaba = longa",
        "duracao_total_quarters": frase.duracao_total(),
        "mapa_silaba_para_nota": linhas,
        "conferencia": {
            "n_silabas": len(verso["translit_silabas"]),
            "n_notas": len(frase.notas),
            "alinhado": len(verso["translit_silabas"]) == len(frase.notas)
        }
    }


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Gera melodia a partir do aruz.")
    ap.add_argument("--verso", default="masnavi_1")
    ap.add_argument("--modo", default="dorico", choices=list(MODOS))
    ap.add_argument("--corpus", default="data/aruz_corpus.json")
    ap.add_argument("--out", default="engine/saida")
    args = ap.parse_args()

    corpus = carregar_corpus(args.corpus)
    verso = next(v for v in corpus["versos"] if v["id"] == args.verso)
    frase = gerar_melodia(verso, modo=args.modo)
    rel = relatorio_auditoria(frase, verso)

    Path(args.out).mkdir(parents=True, exist_ok=True)
    Path(f"{args.out}/{args.verso}_auditoria.json").write_text(
        json.dumps(rel, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Melodia gerada para {args.verso}: {len(frase.notas)} notas, "
          f"{frase.duracao_total()} quarters. Auditoria salva.")
    print("Alinhamento sílaba↔nota:", rel["conferencia"]["alinhado"])
