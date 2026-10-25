#!/usr/bin/env python3
"""
MCP Server for Agentic 3D CAD Generation, Mesh Validation, and Deterministic Rendering.
"""

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import matplotlib
matplotlib.use("Agg")  # Headless rendering without GUI window
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
import numpy as np
import trimesh
from fastmcp import FastMCP

mcp = FastMCP("cad-3d-builder")


def _analyze_stl(stl_path: Path, max_bed_x: float, max_bed_y: float, max_bed_z: float) -> dict[str, Any]:
    """Loads an STL mesh and computes geometric & 3D-printing validation metrics."""
    mesh = trimesh.load_mesh(stl_path, force="mesh")
    extents = mesh.extents  # [x, y, z] bounding box dimensions in mm
    bounds = mesh.bounds    # [[min_x, min_y, min_z], [max_x, max_y, max_z]]

    dim_x, dim_y, dim_z = float(extents[0]), float(extents[1]), float(extents[2])

    # Check if part fits flat on the bed (either standard or rotated 90 degrees on XY)
    fits_xy = (dim_x <= max_bed_x and dim_y <= max_bed_y) or (dim_y <= max_bed_x and dim_x <= max_bed_y)
    fits_bed = bool(fits_xy and (dim_z <= max_bed_z))

    return {
        "file_path": str(stl_path),
        "dimensions_mm": {
            "x": round(dim_x, 2),
            "y": round(dim_y, 2),
            "z": round(dim_z, 2),
        },
        "bounding_box_min": [round(float(v), 2) for v in bounds[0]],
        "bounding_box_max": [round(float(v), 2) for v in bounds[1]],
        "is_watertight": bool(mesh.is_watertight),
        "is_winding_consistent": bool(mesh.is_winding_consistent),
        "triangles_count": int(len(mesh.faces)),
        "vertices_count": int(len(mesh.vertices)),
        "volume_cm3": round(float(mesh.volume / 1000.0), 2) if mesh.is_watertight else None,
        "surface_area_cm2": round(float(mesh.area / 100.0), 2),
        "fits_print_bed": fits_bed,
        "bed_constraint_mm": [max_bed_x, max_bed_y, max_bed_z],
    }


@mcp.tool()
def compile_and_validate_cad(
    script_path: str,
    max_bed_x: float = 220.0,
    max_bed_y: float = 220.0,
    max_bed_z: float = 250.0,
) -> dict[str, Any]:
    """
    Executes a Python CAD script (build123d) in its own directory, discovers all
    generated .stl files, and returns a geometric validation report for each mesh.
    """
    path = Path(script_path).expanduser().resolve()
    if not path.exists():
        return {"status": "error", "message": f"Script not found: {path}"}

    workdir = path.parent

    try:
        proc = subprocess.run(
            [sys.executable, str(path)],
            cwd=str(workdir),
            capture_output=True,
            text=True,
            timeout=180,
        )
    except subprocess.TimeoutExpired:
        return {"status": "error", "message": "CAD script execution timed out after 180 seconds."}

    if proc.returncode != 0:
        return {
            "status": "error",
            "returncode": proc.returncode,
            "stdout": proc.stdout,
            "traceback": proc.stderr,
        }

    stl_files = sorted(workdir.glob("*.stl"))
    if not stl_files:
        return {
            "status": "warning",
            "message": "Script executed successfully, but no .stl files were found in the directory.",
            "stdout": proc.stdout,
        }

    reports = {}
    for stl_file in stl_files:
        try:
            reports[stl_file.name] = _analyze_stl(stl_file, max_bed_x, max_bed_y, max_bed_z)
        except Exception as exc:
            reports[stl_file.name] = {"error": str(exc)}

    return {
        "status": "success",
        "working_directory": str(workdir),
        "stdout": proc.stdout.strip(),
        "stl_reports": reports,
    }


@mcp.tool()
def inspect_stl_file(
    stl_path: str,
    max_bed_x: float = 220.0,
    max_bed_y: float = 220.0,
    max_bed_z: float = 250.0,
) -> dict[str, Any]:
    """
    Inspects an existing .stl file and returns bounding box dimensions, volume,
    triangle count, watertight status, and print bed compatibility.
    """
    path = Path(stl_path).expanduser().resolve()
    if not path.exists():
        return {"status": "error", "message": f"STL file not found: {path}"}

    try:
        return {"status": "success", "report": _analyze_stl(path, max_bed_x, max_bed_y, max_bed_z)}
    except Exception as exc:
        return {"status": "error", "message": str(exc)}


@mcp.tool()
def render_stl_multiview(
    stl_path: str,
    output_filename: str = "",
) -> dict[str, Any]:
    """
    Generates a deterministic 4-view technical blueprint PNG (Isometric, Top XY,
    Front XZ, Side YZ) with millimeter axes from an STL file.
    If 'f3d' is installed on the system, also generates a shaded ambient-occlusion render.
    """
    stl_file = Path(stl_path).expanduser().resolve()
    if not stl_file.exists():
        return {"status": "error", "message": f"STL file not found: {stl_file}"}

    base_name = output_filename if output_filename else f"{stl_file.stem}_multiview.png"
    out_multiview = stl_file.parent / base_name

    mesh = trimesh.load_mesh(stl_file, force="mesh")
    vertices = mesh.vertices
    faces = mesh.faces
    extents = mesh.extents

    # Compute uniform cubic bounding range so aspect ratios are preserved truthfully
    min_bounds, max_bounds = mesh.bounds
    mid = (min_bounds + max_bounds) / 2.0
    max_range = float((max_bounds - min_bounds).max()) / 2.0 * 1.12

    # Compute simple directional face shading so internal features & honeycomb holes pop out
    face_normals = mesh.face_normals
    light_dir = np.array([0.45, -0.65, 0.60])
    light_dir /= np.linalg.norm(light_dir)
    intensities = np.clip(np.dot(face_normals, light_dir), 0.25, 1.0)
    base_rgb = np.array([0.23, 0.51, 0.96])  # Engineering blue
    face_colors = np.column_stack([
        base_rgb[0] * intensities,
        base_rgb[1] * intensities,
        base_rgb[2] * intensities,
        np.full(len(faces), 0.92),
    ])

    fig = plt.figure(figsize=(13, 10), dpi=150, facecolor="#f8fafc")
    watertight_str = "YES" if mesh.is_watertight else "NO (NON-MANIFOLD)"
    fig.suptitle(
        f"STL Technical Sheet: {stl_file.name}\n"
        f"Dimensions: {extents[0]:.1f} (X) × {extents[1]:.1f} (Y) × {extents[2]:.1f} (Z) mm  |  "
        f"Watertight: {watertight_str}  |  Triangles: {len(faces)}",
        fontsize=12,
        fontweight="bold",
        color="#0f172a",
    )

    views = [
        ("Isometric View (+X, -Y, +Z)", 28, -50),
        ("Top View (XY Plane)", 90, -90),
        ("Front View (XZ Plane)", 0, -90),
        ("Right Side View (YZ Plane)", 0, 0),
    ]

    # Show subtle wireframe edges if triangle count is reasonable
    edge_color = "#1e293b" if len(faces) < 12000 else "none"
    line_width = 0.12 if len(faces) < 12000 else 0.0

    for idx, (title, elev, azim) in enumerate(views, 1):
        ax = fig.add_subplot(2, 2, idx, projection="3d", facecolor="#ffffff")
        poly = Poly3DCollection(
            vertices[faces],
            facecolors=face_colors,
            edgecolors=edge_color,
            linewidths=line_width,
        )
        ax.add_collection3d(poly)
        ax.set_xlim(mid[0] - max_range, mid[0] + max_range)
        ax.set_ylim(mid[1] - max_range, mid[1] + max_range)
        ax.set_zlim(mid[2] - max_range, mid[2] + max_range)
        ax.set_box_aspect([1, 1, 1])
        ax.view_init(elev=elev, azim=azim)
        ax.set_title(title, fontsize=10, fontweight="semibold", pad=8)
        ax.set_xlabel("X (mm)", fontsize=8)
        ax.set_ylabel("Y (mm)", fontsize=8)
        ax.set_zlabel("Z (mm)", fontsize=8)
        ax.tick_params(axis="both", which="major", labelsize=7)

    plt.tight_layout(rect=[0, 0, 1, 0.93])
    plt.savefig(out_multiview, bbox_inches="tight")
    plt.close(fig)

    result: dict[str, Any] = {
        "status": "success",
        "multiview_blueprint_png": str(out_multiview),
        "shaded_render_png": None,
    }

    # Optional high-quality shaded render if f3d is installed
    f3d_bin = shutil.which("f3d")
    if f3d_bin:
        out_shaded = stl_file.parent / f"{stl_file.stem}_shaded.png"
        f3d_cmd = [
            f3d_bin,
            str(stl_file),
            f"--output={out_shaded}",
            "--resolution=1600,1200",
            "--ambient-occlusion",
            "--anti-aliasing",
            "--axis",
            "--grid",
            "--color=0.25,0.55,0.95",
            "--bg-color=0.12,0.14,0.18",
        ]
        proc = subprocess.run(f3d_cmd, capture_output=True, text=True, timeout=30)
        if proc.returncode == 0 and out_shaded.exists():
            result["shaded_render_png"] = str(out_shaded)

    return result


@mcp.prompt()
def cad_3d_workflow() -> str:
    """
    Loads the complete 4-phase Parametric CAD & 3D Printing protocol (AGENTS.md)
    so the agent knows hardware constraints, tolerances, and verification steps
    even when running outside the repository folder.
    """
    agents_md = Path(__file__).resolve().parent.parent / "AGENTS.md"
    if agents_md.exists():
        return agents_md.read_text(encoding="utf-8")
    return (
        "Follow the 4-phase CAD workflow: "
        "1) Extract dimensions and check 220x220x250mm bed fit. "
        "2) Write parametric build123d script with 0.45mm sliding clearance and 0.20mm dovetail tolerance. "
        "3) Run compile_and_validate_cad and verify watertight==True. "
        "4) Run render_stl_multiview and visually inspect the PNG before finishing."
    )


def main() -> None:
    try:
        mcp.run(transport="stdio", show_banner=False)
    except TypeError:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()