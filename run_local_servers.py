from __future__ import annotations

import argparse
import ipaddress
import json
import os
import threading
import time
import webbrowser
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request as UrlRequest, urlopen

import uvicorn

from local_https import ensure_local_https_materials


def validate_bind_host(host: str, *, allow_lan: bool = False) -> None:
    try:
        loopback = host == "localhost" or ipaddress.ip_address(host).is_loopback
    except ValueError:
        loopback = False
    if not loopback and not allow_lan:
        raise ValueError("Non-loopback binding requires explicit --lan opt-in.")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local HTTP and HTTPS servers for the chatbot.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--lan", action="store_true", help="Explicitly allow a non-loopback bind address.")
    parser.add_argument("--https", action="store_true", help="Explicitly generate local certificate files and enable HTTPS; does not install a certificate.")
    parser.add_argument("--http-port", type=int, default=8000)
    parser.add_argument("--https-port", type=int, default=8443)
    parser.add_argument("--local-ip", default="")
    parser.add_argument("--open-url", default="")
    parser.add_argument("--startup-timeout", type=float, default=90.0)
    parser.add_argument("--expected-provider", choices=["ollama", "rulebased"], default="ollama")
    args = parser.parse_args(argv)
    try:
        validate_bind_host(args.host, allow_lan=args.lan)
    except ValueError as exc:
        parser.error(str(exc))
    return args


def build_server_threads(
    *, host: str, http_port: int, https_port: int, local_ip: str,
    enable_https: bool = False, allow_lan: bool = False,
) -> tuple[uvicorn.Server, threading.Thread, uvicorn.Server | None, threading.Thread | None]:
    validate_bind_host(host, allow_lan=allow_lan)
    # Public demo paths must be selected before application configuration imports.
    from main import app

    http_config = uvicorn.Config(app, host=host, port=http_port, reload=False, log_level="info", lifespan="on")
    http_server = uvicorn.Server(http_config)
    http_thread = threading.Thread(target=http_server.run, name="chatbot-http", daemon=True)
    if not enable_https:
        return http_server, http_thread, None, None
    materials = ensure_local_https_materials(local_ip=local_ip)
    https_config = uvicorn.Config(
        app,
        host=host,
        port=https_port,
        reload=False,
        log_level="info",
        lifespan="off",
        ssl_certfile=str(materials.cert_path),
        ssl_keyfile=str(materials.key_path),
    )

    https_server = uvicorn.Server(https_config)

    https_thread = threading.Thread(target=https_server.run, name="chatbot-https", daemon=True)
    return http_server, http_thread, https_server, https_thread


def fetch_runtime_config(http_port: int) -> dict[str, Any]:
    request = UrlRequest(url=f"http://127.0.0.1:{http_port}/config", method="GET")
    with urlopen(request, timeout=3) as response:
        if response.status != 200:
            raise RuntimeError(f"/config devolvio HTTP {response.status}.")
        body = response.read().decode("utf-8")
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError("/config devolvio JSON invalido.") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("/config devolvio una respuesta inesperada.")
    return payload


def describe_runtime_config(payload: dict[str, Any]) -> str:
    provider = str(payload.get("provider", "-"))
    llm_required = bool(payload.get("llm_required"))
    active_model = str(payload.get("active_model") or "-")
    return f"provider={provider}, llm_required={llm_required}, active_model={active_model}"


def runtime_config_is_ready(payload: dict[str, Any], *, expected_provider: str) -> bool:
    if expected_provider == "rulebased":
        return True
    provider = str(payload.get("provider") or "").strip().lower()
    active_model = str(payload.get("active_model") or "").strip()
    llm_required = bool(payload.get("llm_required"))
    return provider == "ollama" and not llm_required and bool(active_model)


def build_readiness_failure_message(
    *,
    expected_provider: str,
    last_config: dict[str, Any] | None,
    last_error: str,
) -> str:
    ollama_base_url = os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip() or "http://127.0.0.1:11434"
    ollama_model = os.getenv("OLLAMA_MODEL", "llama3.2:3b").strip() or "llama3.2:3b"

    lines = [
        "No se pudo dejar la app lista antes de abrir el navegador.",
        f"Proveedor esperado: {expected_provider}",
    ]
    if last_config:
        lines.append(f"Ultimo /config: {describe_runtime_config(last_config)}")
    if last_error:
        lines.append(f"Ultimo error de sondeo: {last_error}")

    if expected_provider == "ollama":
        lines.extend(
            [
                f"Ollama URL: {ollama_base_url}",
                f"Modelo configurado: {ollama_model}",
                f"Accion 1: comprueba que 'ollama serve' responde en {ollama_base_url}.",
                f"Accion 2: comprueba que el modelo existe con 'ollama show {ollama_model}'.",
                f"Accion 3: si falta, descargalo con 'ollama pull {ollama_model}'.",
            ]
        )
    else:
        lines.append("Accion: revisa los logs del backend y vuelve a intentar el arranque.")

    return "\n".join(lines)


def wait_for_app_readiness(
    *,
    http_port: int,
    expected_provider: str,
    timeout_s: float,
) -> dict[str, Any]:
    deadline = time.time() + max(5.0, timeout_s)
    last_config: dict[str, Any] | None = None
    last_error = ""

    while time.time() < deadline:
        try:
            payload = fetch_runtime_config(http_port)
            last_config = payload
            if runtime_config_is_ready(payload, expected_provider=expected_provider):
                return payload
            last_error = ""
        except HTTPError as exc:
            last_error = f"/config devolvio HTTP {exc.code}."
        except URLError as exc:
            last_error = f"/config no responde: {exc.reason}"
        except Exception as exc:
            last_error = str(exc)
        time.sleep(1.0)

    raise RuntimeError(
        build_readiness_failure_message(
            expected_provider=expected_provider,
            last_config=last_config,
            last_error=last_error,
        )
    )


def open_browser_if_requested(url: str) -> None:
    normalized_url = str(url or "").strip()
    if not normalized_url:
        return
    print(f"Abriendo navegador: {normalized_url}")
    try:
        webbrowser.open(normalized_url)
    except Exception:
        print(f"No se pudo abrir el navegador automaticamente. Abra manualmente: {normalized_url}")


def monitor_server_threads(
    *,
    http_thread: threading.Thread,
    https_thread: threading.Thread | None,
    http_port: int,
    https_port: int,
) -> None:
    warned_http = False
    warned_https = False
    while True:
        http_alive = http_thread.is_alive()
        https_alive = bool(https_thread and https_thread.is_alive())

        if not http_alive and not https_alive:
            break

        if not http_alive and not warned_http:
            print()
            print(
                f"El servidor HTTP en el puerto {http_port} se ha detenido. "
                f"{'El HTTPS sigue disponible.' if https_alive else 'No queda ningun servidor local activo.'}"
            )
            warned_http = True

        if https_thread is not None and not https_alive and not warned_https:
            print()
            print(
                f"El servidor HTTPS en el puerto {https_port} no esta disponible. "
                f"{'La app sigue abierta por HTTP.' if http_alive else 'No queda ningun servidor local activo.'}"
            )
            warned_https = True

        time.sleep(0.25)


def main() -> int:
    args = parse_args()
    http_server, http_thread, https_server, https_thread = build_server_threads(
        host=args.host,
        http_port=args.http_port,
        https_port=args.https_port,
        local_ip=args.local_ip,
        enable_https=args.https,
        allow_lan=args.lan,
    )

    http_thread.start()
    if https_thread is not None:
        https_thread.start()

    exit_code = 0
    try:
        runtime_config = wait_for_app_readiness(
            http_port=args.http_port,
            expected_provider=args.expected_provider,
            timeout_s=args.startup_timeout,
        )
        print()
        print(f"Backend listo: {describe_runtime_config(runtime_config)}")
        open_browser_if_requested(args.open_url)
        monitor_server_threads(
            http_thread=http_thread,
            https_thread=https_thread,
            http_port=args.http_port,
            https_port=args.https_port,
        )
    except KeyboardInterrupt:
        http_server.should_exit = True
    except RuntimeError as exc:
        exit_code = 1
        print()
        print(exc)
    finally:
        http_server.should_exit = True
        if https_server is not None:
            https_server.should_exit = True
        http_thread.join(timeout=5)
        if https_thread is not None:
            https_thread.join(timeout=5)

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
