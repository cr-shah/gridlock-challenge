# GridLock AI Analyst — Gemini setup

AI explains. GIS verifies. Humans decide.

Snowflake is no longer required. The Python server reads the local project and analysis JSON files and sends facts from the current dataset mode to Gemini. The requested model is `gemini-3.8-flash`.

## Setup

The local `.venv` and dependencies have already been installed on this checkout. For a new checkout:

```sh
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements-analyst.txt
```

Create `.env` from `.env.example` only if it does not already exist. Get an API key from [Google AI Studio](https://aistudio.google.com/apikey) and paste it directly into `.env` locally:

```dotenv
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-3.8-flash
ANALYST_PORT=8002
```

Do not paste the key into chat or frontend files. `.env` is ignored by Git. Old Snowflake entries, if present, are unused and may be removed. API access depends on your Google project's model access and quota. See [Google's API key guide](https://ai.google.dev/gemini-api/docs/api-key).

Start the server from the repo:

```sh
cd /Users/havu/gridlock-challenge
.venv/bin/python -m analyst.server
```

Open **http://127.0.0.1:8002/**. Restart this server after changing `.env`. If the port is occupied, stop the previous analyst server with Ctrl+C in its terminal first. A static server or GitHub Pages cannot run the AI API.

## Demo

1. Select an opportunity in Coordination Radar, open **Ask GridLock**, and ask why it was flagged.
2. Choose **Generate Executive Brief**. Copy it or choose **Save as PDF**, then Save as PDF in the browser print dialog.
3. Select a project in Project Explorer and request a summary.
4. Ask “Show Georgia Power projects” or “What is GIS enrichment?”
5. Switch dataset modes and confirm that the response labels match. Unsupported questions should receive “No supporting evidence was found in the available GridLock dataset.”

The desktop drawer can be resized with its lower-left resize handle. Mobile sizing adapts to the viewport. Conversation history stays in page memory and clears on reload/navigation.

## Grounding

The server reads only the canonical publication in `data/published/` through `canonical_repository.py`. Projects use exact canonical project IDs. Saved Radar matches are hydrated from that catalog, and answers retain dataset-version and pipeline-commit provenance. Legacy/demo files are not used. Geometry state is explicitly VERIFIED, ESTIMATED or UNRESOLVED; unresolved projects remain searchable. Local artifact hashes and matching publication versions are validated before loading. See `CANONICAL_INTEGRATION.md` for the upstream manifest verification limitation.

Gemini writes concise explanations and returns supporting fact IDs. The server validates references against the current dataset and checks that numbers appear in cited facts. These checks do not prove every generated claim: users should review the attached evidence. HTML is stripped from source content before it enters the prompt and from response content before display. The UI supports a limited safe Markdown subset (paragraphs, headings, bold and lists), never raw HTML.

Greetings run locally without an API call. Unsupported questions receive a helpful redirect. Answers end with the evidence disclaimer. Missing purpose/geography is not inferred; place-name queries do not calculate proximity. Gemini requests use the configured free-tier project; the application never upgrades billing or falls back to a paid provider.

Executive briefing values come directly from the selected saved GIS result. AI never writes data or runs/replaces the scoring engine. Model relevance still needs human review. Public dataset facts and questions are sent to Google; credentials remain on the server.

The server binds to localhost for the demo. Public hosting requires HTTPS, authentication, request limits and managed secrets.

## Verification

```sh
.venv/bin/python -m unittest discover -s tests -p 'test_analyst.py'
```

Tests mock Gemini. A live answer must also be tested after adding a valid key. Configuration status only confirms that a key is present, not that it works.
