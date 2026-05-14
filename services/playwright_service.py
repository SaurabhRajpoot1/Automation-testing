"""Playwright test file and execution support."""

import json
import posixpath
import re
from typing import Any

from services.sandbox_constants import (
    BOOTSTRAP_STATE_PATH,
    GENERATED_TESTS_PATH,
    PLAYWRIGHT_CONFIG_PATH,
    PLAYWRIGHT_REPORT_PDF_PATH,
    PLAYWRIGHT_REPORT_PATH,
    PLAYWRIGHT_RESULTS_JSON_PATH,
    PLAYWRIGHT_RESULTS_PATH,
    REPO_PATH,
)
from services.report_service import generate_playwright_pdf_report, upload_playwright_pdf_report
from utils.docker_utils import (
    ensure_container_running,
    exec_shell,
    exec_shell_or_raise,
    get_container,
    put_text_file,
    read_text_file,
)
from utils.logger import log_event


def generate_test_folder(container_id: str, files: list[dict[str, str]]) -> dict[str, Any]:
    try:
        container = get_container(container_id)
        ensure_container_running(container)
        exec_shell_or_raise(container, f"mkdir -p {GENERATED_TESTS_PATH}")

        saved_files = []
        for file_data in files:
            filename = sanitize_test_filename(file_data["name"])
            path = f"{GENERATED_TESTS_PATH}/{filename}"
            put_text_file(container, path, file_data["content"])
            saved_files.append(path)
            log_event("Generated test file saved", {"container_id": container.id, "path": path})

        return {
            "container_id": container.id,
            "tests_path": GENERATED_TESTS_PATH,
            "files": saved_files,
            "status": "test files generated",
        }
    except Exception as exc:
        log_event("Generate test folder failed", {"container_id": container_id, "error": str(exc)})
        return {"error": str(exc)}


def run_playwright_tests(container_id: str) -> dict[str, Any]:
    try:
        container = get_container(container_id)
        ensure_container_running(container)
        bootstrap_state = read_bootstrap_state(container)

        if not bootstrap_state.get("healthy"):
            return {
                "error": "Sandbox must be bootstrapped with a healthy app before running Playwright tests",
                "bootstrap_state": bootstrap_state,
            }

        base_url = bootstrap_state.get("app", {}).get("container_url") or "http://127.0.0.1:3000/"
        ensure_playwright_config(container, base_url)

        log_event("Running Playwright tests", {"container_id": container.id, "base_url": base_url})
        command = (
            f"cd {REPO_PATH} && "
            f"rm -rf {PLAYWRIGHT_REPORT_PATH} {PLAYWRIGHT_RESULTS_PATH} {PLAYWRIGHT_REPORT_PDF_PATH} {PLAYWRIGHT_RESULTS_JSON_PATH} && "
            f"PLAYWRIGHT_BASE_URL={shell_quote(base_url)} "
            f"PLAYWRIGHT_JSON_OUTPUT_NAME={PLAYWRIGHT_RESULTS_JSON_PATH} "
            "npx playwright test tests/generated --reporter=json,html"
        )
        result = exec_shell(container, command)
        raw_report = read_optional_file(container, PLAYWRIGHT_RESULTS_JSON_PATH)
        summary = parse_playwright_summary(raw_report, result.stdout, result.stderr)
        report_pdf = None
        report_upload = None
        report_upload_error = None

        if exec_shell(container, f"test -d {PLAYWRIGHT_REPORT_PATH}").ok:
            try:
                report_pdf = generate_playwright_pdf_report(
                    container,
                    summary=summary,
                    raw_report=raw_report,
                )
                report_upload = upload_playwright_pdf_report(
                    container,
                    container.id,
                    pdf_report=report_pdf,
                )
            except Exception as exc:
                report_upload_error = str(exc)
                log_event(
                    "Playwright report upload failed",
                    {"container_id": container.id, "error": report_upload_error},
                )

        report_cloudinary = report_upload.get("cloudinary") if report_upload else None
        response = {
            "container_id": container.id,
            "exit_code": result.exit_code,
            "status": "passed" if result.exit_code == 0 else "failed",
            "passed": summary["passed"],
            "failed": summary["failed"],
            "skipped": summary["skipped"],
            "timed_out": summary["timed_out"],
            "report_path": PLAYWRIGHT_REPORT_PATH,
            "report_html_path": report_pdf["html_path"] if report_pdf else None,
            "report_pdf_path": report_pdf["pdf_path"] if report_pdf else None,
            "report_url": report_cloudinary.get("url") if report_cloudinary else None,
            "report_artifacts": report_pdf,
            "report_upload": report_upload,
            "report_upload_error": report_upload_error,
            "stdout": result.stdout,
            "stderr": result.stderr,
        }
        log_event("Playwright test run completed", response)
        return response
    except Exception as exc:
        log_event("Run Playwright tests failed", {"container_id": container_id, "error": str(exc)})
        return {"error": str(exc)}


def ensure_playwright_config(container, base_url: str | None = None) -> None:
    exists = exec_shell(container, f"test -f {PLAYWRIGHT_CONFIG_PATH}")
    if exists.ok:
        log_event(
            "Playwright config already exists",
            {"container_id": container.id, "path": PLAYWRIGHT_CONFIG_PATH},
        )
        return

    config = build_playwright_config(base_url or "http://127.0.0.1:3000/")
    put_text_file(container, PLAYWRIGHT_CONFIG_PATH, config)
    log_event(
        "Playwright config created",
        {"container_id": container.id, "path": PLAYWRIGHT_CONFIG_PATH},
    )


def build_playwright_config(base_url: str) -> str:
    return f"""import {{ defineConfig, devices }} from '@playwright/test';

export default defineConfig({{
  testDir: './tests/generated',
  timeout: 30_000,
  expect: {{
    timeout: 10_000,
  }},
  reporter: [
    ['html', {{ outputFolder: 'playwright-report', open: 'never' }}],
  ],
  outputDir: 'test-results',
  use: {{
    baseURL: process.env.PLAYWRIGHT_BASE_URL || '{base_url}',
    trace: 'retain-on-failure',
    screenshot: 'on',
    video: 'retain-on-failure',
  }},
  projects: [
    {{
      name: 'chromium',
      use: {{ ...devices['Desktop Chrome'] }},
    }},
  ],
}});
"""


def read_bootstrap_state(container) -> dict[str, Any]:
    try:
        return json.loads(read_text_file(container, BOOTSTRAP_STATE_PATH))
    except Exception as exc:
        raise RuntimeError("Sandbox has not been bootstrapped yet") from exc


def sanitize_test_filename(filename: str) -> str:
    normalized = posixpath.normpath(filename.strip())
    if normalized.startswith("../") or normalized == ".." or normalized.startswith("/"):
        raise ValueError(f"Invalid test filename: {filename}")
    if not normalized.endswith((".spec.ts", ".test.ts", ".spec.js", ".test.js")):
        raise ValueError(f"Generated Playwright test must be a .spec/.test JS or TS file: {filename}")
    return normalized


def read_optional_file(container, path: str) -> str | None:
    result = exec_shell(container, f"test -f {path} && cat {path}")
    if result.ok:
        return result.stdout
    return None


def parse_playwright_summary(
    raw_json: str | None,
    stdout: str,
    stderr: str,
) -> dict[str, int]:
    summary = {
        "passed": 0,
        "failed": 0,
        "skipped": 0,
        "timed_out": 0,
    }

    if raw_json:
        try:
            report = json.loads(raw_json)
            for test in walk_playwright_tests(report):
                outcomes = [result.get("status") for result in test.get("results", [])]
                if not outcomes:
                    continue
                final_status = outcomes[-1]
                if final_status == "passed":
                    summary["passed"] += 1
                elif final_status == "skipped":
                    summary["skipped"] += 1
                elif final_status == "timedOut":
                    summary["timed_out"] += 1
                else:
                    summary["failed"] += 1
            return summary
        except json.JSONDecodeError:
            pass

    combined = f"{stdout}\n{stderr}"
    for key, pattern in {
        "passed": r"(\d+)\s+passed",
        "failed": r"(\d+)\s+failed",
        "skipped": r"(\d+)\s+skipped",
        "timed_out": r"(\d+)\s+timed? ?out",
    }.items():
        match = re.search(pattern, combined, re.IGNORECASE)
        if match:
            summary[key] = int(match.group(1))

    return summary


def walk_playwright_tests(node: Any):
    if isinstance(node, dict):
        if "results" in node and "expectedStatus" in node:
            yield node
        for value in node.values():
            yield from walk_playwright_tests(value)
    elif isinstance(node, list):
        for item in node:
            yield from walk_playwright_tests(item)


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"
