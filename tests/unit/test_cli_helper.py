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
        self.register_mf_ok = True
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

    def start_installed(self, task_name: str) -> bool:
        self.start_installed_calls.append(task_name)
        return True

    def stop(self) -> None:
        self.stop_calls += 1

    def register_mf(self, name: str = "AK Virtual Camera") -> bool:
        self.register_mf_calls.append(name)
        return self.register_mf_ok

    def scheduled_task_status(self, task_name: str = "AKVirtualCameraHelper") -> dict:
        data = dict(self.task_status)
        data["task_name"] = task_name
        return data

    def status(self):
        return dict(self.runtime_status)


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
