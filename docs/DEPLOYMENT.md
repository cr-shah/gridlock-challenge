# Public deployment

The nationwide frontend and Python API must run together. GitHub Pages on the
older `demo` branch cannot run the national catalog, site context, or weather API.

## Deploy on Render Free

[Deploy the main branch on Render](https://render.com/deploy?repo=https://github.com/cr-shah/gridlock-challenge).

Sign in to an existing Render account, connect this repository if requested, and
review its Blueprint. It must show **one Free Python web service**, no databases,
no disks, and no paid resources. Do not accept a paid plan or billing commitment.
If the workspace already has a payment method, check its usage/spend controls:
Free compute does not automatically waive bandwidth or build-minute overages.
Deploy it and copy the actual `https://…onrender.com` address from the dashboard;
the service name does not guarantee a particular hostname.

The root `render.yaml` pins `main`, a Free instance in Virginia, the build/start
commands, and `/healthz`. Automatic deployment is off: later commits require a
manual deploy. `.python-version` selects Python 3.13.12. Build artifacts include
the already-published regional catalog, national gzip, and historical weather ZIP;
there is no sibling-repository, persistent-storage, or import-job dependency.

No API keys are needed. NWS/USDA/FWS provider calls remain server-side and bounded.
The public entrypoint does **not** load `.env`, import the AI analyst, or expose a
paid Gemini endpoint. AI returns an explicit disabled status, even if a key is
accidentally present in the host environment. The local analyst server is unchanged.

Reference: [Render web services](https://render.com/docs/web-services),
[Blueprint fields](https://render.com/docs/blueprint-spec),
[Free-service limits](https://render.com/docs/free), and
[Python versions](https://render.com/docs/python-version).
Free services spin down after 15 idle minutes and may take about a minute to wake.
They have usage limits and are intended for demos, not availability guarantees.
This app needs no database or persistent disk; its in-memory caches may reset.

## Run the production entrypoint locally

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-hosting.txt
PORT=8010 .venv/bin/gunicorn --config deploy/gunicorn.conf.py deploy.wsgi:application
```

Gunicorn listens on `0.0.0.0:$PORT`, with one worker and eight threads to share the
indexed catalog. Six simultaneous national API operations are admitted, leaving
capacity for health checks and static pages. Startup validates national/regional
publication hashes and the weather archive hash; bad artifacts prevent readiness.
Static file serving allows only root HTML/CSS/JS and published regional JSON.
Credentials, Git metadata, Python sources, and raw national archives are blocked.

## Verify the actual public address

After deployment, substitute the dashboard's URL:

```sh
curl --fail https://YOUR-ACTUAL-HOST.onrender.com/healthz
curl --fail https://YOUR-ACTUAL-HOST.onrender.com/api/nation/geography
curl --fail 'https://YOUR-ACTUAL-HOST.onrender.com/api/nation/projects?state=13&limit=5'
curl --fail 'https://YOUR-ACTUAL-HOST.onrender.com/api/nation/history?lon=-82&lat=34'
curl --fail 'https://YOUR-ACTUAL-HOST.onrender.com/api/nation/site?provider=nws-forecast&lon=-82&lat=34'
```

In a browser verify:

- `/`: national map/filtering, project selection and source evidence.
- **3D time lens**: dates, playback, tilt and confidence legend.
- **Historical work-window lab**: station provenance and completed/excluded trials.
- `/index.html?view=radar`: original regional map and opportunity selection.
- `/project-explorer.html` and `/project-discovery.html`: original catalogs.
- `/.env`, `/.git/config`, and `/data/nation/weather.zip`: HTTP 404.
- `/api/analyst/status`: `ready: false`, public-demo explanation.

Leaflet/MapLibre tiles and scripts require access to their existing public CDNs.
Live public providers can return explicit unavailable or stale statuses; that must
not be mistaken for newly observed site conditions.

## Deployment status at preparation

The October 7 scheduled run found authenticated GitHub access but no Python-hosting
token, connected hosting integration, or authenticated Render browser session.
Render opened its sign-in page. The configuration is deployment-ready; preparation
and local checks are **not** proof of a live public deployment. The exact remaining
requirement is an authenticated Render account with permission to deploy this repo
on Free (or equivalent existing Python hosting access). Account creation and paid
plans require the user's action/authorization.
