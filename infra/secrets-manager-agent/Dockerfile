ARG AWS_SM_AGENT_VERSION=v1.2.1

FROM rust:1.82-bookworm AS build

ARG AWS_SM_AGENT_VERSION

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates git pkg-config libssl-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build

RUN git clone --branch "${AWS_SM_AGENT_VERSION}" --depth 1 https://github.com/aws/aws-secretsmanager-agent.git src

WORKDIR /build/src

RUN cargo build --release --bin aws_secretsmanager_agent

FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=build /build/src/target/release/aws_secretsmanager_agent /usr/local/bin/secrets-manager-agent

ENTRYPOINT ["/usr/local/bin/secrets-manager-agent"]
