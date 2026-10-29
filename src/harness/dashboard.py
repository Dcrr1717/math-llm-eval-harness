"""Render results/summary.json into a self-contained results/dashboard.html."""
from __future__ import annotations

import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SUMMARY = ROOT / "results" / "summary.json"
OUT = ROOT / "results" / "dashboard.html"

_CSS = """
:root{--bg:#f7f8fa;--card:#fff;--ink:#14213a;--muted:#5b6b86;--line:#e5e9f0;
--accent:#145A96;--accent2:#14784B;--bar:#145A96;--barbg:#e8eef5}
@media (prefers-color-scheme:dark){:root{--bg:#0f1420;--card:#171d2b;--ink:#e8edf6;
--muted:#9aa7bd;--line:#273146;--accent:#5aa0e0;--accent2:#5ac08a;--bar:#5aa0e0;--barbg:#223049}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.5 -apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;padding:24px 16px}
.wrap{max-width:980px;margin:0 auto}h1{font-size:24px;margin:0 0 4px}
.sub{color:var(--muted);margin:0 0 20px}
.cards{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:22px}
.kpi{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:14px 18px;flex:1;min-width:150px}
.kpi .v{font-size:26px;font-weight:700}.kpi .l{color:var(--muted);font-size:13px}
.card{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:18px;margin-bottom:18px}h2{font-size:17px;margin:0 0 12px}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:8px 10px;
border-bottom:1px solid var(--line);font-variant-numeric:tabular-nums}
th{color:var(--muted);font-weight:600;font-size:13px}td.num,th.num{text-align:right}
.bar{position:relative;background:var(--barbg);border-radius:6px;height:22px;min-width:60px}
.bar>span{position:absolute;left:0;top:0;bottom:0;background:var(--bar);border-radius:6px}
.bar>b{position:absolute;right:6px;top:0;line-height:22px;font-size:12px;font-weight:600}
.foot{color:var(--muted);font-size:12px;margin-top:8px}
code{background:var(--barbg);padding:1px 5px;border-radius:4px}
"""


def _bar(frac: float, label: str) -> str:
    pct = max(0.0, min(1.0, frac)) * 100
    return f'<div class="bar"><span style="width:{pct:.1f}%"></span><b>{label}</b></div>'


def render(summary: dict) -> str:
    ov = summary.get("overall", {})
    models = summary.get("models", {})
    by_ds = summary.get("by_dataset", {})
    by_topic = summary.get("by_topic", {})
    gm = summary.get("grade_methods", {})
    datasets = summary.get("datasets_present", [])

    # KPIs
    kpis = [
        ("Problems evaluated", f"{ov.get('count',0):,}"),
        ("Overall accuracy", f"{ov.get('accuracy',0):.1%}"),
        ("Total cost", f"${ov.get('cost_usd',0):.2f}"),
        ("Models", f"{len(models)}"),
    ]
    kpi_html = "".join(
        f'<div class="kpi"><div class="v">{html.escape(v)}</div>'
        f'<div class="l">{html.escape(l)}</div></div>'
        for l, v in kpis
    )

    # by model
    rows = ""
    for m, a in sorted(models.items(), key=lambda kv: -kv[1]["accuracy"]):
        acc_lbl = f"{a['accuracy']:.1%}"
        rows += (
            f"<tr><td><b>{html.escape(m)}</b></td>"
            f"<td>{_bar(a['accuracy'], acc_lbl)}</td>"
            f"<td class='num'>{a['count']:,}</td>"
            f"<td class='num'>${a['cost_usd']:.2f}</td>"
            f"<td class='num'>{a['avg_latency_s']:.1f}s</td></tr>"
        )
    model_table = (
        "<table><tr><th>Model</th><th>Accuracy</th><th class='num'>n</th>"
        "<th class='num'>Cost</th><th class='num'>Latency</th></tr>"
        f"{rows}</table>"
    )

    # by dataset (model rows x dataset cols)
    ds_html = ""
    if datasets:
        head = "".join(f"<th class='num'>{html.escape(d)}</th>" for d in datasets)
        body = ""
        for m in sorted(models):
            cells = ""
            for d in datasets:
                a = by_ds.get(m, {}).get(d)
                cells += (
                    f"<td class='num'>{a['accuracy']:.1%}<br><small>n={a['count']}</small></td>"
                    if a else "<td class='num'>-</td>"
                )
            body += f"<tr><td><b>{html.escape(m)}</b></td>{cells}</tr>"
        ds_html = (
            f"<table><tr><th>Model</th>{head}</tr>{body}</table>"
        )

    # grade methods
    gm_html = " · ".join(
        f"{html.escape(k)}: <b>{v}</b>" for k, v in sorted(gm.items(), key=lambda kv: -kv[1])
    ) or "sin datos"

    # topics for the best model
    topic_html = ""
    if by_topic and models:
        best = max(models, key=lambda m: models[m]["accuracy"])
        tmap = by_topic.get(best, {})
        trows = ""
        for t, a in sorted(tmap.items(), key=lambda kv: -kv[1]["accuracy"]):
            acc_lbl = f"{a['accuracy']:.1%}"
            trows += (
                f"<tr><td>{html.escape(t)}</td>"
                f"<td>{_bar(a['accuracy'], acc_lbl)}</td>"
                f"<td class='num'>{a['count']}</td></tr>"
            )
        topic_html = (
            f"<div class='card'><h2>Accuracy by topic — {html.escape(best)}</h2>"
            f"<table><tr><th>Topic</th><th>Accuracy</th><th class='num'>n</th></tr>"
            f"{trows}</table></div>"
        )

    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Math LLM Evaluation — Results</title><style>{_CSS}</style></head>
<body><div class="wrap">
<h1>Math LLM Evaluation</h1>
<p class="sub">Accuracy, cost and latency of Claude models on GSM8K, MATH and a custom
problem set. Grading: exact / numeric / symbolic (SymPy).</p>
<div class="cards">{kpi_html}</div>
<div class="card"><h2>By model</h2>{model_table}
<p class="foot">Correct-grade methods — {gm_html}</p></div>
<div class="card"><h2>Accuracy by dataset</h2>{ds_html}</div>
{topic_html}
<p class="foot">Generated by math-llm-eval-harness · prices used for the cost column are
defined in <code>config/models.yaml</code> (verify against the official pricing page).</p>
</div></body></html>"""


def build_dashboard() -> Path:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8")) if SUMMARY.exists() else {}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(render(summary), encoding="utf-8")
    print(f"[dashboard] -> {OUT}")
    return OUT
