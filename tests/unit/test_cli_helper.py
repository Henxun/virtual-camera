# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from types import SimpleNamespace

from apps.cli.akvc_cli import __main__ as cli


class FakeHelper:
    def __init__(self) -> None:
        self.last_error_message = None
        self.install_calls: list[tuple[str, str]] = []
        self.uninstall_calls: list[str] = []
        self.ensure_calls: list[str] = []
        self.start_installed_calls: list[str] = []
        self.stop_calls = 0
        self.register_mf_calls: list[str] = []
        self.unregister_mf_calls = 0
        self.register_mf_ok = True
        self.unregister_mf_ok = True
        self.runtime_status = {"pid": 1234, "heartbeat_100ns": 99, "producer_seq": 7}
        self.task_status = {
            "task_name": "AKVirtualCameraHelper",
            "installed": True,
            "pipe_reachable": True,
        }

    def install_autostart(self, task_name: str, log_path: str) -> bool:
        self.install_calls.append((task_name, log_path))
        return True

    def uninstall_autostart(self, task_name: str) -> bool:
        self.uninstall_calls.append(task_name)
        return True

    def ensure_running(self, *, task_name: str, prefer_installed: bool = True) -> bool:
        self.ensure_calls.append(task_name)
        return True

    def start_installed(self, task_name: str, timeout_s: float = 8.0) -> bool:
        self.start_installed_calls.append(task_name)
        return True

    def stop(self) -> None:
        self.stop_calls += 1

    def register_mf(self, name: str = "AK Virtual Camera") -> bool:
        self.register_mf_calls.append(name)
        return self.register_mf_ok

    def unregister_mf(self) -> bool:
        self.unregister_mf_calls += 1
        return self.unregister_mf_ok

    def scheduled_task_status(self, task_name: str = "AKVirtualCameraHelper") -> dict:
        data = dict(self.task_status)
        data["task_name"] = task_name
        return data

    def status(self):
        return dict(self.runtime_status)


def test_cli_imports_helper_and_runtime_from_akvc() -> None:
    assert cli.HelperService.__module__ == "akvc.helper_service"
    assert cli.find_dshow_dll.__module__ == "akvc.windows_runtime"


def test_cmd_helper_install_uses_helper(monkeypatch, capsys) -> None:
    helper = FakeHelper()
    monkeypatch.setattr(cli, "HelperService", lambda helper_exe=None: helper)

    rc = cli.cmd_helper_install(SimpleNamespace(exe=None, task_name="TaskA", log="helper.log"))

    assert rc == 0
    assert helper.install_calls == [("TaskA", "helper.log")]
    assert "installed helper task TaskA" in capsys.readouterr().out


def test_cmd_helper_start_uses_ensure_running_by_default(monkeypatch, capsys) -> None:
    helper = FakeHelper()
    monkeypatch.setattr(cli, "HelperService", lambda helper_exe=None: helper)

    rc = cli.cmd_helper_start(SimpleNamespace(exe=None, task_name="TaskA", installed_only=False))

    assert rc == 0
    assert helper.ensure_calls == ["TaskA"]
    assert helper.start_installed_calls == []
    assert "helper reachable" in capsys.readouterr().out


def test_cmd_helper_start_can_force_installed_task(monkeypatch) -> None:
    helper = FakeHelper()
    monkeypatch.setattr(cli, "HelperService", lambda helper_exe=None: helper)

    rc = cli.cmd_helper_start(SimpleNamespace(exe=None, task_name="TaskA", installed_only=True))

    assert rc == 0
    assert helper.start_installed_calls == ["TaskA"]
    assert helper.ensure_calls == []



def test_cmd_helper_register_mf_ensures_running_then_registers(monkeypatch, capsys) -> None:
    helper = FakeHelper()
    monkeypatch.setattr(cli, "HelperService", lambda helper_exe=None: helper)

    rc = cli.cmd_helper_register_mf(SimpleNamespace(exe=None, task_name="TaskA", name="AK Virtual Camera"))

    assert rc == 0
    assert helper.ensure_calls == ["TaskA"]
    assert helper.register_mf_calls == ["AK Virtual Camera"]
    assert "MF virtual camera registered" in capsys.readouterr().out


    helper = FakeHelper()
    monkeypatch.setattr(cli, "HelperService", lambda helper_exe=None: helper)

    rc = cli.cmd_helper_status(SimpleNamespace(task_name="TaskA"))

    out = capsys.readouterr().out
    assert rc == 0
    assert "Helper task:" in out
    assert "Installed:" in out
    assert "Helper PID:" in out


def test_cmd_helper_stop_requests_helper_shutdown(monkeypatch, capsys) -> None:
    helper = FakeHelper()
    monkeypatch.setattr(cli, "HelperService", lambda helper_exe=None: helper)

    rc = cli.cmd_helper_stop(SimpleNamespace())

    assert rc == 0
    assert helper.stop_calls == 1
    assert "helper stop requested" in capsys.readouterr().out


def test_cmd_unregister_removes_mf_then_dshow(monkeypatch, capsys) -> None:
    helper = FakeHelper()
    monkeypatch.setattr(cli, "HelperService", lambda helper_exe=None: helper)
    monkeypatch.setattr(cli, "_find_dll", lambda: cli.Path("C:/tmp/akvc-dshow.dll"))
    monkeypatch.setattr(cli, "_read_inproc_path", lambda: "C:/tmp/akvc-dshow.dll")
    monkeypatch.setattr(cli, "_is_admin", lambda: True)

    calls: list[list[str]] = []

    def fake_call(cmd: list[str]) -> int:
        calls.append(cmd)
        return 0

    monkeypatch.setattr(cli.subprocess, "call", fake_call)
    monkeypatch.setattr(cli.Path, "is_file", lambda self: True)

    rc = cli.cmd_unregister(SimpleNamespace(dll=None))

    assert rc == 0
    assert helper.ensure_calls == ["AKVirtualCameraHelper"]
    assert helper.unregister_mf_calls == 1
    assert calls == [["regsvr32", "/u", "/s", str(cli.Path("C:/tmp/akvc-dshow.dll"))]]
    out = capsys.readouterr().out
    assert "MF virtual camera removed or already absent" in out
    assert "DShow filter unregistered" in out


def test_cmd_unregister_treats_absent_dshow_as_success_when_mf_removed(monkeypatch, capsys) -> None:
    helper = FakeHelper()
    monkeypatch.setattr(cli, "HelperService", lambda helper_exe=None: helper)
    monkeypatch.setattr(cli, "_find_dll", lambda: cli.Path("C:/tmp/akvc-dshow.dll"))
    monkeypatch.setattr(cli, "_read_inproc_path", lambda: None)
    monkeypatch.setattr(cli, "_is_admin", lambda: True)
    monkeypatch.setattr(cli.Path, "is_file", lambda self: True)

    calls: list[list[str]] = []
    monkeypatch.setattr(cli.subprocess, "call", lambda cmd: calls.append(cmd) or 0)

    rc = cli.cmd_unregister(SimpleNamespace(dll=None))

    assert rc == 0
    assert helper.unregister_mf_calls == 1
    assert calls == []
    out = capsys.readouterr().out
    assert "MF virtual camera removed or already absent" in out
    assert "DShow filter already absent" in out


    helper = FakeHelper()
    helper.unregister_mf_ok = False
    monkeypatch.setattr(cli, "HelperService", lambda helper_exe=None: helper)
    monkeypatch.setattr(cli, "_find_dll", lambda: cli.Path("C:/tmp/akvc-dshow.dll"))
    monkeypatch.setattr(cli, "_is_admin", lambda: True)
    monkeypatch.setattr(cli.Path, "is_file", lambda self: True)
    monkeypatch.setattr(cli.subprocess, "call", lambda cmd: 0)

    rc = cli.cmd_unregister(SimpleNamespace(dll=None))

    assert rc == 1
    assert helper.unregister_mf_calls == 1
