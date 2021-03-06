import bpy


class UVTOOLKIT_PT_uv_sync(bpy.types.Panel):
    bl_label = "UV Sync"
    bl_idname = "UVTOOLKIT_PT_uv_sync"
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "UV Toolkit"

    def draw(self, context):
        layout = self.layout
        layout.operator("uv.toolkit_sync_mode", text="Toggle UV Sync", icon='UV_SYNC_SELECT')


class UVTOOLKIT_PT_uv_sync_settings(bpy.types.Panel):
    bl_label = "UV Sync settings"
    bl_parent_id = "UVTOOLKIT_PT_uv_sync"
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        addon_prefs = context.preferences.addons["uv_toolkit"].preferences
        layout.label(text="Auto select mesh")
        layout.prop(addon_prefs, 'uv_sync_auto_select', expand=True)
        layout.label(text="Sync selection mode")
        layout.prop(addon_prefs, 'uv_sync_selection_mode', expand=True)


class UVTOOLKIT_PT_tools(bpy.types.Panel):
    bl_label = "Tools"
    bl_idname = "UVTOOLKIT_PT_tools"
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "UV Toolkit"

    def draw(self, context):
        layout = self.layout

        layout.operator("uv.toolkit_unwrap_selected", text="Unwrap Selected", icon='SELECT_SUBTRACT')
        layout.operator("uv.toolkit_quad_unwrap", text="Quad Unwrap", icon='CON_SAMEVOL')
        layout.operator("uv.toolkit_align_island", text="Align Island", icon='CON_LOCLIMIT')
        layout.operator("uv.toolkit_rip_faces_move", text="Rip Faces", icon='MOD_OPACITY')
        layout.label(text="Shading")
        col = layout.column(align=True)
        col.operator("uv.toolkit_sharp_edges_from_uv_islands", text="Smooth from UV Islands")
        prop = col.operator("uv.seams_from_islands", text="Sharp Edges Only")
        prop.mark_seams, prop.mark_sharp = False, True
        layout.label(text="Seams")
        col = layout.column(align=True)
        prop = col.operator("uv.seams_from_islands", icon='MOD_EDGESPLIT')
        prop.mark_seams, prop.mark_sharp = True, False
        col.operator("uv.toolkit_boundary_seam")
        col.operator("uv.toolkit_mirror_seam")
        col.label(text="Transform")
        col = layout.column(align=True)
        row = col.row(align=True)
        row.scale_x = 3.0
        prop = row.operator("uv.toolkit_move_islands", text="", icon='SORT_DESC')
        prop.move_uv = 0, 1, 0
        row = col.row(align=True)
        split = row.split(align=True)
        prop = split.operator("uv.toolkit_move_islands", text="", icon='BACK')
        prop.move_uv = -1, 0, 0
        prop = split.operator("uv.toolkit_move_islands", text="", icon='SORT_ASC')
        prop.move_uv = 0, -1, 0
        prop = split.operator("uv.toolkit_move_islands", text="", icon='FORWARD')
        prop.move_uv = 1, 0, 0
        row = layout.row(align=True)
        row.operator("uv.toolkit_rotate_uv_islands", text="Rotate –90°").angle = -1.5708
        row.operator("uv.toolkit_rotate_uv_islands", text="Rotate +90°").angle = 1.5708
        layout.label(text="Mirror")
        row = layout.row(align=True)
        prop = row.operator("uv.toolkit_mirror_uv", text="X")
        prop.x, prop.y, prop.z = True, False, False
        prop = row.operator("uv.toolkit_mirror_uv", text="Y")
        prop.x, prop.y, prop.z = False, True, False
        row = layout.row()
        row.operator("mesh.faces_mirror_uv", text="Copy Mirrored UV Coords")


class UVTOOLKIT_PT_display(bpy.types.Panel):
    bl_label = "Display"
    bl_idname = "UVTOOLKIT_PT_display"
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "UV Toolkit"

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        row.operator("uv.toolkit_toggle_texture_mode", text="Show Texture in Viewport", icon='UV_DATA')
        row = layout.row(align=True)
        row.operator("uv.toolkit_change_checker_grid", text="Color Grid").checker_grid_type = 'COLOR_GRID'
        row.operator("uv.toolkit_change_checker_grid", text="Checker Grid").checker_grid_type = 'UV_GRID'
        layout.operator("uv.toolkit_disable_selected_checker_materials", text="Disable selected materials", icon='NODE_COMPOSITING')


class UVTOOLKIT_PT_checker_map(bpy.types.Panel):
    bl_label = "Checker Map"
    bl_idname = "UVTOOLKIT_PT_checker_map"
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "UV Toolkit"

    def draw(self, context):
        uv_toolkit = context.scene.uv_toolkit
        layout = self.layout
        # row = layout.row(align=True)
        col = layout.column(align=True)
        row = col.row(align=True)
        split = row.split(align=True)
        split.prop(uv_toolkit, "checker_map_width")
        split.prop(uv_toolkit, "checker_map_height")
        row = col.row(align=True)
        row .operator("uv.toolkit_custom_sizes_checker_map", icon="UV")
        layout.label(text="Remove")
        row = layout.row()
        row.operator("uv.toolkit_remove_all_checker_maps", text="Remove All Checker Maps", icon='TRASH')


class UVTOOLKIT_PT_settings(bpy.types.Panel):
    bl_label = "Checker Map settings"
    bl_parent_id = "UVTOOLKIT_PT_checker_map"
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        addon_prefs = context.preferences.addons["uv_toolkit"].preferences
        layout.label(text="Auto assign texture in UV Editor")
        layout.prop(addon_prefs, 'assign_image', expand=True)
        layout.label(text="Default checker style")
        layout.prop(addon_prefs, 'checker_type', expand=True)
        layout.label(text="Use flat shading")
        layout.prop(addon_prefs, 'use_flat_shading', expand=True)


class UVTOOLKIT_PT_square(bpy.types.Panel):
    bl_label = "Square"
    bl_parent_id = "UVTOOLKIT_PT_checker_map"
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        prop = row.operator("uv.toolkit_create_checker_map", text="64x64")
        prop.width, prop.height = 64, 64
        prop = row.operator("uv.toolkit_create_checker_map", text="128x128")
        prop.width, prop.height = 128, 128
        row = layout.row()
        prop = row.operator("uv.toolkit_create_checker_map", text="256x256")
        prop.width, prop.height = 256, 256
        prop = row.operator("uv.toolkit_create_checker_map", text="512x512")
        prop.width, prop.height = 512, 512
        row = layout.row()
        prop = row.operator("uv.toolkit_create_checker_map", text="1024x1024")
        prop.width, prop.height = 1024, 1024
        prop = row.operator("uv.toolkit_create_checker_map", text="2048x2048")
        prop.width, prop.height = 2048, 2048
        row = layout.row()
        prop = row.operator("uv.toolkit_create_checker_map", text="4096x4096")
        prop.width, prop.height = 4096, 4096
        prop = row.operator("uv.toolkit_create_checker_map", text="8192x8192")
        prop.width, prop.height = 8192, 8192


class UVTOOLKIT_PT_horizontal_rectangle(bpy.types.Panel):
    bl_label = "Horizontal Rectangle"
    bl_parent_id = "UVTOOLKIT_PT_checker_map"
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        prop = row.operator("uv.toolkit_create_checker_map", text="64x32")
        prop.width, prop.height = 64, 32
        prop = row.operator("uv.toolkit_create_checker_map", text="128x64")
        prop.width, prop.height = 128, 64
        row = layout.row()
        prop = row.operator("uv.toolkit_create_checker_map", text="256x128")
        prop.width, prop.height = 256, 128
        prop = row.operator("uv.toolkit_create_checker_map", text="512x256")
        prop.width, prop.height = 512, 256
        row = layout.row()
        prop = row.operator("uv.toolkit_create_checker_map", text="1024x512")
        prop.width, prop.height = 1024, 512
        prop = row.operator("uv.toolkit_create_checker_map", text="2048x1024")
        prop.width, prop.height = 2048, 1024
        row = layout.row()
        prop = row.operator("uv.toolkit_create_checker_map", text="4096x2048")
        prop.width, prop.height = 4096, 2048
        prop = row.operator("uv.toolkit_create_checker_map", text="8192x4096")
        prop.width, prop.height = 8192, 4096


class UVTOOLKIT_PT_vertical_rectangle(bpy.types.Panel):
    bl_label = "Vertical Rectangle"
    bl_parent_id = "UVTOOLKIT_PT_checker_map"
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        row = layout.row()
        prop = row.operator("uv.toolkit_create_checker_map", text="32x64")
        prop.width, prop.height = 32, 64
        prop = row.operator("uv.toolkit_create_checker_map", text="64x128")
        prop.width, prop.height = 64, 128
        row = layout.row()
        prop = row.operator("uv.toolkit_create_checker_map", text="128x256")
        prop.width, prop.height = 128, 256
        prop = row.operator("uv.toolkit_create_checker_map", text="256x512")
        prop.width, prop.height = 256, 512
        row = layout.row()
        prop = row.operator("uv.toolkit_create_checker_map", text="512x1024")
        prop.width, prop.height = 512, 1024
        prop = row.operator("uv.toolkit_create_checker_map", text="1024x2048")
        prop.width, prop.height = 1024, 2048
        row = layout.row()
        prop = row.operator("uv.toolkit_create_checker_map", text="2048x4096")
        prop.width, prop.height = 2048, 4096
        prop = row.operator("uv.toolkit_create_checker_map", text="4096x8192")
        prop.width, prop.height = 4096, 8192


class UVTOOLKIT_PT_help(bpy.types.Panel):
    bl_label = "Help"
    bl_idname = "UVTOOLKIT_PT_help"
    bl_space_type = 'IMAGE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "UV Toolkit"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        layout.operator("uv.toolkit_hotkeys", icon='TEXT')
        layout.label(text="Support Me on:")
        layout.operator("wm.url_open", text="Gumroad").url = "https://gumroad.com/alexbel"
        layout.operator("wm.url_open", text="PayPal").url = "https://paypal.me/belyakovalexander"
