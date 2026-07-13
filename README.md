# herdr — Coolify project

Debian bookworm container with **Claude Code** (official CLI) + **herdr** installed.
Runs idle; you attach a TTY to use it.

## Deploy in Coolify (project: `herdr`)

Coolify builds from a git repo, so:

1. Push this folder to a git repo (GitHub/GitLab) that Coolify can reach.
2. Coolify → **+ New** → **Project** → name it `herdr`.
3. Inside the project → **+ New Resource** → **Docker Compose** (or "Application"
   → build pack **Dockerfile**), point it at the repo above.
4. (Optional) Project → **Environment / Secrets** → add `CLAUDE_CODE_OAUTH_TOKEN`
   (see Auth below). Skip if you'll log in interactively.
5. **Deploy**.

> Coolify UI is on the host `:8000` (not the `:8080` tunnel).

## Use it

```
docker exec -it herdr herdr          # attach the multiplexer
# inside herdr, spawn a pane and run:
claude                               # first run -> /login if no token set
```

## Auth (sanctioned — official Claude Code CLI)

Two options, both legitimate uses of your Max subscription:

- **Headless token:** on any machine with Claude Code, run `claude setup-token`,
  paste the result into the Coolify secret `CLAUDE_CODE_OAUTH_TOKEN`. Redeploy.
- **Interactive:** leave the token unset, run `claude` inside the container,
  `/login`. Creds land in the `claude-config` volume and persist.

This is the official CLI consuming its own OAuth token — no interception layer.

## Notes

- herdr install is a piped remote installer; review `https://herdr.dev/install.sh`
  before trusting the build.
- Node 22.x is pinned via NodeSource; bump `setup_22.x` if you want a different LTS.
