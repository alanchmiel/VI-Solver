import time
import numpy as np

from VISolver.Domains.CloudServices2 import (
    CloudServices, CreateRandomNetwork, CreateNetworkExample)

# from VISolver.Solvers.Euler_LEGS import Euler_LEGS
from VISolver.Solvers.HeunEuler_LEGS import HeunEuler_LEGS
# from VISolver.Solvers.AdamsBashforthEuler_LEGS import ABEuler_LEGS
# from VISolver.Solvers.CashKarp_LEGS import CashKarp_LEGS

from VISolver.Projection import BoxProjection
from VISolver.Solver import Solve
from VISolver.Options import (
    DescentOptions, Miscellaneous, Reporting, Termination, Initialization)
from VISolver.Log import PrintSimResults, PrintSimStats

from VISolver.Utilities import ListONP2NP

from mpl_toolkits.mplot3d import Axes3D
from matplotlib import cm
from matplotlib.ticker import LinearLocator, FormatStrFormatter
from matplotlib import pyplot as plt

from IPython import embed


def Demo():

    #__CLOUD_SERVICES__##################################################

    # Define Network and Domain
    Network = CreateRandomNetwork(5,4,seed=0)
    Network = CreateNetworkExample(ex=5)
    Domain = CloudServices(Network=Network,gap_alpha=2)

    # Set Method
    eps = 1e-2
    # Method = Euler_LEGS(Domain=Domain,P=BoxProjection(lo=eps))
    Method = HeunEuler_LEGS(Domain=Domain,P=BoxProjection(lo=eps),Delta0=1e0)
    # Method = ABEuler_LEGS(Domain=Domain,P=BoxProjection(lo=eps),Delta0=1e-1)
    # Method = CashKarp_LEGS(Domain=Domain,P=BoxProjection(lo=eps),Delta0=1e0)

    # Initialize Starting Point
    Start = np.ones(Domain.Dim)
    # Start[4] = .7
    # Start[9] = 1.
    # Start = np.array([ 0.5,  4.5,  2.1,  4.5,  4.5,  2.9,  0.5,  2.9,  0.5,  1.3])
    # Start = np.array([ 2.1,  4.5,  1.3,  1.3,  2.1,  3.7,  1.3,  2.1,  3.7,  1.3])
    # Start = np.array([ 0.5,  4.5,  2.1,  4.5,  3.7,  2.9,  0.5,  2.9,  0.5,  2.1])
    # Start = np.array([ 0.5,  2.9,  1.1,  0.5,  2.3,  2.3,  3.5,  1.1,  3.5,  1.7])
    # Start = np.array([ 2.9,  2.9,  2.9,  0.5,  1.7,  0.5,  3.5,  2.9,  3.5,  3.5])

    # Calculate Initial Gap
    gap_0 = Domain.gap_rplus(Start)
    print(Domain.CloudProfits(Start))
    print(Domain.dCloudProfits(Start))

    # Set Options
    Init = Initialization(Step=-1e-3)
    # Init = Initialization(Step=-0.00001)
    Term = Termination(MaxIter=1e5,Tols=[(Domain.gap_rplus,1e-12*gap_0)])
                                         # (Domain.valid,False)])
    Repo = Reporting(Requests=[Domain.gap_rplus,'Step','F Evaluations',
                               'Projections','Data',Domain.eig_stats,
                               'Lyapunov'])
    # Repo = Reporting()
    Misc = Miscellaneous()
    Options = DescentOptions(Init,Term,Repo,Misc)

    # Print Stats
    PrintSimStats(Domain,Method,Options)

    # Start Solver
    tic = time.time()
    CloudServices_Results = Solve(Start,Method,Domain,Options)
    toc = time.time() - tic

    # Print Results
    PrintSimResults(Options,CloudServices_Results,Method,toc)

    x = CloudServices_Results.PermStorage['Data'][-1]
    print('[p...q]')
    print(x)
    print('Qj')
    print(Domain.Demand(x)[0])
    print('Profits')
    print(Domain.CloudProfits(x))
    print('[dpj...dqj')
    print(Domain.dCloudProfits(x))
    print('Qij')
    print(Domain.Demand_IJ(x)[0])

    t = np.abs(np.cumsum(CloudServices_Results.PermStorage['Step']))
    data = CloudServices_Results.PermStorage['Data']
    data = ListONP2NP(data)
    LE = CloudServices_Results.PermStorage['Lyapunov']

    print(Domain.Nash(x))

    # p = np.arange(0.01,20,.1)
    # f = (10.*np.exp(-(p**2./(p+2.))**2.)+np.exp(-(1./10.*p**2./(p+2.))**2.))*(p-1.)
    # fig = plt.figure()
    # fig.suptitle('Profit Non-Convex in Price',fontsize=18)
    # ax = fig.add_subplot(111)
    # ax.plot(p,f,'k',lw=2)
    # ax.set_xlim([0,20])
    # ax.set_ylim([-2,6])
    # plt.xlabel('$p_1$',fontsize=14)
    # plt.ylabel('$\pi_1$',fontsize=14)
    # plt.savefig('NonConvex.png',bbox_inches='tight')

    # fig = plt.figure()
    # # fig.set_size_inches([8,8])
    # title = '5-Cloud, 4-Client Market Opens at ' + \
    #     r'$(p_i=d_i=1 \,\, \forall i)$'
    # fig.suptitle(title,fontsize=18)
    # ax1 = fig.add_subplot(111)
    # l = ax1.plot(t,[-le for le in LE])
    # ax1.set_yscale('log')
    # ax1.invert_yaxis()
    # ax1.set_title('Convergence of characteristic Lyapunov exponent')
    # ax1.set_xlim([0,5.5])
    # mn = min(LE[-1])
    # tk = 50  # -mn/5.//10*10
    # # ax1.set_ylim([(mn//10)*10-tk,2*tk])
    # props = dict(boxstyle='round', facecolor='wheat', alpha=0.5)
    # Lambda_p = ','.join('%.1f' % lam for lam in LE[-1][:Domain.nClouds])
    # Lambda_d = ','.join('%.1f' % lam for lam in LE[-1][Domain.nClouds:])
    # textstr = '$\Lambda=[$'+Lambda_p+','+Lambda_d+'$]$'
    # ax1.text(0.0145, 0.9, textstr, transform=ax1.transAxes, fontsize=14,
    #          va='center', bbox=props)
    # # ax2.legend(l,labels,bbox_to_anchor=(1.05, .5),
    # #            loc='lower left', borderaxespad=0.,
    # #            fancybox=True)
    # # plt.savefig('Scenario1.png',bbox_inches='tight')
    # # plt.clf()
    # plt.show()

    # fig = plt.figure()
    # fig.set_size_inches([8,8])
    # title = '5-Cloud, 4-Client Market Opens at ' + \
    #     r'$(p_i=d_i=1 \,\, \forall i)$'
    # fig.suptitle(title,fontsize=18)
    # ax1 = fig.add_subplot(211)
    # l = ax1.plot(t,data)
    # ax1.set_title('Convergence of market to Nash equilibrium')
    # ax1.set_xlim([0,5.5])
    # labels = ['$p_'+repr(i+1)+'$'for i in xrange(Domain.nClouds)] + \
    #     ['$d_'+repr(i+1)+'$'for i in xrange(Domain.nClouds)]
    # ax1.legend(l,labels,bbox_to_anchor=(1.05, -.075),
    #            loc='lower left', borderaxespad=0.,
    #            fancybox=True)
    # ax2 = fig.add_subplot(212)
    # l = ax2.plot(t,[-le for le in LE])
    # ax2.set_title('Convergence of characteristic Lyapunov exponent')
    # ax2.set_xlim([0,5.5])
    # mn = min(LE[-1])
    # tk = 50  # -mn/5.//10*10
    # ax2.set_ylim([(mn//10)*10-tk,2*tk])
    # props = dict(boxstyle='round', facecolor='wheat', alpha=0.5)
    # Lambda_p = ','.join('%.1f' % lam for lam in LE[-1][:Domain.nClouds])
    # Lambda_d = ','.join('%.1f' % lam for lam in LE[-1][Domain.nClouds:])
    # textstr = '$\Lambda=[$'+Lambda_p+','+Lambda_d+'$]$'
    # ax2.text(0.0145, 0.9, textstr, transform=ax2.transAxes, fontsize=14,
    #          va='center', bbox=props)
    # # ax2.legend(l,labels,bbox_to_anchor=(1.05, .5),
    # #            loc='lower left', borderaxespad=0.,
    # #            fancybox=True)
    # # plt.savefig('Scenario1.png',bbox_inches='tight')
    # # plt.clf()
    # plt.show()

    # for i in xrange(data.shape[1]/2):
    #     plt.plot(data[:,i],data[:,i+data.shape[1]/2])
    # plt.show()

    # gaps = CloudServices_Results.PermStorage[Domain.gap_rplus]
    # gaps = ListONP2NP(gaps)
    # plt.plot(gaps)
    # plt.show()

    # X = np.arange(.1,5,0.01)
    # Y = np.arange(.1,5,0.01)
    # X, Y = np.meshgrid(X,Y)
    # Z = np.zeros_like(X)
    # for i in xrange(X.shape[0]):
    #     for j in xrange(Y.shape[0]):
    #         pJ = np.sum(x[:Domain.nClouds])-x[0]
    #         qJ = np.sum(x[Domain.nClouds:])-x[Domain.nClouds]
    #         pi = X[i,j]
    #         qi = Y[i,j]
    #         xi = np.array([pi,qi])
    #         Z[i,j] = Domain.CloudProfit(0,xi,pJ,qJ)
    # fig = plt.figure()
    # ax = fig.gca(projection='3d')
    # surf = ax.plot_surface(X,Y,Z,rstride=1,cstride=1,
    #                        cmap=cm.coolwarm,linewidth=0,
    #                        antialiased=False)
    # ax.set_zlim(0,35)
    # ax.zaxis.set_major_locator(LinearLocator(10))
    # ax.zaxis.set_major_formatter(FormatStrFormatter('%.02f'))
    # fig.colorbar(surf, shrink=0.5, aspect=5)
    # plt.show()

    # Domain2 = CloudServices(Network=Network,poly_splice=False)

    # i = 0
    # j = 3
    # pi = np.arange(0,.8,.001)
    # pJ = .01
    # qi = qJ = 1
    # Q00 = np.zeros_like(pi)
    # Q200 = Q00.copy()
    # t = np.zeros_like(pi)
    # for p in xrange(len(pi)):
    #     Qoo, too = Domain.Demand_ij(i,j,pi[p],qi,pJ,qJ)
    #     Q2oo, t2oo = Domain2.Demand_ij(i,j,pi[p],qi,pJ,qJ)
    #     Q00[p] = Qoo
    #     Q200[p] = Q2oo
    #     t[p] = too
    # e = pi[np.argmax(t >= 1/np.sqrt(2))]
    # Qe = Q00[np.argmax(t >= 1/np.sqrt(2))]/12.
    # p0 = pi[np.argmax(t >= Domain.t0)]
    # Qp0 = Q00[np.argmax(t >= Domain.t0)]/12.
    # pf = pi[np.argmax(t >= Domain.tf)]
    # Qpf = Q00[np.argmax(t >= Domain.tf)]/12.
    # fig = plt.figure()
    # ax = fig.add_subplot(111)
    # Qij, = ax.plot(pi,Q00/12.,'k-', linewidth=5)
    # exp, = ax.plot(pi,Q200/12.,'k--', linewidth=5)
    # ax.plot(p0,Qp0,'ow',markersize=10)
    # ax.plot(pf,Qpf,'ow',markersize=10)
    # eps = .05
    # ax.plot([-eps,.8+eps],[0,0],'k-.')
    # ax.plot([0,0],[-eps,1+eps],'k-.')
    # # ax.plot([e,e],[0,1])
    # # ax.plot([p0,p0],[0,1])
    # # ax.plot([pf,pf],[0,1])
    # ax.annotate('inelastic', xy=(.04, .97), xycoords='data',
    #             xytext=(.1, .7), textcoords='data',
    #             arrowprops=dict(arrowstyle='simple',facecolor='black'),
    #             # arrowprops=dict(frac=0.1,headwidth=10,width=4,facecolor='black',shrink=.05),
    #             ha='center', va='center', size=18,
    #             )
    # ax.annotate('elastic', xy=(e, Qe), xycoords='data',
    #             xytext=(e+.2, Qe+.2), textcoords='data',
    #             # arrowprops=dict(arrowstyle="simple", facecolor='black'),
    #             arrowprops=dict(frac=0.1,headwidth=10,width=4,facecolor='black',shrink=.1),
    #             ha='center', va='center', size=18,
    #             )
    # ax.annotate('splice', xy=(p0, Qp0), xycoords='data',
    #             xytext=(p0+.2, Qp0+.2), textcoords='data',
    #             # arrowprops=dict(arrowstyle="simple", facecolor='black'),
    #             arrowprops=dict(frac=0.1,headwidth=10,width=4,facecolor='black',shrink=.1),
    #             ha='center', va='center', size=18,
    #             )
    # ax.annotate('zero-cutoff', xy=(pf, Qpf+.02), xycoords='data',
    #             xytext=(pf, Qpf+.2*np.sqrt(2)), textcoords='data',
    #             # arrowprops=dict(arrowstyle="simple", facecolor='black'),
    #             arrowprops=dict(frac=0.1,headwidth=10,width=4,facecolor='black',shrink=.1),
    #             ha='center', va='center', size=18,
    #             )
    # ax.set_xlim(-eps,.8+eps)
    # ax.set_ylim(-eps,1+eps)
    # leg = plt.legend([Qij,exp], [r'$Q_{ij}^{}$', r'$H_{i}e^{-t_{ij}^2}$'], fontsize=20,
    #     fancybox=True)
    # plt.setp(leg.get_texts()[0], fontsize='20', va='center')
    # plt.setp(leg.get_texts()[1], fontsize='20', va='bottom')
    # plt.axis('off')
    # # plt.show()
    # plt.savefig("Demand.png",bbox_inches='tight')

    # embed()

if __name__ == '__main__':
    Demo()
