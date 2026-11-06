"""原生 Curve 控制器外形：水平圆环、取景框与 +Y 前向箭头。"""
from math import cos, sin, tau
import bpy


def create_curve_data():
    """同一 Curve 数据中绘制多条折线，不生成网格或额外辅助对象。"""
    curve = bpy.data.curves.new('Cine_ControlShape', type='CURVE')
    curve.dimensions = '3D'
    curve.resolution_u = 1
    paths = [
        ([(0.8*cos(tau*i/48), 0.8*sin(tau*i/48), 0) for i in range(48)], True),
        ([(-0.45, 0, -0.3), (0.45, 0, -0.3), (0.45, 0, 0.3), (-0.45, 0, 0.3)], True),
        ([(0, 0, 0), (0, 1.4, 0)], False),
        ([(-0.2, 1.1, 0), (0, 1.4, 0), (0.2, 1.1, 0)], False),
        ([(-1, 0, 0), (1, 0, 0)], False),
    ]
    for points, cyclic in paths:
        spline = curve.splines.new('POLY')
        spline.points.add(len(points)-1)
        for point, coordinate in zip(spline.points, points):
            point.co = (*coordinate, 1)
        spline.use_cyclic_u = cyclic
    return curve
