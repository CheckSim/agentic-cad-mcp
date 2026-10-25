#!/usr/bin/env python3
"""
Standalone Zero-Clone Installer for Agentic CAD MCP.
Works via:
  1) curl -fsSL https://raw.githubusercontent.com/CheckSim/agentic-cad-mcp/main/install.py | python3 -
  2) python3 install.py (inside a cloned repo)
  3) agentic-cad-mcp-setup (after pip install)
"""

import argparse
import json
import platform
import re
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

GITHUB_USER = "CheckSim"
GITHUB_REPO = "agentic-cad-mcp"
GITHUB_BRANCH = "main"
GIT_PIP_URL = f"git+https://github.com/{GITHUB_USER}/{GITHUB_REPO}.git@{GITHUB_BRANCH}"
RAW_BASE_URL = f"https://raw.githubusercontent.com/{GITHUB_USER}/{GITHUB_REPO}/{GITHUB_BRANCH}"

SERVER_NAME = "cad-3d-builder"
APP_HOME = Path.home() / ".agentic-cad-mcp"


def print_step(msg: str) -> None:
    print(f"\n\033[1;34m==>\033[0m \033[1m{msg}\033[0m")


def print_ok(msg: str) -> None:
    print(f"  \033[1;32m✔\033[0m {msg}")


def print_warn(msg: str) -> None:
    print(f"  \033[1;33m!\033[0m {msg}")


def tty_input(prompt: str, default: str = "") -> str:
    """Reads interactive user input even when script is piped via 'curl | python3 -'."""
    try:
        if sys.stdin.isatty():
            val = input(prompt).strip()
            return val or default
        # Open /dev/tty on macOS/Linux or CONIN$ on Windows when piped
        tty_path = "CONIN$" if platform.system() == "Windows" else "/dev/tty"
        with open(tty_path, "r", encoding="utf-8") as tty:
            sys.stdout.write(prompt)
            sys.stdout.flush()
            val = tty.readline().strip()
            return val or default
    except Exception:
        return default


def is_local_repo() -> bool:
    """Checks if the script is running from a local git clone."""
    try:
        here = Path(__file__).resolve().parent
        return (here / "mcp_cad_server" / "server.py").exists()
    except NameError:
        # Running via stdin (curl | python3 -)
        return False


def get_venv_paths(venv_dir: Path) -> tuple[Path, Path]:
    if platform.system() == "Windows":
        return venv_dir / "Scripts" / "python.exe", venv_dir / "Scripts" / "agentic-cad-mcp.exe"
    return venv_dir / "bin" / "python", venv_dir / "bin" / "agentic-cad-mcp"


def setup_environment(skip_deps: bool = False) -> tuple[Path, list[str]]:
    """
    Sets up the virtual environment (in ~/.agentic-cad-mcp/venv for zero-clone,
    or ./.venv for local clone) and installs the package via pip.
    Returns (command_path, args_list) for the MCP config.
    """
    local_mode = is_local_repo()
    venv_dir = (Path(__file__).resolve().parent / ".venv") if local_mode else (APP_HOME / "venv")
    py_bin, cli_bin = get_venv_paths(venv_dir)

    if not py_bin.exists():
        print_step(f"Creating isolated environment in {venv_dir}...")
        venv_dir.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run([sys.executable, "-m", "venv", str(venv_dir)], check=True)
        print_ok("Isolated virtual environment created.")
    else:
        print_step(f"Using existing environment at {venv_dir}")

    if not skip_deps:
        print_step("Installing agentic-cad-mcp & CAD engine (build123d, trimesh, matplotlib)...")
        subprocess.run([str(py_bin), "-m", "pip", "install", "--upgrade", "pip", "-q"], check=True)

        if local_mode:
            repo_root = Path(__file__).resolve().parent
            subprocess.run([str(py_bin), "-m", "pip", "install", "-e", str(repo_root)], check=True)
        else:
            subprocess.run([str(py_bin), "-m", "pip", "install", "--upgrade", GIT_PIP_URL], check=True)

        print_ok("Package 'agentic-cad-mcp' installed successfully.")

    # Prefer the installed console_script entrypoint if present
    if cli_bin.exists():
        return cli_bin, []
    # Fallback to running python -m mcp_cad_server.server
    return py_bin, ["-u", "-m", "mcp_cad_server.server"]


def build_mcp_entry(cmd_path: Path, args: list[str]) -> dict:
    return {
        "command": str(cmd_path),
        "args": args,
        "env": {
            "PYTHONUNBUFFERED": "1",
            "MPLBACKEND": "Agg",
            "FASTMCP_SHOW_CLI_BANNER": "false",
        },
    }


def merge_json_config(config_path: Path, cmd_path: Path, args: list[str]) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    data = {}
    if config_path.exists():
        try:
            content = config_path.read_text(encoding="utf-8").strip()
            if content:
                data = json.loads(content)
        except json.JSONDecodeError:
            backup = config_path.with_suffix(".json.bak")
            shutil.copy2(config_path, backup)
            print_warn(f"Backed up malformed JSON to {backup}")

    if "mcpServers" not in data or not isinstance(data["mcpServers"], dict):
        data["mcpServers"] = {}

    data["mcpServers"][SERVER_NAME] = build_mcp_entry(cmd_path, args)
    config_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print_ok(f"Configured: {config_path}")


def merge_codex_toml_config(toml_path: Path, cmd_path: Path, args: list[str]) -> None:
    toml_path.parent.mkdir(parents=True, exist_ok=True)
    existing = toml_path.read_text(encoding="utf-8") if toml_path.exists() else ""

    cmd_str = str(cmd_path).replace("\\", "\\\\")
    args_serialized = ", ".join(f'"{a.replace(chr(92), chr(92)*2)}"' for a in args)

    toml_block = (
        f"[mcp_servers.{SERVER_NAME}]\n"
        f'command = "{cmd_str}"\n'
        f"args = [{args_serialized}]\n"
        f'env = {{ PYTHONUNBUFFERED = "1", MPLBACKEND = "Agg", FASTMCP_SHOW_CLI_BANNER = "false" }}\n'
    )

    pattern = re.compile(rf"\[mcp_servers\.{re.escape(SERVER_NAME)}\].*?(?=\n\[|\Z)", re.DOTALL)
    if pattern.search(existing):
        updated = pattern.sub(toml_block.strip(), existing)
    else:
        sep = "\n\n" if existing and not existing.endswith("\n\n") else ""
        updated = existing + sep + toml_block

    toml_path.write_text(updated.strip() + "\n", encoding="utf-8")
    print_ok(f"Configured: {toml_path}")


def download_agent_docs(target_dir: Path) -> None:
    """Downloads AGENTS.md and CLAUDE.md into the current working directory if requested."""
    for fname in ["AGENTS.md", "CLAUDE.md"]:
        dest = target_dir / fname
        if not dest.exists():
            try:
                url = f"{RAW_BASE_URL}/{fname}"
                urllib.request.urlretrieve(url, dest)
                print_ok(f"Downloaded {fname} into {target_dir}")
            except Exception as exc:
                print_warn(f"Could not download {fname}: {exc}")


def configure_clients(clients: list[str], scope: str, cmd_path: Path, args: list[str]) -> None:
    home = Path.home()
    cwd = Path.cwd()
    scopes = ["project", "global"] if scope == "both" else [scope]

    print_step(f"Registering MCP server '{SERVER_NAME}' for: {', '.join(clients)} (scope: {scope})")

    for sc in scopes:
        if "claude" in clients:
            if sc == "project":
                merge_json_config(cwd / ".mcp.json", cmd_path, args)
            elif sc == "global":
                claude_bin = shutil.which("claude")
                if claude_bin:
                    subprocess.run([claude_bin, "mcp", "remove", SERVER_NAME, "-s", "user"], capture_output=True)
                    cmd = [
                        claude_bin, "mcp", "add", "-s", "user", SERVER_NAME,
                        "-e", "PYTHONUNBUFFERED=1",
                        "-e", "MPLBACKEND=Agg",
                        "-e", "FASTMCP_SHOW_CLI_BANNER=false",
                        "--", str(cmd_path), *args,
                    ]
                    if subprocess.run(cmd, capture_output=True).returncode == 0:
                        print_ok("Registered globally in Claude Code (user scope)")
                    else:
                        merge_json_config(home / ".claude.json", cmd_path, args)
                else:
                    merge_json_config(home / ".claude.json", cmd_path, args)

        if "agy" in clients:
            if sc == "project":
                merge_json_config(cwd / ".agents" / "mcp_config.json", cmd_path, args)
            elif sc == "global":
                merge_json_config(home / ".gemini" / "antigravity" / "mcp_config.json", cmd_path, args)

        if "codex" in clients:
            if sc == "project":
                merge_codex_toml_config(cwd / ".codex" / "config.toml", cmd_path, args)
            elif sc == "global":
                merge_codex_toml_config(home / ".codex" / "config.toml", cmd_path, args)

        if "cursor" in clients:
            target = (cwd / ".cursor" / "mcp.json") if sc == "project" else (home / ".cursor" / "mcp.json")
            merge_json_config(target, cmd_path, args)

        if sc == "project" and not is_local_repo():
            download_agent_docs(cwd)


def interactive_wizard() -> tuple[list[str], str]:
    print("\n\033[1;36m╭──────────────────────────────────────────────────────────╮")
    print("│       Agentic CAD MCP — Zero-Clone Setup Wizard          │")
    print("╰──────────────────────────────────────────────────────────╯\033[0m")
    print("\nWhich AI coding agents do you want to configure?")
    print("  [1] All (Claude Code, Antigravity CLI, Codex, Cursor) [Default]")
    print("  [2] Claude Code only")
    print("  [3] Antigravity CLI (agy) only")
    print("  [4] OpenAI Codex CLI only")
    print("  [5] Cursor only")

    choice = tty_input("\nSelect option [1-5] (Enter for 1): ", default="1")
    mapping = {
        "1": ["claude", "agy", "codex", "cursor"],
        "2": ["claude"],
        "3": ["agy"],
        "4": ["codex"],
        "5": ["cursor"],
    }
    clients = mapping.get(choice, ["claude", "agy", "codex", "cursor"])

    print("\nWhere should the MCP server be registered?")
    print("  [1] Global (available everywhere on your machine) [Default]")
    print("  [2] Current Folder only (creates local config + downloads AGENTS.md)")
    print("  [3] Both Global and Current Folder")

    sc_choice = tty_input("\nSelect scope [1-3] (Enter for 1): ", default="1")
    scope_map = {"1": "global", "2": "project", "3": "both"}
    return clients, scope_map.get(sc_choice, "global")


def main() -> None:
    parser = argparse.ArgumentParser(description="Zero-Clone Installer for Agentic CAD MCP.")
    parser.add_argument("--clients", nargs="+", choices=["claude", "agy", "codex", "cursor", "all"])
    parser.add_argument("--scope", choices=["project", "global", "both"], default="global")
    parser.add_argument("--skip-deps", action="store_true")
    parsed = parser.parse_args()

    if parsed.clients:
        clients = ["claude", "agy", "codex", "cursor"] if "all" in parsed.clients else parsed.clients
        scope = parsed.scope
    else:
        clients, scope = interactive_wizard()

    cmd_path, cmd_args = setup_environment(skip_deps=parsed.skip_deps)
    configure_clients(clients, scope, cmd_path, cmd_args)

    print("\n\033[1;32m✨ Installation Complete!\033[0m")
    print("Open `claude`, `agy`, or `codex` in any folder and start designing 3D STL parts.\n")


if __name__ == "__main__":
    main()