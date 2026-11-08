"""用标准库绘制线框 SVG，并生成抗锯齿透明 PNG；无需图形依赖。"""
from pathlib import Path
from math import cos, sin, pi
import struct
import zlib

ROOT = Path(__file__).resolve().parents[1] / 'ui' / 'assets'
SHAPES = {}
STROKE = 2.4


def arc(cx, cy, rx, ry, start=0, end=360, steps=32):
    return [(cx+rx*cos(t*pi/180), cy+ry*sin(t*pi/180))
            for t in (start+(end-start)*i/steps for i in range(steps+1))]


def camera(x=9, y=13, size=1):
    return [[(x, y), (x+10*size, y), (x+10*size, y+7*size), (x, y+7*size), (x, y)],
            [(x+10*size, y+2*size), (x+14*size, y), (x+14*size, y+7*size), (x+10*size, y+5*size)]]


def arrow(a, b, size=3):
    dx, dy = b[0]-a[0], b[1]-a[1]
    length = max((dx*dx+dy*dy)**0.5, 1e-9)
    dx, dy = dx/length, dy/length
    return [[a, b], [(b[0]-size*(dx-dy*0.65), b[1]-size*(dy+dx*0.65)), b,
                     (b[0]-size*(dx+dy*0.65), b[1]-size*(dy-dx*0.65))]]


def curved_arrow(points):
    return [points]+arrow(points[-2], points[-1], 3.5)[1:]


def spline():
    controls = ((5, 24), (15, 24), (17, 8), (27, 8))
    return [tuple((1-t)**3*controls[0][axis]+3*(1-t)**2*t*controls[1][axis]
                  +3*(1-t)*t*t*controls[2][axis]+t**3*controls[3][axis]
                  for axis in (0, 1)) for t in (i/40 for i in range(41))]


def normalize(paths):
    """所有图标使用相同光学中心和 24 单位主体尺寸，留白由网格统一。"""
    xs = [x for points in paths for x, _y in points]
    ys = [y for points in paths for _x, y in points]
    cx, cy = (min(xs)+max(xs))/2, (min(ys)+max(ys))/2
    factor = 24/max(max(xs)-min(xs), max(ys)-min(ys))
    return [[(16+(x-cx)*factor, 16+(y-cy)*factor) for x, y in points] for points in paths]


def design():
    SHAPES['camera'] = camera(5, 10, 1.3)
    SHAPES['create'] = camera(3, 13, 1.1)+[[(24, 3), (24, 11)], [(20, 7), (28, 7)]]
    SHAPES['origin'] = [arc(16, 16, 6, 6), [(16, 3), (16, 10)], [(16, 22), (16, 29)],
                        [(3, 16), (10, 16)], [(22, 16), (29, 16)]]
    SHAPES['import_pose'] = camera(2, 4, 0.65)+arrow((6, 19), (23, 19))+[[(21, 11), (28, 11), (28, 27), (12, 27), (12, 24)]]
    SHAPES['focus'] = [[(4, 11), (4, 4), (11, 4)], [(21, 4), (28, 4), (28, 11)],
                       [(28, 21), (28, 28), (21, 28)], [(11, 28), (4, 28), (4, 21)], arc(16, 16, 5, 5)]
    SHAPES['aperture'] = [arc(16, 16, 12, 12)]
    for i in range(6):
        angle = i*pi/3
        SHAPES['aperture'].append([(16+12*cos(angle), 16+12*sin(angle)),
                                   (16+5*cos(angle+0.45), 16+5*sin(angle+0.45)),
                                   (16+5*cos(angle+pi/3+0.45), 16+5*sin(angle+pi/3+0.45))])
    SHAPES['dolly'] = camera(2, 12, 0.65)+[[(16, 12), (28, 5), (28, 25), (16, 18)], [(20, 13), (28, 11)], [(20, 17), (28, 19)]]+arrow((3, 28), (17, 28))
    SHAPES['subject'] = [[(6, 10), (16, 4), (26, 10), (26, 23), (16, 29), (6, 23), (6, 10)],
                         [(6, 10), (16, 16), (26, 10)], [(16, 16), (16, 29)]]
    frame = [[(4, 6), (28, 6), (28, 26), (4, 26), (4, 6)]]
    SHAPES['thirds'] = frame+[[(12, 6), (12, 26)], [(20, 6), (20, 26)], [(4, 13), (28, 13)], [(4, 19), (28, 19)]]
    SHAPES['center'] = frame+[[(16, 10), (16, 22)], [(10, 16), (22, 16)]]
    SHAPES['safe'] = frame+[[(8, 10), (24, 10), (24, 22), (8, 22), (8, 10)]]
    SHAPES['mask'] = frame+[[(8, 10), (24, 10), (24, 22), (8, 22), (8, 10)], [(4, 6), (8, 10)],
                          [(28, 6), (24, 10)], [(28, 26), (24, 22)], [(4, 26), (8, 22)]]
    # 小尺寸只保留主语义，避免用微型相机、路径和链环堆叠成难辨的图形。
    SHAPES['distance'] = [[(5, 8), (5, 24)], [(27, 8), (27, 24)]]+arrow((8, 16), (24, 16))+arrow((24, 16), (8, 16))
    SHAPES['orbit_h'] = curved_arrow(arc(16, 16, 12, 6, -45, 270))+[arc(16, 16, 1.8, 1.8)]
    SHAPES['orbit_v'] = curved_arrow(arc(16, 16, 6, 12, 45, 360))+[arc(16, 16, 1.8, 1.8)]
    SHAPES['pan'] = camera(7, 18, 0.9)+curved_arrow(arc(16, 14, 11, 8, 195, 345))
    SHAPES['tilt'] = camera(4, 12, 0.9)+curved_arrow(arc(18, 16, 10, 12, -70, 70))
    SHAPES['roll'] = [[(12, 12), (20, 12), (20, 20), (12, 20), (12, 12)]]+curved_arrow(arc(16, 16, 12, 12, 45, 340))
    SHAPES['lens'] = [arc(16, 16, 12, 12), arc(16, 16, 6, 6)]
    SHAPES['focus_distance'] = [[(4, 10), (4, 22)], arc(24, 16, 4, 4)]+arrow((6, 16), (17, 16))
    SHAPES['dof'] = [[(6, 10), (6, 22)], [(16, 5), (16, 27)], [(26, 10), (26, 22)]]
    SHAPES['path'] = [spline(), arc(5, 24, 1.2, 1.2), arc(27, 8, 1.2, 1.2)]
    # 链环独立表达绑定，不再和样条图形重叠。
    SHAPES['path_bind'] = []
    for cx, cy in ((11, 21), (21, 11)):
        SHAPES['path_bind'].append([(cx+(x-16)*cos(-pi/4)-(y-16)*sin(-pi/4),
                                     cy+(x-16)*sin(-pi/4)+(y-16)*cos(-pi/4))
                                    for x, y in arc(16, 16, 8, 4)])
    SHAPES['path_follow'] = curved_arrow(spline())
    SHAPES['progress'] = [[(4, 16), (11, 16)], [(21, 16), (28, 16)],
                          [(4, 11), (4, 21)], [(28, 11), (28, 21)], arc(16, 16, 4, 4)]
    for name, paths in SHAPES.items():
        SHAPES[name] = normalize(paths)


def png(paths, rgb, size=64, supersample=4):
    scale = size*supersample/32
    width = size*supersample
    mask = bytearray(width*width)
    radius = STROKE/2*scale
    for points in paths:
        for a, b in zip(points, points[1:]):
            ax, ay, bx, by = a[0]*scale, a[1]*scale, b[0]*scale, b[1]*scale
            dx, dy = bx-ax, by-ay
            length = dx*dx+dy*dy
            for y in range(max(0, int(min(ay, by)-radius-1)), min(width, int(max(ay, by)+radius+2))):
                for x in range(max(0, int(min(ax, bx)-radius-1)), min(width, int(max(ax, bx)+radius+2))):
                    t = max(0, min(1, ((x+0.5-ax)*dx+(y+0.5-ay)*dy)/length)) if length else 0
                    if (x+0.5-ax-t*dx)**2+(y+0.5-ay-t*dy)**2 <= radius*radius:
                        mask[y*width+x] = 255
    raw = bytearray()
    for y in range(size):
        raw.append(0)
        for x in range(size):
            alpha = sum(mask[(y*supersample+j)*width+x*supersample+i]
                        for j in range(supersample) for i in range(supersample))//(supersample*supersample)
            raw.extend((*rgb, alpha))
    def chunk(kind, data):
        return struct.pack('>I', len(data))+kind+data+struct.pack('>I', zlib.crc32(kind+data))
    return (b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR', struct.pack('>2I5B', size, size, 8, 6, 0, 0, 0))
            +chunk(b'IDAT', zlib.compress(bytes(raw), 9))+chunk(b'IEND', b''))


def main():
    design()
    for theme, rgb in (('dark', (204, 204, 204)), ('light', (58, 58, 58))):
        directory = ROOT/theme
        directory.mkdir(parents=True, exist_ok=True)
        for name, paths in SHAPES.items():
            (directory/(name+'.png')).write_bytes(png(paths, rgb))
    source = ROOT/'svg'
    source.mkdir(exist_ok=True)
    for name, paths in SHAPES.items():
        lines = ''.join('<polyline points="'+' '.join(f'{x:.2f},{y:.2f}' for x, y in points)+'"/>' for points in paths)
        (source/(name+'.svg')).write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32">'
            f'<g fill="none" stroke="#666666" stroke-width="{STROKE}" stroke-linecap="round" stroke-linejoin="round">'
            +lines+'</g></svg>', encoding='utf-8')
    print(f'已生成 {len(SHAPES)} 个图标，每个包含深浅两版 PNG 及 SVG 源文件')


if __name__ == '__main__':
    main()
