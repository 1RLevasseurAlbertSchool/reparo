"""Offline tests: a scripted fake model drives the real tool loop."""

import sys
from datetime import date
from pathlib import Path
from types import SimpleNamespace as NS

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import agent  # noqa: E402

TODAY = date(2026, 11, 23)


def text(t):
    return NS(type="text", text=t)


def tool(i, name, inp):
    return NS(type="tool_use", id=i, name=name, input=inp)


class FakeClient:
    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        self.messages = self

    def create(self, **kw):
        self.calls.append(kw)
        content, stop = self.script.pop(0)
        return NS(content=content, stop_reason=stop, usage=NS(input_tokens=3000, output_tokens=250))


def test_tools_direct():
    s = agent.new_state()
    a = agent.tool_lookup_appliance({"serial_number": "wm7-2503-1832"}, s, TODAY)
    assert a["found"] and a["under_warranty"] and a["warranty_end"] == "2027-03-14"
    b = agent.tool_lookup_appliance({"serial_number": "WM7-2306-0419"}, s, TODAY)
    assert not b["under_warranty"] and b["out_of_warranty_diagnostic_fee_eur"] == 89
    m = agent.tool_search_manual({"model": "WM-7", "query": "E21 l'eau ne s'évacue pas"}, s, TODAY)
    titles = [x["title"] for x in m["sections"]]
    assert titles[0].startswith("SAFETY") and titles[1].startswith("E21"), titles
    f = agent.tool_search_manual({"model": "RF-3", "query": "fridge not cold enough"}, s, TODAY)
    assert "not cold" in f["sections"][1]["title"].lower(), f["sections"][1]["title"]
    t = agent.tool_book_technician({"serial_number": "DW5-2201-0150", "symptom_summary": "E09",
                                     "probable_part": "heat pump", "urgency": "standard"}, s, TODAY)
    assert t["booked"] and t["customer_fee_eur"] == 89 and t["slot"].startswith("Wed 25 Nov")
    print("direct tools OK:", titles[:2], t["slot"])


def test_resolved_flow():
    script = [
        ([text("Je regarde."), tool("t1", "lookup_appliance", {"serial_number": "WM7-2503-1832"})], "tool_use"),
        ([tool("t2", "search_manual", {"model": "WM-7", "query": "E21 vidange"})], "tool_use"),
        ([text("1. Débranchez la machine…")], "end_turn"),
        ([tool("t3", "log_outcome", {"serial_number": "WM7-2503-1832", "outcome": "resolved_remotely",
                                     "summary": "filtre nettoyé"})], "tool_use"),
        ([text("Parfait, un déplacement de technicien a été évité.")], "end_turn"),
    ]
    c = FakeClient(script)
    s = agent.new_state()
    msgs = [{"role": "user", "content": [{"type": "text", "text": "E21, série WM7-2503-1832"}]}]
    ev = agent.run_turn(c, "claude-sonnet-5-5", msgs, s, TODAY)
    assert [e["tool"] for e in ev] == ["lookup_appliance", "search_manual"]
    assert msgs[-1]["role"] == "assistant"
    msgs.append({"role": "user", "content": [{"type": "text", "text": "Ça marche !"}]})
    ev2 = agent.run_turn(c, "claude-sonnet-5-5", msgs, s, TODAY)
    assert s["visits_avoided"] == 1 and s["brand_cost_avoided_eur"] == 90
    # role alternation and tool_result pairing
    for prev, nxt in zip(msgs, msgs[1:]):
        assert prev["role"] != nxt["role"], (prev["role"], nxt["role"])
    assert abs(s["usage"]["cost_usd"] - 5 * (3000 * 2 + 250 * 10) / 1e6) < 1e-9
    print("resolved flow OK; cost per conversation $%.4f over %d calls" % (s["usage"]["cost_usd"], s["usage"]["calls"]))


def test_safety_flow():
    script = [
        ([tool("t1", "escalate_to_human", {"reason": "safety", "priority": "high", "summary": "odeur de brûlé"}),
          tool("t2", "log_outcome", {"serial_number": "unknown", "outcome": "handed_off", "summary": "sécurité"})], "tool_use"),
        ([text("Débranchez si la prise est sèche… un conseiller vous rappelle sous 15 minutes.")], "end_turn"),
    ]
    c = FakeClient(script)
    s = agent.new_state()
    msgs = [{"role": "user", "content": [{"type": "text", "text": "ça sent le brûlé"}]}]
    agent.run_turn(c, "claude-sonnet-5-5", msgs, s, TODAY)
    assert s["handoffs"][0]["expected_callback"] == "within 15 minutes" and s["visits_avoided"] == 0
    sys_prompt = c.calls[0]["system"]
    assert "SAFETY FIRST" in sys_prompt and c.calls[0]["tools"] == agent.TOOLS
    print("safety flow OK")


if __name__ == "__main__":
    test_tools_direct()
    test_resolved_flow()
    test_safety_flow()
    print("ALL TESTS PASSED")
