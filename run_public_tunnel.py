from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path

from run_local_servers import (
    build_server_threads,
    describe_runtime_config,
    open_browser_if_requested,
    wait_for_app_readiness,
)

TRYCLOUDFLARE_URL_RE = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com", re.IGNORECASE)
GENERIC_HTTPS_URL_RE = re.compile(r"https://[^\s\]]+", re.IGNORECASE)
QUICK_TUNNEL_HOME = Path(__file__).resolve().parent / "data" / "cloudflared_quick"


@dataclass
class TunnelHandle:
    name: str
    process: subprocess.Popen[str]
    url_holder: dict[str, str]
    url_ready: threading.Event
    log_thread: threading.Thread


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local servers plus a free public HTTPS quick tunnel.")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--http-port", type=int, default=8000)
    parser.add_argument("--https-port", type=int, default=8443)
    parser.add_argument("--local-ip", default="")
    parser.add_argument("--open-url", default="")
    parser.add_argument("--startup-timeout", type=float, default=90.0)
    parser.add_argument("--expected-provider", choices=["ollama", "rulebased"], default="ollama")
    return parser.parse_args()


def find_cloudflared() -> str:
    env_candidate = os.environ.get("CLOUDFLARED_EXE", "").strip()
    if env_candidate and Path(env_candidate).exists():
        return env_candidate

    candidates = ["cloudflared", "cloudflared.exe"]
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved

    path_candidates = [
        Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "WinGet" / "Packages",
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "cloudflared",
        Path(os.environ.get("ProgramFiles", "")) / "Cloudflare" / "Cloudflared",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Cloudflare" / "Cloudflared",
    ]
    for base in path_candidates:
        if not str(base):
            continue
        if base.is_file() and base.name.lower() == "cloudflared.exe":
            return str(base)
        if not base.exists():
            continue
        try:
            match = next(base.rglob("cloudflared.exe"))
        except StopIteration:
            continue
        return str(match)

    raise RuntimeError(
        "cloudflared is not installed. Install it for free with 'winget install --id Cloudflare.cloudflared'."
    )


def find_ssh() -> str:
    candidates = ["ssh", "ssh.exe"]
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise RuntimeError("OpenSSH client is not available on this system.")


def build_cloudflared_env() -> dict[str, str]:
    QUICK_TUNNEL_HOME.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    home_value = str(QUICK_TUNNEL_HOME)
    env["HOME"] = home_value
    env["USERPROFILE"] = home_value
    return env


def stream_cloudflared_logs(
    process: subprocess.Popen[str],
    *,
    label: str,
    parse_url,
    url_holder: dict[str, str],
    url_ready: threading.Event,
) -> None:
    assert process.stdout is not None
    for raw_line in process.stdout:
        line = raw_line.strip()
        if not line:
            continue
        url = parse_url(line)
        if url and not url_holder.get("url"):
            url_holder["url"] = url
            url_ready.set()
        print(f"[{label}] {line}")


def parse_cloudflared_url(line: str) -> str | None:
    match = TRYCLOUDFLARE_URL_RE.search(line)
    return match.group(0) if match else None


def parse_localhost_run_url(line: str) -> str | None:
    if "tunneled with tls termination" not in line:
        return None
    match = GENERIC_HTTPS_URL_RE.search(line)
    return match.group(0) if match else None


def start_quick_tunnel(http_port: int) -> TunnelHandle:
    cloudflared = find_cloudflared()
    command = [
        cloudflared,
        "tunnel",
        "--url",
        f"http://127.0.0.1:{http_port}",
        "--no-autoupdate",
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
        env=build_cloudflared_env(),
    )
    url_holder: dict[str, str] = {}
    url_ready = threading.Event()
    log_thread = threading.Thread(
        target=stream_cloudflared_logs,
        args=(process,),
        kwargs={
            "label": "cloudflared",
            "parse_url": parse_cloudflared_url,
            "url_holder": url_holder,
            "url_ready": url_ready,
        },
        name="cloudflared-logs",
        daemon=True,
    )
    log_thread.start()
    return TunnelHandle(
        name="cloudflared",
        process=process,
        url_holder=url_holder,
        url_ready=url_ready,
        log_thread=log_thread,
    )


def start_localhost_run_tunnel(http_port: int) -> TunnelHandle:
    ssh = find_ssh()
    command = [
        ssh,
        "-T",
        "-o",
        "StrictHostKeyChecking=no",
        "-o",
        "ServerAliveInterval=30",
        "-R",
        f"80:127.0.0.1:{http_port}",
        "nokey@localhost.run",
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        bufsize=1,
    )
    url_holder: dict[str, str] = {}
    url_ready = threading.Event()
    log_thread = threading.Thread(
        target=stream_cloudflared_logs,
        args=(process,),
        kwargs={
            "label": "localhost.run",
            "parse_url": parse_localhost_run_url,
            "url_holder": url_holder,
            "url_ready": url_ready,
        },
        name="localhost-run-logs",
        daemon=True,
    )
    log_thread.start()
    return TunnelHandle(
        name="localhost.run",
        process=process,
        url_holder=url_holder,
        url_ready=url_ready,
        log_thread=log_thread,
    )


def stop_tunnel(handle: TunnelHandle | None) -> None:
    if not handle:
        return
    if handle.process.poll() is None:
        handle.process.terminate()
        try:
            handle.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            handle.process.kill()
    handle.log_thread.join(timeout=1)


def wait_for_public_url(handle: TunnelHandle, timeout_s: float = 20.0) -> str:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if handle.url_ready.wait(timeout=0.5):
            return handle.url_holder.get("url", "")
        if handle.process.poll() is not None:
            break
    return handle.url_holder.get("url", "")


def main() -> int:
    args = parse_args()
    http_server, http_thread, https_server, https_thread = build_server_threads(
        host=args.host,
        http_port=args.http_port,
        https_port=args.https_port,
        local_ip=args.local_ip,
    )

    http_thread.start()
    https_thread.start()

    tunnel_handle: TunnelHandle | None = None

    try:
        runtime_config = wait_for_app_readiness(
            http_port=args.http_port,
            expected_provider=args.expected_provider,
            timeout_s=args.startup_timeout,
        )
        print()
        print(f"Backend listo: {describe_runtime_config(runtime_config)}")
        open_browser_if_requested(args.open_url)
        time.sleep(1.0)
        for starter in (start_localhost_run_tunnel, start_quick_tunnel):
            try:
                candidate = starter(args.http_port)
            except RuntimeError as exc:
                print()
                print(f"No se pudo iniciar {starter.__name__}: {exc}")
                continue

            print()
            print(f"Creando enlace publico HTTPS gratis con {candidate.name}...")
            public_url = wait_for_public_url(candidate, timeout_s=20.0)
            if public_url:
                print(f"URL publica segura: {public_url}")
                print("Comparte esta URL en el movil o en otro PC. No hace falta instalar certificado web.")
                print()
                tunnel_handle = candidate
                break

            print(
                f"No se pudo obtener URL publica con {candidate.name}. "
                "La app seguira funcionando en local y se probara el siguiente fallback si existe."
            )
            print()
            stop_tunnel(candidate)

        if tunnel_handle is None:
            print("No se pudo crear ningun enlace publico HTTPS gratis. La app seguira funcionando en local.")
            print()

        warned_http = False
        warned_https = False
        warned_tunnel = False
        while True:
            http_alive = http_thread.is_alive()
            https_alive = https_thread.is_alive()

            if not http_alive and not https_alive:
                break

            if not http_alive and not warned_http:
                print()
                print(
                    f"El servidor HTTP en el puerto {args.http_port} se ha detenido. "
                    f"{'El HTTPS sigue disponible.' if https_alive else 'No queda ningun servidor local activo.'}"
                )
                warned_http = True

            if not https_alive and not warned_https:
                print()
                print(
                    f"El servidor HTTPS en el puerto {args.https_port} no esta disponible. "
                    f"{'La app sigue abierta por HTTP.' if http_alive else 'No queda ningun servidor local activo.'}"
                )
                warned_https = True

            if tunnel_handle and tunnel_handle.process.poll() is not None and not warned_tunnel:
                print()
                print(
                    f"El tunel publico {tunnel_handle.name} se ha detenido. "
                    "La app sigue abierta en local; revisa las lineas del tunel o prueba mas tarde."
                )
                stop_tunnel(tunnel_handle)
                tunnel_handle = None
                warned_tunnel = True

            time.sleep(0.25)
    except KeyboardInterrupt:
        pass
    except RuntimeError as exc:
        print()
        print(exc)
        return 1
    finally:
        http_server.should_exit = True
        https_server.should_exit = True
        stop_tunnel(tunnel_handle)
        http_thread.join(timeout=5)
        https_thread.join(timeout=5)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
