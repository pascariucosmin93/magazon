import os
import signal
import socket
import subprocess
import time
from pathlib import Path

import pytest
import requests


ROOT = Path(__file__).resolve().parents[2]
HOST = "127.0.0.1"
INFRA_PORTS = {
    "postgres": 55432,
    "redis": 56379,
    "kafka": 59094,
}
SERVICE_PORTS = {
    "auth-service": 18080,
    "product-service": 18081,
    "cart-service": 18082,
    "order-service": 18083,
    "inventory-service": 18084,
    "payment-service": 18085,
}
SERVICE_DIRS = {
    "auth-service": ROOT / "services" / "auth-service",
    "product-service": ROOT / "services" / "product-service",
    "cart-service": ROOT / "services" / "cart-service",
    "order-service": ROOT / "services" / "order-service",
    "inventory-service": ROOT / "services" / "inventory-service",
    "payment-service": ROOT / "services" / "payment-service",
}


def _service_database_name(service_name: str) -> str:
    return service_name.replace("-service", "").replace("-", "_") + "_e2e"


def _wait_for_port(host: str, port: int, timeout_seconds: float) -> bool:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(1)
            if sock.connect_ex((host, port)) == 0:
                return True
        time.sleep(1)
    return False


def _wait_for_http(url: str, timeout_seconds: float) -> None:
    deadline = time.time() + timeout_seconds
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            response = requests.get(url, timeout=2)
            if response.status_code == 200:
                return
            last_error = RuntimeError(f"{url} returned {response.status_code}: {response.text}")
        except requests.RequestException as exc:
            last_error = exc
        time.sleep(1)
    raise RuntimeError(f"Timed out waiting for {url}: {last_error}")


def _service_env(service_name: str) -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "PYTHONPATH": str(ROOT),
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONUNBUFFERED": "1",
            "SERVICE_NAME": service_name,
            "SERVICE_PORT": str(SERVICE_PORTS[service_name]),
            "POSTGRES_HOST": HOST,
            "POSTGRES_PORT": str(INFRA_PORTS["postgres"]),
            "POSTGRES_DB": _service_database_name(service_name),
            "POSTGRES_USER": "microshop",
            "POSTGRES_PASSWORD": "microshop",
            "REDIS_URL": f"redis://{HOST}:{INFRA_PORTS['redis']}/0",
            "KAFKA_BOOTSTRAP_SERVERS": f"{HOST}:{INFRA_PORTS['kafka']}",
            "JWT_SECRET": "e2e-jwt-secret-minimum-32-chars-xxx",
            "ADMIN_EMAIL": "admin@microshop.local",
            "ADMIN_PASSWORD": "e2e-admin-password",
            "STRIPE_SECRET_KEY": "sk_test_e2e_local",
            "STRIPE_WEBHOOK_SECRET": "whsec_e2e_local",
            "PUBLIC_BASE_URL": f"http://{HOST}:{SERVICE_PORTS['payment-service']}",
            "INTERNAL_API_TOKEN": "e2e-internal-token",
            "PRODUCT_SERVICE_URL": f"http://{HOST}:{SERVICE_PORTS['product-service']}",
            "ORDER_SERVICE_URL": f"http://{HOST}:{SERVICE_PORTS['order-service']}",
        }
    )
    return env


def _start_service(service_name: str, log_dir: Path) -> tuple[subprocess.Popen[str], Path]:
    log_path = log_dir / f"{service_name}.log"
    log_file = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [
            "python3",
            "-m",
            "uvicorn",
            "app.main:app",
            "--app-dir",
            str(SERVICE_DIRS[service_name]),
            "--host",
            HOST,
            "--port",
            str(SERVICE_PORTS[service_name]),
        ],
        cwd=ROOT,
        env=_service_env(service_name),
        stdout=log_file,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    return process, log_path


def _run_migrations_for_service(service_name: str) -> None:
    migrate_path = SERVICE_DIRS[service_name] / "migrate.py"
    if not migrate_path.exists():
        return
    completed = subprocess.run(
        ["python3", str(migrate_path)],
        cwd=ROOT,
        env=_service_env(service_name),
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"Migration failed for {service_name}\nSTDOUT:\n{completed.stdout}\nSTDERR:\n{completed.stderr}"
        )


def _read_log_tail(log_path: Path, max_chars: int = 6000) -> str:
    if not log_path.exists():
        return f"{log_path.name}: <missing>"
    text = log_path.read_text(encoding="utf-8", errors="replace")
    if len(text) > max_chars:
        text = text[-max_chars:]
    return f"===== {log_path.name} =====\n{text}"


def _stop_processes(processes: dict[str, subprocess.Popen[str]], log_paths: dict[str, Path]) -> None:
    for service_name, process in reversed(list(processes.items())):
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        log_path = log_paths.get(service_name)
        if log_path and process.returncode not in (0, -signal.SIGTERM):
            print(_read_log_tail(log_path))


@pytest.fixture(scope="session")
def e2e_stack(tmp_path_factory: pytest.TempPathFactory) -> dict[str, str]:
    missing = [
        f"{name}:{port}"
        for name, port in INFRA_PORTS.items()
        if not _wait_for_port(HOST, port, timeout_seconds=2)
    ]
    if missing:
        pytest.skip(
            "E2E infra is not running. Start it with "
            "`docker compose -f tests/e2e/docker-compose.infra.yml up -d` "
            f"and retry. Missing: {', '.join(missing)}"
        )

    log_dir = tmp_path_factory.mktemp("e2e-service-logs")
    processes: dict[str, subprocess.Popen[str]] = {}
    log_paths: dict[str, Path] = {}
    service_order = [
        "auth-service",
        "product-service",
        "cart-service",
        "inventory-service",
        "order-service",
        "payment-service",
    ]

    try:
        for service_name in service_order:
            _run_migrations_for_service(service_name)
        for service_name in service_order:
            process, log_path = _start_service(service_name, log_dir)
            processes[service_name] = process
            log_paths[service_name] = log_path

        for service_name in service_order:
            _wait_for_http(
                f"http://{HOST}:{SERVICE_PORTS[service_name]}/ready",
                timeout_seconds=90,
            )
    except Exception as exc:
        _stop_processes(processes, log_paths)
        logs = "\n\n".join(_read_log_tail(path) for path in log_paths.values())
        raise RuntimeError(f"Failed to start E2E stack: {exc}\n\n{logs}") from exc

    yield {name: f"http://{HOST}:{port}" for name, port in SERVICE_PORTS.items()}

    _stop_processes(processes, log_paths)
