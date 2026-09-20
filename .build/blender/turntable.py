# -*- coding: utf-8 -*-
"""任务 3：环绕 turntable（相机绕场地一圈，太阳固定在冬至正午，EEVEE）
用法：Blender --background --python .build/blender/turntable.py -- [width] [frames] [samples]
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy  # noqa: E402
import mathutils  # noqa: E402
import scene as S  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
W = int(argv[0]) if len(argv) > 0 else 1280
N = int(argv[1]) if len(argv) > 1 else 72
SAMPLES = int(argv[2]) if len(argv) > 2 else 32
RES = (W, round(W * 9 / 16))

OUT = Path(__file__).resolve().parents[2] / '.build' / 'renders' / 'turn'
OUT.mkdir(parents=True, exist_ok=True)

ELEV = 0.46                       # 仰角分量，越大越俯视
noon = max(S.GEO['timeline'], key=lambda r: r['alt'])

S.build(mode='arch')
S.set_sun(noon['az'], noon['alt'], strength=3.0)
bpy.context.scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.55

# 先按最"宽"的方向定半径，保证整圈都不出画
center = mathutils.Vector(S.site_center()[0])
radius = 0.0
for k in range(N):
    th = 2 * math.pi * k / N
    cam = S.fit_camera((math.sin(th), -math.cos(th), ELEV), lens=48, margin=1.04, res=RES)
    radius = max(radius, (cam.location - center).length)
print(f'环绕半径取 {radius:.1f} m（对 {N} 个方位取最大值，保证整圈不出画）')

S.setup_render(engine='BLENDER_EEVEE', res=RES, samples=SAMPLES)
cam = bpy.context.scene.camera
for k in range(N):
    th = 2 * math.pi * k / N
    d = mathutils.Vector((math.sin(th), -math.cos(th), ELEV)).normalized()
    cam.location = center + d * radius
    S.look_at(cam, center)
    S.render_to(OUT / f'{k:04d}.png')
    if (k + 1) % 12 == 0:
        print(f'  {k+1}/{N} 帧')

print(f'\n环绕帧完成：{N} 帧 -> {OUT}')
