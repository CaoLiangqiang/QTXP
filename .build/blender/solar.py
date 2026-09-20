#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""前滩尚品 · 冬至日照几何反推

两件事：
1. 用 NOAA 算法算上海冬至 9–15 时的太阳位置（自检：正午高度角应 ≈ 90−纬度−23.44）
2. 楼栋间距未知（没拿到总平面图），所以反过来用宣传图标注的日照时长去**拟合**间距：
   扫描候选间距，看哪个值最能复现各层的日照时长分布。

纯标准库，可用 `python3 .build/blender/solar.py` 单独运行。
结果写入 .build/blender/geometry.json 供 Blender 脚本使用。
"""
import json
import math
from datetime import datetime, timedelta
from pathlib import Path

# ---------------- 场地参数 ----------------
LAT, LON, TZ = 31.23, 121.47, 8          # 上海，北京时间 UTC+8
SOLSTICE = (2026, 12, 21)                 # 冬至
WIN_START, WIN_END = 9.0, 15.0            # 宣传图口径：冬至 9–15 时
STEP_MIN = 5                              # 采样步长（分钟）

FLOOR_H = 3.0                             # 层高 m
UNIT_W = 9.3                              # 单套开间 m（≈102.5m² / 11m 进深）
DEPTH = 11.0                              # 楼栋进深 m
PARAPET = 1.2                             # 女儿墙 m
N_STOREY = 9                              # 地上层数（实际层 1..9）
WIN_Z = 1.5                               # 窗台取值：层内中部

ROOT = Path(__file__).resolve().parents[2]
UNITS = json.loads((ROOT / '.build' / 'units.json').read_text(encoding='utf-8'))


# ---------------- 太阳位置（NOAA） ----------------
def julian_day(dt):
    y, m = dt.year, dt.month
    d = dt.day + (dt.hour + dt.minute / 60 + dt.second / 3600) / 24
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    return int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + d + b - 1524.5


def solar_pos(lat, lon, dt_utc):
    """返回 (方位角°从北顺时针, 高度角°)"""
    jc = (julian_day(dt_utc) - 2451545.0) / 36525.0
    gmls = (280.46646 + jc * (36000.76983 + jc * 0.0003032)) % 360
    gmas = 357.52911 + jc * (35999.05029 - 0.0001537 * jc)
    ecc = 0.016708634 - jc * (0.000042037 + 0.0000001267 * jc)
    ctr = (math.sin(math.radians(gmas)) * (1.914602 - jc * (0.004817 + 0.000014 * jc))
           + math.sin(math.radians(2 * gmas)) * (0.019993 - 0.000101 * jc)
           + math.sin(math.radians(3 * gmas)) * 0.000289)
    stl = gmls + ctr
    omega = 125.04 - 1934.136 * jc
    lam = stl - 0.00569 - 0.00478 * math.sin(math.radians(omega))
    sec = 21.448 - jc * (46.8150 + jc * (0.00059 - jc * 0.001813))
    e0 = 23 + (26 + sec / 60) / 60
    eps = e0 + 0.00256 * math.cos(math.radians(omega))
    decl = math.degrees(math.asin(math.sin(math.radians(eps)) * math.sin(math.radians(lam))))

    y = math.tan(math.radians(eps / 2)) ** 2
    eqt = 4 * math.degrees(
        y * math.sin(2 * math.radians(gmls))
        - 2 * ecc * math.sin(math.radians(gmas))
        + 4 * ecc * y * math.sin(math.radians(gmas)) * math.cos(2 * math.radians(gmls))
        - 0.5 * y * y * math.sin(4 * math.radians(gmls))
        - 1.25 * ecc * ecc * math.sin(2 * math.radians(gmas)))

    minutes = dt_utc.hour * 60 + dt_utc.minute + dt_utc.second / 60
    tst = (minutes + eqt + 4 * lon) % 1440
    ha = tst / 4 - 180
    rl, rd, rh = math.radians(lat), math.radians(decl), math.radians(ha)
    zen = math.acos(max(-1, min(1, math.sin(rl) * math.sin(rd) + math.cos(rl) * math.cos(rd) * math.cos(rh))))
    alt = 90 - math.degrees(zen)
    az = (180 + math.degrees(math.atan2(math.sin(rh),
                                        math.cos(rh) * math.sin(rl) - math.tan(rd) * math.cos(rl)))) % 360
    return az, alt


def sun_vector(az, alt):
    """+X 东, +Y 北, +Z 上。返回由地面指向太阳的单位向量。"""
    a, e = math.radians(az), math.radians(alt)
    return (math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), math.sin(e))


def timeline():
    """冬至 9–15 时的采样点：[(北京时间小时, 方位角, 高度角, 太阳向量)]"""
    out = []
    t = WIN_START
    while t <= WIN_END + 1e-9:
        h, mi = int(t), int(round((t - int(t)) * 60))
        local = datetime(*SOLSTICE, h, mi)
        utc = local - timedelta(hours=TZ)
        az, alt = solar_pos(LAT, LON, utc)
        out.append((t, az, alt, sun_vector(az, alt)))
        t += STEP_MIN / 60
    return out


# ---------------- 楼栋几何 ----------------
def buildings(gap_11_8, gap_8_5):
    """自南向北 11幢 → 8幢 → 5幢。返回 {名称: 包围盒与列信息}
    约定 +Y 为北，11幢 南立面位于 y=0。"""
    order = ['11幢', '8幢', '5幢']
    cols = {}
    for u in UNITS:
        cols.setdefault(u['b'], [])
        k = (u['u'], u['rm'])
        if k not in cols[u['b']]:
            cols[u['b']].append(k)

    top = N_STOREY * FLOOR_H + PARAPET
    out, y = {}, 0.0
    for i, name in enumerate(order):
        if i:
            y += DEPTH + (gap_11_8 if i == 1 else gap_8_5)
        w = len(cols[name]) * UNIT_W
        out[name] = dict(
            y0=y, y1=y + DEPTH,                      # 南面 / 北面
            x0=-w / 2, x1=w / 2, z0=0.0, z1=top,     # 东西居中
            cols=cols[name], width=w,
        )
    return out


def unit_point(bd, col_idx, floor):
    """某户南向窗中点（南立面外侧一点）"""
    x = bd['x0'] + (col_idx + 0.5) * UNIT_W
    return (x, bd['y0'] - 0.05, (floor - 1) * FLOOR_H + WIN_Z)


def ray_hits_box(o, d, b):
    """slab 法：射线是否与长方体相交（t>0）"""
    tmin, tmax = 0.0, 1e18
    for i, (lo, hi) in enumerate(((b['x0'], b['x1']), (b['y0'], b['y1']), (b['z0'], b['z1']))):
        if abs(d[i]) < 1e-12:
            if o[i] < lo or o[i] > hi:
                return False
            continue
        t1, t2 = (lo - o[i]) / d[i], (hi - o[i]) / d[i]
        if t1 > t2:
            t1, t2 = t2, t1
        tmin, tmax = max(tmin, t1), min(tmax, t2)
        if tmin > tmax:
            return False
    return tmax > 0


def sun_hours(bds, tl):
    """返回 {(楼栋, 单元, 室号, 实际层): 日照小时}"""
    span = WIN_END - WIN_START
    res = {}
    for u in UNITS:
        if u['p'] is None:
            continue
        bd = bds[u['b']]
        ci = bd['cols'].index((u['u'], u['rm']))
        p = unit_point(bd, ci, u['fr'])
        others = [v for k, v in bds.items() if k != u['b']]
        lit = 0
        for _, _, alt, sv in tl:
            if alt <= 0:
                continue
            if not any(ray_hits_box(p, sv, o) for o in others):
                lit += 1
        res[(u['b'], u['u'], u['rm'], u['fr'])] = lit / len(tl) * span
    return res


def floor_profile(vals, bname):
    """按楼层聚合成 {实际层: 平均小时}"""
    acc = {}
    for (b, _, _, f), v in vals.items():
        if b == bname:
            acc.setdefault(f, []).append(v)
    return {f: sum(v) / len(v) for f, v in sorted(acc.items())}


def observed_profile(bname):
    acc = {}
    for u in UNITS:
        if u['b'] == bname and u['p'] is not None:
            acc.setdefault(u['fr'], []).append(u['s'])
    return {f: sum(v) / len(v) for f, v in sorted(acc.items())}


# 宣传图对完全无遮挡的户一律标 5.5h（11幢 48/48 套均为 5.5），
# 而 6 小时窗口的理论上限就是 6.0 —— 说明 5.5 是它的封顶值。
# 因此模型值先按同一口径封顶再比较，否则拟合会被这个系统偏差带偏。
OBS_CAP = 5.5


def capped(v):
    return min(v, OBS_CAP)


def fit_gap(bname, tl, lo, hi, step, fixed):
    """扫描间距，返回 (最优间距, SSE, 该间距下的楼层剖面)"""
    obs = observed_profile(bname)
    best = None
    g = lo
    while g <= hi + 1e-9:
        bds = buildings(fixed if bname == '5幢' else g, g if bname == '5幢' else fixed)
        prof = floor_profile(sun_hours(bds, tl), bname)
        sse = sum((capped(prof.get(f, 0)) - o) ** 2 for f, o in obs.items())
        if best is None or sse < best[1]:
            best = (g, sse, prof)
        g += step
    return best


def report(bname, prof, obs, label=''):
    print(f'{label}')
    for f in sorted(obs, reverse=True):
        m = prof.get(f, 0)
        mark = '  ← 信息量所在' if obs[f] < OBS_CAP - 1e-9 else ''
        print(f'  {f}层  实测 {obs[f]:.2f} h   模型 {capped(m):.2f} h'
              f'（未封顶 {m:.2f}）{mark}')


def main():
    tl = timeline()
    noon = max(tl, key=lambda r: r[2])
    expect = 90 - LAT - 23.44
    print('=== 太阳位置自检 ===')
    print(f'冬至正午 高度角 {noon[2]:.2f}°  方位角 {noon[1]:.2f}°  （北京时间 {noon[0]:.2f} 时）')
    print(f'解析值 90−{LAT}−23.44 = {expect:.2f}°  偏差 {abs(noon[2]-expect):.2f}°')
    assert abs(noon[2] - expect) < 0.35, '太阳高度角与解析值偏差过大'
    print(f'9 时 高度角 {tl[0][2]:.2f}° 方位角 {tl[0][1]:.2f}°  |  '
          f'15 时 高度角 {tl[-1][2]:.2f}° 方位角 {tl[-1][1]:.2f}°')
    print(f'采样 {len(tl)} 点，步长 {STEP_MIN} 分钟')

    print('\n=== 反推 11幢 → 8幢 间距（依据 8幢 各层日照）===')
    g1, sse1, prof1 = fit_gap('8幢', tl, 12, 90, 1.0, 40)
    print(f'最优 {g1:.0f} m（封顶口径 SSE {sse1:.2f}）')
    report('8幢', prof1, observed_profile('8幢'))

    print('\n=== 反推 8幢 → 5幢 间距（依据 5幢 各层日照）===')
    g2, sse2, prof2 = fit_gap('5幢', tl, 12, 90, 1.0, g1)
    print(f'最优 {g2:.0f} m（封顶口径 SSE {sse2:.2f}）')
    report('5幢', prof2, observed_profile('5幢'))

    bds = buildings(g1, g2)
    print('\n=== 11幢 对照（最南，理应全程无遮挡）===')
    report('11幢', floor_profile(sun_hours(bds, tl), '11幢'), observed_profile('11幢'))
    out = dict(
        lat=LAT, lon=LON, tz=TZ, solstice=list(SOLSTICE),
        win_start=WIN_START, win_end=WIN_END, step_min=STEP_MIN,
        floor_h=FLOOR_H, unit_w=UNIT_W, depth=DEPTH, parapet=PARAPET,
        n_storey=N_STOREY, win_z=WIN_Z,
        gap_11_8=g1, gap_8_5=g2, sse_8=sse1, sse_5=sse2,
        noon_alt=noon[2], noon_az=noon[1],
        buildings={k: {kk: (vv if kk != 'cols' else [list(c) for c in vv])
                       for kk, vv in v.items()} for k, v in bds.items()},
        timeline=[dict(t=t, az=az, alt=alt) for t, az, alt, _ in tl],
    )
    p = Path(__file__).resolve().parent / 'geometry.json'
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'\n几何参数已写入 {p.name}')
    print(f"场地尺度：东西 {max(b['x1'] for b in bds.values())*2:.0f} m，"
          f"南北 {bds['5幢']['y1']:.0f} m，檐高 {bds['5幢']['z1']:.1f} m")


if __name__ == '__main__':
    main()
