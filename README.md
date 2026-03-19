# Pakistan Courier Tracking Backend

## Commands

- `python -m pip install -r requirements.txt`
- `uvicorn app.main:app --reload`
- `pytest`

## Notes

- `Lightpanda` is preferred when browser execution is required.
- On Windows, the backend now prefers a lightweight local Chromium runner using `puppeteer-core` with an installed browser like Chrome or Brave before touching Edge WebDriver.
- On Windows, Lightpanda's official installation path is `WSL2 + Ubuntu`, then installing the Linux Lightpanda binary inside WSL. Source: [Lightpanda installation docs](https://lightpanda.io/docs/open-source/installation).
- The backend now checks browser runtimes in this order:
  - native `lightpanda` command
  - `lightpanda` installed inside the configured WSL distro
  - repo-local lightweight Chromium runner using an installed browser executable
- `Edge/Selenium` remains the final fallback when `Lightpanda` is unavailable or incompatible.
- Edge fallback first tries `EDGE_DRIVER_PATH`, then auto-downloads a matching driver with `webdriver-manager` if the local driver is missing or version-mismatched.
- Only `TCS` and `Pakistan Post` are wired with live adapters in this initial implementation. The remaining couriers are registered modular stubs so additional integrations can be added without restructuring the service.
- SSL verification uses `certifi` by default. If a machine has a custom corporate or local CA chain, set `CA_BUNDLE_PATH` to a PEM bundle. Use `VERIFY_SSL=false` only as a temporary local debugging fallback.

## Security

- Public docs are disabled by default. Set `ENABLE_PUBLIC_DOCS=true` only when you explicitly want `/docs`, `/redoc`, and `/openapi.json` exposed.
- Set `CORS_ALLOWED_ORIGINS` and `PUBLIC_API_ALLOWED_ORIGINS` to your real frontend origin in production, for example:
  - `https://www.paktrack.pk`
- Set `TRUSTED_HOSTS` to the exact production hosts you expect, for example:
  - `www.paktrack.pk,paktrack.pk,localhost,127.0.0.1`
- Public tracking routes now enforce:
  - origin checks
  - per-IP rate limits
  - request body size limits
  - hardened security headers
- Internal diagnostic routes require `BACKEND_SHARED_SECRET`.

Recommended production values:

- `APP_ENV=production`
- `CORS_ALLOWED_ORIGINS=https://www.paktrack.xyz,https://paktrack.xyz`
- `PUBLIC_API_ALLOWED_ORIGINS=https://www.paktrack.xyz,https://paktrack.xyz`
- `TRUSTED_HOSTS=api.paktrack.xyz,www.paktrack.xyz,paktrack.xyz`
- `ENABLE_PUBLIC_DOCS=false`
- `ENFORCE_ORIGIN_CHECK=true`
- `TRACK_RATE_LIMIT_PER_MINUTE=60`
- `BULK_RATE_LIMIT_PER_MINUTE=12`
- `HEALTH_RATE_LIMIT_PER_MINUTE=30`
- `INTERNAL_RATE_LIMIT_PER_MINUTE=30`

When the frontend is deployed behind a same-origin proxy such as Vercel serverless functions, set:
- `BACKEND_SHARED_SECRET=<strong-random-secret>`

Then let the proxy send `X-Shared-Secret` so the browser never talks to the backend directly.

## Windows Chromium runner

- The backend auto-detects these browser executables:
  - Chrome
  - Brave
  - Edge
- To force a specific browser path, set:
  - `BROWSER_EXECUTABLE_PATH=C:\Path\To\chrome.exe`
- Install the runner dependencies once:
  - `cd backend\browser_runner`
  - `npm.cmd install`

## Windows Lightpanda setup

1. From an administrator shell, install WSL if it is not already installed:
   - `wsl --install`
   - restart Windows
   - `wsl --install -d Ubuntu`
2. Open Ubuntu:
   - `wsl -d Ubuntu`
3. Inside WSL, install Lightpanda:
   - `curl -L -o lightpanda https://github.com/lightpanda-io/browser/releases/download/nightly/lightpanda-x86_64-linux`
   - `chmod a+x ./lightpanda`
   - move it somewhere on the WSL `PATH`, for example `~/bin/lightpanda`
4. In the backend `.env`, keep:
   - `LIGHTPANDA_WSL_DISTRO=Ubuntu`
   - `ALLOW_EDGE_FALLBACK=true`

After that, the backend will try WSL Lightpanda before Edge.
