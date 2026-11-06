"""将空间计算编译成摄像机内部的原生标量驱动器，不创建场景对象。

中间结果按 RNA 属性显式连接，使依赖图负责目标运动、关键帧和子帧求值。
表达式限定为 Blender 的简单表达式；不注册 Python 驱动函数或更新回调。
"""
import re

PREFIX = '_cine2_'
FUNCTIONS = {'sin', 'cos', 'sqrt', 'max', 'min', 'acos', 'abs', 'if', 'else', 'and'}


class DriverGraph:
    """只在绑定时构建的表达式清单，运行时由 Blender 求值。"""

    def __init__(self):
        self.sources = {}
        self.nodes = []
        self.outputs = []

    def input(self, name, path, fallback=0.0):
        self.sources[name] = (path, fallback)
        return name

    def node(self, name, expression):
        names = set(re.findall(r'\b[A-Za-z_]\w*\b', expression)) - FUNCTIONS
        # 科学计数法中的 e 不是变量。
        names.discard('e')
        unknown = names - self.sources.keys()
        if unknown or len(expression) > 255:
            raise ValueError(f'内部表达式无效：{name}, {unknown}, 长度={len(expression)}')
        bindings = {key: self.sources[key] for key in sorted(names)}
        self.nodes.append((PREFIX + name, expression, bindings))
        return self.input(name, f'["{PREFIX}{name}"]')

    def output(self, path, index, expression):
        names = set(re.findall(r'\b[A-Za-z_]\w*\b', expression))
        self.outputs.append((path, index, expression, {key: self.sources[key] for key in names}))

    def quaternion_product(self, name, a, b):
        """Hamilton 乘积；顺序与 mathutils 的 a @ b 相同。"""
        aw, ax, ay, az = a
        bw, bx, by, bz = b
        expressions = (
            f'{aw}*{bw}-{ax}*{bx}-{ay}*{by}-{az}*{bz}',
            f'{aw}*{bx}+{ax}*{bw}+{ay}*{bz}-{az}*{by}',
            f'{aw}*{by}-{ax}*{bz}+{ay}*{bw}+{az}*{bx}',
            f'{aw}*{bz}+{ax}*{by}-{ay}*{bx}+{az}*{bw}',
        )
        return tuple(self.node(name + str(i), expr) for i, expr in enumerate(expressions))

    def rotation_matrix(self, name, q):
        w, x, y, z = q
        expressions = (
            (f'1-2*({y}*{y}+{z}*{z})', f'2*({x}*{y}-{w}*{z})', f'2*({x}*{z}+{w}*{y})'),
            (f'2*({x}*{y}+{w}*{z})', f'1-2*({x}*{x}+{z}*{z})', f'2*({y}*{z}-{w}*{x})'),
            (f'2*({x}*{z}-{w}*{y})', f'2*({y}*{z}+{w}*{x})', f'1-2*({x}*{x}+{y}*{y})'),
        )
        return tuple(tuple(self.node(f'{name}{i}{j}', e) for j, e in enumerate(row))
                     for i, row in enumerate(expressions))


def build_graph(controller_space=False):
    """生成 Orbit → 基准朝向 → Offset → Aim 混合 → 本地旋转。"""
    g = DriverGraph()
    for name, path in (('h', 'horizontal'), ('v', 'vertical'), ('d', 'distance'),
                       ('pan', 'pan'), ('tilt', 'tilt'), ('roll', 'roll'), ('blend', 'aim_influence')):
        g.input(name, 'cine.' + path)
    for i in range(3):
        g.input('o' + str(i), f'cine.offset[{i}]')
        # 空目标采用显式配置的世界原点；目标删除也不会留下无效驱动器。
        # RNA 矩阵属性路径按列索引，平移在第 4 列；与 Python Matrix[i][3] 不同。
        g.input('root' + str(i), f'cine.origin.matrix_world[3][{i}]')
        g.input('fallback' + str(i), f'cine.origin_fallback[{i}]')
        g.input('target' + str(i), f'cine.aim_target.matrix_world[3][{i}]')
    g.input('hasroot', 'cine.origin.matrix_world[3][3]')
    g.input('hasaim', 'cine.aim_target.matrix_world[3][3]')
    inverse = None
    if controller_space:
        # 摄像机挂在可见曲线下；外部目标的世界坐标先转换为曲线本地坐标。
        for i in range(3):
            for j in range(3):
                g.input(f'c{i}{j}', f'cine.controller.matrix_world[{j}][{i}]', float(i == j))
            g.input(f'ct{i}', f'cine.controller.matrix_world[3][{i}]')
        g.node('det', 'c00*(c11*c22-c12*c21)-c01*(c10*c22-c12*c20)+c02*(c10*c21-c11*c20)')
        g.node('den', 'det if abs(det)>1e-12 else (1e-12 if det>=0 else -1e-12)')
        cofactors = (
            ('c11*c22-c12*c21', 'c02*c21-c01*c22', 'c01*c12-c02*c11'),
            ('c12*c20-c10*c22', 'c00*c22-c02*c20', 'c02*c10-c00*c12'),
            ('c10*c21-c11*c20', 'c01*c20-c00*c21', 'c00*c11-c01*c10'),
        )
        inverse = tuple(tuple(g.node(f'inv{i}{j}', f'({expression})/den')
                              for j, expression in enumerate(row)) for i, row in enumerate(cofactors))
    base = tuple(g.input('b' + str(i), f'cine.base_rotation[{i}]', float(i == 0)) for i in range(4))
    # Z 水平旋转再 X 垂直旋转的四元数。
    orbit = tuple(g.node('orb' + str(i), e) for i, e in enumerate((
        'cos(h/2)*cos(v/2)', 'cos(h/2)*sin(v/2)',
        'sin(h/2)*sin(v/2)', 'sin(h/2)*cos(v/2)')))
    orientation = g.quaternion_product('pre', orbit, base)
    rotation = g.rotation_matrix('r', orientation)
    orbit_position = ('d*sin(h)*cos(v)', '-d*cos(h)*cos(v)', '-d*sin(v)')
    position = []
    for i in range(3):
        root_expression = '+'.join(f'{inverse[i][j]}*(root{j}-ct{j})' for j in range(3)) if inverse else f'root{i}'
        g.node('origin' + str(i), f'({root_expression}) if hasroot else fallback{i}')
        r = rotation[i]
        position.append(g.node('pos' + str(i),
            f'origin{i}+({orbit_position[i]})+{r[0]}*o0+{r[1]}*o1-{r[2]}*o2'))

    # 世界朝向：-Z 指向目标、+Y 朝向世界上方，极点退化时使用世界 Y。
    for i in range(3):
        target_expression = '+'.join(f'{inverse[i][j]}*(target{j}-ct{j})' for j in range(3)) if inverse else f'target{i}'
        g.node('dir' + str(i), f'({target_expression})-{position[i]}')
    g.node('length', 'sqrt(dir0*dir0+dir1*dir1+dir2*dir2)')
    for i in range(3):
        g.node('f' + str(i), f'dir{i}/max(length,1e-12)')
    g.node('pole', 'abs(f2)>0.999999')
    g.node('rx', '-f2 if pole else f1')
    g.node('ry', '0 if pole else -f0')
    g.node('rz', 'f0 if pole else 0')
    g.node('rlen', 'sqrt(rx*rx+ry*ry+rz*rz)')
    for axis in ('x', 'y', 'z'):
        g.node('right' + axis, f'r{axis}/max(rlen,1e-12)')
    # up = right × forward。
    g.node('upx', 'righty*f2-rightz*f1')
    g.node('upy', 'rightz*f0-rightx*f2')
    g.node('upz', 'rightx*f1-righty*f0')
    for i, row in enumerate((('rightx', 'upx', '-f0'),
                             ('righty', 'upy', '-f1'),
                             ('rightz', 'upz', '-f2'))):
        for j, value in enumerate(row):
            g.node(f'm{i}{j}', value)
    # 选取最大四元数分量，避免 180° 朝向时 trace 法除零。
    terms = ('1+m00+m11+m22', '1+m00-m11-m22', '1-m00+m11-m22', '1-m00-m11+m22')
    for i, term in enumerate(terms):
        g.node('t' + str(i), term)
    g.node('branch', '0 if t0>=max(t1,t2,t3) else (1 if t1>=max(t2,t3) else (2 if t2>=t3 else 3))')
    g.node('s', '2*sqrt(max(1e-12,max(t0,t1,t2,t3)))')
    rows = (
        ('s/4', '(m21-m12)/s', '(m02-m20)/s', '(m10-m01)/s'),
        ('(m21-m12)/s', 's/4', '(m01+m10)/s', '(m02+m20)/s'),
        ('(m02-m20)/s', '(m01+m10)/s', 's/4', '(m12+m21)/s'),
        ('(m10-m01)/s', '(m02+m20)/s', '(m12+m21)/s', 's/4'),
    )
    aimed = tuple(g.node('aim' + str(i),
        f'{rows[0][i]} if branch==0 else ({rows[1][i]} if branch==1 else ({rows[2][i]} if branch==2 else {rows[3][i]}))')
        for i in range(4))
    g.node('dot', '+'.join(f'{a}*{b}' for a, b in zip(orientation, aimed)))
    g.node('angle', 'acos(min(1,abs(dot)))')
    g.node('weight', 'blend if hasaim and length>1e-10 else 0')
    g.node('wa', '1-weight if angle<1e-6 else sin((1-weight)*angle)/max(sin(angle),1e-12)')
    g.node('wb', 'weight if angle<1e-6 else sin(weight*angle)/max(sin(angle),1e-12)')
    mixed = tuple(g.node('mix' + str(i), f'wa*{a}+wb*{b}*(1 if dot>=0 else -1)')
                  for i, (a, b) in enumerate(zip(orientation, aimed)))
    # XYZ 欧拉角：tilt(X)、pan(Y)、-roll(Z)，与旧控制器顺序一致。
    local = tuple(g.node('local' + str(i), e) for i, e in enumerate((
        'cos(roll/2)*cos(pan/2)*cos(tilt/2)-sin(roll/2)*sin(pan/2)*sin(tilt/2)',
        'cos(roll/2)*cos(pan/2)*sin(tilt/2)+sin(roll/2)*sin(pan/2)*cos(tilt/2)',
        'cos(roll/2)*sin(pan/2)*cos(tilt/2)-sin(roll/2)*cos(pan/2)*sin(tilt/2)',
        '-sin(roll/2)*cos(pan/2)*cos(tilt/2)-cos(roll/2)*sin(pan/2)*sin(tilt/2)')))
    final = g.quaternion_product('out', mixed, local)
    for i in range(3):
        g.output('delta_location', i, position[i])
        g.output('location', i, '0')
        g.output('scale', i, '1')
    for i in range(4):
        g.output('delta_rotation_quaternion', i, final[i])
        g.output('rotation_quaternion', i, str(int(i == 0)))
    return g
