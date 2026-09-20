# -*- coding: utf-8 -*-
"""前滩尚品 · Blender 场景构建（供 stills / hero / sun_study / turntable 复用）

坐标约定：+X 东，+Y 北，+Z 上，单位米。11幢 南立面位于 y=0。
几何来自 geometry.json（由 solar.py 用日照数据反推楼间距后写出）。

只用 bpy 数据 API 建几何（from_pydata / bpy.data.*），不依赖 bpy.ops 的上下文，
唯一用到 ops 的是生成一个球体模板网格，失败时退化为八面体。
"""
import json
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
GEO = json.loads((HERE / 'geometry.json').read_text(encoding='utf-8'))
UNITS = json.loads((ROOT / '.build' / 'units.json').read_text(encoding='utf-8'))

FLOOR_H = GEO['floor_h']
UNIT_W = GEO['unit_w']
BUILDINGS = GEO['buildings']
ORDER = ['11幢', '8幢', '5幢']          # 南 → 北

SUN_COLOR = {5.5: '#c00000', 5: '#e62e2e', 4.5: '#f06018', 4: '#f08c1e',
             3.5: '#f5b41e', 3: '#ffd21e', 2.5: '#b5cc18', 2: '#6ba81e'}
RAMP = ['#1c4e8a', '#2f8fc4', '#63c9a8', '#ffd86b', '#f3903f', '#c9302c']


# ---------------- 颜色 ----------------
def srgb_to_linear(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def hex_rgba(h, a=1.0):
    h = h.lstrip('#')
    return tuple(srgb_to_linear(int(h[i:i+2], 16) / 255) for i in (0, 2, 4)) + (a,)


def ramp_hex(stops, t):
    t = max(0.0, min(1.0, t))
    x = t * (len(stops) - 1)
    i = min(int(x), len(stops) - 2)
    f = x - i
    a = [int(stops[i].lstrip('#')[j:j+2], 16) for j in (0, 2, 4)]
    b = [int(stops[i+1].lstrip('#')[j:j+2], 16) for j in (0, 2, 4)]
    return '#%02x%02x%02x' % tuple(int(a[k] + (b[k] - a[k]) * f) for k in range(3))


def rnd(key, salt=0):
    """FNV-1a 哈希得到的确定性伪随机数 ∈ [0,1)。
    逐户差异必须可复现（同一户每次渲染长得一样），所以不能用 random。"""
    h = 2166136261
    for ch in f'{key}#{salt}':
        h = ((h ^ ord(ch)) * 16777619) & 0xFFFFFFFF
    return (h % 100000) / 100000.0


# ---------------- 网格工具 ----------------
def clear_scene():
    global _BLOB
    _BLOB = None                      # 缓存的网格会被下面删掉，必须同时失效
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.materials,
                 bpy.data.lights, bpy.data.cameras, bpy.data.collections):
        for item in list(coll):
            try:
                coll.remove(item)
            except Exception:
                pass


def add_box(name, x0, x1, y0, y1, z0, z1, mat=None, col=None):
    verts = [(x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
             (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1)]
    faces = [(0, 1, 2, 3), (4, 7, 6, 5), (0, 4, 5, 1),
             (1, 5, 6, 2), (2, 6, 7, 3), (3, 7, 4, 0)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate()
    me.update()
    ob = bpy.data.objects.new(name, me)
    if mat:
        ob.data.materials.append(mat)
    (col or bpy.context.scene.collection).objects.link(ob)
    return ob


def add_beveled_box(name, x0, x1, y0, y1, z0, z1, mat=None, col=None,
                     bevel=0.18, segments=4):
    """带实体圆角的盒体。用于宣传图里标志性的连续圆角檐口与阳台挑板。
    Bevel 保留为 modifier（不 apply），后台渲染能直接计算，避免 bpy.ops 上下文依赖。"""
    ob = add_box(name, x0, x1, y0, y1, z0, z1, mat, col)
    md = ob.modifiers.new('圆角', 'BEVEL')
    md.width = bevel
    md.segments = segments
    md.limit_method = 'ANGLE'
    try:
        md.miter_outer = 'MITER_ARC'
    except Exception:
        pass
    return ob


def add_flared_pier(name, x, y0, y1, z0, z1, mat, col, slim=0.09, flare=0.34):
    """每层一个双端外扩的竖向构件，近似宣传图里的 Y 形 / 拱形 Art Deco 框架。
    用 9 个截面按 smoothstep 收敛宽度，避免旧版 4 截面形成尖锐"打结"。"""
    n = 9
    zs, ws = [], []
    for i in range(n):
        t = i / (n - 1)
        # 离上下端越近越宽；三次 smoothstep 让过渡在端点和中段都没有折角
        q = abs(t - .5) * 2
        q = q*q*(3 - 2*q)
        zs.append(z0 + (z1 - z0) * t)
        ws.append(slim + (flare - slim) * q)
    verts = []
    for yy in (y0, y1):
        for z, w in zip(zs, ws):
            verts.extend([(x - w, yy, z), (x + w, yy, z)])
    faces = []
    side = 2 * n
    for base in (0, side):
        for i in range(n - 1):
            faces.append((base + 2*i, base + 2*i + 1,
                          base + 2*i + 3, base + 2*i + 2))
    for i in range(n - 1):
        a, b = 2*i, 2*(i+1)
        faces += [(a, b, side+b, side+a),
                  (a+1, side+a+1, side+b+1, b+1)]
    faces += [(0, side, side+1, 1),
              (2*n-2, 2*n-1, 4*n-1, 4*n-2)]
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate(); me.update()
    ob = bpy.data.objects.new(name, me)
    ob.data.materials.append(mat)
    col.objects.link(ob)
    md = ob.modifiers.new('柔化边缘', 'BEVEL')
    md.width = 0.025; md.segments = 2
    return ob


def add_quad(name, pts, mat=None, col=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata(pts, [], [(0, 1, 2, 3)])
    me.validate()
    me.update()
    ob = bpy.data.objects.new(name, me)
    if mat:
        ob.data.materials.append(mat)
    (col or bpy.context.scene.collection).objects.link(ob)
    return ob


_BLOB = None


def blob_mesh():
    """一个球体模板网格，树冠等用它做实例复用（只生成一次）。"""
    global _BLOB
    # 被 clear_scene 删除后 _BLOB 会变成悬空的 StructRNA，
    # 访问其任何属性都会抛 ReferenceError，不能只用 `in bpy.data.meshes` 判断。
    try:
        if _BLOB is not None and _BLOB.name in bpy.data.meshes:
            return _BLOB
    except ReferenceError:
        _BLOB = None
    try:
        bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=3, radius=1.0)
        ob = bpy.context.object
        _BLOB = ob.data
        bpy.data.objects.remove(ob, do_unlink=True)
    except Exception as err:                       # 退化为八面体，远景足够
        print('球体 ops 不可用，退化为八面体:', err, file=sys.stderr)
        v = [(0, 0, 1), (1, 0, 0), (0, 1, 0), (-1, 0, 0), (0, -1, 0), (0, 0, -1)]
        f = [(0, 1, 2), (0, 2, 3), (0, 3, 4), (0, 4, 1),
             (5, 2, 1), (5, 3, 2), (5, 4, 3), (5, 1, 4)]
        me = bpy.data.meshes.new('blob')
        me.from_pydata(v, [], f)
        me.validate()
        me.update()
        _BLOB = me
    return _BLOB


def add_instance(name, mesh, loc, scale, mat=None, col=None):
    ob = bpy.data.objects.new(name, mesh)
    ob.location = Vector(loc)
    ob.scale = Vector(scale)
    if mat:
        ob.data = mesh          # 共享网格
        if mat.name not in [m.name for m in mesh.materials if m]:
            pass
    (col or bpy.context.scene.collection).objects.link(ob)
    if mat:
        ob.material_slots  # noqa  触发 slot
        if not ob.data.materials:
            ob.data.materials.append(mat)
        else:
            ob.material_slots[0].link = 'OBJECT'
            ob.material_slots[0].material = mat
    return ob


# ---------------- 材质 ----------------
def set_input(node, names, value):
    for n in names:
        if n in node.inputs:
            node.inputs[n].default_value = value
            return True
    return False


def make_mat(name, color, rough=0.5, metal=0.0, transmit=0.0,
             emit=None, emit_str=0.0, bump=None, coat=0.0):
    """bump=(scale, strength) 时加一层程序化噪声凹凸，让大面积平板不再死板。"""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes.get('Principled BSDF')
    if bsdf is None:
        bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
        nt.links.new(bsdf.outputs[0], nt.nodes['Material Output'].inputs['Surface'])
    set_input(bsdf, ['Base Color'], color)
    set_input(bsdf, ['Roughness'], rough)
    set_input(bsdf, ['Metallic'], metal)
    set_input(bsdf, ['Transmission Weight', 'Transmission'], transmit)
    set_input(bsdf, ['IOR'], 1.5)
    set_input(bsdf, ['Coat Weight', 'Clearcoat'], coat)
    if emit:
        set_input(bsdf, ['Emission Color', 'Emission'], emit)
        set_input(bsdf, ['Emission Strength'], emit_str)
    if bump:
        scale, strength = bump
        noise = nt.nodes.new('ShaderNodeTexNoise')
        noise.inputs['Scale'].default_value = scale
        if 'Detail' in noise.inputs:
            noise.inputs['Detail'].default_value = 6.0
        bn = nt.nodes.new('ShaderNodeBump')
        bn.inputs['Strength'].default_value = strength
        nt.links.new(noise.outputs['Fac'], bn.inputs['Height'])
        nt.links.new(bn.outputs['Normal'], bsdf.inputs['Normal'])
        # 同一噪声轻微扰动基色，避免整面同色
        mix = nt.nodes.new('ShaderNodeMixRGB')
        mix.blend_type = 'MULTIPLY'
        mix.inputs['Fac'].default_value = 0.10
        mix.inputs['Color1'].default_value = color
        mix.inputs['Color2'].default_value = (1.12, 1.08, 1.0, 1.0)
        nt.links.new(noise.outputs['Fac'], mix.inputs['Fac'])
        nt.links.new(mix.outputs['Color'], bsdf.inputs['Base Color'])
    if transmit > 0:
        m.use_backface_culling = False
    return m


def palette():
    """一套材质，构建与渲染脚本共用。

    配色依据：从售楼处宣传物料照片（`宣传图/`，未入库）用
    `extract_palette.py` 降采样取 RGB 反推得到，而非凭感觉调的。
    主要来源与取值见各行注释。

    局限：素材是打印物料的手机翻拍，带印刷色偏与拍摄环境光，
    所以这些值反映的是**色相关系**（暖立面 ↔ 冷玻璃 ↔ 深绿景观），
    不是绝对色值。拿到电子版立面图可进一步校正。"""
    p = {}
    p['地面'] = make_mat('地面', hex_rgba('#8a8a6e'), rough=0.95, bump=(6, 0.06))
    # 暖铺装：IMG_1889 底部 #ae9971 / #bdaa88 / #a18d6f
    p['铺装'] = make_mat('铺装', hex_rgba('#b09a78'), rough=0.70, bump=(22, 0.10))
    # 景观绿：IMG_1889 主色 #487858 / #386848（偏蓝的深绿，
    # 不是我原先用的黄绿 #4a7a2c —— 这是提取数据纠正的第一处错误）
    p['草坪'] = make_mat('草坪', hex_rgba('#3f6f50'), rough=0.95, bump=(40, 0.22))
    p['沥青'] = make_mat('沥青', hex_rgba('#35373c'), rough=0.80, bump=(30, 0.08))
    # 立面暖砂岩：IMG_1888 r4 #d3bfa5 / #bfb09c / #beac96，IMG_1887 r2 #b8a798
    p['外墙'] = make_mat('外墙', hex_rgba('#d3bfa5'), rough=0.56, bump=(9, 0.10))
    # 深色石材带：IMG_1888 #8c7055 / #a38e77
    p['外墙深'] = make_mat('外墙深', hex_rgba('#967d62'), rough=0.60, bump=(9, 0.10))
    p['石材'] = make_mat('石材基座', hex_rgba('#6a5c4c'), rough=0.52, bump=(14, 0.14))
    p['线条'] = make_mat('楼板线条', hex_rgba('#efe4d2'), rough=0.40)
    # 玻璃：IMG_1887 中右列 #4d545b / #485057 / #56626f / #706a65。
    # 实际立面玻璃是**中间调蓝灰**，远比我原先的深藏青 #0f2e45 亮得多
    # —— 这是提取数据纠正的第二处错误，也是此前"太暗太脏"的主因。
    p['玻璃'] = make_mat('玻璃', hex_rgba('#4f5a63'), rough=0.045, metal=0.30, coat=0.6)
    p['栏板'] = make_mat('玻璃栏板', hex_rgba('#7d909c'), rough=0.05, transmit=0.70, coat=0.5)
    p['金属'] = make_mat('金属', hex_rgba('#474d52'), rough=0.30, metal=0.9)
    p['窗框'] = make_mat('窗框', hex_rgba('#2e3236'), rough=0.36, metal=0.6)
    p['女儿墙'] = make_mat('女儿墙', hex_rgba('#c9b69c'), rough=0.54, bump=(9, 0.08))
    p['屋面'] = make_mat('屋面', hex_rgba('#4e4f46'), rough=0.85, bump=(18, 0.12))
    p['树干'] = make_mat('树干', hex_rgba('#4a3524'), rough=0.85)
    # 树冠双色：IMG_1889 的绿色区间上下端
    p['树冠'] = make_mat('树冠', hex_rgba('#356044'), rough=0.9, bump=(28, 0.3))
    p['树冠2'] = make_mat('树冠2', hex_rgba('#588a5e'), rough=0.9, bump=(24, 0.3))
    p['邻楼'] = make_mat('邻楼', hex_rgba('#b8a894'), rough=0.60)
    p['邻楼2'] = make_mat('邻楼2', hex_rgba('#9a9384'), rough=0.62)
    p['邻窗'] = make_mat('邻窗', hex_rgba('#48535c'), rough=0.10, metal=0.3)

    # --- 逐户差异用的窗面材质 ---
    # 真实住宅楼不存在两扇一样的窗：有的拉着窗帘、有的能看进室内、有的只反天空。
    # 这是让渲染"不像模型"的最大杠杆，比贴图分辨率重要得多。
    p['窗帘白'] = make_mat('窗帘白', hex_rgba('#ddd6c8'), rough=0.72)
    p['窗帘暖'] = make_mat('窗帘暖', hex_rgba('#c9b494'), rough=0.74)
    p['窗帘灰'] = make_mat('窗帘灰', hex_rgba('#a0a6a8'), rough=0.70)
    p['室内暗'] = make_mat('室内暗', hex_rgba('#1d2226'), rough=0.85)
    p['室内暖'] = make_mat('室内暖', hex_rgba('#2e2823'), rough=0.8,
                          emit=hex_rgba('#ffc98a'), emit_str=0.25)
    p['玻璃亮'] = make_mat('玻璃亮', hex_rgba('#5d6a74'), rough=0.028, metal=0.34, coat=0.6)
    p['玻璃哑'] = make_mat('玻璃哑', hex_rgba('#414b53'), rough=0.085, metal=0.20, coat=0.4)
    p['空调'] = make_mat('空调外机', hex_rgba('#cbc7bd'), rough=0.55, metal=0.25)
    p['阳台地'] = make_mat('阳台地面', hex_rgba('#ab9a80'), rough=0.62, bump=(30, 0.10))
    return p


# ---------------- 环境文脉 ----------------
def add_context(P, col):
    """场地之外的东西：铺装、草坪、道路、行道树、邻楼体量。
    空场地是"假"的最大来源——哪怕是粗糙的文脉也远胜一块灰板。"""
    x0 = min(b['x0'] for b in BUILDINGS.values())
    x1 = max(b['x1'] for b in BUILDINGS.values())
    y0 = BUILDINGS['11幢']['y0']
    y1 = BUILDINGS['5幢']['y1']
    cx = (x0 + x1) / 2

    # 大地面
    add_box('大地', cx - 400, cx + 400, y0 - 400, y1 + 400, -0.5, -0.05, P['地面'], col)
    # 小区内部铺装
    add_box('场地铺装', x0 - 18, x1 + 18, y0 - 22, y1 + 22, -0.05, 0.02, P['铺装'], col)

    # 楼间草坪 + 步道
    for a, b in (('11幢', '8幢'), ('8幢', '5幢')):
        ya, yb = BUILDINGS[a]['y1'], BUILDINGS[b]['y0']
        add_box(f'草坪_{a}_{b}', x0 - 6, x1 + 6, ya + 4, yb - 4, 0.02, 0.10, P['草坪'], col)
        add_box(f'步道_{a}_{b}', x0 - 6, x1 + 6, (ya + yb) / 2 - 1.6,
                (ya + yb) / 2 + 1.6, 0.10, 0.16, P['铺装'], col)

    # 南北两条市政道路
    for yy, nm in ((y0 - 30, '南路'), (y1 + 30, '北路')):
        add_box(nm, cx - 260, cx + 260, yy - 8, yy + 8, -0.05, 0.03, P['沥青'], col)
        for k in range(-22, 23):                   # 车道中线虚线
            add_box(f'{nm}_线_{k}', cx + k * 11, cx + k * 11 + 4.5,
                    yy - 0.18, yy + 0.18, 0.03, 0.05, P['线条'], col)

    # 行道树与组团树：共享一份平滑球体网格，每棵由 3 个不等高团簇组成，
    # 避免此前一棵树=一个低面数球的占位符观感。
    bm = blob_mesh()
    for poly in bm.polygons:
        poly.use_smooth = True

    # 每栋南侧的精细近景层：大草坪 + 低矮绿篱 + 中轴入口步道。
    # 宣传图的人视效果几乎没有裸露硬地，前景被草坪和修剪灌木占满。
    for bi, bn in enumerate(ORDER):
        bd = BUILDINGS[bn]
        add_box(f'{bn}_前庭草坪', bd['x0'] - 3, bd['x1'] + 3,
                bd['y0'] - 9.5, bd['y0'] - 2.0, .03, .11, P['草坪'], col)
        mid = (bd['x0'] + bd['x1']) / 2
        add_box(f'{bn}_入口步道', mid - 2.0, mid + 2.0,
                bd['y0'] - 10.0, bd['y0'] - .2, .11, .17, P['铺装'], col)
        # 分段绿篱，留出中间入口
        for hi, (ha, hb) in enumerate(((bd['x0'] - 2.2, mid - 2.8),
                                        (mid + 2.8, bd['x1'] + 2.2))):
            if hb > ha:
                add_beveled_box(f'{bn}_绿篱_{hi}', ha, hb,
                                bd['y0'] - 2.5, bd['y0'] - 1.65,
                                .11, .70, P['树冠'], col, bevel=.24, segments=4)
    spots = []
    for yy in (y0 - 24, y1 + 24):
        spots += [(cx + k * 13, yy, 3.4) for k in range(-9, 10)]
    for a, b in (('11幢', '8幢'), ('8幢', '5幢')):
        ya, yb = BUILDINGS[a]['y1'], BUILDINGS[b]['y0']
        spots += [(x0 + 4 + k * 12, ya + 7, 2.8) for k in range(0, 5)]
        spots += [(x0 + 9 + k * 12, yb - 7, 2.6) for k in range(0, 4)]
    spots += [(x0 - 13, y0 + k * 16, 3.0) for k in range(0, 7)]
    spots += [(x1 + 13, y0 + k * 16, 3.0) for k in range(0, 7)]

    for i, (tx, ty, h) in enumerate(spots):
        jx = ((i * 37) % 11 - 5) * 0.35            # 确定性抖动，避免排成死板的行列
        jy = ((i * 53) % 9 - 4) * 0.35
        s = 1.0 + ((i * 29) % 7 - 3) * 0.07
        add_box(f'树干_{i}', tx + jx - 0.16, tx + jx + 0.16, ty + jy - 0.16, ty + jy + 0.16,
                0.0, h * 0.42 * s, P['树干'], col)
        # 主冠 + 两个偏置侧冠，既增加轮廓复杂度又保持网格复用
        crowns = [
            (0.00,  0.00, .78, .36, .34, .40),
            (-.19,  .08, .74, .25, .26, .30),
            (.18,  -.06, .72, .24, .25, .29),
            (-.05, -.16, .84, .22, .21, .26),
            (.07,   .14, .88, .20, .19, .24),
        ]
        for j, (ox, oy, oz, sx, sy, sz) in enumerate(crowns):
            add_instance(f'树冠_{i}_{j}', bm,
                         (tx + jx + ox*h*s, ty + jy + oy*h*s, h*oz*s),
                         (h*sx*s, h*sy*s, h*sz*s),
                         P['树冠'] if (i+j) % 3 else P['树冠2'], col)

    # 邻楼体量：让场地不悬在虚空里
    neigh = [(-150, -60, 34), (-150, 40, 46), (-150, 130, 30),
             (150, -50, 40), (150, 60, 52), (150, 150, 36),
             (-40, -130, 28), (60, -130, 44), (-30, 210, 50), (70, 210, 38)]
    for i, (nx, ny, nh) in enumerate(neigh):
        w, d = 30 + (i % 3) * 9, 20 + (i % 2) * 8
        add_box(f'邻楼_{i}', nx - w / 2, nx + w / 2, ny - d / 2, ny + d / 2,
                0, nh, P['邻楼'] if i % 2 else P['邻楼2'], col)
        for f in range(1, int(nh // 3.2)):         # 简化窗带
            add_box(f'邻楼_{i}_窗_{f}', nx - w / 2 - 0.05, nx + w / 2 + 0.05,
                    ny - d / 2 - 0.05, ny + d / 2 + 0.05,
                    f * 3.2 + 0.9, f * 3.2 + 2.3, P['邻窗'], col)


# ---------------- 主场景 ----------------
def build(mode='arch', metric='price', balconies=True, context=True):
    clear_scene()
    scene = bpy.context.scene
    P = palette()

    env = bpy.data.collections.new('环境')
    scene.collection.children.link(env)
    if context:
        add_context(P, env)
    else:
        add_box('大地', -400, 400, -400, 500, -0.5, -0.05, P['地面'], env)

    by_key = {(u['b'], u['u'], u['rm'], u['fr']): u for u in UNITS}
    valid = [u for u in UNITS if u['p'] is not None]
    ext = {
        'price': (min(u['p'] for u in valid), max(u['p'] for u in valid)),
        'total': (min(u['t'] for u in valid), max(u['t'] for u in valid)),
        'area': (min(u['a'] for u in valid), max(u['a'] for u in valid)),
    }
    data_mats = {}

    def unit_mat(u):
        if mode != 'data':
            return P['玻璃']
        if metric == 'sun':
            hx = SUN_COLOR.get(u['s'], '#888888')
        else:
            lo, hi = ext[metric]
            key = {'price': 'p', 'total': 't', 'area': 'a'}[metric]
            hx = ramp_hex(RAMP, (u[key] - lo) / (hi - lo))
        if hx not in data_mats:
            data_mats[hx] = make_mat('数据_' + hx, hex_rgba(hx), rough=0.25,
                                     emit=hex_rgba(hx), emit_str=0.45)
        return data_mats[hx]

    for name in ORDER:
        b = BUILDINGS[name]
        cols = [tuple(c) for c in b['cols']]
        floors = sorted({u['fr'] for u in UNITS if u['b'] == name})
        min_f = min(floors)
        roof = GEO['n_storey'] * FLOOR_H
        col = bpy.data.collections.new(name)
        scene.collection.children.link(col)

        for f in range(1, GEO['n_storey'] + 1):
            z0, z1 = (f - 1) * FLOOR_H, f * FLOOR_H
            if f < min_f:
                # 宣传图底层是通透架空层，而不是一堵实心墙：后部暗盒 + 前玻璃 + 纤细立柱
                add_box(f'{name}_底层后部_{f}', b['x0'], b['x1'], b['y0'] + 3.0, b['y1'],
                        z0, z1, P['石材'], col)
                add_quad(f'{name}_底层玻璃_{f}',
                         [(b['x0'] + .5, b['y0'] - .08, z0 + .3),
                          (b['x1'] - .5, b['y0'] - .08, z0 + .3),
                          (b['x1'] - .5, b['y0'] - .08, z1 - .25),
                          (b['x0'] + .5, b['y0'] - .08, z1 - .25)], P['玻璃亮'], col)
                for k in range(len(cols) + 1):
                    px = b['x0'] + k * UNIT_W
                    add_beveled_box(f'{name}_底层柱_{f}_{k}', px - .18, px + .18,
                                    b['y0'] - .35, b['y0'] + .45, z0, z1,
                                    P['线条'], col, bevel=.10, segments=3)
            else:
                mat = P['外墙'] if f % 2 else P['外墙深']
                add_box(f'{name}_体_{f}', b['x0'], b['x1'], b['y0'], b['y1'], z0, z1, mat, col)

            # 宣传图最强的形态语言：每层连续的圆角挑檐。南立面突出、四角圆润；
            # 北面另加较窄的水平带，避免整圈做成夸张胶囊形。
            add_beveled_box(f'{name}_南檐_{f}', b['x0'] - .18, b['x1'] + .18,
                            b['y0'] - .72, b['y0'] + .16, z1 - .24, z1 + .04,
                            P['线条'], col, bevel=.22, segments=5)
            add_box(f'{name}_北檐_{f}', b['x0'], b['x1'],
                    b['y1'] - .10, b['y1'] + .28, z1 - .20, z1, P['线条'], col)

        add_box(f'{name}_女儿墙', b['x0'] - 0.12, b['x1'] + 0.12,
                b['y0'] - 0.12, b['y1'] + 0.12, roof, roof + GEO['parapet'], P['女儿墙'], col)

        # 宣传图的 Y 形 / 拱形构架：每个房号边界、每一层都做"中段细、上下外扩"。
        # 连续叠起来后形成纵向节奏和拱形框，不再是普通方柱。
        for f in floors:
            z0, z1 = (f - 1) * FLOOR_H + .12, f * FLOOR_H - .12
            for k in range(len(cols) + 1):
                px = b['x0'] + k * UNIT_W
                edge = (k == 0 or k == len(cols))
                add_flared_pier(f'{name}_拱架_{f}_{k}', px,
                                b['y0'] - 1.78, b['y0'] - 1.30,
                                z0, z1, P['线条'], col,
                                slim=.085 if edge else .060,
                                flare=.34 if edge else .235)
        add_box(f'{name}_屋面', b['x0'], b['x1'], b['y0'], b['y1'],
                roof - 0.05, roof + 0.06, P['屋面'], col)
        # 屋顶机房与电梯井（仅视觉，未计入 solar.py 的遮挡模型）
        mx = (b['x0'] + b['x1']) / 2
        add_box(f'{name}_机房', mx - 6, mx + 6, b['y0'] + 3, b['y0'] + 8,
                roof, roof + 3.2, P['石材'], col)
        add_box(f'{name}_电梯井', mx + 8, mx + 13, b['y1'] - 7, b['y1'] - 3,
                roof, roof + 2.4, P['石材'], col)

        for ci, ck in enumerate(cols):
            cx0 = b['x0'] + ci * UNIT_W
            for f in floors:
                u = by_key.get((name, ck[0], ck[1], f))
                if not u or u['p'] is None:
                    continue
                key = f"{u['b']}|{u['u']}|{u['rm']}|{u['fr']}"
                zb = (f - 1) * FLOOR_H
                x0, x1 = cx0 + 0.70, cx0 + UNIT_W - 0.70
                z0, z1 = zb + 0.90, zb + 2.60
                y = b['y0'] - 0.10

                # 室内凹深：玻璃后面塞一个暗盒，窗才不像贴在墙上的贴纸
                r_in = rnd(key, 3)
                inner = P['室内暖'] if r_in > 0.88 else P['室内暗']
                add_box(f'{name}_室内_{ci}_{f}', x0, x1, b['y0'] + 0.02, b['y0'] + 1.5,
                        z0, z1, inner, col)
                add_box(f'{name}_洞_{ci}_{f}', x0 - 0.14, x1 + 0.14, y, b['y0'],
                        z0 - 0.14, z1 + 0.14, P['窗框'], col)

                # 逐户窗面：约 40% 拉窗帘、12% 敞开露室内、其余反射玻璃
                r = rnd(key, 0)
                if mode == 'data':
                    pm = unit_mat(u)
                elif r < 0.22:
                    pm = P['窗帘白']
                elif r < 0.34:
                    pm = P['窗帘暖']
                elif r < 0.42:
                    pm = P['窗帘灰']
                elif r < 0.54:
                    pm = P['玻璃哑']
                elif r < 0.66:
                    pm = P['玻璃亮']
                else:
                    pm = P['玻璃']
                pane = add_quad(f'{name}_窗_{ci}_{f}',
                                [(x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1)],
                                pm, col)
                pane['unit'] = key
                pane['price'] = u['p']
                pane['sun'] = u['s']

                # 窗棂网格：两道竖框 + 一道横向中横档，替代原来的单根中缝
                for t in (1 / 3, 2 / 3):
                    mx2 = x0 + (x1 - x0) * t
                    add_box(f'{name}_竖棂_{ci}_{f}_{t:.2f}', mx2 - 0.045, mx2 + 0.045,
                            y - 0.05, b['y0'], z0, z1, P['窗框'], col)
                zt = z0 + (z1 - z0) * 0.62
                add_box(f'{name}_横档_{ci}_{f}', x0, x1, y - 0.05, b['y0'],
                        zt - 0.045, zt + 0.045, P['窗框'], col)

                if balconies:
                    # 阳台：挑板 + 玻璃栏板 + 金属扶手 + 侧向隔板。
                    # 改的是轮廓，这是让体量从"写字楼白盒子"变成住宅的关键。
                    bx0, bx1 = cx0 + 0.35, cx0 + UNIT_W - 0.35
                    by = b['y0'] - 1.55
                    add_beveled_box(f'{name}_阳台板_{ci}_{f}', bx0, bx1, by, b['y0'],
                                    zb + 0.02, zb + 0.18, P['线条'], col,
                                    bevel=.16, segments=5)
                    add_box(f'{name}_阳台地_{ci}_{f}', bx0 + 0.09, bx1 - 0.09,
                            by + 0.09, b['y0'], zb + 0.18, zb + 0.21, P['阳台地'], col)
                    add_quad(f'{name}_栏板_{ci}_{f}',
                             [(bx0 + .12, by, zb + 0.21), (bx1 - .12, by, zb + 0.21),
                              (bx1 - .12, by, zb + 1.28), (bx0 + .12, by, zb + 1.28)],
                             P['栏板'], col)
                    add_beveled_box(f'{name}_扶手_{ci}_{f}', bx0, bx1, by - 0.05, by + 0.05,
                                    zb + 1.28, zb + 1.36, P['金属'], col,
                                    bevel=.035, segments=3)
                    for sx in (bx0, bx1):
                        add_quad(f'{name}_侧板_{ci}_{f}_{sx:.1f}',
                                 [(sx, by + .12, zb + 0.21), (sx, b['y0'], zb + 0.21),
                                  (sx, b['y0'], zb + 1.28), (sx, by + .12, zb + 1.28)],
                                 P['栏板'], col)
                    # 宣传图低区阳台有细密竖向金属格栅；上层少量加入，避免每户都一模一样
                    if f <= 3 or rnd(key, 4) > .78:
                        for q in range(8):
                            gx = bx0 + .28 + q * (bx1 - bx0 - .56) / 7
                            add_box(f'{name}_格栅_{ci}_{f}_{q}', gx - .022, gx + .022,
                                    by - .025, by + .03, zb + .23, zb + 1.24,
                                    P['金属'], col)
                    # 空调外机：国内住宅立面最典型的"生活痕迹"，位置左右随户而异
                    if rnd(key, 1) > 0.22:
                        side = rnd(key, 2) > 0.5
                        ax = (bx0 + 0.28) if side else (bx1 - 0.98)
                        add_box(f'{name}_空调_{ci}_{f}', ax, ax + 0.70,
                                by + 0.10, by + 0.42, zb + 0.24, zb + 0.78,
                                P['空调'], col)

        for ci in range(len(cols)):
            cx0 = b['x0'] + ci * UNIT_W
            for f in floors:
                zb = (f - 1) * FLOOR_H
                add_quad(f'{name}_北窗_{ci}_{f}',
                         [(cx0 + 2.2, b['y1'] + 0.09, zb + 1.2),
                          (cx0 + UNIT_W - 2.2, b['y1'] + 0.09, zb + 1.2),
                          (cx0 + UNIT_W - 2.2, b['y1'] + 0.09, zb + 2.3),
                          (cx0 + 2.2, b['y1'] + 0.09, zb + 2.3)],
                         P['玻璃'], col)

        # 宣传图转角是弧形落地玻璃而非整片白山墙。
        # 这里先用两侧 4.2m 宽的包角玻璃近似；圆角挑檐负责把轮廓软化。
        for side, sx in (('西', b['x0'] - .09), ('东', b['x1'] + .09)):
            for f in floors:
                zb = (f - 1) * FLOOR_H
                q = [(sx, b['y0'] + .55, zb + .90),
                     (sx, b['y0'] + 4.75, zb + .90),
                     (sx, b['y0'] + 4.75, zb + 2.60),
                     (sx, b['y0'] + .55, zb + 2.60)]
                if side == '东':
                    q.reverse()
                add_quad(f'{name}_{side}转角窗_{f}', q, P['玻璃亮'], col)
                add_box(f'{name}_{side}转角框_{f}', sx - .04, sx + .04,
                        b['y0'] + 2.60, b['y0'] + 2.69,
                        zb + .90, zb + 2.60, P['窗框'], col)

    return scene


# ---------------- 光照 ----------------
def set_sun(az, alt, strength=2.6, angle_deg=0.53, warm=0.0, sky_strength=0.6):
    """warm∈[0,1]：给低角度阳光加暖色，用于黄昏气氛。"""
    for ob in list(bpy.data.objects):
        if ob.type == 'LIGHT':
            bpy.data.objects.remove(ob, do_unlink=True)

    lamp = bpy.data.lights.new('太阳', type='SUN')
    lamp.energy = strength
    lamp.angle = math.radians(angle_deg)
    # 暖度曲线放狠一些：低角度阳光实际色温约 3000–3500K，
    # 而 AgX 会把高光往白里推，所以源头必须给足暖色才看得出冷暖对比。
    lamp.color = (1.0, 1.0 - 0.30 * warm, 1.0 - 0.60 * warm)
    ob = bpy.data.objects.new('太阳', lamp)
    bpy.context.scene.collection.objects.link(ob)

    a, e = math.radians(az), math.radians(alt)
    to_sun = Vector((math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), math.sin(e)))
    # 瞄点必须与灯位共线，否则 look_at 会引入数度方向误差
    aim = Vector((0.0, BUILDINGS['8幢']['y0'], 0.0))
    ob.location = aim + to_sun * 600
    look_at(ob, aim)

    world = bpy.data.worlds.get('World') or bpy.data.worlds.new('World')
    bpy.context.scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputWorld')
    bg = nt.nodes.new('ShaderNodeBackground')
    sky = nt.nodes.new('ShaderNodeTexSky')
    try:
        # Blender 5.x 把原 NISHITA 改名为 MULTIPLE_SCATTERING
        opts = [i.identifier for i in sky.bl_rna.properties['sky_type'].enum_items]
        sky.sky_type = 'MULTIPLE_SCATTERING' if 'MULTIPLE_SCATTERING' in opts else opts[0]
        sky.sun_elevation = e
        sky.sun_rotation = -a          # 方位角以北为0顺时针，sun_rotation 以北为0逆时针
        if hasattr(sky, 'sun_disc'):
            sky.sun_disc = False
        for attr, val in (('air_density', 1.6), ('dust_density', 2.6 + 2.0 * warm),
                          ('ozone_density', 1.2)):
            if hasattr(sky, attr):
                setattr(sky, attr, val)
    except Exception as err:
        print('天空节点设置降级:', err, file=sys.stderr)
    bg.inputs['Strength'].default_value = sky_strength
    nt.links.new(sky.outputs[0], bg.inputs['Color'])
    nt.links.new(bg.outputs[0], out.inputs['Surface'])
    return ob


# ---------------- 相机 ----------------
def look_at(cam_ob, target, up=(0, 0, 1)):
    """相机看向 -Z、局部 X 右、Y 上。不能用 rotation_difference：
    它返回最短弧四元数，roll 不受控，会导致地平线倾斜。"""
    fwd = (Vector(target) - cam_ob.location).normalized()
    upv = Vector(up)
    right = fwd.cross(upv)
    if right.length < 1e-6:
        right = Vector((1, 0, 0))
    right.normalize()
    true_up = right.cross(fwd)
    cam_ob.rotation_euler = Matrix((
        (right.x, true_up.x, -fwd.x),
        (right.y, true_up.y, -fwd.y),
        (right.z, true_up.z, -fwd.z),
    )).to_euler()


def add_camera(loc, target, lens=45, ortho=None, dof=None):
    cam = bpy.data.cameras.new('相机')
    cam.lens = lens
    if ortho:
        cam.type = 'ORTHO'
        cam.ortho_scale = ortho
    ob = bpy.data.objects.new('相机', cam)
    ob.location = Vector(loc)
    bpy.context.scene.collection.objects.link(ob)
    bpy.context.scene.camera = ob
    look_at(ob, target)
    if dof:
        cam.dof.use_dof = True
        cam.dof.focus_distance = (Vector(target) - Vector(loc)).length
        cam.dof.aperture_fstop = dof
    return ob


def site_bbox():
    xs = [b['x0'] for b in BUILDINGS.values()] + [b['x1'] for b in BUILDINGS.values()]
    ys = [b['y0'] for b in BUILDINGS.values()] + [b['y1'] for b in BUILDINGS.values()]
    top = GEO['n_storey'] * FLOOR_H + GEO['parapet']
    return (min(xs), max(xs), min(ys), max(ys), 0.0, top)


def site_center():
    x0, x1, y0, y1, z0, z1 = site_bbox()
    return ((x0 + x1) / 2, (y0 + y1) / 2, z1 * 0.45), (x1 - x0, y1 - y0, z1)


def fit_camera(direction, lens=50, margin=1.08, target=None, res=(2560, 1440), dof=None):
    """沿 direction（目标→相机）放置相机，使场地包围盒 8 角点全部入画。
    斜视角下单纯按尺寸估距会严重取景过近，必须按角点反算。"""
    x0, x1, y0, y1, z0, z1 = site_bbox()
    tgt = Vector(target) if target else Vector(site_center()[0])
    corners = [Vector((x, y, z)) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]
    tan_h = (36.0 / 2) / lens
    tan_v = tan_h / (res[0] / res[1])
    fwd = Vector(direction).normalized()
    upv = Vector((0, 0, 1))
    right = fwd.cross(upv)
    if right.length < 1e-6:
        right = Vector((1, 0, 0))
    right.normalize()
    true_up = right.cross(fwd)
    d = 1.0
    for c in corners:
        v = c - tgt
        d = max(d, v.dot(fwd) + abs(v.dot(right)) / tan_h,
                v.dot(fwd) + abs(v.dot(true_up)) / tan_v)
    return add_camera(tgt + fwd * d * margin, tgt, lens=lens, dof=dof)


# ---------------- 渲染设置 ----------------
def setup_render(engine='CYCLES', res=(2560, 1440), samples=128,
                 film_transparent=False, exposure=0.0, contrast='Medium Contrast'):
    sc = bpy.context.scene
    if engine == 'CYCLES':
        try:
            bpy.ops.preferences.addon_enable(module='cycles')
        except Exception:
            pass
        sc.render.engine = 'CYCLES'
        prefs = bpy.context.preferences.addons['cycles'].preferences
        prefs.compute_device_type = 'METAL'
        prefs.get_devices()
        for d in prefs.devices:
            d.use = (d.type == 'METAL')
        sc.cycles.device = 'GPU'
        sc.cycles.samples = samples
        sc.cycles.use_denoising = True
        sc.cycles.max_bounces = 8
        sc.cycles.transmission_bounces = 6
        sc.cycles.glossy_bounces = 6
        print('[渲染设备] %s %s' % (prefs.compute_device_type,
                                 [d.name for d in prefs.devices if d.use]))
    else:
        sc.render.engine = 'BLENDER_EEVEE'
        for attr, val in (('taa_render_samples', samples), ('use_raytracing', True),
                          ('use_shadows', True), ('shadow_ray_count', 2)):
            if hasattr(sc.eevee, attr):
                setattr(sc.eevee, attr, val)
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.resolution_percentage = 100
    sc.render.film_transparent = film_transparent
    sc.render.image_settings.file_format = 'PNG'
    sc.render.image_settings.color_mode = 'RGBA' if film_transparent else 'RGB'
    vs = sc.view_settings
    # 注意：在 --background 下用 bl_rna 内省 view_transform / look 的枚举
    # 只会返回 ['NONE']（动态枚举的怪癖），据此判断会得出"AgX 不可用"的错误结论。
    # 正确做法是直接赋值并捕获异常。
    for cand in ('AgX', 'Filmic', 'Standard'):
        try:
            vs.view_transform = cand
            break
        except Exception:
            continue
    vs.exposure = exposure
    for cand in (contrast, f'AgX - {contrast}', 'None'):
        try:
            vs.look = cand
            break
        except Exception:
            continue
    print('[色彩管理] view_transform=%s look=%s exposure=%+.2f'
          % (vs.view_transform, vs.look, vs.exposure))
    return sc


def render_to(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    print('渲染完成 ->', path)
