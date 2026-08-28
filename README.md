# Cópia local — CST Grupo de Compra · Britway Fitness

Réplica de `https://chinasourcetrade.com/wp-content/uploads/formulario-catalogo-brtw.html`
baixada em 28/08/2026.

## Arquivos

| Arquivo | O que é |
|---|---|
| `index.html` | A página, com as alterações listadas abaixo |
| `index.original.html` | O HTML exatamente como veio do servidor, sem nenhuma alteração |
| `vendor/html2pdf.bundle.min.js` | Biblioteca de geração de PDF (v0.10.1), baixada do cdnjs |
| `servidor_pagamento.py` | Serve a página em `GET /` e cria a preferência do Mercado Pago em `POST /` (stdlib só) |
| `Dockerfile` / `docker-compose.yaml` | Empacotamento do endpoint para o Coolify |
| `.env.example` | Variáveis que o endpoint precisa (o `.env` real fica fora do repo) |
| `DEPLOY-COOLIFY.md` | Passo a passo para subir o endpoint e apontar a página para ele |

## Alterações feitas sobre o original

1. **`html2pdf.js` local** — aponta para `vendor/`, com fallback para o CDN se o arquivo local faltar.
2. **PDF em branco (corrigido)** — a proposta fica ancorada no topo do documento
   (`#proposalRoot { top: 0 }`), mas o html2canvas captura a partir do viewport atual.
   Como o catálogo tem ~55 mil px de altura, quem clica em "Baixar PDF" está sempre rolado
   bem para baixo e a captura pegava área vazia. O handler agora volta ao topo antes de
   capturar e devolve a posição de rolagem depois.
3. **Texto cortado na margem esquerda (corrigido)** — as opções do html2canvas forçavam
   `width/windowWidth = 794px`, mas o html2pdf monta o container com a largura útil da A4
   menos as margens (190mm ≈ 718px). A `.prop-page` (794px fixos, `margin: 0 auto`)
   estourava esse container e era deslocada ~38px para a esquerda, cortando a primeira
   letra de cada linha. Removidas as duas opções — o html2canvas passa a medir o elemento
   sozinho e a página encaixa na área imprimível.

## O que já está dentro do HTML (nada precisa ser baixado à parte)

- **753 produtos** com preço em USD, CBM e categoria (`const CATALOG`)
- **780 imagens** embutidas em base64: 752 fotos de produto + 28 amostras de cor
  - único produto sem foto: `T300 — Commercial Treadmill with LCD Screen` (já vinha sem imagem na origem)
- **28 cores** de pintura/couro com swatch
- Regras de preço: `MARKUP_FACTOR = 2.25`, `FREIGHT_PER_CBM = 110` (USD/m³),
  `MIN_ORDER_USD = 3000`, `FALLBACK_FX_RATE = 5.30`
- Todo o CSS e JS (proposta em PDF, WhatsApp, cálculo de totais)

## O que continua dependendo da internet

Estes são serviços externos, não arquivos — não dá para copiar:

- **Cotação USD→BRL**: tenta `open.er-api.com`, depois `api.frankfurter.app`,
  depois `cdn.jsdelivr.net/.../currency-api`. Sem internet, cai no `FALLBACK_FX_RATE` de 5,30.
- **Link de pagamento**: hoje a página ainda aponta para
  `POST https://spfc--beb119269f4011f1a3561607ee4eb77e.web.val.run`. O substituto está
  pronto em `servidor_pagamento.py` — falta trocar a URL no `index.html` e subir o
  endpoint (ver `DEPLOY-COOLIFY.md`).
- **WhatsApp**: `wa.me` (só abre o app/site)

## Como abrir

Direto no navegador:

    xdg-open index.html

Ou por um servidor local (recomendado, evita restrições de `file://`):

    python3 -m http.server 8777 --directory .
    # http://localhost:8777
