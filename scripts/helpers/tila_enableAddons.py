import bpy

modules =   (
            'mesh_f2',
            'TextTools',
            'io_import_images_as_planes',
            'mesh_f2',
            'fspy_blender',
            'object_print3d_utils',
            'mesh_looptools',
            'MACHIN3tools',
            'mesh_mesh_align_plus',
            'node_wrangler',
            'node_presets',
            'mesh_snap_utilities_line',
            'Principled-Baker',
            'object_boolean_tools',
            'optiloops',
            'DNoise',
            'RenderBurst',
            'magic_uv',
            'photographer',
            'transfer_vertex_order',
            'PolyQuilt',
            'ExtraInfo',
            'EasyHDRI',
            'MeasureIt-ARCH',
            'retopoflow',
            'add_curve_extra_objects',
            'io_scene_fbx',
            'io_scene_obj',
            'io_scene_x3d',
            'io_scene_gltf2',
            'io_mesh_stl',
            'io_curve_svg',
            'io_mesh_ply',
            'io_mesh_uv_layout',
            'object_collection_manager',
            'space_view3d_copy_attributes',
            'space_view3d_modifier_tools',
            'EdgeFlow',
            'mesh_tools',
            'space_view3d_align_tools',
            'cycles',
            'Polycount',
            'mira_tools',
            'uvpackmaster2',
            'uv_toolkit',
            'lineup_maker',
            'Tila_Config'
            )

def register():
    # Enabling addons
    for m in modules:
        bpy.ops.preferences.addon_enable(module=m)

def unregister():
    # disabling addons
    for m in modules:
        bpy.ops.preferences.addon_disable(module=m)


if __name__ == '__main__':
    register()