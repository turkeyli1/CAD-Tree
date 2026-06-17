"""
reconstruct_from_tree_json.py
=============================
Load a trees/*.json file (exported by export_lca_trees.py) and reconstruct
the OCC solid, exporting a STEP file.

This is the full generation-time decode path:
  trees/*.json  →  FeatureNode objects  →  OCC shape  →  STEP

Unlike lca_tree_test.py (which works from the original Onshape JSON and uses
exact sketch data), this script works entirely from the serialised tree JSON —
no access to the original json_files/ directory needed.

Structural entity refs (source_node_idx / profile_idx / loop_idx / curve_idx)
are resolved by looking up the source node's sketch_data in the loaded nodes.

Run in cad-tree env:
  python reconstruct_from_tree_json.py                      # all files in trees/
  python reconstruct_from_tree_json.py --file 00000003      # single model
  python reconstruct_from_tree_json.py --out_dir my_steps   # custom output dir
"""
from __future__ import annotations
import argparse, io, json, math, os, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)

import numpy as np  # noqa: E402 (after sys.path setup)
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from occ_builder import (
    _raw_extrude, _raw_revolve, _boolean,
    _apply_fillet, _apply_chamfer, _apply_shell,
)
from OCC.Core.BRepCheck import BRepCheck_Analyzer
from OCC.Core.GProp    import GProp_GProps
from OCC.Core.BRepGProp import brepgprop
from OCC.Core.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCC.Core.IFSelect  import IFSelect_RetDone
from OCC.Core.Interface import Interface_Static
from OCC.Core.TopoDS    import TopoDS_Shape


# ─────────────────────────────────────────────────────────────────────────────
# Minimal FeatureNode-like object for reconstruction
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class TreeNode:
    id:           str
    name:         str
    feature_type: str
    params:       Dict[str, Any]   = field(default_factory=dict)
    entities:     List[Dict]       = field(default_factory=list)
    sketch_data:  Optional[Dict]   = None
    parent_sketch: Optional[Dict]  = None
    parent_op_type: str            = ""
    parent_op_params: Dict[str, Any] = field(default_factory=dict)
    inputs:       List[str]        = field(default_factory=list)
    input_labels: Dict[str, str]   = field(default_factory=dict)


# ─────────────────────────────────────────────────────────────────────────────
# Load tree JSON → list of TreeNode in sequence order
# ─────────────────────────────────────────────────────────────────────────────

def load_tree_json(json_path: str) -> Tuple[List[TreeNode], Dict[str, TreeNode]]:
    """
    Load a trees/*.json file.
    Handles both old format (Onshape string IDs) and new format (integer keys).
    Returns (seq_nodes, node_map) where node_map is keyed by the node key string.
    """
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    nodes_dict = data.get("nodes", {})
    seq_order  = data.get("sequence_order", list(nodes_dict.keys()))

    node_map: Dict[str, TreeNode] = {}
    for key, nd in nodes_dict.items():
        node_map[key] = TreeNode(
            id            = key,
            name          = nd.get("name", key),
            feature_type  = nd.get("feature_type", ""),
            params        = nd.get("params", {}),
            entities      = nd.get("entities", []),
            sketch_data   = nd.get("sketch_data"),
            parent_sketch = {"plane": nd["parent_sketch_plane"]}
                            if nd.get("parent_sketch_plane") else None,
            parent_op_type   = nd.get("parent_op_type", ""),
            parent_op_params = nd.get("parent_op_params", {}),
            inputs        = nd.get("inputs", []),
            input_labels  = nd.get("input_labels", {}),
        )

    # sequence_order may contain integers (new format) or strings (old)
    seq_nodes = [node_map[str(k)] for k in seq_order if str(k) in node_map]
    return seq_nodes, node_map


# ─────────────────────────────────────────────────────────────────────────────
# Reconstruct OCC shape from loaded tree nodes
# ─────────────────────────────────────────────────────────────────────────────

def build_from_tree_json(
    seq_nodes: List[TreeNode],
) -> Tuple[Optional[TopoDS_Shape], Dict[str, str]]:
    """
    Replay the feature sequence and return (shape, feat_info).

    Edge lookup uses brep_edge_centroid (geometric, sequence-order independent).
    src_sketches is keyed by node key (int(node.id)), not enumerate position.
    """
    # Build src_sketches: map node key → sketch_data.
    # Keyed by node.id (integer string cast to int, e.g. "3" → 3), NOT by
    # enumerate position, so source_node_idx in struct refs stays correct
    # regardless of which sequence_order was used to load seq_nodes.
    src_sketches: Dict[int, Dict] = {}
    for node in seq_nodes:
        if node.sketch_data:
            try:
                src_sketches[int(node.id)] = node.sketch_data
            except (ValueError, TypeError):
                pass  # old-format string IDs — best effort

    current: Optional[TopoDS_Shape] = None
    feat_info: Dict[str, str] = {}

    for node in seq_nodes:
        ft  = node.feature_type
        fid = node.id

        if ft in ("extrude", "revolve"):
            if not node.sketch_data:
                feat_info[fid] = "no_sketch"
                continue
            try:
                raw = (_raw_extrude(node) if ft == "extrude"
                       else _raw_revolve(node))
            except Exception as exc:
                print(f"    [!] {node.name} raw build failed: {exc}")
                raw = None

            op_type = node.params.get("operationType", "NEW")
            feat_info[fid] = op_type

            if raw is not None:
                current = _boolean(current, raw, op_type)

        elif ft == "fillet" and current is not None:
            feat_info[fid] = "fillet"
            try:
                current = _apply_fillet(node, current, src_sketches)
            except Exception as exc:
                print(f"    [!] fillet {node.name}: {exc}")

        elif ft == "chamfer" and current is not None:
            feat_info[fid] = "chamfer"
            try:
                current = _apply_chamfer(node, current, src_sketches)
            except Exception as exc:
                print(f"    [!] chamfer {node.name}: {exc}")

        elif ft == "shell" and current is not None:
            feat_info[fid] = "shell"
            try:
                current = _apply_shell(node, current, src_sketches)
            except Exception as exc:
                print(f"    [!] shell {node.name}: {exc}")

    return current, feat_info


# ─────────────────────────────────────────────────────────────────────────────
# OCC helpers
# ─────────────────────────────────────────────────────────────────────────────

def solid_volume(shape: Optional[TopoDS_Shape]) -> float:
    if shape is None:
        return 0.0
    try:
        props = GProp_GProps()
        brepgprop.VolumeProperties(shape, props)
        return abs(props.Mass())
    except Exception:
        return 0.0


def is_valid(shape: Optional[TopoDS_Shape]) -> bool:
    if shape is None:
        return False
    try:
        return BRepCheck_Analyzer(shape).IsValid()
    except Exception:
        return False


def export_step(shape: TopoDS_Shape, path: str) -> bool:
    if shape is None:
        return False
    try:
        Interface_Static.SetCVal("write.step.unit", "MM")
        writer = STEPControl_Writer()
        writer.Transfer(shape, STEPControl_AsIs)
        return writer.Write(path) == IFSelect_RetDone
    except Exception as exc:
        print(f"    [!] STEP export failed: {exc}")
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Per-file reconstruction
# ─────────────────────────────────────────────────────────────────────────────

def reconstruct_file(tree_json_path: str, out_dir: str) -> dict:
    model_id = os.path.splitext(os.path.basename(tree_json_path))[0]
    model_id = model_id.replace("_tree", "")
    sep = "=" * 68

    print(f"\n{sep}")
    print(f"  Model: {model_id}")
    print(sep)

    try:
        seq_nodes, _ = load_tree_json(tree_json_path)
    except Exception as exc:
        print(f"  [FATAL] load failed: {exc}")
        return {"model_id": model_id, "error": str(exc)}

    print(f"  {len(seq_nodes)} nodes in sequence order")
    shape, feat_info = build_from_tree_json(seq_nodes)

    valid = is_valid(shape)
    vol   = solid_volume(shape)

    step_path = os.path.join(out_dir, f"{model_id}_from_tree.step")
    ok = export_step(shape, step_path)
    print(f"  STEP: {'OK' if ok else 'FAILED'}  valid={valid}  volume={vol:.6g} m³")
    print(f"  → {step_path}")

    return {"model_id": model_id, "valid": valid, "volume": vol, "step_ok": ok}


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main():
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(
        description="Reconstruct OCC solids from exported LCA tree JSON files"
    )
    p.add_argument("--trees_dir", default=os.path.join(ROOT, "trees"))
    p.add_argument("--out_dir",   default=os.path.join(ROOT, "tree_steps"))
    p.add_argument("--file",      default=None, help="Model ID, e.g. 00000003")
    args = p.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)

    if args.file:
        tree_files = [os.path.join(args.trees_dir, f"{args.file}_tree.json")]
    else:
        tree_files = sorted(
            os.path.join(args.trees_dir, f)
            for f in os.listdir(args.trees_dir)
            if f.endswith("_tree.json")
        )

    results = []
    for tf in tree_files:
        if not os.path.exists(tf):
            print(f"  [skip] not found: {tf}")
            continue
        r = reconstruct_file(tf, args.out_dir)
        results.append(r)

    sep = "=" * 68
    print(f"\n\n{sep}")
    print("  SUMMARY")
    print(sep)
    ok_count  = sum(1 for r in results if r.get("valid"))
    step_ok   = sum(1 for r in results if r.get("step_ok"))
    print(f"  {ok_count}/{len(results)} valid shapes  |  {step_ok}/{len(results)} STEP files written")
    for r in results:
        if "error" in r:
            print(f"  {r['model_id']:<16} FAILED: {r['error']}")
        else:
            print(f"  {r['model_id']:<16} valid={'✓' if r['valid'] else '✗'}  "
                  f"vol={r['volume']:.5g}")
    print(f"\n  STEP files written to: {args.out_dir}\n")


if __name__ == "__main__":
    main()
