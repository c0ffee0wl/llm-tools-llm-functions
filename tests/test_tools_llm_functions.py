"""Tests for llm-tools-llm-functions plugin."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from llm.plugins import pm
from llm_tools_llm_functions import (
    FunctionJsonParser,
    ToolExecutor,
    ToolWrapper,
)
from config import Config


def test_plugin_is_installed():
    """Test that the plugin is properly installed."""
    names = [mod.__name__ for mod in pm.get_plugins()]
    assert "llm_tools_llm_functions" in names


class TestFunctionJsonParser:
    """Tests for FunctionJsonParser."""

    def test_parse_array_format(self, tmp_path):
        """Test parsing functions.json in array format."""
        functions_data = [
            {
                "name": "test_tool",
                "description": "A test tool",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "input": {"type": "string", "description": "Input text"}
                    },
                    "required": ["input"]
                }
            }
        ]

        json_path = tmp_path / "functions.json"
        with open(json_path, 'w') as f:
            json.dump(functions_data, f)

        parser = FunctionJsonParser(json_path)
        functions = parser.parse()

        assert len(functions) == 1
        assert functions[0]["name"] == "test_tool"
        assert functions[0]["description"] == "A test tool"

    def test_parse_object_format(self, tmp_path):
        """Test parsing functions.json in object format with 'functions' key."""
        functions_data = {
            "functions": [
                {
                    "name": "test_tool",
                    "description": "A test tool"
                }
            ]
        }

        json_path = tmp_path / "functions.json"
        with open(json_path, 'w') as f:
            json.dump(functions_data, f)

        parser = FunctionJsonParser(json_path)
        functions = parser.parse()

        assert len(functions) == 1
        assert functions[0]["name"] == "test_tool"

    def test_file_not_found(self, tmp_path):
        """Test error handling when functions.json doesn't exist."""
        json_path = tmp_path / "nonexistent.json"
        parser = FunctionJsonParser(json_path)

        with pytest.raises(FileNotFoundError):
            parser.parse()

    def test_invalid_json(self, tmp_path):
        """Test error handling for invalid JSON."""
        json_path = tmp_path / "invalid.json"
        with open(json_path, 'w') as f:
            f.write("{ invalid json }")

        parser = FunctionJsonParser(json_path)

        with pytest.raises(ValueError, match="Invalid JSON"):
            parser.parse()


class TestConfig:
    """Tests for Config class."""

    def test_default_paths(self):
        """Test default configuration paths."""
        config = Config()

        assert config.functions_directory == Path.home() / "llm-functions"
        assert config.functions_json_path == Path.home() / "llm-functions" / "functions.json"

    def test_env_var_override(self, tmp_path, monkeypatch):
        """Test environment variable overrides."""
        custom_dir = tmp_path / "custom-llm-functions"
        custom_json = tmp_path / "custom.json"

        monkeypatch.setenv('LLM_FUNCTIONS_DIR', str(custom_dir))
        monkeypatch.setenv('LLM_FUNCTIONS_JSON', str(custom_json))

        config = Config()

        assert config.functions_directory == custom_dir
        assert config.functions_json_path == custom_json

    def test_aichat_functions_dir(self, tmp_path, monkeypatch):
        """Test AICHAT_FUNCTIONS_DIR environment variable."""
        custom_dir = tmp_path / "aichat-functions"
        monkeypatch.setenv('AICHAT_FUNCTIONS_DIR', str(custom_dir))

        config = Config()

        assert config.functions_directory == custom_dir

    def test_env_var_precedence(self, tmp_path, monkeypatch):
        """Test that LLM_FUNCTIONS_DIR takes precedence over AICHAT_FUNCTIONS_DIR."""
        llm_dir = tmp_path / "llm-functions"
        aichat_dir = tmp_path / "aichat-functions"

        monkeypatch.setenv('AICHAT_FUNCTIONS_DIR', str(aichat_dir))
        monkeypatch.setenv('LLM_FUNCTIONS_DIR', str(llm_dir))

        config = Config()

        # LLM_FUNCTIONS_DIR should take precedence
        assert config.functions_directory == llm_dir

    def test_tool_allowlist(self):
        """Test tool allowlist functionality."""
        config = Config()
        config._config = {
            'tool_allowlist': ['allowed_tool']
        }

        assert config.is_tool_allowed('allowed_tool') is True
        assert config.is_tool_allowed('other_tool') is False

    def test_tool_denylist(self):
        """Test tool denylist functionality."""
        config = Config()
        config._config = {
            'tool_denylist': ['denied_tool']
        }

        assert config.is_tool_allowed('denied_tool') is False
        assert config.is_tool_allowed('other_tool') is True

    def test_allowlist_and_denylist(self):
        """Test that denylist takes precedence over allowlist."""
        config = Config()
        config._config = {
            'tool_allowlist': ['tool1', 'tool2'],
            'tool_denylist': ['tool2']
        }

        assert config.is_tool_allowed('tool1') is True
        assert config.is_tool_allowed('tool2') is False
        assert config.is_tool_allowed('tool3') is False


class TestToolExecutor:
    """Tests for ToolExecutor."""

    def test_build_command_basic(self, tmp_path):
        """Test building basic command with parameters."""
        tool_def = {
            "name": "test_tool",
            "parameters": {
                "properties": {
                    "command": {"type": "string"},
                    "verbose": {"type": "boolean"}
                }
            }
        }

        # Create a dummy tool script
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        tool_script = tools_dir / "test_tool.sh"
        tool_script.write_text("#!/bin/bash\necho 'test'")
        tool_script.chmod(0o755)

        executor = ToolExecutor(tool_def, tmp_path)

        # Test with string parameter
        cmd = executor.build_command(command="ls -la")
        assert str(tool_script) in cmd
        assert "--command" in cmd
        assert "ls -la" in cmd

        # Test with boolean parameter
        cmd = executor.build_command(verbose=True)
        assert "--verbose" in cmd

    def test_build_command_finds_script(self, tmp_path):
        """Test that executor finds tool scripts with various extensions."""
        tool_def = {"name": "my_tool", "parameters": {}}

        # Test .sh extension
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        tool_script = tools_dir / "my_tool.sh"
        tool_script.write_text("#!/bin/bash")

        executor = ToolExecutor(tool_def, tmp_path)
        cmd = executor.build_command()
        assert str(tool_script) in cmd

    def test_build_command_script_not_found(self, tmp_path):
        """Test error when tool script is not found."""
        tool_def = {"name": "nonexistent_tool", "parameters": {}}
        executor = ToolExecutor(tool_def, tmp_path)

        with pytest.raises(FileNotFoundError, match="Tool script.*not found"):
            executor.build_command()

    @patch('subprocess.run')
    def test_execute_success(self, mock_run, tmp_path):
        """Test successful tool execution."""
        tool_def = {
            "name": "test_tool",
            "parameters": {
                "properties": {
                    "input": {"type": "string"}
                }
            }
        }

        # Create tool script
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        tool_script = tools_dir / "test_tool.sh"
        tool_script.write_text("#!/bin/bash\necho 'success'")
        tool_script.chmod(0o755)

        # Mock subprocess result
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "success"
        mock_result.stderr = ""
        mock_run.return_value = mock_result

        executor = ToolExecutor(tool_def, tmp_path)

        # Mock the output file reading
        with patch('builtins.open', create=True) as mock_open:
            mock_open.return_value.__enter__ = lambda x: x
            mock_open.return_value.__exit__ = lambda x, *args: None
            mock_open.return_value.read = lambda: "tool output"

            result = executor.execute(input="test")

            # Check that output contains something
            assert "success" in result or "tool output" in result

    @patch('subprocess.run')
    def test_execute_failure(self, mock_run, tmp_path):
        """Test handling of tool execution failure."""
        tool_def = {"name": "test_tool", "parameters": {}}

        # Create tool script
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        tool_script = tools_dir / "test_tool.sh"
        tool_script.write_text("#!/bin/bash\nexit 1")
        tool_script.chmod(0o755)

        # Mock subprocess failure
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stdout = ""
        mock_result.stderr = "error message"
        mock_run.return_value = mock_result

        executor = ToolExecutor(tool_def, tmp_path)

        with patch('builtins.open', create=True):
            with pytest.raises(RuntimeError, match="failed with exit code 1"):
                executor.execute()


class TestToolWrapper:
    """Tests for ToolWrapper."""

    def test_create_callable(self, tmp_path):
        """Test creating a callable function from tool definition."""
        tool_def = {
            "name": "example_tool",
            "description": "An example tool",
            "parameters": {
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Input text"
                    }
                },
                "required": ["text"]
            }
        }

        # Create dummy script
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        tool_script = tools_dir / "example_tool.sh"
        tool_script.write_text("#!/bin/bash")
        tool_script.chmod(0o755)

        wrapper = ToolWrapper(tool_def, tmp_path)
        tool_func = wrapper.create_callable()

        # Check function metadata
        assert tool_func.__name__ == "example_tool"
        assert "An example tool" in tool_func.__doc__
        assert "text" in tool_func.__doc__

    def test_callable_validates_required_params(self, tmp_path):
        """Test that the callable validates required parameters."""
        tool_def = {
            "name": "test_tool",
            "description": "Test",
            "parameters": {
                "properties": {
                    "required_param": {"type": "string"}
                },
                "required": ["required_param"]
            }
        }

        # Create dummy script
        tools_dir = tmp_path / "tools"
        tools_dir.mkdir()
        tool_script = tools_dir / "test_tool.sh"
        tool_script.write_text("#!/bin/bash")
        tool_script.chmod(0o755)

        wrapper = ToolWrapper(tool_def, tmp_path)
        tool_func = wrapper.create_callable()

        # Should raise error for missing required parameter
        with pytest.raises(ValueError, match="Required parameter.*missing"):
            tool_func()


class TestIntegration:
    """Integration tests."""

    def test_full_integration(self, tmp_path, monkeypatch):
        """Test full integration from functions.json to tool registration."""
        # Set up test environment
        functions_dir = tmp_path / "llm-functions"
        functions_dir.mkdir()

        tools_dir = functions_dir / "tools"
        tools_dir.mkdir()

        # Create functions.json
        functions_data = [
            {
                "name": "echo_tool",
                "description": "Echoes input",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "message": {"type": "string", "description": "Message to echo"}
                    },
                    "required": ["message"]
                }
            }
        ]

        functions_json = functions_dir / "functions.json"
        with open(functions_json, 'w') as f:
            json.dump(functions_data, f)

        # Create tool script
        tool_script = tools_dir / "echo_tool.sh"
        tool_script.write_text("#!/bin/bash\necho $@")
        tool_script.chmod(0o755)

        # Set environment to use test directory
        monkeypatch.setenv('LLM_FUNCTIONS_DIR', str(functions_dir))

        # Test the full flow
        from config import get_config
        config = get_config()
        config._config = {}  # Reset config
        config._load_config()

        parser = FunctionJsonParser(config.functions_json_path)
        functions = parser.parse()

        assert len(functions) == 1
        assert functions[0]["name"] == "echo_tool"

        # Create wrapper
        wrapper = ToolWrapper(functions[0], config.functions_directory)
        tool_func = wrapper.create_callable()

        assert tool_func.__name__ == "echo_tool"
        assert "Echoes input" in tool_func.__doc__
