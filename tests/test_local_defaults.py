"""Startup safeguards tested with mocked servers; no listener or tunnel is started."""
import ast
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

import main
import run_local_servers as local
import run_public_tunnel as public


@pytest.fixture()
def demo_environment(tmp_path, monkeypatch):
    private = tmp_path / "private"
    private.mkdir()
    (private / "learning_app.db").write_bytes(b"fictional private sentinel")
    monkeypatch.setenv("APP_DATA_DIR", str(private))
    monkeypatch.setenv("APP_DB_PATH", str(private / "learning_app.db"))
    monkeypatch.setattr(public, "_PUBLIC_DEMO_DIR", None)
    monkeypatch.setattr(public, "QUICK_TUNNEL_HOME", tmp_path / "unused-profile")
    return private


def fake_servers(monkeypatch):
    configs = []
    threads = []
    class Server:
        def __init__(self, config):
            self.config = config
            self.should_exit = False
            configs.append(config)
        def run(self):
            raise AssertionError("Tests must not run application servers")
    class Thread:
        def __init__(self, **kwargs):
            self.kwargs = kwargs
            self.started = False
            threads.append(self)
        def start(self):
            self.started = True
        def join(self, **kwargs):
            pass
        def is_alive(self):
            return False
    monkeypatch.setattr(local.uvicorn, "Server", Server)
    monkeypatch.setattr(local.threading, "Thread", Thread)
    return configs, threads


def test_default_arguments_are_loopback_http_without_browser_or_lan():
    args = local.parse_args([])
    assert args.host == "127.0.0.1"
    assert args.https is False and args.lan is False
    assert args.open_url == ""


@pytest.mark.parametrize("host", ["0.0.0.0", "192.168.0.8", "::"])
def test_non_loopback_binding_requires_explicit_lan_flag(host):
    with pytest.raises(SystemExit):
        local.parse_args(["--host", host])
    assert local.parse_args(["--lan", "--host", host]).host == host
    with pytest.raises(ValueError):
        local.build_server_threads(host=host, http_port=8000, https_port=8443, local_ip="")


def test_default_builder_does_not_prepare_certificates(monkeypatch):
    configs, threads = fake_servers(monkeypatch)
    monkeypatch.setattr(local, "ensure_local_https_materials", lambda **_: pytest.fail("Unexpected certificates"))
    http, thread, https, secure_thread = local.build_server_threads(
        host="127.0.0.1", http_port=8000, https_port=8443, local_ip=""
    )
    assert https is None and secure_thread is None
    assert [config.host for config in configs] == ["127.0.0.1"]
    assert len(threads) == 1 and not thread.started


def test_https_remains_available_only_when_explicitly_enabled(monkeypatch):
    configs, _ = fake_servers(monkeypatch)
    calls = []
    def certificates(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(cert_path=Path("fictional-cert.pem"), key_path=Path("fictional-key.pem"))
    monkeypatch.setattr(local, "ensure_local_https_materials", certificates)
    servers = local.build_server_threads(
        host="127.0.0.1", http_port=8000, https_port=8443, local_ip="", enable_https=True
    )
    assert len(calls) == 1
    assert servers[2] is not None and servers[3] is not None
    assert [config.host for config in configs] == ["127.0.0.1", "127.0.0.1"]


def test_ordinary_main_waits_for_readiness_and_stops_only_mock_servers(monkeypatch):
    configs, threads = fake_servers(monkeypatch)
    monkeypatch.setattr(sys, "argv", ["run_local_servers.py"])
    monkeypatch.setattr(local, "ensure_local_https_materials", lambda **_: pytest.fail("Unexpected certificates"))
    monkeypatch.setattr(local, "wait_for_app_readiness", lambda **_: {"provider": "ollama", "active_model": "fictional"})
    monkeypatch.setattr(local, "open_browser_if_requested", lambda url: None if url == "" else pytest.fail("Unexpected browser"))
    assert local.main() == 0
    assert len(configs) == 1 and configs[0].host == "127.0.0.1"
    assert len(threads) == 1 and threads[0].started


def test_launcher_has_no_executable_install_download_tunnel_or_browser_command():
    lines = Path("iniciar_chatbot.bat").read_text(encoding="utf-8").splitlines()
    commands = [line.strip().lower() for line in lines if line.strip() and not line.strip().lower().startswith(("echo ", "@echo", "rem ", ":"))]
    for command in commands:
        assert "pip install" not in command
        assert "winget install" not in command
        assert "ollama pull" not in command
        assert "run_public_tunnel.py" not in command
        assert "--open-url" not in command
        assert " -m venv " not in command


def test_runner_imports_do_not_capture_the_application_before_mode_checks():
    tree = ast.parse(Path("run_local_servers.py").read_text(encoding="utf-8-sig"))
    assert not any(isinstance(node, ast.ImportFrom) and node.module == "main" for node in tree.body)


@pytest.mark.parametrize("value", [None, "", "  "])
def test_cors_default_and_empty_setting_use_explicit_local_origins(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("ALLOWED_ORIGINS", raising=False)
    else:
        monkeypatch.setenv("ALLOWED_ORIGINS", value)
    origins = main.parse_allowed_origins()
    assert "*" not in origins
    assert origins == main.DEFAULT_LOCAL_ORIGINS


def test_cors_allows_local_preflight_and_blocks_untrusted_origin():
    client = TestClient(main.app)
    headers = {"Origin": "http://127.0.0.1:8000", "Access-Control-Request-Method": "GET"}
    response = client.options("/api/settings", headers=headers)
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == headers["Origin"]
    assert "access-control-allow-credentials" not in response.headers
    headers["Origin"] = "https://untrusted.invalid"
    response = client.options("/api/settings", headers=headers)
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
    client.close()


def test_explicit_custom_cors_origin_is_preserved(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://fictional.invalid")
    assert main.parse_allowed_origins() == ["https://fictional.invalid"]


@pytest.mark.parametrize("arguments", [[], ["--public"], ["--demo-data-dir", "fictional"]])
def test_public_cli_requires_both_explicit_opt_in_and_demo_directory(arguments):
    with pytest.raises(SystemExit):
        public.parse_args(arguments)


def test_public_backend_remains_loopback(tmp_path):
    args = public.parse_args(["--public", "--demo-data-dir", str(tmp_path / "demo")])
    assert args.host == "127.0.0.1" and not args.https
    with pytest.raises(SystemExit):
        public.parse_args(["--public", "--demo-data-dir", str(tmp_path / "demo"), "--host", "0.0.0.0"])


def test_public_demo_redirects_both_stores_and_leaves_existing_data_unchanged(tmp_path, demo_environment):
    demo = tmp_path / "demo"
    public.prepare_demo_data(demo)
    public.require_demo_mode()
    assert Path(public.os.environ["APP_DATA_DIR"]) == demo
    assert Path(public.os.environ["APP_DB_PATH"]) == demo / "learning_app.db"
    assert public.QUICK_TUNNEL_HOME.is_relative_to(demo)
    assert (demo_environment / "learning_app.db").read_bytes() == b"fictional private sentinel"


@pytest.mark.parametrize("location", ["private", "private/child", "."])
def test_public_demo_rejects_personal_directories_and_their_ancestors(tmp_path, demo_environment, location):
    with pytest.raises(ValueError):
        public.prepare_demo_data(tmp_path / location)


def test_public_demo_rejects_nonempty_existing_directory(tmp_path, demo_environment):
    demo = tmp_path / "existing-demo"
    demo.mkdir()
    (demo / "state.json").write_text("fictional stored history", encoding="utf-8")
    with pytest.raises(ValueError):
        public.prepare_demo_data(demo)
    assert (demo / "state.json").read_text(encoding="utf-8") == "fictional stored history"


@pytest.mark.parametrize("starter", [public.start_quick_tunnel, public.start_localhost_run_tunnel])
def test_tunnel_starters_refuse_without_demonstration_mode(monkeypatch, starter):
    monkeypatch.setattr(public, "_PUBLIC_DEMO_DIR", None)
    monkeypatch.setattr(public.subprocess, "Popen", lambda *a, **k: pytest.fail("Unexpected subprocess"))
    with pytest.raises(RuntimeError, match="demonstration"):
        starter(8000)


def test_public_main_refuses_preloaded_application_before_starting_anything(tmp_path, monkeypatch):
    demo = tmp_path / "demo"
    monkeypatch.setattr(sys, "argv", ["run_public_tunnel.py", "--public", "--demo-data-dir", str(demo)])
    monkeypatch.setattr(public, "build_server_threads", lambda **_: pytest.fail("Unexpected server"))
    assert public.main() == 2
    assert not demo.exists()
