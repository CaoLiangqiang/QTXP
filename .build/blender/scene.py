# -*- coding: utf-8 -*-
"""前滩尚品 · Blender 场景构建（供 stills / sun_study / turntable 复用）

坐标约定：+X 东，+Y 北，+Z 上，单位米。11幢 南立面位于 y=0。
几何来自 geometry.json（由 solar.py 用日照数据反推楼间距后写出）。

只用 bpy 数据 API（from_pydata / bpy.data.*），不依赖 bpy.ops 的上下文，
因此在 --background 下行为稳定。
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


# ---------------- 工具 ----------------
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


def clear_scene():
    for coll in (bpy.data.objects, bpy.data.meshes, bpy.data.materials,
                 bpy.data.lights, bpy.data.cameras):
        for item in list(coll):
            coll.remove(item)


def add_box(name, x0, x1, y0, y1, z0, z1, mat=None, parent_col=None):
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
    (parent_col or bpy.context.scene.collection).objects.link(ob)
    return ob


def add_quad(name, pts, mat=None, parent_col=None):
    me = bpy.data.meshes.new(name)
    me.from_pydata(pts, [], [(0, 1, 2, 3)])
    me.validate()
    me.update()
    ob = bpy.data.objects.new(name, me)
    if mat:
        ob.data.materials.append(mat)
    (parent_col or bpy.context.scene.collection).objects.link(ob)
    return ob


def set_input(node, names, value):
    """Principled BSDF 的输入名在各版本间有变动，按候选名依次尝试。"""
    for n in names:
        if n in node.inputs:
            node.inputs[n].default_value = value
            return True
    return False


def make_mat(name, color, rough=0.5, metal=0.0, transmit=0.0, emit=None, emit_str=0.0):
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
    set_input(bsdf, ['IOR'], 1.45)
    if emit:
        set_input(bsdf, ['Emission Color', 'Emission'], emit)
        set_input(bsdf, ['Emission Strength'], emit_str)
    if transmit > 0:
        m.use_backface_culling = False
        try:
            m.blend_method = 'BLEND'
        except Exception:
            pass
    return m


# ---------------- 场景 ----------------
def build(mode='arch', metric='price'):
    """mode: 'arch' 写实建筑材质 / 'data' 窗面按数据着色"""
    clear_scene()
    scene = bpy.context.scene

    # ---- 材质 ----
    m_ground = make_mat('地面', hex_rgba('#6b6f68'), rough=0.92)
    m_facade = make_mat('外墙', hex_rgba('#d8d3c8'), rough=0.62)
    m_facade_d = make_mat('外墙深', hex_rgba('#b9b2a4'), rough=0.68)
    m_podium = make_mat('基座', hex_rgba('#5c5a55'), rough=0.75)
    m_slab = make_mat('楼板线条', hex_rgba('#efeae0'), rough=0.5)
    m_glass = make_mat('玻璃', hex_rgba('#20313d'), rough=0.06, metal=0.0, transmit=0.85)
    m_frame = make_mat('窗框', hex_rgba('#2e3338'), rough=0.4, metal=0.7)
    m_para = make_mat('女儿墙', hex_rgba('#c8c2b6'), rough=0.6)

    # ---- 地面 ----
    span = 220
    ymid = BUILDINGS['5幢']['y1'] / 2
    add_box('地面', -span, span, ymid - span, ymid + span, -0.4, 0.0, m_ground)

    # ---- 数据索引 ----
    by_key = {}
    for u in UNITS:
        by_key[(u['b'], u['u'], u['rm'], u['fr'])] = u
    valid = [u for u in UNITS if u['p'] is not None]
    ext = {
        'price': (min(u['p'] for u in valid), max(u['p'] for u in valid)),
        'total': (min(u['t'] for u in valid), max(u['t'] for u in valid)),
        'area': (min(u['a'] for u in valid), max(u['a'] for u in valid)),
    }

    data_mats = {}

    def unit_mat(u):
        if mode != 'data':
            return m_glass
        if metric == 'sun':
            hx = SUN_COLOR.get(u['s'], '#888888')
        else:
            lo, hi = ext[metric]
            key = {'price': 'p', 'total': 't', 'area': 'a'}[metric]
            hx = ramp_hex(RAMP, (u[key] - lo) / (hi - lo))
        if hx not in data_mats:
            data_mats[hx] = make_mat('数据_' + hx, hex_rgba(hx), rough=0.28,
                                     emit=hex_rgba(hx), emit_str=0.32)
        return data_mats[hx]

    # ---- 楼栋 ----
    for name in ORDER:
        b = BUILDINGS[name]
        cols = [tuple(c) for c in b['cols']]
        floors = sorted({u['fr'] for u in UNITS if u['b'] == name})
        min_f = min(floors)
        roof = GEO['n_storey'] * FLOOR_H

        col = bpy.data.collections.new(name)
        scene.collection.children.link(col)

        # 主体：按层分段，交替微差外墙色，避免大面积单一色板
        for f in range(1, GEO['n_storey'] + 1):
            z0, z1 = (f - 1) * FLOOR_H, f * FLOOR_H
            mat = m_podium if f < min_f else (m_facade if f % 2 else m_facade_d)
            add_box(f'{name}_体_{f}', b['x0'], b['x1'], b['y0'], b['y1'], z0, z1,
                    mat, col)
            # 楼板线条：只向南北外挑，东西向不外扩（否则山墙侧会出现台阶状轮廓）
            add_box(f'{name}_线_{f}', b['x0'], b['x1'],
                    b['y0'] - 0.28, b['y1'] + 0.28, z1 - 0.22, z1, m_slab, col)

        # 女儿墙
        add_box(f'{name}_女儿墙', b['x0'] - 0.1, b['x1'] + 0.1,
                b['y0'] - 0.1, b['y1'] + 0.1, roof, roof + GEO['parapet'], m_para, col)
        # 屋面
        add_box(f'{name}_屋面', b['x0'], b['x1'], b['y0'], b['y1'],
                roof - 0.05, roof + 0.05, m_facade_d, col)

        # 南立面窗：每户一片
        for ci, ck in enumerate(cols):
            cx0 = b['x0'] + ci * UNIT_W
            for f in floors:
                u = by_key.get((name, ck[0], ck[1], f))
                if not u or u['p'] is None:
                    continue
                zb = (f - 1) * FLOOR_H
                x0, x1 = cx0 + 0.75, cx0 + UNIT_W - 0.75
                z0, z1 = zb + 0.95, zb + 2.55
                y = b['y0'] - 0.10
                # 窗洞深色底
                add_box(f'{name}_洞_{ci}_{f}', x0 - 0.12, x1 + 0.12, y, b['y0'],
                        z0 - 0.12, z1 + 0.12, m_frame, col)
                pane = add_quad(f'{name}_窗_{ci}_{f}',
                                [(x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1)],
                                unit_mat(u), col)
                pane['unit'] = f"{u['b']}|{u['u']}|{u['rm']}|{u['fr']}"
                pane['price'] = u['p']
                pane['sun'] = u['s']
                # 竖向分隔窗框
                add_box(f'{name}_框_{ci}_{f}', (x0 + x1) / 2 - 0.05, (x0 + x1) / 2 + 0.05,
                        y - 0.04, b['y0'], z0, z1, m_frame, col)

        # 北立面小窗（丰富体量，不参与数据着色）
        for ci in range(len(cols)):
            cx0 = b['x0'] + ci * UNIT_W
            for f in floors:
                zb = (f - 1) * FLOOR_H
                add_quad(f'{name}_北窗_{ci}_{f}',
                         [(cx0 + 2.2, b['y1'] + 0.08, zb + 1.2),
                          (cx0 + UNIT_W - 2.2, b['y1'] + 0.08, zb + 1.2),
                          (cx0 + UNIT_W - 2.2, b['y1'] + 0.08, zb + 2.3),
                          (cx0 + 2.2, b['y1'] + 0.08, zb + 2.3)],
                         m_glass, col)

    return scene


def set_sun(az, alt, strength=2.0, angle_deg=0.53):
    """按方位角/高度角布置太阳，并让天空与之一致。"""
    for ob in list(bpy.data.objects):
        if ob.type == 'LIGHT':
            bpy.data.objects.remove(ob, do_unlink=True)

    lamp = bpy.data.lights.new('太阳', type='SUN')
    lamp.energy = strength
    lamp.angle = math.radians(angle_deg)
    ob = bpy.data.objects.new('太阳', lamp)
    bpy.context.scene.collection.objects.link(ob)

    a, e = math.radians(az), math.radians(alt)
    to_sun = Vector((math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), math.sin(e)))
    # 瞄点必须与灯位共线：location = aim + to_sun*d，这样 look_at 得到的
    # 出射方向精确等于 -to_sun。若瞄点偏离灯位所在射线，会引入数度方向误差。
    aim = Vector((0.0, BUILDINGS['8幢']['y0'], 0.0))
    ob.location = aim + to_sun * 600
    look_at(ob, aim)

    # 世界：Nishita 天空
    world = bpy.data.worlds.get('World') or bpy.data.worlds.new('World')
    bpy.context.scene.world = world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputWorld')
    bg = nt.nodes.new('ShaderNodeBackground')
    sky = nt.nodes.new('ShaderNodeTexSky')
    try:
        # Blender 5.x 把原 NISHITA 改名为 MULTIPLE_SCATTERING，
        # 枚举为 ('SINGLE_SCATTERING','MULTIPLE_SCATTERING','PREETHAM','HOSEK_WILKIE')
        opts = [i.identifier for i in sky.bl_rna.properties['sky_type'].enum_items]
        sky.sky_type = 'MULTIPLE_SCATTERING' if 'MULTIPLE_SCATTERING' in opts else opts[0]
        sky.sun_elevation = e
        # Blender 的 sun_rotation 以 +Y(北) 为 0、绕天顶逆时针为正；
        # 方位角以北为 0、顺时针为正，故取负。
        sky.sun_rotation = -a
        if hasattr(sky, 'sun_disc'):
            sky.sun_disc = False
        for attr, val in (('air_density', 1.5), ('dust_density', 2.4), ('ozone_density', 1.0)):
            if hasattr(sky, attr):
                setattr(sky, attr, val)
    except Exception as err:
        print('天空节点设置降级:', err, file=sys.stderr)
    bg.inputs['Strength'].default_value = 1.0
    nt.links.new(sky.outputs[0], bg.inputs['Color'])
    nt.links.new(bg.outputs[0], out.inputs['Surface'])
    return ob


def look_at(cam_ob, target, up=(0, 0, 1)):
    """构造朝向矩阵：相机看向 -Z、局部 X 为右、Y 为上。
    不能用 rotation_difference —— 它返回最短弧四元数，roll 不受控，会导致地平线倾斜。"""
    fwd = (Vector(target) - cam_ob.location).normalized()
    upv = Vector(up)
    right = fwd.cross(upv)
    if right.length < 1e-6:                     # 正俯视时退化，另取一个右向
        right = Vector((1, 0, 0))
    right.normalize()
    true_up = right.cross(fwd)
    cam_ob.rotation_euler = Matrix((
        (right.x, true_up.x, -fwd.x),
        (right.y, true_up.y, -fwd.y),
        (right.z, true_up.z, -fwd.z),
    )).to_euler()


def site_bbox():
    xs = [b['x0'] for b in BUILDINGS.values()] + [b['x1'] for b in BUILDINGS.values()]
    ys = [b['y0'] for b in BUILDINGS.values()] + [b['y1'] for b in BUILDINGS.values()]
    top = GEO['n_storey'] * FLOOR_H + GEO['parapet']
    return (min(xs), max(xs), min(ys), max(ys), 0.0, top)


def site_center():
    x0, x1, y0, y1, z0, z1 = site_bbox()
    return ((x0 + x1) / 2, (y0 + y1) / 2, z1 * 0.45), (x1 - x0, y1 - y0, z1)


def fit_camera(direction, lens=50, margin=1.08, target=None, res=(2560, 1440)):
    """沿 direction（由目标指向相机）放置相机，使场地包围盒 8 个角点全部入画。
    与网页版同一套思路：斜视角下单纯按尺寸估距会严重取景过近。"""
    x0, x1, y0, y1, z0, z1 = site_bbox()
    tgt = Vector(target) if target else Vector(site_center()[0])
    corners = [Vector((x, y, z)) for x in (x0, x1) for y in (y0, y1) for z in (z0, z1)]

    sensor = 36.0
    aspect = res[0] / res[1]
    tan_h = (sensor / 2) / lens
    tan_v = tan_h / aspect

    fwd = Vector(direction).normalized()          # 目标 → 相机
    upv = Vector((0, 0, 1))
    right = fwd.cross(upv)
    if right.length < 1e-6:
        right = Vector((1, 0, 0))
    right.normalize()
    true_up = right.cross(fwd)

    d = 1.0
    for c in corners:
        v = c - tgt
        z = v.dot(fwd)
        d = max(d, z + abs(v.dot(right)) / tan_h, z + abs(v.dot(true_up)) / tan_v)
    return add_camera(tgt + fwd * d * margin, tgt, lens=lens)


def add_camera(loc, target, lens=45, ortho=None):
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
    return ob


def setup_render(engine='CYCLES', res=(2560, 1440), samples=128, film_transparent=False):
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
        print('[渲染设备] 类型=%s 启用=%s' % (
            prefs.compute_device_type,
            [(d.name, d.type) for d in prefs.devices if d.use]))
        sc.cycles.samples = samples
        sc.cycles.use_denoising = True
        sc.cycles.max_bounces = 6
        sc.cycles.transmission_bounces = 4
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
    sc.view_settings.view_transform = 'AgX' if 'AgX' in [
        t.identifier for t in sc.view_settings.bl_rna.properties['view_transform'].enum_items
    ] else 'Filmic'
    sc.view_settings.look = 'None'
    return sc


def render_to(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    bpy.context.scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    print('渲染完成 ->', path)
