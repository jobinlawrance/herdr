# syntax=docker/dockerfile:1
# Pinned by digest so a moving `bookworm-slim` tag can't silently invalidate
# every cached layer below. Bump deliberately: docker pull debian:bookworm-slim
# && docker inspect --format '{{index .RepoDigests 0}}' debian:bookworm-slim
FROM debian:bookworm-slim@sha256:60eac759739651111db372c07be67863818726f754804b8707c90979bda511df

ENV DEBIAN_FRONTEND=noninteractive

# Keep apt's downloaded lists + debs in BuildKit cache mounts instead of the
# image, so a rebuild of this layer reuses them instead of re-fetching. The
# default docker-clean hook wipes /var/cache/apt after install, so disable it.
RUN rm -f /etc/apt/apt.conf.d/docker-clean \
    && echo 'Binary::apt::APT::Keep-Downloaded-Packages "true";' > /etc/apt/apt.conf.d/keep-cache

# Base tooling. Cache mounts aren't part of the image layer, so no manual
# `rm -rf /var/lib/apt/lists` is needed to stay slim.
RUN --mount=type=cache,target=/var/cache/apt,sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,sharing=locked \
      apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl git openssh-client ripgrep less tmux python3 \
    && curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y --no-install-recommends nodejs

# Claude Code — official Anthropic CLI, installed globally. npm cache persists
# across rebuilds via the cache mount.
RUN --mount=type=cache,target=/root/.npm \
    npm install -g @anthropic-ai/claude-code

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
# the non-root agent user (~/.local/bin). The uv download cache is mounted
# (uid/gid 1000 = agent, the first useradd -m user) so re-runs skip the
# Python 3.14 download; the installed tool itself lands in the image.
ENV PATH="/home/agent/.local/bin:${PATH}"
RUN --mount=type=cache,target=/home/agent/.cache/uv,uid=1000,gid=1000 \
    curl -LsSf https://astral.sh/uv/install.sh | sh \
    && uv tool install --python 3.14 ccgram \
    && uv tool list | grep -q ccgram

# Health: no HTTP port, so probe the herdr binary — cheap proof the image
# tooling is intact. Coolify reads container health status from this.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD herdr --version || exit 1

# Telegram bridge is the main process (long-lived poller). Needs
# TELEGRAM_BOT_TOKEN + ALLOWED_USERS in env (Coolify secrets) or it exits.
# Attach a shell anytime:  docker exec -it herdr bash   (or `herdr`)
#
# ccgram defaults to CCGRAM_MULTIPLEXER=herdr, which needs the headless herdr
# server running first — otherwise ccgram crash-loops with "herdr server is not
# running". Start the daemon, wait for its API socket, then exec ccgram as PID 1.
CMD ["sh", "-lc", "herdr server >/tmp/herdr-server.log 2>&1 & until herdr status server >/dev/null 2>&1; do sleep 0.5; done; exec ccgram"]
