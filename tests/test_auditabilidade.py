#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Testes da garantia de auditabilidade do motor generativo."""
import sys, json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.generative import (carregar_corpus, gerar_melodia,
                               relatorio_auditoria, durar_por_aruz, DUR_ARUZ)

CORPUS = carregar_corpus(Path(__file__).resolve().parents[1] / "data/aruz_corpus.json")

def _verso(vid):
    return next(v for v in CORPUS["versos"] if v["id"] == vid)

def test_duracao_deriva_do_aruz():
    """Cada duração é exatamente a tabela do aruz (exceto a final, regra da longa)."""
    v = _verso("masnavi_1")
    durs = durar_por_aruz(v["escansao"])
    for simb, d, i in zip(v["escansao"], durs, range(len(durs))):
        if i < len(durs)-1:
            assert d == DUR_ARUZ[simb], f"duração {d} != aruz {simb}"
    assert durs[-1] >= DUR_ARUZ["–"], "última sílaba deve ser longa"

def test_alinhamento_silaba_nota():
    """Toda sílaba gera exatamente uma nota (sem melisma escondido)."""
    for v in CORPUS["versos"]:
        frase = gerar_melodia(v)
        assert len(frase.notas) == len(v["translit_silabas"]), \
            f"{v['id']}: {len(frase.notas)} notas x {len(v['translit_silabas'])} sílabas"

def test_reprodutibilidade():
    """Mesma semente => mesma melodia (requisito de auditoria)."""
    v = _verso("masnavi_1")
    a = gerar_melodia(v, semente="x")
    b = gerar_melodia(v, semente="x")
    assert [n.midi for n in a.notas] == [n.midi for n in b.notas]

def test_trace_completo():
    """Toda nota carrega sua sílaba e símbolo métrico de origem."""
    v = _verso("masnavi_1")
    frase = gerar_melodia(v)
    for n in frase.notas:
        assert n.silaba and n.aruz in DUR_ARUZ and n.origem_verso == v["id"]

def test_relatorio_confere():
    v = _verso("divan_2214")
    rel = relatorio_auditoria(gerar_melodia(v), v)
    assert rel["conferencia"]["alinhado"] is True

if __name__ == "__main__":
    import traceback
    testes = [f for name, f in sorted(globals().items()) if name.startswith("test_")]
    ok = 0
    for t in testes:
        try:
            t(); print(f"PASS {t.__name__}"); ok += 1
        except Exception:
            print(f"FAIL {t.__name__}"); traceback.print_exc()
    print(f"\n{ok}/{len(testes)} testes passaram.")
    sys.exit(0 if ok == len(testes) else 1)
