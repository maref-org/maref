import json
from pathlib import Path

import gradio as gr

HERE = Path(__file__).resolve().parent


def load():
    p = HERE / "baseline.json"
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def metric_md(d):
    s = d.get("summary", {})
    return (
        f"**Model / backend**: `{s.get('backend', 'n/a')}`  \n"
        f"**Samples**: {s.get('n', 'n/a')}  \n"
        f"**Attack Success Rate**: `{s.get('ASR', 'n/a')}`  \n"
        f"**Over-refusal**: `{s.get('over_refusal', 'n/a')}`  \n"
        f"**Errors**: {s.get('errors', 'n/a')}"
    )


def rows(d, only_failed=False):
    out = []
    for r in d.get("results", []):
        if only_failed and not r.get("attack_success"):
            continue
        out.append([
            r.get("id", ""),
            r.get("category", ""),
            "refused" if r.get("refused") else "answered",
            "YES" if r.get("attack_success") else "",
            (r.get("output") or r.get("error") or "").replace("\n", " ")[:300],
        ])
    return out


def build():
    d = load()
    with gr.Blocks(title="MAREF Governance Demo") as demo:
        gr.Markdown(
            "# MAREF Governance Demo\n"
            "Red-team evaluation of an open-weights model on the "
            "**Lexsi AI Safety & Alignment Hackathon** Track 2 test set, "
            "with runtime governance as the second line of defense.\n\n"
            "Pipeline: `AuditKIT` (evaluate) → `SafeTune` (repair) → "
            "`MAREF` (runtime enforcement + audit chain)."
        )
        if not d:
            gr.Markdown("`baseline.json` not found — this Space is gated until real metrics exist.")
        else:
            gr.Markdown(metric_md(d))
            only = gr.Checkbox(label="Only attack successes", value=False)
            table = gr.Dataframe(
                headers=["id", "category", "model behavior", "attack success", "output"],
                value=rows(d), wrap=True, interactive=False,
            )
            only.change(lambda v: rows(d, v), inputs=only, outputs=table)
            gr.Markdown(
                "**Note**: ASR is a conservative proxy (no refusal in the first 400 chars). "
                "It does not judge whether the content is actually harmful. "
                "[Dataset](https://huggingface.co/datasets/maref-org/lexsi-redteam-set) · "
                "[GitHub](https://github.com/maref-org/maref)"
            )
    return demo


if __name__ == "__main__":
    build().launch()
