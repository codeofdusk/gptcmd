"""
Gptcmd package root
Copyright 2025 Bill Dengler
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""

__all__ = ["__version__", "Gptcmd"]

__version__ = "2.3.1"

from .cli import Gptcmd  # noqa: E402
