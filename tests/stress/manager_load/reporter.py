"""
Report generation module for SandboxManager stress tests.

Generates HTML reports with charts and summary statistics.
"""

import json
from datetime import datetime
from pathlib import Path

from .metrics_collector import MetricsCollector, PoolSnapshot, TestSummary


class HTMLReporter:
    """Generates HTML reports from stress test metrics."""

    def __init__(self, collector: MetricsCollector):
        self.collector = collector

    def generate_report(self, output_path: Path | None = None) -> Path:
        """Generate HTML report and save to file."""
        summary = self.collector.generate_summary()
        snapshots = self.collector.snapshots
        task_results = self.collector.task_results

        html = self._generate_html(summary, snapshots, task_results)

        if output_path is None:
            timestamp = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
            output_path = self.collector.output_dir / f"report_{timestamp}.html"

        output_path.write_text(html)
        return output_path

    def _generate_html(self, summary: TestSummary, snapshots: list[PoolSnapshot], task_results: list) -> str:
        """Generate the HTML content."""
        # Prepare chart data
        timestamps = [s.elapsed_seconds for s in snapshots]
        total_sandboxes = [s.total_sandboxes for s in snapshots]
        ready_count = [s.total_ready for s in snapshots]
        in_use_count = [s.total_in_use for s in snapshots]
        creating_count = [s.total_creating for s in snapshots]
        pool_hit_rate = [s.pool_hit_rate for s in snapshots]
        avg_latency = [s.avg_acquire_latency_ms for s in snapshots]

        # Generate HTML
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Stress Test Report - {summary.scenario_name}</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        :root {{
            --bg-primary: #1a1a2e;
            --bg-secondary: #16213e;
            --bg-card: #0f3460;
            --text-primary: #eee;
            --text-secondary: #aaa;
            --accent-success: #00d26a;
            --accent-warning: #ffc107;
            --accent-danger: #ff6b6b;
            --accent-info: #00b4d8;
            --accent-purple: #9b59b6;
        }}

        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            line-height: 1.6;
            padding: 20px;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
        }}

        header {{
            text-align: center;
            margin-bottom: 30px;
            padding: 20px;
            background: var(--bg-secondary);
            border-radius: 10px;
        }}

        h1 {{
            font-size: 2em;
            margin-bottom: 10px;
        }}

        .subtitle {{
            color: var(--text-secondary);
            font-size: 1.1em;
        }}

        .grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}

        .card {{
            background: var(--bg-card);
            border-radius: 10px;
            padding: 20px;
        }}

        .card h3 {{
            font-size: 0.9em;
            color: var(--text-secondary);
            text-transform: uppercase;
            margin-bottom: 10px;
        }}

        .metric {{
            font-size: 2.5em;
            font-weight: bold;
        }}

        .metric.success {{ color: var(--accent-success); }}
        .metric.warning {{ color: var(--accent-warning); }}
        .metric.danger {{ color: var(--accent-danger); }}
        .metric.info {{ color: var(--accent-info); }}
        .metric.purple {{ color: var(--accent-purple); }}

        .metric-sub {{
            font-size: 0.9em;
            color: var(--text-secondary);
        }}

        .chart-container {{
            background: var(--bg-card);
            border-radius: 10px;
            padding: 20px;
            margin-bottom: 30px;
        }}

        .chart-container h2 {{
            margin-bottom: 20px;
            font-size: 1.2em;
        }}

        .chart-wrapper {{
            position: relative;
            height: 300px;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
        }}

        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid var(--bg-secondary);
        }}

        th {{
            color: var(--text-secondary);
            font-weight: 500;
            text-transform: uppercase;
            font-size: 0.85em;
        }}

        .status-badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 20px;
            font-size: 0.85em;
            font-weight: 500;
        }}

        .status-success {{ background: rgba(0, 210, 106, 0.2); color: var(--accent-success); }}
        .status-failed {{ background: rgba(255, 107, 107, 0.2); color: var(--accent-danger); }}

        .two-col {{
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 20px;
        }}

        @media (max-width: 768px) {{
            .two-col {{
                grid-template-columns: 1fr;
            }}
        }}

        footer {{
            text-align: center;
            padding: 20px;
            color: var(--text-secondary);
            font-size: 0.9em;
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>SandboxManager Stress Test Report</h1>
            <p class="subtitle">{summary.scenario_name} | {summary.started_at} - {summary.ended_at}</p>
        </header>

        <!-- Summary Cards -->
        <div class="grid">
            <div class="card">
                <h3>Total Tasks</h3>
                <div class="metric info">{summary.total_tasks}</div>
                <div class="metric-sub">{summary.successful_tasks} successful, {summary.failed_tasks} failed</div>
            </div>
            <div class="card">
                <h3>Success Rate</h3>
                <div class="metric {"success" if summary.success_rate >= 95 else "warning" if summary.success_rate >= 80 else "danger"}">{summary.success_rate:.1f}%</div>
                <div class="metric-sub">Target: >95%</div>
            </div>
            <div class="card">
                <h3>Pool Hit Rate</h3>
                <div class="metric {"success" if summary.pool_hit_rate >= 80 else "warning" if summary.pool_hit_rate >= 50 else "danger"}">{summary.pool_hit_rate:.1f}%</div>
                <div class="metric-sub">{summary.pool_hits} hits / {summary.cold_starts} cold starts</div>
            </div>
            <div class="card">
                <h3>Test Duration</h3>
                <div class="metric purple">{summary.duration_seconds / 60:.1f}m</div>
                <div class="metric-sub">{summary.duration_seconds:.0f} seconds</div>
            </div>
        </div>

        <div class="grid">
            <div class="card">
                <h3>Avg Acquire Latency</h3>
                <div class="metric {"success" if summary.avg_acquire_latency_ms < 1000 else "warning"}">{summary.avg_acquire_latency_ms:.0f}ms</div>
                <div class="metric-sub">Pool: {summary.avg_pool_hit_latency_ms:.0f}ms / Cold: {summary.avg_cold_start_latency_ms:.0f}ms</div>
            </div>
            <div class="card">
                <h3>P95 Latency</h3>
                <div class="metric info">{summary.p95_acquire_latency_ms:.0f}ms</div>
                <div class="metric-sub">P50: {summary.p50_acquire_latency_ms:.0f}ms / P99: {summary.p99_acquire_latency_ms:.0f}ms</div>
            </div>
            <div class="card">
                <h3>Max Concurrent</h3>
                <div class="metric purple">{summary.max_concurrent_sandboxes}</div>
                <div class="metric-sub">Python: {summary.max_concurrent_python} / Node: {summary.max_concurrent_node}</div>
            </div>
            <div class="card">
                <h3>Scale Events</h3>
                <div class="metric info">{summary.scale_up_events + summary.scale_down_events}</div>
                <div class="metric-sub">{summary.scale_up_events} up / {summary.scale_down_events} down</div>
            </div>
        </div>

        <!-- Charts -->
        <div class="chart-container">
            <h2>Sandbox Pool Over Time</h2>
            <div class="chart-wrapper">
                <canvas id="poolChart"></canvas>
            </div>
        </div>

        <div class="two-col">
            <div class="chart-container">
                <h2>Pool Hit Rate Over Time</h2>
                <div class="chart-wrapper">
                    <canvas id="hitRateChart"></canvas>
                </div>
            </div>
            <div class="chart-container">
                <h2>Acquire Latency Over Time</h2>
                <div class="chart-wrapper">
                    <canvas id="latencyChart"></canvas>
                </div>
            </div>
        </div>

        <!-- Breakdown Tables -->
        <div class="two-col">
            <div class="chart-container">
                <h2>Tasks by Category</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Category</th>
                            <th>Total</th>
                            <th>Success</th>
                            <th>Rate</th>
                        </tr>
                    </thead>
                    <tbody>
                        {self._generate_category_rows(summary.tasks_by_category)}
                    </tbody>
                </table>
            </div>
            <div class="chart-container">
                <h2>Tasks by User Group</h2>
                <table>
                    <thead>
                        <tr>
                            <th>Group</th>
                            <th>Total</th>
                            <th>Success</th>
                            <th>Rate</th>
                        </tr>
                    </thead>
                    <tbody>
                        {self._generate_category_rows(summary.tasks_by_user_group)}
                    </tbody>
                </table>
            </div>
        </div>

        <footer>
            Generated by SandboxManager Stress Test Suite | {datetime.utcnow().isoformat()}Z
        </footer>
    </div>

    <script>
        // Chart.js configuration
        Chart.defaults.color = '#aaa';
        Chart.defaults.borderColor = 'rgba(255,255,255,0.1)';

        // Pool chart
        new Chart(document.getElementById('poolChart'), {{
            type: 'line',
            data: {{
                labels: {json.dumps(timestamps)},
                datasets: [
                    {{
                        label: 'Total',
                        data: {json.dumps(total_sandboxes)},
                        borderColor: '#00b4d8',
                        backgroundColor: 'rgba(0, 180, 216, 0.1)',
                        fill: true,
                        tension: 0.3,
                    }},
                    {{
                        label: 'Ready',
                        data: {json.dumps(ready_count)},
                        borderColor: '#00d26a',
                        backgroundColor: 'rgba(0, 210, 106, 0.1)',
                        fill: true,
                        tension: 0.3,
                    }},
                    {{
                        label: 'In Use',
                        data: {json.dumps(in_use_count)},
                        borderColor: '#9b59b6',
                        backgroundColor: 'rgba(155, 89, 182, 0.1)',
                        fill: true,
                        tension: 0.3,
                    }},
                    {{
                        label: 'Creating',
                        data: {json.dumps(creating_count)},
                        borderColor: '#ffc107',
                        backgroundColor: 'rgba(255, 193, 7, 0.1)',
                        fill: true,
                        tension: 0.3,
                    }},
                ],
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    x: {{
                        title: {{ display: true, text: 'Time (seconds)' }},
                    }},
                    y: {{
                        title: {{ display: true, text: 'Sandboxes' }},
                        beginAtZero: true,
                    }},
                }},
                plugins: {{
                    legend: {{ position: 'top' }},
                }},
            }},
        }});

        // Hit rate chart
        new Chart(document.getElementById('hitRateChart'), {{
            type: 'line',
            data: {{
                labels: {json.dumps(timestamps)},
                datasets: [{{
                    label: 'Pool Hit Rate (%)',
                    data: {json.dumps(pool_hit_rate)},
                    borderColor: '#00d26a',
                    backgroundColor: 'rgba(0, 210, 106, 0.2)',
                    fill: true,
                    tension: 0.3,
                }}],
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    x: {{ title: {{ display: true, text: 'Time (seconds)' }} }},
                    y: {{
                        title: {{ display: true, text: 'Hit Rate (%)' }},
                        beginAtZero: true,
                        max: 100,
                    }},
                }},
            }},
        }});

        // Latency chart
        new Chart(document.getElementById('latencyChart'), {{
            type: 'line',
            data: {{
                labels: {json.dumps(timestamps)},
                datasets: [{{
                    label: 'Avg Acquire Latency (ms)',
                    data: {json.dumps(avg_latency)},
                    borderColor: '#ff6b6b',
                    backgroundColor: 'rgba(255, 107, 107, 0.2)',
                    fill: true,
                    tension: 0.3,
                }}],
            }},
            options: {{
                responsive: true,
                maintainAspectRatio: false,
                scales: {{
                    x: {{ title: {{ display: true, text: 'Time (seconds)' }} }},
                    y: {{
                        title: {{ display: true, text: 'Latency (ms)' }},
                        beginAtZero: true,
                    }},
                }},
            }},
        }});
    </script>
</body>
</html>"""

        return html

    def _generate_category_rows(self, data: dict) -> str:
        """Generate table rows for category/group breakdown."""
        rows = []
        for name, stats in sorted(data.items()):
            total = stats.get("total", 0)
            success = stats.get("success", 0)
            rate = success / total * 100 if total > 0 else 0
            status_class = "success" if rate >= 95 else "failed"
            rows.append(f"""
                <tr>
                    <td>{name}</td>
                    <td>{total}</td>
                    <td>{success}</td>
                    <td><span class="status-badge status-{status_class}">{rate:.1f}%</span></td>
                </tr>
            """)
        return "".join(rows) if rows else '<tr><td colspan="4">No data</td></tr>'


def generate_report(collector: MetricsCollector, output_path: Path | None = None) -> Path:
    """Convenience function to generate a report."""
    reporter = HTMLReporter(collector)
    return reporter.generate_report(output_path)
