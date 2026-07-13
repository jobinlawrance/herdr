FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

# Base tooling
RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl git openssh-client ripgrep less tmux python3 \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && rm -rf /var/lib/apt/lists/*

# Claude Code — official Anthropic CLI, installed globally
RUN npm install -g @anthropic-ai/claude-code

# herdr (v0.7.x). Piped remote installer — review https://herdr.dev/install.sh
# if you don't already trust it. Force a system path so the non-root `agent`
# user can run it, and verify so a silent curl failure fails the build.
RUN curl -fsSL https://herdr.dev/install.sh | HERDR_INSTALL_DIR=/usr/local/bin sh \
    && herdr --version

# Run as non-root (Claude Code refuses --dangerously-skip-permissions as root,
# and running interactive tooling as root is a bad default)
RUN useradd -m -s /bin/bash agent
USER agent
WORKDIR /home/agent/workspace

# Health: no HTTP port (sleep infinity + docker exec), so probe the herdr
# binary instead. Fails if herdr is missing/broken; Coolify reads container
# health status from this.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD herdr --version || exit 1

# Keep the container alive; attach with:  docker exec -it herdr herdr
CMD ["sleep", "infinity"]
