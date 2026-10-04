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
Exportação de partitura e MIDI — só com a biblioteca padrão.

Por que sem dependência: o princípio declarado do projeto é que o básico roda
em máquina modesta sem instalar nada (README, e docs/PROCESSO_INTERFACE.md §1,
"Leve"). Uma exportação que exigisse music21 tornaria o artefato principal —
a partitura — inacessível justamente a quem o projeto quer alcançar. music21
continua sendo o caminho opcional para LilyPond/PDF, nada mais.

Toda exportação escreve o relatório de auditoria ao lado dos arquivos: nenhuma
partitura sai do projeto sem a sua procedência. É o mesmo compromisso do
motor, aplicado à saída.

CONVERSÃO DE DURAÇÃO
--------------------
As durações do aruz (0.5, 1.0, 1.5 quarters) são exatas em 480 ticks por
quarter, então não há arredondamento em nenhum dos dois formatos. Notas que
atravessam a barra de compasso são divididas e ligadas (tie) por barrar().
"""
from __future__ import annotations

import json, struct
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from engine.generative import Frase, NotaTrace

DIVISOES = 480          # ticks por quarter: 0.5/1.0/1.5 dão inteiros exatos

# quarterLength -> (tipo MusicXML, nº de pontos de aumento)
TIPOS = {
    6.0: ("whole", 1), 4.0: ("whole", 0), 3.0: ("half", 1), 2.0: ("half", 0),
    1.5: ("quarter", 1), 1.0: ("quarter", 0),
    0.75: ("eighth", 1), 0.5: ("eighth", 0),
    0.375: ("16th", 1), 0.25: ("16th", 0),
    0.1875: ("32nd", 1), 0.125: ("32nd", 0),
}

# classe de altura -> (nome da nota, alteração), grafia com sustenidos
PASSOS = [("C",0),("C",1),("D",0),("D",1),("E",0),("F",0),
          ("F",1),("G",0),("G",1),("A",0),("A",1),("B",0)]


def tipo_musical(dur: float) -> tuple[str, int]:
    """Converte quarterLength em (tipo, pontos) do MusicXML.

    Falha alto em vez de arredondar: uma partitura com duração errada é pior
    que uma exportação que recusa, porque o erro seguiria silencioso até a
    mão do músico.
    """
    chave = round(dur, 6)
    if chave not in TIPOS:
        raise ValueError(
            f"duração {dur} não tem figura exata em MusicXML; "
            f"figuras disponíveis: {sorted(TIPOS)}")
    return TIPOS[chave]


def assinatura_de_compasso(quarters: float) -> tuple[int, int]:
    """Converte a duração do compasso na fórmula (numerador, denominador).

    Necessário porque o compasso deixou de ser sempre 4/4: o pé do ramal dura
    3.5 quarters, que é 7/8. A conversão ingênua — int(3.5) sobre denominador
    4 — escreveria 3/4 numa partitura de 7/8, e o erro seguiria silencioso até
    a estante do músico.
    """
    alvo = round(quarters, 6)
    if alvo <= 0:
        raise ValueError(f"compasso deve ser positivo, recebi {quarters}")
    for denominador, fator in ((4, 1), (8, 2), (16, 4)):
        valor = alvo * fator
        if abs(valor - round(valor)) < 1e-9:
            return int(round(valor)), denominador
    raise ValueError(
        f"compasso de {quarters} quarters não tem fórmula exata até semicolcheia")


def figuras(dur: float) -> list[float]:
    """Decompõe uma duração na soma de figuras que existem na notação.

    Necessário porque nem toda duração tem figura única: 2.5 quarters (o que
    sobra para completar o compasso depois de 9.5 quarters de aruz) é mínima
    + colcheia, não uma figura só. Guloso, da maior figura para a menor.
    """
    alvo = round(dur, 6)
    if alvo <= 0:
        return []
    partes = []
    for fig in sorted(TIPOS, reverse=True):
        while alvo >= fig - 1e-9:
            partes.append(fig)
            alvo = round(alvo - fig, 6)
        if alvo <= 1e-9:
            return partes
    raise ValueError(
        f"duração {dur} não se decompõe em figuras de notação "
        f"(resto {alvo}); figuras: {sorted(TIPOS)}")


@dataclass
class Evento:
    """Um evento de partitura: nota ou pausa, já ajustado ao compasso."""
    dur: float
    midi: int | None = None        # None = pausa
    silaba: str = ""
    tie_inicio: bool = False
    tie_fim: bool = False

    @property
    def pausa(self) -> bool:
        return self.midi is None


def barrar(notas: list[NotaTrace], compasso: float = 4.0,
           anacruse: float = 0.0) -> list[list[Evento]]:
    """Divide a sequência de notas em compassos, ligando com tie a nota que
    atravessa a barra. Função pura.

    A anacruse (deslocamento contra o tempo forte, ver engine/ritmo.py) entra
    como pausa inicial, e o último compasso é completado com pausa para que o
    MusicXML seja válido.
    """
    if compasso <= 0:
        raise ValueError(f"compasso deve ser positivo, recebi {compasso}")

    eventos: list[Evento] = []
    pos = 0.0

    def empurrar(dur: float, midi: int | None, silaba: str = "") -> None:
        """Acrescenta um evento, fatiando-o nas barras de compasso e
        decompondo cada fatia em figuras representáveis. As fatias de uma
        mesma nota são unidas por ligadura, de modo que o músico vê uma nota
        só — a duração que veio da sílaba persa."""
        nonlocal pos
        pedacos: list[float] = []
        restante, cursor = round(dur, 6), pos
        while restante > 1e-9:
            espaco = compasso - (cursor % compasso)
            fatia = round(min(restante, espaco), 6)
            for fig in figuras(fatia):
                pedacos.append(fig)
                cursor += fig
            restante = round(restante - fatia, 6)
        for i, fig in enumerate(pedacos):
            parte = Evento(dur=fig, midi=midi, silaba=silaba if i == 0 else "")
            if midi is not None:
                parte.tie_fim = i > 0
                parte.tie_inicio = i < len(pedacos) - 1
            eventos.append(parte)
        pos = cursor

    if anacruse > 0:
        empurrar(anacruse, None)
    for n in notas:
        empurrar(n.dur, n.midi, n.silaba)
    sobra = (-pos) % compasso
    if sobra > 1e-9:
        empurrar(round(sobra, 6), None)

    compassos: list[list[Evento]] = []
    atual: list[Evento] = []
    acumulado = 0.0
    for ev in eventos:
        atual.append(ev)
        acumulado += ev.dur
        if acumulado >= compasso - 1e-9:
            compassos.append(atual)
            atual, acumulado = [], 0.0
    if atual:
        compassos.append(atual)
    return compassos


# ---------------------------------------------------------------------------
# MusicXML
# ---------------------------------------------------------------------------

def para_musicxml(frase: Frase, titulo: str, compasso: float = 4.0,
                  letra: list[str] | None = None) -> bytes:
    """Gera MusicXML 4.0 partwise para a voz da frase.

    Se `letra` for passada, cada sílaba do português entra no lugar da sílaba
    persa — é o resultado da co-produção. Sem ela, a sílaba transliterada de
    Rumi vai para o <lyric>, o que deixa a partitura auditável à vista: dá
    para conferir a olho que a figura casa com a quantidade da sílaba.
    """
    notas = frase.notas
    if letra is not None:
        if len(letra) != len(notas):
            raise ValueError(
                f"letra tem {len(letra)} sílabas para {len(notas)} notas; "
                "o vínculo 1:1 sílaba<->nota é o compromisso do projeto")
        notas = [NotaTrace(**{**n.__dict__, "silaba": s})
                 for n, s in zip(notas, letra)]

    raiz = ET.Element("score-partwise", version="4.0")
    ET.SubElement(ET.SubElement(raiz, "work"), "work-title").text = titulo
    ident = ET.SubElement(raiz, "identification")
    ET.SubElement(ident, "creator", type="composer").text = (
        "Divã do Vão — ritmo derivado do aruz de Rumi (domínio público)")
    enc = ET.SubElement(ident, "encoding")
    ET.SubElement(enc, "software").text = "Divã do Vão — engine/export.py (stdlib)"
    ET.SubElement(enc, "encoding-date").text = date.today().isoformat()
    # a procedência viaja dentro do próprio arquivo de partitura
    ET.SubElement(ident, "miscellaneous").append(
        _campo("auditoria", f"modo={frase.modo}; metro={frase.metro}; "
                            f"operacoes={frase.operacoes or ['derivacao_direta']}"))

    lista = ET.SubElement(raiz, "part-list")
    parte_id = ET.SubElement(lista, "score-part", id="P1")
    ET.SubElement(parte_id, "part-name").text = "Voz"

    parte = ET.SubElement(raiz, "part", id="P1")
    compassos = barrar(notas, compasso, frase.anacruse)
    for i, eventos in enumerate(compassos, start=1):
        m = ET.SubElement(parte, "measure", number=str(i))
        if i == 1:
            attrs = ET.SubElement(m, "attributes")
            ET.SubElement(attrs, "divisions").text = str(DIVISOES)
            ET.SubElement(ET.SubElement(attrs, "key"), "fifths").text = "0"
            batidas, figura = assinatura_de_compasso(compasso)
            tempo = ET.SubElement(attrs, "time")
            ET.SubElement(tempo, "beats").text = str(batidas)
            ET.SubElement(tempo, "beat-type").text = str(figura)
            clave = ET.SubElement(attrs, "clef")
            ET.SubElement(clave, "sign").text = "G"
            ET.SubElement(clave, "line").text = "2"
        for ev in eventos:
            _nota_xml(m, ev)

    cabeca = (b'<?xml version="1.0" encoding="utf-8"?>\n'
              b'<!DOCTYPE score-partwise PUBLIC '
              b'"-//Recordare//DTD MusicXML 4.0 Partwise//EN" '
              b'"http://www.musicxml.org/dtds/partwise.dtd">\n')
    ET.indent(raiz, space="  ")
    return cabeca + ET.tostring(raiz, encoding="utf-8", xml_declaration=False)


def _campo(nome: str, valor: str) -> ET.Element:
    el = ET.Element("miscellaneous-field", name=nome)
    el.text = valor
    return el


def _nota_xml(compasso_el: ET.Element, ev: Evento) -> None:
    tipo, pontos = tipo_musical(ev.dur)
    el = ET.SubElement(compasso_el, "note")
    if ev.pausa:
        ET.SubElement(el, "rest")
    else:
        passo, alter = PASSOS[ev.midi % 12]
        altura = ET.SubElement(el, "pitch")
        ET.SubElement(altura, "step").text = passo
        if alter:
            ET.SubElement(altura, "alter").text = str(alter)
        ET.SubElement(altura, "octave").text = str(ev.midi // 12 - 1)
    ET.SubElement(el, "duration").text = str(int(round(ev.dur * DIVISOES)))
    if ev.tie_fim:
        ET.SubElement(el, "tie", type="stop")
    if ev.tie_inicio:
        ET.SubElement(el, "tie", type="start")
    ET.SubElement(el, "voice").text = "1"
    ET.SubElement(el, "type").text = tipo
    for _ in range(pontos):
        ET.SubElement(el, "dot")
    if not ev.pausa and PASSOS[ev.midi % 12][1]:
        ET.SubElement(el, "accidental").text = "sharp"
    if ev.tie_fim or ev.tie_inicio:
        nots = ET.SubElement(el, "notations")
        if ev.tie_fim:
            ET.SubElement(nots, "tied", type="stop")
        if ev.tie_inicio:
            ET.SubElement(nots, "tied", type="start")
    if ev.silaba and not ev.pausa:
        letra_el = ET.SubElement(el, "lyric", number="1")
        ET.SubElement(letra_el, "syllabic").text = "single"
        ET.SubElement(letra_el, "text").text = ev.silaba


# ---------------------------------------------------------------------------
# MIDI (Standard MIDI File tipo 0)
# ---------------------------------------------------------------------------

def _vlq(n: int) -> bytes:
    """Quantidade de tamanho variável, como o SMF exige para os deltas."""
    if n < 0:
        raise ValueError(f"delta negativo: {n}")
    saida = bytearray([n & 0x7F])
    n >>= 7
    while n:
        saida.insert(0, (n & 0x7F) | 0x80)
        n >>= 7
    return bytes(saida)


def para_midi(frase: Frase, bpm: int = 88, velocidade: int = 80,
              compasso: float = 4.0) -> bytes:
    """Gera um SMF tipo 0 com a melodia. 88 bpm é o andamento que a
    síntese-guia da interface usa, para que ouvir no app e ouvir o arquivo
    dêem a mesma coisa."""
    if bpm <= 0:
        raise ValueError(f"bpm deve ser positivo, recebi {bpm}")
    eventos = bytearray()
    microseg = int(round(60_000_000 / bpm))
    eventos += _vlq(0) + b"\xFF\x51\x03" + microseg.to_bytes(3, "big")   # tempo
    batidas, figura = assinatura_de_compasso(compasso)
    # o denominador do SMF é potência de 2: 4 -> 2, 8 -> 3, 16 -> 4
    expoente = {4: 2, 8: 3, 16: 4}[figura]
    eventos += _vlq(0) + b"\xFF\x58\x04" + bytes([batidas, expoente, 24, 8])

    delta = int(round(frase.anacruse * DIVISOES))
    for n in frase.notas:
        ticks = int(round(n.dur * DIVISOES))
        eventos += _vlq(delta) + bytes([0x90, n.midi & 0x7F, velocidade])
        eventos += _vlq(ticks) + bytes([0x80, n.midi & 0x7F, 0])
        delta = 0
    eventos += _vlq(0) + b"\xFF\x2F\x00"                                  # fim

    cabeca = b"MThd" + struct.pack(">IHHH", 6, 0, 1, DIVISOES)
    trilha = b"MTrk" + struct.pack(">I", len(eventos)) + bytes(eventos)
    return cabeca + trilha


# ---------------------------------------------------------------------------
# Escrita em disco — sempre com a auditoria ao lado
# ---------------------------------------------------------------------------

def escrever(frase: Frase, relatorio: dict, destino: str | Path, nome: str,
             formatos: list[str] | None = None, titulo: str | None = None,
             compasso: float = 4.0, letra: list[str] | None = None) -> list[Path]:
    """Escreve os formatos pedidos mais o relatório de auditoria.

    A auditoria não é opcional: é ela que distingue esta partitura da saída de
    um gerador opaco.
    """
    formatos = formatos or ["musicxml", "midi"]
    desconhecidos = set(formatos) - {"musicxml", "midi"}
    if desconhecidos:
        raise ValueError(f"formato desconhecido: {sorted(desconhecidos)}; "
                         "use 'musicxml' e/ou 'midi'")
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    escritos = []

    if "musicxml" in formatos:
        alvo = destino / f"{nome}.musicxml"
        alvo.write_bytes(para_musicxml(frase, titulo or nome, compasso, letra))
        escritos.append(alvo)
    if "midi" in formatos:
        alvo = destino / f"{nome}.mid"
        alvo.write_bytes(para_midi(frase, compasso=compasso))
        escritos.append(alvo)

    alvo = destino / f"{nome}_auditoria.json"
    alvo.write_text(json.dumps(relatorio, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    escritos.append(alvo)
    return escritos
