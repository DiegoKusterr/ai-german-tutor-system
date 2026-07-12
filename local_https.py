from __future__ import annotations

import json
import socket
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

try:
    import trustme
except Exception:  # pragma: no cover - runtime dependency guard
    trustme = None


BASE_DIR = Path(__file__).resolve().parent
DEVCERT_DIR = BASE_DIR / "data" / "devcert"
LOCAL_CA_PEM_PATH = DEVCERT_DIR / "local-ca.pem"
LOCAL_CA_CERT_PATH = DEVCERT_DIR / "local-ca.crt"
LOCAL_CERT_PEM_PATH = DEVCERT_DIR / "local-cert.pem"
LOCAL_KEY_PEM_PATH = DEVCERT_DIR / "local-key.pem"
LOCAL_CERT_META_PATH = DEVCERT_DIR / "cert-meta.json"


@dataclass(frozen=True)
class LocalHttpsMaterials:
    ca_cert_path: Path
    cert_path: Path
    key_path: Path
    hosts: list[str]


def build_certificate_hosts(local_ip: str | None = None, extra_hosts: Iterable[str] | None = None) -> list[str]:
    hosts: list[str] = ["localhost", "127.0.0.1"]
    candidate_ip = str(local_ip or "").strip()
    if candidate_ip and candidate_ip not in hosts:
        hosts.append(candidate_ip)

    machine_names = {socket.gethostname().strip(), socket.getfqdn().strip()}
    for host in machine_names:
        if host and host not in hosts:
            hosts.append(host)

    for host in extra_hosts or []:
        cleaned = str(host or "").strip()
        if cleaned and cleaned not in hosts:
            hosts.append(cleaned)

    return hosts


def _write_cert_chain(cert_path: Path, cert_chain: list[object]) -> None:
    cert_bytes = b"".join(getattr(blob, "bytes")() for blob in cert_chain)
    cert_path.write_bytes(cert_bytes)


def ensure_local_https_materials(
    *,
    local_ip: str | None = None,
    cert_dir: Path | None = None,
    extra_hosts: Iterable[str] | None = None,
) -> LocalHttpsMaterials:
    if trustme is None:
        raise RuntimeError("trustme is not installed. Run pip install -r requirements.txt.")

    target_dir = cert_dir or DEVCERT_DIR
    target_dir.mkdir(parents=True, exist_ok=True)

    ca_pem_path = target_dir / LOCAL_CA_PEM_PATH.name
    ca_cert_path = target_dir / LOCAL_CA_CERT_PATH.name
    cert_path = target_dir / LOCAL_CERT_PEM_PATH.name
    key_path = target_dir / LOCAL_KEY_PEM_PATH.name
    meta_path = target_dir / LOCAL_CERT_META_PATH.name

    hosts = build_certificate_hosts(local_ip=local_ip, extra_hosts=extra_hosts)
    expected_meta = {"hosts": hosts}

    if all(path.exists() for path in (ca_pem_path, ca_cert_path, cert_path, key_path, meta_path)):
        try:
            current_meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            current_meta = {}
        if current_meta == expected_meta:
            return LocalHttpsMaterials(
                ca_cert_path=ca_cert_path,
                cert_path=cert_path,
                key_path=key_path,
                hosts=hosts,
            )

    ca = trustme.CA()
    leaf_cert = ca.issue_cert(*hosts)
    ca.cert_pem.write_to_path(ca_pem_path)
    ca.cert_pem.write_to_path(ca_cert_path)
    leaf_cert.private_key_pem.write_to_path(key_path)
    _write_cert_chain(cert_path, list(leaf_cert.cert_chain_pems))
    meta_path.write_text(json.dumps(expected_meta, ensure_ascii=False, indent=2), encoding="utf-8")

    return LocalHttpsMaterials(
        ca_cert_path=ca_cert_path,
        cert_path=cert_path,
        key_path=key_path,
        hosts=hosts,
    )
