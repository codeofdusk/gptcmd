"""
This module contains the ConfigManager class, which controls Gptcmd's
config system.
Copyright 2024 Bill Dengler
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""


import dataclasses
import os
import sys
import platform
import shlex
import shutil
from importlib import resources
from typing import Dict, List, Optional, Type

if sys.version_info >= (3, 8):
    from importlib.metadata import entry_points
else:
    from importlib_metadata import entry_points

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from .llm import LLMProvider
from .llm.openai import AzureAI, OpenAI


DEFAULT_PROVIDERS: Dict[str, Type[LLMProvider]] = {
    "openai": OpenAI,
    "azure": AzureAI,
}


class ConfigError(Exception):
    pass


@dataclasses.dataclass(frozen=True)
class Account:
    name: str
    provider: LLMProvider


class ConfigManager:
    "Handles Gptcmd's configuration system."

    def __init__(
        self,
        config: Dict,
        providers: Optional[Dict[str, Type[LLMProvider]]] = None,
    ):
        """
        Initialize the ConfigManager with a configuration dictionary.
        """
        # Validate the provided config
        if "schema_version" not in config:
            raise ConfigError("Missing 'schema_version'")

        conf = self._load_sample_config()

        my_major = int(conf.pop("schema_version").split(".")[0])
        their_major = int(config["schema_version"].split(".")[0])
        if their_major > my_major:
            raise ConfigError(
                "This configuration is too new for the current version"
                " of Gptcmd!"
            )

        conf.update(config)
        self.conf = conf
        if providers is None:
            providers = self.__class__._discover_external_providers(
                initial_providers=DEFAULT_PROVIDERS
            )
        self.accounts = self._configure_accounts(
            self.conf["accounts"], providers
        )

    @staticmethod
    def _discover_external_providers(
        initial_providers: Optional[Dict[str, Type[LLMProvider]]] = None,
    ) -> Dict[str, Type[LLMProvider]]:
        """
        Discover external providers registered via entry points.
        """
        res: Dict[str, Type[LLMProvider]] = {}
        if initial_providers:
            res.update(initial_providers)
        eps = entry_points()
        ENTRY_POINT_GROUP = "gptcmd.providers"
        if hasattr(eps, "select"):
            selected_eps = eps.select(group=ENTRY_POINT_GROUP)
        else:
            selected_eps = eps.get(ENTRY_POINT_GROUP, ())
        for ep in selected_eps:
            provider_cls = ep.load()
            if ep.name in res:

                def fully_qualified_name(cls):
                    return cls.__module__ + "." + cls.__qualname__

                raise ConfigError(
                    f"Duplicate registration for {ep.name}:"
                    f" {fully_qualified_name(res[ep.name])} and"
                    f" {fully_qualified_name(provider_cls)}"
                )
            else:
                res[ep.name] = provider_cls
        return res

    @classmethod
    def from_toml(cls, path: Optional[str] = None):
        """
        Create a ConfigManager instance from a TOML file.
        """
        if path is None:
            config_root = cls._get_config_root()
            config_path = os.path.join(config_root, "config.toml")
            if not os.path.exists(config_path):
                os.makedirs(config_root, exist_ok=True)
                with resources.path(
                    "gptcmd", "config_sample.toml"
                ) as sample_path:
                    shutil.copy(sample_path, config_path)
        else:
            config_path = path

        try:
            with open(config_path, "rb") as fin:
                return cls(tomllib.load(fin))
        except (FileNotFoundError, OSError, tomllib.TOMLDecodeError) as e:
            raise ConfigError(str(e)) from e

    def _configure_accounts(
        self, account_config: Dict, providers: Dict[str, Type[LLMProvider]]
    ) -> Dict[str, Account]:
        res = {}
        for name, conf in account_config.items():
            if "provider" not in conf:
                raise ConfigError(f"Account {name} has no provider specified")
            provider = providers.get(conf["provider"])
            if not provider:
                raise ConfigError(
                    f"Provider {conf['provider']} is not available. Perhaps"
                    " you need to install it?"
                )
            res[name] = Account(name=name, provider=provider.from_config(conf))
        return res

    @property
    def default_account(self) -> LLMProvider:
        try:
            return self.accounts.get(
                "default",
                next(
                    iter(self.accounts.values())
                ),  # The first configured account
            )
        except StopIteration:
            raise ConfigError("No default account configured")

    @property
    def editor(self) -> List[str]:
        posix = platform.system().lower() != "windows"
        editor = (
            self.conf.get("editor") or self.__class__._get_default_editor()
        )
        return shlex.split(editor, posix=posix)

    @staticmethod
    def _get_config_root():
        """Get the root directory for the configuration file."""
        system = platform.system().lower()
        if system == "windows":
            base_path = os.environ.get("APPDATA") or os.path.expanduser("~")
        elif system == "darwin":
            base_path = os.path.expanduser("~/Library/Application Support")
        else:
            base_path = os.environ.get(
                "XDG_CONFIG_HOME"
            ) or os.path.expanduser("~/.config")
        return os.path.join(base_path, "gptcmd")

    @staticmethod
    def _load_sample_config():
        "Load the sample configuration file as a dict"
        with resources.open_binary("gptcmd", "config_sample.toml") as fin:
            return tomllib.load(fin)

    @staticmethod
    def _get_default_editor():
        system = platform.system().lower()
        if system == "windows":
            # On Windows, default to notepad
            return "notepad"
        else:
            # On Unix-like systems, use the EDITOR environment variable if set
            editor = os.environ.get("EDITOR")
            if editor:
                return editor
            else:
                # Try common editors in order of preference
                for cmd in ("nano", "emacs", "vim", "ed", "vi"):
                    if shutil.which(cmd):
                        return cmd
                raise ConfigError("No editor available")
