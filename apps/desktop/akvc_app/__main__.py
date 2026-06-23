# SPDX-License-Identifier: Apache-2.0
"""Application entry point."""

from __future__ import annotations

import multiprocessing as mp
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from akvc.core import logging as akvc_log

from .services.facade import ServiceFacade
from .viewmodels.main_vm import MainViewModel
from .views.main_window import MainWindow


def main() -> int:
    # Ensure clean spawn semantics on Windows.
    mp.set_start_method("spawn", force=True)

    log_dir = Path.home() / "AppData" / "Local" / "AKVC" / "logs"
    log = akvc_log.configure(level="INFO", log_dir=log_dir, component="akvc.app")
    log.info("akvc.app.start version=%s", "0.2.0")

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("AK Virtual Camera")
    app.setOrganizationName("AKVC")

    facade = ServiceFacade()
    facade.bootstrap()

    vm = MainViewModel(facade)
    win = MainWindow(vm)
    win.show()

    rc = app.exec()
    facade.shutdown()
    log.info("akvc.app.exit code=%s", rc)
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
