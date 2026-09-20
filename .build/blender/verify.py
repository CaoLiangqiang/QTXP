# -*- coding: utf-8 -*-
"""不渲染，只数值校验：太阳灯出射方向、阴影落点、相机取景。
用法：Blender --background --python .build/blender/verify.py
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy  # noqa: E402
import mathutils  # noqa: E402
import scene as S  # noqa: E402

S.build(mode='arch')
ok = True

print('=== 太阳灯朝向 ===')
for t, az, alt in [(9.0, None, None), (S.GEO['timeline'][len(S.GEO['timeline'])//2]['t'], None, None), (15.0, None, None)]:
    rec = min(S.GEO['timeline'], key=lambda r: abs(r['t'] - t))
    lamp = S.set_sun(rec['az'], rec['alt'])
    bpy.context.view_layer.update()                  # matrix_world 是派生值，必须先求值
    a, e = math.radians(rec['az']), math.radians(rec['alt'])
    to_sun = mathutils.Vector((math.sin(a)*math.cos(e), math.cos(a)*math.cos(e), math.sin(e)))
    emit = (lamp.matrix_world.to_quaternion() @ mathutils.Vector((0, 0, -1))).normalized()
    dot = to_sun.dot(emit)
    good = abs(dot + 1) < 0.02
    ok &= good
    # 地面阴影方向 = 出射向量的水平投影
    shadow = mathutils.Vector((emit.x, emit.y, 0)).normalized()
    bearing = (math.degrees(math.atan2(shadow.x, shadow.y)) + 360) % 360
    print(f'{rec["t"]:5.2f}时  方位{rec["az"]:6.2f}° 高度{rec["alt"]:5.2f}°  '
          f'出射·指向太阳={dot:+.4f} {"OK" if good else "错"}  '
          f'地面阴影朝向 {bearing:6.1f}°（0=北）')

print('\n=== 遮挡几何自检（正午）===')
rec = max(S.GEO['timeline'], key=lambda r: r['alt'])
S.set_sun(rec['az'], rec['alt'])
shadow_len = (S.GEO['n_storey'] * S.FLOOR_H + S.GEO['parapet']) / math.tan(math.radians(rec['alt']))
print(f'檐高 {S.GEO["n_storey"]*S.FLOOR_H + S.GEO["parapet"]:.1f} m，正午影长 {shadow_len:.1f} m')
print(f'8幢→5幢 间距 {S.GEO["gap_8_5"]:.0f} m  →  正午影子越过间距 '
      f'{shadow_len - S.GEO["gap_8_5"]:+.1f} m，即打到 5幢 立面 '
      f'{max(0, (shadow_len - S.GEO["gap_8_5"]))*math.tan(math.radians(rec["alt"])):.1f} m 高')
print(f'11幢→8幢 间距 {S.GEO["gap_11_8"]:.0f} m  →  '
      f'{"正午不遮挡" if shadow_len <= S.GEO["gap_11_8"] else "正午仍遮挡"}')

print('\n=== 相机取景 ===')
cam = S.fit_camera((0.70, -1.0, 0.50), lens=50, res=(2560, 1440))
bpy.context.view_layer.update()
x0, x1, y0, y1, z0, z1 = S.site_bbox()
inside = 0
for cx in (x0, x1):
    for cy in (y0, y1):
        for cz in (z0, z1):
            co = bpy.context.scene.camera.matrix_world.inverted() @ mathutils.Vector((cx, cy, cz))
            if co.z >= 0:
                continue
            ndc_x = -co.x / co.z / ((36/2) / cam.data.lens)
            ndc_y = -co.y / co.z / (((36/2) / cam.data.lens) / (2560/1440))
            if abs(ndc_x) <= 1.001 and abs(ndc_y) <= 1.001:
                inside += 1
print(f'相机位置 {tuple(round(v,1) for v in cam.location)}  '
      f'包围盒 8 角点入画 {inside}/8 {"OK" if inside == 8 else "取景不足"}')
ok &= (inside == 8)

print('\n物体数', len(bpy.data.objects), '材质数', len(bpy.data.materials))
print('总体', 'OK' if ok else '有问题')
sys.exit(0 if ok else 1)
