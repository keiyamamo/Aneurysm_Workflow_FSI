"""
Problem file for aneurysm FSI simulation
"""
import os
import numpy as np

from vampy.simulation.Womersley import make_womersley_bcs, compute_boundary_geometry_acrn
from turtleFSI.problems import *
from dolfin import HDF5File, Mesh, MeshFunction, facets, assemble, UserExpression, sqrt, FacetNormal, ds, \
    DirichletBC, Measure, inner, parameters, VectorFunctionSpace, Function, XDMFFile, File

from vasp.simulations.simulation_common import load_probe_points, calculate_and_print_flow_properties, \
    print_probe_points

# set compiler arguments
parameters["form_compiler"]["quadrature_degree"] = 6
parameters["form_compiler"]["optimize"] = True
# The "ghost_mode" has to do with the assembly of form containing the facet
# normals n('+') within interior boundaries (dS). for 3D mesh the value should
# be "shared_vertex", for 2D mesh "shared_facet", the default value is "none"
parameters["ghost_mode"] = "shared_vertex"
_compiler_parameters = dict(parameters["form_compiler"])


def set_problem_parameters(default_variables, **namespace):

    # Compute some solid parameters
    # Need to stay here since mus_s and lambda_s are functions of nu_s and E_s
    E_s_val = 1E6
    nu_s_val = 0.45
    mu_s_val = E_s_val / (2 * (1 + nu_s_val))  # 0.345E6
    lambda_s_val = nu_s_val * 2. * mu_s_val / (1. - 2. * nu_s_val)

    default_variables.update(dict(
        # Temporal parameters
        T=1.902,  # Simulation end time
        dt=0.001,  # Timne step size
        theta=0.501,  # Theta scheme parameter
        save_step=1,  # Save frequency of files for visualisation
        save_solution_after_tstep=5000,  # Start saving the solution after this time step for the mean value
        checkpoint_step=50,  # Save frequency of checkpoint files
        # Linear solver parameters
        linear_solver="mumps",
        atol=1e-10,  # Absolute tolerance in the Newton solver
        rtol=1e-9,  # Relative tolerance in the Newton solver
        recompute=20,  # Recompute the Jacobian matix within time steps
        recompute_tstep=20,  # Recompute the Jacobian matix over time steps
        # boundary condition parameters
        inlet_id=2,  # inlet id for the fluid
        inlet_outlet_s_id=11,  # inlet and outlet id for solid
        fsi_id=22,  # id for fsi surface
        rigid_id=11,  # "rigid wall" id for the fluid
        outer_id=33,  # id for the outer surface of the solid
        # Fluid parameters
        Q_mean=1.25E-06,
        P_mean=11200,
        T_Cycle=0.951,  # Used to define length of flow waveform
        rho_f=1.000E3,  # Fluid density [kg/m3]
        mu_f=3.5E-3,  # Fluid dynamic viscosity [Pa.s]
        dx_f_id=1,  # ID of marker in the fluid domain
        # mesh lifting parameters (see turtleFSI for options)
        extrapolation="laplace",
        extrapolation_sub_type="constant",
        # Solid parameters
        rho_s=1.0E3,  # Solid density [kg/m3]
        mu_s=mu_s_val,  # Solid shear modulus or 2nd Lame Coef. [Pa]
        nu_s=nu_s_val,  # Solid Poisson ratio [-]
        lambda_s=lambda_s_val,  # Solid Young's modulus [Pa]
        dx_s_id=2,  # ID of marker in the solid domain
        k_s=[1E5],
        c_s=[10],
        ds_s_id=[33],
        # FSI parameters
        fsi_region=[0.123, 0.134, 0.063, 0.004],  # x, y, and z coordinate of FSI region center,
                                                  # and radius of FSI region sphere
        # Simulation parameters
        folder="aneurysm_results",  # Folder name generated for the simulation
        mesh_path="mesh/file_aneurysm.h5",
        FC_file="FC_MCA_10",  # File name containing the fourier coefficients for the flow waveform
        P_FC_File="FC_Pressure",  # File name containing the fourier coefficients for the pressure waveform
        compiler_parameters=_compiler_parameters,  # Update the defaul values of the compiler arguments (FEniCS)
        save_deg=2,  # Degree of the functions saved for visualisation
        scale_probe=True,  # Scale the probe points to meters
        solid_properties={"dx_s_id":2,"material_model":"MooneyRivlin","rho_s":1.0E3,"mu_s":mu_s_val,"lambda_s":lambda_s_val,"C01":0.02e6,"C10":0.0,"C11":1.8e6},
    ))

    return default_variables


def get_mesh_domain_and_boundaries(mesh_path, inlet_outlet_s_id, **namespace):

    # Read mesh
    mesh = Mesh()
    hdf = HDF5File(mesh.mpi_comm(), mesh_path, "r")
    hdf.read(mesh, "/mesh", False)
    boundaries = MeshFunction("size_t", mesh, 2)
    hdf.read(boundaries, "/boundaries")
    domains = MeshFunction("size_t", mesh, 3)
    hdf.read(domains, "/domains")

     # Only consider FSI in domain within this sphere
    sph_x = 0.13041167578008384
    sph_y = 0.12452007418678859
    sph_z = 0.07041177980223849
    sph_rad = 0.0030475867789993712

    i = 0
    for submesh_facet in facets(mesh):
        idx_facet = boundaries.array()[i]
        if idx_facet == inlet_outlet_s_id:
            mid = submesh_facet.midpoint()
            dist_sph_center = np.sqrt((mid.x() - sph_x) ** 2 + (mid.y() - sph_y) ** 2 + (mid.z() - sph_z) ** 2)
            if dist_sph_center < sph_rad:
                boundaries.array()[i] = 44  # changed "fsi" idx to "rigid wall" idx
        i += 1

    sph_x = 0.1186985091521019
    sph_y = 0.14507860743227508
    sph_z = 0.06475670585218873
    sph_rad = 0.0030475867789993712

    i = 0
    for submesh_facet in facets(mesh):
        idx_facet = boundaries.array()[i]
        if idx_facet == inlet_outlet_s_id:
            mid = submesh_facet.midpoint()
            dist_sph_center = np.sqrt((mid.x() - sph_x) ** 2 + (mid.y() - sph_y) ** 2 + (mid.z() - sph_z) ** 2)
            if dist_sph_center < sph_rad:
                boundaries.array()[i] = 44  # changed "fsi" idx to "rigid wall" idx
        i += 1

    # File("boundaries_attempt_2.pvd") << boundaries
    # exit()

    return mesh, domains, boundaries


class InnerP(UserExpression):
    def __init__(self, t, t_start, t_ramp, An, Bn, period, P_mean, **kwargs):
        self.t = t
        self.t_start = t_start
        self.t_ramp = t_ramp
        self.An = An
        self.Bn = Bn
        self.omega = (2.0 * np.pi / period)
        self.P_mean = P_mean
        self.p_0 = 0.0  # Initial pressure
        self.P = self.p_0  # Apply initial pressure to inner pressure variable
        super().__init__(**kwargs)

    def update(self, t):
        self.t = t
        # apply a sigmoid ramp to the pressure
        if self.t < self.t_start:
            ramp_factor = 0.0
        elif self.t < self.t_ramp and self.t >= self.t_start:
            ramp_factor = -0.5 * np.cos(np.pi * (self.t - self.t_start) / (self.t_ramp - self.t_start)) + 0.5
        else:
            ramp_factor = 1.0
        if MPI.rank(MPI.comm_world) == 0:
            print("ramp_factor = {} m^3/s".format(ramp_factor))

        # Caclulate Pn (normalized pressure)from Fourier Coefficients
        Pn = 0 + 0j
        for i in range(len(self.An)):
            Pn = Pn + (self.An[i] - self.Bn[i] * 1j) * np.exp(1j * i * self.omega * self.t)
        Pn = abs(Pn)

        # Multiply by mean pressure and ramp factor
        self.P = ramp_factor * Pn * self.P_mean
        if MPI.rank(MPI.comm_world) == 0:
            print("P = {} Pa".format(self.P))

    def eval(self, value, x):
        value[0] = self.P

    def value_shape(self):
        return ()


def create_bcs(t, DVP, mesh, boundaries, mu_f, F_fluid_nonlinear,
               fsi_id, inlet_id, inlet_outlet_s_id,
               rigid_id, psi, F_solid_linear, p_deg, FC_file,
               Q_mean, P_FC_File, P_mean, T_Cycle, **namespace):

    # Load fourier coefficients for the velocity and scale by flow rate
    An, Bn = np.loadtxt(os.path.join(os.path.dirname(os.path.abspath(__file__)), FC_file)).T
    # Convert to complex fourier coefficients
    Cn = (An - Bn * 1j) * Q_mean
    _, tmp_center, tmp_radius, tmp_normal = compute_boundary_geometry_acrn(mesh, inlet_id, boundaries)

    # Create Womersley boundary condition at inlet
    tmp_element = DVP.sub(1).sub(0).ufl_element()
    inlet = make_womersley_bcs(T_Cycle, None, mu_f, tmp_center, tmp_radius, tmp_normal, tmp_element, Cn=Cn)
    # Initialize inlet expressions with initial time
    for uc in inlet:
        uc.set_t(t)

    # Create Boundary conditions for the velocity
    u_inlet = [DirichletBC(DVP.sub(1).sub(i), inlet[i], boundaries, inlet_id) for i in range(3)]
    u_inlet_s = DirichletBC(DVP.sub(1), ((0.0, 0.0, 0.0)), boundaries, inlet_outlet_s_id)

    # Solid Displacement BCs
    d_inlet = DirichletBC(DVP.sub(0), (0.0, 0.0, 0.0), boundaries, inlet_id)
    d_inlet_s = DirichletBC(DVP.sub(0), (0.0, 0.0, 0.0), boundaries, inlet_outlet_s_id)

    # Assemble boundary conditions
    bcs = u_inlet + [u_inlet_s, d_inlet, d_inlet_s]

    # Load Fourier coefficients for the pressure and scale by flow rate
    An_P, Bn_P = np.loadtxt(os.path.join(os.path.dirname(os.path.abspath(__file__)), P_FC_File)).T

    # Apply pulsatile pressure at the fsi interface by modifying the variational form
    n = FacetNormal(mesh)
    # dSS = Measure("dS", domain=mesh, subdomain_data=boundaries)
    p_out_bc_val = InnerP(t=0.0, t_start=0.2, t_ramp=0.4, An=An_P, Bn=Bn_P, period=T_Cycle, P_mean=P_mean, degree=p_deg)
    # F_solid_linear += p_out_bc_val * inner(n('+'), psi('+')) * dSS(fsi_id)

    dso1 = ds(2, domain=mesh, subdomain_data=boundaries) # Outlet surface
    dso2 = ds(4, domain=mesh, subdomain_data=boundaries) # Outlet surface

    F_fluid_nonlinear += p_out_bc_val * inner(n, psi)*dso1
    F_fluid_nonlinear += p_out_bc_val * inner(n, psi)*dso2

    # Create inlet subdomain for computing the flow rate inside post_solve
    dsi = ds(inlet_id, domain=mesh, subdomain_data=boundaries)
    inlet_area = assemble(1.0 * dsi)
    return dict(bcs=bcs, inlet=inlet, p_out_bc_val=p_out_bc_val, F_fluid_nonlinear=F_fluid_nonlinear, n=n, dsi=dsi,
                inlet_area=inlet_area)


def initiate(mesh_path, scale_probe, mesh, v_deg, p_deg, **namespace):

    probe_points = load_probe_points(mesh_path)
    # In case the probe points are in mm, scale them to meters
    if scale_probe:
        probe_points = probe_points * 0.001

    Vv = VectorFunctionSpace(mesh, "CG", v_deg)
    V = FunctionSpace(mesh, "CG", p_deg)
    d_mean = Function(Vv)
    u_mean = Function(Vv)
    p_mean = Function(V)

    return dict(probe_points=probe_points, d_mean=d_mean, u_mean=u_mean, p_mean=p_mean)


def pre_solve(t, inlet, p_out_bc_val, **namespace):
    for uc in inlet:
        # Update the time variable used for the inlet boundary condition
        uc.set_t(t)

        # Multiply by cosine function to ramp up smoothly over time interval 0-250 ms
        if t < 0.25:
            uc.scale_value = -0.5 * np.cos(np.pi * t / 0.25) + 0.5
        else:
            uc.scale_value = 1.0

    # Update pressure condition
    p_out_bc_val.update(t)

    return dict(inlet=inlet, p_out_bc_val=p_out_bc_val)


def post_solve(dvp_, n, dsi, dt, mesh, inlet_area, mu_f, rho_f, probe_points, t,
               save_solution_after_tstep, d_mean, u_mean, p_mean, **namespace):
    d = dvp_["n"].sub(0, deepcopy=True)
    v = dvp_["n"].sub(1, deepcopy=True)
    p = dvp_["n"].sub(2, deepcopy=True)

    print_probe_points(v, p, probe_points)
    calculate_and_print_flow_properties(dt, mesh, v, inlet_area, mu_f, rho_f, n, dsi)

    if t >= save_solution_after_tstep * dt:
        # Here, we accumulate the velocity filed in u_mean
        d_mean.vector().axpy(1, d.vector())
        u_mean.vector().axpy(1, v.vector())
        p_mean.vector().axpy(1, p.vector())
        return dict(u_mean=u_mean, d_mean=d_mean, p_mean=p_mean)
    else:
        return None


def finished(d_mean, u_mean, p_mean, visualization_folder, save_solution_after_tstep, T, dt, **namespace):
    # Divide the accumulated vectors by the number of time steps
    num_steps = T / dt - save_solution_after_tstep + 1
    for data in [d_mean, u_mean, p_mean]:
        data.vector()[:] = data.vector()[:] / num_steps

    # Save u_mean as a XDMF file using the checkpoint
    data_names = [
        (d_mean, "d_mean.xdmf"),
        (u_mean, "u_mean.xdmf"),
        (p_mean, "p_mean.xdmf")
    ]

    for vector, data_name in data_names:
        file_path = os.path.join(visualization_folder, data_name)
        with XDMFFile(MPI.comm_world, file_path) as f:
            f.write_checkpoint(vector, data_name, 0, XDMFFile.Encoding.HDF5)
