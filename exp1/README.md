# Experiment 1 — Tree Structure Soundness Validation

Validates the v2 LCA dependency-tree representation on 30 SeekCAD models by running the full round-trip:

```
SeekCAD JSON  →  LCA tree JSON  →  OCC solid  →  STEP file
```

## Directory layout

```
exp1/
├── trees/    30 LCA tree JSON files  (one per model)
├── steps/    30 reconstructed STEP files
├── jsons/    30 source SeekCAD JSONs  (local only, not tracked in git)
└── README.md
```

## Results (30 models)

| Metric | Count |
|--------|-------|
| STEP files written | 30 / 30 |
| Valid solids (BRepCheck) | 21 / 30 |

Invalid solids are mostly multi-body NEW+ADD mixes or degenerate boolean
results — known OCC limitation documented in `project-v2-verify-findings`
memory entry.

## Reproducing

Requires the `cad-tree` conda env (pythonocc-core).

**Step 1 — JSON → LCA tree JSON** (run from project root):
```powershell
$e = "F:\Miniconda\envs\cad-tree"
$env:PATH = "$e;$e\Library\bin;$e\Library\mingw-w64\bin;$e\Scripts;" + $env:PATH
$env:PYTHONIOENCODING = "utf-8"
& "$e\python.exe" export_lca_trees.py --json_dir exp1\jsons --out_dir exp1\trees
```

**Step 2 — LCA tree JSON → STEP** (run from project root):
```powershell
& "$e\python.exe" reconstruct_from_tree_json.py --trees_dir exp1\trees --out_dir exp1\steps
```

## v2 LCA tree rule (brief)

Every non-sketch feature is assigned a category A/I/C/M and a greedy depth:

- **A** = boolean add (extrude/revolve NEW or ADD)
- **I** = boolean intersect
- **C** = boolean cut (REMOVE)
- **M** = modifying (fillet / chamfer / shell)

Decode order within each depth: A → I → C → M.  
Edges exist only between geometrically-dependent feature pairs (dependence-gated,
2026-06-02 fix).  Independent features share a layer and may be applied in any order.

See `tree_rule_lib.py` and `lca_tree_proof.tex` for the full specification.
