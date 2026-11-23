"""Reparo: AI after-sales assistant for home-appliance brands (proof of concept).

Run locally:  streamlit run app.py
Secrets:      ANTHROPIC_API_KEY (and optionally REPARO_MODEL) in .streamlit/secrets.toml
"""

from __future__ import annotations

import base64
import io
import os
from datetime import date

import streamlit as st

import agent

st.set_page_config(page_title="Reparo · AI after-sales assistant", page_icon="🔧", layout="wide")

CSS = """
<style>
  html, body, [class*="css"] { font-family: 'Inter', 'Helvetica Neue', Arial, sans-serif; }
  .block-container { padding-top: 2rem; max-width: 1200px; }
  h1 { font-weight: 650; letter-spacing: -0.02em; font-size: 1.9rem !important; margin-bottom: 0 !important; }
  .sub { color: #5B6472; font-size: 0.95rem; margin-top: 0.2rem; margin-bottom: 1.2rem; }
  .kpi { border: 1px solid #E5E7EB; border-radius: 10px; padding: 12px 14px; margin-bottom: 10px; background: #FFFFFF; }
  .kpi .label { color: #5B6472; font-size: 0.78rem; text-transform: uppercase; letter-spacing: 0.04em; }
  .kpi .value { color: #0B1F3A; font-size: 1.55rem; font-weight: 650; line-height: 1.3; }
  .kpi .value.accent { color: #1F5EFF; }
  .tool { color: #5B6472; font-size: 0.8rem; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; margin: 2px 0; }
  .ticket { border-left: 3px solid #1F5EFF; padding: 6px 10px; margin: 6px 0; background: #F6F8FB; font-size: 0.84rem; }
  .handoff { border-left: 3px solid #D92D20; padding: 6px 10px; margin: 6px 0; background: #FEF3F2; font-size: 0.84rem; }
  .note { color: #8A93A2; font-size: 0.75rem; }
</style>
"""
st.markdown(CSS, unsafe_allow_html=True)

TOOL_LABELS = {
    "lookup_appliance": "Warranty register",
    "search_manual": "Service manual",
    "book_technician": "Technician booking",
    "log_outcome": "Case outcome",
    "escalate_to_human": "Hand-off to human",
}


def get_secret(name: str, default: str | None = None) -> str | None:
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.environ.get(name, default)


@st.cache_resource
def get_client(api_key: str):
    import anthropic
    return anthropic.Anthropic(api_key=api_key)


def reset():
    st.session_state.messages = []
    st.session_state.display = []
    st.session_state.state = agent.new_state()


if "messages" not in st.session_state:
    reset()

# ----------------------------------------------------------------------- sidebar
register = agent.load_register()
today = date.today()
with st.sidebar:
    st.markdown("### Demo appliances")
    st.caption("Fictional brand Arvel. Give one of these serial numbers to the assistant.")
    for a in register["appliances"]:
        end = agent.warranty_end(date.fromisoformat(a["purchase_date"]), register["legal_warranty_years"])
        status = "under warranty" if today <= end else "out of warranty"
        st.markdown(f"`{a['serial']}`  \n{a['type'].split(' (')[0]} · {status}")
    st.divider()
    models = {"Claude Sonnet 5.5 (default)": "claude-sonnet-5-5", "Claude Haiku 5.5 (cheapest)": "claude-haiku-5-5"}
    default_model = get_secret("REPARO_MODEL", "claude-sonnet-5-5")
    labels = list(models)
    idx = list(models.values()).index(default_model) if default_model in models.values() else 0
    model_label = st.selectbox("Model", labels, index=idx)
    model = models[model_label]
    if st.button("New conversation", width="stretch"):
        reset()
        st.rerun()
    st.markdown('<p class="note">Proof of concept. Fictional brand, products and customers. '
                'Answers are generated live by the model from the Arvel manuals.</p>', unsafe_allow_html=True)

# ------------------------------------------------------------------------ header
st.markdown("<h1>Reparo</h1>", unsafe_allow_html=True)
st.markdown('<div class="sub">AI after-sales assistant · demo for Arvel (fictional brand). '
            'Describe a problem with a washing machine, a dishwasher or a fridge, or send a photo of the display.</div>',
            unsafe_allow_html=True)

api_key = get_secret("ANTHROPIC_API_KEY")
if not api_key:
    st.error("No API key found. Add ANTHROPIC_API_KEY to the app secrets (see README).")
    st.stop()
client = get_client(api_key)

left, right = st.columns([2.1, 1], gap="large")


def render_events(events):
    for e in events:
        label = TOOL_LABELS.get(e["tool"], e["tool"])
        detail = ""
        inp, out = e["input"], e["output"]
        if e["tool"] == "lookup_appliance" and out.get("found"):
            detail = f"{out['model']} · {'under warranty until ' + out['warranty_end'] if out['under_warranty'] else 'out of warranty'}"
        elif e["tool"] == "search_manual":
            titles = [s["title"] for s in out.get("sections", [])][1:]
            detail = f"{inp.get('model')} · {', '.join(titles)}"
        elif e["tool"] == "book_technician" and out.get("booked"):
            detail = f"{out['ticket_id']} · {out['slot']} · part: {out['probable_part']}"
        elif e["tool"] == "log_outcome":
            detail = out.get("value") or inp.get("outcome", "")
        elif e["tool"] == "escalate_to_human":
            detail = f"{out.get('handoff_id')} · {inp.get('reason')} · priority {inp.get('priority')}"
        st.markdown(f'<div class="tool">→ {label}{" · " + detail if detail else ""}</div>', unsafe_allow_html=True)


def image_block(uploaded) -> tuple[dict, bytes]:
    from PIL import Image
    img = Image.open(uploaded)
    img = img.convert("RGB")
    img.thumbnail((1024, 1024))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    data = buf.getvalue()
    return ({"type": "image", "source": {"type": "base64", "media_type": "image/jpeg",
                                          "data": base64.b64encode(data).decode()}}, data)


def handle(text: str, files=None):
    content = []
    shown_image = None
    for f in files or []:
        block, raw = image_block(f)
        content.append(block)
        shown_image = raw
    content.append({"type": "text", "text": text or "Here is a photo of my appliance."})
    msgs = st.session_state.messages
    if msgs and msgs[-1]["role"] == "user":  # previous turn ended on tool results
        msgs[-1]["content"].extend(content)
    else:
        msgs.append({"role": "user", "content": content})
    st.session_state.display.append({"role": "user", "text": text, "image": shown_image})
    start = len(msgs)
    try:
        events = agent.run_turn(client, model, msgs, st.session_state.state, today)
    except Exception as exc:
        st.session_state.display.append({"role": "assistant", "text": f"Sorry, the assistant is unavailable right now ({type(exc).__name__}). Please try again.", "events": []})
        return
    texts = []
    for m in msgs[start:]:
        if m["role"] == "assistant":
            texts += [c["text"] for c in m["content"] if c.get("type") == "text" and c.get("text", "").strip()]
    st.session_state.display.append({"role": "assistant", "text": "\n\n".join(texts) or "…", "events": events})


with left:
    if not st.session_state.display:
        st.markdown("**Try for example**")
        examples = [
            "Mon lave-linge affiche E21 et l'eau ne s'évacue pas",
            "My fridge is not cold enough",
            "Ça sent le brûlé derrière mon lave-vaisselle",
        ]
        cols = st.columns(len(examples))
        for c, ex in zip(cols, examples):
            if c.button(ex, width="stretch"):
                st.session_state.pending = ex
    for item in st.session_state.display:
        with st.chat_message(item["role"]):
            if item.get("image"):
                st.image(item["image"], width=220)
            if item.get("events"):
                render_events(item["events"])
            if item.get("text"):
                st.markdown(item["text"])

prompt = st.chat_input("Describe the problem, or attach a photo of the display", accept_file=True,
                       file_type=["png", "jpg", "jpeg", "webp"])
pending = st.session_state.pop("pending", None)
if prompt or pending:
    if pending:
        text, files = pending, []
    elif isinstance(prompt, str):
        text, files = prompt, []
    else:
        text, files = prompt.text, prompt.files
    with left:
        with st.spinner("Reparo is checking the manual…"):
            handle(text, files)
    st.rerun()

# ------------------------------------------------------------------- ops panel
s = st.session_state.state
with right:
    st.markdown("#### Live operations")

    def kpi(label, value, accent=False):
        st.markdown(f'<div class="kpi"><div class="label">{label}</div>'
                    f'<div class="value{" accent" if accent else ""}">{value}</div></div>', unsafe_allow_html=True)

    kpi("Technician visits avoided", s["visits_avoided"], accent=True)
    kpi("Warranty cost avoided (brand)", f"{s['brand_cost_avoided_eur']} €", accent=True)
    if s["customer_fees_avoided_eur"]:
        kpi("Diagnostic fees avoided (customer)", f"{s['customer_fees_avoided_eur']} €")
    kpi("Technicians booked · hand-offs", f"{len(s['tickets'])} · {len(s['handoffs'])}")
    u = s["usage"]
    last = s["turn_latencies_s"][-1] if s["turn_latencies_s"] else 0
    kpi("AI cost of this conversation", f"${u['cost_usd']:.4f}")
    st.markdown(f'<p class="note">{u["calls"]} model calls · {u["input_tokens"]:,} input / {u["output_tokens"]:,} output tokens · '
                f'last answer in {last}s · {model}</p>', unsafe_allow_html=True)

    if s["tickets"]:
        st.markdown("##### Technician tickets")
        for t in s["tickets"]:
            fee = "covered by warranty" if t["covered_by_warranty"] else f"diagnostic fee {t['customer_fee_eur']} €"
            st.markdown(f'<div class="ticket"><b>{t["ticket_id"]}</b> · {t["model"]} · {t["city"]}<br>'
                        f'{t["slot"]} · {t["urgency"]} · {fee}<br>Probable part: <b>{t["probable_part"]}</b><br>'
                        f'<span class="note">{t["pre_diagnosis"]}</span></div>', unsafe_allow_html=True)
    if s["handoffs"]:
        st.markdown("##### Human hand-offs")
        for h in s["handoffs"]:
            st.markdown(f'<div class="handoff"><b>{h["handoff_id"]}</b> · {h["reason"]} · priority {h["priority"]} · '
                        f'callback {h["expected_callback"]}<br><span class="note">{h["summary"]}</span></div>',
                        unsafe_allow_html=True)
