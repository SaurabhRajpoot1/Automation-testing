"""Playwright PDF report generation and upload logic."""

import base64
import html
import json
from pathlib import PurePosixPath
from typing import Any

from services.cloudinary_service import upload_to_cloudinary
from services.sandbox_constants import (
    PLAYWRIGHT_REPORT_HTML_PATH,
    PLAYWRIGHT_REPORT_PDF_PATH,
    PLAYWRIGHT_REPORT_PATH,
    PLAYWRIGHT_RESULTS_PATH,
)
from utils.docker_utils import exec_shell, exec_shell_or_raise, put_text_file, read_binary_file
from utils.logger import log_event


def generate_playwright_pdf_report(
    container,
    *,
    summary: dict[str, int],
    raw_report: str | None,
) -> dict[str, Any]:
    screenshot_paths = list_artifacts(container, PLAYWRIGHT_RESULTS_PATH, "png")
    screenshots = collect_screenshots(container, screenshot_paths)
    video_count = count_artifacts(container, PLAYWRIGHT_RESULTS_PATH, "webm")
    trace_count = count_artifacts(container, PLAYWRIGHT_RESULTS_PATH, "zip")
    failed_tests = extract_failed_tests(raw_report)

    html_content = build_playwright_pdf_html(
        summary=summary,
        failed_tests=failed_tests,
        screenshots=screenshots,
        video_count=video_count,
        trace_count=trace_count,
    )
    put_text_file(container, PLAYWRIGHT_REPORT_HTML_PATH, html_content)
    exec_shell_or_raise(
        container,
        f"""cd {PLAYWRIGHT_REPORT_PATH.rsplit("/", 1)[0]} && node - <<'JS'
const {{ pathToFileURL }} = require('url');

let chromium;
try {{
  ({{ chromium }} = require('playwright'));
}} catch (error) {{
  ({{ chromium }} = require('@playwright/test'));
}}

const htmlPath = {PLAYWRIGHT_REPORT_HTML_PATH!r};
const pdfPath = {PLAYWRIGHT_REPORT_PDF_PATH!r};

(async () => {{
  const browser = await chromium.launch();
  const page = await browser.newPage({{ viewport: {{ width: 1440, height: 1024 }} }});
  await page.goto(pathToFileURL(htmlPath).href, {{ waitUntil: 'load' }});
  await page.pdf({{
    path: pdfPath,
    format: 'A4',
    printBackground: true,
    margin: {{ top: '20px', right: '20px', bottom: '20px', left: '20px' }},
  }});
  await browser.close();
}})().catch((error) => {{
  console.error(error);
  process.exit(1);
}});
JS""",
    )

    return {
        "pdf_path": PLAYWRIGHT_REPORT_PDF_PATH,
        "html_path": PLAYWRIGHT_REPORT_HTML_PATH,
        "report_path": PLAYWRIGHT_REPORT_PATH,
        "screenshots": len(screenshots),
        "videos": video_count,
        "traces": trace_count,
        "failed_tests": len(failed_tests),
    }


def upload_playwright_pdf_report(
    container,
    container_id: str,
    *,
    pdf_report: dict[str, Any],
) -> dict[str, Any]:
    pdf_bytes = read_binary_file(container, pdf_report["pdf_path"])
    filename = f"playwright-report-{container_id[:12]}.pdf"

    upload_result = upload_to_cloudinary(
        pdf_bytes,
        filename,
        folder="playwright-reports",
        resource_type="raw",
    )
    log_event(
        "Playwright PDF report uploaded to Cloudinary",
        {
            "container_id": container.id,
            "cloudinary": upload_result,
            "screenshots": pdf_report["screenshots"],
            "videos": pdf_report["videos"],
            "traces": pdf_report["traces"],
        },
    )

    return {
        **pdf_report,
        "filename": filename,
        "cloudinary": upload_result,
    }


def collect_screenshots(container, paths: list[str]) -> list[dict[str, str]]:
    screenshots = []
    for path in paths:
        image_bytes = read_binary_file(container, path)
        data_url = "data:image/png;base64," + base64.b64encode(image_bytes).decode("ascii")
        screenshots.append(
            {
                "name": PurePosixPath(path).name,
                "path": path,
                "data_url": data_url,
            }
        )

    return screenshots


def count_artifacts(container, base_path: str, extension: str) -> int:
    result = exec_shell(
        container,
        f"if [ -d {base_path} ]; then find {base_path} -type f -name '*.{extension}' | wc -l; else echo 0; fi",
    )
    if not result.ok:
        return 0

    try:
        return int(result.stdout.strip() or "0")
    except ValueError:
        return 0


def list_artifacts(container, base_path: str, extension: str) -> list[str]:
    result = exec_shell(
        container,
        f"if [ -d {base_path} ]; then find {base_path} -type f -name '*.{extension}' | sort; fi",
    )
    if not result.ok:
        return []

    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def extract_failed_tests(raw_report: str | None) -> list[dict[str, str]]:
    if not raw_report:
        return []

    try:
        report = json.loads(raw_report)
    except json.JSONDecodeError:
        return []

    failed = []
    for test in walk_playwright_tests(report):
        results = test.get("results") or []
        if not results:
            continue

        last_result = results[-1]
        status = last_result.get("status")
        if status not in {"failed", "timedOut", "interrupted"}:
            continue

        title = " > ".join(test.get("titlePath") or [test.get("title", "Unnamed test")])
        error_text = ""
        errors = last_result.get("errors") or []
        if errors:
            first_error = errors[0]
            error_text = first_error.get("message") or first_error.get("value") or ""

        failed.append(
            {
                "title": title,
                "status": status,
                "error": error_text.strip(),
            }
        )

    return failed


def walk_playwright_tests(node: Any):
    if isinstance(node, dict):
        if "results" in node and "expectedStatus" in node:
            yield node
        for value in node.values():
            yield from walk_playwright_tests(value)
    elif isinstance(node, list):
        for item in node:
            yield from walk_playwright_tests(item)


def build_playwright_pdf_html(
    *,
    summary: dict[str, int],
    failed_tests: list[dict[str, str]],
    screenshots: list[dict[str, str]],
    video_count: int,
    trace_count: int,
) -> str:
    screenshot_blocks = "\n".join(
        build_screenshot_block(screenshot)
        for screenshot in screenshots
    ) or "<p class='muted'>No screenshots captured.</p>"

    failed_blocks = "\n".join(
        f"""
        <section class="failure">
          <h3>{html.escape(test['title'])}</h3>
          <p class="status">Status: {html.escape(test['status'])}</p>
          <pre>{html.escape(test['error'] or 'No error message available')}</pre>
        </section>
        """
        for test in failed_tests
    ) or "<p class='muted'>No failed test details available.</p>"

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Playwright Test Report</title>
  <style>
    @page {{
      size: A4;
      margin: 20px;
    }}
    body {{
      font-family: Arial, sans-serif;
      color: #1f2937;
      margin: 0;
      padding: 24px;
      background: #f8fafc;
    }}
    h1, h2, h3 {{
      margin: 0 0 12px;
    }}
    .meta, .failure, .shot {{
      background: white;
      border: 1px solid #dbe2ea;
      border-radius: 10px;
      padding: 16px;
      margin-bottom: 16px;
      box-shadow: 0 4px 12px rgba(15, 23, 42, 0.05);
      break-inside: avoid;
      page-break-inside: avoid;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 12px;
      margin: 16px 0 24px;
    }}
    .stat {{
      background: white;
      border: 1px solid #dbe2ea;
      border-radius: 10px;
      padding: 12px;
      text-align: center;
      break-inside: avoid;
      page-break-inside: avoid;
    }}
    .label {{
      color: #64748b;
      font-size: 12px;
      text-transform: uppercase;
    }}
    .value {{
      font-size: 22px;
      font-weight: 700;
      margin-top: 6px;
    }}
    .muted {{
      color: #64748b;
    }}
    .status {{
      color: #991b1b;
      font-weight: 600;
    }}
    pre {{
      white-space: pre-wrap;
      word-break: break-word;
      background: #f8fafc;
      border-radius: 8px;
      padding: 12px;
      font-size: 12px;
      border: 1px solid #e2e8f0;
    }}
    img {{
      width: 100%;
      max-height: 680px;
      object-fit: contain;
      border: 1px solid #cbd5e1;
      border-radius: 8px;
      margin-top: 12px;
      background: #ffffff;
    }}
    .caption {{
      font-size: 12px;
      color: #475569;
      margin-top: 8px;
    }}
  </style>
</head>
<body>
  <h1>Playwright Test Report</h1>
  <div class="meta">
    <p><strong>Failures:</strong> {summary['failed']}</p>
    <p><strong>Timed out:</strong> {summary['timed_out']}</p>
    <p><strong>Videos:</strong> {video_count}</p>
    <p><strong>Traces:</strong> {trace_count}</p>
  </div>
  <div class="stats">
    <div class="stat"><div class="label">Passed</div><div class="value">{summary['passed']}</div></div>
    <div class="stat"><div class="label">Failed</div><div class="value">{summary['failed']}</div></div>
    <div class="stat"><div class="label">Timed Out</div><div class="value">{summary['timed_out']}</div></div>
    <div class="stat"><div class="label">Screenshots</div><div class="value">{len(screenshots)}</div></div>
  </div>
  <h2>Failed Tests</h2>
  {failed_blocks}
  <h2>Screenshots</h2>
  {screenshot_blocks}
</body>
</html>
"""


def build_screenshot_block(screenshot: dict[str, str]) -> str:
    return f"""
    <section class="shot">
      <h3>{html.escape(screenshot['name'])}</h3>
      <img src="{screenshot['data_url']}" alt="{html.escape(screenshot['path'])}" />
      <p class="caption">{html.escape(screenshot['path'])}</p>
    </section>
    """
