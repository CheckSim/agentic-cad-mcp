# Agentic CAD MCP — Text & Sketch to 3D-Printable STL

An autonomous agentic workflow and local **Model Context Protocol (MCP)** server that turns natural language descriptions, reference photos, and hand-drawn dimensional sketches into watertight, 3D-printable `.stl` files using Python (`build123d` / OpenCascade).

Works out of the box with terminal-first AI coding agents and IDEs:
- **Claude Code** (`claude`)
- **Antigravity CLI** (`agy`)
- **OpenAI Codex CLI** (`codex`)
- **Cursor** & **Windsurf**

---

## Why Deterministic CAD + Mesh Rendering?

LLMs fail when asked to output raw `.stl` coordinates directly, and AI image generators hallucinate geometries that cannot be 3D printed. **Agentic CAD MCP** bridges the gap through a **4-Phase Closed-Loop Pipeline**:

1. **Vision-to-Spec Extraction:** The agent extracts explicit dimensions ($X, Y, Z$) from your sketch or prompt, checks derived math, and verifies fit against your 3D printer's build volume (default: `220 × 220 × 250 mm`).
2. **Parametric Code Generation (`build123d`):** The agent writes clean Python CAD scripts with real-world FDM tolerances (`0.45 mm` sliding clearance, `0.20 mm` press-fit dovetail joints, and automatic part splitting when a model exceeds the print bed).
3. **Automated Mesh Validation (MCP):** The MCP server executes the script, inspects every generated `.stl` with `trimesh`, and returns exact bounding-box dimensions, volume ($\text{cm}^3$), triangle count, bed compatibility, and watertight (manifold) status.
4. **Deterministic Visual Self-Correction (MCP):** Instead of hallucinating previews with an image model, the server renders a 4-view technical blueprint (`Isometric`, `Top XY`, `Front XZ`, `Side YZ`) directly from the compiled `.stl` mesh. The multimodal agent inspects its own render to catch misplaced holes or boolean errors before delivering the final files.

---

## Quick Installation (Zero-Clone)

Requires **Python 3.11 or 3.12**. You can install and register the MCP server across your favorite AI agents with a single command—no manual repository cloning or JSON editing required:

```bash
curl -fsSL [https://raw.githubusercontent.com/CheckSim/agentic-cad-mcp/main/install.py](https://raw.githubusercontent.com/CheckSim/agentic-cad-mcp/main/install.py) | python3 -
```

The interactive wizard will:
1. Create an isolated environment in `~/.agentic-cad-mcp/venv` and install the CAD engine (`build123d`, `trimesh`, `matplotlib`, `fastmcp`).
2. Let you choose which agents to configure (**Claude Code**, **Antigravity CLI**, **Codex CLI**, **Cursor**).
3. Non-destructively register the `cad-3d-builder` MCP server globally (or in your current project folder).

### Non-Interactive / Automated Install

For dotfiles or CI setups, pass `--clients` and `--scope` directly:

```bash
curl -fsSL [https://raw.githubusercontent.com/CheckSim/agentic-cad-mcp/main/install.py](https://raw.githubusercontent.com/CheckSim/agentic-cad-mcp/main/install.py) | python3 - --clients all --scope global
```

---

## Alternative Installation Methods

### Option A: Install via `pip`

```bash
pip install git+[https://github.com/CheckSim/agentic-cad-mcp.git](https://github.com/CheckSim/agentic-cad-mcp.git)

# Run the interactive setup wizard to register the MCP server with Claude, Agy, Codex, or Cursor
agentic-cad-mcp-setup
```

### Option B: Local Repository Clone (For Contributors)

```bash
git clone [https://github.com/CheckSim/agentic-cad-mcp.git](https://github.com/CheckSim/agentic-cad-mcp.git)
cd agentic-cad-mcp
python3 install.py
```

### Optional: Install `f3d` for Shaded Studio Renders

By default, the MCP server generates a 4-view orthographic & isometric technical blueprint using `matplotlib`. If [F3D](https://f3d.app/) is installed on your system, the server will also generate a shaded 3D studio render with ambient occlusion:

```bash
# macOS
brew install f3d

# Ubuntu / Debian
sudo apt install f3d

# Windows
winget install f3d-app.f3d
```

---

## Usage & Example Prompts

Once installed, launch your agent (`claude`, `agy`, or `codex`) in any folder and describe or attach your design:

### 1. From a Hand-Drawn Dimensional Sketch
> *"Look at `./sketch_dimensions.jpg`. Build an under-monitor organizer with two long front drawers, one side drawer on each wing, and honeycomb cutouts on the side walls and horizontal divider. My print bed is 220x220mm—split oversized parts in half using dovetail joints on the base and flat cuts on the vertical walls."*

### 2. From Natural Language Specifications
> *"Design a parametric VESA 100x100mm wall mount bracket with 4mm wall thickness, countersunk M4 holes, and a 15-degree downward tilt. Compile the STL, verify it is watertight, and generate the multiview render."*

---

## Exposed MCP Tools & Prompts

| Type | Name | Description |
| :--- | :--- | :--- |
| **Tool** | `compile_and_validate_cad` | Executes a `build123d` Python script and returns a JSON report for every generated `.stl` (exact $X/Y/Z$ bounding box in mm, watertight status, triangle count, volume in $\text{cm}^3$, and print-bed compatibility). |
| **Tool** | `render_stl_multiview` | Generates a deterministic 4-view technical blueprint PNG (`Isometric`, `Top XY`, `Front XZ`, `Side YZ`) with millimeter axes from a compiled `.stl` file, plus an optional shaded render via `f3d`. |
| **Tool** | `inspect_stl_file` | Inspects any existing `.stl` file without recompiling, returning geometric metadata and sliceability checks. |
| **Prompt** | `cad_3d_workflow` | Injects the 4-phase FDM engineering protocol and tolerance guidelines (`AGENTS.md`) into the agent's context even when running outside the repository folder. |

---

## Repository Structure

```text
agentic-cad-mcp/
├── AGENTS.md                  # Universal 4-phase CAD engineering protocol
├── CLAUDE.md                  # Claude Code entry point
├── install.py                 # Zero-dependency cross-platform setup wizard
├── pyproject.toml             # Python packaging & CLI entrypoints
├── mcp_cad_server/
│   ├── __init__.py
│   ├── AGENTS.md              # Packaged protocol for global installations
│   ├── requirements.txt       # Python dependencies
│   └── server.py              # FastMCP server implementation
└── projects/                  # Default workspace for local builds
```

---

## License

Released under the [MIT License](LICENSE.md).