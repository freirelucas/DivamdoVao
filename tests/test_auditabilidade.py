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
"""Testes da garantia de auditabilidade do motor generativo.

Cada teste trava um invariante da cadeia que o projeto promete:

    metro -> escansão -> duração -> [operações] -> partitura
                      \\-> grau do modo -> altura

Os cinco primeiros são os testes originais. Os demais foram acrescentados
junto com as correções que eles verificam — vários falhariam no estado
anterior, e é isso que os torna úteis.
"""
import json, subprocess, sys, tempfile, urllib.error, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

RAIZ = Path(__file__).resolve().parents[1]

from engine.generative import (carregar_corpus, gerar_melodia, conferir_metro,
                               relatorio_auditoria, durar_por_aruz,
                               graus_no_ambito, refletir, _passear,
                               DUR_ARUZ, MODOS)
from engine import ritmo
from engine.export import barrar, figuras, para_musicxml, para_midi, DIVISOES

CORPUS = carregar_corpus(RAIZ / "data/aruz_corpus.json")
TONICA = 62

def _verso(vid):
    return next(v for v in CORPUS["versos"] if v["id"] == vid)

def _todas_as_frases():
    """Todo verso x todo modo — o espaço em que os invariantes devem valer."""
    for modo in MODOS:
        for v in CORPUS["versos"]:
            yield modo, v, gerar_melodia(v, modo=modo)


# --------------------------------------------------------------------------
# Os cinco originais
# --------------------------------------------------------------------------

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


# --------------------------------------------------------------------------
# Altura: o relatório tem de explicar a nota que ele publica
# --------------------------------------------------------------------------

def test_altura_auditavel():
    """Toda nota satisfaz midi = tônica + graus[grau_modal] + 12*oitava.

    Antes da correção, o grau_modal era gravado antes da trava de âmbito e a
    última nota era sobrescrita sem atualizar o trace: 6 das 11 notas de
    eolio/masnavi_2 publicavam um grau que não reconstruía o MIDI emitido.
    """
    for modo, v, frase in _todas_as_frases():
        graus = MODOS[modo]
        for n in frase.notas:
            esperado = TONICA + graus[n.grau_modal] + 12 * n.oitava
            assert n.midi == esperado, (
                f"{v['id']}/{modo} sílaba {n.silaba}: midi {n.midi} mas o trace "
                f"(grau {n.grau_modal}, oitava {n.oitava}) implica {esperado}")

def test_toda_nota_dentro_do_modo():
    """Nenhuma altura emitida cai fora do modo declarado, a última inclusive.

    Antes: 8 de 144 notas saíam fora — a trava de âmbito cortava em espaço de
    semitom, e o fecho de frase usava terça menor fixa mesmo em modo maior.
    """
    for modo, v, frase in _todas_as_frases():
        classes = {(TONICA + g) % 12 for g in MODOS[modo]}
        fora = [n.midi for n in frase.notas if n.midi % 12 not in classes]
        assert not fora, f"{v['id']}/{modo}: notas fora do modo: {fora}"

def test_fecho_de_frase_e_modal():
    """A frase repousa em tônica, terça ou quinta DO MODO."""
    for modo, v, frase in _todas_as_frases():
        graus = MODOS[modo]
        repousos = {graus[0], graus[2], graus[4]}
        intervalo = frase.notas[-1].midi - TONICA
        assert intervalo in repousos, (
            f"{v['id']}/{modo}: fecho em {intervalo} semitons, "
            f"fora dos repousos do modo {sorted(repousos)}")

def test_ambito_respeitado():
    """Nenhuma nota ultrapassa o âmbito pedido, em qualquer modo."""
    for ambito in (5, 9, 14, 24):
        for modo in MODOS:
            for v in CORPUS["versos"]:
                frase = gerar_melodia(v, modo=modo, ambito=ambito)
                for n in frase.notas:
                    assert 0 <= n.midi - TONICA <= ambito, (
                        f"{v['id']}/{modo}: {n.midi - TONICA} semitons "
                        f"fora do âmbito {ambito}")

def test_passo_nao_nulo_sempre_move():
    """Um passo não-nulo nunca deixa a melodia parada.

    A reflexão pura tem pontos fixos (um passo -2 a partir do grau 1 volta ao
    grau 1, porque a tônica fica no piso do âmbito), o que reproduziria o
    platô de notas repetidas que a reflexão existe para evitar. _passear
    espelha o passo nesse caso. Só restam travas quando o passo é maior que o
    âmbito inteiro (teto <= 2), o que exige um âmbito degenerado de ~3
    semitons; com o padrão de 9, todo modo dá teto 5.
    """
    for teto in range(3, 12):
        for grau in range(teto + 1):
            for passo in (-3, -2, -1, 1, 2, 3):
                assert _passear(grau, passo, teto) != grau, (
                    f"passo {passo:+d} a partir do grau {grau} (teto {teto}) "
                    "não moveu")

def test_refletir_fica_no_intervalo():
    """A reflexão nunca devolve índice fora de [0, teto]."""
    for teto in range(0, 12):
        for idx in range(-40, 41):
            assert 0 <= refletir(idx, teto) <= max(teto, 0)

def test_graus_no_ambito():
    """A contagem de graus cabíveis bate com a conta direta."""
    for modo, graus in MODOS.items():
        for ambito in range(0, 30):
            n = graus_no_ambito(graus, ambito)
            for i in range(n):
                oitava, dentro = divmod(i, len(graus))
                assert graus[dentro] + 12*oitava <= ambito
            oitava, dentro = divmod(n, len(graus))
            assert graus[dentro] + 12*oitava > ambito


# --------------------------------------------------------------------------
# Metro: a camada acima do aruz
# --------------------------------------------------------------------------

def test_metro_confere_com_escansao():
    """Todo verso marcado metro_conferido: true passa na conferência — e todo
    verso que não passa está explicitamente marcado como false.

    É o que mantém a divergência de divan_2214 visível sem deixar a suíte
    vermelha, e o que faz um verso novo mal escaneado quebrar o build.
    """
    for v in CORPUS["versos"]:
        r = conferir_metro(v, CORPUS["metros"])
        marcado = v.get("metro_conferido")
        assert marcado is not None, \
            f"{v['id']}: falta declarar metro_conferido"
        if marcado:
            assert r["conforme"], \
                f"{v['id']} marcado como conferido mas diverge: {r['divergencias']}"
        else:
            assert not r["conforme"], (
                f"{v['id']} está marcado metro_conferido: false mas confere — "
                "atualize o corpus em vez de deixar a marca desatualizada")
            assert r["divergencias"], f"{v['id']}: sem divergência registrada"

def test_masnavi_e_ramal_mahzuf():
    """Os dois hemistíquios do Masnavi são ramal mosaddas mahzuf:
    fāʿilātun fāʿilātun fāʿilun, ou seja –u–– –u–– –u–."""
    for vid in ("masnavi_1", "masnavi_2"):
        r = conferir_metro(_verso(vid), CORPUS["metros"])
        assert r["conforme"], r["divergencias"]
        assert [p["escansao"] for p in r["pes"]] == ["–u––", "–u––", "–u–"], \
            f"{vid}: pés {[p['escansao'] for p in r['pes']]}"
        assert r["pes"][-1]["truncado"], "o último pé do mahzuf é truncado"

def test_metro_desconhecido_nao_explode():
    """Um metro não declarado vira divergência, não exceção."""
    r = conferir_metro({"metro": "inventado", "escansao": ["–", "u"]},
                       CORPUS["metros"])
    assert r["conforme"] is False and r["divergencias"]


# --------------------------------------------------------------------------
# Operações rítmicas: o rastro sobrevive à transformação
# --------------------------------------------------------------------------

def test_operacoes_preservam_dur_base():
    """Depois de qualquer operação, dur_base ainda é a duração do aruz."""
    v = _verso("masnavi_1")
    base = gerar_melodia(v, modo="dorico")
    casos = {
        "inversao": ritmo.inversao_metrica(base),
        "aumentacao": ritmo.aumentacao(base, 2),
        "diminuicao": ritmo.diminuicao(base, 2),
        "deslocamento": ritmo.deslocamento(base, 0.5),
        "cadeia": ritmo.aumentacao(ritmo.inversao_metrica(base), 2),
    }
    esperado = durar_por_aruz(v["escansao"])
    for nome, frase in casos.items():
        r = ritmo.conferir_rastro(frase)
        assert r["rastro_intacto"], f"{nome}: {r['divergencias']}"
        assert [n.dur_base for n in frase.notas] == esperado, nome
        assert frase.operacoes, f"{nome}: operação não registrada"

def test_operacoes_sao_puras():
    """Nenhuma operação muta a frase que recebe."""
    v = _verso("masnavi_1")
    base = gerar_melodia(v, modo="dorico")
    antes = [(n.midi, n.dur) for n in base.notas]
    for op in (ritmo.inversao_metrica, ritmo.aumentacao, ritmo.diminuicao,
               ritmo.deslocamento):
        op(base)
    assert [(n.midi, n.dur) for n in base.notas] == antes
    assert base.operacoes == [] and base.anacruse == 0.0

def test_inversao_e_involutiva():
    """Inverter duas vezes devolve a escansão original — inclusive a
    superlonga, que é o seu próprio espelho."""
    for v in CORPUS["versos"]:
        e = v["escansao"]
        assert ritmo.inverter_escansao(ritmo.inverter_escansao(e)) == e
    assert ritmo.inverter_escansao(["=", "u", "–"]) == ["=", "–", "u"]

def test_inversao_nao_mexe_nas_alturas():
    """A inversão é rítmica: as alturas ficam onde estavam."""
    base = gerar_melodia(_verso("masnavi_1"), modo="lidio")
    inv = ritmo.inversao_metrica(base)
    assert [n.midi for n in inv.notas] == [n.midi for n in base.notas]

def test_aumentacao_escala_o_total():
    base = gerar_melodia(_verso("masnavi_1"))
    assert ritmo.aumentacao(base, 2).duracao_total() == 2 * base.duracao_total()
    assert ritmo.diminuicao(base, 2).duracao_total() == base.duracao_total() / 2

def test_fator_invalido_recusado():
    base = gerar_melodia(_verso("masnavi_1"))
    for fator in (0, -1):
        try:
            ritmo.aumentacao(base, fator)
        except ValueError:
            pass
        else:
            raise AssertionError(f"fator {fator} deveria ter sido recusado")


# --------------------------------------------------------------------------
# Exportação
# --------------------------------------------------------------------------

def test_figuras_somam_a_duracao():
    """A decomposição em figuras de notação preserva a duração."""
    for dur in (0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 2.5, 3.5, 9.5, 12.0):
        partes = figuras(dur)
        assert abs(sum(partes) - dur) < 1e-9, f"{dur} -> {partes}"

def test_barrar_preenche_compassos():
    """Todo compasso fica exatamente cheio, com ou sem anacruse."""
    for anacruse in (0.0, 0.5, 0.75):
        for modo in MODOS:
            for v in CORPUS["versos"]:
                frase = gerar_melodia(v, modo=modo)
                for i, comp in enumerate(barrar(frase.notas, 4.0, anacruse), 1):
                    soma = sum(e.dur for e in comp)
                    assert abs(soma - 4.0) < 1e-9, \
                        f"{v['id']}/{modo} anacruse {anacruse}: compasso {i} soma {soma}"

def test_barrar_liga_o_que_atravessa_a_barra():
    """Nota partida na barra vira ligadura, e a soma das partes é a original."""
    frase = gerar_melodia(_verso("masnavi_1"), modo="dorico")
    eventos = [e for comp in barrar(frase.notas, 4.0) for e in comp]
    soma_notas = sum(e.dur for e in eventos if not e.pausa)
    assert abs(soma_notas - frase.duracao_total()) < 1e-9
    assert any(e.tie_inicio for e in eventos), "masnavi_1 atravessa a barra em 4/4"
    for a, b in zip(eventos, eventos[1:]):
        if a.tie_inicio:
            assert b.tie_fim and b.midi == a.midi, "ligadura sem par"

def test_musicxml_round_trip():
    """Reler o MusicXML devolve as mesmas notas, durações e sílabas."""
    passos = {"C":0,"D":2,"E":4,"F":5,"G":7,"A":9,"B":11}
    for modo in MODOS:
        for v in CORPUS["versos"]:
            frase = gerar_melodia(v, modo=modo)
            raiz = ET.fromstring(para_musicxml(frase, v["obra"]))
            notas = [n for n in raiz.iter("note") if n.find("rest") is None]
            inicios = [n for n in notas
                       if not any(t.get("type") == "stop" for t in n.findall("tie"))]
            assert len(inicios) == len(frase.notas), f"{v['id']}/{modo}"
            soma = sum(int(n.findtext("duration")) for n in notas) / DIVISOES
            assert abs(soma - frase.duracao_total()) < 1e-9
            alturas, silabas = [], []
            for n in inicios:
                p = n.find("pitch")
                alturas.append((int(p.findtext("octave")) + 1) * 12
                               + passos[p.findtext("step")]
                               + int(p.findtext("alter") or 0))
                silabas.append(n.findtext("lyric/text"))
            assert alturas == [n.midi for n in frase.notas], f"{v['id']}/{modo}"
            assert silabas == [n.silaba for n in frase.notas], f"{v['id']}/{modo}"

def test_midi_round_trip():
    """O SMF gerado tem cabeçalho válido, pares note-on/off e a duração certa."""
    def vlq(b, i):
        n = 0
        while True:
            n = (n << 7) | (b[i] & 0x7F); mais = b[i] & 0x80; i += 1
            if not mais:
                return n, i
    for modo in MODOS:
        frase = gerar_melodia(_verso("masnavi_1"), modo=modo)
        dados = para_midi(frase)
        assert dados[:4] == b"MThd" and dados[14:18] == b"MTrk"
        tam = int.from_bytes(dados[18:22], "big")
        corpo = dados[22:22 + tam]
        assert len(corpo) == tam, "tamanho da trilha não bate"
        i = t = ons = offs = fim = 0
        while i < len(corpo):
            d, i = vlq(corpo, i); t += d
            st = corpo[i]
            if st == 0xFF:
                meta = corpo[i+1]; i += 2; ln, i = vlq(corpo, i); i += ln
                if meta == 0x2F:
                    break
            else:
                ons += st == 0x90; offs += st == 0x80
                if st == 0x80:
                    fim = t
                i += 3
        assert ons == offs == len(frase.notas), modo
        assert abs(fim / DIVISOES - frase.duracao_total()) < 1e-9, modo

def test_export_recusa_duracao_impossivel():
    """Duração sem figura exata falha alto em vez de virar partitura errada."""
    try:
        figuras(0.07)
    except ValueError:
        pass
    else:
        raise AssertionError("0.07 deveria ter sido recusada")

def test_letra_com_contagem_errada_recusada():
    """Exportar letra que não casa 1:1 com as notas é recusado."""
    frase = gerar_melodia(_verso("masnavi_1"))
    try:
        para_musicxml(frase, "t", letra=["uma", "duas"])
    except ValueError:
        pass
    else:
        raise AssertionError("letra de 2 sílabas para 11 notas deveria falhar")


# --------------------------------------------------------------------------
# API: entrada inválida responde, não derruba a conexão
# --------------------------------------------------------------------------

def _pedir(porta, caminho, dados=None, cru=None):
    url = f"http://127.0.0.1:{porta}{caminho}"
    corpo = cru if cru is not None else (
        json.dumps(dados).encode() if dados is not None else None)
    req = urllib.request.Request(url, data=corpo, method="POST" if corpo else "GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")

def test_api_responde_a_entrada_invalida():
    """Antes, modo inexistente, entropia não numérica e JSON malformado
    matavam a thread do handler e o cliente não recebia resposta nenhuma."""
    porta = 8977
    srv = subprocess.Popen([sys.executable, "app/server.py", str(porta)],
                           cwd=RAIZ, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        for _ in range(50):
            try:
                if _pedir(porta, "/api/corpus")[0] == 200:
                    break
            except Exception:
                pass
            import time; time.sleep(0.1)
        else:
            raise AssertionError("servidor não subiu")

        ok, _ = _pedir(porta, "/api/gerar", {"verso_id": "masnavi_1"})
        assert ok == 200

        casos = [
            ("modo inválido",      {"verso_id": "masnavi_1", "modo": "frigio"}, None),
            ("entropia não numérica", {"verso_id": "masnavi_1", "entropia": "abc"}, None),
            ("verso inexistente",  {"verso_id": "nao_existe"}, None),
            ("entropia fora da faixa", {"verso_id": "masnavi_1", "entropia": 5}, None),
            ("âmbito degenerado",  {"verso_id": "masnavi_1", "ambito": 0}, None),
            ("operação inválida",  {"verso_id": "masnavi_1", "operacao": "xyz"}, None),
            ("JSON malformado",    None, b"{nope"),
            ("corpo não-objeto",   None, b"[1,2,3]"),
            ("corpo grande demais", None, b'{"x":"' + b"a" * 70000 + b'"}'),
        ]
        for nome, dados, cru in casos:
            status, corpo = _pedir(porta, "/api/gerar", dados, cru)
            assert status == 400, f"{nome}: esperava 400, veio {status}"
            assert corpo.get("erro"), f"{nome}: resposta sem campo 'erro'"

        assert _pedir(porta, "/api/nada")[0] == 404
    finally:
        srv.terminate(); srv.wait(timeout=10)

def test_api_expoe_a_cadeia_de_auditoria():
    """A resposta traz o que a interface precisa para mostrar a procedência."""
    porta = 8978
    srv = subprocess.Popen([sys.executable, "app/server.py", str(porta)],
                           cwd=RAIZ, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    try:
        for _ in range(50):
            try:
                if _pedir(porta, "/api/corpus")[0] == 200:
                    break
            except Exception:
                pass
            import time; time.sleep(0.1)
        status, corpo = _pedir(porta, "/api/corpus")
        assert status == 200
        for v in corpo["versos"]:
            assert "metro_conferido" in v and "conferencia_metro" in v

        status, d = _pedir(porta, "/api/gerar",
                           {"verso_id": "masnavi_1", "operacao": "inversao"})
        assert status == 200
        assert d["operacoes"] == ["inversao_metrica"]
        assert d["rastro"]["rastro_intacto"] is True
        assert d["auditoria"]["regra_altura"]
        assert d["auditoria"]["conferencia_metro"]["conforme"] is True
        for n in d["notas"]:
            assert {"dur", "dur_base", "grau_modal", "oitava"} <= set(n)
    finally:
        srv.terminate(); srv.wait(timeout=10)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def test_cli_exporta_com_auditoria():
    """A CLI escreve partitura, MIDI e o relatório — nunca partitura sozinha."""
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run(
            [sys.executable, "engine/generative.py", "--verso", "masnavi_1",
             "--modo", "lidio", "--export", "musicxml,midi", "--out", tmp],
            cwd=RAIZ, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        for nome in ("masnavi_1.musicxml", "masnavi_1.mid",
                     "masnavi_1_auditoria.json"):
            assert (Path(tmp) / nome).exists(), f"faltou {nome}"
        rel = json.loads((Path(tmp) / "masnavi_1_auditoria.json").read_text("utf-8"))
        assert rel["regra_altura"] and rel["conferencia_metro"]["conforme"]


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
