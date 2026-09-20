#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""从宣传图照片里提取配色：降采样成小网格直接读 RGB。
读图能力不可用时的替代手段——看不见画面，但能拿到真实颜色与空间分布。
用法：python3 .build/blender/extract_palette.py 宣传图/*.JPG
"""
import subprocess
import sys
from collections import Counter
from pathlib import Path

COLS, ROWS = 6, 9          # 空间网格
FINE = 40                  # 主色统计用的细网格边长


def grid_rgb(path, cols, rows):
    out = subprocess.run(
        ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-i', str(path),
         '-vf', f'scale={cols}:{rows}:flags=area', '-frames:v', '1',
         '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'],
        capture_output=True, check=True).stdout
    px = [tuple(out[i:i+3]) for i in range(0, len(out), 3)]
    return [px[r*cols:(r+1)*cols] for r in range(rows)]


def hx(c):
    return '#%02x%02x%02x' % c


def luma(c):
    return 0.2126*c[0] + 0.7152*c[1] + 0.0722*c[2]


def sat(c):
    mx, mn = max(c), min(c)
    return 0 if mx == 0 else (mx - mn) / mx


def main(paths):
    for p in paths:
        p = Path(p)
        print('=' * 72)
        print(p.name)
        g = grid_rgb(p, COLS, ROWS)
        print(f'  空间网格 {COLS}×{ROWS}（从上到下 = 画面顶到底）')
        for r, row in enumerate(g):
            band = '上' if r < ROWS/3 else ('中' if r < 2*ROWS/3 else '下')
            cells = '  '.join(f'{hx(c)}' for c in row)
            print(f'   {band} r{r}  {cells}')

        fine = grid_rgb(p, FINE, FINE)
        flat = [c for row in fine for c in row]
        # 量化到 16 级后统计主色
        q = Counter(tuple(v // 16 * 16 + 8 for v in c) for c in flat)
        print('  主色（量化后出现频次 top 8）：')
        for c, n in q.most_common(8):
            print(f'    {hx(c)}  {n*100/len(flat):5.1f}%  亮度{luma(c):5.1f} 饱和{sat(c):.2f}')
        # 最饱和与最亮/最暗的代表色，通常分别对应景观、天空/立面高光、玻璃/阴影
        bysat = sorted(flat, key=sat, reverse=True)[:len(flat)//50]
        bylum = sorted(flat, key=luma)
        print(f'  最饱和代表 {hx(bysat[len(bysat)//2])}  '
              f'最暗代表 {hx(bylum[len(bylum)//50])}  '
              f'最亮代表 {hx(bylum[-len(bylum)//50])}')


if __name__ == '__main__':
    main(sys.argv[1:])
