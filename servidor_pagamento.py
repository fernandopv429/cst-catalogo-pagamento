#!/usr/bin/env python3
"""Endpoint de link de pagamento do catálogo CST — cria uma preferência no Mercado Pago.

    python3 servidor_pagamento.py                 # sobe em 0.0.0.0:8098
    python3 servidor_pagamento.py --porta 9000
    python3 servidor_pagamento.py --env-file /caminho/.env.mercadopago

É o par de servidor do botão "Gerar link de pagamento" da página. O contrato com o
front é o que a página já usa hoje:

    POST /  (ou /pagamento)
    { "valor": 8234.83, "descricao": "...", "cliente": {"nome": "...", "email": "..."},
      "referencia": "pedido-PROP-2026-5927" }
    ->  200 { "link": "https://www.mercadopago.com.br/checkout/..." }
    ->  4xx/5xx { "error": "mensagem para mostrar na tela" }

Autenticação: cabeçalho X-API-Key, conferido contra API_KEY do ambiente. Sem a
variável o serviço responde 503 — falha fechada, igual à API de ingestão: isto aqui
gasta dinheiro de verdade quando o token for o de produção, não pode ficar aberto
por esquecimento no deploy.

ATENÇÃO sobre a chave: a página é servida estática e pública, então a API_KEY que
ela mandar é legível por qualquer visitante. Ela barra varredura automática, não um
atacante decidido. A defesa que vale é a lista de origens (ORIGENS_PERMITIDAS) mais
o limite por minuto abaixo.

O MERCADOPAGO_ACCESS_TOKEN nunca sai daqui — o front não o vê em momento algum.

Biblioteca padrão só, sem dependência de framework (este ambiente não tem pip).
"""
import argparse
import collections
import hmac
import json
import os
import pathlib
import sys
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

AQUI = pathlib.Path(__file__).resolve().parent

LIMITE_CORPO = 64 << 10          # 64 KB: o corpo esperado tem meia dúzia de campos
MP_TIMEOUT = 20                  # segundos de paciência com a API do Mercado Pago
TETO_POR_MINUTO = 30             # preferências por IP por minuto
VALOR_MAXIMO = 5_000_000.0       # trava de sanidade contra valor absurdo

ORIGENS_PADRAO = "https://chinasourcetrade.com,https://catalogo.a5ecossistema.tech,http://localhost:8777"

# A página é servida por este mesmo processo quando os arquivos estão presentes.
# Página e endpoint na mesma origem = o navegador nem chega a fazer preflight, e a
# lista de origens acima só importa para quem servir a página de outro domínio.
PAGINA = AQUI / "index.html"
VENDOR = AQUI / "vendor"
TIPOS = {
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".html": "text/html; charset=utf-8",
}

_env_extra = {}
_batidas = collections.defaultdict(collections.deque)
_trava = threading.Lock()


def carrega_env(caminho):
    """Lê um .env simples para dentro de _env_extra (sem sobrescrever o ambiente)."""
    arq = pathlib.Path(caminho)
    if not arq.exists():
        return False
    for linha in arq.read_text(encoding="utf-8").splitlines():
        linha = linha.strip()
        if linha and not linha.startswith("#") and "=" in linha:
            k, v = linha.split("=", 1)
            _env_extra[k.strip()] = v.strip().strip('"').strip("'")
    return True


def env(chave, padrao=None):
    return os.environ.get(chave) or _env_extra.get(chave) or padrao


def origens():
    return [o.strip() for o in env("ORIGENS_PERMITIDAS", ORIGENS_PADRAO).split(",") if o.strip()]


def dentro_do_teto(ip):
    """Janela deslizante de 60s por IP. Devolve False quando estourou."""
    agora = time.monotonic()
    with _trava:
        fila = _batidas[ip]
        while fila and agora - fila[0] > 60:
            fila.popleft()
        if len(fila) >= TETO_POR_MINUTO:
            return False
        fila.append(agora)
        return True


def cria_preferencia(token, valor, descricao, nome, email, referencia):
    """Chama a API do Mercado Pago. Devolve (dados, None) ou (None, mensagem de erro)."""
    item = {
        "title": descricao[:250],
        "quantity": 1,
        "unit_price": valor,
        "currency_id": "BRL",
    }
    corpo = {"items": [item], "external_reference": referencia}

    pagador = {}
    if nome:
        pagador["name"] = nome[:100]
    if email and "@" in email:
        pagador["email"] = email[:100]
    if pagador:
        corpo["payer"] = pagador

    req = urllib.request.Request(
        "https://api.mercadopago.com/checkout/preferences",
        data=json.dumps(corpo).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=MP_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        detalhe = e.read().decode("utf-8", "replace")[:500]
        try:
            msg = json.loads(detalhe).get("message") or detalhe
        except ValueError:
            msg = detalhe
        print(f"  mercado pago respondeu {e.code}: {detalhe}", file=sys.stderr)
        if e.code in (401, 403):
            return None, "token do Mercado Pago recusado — confira MERCADOPAGO_ACCESS_TOKEN"
        return None, f"Mercado Pago recusou o pedido: {msg}"
    except urllib.error.URLError as e:
        print(f"  falha de rede ao falar com o mercado pago: {e}", file=sys.stderr)
        return None, "não foi possível falar com o Mercado Pago"


class Handler(BaseHTTPRequestHandler):
    server_version = "PagamentoCST/1.0"

    def log_message(self, formato, *args):
        print(f"{self.address_string()} {formato % args}", file=sys.stderr)

    # ---- resposta -------------------------------------------------------

    def _origem_liberada(self):
        origem = self.headers.get("Origin")
        return origem if origem in origens() else None

    def _cabecalhos_cors(self):
        if (origem := self._origem_liberada()):
            self.send_header("Access-Control-Allow-Origin", origem)
            self.send_header("Vary", "Origin")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, X-API-Key")
            self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
            self.send_header("Access-Control-Max-Age", "86400")

    def responde(self, codigo, payload):
        corpo = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(codigo)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(corpo)))
        self._cabecalhos_cors()
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(corpo)

    def serve_arquivo(self, alvo, cache):
        try:
            dados = alvo.read_bytes()
        except OSError:
            return self.responde(404, {"error": "arquivo não encontrado"})
        self.send_response(200)
        self.send_header("Content-Type", TIPOS.get(alvo.suffix, "application/octet-stream"))
        self.send_header("Content-Length", str(len(dados)))
        self.send_header("Cache-Control", cache)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(dados)

    # ---- rotas ----------------------------------------------------------

    def do_OPTIONS(self):
        self.send_response(204)
        self._cabecalhos_cors()
        self.end_headers()

    def do_HEAD(self):
        # Alguns health checks (Coolify inclusive, dependendo da configuração) batem
        # de HEAD. Sem isto o BaseHTTPRequestHandler responde 501 e o container é
        # marcado como doente estando perfeitamente de pé. As respostas abaixo já
        # omitem o corpo quando o método é HEAD.
        self.do_GET()

    def saude(self):
        self.responde(200, {
            "ok": True,
            "servico": "catálogo CST + link de pagamento",
            "pagina_servida": PAGINA.exists(),
            "token_configurado": bool(env("MERCADOPAGO_ACCESS_TOKEN")),
            "chave_configurada": bool(env("API_KEY")),
        })

    def do_GET(self):
        rota = self.path.split("?")[0]
        limpa = rota.rstrip("/")

        if limpa == "/saude":
            return self.saude()

        if limpa in ("", "/index.html"):
            # Sem a página na imagem (deploy só do endpoint), a raiz continua
            # devolvendo a saúde, como era antes.
            if PAGINA.exists():
                return self.serve_arquivo(PAGINA, "no-cache")
            return self.saude()

        if rota.startswith("/vendor/"):
            # Caminho resolvido e conferido contra a pasta vendor: sem isso um
            # ../../etc/passwd sairia daqui.
            alvo = (VENDOR / rota[len("/vendor/"):]).resolve()
            if VENDOR.resolve() in alvo.parents and alvo.is_file():
                return self.serve_arquivo(alvo, "public, max-age=86400")
            return self.responde(404, {"error": "arquivo não encontrado"})

        return self.responde(404, {"error": "rota não encontrada"})

    def do_POST(self):
        if self.path.split("?")[0].rstrip("/") not in ("", "/pagamento"):
            return self.responde(404, {"error": "rota não encontrada"})

        chave_esperada = env("API_KEY")
        token = env("MERCADOPAGO_ACCESS_TOKEN")
        if not chave_esperada or not token:
            faltando = [n for n, v in (("API_KEY", chave_esperada),
                                       ("MERCADOPAGO_ACCESS_TOKEN", token)) if not v]
            print(f"  recusado: falta no ambiente {', '.join(faltando)}", file=sys.stderr)
            return self.responde(503, {"error": "serviço não configurado"})

        recebida = self.headers.get("X-API-Key", "")
        if not hmac.compare_digest(recebida, chave_esperada):
            return self.responde(401, {"error": "chave inválida"})

        if not dentro_do_teto(self.client_address[0]):
            return self.responde(429, {"error": "muitas tentativas, espere um minuto"})

        try:
            tamanho = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self.responde(400, {"error": "Content-Length inválido"})
        if tamanho <= 0 or tamanho > LIMITE_CORPO:
            return self.responde(400, {"error": "corpo ausente ou grande demais"})

        try:
            dados = json.loads(self.rfile.read(tamanho).decode("utf-8"))
        except (ValueError, UnicodeDecodeError):
            return self.responde(400, {"error": "corpo não é JSON válido"})
        if not isinstance(dados, dict):
            return self.responde(400, {"error": "corpo precisa ser um objeto JSON"})

        try:
            valor = round(float(dados.get("valor")), 2)
        except (TypeError, ValueError):
            return self.responde(400, {"error": "valor ausente ou não numérico"})
        if not (valor > 0) or valor > VALOR_MAXIMO:
            return self.responde(400, {"error": "valor fora da faixa aceita"})

        descricao = str(dados.get("descricao") or "Pedido CST").strip()
        referencia = str(dados.get("referencia") or "").strip()[:256]
        cliente = dados.get("cliente") if isinstance(dados.get("cliente"), dict) else {}
        nome = str(cliente.get("nome") or "").strip()
        email = str(cliente.get("email") or "").strip()

        pref, erro = cria_preferencia(token, valor, descricao, nome, email, referencia)
        if erro:
            return self.responde(502, {"error": erro})

        link = pref.get("init_point") or pref.get("sandbox_init_point")
        if not link:
            return self.responde(502, {"error": "Mercado Pago não devolveu link de pagamento"})

        print(f"  preferência {pref.get('id')} criada — R$ {valor:.2f} ref={referencia}",
              file=sys.stderr)
        return self.responde(200, {
            "link": link,
            "preference_id": pref.get("id"),
            "sandbox_link": pref.get("sandbox_init_point"),
        })


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--porta", type=int, default=int(os.environ.get("PORTA", 8098)))
    p.add_argument("--host", default=os.environ.get("HOST", "0.0.0.0"))
    p.add_argument("--env-file", default=os.environ.get("MP_ENV_FILE"))
    args = p.parse_args()

    candidatos = [args.env_file] if args.env_file else [
        AQUI / ".env.mercadopago",
        pathlib.Path.home() / "Área de trabalho" / "Conexão_geral" / ".env.mercadopago",
    ]
    for c in candidatos:
        if c and carrega_env(c):
            print(f"ambiente lido de {c}", file=sys.stderr)
            break

    if not env("API_KEY") or not env("MERCADOPAGO_ACCESS_TOKEN"):
        print("aviso: API_KEY e/ou MERCADOPAGO_ACCESS_TOKEN ausentes — "
              "as chamadas vão responder 503 até configurar", file=sys.stderr)

    print(f"origens liberadas: {', '.join(origens())}", file=sys.stderr)
    print(f"ouvindo em http://{args.host}:{args.porta}", file=sys.stderr)
    ThreadingHTTPServer((args.host, args.porta), Handler).serve_forever()


if __name__ == "__main__":
    main()
