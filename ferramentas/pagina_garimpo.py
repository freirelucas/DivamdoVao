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
Gera a página do Garimpo — a exploração das pontes, para olhar em vez de ler log.

Monta uma página só com HTML e CSS (nenhuma dependência, nenhum dado externo)
a partir de tres fontes do próprio repositório: data/pontes.json, o índice do
corpus árabe, e as medidas de engine/forma.py. O estatuto epistêmico de cada
ponte é a estrutura visual da página, não um rodapé: sete das doze pontes são
leitura do autor, uma é genealogia contestada, e um achado bonito faz esquecer
disso em dois minutos.

A cor vermelha é rubricação. Nos manuscritos árabes o vermelho marca estrutura;
aqui marca o que exige cuidado.

    python3 ferramentas/pagina_garimpo.py --saida /tmp/garimpo.html
"""
from __future__ import annotations

import argparse
import html
import json
import sqlite3
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))

from ferramentas.garimpar import carregar_pontes, garimpar, panorama  # noqa: E402

CABECA = Path(__file__).resolve().parent / "modelos/garimpo_cabeca.html"

BADGE = {"fato_da_fonte": ("b-fato", "fato da fonte"),
         "paralelo_formal_observavel": ("b-par", "paralelo formal observável"),
         "comparacao_academica": ("b-acad", "comparação acadêmica"),
         "genealogia_contestada": ("b-cont", "genealogia contestada"),
         "leitura_autoral": ("b-aut", "leitura do autor")}
ORDEM = list(BADGE)

# medidas de forma, obtidas rodando engine/forma.py nos dois corpora
MEDIDAS = {
    "persa": {"n": 145, "monorrima": 97.9, "tasri": 94.5, "radif": 58.6,
              "rotulo": "Persa — gazais de Rumi"},
    "arabe": {"n": 1200, "monorrima": 84.7, "tasri": 32.9, "radif": 0.0,
              "rotulo": "Árabe — amostra do índice"},
    "leitura": ("O radīf em 0,0% no árabe contra 58,6% no persa confirma uma previsão: a "
                "palavra que se repete depois da rima é recurso persa/urdu, não árabe. Na "
                "prática: 6 de cada 10 gazais de Rumi entregam um refrão de uma palavra já "
                "pronto; o árabe entrega só a rima, e o estribilho fica por conta do autor."),
}


def _n(x: int) -> str:
    return f"{x:,}".replace(",", ".")


def montar(indice: Path, pontes_json: Path | None = None) -> str:
    e = html.escape
    pontes = carregar_pontes(pontes_json)
    meta = pontes["_meta"]
    con = sqlite3.connect(f"file:{indice}?mode=ro", uri=True)
    pan = {l["ponte"]: l["hemistiquios"] for l in panorama(con, pontes)}
    corpus = {
        "poemas": con.execute("SELECT count(*) FROM poemas").fetchone()[0],
        "hemistiquios": con.execute("SELECT count(*) FROM hemistiquios").fetchone()[0],
        "poetas": con.execute("SELECT count(DISTINCT poeta) FROM poemas").fetchone()[0],
    }
    resumo = json.loads(con.execute(
        "SELECT valor FROM fonte WHERE chave='resumo_da_indexacao'").fetchone()[0])
    excluidos = resumo.get("pulados_por_era_moderna", 0)

    p = ['<div class="env">', '<p class="eyebrow">Divã do Vão · garimpo</p>',
         '<h1>Garimpo de Canção</h1>',
         '<p class="sub">Doze pontes entre os <i>topoi</i> da poesia árabe clássica e os '
         'registros da canção brasileira. Cada ponte diz em que você pode se apoiar e o que '
         'é leitura sua — e abre no verso que o corpus tem para oferecer.</p>', '<div class="nums">']
    for v, l in [(_n(corpus["poemas"]), "poemas indexados"),
                 (_n(corpus["hemistiquios"]), "hemistíquios"),
                 (_n(corpus["poetas"]), "poetas"),
                 (_n(excluidos), "excluídos por direitos")]:
        p.append(f'<div class="num"><b>{v}</b><span>{e(l)}</span></div>')
    p.append('</div>')

    p.append('<section><p class="eyebrow">O que cada marca quer dizer</p>'
             '<h2>Estatuto, não enfeite</h2>'
             f'<p class="sub">{e(meta["_por_que_declarar_estatuto"])}</p><div class="leg">')
    for k in ORDEM:
        cls, rot = BADGE[k]
        p.append(f'<div><span class="badge {cls}">{e(rot)}</span>'
                 f'<p>{e(meta["_estatutos"][k])}</p></div>')
    p.append('</div></section>')

    p.append('<hr class="r"><section><p class="eyebrow">Medido no texto, não no rótulo</p>'
             '<h2>A forma que o corpus entrega</h2>'
             '<p class="sub">Rima, abertura de rima dupla e palavra-refrão, contadas nos dois '
             'corpora. A última coluna é o resultado mais útil, porque nasceu de um erro meu '
             'corrigido — e a correção fez uma previsão que se confirmou.</p>'
             '<div class="rolo"><table class="tab"><thead><tr><th>corpus</th><th>amostra</th>'
             '<th>monorrima</th><th>taṣrīʿ</th><th>radīf</th></tr></thead><tbody>')
    for k in ("persa", "arabe"):
        x = MEDIDAS[k]
        cls = ' class="n zero"' if x["radif"] == 0.0 else ' class="n"'
        p.append(f'<tr><td>{e(x["rotulo"])}</td><td class="n">{_n(x["n"])}</td>'
                 f'<td class="n">{x["monorrima"]}%</td><td class="n">{x["tasri"]}%</td>'
                 f'<td{cls}>{x["radif"]}%</td></tr>')
    p.append('</tbody></table></div>'
             f'<div class="nota"><b>O zero importa.</b> {e(MEDIDAS["leitura"])}</div></section>')

    # o dístico onde três pontes se cruzam: a chuva que salva, os vestígios do
    # lugar perdido e a elegia, num só bayt de al-Khansāʾ. Vem do corpus, não
    # de curadoria minha a mão: é a consulta abaixo que o encontra.
    d = con.execute(
        "SELECT h.texto, h2.texto, p.poeta, p.era, p.metro, p.url "
        "  FROM hemistiquios h "
        "  JOIN hemistiquios h2 ON h2.poema_id=h.poema_id AND h2.bayt=h.bayt "
        "                      AND h2.metade=2 "
        "  JOIN poemas p ON p.id=h.poema_id "
        " WHERE h.metade=1 AND p.era LIKE '%الجاهلي%' AND h.texto LIKE '%سَقى%' "
        "   AND (h.texto LIKE '%جَدَث%' OR h2.texto LIKE '%الغَيث%') LIMIT 1").fetchone()
    if d:
        p.append('<hr class="r"><section><p class="eyebrow">Onde três pontes se cruzam</p>'
                 '<h2>Um dístico de al-Khansāʾ</h2>'
                 '<div class="ficha destaque"><div class="corpo" '
                 'style="display:block;border:0"><div class="copla" '
                 'style="border:0;padding-top:4px">'
                 f'<div class="v">{e(d[0])}</div><div class="v">{e(d[1])}</div>'
                 f'<div class="cred"><span>{e(d[2])}</span><span>{e(d[3])}</span>'
                 f'<span>metro {e(d[4])}</span>'
                 f'<a href="{e(d[5])}" target="_blank" rel="noopener">fonte</a></div></div>'
                 '<p style="margin-top:10px">A chuva que salva (<i>ghayth</i>), os vestígios '
                 'do lugar perdido (<i>aṭlāl</i>) e a elegia (<i>rithāʾ</i>) no mesmo bayt: '
                 'a maior elegista da poesia árabe pedindo que as chuvas da primavera reguem '
                 'um túmulo. Três pontes desta tabela se cruzam num verso, e a imagem é '
                 'exatamente a da canção que este projeto procura.</p></div></div></section>')

    p.append('<hr class="r"><section><p class="eyebrow">Doze pontes</p>'
             '<h2>Garimpar por tema</h2>'
             '<p class="sub">Ordenadas pelo material que cada uma alcança. Filtre pelo '
             'estatuto para ver só o que é fato, ou só o que é sua escolha.</p>'
             '<div class="filtros" role="group" aria-label="Filtrar por estatuto">'
             '<button class="chip" data-f="todos" aria-pressed="true">todas</button>')
    for k in ORDEM:
        p.append(f'<button class="chip" data-f="{k}" aria-pressed="false">'
                 f'{e(BADGE[k][1])}</button>')
    p.append('</div><div class="fichas" id="fichas">')

    fichas = [b for i, b in pontes.items() if i != "_meta"]
    for i, b in enumerate(sorted(fichas, key=lambda x: -pan.get(x["id"], 0))):
        cls, rot = BADGE[b["estatuto"]]
        dest = " destaque" if b["estatuto"] == "genealogia_contestada" else ""
        t, r, cm = b["topos"], b["registro_brasileiro"], b["consequencia_musical"]
        p.append(f'<article class="ficha{dest}" data-est="{b["estatuto"]}" data-aberta="0">'
                 f'<button class="cab" aria-expanded="false" aria-controls="c{i}"><span>'
                 f'<span class="ar">{e(t["arabe"])}</span>'
                 f'<span class="par">{e(r["nome"])}</span><span class="meta">'
                 f'<span>{e(t["nome"])}</span><span>autoriza: {e(cm["camada"])}</span>'
                 f'<span>acesso {e(b["acesso"])}</span></span></span><span class="dir">'
                 f'<span class="badge {cls}">{e(rot)}</span>'
                 f'<span class="qtd">{_n(pan.get(b["id"], 0))} hemist.</span>'
                 f'<span class="seta" aria-hidden="true">abrir ↓</span></span></button>'
                 f'<div class="corpo" id="c{i}">'
                 f'<h3>O topos</h3><p>{e(t["o_que_e"])}</p>'
                 f'<p style="color:var(--tinta2);font-size:.9rem">{e(t["onde_aparece"])}</p>'
                 f'<h3>O registro brasileiro</h3><p>{e(r["o_que_e"])}</p>'
                 f'<h3>O que têm em comum</h3><p>{e(r["o_que_tem_em_comum"])}</p>'
                 f'<h3>Por que este estatuto</h3><p>{e(b["por_que"])}</p>')
        cai = b.get("o_que_derrubaria") or b.get("o_que_confirmaria")
        if cai:
            p.append(f'<h3>O que derrubaria</h3><p>{e(cai)}</p>')
        if t.get("ERRO_CORRIGIDO"):
            p.append(f'<div class="nota"><b>Erro corrigido.</b> {e(t["ERRO_CORRIGIDO"])}</div>')
        if b.get("USO_PERMITIDO"):
            p.append(f'<div class="nota"><b>Uso permitido.</b> {e(b["USO_PERMITIDO"])}</div>')
        p.append(f'<h3>O que autoriza na música</h3><p>{e(cm["efeito"])}</p>'
                 f'<p style="color:var(--tinta2);font-size:.9rem"><b>Garantia:</b> '
                 f'{e(cm["garantia"])}</p><h3>Termos de garimpo</h3><div class="termos">')
        for ar, pt in zip(b["busca"]["palavras"], b["busca"]["glosa"]):
            p.append(f'<span class="termo"><i>{e(ar)}</i><s>{e(pt)}</s></span>')
        p.append('</div>')
        if b["busca"].get("aviso"):
            p.append(f'<div class="nota"><b>Atenção.</b> {e(b["busca"]["aviso"])}</div>')
        if b["acesso"] == "lexical":
            g = garimpar(b["id"], con, pontes, limite=6, por_termo=40)
            p.append(f'<h3>Amostra — {_n(g["coplas_distintas"])} coplas distintas</h3>')
            for c in g["amostra"]:
                p.append(f'<div class="copla"><div class="v">{e(c["sadr"])}</div>')
                if c["ajuz"]:
                    p.append(f'<div class="v">{e(c["ajuz"])}</div>')
                p.append(f'<div class="cred"><span>{e(c["poeta"])}</span>'
                         f'<span>{e(c["era"] or "era não dada")}</span>'
                         f'<span>{e(c["metro"])} ({e(c["metro_rom"])})</span>'
                         f'<span>casou em {e(c["termo_que_casou"])}</span>'
                         f'<a href="{e(c["url"])}" target="_blank" rel="noopener">fonte</a>'
                         f'</div></div>')
        else:
            p.append('<p class="vazio">Esta ponte não se garimpa por palavra — ver o acesso '
                     'declarado acima.</p>')
        p.append('</div></article>')
    p.append('</div></section>')

    p.append('<footer><p>Corpus: <b>Ashaar</b> (ARBML), colhido de aldiwan.net. O artigo '
             'declara CC BY 4.0; o cartão do dataset não traz campo de licença, e a '
             'discrepância fica registrada em vez de assumida. Os poemas são, na maioria '
             'esmagadora, de domínio público — poetas de era moderna foram excluídos.</p>'
             '<p>Medidas por <span style="font-family:var(--mono)">engine/forma.py</span>; '
             'garimpo por <span style="font-family:var(--mono)">ferramentas/garimpar.py</span>; '
             'pontes em <span style="font-family:var(--mono)">data/pontes.json</span>.</p>'
             '</footer></div>')

    p.append("""<script>
const fichas = Array.from(document.querySelectorAll('.ficha[data-est]'));
document.querySelectorAll('.cab').forEach(function(b){
  b.addEventListener('click', function(){
    const f = b.closest('.ficha'), aberta = f.dataset.aberta === '1';
    f.dataset.aberta = aberta ? '0' : '1';
    b.setAttribute('aria-expanded', String(!aberta));
    const s = b.querySelector('.seta');
    if (s) s.textContent = aberta ? 'abrir \\u2193' : 'fechar \\u2191';
  });
});
document.querySelectorAll('.chip').forEach(function(c){
  c.addEventListener('click', function(){
    const f = c.dataset.f;
    document.querySelectorAll('.chip').forEach(function(o){
      o.setAttribute('aria-pressed', String(o === c));
    });
    fichas.forEach(function(x){ x.hidden = !(f === 'todos' || x.dataset.est === f); });
  });
});
</script>""")
    return CABECA.read_text(encoding="utf-8") + "\n".join(p) + "\n"


def _cli(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--indice", default=str(RAIZ / ".cache_arabe/arabe.sqlite"))
    ap.add_argument("--pontes", default=str(RAIZ / "data/pontes.json"))
    ap.add_argument("--saida", required=True)
    a = ap.parse_args(argv)
    idx = Path(a.indice)
    if not idx.exists():
        print(f"índice ausente: {idx}\nMonte com ferramentas/indexar_arabe.py",
              file=sys.stderr)
        return 2
    h = montar(idx, Path(a.pontes))
    Path(a.saida).write_text(h, encoding="utf-8")
    print(f"página gerada: {a.saida}  ({len(h.encode())/1000:.0f} KB)")
    return 0


if __name__ == "__main__":
    sys.exit(_cli(sys.argv[1:]))
