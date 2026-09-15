#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Servidor local do Divã do Vão — sem dependências externas (só stdlib).
Sobe a interface de co-produção e uma API mínima sobre o motor generativo.

Uso:
    python3 app/server.py
    # abre http://localhost:8000

Endpoints:
    GET  /                      -> interface (app/index.html)
    GET  /api/corpus            -> lista de versos escaneados
    POST /api/gerar             -> {verso_id, modo, entropia} => melodia + auditoria
"""
import json, sys
from pathlib import Path
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RAIZ = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(RAIZ))
from engine.generative import carregar_corpus, gerar_melodia, relatorio_auditoria

CORPUS = carregar_corpus(RAIZ / "data/aruz_corpus.json")

def _midi_para_nome(m):
    nomes = ["C","C#","D","D#","E","F","F#","G","G#","A","A#","B"]
    return f"{nomes[m%12]}{m//12 - 1}"

class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def log_message(self, *a):  # silencioso
        pass

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            html = (RAIZ / "app/index.html").read_text(encoding="utf-8")
            return self._send(200, html, "text/html; charset=utf-8")
        if self.path == "/api/corpus":
            versos = [{
                "id": v["id"], "obra": v["obra"], "metro": v["metro"],
                "persa": v["persa"], "silabas": v["translit_silabas"],
                "escansao": v["escansao"], "glosa_pt": v.get("glosa_pt",""),
                "imagem": v.get("imagem","")
            } for v in CORPUS["versos"]]
            return self._send(200, json.dumps({"versos": versos, "metros": CORPUS["metros"]}, ensure_ascii=False))
        return self._send(404, json.dumps({"erro": "não encontrado"}))

    def do_POST(self):
        if self.path != "/api/gerar":
            return self._send(404, json.dumps({"erro": "não encontrado"}))
        n = int(self.headers.get("Content-Length", 0))
        req = json.loads(self.rfile.read(n) or b"{}")
        verso = next((v for v in CORPUS["versos"] if v["id"] == req.get("verso_id")), None)
        if not verso:
            return self._send(400, json.dumps({"erro": "verso_id inválido"}))
        frase = gerar_melodia(
            verso,
            modo=req.get("modo", "dorico"),
            entropia=float(req.get("entropia", 0.4)),
            semente=req.get("semente", "diva"))
        rel = relatorio_auditoria(frase, verso)
        notas = [{
            "midi": nt.midi, "nome": _midi_para_nome(nt.midi), "dur": nt.dur,
            "silaba": nt.silaba, "aruz": nt.aruz
        } for nt in frase.notas]
        return self._send(200, json.dumps({
            "notas": notas, "auditoria": rel,
            "tonica": frase.tonica_midi, "modo": frase.modo
        }, ensure_ascii=False))


def main(port=8000):
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"Divã do Vão — app local em http://localhost:{port}  (Ctrl+C para sair)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nEncerrado.")

if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 8000)
