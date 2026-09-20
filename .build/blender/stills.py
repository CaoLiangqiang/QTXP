# -*- coding: utf-8 -*-
"""任务 1：高画质效果图（Cycles + Metal GPU）
用法：Blender --background --python .build/blender/stills.py -- [samples] [width]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy  # noqa: E402
import scene as S  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
SAMPLES = int(argv[0]) if len(argv) > 0 else 160
W = int(argv[1]) if len(argv) > 1 else 2560
RES = (W, round(W * 9 / 16))
OUT = Path(__file__).resolve().parents[2] / '.build' / 'renders'

noon = max(S.GEO['timeline'], key=lambda r: r['alt'])
nine = min(S.GEO['timeline'], key=lambda r: abs(r['t'] - 9.25))

# (文件名, 着色模式, 指标, 时刻, 相机方向, 焦距, 正交尺寸)
SHOTS = [
    ('01_东南鸟瞰',   'arch', None,    noon, (0.70, -1.00, 0.50), 50, None),
    ('02_正午长影',   'arch', None,    nine, (0.28, -1.00, 0.30), 55, None),
    ('03_俯视总平',   'arch', None,    noon, (0.02, -0.18, 1.00), 50, None),
    ('04_单价着色',   'data', 'price', noon, (0.70, -1.00, 0.50), 50, None),
    ('05_日照着色',   'data', 'sun',   noon, (0.55, -1.00, 0.62), 50, None),
]

for name, mode, metric, t, direction, lens, ortho in SHOTS:
    print(f'\n===== {name}  mode={mode} metric={metric} '
          f't={t["t"]:.2f}h alt={t["alt"]:.1f}° =====')
    S.build(mode=mode, metric=metric or 'price')
    S.set_sun(t['az'], t['alt'], strength=3.0)
    bpy.context.scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.55
    S.fit_camera(direction, lens=lens, margin=1.06, res=RES)
    S.setup_render(engine='CYCLES', res=RES, samples=SAMPLES)
    S.render_to(OUT / f'{name}.png')

print('\n全部效果图完成')
