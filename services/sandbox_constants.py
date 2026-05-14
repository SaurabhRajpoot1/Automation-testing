"""Shared sandbox paths and image settings."""

SANDBOX_BASE_IMAGE = "mcr.microsoft.com/playwright:v1.59.1-jammy"

SANDBOX_WORKDIR = "/workspace"
REPO_PATH = f"{SANDBOX_WORKDIR}/repo"

GENERATED_TESTS_PATH = f"{REPO_PATH}/tests/generated"

PLAYWRIGHT_REPORT_PATH = f"{REPO_PATH}/playwright-report"
PLAYWRIGHT_CONFIG_PATH = f"{REPO_PATH}/playwright.config.ts"
PLAYWRIGHT_RESULTS_PATH = f"{REPO_PATH}/test-results"
PLAYWRIGHT_RESULTS_JSON_PATH = "/tmp/playwright-results.json"
PLAYWRIGHT_REPORT_PDF_PATH = "/tmp/playwright-report-summary.pdf"
PLAYWRIGHT_REPORT_HTML_PATH = "/tmp/playwright-report-summary.html"

BOOTSTRAP_STATE_PATH = "/tmp/sandbox-bootstrap.json"
APP_LOG_PATH = "/tmp/sandbox-app.log"
APP_PID_PATH = "/tmp/sandbox-app.pid"

SANDBOX_PORTS = (
    "3000/tcp",
    "4173/tcp",
    "5000/tcp",
    "5173/tcp",
    "8000/tcp",
    "8080/tcp",
)
