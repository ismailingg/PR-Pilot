# =============================================================================
# PRPilot Test Sandbox — Multi-Runtime Image
# Supports: Python, Node.js, Go, Rust, Java (Maven), Ruby
#
# Build:   docker build -t prpilot-sandbox .
# Test:    docker run --rm prpilot-sandbox python3 --version
# =============================================================================

FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

# Go and Cargo bins need to be on PATH for the sandbox user too
ENV PATH="/usr/local/go/bin:/home/sandbox/.cargo/bin:${PATH}"

# -----------------------------------------------------------------------------
# 1. Base system tools + git
# -----------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    wget \
    git \
    ca-certificates \
    gnupg \
    unzip \
    build-essential \
    libssl-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# -----------------------------------------------------------------------------
# 2. Python 3.12 + pip + pytest + common test libs
# -----------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.12 \
    python3.12-dev \
    python3-pip \
    python3-venv \
    && rm -rf /var/lib/apt/lists/* \
    && pip3 install --no-cache-dir --break-system-packages \
        pytest \
        pytest-cov \
        pytest-asyncio \
        httpx \
        requests

# -----------------------------------------------------------------------------
# 3. Node.js 20 LTS
# -----------------------------------------------------------------------------
RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# -----------------------------------------------------------------------------
# 4. Go 1.22
# -----------------------------------------------------------------------------
RUN wget -q https://go.dev/dl/go1.22.3.linux-amd64.tar.gz \
    && tar -C /usr/local -xzf go1.22.3.linux-amd64.tar.gz \
    && rm go1.22.3.linux-amd64.tar.gz

# -----------------------------------------------------------------------------
# 5. Java 21 + Maven
# (before Rust so layer cache stays valid during iterative builds)
# -----------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    openjdk-21-jdk \
    maven \
    && rm -rf /var/lib/apt/lists/*

# -----------------------------------------------------------------------------
# 6. Ruby + Bundler + RSpec
# -----------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
    ruby-full \
    && rm -rf /var/lib/apt/lists/* \
    && gem install bundler rspec --no-document

# -----------------------------------------------------------------------------
# 7. Non-root sandbox user
# Rust is installed per-user so it must come AFTER useradd
# -----------------------------------------------------------------------------
RUN useradd -ms /bin/bash sandbox

USER sandbox
WORKDIR /home/sandbox

# Install Rust as the sandbox user (rustup is per-user by design)
RUN curl https://sh.rustup.rs -sSf | sh -s -- -y --default-toolchain stable \
    && . "$HOME/.cargo/env"

# Pre-warm Rust registry so first cargo build isn't slow
RUN /home/sandbox/.cargo/bin/cargo search serde --limit 1 > /dev/null 2>&1 || true

# Verify all runtimes are accessible
RUN python3 --version && \
    node --version && \
    npm --version && \
    go version && \
    /home/sandbox/.cargo/bin/rustc --version && \
    java --version && \
    ruby --version

CMD ["/bin/bash"]