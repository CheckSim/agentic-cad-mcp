# Claude Code Instructions

@AGENTS.md

## Claude Code Specific Notes
- Always use the `cad-3d-builder` MCP tools (`compile_and_validate_cad`, `render_stl_multiview`, `inspect_stl_file`) rather-than running ad-hoc shell scripts when compiling or inspecting `.stl` files.
- After calling `render_stl_multiview`, always use your `Read` tool on the returned `.png` file path to visually verify the geometry before concluding your turn.