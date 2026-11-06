"""Bake Operator（规范 §40-43）。

Bake 的职责：采样当前真实 evaluated Camera Matrix，Bake 成普通 Camera 关键帧。

正确流程：
    1. 逐帧采样 evaluated matrix_world（此时 rig 还在，读的是真实结果）
    2. 移除 rig（解除 Controller，Camera 恢复普通相机）
    3. 把采样结果写成 location + rotation_quaternion 关键帧（§43）

绝不重新用 Distance/Horizontal/Vertical 独立推算位置。
"""
import bpy

from ..core import rig, dolly_zoom


class CINE_OT_bake(bpy.types.Operator):
    bl_idname = "cine.bake"
    bl_label = "烘焙为关键帧"
    bl_description = "采样摄像机最终位姿，解除控制器后烘焙为普通相机关键帧；希区柯克启用时同时烘焙焦距"
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        obj = rig.resolve_camera(context)
        return obj is not None and obj.type == 'CAMERA' and obj.cine.enabled

    def execute(self, context):
        camera = rig.resolve_camera(context)
        rig.make_independent(context, camera)
        scene = context.scene
        start = scene.frame_start
        end = scene.frame_end
        depsgraph = context.evaluated_depsgraph_get()

        cur = scene.frame_current
        bake_lens = dolly_zoom.is_enabled(camera)

        # 1. 采样：逐帧读 evaluated matrix_world（真实结果，§40）
        samples = {}
        lenses = {}
        for frame in range(start, end + 1):
            scene.frame_set(frame)
            depsgraph.update()
            cam_eval = camera.evaluated_get(depsgraph)
            samples[frame] = cam_eval.matrix_world.copy()
            if bake_lens:
                lenses[frame] = cam_eval.data.lens

        # 2. 移除 rig（解除 Controller）
        rig.remove_rig(context, camera)

        # 3. 写关键帧（QUATERNION，§43）
        camera.rotation_mode = 'QUATERNION'
        for frame in range(start, end + 1):
            M = samples[frame]
            loc, rot, _scale = M.decompose()
            camera.matrix_world = M
            camera.keyframe_insert(data_path="location", frame=frame)
            camera.keyframe_insert(data_path="rotation_quaternion", frame=frame)

            if bake_lens:
                camera.data.lens = lenses[frame]
                camera.data.keyframe_insert(data_path='lens', frame=frame, group='Cine 希区柯克烘焙')

        scene.frame_set(cur)
        self.report({'INFO'}, f"已烘焙第 {start} 至 {end} 帧")
        return {'FINISHED'}


def register():
    bpy.utils.register_class(CINE_OT_bake)


def unregister():
    bpy.utils.unregister_class(CINE_OT_bake)
