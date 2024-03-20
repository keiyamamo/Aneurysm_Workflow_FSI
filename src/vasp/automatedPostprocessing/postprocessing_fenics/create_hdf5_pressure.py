# Copyright (c) 2023 David Bruneau
# Modified by Kei Yamamoto 2023
# SPDX-License-Identifier: GPL-3.0-or-later

"""
This script reads the displacement and velocity data from turtleFSI output and reformats the data so that it can be read
in fenics. The output files are saved in the Visualization_separate_domain folder.
"""

import numpy as np
import h5py
from pathlib import Path
import json
import logging
import argparse
from tqdm import tqdm

from vasp.automatedPostprocessing.postprocessing_common import get_domain_ids, output_file_lists
from dolfin import Mesh, HDF5File, VectorFunctionSpace, Function, MPI, parameters


# set compiler arguments
parameters["reorder_dofs_serial"] = False


def parse_arguments() -> argparse.Namespace:
    """
    Parse command line arguments.

    Returns:
        argparse.Namespace: Parsed command-line arguments.
    """
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument("--folder", type=Path, help="Path to simulation results")
    parser.add_argument('--mesh-path', type=Path, default=None,
                        help="Path to the mesh file. If not given (None), " +
                             "it will assume that mesh is located <folder>/Mesh/mesh.h5)")
    parser.add_argument("--stride", type=int, default=1, help="Save frequency of simulation")
    parser.add_argument("-st", "--start-time", type=float, default=None, help="Desired start time for postprocessing")
    parser.add_argument("-et", "--end-time", type=float, default=None, help="Desired end time for postprocessing")
    parser.add_argument("--log-level", type=int, default=20,
                        help="Specify the log level (default is 20, which is INFO)")

    return parser.parse_args()


def create_hdf5(visualization_path, mesh_path, save_time_step, stride, start_time, end_time,
                fluid_domain_id, solid_domain_id):

    """
    Loads displacement/velocity data from turtleFSI output and reformats the data so that it can be read in fenics.

    Args:
        visualization_path (Path): Path to the folder containing the visualization files (displacement/velocity.h5)
        mesh_path (Path): Path to the mesh file (mesh.h5 or mesh_refined.h5 depending on save_deg)
        stride: stride of the time steps to be saved
        start_t (float): desired start time for the output file
        end_t (float): desired end time for the output file
        extracct_solid_only (bool): If True, only the solid domain is extracted for displacement.
                                    If False, both the fluid and solid domains are extracted.
        fluid_domain_id (int or list): ID of the fluid domain
        solid_domain_id (int or list): ID of the solid domain
    """

    # Define mesh path related variables
    fluid_domain_path = mesh_path.with_name(mesh_path.stem + "_fluid.h5")
  
    # Check if the input mesh exists
    if not fluid_domain_path.exists():
        raise ValueError("Mesh file not found.")

    # Read fluid and solid mesh
    logging.info("--- Reading fluid mesh file \n")
    mesh_fluid = Mesh()
    with HDF5File(MPI.comm_world, str(fluid_domain_path), "r") as mesh_file:
        mesh_file.read(mesh_fluid, "mesh", False)

    # Define function spaces and functions
    logging.info("--- Defining function spaces and functions \n")
    Vf = VectorFunctionSpace(mesh_fluid, "CG", 1)
    d = Function(Vf)

    # Define paths for displacement files
    xdmf_file_p = visualization_path / "pressure.xdmf"

    # Get information about h5 files associated with xdmf files and also information about the timesteps
    logging.info("--- Getting information about h5 files \n")
    h5file_name_list_p, timevalue_list, index_list_p = output_file_lists(xdmf_file_p)

    fluid_ids, _, _ = get_domain_ids(mesh_path, fluid_domain_id, solid_domain_id)

    # Open up the first displacement.h5 file to get the number of timesteps and nodes for the output data
    file_p = visualization_path / h5file_name_list_p[0]
    vector_data_p = h5py.File(str(file_p))
    vector_array_all_p = vector_data_p['VisualisationVector/0'][:, :]
    vector_array_p = vector_array_all_p[fluid_ids, :]

    # Define path to the output files
    visualization_separate_domain_folder = visualization_path.parent / "Visualization_separate_domain"
    d_output_path = visualization_separate_domain_folder / "p.h5" 
    # Initialize h5 file names that might differ during the loop
    h5_file_prev_p = None

    # Define start and end time and indices for the loop
    start_time = start_time if start_time is not None else timevalue_list[0]

    if end_time is not None:
        assert end_time > start_time, "end_time must be greater than start_time"
        assert end_time <= timevalue_list[-1], "end_time must be less than the last time step"

    end_time = end_time if end_time is not None else timevalue_list[-1]

    start_time_index = int(start_time / save_time_step) - 1
    end_time_index = int(end_time / save_time_step) + 1

    # Initialize tqdm with the total number of iterations
    progress_bar = tqdm(total=end_time_index - start_time_index, desc="--- Converting data:", unit="step")

    for file_counter in range(start_time_index, end_time_index, stride):

        time = timevalue_list[file_counter]

        if file_counter > start_time_index:
            if np.abs(time - timevalue_list[file_counter - 1] - save_time_step) > 1e-8:
                logging.warning("WARNING : Uenven temporal spacing detected")

        # Open input displacement h5 file
        h5_file_p = visualization_path / h5file_name_list_p[file_counter]
        if h5_file_p != h5_file_prev_p:
            vector_data_p.close()
            vector_data_p = h5py.File(str(h5_file_p))
        h5_file_prev_p = h5_file_p

        # Open up Vector Arrays from h5 file
        array_name_d = 'VisualisationVector/' + str((index_list_p[file_counter]))
        vector_array_all_p = vector_data_p[array_name_d][:, :]
        vector_array_p = vector_array_all_p[fluid_ids, :]

        # Flatten the vector array and insert into the function
        vector_np_flat_p = vector_array_p.flatten('F')
        d.vector().set_local(vector_np_flat_p)

        file_mode = "a" if file_counter > start_time_index else "w"

        # Save pressure
        viz_p_file = HDF5File(MPI.comm_world, str(d_output_path), file_mode=file_mode)
        viz_p_file.write(d, "/pressure", time)
        viz_p_file.close()

        # Update the information in the progress bar
        progress_bar.set_postfix({"Timestep": index_list_p[file_counter], "Time": timevalue_list[file_counter],
                                 "File": h5file_name_list_p[file_counter]})
        progress_bar.update()

    progress_bar.close()

    logging.info("--- Finished reading solutions")
    logging.info(f"--- Saved p.h5 in {visualization_separate_domain_folder.absolute()}")


def main() -> None:

    assert MPI.size(MPI.comm_world) == 1, "This script only runs in serial."

    args = parse_arguments()

    logging.basicConfig(level=args.log_level, format="%(message)s")

    # Define paths for visulization and mesh files
    folder_path = Path(args.folder)
    visualization_path = folder_path / "Visualization"

    # Read parameters from default_variables.json
    parameter_path = folder_path / "Checkpoint" / "default_variables.json"
    with open(parameter_path, "r") as f:
        parameters = json.load(f)
        dt = parameters["dt"]
        save_step = parameters["save_step"]
        save_time_step = dt * save_step
        logging.info(f"save_time_step: {save_time_step} \n")
        fluid_domain_id = parameters["dx_f_id"]
        solid_domain_id = parameters["dx_s_id"]

        logging.info(f"--- Fluid domain ID: {fluid_domain_id} and Solid domain ID: {solid_domain_id} \n")

    if args.mesh_path:
        mesh_path = Path(args.mesh_path)
        logging.info("--- Using user-defined mesh \n")
        assert mesh_path.exists(), f"Mesh file {mesh_path} not found."
    else:
        mesh_path = folder_path / "Mesh" / "mesh.h5"
        logging.info("--- Using non-refined mesh \n")
        assert mesh_path.exists(), f"Mesh file {mesh_path} not found."

    create_hdf5(visualization_path, mesh_path, save_time_step, args.stride,
                args.start_time, args.end_time, fluid_domain_id, solid_domain_id)


if __name__ == '__main__':
    main()
