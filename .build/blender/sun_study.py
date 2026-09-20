# -*- coding: utf-8 -*-
"""任务 2：冬至日照动画（9–15 时逐帧推进太阳，EEVEE）
每帧只改太阳与天空，相机固定，因此帧间只有光影变化。
用法：Blender --background --python .build/blender/sun_study.py -- [width] [samples] [every]
  every=2 表示隔帧取样（快速预览）
"""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy  # noqa: E402
import scene as S  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
W = int(argv[0]) if len(argv) > 0 else 1600
SAMPLES = int(argv[1]) if len(argv) > 1 else 32
EVERY = int(argv[2]) if len(argv) > 2 else 1
RES = (W, round(W * 9 / 16))

OUT = Path(__file__).resolve().parents[2] / '.build' / 'renders' / 'sun'
OUT.mkdir(parents=True, exist_ok=True)

tl = S.GEO['timeline'][::EVERY]

# 场景与相机只建一次
S.build(mode='arch')
S.fit_camera((0.62, -1.00, 0.46), lens=48, margin=1.04, res=RES)
S.setup_render(engine='BLENDER_EEVEE', res=RES, samples=SAMPLES)

meta = []
for i, rec in enumerate(tl):
    S.set_sun(rec['az'], rec['alt'], strength=3.2)
    bpy.context.scene.world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.5
    hh = int(rec['t'])
    mm = int(round((rec['t'] - hh) * 60))
    S.render_to(OUT / f'{i:04d}.png')
    meta.append(dict(i=i, t=rec['t'], label=f'{hh:02d}:{mm:02d}',
                     az=round(rec['az'], 2), alt=round(rec['alt'], 2)))
    print(f'  帧 {i+1}/{len(tl)}  {hh:02d}:{mm:02d}  高度角 {rec["alt"]:.1f}°')

(OUT / 'frames.json').write_text(json.dumps(meta, ensure_ascii=False), encoding='utf-8')
print(f'\n日照动画帧完成：{len(tl)} 帧 -> {OUT}')
