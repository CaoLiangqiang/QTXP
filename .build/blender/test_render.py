# -*- coding: utf-8 -*-
"""测试渲染：验证取景、太阳方向与曝光配比。
用法：Blender --background --python .build/blender/test_render.py -- [sun] [sky]
"""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy  # noqa: E402
import mathutils  # noqa: E402
import scene as S  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
SUN = float(argv[0]) if len(argv) > 0 else 3.0
SKY = float(argv[1]) if len(argv) > 1 else 0.6

OUT = Path(__file__).resolve().parents[2] / '.build' / 'renders'
RES = (1280, 720)

S.build(mode='arch')
lamp = S.set_sun(S.GEO['noon_az'], S.GEO['noon_alt'], strength=SUN)
bpy.context.scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value = SKY

a, e = math.radians(S.GEO['noon_az']), math.radians(S.GEO['noon_alt'])
to_sun = mathutils.Vector((math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), math.sin(e)))
emit = lamp.matrix_world.to_quaternion() @ mathutils.Vector((0, 0, -1))
print(f'[太阳] 指向太阳 {tuple(round(v,3) for v in to_sun)}  '
      f'灯光出射 {tuple(round(v,3) for v in emit)}  '
      f'点积(应≈-1) {to_sun.dot(emit):.3f}')

S.fit_camera((0.70, -1.0, 0.50), lens=50, res=RES)
S.setup_render(engine='CYCLES', res=RES, samples=48)
S.render_to(OUT / f'test_sun{SUN:g}_sky{SKY:g}.png')
