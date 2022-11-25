import argparse
from os import path
import ToolRepairSTL

from morphman.common.vmtk_wrapper import vmtk_smooth_surface, read_polydata, write_polydata, vmtk_cap_polydata
from morphman.common.vtk_wrapper import vtk_clean_polydata, vtk_triangulate_surface
from morphman.common.surface_operations import is_surface_capped, get_uncapped_surface
from morphman.common.common import get_parameters, write_parameters

def str2bool(boolean):
    """Convert a string to boolean.
    Args:
        boolean (str): Input string.
    Returns:
        return (bool): Converted string.
    """
    if boolean.lower() in ('yes', 'true', 't', 'y', '1'):
        return True
    elif boolean.lower() in ('no', 'false', 'f', 'n', '0'):
        return False
    else:
        raise ValueError('Boolean value expected.')


def run_pre_processing(filename_model, verbose_print, smoothing_method, smoothing_factor, meshing_method,
                       refine_region, create_flow_extensions, viz, coarsening_factor,
                       inlet_flow_extension_length, outlet_flow_extension_length, edge_length, region_points,
                       compress_mesh):
    # Get paths
    abs_path = path.abspath(path.dirname(__file__))
    case_name = filename_model.rsplit(path.sep, 1)[-1].rsplit('.')[0]
    dir_path = filename_model.rsplit(path.sep, 1)[0]

    # Naming conventions
    file_name_centerlines = path.join(dir_path, case_name + "_centerlines.vtp")
    file_name_refine_region_centerlines = path.join(dir_path, case_name + "_refine_region_centerline.vtp")
    file_name_region_centerlines = path.join(dir_path, case_name + "_sac_centerline_{}.vtp")
    file_name_distance_to_sphere_diam = path.join(dir_path, case_name + "_distance_to_sphere_diam.vtp")
    file_name_distance_to_sphere_const = path.join(dir_path, case_name + "_distance_to_sphere_const.vtp")
    file_name_distance_to_sphere_curv = path.join(dir_path, case_name + "_distance_to_sphere_curv.vtp")
    file_name_probe_points = path.join(dir_path, case_name + "_probe_point")
    file_name_voronoi = path.join(dir_path, case_name + "_voronoi.vtp")
    file_name_voronoi_smooth = path.join(dir_path, case_name + "_voronoi_smooth.vtp")
    file_name_surface_smooth = path.join(dir_path, case_name + "_smooth.vtp")
    file_name_model_flow_ext = path.join(dir_path, case_name + "_flowext.vtp")
    file_name_clipped_model = path.join(dir_path, case_name + "_clippedmodel.vtp")
    file_name_flow_centerlines = path.join(dir_path, case_name + "_flow_cl.vtp")
    file_name_surface_name = path.join(dir_path, case_name + "_remeshed_surface.vtp")
    file_name_xml_mesh = path.join(dir_path, case_name + ".xml")
    file_name_vtu_mesh = path.join(dir_path, case_name + ".vtu")
    file_name_run_script = path.join(dir_path, case_name + ".sh")

    print("\n--- Working on case:", case_name, "\n")

      # Open the surface file.
    print("--- Load model file\n")
    surface = read_polydata(filename_model)

    # Check if surface is closed and uncapps model if True
    if is_surface_capped(surface)[0] and smoothing_method != "voronoi":
        if not path.isfile(file_name_clipped_model):
            print("--- Clipping the models inlets and outlets.\n")
            # TODO: Add input parameters as input to automatedPreProcessing
            # Value of gradients_limit should be generally low, to detect flat surfaces corresponding
            # to closed boundaries. Area_limit will set an upper limit of the detected area, may vary between models.
            # The circleness_limit parameters determines the detected regions similarity to a circle, often assumed
            # to be close to a circle.
            surface = get_uncapped_surface(surface, gradients_limit=0.01, area_limit=20, circleness_limit=5)
            write_polydata(surface, file_name_clipped_model)
        else:
            surface = read_polydata(file_name_clipped_model)
    parameters = get_parameters(path.join(dir_path, case_name))

    if "check_surface" not in parameters.keys():
        surface = vtk_clean_polydata(surface)
        surface = vtk_triangulate_surface(surface)

        # Check the mesh if there is redundant nodes or NaN triangles.
        ToolRepairSTL.surfaceOverview(surface)
        ToolRepairSTL.foundAndDeleteNaNTriangles(surface)
        surface = ToolRepairSTL.cleanTheSurface(surface)
        foundNaN = ToolRepairSTL.foundAndDeleteNaNTriangles(surface)
        if foundNaN:
            raise RuntimeError(("There is an issue with the surface. "
                                "Nan coordinates or some other shenanigans."))
        else:
            parameters["check_surface"] = True
            write_parameters(parameters, path.join(dir_path, case_name))
        
          # Create a capped version of the surface
        capped_surface = vmtk_cap_polydata(surface)



def read_command_line():
    """
    Read arguments from commandline and return all values in a dictionary.
    """
    parser = argparse.ArgumentParser(
        description="Automated pre-processing for vascular modeling.")

    parser.add_argument('-v', '--verbosity',
                        dest='verbosity',
                        type=str2bool,
                        default=False,
                        help="Activates the verbose mode.")

    parser.add_argument('-i', '--inputModel',
                        type=str,
                        required=False,
                        dest='fileNameModel',
                        default='example/surface.vtp',
                        help="Input file containing the 3D model.")

    parser.add_argument('-cM', '--compress-mesh',
                        type=str2bool,
                        required=False,
                        dest='compressMesh',
                        default=True,
                        help="Compress output mesh after generation.")

    parser.add_argument('-sM', '--smoothingMethod',
                        type=str,
                        required=False,
                        dest='smoothingMethod',
                        default="no_smooth",
                        choices=["voronoi", "no_smooth", "laplace", "taubin"],
                        help="Smoothing method, for now only Voronoi smoothing is available." +
                             " For Voronoi smoothing you can also control smoothingFactor" +
                             " (default = 0.25).")

    parser.add_argument('-c', '--coarseningFactor',
                        type=float,
                        required=False,
                        dest='coarseningFactor',
                        default=1.0,
                        help="Refine or coarsen the standard mesh size. The higher the value the coarser the mesh.")

    parser.add_argument('-sF', '--smoothingFactor',
                        type=float,
                        required=False,
                        dest='smoothingFactor',
                        default=0.25,
                        help="smoothingFactor for VoronoiSmoothing, removes all spheres which" +
                             " has a radius < MISR*(1-0.25), where MISR varying along the centerline.")

    parser.add_argument('-m', '--meshingMethod',
                        dest="meshingMethod",
                        type=str,
                        choices=["diameter", "curvature", "constant"],
                        default="diameter")

    parser.add_argument('-el', '--edge-length',
                        dest="edgeLength",
                        default=None,
                        type=float,
                        help="Characteristic edge length used for meshing.")

    parser.add_argument('-r', '--refine-region',
                        dest="refineRegion",
                        type=str2bool,
                        default=False,
                        help="Determine weather or not to refine a specific region of " +
                             "the input model. Default is False.")

    parser.add_argument('-rp', '--region-points',
                        dest="regionPoints",
                        type=float,
                        nargs="+",
                        default=None,
                        help="If -r or --refine-region is True, the user can provide the point(s)"
                             " which defines the regions to refine. " +
                             "Example providing the points (0.1, 5.0, -1) and (1, -5.2, 3.21):" +
                             " --region-points 0.1 5 -1 1 5.24 3.21")

    parser.add_argument('-f', '--flowext',
                        dest="flowExtension",
                        default=True,
                        type=str2bool,
                        help="Add flow extensions to to the model.")

    parser.add_argument('-fli', '--inletFlowext',
                        dest="inletFlowExtLen",
                        default=5,
                        type=float,
                        help="Length of flow extensions at inlet(s).")

    parser.add_argument('-flo', '--outletFlowext',
                        dest="outletFlowExtLen",
                        default=5,
                        type=float,
                        help="Length of flow extensions at outlet(s).")

    parser.add_argument('-vz', '--visualize',
                        dest="viz",
                        default=True,
                        type=str2bool,
                        help="Visualize surface, inlet, outlet and probes after meshing.")


    args, _ = parser.parse_known_args()

    if args.verbosity:
        print()
        print("--- VERBOSE MODE ACTIVATED ---")

        def verbose_print(*args):
            for arg in args:
                print(arg, end=' ')
                print()
    else:
        verbose_print = lambda *a: None

    verbose_print(args)

    return dict(filename_model=args.fileNameModel, verbose_print=verbose_print, smoothing_method=args.smoothingMethod,
                smoothing_factor=args.smoothingFactor, meshing_method=args.meshingMethod,
                refine_region=args.refineRegion, create_flow_extensions=args.flowExtension, viz=args.viz,
                coarsening_factor=args.coarseningFactor, inlet_flow_extension_length=args.inletFlowExtLen,
                edge_length=args.edgeLength, region_points=args.regionPoints, compress_mesh=args.compressMesh,
                outlet_flow_extension_length=args.outletFlowExtLen)

if __name__ == "__main__":
    run_pre_processing(**read_command_line()) 