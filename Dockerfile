FROM runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04

WORKDIR /app

COPY . .

RUN apt-get update && apt-get install -y \
    unzip \
    docker.io

RUN curl -fsSL https://bun.sh/install | bash -s "bun-v1.1.33"
RUN export DEPOT_INSTALL_DIR=/root/.depot/bin
RUN export PATH=$DEPOT_INSTALL_DIR:$PATH
RUN curl -L https://depot.dev/install-cli.sh | sh -s 2.76.0

RUN ls -la serverless-registry

RUN cd serverless-registry/push && \
    bun install

RUN pip install -r requirements.txt

CMD ["python3", "handler.py"]