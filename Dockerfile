FROM runpod/pytorch:2.4.0-py3.11-cuda12.4.1-devel-ubuntu22.04

WORKDIR /app

COPY . .

RUN apt-get update && apt-get install -y \
    unzip \
    docker.io \
    curl \
    docker-buildx

RUN curl -fsSL https://bun.sh/install | bash -s "bun-v1.1.32" && \
    ln -s $HOME/.bun/bin/bun /usr/local/bin/bun
RUN export PATH=$PATH:~/.bun/bin
RUN export DEPOT_INSTALL_DIR=/root/.depot/bin
RUN export PATH=$DEPOT_INSTALL_DIR:$PATH:~/.bun/bin
RUN curl -L https://depot.dev/install-cli.sh | bash -s 2.76.0
RUN wget -qO- https://get.pnpm.io/install.sh | bash -

RUN ls -la serverless-registry

RUN pip install -r requirements.txt

CMD ["python3", "handler.py"]