
from .utils import *
from .pack_context import *
from .prefs import *
from .operator import UVP2_OT_PackOperatorGeneric
from .operator_box import bgl_set_color, editor_draw_msg

import bmesh
import bpy
import bgl
import blf

class UvIslandMetadata:

    def __init__(self, __idx, __int_params):
        self.idx = __idx
        self.int_params = __int_params

def island_param_draw_callback(self, context):

    try:

        font_id = 0
        bgl_set_color(font_id, self.text_color)
        blf.size(font_id, 20, 72)

        for i_metadata in self.island_metadata:

            region_coord = context.region.view2d.view_to_region(i_metadata.text_coords[0], i_metadata.text_coords[1])
            blf.position(font_id, region_coord[0], region_coord[1], 0)
            blf.draw(font_id, i_metadata.param_text)

        editor_draw_msg(self.text_color, "Press any key to hide '{}' values".format(self.param_info.NAME))

    except Exception as ex:
        if in_debug_mode():
            print_backtrace(ex)


class UVP2_OT_ShowIslandParam(UVP2_OT_PackOperatorGeneric):

    def __init__(self):
        self.__draw_handler = None
        self.text_color = (1, 1, 1, 1)

    def remove_handler(self):
        if self.__draw_handler is not None:
            bpy.types.SpaceImageEditor.draw_handler_remove(self.__draw_handler, 'WINDOW')

    def finish_after_op_done(self):
        return False

    def validate_pack_params(self):
        pass

    def process_result(self):

        if self.islands_metadata_msg is None:
            self.raiseUnexpectedOutputError()

        self.island_metadata = []
        entry_count = force_read_int(self.islands_metadata_msg)

        for i in range(entry_count):
            
            idx = force_read_int(self.islands_metadata_msg)
            int_params = []

            for j in range(UvIslandIntParams.COUNT):
                int_params.append(force_read_int(self.islands_metadata_msg))

            i_metadata = UvIslandMetadata(idx, int_params)

            # Calculate bbox center
            bbox = self.p_context.calc_island_bbox(idx)
            i_metadata.text_coords = (bbox[1] + bbox[0]) / 2.0
            i_metadata.param_text = self.param_info.param_to_text(i_metadata.int_params[self.param_info.PARAM_IDX])

            self.island_metadata.append(i_metadata)

        context = self.p_context.context
        handler_args = (self, context)
        self.__draw_handler = bpy.types.SpaceImageEditor.draw_handler_add(island_param_draw_callback, handler_args, 'WINDOW', 'POST_PIXEL')

        context.area.tag_redraw()
        self.report({'INFO'}, 'Done')

    def get_uvp_args(self):

        uvp_args = ['-o', str(UvPackerOpcode.GET_ISLANDS_METADATA), '-R']
        return uvp_args

    def handle_event_spec(self, event):

        if not self.op_done():
            return False

        if event.type not in {'MIDDLEMOUSE', 'INBETWEEN_MOUSEMOVE', 'MOUSEMOVE', 'TIMER', 'TIMER_REPORT', 'WHEELDOWNMOUSE', 'WHEELUPMOUSE'} and event.value == 'PRESS':
            # print('--')
            # print(event.type)
            # print(event.value)
            self.remove_handler()
            raise OpFinishedException()

        return True


class UVP2_OT_SetIslandParam(UVP2_OT_ShowIslandParam):

    bl_options = {'UNDO'}

    def pre_op_initialize(self):

        self.p_context.set_vcolor(
            self.param_info.get_vcolor_chname(),
            self.get_vcolor_value(),
            self.param_info.get_default_vcolor())
        
        self.p_context.update_meshes()

    def get_vcolor_value(self):
        return self.param_info.param_to_vcolor(getattr(self.scene_props, self.param_info.PROP_NAME))


class UVP2_OT_ResetIslandParam(UVP2_OT_SetIslandParam):

    def get_vcolor_value(self):
        return self.param_info.get_default_vcolor()



# ROTATION STEP

class UVP2_OT_RotStepIslandParamGeneric:

    param_info = RotStepIslandParamInfo()

    def send_rot_step(self):
        return True


class UVP2_OT_ShowRotStepIslandParam(UVP2_OT_RotStepIslandParamGeneric, UVP2_OT_ShowIslandParam):

    bl_idname = 'uvpackmaster2.uv_show_rot_step_island_param'
    bl_label = 'Show Rotation Step'
    bl_description = "Show rotation step assigned to the selected islands"


class UVP2_OT_SetRotStepIslandParam(UVP2_OT_RotStepIslandParamGeneric, UVP2_OT_SetIslandParam):

    bl_idname = 'uvpackmaster2.set_island_rot_step'
    bl_label = 'Set Rotation Step'
    bl_description = "Set rotation step value for the selected islands. The value to be set is defined by the 'Rotation Step Value' parameter"


class UVP2_OT_ResetRotStepIslandParam(UVP2_OT_RotStepIslandParamGeneric, UVP2_OT_ResetIslandParam):

    bl_idname = 'uvpackmaster2.reset_island_rot_step'
    bl_label = 'Reset Rotation Step'
    bl_description = "Reset rotation step value for the selected islands. After reset the 'G' value will be assigned to the islands, which means they will use the global 'Rotation Step' parameter when generating orientations"



# MANUAL GROUP

class UVP2_OT_ManualGroupIslandParamGeneric:

    param_info = GroupIslandParamInfo()

    def grouping_enabled(self):
        return True

    def get_group_method(self):
        return UvGroupingMethod.MANUAL.code


class UVP2_OT_ShowManualGroupIslandParam(UVP2_OT_ManualGroupIslandParamGeneric, UVP2_OT_ShowIslandParam):

    bl_idname = 'uvpackmaster2.uv_show_manual_group_island_param'
    bl_label = 'Show Groups'
    bl_description = "Show manual group numbers the selected islands are assigned to"


class UVP2_OT_SetManualGroupIslandParam(UVP2_OT_ManualGroupIslandParamGeneric, UVP2_OT_SetIslandParam):

    bl_idname = 'uvpackmaster2.set_island_manual_group'
    bl_label = 'Assign Islands To Group'
    bl_description = "Assign the selected islands to a manual group determined by the 'Group Number' parameter"


class UVP2_OT_ResetManualGroupIslandParam(UVP2_OT_ManualGroupIslandParamGeneric, UVP2_OT_ResetIslandParam):

    bl_idname = 'uvpackmaster2.reset_island_manual_group'
    bl_label = 'Reset Groups'
    bl_description = "Reset the manual group assignment for the selected islands"

