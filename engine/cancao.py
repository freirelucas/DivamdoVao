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
A canção — o objeto que faltava, e o livro-razão que o torna honesto.

O QUE ESTE MÓDULO É
-------------------
Até aqui o projeto produzia MELODIAS: uma frase por verso, ritmo derivado do
aruz, alturas num modo. Uma canção não é isso. Uma canção tem seções, forma,
tom, letra, cadências e arranjo — e a auditoria crítica deste repositório
apontava, desde o começo, que esse objeto não existia.

Ele existe aqui. E existe com uma exigência que o resto do projeto impõe: cada
camada declara DE ONDE VEM. Porque a tentação, num objeto deste tamanho, é
apresentar a canção inteira como "derivada de Rumi" quando só o ritmo é.

AS QUATRO GARANTIAS
-------------------
  derivado          Sai da fonte por regra, e a regra é conferível. O ritmo
                    (escansão do aruz), o lugar das cadências (onde cai a rima),
                    a cabeça separada (onde há taṣrīʿ), o refrão (onde há radīf).
  constrangido      Não sai da fonte, mas a fonte limita. O número de sílabas da
                    letra em português: o aruz não escolhe as palavras, mas diz
                    quantas posições há e qual a quantidade de cada uma.
  hipotese_rotulada Pode soar melhor, e é palpite derivado da tese do projeto.
                    Entra marcado, e o julgamento do autor confirma ou mata.
  autoral           Escolha do autor. A harmonia, a cor, o modo, o arranjo, o
                    timbre, e a letra em português. NÃO é defeito — é a obra.
                    O defeito seria chamar isso de derivado.

POR QUE A HARMONIA É AUTORAL, E ISSO NÃO É MODÉSTIA
---------------------------------------------------
O aruz é sistema de QUANTIDADE silábica. Não tem altura, não tem acorde, não
tem função. A música clássica árabe e persa é modal e essencialmente não
harmônica no sentido europeu. Logo, harmonia funcional não pode ser derivada
do poema: ela é importação, e neste projeto é a importação deliberada do Clube
da Esquina.

O que a fonte dá é PERIODICIDADE: a qasida e o gazal rimam na mesma sílaba do
primeiro ao último dístico, e isso é contável. Rima no texto licencia rima na
harmonia. Então o LUGAR das cadências é derivado, e QUAL acorde cadencia é
autoral. O plano harmônico aqui separa as duas coisas em campos diferentes, de
propósito, para que nenhuma saída possa confundi-las.

Só stdlib. Função pura onde possível. Nenhuma rede.
"""
from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
# rodando como script, sys.path[0] é engine/ e os imports de pacote falham; a
# raiz entra antes deles. Mesmo arranjo de engine/pipeline.py.
if __name__ == "__main__" and str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

from engine.complexidade import (ajuste_prosodico, compasso_natural,
                                 contagem_cantada, elidir_para,
                                 separar_silabas_pt, silabar_pt)
from engine.forma import cadencias as cadencias_da_forma
from engine.forma import radif_do_poema, rima_do_poema, tem_tasri
from engine.generative import (DUR_ARUZ, MODOS, Frase, conferir_metro,
                               durar_por_aruz, expandir_escansao, gerar_melodia,
                               relatorio_auditoria, silabas_do_verso)
from engine.ritmo import OPERACOES

GARANTIAS = {
    "derivado": ("Sai da fonte por regra conferível. Se isto estiver errado, é defeito "
                 "do código, não escolha de ninguém."),
    "constrangido": ("Não sai da fonte, mas a fonte limita o que pode ser. Há liberdade "
                     "dentro de um molde que a fonte determina."),
    "hipotese_rotulada": ("Palpite derivado da tese do projeto. Entra marcado e espera o "
                          "julgamento do autor, que confirma ou mata."),
    "autoral": ("Escolha do autor. É a obra, não uma lacuna. Chamar isto de derivado "
                "seria fabricação."),
}

# ---------------------------------------------------------------------------
# harmonia: o vocabulário é mecânico, a escolha é autoral
# ---------------------------------------------------------------------------

NOMES_GRAU = ["I", "II", "III", "IV", "V", "VI", "VII"]
_PC = ["C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B"]


def _qualidade(intervalos: tuple[int, int, int]) -> str:
    """Nomeia a tétrade pelos seus intervalos, sem tabela de exceções."""
    t, q, s = intervalos
    return {(4, 7, 11): "maj7", (4, 7, 10): "7", (3, 7, 10): "m7",
            (3, 6, 10): "m7b5", (3, 7, 11): "mMaj7", (4, 8, 11): "maj7#5",
            (3, 6, 9): "dim7"}.get((t, q, s), f"?{t}-{q}-{s}")


def acordes_do_modo(modo: str, tonica_midi: int = 62) -> list[dict]:
    """As sete tétrades construídas com as notas do próprio modo.

    Mecânico: empilha 1-3-5-7 sobre cada grau usando só as alturas do modo. Não
    é escolha estética — é o que o modo contém. A escolha estética é qual
    destes acordes se usa e quando, e essa fica em PREFERENCIA_CADENCIAL,
    marcada como autoral.
    """
    if modo not in MODOS:
        raise ValueError(f"modo desconhecido: {modo!r}")
    g = MODOS[modo]
    n = len(g)
    saida = []
    for i in range(n):
        graus = [g[(i + k) % n] + 12 * ((i + k) // n) for k in (0, 2, 4, 6)]
        inter = tuple(x - graus[0] for x in graus[1:])
        raiz = (tonica_midi + g[i]) % 12
        saida.append({
            "grau": NOMES_GRAU[i],
            "raiz_midi": tonica_midi + g[i],
            "raiz": _PC[raiz],
            "qualidade": _qualidade(inter),  # type: ignore[arg-type]
            "notas_midi": [tonica_midi + x for x in graus],
            "cifra": f"{_PC[raiz]}{_qualidade(inter)}",  # type: ignore[arg-type]
        })
    return saida


# ESCOLHA AUTORAL, declarada como tal. Diz em que grau do modo cada tipo de
# cadência repousa. Trocar isto troca a cor da canção e não quebra nada do
# rastro de auditoria — é exatamente o grau de liberdade que o autor tem.
PREFERENCIA_CADENCIAL = {
    "dorico": {"cadencia": "I", "meia_cadencia": "IV", "cabeca": "VII",
               "por_que": "o IV maior do dórico é a cor mineira; o bVII abre a cabeça"},
    "eolio": {"cadencia": "I", "meia_cadencia": "VI", "cabeca": "III",
              "por_que": "menor natural: o VI é o repouso melancólico"},
    "lidio": {"cadencia": "I", "meia_cadencia": "II", "cabeca": "V",
              "por_que": "a 4ª aumentada pede o II como suspensão brilhante"},
    "mixolidio": {"cadencia": "I", "meia_cadencia": "VII", "cabeca": "IV",
                  "por_que": "o bVII do mixolídio é a dominante suave"},
}


# ---------------------------------------------------------------------------
# o molde da letra: a fonte não escreve a letra, mas diz a forma dela
# ---------------------------------------------------------------------------

def molde_da_letra(verso: dict) -> dict:
    """O molde métrico em que a letra em português tem de caber.

    Isto é o coração da co-produção que o projeto prometeu desde o primeiro
    documento e nunca entregou: a máquina NÃO escreve a letra. Ela guarda o
    molde — quantas sílabas, qual longa, qual curta, quanto dura cada uma — e
    confere se o português do autor cabe.

    Garantia: constrangido. O aruz não escolhe palavra nenhuma; só diz quantas
    posições há e qual a quantidade de cada posição.
    """
    esc = verso["escansao"]
    durs = durar_por_aruz(esc)
    rot, conferidas = silabas_do_verso(verso)
    return {
        "verso_id": verso["id"],
        "n_silabas": len(esc),
        "escansao": list(esc),
        "duracoes_quarters": durs,
        "duracao_total": round(sum(durs), 4),
        "posicoes_longas": [i + 1 for i, s in enumerate(esc) if s in ("–", "=")],
        "posicoes_curtas": [i + 1 for i, s in enumerate(esc) if s == "u"],
        "rotulos_da_fonte": rot,
        "silabas_da_fonte_conferidas": conferidas,
        "_garantia": "constrangido",
        "_o_que_isto_e": ("O molde, não a letra. A letra em português é autoral; este "
                          "campo só diz em que forma ela tem de caber para que uma "
                          "sílaba continue valendo uma nota."),
    }


def conferir_letra(verso: dict, letra_pt: str, frase: Frase | None = None) -> dict:
    """Confere a letra do autor contra o molde, e diz onde não encaixa.

    Duas conferências: a de CONTAGEM (sílabas do português contra posições do
    aruz) e a PROSÓDICA (tônica do português caindo em sílaba longa do aruz),
    que engine/complexidade.py já sabe medir.
    """
    molde = molde_da_letra(verso)
    # Contagem CANTADA, não escrita. O português cantado funde a vogal final de
    # uma palavra com a inicial da seguinte — "escuta o junco" se canta
    # es-cu-ta_o-jun-co —, e a metrificação portuguesa sempre contou assim.
    # Sem isso o molde rejeitava letra que de fato cabe: na primeira rodada
    # toda candidata "estourava" por sílabas que o canto funde sozinho.
    cc = contagem_cantada(letra_pt)
    palavras = cc["silabacao"]
    hifenizada = "-" in letra_pt
    silabas = cc["silabas"]
    n = cc["n_escritas"]
    minimo, maximo = cc["intervalo"]
    esperado = molde["n_silabas"]
    encaixa = minimo <= esperado <= maximo
    saida = {
        "letra": letra_pt,
        "silabas_do_portugues": silabas,
        "n_silabas_escritas": n,
        "n_silabas_cantadas": minimo,
        "intervalo_cantavel": [minimo, maximo],
        "n_posicoes_do_aruz": esperado,
        "encaixa_na_contagem": encaixa,
        "elisoes_necessarias": (n - esperado) if encaixa else None,
        "elisoes_possiveis": [x["funde_em"] for x in cc["elisoes_possiveis"]],
        "sobra_ou_falta": 0 if encaixa else (minimo - esperado if esperado < minimo
                                             else esperado - maximo),
        "silabacao": [" - ".join(x) for x in palavras],
        "silabacao_veio_do_autor": hifenizada,
        "_sobre_a_contagem": (
            "A letra encaixa se as posições do aruz caírem entre a contagem cantada "
            "(com toda elisão) e a escrita (com nenhuma): a elisão é escolha de quem "
            "canta, não regra."),
        "_sobre_a_silabacao": (
            "divisão feita pelo autor, por hífen" if hifenizada else
            "divisão automática por regra (acerta 98,7% da lista de prova de "
            "engine/complexidade.py). Para corrigir, escreva a letra com hífens: "
            "o hífen do autor sempre vence a regra."),
        "molde": molde,
    }
    if frase is None:
        frase = gerar_melodia(verso)
    if encaixa:
        saida["prosodia"] = ajuste_prosodico(frase, letra_pt)
        saida["o_que_fazer"] = (
            f"cabe: cante {esperado} sílabas usando {n - esperado} das "
            f"{len(saida['elisoes_possiveis'])} elisões possíveis"
            if n > esperado else "cabe sem elisão nenhuma")
    else:
        saida["prosodia"] = None
        falta = esperado - maximo if esperado > maximo else minimo - esperado
        saida["o_que_fazer"] = (
            f"não cabe: o verso tem {esperado} posições e a letra canta entre "
            f"{minimo} e {maximo} sílabas. "
            + (f"Acrescente {falta} sílaba(s)." if esperado > maximo
               else f"Corte {falta} sílaba(s), ou crie contato de vogais para elidir."))
    return saida


# ---------------------------------------------------------------------------
# seções
# ---------------------------------------------------------------------------

@dataclass
class Secao:
    """Um trecho da canção, com os versos que o compõem e a razão de existir."""
    nome: str
    papel: str
    versos: list[dict]
    modo: str = "dorico"
    operacao: str = ""
    garantia_do_papel: str = "autoral"
    por_que: str = ""

    def duracao_quarters(self) -> float:
        return round(sum(sum(durar_por_aruz(v["escansao"])) for v in self.versos), 4)


def secionar(coplas: list[tuple[str, ...]], versos: list[dict], *,
             por_copla: int = 2, modo: str = "dorico") -> list[Secao]:
    """Divide os dísticos em seções, derivando o que a forma marca.

    O que é DERIVADO: a cabeça. Onde há taṣrīʿ — os dois hemistíquios do
    primeiro dístico rimando — a fonte está marcando a abertura como
    formalmente distinta, e tratá-la como cabeça da canção é consequência disso,
    não gosto nosso.

    O que é AUTORAL: todo o resto do agrupamento. Quantos dísticos por seção,
    onde entra o refrão, se há coda. A qasida tem forma tripartite documentada
    (nasīb → raḥīl → gharaḍ), mas detectá-la automaticamente exigiria ler o
    assunto do poema, e ler assunto por palavra-chave seria palpite. Então o
    agrupamento é por posição, e fica declarado como escolha.
    """
    r = rima_do_poema(coplas)
    d = radif_do_poema(coplas)
    cabeca = tem_tasri(coplas[0], r["rima"], d.get("radif", "")) if coplas else False

    # versos vêm em hemistíquios; dois por dístico
    por_distico: list[list[dict]] = [versos[i:i + 2] for i in range(0, len(versos), 2)]
    secoes: list[Secao] = []
    i = 0
    if cabeca and por_distico:
        secoes.append(Secao(
            nome="cabeça", papel="maṭlaʿ", versos=por_distico[0], modo=modo,
            garantia_do_papel="derivado",
            por_que=("há taṣrīʿ: os dois hemistíquios do primeiro dístico rimam, e a "
                     "fonte marca a abertura como formalmente distinta")))
        i = 1
    letras = "ABCDEFGH"
    k = 0
    while i < len(por_distico):
        bloco = [v for d2 in por_distico[i:i + por_copla] for v in d2]
        secoes.append(Secao(
            nome=letras[k % len(letras)], papel="corpo", versos=bloco, modo=modo,
            garantia_do_papel="autoral",
            por_que=(f"agrupamento de {por_copla} dísticos por seção — escolha de forma, "
                     "não propriedade da fonte")))
        i += por_copla
        k += 1
    return secoes


# ---------------------------------------------------------------------------
# a canção
# ---------------------------------------------------------------------------

@dataclass
class Cancao:
    """A canção montada: seções, tom, compasso, plano harmônico e letra."""
    id: str
    titulo: str
    secoes: list[Secao]
    metros: dict
    tonica_midi: int = 62
    bpm: int = 88
    compasso: float = 0.0            # 0 = deixar o metro decidir
    letra: dict[str, str] = field(default_factory=dict)
    semente: str = "diva"
    motivico: bool = True

    # ---- derivados ----

    def coplas(self) -> list[tuple[str, ...]]:
        vs = [v for s in self.secoes for v in s.versos]
        return [tuple(v["persa"] for v in vs[i:i + 2]) for i in range(0, len(vs), 2)]

    def versos(self) -> list[dict]:
        return [v for s in self.secoes for v in s.versos]

    def compasso_efetivo(self) -> dict:
        """O compasso: o pé do metro decide, e isso é derivado."""
        if self.compasso:
            return {"quarters": self.compasso, "_garantia": "autoral",
                    "por_que": "compasso fixado à mão, sobrepondo o do metro"}
        v = self.versos()[0]
        cn = compasso_natural(v, self.metros)
        if not cn.get("aplicavel"):
            return {"quarters": 4.0, "_garantia": "autoral",
                    "por_que": "o metro não declara pé: 4/4 por omissão, não por derivação",
                    "detalhe": cn}
        if cn.get("compasso_sugerido"):
            q = cn["compasso_sugerido"]
            return {"quarters": q, "_garantia": "derivado",
                    "por_que": (f"o pé do metro {v.get('metro')} mede {q} quarters "
                                f"({int(q / 0.5)} colcheias)"),
                    "detalhe": cn}
        # Pés ALTERNADOS (o rajaz mosamman matvi makhbun, por exemplo) não têm um
        # pé único que meça a barra. Mas o CICLO dos pés se repete, e a soma do
        # ciclo é tão derivável quanto a do pé: é a menor unidade que volta igual.
        ciclo = sum(cn["duracao_do_pe"])
        return {"quarters": ciclo, "_garantia": "derivado",
                "por_que": (f"o metro {v.get('metro')} tem pés alternados "
                            f"({' + '.join(str(d) for d in cn['duracao_do_pe'])}); a barra "
                            f"é o ciclo inteiro, {ciclo} quarters, que é a menor unidade "
                            f"que volta igual"),
                "detalhe": cn}

    def frases(self) -> dict[str, list[Frase]]:
        """Uma frase melódica por verso, por seção."""
        saida: dict[str, list[Frase]] = {}
        for s in self.secoes:
            fs = []
            for j, v in enumerate(s.versos):
                f = gerar_melodia(v, modo=s.modo, tonica_midi=self.tonica_midi,
                                  semente=f"{self.semente}:{s.nome}:{j}",
                                  motivico=self.motivico, metros=self.metros)
                if s.operacao:
                    f = OPERACOES[s.operacao](f)
                    if isinstance(f, tuple):
                        f = f[0]
                fs.append(f)
            saida[s.nome] = fs
        return saida

    def plano_harmonico(self) -> dict:
        """Onde cadenciar (derivado) e em que acorde (autoral), em campos separados.

        A separação é o ponto. Juntar as duas coisas num só campo "harmonia"
        permitiria apresentar a cor Clube da Esquina como consequência do aruz,
        que é falso.
        """
        cop = self.coplas()
        cad = cadencias_da_forma(cop)
        modo = self.secoes[0].modo if self.secoes else "dorico"
        vocab = acordes_do_modo(modo, self.tonica_midi)
        por_grau = {a["grau"]: a for a in vocab}
        pref = PREFERENCIA_CADENCIAL.get(modo, PREFERENCIA_CADENCIAL["dorico"])

        pontos = []
        for p in cad["pontos"]:
            tipo = p["tipo"]
            grau = pref["cabeca"] if (p["bayt"] == 1 and cad["cabeca_separada"]
                                      and tipo == "cadência") else \
                   pref["cadencia"] if tipo == "cadência" else pref["meia_cadencia"]
            pontos.append({
                "bayt": p["bayt"], "em": p["em"], "tipo": tipo,
                "lugar_por_que": p["por_que"],
                "lugar_garantia": "derivado",
                "grau": grau, "cifra": por_grau[grau]["cifra"],
                "notas_midi": por_grau[grau]["notas_midi"],
                "acorde_garantia": "autoral",
            })
        return {
            "modo": modo,
            "vocabulario": vocab,
            "vocabulario_garantia": "constrangido",
            "_vocabulario_por_que": ("as sete tétrades são empilhadas com as notas do "
                                     "próprio modo: mecânico, não estético"),
            "preferencia_cadencial": pref,
            "preferencia_garantia": "autoral",
            "pontos": pontos,
            "refrao_dado_pela_fonte": cad["refrao_dado_pela_fonte"],
            "rima": cad["rima"], "radif": cad["radif"],
            "tasri_na_abertura": cad["tasri_na_abertura"],
            "_fronteira": ("O LUGAR de cada cadência é derivado: cai onde cai a rima, que "
                           "é contável no texto. QUAL acorde cadencia é autoral: o aruz "
                           "não tem altura nem função harmônica, e a música clássica "
                           "árabe e persa é modal. Os dois campos ficam separados para "
                           "que nenhuma saída possa confundi-los."),
        }

    def moldes(self) -> list[dict]:
        return [molde_da_letra(v) for v in self.versos()]

    def conferir_a_letra(self) -> dict:
        """Confere a letra escrita até agora contra os moldes."""
        fr = self.frases()
        linhas, ok, faltam = [], 0, 0
        for s in self.secoes:
            fs = fr[s.nome]
            for j, v in enumerate(s.versos):
                lt = self.letra.get(v["id"], "")
                if not lt:
                    faltam += 1
                    linhas.append({"verso_id": v["id"], "secao": s.nome,
                                   "estado": "sem letra",
                                   "molde": molde_da_letra(v)})
                    continue
                c = conferir_letra(v, lt, fs[j])
                ok += bool(c["encaixa_na_contagem"])
                linhas.append({"verso_id": v["id"], "secao": s.nome,
                               "estado": "encaixa" if c["encaixa_na_contagem"]
                                         else "não encaixa", **c})
        total = len(self.versos())
        return {"n_versos": total, "com_letra": total - faltam, "sem_letra": faltam,
                "encaixam": ok, "linhas": linhas,
                "_garantia": "constrangido",
                "_o_que_isto_e": ("A letra é autoral; o molde é constrangido pela fonte. "
                                  "Esta conferência não escreve nada — só diz onde o "
                                  "português não cabe no aruz.")}

    def auditoria(self) -> dict:
        """O livro-razão: toda camada da canção, com sua garantia.

        É este relatório que distingue a canção de uma saída de gerador opaco —
        e é ele que impede o projeto de apresentar a sua harmonia como se fosse
        de Rumi.
        """
        comp = self.compasso_efetivo()
        ph = self.plano_harmonico()
        fr = self.frases()
        por_secao = []
        for s in self.secoes:
            fs = fr[s.nome]
            por_secao.append({
                "nome": s.nome, "papel": s.papel,
                "papel_garantia": s.garantia_do_papel, "papel_por_que": s.por_que,
                "n_versos": len(s.versos), "versos": [v["id"] for v in s.versos],
                "modo": s.modo, "modo_garantia": "autoral",
                "operacao_ritmica": s.operacao or None,
                "operacao_garantia": "autoral" if s.operacao else None,
                "duracao_quarters": s.duracao_quarters(),
                "n_notas": sum(len(f.notas) for f in fs),
                "conferencia_metro": [conferir_metro(v, self.metros)["conforme"]
                                      for v in s.versos],
            })
        camadas = {
            "ritmo": {"garantia": "derivado",
                      "de_onde": "escansão do aruz; dur = DUR_ARUZ[símbolo], final longa"},
            "compasso": {"garantia": comp["_garantia"], "de_onde": comp["por_que"]},
            "forma_cabeca": {"garantia": "derivado" if ph["tasri_na_abertura"] else "autoral",
                             "de_onde": ("taṣrīʿ no primeiro dístico" if ph["tasri_na_abertura"]
                                         else "sem taṣrīʿ: a cabeça é escolha de forma")},
            "forma_agrupamento": {"garantia": "autoral",
                                  "de_onde": "quantos dísticos por seção"},
            "lugar_das_cadencias": {"garantia": "derivado",
                                    "de_onde": f"onde cai a rima {ph['rima']['rima']!r} "
                                               f"(cobertura {ph['rima']['cobertura']})"},
            "vocabulario_harmonico": {"garantia": "constrangido",
                                      "de_onde": "tétrades do próprio modo"},
            "escolha_dos_acordes": {"garantia": "autoral",
                                    "de_onde": "PREFERENCIA_CADENCIAL — cor do autor"},
            "refrao": {"garantia": "derivado" if ph["refrao_dado_pela_fonte"] else "autoral",
                       "de_onde": (f"radīf {ph['radif']['radif']!r} repetido pela fonte"
                                   if ph["refrao_dado_pela_fonte"]
                                   else "sem radīf: o estribilho é invenção do autor")},
            "alturas_da_melodia": {"garantia": "constrangido",
                                   "de_onde": ("todo grau pertence ao modo e ao âmbito; o "
                                               "contorno é passeio com semente fixa")},
            "contorno_motivico": {"garantia": "hipotese_rotulada" if self.motivico else None,
                                  "de_onde": ("o pé seguinte varia o contorno do primeiro; "
                                              "que soe melhor é hipótese"
                                              if self.motivico else None)},
            "letra_em_portugues": {"garantia": "autoral",
                                   "de_onde": "recriação do autor, no molde do aruz"},
            "molde_da_letra": {"garantia": "constrangido",
                               "de_onde": "nº de posições e quantidade de cada uma"},
            "tom_timbre_arranjo": {"garantia": "autoral",
                                   "de_onde": "escolha do autor"},
        }
        contagem: dict[str, int] = {}
        for c in camadas.values():
            if c.get("garantia"):
                contagem[c["garantia"]] = contagem.get(c["garantia"], 0) + 1
        return {
            "cancao": self.id, "titulo": self.titulo,
            "n_secoes": len(self.secoes), "n_versos": len(self.versos()),
            "tonica_midi": self.tonica_midi, "bpm": self.bpm,
            "compasso": comp,
            "duracao_total_quarters": round(sum(s.duracao_quarters()
                                                for s in self.secoes), 4),
            "duracao_total_segundos": round(sum(s.duracao_quarters()
                                                for s in self.secoes) * 60 / self.bpm, 1),
            "secoes": por_secao,
            "plano_harmonico": ph,
            "letra": self.conferir_a_letra(),
            "camadas": camadas,
            "resumo_das_garantias": contagem,
            "_garantias": GARANTIAS,
            "_a_fronteira_que_importa": (
                "O ritmo é de Rumi. A harmonia é do autor. O lugar das cadências é da "
                "fonte; a cor delas é do autor. A letra em português é do autor, num "
                "molde que a fonte determina. Nenhuma dessas linhas é modéstia: "
                "trocá-las de lugar seria a fabricação que engine/filtros.py registra."),
        }


def montar(versos: list[dict], metros: dict, *, titulo: str = "",
           id: str = "cancao", modo: str = "dorico", tonica_midi: int = 62,
           bpm: int = 88, por_copla: int = 2, letra: dict | None = None,
           semente: str = "diva", motivico: bool = True) -> Cancao:
    """Monta a canção a partir de versos escolhidos, na ordem em que vierem."""
    if not versos:
        raise ValueError("sem versos: não há canção a montar")
    coplas = [tuple(v["persa"] for v in versos[i:i + 2])
              for i in range(0, len(versos), 2)]
    secoes = secionar(coplas, versos, por_copla=por_copla, modo=modo)
    return Cancao(id=id, titulo=titulo or id, secoes=secoes, metros=metros,
                  tonica_midi=tonica_midi, bpm=bpm, letra=letra or {},
                  semente=semente, motivico=motivico)


def escrever_cancao(c: Cancao, destino: str | Path, nome: str = "") -> list[Path]:
    """Grava a canção: uma partitura e um MIDI por seção, e a auditoria inteira."""
    from engine.export import escrever
    destino = Path(destino)
    destino.mkdir(parents=True, exist_ok=True)
    nome = nome or c.id
    comp = c.compasso_efetivo()["quarters"]
    fr = c.frases()
    escritos: list[Path] = []
    for s in c.secoes:
        for j, (v, f) in enumerate(zip(s.versos, fr[s.nome])):
            rel = relatorio_auditoria(f, v, c.metros)
            # a partitura exige uma sílaba por nota — é o compromisso do
            # projeto, e o exportador recusa qualquer outra coisa. Então o que
            # vai para lá é a letra JÁ ELIDIDA no número de notas, não a linha
            # inteira: "Escuta o junco…" vira es·cu·ta_o·jun·co…, 11 sílabas
            # para 11 notas.
            silabas = None
            if v["id"] in c.letra:
                e = elidir_para(c.letra[v["id"]], len(f.notas))
                if e.get("aplicavel"):
                    silabas = e["silabas"]
                    rel["letra_elidida"] = {
                        "silabas": silabas,
                        "elisoes_aplicadas": e["elisoes_aplicadas"],
                        "_garantia": "autoral (a letra) sobre molde constrangido (o aruz)"}
                else:
                    rel["letra_nao_encaixou"] = {
                        "letra": c.letra[v["id"]], "motivo": e.get("motivo", ""),
                        "n_notas": len(f.notas)}
            escritos += escrever(f, rel, destino, f"{nome}_{s.nome}_{j + 1}",
                                 titulo=f"{c.titulo} — {s.nome}", compasso=comp,
                                 letra=silabas)
    arq = destino / f"{nome}_cancao.json"
    arq.write_text(json.dumps(c.auditoria(), ensure_ascii=False, indent=1) + "\n",
                   encoding="utf-8")
    escritos.append(arq)
    return escritos


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _carregar(corpus: str) -> dict:
    return json.loads(Path(corpus).read_text(encoding="utf-8"))


def _cli(argv: list[str]) -> int:
    import argparse
    ap = argparse.ArgumentParser(
        description="Monta uma canção a partir de versos do corpus, com o livro-razão "
                    "das garantias.",
        epilog="Exemplos:\n"
               "  %(prog)s --poema https://ganjoor.net/moulavi/shams/ghazalsh/sh1\n"
               "  %(prog)s --poema <url> --modo lidio --por-copla 3 --json\n"
               "  %(prog)s --verso masnavi_1 --letra 'Escuta o junco: ele conta a dor que tem'\n"
               "  %(prog)s --poema <url> --export /tmp/saida",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--corpus", default=str(RAIZ / "data/corpus_colhido.json"))
    ap.add_argument("--poema", help="url de origem: usa todos os versos daquele poema")
    ap.add_argument("--verso", action="append", default=[], help="id de verso (repetível)")
    ap.add_argument("--modo", default="dorico", choices=sorted(MODOS))
    ap.add_argument("--tonica", type=int, default=62)
    ap.add_argument("--bpm", type=int, default=88)
    ap.add_argument("--por-copla", type=int, default=2)
    ap.add_argument("--letra", help="letra em português para o primeiro verso")
    ap.add_argument("--titulo", default="")
    ap.add_argument("--export", help="diretório onde gravar partituras, MIDI e auditoria")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args(argv)

    c = _carregar(a.corpus)
    if a.poema:
        vs = [v for v in c["versos"] if v.get("_origem", {}).get("url") == a.poema]
        vs.sort(key=lambda v: (int(str(v["_origem"]["copla"]).lstrip("bn") or 0),
                               v["_origem"]["hemistiquio"]))
    elif a.verso:
        por_id = {v["id"]: v for v in c["versos"]}
        faltam = [i for i in a.verso if i not in por_id]
        if faltam:
            ap.error(f"verso(s) não encontrado(s): {', '.join(faltam)}")
        vs = [por_id[i] for i in a.verso]
    else:
        ap.error("informe --poema ou --verso")
    if not vs:
        ap.error("nenhum verso encontrado para esse poema")

    letra = {vs[0]["id"]: a.letra} if a.letra else {}
    can = montar(vs, c["metros"], titulo=a.titulo or (vs[0].get("obra") or "canção"),
                 id="cancao", modo=a.modo, tonica_midi=a.tonica, bpm=a.bpm,
                 por_copla=a.por_copla, letra=letra)
    aud = can.auditoria()

    if a.json:
        print(json.dumps(aud, ensure_ascii=False, indent=1))
    else:
        print(f"{aud['titulo']}")
        print(f"  {aud['n_secoes']} seções · {aud['n_versos']} versos · "
              f"{aud['duracao_total_quarters']} quarters = "
              f"{aud['duracao_total_segundos']}s a {aud['bpm']} bpm")
        cp = aud["compasso"]
        print(f"  compasso {cp['quarters']} [{cp['_garantia']}] — {cp['por_que']}")
        print("\n  SEÇÕES")
        for s in aud["secoes"]:
            print(f"    {s['nome']:8s} {s['papel']:8s} [{s['papel_garantia']:9s}] "
                  f"{s['n_versos']} versos, {s['n_notas']} notas")
        ph = aud["plano_harmonico"]
        print(f"\n  FORMA MEDIDA NO TEXTO")
        print(f"    rima {ph['rima']['rima']!r} (cobertura {ph['rima']['cobertura']}) · "
              f"taṣrīʿ {ph['tasri_na_abertura']} · refrão da fonte "
              f"{ph['refrao_dado_pela_fonte']}")
        print(f"\n  CADÊNCIAS  (lugar derivado · acorde autoral)")
        for p in ph["pontos"][:8]:
            print(f"    bayt {p['bayt']:2d} {p['em']:14s} {p['tipo']:14s} "
                  f"{p['grau']:4s} {p['cifra']}")
        if len(ph["pontos"]) > 8:
            print(f"    ... +{len(ph['pontos']) - 8} pontos")
        print(f"\n  LIVRO-RAZÃO")
        for k, v in aud["camadas"].items():
            if v.get("garantia"):
                print(f"    {k:24s} {v['garantia']:18s} {v['de_onde'][:52]}")
        print(f"\n    resumo: {aud['resumo_das_garantias']}")
        lt = aud["letra"]
        print(f"\n  LETRA  {lt['com_letra']}/{lt['n_versos']} versos com letra, "
              f"{lt['encaixam']} encaixam")
        for l in lt["linhas"]:
            if l["estado"] == "sem letra":
                continue
            print(f"    [{l['estado']}] {l['verso_id']}: «{l['letra']}»")
            print(f"      {l['o_que_fazer']}")
            if l.get("prosodia") and l["prosodia"].get("aplicavel"):
                pr = l["prosodia"]
                print(f"      ajuste prosódico {pr['ajuste']} "
                      f"({pr['tonicas_em_longa']}/{pr['tonicas']} tônicas em longa)")
        print(f"\n  {aud['_a_fronteira_que_importa']}")

    if a.export:
        for p in escrever_cancao(can, a.export):
            print(f"gravado: {p}")
    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
