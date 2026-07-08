"""PipeGuard dashboard — the operator's provenance & QC decision gate.

Deliberately a THIN view. All logic lives in the `pipeguard` package; this file
only loads a run, calls `run_gate`, and renders the decision cards. Porting to
FastAPI + React later means reusing `pipeguard` untouched and rewriting only
this rendering layer.

Run:  streamlit run app/streamlit_app.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Make the src/ package importable without an install step (dev convenience).
_SRC = Path(__file__).resolve().parent.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from pipeguard import DecisionCard, RunArtifacts, load_run, run_gate  # noqa: E402
from pipeguard.engine import get_synthesizer  # noqa: E402

DATA_ROOT = Path(__file__).resolve().parent.parent / "data"

# Verdict -> (emoji, accent color, human label)
VERDICT_STYLE = {
    "proceed": ("✅", "#1a7f37", "Proceed"),
    "hold": ("🟡", "#9a6700", "Hold"),
    "rerun": ("🔁", "#bc4c00", "Rerun"),
    "escalate": ("🚨", "#cf222e", "Escalate"),
}
SEVERITY_ICON = {"critical": "🔴", "warn": "🟠", "info": "🔵"}

st.set_page_config(page_title="PipeGuard — Decision Gate", page_icon="🧬", layout="wide")


@st.cache_data(show_spinner=False)  # type: ignore[untyped-decorator]
def _load(run_dir: str) -> RunArtifacts:
    return load_run(run_dir)


def _verdict_badge(verdict: str) -> str:
    emoji, color, label = VERDICT_STYLE.get(verdict, ("⚪", "#57606a", verdict))
    return (
        f"<span style='background:{color};color:white;padding:2px 10px;"
        f"border-radius:12px;font-weight:600;font-size:0.85rem'>{emoji} {label.upper()}</span>"
    )


def _render_card(card: DecisionCard) -> None:
    emoji, _color, label = VERDICT_STYLE.get(
        card.verdict.value, ("⚪", "#57606a", card.verdict.value)
    )
    open_by_default = card.is_actionable
    header = f"{emoji}  {card.sample_id} — {label.upper()}  ·  {card.headline}"

    with st.expander(header, expanded=open_by_default):
        left, right = st.columns([4, 1])
        with left:
            st.markdown(_verdict_badge(card.verdict.value), unsafe_allow_html=True)
            st.markdown(f"**{card.headline}**")
            st.write(card.rationale)
            if card.next_steps:
                st.markdown("**Recommended next steps**")
                for step in card.next_steps:
                    st.markdown(f"- {step}")
        with right:
            st.metric("Confidence", f"{card.confidence * 100:.0f}%")
            st.caption(f"narration: `{card.generated_by}`")

        if card.findings:
            st.markdown("**Supporting evidence**")
            rows = []
            for f in card.findings:
                evidence = "; ".join(
                    f"{e.source}"
                    + (f" [{e.locator}]" if e.locator else "")
                    + (f" = {e.value}" if e.value else "")
                    + (f" (expected {e.expected})" if e.expected else "")
                    for e in f.evidence
                )
                rows.append(
                    {
                        "": SEVERITY_ICON.get(f.severity.value, ""),
                        "Category": f.category.value,
                        "Rule": f.rule_id,
                        "Finding": f.title,
                        "Evidence": evidence,
                    }
                )
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        else:
            st.success("No provenance, metadata, or QC issues found for this sample.")


def main() -> None:
    st.title("🧬 PipeGuard")
    st.caption(
        "AI-assisted provenance & QC decision gate for a genomics run. "
        "Should each sample **proceed, hold, rerun, or escalate** — and why?"
    )

    # --- Sidebar: run selection + synthesizer status ---
    with st.sidebar:
        st.header("Run")
        runs = (
            sorted(p.name for p in DATA_ROOT.iterdir() if p.is_dir()) if DATA_ROOT.exists() else []
        )
        default_idx = runs.index("mock_run_01") if "mock_run_01" in runs else 0
        run_name = st.selectbox("Sequencing run", runs, index=default_idx) if runs else None

        synth = get_synthesizer()
        st.divider()
        st.subheader("Synthesizer")
        if synth.name == "claude":
            st.success("🤖 Live Claude synthesis is ON")
            st.caption(f"model: `{os.environ.get('PIPEGUARD_CLAUDE_MODEL', 'claude-opus-4-8')}`")
        else:
            st.info("📋 Offline rule-based narration (stub)")
            st.caption("Set `PIPEGUARD_SYNTHESIZER=claude` to enable live Claude synthesis.")

    if not run_name:
        st.warning(f"No runs found under `{DATA_ROOT}`.")
        return

    artifacts = _load(str(DATA_ROOT / run_name))
    cards = run_gate(artifacts, synthesizer=synth)

    # --- Summary strip ---
    counts = dict.fromkeys(VERDICT_STYLE, 0)
    for c in cards:
        counts[c.verdict.value] = counts.get(c.verdict.value, 0) + 1

    st.subheader(f"Run `{artifacts.run_id}` — {len(cards)} samples")
    cols = st.columns(5)
    cols[0].metric("Samples", len(cards))
    for col, verdict in zip(cols[1:], ("proceed", "hold", "rerun", "escalate"), strict=True):
        emoji, _, label = VERDICT_STYLE[verdict]
        col.metric(f"{emoji} {label}", counts.get(verdict, 0))

    actionable = [c for c in cards if c.is_actionable]
    if actionable:
        st.warning(
            f"**{len(actionable)} sample(s) need operator attention** before this run is released."
        )
    else:
        st.success("All samples cleared the gate.")

    st.divider()

    # --- Decision cards (already sorted most-urgent first) ---
    for card in cards:
        _render_card(card)

    # --- Export ---
    st.divider()
    payload = "[\n" + ",\n".join(c.model_dump_json(indent=2) for c in cards) + "\n]"
    st.download_button(
        "⬇️ Download decision cards (JSON)",
        payload,
        file_name=f"{artifacts.run_id}_decision_cards.json",
        mime="application/json",
    )


if __name__ == "__main__":
    main()
