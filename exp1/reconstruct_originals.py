"""
Batch-reconstruct original solids from source SeekCAD JSONs.
Output: exp1/steps/<id>_original.step

Run in cad-tree env from project root:
  python exp1/reconstruct_originals.py
"""
from __future__ import annotations
import io, json, os, sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

HERE   = os.path.dirname(os.path.abspath(__file__))
JSONS  = os.path.join(HERE, "jsons")
STEPS  = os.path.join(HERE, "steps")

from visualize.sequence import CADSequence
from visualize.utils import occ_utils
from OCC.Core.BRepCheck import BRepCheck_Analyzer
from OCC.Core.GProp     import GProp_GProps
from OCC.Core.BRepGProp import brepgprop
from OCC.Core.STEPControl import STEPControl_Writer, STEPControl_AsIs
from OCC.Core.IFSelect   import IFSelect_RetDone
from OCC.Core.Interface  import Interface_Static

DROP_TYPES = {"fillet", "chamfer", "shell"}


def solid_volume(shape):
    if shape is None:
        return 0.0
    try:
        p = GProp_GProps()
        brepgprop.VolumeProperties(shape, p)
        return abs(p.Mass())
    except Exception:
        return 0.0


def is_valid(shape):
    if shape is None:
        return False
    try:
        return BRepCheck_Analyzer(shape).IsValid()
    except Exception:
        return False


def export_step(shape, path):
    try:
        Interface_Static.SetCVal("write.step.unit", "MM")
        w = STEPControl_Writer()
        w.Transfer(shape, STEPControl_AsIs)
        return w.Write(path) == IFSelect_RetDone
    except Exception as e:
        print(f"    [!] STEP export failed: {e}")
        return False


def reconstruct_one(json_path, out_path):
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)

    # Drop empty modifying features (no resolved entity refs → OCC rejects)
    dropped = [k for k, v in data["features"].items()
               if v.get("type") in DROP_TYPES and not v.get("entities")]
    if dropped:
        data["features"] = {k: v for k, v in data["features"].items()
                            if k not in dropped}
        data["sequence"] = [s for s in data["sequence"]
                            if s.get("feature_id") not in dropped]

    cad_seq = CADSequence.from_dict(data, _clean_shape=True,
                                    validate=True, strict=False, debug=False)
    shape = cad_seq.create_CAD()
    ok    = export_step(shape, out_path)
    return shape, ok


def main():
    os.makedirs(STEPS, exist_ok=True)
    json_files = sorted(f for f in os.listdir(JSONS) if f.endswith(".json"))

    results = []
    for fname in json_files:
        mid      = fname[:-5]
        src      = os.path.join(JSONS, fname)
        out_path = os.path.join(STEPS, f"{mid}_original.step")

        print(f"\n{'='*60}")
        print(f"  Model: {mid}")
        try:
            shape, step_ok = reconstruct_one(src, out_path)
            valid = is_valid(shape)
            vol   = solid_volume(shape)
            print(f"  STEP: {'OK' if step_ok else 'FAILED'}  valid={valid}  volume={vol:.6g}")
            results.append({"id": mid, "valid": valid, "vol": vol, "step_ok": step_ok})
        except Exception as e:
            print(f"  FAILED: {e}")
            results.append({"id": mid, "error": str(e)})

    print(f"\n\n{'='*60}")
    print("  SUMMARY")
    print(f"{'='*60}")
    ok  = sum(1 for r in results if r.get("valid"))
    stp = sum(1 for r in results if r.get("step_ok"))
    print(f"  {ok}/{len(results)} valid  |  {stp}/{len(results)} STEP written")
    for r in results:
        if "error" in r:
            print(f"  {r['id']}  FAILED: {r['error']}")
        else:
            flag = "✓" if r["valid"] else "✗"
            print(f"  {r['id']}  valid={flag}  vol={r['vol']:.5g}")


if __name__ == "__main__":
    main()
