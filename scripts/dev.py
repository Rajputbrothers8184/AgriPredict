#!/usr/bin/env python3
"""Start the whole AgriPredict stack locally with one command.

    python3 scripts/dev.py

What it does, in order:

1. Finds a Python interpreter that can import the backend's dependencies.
2. Creates the SQLite schema and seeds reference data (idempotent).
3. Seeds demo price history if the database has no prices (idempotent).
4. Starts the ML service on 8001 and the API on 8000.
5. Health-gates both — the API's own /health polls the ML service, so this
   catches "started but not actually working" instead of printing a URL to
   something that will fail on the first request.
6. Streams both logs with a prefix and shuts both down on Ctrl-C.

Everything it runs is a command documented in docs/installation/README.md; this
is a convenience wrapper, not a second source of truth.

Why Python and not a shell script: the health gate needs a timeout loop, and
signalling two child processes correctly is easier to get right (and to test)
in Python than in bash on both macOS and Linux.

Standard library only — it must run before anything is installed.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
BACKEND_DIR = REPO_ROOT / "backend"
ML_DIR = REPO_ROOT / "ml"

DEFAULT_API_PORT = 8000
DEFAULT_ML_PORT = 8001

DEV_SECRET = "dev-only-secret-key-not-for-production-0000"

DEMO_EMAIL = "demo@agripredict.pk"
DEMO_PASSWORD = "Sunflower2026"

C_RESET = "\033[0m"
C_DIM = "\033[2m"
C_BOLD = "\033[1m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_RED = "\033[31m"
C_CYAN = "\033[36m"


def supports_colour() -> bool:
    return sys.stdout.isatty() and os.environ.get("NO_COLOR") is None


def paint(text: str, colour: str) -> str:
    return f"{colour}{text}{C_RESET}" if supports_colour() else text


def say(message: str = "") -> None:
    print(message, flush=True)


def step(message: str) -> None:
    say(f"{paint('==>', C_CYAN)} {message}")


def warn(message: str) -> None:
    say(f"{paint('  !', C_YELLOW)} {message}")


def fail(message: str) -> None:
    say(f"{paint('  x', C_RED)} {message}")


# ---------------------------------------------------------------------------
# Interpreter discovery
# ---------------------------------------------------------------------------
def candidates(explicit: str | None, service: str) -> list[Path]:
    """Interpreters to try, most specific first."""
    found: list[Path] = []
    if explicit:
        found.append(Path(explicit).expanduser())
    env_override = os.environ.get("AGRI_PYTHON")
    if env_override:
        found.append(Path(env_override).expanduser())
    # A per-service venv is what docs/installation recommends.
    found.append(REPO_ROOT / service / ".venv" / "bin" / "python")
    found.append(REPO_ROOT / service / ".venv" / "Scripts" / "python.exe")
    # A shared venv at the repo root is handy and is what this repo's own
    # development used.
    found.append(REPO_ROOT / ".venv" / "bin" / "python")
    found.append(REPO_ROOT / ".venv" / "Scripts" / "python.exe")
    # Some sandboxes and CI images provide a single venv next to the checkout.
    found.append(REPO_ROOT.parent / ".venv" / "bin" / "python")
    found.append(REPO_ROOT.parent / ".venv" / "Scripts" / "python.exe")
    found.append(Path(sys.executable))
    found.append(Path("python3"))
    return found


def find_interpreter(explicit: str | None) -> tuple[Path | None, list[str]]:
    """Return the first interpreter that can import every runtime dependency."""
    missing: list[str] = []
    seen: set[str] = set()
    for path in candidates(explicit, "backend"):
        key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if not (path.exists() or path.name in {"python3", "python"}):
            continue
        try:
            check = subprocess.run(
                [
                    str(path),
                    "-c",
                    "import fastapi, uvicorn, sqlalchemy, pydantic, jwt, httpx, reportlab, openpyxl",
                ],
                capture_output=True,
                timeout=60,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue
        if check.returncode == 0:
            return path, []
        if not missing:
            missing = check.stderr.decode(errors="replace").strip().splitlines()[-1:]
    return None, missing


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def http_json(url: str, timeout: float = 2.0):
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read())


def port_in_use(port: int) -> bool:
    import socket

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def wait_for_health(url: str, *, label: str, timeout: float, process: subprocess.Popen) -> bool:
    """Poll until the endpoint answers 200, the process dies, or time runs out."""
    deadline = time.time() + timeout
    last_error = "no response"
    while time.time() < deadline:
        if process.poll() is not None:
            fail(f"{label} exited during startup (code {process.returncode})")
            return False
        try:
            payload = http_json(url, timeout=2.0)
            if payload.get("status") in {"ok", "degraded"}:
                return True
            last_error = f"status={payload.get('status')!r}"
        except urllib.error.URLError as exc:
            last_error = str(getattr(exc, "reason", exc))
        except (json.JSONDecodeError, TimeoutError, OSError) as exc:
            last_error = str(exc)
        time.sleep(0.4)
    fail(f"{label} did not become healthy within {timeout:.0f}s ({last_error})")
    return False


def stream(process: subprocess.Popen, label: str, colour: str) -> threading.Thread:
    """Copy a child's output to ours, line by line, with a prefix."""

    def pump() -> None:
        assert process.stdout is not None
        prefix = paint(f"[{label}]", colour)
        for raw in iter(process.stdout.readline, b""):
            line = raw.decode(errors="replace").rstrip("\n")
            print(f"{prefix} {line}", flush=True)

    thread = threading.Thread(target=pump, daemon=True)
    thread.start()
    return thread


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    parser = argparse.ArgumentParser(
        description="Start the ML service and the API, with data seeded.",
        epilog="Ctrl-C stops both services.",
    )
    parser.add_argument("--api-port", type=int, default=DEFAULT_API_PORT)
    parser.add_argument("--ml-port", type=int, default=DEFAULT_ML_PORT)
    parser.add_argument("--python", default=None, help="interpreter to use for both services")
    parser.add_argument(
        "--no-ml",
        action="store_true",
        help="start only the API; forecasts fall back to the baseline",
    )
    parser.add_argument(
        "--no-seed",
        action="store_true",
        help="skip schema creation and demo data (manage the database yourself)",
    )
    parser.add_argument(
        "--reload",
        action="store_true",
        help="auto-reload on code changes (slower startup)",
    )
    parser.add_argument(
        "--frame-options",
        default=os.environ.get("FRAME_OPTIONS", "DENY"),
        help="X-Frame-Options policy; SAMEORIGIN is needed to embed the API in a browser preview",
    )
    parser.add_argument("--timeout", type=float, default=60.0, help="per-service startup budget")
    args = parser.parse_args()

    say()
    say(paint("  AgriPredict — local development stack", C_BOLD))
    say(paint(f"  {REPO_ROOT}", C_DIM))
    say()

    # --- 1. interpreter ----------------------------------------------------
    step("Locating a Python interpreter with the backend dependencies")
    interpreter, missing = find_interpreter(args.python)
    if interpreter is None:
        fail("no interpreter could import the backend dependencies.")
        if missing:
            say(f"     last import error: {missing[0]}")
        say()
        say("  Create the environments, then run this again:")
        say()
        say("    make setup        # or see docs/installation/README.md")
        say()
        return 1
    say(f"    using {interpreter}")

    # --- 2. ports ----------------------------------------------------------
    wanted = [("API", args.api_port)]
    if not args.no_ml:
        wanted.insert(0, ("ML service", args.ml_port))
    for label, port in wanted:
        if port_in_use(port):
            fail(f"port {port} is already in use (needed by the {label}).")
            say(f"     Stop that process, or choose another port: --{'ml' if 'ML' in label else 'api'}-port")
            return 1

    # --- 3. data ----------------------------------------------------------
    db_path = BACKEND_DIR / "agripredict.db"
    if not args.no_seed:
        if db_path.exists():
            step("Checking the database")
            say(f"    found {db_path.name}")
        else:
            step("Creating the database and seeding reference data")
            say(f"    {db_path.name} will be created on first start")

    api_env = {
        **os.environ,
        "DATABASE_URL": os.environ.get("DATABASE_URL", "sqlite:///./agripredict.db"),
        "SECRET_KEY": os.environ.get("SECRET_KEY", DEV_SECRET),
        "ML_SERVICE_ENABLED": "false" if args.no_ml else "true",
        "ML_SERVICE_URL": f"http://127.0.0.1:{args.ml_port}",
        "WEATHER_PROVIDER": os.environ.get("WEATHER_PROVIDER", "mock"),
        "FRAME_OPTIONS": args.frame_options,
        "PYTHONPATH": str(BACKEND_DIR),
        "PYTHONUNBUFFERED": "1",
    }

    if not args.no_seed:
        # Django-style implicit migration is not a thing here, so the schema is
        # created explicitly. Both scripts are idempotent.
        step("Preparing the schema and demo prices")
        prepare = subprocess.run(
            [str(interpreter), "-c", PREPARE_SNIPPET, DEMO_EMAIL, DEMO_PASSWORD],
            cwd=BACKEND_DIR,
            env=api_env,
            capture_output=True,
        )
        output = (prepare.stdout + prepare.stderr).decode(errors="replace").strip()
        for line in output.splitlines():
            say(f"    {line}")
        if prepare.returncode != 0:
            fail("database preparation failed")
            return 1

    processes: list[tuple[str, subprocess.Popen]] = []

    def shutdown(*_args) -> None:
        for _label, process in processes:
            if process.poll() is None:
                process.terminate()
        deadline = time.time() + 8
        for _label, process in processes:
            remaining = max(0.1, deadline - time.time())
            try:
                process.wait(timeout=remaining)
            except subprocess.TimeoutExpired:
                process.kill()

    def on_signal(_signum, _frame):
        raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, on_signal)

    try:
        # --- 4. ML service -------------------------------------------------
        if not args.no_ml:
            step(f"Starting the ML service on {args.ml_port}")
            ml_env = {
                **os.environ,
                "PYTHONPATH": str(ML_DIR),
                "PYTHONUNBUFFERED": "1",
            }
            ml_cmd = [
                str(interpreter), "-m", "uvicorn", "inference.service:app",
                "--host", "0.0.0.0", "--port", str(args.ml_port),
            ]
            if args.reload:
                ml_cmd.append("--reload")
            ml_process = subprocess.Popen(
                ml_cmd, cwd=ML_DIR, env=ml_env,
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            )
            processes.append(("ML", ml_process))
            stream(ml_process, "ML", C_CYAN)
            if not wait_for_health(
                f"http://127.0.0.1:{args.ml_port}/health",
                label="ML service", timeout=args.timeout, process=ml_process,
            ):
                shutdown()
                return 1
            say(f"    {paint('healthy', C_GREEN)}  http://127.0.0.1:{args.ml_port}/docs")

        # --- 5. API --------------------------------------------------------
        step(f"Starting the API on {args.api_port}")
        api_cmd = [
            str(interpreter), "-m", "uvicorn", "app.main:app",
            "--host", "0.0.0.0", "--port", str(args.api_port),
        ]
        if args.reload:
            api_cmd.append("--reload")
        api_process = subprocess.Popen(
            api_cmd, cwd=BACKEND_DIR, env=api_env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        processes.append(("API", api_process))
        stream(api_process, "API", C_YELLOW)
        if not wait_for_health(
            f"http://127.0.0.1:{args.api_port}/health",
            label="API", timeout=args.timeout, process=api_process,
        ):
            shutdown()
            return 1

        # The API's /health polls the ML service, so this is the real check:
        # both processes up AND wired to each other.
        try:
            health = http_json(f"http://127.0.0.1:{args.api_port}/health")
        except Exception:  # noqa: BLE001 - reported below
            health = {}
        say(
            f"    {paint('healthy', C_GREEN)}  database={health.get('database')} "
            f"ml={health.get('ml_service')}"
        )

        base = f"http://127.0.0.1:{args.api_port}"
        say()
        say(paint("  Ready", C_GREEN + C_BOLD))
        say(f"    API      {base}")
        say(f"    docs     {base}/docs")
        say(f"    health   {base}/health")
        if not args.no_ml:
            say(f"    ML       http://127.0.0.1:{args.ml_port}/docs")
        say()
        say(paint("  Demo account (seeded):  demo@agripredict.pk / Sunflower2026", C_DIM))
        say(
            paint(
                "  Android client: cd frontend && npm install && npm run android",
                C_DIM,
            )
        )
        say(paint("  Press Ctrl-C to stop.", C_DIM))
        say()

        # --- 6. supervise --------------------------------------------------
        while True:
            for label, process in processes:
                code = process.poll()
                if code is not None:
                    fail(f"the {label} process exited (code {code}); stopping the rest.")
                    shutdown()
                    return code or 1
            time.sleep(0.5)
    except KeyboardInterrupt:
        say()
        step("Shutting down")
        shutdown()
        say("    stopped")
        return 0


# Runs inside the backend directory with the backend environment, so it can use
# the application's own code rather than reimplementing schema creation.
PREPARE_SNIPPET = r"""
import sys

DEMO_EMAIL, DEMO_PASSWORD = sys.argv[1], sys.argv[2]

from app.database import init_db, SessionLocal
from app.services.seed_service import seed_reference_data
from sqlalchemy import func, select
from app.models import PriceRecord, User

init_db()
with SessionLocal() as session:
    seed_reference_data(session)
    prices = session.scalar(select(func.count()).select_from(PriceRecord)) or 0
    print(f"reference data ready, {prices} price rows")

    # The banner quotes demo credentials, so they have to exist. Created only
    # for a local development run: this script is never the production path, and
    # a known password must not exist on a real deployment.
    exists = session.scalar(select(User).where(User.email == DEMO_EMAIL))
    if exists is None:
        from app.schemas import UserCreate
        from app.services import auth_service

        auth_service.register_user(
            session,
            UserCreate(email=DEMO_EMAIL, password=DEMO_PASSWORD, full_name="Demo Farmer"),
        )
        print(f"created the demo account ({DEMO_EMAIL})")
    else:
        print("demo account already present")

if prices == 0:
    import runpy
    sys.argv = ["seed_demo_prices.py", "--days", "400"]
    runpy.run_path("scripts/seed_demo_prices.py", run_name="__main__")
"""


if __name__ == "__main__":
    raise SystemExit(main())
