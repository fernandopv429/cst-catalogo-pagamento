# Endpoint de link de pagamento do catálogo CST (Mercado Pago).
#
# O servidor é biblioteca padrão do Python — não há requirements.txt porque não há
# dependência nenhuma. Por isso a imagem é slim e o build não tem etapa de pip.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    PORTA=8098

WORKDIR /app

COPY servidor_pagamento.py .

# Sem root: o processo não escreve em disco, não há motivo para ter permissão.
RUN useradd --system --create-home --uid 10001 pagamento \
    && chown -R pagamento:pagamento /app
USER pagamento

EXPOSE 8098

# O Coolify tem healthcheck próprio; este cobre `docker run` avulso e o
# `docker compose` local. /saude não chama o Mercado Pago — só confirma que o
# processo está de pé e se as variáveis estão presentes.
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD python3 -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8098/saude', timeout=4).status==200 else 1)"

CMD ["python3", "servidor_pagamento.py"]
