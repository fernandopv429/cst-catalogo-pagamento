# Subir o endpoint de pagamento no Coolify

O container serve **as duas coisas**: a página em `GET /` e o link de pagamento em
`POST /`. Não conflitam porque um é GET e o outro é POST.

Isso é de propósito. Página e endpoint na mesma origem significa que o navegador nem
chega a fazer preflight — some a classe inteira de erro de CORS, que é a forma mais
comum de esse tipo de integração quebrar em produção (e quebrar de um jeito chato: o
`curl` funciona e o botão não).

O motivo de existir um servidor: o access token do Mercado Pago não pode ficar no HTML.
A página é estática e pública; qualquer visitante leria o token e poderia gerar cobranças
na conta. O token vive aqui, e o navegador nunca o vê.

## 1. Colocar num repositório

Já está feito: `github.com/fernandopv429/cst-catalogo-pagamento`, privado.

Entram na imagem o `servidor_pagamento.py`, o `index.html` e o `vendor/`. Ficam de
fora o `.env` (credenciais), o `index.original.html` (só comparação) e os `.md` —
ver `.dockerignore`.

## 2. Criar o recurso no Coolify

- **New Resource → Application → Public/Private Repository**, apontando para o repo acima.
- **Build Pack: Dockerfile** (o `Dockerfile` na raiz já está pronto).
  Se preferir usar o compose, escolha **Docker Compose** e aponte para `docker-compose.yaml`.
- **Port Exposes: `8098`** — é a porta que o container escuta.
- **Domínio**: aponte um subdomínio seu, por exemplo `catalogo.a5ecossistema.tech`.
  O Coolify cuida do HTTPS. **Precisa ser HTTPS**: a página é servida em `https://`,
  e navegador não deixa página segura chamar endpoint `http://`.

## 3. Variáveis de ambiente

Em **Environment Variables**, marcando todas como *Build variable? não* (são de runtime):

| Variável | Valor |
|---|---|
| `MERCADOPAGO_ACCESS_TOKEN` | o token da conta. **Marque como secret.** |
| `API_KEY` | a chave que a página manda no `X-API-Key` |
| `ORIGENS_PERMITIDAS` | `https://chinasourcetrade.com,https://catalogo.a5ecossistema.tech` |
| `HOST` | `0.0.0.0` |
| `PORTA` | `8098` |

Sem `MERCADOPAGO_ACCESS_TOKEN` **ou** sem `API_KEY` o serviço responde `503` em toda
chamada — falha fechada, de propósito: isto gasta dinheiro de verdade quando o token
for o de produção, não pode ficar aberto por esquecimento no deploy.

O token que está em uso hoje é de uma **conta de teste** (usuário `TESTUSER...`).
Serve para validar o fluxo inteiro sem mover dinheiro. Para faturar de verdade, troque
por um token da conta real — e só por essa variável, nada no código muda.

## 4. Health check

Use **`GET /saude`** — a raiz agora devolve a página, não JSON. Resposta esperada:

    {"ok": true, "servico": "catálogo CST + link de pagamento",
     "pagina_servida": true, "token_configurado": true, "chave_configurada": true}

Ele **não** chama o Mercado Pago — só confirma que o processo está de pé e que as
variáveis chegaram. Assim o health check não gera tráfego na API do MP.

## 5. Conferir depois de subir

    curl https://catalogo.a5ecossistema.tech/saude          # deve trazer pagina_servida: true
    curl -I https://catalogo.a5ecossistema.tech/            # deve ser text/html, ~3,4 MB

    curl -X POST https://catalogo.a5ecossistema.tech/ \
      -H "Content-Type: application/json" \
      -H "X-API-Key: SUA_API_KEY" \
      -d '{"valor":1.00,"descricao":"teste","cliente":{"nome":"Teste","email":"t@t.com"},"referencia":"teste-1"}'

Resposta esperada: `{"link":"https://www.mercadopago.com.br/checkout/...", "preference_id":"..."}`.

## 6. A página

Não há nada a editar: o `index.html` já aponta para `https://catalogo.a5ecossistema.tech`
e manda a chave no cabeçalho `X-API-Key`. O endereço é escolhido sozinho — em `localhost`
a página fala com o servidor local, em qualquer outro host com o domínio público. A mesma
cópia serve para testar e para publicar.

Depois do deploy, a página fica em `https://catalogo.a5ecossistema.tech/`.

A cópia no WordPress (`chinasourcetrade.com/wp-content/uploads/...`) é opcional a partir
daqui. Se você mantiver as duas, a do WordPress chama o endpoint de outro domínio —
funciona, porque `chinasourcetrade.com` está em `ORIGENS_PERMITIDAS`, mas aí você passa a
ter dois lugares para atualizar a cada mudança. Servir só pelo Coolify evita isso.

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
