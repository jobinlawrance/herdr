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

# herdr
# NOTE: this is a piped remote installer (curl | sh). Review the script at
# https://herdr.dev/install.sh before building if you don't already trust it.
# If the installer needs a non-default path, set it here.
RUN curl -fsSL https://herdr.dev/install.sh | sh

# Run as non-root (Claude Code refuses --dangerously-skip-permissions as root,
# and running interactive tooling as root is a bad default)
RUN useradd -m -s /bin/bash agent
USER agent
WORKDIR /home/agent/workspace

# Keep the container alive; attach with:  docker exec -it herdr herdr
CMD ["sleep", "infinity"]
