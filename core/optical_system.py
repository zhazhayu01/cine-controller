"""Optical System —— 只影响 Camera Data，绝不修改 Camera Transform。

参数：
    Lens / Sensor / Shift / DOF / Focus Target / Focus Distance / F-Stop

规则（规范 §6 / §7 / §8）：
    - 只能写 camera.data 相关属性。
    - Focus Target 严格与 Camera Transform 解耦。
    - Focus Target 变化绝不得触发 rig rebuild / preserve_pose / set_origin。
"""
from mathutils import Vector


def apply_focus_to_camera(camera_obj, focus_target=None, focus_distance=None, f_stop=None) -> None:
    """把 Focus 相关参数写入 Camera Data DOF。

    Focus Target 直接绑定到 camera.data.dof.focus_object（规范 §7），
    绝不经过 Helper Transform / Camera Transform。
    """
    if camera_obj is None or camera_obj.data is None:
        return
    cam = camera_obj.data
    dof = cam.dof

    # 绑定 focus_object 需要 camera 是 DATA 类型
    if focus_target is not None:
        dof.focus_object = focus_target
    elif focus_target is None and "focus_object" in dir(dof):
        # 显式解绑时置 None
        dof.focus_object = None

    if focus_distance is not None:
        dof.focus_distance = float(focus_distance)

    if f_stop is not None:
        dof.aperture_fstop = float(f_stop)


def apply_lens_to_camera(camera_obj, lens=None, sensor_width=None, shift_x=None, shift_y=None) -> None:
    """写入 Lens / Sensor / Shift，全部只动 camera.data。"""
    if camera_obj is None or camera_obj.data is None:
        return
    cam = camera_obj.data

    if lens is not None:
        cam.lens = float(lens)
    if sensor_width is not None:
        cam.sensor_width = float(sensor_width)
    if shift_x is not None:
        cam.shift_x = float(shift_x)
    if shift_y is not None:
        cam.shift_y = float(shift_y)
