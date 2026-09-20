# -*- coding: utf-8 -*-
"""效果图（气氛向）：低角度暖光 + 近景 + 景深。
和 stills.py 的区别：stills 是"看得清"的分析图，这里是"看得好"的表现图。
用法：Blender --background --python .build/blender/hero.py -- [samples] [width]
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bpy  # noqa: E402
import scene as S  # noqa: E402

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
SAMPLES = int(argv[0]) if len(argv) > 0 else 200
W = int(argv[1]) if len(argv) > 1 else 2560
RES = (W, round(W * 9 / 16))
OUT = Path(__file__).resolve().parents[2] / '.build' / 'renders'

tl = S.GEO['timeline']
noon = max(tl, key=lambda r: r['alt'])
late = min(tl, key=lambda r: abs(r['t'] - 14.75))     # 冬至 14:45，高度角约 21°，西南向

B11, B8, B5 = S.BUILDINGS['11幢'], S.BUILDINGS['8幢'], S.BUILDINGS['5幢']

print(f'黄昏取 {late["t"]:.2f}时 方位{late["az"]:.1f}° 高度{late["alt"]:.1f}°（真实冬至时刻，非摆拍）')

S.build(mode='arch', balconies=True, context=True)

SHOTS = [
    # 10 黄昏鸟瞰：相机东南、太阳西南 —— 侧逆光让体量有明暗交界
    dict(name='10_黄昏鸟瞰', sun=late, warm=0.95, sun_e=3.4, sky=0.50, exposure=0.20,
         fit=(0.78, -1.00, 0.34), lens=52, dof=None),
    # 11 近景人视：贴近 11幢 南立面，展示阳台与栏板。
    # 视高压到 1.9 m（真人视线）并让南侧行道树与草坪进入前景 ——
    # 近景图缺前景是"假"的另一大来源。
    dict(name='11_近景人视', sun=late, warm=0.9, sun_e=3.6, sky=0.55, exposure=0.10,
         loc=(40, -42, 1.9), target=(-10, 4, 17), lens=28, dof=6.0),
    # 12 楼间对望：站在 8幢 与 5幢 之间（间距 30 m），看正午阴影切在 5幢 立面上
    dict(name='12_楼间对望', sun=noon, warm=0.15, sun_e=3.0, sky=0.6, exposure=0.0,
         loc=(30, B8['y1'] + 6, 4.2), target=(-12, B5['y0'], 15), lens=32, dof=7.0),
]

for s in SHOTS:
    print(f'\n===== {s["name"]}  {s["sun"]["t"]:.2f}时 alt={s["sun"]["alt"]:.1f}° =====')
    S.set_sun(s['sun']['az'], s['sun']['alt'], strength=s['sun_e'],
              warm=s['warm'], sky_strength=s['sky'])
    if 'fit' in s:
        S.fit_camera(s['fit'], lens=s['lens'], margin=1.04, res=RES, dof=s['dof'])
    else:
        S.add_camera(s['loc'], s['target'], lens=s['lens'], dof=s['dof'])
    S.setup_render(engine='CYCLES', res=RES, samples=SAMPLES, exposure=s['exposure'])
    S.render_to(OUT / f'{s["name"]}.png')

print('\n气氛效果图完成')
