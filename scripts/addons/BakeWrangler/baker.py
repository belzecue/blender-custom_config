import os.path
import bpy
from datetime import datetime
try:
    from BakeWrangler.nodes import node_tree
    from BakeWrangler.nodes.node_tree import _print
    from BakeWrangler.nodes.node_tree import material_recursor
except:
    import sys
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from nodes import node_tree
    from nodes.node_tree import _print
    from nodes.node_tree import material_recursor



# Process the node tree with the given node as the starting point
def process_tree(tree_name, node_name):
    # Create a base scene to work from that has every object in it
    global base_scene
    base_scene = bpy.data.scenes.new("BakeWrangler_Base")
    bpy.context.window.scene = base_scene
    for obj in bpy.data.objects:
        base_scene.collection.objects.link(obj)
    # Add a property on objects that can link to a copy made
    bpy.types.Object.bw_copy = bpy.props.PointerProperty(name="Object Copy", description="Copy with some data not applied", type=bpy.types.Object)
    
    # Get tree position
    tree = bpy.data.node_groups[tree_name]
    node = tree.nodes[node_name]
    err = False
    
    _print("> Processing [%s]" % (node.get_name()), tag=True)
    _print(">", tag=True)
    if debug: _print("> Debugging output enabled", tag=True)
        
    # Decide how to process tree based on starting node type
    if node.bl_idname == 'BakeWrangler_Bake_Pass':
        # A Bake Pass node should bake all attached meshes to a single image then generate all attached outputs
        err, img_bake, img_mask = process_bake_pass_input(node)
        err += process_bake_pass_output(node, img_bake, img_mask)
        
    elif node.bl_idname == 'BakeWrangler_Output_Image_Path':
        # An Image Path node should bake all attached Bake Pass nodes, but only process the results for itself
        req_passes = []
        req_channs = 0
        for input in node.inputs:
            if input.is_linked and input.valid and input.links[0].is_valid:
                link = input.links[0]
                req_channs += 1
                if not req_passes.count(link.from_node):
                    req_passes.append(link.from_node)
                    
        _print("> Generating [%i] passes for [%i] input channels:" % (len(req_passes), req_channs), tag=True)
        _print(">", tag=True)
        
        for bake_pass in req_passes:
            _print("> [%s]" % (bake_pass.get_name()), tag=True)
            err, img_bake, img_mask = process_bake_pass_input(bake_pass)
            err += process_bake_pass_output(bake_pass, img_bake, img_mask, node)
            if bake_pass != req_passes[-1]:
                _print(">", tag=True)
                
    elif node.bl_idname == 'BakeWrangler_Output_Batch_Bake':
        # Batch process node will have a number of Image Path nodes connected. Most efficient process should
        # be to determine all required unique bake passes and perform them same as in the Bake Pass case
        req_passes = []
        total_imgs = []
        for input in node.inputs:
            if input.is_linked and input.valid and input.links[0].is_valid:
                output_img = input.links[0].from_node
                if not total_imgs.count(output_img):
                    total_imgs.append(output_img)
                for bake in output_img.inputs:
                    if bake.is_linked and bake.valid and bake.links[0].is_valid:
                        link = bake.links[0]
                        if not req_passes.count(link.from_node):
                            req_passes.append(link.from_node)
                            
        _print("> Generating [%i] passes for [%i] output images:" % (len(req_passes), len(total_imgs)), tag=True)
        _print(">", tag=True)
        
        for bake_pass in req_passes:
            _print("> [%s]" % (bake_pass.get_name()), tag=True)
            err, img_bake, img_mask = process_bake_pass_input(bake_pass)
            err += process_bake_pass_output(bake_pass, img_bake, img_mask)
            if bake_pass != req_passes[-1]:
                _print(">", tag=True)
                
    return err



# Pretty much everything here is about preventing blender crashing or failing in some way that only happens
# when it runs a background bake. Perhaps it wont be needed some day, but for now trying to keep all such
# things in one place. Modifiers are applied or removed and non mesh types are converted.
def prep_objects_for_bake(object, bake_strategy):
    # Make obj the only selected + active
    bpy.ops.object.select_all(action='DESELECT')
    object.select_set(True)
    bpy.context.view_layer.objects.active = object
    
    # Deal with mods
    if len(object.modifiers):
        has_multires = False
        for mod in object.modifiers:
            # Handle mulires differently
            if mod.type == 'MULTIRES' and mod.show_render:
                has_multires = True
                continue
            if mod.show_render:
                # A mod can be disabled by invalid settings, which will throw an exception when trying to apply it
                try:
                    bpy.ops.object.modifier_apply(modifier=mod.name)
                except:
                    _print(">    Error applying modifier '%s' to object '%s'" % (mod.name, object.name), tag=True) 
                    bpy.ops.object.modifier_remove(modifier=mod.name)
            else:
                bpy.ops.object.modifier_remove(modifier=mod.name)
        # Need to make a copy with multires mod intact
        if has_multires:
            copy = object.copy()
            copy.data = object.data.copy()
            copy.name = "BW_" + object.name
            object.bw_copy = copy
            base_scene.collection.objects.link(copy)
            # Now apply the multires mods
            for mod in object.modifiers:
                if mod.show_render:
                    # A mod can be disabled by invalid settings, which will throw an exception when trying to apply it
                    try:
                        bpy.ops.object.modifier_apply(modifier=mod.name)
                    except:
                        _print(">    Error applying modifier '%s' to object '%s'" % (mod.name, object.name), tag=True) 
                        bpy.ops.object.modifier_remove(modifier=mod.name)
                else:
                    bpy.ops.object.modifier_remove(modifier=mod.name)
            
    # Deal with object type
    if object.type != 'MESH':
        # Apply render resolution if its set before turning into a mesh
        if object.type == 'META':
            if object.data.render_resolution > 0:
                object.data.resolution = object.data.render_resolution
        else:
            if object.data.render_resolution_u > 0:
                object.data.resolution_u = object.data.render_resolution_u
            if object.data.render_resolution_v > 0:
                object.data.resolution_v = object.data.render_resolution_v
        # Convert
        bpy.ops.object.convert(target='MESH')
            
            
    
# Takes a bake pass node and returns the baked image and baked mask
def process_bake_pass_input(node):
    pass_start = datetime.now()
    err = False
    
    # Gather pass settings
    bake_mesh = []
    img_bake = None
    img_mask = None
    bake_dev = node.bake_device
    bake_samp = node.bake_samples
    mask_samp = node.mask_samples
    bake_type = node.bake_pass
    x_res = node.bake_xres
    y_res = node.bake_yres
    # Settings for normal pass
    norm_s = node.norm_space
    norm_r = node.norm_R
    norm_g = node.norm_G
    norm_b = node.norm_B
    # Settings for curvature pass
    curve_px = node.curve_px
    # Settings for passes with selectable influence
    infl_direct = node.use_direct
    infl_indirect = node.use_indirect
    infl_color = node.use_color
    # Settings for what to combine in combined pass
    comb_diffuse = node.use_diffuse
    comb_glossy = node.use_glossy
    comb_trans = node.use_transmission
    comb_subsurf = node.use_subsurface
    comb_ao = node.use_ao
    comb_emit = node.use_emit
    
    # Set up the pass influences if the bake uses them
    pass_influences = set()
    if bake_type in node.bake_has_influence:
        if infl_direct:
            pass_influences.add('DIRECT')
        if infl_indirect:
            pass_influences.add('INDIRECT')
        if infl_color:
            pass_influences.add('COLOR')
        if bake_type == 'COMBINED':
            if comb_diffuse:
                pass_influences.add('DIFFUSE')
            if comb_glossy:
                pass_influences.add('GLOSSY')
            if comb_trans:
                pass_influences.add('TRANSMISSION')
            if comb_subsurf:
                pass_influences.add('SUBSURFACE')
            if comb_ao:
                pass_influences.add('AO')
            if comb_emit:
                pass_influences.add('EMIT')
                
    # Get bake mesh inputs
    inputs = node.inputs
    for input in inputs:
        if input.is_linked and input.valid:
            if not bake_mesh.count(input.links[0].from_node):
                bake_mesh.append(input.links[0].from_node)
    
    _print(">  Bake Mesh: %i" % (len(bake_mesh)), tag=True)
    
    # Generate the bake and mask images
    img_bake = bpy.data.images.new(node.get_name(), width=x_res, height=y_res)
    img_bake.alpha_mode = 'NONE'
    img_bake.colorspace_settings.name = 'Non-Color'
    img_bake.colorspace_settings.is_data = True
    if bake_type in ['NORMAL', 'CURVATURE', 'CURVE_SMOOTH']:
        img_bake.generated_color = (0.5, 0.5, 1.0, 1.0)
    img_bake.use_generated_float = True
                
    img_mask = bpy.data.images.new("mask_" + node.get_name(), width=x_res, height=y_res)
    img_mask.alpha_mode = 'NONE'
    img_mask.colorspace_settings.name = 'Non-Color'
    img_mask.colorspace_settings.is_data = True
    
    # Begin processing bake meshes
    for mesh in bake_mesh:
        active_meshes = mesh.get_objects('TARGET')
        selected_objs = mesh.get_objects('SOURCE')
        scene_objs = mesh.get_objects('SCENE')
        
        _print(">   %i/%i: [%s] with %i active meshes" % ((bake_mesh.index(mesh) + 1), len(bake_mesh), mesh.get_name(), len(active_meshes)), tag=True)
        # Gather settings for this mesh. Validation should have been done before this script was ever run
        # so all settings will be assumed valid.
        margin = mesh.margin
        padding = mesh.mask_margin
        multi = mesh.multi_res
        multi_pass = mesh.multi_res_pass
        ray_dist = mesh.ray_dist
        
        # Process each active mesh
        for active in active_meshes:
            # Load in template bake scene with mostly optimized settings for baking
            bake_scene_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "resources", "BakeWrangler_Scene.blend")
            with bpy.data.libraries.load(bake_scene_path, link=False, relative=False) as (file_from, file_to):
                file_to.scenes.append("BakeWrangler")
            bake_scene = file_to.scenes[0]
            # Set the cycles values that aren't saved in the template and give it a name that can be traced
            bake_scene.cycles.device = bake_dev
            bake_scene.cycles.samples = bake_samp
            bake_scene.cycles.aa_samples = bake_samp
            bake_scene.name = "bake_" + node.get_name() + "_" + mesh.get_name() + "_" + active[0].name
            
            # Firstly there are two main categories of bake. Either the bake is of some data that blender can calculate
            # (normals, roughness, etc) or it is of some property of the material (albedo, metalness, etc). The first set
            # don't require any changes to be made to materials, while the second set do.
            # Then there are three possibilities for where to get the data. For a single object, the data comes from its
            # own materials. A sub case of this is using a multires modifier to get some data (normals). Finally many
            # objects can be mapped to the surface of the target, in which case the materials on the target don't matter,
            # but the materials on everything else does.
            
            cage = False
            cage_object = None
            cage_obj_name = ""
            to_active = False
            
            # Determine what strategy to use for this bake and set up the data for it
            bake_strategy = ''
            if multi == True:
                bake_strategy = 'MULTI'
            else:
                select_check = False
                for obj in selected_objs:
                    if obj[0] != active[0]:
                        select_check = True
                if select_check:
                    bake_strategy = 'TOACT'
                    to_active = True
                else:
                    bake_strategy = 'SOLO'
                
            # Regardless of strategy the following data will be used. Copies are made so other passes can get the originals
            prep_objects_for_bake(active[0], bake_strategy)
            act = active[0]
            if multi:
                act = active[0].bw_copy
            target = act.copy()
            target.data = act.data.copy()
            bake_scene.collection.objects.link(target)
            
            # Copy all scene objects over if not a multi-res pass
            if not multi:
                scene = bpy.data.collections.new("Scene_" + active[0].name)
                for obj in scene_objs:
                    copy = obj[0].copy()
                    copy.data = obj[0].data.copy()
                    scene.objects.link(copy)
                bake_scene.collection.children.link(scene)
            
            # Set UV map to use if one was selected
            if len(active) > 1 and active[1] not in [None, ""]:
                target.data.uv_layers.active = target.data.uv_layers[active[1]]
            
            # Copy all selected objects over if 'to active' pass
            if to_active:
                selected = bpy.data.collections.new("Selected_" + active[0].name)
                for obj in selected_objs:
                    if obj[0] != active[0]:
                        prep_objects_for_bake(obj[0], bake_strategy)
                        copy = obj[0].copy()
                        copy.data = obj[0].data.copy()
                        selected.objects.link(copy)
                bake_scene.collection.children.link(selected)
                # Materials should be removed from the target copy for To active
                target.data.materials.clear()
                target.data.polygons.foreach_set('material_index', [0] * len(target.data.polygons))
                target.data.update()
                # Add the cage copy to the scene because it doesn't work properly in a different scene currently
                if len(active) > 2 and active[2]:
                    cage = True
                    prep_objects_for_bake(active[2], bake_strategy)
                    cage_object = active[2].copy()
                    cage_object.data = active[2].data.copy()
                    bake_scene.collection.objects.link(cage_object)
                    cage_obj_name = cage_object.name
                    
            # Switch into bake scene
            bpy.context.window.scene = bake_scene
                
            # Select the target and make it active
            bpy.ops.object.select_all(action='DESELECT')
            target.select_set(True)
            bpy.context.view_layer.objects.active = target
            
            # Make single user copies of all materials still in play
            bpy.ops.object.select_all(action='SELECT')
            
            # De-select the cage if its in use
            if cage:
                cage_object.select_set(False)
                
            # De-select scene only items
            for obj in scene.objects:
                obj.select_set(False)
            bpy.ops.object.make_single_user(type='SELECTED_OBJECTS', object=False, obdata=False, material=True, animation=False)
            
            # Collect a list of all the materials, making sure each is only added once
            unique_mats = []
            if bake_strategy == 'TOACT':
                # Get materials from all the objects except the target
                for obj in selected.objects:
                    has_mat = False
                    if bake_type == 'CAVITY' and len(obj.material_slots):
                        for slot in obj.material_slots:
                            # Replace texture with cavity shader
                            if slot.material != None:
                                slot.material = cavity_shader
                    if len(obj.data.materials):
                        for mat in obj.data.materials:
                            # Slots can be empty
                            if mat != None:
                                has_mat = True
                                if unique_mats.count(mat) == 0:
                                    unique_mats.append(mat)
                    if not has_mat:
                        # If the object has no materials, one needs to be added for the mask baking step or for cavity map
                        if bake_type == 'CAVITY':
                            mat = cavity_shader
                        else:
                            mat = bpy.data.materials.new(name="mask_" + obj.name)
                            mat.use_nodes = True
                        obj.data.materials.append(mat)
                        if unique_mats.count(mat) == 0:
                            unique_mats.append(mat)
            else:
                # Get materials from only the target and add cavity shader if needed
                if bake_type == 'CAVITY':
                    if len(target.material_slots):
                        for slot in target.material_slots:
                            # Replace texture with cavity shader
                            if slot.material != None:
                                slot.material = cavity_shader
                    else:
                        target.data.materials.append(cavity_shader)
                if len(target.data.materials):
                    for mat in target.data.materials:
                        # Slots can be empty
                        if mat != None:
                            if unique_mats.count(mat) == 0:
                                unique_mats.append(mat)
                                    
            # Add simple image node material to target object for To active bake or if it doesn't have a material
            if bake_strategy == 'TOACT' or len(target.data.materials) < 1:
                mat = bpy.data.materials.new(name="mat_" + node.get_name() + "_" + mesh.get_name())
                mat.use_nodes = True
                image_node = mat.node_tree.nodes.new("ShaderNodeTexImage")
                image_node.image = img_bake
                image_node.select = True
                mat.node_tree.nodes.active = image_node
                target.data.materials.append(mat)
            
            # Prepare the materials for the bake type
            for mat in unique_mats:
                if debug: _print(">    Preparing material [%s] for [%s] bake" % (mat.name, bake_type), tag=True)
                prep_material_for_bake(node, mat.node_tree, bake_type)
                
                if bake_strategy != 'TOACT':
                    # For non To active bakes, add an image node to the material and make it selected + active for bake image
                    image_node = mat.node_tree.nodes.new("ShaderNodeTexImage")
                    image_node.image = img_bake
                    image_node.select = True
                    mat.node_tree.nodes.active = image_node
            
            # Set 'real' bake pass. PBR use EMIT rather than the named pass, since those passes don't exist.
            if bake_type in node.bake_pbr:
                real_bake_type = 'EMIT'
            elif bake_type in ['CURVATURE', 'CURVE_SMOOTH']:
                real_bake_type = 'NORMAL'
                norm_s = 'TANGENT'
                norm_r = 'POS_X'
                norm_g = 'POS_Y'
                norm_b = 'POS_Z'
            else:
                real_bake_type = bake_type
                
            if debug: _print(">     Real bake type set to [%s]" % (real_bake_type), tag=True)
                
            # Update view layer to be safe
            bpy.context.view_layer.update()
            start = datetime.now()
            _print(">    -Baking %s pass: " % (bake_type), tag=True, wrap=False)
            
            # Do the bake. Most of the properties can be passed as arguments to the operator.
            try:
                if bake_strategy != 'MULTI':
                    bpy.ops.object.bake(
                        type=real_bake_type,
                        pass_filter=pass_influences,
                        margin=margin,
                        use_selected_to_active=to_active,
                        cage_extrusion=ray_dist,
                        cage_object=cage_obj_name,
                        normal_space=norm_s,
                        normal_r=norm_r,
                        normal_g=norm_g,
                        normal_b=norm_b,
                        save_mode='INTERNAL',
                        use_clear=False,
                        use_cage=cage,
                        )
                else:
                    bpy.context.scene.render.use_bake_multires = True
                    bpy.context.scene.render.bake_margin = margin
                    bpy.context.scene.render.bake_type = multi_pass
                    bpy.context.scene.render.use_bake_clear = False
                    bpy.ops.object.bake_image()
            except RuntimeError as error:
                _print("%s" % (error), tag=True)
                err = True
            else:
                _print("Completed in %s" % (str(datetime.now() - start)), tag=True)
            
            # Bake the mask if samples are non zero
            if mask_samp > 0:
                # Set samples to the mask value
                bake_scene.cycles.samples = mask_samp
                bake_scene.cycles.aa_samples = mask_samp
                
                # Requires adding a pure while emit shader to all the materials first and changing target image
                for mat in unique_mats:
                    prep_material_for_bake(node, mat.node_tree, 'MASK')
                    
                    if bake_strategy != 'TOACT':
                        # Add image node to material and make it selected + active
                        image_node = mat.node_tree.nodes.new("ShaderNodeTexImage")
                        image_node.image = img_mask
                        image_node.select = True
                        mat.node_tree.nodes.active = image_node
                
                if bake_strategy == 'TOACT':
                    # Add image node to target and make it selected + active (should only be one material at this point)
                    image_node = target.data.materials[0].node_tree.nodes.new("ShaderNodeTexImage")
                    image_node.image = img_mask
                    image_node.select = True
                    target.data.materials[0].node_tree.nodes.active = image_node
                
                # Update view layer to be safe
                bpy.context.view_layer.update()
                start = datetime.now()
                _print(">    -Baking MASK pass: ", tag=True, wrap=False)
                
                try:
                    bpy.ops.object.bake(
                        type='EMIT',
                        margin=margin + padding,
                        use_selected_to_active=to_active,
                        cage_extrusion=ray_dist,
                        cage_object=cage_obj_name,
                        save_mode='INTERNAL',
                        use_clear=False,
                        use_cage=cage,
                        )
                except RuntimeError as error:
                    _print("%s" % (error), tag=True)
                    err = True
                else:
                    _print("Completed in %s" % (str(datetime.now() - start)), tag=True)
            
            # Switch back to main scene before next pass. Nothing will be deleted so that the file can be examined for debugging.
            bpy.context.window.scene = base_scene
    
    # Perform compositor pass if needed
    if bake_type == 'CURVATURE' or bake_type == 'CURVE_SMOOTH':
        start = datetime.now()
        _print(">   Compositing passes: ", tag=True, wrap=False)
        
        if debug: _print(">   Switching to compositor scene", tag=True)
        
        # Switch into compositor scene
        bpy.context.window.scene = compositor_scene      
        
        # Hook up the correct compositor tree to the output node and set the input to the bake data
        if debug: _print(">   Setting composit tree input and output", tag=True)
        comp_nodes = bpy.context.window.scene.node_tree.nodes
        comp_links = bpy.context.window.scene.node_tree.links
        if bake_type == 'CURVATURE':
            comp_out = 'curve_out'
        else:
            comp_out = 'curve_smooth_out'
        
        comp_nodes['bw_smooth_input'].image = img_bake
        comp_links.new(comp_nodes[comp_out].outputs[0], comp_nodes['bw_smooth_render'].inputs[0])
        
        # Render output
        bpy.context.window.scene.render.resolution_x = x_res
        bpy.context.window.scene.render.resolution_y = y_res
        bpy.ops.render.render(write_still=True, use_viewport=False)
        comp_img = bpy.data.images.load(bpy.context.window.scene.render.filepath + bpy.context.window.scene.render.file_extension)
        
        if debug: _print(">   Copying composit image (%dpx) to bake data (%dpx)" % (len(comp_img.pixels), len(img_bake.pixels)), tag=True)
        
        # Replace bake data with composit
        if len(comp_img.pixels) == len(img_bake.pixels):
            img_bake.pixels = comp_img.pixels[:]
            img_bake.update()
        
        _print("Completed in %s" % (str(datetime.now() - start)), tag=True)
        bpy.context.window.scene = base_scene
        
    _print(">", tag=True)   
    _print(">  Input Meshes processed in %s" % (str(datetime.now() - pass_start)), tag=True)
    
    # Finished inputs, return the bakes
    return [err, img_bake, img_mask]



# Takes a bake pass node along with the generated image and mask. Processes all attached outputs. Or if a target node is given
# only outputs that go to that node will be processed.
def process_bake_pass_output(node, bake, mask, target=None):
    pass_start = datetime.now()
    err = False
    
    # Each output can link to multiple nodes, so each link must be processed
    outputs = []
    for output in node.outputs:
        if output.is_linked:
            for link in output.links:
                if link.is_valid and link.to_socket.valid:
                    if target and target != link.to_node:
                        continue
                    outputs.append([output.name, link.to_node, link.to_socket.name])
    _print(">", tag=True)
    _print(">  Output Images/Channels: %i" % (len(outputs)), tag=True)

    # Process all the valid outputs
    for bake_data, output_node, socket in outputs:
        _print(">   %i/%i: [%s]" % ((outputs.index([bake_data, output_node, socket]) + 1), len(outputs), output_node.get_name() + " {" + socket + "}"), tag=True)
        
        output_image = None
        output_size = [output_node.img_xres, output_node.img_yres]
        output_path = output_node.img_path
        output_name = output_node.img_name
        output_file = os.path.join(os.path.realpath(output_path), output_name)
        output_fill = [output_node.inputs['R'].is_linked and output_node.inputs['R'].valid,
                       output_node.inputs['G'].is_linked and output_node.inputs['G'].valid,
                       output_node.inputs['B'].is_linked and output_node.inputs['B'].valid,
                       output_node.inputs['Alpha'].is_linked and output_node.inputs['Alpha'].valid]
        
        # Convert bake to selected color space
        _print(">   - Performing color space conversion to: %s" % (output_node.img_color_space), tag=True)
        err, bake_copy, img_scene = convert_to_color_space(bake, output_node.img_color_space, node.bake_device)
        mask_copy = mask
        
        # See if the output exists or if a new file should be created
        if os.path.exists(output_file):
            # Open it
            _print(">   - Using existing file", tag=True)
            output_image = bpy.data.images.load(os.path.abspath(output_file))
        else:
            # Create it
            _print(">   - Creating file", tag=True)
            output_image = bpy.data.images.new(output_node.name + "." + output_node.label, width=output_size[0], height=output_size[1])
            output_image.filepath_raw = os.path.abspath(output_file)
            if node.bake_pass == 'NORMAL':
                output_image.generated_color = (0.5, 0.5, 1.0, 1.0)
            output_image.use_generated_float = True
        
        # Set the color space, etc
        #output_image.colorspace_settings.name = output_node.img_color_space
        output_image.colorspace_settings.name = 'Raw'
        if output_node.img_color_space == 'Non-Color':
            output_image.colorspace_settings.is_data = True
        output_image.alpha_mode = 'STRAIGHT'
        output_image.file_format = output_node.img_type
        
        # The image could be a different size to what is specified. If so, scale it to match
        if output_image.size[0] != output_size[0] or output_image.size[1] != output_size[1]:
            _print(">   -- Resolution mis-match, scaling", tag=True)
            output_image.scale(output_size[0], output_size[1])

        if debug: _print(">     Loaded image: %i x %i, %i channels, %i bpp, %i px (%i values)" % (output_image.size[0], output_image.size[1], output_image.channels, output_image.depth, len(output_image.pixels) / output_image.channels, len(output_image.pixels)), tag=True)
                
        # If the output is a different size to the bake, make a copy of the bake data and scale it to match.
        # A copy is used because multiple outputs can reference the same bake data and be different sizes, so
        # the original data needs to be preserved.
        if bake.size[0] != output_size[0] or bake.size[1] != output_size[1]:
            _print(">   - Bake resolution mis-match, scaling bake", tag=True)
            
            #bake_copy = bake.copy()
            #bake_copy.pixels = list(bake.pixels)
            bake_copy.scale(output_size[0], output_size[1])
            
            mask_copy = mask.copy()
            mask_copy.pixels = list(mask.pixels)
            mask_copy.scale(output_size[0], output_size[1])
        
        # Prepare a copy of the pixels in image, mask and output as accessing the data directly is quite slow.
        # Making a copy and working with that is many times faster for some reason.
        bake_px = list(bake_copy.pixels)
        mask_px = list()
        output_px = list(output_image.pixels)
        
        if debug: _print(">     Baked  image: %i x %i, %i channels, %i bpp, %i px (%i values)" % (bake_copy.size[0], bake_copy.size[1], bake_copy.channels, bake_copy.depth, len(bake_copy.pixels) / bake_copy.channels, len(bake_copy.pixels)), tag=True)
        
        # Color to Color could just be copied directly, but so that order of bakes doesn't matter in
        # batch mode everything will get mapped, leaving a channel empty if another pass will fill it
        map_time = datetime.now()
        _print(">   - Bake data mapping to output image: ", tag=True, wrap=False)
        # Get the bake channel
        bake_channel = 0
        if bake_data == 'Color' or bake_data == 'Value':
            pass
        elif bake_data == 'R' and bake_copy.channels > 0:
            bake_channel = 0
        elif bake_data == 'G' and bake_copy.channels > 1:
            bake_channel = 1
        elif bake_data == 'B' and bake_copy.channels > 2:
            bake_channel = 2
        else:
            _print("Error: Bake image does not have enough channels to read '%s'" % (bake_data), tag=True)
            err = True
            continue
        
        # Get the output channel
        output_channel = 0
        if socket == 'Color':
            pass
        elif socket == 'R' and output_image.channels > 0:
            output_channel = 0
        elif socket == 'G' and output_image.channels > 1:
            output_channel = 1
        elif socket == 'B' and output_image.channels > 2:
            output_channel = 2
        elif socket == 'Alpha' and output_image.channels > 3:
            output_channel = 3
        else:
            _print("Error: Output image does not have enough channels to write '%s'" % (socket), tag=True)
            err = True
            continue
        
        bake_use_mask = False
        if node.mask_samples > 0:
            mask_px = list(mask_copy.pixels)
            bake_use_mask = True
        
        # The bake will be an RGB image, but most outputs don't use all of the channels. Iterate over all
        # the pixels and map the correct bake data to the correct output channel.
        for pix in range(output_size[0] * output_size[1]):
            # Pixels are 'channels' values long
            bake_index = pix * bake_copy.channels
            out_index = pix * output_image.channels
            
            # What data should be mapped?
            if bake_use_mask and not mask_px[bake_index]:
                continue
                
            elif bake_data == 'Color':
                if socket == 'Color':
                    for chan in range(bake_copy.channels):
                        if output_image.channels > chan and not output_fill[chan]:
                            output_px[out_index + chan] = bake_px[bake_index + chan]
                else:
                    # Its not entirely clear how a color should be mapped to a single channel, so the output
                    # channel will get the relevent channel from the color, as that seems the most useful.
                    if bake_copy.channels >= output_image.channels:
                        output_px[out_index + output_channel] = bake_px[bake_index + output_channel]
                    # Fall back to just using the first value
                    else:
                        output_px[out_index + output_channel] = bake_px[bake_index]
                    
            # Value should be the highest value channel, excluding alpha
            elif bake_data == 'Value':
                val = 0
                for chan in range(bake_copy.channels - 1):
                    if bake_px[bake_index + chan] > val:
                        val = bake_px[bake_index + chan]
                        
                output_px[out_index + output_channel] = val
            
            # Anything else is a simple channel to other channel mapping, unless its to the color input
            else:
                # If a single value is mapped to color, try putting it in the same channel it came from
                if socket == 'Color':
                    if output_image.channels >= bake_copy.channels:
                        output_px[out_index + bake_channel] = bake_px[bake_index + bake_channel]
                    # Fall back to puttint it in the first channel
                    else:
                        output_px[out_index] = bake_px[bake_index + bake_channel]
                        
                else:
                    output_px[out_index + output_channel] = bake_px[bake_index + bake_channel]
                
        _print("Done in %s" % (str(datetime.now() - map_time)), tag=True)
        
        if debug: _print(">     Will try to write %i values to space for %i" % (len(output_px), len(output_image.pixels)), tag=True)   
        
        # Copy the pixels to the image and save it
        _print(">   - Writing pixels and saving image: ", tag=True, wrap=False)
        output_image.pixels[0:] = output_px
        
        # Configure output image settings
        #img_scene = bpy.context.window.scene
        img_settings = img_scene.render.image_settings
        img_settings.file_format = output_node.img_type
        
        # Color mode, split between formats that support alpha and those that don't
        if output_node.img_type == 'BMP' or output_node.img_type == 'JPEG' or output_node.img_type == 'CINEON' or output_node.img_type == 'HDR':
            # Non alpha formats
            img_settings.color_mode = output_node.img_color_mode_noalpha
        else:
            # Alpha supported formats
            img_settings.color_mode = output_node.img_color_mode
            
        # Color Depths, depends on format:
        if output_node.img_type == 'PNG' or output_node.img_type == 'TIFF':
            img_settings.color_depth = output_node.img_color_depth_8_16
        elif output_node.img_type == 'JPEG2000':
            img_settings.color_depth = output_node.img_color_depth_8_12_16
        elif output_node.img_type == 'DPX':
            img_settings.color_depth = output_node.img_color_depth_8_10_12_16
        elif output_node.img_type == 'OPEN_EXR_MULTILAYER' or output_node.img_type == 'OPEN_EXR':
            img_settings.color_depth = output_node.img_color_depth_16_32
        
        # Compression / Quality for formats that support it
        if output_node.img_type == 'PNG':
            img_settings.compression = output_node.img_compression
        elif output_node.img_type == 'JPEG' or output_node.img_type == 'JPEG2000':
            img_settings.quality = output_node.img_quality
            
        # Codecs for formats that use them
        if output_node.img_type == 'JPEG2000':
            img_settings.jpeg2k_codec = output_node.img_codec_jpeg2k
        elif output_node.img_type == 'OPEN_EXR' or output_node.img_type == 'OPEN_EXR_MULTILAYER':
            img_settings.exr_codec = output_node.img_codec_openexr
        elif output_node.img_type == 'TIFF':
            img_settings.tiff_codec = output_node.img_codec_tiff
            
        # Additional settings used by some formats
        if output_node.img_type == 'JPEG2000':
            img_settings.use_jpeg2k_cinema_preset = output_node.img_jpeg2k_cinema
            img_settings.use_jpeg2k_cinema_48 = output_node.img_jpeg2k_cinema48
            img_settings.use_jpeg2k_ycc = output_node.img_jpeg2k_ycc
        elif output_node.img_type == 'DPX':
            img_settings.use_cineon_log = output_node.img_dpx_log
        elif output_node.img_type == 'OPEN_EXR':
            img_settings.use_zbuffer = output_node.img_openexr_zbuff
        
        # Save image using the render format settings
        output_image.save_render(output_image.filepath_raw, scene=img_scene)
        _print("Done", tag=True)
    
    _print(">", tag=True)   
    _print(">  Output Images processed in %s" % (str(datetime.now() - pass_start)), tag=True)
    
    return err



# Takes a bake and converts it to the target color space by projecting it to an emission plane and baking to
# a new image with the specified color space set. Returns [err, the new image, template scene].
def convert_to_color_space(bake, color_space, device):
    err = False 
    # Create new file to be color spaced version of the bake
    img_conv = bpy.data.images.new(bake.name + "_" + color_space, width=bake.size[0], height=bake.size[1])
    img_conv.alpha_mode = 'NONE'
    img_conv.colorspace_settings.name = color_space
    if color_space == 'Non-Color':
        img_conv.colorspace_settings.is_data = True
    img_conv.use_generated_float = True
    
    # Load up the template scene
    bake_scene_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "resources", "BakeWrangler_Scene.blend")
    bake_scene = None
    with bpy.data.libraries.load(bake_scene_path, link=False, relative=False) as (file_from, file_to):
        file_to.scenes.append("BakeWrangler")
    bake_scene = file_to.scenes[0]
    # Set the cycles values that aren't saved in the template and give it a name that can be traced
    bake_scene.cycles.device = device
    bake_scene.cycles.samples = 12
    bake_scene.cycles.aa_samples = 12
    bake_scene.name = "convert_" + bake.name + "_" + color_space
    
    # Switch into bake scene
    bpy.context.window.scene = bake_scene
    
    # Now create a new plane, stick an emission material on it with the bake and do a new bake
    bpy.ops.object.select_all(action='DESELECT')
    bpy.ops.mesh.primitive_plane_add()
    plane = bpy.context.active_object
    plane.name = "plane_" + bake.name + "_" + color_space
    
    # Set up the material then add it to the plane
    mat = bpy.data.materials.new(name="mat_convert_" + bake.name + "_" + color_space)
    mat.use_nodes = True
    mat.node_tree.nodes.clear()
    img_src = mat.node_tree.nodes.new('ShaderNodeTexImage')
    img_src.image = bake
    img_src.select = False
    emit = mat.node_tree.nodes.new('ShaderNodeEmission')
    mat.node_tree.links.new(img_src.outputs['Color'], emit.inputs['Color'])
    outp = mat.node_tree.nodes.new('ShaderNodeOutputMaterial')
    outp.target = 'CYCLES'
    mat.node_tree.links.new(emit.outputs['Emission'], outp.inputs['Surface'])
    img_dst = mat.node_tree.nodes.new('ShaderNodeTexImage')
    img_dst.image = img_conv
    img_dst.select = True
    mat.node_tree.nodes.active = img_dst
    
    plane.data.materials.append(mat)
    
    # Try the bake
    try:
        bpy.ops.object.bake(
            type='EMIT',
            margin=0,
            save_mode='INTERNAL',
            use_clear=True,
            )
    except RuntimeError as error:
        _print("%s" % (error), tag=True)
        err = True
        
    # Switch back to main scene before next pass. Nothing will be deleted so that the file can be examined for debugging.
    bpy.context.window.scene = base_scene
    
    return [err, img_conv, bake_scene]
    


# Takes a node of type OUTPUT_MATERIAL, BSDF_PRINCIPLED or MIX_SHADER. Starting with an output node it will
# recursively generate an emission shader to replace the output with the desired bake type. The link_socket
# is used for creating node tree links.
def prep_material_rec(node, link_socket, bake_type):
    tree = node.id_data
    nodes = tree.nodes
    links = tree.links
    # Three cases:
    if node.type == 'OUTPUT_MATERIAL':
        # Start of shader. Create new emission shader and connect it to the output
        next_node = link_socket.links[0].from_node
        node_emit = nodes.new('ShaderNodeEmission')
        links.new(node_emit.outputs['Emission'], link_socket)
        # Recurse
        return prep_material_rec(next_node, node_emit.inputs['Color'], bake_type)
        
    if node.type == 'MIX_SHADER':
        # Mix shader needs to generate a mix RGB maintaining the same Fac input if linked
        mix_node = nodes.new('ShaderNodeMixRGB')
        if node.inputs['Fac'].is_linked:
            # Connect Fac input
            links.new(node.inputs['Fac'].links[0].from_socket, mix_node.inputs['Fac'])
        else:
            # Set Fac value to match instead
            mix_node.inputs['Fac'].default_value = node.inputs['Fac'].default_value
        # Connect mix output to previous socket
        links.new(mix_node.outputs['Color'], link_socket)
        # Recurse
        branchA = prep_material_rec(node.inputs[1].links[0].from_node, mix_node.inputs['Color1'], bake_type)
        branchB = prep_material_rec(node.inputs[2].links[0].from_node, mix_node.inputs['Color2'], bake_type)
        return branchA and branchB
        
    if node.type == 'BSDF_PRINCIPLED':
        # End of a branch as far as the prep is concerned. Either link the desired bake value or set the
        # previous socket to the value if it isn't linked
        if bake_type == 'ALBEDO':
            bake_input = node.inputs['Base Color']
        elif bake_type == 'METALLIC':
            bake_input = node.inputs['Metallic']
        elif bake_type == 'ALPHA':
            bake_input = node.inputs['Alpha']
        elif bake_type == 'SPECULAR':
            bake_input = node.inputs['Specular']
        else:
            bake_input = None
            
        if debug: _print(">      Reached branch end, ", tag=True, wrap=False)
            
        if bake_input:
            if bake_input.is_linked:
                if debug: _print("Link found, [%s] will be connected" % (bake_input.links[0].from_socket), tag=True)
                # Connect the linked node up to the emit shader
                links.new(bake_input.links[0].from_socket, link_socket)
            else:
                if debug: _print("Not linked, value will be copied", tag=True)
                # Copy the value into the socket instead
                if bake_input.type == 'RGBA':
                    link_socket.default_value = bake_input.default_value
                else:
                    link_socket.default_value[0] = bake_input.default_value
                    link_socket.default_value[1] = bake_input.default_value
                    link_socket.default_value[2] = bake_input.default_value
                    link_socket.default_value[3] = 1.0
            # Branch completed
            return True
            
    # Something went wrong
    if debug: _print(">      Error: Reached unsupported node type", tag=True)
    return False



# Takes a materials node tree and makes any changes necessary to perform the given bake type. A material must
# end with principled shader(s) and mix shader(s) connected to a material output in order to be set up for any
# emission node bakes.
def prep_material_for_bake(node, node_tree, bake_type):
    # Bake types with built-in passes don't require any preparation
    if not node_tree or bake_type in node.bake_built_in or bake_type == 'CURVATURE' or bake_type == 'CURVE_SMOOTH' or bake_type == 'CAVITY':
        return
    
    # Mask is a special case where an emit shader and output can just be added to any material
    elif bake_type == 'MASK':
        nodes = node_tree.nodes
        
        # Add white emit and a new active output
        emit = nodes.new('ShaderNodeEmission')
        emit.inputs['Color'].default_value = [1.0, 1.0, 1.0, 1.0]
        outp = nodes.new('ShaderNodeOutputMaterial')
        node_tree.links.new(emit.outputs['Emission'], outp.inputs['Surface'])
        outp.target = 'CYCLES'
        
        # Make all outputs not active
        for node in nodes:
            if node.type == 'OUTPUT_MATERIAL':
                node.is_active_output = False
                
        outp.is_active_output = True
        return
        
    # The material has to have a node tree and it needs at least 2 nodes to be valid
    elif len(node_tree.nodes) < 2:
        return
    
    # All other bake types use an emission shader with the value plugged into it
    
    # A material can have multiple output nodes. Blender seems to preference the output to use like so:
    # 1 - Target set to current Renderer and Active (picks first if multiple are set active)
    # 2 - First output with Target set to Renderer if no others with that target are set Active
    # 3 - Active output (picks first if mutliple are active)
    #
    # Strategy will be to find all valid outputs and evaluate if they can be used in the same order as above.
    # The first usable output found will be selected and also changed to be the first choice for blender.
    # Four buckets: Cycles + Active, Cycles, Generic + Active, Generic
    nodes = node_tree.nodes
    node_cycles_out_active = []
    node_cycles_out = []
    node_generic_out_active = []
    node_generic_out = []
    node_selected_output = None
    
    # Collect all outputs
    for node in nodes:
        if node.type == 'OUTPUT_MATERIAL':
            if node.target == 'CYCLES':
                if node.is_active_output:
                    node_cycles_out_active.append(node)
                else:
                    node_cycles_out.append(node)
            elif node.target == 'ALL':
                if node.is_active_output:
                    node_generic_out_active.append(node)
                else:
                    node_generic_out.append(node)
                
    # Select the first usable output using the order explained above and make sure no other outputs are set active
    node_outputs = node_cycles_out_active + node_cycles_out + node_generic_out_active + node_generic_out
    for node in node_outputs:
        input = node.inputs['Surface']
        if not node_selected_output and material_recursor(node):
            node_selected_output = node
            node.is_active_output = True
        else:
            node.is_active_output = False
    
    if not node_selected_output:
        return
    
    # Output has been selected. An emission shader will now be built, replacing mix shaders with mix RGB
    # nodes and principled shaders with just the desired data for the bake type. Recursion used.
    if debug: _print(">     Chosen output [%s] decending tree:" % (node_selected_output.name), tag=True)
    return prep_material_rec(node_selected_output, node_selected_output.inputs['Surface'], bake_type)



# It's a me, main
def main():
    import sys       # to get command line args
    import argparse  # to parse options for us and print a nice help message

    # get the args passed to blender after "--", all of which are ignored by
    # blender so scripts may receive their own arguments
    argv = sys.argv

    if "--" not in argv:
        argv = []  # as if no args are passed
    else:
        argv = argv[argv.index("--") + 1:]  # get all args after "--"

    # When --help or no args are given, print this help
    usage_text = (
        "This script is used internally by Bake Wrangler add-on."
    )

    parser = argparse.ArgumentParser(description=usage_text)

    # Possible types are: string, int, long, choice, float and complex.
    parser.add_argument(
        "-t", "--tree", dest="tree", type=str, required=True,
        help="Name of bakery tree where the starting node is",
    )
    parser.add_argument(
        "-n", "--node", dest="node", type=str, required=True,
        help="Name of bakery node to start process from",
    )
    parser.add_argument(
        "-d", "--debug", dest="debug", type=int, required=False,
        help="Enable debug messages",
    )

    args = parser.parse_args(argv)

    if not argv:
        parser.print_help()
        return

    if not args.tree or not args.node:
        print("Error: Bake Wrangler baker required arguments not found")
        return
    
    global debug
    if args.debug:
        debug = bool(args.debug)
    else:
        debug = False
    
    # Make sure the node classes are registered
    try:
        node_tree.register()
    except:
        print("Info: Bake Wrangler nodes already registered")
    else:
        print("Info: Bake Wrangler nodes registered")
    
    # Load shaders and scenes
    bake_scene_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "resources", "BakeWrangler_Scene.blend")
    with bpy.data.libraries.load(bake_scene_path, link=False, relative=False) as (file_from, file_to):
        file_to.materials.append("BW_Cavity_Map")
        file_to.scenes.append("BakeWranglerComp")
    global cavity_shader
    cavity_shader = file_to.materials[0]
    global compositor_scene
    compositor_scene = file_to.scenes[0]
    
    # Start processing bakery node tree
    err = process_tree(args.tree, args.node)
    
    # Send end tag
    if err:
        _print("<ERRORS>", tag=True)
    else:
        _print("<FINISH>", tag=True)
        
    # Save changes to the file for debugging and exit
    bpy.ops.wm.save_mainfile(filepath=bpy.data.filepath, exit=True)
    
    return 0


if __name__ == "__main__":
    main()
