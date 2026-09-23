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
A peneira — e o registro de por que ela é tão fina.

Este módulo rejeita quase nada: só melodia degenerada, o que dá ~0,07% do
espaço. Isso não é descuido. É o resultado de quatro tentativas de heurística
que a medição derrubou, e o registro delas fica aqui para que ninguém as
refaça.

QUATRO HEURÍSTICAS PROPOSTAS E DERRUBADAS
-----------------------------------------

1. **Cinco filtros de "sanidade", reprovando 9 em 10.** Gosto sem dados.
   "Sem salto > 5 semitons" cortava 32,5% das melodias para remover o que já
   era 3,98% dos intervalos — a cauda longa já era rara sozinha. E "termina na
   tônica" cortava 66,6%, jogando fora dois dos três fechos que o próprio
   motor faz de propósito (tônica, terça e quinta, 1/3 cada).

2. **Alvo de 0,72 de reversão após salto** (von Hippel & Huron). É norma de
   música clássica ocidental, e os mesmos autores avisam que proximidade e
   reversão podem ser artefato de âmbito — o nosso tem 6 alturas. Não há razão
   para supor que seja o alvo deste projeto.

3. **Usar exemplos/*.musicxml como perfil de estilo "do autor".** Autoria
   inventada: o campo <creator type="composer"> desses arquivos diz "Divã do
   Vão", que é o nome do projeto e não de uma pessoa, e eles foram gerados por
   music21. O próprio exemplos/README.md já dizia que não são saída deste motor.

4. **Lote inicial "diverso" por k-center.** Medido: 26% PIOR que sorteio
   aleatório em cobertura do espaço, porque k-center escolhe extremos e
   extremos cobrem mal o miolo. Ver engine/selecao.py para o que funcionou.

O padrão é o mesmo nas quatro: buscar uma autoridade externa para ancorar a
escolha — intuição, norma publicada, autoria suposta, diversidade vaga — em
vez de aceitar que **ainda não existe verdade de referência neste projeto**. A
única que vai existir é o julgamento do autor, e é para isso que serve
engine/gosto.py.

REGRA QUE ESTE MÓDULO SEGUE
---------------------------
Um filtro só entra aqui se rejeitar algo que **não é melodia**, não algo que
seja melodia ruim. Salto grande, nota repetida, contorno monótono e fecho em
terça ou quinta são material musical legítimo: viram atributo do ranqueador,
nunca corte. O teste test_peneira_nao_corta_por_gosto trava isso.
"""
from __future__ import annotations

from dataclasses import dataclass

from engine.generative import Frase


@dataclass
class Veredito:
    """Resultado da peneira para uma frase. Sempre diz qual filtro reprovou e
    por quê — rejeição muda não é auditável."""
    passou: bool
    filtro: str = ""
    motivo: str = ""

    def __bool__(self) -> bool:
        return self.passou


def sem_melodia(frase: Frase) -> Veredito:
    """Todas as notas na mesma altura: é recitação em monotom, não melodia."""
    alturas = {n.midi for n in frase.notas}
    if len(alturas) <= 1:
        return Veredito(False, "sem_melodia",
                        f"todas as {len(frase.notas)} notas na mesma altura")
    return Veredito(True)


def quase_sem_melodia(frase: Frase) -> Veredito:
    """Duas alturas para oito notas ou mais.

    O limiar é sobre o número de alturas DISPONÍVEIS, não sobre gosto: uma
    frase longa que usa duas alturas não explorou o modo, é alternância. Frases
    curtas escapam, porque aí duas alturas podem ser a frase inteira.
    """
    alturas = {n.midi for n in frase.notas}
    if len(frase.notas) >= 8 and len(alturas) <= 2:
        return Veredito(False, "quase_sem_melodia",
                        f"{len(alturas)} alturas em {len(frase.notas)} notas")
    return Veredito(True)


# A peneira inteira. Acrescentar algo aqui exige mostrar que o rejeitado não é
# melodia — ver a regra no topo do módulo.
PENEIRA = (sem_melodia, quase_sem_melodia)


def peneirar(frase: Frase) -> Veredito:
    """Aplica a peneira. Devolve o primeiro veredito de reprovação, ou aprovação."""
    for filtro in PENEIRA:
        veredito = filtro(frase)
        if not veredito.passou:
            return veredito
    return Veredito(True)


def relatorio(frases: list[Frase]) -> dict:
    """Quanto a peneira cortou, e por qual filtro. Serve para vigiar o próprio
    módulo: se a taxa de corte subir muito acima de 1%, alguém pôs gosto aqui."""
    vereditos = [peneirar(f) for f in frases]
    reprovados = [v for v in vereditos if not v.passou]
    por_filtro: dict[str, int] = {}
    for v in reprovados:
        por_filtro[v.filtro] = por_filtro.get(v.filtro, 0) + 1
    total = len(frases) or 1
    return {
        "avaliadas": len(frases),
        "reprovadas": len(reprovados),
        "taxa_de_corte": round(len(reprovados) / total, 6),
        "por_filtro": por_filtro,
        "aviso": None if len(reprovados) / total <= 0.01 else
                 "taxa de corte acima de 1%: a peneira deveria rejeitar só o "
                 "degenerado — confira se não entrou critério de gosto",
    }
