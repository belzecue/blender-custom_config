import os.path
import bpy
from datetime import datetime
try:
    from BakeWrangler.nodes import node_tree
    from BakeWrangler.nodes.node_tree import _print
except:
    import sys
    sys.path.append(os.path.dirname(os.path.abspath(__file__)))
    from nodes import node_tree
    from nodes.node_tree import _print



# Process the node tree with the given node as the starting point
def process_tree(tree_name, node_name):
    tree = bpy.data.node_groups[tree_name]
    node = tree.nodes[node_name]
    err = False
    
    _print("> Processing [%s]" % (node.get_name()), tag=True)
    
    # Decide how to process tree based on starting node type
    if node.bl_idname == 'BakeWrangler_Bake_Pass':
        # A Bake Pass node should bake all attached meshes to a single image then generate all attached outputs
        err, img_bake, img_mask = process_bake_pass_input(node)
        err = process_bake_pass_output(node, img_bake, img_mask)
    
    return err



# Takes a bake pass node and returns the baked image and baked mask
def process_bake_pass_input(node):
    pass_start = datetime.now()
    err = False
    
    # Gather pass settings
    meshes = []
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
                
    # Gather unique input meshes
    inputs = node.inputs
    for input in inputs:
        if input.is_linked:
            link = input.links[0]
            if link.is_valid and not meshes.count(link.from_node):
                meshes.append(link.from_node)
    
    _print(">  Input Meshes: %i" % (len(meshes)), tag=True)
    
    # Generate the bake and mask images
    img_bake = bpy.data.images.new(node.get_name(), width=x_res, height=y_res)
    img_bake.alpha_mode = 'NONE'
    img_bake.colorspace_settings.name = 'Raw'
    if bake_type == 'NORMAL':
        img_bake.colorspace_settings.is_data = True
        img_bake.generated_color = (0.5, 0.5, 1.0, 1.0)
                
    img_mask = bpy.data.images.new("mask_" + node.get_name(), width=x_res, height=y_res)
    img_mask.alpha_mode = 'NONE'
    img_mask.colorspace_settings.name = 'Raw'
    img_mask.colorspace_settings.is_data = True
    
    # Begin processing input meshes
    for mesh in meshes:
        _print(">   %i/%i: [%s]" % ((meshes.index(mesh) + 1), len(meshes), mesh.get_name()), tag=True)
        # Gather settings for this mesh. Validation should have been done before this script was ever run
        # so all settings will be assumed valid.
        objects = mesh.get_objects()
        target = objects.pop(0)
        margin = mesh.margin
        padding = mesh.mask_margin
        multi = mesh.multi_res
        multi_pass = mesh.multi_res_pass
        cage = mesh.cage
        cage_obj = mesh.cage_obj
        cage_cpy = None
        cage_obj_name = ""
        ray_dist = mesh.ray_dist
        to_active = len(objects) > 0
        if cage:
            cage_cpy = cage_obj.copy()
            cage_cpy.data = cage_obj.data.copy()
            cage_obj_name = cage_cpy.name
        
        # Load in template bake scene with mostly optimised settings for baking
        bake_scene_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), "resources", "BakeWrangler_Scene.blend")
        bake_scene = None
        with bpy.data.libraries.load(bake_scene_path, link=False, relative=False) as (file_from, file_to):
            file_to.scenes.append("BakeWrangler")
        bake_scene = file_to.scenes[0]
        # Set the cycles values that aren't saved in the template and give it a name that can be traced
        bake_scene.cycles.device = bake_dev
        bake_scene.cycles.samples = bake_samp
        bake_scene.cycles.aa_samples = bake_samp
        bake_scene.name = "bake_" + node.get_name() + "_" + mesh.get_name()
        
        # Firstly there are two main catagories of bake. Either the bake is of some data that blender can calculate
        # (normals, roughness, etc) or it is of some property of the material (albedo, metalness, etc). The first set
        # don't require any changes to be made to materials, while the second set do.
        # Then there are three posibilities for where to get the data. For a single object, the data comes from its
        # own materials. A sub case of this is using a multires modifier to get some data (normals). Finally many
        # objects can be mapped to the surface of the target, in which case the materials on the target don't matter,
        # but the materials on everything else does.
        
        # Regardless of strategy the following data will be used. Copies are made so other passes can get the originals
        target_cpy = target.copy()
        target_cpy.data = target.data.copy()
        bake_scene.collection.objects.link(target_cpy)
        
        # Determine what strategy to use for this bake and set up the data for it
        bake_strategy = ''
        if multi == True:
            bake_strategy = 'MULTI'
            cage = False
            to_active = False
        elif to_active:
            bake_strategy = 'TOACT'
            # To active needs a copy of all the objects, not just target
            object_cpys = []
            for obj in objects:
                copy = obj.copy()
                copy.data = obj.data.copy()
                object_cpys.append(copy)
                bake_scene.collection.objects.link(copy)
            # Materials should be removed from the target copy for To active
            target_cpy.data.materials.clear()
            target_cpy.data.polygons.foreach_set('material_index', [0] * len(target_cpy.data.polygons))
            target_cpy.data.update()
            # Add the cage copy to the scene because it doesn't work properly in a different scene currently
            if cage:
                bake_scene.collection.objects.link(cage_cpy)
        else:
            bake_strategy = 'SOLO'
            cage = False
            to_active = False
                
        # Switch into bake scene
        prev_scene = bpy.context.window.scene
        prev_layer = bpy.context.view_layer
        bpy.context.window.scene = bake_scene
        # Trick to make the view layer stay the same on switching back maybe?
        bpy.context.view_layer.name = prev_layer.name
        
        # Apply or remove all modifiers depending on their render settings as mods are causing crashes in some cases
        for obj in bpy.context.window.scene.objects:
            bpy.ops.object.select_all(action='DESELECT')
            bpy.context.view_layer.objects.active = obj
            if len(obj.modifiers):
                for mod in obj.modifiers:
                    # Don't get rid of multires mods if they are the target to bake
                    if bake_strategy == 'MULTI' and mod.type == 'MULTIRES' and mod.show_render:
                        continue
                    if mod.show_render:
                        # A mod can be disabled by invalid settings, which will throw an exception when trying to apply it
                        try:
                            bpy.ops.object.modifier_apply(modifier=mod.name)
                        except:
                            bpy.ops.object.modifier_remove(modifier=mod.name)
                    else:
                        bpy.ops.object.modifier_remove(modifier=mod.name)
            
        # Select the target and make it active
        bpy.ops.object.select_all(action='DESELECT')
        target_cpy.select_set(True)
        bpy.context.view_layer.objects.active = target_cpy
        
        # Make single user copies of all materials still in play. Even if they wont be changed by this bake.
        bpy.ops.object.select_all(action='SELECT')
        # Deselect the cage if its in use
        if cage:
            cage_cpy.select_set(False)
        bpy.ops.object.make_single_user(type='SELECTED_OBJECTS', object=False, obdata=False, material=True, animation=False)
        
        # Collect a list of all the materials, making sure each is only added once
        unique_mats = []
        if bake_strategy == 'TOACT':
            # Get materials from all the objects except the target
            for obj in object_cpys:
                has_mat = False
                if len(obj.data.materials):
                    for mat in obj.data.materials:
                        # Slots can be empty
                        if mat != None:
                            has_mat = True
                            if unique_mats.count(mat) == 0:
                                unique_mats.append(mat)
                if not has_mat:
                    # If the object has no materials, one needs to be added for the mask baking step
                    mat = bpy.data.materials.new(name="mask_" + obj.name)
                    mat.use_nodes = True
                    obj.data.materials.append(mat)
                    if unique_mats.count(mat) == 0:
                        unique_mats.append(mat)
        else:
            # Get materials from only the target
            if len(target_cpy.data.materials):
                for mat in target_cpy.data.materials:
                    # Slots can be empty
                    if mat != None:
                        if unique_mats.count(mat) == 0:
                            unique_mats.append(mat)
                                
        # Add simple image node material to target object for To active bake or if it doesn't have a material
        if bake_strategy == 'TOACT' or len(target_cpy.data.materials) < 1:
            mat = bpy.data.materials.new(name="mat_" + node.get_name() + "_" + mesh.get_name())
            mat.use_nodes = True
            image_node = mat.node_tree.nodes.new("ShaderNodeTexImage")
            image_node.image = img_bake
            image_node.select = True
            mat.node_tree.nodes.active = image_node
            target_cpy.data.materials.append(mat)
        
        # Prepare the materials for the bake type
        for mat in unique_mats:
            prep_material_for_bake(node, mat.node_tree, bake_type)
            
            if bake_strategy != 'TOACT':
                # For non To active bakes, add an image node to the material and make it selected + active for bake image
                image_node = mat.node_tree.nodes.new("ShaderNodeTexImage")
                image_node.image = img_bake
                image_node.select = True
                mat.node_tree.nodes.active = image_node
        
        start = datetime.now()
        _print(">    -Baking %s pass: " % (bake_type), tag=True, wrap=False)
        
        # Set 'real' bake pass. PBR use EMIT rather than the named pass, since those passes don't exist.
        if not bake_type in node.bake_built_in:
            bake_type = 'EMIT'
            
        # Do the bake. Most of the properies can be passed as arguments to the operator.
        try:
            if bake_strategy != 'MULTI':
                bpy.ops.object.bake(
                    type=bake_type,
                    pass_filter=pass_influences,
                    margin=margin,
                    use_selected_to_active=to_active,
                    cage_extrusion=ray_dist,
                    cage_object=cage_obj_name,
                    normal_space='TANGENT',
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
                image_node = target_cpy.data.materials[0].node_tree.nodes.new("ShaderNodeTexImage")
                image_node.image = img_mask
                image_node.select = True
                target_cpy.data.materials[0].node_tree.nodes.active = image_node
            
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
        bpy.context.window.scene = prev_scene
    
    _print(">", tag=True)   
    _print(">  Input Meshes processed in %s" % (str(datetime.now() - pass_start)), tag=True)
    
    # Finished inputs, return the bakes
    return [err, img_bake, img_mask]



# Takes a bake pass node along with the generated image and mask. Processes all attached outputs.
def process_bake_pass_output(node, bake, mask):
    pass_start = datetime.now()
    err = False
    
    # Each output can link to multiple nodes, so each link must be processed
    outputs = []
    for output in node.outputs:
        if output.is_linked:
            for link in output.links:
                if link.is_valid:
                    outputs.append([output.name, link.to_node, link.to_socket.name])
    
    _print(">", tag=True)
    _print(">  Output Images: %i" % (len(outputs)), tag=True)
    
    # Process all the valid outputs
    for bake_data, output_node, socket in outputs:
        _print(">   %i/%i: [%s]" % ((outputs.index([bake_data, output_node, socket]) + 1), len(outputs), output_node.get_name()), tag=True)
        
        output_image = None
        output_size = [output_node.img_xres, output_node.img_yres]
        output_path = output_node.img_path
        output_name = output_node.img_name
        output_file = os.path.join(os.path.realpath(output_path), output_name)
        
        # See if the output exists or if a new file should be created
        if os.path.exists(output_file):
            # Open it
            _print(">   - Using existing file", tag=True)
            output_image = bpy.data.images.load(os.path.abspath(output_file))
            
            # The image could be a different size to what is specified. If so, scale it to match
            if output_image.size[0] != output_size[0] or output_image.size[1] != output_size[1]:
                _print(">   -- Resolution mis-match, scaling", tag=True)
                output_image.scale(output_size[0], output_size[1])
        else:
            # Create it
            _print(">   - Creating file", tag=True)
            output_image = bpy.data.images.new(output_node.name + "." + output_node.label, width=output_size[0], height=output_size[1])
            output_image.filepath_raw = os.path.abspath(output_file)
            if node.bake_pass == 'NORMAL':
                output_image.generated_color = (0.5, 0.5, 1.0, 1.0)
        
        # Set the color space, etc
        output_image.colorspace_settings.name = output_node.img_color_space
        if output_node.img_color_space == 'Non-Color':
            output_image.colorspace_settings.is_data = True
        output_image.alpha_mode = 'STRAIGHT'
        output_image.file_format = output_node.img_type
        
        # If the output is a different size to the bake, make a copy of the bake data and scale it to match.
        # A copy is used because multiple outputs can reference the same bake data and be different sizes, so
        # the original data needs to be preserved.
        bake_copy = bake
        mask_copy = mask
        if bake.size[0] != output_size[0] or bake.size[1] != output_size[1]:
            _print(">   - Bake resolution mis-match, scaling bake", tag=True)
            
            bake_copy = bake.copy()
            bake_copy.pixels = list(bake.pixels)
            bake_copy.scale(output_size[0], output_size[1])
            
            mask_copy = mask.copy()
            mask_copy.pixels = list(mask.pixels)
            mask_copy.scale(output_size[0], output_size[1])
        
        # Prepare a copy of the pixels in image, mask and output as accessing the data directly is quite slow.
        # Making a copy and working with that is many times faster for some reason.
        bake_px = list(bake_copy.pixels)
        mask_px = list()
        output_px = list(output_image.pixels)
        
        # Color to Color can just be copied directly, anything else needs some intermediate steps
        if not (bake_data == 'Color' and socket == 'Color' and not node.mask_samples > 0):
            map_time = datetime.now()
            _print(">   - Bake data requies mapping to output image: ", tag=True, wrap=False)
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
                            if output_image.channels > chan:
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
        else:
            output_px = bake_px
            
        # Copy the pixels to the image and save it
        _print(">   - Writing pixels and saving image: ", tag=True, wrap=False)
        output_image.pixels[0:] = output_px
        
        # Configure output image settings
        img_scene = bpy.context.window.scene
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



# Takes a materials node tree and makes any changes necessary to perform the given bake type. A material must
# end with a principled shader connected to a material output in order to be set up for any emission node bakes.
def prep_material_for_bake(node, node_tree, bake_type):
    # Bake types with built-in passes don't require any perperation
    if not node_tree or bake_type in node.bake_built_in:
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
    node_selected_shader = None
    
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
                    node_generic_outputs.append(node)
                
    # Select the first usable output using the order explained above and make sure no other outputs are set active
    node_outputs = node_cycles_out_active + node_cycles_out + node_generic_out_active + node_generic_out
    for node in node_outputs:
        input = node.inputs['Surface']
        if not node_selected_output and input.is_linked and input.links[0].from_node.type == 'BSDF_PRINCIPLED':
            node_selected_output = node
            node_selected_shader = input.links[0].from_node
            node.is_active_output = True
        else:
            node.is_active_output = False
    
    if not node_selected_output or not node_selected_shader:
        return
    
    # Output and Shader have been chosen. Next pick the shader input based on bake type
    node_shader_input = None
    if bake_type == 'ALBEDO':
        node_shader_input = node_selected_shader.inputs['Base Color']
    elif bake_type == 'METALIC':
        node_shader_input = node_selected_shader.inputs['Metallic']
    elif bake_type == 'ALPHA':
        node_shader_input = node_selected_shader.inputs['Alpha']

    # Add emission shader and connect it to the output
    node_emit = nodes.new('ShaderNodeEmission')
    node_tree.links.new(node_emit.outputs['Emission'], node_selected_output.inputs['Surface'])
    
    # The input value can either be coming from a linked node or be set on the node. Either connect the link
    # or copy the value
    if node_shader_input.is_linked:
        node_tree.links.new(node_shader_input.links[0].from_socket, node_emit.inputs[0])
    else:
        if node_shader_input.type == 'RGBA':
            node_emit.inputs[0].default_value = node_shader_input.default_value
        else:
            node_emit.inputs[0].default_value[0] = node_shader_input.default_value
            node_emit.inputs[0].default_value[1] = node_shader_input.default_value
            node_emit.inputs[0].default_value[2] = node_shader_input.default_value
            node_emit.inputs[0].default_value[3] = 1.0
            
    return



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
        "This scipt is used internally by Bake Wrangler addon."
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

    args = parser.parse_args(argv)

    if not argv:
        parser.print_help()
        return

    if not args.tree or not args.node:
        print("Error: required arguments not found")
        return
    
    # Make sure the node classes are registered
    try:
        node_tree.register()
    except:
        print("Info: Bake Wrangler nodes already registered")
    else:
        print("Info: Bake Wrangler nodes registered")
        
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
