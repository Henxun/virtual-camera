# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

from apps.desktop.akvc_app.services.facade import ServiceFacade


class FakeHelper:
    def __init__(self, *, start_result: bool = True, ping_result: bool = True, register_result: bool = True,
                 last_error_message: str | None = None) -> None:
        self.start_result = start_result
        self.ping_result = ping_result
        self.register_result = register_result
        self.last_error_message = last_error_message

    def start(self) -> bool:
        return self.start_result

    def ping(self) -> bool:
        return self.ping_result

    def register_mf(self, name: str = "AK Virtual Camera") -> bool:
        return self.register_result

    def stop(self) -> None:
        return None


def test_start_raises_when_helper_fails(monkeypatch) -> None:
    facade = ServiceFacade()
    facade._state.selected_source_id = "demo"
    facade._helper = FakeHelper(
        start_result=False,
        last_error_message="helper launch failed",
    )
    monkeypatch.setattr(facade, "_is_windows", True)

    try:
        facade.start()
    except RuntimeError as exc:
        assert "helper launch failed" in str(exc)
    else:
        raise AssertionError("start should fail when helper does not start")


def test_start_raises_when_mf_registration_fails(monkeypatch) -> None:
    facade = ServiceFacade()
    facade._state.selected_source_id = "demo"
    facade._helper = FakeHelper(register_result=False)
    monkeypatch.setattr(facade, "_is_windows", True)

    try:
        facade.start()
    except RuntimeError as exc:
        assert "register MF virtual camera" in str(exc)
    else:
        raise AssertionError("start should fail when MF registration fails")
