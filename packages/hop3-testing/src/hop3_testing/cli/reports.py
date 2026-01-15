# Copyright (c) 2023-2025, Abilian SAS
#
# SPDX-License-Identifier: Apache-2.0

"""Report generation for test results."""

from __future__ import annotations

import html
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    from hop3_testing.runners.base import TestResult
    from hop3_testing.targets.base import DeploymentTarget


def generate_reports(
    target: DeploymentTarget,
    report: str,
    results: list[TestResult],
) -> None:
    """Generate diagnostic reports based on report option.

    Args:
        target: The deployment target (may have diagnostics)
        report: Report format: "none", "text", or "html"
        results: List of test results
    """
    if report == "none":
        return

    # Check if target has diagnostics (new targets do)
    if hasattr(target, "diagnostics") and hasattr(target, "save_diagnostics"):
        if report == "html":
            log_path = target.save_diagnostics(generate_html=False)
            # Generate comprehensive HTML report with test results
            html_path = generate_html_report(target, results, log_path)
            click.echo(f"\nHTML report saved to: {html_path}")
            click.echo(f"Diagnostic logs saved to: {log_path}")
        elif report == "text":
            # Text report - save logs and show console output if there were failures
            has_failures = any(not r.passed for r in results)
            if has_failures:
                log_path = target.save_diagnostics(generate_html=False)
                click.echo(f"\nDiagnostic logs saved to: {log_path}")
                # Show diagnostics in console
                if hasattr(target.diagnostics, "dump_to_console"):
                    click.echo(target.diagnostics.dump_to_console())


def generate_html_report(
    target: DeploymentTarget, results: list[TestResult], log_path: Path
) -> Path:
    """Generate a comprehensive HTML report with test results and diagnostics.

    Args:
        target: The deployment target (has diagnostics)
        results: List of TestResult objects
        log_path: Path to diagnostic logs

    Returns:
        Path to generated HTML report
    """
    # Calculate summary stats
    total = len(results)
    passed = sum(1 for r in results if r.passed)
    failed = total - passed
    total_duration = sum(r.total_duration for r in results)

    def is_short_content(text: str) -> bool:
        """Check if content is short enough to show inline (no foldable section)."""
        return len(text) < 100 and "\n" not in text

    def phase_html(
        phase_id: str, status: str, name: str, content: str, is_success: bool
    ) -> str:
        """Generate HTML for a phase, using inline or foldable based on content length."""
        status_class = "phase-success" if is_success else "phase-failure"
        escaped_content = html.escape(content)

        if is_short_content(content):
            # Short content: show inline, no foldable
            return f"""
            <div class="phase {status_class} phase-inline">
                <span class="phase-icon">{status}</span>
                <span class="phase-name">{html.escape(name)}</span>
                <span class="phase-message">{escaped_content}</span>
            </div>
            """
        # Long content: foldable section
        return f"""
            <div class="phase {status_class}" onclick="togglePhase('{phase_id}')">
                <span class="phase-icon">{status}</span>
                <span class="phase-name">{html.escape(name)}</span>
                <span class="phase-toggle">+</span>
            </div>
            <div id="{phase_id}" class="phase-logs" style="display:none">
                <pre>{escaped_content}</pre>
            </div>
            """

    # Build test results - each test is a clickable card
    test_cards = []
    for idx, r in enumerate(results):
        status_class = "success" if r.passed else "failure"
        status_icon = "\u2713" if r.passed else "\u2717"
        test_id = f"test-{idx}"

        # Build phases list
        phases_html = []

        # Phase 1: Deployment (only if there are logs or it failed)
        if r.deploy_logs:
            deploy_status = (
                "\u2713" if not r.error or "deploy" not in r.error.lower() else "\u2717"
            )
            is_success = deploy_status == "\u2713"
            phases_html.append(
                phase_html(
                    f"{test_id}-deploy",
                    deploy_status,
                    "Deploy",
                    r.deploy_logs,
                    is_success,
                )
            )

        # Phase 2: Validations
        if r.validation_results:
            for v_idx, v in enumerate(r.validation_results):
                v_status = "\u2713" if v.passed else "\u2717"
                v_id = f"{test_id}-val-{v_idx}"

                # Build content from message and details
                v_content = v.message or f"{'Passed' if v.passed else 'Failed'}"
                if v.details:
                    # Add relevant details
                    detail_lines = []
                    for key, val in v.details.items():
                        if key not in {
                            "passed",
                        }:  # Skip redundant fields
                            detail_lines.append(f"{key}: {val}")
                    if detail_lines:
                        v_content += "\n" + "\n".join(detail_lines)

                phases_html.append(
                    phase_html(v_id, v_status, v.type_name, v_content, v.passed)
                )

        # Phase 3: Error (if any, always foldable since errors tend to be long)
        if r.error:
            phases_html.append(f"""
            <div class="phase phase-failure" onclick="togglePhase('{test_id}-error')">
                <span class="phase-icon">\u2717</span>
                <span class="phase-name">Error</span>
                <span class="phase-toggle">+</span>
            </div>
            <div id="{test_id}-error" class="phase-logs" style="display:none">
                <pre class="error-log">{html.escape(r.error)}</pre>
            </div>
            """)

        test_cards.append(f"""
        <div class="test-card {status_class}">
            <div class="test-header" onclick="toggleTest('{test_id}')">
                <span class="test-status">{status_icon}</span>
                <span class="test-name">{html.escape(r.test.name)}</span>
                <span class="test-meta">{html.escape(str(r.test.category) if r.test.category else "unknown")} | {html.escape(str(r.test.tier) if r.test.tier else "unknown")} | {r.total_duration:.2f}s</span>
                <span class="test-toggle">&#9660;</span>
            </div>
            <div id="{test_id}" class="test-details" style="display:none">
                <div class="phases">
                    {"".join(phases_html)}
                </div>
            </div>
        </div>
        """)

    # Build diagnostic entries if available
    diag_cards = []
    if hasattr(target, "diagnostics"):
        diag = target.diagnostics
        if diag.entries:
            for d_idx, e in enumerate(diag.entries):
                d_status = "\u2713" if e.success else "\u2717"
                d_class = "phase-success" if e.success else "phase-failure"
                d_id = f"diag-{d_idx}"

                # Get stdout/stderr if available
                logs = ""
                if hasattr(e, "stdout") and e.stdout:
                    logs += f"=== stdout ===\n{e.stdout}\n"
                if hasattr(e, "stderr") and e.stderr:
                    logs += f"=== stderr ===\n{e.stderr}\n"
                if hasattr(e, "details") and e.details:
                    logs += f"=== details ===\n{e.details}\n"
                if not logs:
                    logs = e.message

                diag_cards.append(f"""
                <div class="phase {d_class}" onclick="togglePhase('{d_id}')">
                    <span class="phase-icon">{d_status}</span>
                    <span class="phase-name">{html.escape(e.phase)} / {html.escape(e.layer)} / {html.escape(e.operation)}</span>
                    <span class="phase-duration">{e.duration:.2f}s</span>
                    <span class="phase-toggle">+</span>
                </div>
                <div id="{d_id}" class="phase-logs" style="display:none">
                    <pre>{html.escape(logs)}</pre>
                </div>
                """)

    diag_section = ""
    if diag_cards:
        diag_section = f"""
        <div class="section">
            <h2 onclick="toggleSection('diag-section')" class="section-header">
                Infrastructure Diagnostics
                <span class="section-toggle">&#9660;</span>
            </h2>
            <div id="diag-section" class="phases">
                {"".join(diag_cards)}
            </div>
        </div>
        """

    # Get context info
    ctx = target.diagnostics.context if hasattr(target, "diagnostics") else None
    test_name = ctx.test_name if ctx else "Unknown"
    config_name = ctx.config if ctx else "Unknown"
    run_id = ctx.run_id if ctx else "Unknown"

    html_content = _build_html_template(
        test_name=test_name,
        config_name=config_name,
        run_id=run_id,
        passed=passed,
        failed=failed,
        total=total,
        total_duration=total_duration,
        test_cards=test_cards,
        diag_section=diag_section,
        log_path=log_path,
    )

    # Save HTML report
    html_path = log_path / "report.html"
    html_path.write_text(html_content)
    return html_path


def _build_html_template(
    *,
    test_name: str,
    config_name: str,
    run_id: str,
    passed: int,
    failed: int,
    total: int,
    total_duration: float,
    test_cards: list[str],
    diag_section: str,
    log_path: Path,
) -> str:
    """Build the complete HTML report template."""
    return f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Hop3 Test Report - {html.escape(test_name)}</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            max-width: 1200px;
            margin: 0 auto;
            padding: 20px;
            background: #f5f5f5;
        }}
        .header {{
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            color: white;
            padding: 25px;
            border-radius: 12px;
            margin-bottom: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .header h1 {{ margin: 0 0 10px 0; }}
        .meta {{ opacity: 0.8; font-size: 14px; }}
        .stats {{
            display: flex;
            gap: 15px;
            margin-top: 20px;
            flex-wrap: wrap;
        }}
        .stat {{
            background: rgba(255,255,255,0.1);
            padding: 12px 20px;
            border-radius: 8px;
            font-weight: 500;
        }}
        .stat.passed {{ border-left: 4px solid #4caf50; }}
        .stat.failed {{ border-left: 4px solid #f44336; }}
        .section {{
            background: white;
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 20px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.08);
        }}
        .section h2 {{
            margin: 0 0 15px 0;
            padding-bottom: 10px;
            border-bottom: 2px solid #eee;
        }}
        .section-header {{
            cursor: pointer;
            user-select: none;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }}
        .section-toggle {{ font-size: 12px; }}

        /* Test cards */
        .test-card {{
            border: 1px solid #e0e0e0;
            border-radius: 8px;
            margin-bottom: 10px;
            overflow: hidden;
        }}
        .test-card.success {{ border-left: 4px solid #4caf50; }}
        .test-card.failure {{ border-left: 4px solid #f44336; background: #fff8f8; }}
        .test-header {{
            padding: 15px;
            cursor: pointer;
            display: flex;
            align-items: center;
            gap: 12px;
            background: #fafafa;
            transition: background 0.2s;
        }}
        .test-header:hover {{ background: #f0f0f0; }}
        .test-status {{
            font-size: 20px;
            font-weight: bold;
        }}
        .test-card.success .test-status {{ color: #4caf50; }}
        .test-card.failure .test-status {{ color: #f44336; }}
        .test-name {{
            font-weight: 600;
            flex: 1;
        }}
        .test-meta {{
            color: #666;
            font-size: 13px;
        }}
        .test-toggle {{
            color: #999;
            font-size: 12px;
        }}
        .test-details {{
            padding: 0 15px 15px 15px;
            border-top: 1px solid #eee;
        }}

        /* Phases */
        .phases {{
            margin-top: 10px;
        }}
        .phase {{
            display: flex;
            align-items: center;
            gap: 10px;
            padding: 10px 12px;
            margin: 4px 0;
            border-radius: 6px;
            cursor: pointer;
            transition: background 0.2s;
        }}
        .phase:hover {{ filter: brightness(0.95); }}
        .phase-success {{ background: #e8f5e9; }}
        .phase-failure {{ background: #ffebee; }}
        .phase-icon {{ font-weight: bold; }}
        .phase-success .phase-icon {{ color: #4caf50; }}
        .phase-failure .phase-icon {{ color: #f44336; }}
        .phase-name {{ flex: 1; font-weight: 500; }}
        .phase-duration {{ color: #666; font-size: 12px; }}
        .phase-toggle {{ color: #999; font-size: 14px; min-width: 12px; }}
        /* Inline phases (short content, no foldable section) */
        .phase-inline {{
            cursor: default;
        }}
        .phase-inline:hover {{ filter: none; }}
        .phase-inline .phase-name {{ flex: 0 0 auto; min-width: 100px; }}
        .phase-message {{
            color: #555;
            font-size: 13px;
            flex: 1;
        }}
        .phase-logs {{
            margin: 4px 0 4px 20px;
            border-left: 3px solid #ddd;
        }}
        .phase-logs pre {{
            margin: 0;
            padding: 12px;
            font-size: 12px;
            background: #1a1a2e;
            color: #e0e0e0;
            border-radius: 0 6px 6px 0;
            max-height: 400px;
            overflow: auto;
            white-space: pre-wrap;
            word-break: break-word;
        }}
        .error-log {{
            background: #2d1f1f !important;
            color: #ffcdd2 !important;
        }}

        footer {{
            text-align: center;
            color: #666;
            margin-top: 40px;
            padding: 20px;
            font-size: 13px;
        }}
    </style>
</head>
<body>
    <div class="header">
        <h1>Hop3 Test Report</h1>
        <div class="meta">
            Test: <strong>{html.escape(test_name)}</strong> |
            Config: {html.escape(config_name)} |
            Run: {html.escape(run_id)}
        </div>
        <div class="stats">
            <div class="stat passed">Passed: {passed}</div>
            <div class="stat failed">Failed: {failed}</div>
            <div class="stat">Total: {total}</div>
            <div class="stat">Duration: {total_duration:.1f}s</div>
        </div>
    </div>

    <div class="section">
        <h2>Test Results</h2>
        <p style="color:#666;font-size:13px;margin-bottom:15px;">
            Click on a test to expand details. Click on each phase to see logs.
        </p>
        {"".join(test_cards)}
    </div>

    {diag_section}

    <footer>
        Generated by hop3-testing at {datetime.now().isoformat()}<br>
        Logs directory: {html.escape(str(log_path))}
    </footer>

    <script>
        function toggleTest(id) {{
            const el = document.getElementById(id);
            const toggle = el.previousElementSibling.querySelector('.test-toggle');
            if (el.style.display === 'none') {{
                el.style.display = 'block';
                toggle.innerHTML = '&#9650;';
            }} else {{
                el.style.display = 'none';
                toggle.innerHTML = '&#9660;';
            }}
        }}

        function togglePhase(id) {{
            const el = document.getElementById(id);
            const toggle = el.previousElementSibling.querySelector('.phase-toggle');
            if (el.style.display === 'none') {{
                el.style.display = 'block';
                toggle.textContent = '-';
            }} else {{
                el.style.display = 'none';
                toggle.textContent = '+';
            }}
            event.stopPropagation();
        }}

        function toggleSection(id) {{
            const el = document.getElementById(id);
            if (el.style.display === 'none') {{
                el.style.display = 'block';
            }} else {{
                el.style.display = 'none';
            }}
        }}

        // Auto-expand failed tests
        document.querySelectorAll('.test-card.failure').forEach(card => {{
            const details = card.querySelector('.test-details');
            const toggle = card.querySelector('.test-toggle');
            if (details) {{
                details.style.display = 'block';
                toggle.innerHTML = '&#9650;';
            }}
        }});
    </script>
</body>
</html>
"""
