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

# ccgram — control Claude Code from Telegram. It drives tmux (installed above),
# not an agent SDK, so your session stays the source of truth. Needs Python
# 3.14; uv fetches + pins it independent of the system python3. Installed under
# the non-root agent user (~/.local/bin).
ENV PATH="/home/agent/.local/bin:${PATH}"
RUN curl -LsSf https://astral.sh/uv/install.sh | sh \
    && uv tool install --python 3.14 ccgram \
    && uv tool list | grep -q ccgram

# Health: no HTTP port, so probe the herdr binary — cheap proof the image
# tooling is intact. Coolify reads container health status from this.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD herdr --version || exit 1

# Telegram bridge is the main process (long-lived poller). Needs
# TELEGRAM_BOT_TOKEN + ALLOWED_USERS in env (Coolify secrets) or it exits.
# Attach a shell anytime:  docker exec -it herdr bash   (or `herdr`)
CMD ["ccgram"]
