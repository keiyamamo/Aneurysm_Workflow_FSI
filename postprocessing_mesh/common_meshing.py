from argparse import ArgumentParser
import numpy as np
import h5py
import shutil
import os
from pathlib import Path

def read_command_line():
    """Read arguments from commandline"""
    parser = ArgumentParser()

    parser.add_argument('--fp', "-folder_path",  type=Path, help="Path to simulation results",
                        )
    parser.add_argument('--mesh', type=str, default="file_stenosis", help="Mesh File Name",
                        metavar="PATH")

    args = parser.parse_args()

    return args.fp, args.mesh


def get_domain_topology(meshFile):
    # This function obtains the topology for the fluid, solid, and all elements of the input mesh
    vectorData = h5py.File(meshFile)
    domainsLoc = 'domains/values'
    domains = vectorData[domainsLoc][:] # Open domain array
    id_wall = (domains>1).nonzero() # domain = 2 is the solid
    id_fluid = (domains==1).nonzero() # domain = 1 is the fluid

    topologyLoc = 'domains/topology'
    allTopology = vectorData[topologyLoc][:,:] 
    wallTopology=allTopology[id_wall,:] 
    fluidTopology=allTopology[id_fluid,:]

    return fluidTopology, wallTopology, allTopology

def get_domain_ids(meshFile):
    # This function obtains a list of the node IDs for the fluid, solid, and all elements of the input mesh

    # Get topology of fluid, solid and whole mesh
    fluidTopology, wallTopology, allTopology = get_domain_topology(meshFile)
    wallIDs = np.unique(wallTopology) # find the unique node ids in the wall topology, sorted in ascending order
    fluidIDs = np.unique(fluidTopology) # find the unique node ids in the fluid topology, sorted in ascending order
    allIDs = np.unique(allTopology) 
    return fluidIDs, wallIDs, allIDs

def fix_fluid_only_mesh(meshFile):
    # This function fixes the node numbering so that the numbers start at 0 and are continuous integers

    #read in the fsi mesh:
    fsi_mesh = h5py.File(meshFile,'r')

    # Count fluid and total nodes
    coordArrayFSI= fsi_mesh['mesh/coordinates'][:,:]
    topoArrayFSI= fsi_mesh['mesh/topology'][:,:]
    nNodesFSI = coordArrayFSI.shape[0]
    nElementsFSI = topoArrayFSI.shape[0]

    # Get fluid only topology
    fluidTopology, wallTopology, allTopology = get_domain_topology(meshFile)
    fluidIDs, wallIDs, allIDs = get_domain_ids(meshFile)
    coordArrayFluid= fsi_mesh['mesh/coordinates'][fluidIDs,:]

    # Copy mesh file to new "fixed" file
    fluid_mesh_path =  meshFile.replace(".h5","_fluid_only.h5")    
    fluid_mesh_path_fixed =  meshFile.replace(".h5","_fluid_only_fixed.h5")    

    # Fix Fluid topology
    for node_id in range(len(fluidIDs)):
        fluidTopology = np.where(fluidTopology == fluidIDs[node_id], node_id, fluidTopology)

    shutil.copyfile(fluid_mesh_path, fluid_mesh_path_fixed)

    # Replace all the arrays in the "fixed" file with the correct node numbering and topology
    vectorData = h5py.File(fluid_mesh_path_fixed,'a')

    geoArray = vectorData["mesh/coordinates"]
    geoArray[...] = coordArrayFluid
    topoArray = vectorData["mesh/topology"]
    topoArray[...] = fluidTopology
    vectorData.close() 

    os.remove(fluid_mesh_path)
    os.rename(fluid_mesh_path_fixed,fluid_mesh_path)

def fix_solid_only_mesh(meshFile):


    #read in the fsi mesh:
    fsi_mesh = h5py.File(meshFile,'r')

    # Count fluid and total nodes
    coordArrayFSI= fsi_mesh['mesh/coordinates'][:,:]
    topoArrayFSI= fsi_mesh['mesh/topology'][:,:]
    nNodesFSI = coordArrayFSI.shape[0]
    nElementsFSI = topoArrayFSI.shape[0]

    # Get fluid only topology
    fluidTopology, wallTopology, allTopology = get_domain_topology(meshFile)
    fluidIDs, wallIDs, allIDs = get_domain_ids(meshFile)
    coordArraySolid= fsi_mesh['mesh/coordinates'][wallIDs,:]

    # Copy mesh file to new "fixed" file
    solid_mesh_path =  meshFile.replace(".h5","_solid_only.h5")    
    solid_mesh_path_fixed =  meshFile.replace(".h5","_solid_only_fixed.h5")    

    # Fix Wall topology
    for node_id in range(len(wallIDs)):
        wallTopology = np.where(wallTopology == wallIDs[node_id], node_id, wallTopology)

    shutil.copyfile(solid_mesh_path, solid_mesh_path_fixed)

    # Replace all the arrays in the "fixed" file with the correct node numbering and topology
    vectorData = h5py.File(solid_mesh_path_fixed,'a')

    geoArray = vectorData["mesh/coordinates"]
    geoArray[...] = coordArraySolid
    topoArray = vectorData["mesh/topology"]
    topoArray[...] = wallTopology
    vectorData.close() 

    os.remove(solid_mesh_path)
    os.rename(solid_mesh_path_fixed,solid_mesh_path)