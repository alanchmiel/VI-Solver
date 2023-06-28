from __future__ import division
import numpy as np
import pathos.multiprocessing as mp  # https://github.com/uqfoundation/pathos

from VISolver.BoA.Utilities import (
    int2ind,ind2pt,ind2int,pt2inds,neighbors,
    update_LERef,adjustLEs2Ref,update_Prob_Data)


def LE(x):
    # Unpack input - can't use *x with pool.map
    center_ind,sim,args,grid,shape,eps,q,r,Dinv = x

    # Select neighbors
    selected, _ = neighbors(center_ind,grid,r,q,Dinv)

    # Convert indices to ids and pts
    group_inds = [center_ind] + selected
    group_ids = [ind2int(ind,shape) for ind in group_inds]
    group_pts = [ind2pt(ind,grid,checkBnds=True) for ind in group_inds]

    # Max distance of any point to a grid vertex
    ddiag = np.linalg.norm(grid[:,3])

    # Compute LEs and record endpoints
    les = []
    endpts = []
    bnd_ind_sum = {}
    for start in group_pts:
        # Run simulation
        results = sim(start,*args)
        # Record results
        endpts += [results.TempStorage['Data'][-1]]
        le = results.TempStorage['Lyapunov'][-1]
        les += [le]

        # Record fastest evolving component of LE and record time series
        c = np.max(np.abs(le))
        t = np.cumsum([0]+results.PermStorage['Step'][:-1])
        T = t[-1]

        # Determine cube surrounding starting point
        pt0 = results.PermStorage['Data'][0]
        cube_inds = pt2inds(pt0,grid)
        cube_pts = np.array([ind2pt(ind,grid) for ind in cube_inds])

        # Iterate through trajectory and compute probability decay
        for k, pt in enumerate(results.PermStorage['Data']):
            # Record current time, time step, and distance from cube corners
            tk = t[k]
            dt = results.PermStorage['Step'][k]
            ds = np.linalg.norm(pt-cube_pts,axis=1)

            # Update surrounding cube if point has crossed cube boundary
            if any(ds > ddiag):
                cube_inds = pt2inds(pt,grid)
                cube_pts = np.array([ind2pt(ind,grid) for ind in cube_inds])
                ds = np.linalg.norm(pt-cube_pts,axis=1)

            # Determine if cube lies within specified BoA monitoring zone
            inbnds = np.all(np.logical_and(cube_pts >= grid[:,0],
                                           cube_pts <= grid[:,1]),
                            axis=1)

            # Record weighted decays (numerator) and weights (denominator) for
            # each associated cube corner (grid point)
            for idx, cube_ind in enumerate(cube_inds):
                if inbnds[idx]:
                    if not (cube_ind in bnd_ind_sum):
                        bnd_ind_sum[cube_ind] = [0,0]
                    bnd_ind_sum[cube_ind][0] += np.exp(-c*tk/T)*dt  # heuristic
                    bnd_ind_sum[cube_ind][1] += dt
    return [group_ids,les,endpts,bnd_ind_sum]


def MCT(sim,args,grid,nodes=8,parallel=True,limit=1,AVG=.01,eta_1=1.2,eta_2=.95,
        eps=1.,L=1,q=2,r=1.1,Dinv=1):
    # Initialize helper variables, uniform distribution, and recording structs
    shape = tuple(grid[:,2])
    ids = range(int(np.prod(shape)))
    p = np.ones(np.prod(shape))/np.prod(shape)
    ref = None
    ref_ept = None
    data = {}
    B_pairs = 0
    bndry_ids_master = set()
    starts = set()

    # Determine if using pathos multiprocessing
    if nodes <= 1 or not parallel:
        parallel = False
    else:
        pool = mp.ProcessingPool(nodes=nodes)

    # Initalize counters
    i = 0
    avg = np.inf
    while (i < limit) and (avg > AVG):
        print('Iteration '+repr(i))

        # Draw grid points from probability distribution p
        center_ids = np.random.choice(ids,size=L,p=p)
        starts |= set(center_ids)
        center_inds = [int2ind(center_id,shape) for center_id in center_ids]
        x = [(ind,sim,args,grid,shape,eps,q,r,Dinv) for ind in center_inds]

        # Compute LEs of selected grid points (and their neighbors)
        if parallel:
            groups = pool.map(LE,x)
        else:
            groups = [LE(xi) for xi in x]

        # Aggregate trajectory information
        bnd_ind_sum_master = {}
        for group in groups:
            bnd_ind_sum = group[3]
            for key,val in bnd_ind_sum.iteritems():
                if not (key in bnd_ind_sum_master):
                    bnd_ind_sum_master[key] = [0,0]
                bnd_ind_sum_master[key][0] += val[0]
                bnd_ind_sum_master[key][1] += val[1]

        # Update set of LEs with any new LEs found
        for group in groups:
            les = group[1]
            endpts = group[2]
            ref, data, ref_ept = update_LERef(ref,les,eps,data,ref_ept,endpts)

        # Associate all LEs from recent run with LEs in reference base
        for group in groups:
            les = group[1]
            adjustLEs2Ref(ref,les)

        # Update probability distribution p for selected grid points
        bndry_ids_all = set()
        for group in groups:
            group_ids, group_les = group[:2]
            p, data, b_pairs, bndry_ids = update_Prob_Data(group_ids,shape,grid,
                                                           group_les,eps,
                                                           p,eta_1,eta_2,
                                                           data)
            B_pairs += b_pairs
            bndry_ids_all |= bndry_ids
        # Update probability distribution p for grid points along trajectories
        for key,val in bnd_ind_sum_master.iteritems():
            _int = ind2int(key,shape)
            p[_int] *= val[0]/val[1]
        p = p/np.sum(p)

        # Update counters
        i += 1
        avg = B_pairs/((q+1)*L*i)
        bndry_ids_master |= bndry_ids_all
    return ref, data, p, i, avg, bndry_ids_master, starts
