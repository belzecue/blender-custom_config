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
    global mesh_scene
    global active_scene
    base_scene = output_scene
    mesh_scene = bpy.data.scenes.new("BakeWrangler_Mesh")
    active_scene = bpy.context.window.scene
    bpy.context.window.scene = base_scene
    for obj in bpy.data.objects:
        base_scene.collection.objects.link(obj)
    # Add a property on objects that can link to a copy made
    bpy.types.Object.bw_copy = bpy.props.PointerProperty(name="Object Copy", description="Copy with modifiers applied", type=bpy.types.Object)
    
    # Get tree position
    tree = bpy.data.node_groups[tree_name]
    node = tree.nodes[node_name]
    err = False
    
    if debug: _print("> Debugging output enabled", tag=True)
    
    # Bake passes will be grouped by output as {'output.name': [[out_chan, in_chan, pass1], [out_chan, in_chan, passX]]}
    bake_tree = {}
    passes = 0
    
    # Pack tree based on starting node point
    if node.bl_idname == 'BakeWrangler_Bake_Pass':
        # Add all valid outputs
        for output in node.outputs:
            if output.is_linked:
                for link in output.links:
                    if link.to_socket.valid:
                        if link.to_node.name not in bake_tree.keys():
                            bake_tree[link.to_node.name] = []
                        bake_tree[link.to_node.name].append([link.to_socket.name, output.name, node])
                        passes += 1
    else:
        if node.bl_idname == 'BakeWrangler_Output_Image_Path':
            # Just add this output
            bake_tree[node.name] = []
        elif node.bl_idname == 'BakeWrangler_Output_Batch_Bake':
            # Add all connected valid inputs
            for input in node.inputs:
                if input.is_linked and input.valid and input.links[0].from_node.name not in bake_tree.keys():
                    bake_tree[input.links[0].from_node.name] = []
        else:
            _print("> Invalid bake tree starting node", tag=True)
            return True
        # Add passes to their group(s)
        for output in bake_tree.keys():
            node = tree.nodes[output]
            # All valid inputs should be in this outputs group
            for input in node.inputs:
                if input.is_linked and input.valid:
                    bake_tree[output].append([input.name, input.links[0].from_socket.name, input.links[0].from_node])
                    passes += 1
                
    # Perform passes needed for each output group
    _print("> Processing [%s]: Creating %i images" % (node.get_name(), len(bake_tree.keys())), tag=True)
    _print(">", tag=True)
    error = 0
    for output in bake_tree.keys():
        node = tree.nodes[output]
        output_format = node.get_format()
        _print("> Output: [%s]" % (node.name_with_ext()), tag=True)
        for bake in bake_tree[output]:
            _print(">  Pass: [%s] " % (bake[2].get_name()), tag=True, wrap=False)
            err, img_bake, img_mask = process_bake_pass_input(bake[2], output_format)
            err += process_bake_pass_output(node, img_bake, img_mask, output_format, bake[1], bake[0])
            if err:
                error += err
    return error
            
            
    
# Takes a bake pass node and returns the baked image and baked mask
def process_bake_pass_input(node, format):
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
    bake_settings = {}
    bake_settings["x_res"] = node.bake_xres
    bake_settings["y_res"] = node.bake_yres
    bake_settings["node_name"] = node.get_name()
    # Settings for normal pass
    bake_settings["norm_s"] = node.norm_space
    bake_settings["norm_r"] = node.norm_R
    bake_settings["norm_g"] = node.norm_G
    bake_settings["norm_b"] = node.norm_B
    # Settings for curvature pass
    bake_settings["curve_px"] = node.curve_px
    # Settings for cavity pass
    bake_settings["cavity_samp"] = node.cavity_samp
    bake_settings["cavity_dist"] = node.cavity_dist
    bake_settings["cavity_gamma"] = node.cavity_gamma
    # Settings for passes with selectable influence
    bake_settings["infl_direct"] = node.use_direct
    bake_settings["infl_indirect"] = node.use_indirect
    bake_settings["infl_color"] = node.use_color
    # Settings for what to combine in combined pass
    bake_settings["comb_diffuse"] = node.use_diffuse
    bake_settings["comb_glossy"] = node.use_glossy
    bake_settings["comb_trans"] = node.use_transmission
    bake_settings["comb_subsurf"] = node.use_subsurface
    bake_settings["comb_ao"] = node.use_ao
    bake_settings["comb_emit"] = node.use_emit
    # Settings related to World and render
    use_world = node.use_world
    the_world = node.the_world
    cpy_render = node.cpy_render
    cpy_from = node.cpy_from
    use_float = node.use_float
    
    # Set up the pass influences if the bake uses them
    bake_settings["pass_influences"] = set()
    if bake_type in node.bake_has_influence:
        if infl_direct:
            bake_settings["pass_influences"].add('DIRECT')
        if infl_indirect:
            bake_settings["pass_influences"].add('INDIRECT')
        if infl_color:
            bake_settings["pass_influences"].add('COLOR')
        if bake_type == 'COMBINED':
            if comb_diffuse:
                bake_settings["pass_influences"].add('DIFFUSE')
            if comb_glossy:
                bake_settings["pass_influences"].add('GLOSSY')
            if comb_trans:
                bake_settings["pass_influences"].add('TRANSMISSION')
            if comb_subsurf:
                bake_settings["pass_influences"].add('SUBSURFACE')
            if comb_ao:
                bake_settings["pass_influences"].add('AO')
            if comb_emit:
                bake_settings["pass_influences"].add('EMIT')
                
    # Get bake mesh inputs
    inputs = node.inputs
    for input in inputs:
        if input.is_linked and input.valid:
            if not bake_mesh.count(input.links[0].from_node):
                bake_mesh.append(input.links[0].from_node)
    
    _print(" [Mesh Nodes (%i)]" % (len(bake_mesh)), tag=True)
    
    # Generate the bake and mask images
    img_bake = bpy.data.images.new(node.get_name(), width=bake_settings["x_res"], height=bake_settings["y_res"])
    img_bake.alpha_mode = 'NONE'
    if use_float:
        img_bake.use_generated_float = True
    img_bake.colorspace_settings.name = format['img_color_space']
    if format['img_color_space'] == "Non-Color":
        img_bake.colorspace_settings.is_data = True
    if bake_type in ['NORMAL', 'CURVATURE', 'CURVE_SMOOTH']:
        img_bake.generated_color = (0.5, 0.5, 1.0, 1.0)
                
    img_mask = bpy.data.images.new("mask_" + node.get_name(), width=bake_settings["x_res"], height=bake_settings["y_res"])
    img_mask.alpha_mode = 'NONE'
    img_mask.colorspace_settings.name = 'Non-Color'
    img_mask.colorspace_settings.is_data = True
    
    # Begin processing bake meshes
    for mesh in bake_mesh:
        active_meshes = mesh.get_objects('TARGET')
        selected_objs = mesh.get_objects('SOURCE')
        scene_objs = mesh.get_objects('SCENE')
        
        _print(">   Mesh: [%s] [Targets (%i)]" % (mesh.get_name(), len(active_meshes)), tag=True)
        # Gather settings for this mesh. Validation should have been done before this script was ever run
        # so all settings will be assumed valid.
        bake_settings["margin"] = mesh.margin
        bake_settings["padding"] = mesh.mask_margin
        multi = mesh.multi_res
        multi_pass = mesh.multi_res_pass
        bake_settings["ray_dist"] = mesh.ray_dist
        bake_settings["mesh_name"] = mesh.get_name()
        
        # Process each active mesh
        for active in active_meshes:
            # Load in template bake scene with mostly optimized settings for baking
            bake_scene_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "resources", "BakeWrangler_Scene.blend")
            with bpy.data.libraries.load(bake_scene_path, link=False, relative=False) as (file_from, file_to):
                file_to.scenes.append("BakeWrangler")
            bake_scene = file_to.scenes[0]
            bake_scene.name = "bake_" + node.get_name() + "_" + mesh.get_name() + "_" + active[0].name
            
            # Set image format output
            apply_output_format(bake_scene, format)
            
            # Copy render settings if required
            if cpy_render:
                if cpy_from in [None, ""]:
                    cpy_from = active_scene
                copy_render_settings(cpy_from, bake_scene)
            
            # Set the device and sample count to override anything that could have been copied
            bake_scene.cycles.device = bake_dev
            bake_scene.cycles.samples = bake_samp
            bake_scene.cycles.aa_samples = bake_samp
            
            # Set custom world instead of default if enabled
            if use_world:
                if the_world not in [None, ""]:
                    bake_scene.world = the_world
                else:
                    bake_scene.world = active_scene.world
                        
            # Determine what strategy to use for this bake
            bake_settings["cage"] = False
            bake_settings["cage_object"] = None
            bake_settings["cage_obj_name"] = ""
            to_active = False
            if not multi:
                for obj in selected_objs:
                    # Let a duplicate of the target object count if they use different UV Maps
                    if obj[0] != active[0] or (len(obj) > 1 and len(active) > 1 and obj[1] != active[1]):
                        to_active = True
                        break
                # Copy all selected objects over if 'to active' pass
                if to_active:
                    selected = bpy.data.collections.new("Selected_" + active[0].name)
                    for obj in selected_objs:
                        # Let a duplicate of the target object in if they use different UV Maps
                        if obj[0] != active[0] or (len(obj) > 1 and len(active) > 1 and obj[1] != active[1]):
                            prep_object_for_bake(obj[0])
                            copy = obj[0].bw_copy.copy()
                            copy.data = obj[0].bw_copy.data.copy()
                            selected.objects.link(copy)
                            # Set UV map to use if one was selected
                            if len(obj) > 1 and obj[1] not in [None, ""]:
                                copy.data.uv_layers.active = copy.data.uv_layers[obj[1]]
                    bake_scene.collection.children.link(selected)
                    # Add the cage copy to the scene because it doesn't work properly in a different scene currently
                    if len(active) > 2 and active[2]:
                        bake_settings["cage"] = True
                        prep_object_for_bake(active[2])
                        bake_settings["cage_object"] = active[2].bw_copy.copy()
                        bake_settings["cage_object"].data = active[2].bw_copy.data.copy()
                        bake_settings["cage_obj_name"] = bake_settings["cage_object"].name
            else:
                # Collection of base objects for multi-res to link into
                base_col = bpy.data.collections.new("Base_" + active[0].name)
                bake_scene.collection.children.link(base_col)
                
            # Regardless of strategy the following data will be used. Copies are made so other passes can get the originals
            active_obj = active[0]
            if not multi:
                prep_object_for_bake(active[0])
                active_obj = active[0].bw_copy
            target = active_obj.copy()
            target.data = active_obj.data.copy()

            # Set UV map to use if one was selected
            if len(active) > 1 and active[1] not in [None, ""]:
                target.data.uv_layers.active = target.data.uv_layers[active[1]]
            
            # Materials should be removed from the target copy for To active
            if to_active:
                target.data.materials.clear()
                target.data.polygons.foreach_set('material_index', [0] * len(target.data.polygons))
                target.data.update()
            # Add target before doing mats
            else:
                bake_scene.collection.objects.link(target)
                
            # Create unique copies for every material in the scene before anything else is done
            unique_mats = make_materials_unique_to_scene(bake_scene, node.get_name() + "_" + mesh.get_name() + "_" + active[0].name, bake_type, bake_settings)
            
            # Add target after doing mats
            if to_active:
                bake_scene.collection.objects.link(target)
                
            # Copy all scene objects over if not a multi-res pass
            if not multi:
                scene = bpy.data.collections.new("Scene_" + active[0].name)
                for obj in scene_objs:
                    copy = obj[0].copy()
                    copy.data = obj[0].data.copy()
                    scene.objects.link(copy)
                bake_scene.collection.children.link(scene)
                # Add cage object
                if bake_settings["cage"]:
                    bake_scene.collection.objects.link(bake_settings["cage_object"])
              
            # Switch into bake scene
            bpy.context.window.scene = bake_scene
                
            # Select the target and make it active
            bpy.ops.object.select_all(action='DESELECT')
            target.select_set(True)
            bpy.context.view_layer.objects.active = target
            
            # Perform bake type needed
            if multi:
                err = bake_multi_res(img_bake, multi_pass, unique_mats, bake_settings, base_col)
            elif to_active:
                err = bake_to_active(img_bake, bake_type, unique_mats, bake_settings, selected)
            else:
                err = bake_solo(img_bake, bake_type, unique_mats, bake_settings)
                
            # Bake the mask if samples are non zero
            if mask_samp > 0:
                # Set samples to the mask value
                bake_scene.cycles.device = bake_dev
                bake_scene.cycles.samples = mask_samp
                bake_scene.cycles.aa_samples = mask_samp
                err += bake_mask(img_mask, unique_mats, bake_settings, to_active)
            # Otherwise make the mask all white
            else:
                img_mask.generated_color = (1.0, 1.0, 1.0, 1.0)
            
            # Switch back to main scene before next pass. Nothing will be deleted so that the file can be examined for debugging.
            bpy.context.window.scene = base_scene
    
    # Perform compositor pass if needed
    if bake_type in ['CURVATURE', 'CURVE_SMOOTH', 'SMOOTHNESS']:
        err += composit_pass(img_bake, bake_type, bake_settings, format)
        
    _print(">  Pass completed in %s" % (str(datetime.now() - pass_start)), tag=True)
    
    # Finished inputs, return the bakes
    return [err, img_bake, img_mask]



# Bake a multi-res pass
def bake_multi_res(img_bake, bake_type, materials, settings, base_col):
    # Add a bake target image node to each material
    for mat in materials.values():
        if debug: _print(">    Preparing material [%s] for [Multi-Res %s] bake" % (mat.name, bake_type), tag=True)
        image_node = mat.node_tree.nodes.new("ShaderNodeTexImage")
        image_node.image = img_bake
        image_node.select = True
        mat.node_tree.nodes.active = image_node
        
    # Next link all the objects from the base scene to hopefully stop any modifier errors
    for obj in base_scene.objects:
        base_col.objects.link(obj)
    
    # Bake it
    return bake(bake_type, settings, False, True)



# Bake a to-active pass
def bake_to_active(img_bake, bake_type, materials, settings, selected):
    # Make the source objects selected
    for obj in selected.objects:
        obj.select_set(True)
        
    # Add texture node set up to target object
    mat = bpy.data.materials.new(name="mat_" + settings["node_name"] + "_" + settings["mesh_name"])
    mat.use_nodes = True
    image_node = mat.node_tree.nodes.new("ShaderNodeTexImage")
    image_node.image = img_bake
    image_node.select = True
    mat.node_tree.nodes.active = image_node
    bpy.context.view_layer.objects.active.data.materials.append(mat)
    
    # Prepare the materials for the bake type
    for mat in materials.values():
        if debug: _print(">    Preparing material [%s] for [%s] bake" % (mat.name, bake_type), tag=True)
        prep_material_for_bake(mat.node_tree, bake_type)
        
    # Bake it
    return bake(bake_type, settings, True, False)



# Bake single object pass
def bake_solo(img_bake, bake_type, materials, settings):
    # Prepare the materials for the bake type
    for mat in materials.values():
        if debug: _print(">    Preparing material [%s] for [%s] bake" % (mat.name, bake_type), tag=True)
        prep_material_for_bake(mat.node_tree, bake_type)
        # For non To active bakes, add an image node to the material and make it selected + active for bake image
        image_node = mat.node_tree.nodes.new("ShaderNodeTexImage")
        image_node.image = img_bake
        image_node.select = True
        mat.node_tree.nodes.active = image_node
        
    # Bake it
    return bake(bake_type, settings, False, False)
        
        

# Bake a masking pass
def bake_mask(img_mask, materials, settings, to_active):
    # Requires adding a pure while emit shader to all the materials first and changing target image
    for mat in materials.values():
        prep_material_for_bake(mat.node_tree, 'MASK')
        
        # Add image node to material and make it selected + active
        if not to_active:
            image_node = mat.node_tree.nodes.new("ShaderNodeTexImage")
            image_node.image = img_mask
            image_node.select = True
            mat.node_tree.nodes.active = image_node
    
    # Add image node to target and make it selected + active (should only be one material at this point)
    if to_active:
        image_node = bpy.context.view_layer.objects.active.material_slots[0].material.node_tree.nodes.new("ShaderNodeTexImage")
        image_node.image = img_mask
        image_node.select = True
        bpy.context.view_layer.objects.active.material_slots[0].material.node_tree.nodes.active = image_node
    
    # Bake it
    settings["margin"] += settings["padding"]
    return bake('MASK', settings, to_active, False)
    
    
    
# Call actual bake commands
def bake(bake_type, settings, to_active, multi):
    # Set 'real' bake pass. PBR use EMIT rather than the named pass, since those passes don't exist.
    if bake_type in ['ALBEDO', 'METALLIC', 'ALPHA', 'CAVITY', 'SPECULAR', 'MASK']:
        real_bake_type = 'EMIT'
    elif bake_type == 'SMOOTHNESS':
        real_bake_type = 'ROUGHNESS'
    elif bake_type in ['CURVATURE', 'CURVE_SMOOTH']:
        real_bake_type = 'NORMAL'
        settings["norm_s"] = 'TANGENT'
        settings["norm_r"] = 'POS_X'
        settings["norm_g"] = 'POS_Y'
        settings["norm_b"] = 'POS_Z'
    else:
        real_bake_type = bake_type
        
    if debug: _print(">     Real bake type set to [%s]" % (real_bake_type), tag=True)
        
    # Update view layer to be safe
    bpy.context.view_layer.update()
    start = datetime.now()
    _print(">    -Baking %s pass: " % (bake_type), tag=True, wrap=False)
    
    # Do the bake. Most of the properties can be passed as arguments to the operator.
    err = False
    try:
        if not multi:
            bpy.ops.object.bake(
                type=real_bake_type,
                pass_filter=settings["pass_influences"],
                margin=settings["margin"],
                use_selected_to_active=to_active,
                cage_extrusion=settings["ray_dist"],
                cage_object=settings["cage_obj_name"],
                normal_space=settings["norm_s"],
                normal_r=settings["norm_r"],
                normal_g=settings["norm_g"],
                normal_b=settings["norm_b"],
                save_mode='INTERNAL',
                use_clear=False,
                use_cage=settings["cage"],
            )
        else:
            bpy.context.scene.render.use_bake_multires = True
            bpy.context.scene.render.bake_margin = settings["margin"]
            bpy.context.scene.render.bake_type = bake_type
            bpy.context.scene.render.use_bake_clear = False
            bpy.ops.object.bake_image()
    except RuntimeError as error:
        _print("%s" % (error), tag=True)
        err = True
    else:
        _print("Completed in %s" % (str(datetime.now() - start)), tag=True)
    return err



# Perform requested compositor pass on image
def composit_pass(img_bake, bake_type, settings, format):
    start = datetime.now()
    _print(">   Compositing pass: ", tag=True, wrap=False)
    if debug: _print(">   Switching to compositor scene", tag=True)
    
    # Switch into compositor scene and apply output format
    bpy.context.window.scene = compositor_scene
    #apply_output_format(compositor_scene, format)
    
    # Hook up the correct compositor tree to the output node and set the input to the bake data
    if debug: _print(">   Setting composit tree input and output", tag=True)
    comp_nodes = bpy.context.scene.node_tree.nodes
    comp_links = bpy.context.scene.node_tree.links
    comp_input = comp_nodes["bw_comp_input"]
    comp_output = comp_nodes["bw_comp_output"]
    
    if bake_type == 'CURVATURE':
        comp_proc = "bw_comp_curve"
        comp_nodes["curve_px"].outputs[0].default_value = settings["curve_px"]
    elif bake_type == 'CURVE_SMOOTH':
        comp_proc = "bw_comp_curve_smooth"
    elif bake_type == 'SMOOTHNESS':
        comp_proc = "bw_comp_invert"
    else:
        _print("Invalid pass", tag=True)
        bpy.context.scene = base_scene
        return True
    
    comp_input.image = img_bake
    comp_links.new(comp_nodes[comp_proc].outputs[0], comp_output.inputs[0])
    
    # Render output
    bpy.context.scene.render.resolution_x = settings["x_res"]
    bpy.context.scene.render.resolution_y = settings["y_res"]
    bpy.ops.render.render(write_still=True, use_viewport=False)
    comp_img = bpy.data.images.load(bpy.context.scene.render.filepath + bpy.context.scene.render.file_extension)
    
    if debug: _print(">   Copying composit image (%dpx) to bake data (%dpx)" % (len(comp_img.pixels), len(img_bake.pixels)), tag=True)
    
    # Replace bake data with composit
    if len(comp_img.pixels) == len(img_bake.pixels):
        img_bake.pixels = comp_img.pixels[:]
        img_bake.update()
        _print("Completed in %s" % (str(datetime.now() - start)), tag=True)
        bpy.context.window.scene = base_scene
        return False
    else:
        _print("Failed", tag=True)
        bpy.context.window.scene = base_scene
        return True



# Takes an output node along with a bake and optional mask which are composited and saved
def process_bake_pass_output(node, bake, mask, format, in_chan, out_chan):
    pass_start = datetime.now()
    err = False
    
    output_image = None
    output_size = [node.img_xres, node.img_yres]
    output_path = node.img_path
    output_name = node.name_with_ext()
    output_file = os.path.join(os.path.realpath(output_path), output_name)
    
    _print(">  Writing file to %s" % (output_file), tag=True)
    
    # See if the output exists or if a new file should be created
    if os.path.exists(output_file):
        # Open it
        _print(">   - Using existing file", tag=True)
        output_image = bpy.data.images.load(os.path.abspath(output_file))
    else:
        # Create it
        _print(">   - Creating file", tag=True)
        output_image = bpy.data.images.new(node.name, width=output_size[0], height=output_size[1])
        output_image.filepath_raw = os.path.abspath(output_file)
        output_image.use_generated_float = True
    
    # Set format
    #output_image.colorspace_settings.name = format['img_color_space']
    if format['img_color_space'] == 'Non-Color':
        output_image.colorspace_settings.is_data = True
    output_image.alpha_mode = 'STRAIGHT'
    output_image.file_format = node.img_type
    
    if debug: _print(">     Loaded image: %i x %i, %i channels, %i bpp, %i px (%i values)" % (output_image.size[0], output_image.size[1], output_image.channels, output_image.depth, len(output_image.pixels) / output_image.channels, len(output_image.pixels)), tag=True)
    if debug: _print(">     Baked  image: %i x %i, %i channels, %i bpp, %i px (%i values)" % (bake.size[0], bake.size[1], bake.channels, bake.depth, len(bake.pixels) / bake.channels, len(bake.pixels)), tag=True)
    
    # Switch into output scene and apply output format
    bpy.context.window.scene = output_scene
    apply_output_format(output_scene, format)
    
    # Hook up the correct compositor tree sockets for the desired output
    if debug: _print(">   Setting output composit tree input and output", tag=True)
    comp_nodes = bpy.context.scene.node_tree.nodes
    comp_links = bpy.context.scene.node_tree.links
    rgb_bake = comp_nodes["bw_rgb_bake"]
    rgb_bake_r = rgb_bake.outputs["R"]
    rgb_bake_g = rgb_bake.outputs["G"]
    rgb_bake_b = rgb_bake.outputs["B"]
    rgb_out = comp_nodes["bw_rgb_out"]
    rgb_out_r = rgb_out.inputs["R"]
    rgb_out_g = rgb_out.inputs["G"]
    rgb_out_b = rgb_out.inputs["B"]
    alpha_out = comp_nodes["bw_alpha_out"].inputs[2]
    value_bake = comp_nodes["bw_value_bake"].outputs[0]
    mask_in = comp_nodes["bw_img_mask"]
    bake_in = comp_nodes["bw_img_bake"]
    output_img = comp_nodes["bw_img_output"]
    rgba_img = comp_nodes["bw_rgba_img"]
    rgba_img_r = rgba_img.outputs["R"]
    rgba_img_g = rgba_img.outputs["G"]
    rgba_img_b = rgba_img.outputs["B"]
    rgba_img_a = rgba_img.outputs["A"]
    
    # Make sure nothing is connected to the output from previous iterations
    for input in rgb_out.inputs:
        links = []
        for link in input.links:
            links.append(link)
        for link in links:
            comp_links.remove(link)
    
    # Connect all img channels to output, the bake channels will override them below    
    comp_links.new(rgb_out_r, rgba_img_r)
    comp_links.new(rgb_out_g, rgba_img_g)
    comp_links.new(rgb_out_b, rgba_img_b)
    comp_links.new(alpha_out, rgba_img_a)
    
    # Connect for Color input
    if in_chan == "Color":
        # Connect all bake color channels, but keep img alpha
        if out_chan == "Color":
            comp_links.new(rgb_out_r, rgb_bake_r)
            comp_links.new(rgb_out_g, rgb_bake_g)
            comp_links.new(rgb_out_b, rgb_bake_b)
        if out_chan == "R":
            comp_links.new(rgb_out_r, rgb_bake_r)
        if out_chan == "G":
            comp_links.new(rgb_out_g, rgb_bake_g)
        if out_chan == "B":
            comp_links.new(rgb_out_b, rgb_bake_b)
        if out_chan == "Alpha":
            comp_links.new(alpha_out, value_bake)
    # Connect for any other inputs
    else:
        in_socket = ""
        if in_chan == "R":
            in_socket = rgb_bake_r
        elif in_chan == "G":
            in_socket = rgb_bake_g
        elif in_chan == "B":
            in_socket = rgb_bake_b
        elif in_chan == "Value":
            in_socket = value_bake
            
        out_socket = ""
        if out_chan == "Color":
            if in_chan == "R":
                out_socket = rgb_out_r
            elif in_chan == "G":
                out_socket = rgb_out_g
            elif in_chan == "B":
                out_socket = rgb_out_b
            elif in_chan == "Value":
                comp_links.new(rgb_out_r, value_bake)
                comp_links.new(rgb_out_g, value_bake)
                comp_links.new(rgb_out_b, value_bake)
        elif out_chan == "R":
            out_socket = rgb_out_r
        elif out_chan == "G":
            out_socket = rgb_out_g
        elif out_chan == "B":
            out_socket = rgb_out_b
        elif out_chan == "Alpha":
            out_socket = alpha_out
        
        if out_socket != "":
            comp_links.new(out_socket, in_socket)
    
    # Set input images
    bake_in.image = bake
    mask_in.image = mask
    output_img.image = output_image

    # Render output
    bpy.context.scene.render.filepath = output_file
    bpy.context.scene.render.resolution_x = output_size[0]
    bpy.context.scene.render.resolution_y = output_size[1]
    bpy.ops.render.render(write_still=True, use_viewport=False)
    output_image.update()
    
    _print(">", tag=True)
    
    return err



# Apply image format settings to scenes output settings
def apply_output_format(target_scene, format):
    # Configure output image settings
    img_settings = target_scene.render.image_settings
    img_settings.file_format = img_type = format["img_type"]
    
    # Color mode, split between formats that support alpha and those that don't
    if img_type in ['BMP', 'JPEG', 'CINEON', 'HDR']:
        # Non alpha formats
        img_settings.color_mode = format["img_color_mode_noalpha"]
    else:
        # Alpha supported formats
        img_settings.color_mode = format["img_color_mode"]
        
    # Color Depths, depends on format:
    if img_type in ['PNG', 'TIFF']:
        img_settings.color_depth = format["img_color_depth_8_16"]
    elif img_type == 'JPEG2000':
        img_settings.color_depth = format["img_color_depth_8_12_16"]
    elif img_type == 'DPX':
        img_settings.color_depth = format["img_color_depth_8_10_12_16"]
    elif img_type in ['OPEN_EXR_MULTILAYER', 'OPEN_EXR']:
        img_settings.color_depth = format["img_color_depth_16_32"]
    
    # Compression / Quality for formats that support it
    if img_type == 'PNG':
        img_settings.compression = format["img_compression"]
    elif img_type in ['JPEG', 'JPEG2000']:
        img_settings.quality = format["img_quality"]
        
    # Codecs for formats that use them
    if img_type == 'JPEG2000':
        img_settings.jpeg2k_codec = format["img_codec_jpeg2k"]
    elif img_type in ['OPEN_EXR', 'OPEN_EXR_MULTILAYER']:
        img_settings.exr_codec = format["img_codec_openexr"]
    elif img_type == 'TIFF':
        img_settings.tiff_codec = format["img_codec_tiff"]
        
    # Additional settings used by some formats
    if img_type == 'JPEG2000':
        img_settings.use_jpeg2k_cinema_preset = format["img_jpeg2k_cinema"]
        img_settings.use_jpeg2k_cinema_48 = format["img_jpeg2k_cinema48"]
        img_settings.use_jpeg2k_ycc = format["img_jpeg2k_ycc"]
    elif img_type == 'DPX':
        img_settings.use_cineon_log = format["img_dpx_log"]
    elif img_type == 'OPEN_EXR':
        img_settings.use_zbuffer = format["img_openexr_zbuff"]



# Copy render settings from source scene to active scene
def copy_render_settings(source, target):
    # Copy all Cycles settings
    for setting in source.cycles.bl_rna.properties.keys():
        if setting not in ["rna_type", "name"]:
            setattr(target.cycles, setting, getattr(source.cycles, setting))
    for setting in source.cycles_curves.bl_rna.properties.keys():
        if setting not in ["rna_type", "name"]:
            setattr(target.cycles_curves, setting, getattr(source.cycles_curves, setting))
    # Copy SOME Render settings
    for setting in source.render.bl_rna.properties.keys():
        if setting in ["tile_x",
                       "tile_y",
                       "dither_intensity",
                       "filter_size",
                       "film_transparent",
                       "use_freestyle",
                       "threads",
                       "threads_mode",
                       "hair_type",
                       "hair_subdiv",
                       "use_simplify",
                       "simplify_subdivision",
                       "simplify_child_particles",
                       "simplify_subdivision_render",
                       "simplify_child_particles_render",
                       "use_simplify_smoke_highres",
                       "simplify_gpencil",
                       "simplify_gpencil_onplay",
                       "simplify_gpencil_view_fill",
                       "simplify_gpencil_remove_lines",
                       "simplify_gpencil_view_modifier",
                       "simplify_gpencil_shader_fx",
                       "simplify_gpencil_blend",
                       "simplify_gpencil_tint",
                      ]:
            setattr(target.render, setting, getattr(source.render, setting))



# Pretty much everything here is about preventing blender crashing or failing in some way that only happens
# when it runs a background bake. Perhaps it wont be needed some day, but for now trying to keep all such
# things in one place. Modifiers are applied or removed and non mesh types are converted.
def prep_object_for_bake(object):
    # Create a copy of the object to modify and put it into the mesh only scene
    if not object.bw_copy:
        copy = object.copy()
        copy.data = object.data.copy()
        copy.name = "BW_" + object.name
        base_scene.collection.objects.link(copy)
    else:
        # Object already preped
        return
        
    # Make obj the only selected + active
    bpy.ops.object.select_all(action='DESELECT')
    copy.select_set(True)
    bpy.context.view_layer.objects.active = copy
                    
    # Deal with mods
    if len(copy.modifiers):
        for mod in copy.modifiers:
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
            if copy.data.render_resolution > 0:
                copy.data.resolution = copy.data.render_resolution
        else:
            if copy.data.render_resolution_u > 0:
                copy.data.resolution_u = copy.data.render_resolution_u
            if object.data.render_resolution_v > 0:
                copy.data.resolution_v = copy.data.render_resolution_v
        # Convert
        bpy.ops.object.convert(target='MESH')
        
        # Meta objects seem to get deleted and a new object replaces them, breaking the reference
        if object.type == 'META':
            copy = bpy.context.view_layer.objects.active
    
    # Link copy to original, remove from base scene and add to mesh scene
    object.bw_copy = copy
    mesh_scene.collection.objects.link(copy)
    base_scene.collection.objects.unlink(copy)



# Takes a materials node tree and makes any changes necessary to perform the given bake type. A material must
# end with principled shader(s) and mix shader(s) connected to a material output in order to be set up for any
# emission node bakes.
def prep_material_for_bake(node_tree, bake_type):
    # Bake types with built-in passes don't require any preparation
    if not node_tree or bake_type in ['NORMAL', 'ROUGHNESS', 'SMOOTHNESS', 'AO', 'SUBSURFACE', 'TRANSMISSION', 'GLOSSY', 'DIFFUSE', 'ENVIRONMENT', 'EMIT', 'UV', 'SHADOW', 'COMBINED', 'CURVATURE', 'CURVE_SMOOTH', 'CAVITY']:
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
    if debug: _print(">     Chosen output [%s] descending tree:" % (node_selected_output.name), tag=True)
    return prep_material_rec(node_selected_output, node_selected_output.inputs['Surface'], bake_type)



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



# Consider all materials in scene and create scene only copies
def make_materials_unique_to_scene(scene, suffix, bake_type, settings):
    # Go through all the materials on every object
    materials = {}
    
    if bake_type == 'CAVITY':
        # Configure shader
        nodes = cavity_shader.node_tree.nodes
        node_ao = nodes["bw_ao_cavity"]
        node_gamma = nodes["bw_ao_cavity_gamma"]
        node_ao.samples = settings["cavity_samp"]
        node_ao.inputs["Distance"].default_value = settings["cavity_dist"]
        node_gamma.inputs["Gamma"].default_value = settings["cavity_gamma"]
        
    for obj in scene.objects:
        # Some bake types replace materials with a special one
        if bake_type in ['CAVITY']:
            # Clear all materials
            obj.data.materials.clear()
            obj.data.polygons.foreach_set('material_index', [0] * len(obj.data.polygons))
            obj.data.update()
            # Add cavity shader
            obj.data.materials.append(cavity_shader)
            materials["cavity"] = cavity_shader
        # Otherwise normal processing
        elif len(obj.material_slots):
            for slot in obj.material_slots:
                # If its a new material, create a copy (adding suffix) and add the pair to the list
                if slot.material.name not in materials:
                    copy = slot.material.copy()
                    copy.name = slot.material.name + suffix
                    materials[slot.material.name] = copy
                    replace = copy
                else:
                    replace = materials[slot.material.name]
                # Replace with copy
                slot.material = replace
    # Return the dict
    return materials



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
        
    # Make sure to be in object mode before doing anything
    bpy.ops.object.mode_set(mode='OBJECT')
    
    # Load shaders and scenes
    bake_scene_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "resources", "BakeWrangler_Scene.blend")
    with bpy.data.libraries.load(bake_scene_path, link=False, relative=False) as (file_from, file_to):
        file_to.materials.append("BW_Cavity_Map")
        file_to.scenes.append("BakeWranglerComp")
        file_to.scenes.append("BakeWranglerOutput")
    global cavity_shader
    cavity_shader = file_to.materials[0]
    global compositor_scene
    compositor_scene = file_to.scenes[0]
    global output_scene
    output_scene = file_to.scenes[1]
    
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
