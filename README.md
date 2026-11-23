# Reparo: AI after-sales assistant (proof of concept)

Reparo diagnoses a home-appliance problem with the customer, from the brand's own manuals.
It solves the problem remotely when the manual allows it (no technician trip), and otherwise
books a technician with a pre-diagnosis (the right part on the first visit).
Safety cases and out-of-scope requests go to a human, with a summary.

**Moment of truth:** a customer writes "My washing machine shows E21 and won't drain" (or sends a photo of the
display). In seconds Reparo finds the appliance, checks the warranty, guides the 3 manual steps, and logs
"technician visit avoided: 90 EUR". If the problem persists, it books a technician with the probable part.

Everything is fictional: the brand Arvel, its 3 products, manuals and 6 customers (`data/`).

## How it works

- `agent.py`: a tool-use loop around one Claude model, with 5 tools:
  `lookup_appliance` (warranty register), `search_manual` (retrieval in the manual sections),
  `book_technician`, `log_outcome`, `escalate_to_human`.
- `app.py`: the Streamlit interface (chat + photo upload + "Live operations" panel with visits avoided,
  euros avoided, tickets, hand-offs and the AI cost of the conversation).
- `data/`: warranty register (`appliances.json`) and customer-level manuals (`manuals/*.md`).
- `tests/test_agent.py`: offline tests with a scripted fake model (`python tests/test_agent.py`).

## Deploy on Streamlit Community Cloud (about 15 minutes)

1. **API key.** Either an OpenRouter key (https://openrouter.ai, with a few dollars of credit) or an Anthropic key (https://platform.claude.com).
   A demo conversation costs about $0.04 with Claude Sonnet 5.5.
2. **GitHub.** Create a new repository (public or private) and upload the whole `reparo` folder
   (`app.py` must be at the root of the repository).
3. **Streamlit.** Go to https://share.streamlit.io, sign in with GitHub, click "Create app", pick the
   repository, branch `main`, main file `app.py`.
4. **Secret.** In "Advanced settings" → "Secrets", paste ONE of these lines:
   ```
   OPENROUTER_API_KEY = "sk-or-..."
   ```
   (OpenRouter key: the app calls Claude through OpenRouter) or
   ```
   ANTHROPIC_API_KEY = "sk-ant-..."
   ```
   (Anthropic key: the app calls Claude directly). If both are set, OpenRouter is used.
   Optional: `REPARO_MODEL = "anthropic/claude-haiku-5.5"` (OpenRouter) or `"claude-haiku-5-5"` (Anthropic)
   to use the cheapest model by default.
5. Deploy. You get a public URL like `https://reparo-xxxx.streamlit.app`: this is the link to e-mail.
6. Set a spending limit on the API key (platform console) and never show the key on screen.

Note: a free Streamlit app goes to sleep after a few days without visits. Open the link the morning
of the defence so it wakes up (about 30 seconds).

Run locally instead: `pip install -r requirements.txt`, put the key in `.streamlit/secrets.toml`
(same line as above), then `streamlit run app.py`.

## Demo script (3 minutes, slide 3)

1. **Context (1 sentence):** "Half of the technician visits under warranty need no spare part."
2. **Happy path:** "Mon lave-linge affiche E21 et l'eau ne s'évacue pas", serial `WM7-2503-1832`.
   Follow the steps, answer "c'est bon, ça marche". Point at the panel: 1 visit avoided, 90 €.
3. **Jury input:** a juror picks any appliance in the sidebar and describes a problem in their own words
   (or takes a photo of an error code written on paper).
4. **Edge cases:** "Ça sent le brûlé derrière mon lave-vaisselle" → safety instructions + human hand-off.
   "Je veux être remboursé" → hand-off with summary.
5. **Numbers:** the panel shows the AI cost of the conversation (about $0.04) against 90 € avoided,
   and the answer time.

## Test inputs

| Type | Input | Expected |
|---|---|---|
| Easy | "My washing machine shows E21", serial WM7-2503-1832 | Filter steps; resolved → 90 € avoided |
| Easy | "Mon frigo ne refroidit plus assez", serial RF3-2602-1405 | Setting, vents, seal; wait 24 h |
| Tricky | "Lave-vaisselle E15, j'ai mis du liquide vaisselle", DW5-2509-2211 | Foam explanation, dry 12 h |
| Tricky | "Lave-vaisselle E09", DW5-2201-0150 (out of warranty) | Reset, then technician with 89 € fee announced, agreement asked |
| Out of scope / safety | "Ça sent le brûlé", any serial | Safety lines + urgent hand-off, no troubleshooting |

## Limits (say them before the jury asks)

- Fictional data; in production the agent connects to the brand's warranty CRM, manuals and repair network.
- Only customer-level steps from the manual are allowed; the agent never asks to open the appliance.
- The euro counter assumes 90 € per warranty visit (assumption for the pitch).
