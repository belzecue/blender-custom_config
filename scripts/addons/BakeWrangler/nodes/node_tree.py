import os
import sys
import threading
import subprocess
from datetime import datetime, timedelta
import bpy
from bpy.types import NodeTree, Node, NodeSocket, NodeSocketColor, NodeSocketFloat



# Message formatter
def _print(str, node=None, ret=False, tag=False, wrap=True):
    output = str
    endl = ''
    flsh = False
    
    if node:
        output = "[%s]: %s" % (node.get_name(), output)
        
    if tag:
        output = "<%s>%s" % ("PBAKE", output)
        flsh = True
        if wrap:
            output = "%s</%s>" % (output, "PWRAP")
        else:
            output = "%s</%s>" % (output, "PBAKE")
        
    if wrap:
        endl = '\n'
        
    if ret:
        return output
    else:
        print(output, end=endl, flush=flsh)
    

#
# Bake Wrangler Operators
#

# Base class for all bakery operators, provides data to find owning node, etc.
class BakeWrangler_Operator:
    # Use strings to store their names, since Node isn't a subclass of ID it can't be stored as a pointer
    tree: bpy.props.StringProperty()
    node: bpy.props.StringProperty()

    @classmethod
    def poll(type, context):
        if context.area is not None:
            return context.area.type == "NODE_EDITOR" and context.space_data.tree_type == "BakeWrangler_Tree"
        else:
            return True


# Dummy operator to draw when a bake is in progress
class BakeWrangler_Operator_Dummy(BakeWrangler_Operator, bpy.types.Operator):
    '''Bake currently in progress, either cancel the current bake or wait for it to finish'''
    bl_idname = "bake_wrangler_op.dummy"
    bl_label = ""
    
    @classmethod
    def poll(type, context):
        # This operator is always supposed to be disabled
        return False
    
    
# Kill switch to stop a bake in progress
class BakeWrangler_Operator_BakeStop(BakeWrangler_Operator, bpy.types.Operator):
    '''Cancel currently running bake'''
    bl_idname = "bake_wrangler_op.bake_stop"
    bl_label = "Cancel Bake"
    
    # Stop the currently running bake
    def execute(self, context):
        tree = bpy.data.node_groups[self.tree]
        if tree.baking != None:
            tree.baking.stop()
            tree.interface_update(context)
        return {'FINISHED'}
    
    # Ask the user if they really want to cancel bake
    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)
    
    
# Operator for bake pass node
class BakeWrangler_Operator_BakePass(BakeWrangler_Operator, bpy.types.Operator):
    '''Perform the bake pass and generate all connected image outputs'''
    bl_idname = "bake_wrangler_op.bake_pass"
    bl_label = "Bake Pass"

    _timer = None
    
    _thread = None
    _kill = False
    _success = False
    _finish = False
    _lock = threading.Lock()
    stopping = False
    
    start = None
    valid = None
    blend_copy = None
    blend_log = None
    bake_proc = None
    
    # Stop this bake if it's currently running
    def stop(self, kill=True):
        if self._thread and self._thread.is_alive() and kill:
            with self._lock:
                self.stopping = self._kill = True
        return self.stopping
    
    # Runs a blender subprocess
    def thread(self, node_name, tree_name, file_name, exec_name, script_name):
        tree = bpy.data.node_groups[self.tree]
        node = tree.nodes[self.node]
        _print("Launching background process:", node=node)
        _print("================================================================================")
        sub = subprocess.Popen([
            exec_name,
            file_name,
            "--background",
            "--python", script_name,
            "--",
            "--tree", tree_name,
            "--node", node_name,
            ], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        
        # Read output from subprocess and print tagged lines
        out = ""
        kill = False
        while sub.poll() == None:
            # Check for kill flag
            if self._lock.acquire(blocking=False):
                if self._kill:
                    _print("Bake cancelled, terminating process...")
                    sub.kill()
                    out, err = sub.communicate()
                    kill = True
                self._lock.release()
            
            if not kill:
                out = sub.stdout.read(1)
                # Collect tagged lines and display them in console
                if out == '<':
                    out += sub.stdout.read(6)
                    if out == "<PBAKE>":
                        tag_end = False
                        tag_line = ""
                        out = ""
                        # Read until end tag is found
                        while not tag_end:
                            tag_line = sub.stdout.read(1)
                            
                            if tag_line == '<':
                                tag_line += sub.stdout.read(7)
                                if tag_line == "</PBAKE>":
                                    tag_end = True
                                    out += '\n'
                                elif tag_line == "</PWRAP>":
                                    tag_end = True
                                    sys.stdout.write('\n')
                                    sys.stdout.flush()
                                elif tag_line == "<FINISH>":
                                    tag_end = True
                                    self._success = True
                                    self._finish = True
                                elif tag_line == "<ERRORS>":
                                    tag_end = True
                                    self._success = False
                                    self._finish = True
                                    
                            if tag_line != '' and not tag_end:
                                sys.stdout.write(tag_line)
                                sys.stdout.flush()
                                out += tag_line
        
            # Write to log
            if out != '' and self.blend_log:
                self.blend_log.write(out)
                self.blend_log.flush()
        _print("================================================================================")
        _print("Background process ended", node=node)

    # Event handler
    def modal(self, context, event):
        tree = bpy.data.node_groups[self.tree]
        node = tree.nodes[self.node]
        
        # Check if the bake thread has ended every timer event
        if event.type == 'TIMER':
            if not self._thread.is_alive():
                self.cancel(context)
                if self._kill:
                    _print("Bake canceled after %s\n" % (str(datetime.now() - self.start)), node=node)
                    self.report({'WARNING'}, "Bake Canceled")
                    return {'CANCELLED'}
                else:
                    if self._success and self._finish:
                        _print("Bake finished in %s\n" % (str(datetime.now() - self.start)), node=node)
                        self.report({'INFO'}, "Bake Completed")
                    elif self._finish:
                        _print("Bake finished with errors after %s\n" % (str(datetime.now() - self.start)), node=node)
                        self.report({'WARNING'}, "Bake Finished with Errors")
                    else:
                        _print("Bake failed after %s\n" % (str(datetime.now() - self.start)), node=node)
                        self.report({'ERROR'}, "Bake Failed")
                    return {'FINISHED'}
            
        return {'PASS_THROUGH'}
    
    # Called after invoke to perform the bake if everything passed validation
    def execute(self, context):
        if self.valid == None:
            self.report({'ERROR'}, "Call invoke first")
            return {'CANCELLED'}
        elif not self.valid[0]:
            self.cancel(context)
            self.report({'ERROR'}, "Validation failed")
            return {'CANCELLED'}
        
        self.start = datetime.now()
        tree = bpy.data.node_groups[self.tree]
        node = tree.nodes[self.node]
        
        # Save a temporary copy of the blend file and store the path. Make sure the path doesn't exist first.
        # All baking will be done using this copy so the user can continue working in this session.
        blend_name = bpy.path.clean_name(bpy.path.display_name_from_filepath(bpy.data.filepath))
        blend_temp = bpy.path.abspath(bpy.app.tempdir)
        node_cname = bpy.path.clean_name(node.get_name())
        blend_copy = os.path.join(blend_temp, blend_name + "_" + node_cname)
        
        # Increment file name until it doesn't exist
        if os.path.exists(blend_copy + ".blend"):
            fno = 1
            while os.path.exists(blend_copy + str(fno) + ".blend"):
                fno = fno + 1
            blend_copy = blend_copy + str(fno) + ".blend"
        else:
            blend_copy = blend_copy + ".blend"
        
        # Print out start message and temp path
        _print("")
        _print("=== Bake starts ===", node=node)
        _print("Creating temporary files in %s" % (blend_temp), node=node)
        
        bpy.ops.wm.save_as_mainfile(filepath=blend_copy, copy=True)
        
        # Check copy exists
        if not os.path.exists(blend_copy):
            self.report({'ERROR'}, "Blend file copy failed")
            return {'CANCELLED'}
        else:
            self.blend_copy = blend_copy
            
        # Open a log file at the same location with a .log appended to the name
        log_err = None
        blend_log = None
        try:
            blend_log = open(blend_copy + ".log", "a")
        except OSError as err:
            self.report({'WARNING'}, "Couldn't create log file")
            log_err = err.strerror
        else:
            self.blend_log = blend_log
        
        # Print out blend copy and log names
        _print(" - %s" % (os.path.basename(self.blend_copy)), node=node) 
        if self.blend_log and not log_err:
            _print(" - %s" % (os.path.basename(blend_copy + ".log")), node=node)
        else:
            _print(" - Log file creation failed: %s" % (log_err), node=node)
        
        # Create a thread which will launch a background instance of blender running a script that does all the work.
        # Proccess is complete when thread exits. Will need full path to blender, node, temp file and proc script.
        blend_exec = bpy.path.abspath(bpy.app.binary_path)
        self._thread = threading.Thread(target=self.thread, args=(self.node, self.tree, self.blend_copy, blend_exec, self.bake_proc,))
        
        # Add a timer to periodically check if the bake has finished
        wm = context.window_manager
        self._timer = wm.event_timer_add(5.0, window=context.window)
        wm.modal_handler_add(self)
        
        self._thread.start()
        return {'RUNNING_MODAL'}
    
    # Called by UI when the button is clicked. Will validate settings and prepare files for execute
    def invoke(self, context, event):
        # Do full validation of bake so it can be reported in the popup dialog
        tree = bpy.data.node_groups[self.tree]
        node = tree.nodes[self.node]
        tree.baking = self
        tree.interface_update(context)
        self.valid = node.validate()
        
        # Check processing script exists
        bake_path = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
        bake_proc = bpy.path.abspath(os.path.join(bake_path, "baker.py"))
        if not os.path.exists(bake_proc):
            self.valid[0] = False
            self.valid.append(_print("Bake processing script wasn't found at '%s'" % (bake_proc), node=node, ret=True))
        else:
            self.bake_proc = bake_proc
        
        # Check baking scene file exists
        scene_file = bpy.path.abspath(os.path.join(bake_path, "resources", "BakeWrangler_Scene.blend"))
        if not os.path.exists(scene_file):
            self.valid[0] = False
            self.valid.append(_print("Bake scene wasn't found at '%s'" % (scene_file), node=node, ret=True))
        
        # Draw pop-up that will use custom draw function to display any validation errors
        return context.window_manager.invoke_props_dialog(self, width=400)
    
    # Cancel the bake
    def cancel(self, context):
        tree = bpy.data.node_groups[self.tree]
        if self._timer:
            wm = context.window_manager
            wm.event_timer_remove(self._timer)
        if self.blend_log:
            self.blend_log.close()
        if tree.baking != None:
            tree.baking = None
            tree.interface_update(context)
    
    # Draw custom popup
    def draw(self, context):
        tree = bpy.data.node_groups[self.tree]
        node = tree.nodes[self.node]
        layout = self.layout
        if not self.valid[0]:
            layout.label(text="!!! Validation FAILED:")
            _print("")
            _print("!!! Validation FAILED:", node=node)
            col = layout.column()
            for i in range(len(self.valid) - 1):
                col.label(text=self.valid[i + 1])
                _print(self.valid[i + 1])
            layout.label(text="See console for details")
            _print("")
        else:
            layout.label(text="%s ready to bake:" % (node.get_name()))
            if len(self.valid) > 1:
                layout.label(text="")
                layout.label(text="!!! Material Warnings:")
                _print("")
                _print("!!! Material Warnings:")
                col = layout.column()
                for i in range(len(self.valid) - 1):
                    col.label(text=self.valid[i + 1])
                    _print(self.valid[i + 1])
            layout.label(text="See console for progress information and warnings")


class BakeWrangler_Operator_BakeImage(BakeWrangler_Operator, bpy.types.Operator):
    '''Perform the connected bake pass or passes and generate just the single image output'''
    bl_idname = "bake_wrangler_op.bake_image"
    bl_label = "Bake Image"

    def execute(self, context):
        pass
    
    @classmethod
    def poll(type, context):
        # Not yet implemented
        return False
    


#
# Bake Wrangler nodes system
#

# Node tree definition that shows up in the editor type list. Sets the name, icon and description.
class BakeWrangler_Tree(NodeTree):
    '''Improved baking system to extend and replace existing internal bake system'''
    bl_label = 'Bake Node Editor'
    bl_icon = 'NODETREE'
    
    # Does this need a lock for modal event access?
    baking = None


# Custom Sockets:

# Base class for all bakery sockets
class BakeWrangler_Tree_Socket:
    # Workaround for link.is_valid being un-usable
    valid: bpy.props.BoolProperty()
    
    def socket_label(self, text):
        if self.is_output or (self.is_linked and self.valid) or (not self.is_output and not self.is_linked):
            return text
        else:
            return text + " [invalid]"
            
    def socket_color(self, color):
        if not self.is_output and self.is_linked and not self.valid:
            return (1.0, 0.0, 0.0, 1.0)
        else:
            return color
    

# Socket for sharing high poly mesh, or really any mesh data that should be in the bake but isn't the target
class BakeWrangler_Socket_HighPolyMesh(NodeSocket, BakeWrangler_Tree_Socket):
    '''Socket for connecting a high poly mesh node'''
    bl_label = 'High Poly'
    
    # Called to filter objects listed in the value search field. Only objects of type 'MESH' are shown.
    def value_prop_filter(self, object):
        return object.type == 'MESH'
    
    # Called when the value propery changes.
    def value_prop_update(self, context):
        if self.node and self.node.bl_idname == 'BakeWrangler_Input_HighPolyMesh':
            self.node.update_inputs()
        
    value: bpy.props.PointerProperty(name="High Poly Mesh", description="Object to be part of selection when doing a selected to active type bake.", type=bpy.types.Object, poll=value_prop_filter, update=value_prop_update)
    
    def draw(self, context, layout, node, text):
        if node.bl_idname == 'BakeWrangler_Input_Mesh' and node.multi_res:
            layout.label(text=text + " [ignored]")
        elif not self.is_output and not self.is_linked and node.bl_idname != 'BakeWrangler_Input_Mesh':
            layout.prop_search(self, "value", context.scene, "objects", text="")
        else:
            layout.label(text=BakeWrangler_Tree_Socket.socket_label(self, text))

    def draw_color(self, context, node):
        return BakeWrangler_Tree_Socket.socket_color(self, (0.0, 0.2, 1.0, 1.0))
    

# Socket for sharing a target mesh
class BakeWrangler_Socket_Mesh(NodeSocket, BakeWrangler_Tree_Socket):
    '''Socket for connecting a mesh node'''
    bl_label = 'Mesh'
    
    def draw(self, context, layout, node, text):
        layout.label(text=BakeWrangler_Tree_Socket.socket_label(self, text))

    def draw_color(self, context, node):
        return BakeWrangler_Tree_Socket.socket_color(self, (0.0, 0.5, 1.0, 1.0))
    

# Socket for connecting a bake pass up to a batch controller (oven)
class BakeWrangler_Socket_Pass(NodeSocket, BakeWrangler_Tree_Socket):
    '''Socket for connecting a bake pass node'''
    bl_label = 'Pass'
    
    def draw(self, context, layout, node, text):
        layout.label(text=BakeWrangler_Tree_Socket.socket_label(self, text))

    def draw_color(self, context, node):
        return BakeWrangler_Tree_Socket.socket_color(self, (1.0, 0.5, 1.0, 1.0))
    
    
# Socket for RGB(A) data, extends the base color node
class BakeWrangler_Socket_Color(NodeSocketColor, BakeWrangler_Tree_Socket):
    '''Socket for RGB(A) data'''
    bl_label = 'Color'
    
    def draw(self, context, layout, node, text):
        layout.label(text=BakeWrangler_Tree_Socket.socket_label(self, text))
        
    def draw_color(self, context, node):
        return BakeWrangler_Tree_Socket.socket_color(self, (0.78, 0.78, 0.16, 1.0))


# Socket for Float data, extends the base float node
class BakeWrangler_Socket_Float(NodeSocketFloat, BakeWrangler_Tree_Socket):
    '''Socket for Float data'''
    bl_label = 'Float'
    
    def draw(self, context, layout, node, text):
        layout.label(text=BakeWrangler_Tree_Socket.socket_label(self, text))
    
    def draw_color(self, context, node):
        return BakeWrangler_Tree_Socket.socket_color(self, (0.631, 0.631, 0.631, 1.0))
    

# Custom Nodes:

# Base class for all bakery nodes. Identifies that they belong in the bakery tree.
class BakeWrangler_Tree_Node:
    @classmethod
    def poll(cls, ntree):
        return ntree.bl_idname == 'BakeWrangler_Tree_Node'
    
    def get_name(self):
        name = self.name
        if self.label:
            name += ".%s" % (self.label)
        return name
    
    def validate(self):
        return [True]


# Input node that takes any number of mesh objects that should be selected durning a bake
class BakeWrangler_Input_HighPolyMesh(Node, BakeWrangler_Tree_Node):
    '''High poly mesh data node'''
    bl_label = 'High Poly Meshs'
    
    # Makes sure there is always one empty input socket at the bottom by adding and removing sockets
    # when their values.
    def update_inputs(self):
        idx = 0
        for socket in self.inputs:
            if socket.value or socket.is_linked:
                if len(self.inputs) == idx + 1:
                    self.inputs.new('BakeWrangler_Socket_HighPolyMesh', "High Poly")
            else:
                if len(self.inputs) > idx + 1:
                    self.inputs.remove(socket)
                    idx = idx - 1
            idx = idx + 1
    
    # Returns a list of all chosen mesh objects. May recurse through multiple connected nodes.
    def get_objects(self):
        objects = []
        for input in self.inputs:
            if not input.is_linked:
                if input.value:
                    objects.append(input.value)
            else:
                linked_objects = []
                if input.links[0].is_valid and input.valid:
                    linked_objects = input.links[0].from_node.get_objects()
                if len(linked_objects):
                    objects.extend(linked_objects)
        return objects
    
    def init(self, context):
        # Sockets IN
        self.inputs.new('BakeWrangler_Socket_HighPolyMesh', "High Poly")
        # Sockets OUT
        self.outputs.new('BakeWrangler_Socket_HighPolyMesh', "High Poly")
  
    def draw_buttons(self, context, layout):
        layout.label(text="Meshs:")

    def update(self):
        self.update_inputs()
    
    # Validate incoming links
    def insert_link(self, link):
        if link.to_node == self:
            if link.from_socket.bl_idname == link.to_socket.bl_idname:
                link.to_socket.valid = True
            else:
                link.to_socket.valid = False


# Input node that takes a single target mesh and its bake settings. High poly mesh nodes can be added as input.
class BakeWrangler_Input_Mesh(Node, BakeWrangler_Tree_Node):
    '''Mesh data and settings node'''
    bl_label = 'Mesh'
    
    # Returns the most identifing string for the node
    def get_name(self):
        name = BakeWrangler_Tree_Node.get_name(self)
        if self.mesh_object:
            name += " (%s)" % (self.mesh_object.name)
        return name
    
    # Check node settings are valid to bake. Returns true/false, plus error message.
    def validate(self, check_materials=False):
        valid = [True]
        # Is a mesh selected?
        if not self.mesh_object:
            valid[0] = False
            valid.append(_print("No valid mesh object selected", node=self, ret=True))
        # Check for multires modifier if multires is enabled
        if self.multi_res and self.mesh_object:
            has_multi_mod = False
            if len(self.mesh_object.modifiers):
                for mod in self.mesh_object.modifiers:
                    if mod.type == 'MULTIRES' and mod.total_levels > 0:
                        has_multi_mod = True
                        break
            if not has_multi_mod:
                valid[0] = False
                valid.append(_print("Multires enabled but no multires data on selected mesh object", node=self, ret=True))
        # Check cage if enabled
        if self.cage:
            if not self.cage_obj:
                valid[0] = False
                valid.append(_print("Cage enabled but no cage object selected", node=self, ret=True))
            if self.mesh_object and self.cage_obj and len(self.mesh_object.data.polygons) != len(self.cage_obj.data.polygons):
                    valid[0] = False
                    valid.append(_print("Cage object face count does not match mesh object", node=self, ret=True))
            if self.mesh_object and len(self.get_objects()) < 2:
                valid[0] = False
                valid.append(_print("Cage enabled but no high poly objects selected", node=self, ret=True))
                
        # Validated?
        if not valid[0]:
            return valid
        
        # Valid, should materials also be checked?
        if check_materials:
            # Some bake types need to modify the materials, check if this can be done. A failure wont invalidate
            # but warnings will be issued about the materails that fail.
            mats = []
            others = self.get_objects()
            if self.multi_res or len(others) < 2:
                # Just check self materials
                if len(self.mesh_object.data.materials):
                    for mat in self.mesh_object.data.materials:
                        if mats.count(mat) == 0:
                            mats.append(mat)
            else:
                # Just check not self materials
                others.pop(0)
                for obj in others:
                    if len(obj.data.materials):
                        for mat in obj.data.materials:
                            if mats.count(mat) == 0:
                                mats.append(mat)
            
            # Go through the list of materials and see if they will pass the prep phase
            for mat in mats:
                nodes = mat.node_tree.nodes
                node_outputs = []
                passed = False
                
                # Not a node based material or not enough nodes to be valid
                if not nodes or len(nodes) < 2:
                    valid.append(_print("'%s' not node based or too few nodes" % (mat.name), node=self, ret=True))
                    continue
                
                # Collect all outputs
                for node in nodes:
                    if node.type == 'OUTPUT_MATERIAL':
                        if node.target == 'CYCLES' or node.target == 'ALL':
                            node_outputs.append(node)
                            
                # Try to find at least one usable node pair from the outputs
                for node in node_outputs:
                    input = node.inputs['Surface']
                    if input.is_linked and input.links[0].from_node.type == 'BSDF_PRINCIPLED':
                        passed = True
                        break
                
                # Didn't find any usable node pairs
                if not passed:
                    valid.append(_print("'%s' No Principled Shader -> Material Output node set up" % (mat.name), node=self, ret=True))
                     
        return valid
    
    # Returns a list of all chosen mesh objects. The bake target will be at index 0, extra objects indicate
    # a 'selected to active' type bake should be performed. May recurse through multiple prior nodes. If no
    # mesh_object is set an empty list will be returned instead. Only unique objects will be returned.
    def get_objects(self):
        objects = []
        if self.mesh_object:
            objects.append(self.mesh_object)
            if not self.inputs[0].is_linked:
                if self.inputs[0].value and objects.count(self.inputs[0].value) == 0:
                    objects.append(self.inputs[0].value)
            else:
                linked_objects = []
                if self.inputs[0].links[0].is_valid and self.inputs[0].valid:
                    linked_objects = self.inputs[0].links[0].from_node.get_objects()
                if len(linked_objects):
                    for obj in linked_objects:
                        if objects.count(obj) == 0:
                            objects.append(obj)
        return objects
    
    # Filter for prop_search field used to select mesh_object
    def mesh_object_filter(self, object):
        return object.type == 'MESH'
    
    multi_res_passes = (
        ('NORMALS', "Normals", "Bake normals"),
        ('DISPLACEMENT', "Displacment", "Bake displacement"),
    )
    
    mesh_object: bpy.props.PointerProperty(name="Bake Target", description="Mesh that will be the active object during the bake", type=bpy.types.Object, poll=mesh_object_filter)
    ray_dist: bpy.props.FloatProperty(name="Ray Distance", description="Distance to use for inward ray cast when using a selected to active bake", default=0.01, step=1, min=0.0, unit='LENGTH')
    margin: bpy.props.IntProperty(name="Margin", description="Extends the baked result as a post process filter", default=0, min=0, subtype='PIXEL')
    mask_margin: bpy.props.IntProperty(name="Mask Margin", description="Adds extra padding to the mask bake. Use if edge details are being cut off", default=0, min=0, subtype='PIXEL')
    multi_res: bpy.props.BoolProperty(name="Multires", description="Bake directly from multires object. This will disable or ignore the other bake settings.\nOnly Normals and Displacment can be baked")
    multi_res_pass: bpy.props.EnumProperty(name="Pass", description="Choose shading information to bake into the image.\nMultires pass will override any connected bake pass", items=multi_res_passes, default='NORMALS')
    cage: bpy.props.BoolProperty(name="Cage", description="Cast rays to active object from a cage. The cage must have the same number of faces")
    cage_obj: bpy.props.PointerProperty(name="Cage Object", description="Object to use as a cage instead of calculating the cage from the active object", type=bpy.types.Object, poll=mesh_object_filter)
    
    
    def init(self, context):
        # Sockets IN
        self.inputs.new('BakeWrangler_Socket_HighPolyMesh', "High Polys")
        # Sockets OUT
        self.outputs.new('BakeWrangler_Socket_Mesh', "Mesh")

    def draw_buttons(self, context, layout):
        layout.label(text="Mesh Object:")
        layout.prop_search(self, "mesh_object", context.scene, "objects", text="")
        layout.prop(self, "margin", text="Margin")
        layout.prop(self, "mask_margin", text="Padding")
        layout.prop(self, "multi_res", text="From Multires")
        if not self.multi_res:
            if not self.cage:
                layout.prop(self, "cage", text="Cage")
            else:
                layout.prop(self, "cage", text="Cage:")
                layout.prop_search(self, "cage_obj", context.scene, "objects", text="")
            layout.label(text="Bake From:")
            layout.prop(self, "ray_dist", text="Ray Dist")
        else:
            layout.prop(self, "multi_res_pass")
    
    def update(self):
        # Links can get inserted without calling insert_link, but update is called.
        for socket in self.inputs:
            if socket.is_linked and not socket.valid:
                self.insert_link(socket.links[0])
            
    # Validate incoming links
    def insert_link(self, link):
        if link.to_node == self:
            if link.from_socket.bl_idname == link.to_socket.bl_idname:
                link.to_socket.valid = True
            else:
                link.to_socket.valid = False
        

# Baking node that holds all the settings for a type of bake 'pass'. Takes one or more mesh input nodes as input.
class BakeWrangler_Bake_Pass(Node, BakeWrangler_Tree_Node):
    '''Baking pass node'''
    bl_label = 'Bake Pass'
    
    # Returns the most identifing string for the node
    def get_name(self):
        name = BakeWrangler_Tree_Node.get_name(self)
        if self.bake_pass:
            name += " (%s)" % (self.bake_pass)
        return name
    
    # Check node settings are valid to bake. Returns true/false, plus error message(s).
    def validate(self):
        valid = [True]
        # Validate inputs
        has_valid_input = False
        for input in self.inputs:
            if input.is_linked and input.links[0].is_valid and input.valid:
                if self.bake_pass in self.bake_built_in:
                    input_valid = input.links[0].from_node.validate()
                else:
                    input_valid = input.links[0].from_node.validate(check_materials=True)
                if not input_valid[0]:
                    valid[0] = input_valid.pop(0)
                    valid += input_valid
                else:
                    input_valid.pop(0)
                    valid += input_valid
                    has_valid_input = True
        errs = len(valid)
        if not has_valid_input and errs < 2:
            valid[0] = False
            valid.append(_print("Has no valid inputs connected", node=self, ret=True))
        # Validate outputs
        has_valid_output = False
        for output in self.outputs:
            if output.is_linked:
                for link in output.links:
                    if link.is_valid and link.to_socket.valid:
                        output_valid = link.to_node.validate()
                        if not output_valid[0]:
                            valid[0] = output_valid.pop(0)
                            valid += output_valid
                        else:
                            output_valid.pop(0)
                            valid += output_valid
                            has_valid_output = True
        if not has_valid_output and errs == len(valid):
            valid[0] = False
            valid.append(_print("Has no valid outputs connected", node=self, ret=True))
        # Validated
        return valid
    
    # Makes sure there is always one empty input socket at the bottom by adding and removing sockets
    # as required
    def update_inputs(self):
        idx = 0
        for socket in self.inputs:
            if socket.is_linked:
                if len(self.inputs) == idx + 1:
                    self.inputs.new('BakeWrangler_Socket_Mesh', "Mesh")
            else:
                if len(self.inputs) > idx + 1:
                    self.inputs.remove(socket)
                    idx = idx - 1
            idx = idx + 1
    
    bake_passes = (
        ('ALBEDO', "Albedo", "Surface color without lighting (Principled shader only)"),
        ('METALIC', "Metalic", "Surface metalness values (Principled shader only)"),
        ('ALPHA', "Alpha", "Surface transparency values (Principled shader only)"),
        
        ('NORMAL', "Normal", "Surface tangent normals"),
        ('ROUGHNESS', "Roughness", "Surface roughness values"),
        ('AO', "Ambient Occlusion", "Surface self occlusion values"),
        
        ('SUBSURFACE', "Subsurface", "Subsurface color"),
        ('TRANSMISSION', "Transmission", "Colors of light passing through a material"),
        ('GLOSSY', "Glossy", "Colors of a surface generated by a glossy shader"),
        ('DIFFUSE', "Diffuse", "Colors of a surface generated by a diffuse shader"),
        ('ENVIRONMENT', "Environment", "Colors coming from the environment"),
        ('EMIT', "Emit", "Surface self emission color values"),
        ('UV', "UV", "UV Layout"),
        ('SHADOW', "Shadow", "Shadow map"),
        ('COMBINED', "Combined", "Combine multiple passes into a single bake"),
    )
    
    bake_built_in = ['NORMAL', 'ROUGHNESS', 'AO', 'SUBSURFACE', 'TRANSMISSION', 'GLOSSY', 'DIFFUSE', 'ENVIRONMENT', 'EMIT', 'UV', 'SHADOW', 'COMBINED']
    bake_has_influence = ['SUBSURFACE', 'TRANSMISSION', 'GLOSSY', 'DIFFUSE', 'COMBINED']
    
    normal_spaces = (
        ('TANGENT', "Tangent", "Bake the normals in tangent space"),
        ('OBJECT', "Object", "Bake the normals in object space"),
    )
    
    normal_swizzle = (
        ('POS_X', "+X", ""),
        ('POS_Y', "+Y", ""),
        ('POS_Z', "+Z", ""),
        ('NEG_X', "-X", ""),
        ('NEG_Y', "-Y", ""),
        ('NEG_Z', "-Z", ""),
    )
    
    cycles_devices = (
        ('CPU', "CPU", "Use CPU for baking"),
        ('GPU', "GPU", "Use GPU for baking"),
    )

    bake_pass: bpy.props.EnumProperty(name="Pass", description="Type of pass to bake", items=bake_passes, default='NORMAL')
    bake_samples: bpy.props.IntProperty(name="Bake Samples", description="Number of samples to bake for each pixel. Use 25 to 50 samples for most bake types (AO may look better with more).\nQuality is gained by increaseing resolution rather than samples past that point", default=32, min=1)
    bake_xres: bpy.props.IntProperty(name="Bake X resolution", description="Number of horizontal pixels in bake. Power of 2 image sizes are recommended for exporting", default=1024, min=1, subtype='PIXEL')
    bake_yres: bpy.props.IntProperty(name="Bake Y resolution", description="Number of vertical pixels in bake. Power of 2 image sizes are recommended for exporting", default=1024, min=1, subtype='PIXEL')
    mask_samples: bpy.props.IntProperty(name="Mask Samples", description="Number of samples to bake for each pixel in the mask. This can be a low value.\nSetting to 0 will disable masking, which is much faster but will completely overwrite the output image", default=0, min=0)
    norm_space: bpy.props.EnumProperty(name="Space", description="Space to bake the normals in", items=normal_spaces, default='TANGENT')
    norm_R: bpy.props.EnumProperty(name="R", description="Axis to bake in Red channel", items=normal_swizzle, default='POS_X')
    norm_G: bpy.props.EnumProperty(name="G", description="Axis to bake in Green channel", items=normal_swizzle, default='POS_Y')
    norm_B: bpy.props.EnumProperty(name="B", description="Axis to bake in Blue channel", items=normal_swizzle, default='POS_Z')
    bake_device: bpy.props.EnumProperty(name="Device", description="Bake device", items=cycles_devices, default='CPU')
    use_direct: bpy.props.BoolProperty(name="Direct", description="Add direct lighting contribution", default=True)
    use_indirect: bpy.props.BoolProperty(name="Indirect", description="Add indirect lighting contribution", default=True)
    use_color: bpy.props.BoolProperty(name="Color", description="Color the pass", default=True)
    use_diffuse: bpy.props.BoolProperty(name="Diffuse", description="Add diffuse contribution", default=True)
    use_glossy: bpy.props.BoolProperty(name="Glossy", description="Add glossy contribution", default=True)
    use_transmission: bpy.props.BoolProperty(name="Transmission", description="Add transmission contribution", default=True)
    use_subsurface: bpy.props.BoolProperty(name="Subsurface", description="Add subsurface contribution", default=True)
    use_ao: bpy.props.BoolProperty(name="Ambient Occlusion", description="Add ambient occlusion contribution", default=True)
    use_emit: bpy.props.BoolProperty(name="Emit", description="Add emission contribution", default=True)

    def init(self, context):
        # Sockets IN
        self.inputs.new('BakeWrangler_Socket_Mesh', "Mesh")
        # Sockets OUT
        self.outputs.new('BakeWrangler_Socket_Color', "Color")
        self.outputs.new('BakeWrangler_Socket_Float', "R")
        self.outputs.new('BakeWrangler_Socket_Float', "G")
        self.outputs.new('BakeWrangler_Socket_Float', "B")
        self.outputs.new('BakeWrangler_Socket_Float', "Value")

    def draw_buttons(self, context, layout):
        if self.id_data.baking != None:
            if self.id_data.baking.node == self.name:
                if self.id_data.baking.stop(kill=False):
                    layout.operator("bake_wrangler_op.dummy", icon='CANCEL', text="Stopping...")
                else:
                    op = layout.operator("bake_wrangler_op.bake_stop", icon='CANCEL')
                    op.tree = self.id_data.name
                    op.node = self.name
            else:
                layout.operator("bake_wrangler_op.dummy", icon='RENDER_STILL', text="Bake Pass")
        else:
            op = layout.operator("bake_wrangler_op.bake_pass", icon='RENDER_STILL')
            op.tree = self.id_data.name
            op.node = self.name
        layout.prop(self, "bake_pass")
        if self.bake_pass == 'NORMAL':
            split = layout.split(factor=0.5)
            col = split.column(align=True)
            col.alignment = 'RIGHT'
            col.label(text="Space:")
            col.label(text="R:")
            col.label(text="G:")
            col.label(text="B:")
            col = split.column(align=True)
            col.prop(self, "norm_space", text="")
            col.prop(self, "norm_R", text="")
            col.prop(self, "norm_G", text="")
            col.prop(self, "norm_B", text="")
        elif self.bake_pass in self.bake_has_influence:
            row = layout.row(align=True)
            row.use_property_split = False
            row.prop(self, "use_direct", toggle=True)
            row.prop(self, "use_indirect", toggle=True)
            if self.bake_pass != 'COMBINED':
                row.prop(self, "use_color", toggle=True)
            else:
                col = layout.column(align=True)
                col.prop(self, "use_diffuse")
                col.prop(self, "use_glossy")
                col.prop(self, "use_transmission")
                col.prop(self, "use_subsurface")
                col.prop(self, "use_ao")
                col.prop(self, "use_emit")
        split = layout.split()
        split.label(text="Device:")
        split.prop(self, "bake_device", text="")
        split = layout.split()
        split.label(text="Samples:")
        split.prop(self, "bake_samples", text="")
        split = layout.split()
        split.label(text="Mask:")
        split.prop(self, "mask_samples", text="")
        split = layout.split(factor=0.15)
        split.label(text="X:")
        split.prop(self, "bake_xres", text="")
        split = layout.split(factor=0.15)
        split.label(text="Y:")
        split.prop(self, "bake_yres", text="")
    
    def update(self):
        self.update_inputs()
        # Links can get inserted without calling insert_link, but update is called.
        for socket in self.inputs:
            if socket.is_linked and not socket.valid:
                self.insert_link(socket.links[0])
    
    # Validate incoming links
    def insert_link(self, link):
        if link.to_node == self:
            if link.from_socket.bl_idname == link.to_socket.bl_idname:
                link.to_socket.valid = True
            else:
                link.to_socket.valid = False


# Output node that specifies the path to a file where a bake should be saved along with size and format information.
# Takes input from the outputs of a bake pass node. Connecting multiple inputs will cause higher position inputs to
# be over written by lower ones. Eg: Having a color input and an R input would cause the R channel of the color data
# to be overwritten by the data connected tot he R input.
class BakeWrangler_Output_Image_Path(Node, BakeWrangler_Tree_Node):
    '''Output image path node'''
    bl_label = 'Output Image Path'
    
    # Returns the most identifing string for the node
    def get_name(self):
        name = BakeWrangler_Tree_Node.get_name(self)
        if self.img_name:
            name += " (%s)" % (self.img_name)
        return name
    
    # Check node settings are valid to bake. Returns true/false, plus error message(s).
    def validate(self):
        valid = [True]
        # Validate inputs
        has_valid_input = False
        for input in self.inputs:
            if input.is_linked and input.links[0].is_valid and input.valid:
                has_valid_input = True
                break
        if not has_valid_input:
            valid[0] = False
            valid.append(_print("Has no valid inputs connected", node=self, ret=True))
        # Validate file path
        if not os.path.isdir(os.path.abspath(self.img_path)):
            valid[0] = False
            valid.append(_print("Invalid path '%s'" % (os.path.abspath(self.img_path)), node=self, ret=True))
        # Check if there is read/write access to the file/directory
        file_path = os.path.join(os.path.abspath(self.img_path), self.img_name)
        if os.path.exists(file_path):
            if os.path.isfile(file_path):
                # It exists so try to open it r/w
                try:
                    file = open(file_path, "a")
                except OSError as err:
                    valid[0] = False
                    valid.append(_print("Error trying to open file at '%s'" % (err.strerror), node=self, ret=True))
                else:
                    # See if it can be read as an image
                    file.close()
                    file_img = bpy.data.images.load(file_path)
                    if not len(file_img.pixels):
                        valid[0] = False
                        valid.append(_print("File exists but doesn't seem to be a known image format", node=self, ret=True))
                    bpy.data.images.remove(file_img)
            else:
                # It exists but isn't a file
                valid[0] = False
                valid.append(_print("File exists but isn't a regular file at '%s'" % (file_path), node=self, ret=True))
        else:
            # See if it can be created
            try:
                file = open(file_path, "a")
            except OSError as err:
                valid[0] = False
                valid.append(_print("%s trying to create file at '%s'" % (err.strerror, file_path), node=self, ret=True))
            else:
                file.close()
                os.remove(file_path)
        # Validated
        return valid
    
    def update_path(self, context):
        cwd = os.path.dirname(bpy.data.filepath)
        path = os.path.normpath(os.path.join(cwd, bpy.path.abspath(self.img_path)))
        if self.img_path != path:
            self.img_path = path
        
    def update_ext(self, context):
        name, ext = os.path.splitext(self.img_name)
        if ext:
            for enum, iext in self.img_ext:
                if ext.lower() == iext:
                    for enum, iext in self.img_ext:
                        if self.img_type == enum:
                            self.img_name = name + iext
                            break
                    break
    
    # Recreate image format drop down as the built in one doesn't seem usable? Also most of the settings
    # for the built in image settings selector don't seem applicable to saving from script...
    img_format = (
        ('BMP', "BMP", "Output image in bitmap format."),
        ('IRIS', "Iris", "Output image in (old!) SGI IRIS format."),
        ('PNG', "PNG", "Output image in PNG format."),
        ('JPEG', "JPEG", "Output image in JPEG format."),
        ('JPEG2000', "JPEG 2000", "Output image in JPEG 2000 format."),
        ('TARGA', "Targa", "Output image in Targa format."),
        ('TARGA_RAW', "Targa Raw", "Output image in uncompressed Targa format."),
        ('CINEON', "Cineon", "Output image in Cineon format."),
        ('DPX', "DPX", "Output image in DPX format."),
        ('OPEN_EXR_MULTILAYER', "OpenEXR MultiLayer", "Output image in multilayer OpenEXR format."),
        ('OPEN_EXR', "OpenEXR", "Output image in OpenEXR format."),
        ('HDR', "Radiance HDR", "Output image in Radiance HDR format."),
        ('TIFF', "TIFF", "Output image in TIFF format."),
    )
    
    img_ext = (
        ('BMP', ".bmp"),
        ('IRIS', ".rgb"),
        ('PNG', ".png"),
        ('JPEG', ".jpg"),
        ('JPEG2000', ".jp2"),
        ('TARGA', ".tga"),
        ('TARGA_RAW', ".tga"),
        ('CINEON', ".cin"),
        ('DPX', ".dpx"),
        ('OPEN_EXR_MULTILAYER', ".exr"),
        ('OPEN_EXR', ".exr"),
        ('HDR', ".hdr"),
        ('TIFF', ".tif"),
    )
    
    img_color_modes = (
        ('BW', "BW", "Image saved in 8 bit grayscale"),
        ('RGB', "RGB", "Image saved with RGB (color) data"),
        ('RGBA', "RGBA", "Image saved with RGB and Alpha data"),
    )
    
    img_color_modes_noalpha = (
        ('BW', "BW", "Image saved in 8 bit grayscale"),
        ('RGB', "RGB", "Image saved with RGB (color) data"),
    )
    
    img_color_depths_8_16 = (
        ('8', "8", "8 bit color channels"),
        ('16', "16", "16 bit color channels"),
    )
    
    img_color_depths_8_12_16 = (
        ('8', "8", "8 bit color channels"),
        ('12', "12", "12 bit color channels"),
        ('16', "16", "16 bit color channels"),
    )
    
    img_color_depths_8_10_12_16 = (
        ('8', "8", "8 bit color channels"),
        ('10', "10", "10 bit color channels"),
        ('12', "12", "12 bit color channels"),
        ('16', "16", "16 bit color channels"),
    )
    
    img_color_depths_16_32 = (
        ('16', "Float (Half)", "16 bit color channels"),
        ('32', "Float (Full)", "32 bit color channels"),
    )
    
    img_codecs_jpeg2k = (
        ('JP2', "JP2", ""),
        ('J2K', "J2K", ""),
    )
    
    img_codecs_openexr = (
        ('DWAA', "DWAA (lossy)", ""),
        ('B44A', "B44A (lossy)", ""),
        ('ZIPS', "ZIPS (lossless)", ""),
        ('RLE', "RLE (lossless)", ""),
        ('RLE', "RLE (lossless)", ""),
        ('PIZ', "PIZ (lossless)", ""),
        ('ZIP', "ZIP (lossless)", ""),
        ('PXR24', "Pxr24 (lossy)", ""),
        ('NONE', "None", ""),
    )    
    
    img_codecs_tiff = (
        ('PACKBITS', "Pack Bits", ""),
        ('LZW', "LZW", ""),
        ('DEFLATE', "Deflate", ""),
        ('NONE', "None", ""),
    )
    
    img_color_spaces = (
        ('Filmic Log', "Filmic Log", "Log based filmic shaper with 16.5 stops of latitude, and 25 stops of dynamic range"),
        ('Linear', "Linear", "Rec. 709 (Full Range), Blender native linear space"),
        ('Linear ACES', "Linear ACES", "ACES linear space"),
        ('Non-Color', "Non-Color", "Color space used for images which contains non-color data (i,e, normal maps)"),
        ('Raw', "Raw", "Raw"),
        ('sRGB', "sRGB", "Standard RGB Display Space"),
        ('XYZ', "XYZ", "XYZ"),
    )
    
    # Properties that are part of the ImageFormatSettings data, recreated here because that data block isn't usable by mods
    # Color Modes
    img_color_mode: bpy.props.EnumProperty(name="Color", description="Choose BW for saving grayscale images, RGB for saving red, green and blue channels, and RGBA for saving red, green, blue and alpha channels", items=img_color_modes, default='RGB')
    img_color_mode_noalpha: bpy.props.EnumProperty(name="Color", description="Choose BW for saving grayscale images, RGB for saving red, green and blue channels", items=img_color_modes_noalpha, default='RGB')
    
    # Color Depths
    img_color_depth_8_16: bpy.props.EnumProperty(name="Color Depth", description="Bit depth per channel", items=img_color_depths_8_16, default='8')
    img_color_depth_8_12_16: bpy.props.EnumProperty(name="Color Depth", description="Bit depth per channel", items=img_color_depths_8_12_16, default='8')
    img_color_depth_8_10_12_16: bpy.props.EnumProperty(name="Color Depth", description="Bit depth per channel", items=img_color_depths_8_10_12_16, default='8')
    img_color_depth_16_32: bpy.props.EnumProperty(name="Color Depth", description="Bit depth per channel", items=img_color_depths_16_32, default='16')
    
    # Compression / Quality
    img_compression: bpy.props.IntProperty(name="Compression", description="Amount of time to determine best compression: 0 = no compression, 100 = maximum lossless compression", default=15, min=0, max=100, subtype='PERCENTAGE')
    img_quality: bpy.props.IntProperty(name="Quality", description="Quality for image formats that support lossy compression", default=90, min=0, max=100, subtype='PERCENTAGE')
    
    # Codecs
    img_codec_jpeg2k: bpy.props.EnumProperty(name="Codec", description="Codec settings for jpeg2000", items=img_codecs_jpeg2k, default='JP2')
    img_codec_openexr: bpy.props.EnumProperty(name="Codec", description="Codec settings for OpenEXR", items=img_codecs_openexr, default='ZIP')
    img_codec_tiff: bpy.props.EnumProperty(name="Compression", description="Compression mode for TIFF", items=img_codecs_tiff, default='DEFLATE')
    
    # Other random image format settings
    img_jpeg2k_cinema: bpy.props.BoolProperty(name="Cinema", description="Use Openjpeg Cinema Preset", default=True)
    img_jpeg2k_cinema48: bpy.props.BoolProperty(name="Cinema (48)", description="Use Openjpeg Cinema Preset (48 fps)", default=False)
    img_jpeg2k_ycc: bpy.props.BoolProperty(name="YCC", description="Save luminance-chrominance-chrominance channels instead of RGB colors", default=False)
    img_dpx_log: bpy.props.BoolProperty(name="Log", description="Convert to logarithmic color space", default=False)
    img_openexr_zbuff: bpy.props.BoolProperty(name="Z Buffer", description="Save the z-depth per pixel (32 bit unsigned int z-buffer)", default=True)
    
    img_color_space: bpy.props.EnumProperty(name="Color Space", description="Color space to use when saving the image", items=img_color_spaces, default='sRGB')
    #image: bpy.props.PointerProperty(type=bpy.types.Image)
    img_path: bpy.props.StringProperty(name="Output Path", description="Path to save image in", default="", subtype='DIR_PATH', update=update_path)
    img_name: bpy.props.StringProperty(name="Output File", description="File to save image in", default="Image", subtype='FILE_NAME')
    img_type: bpy.props.EnumProperty(name="Image Format", description="File format to save bake as", items=img_format, default='PNG', update=update_ext)
    img_xres: bpy.props.IntProperty(name="Image X resolution", description="Number of horizontal pixels in image. Bake pass data will be scaled to fit the image size. Power of 2 sizes are usually best for exporting", default=2048, min=1, subtype='PIXEL')
    img_yres: bpy.props.IntProperty(name="Image Y resolution", description="Number of vertical pixels in image. Bake pass data will be scaled to fit the image size. Power of 2 sizes are usually best for exporting", default=2048, min=1, subtype='PIXEL')

    def init(self, context):
        # Sockets IN
        self.inputs.new('BakeWrangler_Socket_Color', "Color")
        # Sockets OUT
        self.inputs.new('BakeWrangler_Socket_Float', "Alpha")
        self.inputs.new('BakeWrangler_Socket_Float', "R")
        self.inputs.new('BakeWrangler_Socket_Float', "G")
        self.inputs.new('BakeWrangler_Socket_Float', "B")
        
        # Set initial output format to what ever is currently selected in the render settings (if it's in the list)
        for type, name, desc in self.img_format:
            if bpy.context.scene.render.image_settings.file_format == type:
                self.img_type = type
                # Set the extension
                for enum, ext in self.img_ext:
                    if enum == type:
                        self.img_name += ext
                break

    def draw_buttons(self, context, layout):
        #layout.template_ID(self, "image", new="image.new", open="image.open")
        if self.id_data.baking != None:
            layout.operator("bake_wrangler_op.dummy", icon='RENDER_STILL', text="Bake Image")
        else:
            op = layout.operator("bake_wrangler_op.bake_image", icon='IMAGE')
            op.tree = self.id_data.name
            op.node = self.name
        layout.label(text="Image Path:")
        layout.prop(self, "img_path", text="")
        layout.prop(self, "img_name", text="")
        split = layout.split(factor=0.4)
        split.label(text="Format:")
        split.prop(self, "img_type", text="")
        split = layout.split(factor=0.2)
        split.label(text="X:")
        split.prop(self, "img_xres", text="")
        split = layout.split(factor=0.2)
        split.label(text="Y:")
        split.prop(self, "img_yres", text="")
        # Color Spaces
        if self.img_type != 'CINEON':
            split = layout.split(factor=0.4)
            split.label(text="Space:")
            split.prop(self, "img_color_space", text="")
        # Color Modes
        if self.img_type == 'BMP' or self.img_type == 'JPEG' or self.img_type == 'CINEON' or self.img_type == 'HDR':
            split = layout.split(factor=0.4)
            split.label(text="Color:")
            split.prop(self, "img_color_mode_noalpha", text="")
        if self.img_type == 'IRIS' or self.img_type == 'PNG' or self.img_type == 'JPEG2000' or self.img_type == 'TARGA' or self.img_type == 'TARGA_RAW' or self.img_type == 'DPX' or self.img_type == 'OPEN_EXR_MULTILAYER' or self.img_type == 'OPEN_EXR' or self.img_type == 'TIFF':
            split = layout.split(factor=0.4)
            split.label(text="Color:")
            split.prop(self, "img_color_mode", text="")
        # Color Depths
        if self.img_type == 'PNG' or self.img_type == 'TIFF':
            split = layout.split(factor=0.4)
            split.label(text="Depth:")
            split.prop(self, "img_color_depth_8_16", text="")
        if self.img_type == 'JPEG2000':
            split = layout.split(factor=0.4)
            split.label(text="Depth:")
            split.prop(self, "img_color_depth_8_12_16", text="")
        if self.img_type == 'DPX':
            split = layout.split(factor=0.4)
            split.label(text="Depth:")
            split.prop(self, "img_color_depth_8_10_12_16", text="")
        if self.img_type == 'OPEN_EXR_MULTILAYER' or self.img_type == 'OPEN_EXR':
            split = layout.split(factor=0.4)
            split.label(text="Depth:")
            split.prop(self, "img_color_depth_16_32", text="")
        # Compression / Quality
        if self.img_type == 'PNG':
            split = layout.split(factor=0.4)
            split.label(text="Compression:")
            split.prop(self, "img_compression", text="")
        if self.img_type == 'JPEG' or self.img_type == 'JPEG2000':
            split = layout.split(factor=0.4)
            split.label(text="Quality:")
            split.prop(self, "img_quality", text="")
        # Codecs
        if self.img_type == 'JPEG2000':
            split = layout.split(factor=0.4)
            split.label(text="Codec:")
            split.prop(self, "img_codec_jpeg2k", text="")
        if self.img_type == 'OPEN_EXR' or self.img_type == 'OPEN_EXR_MULTILAYER':
            split = layout.split(factor=0.4)
            split.label(text="Codec:")
            split.prop(self, "img_codec_openexr", text="")
        if self.img_type == 'TIFF':
            split = layout.split(factor=0.4)
            split.label(text="Compression:")
            split.prop(self, "img_codec_tiff", text="")
        # Other random image settings
        if self.img_type == 'JPEG2000':
            layout.prop(self, "img_jpeg2k_cinema")
            layout.prop(self, "img_jpeg2k_cinema48")
            layout.prop(self, "img_jpeg2k_ycc")
        if self.img_type == 'DPX':
            layout.prop(self, "img_dpx_log")
        if self.img_type == 'OPEN_EXR':
            layout.prop(self, "img_openexr_zbuff")
    
    def update(self):
        # Links can get inserted without calling insert_link, but update is called.
        for socket in self.inputs:
            if socket.is_linked and not socket.valid:
                self.insert_link(socket.links[0])
                
    # Validate incoming links
    def insert_link(self, link):
        if link.to_node == self:
            if link.from_node.bl_idname == 'BakeWrangler_Bake_Pass':
                link.to_socket.valid = True
            else:
                link.to_socket.valid = False
        

# Output controller node provides batch execution of multiple conntected bake passes. 
class BakeWrangler_Output_Oven(Node, BakeWrangler_Tree_Node):
    '''Output controller oven node'''
    bl_label = 'Oven'
    
    # Returns the most identifing string for the node
    def get_name(self):
        name = BakeWrangler_Tree_Node.get_name()
        return name

    def init(self, context):
        self.inputs.new('BakeWrangler_Socket_Recipe', "Recipe")

    def draw_buttons(self, context, layout):
        layout.label(text="add recipe button")
        


#
# Node Categories
#

import nodeitems_utils
from nodeitems_utils import NodeCategory, NodeItem

# Base class for the node category menu system
class BakeWrangler_Node_Category(NodeCategory):
    @classmethod
    def poll(cls, context):
        return context.space_data.tree_type == 'BakeWrangler_Tree'

# List of all bakery nodes put into categories with identifier, name
BakeWrangler_Node_Categories = [
    BakeWrangler_Node_Category('Inputs', "Inputs", items=[
        NodeItem("BakeWrangler_Input_HighPolyMesh"),
        NodeItem("BakeWrangler_Input_Mesh"),
    ]),
    BakeWrangler_Node_Category('Baking', "Baking", items=[
        NodeItem("BakeWrangler_Bake_Pass"),
    ]),
    BakeWrangler_Node_Category('Outputs', "Outputs", items=[
        NodeItem("BakeWrangler_Output_Image_Path"),
        NodeItem("BakeWrangler_Output_Oven"),
    ]),
]



#
# Registration
#

# All bakery classes that need to be registered
classes = (
    BakeWrangler_Operator_Dummy,
    BakeWrangler_Operator_BakeStop,
    BakeWrangler_Operator_BakePass,
    BakeWrangler_Operator_BakeImage,
    BakeWrangler_Tree,
    BakeWrangler_Socket_HighPolyMesh,
    BakeWrangler_Socket_Mesh,
    BakeWrangler_Socket_Pass,
    BakeWrangler_Socket_Color,
    BakeWrangler_Socket_Float,
    BakeWrangler_Input_HighPolyMesh,
    BakeWrangler_Input_Mesh,
    BakeWrangler_Bake_Pass,
    BakeWrangler_Output_Image_Path,
    BakeWrangler_Output_Oven,
)


def register():
    from bpy.utils import register_class
    for cls in classes:
        register_class(cls)

    nodeitems_utils.register_node_categories('BakeWrangler_Nodes', BakeWrangler_Node_Categories)


def unregister():
    nodeitems_utils.unregister_node_categories('BakeWrangler_Nodes')

    from bpy.utils import unregister_class
    for cls in reversed(classes):
        unregister_class(cls)


if __name__ == "__main__":
    register()
