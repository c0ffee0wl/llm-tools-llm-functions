# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an LLM plugin that integrates [llm-functions](https://github.com/sigoden/llm-functions) tools with Simon Willison's [llm](https://llm.datasette.io/) CLI. The plugin automatically discovers and registers llm-functions tools (Bash, JavaScript, Python scripts) as native llm tools for function calling.

## Development Commands

### Setup
```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install in editable mode with test dependencies
python -m pip install -e '.[test]'
```

### Testing
```bash
# Run all tests
python -m pytest

# Run tests with coverage
python -m pytest --cov=. --cov-report=html

# Run specific test file
python -m pytest tests/test_tools_llm_functions.py

# Run specific test
python -m pytest tests/test_tools_llm_functions.py::test_plugin_is_installed
```

### Installation for Local Testing
```bash
# Install plugin for use with llm CLI
llm install -e /path/to/llm-tools-llm-functions

# Verify installation
llm plugins
llm tools list
```

## Architecture

The plugin consists of four main components in two files:

### Core Components (llm_tools_llm_functions.py)

1. **FunctionJsonParser**: Parses llm-functions' `functions.json` to extract tool definitions. Handles both array format and object format with a 'functions' key.

2. **ToolExecutor**: Executes tool scripts via subprocess. Sets up the execution environment with:
   - `LLM_OUTPUT`: temporary file for tool output
   - `ROOT_DIR`: functions directory path
   - Handles parameter mapping from JSON Schema to command-line arguments
   - Enforces timeout and output size limits

3. **ToolWrapper**: Wraps llm-functions tool definitions as Python callables compatible with llm's tool system. Dynamically generates function signatures and validates required parameters at runtime.

4. **register_tools()**: LLM plugin hook that discovers tools from functions.json, filters them based on security configuration (allowlist/denylist), and registers them with llm.

### Configuration (config.py)

**Config**: Manages configuration with precedence: environment variables > YAML config file > defaults.

Environment variable precedence:
- `LLM_FUNCTIONS_DIR` (highest priority, plugin-specific)
- `AICHAT_FUNCTIONS_DIR` (standard llm-functions variable)
- YAML config file at `~/.config/io.datasette.llm/llm-functions.yaml`
- Default: `~/llm-functions`

## Key Design Patterns

### Tool Discovery Flow
1. Check if functions directory exists (silent skip if not)
2. Parse `functions.json` for tool definitions
3. Filter tools based on allowlist/denylist
4. Wrap each tool as Python callable
5. Register with llm via plugin hook

### Parameter Mapping
JSON Schema parameters are converted to command-line arguments:
- Property `command` → `--command value`
- Boolean `verbose` → `--verbose` (if true)
- Underscores in names converted to hyphens

### Tool Script Resolution
Searches for tool scripts in order:
1. `{functions_dir}/tools/{tool_name}.sh`
2. `{functions_dir}/tools/{tool_name}.js`
3. `{functions_dir}/tools/{tool_name}.py`
4. `{functions_dir}/tools/{tool_name}` (no extension)
5. Falls back to root of functions_dir

## Testing Strategy

Tests use pytest with temporary directories and mocking:
- `tmp_path` fixtures for creating isolated test environments
- `monkeypatch` for environment variable testing
- `unittest.mock.patch` for subprocess operations
- Integration tests validate the full flow from JSON parsing to tool execution

Test organization:
- Unit tests for each component (Parser, Executor, Wrapper, Config)
- Integration tests for end-to-end workflows
- Security tests for allowlist/denylist functionality

## Security Considerations

This plugin executes external scripts that can run arbitrary code. Security features:
- **Tool allowlist**: Explicitly allow only trusted tools
- **Tool denylist**: Block dangerous tools (denylist takes precedence)
- **Execution limits**: Configurable timeout and output size limits
- **Silent failures**: Plugin won't crash llm if functions.json is missing

When testing or implementing security features, denylist ALWAYS takes precedence over allowlist (see tests/test_tools_llm_functions.py::TestConfig::test_allowlist_and_denylist).

## CI/CD

- **test.yml**: Runs pytest on Python 3.10-3.14 for all pushes and PRs
- **publish.yml**: Builds and publishes to PyPI on release creation (uses trusted publishing)

## Dependencies

- `llm`: Simon Willison's LLM CLI tool (plugin host)
- `pyyaml`: For YAML configuration file parsing
- `pytest`: Test framework (test dependency only)
