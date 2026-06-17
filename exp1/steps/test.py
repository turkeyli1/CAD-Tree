from OCC.Core.STEPControl import STEPControl_Reader
from OCC.Core.TopAbs import TopAbs_SOLID, TopAbs_SHELL, TopAbs_FACE
from OCC.Core.TopExp import TopExp_Explorer
from OCC.Core.BRepCheck import BRepCheck_Analyzer

reader = STEPControl_Reader()
reader.ReadFile("00000001_from_tree.step")
reader.TransferRoots()
shape = reader.OneShape()

# 检查是否有 solid
exp = TopExp_Explorer(shape, TopAbs_SOLID)
solid_count = 0
while exp.More():
    solid_count += 1
    exp.Next()
print(f"Solid 数量: {solid_count}")

# 检查 BRep 合法性
analyzer = BRepCheck_Analyzer(shape)
print(f"BRep 合法: {analyzer.IsValid()}")
from OCC.Core.Bnd import Bnd_Box
from OCC.Core.BRepBndLib import brepbndlib

bbox = Bnd_Box()
brepbndlib.Add(shape, bbox)
xmin, ymin, zmin, xmax, ymax, zmax = bbox.Get()

print(f"X: {xmin:.4f} ~ {xmax:.4f},  尺寸: {xmax-xmin:.4f}")
print(f"Y: {ymin:.4f} ~ {ymax:.4f},  尺寸: {ymax-ymin:.4f}")
print(f"Z: {zmin:.4f} ~ {zmax:.4f},  尺寸: {zmax-zmin:.4f}")
print(f"中心: ({(xmin+xmax)/2:.4f}, {(ymin+ymax)/2:.4f}, {(zmin+zmax)/2:.4f})")