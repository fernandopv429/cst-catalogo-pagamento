# Subir o endpoint de pagamento no Coolify

O que sobe é **só o `servidor_pagamento.py`**. A página (`index.html`) continua onde
está, servida pelo WordPress em `chinasourcetrade.com` — ela só precisa apontar para a
URL nova, e isso é uma linha de configuração no arquivo (ver o fim deste documento).

O motivo de existir um servidor: o access token do Mercado Pago não pode ficar no HTML.
A página é estática e pública; qualquer visitante leria o token e poderia gerar cobranças
na conta. O token vive aqui, e o navegador nunca o vê.

## 1. Colocar num repositório

O Coolify puxa de um Git. Como este endpoint não tem nada a ver com a API de petições,
o mais limpo é um repositório próprio (`cst-pagamento`, por exemplo) com estes arquivos:

    servidor_pagamento.py
    Dockerfile
    docker-compose.yaml
    .dockerignore
    .gitignore
    .env.example
    DEPLOY-COOLIFY.md

**Não** suba o `.env`, o `index.html` nem o `vendor/` — o `.gitignore` e o
`.dockerignore` já cuidam disso.

## 2. Criar o recurso no Coolify

- **New Resource → Application → Public/Private Repository**, apontando para o repo acima.
- **Build Pack: Dockerfile** (o `Dockerfile` na raiz já está pronto).
  Se preferir usar o compose, escolha **Docker Compose** e aponte para `docker-compose.yaml`.
- **Port Exposes: `8098`** — é a porta que o container escuta.
- **Domínio**: aponte um subdomínio seu, por exemplo `pagamento.nexusdevhub.com`.
  O Coolify cuida do HTTPS. **Precisa ser HTTPS**: a página é servida em `https://`,
  e navegador não deixa página segura chamar endpoint `http://`.

## 3. Variáveis de ambiente

Em **Environment Variables**, marcando todas como *Build variable? não* (são de runtime):

| Variável | Valor |
|---|---|
| `MERCADOPAGO_ACCESS_TOKEN` | o token da conta. **Marque como secret.** |
| `API_KEY` | a chave que a página manda no `X-API-Key` |
| `ORIGENS_PERMITIDAS` | `https://chinasourcetrade.com` |
| `HOST` | `0.0.0.0` |
| `PORTA` | `8098` |

Sem `MERCADOPAGO_ACCESS_TOKEN` **ou** sem `API_KEY` o serviço responde `503` em toda
chamada — falha fechada, de propósito: isto gasta dinheiro de verdade quando o token
for o de produção, não pode ficar aberto por esquecimento no deploy.

O token que está em uso hoje é de uma **conta de teste** (usuário `TESTUSER...`).
Serve para validar o fluxo inteiro sem mover dinheiro. Para faturar de verdade, troque
por um token da conta real — e só por essa variável, nada no código muda.

## 4. Health check

O Coolify pode usar `GET /saude`, que devolve:

    {"ok": true, "servico": "link de pagamento CST",
     "token_configurado": true, "chave_configurada": true}

Ele **não** chama o Mercado Pago — só confirma que o processo está de pé e que as
variáveis chegaram. Assim o health check não gera tráfego na API do MP.

## 5. Conferir depois de subir

    curl https://pagamento.nexusdevhub.com/saude

    curl -X POST https://pagamento.nexusdevhub.com/ \
      -H "Content-Type: application/json" \
      -H "X-API-Key: SUA_API_KEY" \
      -d '{"valor":1.00,"descricao":"teste","cliente":{"nome":"Teste","email":"t@t.com"},"referencia":"teste-1"}'

Resposta esperada: `{"link":"https://www.mercadopago.com.br/checkout/...", "preference_id":"..."}`.

## 6. Apontar a página para o endpoint novo

No `index.html`, dentro do bloco `<script>` principal, a chamada de pagamento está em
`document.getElementById('gerarLinkPagamentoBtn')`. Hoje ela é assim:

```js
const resp = await fetch('https://spfc--beb119269f4011f1a3561607ee4eb77e.web.val.run', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
```

Troque por:

```js
const resp = await fetch('https://pagamento.nexusdevhub.com/', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json', 'X-API-Key': 'SUA_API_KEY' },
```

Depois re-suba o `index.html` para `wp-content/uploads/`.

O resto do corpo da chamada não muda — o servidor foi escrito para aceitar exatamente o
formato que a página já mandava (`valor`, `descricao`, `cliente{nome,email}`, `referencia`)
e devolver exatamente o que ela já espera (`{link}` no sucesso, `{error}` na falha).

## O que protege este endpoint

Vale ser franco sobre cada camada:

| Camada | Protege de quê | Limite |
|---|---|---|
| `ORIGENS_PERMITIDAS` (CORS) | outra página chamar seu endpoint pelo navegador | não impede um `curl` |
| `X-API-Key` | varredura automática de endpoints abertos | a chave está no HTML público, qualquer visitante copia |
| Teto de 30 chamadas/min por IP | alguém inflar sua conta de preferências | IP rotativo passa |
| Teto de valor por pedido | valor absurdo criado por engano ou de propósito | — |

Nenhuma delas guarda dinheiro: uma preferência é só um link de cobrança, quem paga
escolhe pagar. O que realmente importa é que **o access token não vaze** — e ele não sai
do servidor.
