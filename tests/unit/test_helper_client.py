# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from pathlib import Path

from akvc.core.helper.client import DEFAULT_PERSISTENT_LOG, HelperService


class FakeNative:
    def __init__(self) -> None:
        self.ping_values = [False]
        self.last_launch_error = ""
        self.last_pipe_error = ""
        self.install_calls: list[tuple[str, str, str]] = []
        self.uninstall_calls: list[str] = []
        self.start_installed_calls: list[str] = []
        self.launch_calls: list[tuple[str, int, str]] = []
        self.quit_calls = 0
        self.status_value = None
        self.scheduled_status = {
            "task_name": "AKVirtualCameraHelper",
            "installed": False,
            "pipe_reachable": False,
        }
        self.elevated = False

    def ping(self) -> bool:
        if len(self.ping_values) > 1:
            return self.ping_values.pop(0)
        return self.ping_values[0]

    def status(self):
        return self.status_value

    def register_mf(self, name: str) -> bool:
        return True

    def install_autostart(self, exe_path: str, log_path: str, task_name: str) -> bool:
        self.install_calls.append((exe_path, log_path, task_name))
        self.scheduled_status = {
            "task_name": task_name,
            "installed": True,
            "pipe_reachable": False,
        }
        return True

    def uninstall_autostart(self, task_name: str) -> bool:
        self.uninstall_calls.append(task_name)
        self.scheduled_status = {
            "task_name": task_name,
            "installed": False,
            "pipe_reachable": False,
        }
        return True

    def start_installed(self, task_name: str) -> bool:
        self.start_installed_calls.append(task_name)
        return True

    def scheduled_task_status(self, task_name: str) -> dict:
        data = dict(self.scheduled_status)
        data["task_name"] = task_name
        return data

    def is_process_elevated(self) -> bool:
        return self.elevated

    def launch(self, exe_path: str, parent_pid: int, log_path: str) -> bool:
        self.launch_calls.append((exe_path, parent_pid, log_path))
        return True

    def quit(self) -> bool:
        self.quit_calls += 1
        return True


class DummyProc:
    def __init__(self) -> None:
        self.wait_calls: list[float] = []
        self.killed = False

    def wait(self, timeout: float | None = None) -> None:
        self.wait_calls.append(0.0 if timeout is None else timeout)

    def kill(self) -> None:
        self.killed = True


def make_helper(monkeypatch, native: FakeNative) -> HelperService:
    monkeypatch.setattr("akvc.core.helper.client.NativeWindowsHelperClient", lambda: native)
    return HelperService(helper_exe=Path("C:/tmp/akvc_helper.exe"))


def test_install_autostart_uses_helper_exe(monkeypatch) -> None:
    native = FakeNative()
    helper = make_helper(monkeypatch, native)
    monkeypatch.setattr("akvc.core.helper.client.find_helper_exe", lambda explicit=None: Path("C:/tmp/akvc_helper.exe"))

    assert helper.install_autostart(log_path=DEFAULT_PERSISTENT_LOG)
    assert native.install_calls == [(
        str(Path("C:/tmp/akvc_helper.exe")),
        DEFAULT_PERSISTENT_LOG,
        "AKVirtualCameraHelper",
    )]


def test_start_prefers_installed_helper(monkeypatch) -> None:
    native = FakeNative()
    native.scheduled_status["installed"] = True
    native.ping_values = [False, False, True]
    helper = make_helper(monkeypatch, native)

    assert helper.start()
    assert native.start_installed_calls == ["AKVirtualCameraHelper"]
    assert native.launch_calls == []


def test_start_falls_back_to_launch_when_not_installed(monkeypatch) -> None:
    native = FakeNative()
    native.ping_values = [False, True]
    helper = make_helper(monkeypatch, native)
    monkeypatch.setattr("akvc.core.helper.client.find_helper_exe", lambda explicit=None: Path("C:/tmp/akvc_helper.exe"))

    assert helper.start()
    assert native.start_installed_calls == []
    assert len(native.launch_calls) == 1


def test_stop_requests_quit_and_waits_for_proc(monkeypatch) -> None:
    native = FakeNative()
    helper = make_helper(monkeypatch, native)
    helper._proc = DummyProc()

    helper.stop(timeout=0.5)

    assert native.quit_calls == 1
    assert helper._proc is None


def test_scheduled_task_status_returns_native_dict(monkeypatch) -> None:
    native = FakeNative()
    native.scheduled_status = {
        "task_name": "CustomTask",
        "installed": True,
        "pipe_reachable": True,
    }
    helper = make_helper(monkeypatch, native)

    status = helper.scheduled_task_status("CustomTask")

    assert status == {
        "task_name": "CustomTask",
        "installed": True,
        "pipe_reachable": True,
    }
