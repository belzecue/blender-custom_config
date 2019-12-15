
import multiprocessing

from .prefs import get_prefs
from .operator import *
from .operator_islands import *
from .operator_box import *
from .utils import *
from .presets import *
from .labels import UvpLabels
from .register import UVP2_OT_SelectUvpEngine

import bpy


class UVP2_UL_DeviceList(bpy.types.UIList):

    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        dev_name = str(item.name)

        row = layout.row()
        icon_id = 'NONE'

        if not item.supported:
            dev_name += ' ' + UvpLabels.FEATURE_NOT_SUPPORTED_MSG
            icon_id = UvpLabels.FEATURE_NOT_SUPPORTED_ICON

        row.label(text=dev_name, icon=icon_id)


class UVP2_PT_MainBase(bpy.types.Panel):
    bl_idname = 'UVP2_PT_MainBase'
    bl_label = 'UVPackmaster2'
    bl_context = ''

    def draw(self, context):
        layout = self.layout
        prefs = get_prefs()
        scene_props = context.scene.uvp2_props
        demo_suffix = " (DEMO)" if prefs.FEATURE_demo else ''

        row = layout.row()
        row.label(text=prefs.label_message)

        if not prefs.uvp_initialized:
            row.operator(UVP2_OT_UvpSetupHelp.bl_idname, icon='HELP', text='')

        row = layout.row()

        row2 = row.row()
        row2.enabled = False
        row2.prop(prefs, 'uvp_path')
        select_icon = 'FILEBROWSER' if is_blender28() else 'FILE_FOLDER'
        row.operator(UVP2_OT_SelectUvpEngine.bl_idname, icon=select_icon, text='')

        col = layout.column(align=True)
        col.separator()

        if in_debug_mode():
            box = col.box()
            col2 = box.column(align=True)
            col2.label(text="Debug options:")
            row = col2.row(align=True)
            row.prop(prefs, "write_to_file")
            row = col2.row(align=True)
            row.prop(prefs, "simplify_disable")
            row = col2.row(align=True)
            row.prop(prefs, "wait_for_debugger")
            row = col2.row(align=True)
            row.prop(prefs, "seed")
            row = col2.row(align=True)
            row.prop(prefs, "test_param")
            col.separator()

        row = col.row(align=True)
        row.enabled = prefs.FEATURE_overlap_check

        row.operator(UVP2_OT_OverlapCheckOperator.bl_idname)
        if not prefs.FEATURE_overlap_check:
            row.label(text=UvpLabels.FEATURE_NOT_SUPPORTED_MSG)

        col.operator(UVP2_OT_MeasureAreaOperator.bl_idname)

        # Validate operator

        row = col.row(align=True)
        row.enabled = prefs.FEATURE_validation

        row.operator(UVP2_OT_ValidateOperator.bl_idname, text=UVP2_OT_ValidateOperator.bl_label + demo_suffix)
        if not prefs.FEATURE_validation:
            row.label(text=UvpLabels.FEATURE_NOT_SUPPORTED_MSG)

        row = col.row(align=True)
        row.scale_y = 1.75
        row.operator(UVP2_OT_PackOperator.bl_idname, text=UVP2_OT_PackOperator.bl_label + demo_suffix)

        col.separator()
        col.label(text='Option presets:')
        row = col.row(align=True)
        row.operator(UVP2_OT_SavePreset.bl_idname)
        row.operator(UVP2_OT_LoadPreset.bl_idname)
        
        
class UVP2_PT_PackingDeviceBase(bpy.types.Panel):
    bl_label = 'Packing Devices'
    bl_context = ''
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        prefs = get_prefs()
        scene_props = context.scene.uvp2_props
        col = layout.column(align=True)

        col.template_list("UVP2_UL_DeviceList", "", prefs, "dev_array",
                          prefs, "sel_dev_idx")

        # Multi device
        box = col.box()
        box.enabled = prefs.FEATURE_multi_device_pack

        row = box.row()

        if not prefs.FEATURE_multi_device_pack:
            row.prop(prefs, "DISABLED_multi_device_pack")
            row.label(text=UvpLabels.FEATURE_NOT_SUPPORTED_MSG)
        else:
            row.prop(scene_props, "multi_device_pack")


class UVP2_PT_BasicOptionsBase(bpy.types.Panel):
    bl_label = 'Basic Options'
    bl_context = ''

    def draw(self, context):
        layout = self.layout
        prefs = get_prefs()
        scene_props = context.scene.uvp2_props
        col = layout.column(align=True)

        col.prop(prefs, "thread_count")
        col.prop(scene_props, "margin")
        col.prop(scene_props, "precision")

        # Rotation Resolution
        box = col.box()
        box.enabled = prefs.FEATURE_island_rotation

        row = box.row()

        if not prefs.FEATURE_island_rotation:
            row.prop(prefs, "DISABLED_rot_enable")
            row.label(text=UvpLabels.FEATURE_NOT_SUPPORTED_MSG)
        else:
            row.prop(scene_props, "rot_enable")

        row = box.row()
        row.enabled = scene_props.rot_enable
        row.prop(scene_props, "prerot_disable")

        row = col.row(align=True)
        row.enabled = scene_props.rot_enable
        row.prop(scene_props, "rot_step")

        # Post scale disable
        box = col.box()
        row = box.row()
        row.prop(scene_props, "postscale_disable")

        # Overlap check
        box = col.box()
        box.enabled = prefs.FEATURE_overlap_check
        row = box.row()

        if not prefs.FEATURE_overlap_check:
            row.prop(prefs, "DISABLED_overlap_check")
            row.label(text=UvpLabels.FEATURE_NOT_SUPPORTED_MSG)
        else:
            row.prop(scene_props, "overlap_check")

        # Area measure
        box = col.box()
        row = box.row()
        row.prop(scene_props, "area_measure")

        # Pre validate
        pre_validate_name = UvpLabels.PRE_VALIDATE_NAME
        if prefs.FEATURE_demo:
            pre_validate_name += ' (DEMO)'

        box = col.box()
        box.enabled = prefs.FEATURE_validation
        row = box.row()

        if not prefs.FEATURE_validation:
            row.prop(prefs, "DISABLED_pre_validate", text=pre_validate_name)
            row.label(text=UvpLabels.FEATURE_NOT_SUPPORTED_MSG)
        else:
            row.prop(scene_props, "pre_validate", text=pre_validate_name)


class UVP2_PT_IslandRotStepBase(bpy.types.Panel):
    bl_label = 'Island Rotation Step'
    bl_context = ''
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        prefs = get_prefs()
        scene_props = context.scene.uvp2_props

        panel_enabled = True

        if not prefs.FEATURE_island_rotation_step:
            layout.label(text=UvpLabels.FEATURE_NOT_SUPPORTED_MSG)
            panel_enabled = False
        elif not scene_props.rot_enable:
            layout.label(text='Enable rotations in Basic Options in order to activate this panel', icon='ERROR')
            panel_enabled = False

        col = layout.column(align=True)
        col.enabled = panel_enabled

        box = col.box()
        row = box.row()
        row.prop(scene_props, "island_rot_step_enable")
        row.operator(UVP2_OT_IslandRotStepHelp.bl_idname, icon='HELP', text='')

        box = col.box()
        box.enabled = scene_props.island_rot_step_enable
        col2 = box.column(align=True)

        row = col2.row(align=True)
        row.prop(scene_props, "island_rot_step")

        row = col2.row(align=True)
        row.operator(UVP2_OT_SetRotStepIslandParam.bl_idname)

        col2.separator()
        row = col2.row(align=True)
        row.operator(UVP2_OT_ResetRotStepIslandParam.bl_idname)

        row = col2.row(align=True)
        row.operator(UVP2_OT_ShowRotStepIslandParam.bl_idname)


class UVP2_PT_HeuristicBase(bpy.types.Panel):
    bl_label = 'Heuristic'
    bl_context = ''
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        prefs = get_prefs()
        scene_props = context.scene.uvp2_props
        col = layout.column(align=True)

        # Heuristic search
        box = col.box()
        box.enabled = prefs.FEATURE_heuristic_search

        row = box.row()

        if not prefs.FEATURE_heuristic_search:
            row.prop(prefs, "DISABLED_heuristic_enable")
            row.label(text=UvpLabels.FEATURE_NOT_SUPPORTED_MSG)
        else:
            row.prop(scene_props, "heuristic_enable")

        row = col.row(align=True)
        row.enabled = prefs.heuristic_enabled(scene_props)
        row.prop(scene_props, "heuristic_search_time")

        # Advanced Heuristic
        box = col.box()
        box.enabled = prefs.advanced_heuristic_available(scene_props)
        row = box.row()

        if not prefs.FEATURE_advanced_heuristic:
            row.prop(prefs, "DISABLED_advanced_heuristic")
            row.label(text=UvpLabels.FEATURE_NOT_SUPPORTED_MSG)
        else:
            row.prop(scene_props, "advanced_heuristic")


class UVP2_PT_NonSquarePackingBase(bpy.types.Panel):
    bl_label = 'Non-Square Packing'
    bl_context = ''
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        prefs = get_prefs()
        scene_props = context.scene.uvp2_props
        col = layout.column(align=True)

        # Tex ratio
        box = col.box()
        box.enabled = prefs.pack_ratio_supported()
        row = box.row()

        if not box.enabled:
            row.prop(prefs, "DISABLED_tex_ratio")
            row.label(text=UvpLabels.FEATURE_NOT_SUPPORTED_MSG)
        else:
            row.prop(scene_props, "tex_ratio")

        col.separator()
        row = col.row(align=True)
        row.operator(UVP2_OT_AdjustIslandsToTexture.bl_idname)
        row.operator(UVP2_OT_NonSquarePackingHelp.bl_idname, icon='HELP', text='')

        row = col.row(align=True)
        row.operator(UVP2_OT_UndoIslandsAdjustemntToTexture.bl_idname)

class UVP2_PT_AdvancedOptionsBase(bpy.types.Panel):
    bl_label = 'Advanced Options'
    bl_context = ''
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        prefs = get_prefs()
        scene_props = context.scene.uvp2_props
        demo_suffix = " (DEMO)" if prefs.FEATURE_demo else ''
        col = layout.column(align=True)

        # Pack to others
        box = col.box()
        box.enabled = prefs.FEATURE_pack_to_others
        row = box.row()

        if not prefs.FEATURE_pack_to_others:
            row.prop(prefs, "DISABLED_pack_to_others")
            row.label(text=UvpLabels.FEATURE_NOT_SUPPORTED_MSG)
        else:
            row.prop(scene_props, "pack_to_others")

        # Lock overlapping
        box = col.box()
        box.enabled = prefs.FEATURE_lock_overlapping
        row = box.row()

        if not prefs.FEATURE_lock_overlapping:
            row.prop(prefs, "DISABLED_lock_overlapping")
            row.label(text=UvpLabels.FEATURE_NOT_SUPPORTED_MSG)
        else:
            row.prop(scene_props, "lock_overlapping")

        # Grouped pack
        box = col.box()
        box.enabled = True

        col2 = box.column(align=True)
        col2.label(text=UvpLabels.PACK_MODE_NAME + ':')
        row = col2.row(align=True)

        row.prop(scene_props, "pack_mode", text='')

        if prefs.pack_to_tiles(scene_props):
            row = col2.row(align=True)
            row.prop(scene_props, "tiles_in_row")

        if prefs.grouping_enabled(scene_props):
            col2 = box.column()
            col2.label(text=UvpLabels.GROUP_METHOD_NAME + ':')

            row = col2.row()
            row.prop(scene_props, "group_method", text='')
            col2.separator()

        # Similarity threshold
        row = col.row(align=True)
        row.prop(scene_props, "similarity_threshold")
        row.operator(UVP2_OT_SimilarityDetectionHelp.bl_idname, icon='HELP', text='')

        row = col.row(align=True)
        row.operator(UVP2_OT_SelectSimilarOperator.bl_idname, text=UVP2_OT_SelectSimilarOperator.bl_label + demo_suffix)

        row = col.row(align=True)
        row.operator(UVP2_OT_AlignSimilarOperator.bl_idname, text=UVP2_OT_AlignSimilarOperator.bl_label + demo_suffix)

        col.separator()
        col.label(text='Pixel Margin Options:')

        # Pixel margin
        row = col.row(align=True)
        row.prop(scene_props, "pixel_margin")
        row.operator(UVP2_OT_PixelMarginHelp.bl_idname, icon='HELP', text='')

        pm_col = col.column(align=True)
        pm_col.enabled = prefs.pixel_margin_enabled(scene_props)

        # Pixel padding
        row = pm_col.row(align=True)
        row.prop(scene_props, "pixel_padding")

        # Pixel Margin Adjust Time
        row = pm_col.row(align=True)
        row.prop(scene_props, "pixel_margin_adjust_time")

        # Pixel Margin Tex Size
        row = pm_col.row(align=True)
        row.prop(scene_props, "pixel_margin_tex_size")

        if prefs.pack_ratio_enabled(scene_props):
            row.enabled = False
            pm_col.label(text='Active texture dimensions are used to calculate pixel margin', icon='ERROR')


class UVP2_PT_TargetBoxBase(bpy.types.Panel):
    bl_label = 'Packing Box'
    bl_context = ''
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        prefs = get_prefs()
        scene_props = context.scene.uvp2_props
        col = layout.column(align=True)
        col.enabled = prefs.FEATURE_target_box

        row = col.row(align=True)
        if prefs.target_box_enable:
            row.operator(UVP2_OT_DisableTargetBox.bl_idname)
        else:
            row.operator(UVP2_OT_EnableTargetBox.bl_idname)

        if not prefs.FEATURE_target_box:
            row.label(text=UvpLabels.FEATURE_NOT_SUPPORTED_MSG)

        box = col.box()
        box.enabled = prefs.target_box_enable
        col2 = box.column(align=True)

        row = col2.row(align=True)
        row.operator(UVP2_OT_DrawTargetBox.bl_idname)

        row = col2.row(align=True)
        row.operator(UVP2_OT_LoadTargetBox.bl_idname)

        col2.separator()
        col2.label(text='Set packing box to UDIM tile:')
        row = col2.row(align=True)
        row.prop(scene_props, "target_box_tile_x")
        row.prop(scene_props, "target_box_tile_y")

        row = col2.row(align=True)
        row.operator(UVP2_OT_SetTargetBoxTile.bl_idname)

        col2.separator()
        col2.label(text='Packing box coordinates:')
        row = col2.row(align=True)
        row.prop(scene_props, "target_box_p1_x")

        row = col2.row(align=True)
        row.prop(scene_props, "target_box_p1_y")

        row = col2.row(align=True)
        row.prop(scene_props, "target_box_p2_x")

        row = col2.row(align=True)
        row.prop(scene_props, "target_box_p2_y")


class UVP2_PT_WarningsBase(bpy.types.Panel):
    bl_label = 'Warnings'
    bl_context = ''
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        prefs = get_prefs()
        scene_props = context.scene.uvp2_props
        col = layout.column(align=True)

        active_dev = prefs.dev_array[prefs.sel_dev_idx] if prefs.sel_dev_idx < len(prefs.dev_array) else None
        warnings = []

        if prefs.thread_count < multiprocessing.cpu_count():
            warnings.append('Thread Count value is lower than the number of cores in your system - consider increasing that parameter in order to increase the packer speed')

        if not scene_props.rot_enable:
            warnings.append('Packing is not optimal for most UV maps with island rotations disabled. Disable rotations only when packing a UV map with a huge number of small islands')

        if prefs.FEATURE_island_rotation and scene_props.prerot_disable:
            warnings.append('Pre-rotation usually optimizes packing, disable it only if you have a good reason')

        if scene_props.postscale_disable:
            warnings.append("When the 'Post-Scaling Disable' option is on, islands won't be adjusted to fit the unit UV square after packing is done")

        if prefs.pack_ratio_supported():
            try:
                ratio = get_active_image_ratio(context)

                if not scene_props.tex_ratio and ratio != 1.0:
                    warnings.append("The active texture is non-square, but the 'Use Texture Ratio' option is disabled. Did you forget to enable it?")

                if scene_props.tex_ratio and ratio < 1.0:
                    warnings.append('Packing is slower when packing into a vertically oriented texture. Consider changing the texture orientation')
            except:
                pass

        if prefs.pixel_margin_enabled(scene_props) and prefs.packing_scales_islands(scene_props) and scene_props.pixel_margin_adjust_time > 1:
            warnings.append("The pixel margin adjustment time set to one second should be enough for a usual UV map. Set the adjustment time to greater values only if the resulting pixel margin after packing is not accurate enough for you.")

        for warn in warnings:
            box = col.box()

            warn_split = split_by_chars(warn, 40)
            if len(warn_split) > 0:
                box.separator()
                for warn_part in warn_split:
                    box.label(text=warn_part)
                box.separator()


class UVP2_PT_StatisticsBase(bpy.types.Panel):
    bl_label = 'Statistics'
    bl_context = ''
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout
        prefs = get_prefs()
        scene_props = context.scene.uvp2_props
        col = layout.column(align=True)
        col.label(text='Last operation statistics:')
        col.separator()

        if prefs.stats_area >= 0.0:
            box = col.box()
            box.label(text='Area: ' + str(round(prefs.stats_area, 3)))

        for idx, stats in enumerate(prefs.stats_array):
            col.separator()
            col.label(text='Packing device ' + str(idx) + ':')
            box = col.box()
            box.label(text='Iteration count: ' + str(stats.iter_count))

            box = col.box()
            box.label(text='Total packing time: ' + str(stats.total_time) + ' ms')

            box = col.box()
            box.label(text='Average iteration time: ' + str(stats.avg_time) + ' ms')

class UVP2_PT_HelpBase(bpy.types.Panel):
    bl_label = 'Help'
    bl_context = ''
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        layout = self.layout

        col = layout.column(align=True)

        row = col.row(align=True)
        row.operator(UVP2_OT_UvpSetupHelp.bl_idname, icon='HELP', text='UVP Setup')
        row = col.row(align=True)
        row.operator(UVP2_OT_InvalidTopologyHelp.bl_idname, icon='HELP', text='Invalid Topology')
        row = col.row(align=True)
        row.operator(UVP2_OT_NonSquarePackingHelp.bl_idname, icon='HELP', text='Non-Square Packing')
        row = col.row(align=True)
        row.operator(UVP2_OT_SimilarityDetectionHelp.bl_idname, icon='HELP', text='Similarity Detection')
        row = col.row(align=True)
        row.operator(UVP2_OT_PixelMarginHelp.bl_idname, icon='HELP', text='Pixel Margin')
        row = col.row(align=True)
        row.operator(UVP2_OT_IslandRotStepHelp.bl_idname, icon='HELP', text='Island Rotation Step')