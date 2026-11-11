"""Fresh-process checks for dotenv loading before project configuration imports."""
import json
import os
from pathlib import Path
import subprocess
import sys
import sysconfig

import pytest


_PROBE = r"""
import json
import os
from pathlib import Path
import sys

project, env_file, work_root = map(Path, sys.argv[1:])
for package_path in json.loads(os.environ["CONFIGURATION_PROBE_PACKAGE_PATHS"]):
    if package_path:
        sys.path.append(package_path)
sys.path.insert(0, str(project))
sys.dont_write_bytecode = True
work_root = work_root.resolve()
write_flags = os.O_WRONLY | os.O_RDWR | os.O_APPEND | os.O_CREAT | os.O_TRUNC

def check_write(path):
    if isinstance(path, int) or os.fsdecode(path) == ":memory:":
        return
    resolved = Path(os.fsdecode(path)).resolve()
    if not resolved.is_relative_to(work_root):
        raise PermissionError("Configuration probe attempted a write outside its temporary directory")

def offline_guard(event, args):
    if event == "open":
        path, mode, flags = args
        if (flags is not None and flags & write_flags) or (isinstance(mode, str) and any(ch in mode for ch in "wax+")):
            check_write(path)
    elif event == "sqlite3.connect":
        check_write(args[0])
    elif event in {"os.mkdir", "os.remove", "os.rmdir", "os.chmod", "os.utime", "os.truncate"}:
        check_write(args[0])
    elif event in {"os.rename", "os.link", "os.symlink"}:
        check_write(args[0])
        check_write(args[1])
    elif event in {
        "socket.connect", "socket.bind", "socket.sendto", "socket.getaddrinfo",
        "socket.gethostbyname", "socket.gethostbyaddr", "socket.getnameinfo",
        "subprocess.Popen", "os.system", "os.startfile", "os.posix_spawn", "os.spawn",
    }:
        raise PermissionError("Configuration probe permits no network or subprocess operations")

sys.addaudithook(offline_guard)
import dotenv

original_load_dotenv = dotenv.load_dotenv
def load_test_dotenv(*args, **kwargs):
    # Only redirect the file location; use real parsing and default precedence.
    kwargs["dotenv_path"] = env_file
    return original_load_dotenv(*args, **kwargs)

dotenv.load_dotenv = load_test_dotenv
import main
from learning_app import config, db
from learning_app.services import exam_mock_llm, tutor_tts

print(json.dumps({
    "data_dir": str(config.DATA_DIR),
    "main_data_dir": str(main.DATA_DIR),
    "db_path": str(config.DB_PATH),
    "db_connection_path": str(db.DB_PATH),
    "language": config.DEFAULT_EXPLANATION_LANGUAGE,
    "goal": config.DEFAULT_GOAL_EXAM,
    "tts_provider": tutor_tts.TUTOR_TTS_PROVIDER,
    "mock_llm_enabled": exam_mock_llm.EXAM_MOCK_LLM_ENABLED,
}))
"""


@pytest.mark.parametrize("process_overrides", [False, True], ids=["dotenv-values", "process-precedence"])
def test_configuration_is_loaded_before_dependent_modules(
    tmp_path: Path, process_overrides: bool
) -> None:
    project = Path(__file__).resolve().parents[1]
    env_file = tmp_path / "synthetic.env"
    from_file = tmp_path / "dotenv-data"
    from_process = tmp_path / "process-data"
    env_file.write_text(
        "\n".join([
            f"APP_DATA_DIR={json.dumps(from_file.as_posix(), ensure_ascii=False)}",
            f"APP_DB_PATH={json.dumps((from_file / 'from-dotenv.db').as_posix(), ensure_ascii=False)}",
            "APP_EXPLANATION_LANGUAGE=en",
            "APP_DEFAULT_GOAL_EXAM=goethe_c1",
            "TUTOR_TTS_PROVIDER=none",
            "EXAM_MOCK_LLM_ENABLED=1",
        ]) + "\n",
        encoding="utf-8",
    )
    probe = tmp_path / "configuration_probe.py"
    probe.write_text(_PROBE, encoding="utf-8")
    allowed = {
        "SYSTEMROOT", "WINDIR", "SYSTEMDRIVE", "PATH", "PATHEXT", "COMSPEC",
        "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS", "PROGRAMFILES",
        "PROGRAMFILES(X86)", "PROGRAMW6432",
    }
    child_env = {key: value for key, value in os.environ.items() if key.upper() in allowed}
    child_env.update({
        "CONFIGURATION_PROBE_PACKAGE_PATHS": json.dumps(list(dict.fromkeys(
            [sysconfig.get_path("purelib"), sysconfig.get_path("platlib")]
            + [item for item in sys.path if item.endswith(("site-packages", "dist-packages"))]
        ))),
        "TEMP": str(tmp_path), "TMP": str(tmp_path),
        "USERPROFILE": str(tmp_path / "profile"),
        "APPDATA": str(tmp_path / "profile" / "AppData" / "Roaming"),
        "LOCALAPPDATA": str(tmp_path / "profile" / "AppData" / "Local"),
        "HF_HOME": str(tmp_path / "hf-cache"),
        "XDG_CACHE_HOME": str(tmp_path / "cache"),
        "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1",
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "PYTHONDONTWRITEBYTECODE": "1", "OLLAMA_ENABLE_STARTUP_WARMUP": "0",
        "CHAT_PROVIDER": "rulebased", "MOCK_AUDIO_PROVIDER": "none",
    })
    expected = {
        "data_dir": str(from_file.resolve()),
        "main_data_dir": str(from_file.resolve()),
        "db_path": str((from_file / "from-dotenv.db").resolve()),
        "db_connection_path": str((from_file / "from-dotenv.db").resolve()),
        "language": "en", "goal": "goethe_c1",
        "tts_provider": "none", "mock_llm_enabled": True,
    }
    if process_overrides:
        child_env.update({
            "APP_DATA_DIR": str(from_process),
            "APP_DB_PATH": str(from_process / "from-process.db"),
            "APP_EXPLANATION_LANGUAGE": "de",
            "APP_DEFAULT_GOAL_EXAM": "goethe_a2",
            "TUTOR_TTS_PROVIDER": "piper",
            "EXAM_MOCK_LLM_ENABLED": "0",
        })
        expected.update({
            "data_dir": str(from_process.resolve()),
            "main_data_dir": str(from_process.resolve()),
            "db_path": str((from_process / "from-process.db").resolve()),
            "db_connection_path": str((from_process / "from-process.db").resolve()),
            "language": "de", "goal": "goethe_a2",
            "tts_provider": "piper", "mock_llm_enabled": False,
        })
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-S", str(probe), str(project), str(env_file), str(tmp_path)],
        cwd=tmp_path, env=child_env, capture_output=True, text=True, encoding="utf-8",
        timeout=60, check=False,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == expected
