from pathlib import Path

import local_https


def test_build_certificate_hosts_includes_local_ip_and_defaults() -> None:
    hosts = local_https.build_certificate_hosts(local_ip="192.168.0.27")

    assert "localhost" in hosts
    assert "127.0.0.1" in hosts
    assert "192.168.0.27" in hosts


def test_ensure_local_https_materials_writes_expected_files(tmp_path: Path) -> None:
    materials = local_https.ensure_local_https_materials(
        local_ip="192.168.0.27",
        cert_dir=tmp_path,
    )

    assert materials.ca_cert_path.exists()
    assert materials.cert_path.exists()
    assert materials.key_path.exists()
    assert "192.168.0.27" in materials.hosts


def test_paid_deployment_blueprint_removed() -> None:
    assert not Path("render.yaml").exists()


def test_public_launcher_and_tunnel_script_exist() -> None:
    launcher = Path("iniciar_chatbot.bat").read_text(encoding="utf-8")
    runner = Path("run_public_tunnel.py").read_text(encoding="utf-8")
    readme = Path("README.md").read_text(encoding="utf-8")

    assert "run_local_servers.py %*" in launcher
    assert 'parser.add_argument("--public"' in runner
    assert 'parser.add_argument("--demo-data-dir"' in runner
    assert "require_demo_mode()" in runner
    assert "trycloudflare" in runner
    assert "localhost.run" in runner
    assert "iniciar_chatbot.bat" in readme
    assert not Path("iniciar_chatbot_publico.bat").exists()
