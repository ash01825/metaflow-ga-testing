#!/usr/bin/env python3
"""
scripts/merge_results.py
Merge per-backend JUnit XML files from test-results/ into a unified matrix.

Usage (local):
    tox -e local && python scripts/merge_results.py

Usage (CI — writes both a Markdown summary and a standalone HTML report):
    python scripts/merge_results.py \
        --summary-file "$GITHUB_STEP_SUMMARY" \
        --html test-results/report.html

Each tox environment writes its results to:
    test-results/local.xml
    test-results/kubernetes.xml
    test-results/argo.xml

The script discovers backends automatically by globbing *.xml in test-results/.
Missing backends show "—" (not run), not "FAIL".
"""

import argparse
import glob
import os
import sys
import xml.etree.ElementTree as ET


def parse_xml(path):
    results = {}
    for tc in ET.parse(path).getroot().iter("testcase"):
        name = tc.get("name")
        duration = float(tc.get("time", 0))
        failure = tc.find("failure")
        skipped = tc.find("skipped")
        if failure is not None:
            results[name] = {
                "status": "FAIL",
                "duration_s": duration,
                "detail": (failure.text or failure.get("message", "")).strip(),
            }
        elif skipped is not None:
            results[name] = {"status": "SKIP", "duration_s": duration, "detail": ""}
        else:
            results[name] = {"status": "PASS", "duration_s": duration, "detail": ""}
    return results


def build_matrix(results_dir):
    xml_files = sorted(glob.glob(os.path.join(results_dir, "*.xml")))
    if not xml_files:
        sys.exit(f"No XML files found in {results_dir}/")

    backends = [os.path.splitext(os.path.basename(f))[0] for f in xml_files]
    per_backend = {b: parse_xml(f) for b, f in zip(backends, xml_files)}
    all_tests = sorted({t for r in per_backend.values() for t in r})
    matrix = {t: {b: per_backend[b].get(t) for b in backends} for t in all_tests}
    return backends, matrix


def print_terminal(backends, matrix):
    col_w = 18
    header = f"{'Test':<45}" + "".join(f"  {b:<{col_w}}" for b in backends)
    print(header)
    print("-" * len(header))
    for test, row in matrix.items():
        line = f"{test:<45}"
        for b in backends:
            r = row[b]
            cell = f"{r['status']} ({r['duration_s']:.1f}s)" if r else "----"
            line += f"  {cell:<{col_w}}"
        print(line)
    print()
    for b in backends:
        passed = sum(1 for r in matrix.values() if r[b] and r[b]["status"] == "PASS")
        failed = sum(1 for r in matrix.values() if r[b] and r[b]["status"] == "FAIL")
        not_run = sum(1 for r in matrix.values() if r[b] is None)
        print(f"  {b}: {passed} passed, {failed} failed, {not_run} not run")


def build_markdown(backends, matrix):
    ICONS = {"PASS": ":white_check_mark:", "FAIL": ":x:", "SKIP": ":large_blue_circle:"}

    lines = ["## Test Results by Backend", ""]
    lines += [
        "| Test | " + " | ".join(backends) + " |",
        "|------|" + "".join("---|" for _ in backends),
    ]
    for test, row in matrix.items():
        cells = []
        for b in backends:
            r = row[b]
            cells.append(
                ":heavy_minus_sign:" if r is None
                else f"{ICONS.get(r['status'], '?')} `{r['duration_s']:.1f}s`"
            )
        lines.append(f"| `{test}` | " + " | ".join(cells) + " |")

    lines += ["", "**Summary**", ""]
    for b in backends:
        passed = sum(1 for r in matrix.values() if r[b] and r[b]["status"] == "PASS")
        failed = sum(1 for r in matrix.values() if r[b] and r[b]["status"] == "FAIL")
        not_run = sum(1 for r in matrix.values() if r[b] is None)
        icon = ":x:" if failed else ":white_check_mark:"
        lines.append(f"- **{b}**: {icon} {passed} passed, {failed} failed, {not_run} not run")

    return "\n".join(lines)


def build_html(backends, matrix):
    COLORS = {"PASS": "#2da44e", "FAIL": "#cf222e", "SKIP": "#6e7781", None: "#6e7781"}
    SYMBOLS = {"PASS": "✓", "FAIL": "✗", "SKIP": "S", None: "—"}

    rows_html = ""
    for test, row in matrix.items():
        cells = ""
        for b in backends:
            r = row[b]
            status = r["status"] if r else None
            color = COLORS[status]
            sym = SYMBOLS[status]
            if r and status == "FAIL" and r["detail"]:
                tip = r["detail"][:300].replace('"', "&quot;")
                cells += (
                    f'<td style="color:{color};font-weight:bold" title="{tip}">'
                    f'{sym} <span style="font-size:0.8em;font-weight:normal">{r["duration_s"]:.1f}s</span></td>'
                )
            elif r:
                cells += (
                    f'<td style="color:{color};font-weight:bold">'
                    f'{sym} <span style="font-size:0.8em;font-weight:normal">{r["duration_s"]:.1f}s</span></td>'
                )
            else:
                cells += f'<td style="color:{color}">—</td>'
        rows_html += f"<tr><td><code>{test}</code></td>{cells}</tr>\n"

    header_cells = "".join(f"<th>{b}</th>" for b in backends)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Metaflow QA Test Report</title>
<style>
  body  {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; margin: 2em; background: #f6f8fa; color: #24292f; }}
  table {{ border-collapse: collapse; width: 100%; background: white; box-shadow: 0 1px 3px rgba(0,0,0,.12); border-radius: 6px; overflow: hidden; }}
  th    {{ background: #f6f8fa; padding: .6em 1em; text-align: left; border-bottom: 1px solid #d0d7de; font-size: .85em; }}
  td    {{ padding: .5em 1em; border-bottom: 1px solid #eaeef2; font-size: .9em; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover {{ background: #f6f8fa; }}
</style>
</head>
<body>
<h1>Metaflow QA: Cross-Backend Test Report</h1>
<table>
  <thead><tr><th>Test</th>{header_cells}</tr></thead>
  <tbody>{rows_html}</tbody>
</table>
<p style="font-size:.8em;color:#6e7781;margin-top:1em">
  ✓ passed &nbsp; ✗ failed (hover for traceback) &nbsp; — not run on this backend
</p>
</body>
</html>"""


def main():
    parser = argparse.ArgumentParser(description="Merge per-backend JUnit XML results into one matrix.")
    parser.add_argument("--results-dir", default="test-results")
    parser.add_argument("--summary-file", default=None, help="Append Markdown to this file (use $GITHUB_STEP_SUMMARY in CI)")
    parser.add_argument("--html", default=None, help="Write a standalone HTML report to this path")
    args = parser.parse_args()

    backends, matrix = build_matrix(args.results_dir)
    print_terminal(backends, matrix)

    if args.summary_file:
        with open(args.summary_file, "a") as f:
            f.write(build_markdown(backends, matrix) + "\n")
        print(f"Markdown summary written to {args.summary_file}")

    if args.html:
        os.makedirs(os.path.dirname(args.html) or ".", exist_ok=True)
        with open(args.html, "w") as f:
            f.write(build_html(backends, matrix))
        print(f"HTML report written to {args.html}")

    # Exit non-zero if any test failed (useful for CI gate)
    any_failed = any(
        r["status"] == "FAIL"
        for row in matrix.values()
        for r in row.values()
        if r is not None
    )
    sys.exit(1 if any_failed else 0)


if __name__ == "__main__":
    main()
