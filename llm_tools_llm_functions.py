"""LLM plugin for integrating llm-functions tools."""

import json
import subprocess
import tempfile
import shlex
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable
import llm

from config import get_config


class FunctionJsonParser:
    """Parses llm-functions functions.json file."""

    def __init__(self, json_path: Path):
        self.json_path = json_path
        self._functions: List[Dict[str, Any]] = []

    def parse(self) -> List[Dict[str, Any]]:
        """Parse the functions.json file and return list of function definitions."""
        if not self.json_path.exists():
            raise FileNotFoundError(
                f"functions.json not found at {self.json_path}. "
                "Make sure llm-functions is installed and configured."
            )

        try:
            with open(self.json_path, 'r') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {self.json_path}: {e}")

        # Handle both array format and object format
        if isinstance(data, list):
            self._functions = data
        elif isinstance(data, dict):
            # If it's a dict with a 'functions' key
            self._functions = data.get('functions', [])
        else:
            raise ValueError(f"Unexpected format in {self.json_path}")

        return self._functions

    def get_functions(self) -> List[Dict[str, Any]]:
        """Get the parsed functions."""
        return self._functions


class ToolExecutor:
    """Executes llm-functions tools via subprocess."""

    def __init__(self, tool_def: Dict[str, Any], functions_dir: Path):
        self.tool_def = tool_def
        self.functions_dir = functions_dir
        self.config = get_config()

    def build_command(self, **kwargs) -> List[str]:
        """Build command line arguments from tool definition and kwargs."""
        tool_name = self.tool_def.get('name')

        # Look for the tool script in the functions directory
        # Try different extensions: .sh, .js, .py
        tool_script = None
        for ext in ['.sh', '.js', '.py', '']:
            candidate = self.functions_dir / 'tools' / f"{tool_name}{ext}"
            if candidate.exists():
                tool_script = candidate
                break

        if not tool_script:
            # Try looking in root of functions directory
            for ext in ['.sh', '.js', '.py', '']:
                candidate = self.functions_dir / f"{tool_name}{ext}"
                if candidate.exists():
                    tool_script = candidate
                    break

        if not tool_script or not tool_script.exists():
            raise FileNotFoundError(
                f"Tool script for '{tool_name}' not found in {self.functions_dir}"
            )

        # Build command based on parameters
        cmd = [str(tool_script)]

        # Process parameters from the tool definition
        parameters = self.tool_def.get('parameters', {})
        properties = parameters.get('properties', {})
        required = parameters.get('required', [])

        # Add arguments based on parameters
        for param_name, param_value in kwargs.items():
            if param_name not in properties:
                continue

            param_def = properties[param_name]

            # Convert parameter name to command-line format (e.g., "command" -> "--command")
            arg_name = f"--{param_name.replace('_', '-')}"

            # Handle different parameter types
            if param_def.get('type') == 'boolean':
                if param_value:
                    cmd.append(arg_name)
            else:
                cmd.extend([arg_name, str(param_value)])

        return cmd

    def execute(self, **kwargs) -> str:
        """Execute the tool with given arguments."""
        cmd = self.build_command(**kwargs)

        # Create temporary file for output (llm-functions uses LLM_OUTPUT)
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, suffix='.txt') as tmp_output:
            output_path = tmp_output.name

        try:
            # Set up environment
            env = {
                **subprocess.os.environ.copy(),
                'LLM_OUTPUT': output_path,
                'ROOT_DIR': str(self.functions_dir),
            }

            # Execute command
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.timeout,
                env=env,
                cwd=str(self.functions_dir),
            )

            # Read output from LLM_OUTPUT file
            try:
                with open(output_path, 'r') as f:
                    output = f.read()
            except FileNotFoundError:
                output = ""

            # Also include stdout if available
            if result.stdout:
                output = (output + "\n" + result.stdout).strip()

            # Check for errors
            if result.returncode != 0:
                error_msg = f"Tool '{self.tool_def.get('name')}' failed with exit code {result.returncode}"
                if result.stderr:
                    error_msg += f"\nStderr: {result.stderr}"
                raise RuntimeError(error_msg)

            # Check output size limit
            if len(output) > self.config.max_output_size:
                output = output[:self.config.max_output_size] + "\n\n[Output truncated]"

            return output

        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"Tool '{self.tool_def.get('name')}' timed out after {self.config.timeout} seconds"
            )
        finally:
            # Clean up temporary file
            try:
                Path(output_path).unlink()
            except:
                pass


class ToolWrapper:
    """Wraps an llm-functions tool as a Python callable for llm."""

    def __init__(self, tool_def: Dict[str, Any], functions_dir: Path):
        self.tool_def = tool_def
        self.functions_dir = functions_dir
        self.executor = ToolExecutor(tool_def, functions_dir)

        # Extract metadata
        self.name = tool_def.get('name', 'unknown')
        self.description = tool_def.get('description', '')
        self.parameters = tool_def.get('parameters', {})

    def create_callable(self) -> Callable:
        """Create a Python function that can be registered with llm."""
        tool_def = self.tool_def
        executor = self.executor

        # Build function signature dynamically
        parameters = tool_def.get('parameters', {})
        properties = parameters.get('properties', {})
        required = parameters.get('required', [])

        # Create the wrapper function
        def tool_function(**kwargs) -> str:
            """
            Dynamically created tool function.
            The actual docstring will be set from the tool definition.
            """
            # Validate required parameters
            for req_param in required:
                if req_param not in kwargs:
                    raise ValueError(f"Required parameter '{req_param}' missing")

            # Execute the tool
            return executor.execute(**kwargs)

        # Set function metadata
        tool_function.__name__ = tool_def.get('name', 'unknown_tool')

        # Build comprehensive docstring
        description = tool_def.get('description', 'No description available')
        docstring_parts = [description]

        if properties:
            docstring_parts.append("\n\nArgs:")
            for param_name, param_def in properties.items():
                param_desc = param_def.get('description', 'No description')
                param_type = param_def.get('type', 'string')
                required_marker = " (required)" if param_name in required else ""
                docstring_parts.append(
                    f"    {param_name} ({param_type}): {param_desc}{required_marker}"
                )

        tool_function.__doc__ = "\n".join(docstring_parts)

        return tool_function


@llm.hookimpl
def register_tools(register):
    """Register llm-functions tools with llm."""
    config = get_config()

    # Check if functions directory exists
    if not config.functions_directory.exists():
        # Silently skip if directory doesn't exist
        # This allows the plugin to be installed without llm-functions
        return

    # Check if functions.json exists
    if not config.functions_json_path.exists():
        # Silently skip if functions.json doesn't exist
        return

    try:
        # Parse functions.json
        parser = FunctionJsonParser(config.functions_json_path)
        functions = parser.parse()

        # Register each function as a tool
        for func_def in functions:
            tool_name = func_def.get('name')

            # Check if tool is allowed
            if not config.is_tool_allowed(tool_name):
                continue

            # Create wrapper
            wrapper = ToolWrapper(func_def, config.functions_directory)
            tool_callable = wrapper.create_callable()

            # Register with llm
            register(tool_callable)

    except Exception as e:
        # Log error but don't crash the plugin system
        # In production, we might want to use proper logging
        pass
