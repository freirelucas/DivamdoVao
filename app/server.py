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
Servidor local do Divã do Vão — sem dependências externas (só stdlib).
Sobe a interface de co-produção e uma API mínima sobre o motor generativo.

Uso:
    python3 app/server.py
    # abre http://localhost:8000

Endpoints:
    GET  /                      -> interface (app/index.html)
    GET  /api/corpus            -> lista de versos escaneados + conferência do metro
    POST /api/gerar             -> {verso_id, modo, entropia, ambito, tonica,
                                    semente, operacao} => melodia + auditoria

Erros sempre voltam como JSON com status HTTP adequado. Antes, uma entrada
inválida (modo inexistente, entropia não numérica, JSON malformado) derrubava
a thread do handler com traceback e o cliente não recebia resposta nenhuma —
a interface travava sem mensagem.
"""
import json, sys
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from engine.generative import (carregar_corpus, gerar_melodia,
                               relatorio_auditoria, conferir_metro, MODOS)
from engine.ritmo import OPERACOES, conferir_rastro

CORPUS = carregar_corpus(RAIZ / "data/aruz_corpus.json")
LIMITE_CORPO = 64 * 1024        # o corpo do POST é um punhado de parâmetros

def _midi_para_nome(m):
    nomes = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
    return f"{nomes[m%12]}{m//12 - 1}"


class ErroCliente(Exception):
    """Entrada inválida: vira 400 com mensagem, não traceback."""


def _numero(req, chave, padrao, minimo, maximo, inteiro=False):
    """Lê um parâmetro numérico do corpo, validando tipo e faixa."""
    bruto = req.get(chave, padrao)
    try:
        valor = int(bruto) if inteiro else float(bruto)
    except (TypeError, ValueError):
        raise ErroCliente(f"'{chave}' deve ser {'inteiro' if inteiro else 'número'}, "
                          f"recebi {bruto!r}")
    if not minimo <= valor <= maximo:
        raise ErroCliente(f"'{chave}' deve estar entre {minimo} e {maximo}, "
                          f"recebi {valor}")
    return valor


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _erro(self, code, mensagem):
        self._send(code, json.dumps({"erro": mensagem}, ensure_ascii=False))

    def log_message(self, *a):  # silencioso
        pass

    def do_GET(self):
        try:
            if self.path in ("/", "/index.html"):
                html = (RAIZ / "app/index.html").read_text(encoding="utf-8")
                return self._send(200, html, "text/html; charset=utf-8")
            if self.path == "/favicon.ico":
                # o navegador pede sempre; sem isto o console do app local
                # nasce com um 404 que não é problema de ninguém
                return self._send(204, b"", "image/x-icon")
            if self.path == "/api/corpus":
                versos = []
                for v in CORPUS["versos"]:
                    # a conferência metro<->escansão viaja com o verso: a
                    # interface mostra quando a fonte não foi conferida, em vez
                    # de apresentar toda escansão como igualmente firme.
                    versos.append({
                        "id": v["id"], "obra": v["obra"], "metro": v["metro"],
                        "persa": v["persa"], "silabas": v["translit_silabas"],
                        "escansao": v["escansao"], "glosa_pt": v.get("glosa_pt",""),
                        "imagem": v.get("imagem",""),
                        "metro_conferido": v.get("metro_conferido"),
                        "conferencia_metro": conferir_metro(v, CORPUS["metros"]),
                    })
                return self._send(200, json.dumps(
                    {"versos": versos, "metros": CORPUS["metros"],
                     "modos": sorted(MODOS), "operacoes": sorted(OPERACOES)},
                    ensure_ascii=False))
            return self._erro(404, "não encontrado")
        except Exception as e:                                   # nunca derruba
            return self._erro(500, f"erro interno: {type(e).__name__}: {e}")

    def do_POST(self):
        try:
            if self.path != "/api/gerar":
                return self._erro(404, "não encontrado")
            req = self._corpo()
            verso = next((v for v in CORPUS["versos"]
                          if v["id"] == req.get("verso_id")), None)
            if not verso:
                raise ErroCliente(
                    f"verso_id inválido: {req.get('verso_id')!r}; disponíveis: "
                    f"{[v['id'] for v in CORPUS['versos']]}")
            modo = req.get("modo", "dorico")
            if modo not in MODOS:
                raise ErroCliente(f"modo inválido: {modo!r}; use um de {sorted(MODOS)}")
            operacao = req.get("operacao") or ""
            if operacao and operacao not in OPERACOES:
                raise ErroCliente(f"operação inválida: {operacao!r}; "
                                  f"use uma de {sorted(OPERACOES)}")

            frase = gerar_melodia(
                verso, modo=modo,
                tonica_midi=_numero(req, "tonica", 62, 21, 108, inteiro=True),
                entropia=_numero(req, "entropia", 0.4, 0.0, 1.0),
                ambito=_numero(req, "ambito", 9, 2, 36, inteiro=True),
                semente=str(req.get("semente", "diva")))
            if operacao:
                frase = OPERACOES[operacao](frase)

            rel = relatorio_auditoria(frase, verso, CORPUS["metros"])
            notas = [{
                "midi": nt.midi, "nome": _midi_para_nome(nt.midi), "dur": nt.dur,
                "dur_base": nt.dur_base, "silaba": nt.silaba, "aruz": nt.aruz,
                "grau_modal": nt.grau_modal, "oitava": nt.oitava
            } for nt in frase.notas]
            return self._send(200, json.dumps({
                "notas": notas, "auditoria": rel,
                "tonica": frase.tonica_midi, "modo": frase.modo,
                "anacruse": frase.anacruse,
                "operacoes": frase.operacoes,
                "rastro": conferir_rastro(frase),
            }, ensure_ascii=False))
        except ErroCliente as e:
            return self._erro(400, str(e))
        except ValueError as e:          # validações do motor (corpus, âmbito)
            return self._erro(400, str(e))
        except Exception as e:
            return self._erro(500, f"erro interno: {type(e).__name__}: {e}")

    def _corpo(self) -> dict:
        """Lê e decodifica o corpo do POST, recusando o que não serve."""
        try:
            n = int(self.headers.get("Content-Length", 0) or 0)
        except ValueError:
            raise ErroCliente("Content-Length inválido")
        if n < 0:
            raise ErroCliente("Content-Length inválido")
        if n > LIMITE_CORPO:
            raise ErroCliente(f"corpo grande demais: {n} bytes "
                              f"(limite {LIMITE_CORPO})")
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError as e:
            raise ErroCliente(f"JSON malformado: {e}")
        if not isinstance(req, dict):
            raise ErroCliente("o corpo deve ser um objeto JSON")
        return req


def main(port=8000):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Divã do Vão — app local em http://localhost:{port}  (Ctrl+C para sair)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrado.")

if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8000)
