import os
import sys
import platform
import shutil
from importlib import resources
from typing import Dict, Optional, Type

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from .llm import LLMProvider, OpenAI


"""
This module contains the ConfigManager class, which controls Gptcmd's
config system.
Copyright 2024 Bill Dengler
This Source Code Form is subject to the terms of the Mozilla Public
License, v. 2.0. If a copy of the MPL was not distributed with this
file, You can obtain one at https://mozilla.org/MPL/2.0/.
"""


DEFAULT_PROVIDERS: Dict[str, Type[LLMProvider]] = {"openai": OpenAI}


class ConfigError(Exception):
    pass


class ConfigManager:
    "Handles Gptcmd's configuration system."

    def __init__(
        self,
        config: Dict,
        providers: Dict[str, Type[LLMProvider]] = DEFAULT_PROVIDERS,
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
        self.accounts = self._configure_accounts(
            self.conf["accounts"], providers
        )

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
    ) -> Dict[str, LLMProvider]:
        res = {}
        for name, conf in account_config.items():
            if "provider" not in conf:
                raise ConfigError(f"Account {name} has no provider specified")
            provider = providers.get(conf["provider"])
            if not provider:
                raise ConfigError(
                    f"Provider {conf['provider']} is not available"
                )
            res[name] = provider.from_config(conf)
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
