## Deployment & Production Infrastructure

Be My Lens is deployed as a Dockerized FastAPI backend on a Hetzner VPS. Render is no longer the production backend.

### Production architecture

- Production API: `https://be-my-lens.planverse.io/`
- FastAPI listens on port `8000` inside the Docker container.
- Port `8000` is **not exposed publicly**.
- Caddy is the shared public reverse proxy for the VPS and terminates HTTPS.
- Caddy forwards `be-my-lens.planverse.io` to the Docker service `be-my-lens:8000`.
- The Be My Lens container and Caddy communicate over the external Docker network `proxy`.
- Planverse is a separate application/container and must not be coupled to this repository's application deployment.

The production filesystem is approximately:

```text
/opt/
├── be-my-lens/
│   ├── docker-compose.yml
│   ├── Dockerfile
│   ├── .env
│   └── server/
│       ├── app.py
│       ├── requirements.txt
│       └── prompts/
│
├── planverse/
│   └── ...
│
└── caddy/
    ├── docker-compose.yml
    └── Caddyfile
Docker

The application is built from /opt/be-my-lens/Dockerfile and run with /opt/be-my-lens/docker-compose.yml.

The Compose service is named be-my-lens and should:

use restart: unless-stopped
load production secrets from .env
expose port 8000 only to Docker networks
join the external proxy network so Caddy can reach it

Do not add a public ports: "8000:8000" mapping unless there is a specific operational reason.

Environment variables

Production secrets live only in /opt/be-my-lens/.env and must never be committed to Git.

Required variables:

OPENAI_API_KEY=
OPENAI_MODEL=gpt-4.1-mini
PROMPT_LOCALE=ar

.env.example may contain variable names and non-secret defaults, but never real credentials.

When changing environment variables, remember that the running container must be recreated for changes in .env to take effect.

Reverse proxy / DNS

Caddy is managed separately from this repository.

The relevant Caddy configuration is:

be-my-lens.planverse.io {
    reverse_proxy be-my-lens:8000
}

DNS for be-my-lens.planverse.io points to the Hetzner server. Caddy provides HTTPS automatically.

Do not modify or replace the shared Caddy setup from this repository unless the infrastructure configuration is intentionally being changed.

Deployment

The application should be deployed by updating the Docker image/container on the Hetzner server rather than by running FastAPI directly with a host-level Python installation.

The production deployment must preserve:

/opt/be-my-lens/.env
the Docker Compose configuration
access to the shared proxy network
the public hostname be-my-lens.planverse.io

The intended development flow is:

local development
    ↓
    git commit / push
    ↓
    GitHub
    ↓
    GitHub Actions builds the Docker image
    ↓
    production server updates the container

Do not place production secrets in GitHub repository files or inside the Docker image.

Manual deployment without GitHub integration

The GitHub Actions flow is not set up yet, so deploy changes manually until it is. Keep every manual deploy small, reversible, and verified.

Deploy from the WSL checkout to the Hetzner VPS:

1. Run backend tests locally first:

   ```bash
   cd server && .venv/bin/python -m pytest tests -q
   ```

2. Back up the current production server directory on the VPS, so rollback is one copy away:

   ```bash
   ssh <user>@<hetzner-host> "sudo cp -a /opt/be-my-lens/server /opt/be-my-lens/server.bak.$(date +%Y%m%d%H%M%S)"
   ```

3. Copy only the changed backend files (never `.env`) from the checkout to the VPS, for example for `server/app.py` and `server/prompts/`:

   ```bash
   rsync -av --exclude '.venv' --exclude '__pycache__' --exclude '.env' \
     server/app.py server/prompts server/requirements.txt \
     <user>@<hetzner-host>:/tmp/be-my-lens-upload/

   ssh <user>@<hetzner-host> "sudo rsync -a /tmp/be-my-lens-upload/ /opt/be-my-lens/server/"
   ```

4. Rebuild and restart the container:

   ```bash
   ssh <user>@<hetzner-host> "cd /opt/be-my-lens && sudo docker compose build && sudo docker compose up -d"
   ```

5. Verify:

   ```bash
   curl https://be-my-lens.planverse.io/health
   ssh <user>@<hetzner-host> "cd /opt/be-my-lens && sudo docker compose ps && sudo docker compose logs --tail 100 be-my-lens"
   ```

6. Roll back if health checks fail or behavior regresses: restore the backup from step 2 into `/opt/be-my-lens/server`, rerun step 4, and verify again.

Notes:

- `/opt/be-my-lens/.env` must never be overwritten by a deploy; it is excluded from every rsync above.
- Test a text-only endpoint manually after deploy, for example:

  ```bash
  curl -sS -X POST https://be-my-lens.planverse.io/translate_text \
    -H 'Content-Type: application/json' \
    -d '{"text": "hello"}'
  ```

  The expected response is a JSON object with an `answer` field.
- The Android app must point at the production backend via `API_BASE_URL` for on-device verification of the new mode.

Verification

The basic production health check is:

curl https://be-my-lens.planverse.io/health

Expected response:

{"status":"ok"}

For server-side troubleshooting:

cd /opt/be-my-lens
docker compose ps
docker compose logs --tail 100 be-my-lens

A healthy container should show Uvicorn listening on:

0.0.0.0:8000
