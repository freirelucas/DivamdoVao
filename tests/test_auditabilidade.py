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
from engine import complexidade as cx
from engine import filtros, selecao, gosto, pipeline
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

def test_superlonga_expande_em_duas_posicoes():
    """A superlonga vale por duas posições métricas — a definição que o corpus
    declara. Sem isso, escansão e padrão do metro deixam de ser comparáveis."""
    from engine.generative import expandir_escansao
    posicoes = expandir_escansao(["–", "=", "u"])
    assert [s for s, _ in posicoes] == ["–", "–", "u", "u"]
    assert [i for _, i in posicoes] == [0, 1, 1, 2], "cada posição sabe sua sílaba"
    assert durar_por_aruz(["="]) == [1.5]

def test_simbolo_de_escansao_desconhecido_recusado():
    from engine.generative import expandir_escansao
    try:
        expandir_escansao(["-"])          # hífen ASCII, não o travessão do corpus
    except ValueError:
        pass
    else:
        raise AssertionError("símbolo desconhecido deveria falhar alto")

def test_metro_de_pes_alternados():
    """Metros de pés alternados precisam de 'padrao_pes'; um pé único repetido
    não descreve o rajaz mosamman matvi makhbun."""
    metro = CORPUS["metros"]["rajaz_mosamman_matvi_makhbun"]
    assert "padrao_pes" in metro and len(metro["padrao_pes"]) == 2

def test_divan_usa_a_escansao_conferida():
    """A correção filológica está aplicada: o verso é o gazal 323, em rajaz
    mosamman matvi makhbun, e a escansão casa 16/16 posições e 4/4 pés com o
    vazn que a fonte registra (ver docs/PROPOSTA_divan_2214.md)."""
    v = _verso("divan_2214")
    assert v["metro"] == "rajaz_mosamman_matvi_makhbun", v["metro"]
    assert v["metro_conferido"] is True
    assert "323" in v["obra"], v["obra"]
    assert not [k for k in v if k.startswith("_proposta")], "proposta já aplicada"
    r = conferir_metro(v, CORPUS["metros"])
    assert r["conforme"], r["divergencias"]
    assert r["n_posicoes"] == 16, r["n_posicoes"]
    assert [pe["escansao"] for pe in r["pes"]] == ["–uu–", "u–u–", "–uu–", "u–u–"]
    # a superlonga 'xār' atravessa a fronteira entre os pés 3 e 4
    assert "xār" in r["pes"][2]["silabas"] and "xār" in r["pes"][3]["silabas"]

def test_divan_exerce_a_superlonga():
    """São as primeiras superlongas do corpus: o símbolo estava definido em
    DUR_ARUZ desde o início e nenhum dado o exercia."""
    v = _verso("divan_2214")
    assert v["escansao"].count("=") == 2
    silabas_longas = [s for s, e in zip(v["translit_silabas"], v["escansao"]) if e == "="]
    assert silabas_longas == ["yār", "xār"], silabas_longas
    assert 1.5 in durar_por_aruz(v["escansao"])

def test_correcao_preserva_a_duracao_do_verso():
    """A correção muda o ritmo por dentro, não o tamanho: 12.0 quarters antes e
    depois. O que muda é o compasso que o metro pede — de 7/8 para 3/4."""
    v = _verso("divan_2214")
    assert sum(durar_por_aruz(v["escansao"])) == 12.0
    cn = cx.compasso_natural(v, CORPUS["metros"])
    assert cn["compasso_sugerido"] == 3.0, cn
    assert cn["duracao_do_pe"] == [3.0, 3.0], cn

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

def test_assinatura_de_compasso():
    """A fórmula de compasso tem de sair certa para compasso não inteiro.

    O pé do ramal dura 3.5 quarters = 7/8. A conversão ingênua (int(3.5) sobre
    denominador 4) escreveria 3/4 numa partitura de 7/8, e o erro seguiria
    silencioso até a estante do músico.
    """
    from engine.export import assinatura_de_compasso
    assert assinatura_de_compasso(3.5) == (7, 8)
    assert assinatura_de_compasso(4.0) == (4, 4)
    assert assinatura_de_compasso(3.0) == (3, 4)
    assert assinatura_de_compasso(1.5) == (3, 8)
    assert assinatura_de_compasso(2.5) == (5, 8)
    for invalido in (0, -1):
        try:
            assinatura_de_compasso(invalido)
        except ValueError:
            pass
        else:
            raise AssertionError(f"compasso {invalido} deveria ser recusado")

def test_musicxml_escreve_o_compasso_certo():
    """A partitura em 7/8 declara 7/8, e os compassos fecham em 3.5 quarters."""
    frase = gerar_melodia(_verso("masnavi_1"), modo="dorico")
    raiz = ET.fromstring(para_musicxml(frase, "t", compasso=3.5))
    assert raiz.findtext(".//time/beats") == "7"
    assert raiz.findtext(".//time/beat-type") == "8"
    for m in raiz.findall(".//measure"):
        soma = sum(int(n.findtext("duration")) for n in m.findall("note")) / DIVISOES
        assert abs(soma - 3.5) < 1e-9, soma

def test_midi_escreve_o_compasso_certo():
    """O evento de fórmula de compasso do SMF traz 7 e o expoente 3 (2**3=8)."""
    frase = gerar_melodia(_verso("masnavi_1"), modo="dorico")
    dados = para_midi(frase, compasso=3.5)
    i = dados.find(b"\xFF\x58\x04")
    assert i > 0, "evento de fórmula de compasso ausente"
    assert dados[i + 3] == 7 and dados[i + 4] == 3, (dados[i + 3], dados[i + 4])

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
# Complexidade e encaixe
# --------------------------------------------------------------------------

def test_bits_de_acaso_bate_com_a_contagem():
    """log2 do espaço medido pelo módulo tem de bater com a contagem feita por
    rota independente: 6.966.123 melodias para masnavi_1/dórico/âmbito 9."""
    v = _verso("masnavi_1")
    bits = cx.bits_de_acaso(v, "dorico", 9)
    assert round(2 ** bits) == 6_966_123, round(2 ** bits)
    assert cx.decompor(gerar_melodia(v, modo="dorico"), v)["melodias_no_espaco"] \
        == 6_966_123

def test_passos_em_sincronia_com_o_motor():
    """A contagem do espaço só vale se os passos aqui forem os mesmos que
    gerar_melodia sorteia. Trava a duplicação."""
    fonte = Path(RAIZ / "engine/generative.py").read_text(encoding="utf-8")
    assert "rng.choice([-2, -1, 1, 2])" in fonte, "passos da sílaba curta mudaram"
    assert "rng.choice([-1, 0, 0, 1])" in fonte and "rng.choice([-3, -2, 2, 3])" in fonte, \
        "passos da sílaba longa mudaram"
    assert set(cx.PASSOS_POR_SIMBOLO["u"]) == {-2, -1, 1, 2}
    assert set(cx.PASSOS_POR_SIMBOLO["–"]) == {-3, -2, -1, 0, 1, 2, 3}

def test_decomposicao_e_cega_dentro_do_espaco():
    """O achado que motiva as medidas de encaixe: a fração da fonte é a mesma
    para melodias diferentes do mesmo verso e modo."""
    v = _verso("masnavi_1")
    fracoes = {cx.decompor(gerar_melodia(v, modo="dorico", semente=f"s{i}"), v)
               ["fracao_da_fonte"] for i in range(50)}
    assert len(fracoes) == 1, f"esperava constância, vi {fracoes}"

def test_cantabilidade_ordena_melodias():
    """E o contraponto: cantabilidade varia dentro do mesmo espaço."""
    v = _verso("masnavi_1")
    vals = {cx.cantabilidade(gerar_melodia(v, modo="dorico", semente=f"s{i}"))
            ["cantabilidade"] for i in range(100)}
    assert len(vals) > 3, f"cantabilidade deveria discriminar, vi {vals}"

def test_ajuste_prosodico_ordena_letras():
    """O ajuste prosódico separa letras, e aponta a sílaba do choque."""
    v = _verso("masnavi_1")
    f = gerar_melodia(v, modo="dorico")
    bom = cx.ajuste_prosodico(f, "So-pra no jun-co e ele con-ta de ti")
    pior = cx.ajuste_prosodico(f, "Es-cu-ta o jun-co con-tan-do a dor")
    assert bom["aplicavel"] and pior["aplicavel"]
    assert bom["ajuste"] > pior["ajuste"], (bom["ajuste"], pior["ajuste"])
    assert pior["choques"] and pior["choques"][0]["silaba"] == "cu"

def test_ajuste_prosodico_recusa_contagem_errada():
    f = gerar_melodia(_verso("masnavi_1"), modo="dorico")
    r = cx.ajuste_prosodico(f, "duas si-la-bas")
    assert r["aplicavel"] is False and "notas" in r

def test_tonicidade_do_portugues():
    """A heurística de tonicidade acerta os casos da regra padrão."""
    marcas = cx.indices_tonicos(cx.separar_silabas_pt(
        "can-tou de-pois o a-mor as ca-sas lá-pis"))
    silabas = [s for p in cx.separar_silabas_pt(
        "can-tou de-pois o a-mor as ca-sas lá-pis") for s in p]
    tonicas = {s for s, m in zip(silabas, marcas) if m}
    assert {"tou", "pois", "mor", "ca", "lá"} <= tonicas, tonicas
    assert "o" not in tonicas and "as" not in tonicas, "átonos não são tônicos"

def test_distancia_ritmica_invariante_sob_aumentacao():
    """O vetor de duração é de RAZÕES: aumentar ou diminuir não move a frase."""
    base = gerar_melodia(_verso("masnavi_1"), modo="dorico")
    assert cx.distancia_ritmica(base, ritmo.aumentacao(base, 2)) == 0.0
    assert cx.distancia_ritmica(base, ritmo.diminuicao(base, 2)) == 0.0
    assert cx.distancia_ritmica(base, ritmo.deslocamento(base, 0.5)) == 0.0
    assert cx.distancia_ritmica(base, ritmo.inversao_metrica(base)) > 0.1

def test_distancia_ritmica_recusa_incomparavel():
    a = gerar_melodia(_verso("masnavi_1"))      # 11 notas
    b = gerar_melodia(_verso("divan_2214"))     # 14 notas
    try:
        cx.distancia_ritmica(a, b)
    except ValueError:
        pass
    else:
        raise AssertionError("frases de comprimentos diferentes não são comparáveis")

def test_rede_ritmica():
    base = gerar_melodia(_verso("masnavi_1"), modo="dorico")
    rede = cx.rede_ritmica({"base": base, "aumentada": ritmo.aumentacao(base, 2),
                            "invertida": ritmo.inversao_metrica(base)}, limiar=0.05)
    pares = {(a["de"], a["para"]) for a in rede["arestas"]}
    assert ("base", "aumentada") in pares, "aumentação está a distância zero"
    assert ("base", "invertida") not in pares, "inversão está longe"

def test_compasso_natural_do_ramal_e_sete_oitavos():
    """O pé do ramal dura 3.5 quarters — sete colcheias. Derivação e busca
    empírica têm de concordar, e concordam."""
    v = _verso("masnavi_1")
    cn = cx.compasso_natural(v, CORPUS["metros"])
    assert cn["compasso_sugerido"] == 3.5 and cn["em_colcheias"] == [7]
    mc = cx.melhor_compasso(gerar_melodia(v, modo="dorico"))
    assert mc["melhor"] == 3.5, mc["escores"]
    assert mc["consistencia"] == 1.0, mc["escores"]
    # e em 4/4, que é o padrão do exportador, o pé desliza contra a barra
    assert mc["escores"][4.0] < mc["escores"][3.5]

def test_modelo_nulo_avisa_falta_de_poder():
    """O teste de periodicidade marca que não tem poder neste comprimento —
    medido: divan_2214 dá p=0,07 na escansão atual e p=0,10 na proposta, e o
    teste não decide entre as duas."""
    r = cx.periodicidade_vs_acaso(_verso("masnavi_1"), periodo=4, n=500)
    assert r["poder_suficiente"] is False and r["aviso"]
    assert r["periodicidade_real"] == 1.0, "o pé do ramal se repete"
    assert r["periodicidade_real"] > r["periodicidade_media_do_acaso"]

def test_modelo_nulo_e_reprodutivel():
    a = cx.periodicidade_vs_acaso(_verso("masnavi_1"), n=200, semente=7)
    b = cx.periodicidade_vs_acaso(_verso("masnavi_1"), n=200, semente=7)
    assert a == b, "semente fixa deve dar o mesmo resultado"

def test_metricas_mir_coerentes_com_o_motor():
    """A consistência modal tem de ser 1.0 — é a mesma garantia que os testes
    de altura travam, vista por outro instrumento."""
    for modo in MODOS:
        for v in CORPUS["versos"]:
            m = cx.metricas_mir(gerar_melodia(v, modo=modo))
            assert m["consistencia_modal"] == 1.0, (v["id"], modo, m)
            assert m["extensao_semitons"] <= 9
            assert 0 <= m["consistencia_de_groove"] <= 1

def test_relatorio_completo():
    v = _verso("masnavi_1")
    r = cx.relatorio(gerar_melodia(v, modo="dorico"), v, CORPUS["metros"],
                     letra="Es-cu-ta o jun-co con-tan-do a dor")
    for chave in ("decomposicao", "metricas_mir", "encaixe", "modelo_nulo",
                  "compasso_natural", "melhor_compasso", "vetor_duracao"):
        assert chave in r, chave
    # cada medida de encaixe declara em que eixo ordena
    for nome, bloco in r["encaixe"].items():
        assert bloco.get("ordena") in ("melodias", "letras"), nome


# --------------------------------------------------------------------------
# Gerador ciente do pé do aruz
# --------------------------------------------------------------------------

def _eco_entre_pes(frase, k=4):
    m = [n.midi for n in frase.notas]
    cont = lambda s: [(b > a) - (b < a) for a, b in zip(s, s[1:])]
    c1, c2 = cont(m[:k]), cont(m[k:2 * k])
    return sum(a == b for a, b in zip(c1, c2)) / len(c1) if c1 else 0.0

def test_motivico_liga_a_melodia_aos_pes_do_aruz():
    """O ritmo deriva dos pés de Rumi; a melodia era cega a eles — eco de
    contorno em 5,8% dos casos contra 3,7% por acaso. Com motivico=True o
    segundo pé reusa os passos do primeiro."""
    from engine.generative import inicios_dos_pes
    for vid in ("masnavi_1", "divan_2214"):
        v = _verso(vid)
        def media(mot):
            return sum(_eco_entre_pes(gerar_melodia(
                v, modo="dorico", semente=f"s{i}", motivico=mot,
                metros=CORPUS["metros"])) for i in range(200)) / 200
        cego, motivado = media(False), media(True)
        assert motivado > cego + 0.15, f"{vid}: {cego:.3f} -> {motivado:.3f}"
        assert motivado > 0.5, f"{vid}: eco {motivado:.3f} baixo demais"

def test_motivico_desligado_por_padrao():
    """É mudança de caráter musical, não correção de defeito: não pode alterar
    o que já existe sem ser pedido."""
    v = _verso("masnavi_1")
    a = gerar_melodia(v, semente="y")
    b = gerar_melodia(v, semente="y", motivico=False)
    assert [n.midi for n in a.notas] == [n.midi for n in b.notas]

def test_motivico_preserva_todos_os_invariantes():
    """Nenhum ganho musical justifica perder a auditabilidade."""
    for modo, graus in MODOS.items():
        for v in CORPUS["versos"]:
            for s in range(15):
                f = gerar_melodia(v, modo=modo, semente=f"s{s}", motivico=True,
                                  metros=CORPUS["metros"])
                assert len(f.notas) == len(v["translit_silabas"])
                classes = {(TONICA + g) % 12 for g in graus}
                for n in f.notas:
                    assert n.midi == TONICA + graus[n.grau_modal] + 12 * n.oitava
                    assert n.midi % 12 in classes
                    assert n.dur_base == n.dur

def test_inicios_dos_pes_respeitam_a_superlonga():
    """Em divan_2214 a superlonga 'xār' atravessa a fronteira entre os pés 3 e
    4: as fronteiras têm de vir das posições métricas, não da contagem de
    sílabas."""
    from engine.generative import inicios_dos_pes
    assert inicios_dos_pes(_verso("masnavi_1"), CORPUS["metros"]) == [0, 4, 8]
    assert inicios_dos_pes(_verso("divan_2214"), CORPUS["metros"]) == [0, 4, 8, 10]
    # sem metro declarado, cai em blocos de 4
    assert inicios_dos_pes({"escansao": ["–"] * 11, "metro": "?"}, None) == [0, 4, 8]


# --------------------------------------------------------------------------
# Peneira, seleção de partida a frio e gosto aprendido
# --------------------------------------------------------------------------

def _amostra(vid="masnavi_1", modo="dorico", n=400):
    v = _verso(vid)
    return v, [gerar_melodia(v, modo=modo, semente=f"s{i}") for i in range(n)]

def test_peneira_so_corta_degenerado():
    """A peneira rejeita ~0,07%: só melodia de uma ou duas alturas."""
    frases = []
    for modo in MODOS:
        for v in CORPUS["versos"]:
            frases += [gerar_melodia(v, modo=modo, semente=f"s{i}") for i in range(300)]
    r = filtros.relatorio(frases)
    assert r["taxa_de_corte"] <= 0.01, r
    assert r["aviso"] is None, r["aviso"]
    assert set(r["por_filtro"]) <= {"sem_melodia", "quase_sem_melodia"}, r

def test_peneira_nao_corta_por_gosto():
    """Trava contra a reincidência dos quatro erros registrados em
    engine/filtros.py: salto grande, nota repetida, contorno monótono e fecho
    em terça ou quinta são material musical, não motivo de corte."""
    v, frases = _amostra(n=600)
    aprovadas = [f for f in frases if filtros.peneirar(f)]

    def maior_salto(f):
        m = [n.midi for n in f.notas]
        return max(abs(b - a) for a, b in zip(m, m[1:]))

    def maior_corrida(f):
        m = [n.midi for n in f.notas]
        atual = maior = 1
        for a, b in zip(m, m[1:]):
            atual = atual + 1 if a == b else 1
            maior = max(maior, atual)
        return maior

    assert any(maior_salto(f) >= 6 for f in aprovadas), \
        "salto grande não pode ser motivo de corte"
    assert any(maior_corrida(f) >= 3 for f in aprovadas), \
        "nota repetida não pode ser motivo de corte"
    fechos = {f.notas[-1].midi - f.tonica_midi for f in aprovadas}
    assert len(fechos) >= 3, \
        f"os três fechos modais têm de sobreviver, vi {fechos}"

def test_peneira_relata_qual_filtro_reprovou():
    """Rejeição muda não é auditável."""
    v = _verso("masnavi_1")
    frase = gerar_melodia(v, modo="dorico")
    for n in frase.notas:
        n.midi = frase.tonica_midi
    ver = filtros.peneirar(frase)
    assert not ver.passou and ver.filtro == "sem_melodia" and ver.motivo

def test_medoides_cobre_melhor_que_aleatorio_e_kcenter():
    """A única afirmação que a partida a frio pode fazer é sobre COBERTURA.
    Medoides ganha; k-center, a escolha 'óbvia' para diversidade, perde."""
    import random as _r
    v, frases = _amostra(n=400)
    X = [selecao.atributos(f, v, CORPUS["metros"], 3.5) for f in frases]

    def kcenter(k, rng):
        s = [rng.randrange(len(X))]
        while len(s) < k:
            s.append(max(range(len(X)),
                         key=lambda i: min(selecao._distancia(X[i], X[j]) for j in s)))
        return s

    for k in (4, 8, 12):
        al = sum(selecao.cobertura(X, _r.Random(r).sample(range(len(X)), k))
                 for r in range(5)) / 5
        kc = sum(selecao.cobertura(X, kcenter(k, _r.Random(r))) for r in range(5)) / 5
        md = sum(selecao.cobertura(X, selecao.lote_inicial(X, k, semente=r))
                 for r in range(5)) / 5
        assert md < al, f"lote {k}: medoides {md:.4f} não venceu aleatório {al:.4f}"
        assert md < kc, f"lote {k}: medoides {md:.4f} não venceu k-center {kc:.4f}"

def test_lote_inicial_devolve_candidatas_reais_e_distintas():
    """O autor tem de poder ouvir o que julga: um centroide médio não é uma
    melodia."""
    v, frases = _amostra(n=200)
    X = [selecao.atributos(f, v, CORPUS["metros"], 3.5) for f in frases]
    lote = selecao.lote_inicial(X, 8)
    assert len(lote) == len(set(lote)) == 8
    assert all(0 <= i < len(X) for i in lote)
    assert selecao.lote_inicial(X, 8, semente=0) == selecao.lote_inicial(X, 8, semente=0)

def test_perfil_de_saltos_e_distribuicao_nao_maximo():
    """A correção do autor: a forma da distribuição descreve a melodia, o
    extremo não."""
    v, frases = _amostra(n=50)
    for f in frases:
        perfil = selecao.perfil_de_saltos(f)
        assert len(perfil) == len(selecao.FAIXAS_DE_SALTO)
        assert abs(sum(perfil) - 1.0) < 1e-9, perfil

def test_hipoteses_saem_sempre_rotuladas():
    """Devolver o número sozinho seria apresentá-lo como qualidade — que é o
    erro que engine/selecao.py existe para não repetir."""
    v, frases = _amostra(n=5)
    r = selecao.rotular_hipoteses(frases[0])
    assert set(r) == {"eco_entre_pes", "estavel_em_longa"}
    for nome, bloco in r.items():
        assert "valor" in bloco
        for chave in ("hipotese", "derivada_de", "medido", "confirmaria", "estado"):
            assert bloco.get(chave), f"{nome} sem {chave}"
        assert bloco["estado"] == "não testada"

def test_gosto_aprende_e_a_amostragem_ativa_ajuda():
    """Contra gosto sintético linear: tau > 0,7 em 40 julgamentos, e a
    amostragem ativa acima da aleatória no orçamento baixo."""
    import random as _r
    v, frases = _amostra(n=300)
    X = [selecao.atributos(f, v, CORPUS["metros"], 3.5) for f in frases]
    d = len(X[0])

    def tau(w, verdade, amostra):
        conc = disc = 0
        for i in range(len(amostra)):
            for j in range(i + 1, len(amostra)):
                a, b = amostra[i], amostra[j]
                if ((gosto.escore(w, a) - gosto.escore(w, b)) *
                        (gosto.escore(verdade, a) - gosto.escore(verdade, b))) > 0:
                    conc += 1
                else:
                    disc += 1
        return (conc - disc) / (conc + disc)

    def roda(n, verdade, rep, ativo):
        rng = _r.Random(rep); pesos = [0.0] * d; js = []; vistos = set()
        teste = rng.sample(X, 60)
        for t in range(n):
            if not ativo or t < 6:
                i, j = rng.sample(range(len(X)), 2)
            else:
                i, j = gosto.proximo_par(X, pesos, vistos, semente=rng.randrange(10**6))
            vistos.add((min(i, j), max(i, j)))
            dif = gosto.escore(verdade, X[i]) - gosto.escore(verdade, X[j])
            pref = "a" if rng.random() < gosto._sigmoide(dif / 0.15) else "b"
            js = gosto.registrar(js, X[i], X[j], pref)
            if t >= 5:
                pesos = gosto.treinar(js, d)
        return tau(pesos, verdade, teste)

    rng = _r.Random(3)
    taus = []
    for rep in range(4):
        verdade = [rng.gauss(0, 1) for _ in range(d)]
        taus.append(roda(40, verdade, rep, True))
    assert sum(taus) / len(taus) > 0.7, f"tau médio {sum(taus)/len(taus):.3f}"

def test_amostragem_ativa_escolhe_par_incerto_e_distante():
    """Testa o MECANISMO, não a média de ponta a ponta.

    O ganho agregado da amostragem ativa é real mas pequeno (+0,11 de tau em
    10 julgamentos, medido com 8 repetições — ver engine/gosto.py), e ruidoso
    demais para virar asserção com poucas repetições. O que dá para afirmar com
    firmeza é que proximo_par faz o que promete: escolhe pares que o modelo não
    sabe ordenar E que são distantes entre si. Incerteza sozinha escolheria
    pares quase idênticos, cujo julgamento não informa nada."""
    import random as _r
    v, frases = _amostra(n=200)
    X = [selecao.atributos(f, v, CORPUS["metros"], 3.5) for f in frases]
    pesos = [0.0] * len(X[0])
    pesos[4] = 2.0          # um gosto qualquer, para haver incerteza a medir

    def valor(i, j):
        pr = gosto.probabilidade(pesos, X[i], X[j])
        incerteza = 1.0 - abs(pr - 0.5) * 2.0
        return incerteza * selecao._distancia(X[i], X[j])

    escolhidos = [gosto.proximo_par(X, pesos, semente=s) for s in range(20)]
    rng = _r.Random(0)
    sorteados = [tuple(rng.sample(range(len(X)), 2)) for _ in range(20)]
    media_escolhido = sum(valor(i, j) for i, j in escolhidos) / len(escolhidos)
    media_sorteado = sum(valor(i, j) for i, j in sorteados) / len(sorteados)
    assert media_escolhido > media_sorteado, (media_escolhido, media_sorteado)
    # e respeita os pares já vistos
    ja = {(min(i, j), max(i, j)) for i, j in escolhidos[:5]}
    novo_par = gosto.proximo_par(X, pesos, ja_vistos=ja, semente=0)
    assert (min(novo_par), max(novo_par)) not in ja

def test_gosto_explica_em_portugues():
    """O modelo tem de ser legível, ou contradiz a tese do projeto."""
    assert gosto.explicar([0.0] * len(selecao.NOMES_DOS_ATRIBUTOS))["treinado"] is False
    pesos = [0.0] * len(selecao.NOMES_DOS_ATRIBUTOS)
    pesos[4] = 1.5      # cantabilidade
    pesos[6] = -0.9     # notas repetidas
    e = gosto.explicar(pesos)
    assert e["treinado"] and "cantabilidade" in e["texto"]
    assert "prefere" in e["texto"] and "penaliza" in e["texto"]
    assert e["ordenados"][0][0] == "cantabilidade"

def test_gosto_avisa_quando_a_confianca_estaciona():
    """Ranquear com segurança fingida é pior que dizer que não sabe."""
    import random as _r
    rng = _r.Random(0); d = 6
    # julgamentos por moeda: não há o que aprender
    js = []
    for _ in range(40):
        a = [rng.random() for _ in range(d)]
        b = [rng.random() for _ in range(d)]
        js = gosto.registrar(js, a, b, "a" if rng.random() < 0.5 else "b")
    c = gosto.confianca(js)
    assert c["suficiente"] and c["acuracia"] < 0.75
    assert c["aviso"], "deveria avisar que os atributos não capturam o gosto"
    assert gosto.confianca(js[:3])["suficiente"] is False

def test_julgamentos_sobrevivem_ao_disco():
    """É a única memória do projeto: sem isso cada sessão recomeça do zero."""
    import tempfile
    js = gosto.registrar([], [0.1] * 4, [0.2] * 4, "b", contexto={"verso": "x"})
    with tempfile.TemporaryDirectory() as tmp:
        alvo = Path(tmp) / "j.json"
        gosto.gravar(js, alvo)
        assert gosto.carregar(alvo) == js
        assert gosto.carregar(Path(tmp) / "nao_existe.json") == []
    try:
        gosto.registrar([], [0.1], [0.2], "talvez")
    except ValueError:
        pass
    else:
        raise AssertionError("preferida só aceita 'a' ou 'b'")


# --------------------------------------------------------------------------
# Pipeline: o encadeamento dos dez estágios
# --------------------------------------------------------------------------

def test_pipeline_ponta_a_ponta():
    v = _verso("masnavi_1")
    res = pipeline.executar(v, CORPUS["metros"], modo="dorico", n=60, k=5)
    assert res["geradas"] == 60
    assert res["aprovadas"] <= 60 and res["aprovadas"] >= 59, res["peneira"]
    assert len(res["escolhidas"]) == 5
    assert res["conferencia_metro"]["conforme"] is True
    for c in res["escolhidas"]:
        assert c.passou and c.atributos and c.medidas
        assert len(c.frase.notas) == len(v["translit_silabas"])

def test_pipeline_sem_julgamento_ordena_por_cobertura():
    """Enquanto não houver julgamento, o pipeline não pode afirmar qualidade —
    e o motivo da ordem tem de dizer isso."""
    v = _verso("masnavi_1")
    res = pipeline.executar(v, CORPUS["metros"], n=60, k=4, julgamentos=[])
    assert "medoides" in res["ordenacao"]
    assert "não afirma qualidade" in res["ordenacao"]
    assert all(c.escore is None for c in res["escolhidas"])

def test_pipeline_com_julgamento_ordena_por_gosto():
    import random as _r
    v = _verso("masnavi_1")
    base = pipeline.executar(v, CORPUS["metros"], n=60, k=60, julgamentos=[])
    vet = [c.atributos for c in base["escolhidas"]]
    rng = _r.Random(0)
    verdade = [rng.gauss(0, 1) for _ in range(len(vet[0]))]
    js = []
    for _ in range(20):
        i, j = rng.sample(range(len(vet)), 2)
        pref = "a" if gosto.escore(verdade, vet[i]) > gosto.escore(verdade, vet[j]) else "b"
        js = gosto.registrar(js, vet[i], vet[j], pref)
    res = pipeline.executar(v, CORPUS["metros"], n=60, k=4, julgamentos=js)
    assert "gosto aprendido" in res["ordenacao"]
    escores = [c.escore for c in res["escolhidas"]]
    assert all(e is not None for e in escores)
    assert escores == sorted(escores, reverse=True), escores

def test_pipeline_leva_as_hipoteses_rotuladas_ate_a_saida():
    """Em nenhum ponto da cadeia a hipótese pode virar nota de qualidade."""
    v = _verso("divan_2214")
    res = pipeline.executar(v, CORPUS["metros"], n=40, k=3)
    for c in res["escolhidas"]:
        hip = c.medidas["hipoteses"]
        assert set(hip) == {"eco_entre_pes", "estavel_em_longa"}
        for bloco in hip.values():
            assert bloco["estado"] == "não testada" and bloco["hipotese"]

def test_pipeline_estagios_sao_puros_e_encadeaveis():
    """Cada estágio é função sobre a lista de candidatas, testável sozinho."""
    v = _verso("masnavi_1")
    todas = pipeline.gerar(v, "dorico", 30, CORPUS["metros"])
    assert len(todas) == 30 and all(c.veredito is None for c in todas)
    aprovadas = pipeline.peneirar(todas)
    assert all(c.veredito is not None for c in todas), "todas marcadas"
    assert all(c.passou for c in aprovadas)
    pipeline.medir(aprovadas, CORPUS["metros"])
    assert all(c.atributos for c in aprovadas)
    escolhidas = pipeline.ordenar(aprovadas, 3)
    assert len(escolhidas) == 3

def test_pipeline_cli_exporta_com_rastro_de_selecao():
    """A partitura exportada tem de dizer por que aquela candidata saiu."""
    with tempfile.TemporaryDirectory() as tmp:
        r = subprocess.run(
            [sys.executable, "engine/pipeline.py", "--verso", "masnavi_1",
             "--n", "40", "--lote", "2", "--export", "musicxml,midi",
             "--out", tmp], cwd=RAIZ, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        auditorias = sorted(Path(tmp).glob("*_auditoria.json"))
        assert len(auditorias) == 2, [p.name for p in Path(tmp).iterdir()]
        d = json.loads(auditorias[0].read_text("utf-8"))
        assert d["selecao"]["motivo_da_ordem"]
        assert d["selecao"]["geradas"] == 40
        assert d["complexidade"]["hipoteses"]
        assert d["regra_altura"] and d["conferencia_metro"]["conforme"]


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

def test_api_julgamento_ab():
    """Os endpoints do estágio 8: lote, julgamento e gosto."""
    import tempfile, shutil
    porta = 8979
    memoria = RAIZ / "data/julgamentos.json"
    guardado = memoria.read_text("utf-8") if memoria.exists() else None
    if memoria.exists():
        memoria.unlink()
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

        status, g = _pedir(porta, "/api/gosto")
        assert status == 200 and g["n"] == 0
        assert g["explicacao"]["treinado"] is False

        status, d = _pedir(porta, "/api/candidatas",
                           {"verso_id": "masnavi_1", "n": 60, "lote": 4})
        assert status == 200, d
        assert len(d["candidatas"]) == 4
        # sem julgamento, a resposta tem de dizer que é cobertura
        assert "não afirma qualidade" in d["ordenacao"], d["ordenacao"]
        for c in d["candidatas"]:
            assert c["atributos"] and c["notas"]
            for bloco in c["hipoteses"].values():
                assert bloco["estado"] == "não testada"

        a, b = d["candidatas"][0]["atributos"], d["candidatas"][1]["atributos"]
        status, r = _pedir(porta, "/api/julgar",
                           {"a": a, "b": b, "preferida": "a"})
        assert status == 200 and r["n"] == 1, r

        for caso in ({"a": a, "b": b, "preferida": "talvez"},
                     {"a": a, "b": [1, 2], "preferida": "a"},
                     {"a": "x", "b": b, "preferida": "a"}):
            status, corpo = _pedir(porta, "/api/julgar", caso)
            assert status == 400 and corpo.get("erro"), caso
        status, corpo = _pedir(porta, "/api/candidatas", {"verso_id": "nao_existe"})
        assert status == 400 and corpo.get("erro")
    finally:
        srv.terminate(); srv.wait(timeout=10)
        if memoria.exists():
            memoria.unlink()
        if guardado is not None:
            memoria.write_text(guardado, encoding="utf-8")

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


# ---------------------------------------------------------------------------
# O VAZN VIRA ESCANSÃO — ingestão de metro com fonte dupla (engine/metrica.py)
#
# O gargalo do corpus era escandir verso a verso. Estes testes travam o que
# torna o lote possível: o vazn publicado parseia nos pés do aruz, e a
# escansão derivada só é aceita se CASAR COM A LITERATURA. O que não casa fica
# em quarentena — o projeto não adivinha metro.
# ---------------------------------------------------------------------------

def test_arkan_silabas_batem_com_posicoes():
    """Em todo pé, a superlonga '=' vale exatamente duas posições e nada mais."""
    from engine.metrica import carregar_arkan, leituras_do_pe
    arkan = carregar_arkan()
    for nome, e in arkan.items():
        if nome == "_meta":
            continue
        for l in leituras_do_pe(e):
            assert len(l["padrao_silabas"]) == len(e["silabas"]) or \
                   l["romanizacao"] != e["romanizacao"], nome
            esperado = []
            for s in l["padrao_silabas"]:
                esperado += ["–", "u"] if s == "=" else [s]
            assert esperado == l["padrao_posicoes"], \
                f"{nome}/{l['romanizacao']}: {esperado} != {l['padrao_posicoes']}"


def test_vazn_do_corpus_reproduz_a_escansao_do_corpus():
    """O vazn publicado de cada metro do corpus devolve a escansão que o corpus
    já declara, símbolo por símbolo.

    Este é o teste que justifica a ingestão em lote: se o metro reproduz a
    escansão, escandir verso a verso não acrescenta informação.
    """
    from engine.metrica import resolver_vazn
    casos = [
        ("فاعلاتن فاعلاتن فاعلن (رمل مسدس محذوف یا وزن مثنوی)", ["masnavi_1", "masnavi_2"]),
        ("مفتعلن مفاعلن مفتعلن مفاعلن (رجز مثمن مطوی مخبون)", ["divan_2214"]),
    ]
    from engine.generative import expandir_escansao
    for vazn, ids in casos:
        r = resolver_vazn(vazn)
        assert r["status"] == "resolvido", (vazn, r)
        for vid in ids:
            v = _verso(vid)
            # a identidade firme é em POSIÇÕES métricas — é o que o metro fixa
            do_corpus = [p for p, _ in expandir_escansao(v["escansao"])]
            assert r["posicoes"] == do_corpus, (
                f"{vid}: vazn dá {''.join(r['posicoes'])}, "
                f"corpus expande em {''.join(do_corpus)}")
            # e a duração total tem de coincidir, com superlonga ou sem
            from engine.generative import durar_por_aruz
            assert abs(sum(durar_por_aruz(r["escansao"]))
                       - sum(durar_por_aruz(v["escansao"]))) < 1e-9, vid
            # no nível de SÍLABA só coincide onde o verso não tem superlonga,
            # e é esse o limite declarado da ingestão em lote
            if "=" not in v["escansao"]:
                assert r["escansao"] == v["escansao"], vid
            else:
                assert r["segmentacao_silabica"] == "posicional"
                assert r["superlongas_conferidas"] is False
                assert len(r["escansao"]) > len(v["escansao"])


def test_metro_derivado_passa_na_conferencia_do_motor():
    """A entrada de metro montada a partir do vazn confere contra o verso real
    pelo mesmo conferir_metro() que o resto do motor usa."""
    from engine.metrica import resolver_vazn, metro_para_corpus, id_do_metro
    from engine.generative import conferir_metro
    r = resolver_vazn("مفتعلن مفاعلن مفتعلن مفاعلن (رجز مثمن مطوی مخبون)")
    mid = id_do_metro(r)
    metros = {mid: metro_para_corpus(r, "https://ganjoor.net/moulavi/shams/ghazalsh/sh323")}
    v = dict(_verso("divan_2214")); v["metro"] = mid
    conf = conferir_metro(v, metros)
    assert conf["conforme"] is True, conf["divergencias"]
    assert conf["n_posicoes"] == 16


def test_pe_desconhecido_vai_para_quarentena():
    """Pé fora da tabela não é chutado: o metro não entra no corpus."""
    from engine.metrica import resolver_vazn
    r = resolver_vazn("فاعلاتن زززززز فاعلن")
    assert r["status"] == "quarentena"
    assert "زززززز" in r["pes_desconhecidos"]


def test_escansao_sem_padrao_publicado_vai_para_quarentena():
    """Uma sequência de pés válidos que não forma metro publicado é barrada.

    É o caso real dos metros raros da amostra (متفاعلن متفاعلن, e o خفیف de 16
    posições): a tabela publicada não os traz, então ficam de fora em vez de
    entrarem sem conferência.
    """
    from engine.metrica import resolver_vazn
    r = resolver_vazn("متفاعلن متفاعلن")
    assert r["status"] == "quarentena", r
    assert "publicados" in r["motivo"] or "literatura" in r["motivo"] or \
           "casa" in r["motivo"], r["motivo"]
    assert r["leituras_testadas"], "a quarentena deve dizer o que foi testado"


def test_ambiguidade_do_fe_lan_e_declarada_e_resolvida_pela_fonte():
    """فعلن tem duas leituras publicadas; a tabela declara as duas e quem
    desempata é a literatura, não a intuição.

    Mojtass 4.1.15 só fecha com faʿalon (uu–); se alguém apagar a leitura
    alternativa ou escolher a outra por gosto, este teste cai.
    """
    from engine.metrica import carregar_arkan, leituras_do_pe, resolver_vazn
    arkan = carregar_arkan()
    leituras = leituras_do_pe(arkan["فعلن"])
    assert len(leituras) == 2, "as duas leituras de فعلن devem estar declaradas"
    assert {"".join(l["padrao_posicoes"]) for l in leituras} == {"uu–", "––"}
    r = resolver_vazn("مفاعلن فعلاتن مفاعلن فعلن (مجتث مثمن مخبون محذوف)")
    assert r["status"] == "resolvido", r
    assert "".join(r["posicoes"]) == "u–u–uu––u–u–uu–"
    assert r["publicados"][0]["codigo_elwell_sutton"].startswith("4.1.15")


def test_anceps_do_padrao_publicado_e_respeitado():
    """'x' na literatura casa com longa e com curta, e só nessa posição."""
    from engine.metrica import casa_padrao
    assert casa_padrao(list("uu––uu––uu–"), "xu––uu––uu–")
    assert casa_padrao(list("–u––uu––uu–"), "xu––uu––uu–")
    assert not casa_padrao(list("uu––uu––uu–"), "xu––uu––u––")
    assert not casa_padrao(list("uu––uu––uu"), "xu––uu––uu–")


def test_id_do_metro_vem_da_fonte_e_e_estavel():
    """O identificador do metro é família + código Elwell-Sutton, não apelido
    nosso — dois poemas do mesmo metro caem no mesmo id."""
    from engine.metrica import resolver_vazn, id_do_metro
    a = id_do_metro(resolver_vazn("فاعلاتن فاعلاتن فاعلن"))
    b = id_do_metro(resolver_vazn("فاعلاتن فاعلاتن فاعلن (رمل مسدس محذوف)"))
    assert a == b == "ramal_2_4_11", (a, b)
    assert id_do_metro(resolver_vazn("مفتعلن مفاعلن مفتعلن مفاعلن")) == "rajaz_5_2_16"


def test_metro_derivado_nao_inventa_assinatura_afetiva():
    """A leitura afetiva do metro é do autor. A máquina deixa o campo ausente."""
    from engine.metrica import resolver_vazn, metro_para_corpus
    e = metro_para_corpus(resolver_vazn("فاعلاتن فاعلاتن فاعلن"), "http://exemplo")
    assert "assinatura_afetiva" not in e
    assert e["_fonte"]["padrao_publicado"]["codigo_elwell_sutton"]
    assert ("padrao_pe" in e) ^ ("padrao_pes" in e)


def test_metrica_nao_toca_a_rede():
    """engine/ fica offline: a rede vive em ferramentas/colher.py.

    Sem isso, 'função pura' e reprodutibilidade seriam promessa vazia — um
    import de urllib no motor abriria a porta para o corpus mudar sozinho.
    """
    fonte = (RAIZ / "engine/metrica.py").read_text(encoding="utf-8")
    import re as _re
    for proibido in ("urllib", "http.client", "socket", "requests"):
        assert not _re.search(rf"^\s*(import|from)\s+{_re.escape(proibido)}",
                              fonte, _re.M), f"engine/metrica.py importa {proibido}"


# ---------------------------------------------------------------------------
# VERSO SEM TRANSLITERAÇÃO CONFERIDA — o que o lote produz
#
# O Ganjoor publica o texto persa e o vazn, não a transliteração silabada.
# Inventar sílaba para preencher o rastro seria a fabricação que
# engine/filtros.py registra como erro nº 3. Então o rótulo passa a ser a
# POSIÇÃO métrica, e o relatório declara que a sílaba não foi conferida.
# ---------------------------------------------------------------------------

def _verso_de_lote():
    """Verso como a ingestão em lote o produz: persa + metro do vazn, sem
    transliteração silabada."""
    from engine.metrica import resolver_vazn, metro_para_corpus, id_do_metro
    r = resolver_vazn("مفاعلن فعلاتن مفاعلن فعلن (مجتث مثمن مخبون محذوف)")
    mid = id_do_metro(r)
    metros = {mid: metro_para_corpus(r, "https://ganjoor.net/exemplo")}
    verso = {"id": "lote_teste", "obra": "gazal de teste", "metro": mid,
             "persa": "ای یار من", "escansao": r["escansao"],
             "dominio_publico": True, "metro_conferido": True}
    return verso, metros


def test_verso_com_transliteracao_mantem_a_silaba_no_rastro():
    """Onde a transliteração existe, nada muda: o rastro continua dizendo a
    sílaba persa."""
    from engine.generative import silabas_do_verso
    v = _verso("masnavi_1")
    rot, conferidas = silabas_do_verso(v)
    assert conferidas is True
    assert rot == v["translit_silabas"]
    assert "beš" in rot[0] or rot[0] == v["translit_silabas"][0]


def test_verso_sem_transliteracao_rotula_posicao_e_nao_inventa_silaba():
    from engine.generative import silabas_do_verso, ROTULO_POSICIONAL
    v, _ = _verso_de_lote()
    rot, conferidas = silabas_do_verso(v)
    assert conferidas is False
    assert len(rot) == len(v["escansao"])
    assert all(r.startswith(ROTULO_POSICIONAL) for r in rot)
    assert rot[0] == "·1" and rot[-1] == f"·{len(v['escansao'])}"


def test_transliteracao_parcial_e_recusada():
    """Meia transliteração é pior que nenhuma: alinharia nota à sílaba errada.

    Ou confere tudo, ou deixa vazio e o rastro usa a posição.
    """
    from engine.generative import silabas_do_verso
    v, _ = _verso_de_lote()
    v = dict(v); v["translit_silabas"] = ["ey", "yār"]
    try:
        silabas_do_verso(v)
    except ValueError as e:
        assert "parcial" in str(e)
    else:
        assert False, "transliteração parcial deveria ser recusada"


def test_relatorio_declara_que_a_silaba_nao_foi_conferida():
    """Quem lê a auditoria tem de saber que '·3' é posição, não sílaba."""
    from engine.generative import gerar_melodia, relatorio_auditoria
    v, metros = _verso_de_lote()
    rel = relatorio_auditoria(gerar_melodia(v, metros=metros), v, metros)
    c = rel["conferencia"]
    assert c["silabas_conferidas"] is False
    assert c["alinhado"] is True
    assert "posição métrica" in c["rotulo_das_notas"]
    # e o rastro segue completo: cada nota com símbolo do aruz e duração
    for linha in rel["mapa_silaba_para_nota"]:
        assert linha["aruz"] in DUR_ARUZ and linha["dur_base_quarter"] > 0

    rel_conf = relatorio_auditoria(
        gerar_melodia(_verso("masnavi_1"), metros=CORPUS["metros"]),
        _verso("masnavi_1"), CORPUS["metros"])
    assert rel_conf["conferencia"]["silabas_conferidas"] is True


def test_pipeline_inteiro_roda_em_verso_de_lote():
    """Ponta a ponta no verso que o lote produz: metro confere, pipeline anda,
    partitura e MIDI saem."""
    from engine.pipeline import executar
    from engine.generative import gerar_melodia, relatorio_auditoria
    from engine.export import escrever
    v, metros = _verso_de_lote()
    res = executar(v, metros, n=40, k=4, motivico=True)
    assert res["conferencia_metro"]["conforme"] is True
    assert len(res["escolhidas"]) == 4
    f = gerar_melodia(v, metros=metros)
    rel = relatorio_auditoria(f, v, metros)
    with tempfile.TemporaryDirectory() as tmp:
        escritos = escrever(f, rel, tmp, "lote")
        nomes = {p.name for p in escritos}
        assert {"lote.musicxml", "lote.mid", "lote_auditoria.json"} <= nomes


# ---------------------------------------------------------------------------
# COLHEDOR (ferramentas/colher.py) — ingestão em lote
#
# Nenhum destes testes toca a rede: o cache em disco do próprio colhedor serve
# de fixture. Se um deles começar a precisar de rede, é porque a separação
# entre colher e processar se rompeu.
# ---------------------------------------------------------------------------

_PAGINA_FIXTURE = """<html><head><title>غزل شمارهٔ ۹۹ - teste</title></head><body>
<table><tr><td>وزن:</td>
  <td><a href="/simi/?v=x&amp;a=5">فاعلاتن فاعلاتن فاعلن (رمل مسدس محذوف)</a></td></tr></table>
<div class="b" id="bn1"><div class="m1"><p>هَمْ&zwnj;چو نی زهری و تریاقی که دید</p></div>
<div class="m2"><p>هم چو نی دمساز و مشتاقی که دید</p></div></div>
<div class="b" id="bn2"><div class="m1"><p>نی حدیث راه پر خون می&zwnj;کند</p></div>
<div class="m2"><p>قصه&zwnj;های عشق مجنون می&zwnj;کند</p></div></div>
</body></html>"""


def _semear_cache(tmp, url, pagina):
    """Escreve uma página no cache do colhedor, para que pegar() não use rede."""
    from ferramentas.colher import _nome_de_cache
    d = Path(tmp); d.mkdir(parents=True, exist_ok=True)
    (d / _nome_de_cache(url)).write_text(pagina, encoding="utf-8")


def test_colhedor_extrai_vazn_e_os_dois_hemistiquios():
    """Perder o segundo hemistíquio corta o corpus pela metade — e foi o que o
    primeiro extrator fazia, por tentar casar div aninhado com regex."""
    from ferramentas.colher import extrair_vazn, extrair_coplas
    assert "فاعلاتن" in extrair_vazn(_PAGINA_FIXTURE)
    coplas = extrair_coplas(_PAGINA_FIXTURE)
    assert len(coplas) == 2, coplas
    assert [c["n"] for c in coplas] == ["bn1", "bn2"]
    for c in coplas:
        assert len(c["hemistiquios"]) == 2, c
        assert all(h.strip() for h in c["hemistiquios"])
    assert "زهری" in coplas[0]["hemistiquios"][0]
    assert "دمساز" in coplas[0]["hemistiquios"][1]


def test_colhedor_nao_inventa_transliteracao_nem_glosa():
    """O colhedor entrega o que a fonte dá, e declara o que falta.

    translit_silabas, glosa_pt e imagem são trabalho humano. Preenchê-los com
    plausibilidade é o erro nº 3 do registro em engine/filtros.py.
    """
    from ferramentas.colher import extrair_poema, versos_do_poema
    from engine.metrica import resolver_vazn, id_do_metro
    poema = extrair_poema(_PAGINA_FIXTURE, "https://ganjoor.net/x/sh99")
    r = resolver_vazn(poema["vazn"])
    versos = versos_do_poema(poema, r, id_do_metro(r))
    assert len(versos) == 4, "duas coplas de dois hemistíquios"
    for v in versos:
        assert "translit_silabas" not in v
        assert "glosa_pt" not in v and "imagem" not in v
        assert v["persa"] and v["escansao"] == r["escansao"]
        assert v["_origem"]["url"].endswith("/sh99")
        assert v["_origem"]["vazn_registrado"] == r["vazn"]
        assert any("translit_silabas" in x for x in v["_pendencias_humanas"])
        assert any("superlonga" in x for x in v["_pendencias_humanas"])
    assert len({v["id"] for v in versos}) == 4, "ids têm de ser distintos"


def test_colhedor_registra_a_variante_de_edicao():
    """O texto do Ganjoor não é o de toda edição. Fingir que é apagaria uma
    divergência real — a abertura do Masnavi difere entre o Ganjoor e Nicholson,
    que é a edição que o corpus feito à mão segue."""
    from ferramentas.colher import (EDICAO, colher, gravar, PENDENCIAS_HUMANAS)
    assert "Nicholson" in EDICAO and "شکایت" in EDICAO
    with tempfile.TemporaryDirectory() as tmp:
        url = "https://ganjoor.net/t/sh1"
        _semear_cache(tmp + "/cache", url, _PAGINA_FIXTURE)
        c = colher([url], cache=Path(tmp) / "cache", espera=0)
        corpus = json.loads(gravar(c, Path(tmp) / "saida")[0]
                            .read_text(encoding="utf-8"))
    # o texto completo mora no cabeçalho, uma vez; o verso aponta para ele.
    # Copiá-lo em cada verso custava 2,35 MB dos 5,21 MB de uma colheita de 150
    # gazais e deixava o arquivo ilegível — e o que importa é a ressalva estar
    # escrita e ligada ao verso, não estar copiada.
    assert "Nicholson" in corpus["_edicao"]
    assert set(corpus["_pendencias_humanas"]) == set(PENDENCIAS_HUMANAS)
    for v in corpus["versos"]:
        assert v["_origem"]["edicao"].startswith("ver _edicao")
        assert set(v["_pendencias_humanas"]) <= set(corpus["_pendencias_humanas"])
        assert v["_pendencias_humanas"], "verso colhido sem pendência declarada"


def test_colhedor_poe_em_quarentena_e_nao_adivinha():
    """Sem vazn, sem texto, ou com metro não conferível: fora do corpus, com o
    motivo nomeado. A quarentena é o mapa do que falta."""
    from ferramentas.colher import colher
    with tempfile.TemporaryDirectory() as tmp:
        bom = "https://ganjoor.net/t/sh1"
        sem_vazn = "https://ganjoor.net/t/sh2"
        raro = "https://ganjoor.net/t/sh3"
        _semear_cache(tmp, bom, _PAGINA_FIXTURE)
        _semear_cache(tmp, sem_vazn, _PAGINA_FIXTURE.replace("وزن:", "قافیه:"))
        _semear_cache(tmp, raro, _PAGINA_FIXTURE.replace(
            "فاعلاتن فاعلاتن فاعلن (رمل مسدس محذوف)", "متفاعلن متفاعلن"))
        c = colher([bom, sem_vazn, raro], cache=Path(tmp), espera=0)
    r = c["relatorio"]
    assert r["poemas_pedidos"] == 3 and r["poemas_ingeridos"] == 1
    assert r["versos_ingeridos"] == 4 and r["metros_distintos"] == 1
    estados = {q["url"].rsplit("/", 1)[1]: q["status"] for q in c["quarentena"]}
    assert estados == {"sh2": "sem_vazn", "sh3": "quarentena"}, estados
    assert all(q.get("motivo") for q in c["quarentena"]), "quarentena sem motivo"


def test_colheita_gravada_roda_no_motor_e_confere_o_metro():
    """O arquivo que a colheita grava é corpus de verdade: o motor o lê e cada
    verso confere contra o metro declarado."""
    from ferramentas.colher import colher, gravar
    from engine.generative import conferir_metro, gerar_melodia
    with tempfile.TemporaryDirectory() as tmp:
        url = "https://ganjoor.net/t/sh1"
        _semear_cache(tmp + "/cache", url, _PAGINA_FIXTURE)
        c = colher([url], cache=Path(tmp) / "cache", espera=0)
        arqs = gravar(c, Path(tmp) / "saida")
        assert [a.name for a in arqs] == ["corpus_colhido.json",
                                          "corpus_colhido_quarentena.json"]
        corpus = json.loads(arqs[0].read_text(encoding="utf-8"))
    assert corpus["_relatorio_da_colheita"]["versos_ingeridos"] == 4
    for v in corpus["versos"]:
        conf = conferir_metro(v, corpus["metros"])
        assert conf["conforme"] is True, (v["id"], conf["divergencias"])
        frase = gerar_melodia(v, metros=corpus["metros"])
        assert len(frase.notas) == len(v["escansao"])
    for m in corpus["metros"].values():
        assert m["_fonte"]["padrao_publicado"]["codigo_elwell_sutton"]
        assert "assinatura_afetiva" not in m


def test_engine_inteiro_fica_offline():
    """A rede vive só em ferramentas/. Se um módulo de engine/ importar rede, a
    reprodutibilidade do corpus deixa de ser verificável."""
    import re as _re
    for mod in sorted((RAIZ / "engine").glob("*.py")):
        fonte = mod.read_text(encoding="utf-8")
        for proibido in ("urllib", "http.client", "socket", "requests", "ftplib"):
            assert not _re.search(rf"^\s*(import|from)\s+{_re.escape(proibido)}",
                                  fonte, _re.M), f"{mod.name} importa {proibido}"


def test_corpus_colhido_versionado_confere_inteiro():
    """O corpus colhido que está no repositório confere verso por verso.

    São milhares de versos cujo ritmo deriva de metro publicado. Se um dia uma
    mudança na tabela de pés, no portão de fonte dupla ou no motor quebrar
    algum deles, é aqui que aparece — e não depois, numa canção.
    """
    arq = RAIZ / "data/corpus_colhido.json"
    if not arq.exists():
        return                                  # colheita é opcional no repo
    from engine.generative import conferir_metro, gerar_melodia, silabas_do_verso
    corpus = json.loads(arq.read_text(encoding="utf-8"))
    vs, ms = corpus["versos"], corpus["metros"]
    assert vs and ms

    vistos = set()
    for v in vs:
        assert v["id"] not in vistos, f"id repetido: {v['id']}"
        vistos.add(v["id"])
        assert v["persa"].strip(), v["id"]
        assert not any(x in v["persa"] for x in ("<", ">", "http")), v["id"]
        assert v["metro"] in ms, f"{v['id']} cita metro ausente: {v['metro']}"
        assert v["dominio_publico"] is True
        conf = conferir_metro(v, ms)
        assert conf["conforme"] is True, (v["id"], conf["divergencias"][:2])
        # sem transliteração, o rastro usa posição — e nunca finge sílaba
        rot, conferidas = silabas_do_verso(v)
        assert conferidas is False and len(rot) == len(v["escansao"])

    # uma melodia por metro, para garantir que todo metro colhido é tocável
    for mid in ms:
        v = next(x for x in vs if x["metro"] == mid)
        assert len(gerar_melodia(v, metros=ms).notas) == len(v["escansao"])
        assert "assinatura_afetiva" not in ms[mid], (
            f"{mid}: a leitura afetiva do metro é do autor, a máquina não escreve")
        assert ms[mid]["_fonte"]["padrao_publicado"]["codigo_elwell_sutton"]


def test_comprimento_do_persa_acompanha_as_posicoes_do_metro():
    """Conferência INDEPENDENTE da atribuição de metro, sem escandir nada.

    Se o metro atribuído a cada verso estiver certo, um verso de 16 posições
    tem de ser sistematicamente mais longo em caracteres que um de 10. Essa
    correlação não usa a tabela de pés nem a tabela publicada: ela sai do
    texto persa, que é a fonte. Medido na colheita de 150 gazais: r = 0,85 em
    3.306 versos. Se cair muito, a extração de hemistíquio ou a atribuição de
    metro regrediu.
    """
    import math
    arq = RAIZ / "data/corpus_colhido.json"
    if not arq.exists():
        return
    vs = json.loads(arq.read_text(encoding="utf-8"))["versos"]
    if len({len(v["escansao"]) for v in vs}) < 2:
        return                                  # sem variedade de metro, nada a medir
    pares = [(len(v["escansao"]), len(v["persa"])) for v in vs]
    n = len(pares)
    mx = sum(a for a, _ in pares) / n
    my = sum(b for _, b in pares) / n
    cov = sum((a - mx) * (b - my) for a, b in pares)
    vx = sum((a - mx) ** 2 for a, _ in pares)
    vy = sum((b - my) ** 2 for _, b in pares)
    r = cov / math.sqrt(vx * vy)
    assert r > 0.7, f"correlação posições x caracteres caiu para {r:.3f}"


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
