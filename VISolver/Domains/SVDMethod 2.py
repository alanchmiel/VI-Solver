import numpy as np
from scipy.sparse.linalg import svds
# from scipy.linalg import diagsvd

from VISolver.Domain import Domain


class SVDMethod(Domain):

    def __init__(self,Data,keepData=False,tau=1.,Dim=None):
        self.Data = self.load_data(Data)
        self.keepData = keepData
        self.tau = tau
        self.Dim = Dim
        self.last_F = np.inf

    def load_data(self,Data):
        self.mask = (Data != 0).toarray()
        self.fro = np.linalg.norm(self.mask*Data.toarray(),ord='fro')
        return Data.toarray()

    def unpack(self,parameters):
        return parameters.reshape(self.Data.shape)

    def F(self,parameters):
        R = self.shrink(self.unpack(parameters),self.tau)
        # grad = np.asarray(self.Data-R)*self.mask
        grad = (self.Data-R)*self.mask
        self.last_F = grad
        return grad.flatten()

    def shrink(self,x,tau,k=10):
        U, S, Vt = svds(x,k=k)
        # U, S, Vt = np.linalg.svd(x,full_matrices=False)
        # U, S, Vt = np.linalg.svd(x)
        sub_thresh = (np.abs(S) <= tau)
        S[sub_thresh] = 0.
        S[~sub_thresh] = S[~sub_thresh] - np.sign(S[~sub_thresh])*tau
        # s = np.clip(S-np.sign(S)*tau,0.,np.inf)
        # R = U.dot(np.diag(s)).dot(Vt)
        R = U.dot(np.diag(S)).dot(Vt)
        # R = U.dot(diagsvd(s,U.shape[1],Vt.shape[0])).dot(Vt)
        return R

    def rel_error(self,parameters):
        err = np.linalg.norm(self.last_F,ord='fro')/self.fro
        print(err)
        return err
