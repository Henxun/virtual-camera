#!/usr/bin/env python3
# SPDX-License-Identifier: Apache-2.0
"""Top-level entry point for Nuitka packaging.

Nuitka compiles this file as the main script. It imports the akvc_app package
(absolute import) and runs its main(), avoiding the relative-import issues that
arise when compiling akvc_app/__main__.py directly as a standalone script.
"""

from __future__ import annotations

import sys

from akvc_app.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
