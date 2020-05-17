'''
Copyright (C) 2019 Dancing Fortune Software All Rights Reserved

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
'''

bl_info = {
    'name': 'Bake Wrangler',
    'description': 'Bake Wrangler aims to improve all baking tasks with a node based interface and provide some additional common bake passes',
    'author': 'Dancing Fortune Software',
    'version': ('RC', 1, 0),
    'blender': (2, 82, 0),
    'location': 'Editor Type -> Bake Node Editor',
    'wiki_url': '',
    'category': 'Render'}


import bpy
from . import nodes



# Preferences 
class BakeWrangler_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__
    
    text_msgs: bpy.props.BoolProperty(name="Messages to Text editor", description="Write messages to a text block in addition to the console", default=True)
    clear_msgs: bpy.props.BoolProperty(name="Clear Old Messages", description="Clear the text block before each new bake", default=True)
    wind_msgs: bpy.props.BoolProperty(name="Open Text in new Window", description="A new window will be opened displaying the text block each time a new bake is started (must be closed manually)", default=True)
    
    debug: bpy.props.BoolProperty(name="Debug", description="Enable additional debugging output", default=False)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "text_msgs")
        if self.text_msgs:
            box = layout.box()
            box.prop(self, "clear_msgs")
            box.prop(self, "wind_msgs")
        layout.prop(self, "debug")
        
        
        
def register():
    from bpy.utils import register_class
    register_class(BakeWrangler_Preferences)
    nodes.register()


def unregister():
    from bpy.utils import unregister_class
    nodes.unregister()
    unregister_class(BakeWrangler_Preferences)
