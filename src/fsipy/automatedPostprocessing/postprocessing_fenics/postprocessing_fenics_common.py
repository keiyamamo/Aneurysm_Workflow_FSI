# Copyright (c) 2023 Simula Research Laboratory
# SPDX-License-Identifier: GPL-3.0-or-later
"""common functions for postprocessing-fenics scripts"""

import argparse
from pathlib import Path
from dolfin import TestFunction, TrialFunction, inner, Function, LocalSolver, dx


def parse_arguments() -> argparse.Namespace:
    """
    Parse command line arguments.

    Returns:
        argparse.Namespace: Parsed command-line arguments.
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--folder", type=Path, help="Path to simulation results")
    parser.add_argument('--mesh-path', type=Path, default=None,
                        help="Path to the mesh file (default: <folder_path>/Mesh/mesh.h5)")
    parser.add_argument("--stride", type=int, default=1, help="Save frequency of simulation")
    parser.add_argument("-st", "--start-time", type=float, default=None, help="Desired start time for postprocessing")
    parser.add_argument("-et", "--end-time", type=float, default=None, help="Desired end time for postprocessing")
    parser.add_argument("--extract-solid-only", action="store_true", help="Extract solid displacement only")
    parser.add_argument("--log-level", type=int, default=20,
                        help="Specify the log level (default is 20, which is INFO)")

    return parser.parse_args()


def project_dg(f, V) -> Function:
    """
    Project a function v into a DG space V.
    It perfomrs the same operation as dolfin.project, but it is more efficient
    since we use local_solver which is possible since we use DG spaces.

    Args:
        v (dolfin.Function): Function to be projected
        V (dolfin.FunctionSpace): DG space
        dx_s (dolfin.Measure): Measure over the solid domain

    Returns:
        dolfin.Function: Projected function
    """
    v = TestFunction(V)
    u = TrialFunction(V)
    a = inner(u, v) * dx
    L = inner(f, v) * dx
    u_ = Function(V)
    solver = LocalSolver(a, L)
    solver.factorize()
    solver.solve_local_rhs(u_)

    return u_
