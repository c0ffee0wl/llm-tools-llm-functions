"""Configuration management for llm-tools-llm-functions plugin."""

import os
import yaml
from pathlib import Path
from typing import Optional, Dict, Any, List


class Config:
    """Manages configuration for llm-functions integration."""

    DEFAULT_FUNCTIONS_DIR = Path.home() / "llm-functions"
    DEFAULT_FUNCTIONS_JSON = "functions.json"
    CONFIG_FILE_PATH = Path.home() / ".config" / "io.datasette.llm" / "llm-functions.yaml"

    def __init__(self):
        self._config: Dict[str, Any] = {}
        self._load_config()

    def _load_config(self):
        """Load configuration from file and environment variables."""
        # Load from config file if it exists
        if self.CONFIG_FILE_PATH.exists():
            try:
                with open(self.CONFIG_FILE_PATH, 'r') as f:
                    self._config = yaml.safe_load(f) or {}
            except Exception as e:
                # If config file is malformed, use defaults
                self._config = {}

        # Environment variables override config file
        # Priority: LLM_FUNCTIONS_DIR > AICHAT_FUNCTIONS_DIR > config file > default
        if os.environ.get('LLM_FUNCTIONS_DIR'):
            self._config['functions_directory'] = os.environ['LLM_FUNCTIONS_DIR']
        elif os.environ.get('AICHAT_FUNCTIONS_DIR'):
            # Fallback to standard llm-functions environment variable
            self._config['functions_directory'] = os.environ['AICHAT_FUNCTIONS_DIR']

        if os.environ.get('LLM_FUNCTIONS_JSON'):
            self._config['functions_json'] = os.environ['LLM_FUNCTIONS_JSON']

    @property
    def functions_directory(self) -> Path:
        """Get the llm-functions directory path."""
        dir_path = self._config.get('functions_directory', self.DEFAULT_FUNCTIONS_DIR)
        return Path(dir_path).expanduser()

    @property
    def functions_json_path(self) -> Path:
        """Get the full path to functions.json."""
        json_path = self._config.get('functions_json')
        if json_path:
            return Path(json_path).expanduser()

        # Default: functions.json in the functions directory
        return self.functions_directory / self.DEFAULT_FUNCTIONS_JSON

    @property
    def tool_allowlist(self) -> Optional[List[str]]:
        """Get list of allowed tool names. None means all tools allowed."""
        allowlist = self._config.get('tool_allowlist')
        return allowlist if allowlist else None

    @property
    def tool_denylist(self) -> List[str]:
        """Get list of denied tool names."""
        return self._config.get('tool_denylist', [])

    @property
    def enable_guard(self) -> bool:
        """Whether to use llm-functions guard_operation.sh."""
        return self._config.get('enable_guard', True)

    @property
    def max_output_size(self) -> int:
        """Maximum output size in bytes."""
        return self._config.get('max_output_size', 1024 * 1024)  # 1MB default

    @property
    def timeout(self) -> int:
        """Execution timeout in seconds."""
        return self._config.get('timeout', 30)

    def is_tool_allowed(self, tool_name: str) -> bool:
        """Check if a tool is allowed to be registered and executed."""
        # Check denylist first
        if tool_name in self.tool_denylist:
            return False

        # If allowlist exists, tool must be in it
        if self.tool_allowlist is not None:
            return tool_name in self.tool_allowlist

        # No allowlist means all tools allowed (except denied ones)
        return True


# Global config instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get or create the global configuration instance."""
    global _config
    if _config is None:
        _config = Config()
    return _config
