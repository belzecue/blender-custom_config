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
    'version': (0, 9, 5, 2),
    'blender': (2, 82, 0),
    'location': 'Editor Type -> Bake Node Editor',
    'wiki_url': '',
    'category': 'Render'}


import bpy
from . import nodes



# Preferences 
class BakeWrangler_Preferences(bpy.types.AddonPreferences):
    bl_idname = __package__
    
    debug: bpy.props.BoolProperty(name="Debug", description="Enable additional debugging output", default=False)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "debug")
        
        

def register():
    from bpy.utils import register_class
    register_class(BakeWrangler_Preferences)
    nodes.register()


def unregister():
    from bpy.utils import unregister_class
    nodes.unregister()
    unregister_class(BakeWrangler_Preferences)
