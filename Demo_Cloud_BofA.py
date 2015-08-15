# import time
import numpy as np

from VISolver.Domains.CloudServices import (
    CloudServices, CreateNetworkExample)

# from VISolver.Solvers.Euler_LEGS import Euler_LEGS
# from VISolver.Solvers.HeunEuler_LEGS import HeunEuler_LEGS
from VISolver.Solvers.AdamsBashforthEuler_LEGS import ABEuler_LEGS
# from VISolver.Solvers.CashKarp_LEGS import CashKarp_LEGS

from VISolver.Projection import BoxProjection
from VISolver.Solver import Solve
from VISolver.Options import (
    DescentOptions, Miscellaneous, Reporting, Termination, Initialization)
from VISolver.Log import PrintSimStats

from VISolver.Utilities import ListONP2NP, aug_grid, MCLE_BofA_ID_par2

from matplotlib import pyplot as plt
from IPython import embed

from sklearn.svm import SVC


def Demo():

    #__CLOUD_SERVICES__##################################################

    # Define Network and Domain
    Network = CreateNetworkExample(ex=2)
    Domain = CloudServices(Network=Network,gap_alpha=2)

    # Set Method
    eps = 1e-2
    # Method = Euler_LEGS(Domain=Domain,P=BoxProjection(lo=eps))
    # Method = HeunEuler_LEGS(Domain=Domain,P=BoxProjection(lo=eps),Delta0=1e-1)
    Method = ABEuler_LEGS(Domain=Domain,P=BoxProjection(lo=eps),Delta0=1e-1)
    # Method = CashKarp_LEGS(Domain=Domain,P=BoxProjection(lo=eps),Delta0=1e-6)

    # Set Options
    Init = Initialization(Step=1e-5)
    Term = Termination(MaxIter=1e5)  # ,Tols=[(Domain.valid,False)])
    Repo = Reporting(Requests=['Data','Step'])
    Misc = Miscellaneous()
    Options = DescentOptions(Init,Term,Repo,Misc)
    args = (Method,Domain,Options)
    sim = Solve

    # Print Stats
    PrintSimStats(Domain,Method,Options)

    grid = [np.array([.5,4.5,6])]*Domain.Dim
    grid = ListONP2NP(grid)
    grid = aug_grid(grid)
    Dinv = np.diag(1./grid[:,3])

    results = MCLE_BofA_ID_par2(sim,args,grid,nodes=8,limit=50,AVG=.01,
                                eta_1=1.2,eta_2=.95,eps=1.,
                                L=8,q=2,r=1.1,Dinv=Dinv)
    ref, data, p, i, avg, bndry_ids = results

    # plt.figure()
    # obs = (0,1)
    # c = plt.cm.hsv(np.random.rand(len(ref)))
    # for cat,lam in enumerate(ref):

    #     samples = data[hash(str(lam))]
    #     n = len(samples)
    #     X = np.empty((len(samples)*2,len(samples[0][0])))
    #     for idx,sample in enumerate(samples):
    #         X[idx] = sample[0]
    #         X[idx+len(samples)] = sample[1]
    #     Y = np.zeros(len(samples)*2)
    #     Y[:n] = 1

    #     clf = SVC()
    #     clf.fit(X,Y)

    #     xx, yy = np.meshgrid(np.linspace(grid[obs[0],0],grid[obs[0],1],500),
    #                          np.linspace(grid[obs[1],0],grid[obs[1],1],500))
    #     padding = np.ones(len(xx.ravel()))
    #     test = ()
    #     for i in xrange(Domain.Dim):
    #         if i == obs[0]:
    #             test += (xx.ravel(),)
    #         elif i == obs[1]:
    #             test += (yy.ravel(),)
    #         else:
    #             test += (padding,)
    #     test = np.vstack(test).T
    #     # test = np.vstack((xx.ravel(),yy.ravel())+(padding,)*(Domain.Dim-2)).T
    #     Z = clf.decision_function(test)
    #     Z = Z.reshape(xx.shape)
    #     Zma = np.ma.masked_where(Z < 0,Z)

    #     plt.imshow(Zma, interpolation='nearest',
    #                extent=(xx.min(), xx.max(), yy.min(), yy.max()),
    #                aspect='auto', origin='lower', cmap='bone_r', zorder=0)
    #     plt.contour(xx, yy, Z, colors='k', levels=[0], linewidths=2,
    #                 linetypes='-.', zorder=1)
    #     plt.scatter(X[:n, obs[0]], X[:n, obs[1]], s=30, c=c[cat], zorder=2)

    # # plt.xticks(())
    # # plt.yticks(())
    # ax = plt.gca()
    # ax.set_xlim([grid[obs[0],0],grid[obs[0],1]])
    # ax.set_ylim([grid[obs[1],0],grid[obs[1],1]])
    # ax.set_aspect('equal')
    # plt.savefig('bndry_pts.png',format='png')

    # plt.figure()
    # pmap = np.swapaxes(np.reshape(p,tuple(grid[:,2])),0,1)
    # plt.imshow(pmap,'jet',origin='lower')
    # plt.gca().set_aspect('equal')

    # plt.show()

    embed()

if __name__ == '__main__':
    Demo()
