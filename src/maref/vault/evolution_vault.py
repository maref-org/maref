"""EvolutionVault — RSI 实验结果持久化 + 趋势分析 + 可视化"""

from __future__ import annotations

import csv
import json
import logging
import statistics
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ExperimentRecord:
    timestamp: str
    target: str
    consistency_score: float
    action: str  # keep / discard
    dimensions: dict[str, float] = field(default_factory=dict)
    notes: str = ""
    mas_ts_score: float = 0.0
    mas_ts_level: str = ""
    duration_s: float = 0.0
    delta: float = 0.0


@dataclass
class TrendSummary:
    target: str
    total_runs: int
    keep_count: int
    discard_count: int
    avg_score: float
    best_score: float
    latest_score: float
    score_trend: str  # improving / declining / stable
    volatility: float
    keep_rate: float
    window_scores: list[float]


class EvolutionVault:
    """持久化实验记录 + 趋势分析 + 仪表板生成"""

    def __init__(self, vault_path: str | Path = "vault"):
        self.vault_path = Path(vault_path)
        self.results_file = self.vault_path / "evolution_vault.tsv"
        self.reports_dir = self.vault_path / "reports"
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    RECORD_HEADER = [
        "timestamp", "target", "consistency_score", "action",
        "dimensions", "notes", "mas_ts_score", "mas_ts_level",
        "duration_s", "delta",
    ]

    def record(self, entry: ExperimentRecord) -> None:
        file_exists = self.results_file.exists() and self.results_file.stat().st_size > 0
        with open(self.results_file, "a", encoding="utf-8", newline="") as f:
            writer = csv.writer(f, delimiter="\t")
            if not file_exists:
                writer.writerow(self.RECORD_HEADER)
            writer.writerow([
                entry.timestamp,
                entry.target,
                f"{entry.consistency_score:.4f}",
                entry.action,
                json.dumps(entry.dimensions, ensure_ascii=False),
                entry.notes,
                f"{entry.mas_ts_score:.1f}",
                entry.mas_ts_level,
                f"{entry.duration_s:.2f}",
                f"{entry.delta:.4f}",
            ])

    def load_all(self) -> list[ExperimentRecord]:
        if not self.results_file.exists():
            return []
        with open(self.results_file, encoding="utf-8") as f:
            reader = csv.DictReader(f, delimiter="\t", fieldnames=self.RECORD_HEADER)
            records = []
            for i, row in enumerate(reader):
                if i == 0 and all(row.get(k, "") == k for k in self.RECORD_HEADER):
                    continue
                try:
                    dims = json.loads(row.get("dimensions", "{}") or "{}")
                except (json.JSONDecodeError, TypeError):
                    dims = {}
                records.append(ExperimentRecord(
                    timestamp=row.get("timestamp", ""),
                    target=row.get("target", ""),
                    consistency_score=float(row.get("consistency_score", 0) or 0),
                    action=row.get("action", ""),
                    dimensions=dims,
                    notes=row.get("notes", ""),
                    mas_ts_score=float(row.get("mas_ts_score", 0) or 0),
                    mas_ts_level=row.get("mas_ts_level", ""),
                    duration_s=float(row.get("duration_s", 0) or 0),
                    delta=float(row.get("delta", 0) or 0),
                ))
            return records

    def get_trend(self, target: str, window: int = 20) -> TrendSummary:
        records = self.load_all()
        target_records = [r for r in records if r.target == target]
        if not target_records:
            return TrendSummary(
                target=target, total_runs=0, keep_count=0, discard_count=0,
                avg_score=0.0, best_score=0.0, latest_score=0.0,
                score_trend="stable", volatility=0.0, keep_rate=0.0,
                window_scores=[],
            )

        recent = target_records[-window:]
        scores = [r.consistency_score for r in recent]
        keeps = sum(1 for r in target_records if r.action == "keep")
        discards = sum(1 for r in target_records if r.action == "discard")

        avg_score = sum(scores) / len(scores) if scores else 0.0
        best_score = max(scores) if scores else 0.0
        latest_score = scores[-1] if scores else 0.0
        volatility = statistics.stdev(scores) if len(scores) > 1 else 0.0

        if len(scores) >= 3:
            first_half = sum(scores[:len(scores)//2]) / (len(scores)//2)
            second_half = sum(scores[len(scores)//2:]) / (len(scores) - len(scores)//2)
            if second_half - first_half > 0.02:
                score_trend = "improving"
            elif first_half - second_half > 0.02:
                score_trend = "declining"
            else:
                score_trend = "stable"
        else:
            score_trend = "stable"

        total = len(target_records)
        keep_rate = keeps / total if total > 0 else 0.0

        return TrendSummary(
            target=target, total_runs=total,
            keep_count=keeps, discard_count=discards,
            avg_score=round(avg_score, 4),
            best_score=round(best_score, 4),
            latest_score=round(latest_score, 4),
            score_trend=score_trend,
            volatility=round(volatility, 4),
            keep_rate=round(keep_rate, 4),
            window_scores=scores,
        )

    def all_targets(self) -> list[str]:
        records = self.load_all()
        return list({r.target for r in records})

    def generate_dashboard_html(self, output_path: str | Path | None = None) -> str:
        if output_path is None:
            output_path = self.reports_dir / "dashboard.html"
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        targets = self.all_targets()
        trends = {t: self.get_trend(t) for t in targets}
        all_records = self.load_all()

        recent = all_records[-50:] if len(all_records) > 50 else all_records
        timeline_labels = json.dumps([r.timestamp[-8:] for r in recent])
        timeline_scores = json.dumps([r.consistency_score for r in recent])
        timeline_actions = json.dumps([r.action for r in recent])

        target_summaries = ""
        for target, trend in sorted(trends.items(), key=lambda x: x[1].latest_score, reverse=True):
            bar_color = "#4ade80" if trend.score_trend == "improving" else "#f87171" if trend.score_trend == "declining" else "#fbbf24"
            target_summaries += f"""
            <div class="card">
                <h3>{target}</h3>
                <div class="stat-row">
                    <span class="stat-label">Score</span>
                    <span class="stat-value">{trend.latest_score:.2f} / {trend.best_score:.2f}</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Trend</span>
                    <span class="stat-value" style="color:{bar_color}">{trend.score_trend}</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Keep/Discard</span>
                    <span class="stat-value">{trend.keep_count}/{trend.discard_count} ({trend.keep_rate:.0%})</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Runs</span>
                    <span class="stat-value">{trend.total_runs}</span>
                </div>
                <div class="stat-row">
                    <span class="stat-label">Volatility</span>
                    <span class="stat-value">{trend.volatility:.3f}</span>
                </div>
            </div>"""

        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>EvolutionVault Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0f172a; color: #e2e8f0; padding: 24px; }}
h1 {{ font-size: 1.5rem; margin-bottom: 8px; color: #f1f5f9; }}
.subtitle {{ color: #94a3b8; margin-bottom: 24px; font-size: 0.875rem; }}
.dashboard {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 16px; margin-bottom: 32px; }}
.card {{ background: #1e293b; border-radius: 12px; padding: 20px; border: 1px solid #334155; }}
.card h3 {{ font-size: 0.9rem; color: #94a3b8; margin-bottom: 12px; text-transform: uppercase; letter-spacing: 0.05em; }}
.stat-row {{ display: flex; justify-content: space-between; padding: 4px 0; font-size: 0.85rem; }}
.stat-label {{ color: #64748b; }}
.stat-value {{ font-weight: 600; color: #e2e8f0; }}
.chart-container {{ background: #1e293b; border-radius: 12px; padding: 20px; border: 1px solid #334155; margin-bottom: 16px; }}
canvas {{ max-height: 300px; }}
.footer {{ text-align: center; color: #64748b; font-size: 0.75rem; padding: 16px; border-top: 1px solid #334155; margin-top: 32px; }}
</style>
</head>
<body>
<h1>EvolutionVault</h1>
<p class="subtitle">RSI 實驗趨勢儀表板 &mdash; 更新于 {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
<div class="dashboard">
{target_summaries}
</div>
<div class="chart-container">
<h3 style="margin-bottom:12px;color:#94a3b8;font-size:0.9rem;text-transform:uppercase;letter-spacing:0.05em;">Score Timeline</h3>
<canvas id="scoreChart"></canvas>
</div>
<div class="chart-container">
<h3 style="margin-bottom:12px;color:#94a3b8;font-size:0.9rem;text-transform:uppercase;letter-spacing:0.05em;">Action Distribution</h3>
<canvas id="actionChart"></canvas>
</div>
<script>
const labels = {timeline_labels};
const scores = {timeline_scores};
const actions = {timeline_actions};
new Chart(document.getElementById('scoreChart'), {{
    type: 'line',
    data: {{
        labels: labels,
        datasets: [{{
            label: 'Score',
            data: scores,
            borderColor: '#4ade80',
            backgroundColor: 'rgba(74, 222, 128, 0.1)',
            fill: true,
            tension: 0.4,
            pointRadius: 3,
        }}]
    }},
    options: {{
        responsive: true,
        plugins: {{ legend: {{ display: false }} }},
        scales: {{
            x: {{ ticks: {{ color: '#64748b' }}, grid: {{ color: '#1e293b' }} }},
            y: {{ min: 0, max: 1, ticks: {{ color: '#64748b' }}, grid: {{ color: '#1e293b' }} }}
        }}
    }}
}});
const keepCount = actions.filter(a => a === 'keep').length;
const discardCount = actions.filter(a => a === 'discard').length;
new Chart(document.getElementById('actionChart'), {{
    type: 'doughnut',
    data: {{
        labels: ['Keep', 'Discard'],
        datasets: [{{
            data: [keepCount, discardCount],
            backgroundColor: ['#4ade80', '#f87171'],
        }}]
    }},
    options: {{
        responsive: true,
        plugins: {{ legend: {{ labels: {{ color: '#e2e8f0' }} }} }}
    }}
}});
</script>
<div class="footer">
MAREF EvolutionVault &mdash; {len(all_records)} 条记录 &mdash; {len(targets)} 个目标
</div>
</body>
</html>"""
        output_path.write_text(html, encoding="utf-8")
        logger.info("Dashboard written to %s", output_path)
        return html

    def summary_report(self) -> dict[str, Any]:
        targets = self.all_targets()
        trends = {t: self.get_trend(t) for t in targets}
        all_records = self.load_all()

        total = len(all_records)
        keeps = sum(1 for r in all_records if r.action == "keep")
        discards = sum(1 for r in all_records if r.action == "discard")

        return {
            "total_records": total,
            "total_targets": len(targets),
            "keeps": keeps,
            "discards": discards,
            "keep_rate": round(keeps / total, 4) if total > 0 else 0,
            "targets": {
                t: {
                    "avg_score": tr.avg_score,
                    "best_score": tr.best_score,
                    "latest_score": tr.latest_score,
                    "trend": tr.score_trend,
                    "keep_rate": tr.keep_rate,
                    "total_runs": tr.total_runs,
                }
                for t, tr in trends.items()
            },
        }
