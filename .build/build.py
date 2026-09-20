#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把 .build/viz.tpl.html 与内联依赖、数据合成为单文件 HTML。
用法: python3 .build/build.py
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
B = ROOT / '.build'
OUT = ROOT / '前滩尚品_3D可视化.html'
# GitHub Pages 用：与上面字节完全相同，因此 git 按内容哈希去重，不额外占体积
PAGE = ROOT / 'index.html'

tpl = (B / 'viz.tpl.html').read_text(encoding='utf-8')
parts = {
    '/*__THREE__*/': B / 'three.min.js',
    '/*__ORBIT__*/': B / 'OrbitControls.js',
    '/*__XLSX__*/':  B / 'xlsx.js',
    '/*__DATA__*/':  B / 'units.json',
}
for token, f in parts.items():
    if token not in tpl:
        raise SystemExit(f'模板缺少占位符 {token}')
    tpl = tpl.replace(token, f.read_text(encoding='utf-8'))

OUT.write_text(tpl, encoding='utf-8')
PAGE.write_text(tpl, encoding='utf-8')
print(f'已生成 {OUT.name} 与 {PAGE.name}  各 {OUT.stat().st_size/1024:.0f} KB')
