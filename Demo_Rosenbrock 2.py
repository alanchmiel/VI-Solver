import time
import itertools
import numpy as np

from itertools import cycle
import matplotlib.pyplot as plt
from mpl_toolkits.mplot3d import Axes3D
from matplotlib import cm

from VISolver.Domains.Rosenbrock import Rosenbrock

from VISolver.Solvers.Euler import Euler
from VISolver.Solvers.HeunEuler_PhaseSpace import HeunEuler_PhaseSpace
# from VISolver.Solvers.HeunEuler_AdaGrad_PhaseSpace import \
#     HeunEuler_AdaGrad_PhaseSpace

from VISolver.Solver import Solve
from VISolver.Options import (
    DescentOptions, Miscellaneous, Reporting, Termination, Initialization)
from VISolver.Log import PrintSimResults, PrintSimStats


def Demo():

    # __ROSENBROCK__############################################################
    # __STEEPEST_DESCENT__######################################################

    # Define Domain
    Domain = Rosenbrock(Dim=2)

    # Set Method
    # Method = Euler(Domain=Domain,FixStep=True)
    Method = HeunEuler_PhaseSpace(Domain=Domain,Delta0=1e-3,MinStep=-1e-2,MaxStep=0.,DimWise=True)
    # Method = HeunEuler_PhaseSpace(Domain=Domain,Delta0=1e-1,DimWise=False)
    # Method = HeunEuler_AdaGrad_PhaseSpace(Domain=Domain,Delta0=1e-1)

    # Set Options
    Term = Termination(MaxIter=20000,Tols=[(Domain.f_Error,1e-6)])
    Repo = Reporting(Requests=[Domain.f_Error, 'Step', 'F Evaluations',
                               'Projections','Data'])
    Misc = Miscellaneous()

    # Set starting point and step size ranges
    r = 2
    rads = np.linspace(0,2*np.pi,num=4,endpoint=False)
    steps = -np.logspace(-5,-3,num=3,endpoint=True)
    # steps = -np.logspace(-8,-6,num=3,endpoint=True)

    # Construct figure
    fig = plt.figure()
    ax = fig.add_subplot(111, projection='3d')
    ax.view_init(azim=-160.)
    X = np.arange(-1.5, 3.5, 0.25)
    Y = np.arange(-1.5, 3.5, 0.25)
    X, Y = np.meshgrid(X, Y)
    Z = np.zeros_like(X)
    for i in range(Z.shape[0]):
        for j in range(Z.shape[1]):
            Z[i,j] = Domain.f(np.array([X[i,j],Y[i,j]]))
    ax.plot_surface(X,Y,Z,rstride=1,cstride=1,cmap=cm.coolwarm,
                    linewidth=0,antialiased=False)
    ax.set_xlim3d(np.min(X),np.max(X))
    ax.set_ylim3d(np.min(Y),np.max(Y))
    ax.set_zlim3d(np.min(Z),np.max(Z))
    ax.set_xlabel('X axis')
    ax.set_ylabel('Y axis')
    ax.zaxis.set_rotate_label(False)  # disable automatic rotation
    ax.set_zlabel('f(X,Y)',rotation=90)
    ax.text2D(0.05, 0.95, 'Steepest Descent on the\nRosenbrock Function',
              transform=ax.transAxes)
    lw = cycle(range(2*len(steps),0,-2))
    plt.ion()
    plt.show()

    # Compute trajectories
    for rad, step in itertools.product(rads,steps):

        # Initialize Starting Point
        assert Domain.Dim == 2
        Start = Domain.ArgMin + r*np.asarray([np.cos(rad),np.sin(rad)])

        # Set Options
        Init = Initialization(Step=step)
        Options = DescentOptions(Init,Term,Repo,Misc)

        # Print Stats
        PrintSimStats(Domain,Method,Options)

        # Start Solver
        tic = time.time()
        Rosenbrock_Results = Solve(Start,Method,Domain,Options)
        toc = time.time() - tic

        # Print Results
        PrintSimResults(Options,Rosenbrock_Results,Method,toc)

        # Plot Results
        data_SD = Rosenbrock_Results.PermStorage['Data']
        res_SD = np.asarray(Rosenbrock_Results.PermStorage[Domain.f_Error])
        res_SD[np.isnan(res_SD)] = np.inf
        trajX = []
        trajY = []
        trajZ = []
        for i in range(len(data_SD)):
            trajX.append(data_SD[i][0])
            trajY.append(data_SD[i][1])
            trajZ.append(res_SD[i])
        ax.plot(trajX,trajY,trajZ,lw=next(lw))
        plt.draw()
    plt.ioff()
    plt.show()

    # __NEWTONS_METHOD____######################################################

    # Define Domain
    Domain = Rosenbrock(Dim=2,Newton=True)

    # Set Method
    Method = Euler(Domain=Domain,FixStep=True)

    # Set Options
    Term = Termination(MaxIter=20000,Tols=[(Domain.f_Error,1e-6)])
    Repo = Reporting(Requests=[Domain.f_Error, 'Step', 'F Evaluations',
                               'Projections','Data'])
    Misc = Miscellaneous()
    Init = Initialization(Step=-1e-3)
    Options = DescentOptions(Init,Term,Repo,Misc)

    # Print Stats
    PrintSimStats(Domain,Method,Options)

    # Start Solver
    tic = time.time()
    Rosenbrock_Results = Solve(Start,Method,Domain,Options)  # Use same Start
    toc = time.time() - tic

    # Print Results
    PrintSimResults(Options,Rosenbrock_Results,Method,toc)

    # Plot Results
    data_N = Rosenbrock_Results.PermStorage['Data']
    res_N = np.asarray(Rosenbrock_Results.PermStorage[Domain.f_Error])
    fig = plt.figure()
    ax = fig.add_subplot(111)
    ax.plot(res_N,label='Newton''s Method')
    ax.plot(res_SD,label='Steepest Descent')
    ax.set_yscale('log')
    ax.set_xlabel('Iterations (k)')
    ax.set_ylabel('f(X,Y) [log-scale]')
    ax.set_title('Rosenbrock Test: Newton''s Method vs Steepest Descent')
    ax.legend()
    plt.show()

    fig = plt.figure()
    ax = fig.add_subplot(111)
    diff_N = [np.linalg.norm(d-Domain.ArgMin) for d in data_N]
    diff_SD = [np.linalg.norm(d-Domain.ArgMin) for d in data_SD]
    ax.plot(diff_N,label='Newton''s Method')
    ax.plot(diff_SD,label='Steepest Descent')
    ax.set_yscale('log')
    ax.set_xlabel('Iterations (k)')
    ax.set_ylabel(r'$||x-x^*||$ [log-scale]')
    ax.set_title('Rosenbrock Test: Newton''s Method vs Steepest Descent')
    ax.legend()
    plt.show()


if __name__ == '__main__':
    Demo()
