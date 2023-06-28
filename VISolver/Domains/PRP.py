import numpy as np

import matplotlib as mpl
mpl.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.collections as mc
import matplotlib.cm as cm

from VISolver.Domain import Domain


class PRP(Domain):

    def __init__(self,Network,alpha=2): # This is probably only really 
        self.UnpackNetwork(Network) # important for the random example... 
        self.Network = (self.nC,self.nB,self.nD,self.nR) # Might not need to 
        self.Dim = self.CalculateNetworkSize() # do anything here?
        self.alpha = alpha

        self.cmap = cm.Reds
        norm = mpl.colors.Normalize(vmin=0.,vmax=1.)
        self.to_rgba = [cm.ScalarMappable(norm=norm, cmap=self.cmap).to_rgba]*6

    def F(self,Data):
        return self.F_P2UP(Data)

    def gap_rplus(self, X):
        dFdX = self.F(X)

        Y = np.maximum(0,X - dFdX/self.alpha)
        Z = X - Y

        return np.dot(dFdX,Z) - self.alpha/2.*np.dot(Z,Z)

    # Functions Used to Animate and Save Network Run to Movie File

    def FlowNormalizeColormap(self,Data,cmap):
        self.cmap = cmap
        maxFlows = [0]*6
        for data in Data:
            flows = list(self.PathFlow2LinkFlow_x2f(self.UnpackPathFlows(data)))
            newFlows = [np.max(flow) for flow in flows]
            maxFlows = np.max([maxFlows,newFlows],axis=0)
        norm = [mpl.colors.Normalize(vmin=0.,vmax=mxf) for mxf in maxFlows]
        self.to_rgba = [cm.ScalarMappable(norm=n, cmap=self.cmap).to_rgba
                        for n in norm]

    def InitVisual(self):

        ax = plt.gca()
        fig = plt.gcf()

        # Add Colorbar
        cax = fig.add_axes([0.95, 0.2, 0.02, 0.6])
        plt.axis('off')
        cb = mpl.colorbar.ColorbarBase(cax, cmap=self.cmap,
                                       spacing='proportional')
        cb.set_label('Blood Flow')

        plt.sca(ax)

        # Create Network Skeleton
        Ox = (max([self.nC,self.nB,self.nD,self.nR]) - 1.)/2.
        Cx = np.linspace(Ox-(self.nC-1.)/2.,Ox+(self.nC-1.)/2.,self.nC)
        Bx = np.linspace(Ox-(self.nB-1.)/2.,Ox+(self.nB-1.)/2.,self.nB)
        Px = np.linspace(Ox-(self.nB-1.)/2.,Ox+(self.nB-1.)/2.,self.nB)
        Sx = np.linspace(Ox-(self.nB-1.)/2.,Ox+(self.nB-1.)/2.,self.nB)
        Dx = np.linspace(Ox-(self.nD-1.)/2.,Ox+(self.nD-1.)/2.,self.nD)
        Rx = np.linspace(Ox-(self.nR-1.)/2.,Ox+(self.nR-1.)/2.,self.nR)

        Oy = 6.
        Cy = 5.
        By = 4.
        Py = 3.
        Sy = 2.
        Dy = 1.
        Ry = 0.

        od = []
        for c in range(self.nC):
            od.append([(Ox,Oy),(Cx[c],Cy)])
        for c in range(self.nC):
            for b in range(self.nB):
                od.append([(Cx[c],Cy),(Bx[b],By)])
        for b in range(self.nB):
            od.append([(Bx[b],By),(Px[b],Py)])
        for p in range(self.nB):
            od.append([(Px[p],Py),(Sx[p],Sy)])
        for s in range(self.nB):
            for d in range(self.nD):
                od.append([(Sx[s],Sy),(Dx[d],Dy)])
        for d in range(self.nD):
            for r in range(self.nR):
                od.append([(Dx[d],Dy),(Rx[r],Ry)])
        lc = mc.LineCollection(od, colors=(0,0,0,0), linewidths=10)
        ax.add_collection(lc)
        ax.set_xlim((0,2*Ox))
        ax.set_ylim((-.5,6.5))
        ax.add_collection(lc)

        # Annotate Plot
        plt.box('off')
        plt.yticks([0,1,2,3,4,5,6],['Hospitals', 'Distribution', 'Storage',
                                    'Labs', 'Blood Centers', 'Collection',
                                    'Organization'], rotation=45)
        plt.xticks(Rx,['Hospital\n'+str(r+1) for r in range(self.nR)])
        plt.tick_params(axis='y',right='off')
        plt.tick_params(axis='x',top='off')

        return ax.collections

    def UpdateVisual(self,num,ax,Frames,annotations):

        Data = Frames[num]

        # Check for Next Annotation
        if len(annotations) > 0:
            ann = annotations[-1]
            if num >= ann[0]:
                ann[1](ann[2])
                annotations.pop()

        # Unpack Data
        f_1C, f_CB, f_BP, f_PS, f_SD, f_DR = \
            self.PathFlow2LinkFlow_x2f(self.UnpackPathFlows(Data))

        colors = []
        for c in range(self.nC):
            colors.append(self.to_rgba[0](f_1C[c]))
        for c in range(self.nC):
            for b in range(self.nB):
                colors.append(self.to_rgba[1](f_CB[c,b]))
        for b in range(self.nB):
            colors.append(self.to_rgba[2](f_BP[b]))
        for p in range(self.nB):
            colors.append(self.to_rgba[3](f_PS[p]))
        for s in range(self.nB):
            for d in range(self.nD):
                colors.append(self.to_rgba[4](f_SD[s,d]))
        for d in range(self.nD):
            for r in range(self.nR):
                colors.append(self.to_rgba[5](f_DR[d,r]))

        ax.collections[0].set_color(colors)

        return ax.collections

    # Functions used to Initialize the BloodBank Network and Calculate F

    def UnpackNetwork(self,Network):

        self.nC,self.nB,self.nD,self.nR,\
            self.alpha_CBx,self.alpha_BPx,self.alpha_PSx,\
            self.alpha_SDx,self.alpha_DRx,\
            self.alpha_CBf,self.alpha_BPf,self.alpha_PSf,\
            self.alpha_SDf,self.alpha_DRf,\
            self.mu,\
            self.chat_pow1_1C,self.chat_pow1_CB,self.chat_pow1_BP,\
            self.chat_pow1_PS,self.chat_pow1_SD,self.chat_pow1_DR,\
            self.chat_pow2_1C,self.chat_pow2_CB,self.chat_pow2_BP,\
            self.chat_pow2_PS,self.chat_pow2_SD,self.chat_pow2_DR,\
            self.zhat_1C,self.zhat_CB,self.zhat_BP,self.zhat_PS,\
            self.zhat_SD,self.zhat_DR,\
            self.rhat,\
            self.pihat_pow1_1C,self.pihat_pow1_CB,self.pihat_pow1_BP,\
            self.pihat_pow1_PS,self.pihat_pow1_SD,self.pihat_pow1_DR,\
            self.pihat_pow2_1C,self.pihat_pow2_CB,self.pihat_pow2_BP,\
            self.pihat_pow2_PS,self.pihat_pow2_SD,self.pihat_pow2_DR,\
            self.ubar_1C,self.ubar_CB,self.ubar_BP,self.ubar_PS,\
            self.ubar_SD,self.ubar_DR,\
            self.ind_C___C,\
            self.ind_CB__C,self.ind_CB__B,\
            self.ind_CBD_C,self.ind_CBD_B,self.ind_CBD_D,\
            self.ind_CBDR_C,self.ind_CBDR_B,self.ind_CBDR_D,self.ind_CBDR_R,\
            self.prob_low,self.prob_high,\
            self.theta,\
            self.lambda_minus,self.lambda_plus = Network

    def UnpackPathFlows(self,Data):

        return np.reshape(Data[0:self.nC*self.nB*self.nD*self.nR],
                         (self.nC,self.nB,self.nD,self.nR))

    def CalculateNetworkSize(self):

        xSize = self.nC*self.nB*self.nD*self.nR
        uSize = gamSize = self.nC+self.nC*self.nB+self.nB+self.nB + \
            self.nB*self.nD+self.nD*self.nR

        return xSize+uSize+gamSize

    def F_P2UP(self,Data):

        # Unpack Data
        ptr = 0
        x = np.reshape(Data[ptr:ptr+self.nC*self.nB*self.nD*self.nR],
                       (self.nC,self.nB,self.nD,self.nR))
        ptr += self.nC*self.nB*self.nD*self.nR
        u_1C = np.reshape(Data[ptr:ptr+self.nC],(self.nC,))
        ptr += self.nC
        u_CB = np.reshape(Data[ptr:ptr+self.nC*self.nB],(self.nC,self.nB))
        ptr += self.nC*self.nB
        u_BP = np.reshape(Data[ptr:ptr+self.nB],(self.nB,))
        ptr += self.nB
        u_PS = np.reshape(Data[ptr:ptr+self.nB],(self.nB,))
        ptr += self.nB
        u_SD = np.reshape(Data[ptr:ptr+self.nB*self.nD],(self.nB,self.nD))
        ptr += self.nB*self.nD
        u_DR = np.reshape(Data[ptr:ptr+self.nD*self.nR],(self.nD,self.nR))
        ptr += self.nD*self.nR
        gam_1C = np.reshape(Data[ptr:ptr+self.nC],(self.nC,))
        ptr += self.nC
        gam_CB = np.reshape(Data[ptr:ptr+self.nC*self.nB],(self.nC,self.nB))
        ptr += self.nC*self.nB
        gam_BP = np.reshape(Data[ptr:ptr+self.nB],(self.nB,))
        ptr += self.nB
        gam_PS = np.reshape(Data[ptr:ptr+self.nB],(self.nB,))
        ptr += self.nB
        gam_SD = np.reshape(Data[ptr:ptr+self.nB*self.nD],(self.nB,self.nD))
        ptr += self.nB*self.nD
        gam_DR = np.reshape(Data[ptr:ptr+self.nD*self.nR],(self.nD,self.nR))
        ptr = 0

        F_unpacked = self.FX_dX(x,
                                u_1C,u_CB,u_BP,u_PS,u_SD,u_DR,
                                gam_1C,gam_CB,gam_BP,gam_PS,gam_SD,gam_DR)

        # Pack Data
        F_packed = np.array([])
        for Fx in F_unpacked:
            F_packed = np.append(F_packed,Fx.flatten())

        return F_packed

    def PathFlow2LinkFlow_x2f(self,x):

        f_1C = np.reshape(np.sum(x[self.ind_C___C,:,:,:],axis=(1,2,3)),
                          (self.nC,))
        x_CB = x[self.ind_CB__C,self.ind_CB__B,:,:]*self.alpha_CBx
        f_CB = np.reshape(np.sum(x_CB,axis=(1,2)),(self.nC,self.nB))
        x_BP = x[self.ind_CB__C,self.ind_CB__B,:,:]*self.alpha_BPx
        f_BP = np.sum(np.reshape(x_BP,(self.nC,self.nB,self.nD,self.nR)),
                      axis=(0,2,3))
        f_PS = f_BP*self.alpha_PSx
        x_SD = x[self.ind_CB__C,self.ind_CB__B,:,:]*self.alpha_SDx
        f_SD = np.sum(np.reshape(x_SD,(self.nC,self.nB,self.nD,self.nR)),
                      axis=(0,3))
        x_DR = x[self.ind_CBD_C,self.ind_CBD_B,self.ind_CBD_D,:]*self.alpha_DRx
        f_DR = np.sum(np.reshape(x_DR,(self.nC,self.nB,self.nD,self.nR)),
                      axis=(0,1))

        return f_1C, f_CB, f_BP, f_PS, f_SD, f_DR

    def TotalOperationalCost_Chatx(self,x,f_1C,f_CB,f_BP,f_PS,f_SD,f_DR):

        c_1C = self.chat_pow2_1C[self.ind_CBDR_C]*f_1C[self.ind_CBDR_C] + \
            self.chat_pow1_1C[self.ind_CBDR_C]
        c_CB = self.chat_pow2_CB[self.ind_CBDR_C,self.ind_CBDR_B] * \
            f_CB[self.ind_CBDR_C,self.ind_CBDR_B] + \
            self.chat_pow1_CB[self.ind_CBDR_C,self.ind_CBDR_B]
        c_BP = self.chat_pow2_BP[self.ind_CBDR_B]*f_BP[self.ind_CBDR_B] + \
            self.chat_pow1_BP[self.ind_CBDR_B]
        c_PS = self.chat_pow2_PS[self.ind_CBDR_B]*f_PS[self.ind_CBDR_B] + \
            self.chat_pow1_PS[self.ind_CBDR_B]
        c_SD = self.chat_pow2_SD[self.ind_CBDR_B,self.ind_CBDR_D] * \
            f_SD[self.ind_CBDR_B,self.ind_CBDR_D] + \
            self.chat_pow1_SD[self.ind_CBDR_B,self.ind_CBDR_D]
        c_DR = self.chat_pow2_DR[self.ind_CBDR_D,self.ind_CBDR_R] * \
            f_DR[self.ind_CBDR_D,self.ind_CBDR_R] + \
            self.chat_pow1_DR[self.ind_CBDR_D,self.ind_CBDR_R]

        return x*np.reshape(c_1C +
                            c_CB*self.alpha_CBf +
                            c_BP*self.alpha_BPf +
                            c_PS*self.alpha_PSf +
                            c_SD*self.alpha_SDf +
                            c_DR*self.alpha_DRf,
                            x.shape)

    def dTotalOperationalCostdx_dChatxdx(self,x,f_1C,f_CB,f_BP,f_PS,f_SD,f_DR):

        dc_1C = 2.*self.chat_pow2_1C[self.ind_CBDR_C]*f_1C[self.ind_CBDR_C] + \
            self.chat_pow1_1C[self.ind_CBDR_C]
        dc_CB = 2.*self.chat_pow2_CB[self.ind_CBDR_C,self.ind_CBDR_B] * \
            f_CB[self.ind_CBDR_C,self.ind_CBDR_B] + \
            self.chat_pow1_CB[self.ind_CBDR_C,self.ind_CBDR_B]
        dc_BP = 2.*self.chat_pow2_BP[self.ind_CBDR_B]*f_BP[self.ind_CBDR_B] + \
            self.chat_pow1_BP[self.ind_CBDR_B]
        dc_PS = 2.*self.chat_pow2_PS[self.ind_CBDR_B]*f_PS[self.ind_CBDR_B] + \
            self.chat_pow1_PS[self.ind_CBDR_B]
        dc_SD = 2.*self.chat_pow2_SD[self.ind_CBDR_B,self.ind_CBDR_D] * \
            f_SD[self.ind_CBDR_B,self.ind_CBDR_D] + \
            self.chat_pow1_SD[self.ind_CBDR_B,self.ind_CBDR_D]
        dc_DR = 2.*self.chat_pow2_DR[self.ind_CBDR_D,self.ind_CBDR_R] * \
            f_DR[self.ind_CBDR_D,self.ind_CBDR_R] + \
            self.chat_pow1_DR[self.ind_CBDR_D,self.ind_CBDR_R]

        return np.reshape(dc_1C +
                          dc_CB*self.alpha_CBf +
                          dc_BP*self.alpha_BPf +
                          dc_PS*self.alpha_PSf +
                          dc_SD*self.alpha_SDf +
                          dc_DR*self.alpha_DRf,
                          x.shape)

    def TotalDiscardingCost_Zhatx(self,x,f_1C,f_CB,f_BP,f_PS,f_SD,f_DR):

        z_1C = self.zhat_1C[self.ind_CBDR_C]*f_1C[self.ind_CBDR_C]
        z_CB = self.zhat_CB[self.ind_CBDR_C,self.ind_CBDR_B] * \
            f_CB[self.ind_CBDR_C,self.ind_CBDR_B]
        z_BP = self.zhat_BP[self.ind_CBDR_B]*f_BP[self.ind_CBDR_B]
        z_PS = self.zhat_PS[self.ind_CBDR_B]*f_PS[self.ind_CBDR_B]
        z_SD = self.zhat_SD[self.ind_CBDR_B,self.ind_CBDR_D] * \
            f_SD[self.ind_CBDR_B,self.ind_CBDR_D]
        z_DR = self.zhat_DR[self.ind_CBDR_D,self.ind_CBDR_R] * \
            f_DR[self.ind_CBDR_D,self.ind_CBDR_R]

        return x*np.reshape(z_1C +
                            z_CB*self.alpha_CBf +
                            z_BP*self.alpha_BPf +
                            z_PS*self.alpha_PSf +
                            z_SD*self.alpha_SDf +
                            z_DR*self.alpha_DRf,
                            x.shape)

    def dTotalDiscardingCostdx_dZhatxdx(self,x,f_1C,f_CB,f_BP,f_PS,f_SD,f_DR):

        dz_1C = 2.*self.zhat_1C[self.ind_CBDR_C]*f_1C[self.ind_CBDR_C]
        dz_CB = 2.*self.zhat_CB[self.ind_CBDR_C,self.ind_CBDR_B] * \
            f_CB[self.ind_CBDR_C,self.ind_CBDR_B]
        dz_BP = 2.*self.zhat_BP[self.ind_CBDR_B]*f_BP[self.ind_CBDR_B]
        dz_PS = 2.*self.zhat_PS[self.ind_CBDR_B]*f_PS[self.ind_CBDR_B]
        dz_SD = 2.*self.zhat_SD[self.ind_CBDR_B,self.ind_CBDR_D] * \
            f_SD[self.ind_CBDR_B,self.ind_CBDR_D]
        dz_DR = 2.*self.zhat_DR[self.ind_CBDR_D,self.ind_CBDR_R] * \
            f_DR[self.ind_CBDR_D,self.ind_CBDR_R]

        return np.reshape(dz_1C +
                          dz_CB*self.alpha_CBf +
                          dz_BP*self.alpha_BPf +
                          dz_PS*self.alpha_PSf +
                          dz_SD*self.alpha_SDf +
                          dz_DR*self.alpha_DRf,
                          x.shape)

    def TotalRisk_Rhatx(self,x,f_1C):

        r_1C = self.rhat[self.ind_CBDR_C]*f_1C[self.ind_CBDR_C]

        return x*np.reshape(r_1C,x.shape)

    def dTotalRiskdx_dRhatxdx(self,x,f_1C):

        dr_1C = 2.*self.rhat[self.ind_CBDR_C]*f_1C[self.ind_CBDR_C]

        return np.reshape(dr_1C,x.shape)

    def TotalInvestmentCost_Pihatu(self,u_1C,u_CB,u_BP,u_PS,u_SD,u_DR):

        pi_1C = self.pihat_pow2_1C*(u_1C**2)+self.pihat_pow1_1C*u_1C
        pi_CB = self.pihat_pow2_CB*(u_CB**2)+self.pihat_pow1_CB*u_CB
        pi_BP = self.pihat_pow2_BP*(u_BP**2)+self.pihat_pow1_BP*u_BP
        pi_PS = self.pihat_pow2_PS*(u_PS**2)+self.pihat_pow1_PS*u_PS
        pi_SD = self.pihat_pow2_SD*(u_SD**2)+self.pihat_pow1_SD*u_SD
        pi_DR = self.pihat_pow2_DR*(u_DR**2)+self.pihat_pow1_DR*u_DR

        return pi_1C, pi_CB, pi_BP, pi_PS, pi_SD, pi_DR

    def dTotalInvestmentCostdu_dPihatudu(self,u_1C,u_CB,u_BP,u_PS,u_SD,u_DR):

        dpi_1C = 2.*self.pihat_pow2_1C*u_1C+self.pihat_pow1_1C
        dpi_CB = 2.*self.pihat_pow2_CB*u_CB+self.pihat_pow1_CB
        dpi_BP = 2.*self.pihat_pow2_BP*u_BP+self.pihat_pow1_BP
        dpi_PS = 2.*self.pihat_pow2_PS*u_PS+self.pihat_pow1_PS
        dpi_SD = 2.*self.pihat_pow2_SD*u_SD+self.pihat_pow1_SD
        dpi_DR = 2.*self.pihat_pow2_DR*u_DR+self.pihat_pow1_DR

        return dpi_1C, dpi_CB, dpi_BP, dpi_PS, dpi_SD, dpi_DR

    def ExpectedShortage_EMinus(self,x):

        nu = np.sum(x*self.mu,axis=(0,1,2))

        return ((nu**2)/2.-nu*self.prob_high+(self.prob_high**2)/2.) / \
            (self.prob_high-self.prob_low)

    def ExpectedSurplus_EPlus(self,x):

        nu = np.sum(x*self.mu,axis=(0,1,2))

        return ((nu**2)/2.-nu*self.prob_low+(self.prob_low**2)/2.) / \
            (self.prob_high-self.prob_low)

    def ProbabilityDistributionFunction_Pknuk(self,x):

        nu = np.sum(x*self.mu,axis=(0,1,2))

        return (nu-self.prob_low)/(self.prob_high-self.prob_low)

    def MulticriteriaObjective_Obj(self,x,u_1C,u_CB,u_BP,u_PS,u_SD,u_DR):

        f_1C, f_CB, f_BP, f_PS, f_SD, f_DR = self.PathFlow2LinkFlow_x2f(x)
        Chatx = self.TotalOperationalCost_Chatx(x,f_1C,f_CB,f_BP,f_PS,f_SD,f_DR)
        Zhatx = self.TotalDiscardingCost_Zhatx(x,f_1C,f_CB,f_BP,f_PS,f_SD,f_DR)
        pi_1C, pi_CB, pi_BP, pi_PS, pi_SD, pi_DR = \
            self.TotalInvestmentCost_Pihatu(u_1C,u_CB,u_BP,u_PS,u_SD,u_DR)
        EMinus = self.ExpectedShortage_EMinus(x)
        EPlus = self.ExpectedSurplus_EPlus(x)
        Rhatx = self.TotalRisk_Rhatx(x,f_1C)

        return np.sum(Chatx+Zhatx) + \
            np.sum(pi_1C)+np.sum(pi_CB)+np.sum(pi_BP)+np.sum(pi_PS) + \
            np.sum(pi_SD)+np.sum(pi_DR) + \
            np.sum(self.lambda_minus*EMinus+self.lambda_plus*EPlus) + \
            np.sum(Rhatx)*self.theta

    def Lagrangian_L(self,x,u_1C,u_CB,u_BP,u_PS,u_SD,u_DR,
                     gam_1C,gam_CB,gam_BP,gam_PS,gam_SD,gam_DR):

        f_1C, f_CB, f_BP, f_PS, f_SD, f_DR = self.PathFlow2LinkFlow_x2f(x)
        Chatx = self.TotalOperationalCost_Chatx(x,f_1C,f_CB,f_BP,f_PS,f_SD,f_DR)
        Zhatx = self.TotalDiscardingCost_Zhatx(x,f_1C,f_CB,f_BP,f_PS,f_SD,f_DR)
        pi_1C, pi_CB, pi_BP, pi_PS, pi_SD, pi_DR = \
            self.TotalInvestmentCost_Pihatu(u_1C,u_CB,u_BP,u_PS,u_SD,u_DR)
        EMinus = self.ExpectedShortage_EMinus(x)
        EPlus = self.ExpectedSurplus_EPlus(x)
        Rhatx = self.TotalRisk_Rhatx(x,f_1C)
        dgam_1C, dgam_CB, dgam_BP, dgam_PS, dgam_SD, dgam_DR = \
            self.F3X_dgam(f_1C, f_CB, f_BP, f_PS, f_SD, f_DR,
                          u_1C,u_CB,u_BP,u_PS,u_SD,u_DR)

        return np.sum(Chatx+Zhatx) + \
            np.sum(pi_1C)+np.sum(pi_CB)+np.sum(pi_BP)+np.sum(pi_PS) + \
            np.sum(pi_SD)+np.sum(pi_DR) + \
            np.sum(self.lambda_minus*EMinus+self.lambda_plus*EPlus) + \
            np.sum(Rhatx)*self.theta - \
            np.sum(gam_1C*dgam_1C)-np.sum(gam_CB*dgam_CB) - \
            np.sum(gam_BP*dgam_BP)-np.sum(gam_PS*dgam_PS) - \
            np.sum(gam_SD*dgam_SD)-np.sum(gam_DR*dgam_DR)

    def F1X_dx(self,x,f_1C,f_CB,f_BP,f_PS,f_SD,f_DR,
               gam_1C,gam_CB,gam_BP,gam_PS,gam_SD,gam_DR):

        dChatxdx = self.dTotalOperationalCostdx_dChatxdx(x,f_1C,f_CB,f_BP,
                                                         f_PS,f_SD,f_DR)
        dZhatxdx = self.dTotalDiscardingCostdx_dZhatxdx(x,f_1C,f_CB,f_BP,
                                                        f_PS,f_SD,f_DR)
        Pknuk = np.tile(self.ProbabilityDistributionFunction_Pknuk(x),
                        (self.nC,self.nB,self.nD,1))
        Gam = np.reshape(gam_1C[self.ind_CBDR_C] +
                         gam_CB[self.ind_CBDR_C,self.ind_CBDR_B] +
                         gam_BP[self.ind_CBDR_B] +
                         gam_PS[self.ind_CBDR_B] +
                         gam_SD[self.ind_CBDR_B,self.ind_CBDR_D] +
                         gam_DR[self.ind_CBDR_D,self.ind_CBDR_R],
                         (self.nC,self.nB,self.nD,self.nR))
        dRhatxdx = self.dTotalRiskdx_dRhatxdx(x,f_1C)

        return dChatxdx + dZhatxdx + self.lambda_plus*self.mu*Pknuk - \
            self.lambda_minus*self.mu*(1-Pknuk) + Gam + self.theta*dRhatxdx

    def F2X_du(self,u_1C,u_CB,u_BP,u_PS,u_SD,u_DR,
               gam_1C,gam_CB,gam_BP,gam_PS,gam_SD,gam_DR):

        dpi_1C, dpi_CB, dpi_BP, dpi_PS, dpi_SD, dpi_DR = \
            self.dTotalInvestmentCostdu_dPihatudu(u_1C,u_CB,u_BP,u_PS,u_SD,u_DR)

        du_1C = dpi_1C - gam_1C
        du_CB = dpi_CB - gam_CB
        du_BP = dpi_BP - gam_BP
        du_PS = dpi_PS - gam_PS
        du_SD = dpi_SD - gam_SD
        du_DR = dpi_DR - gam_DR

        return du_1C, du_CB, du_BP, du_PS, du_SD, du_DR

    def F3X_dgam(self,f_1C,f_CB,f_BP,f_PS,f_SD,f_DR,
                 u_1C,u_CB,u_BP,u_PS,u_SD,u_DR):

        dgam_1C = self.ubar_1C + u_1C - f_1C
        dgam_CB = self.ubar_CB + u_CB - f_CB
        dgam_BP = self.ubar_BP + u_BP - f_BP
        dgam_PS = self.ubar_PS + u_PS - f_PS
        dgam_SD = self.ubar_SD + u_SD - f_SD
        dgam_DR = self.ubar_DR + u_DR - f_DR

        return dgam_1C, dgam_CB, dgam_BP, dgam_PS, dgam_SD, dgam_DR

    def FX_dX(self,x,u_1C,u_CB,u_BP,u_PS,u_SD,u_DR,
              gam_1C,gam_CB,gam_BP,gam_PS,gam_SD,gam_DR):

        f_1C, f_CB, f_BP, f_PS, f_SD, f_DR = self.PathFlow2LinkFlow_x2f(x)
        dx = self.F1X_dx(x,f_1C,f_CB,f_BP,f_PS,f_SD,f_DR,
                         gam_1C,gam_CB,gam_BP,gam_PS,gam_SD,gam_DR)
        du_1C, du_CB, du_BP, du_PS, du_SD, du_DR = \
            self.F2X_du(u_1C,u_CB,u_BP,u_PS,u_SD,u_DR,
                        gam_1C,gam_CB,gam_BP,gam_PS,gam_SD,gam_DR)
        dgam_1C, dgam_CB, dgam_BP, dgam_PS, dgam_SD, dgam_DR = \
            self.F3X_dgam(f_1C,f_CB,f_BP,f_PS,f_SD,f_DR,
                          u_1C,u_CB,u_BP,u_PS,u_SD,u_DR)

        return [dx,
                du_1C,   du_CB,   du_BP,   du_PS,   du_SD,   du_DR,
                dgam_1C, dgam_CB, dgam_BP, dgam_PS, dgam_SD, dgam_DR]


def CreateNetworkExample(ex=1):
    # Example 1 from Nagurney's Supply Chain Network Design
    # of a Sustainable Blood Banking System

    nC = 2 #Set the width of each stage
    nB = 2
    nP = 2
    nS = 2
    nD = 2
    nR = 3

    alpha_1C = np.zeros((nC,))   #create rowsxcolumns matrix (2x1)
    alpha_CB = np.zeros((nC,nB)) #(2x2)
    alpha_BP = np.zeros((nP,))   #These matrices hold the "loss" ... what per-
    alpha_PS = np.zeros((nS,))   #cent is lost between nodes
    alpha_SD = np.zeros((nS,nD))
    alpha_DR = np.zeros((nD,nR))

    alpha_1C[0] = 1 # Link 1
    alpha_1C[1] = 1 # Link 2
    alpha_CB[0,0] = 1.# Link 3 C1 to B1
    alpha_CB[0,1] = 1. # Link 4 C1 to B2
    alpha_CB[1,0] = 1.
    alpha_CB[1,1] = 1.
    alpha_BP[0] = 1.
    alpha_BP[1] = 1.
    alpha_PS[0] = 1.
    alpha_PS[1] = 1.
    alpha_SD[0,0] = 1.
    alpha_SD[0,1] = 1.
    alpha_SD[1,0] = 1.
    alpha_SD[1,1] = 1.
    # last set of links has no effect? see formula on page 9 for link flows
    alpha_DR[0,0] = 1.
    alpha_DR[0,1] = 1.
    alpha_DR[0,2] = 1
    alpha_DR[1,0] = 1.
    alpha_DR[1,1] = 1.
    alpha_DR[1,2] = 1

    chat_pow1_1C = np.zeros((nC,)) # These are the coefficients for the 
    chat_pow1_CB = np.zeros((nC,nB)) # Operational costs - in the form
    chat_pow1_BP = np.zeros((nP,))   # k_0f^2+k_1f
    chat_pow1_PS = np.zeros((nS,))
    chat_pow1_SD = np.zeros((nS,nD))
    chat_pow1_DR = np.zeros((nD,nR))

    chat_pow2_1C = np.zeros((nC,))   #pow2 is the f^2 K
    chat_pow2_CB = np.zeros((nC,nB))
    chat_pow2_BP = np.zeros((nP,))
    chat_pow2_PS = np.zeros((nS,))
    chat_pow2_SD = np.zeros((nS,nD))
    chat_pow2_DR = np.zeros((nD,nR))


  # chat_pow1_1C[0] = 15.
  # chat_pow2_1C[0] = 6.
  # chat_pow1_1C[1] = 11.
  # chat_pow2_1C[1] = 9.
  # chat_pow1_CB[0,0] = 1.
  # chat_pow2_CB[0,0] = .7
  # chat_pow1_CB[0,1] = 1.
  # chat_pow2_CB[0,1] = 1.2
  # chat_pow1_CB[1,0] = 3.
  # chat_pow2_CB[1,0] = 1.
  # chat_pow1_CB[1,1] = 2.
  # chat_pow2_CB[1,1] = .8
  # chat_pow1_BP[0] = 2.
  # chat_pow2_BP[0] = 2.5
  # chat_pow1_BP[1] = 5.
  # chat_pow2_BP[1] = 3.
  # chat_pow1_PS[0] = 6.
  # chat_pow2_PS[0] = .8
  # chat_pow1_PS[1] = 3.
  # chat_pow2_PS[1] = .5
  # chat_pow1_SD[0,0] = 1.
  # chat_pow2_SD[0,0] = .3
  # chat_pow1_SD[0,1] = 2.
  # chat_pow2_SD[0,1] = .5
  # chat_pow1_SD[1,0] = 2.
  # chat_pow2_SD[1,0] = .4
  # chat_pow1_SD[1,1] = 1.
  # chat_pow2_SD[1,1] = .6
  # chat_pow1_DR[0,0] = 1.
  # chat_pow2_DR[0,0] = .4
  # chat_pow1_DR[0,1] = 2.
  # chat_pow2_DR[0,1] = .8
  # chat_pow1_DR[0,2] = 3.
  # chat_pow2_DR[0,2] = .5
  # chat_pow1_DR[1,0] = 1.
  # chat_pow2_DR[1,0] = .7
  # chat_pow1_DR[1,1] = 4.
  # chat_pow2_DR[1,1] = .6
  # chat_pow1_DR[1,2] = 5.
  # chat_pow2_DR[1,2] = 1.1


    chat_pow1_1C[0] = 0.
    chat_pow2_1C[0] = 0.
    chat_pow1_1C[1] = 0.
    chat_pow2_1C[1] = 0.
    chat_pow1_CB[0,0] = 1.
    chat_pow2_CB[0,0] = .7
    chat_pow1_CB[0,1] = 1.
    chat_pow2_CB[0,1] = 1.2
    chat_pow1_CB[1,0] = 3.
    chat_pow2_CB[1,0] = 1.
    chat_pow1_CB[1,1] = 2.
    chat_pow2_CB[1,1] = .8
    chat_pow1_BP[0] = 0
    chat_pow2_BP[0] = 0
    chat_pow1_BP[1] = 0
    chat_pow2_BP[1] = 0
    chat_pow1_PS[0] = 0
    chat_pow2_PS[0] = 0
    chat_pow1_PS[1] = 0
    chat_pow2_PS[1] = 0
    chat_pow1_SD[0,0] = 1.
    chat_pow2_SD[0,0] = .3
    chat_pow1_SD[0,1] = 2.
    chat_pow2_SD[0,1] = .5
    chat_pow1_SD[1,0] = 2.
    chat_pow2_SD[1,0] = .4
    chat_pow1_SD[1,1] = 1.
    chat_pow2_SD[1,1] = .6
    chat_pow1_DR[0,0] = 1.
    chat_pow2_DR[0,0] = .4
    chat_pow1_DR[0,1] = 2.
    chat_pow2_DR[0,1] = .8
    chat_pow1_DR[0,2] = 3.
    chat_pow2_DR[0,2] = .5
    chat_pow1_DR[1,0] = 1.
    chat_pow2_DR[1,0] = .7
    chat_pow1_DR[1,1] = 4.
    chat_pow2_DR[1,1] = .6
    chat_pow1_DR[1,2] = 5.
    chat_pow2_DR[1,2] = 1.1

    zhat_1C = np.zeros((nC,)) #This is the discard cost function 
    zhat_CB = np.zeros((nC,nB))
    zhat_BP = np.zeros((nP,))
    zhat_PS = np.zeros((nS,))
    zhat_SD = np.zeros((nS,nD))
    zhat_DR = np.zeros((nD,nR))

    zhat_1C[0] = 0
    zhat_1C[1] = 0
    zhat_CB[0,0] = 0
    zhat_CB[0,1] = 0
    zhat_CB[1,0] = 0
    zhat_CB[1,1] = 0
    zhat_BP[0] = 0
    zhat_BP[1] = 0
    zhat_PS[0] = 0
    zhat_PS[1] = 0
    zhat_SD[0,0] = 0
    zhat_SD[0,1] = 0
    zhat_SD[1,0] = 0
    zhat_SD[1,1] = 0
    zhat_DR[0,0] = 0
    zhat_DR[0,1] = 0
    zhat_DR[0,2] = 0
    zhat_DR[1,0] = 0
    zhat_DR[1,1] = 0 
    zhat_DR[1,2] = 0

    pihat_pow1_1C = np.zeros((nC,)) # This is the cost to add capacity
    pihat_pow1_CB = np.zeros((nC,nB)) # This could be used as a refinery cost add
    pihat_pow1_BP = np.zeros((nP,))
    pihat_pow1_PS = np.zeros((nS,))
    pihat_pow1_SD = np.zeros((nS,nD))
    pihat_pow1_DR = np.zeros((nD,nR))

    pihat_pow2_1C = np.zeros((nC,))
    pihat_pow2_CB = np.zeros((nC,nB))
    pihat_pow2_BP = np.zeros((nP,))
    pihat_pow2_PS = np.zeros((nS,))
    pihat_pow2_SD = np.zeros((nS,nD))
    pihat_pow2_DR = np.zeros((nD,nR))

    pihat_pow1_1C[0] = 0
    pihat_pow2_1C[0] = 0
    pihat_pow1_1C[1] = 0
    pihat_pow2_1C[1] = 0
    pihat_pow1_CB[0,0] = 2.
    pihat_pow2_CB[0,0] = 1.
    pihat_pow1_CB[0,1] = 1.
    pihat_pow2_CB[0,1] = 2.
    pihat_pow1_CB[1,0] = 1.
    pihat_pow2_CB[1,0] = 1.
    pihat_pow1_CB[1,1] = 3.
    pihat_pow2_CB[1,1] = 1.5
    pihat_pow1_BP[0] = 0
    pihat_pow2_BP[0] = 0
    pihat_pow1_BP[1] = 0
    pihat_pow2_BP[1] = 0
    pihat_pow1_PS[0] = 0
    pihat_pow2_PS[0] = 0
    pihat_pow1_PS[1] = 0
    pihat_pow2_PS[1] = 0
    pihat_pow1_SD[0,0] = 1.
    pihat_pow2_SD[0,0] = 1.
    pihat_pow1_SD[0,1] = 1.
    pihat_pow2_SD[0,1] = 1.5
    pihat_pow1_SD[1,0] = 1.5
    pihat_pow2_SD[1,0] = 1.8
    pihat_pow1_SD[1,1] = 2.
    pihat_pow2_SD[1,1] = 1.
    pihat_pow1_DR[0,0] = 1.1
    pihat_pow2_DR[0,0] = .5
    pihat_pow1_DR[0,1] = 3.
    pihat_pow2_DR[0,1] = .7
    pihat_pow1_DR[0,2] = 1.
    pihat_pow2_DR[0,2] = 2.
    pihat_pow1_DR[1,0] = 1.
    pihat_pow2_DR[1,0] = 1.
    pihat_pow1_DR[1,1] = 2.
    pihat_pow2_DR[1,1] = 1.
    pihat_pow1_DR[1,2] = 1.
    pihat_pow2_DR[1,2] = .8

    prob_low = np.zeros((nR,))
    prob_high = np.zeros((nR,))

    prob_low[0] = 5.
    prob_high[0] = 10.
    prob_low[1] = 40.
    prob_high[1] = 50.
    prob_low[2] = 25.
    prob_high[2] = 40.
    if ex == 2:
        prob_low[0] = 25.
        prob_high[0] = 30.
        prob_low[1] = 25.
        prob_high[1] = 40.
        prob_low[2] = 20.
        prob_high[2] = 30.
    elif ex == 3:
        prob_low[0] = 35.
        prob_high[0] = 50.
        prob_low[1] = 20.
        prob_high[1] = 30.
        prob_low[2] = 15.
        prob_high[2] = 20.

    lambda_minus = np.zeros((nR,))
    lambda_plus = np.zeros((nR,))

    lambda_minus[0] = 2800.
    lambda_plus[0] = 50.
    lambda_minus[1] = 3000.
    lambda_plus[1] = 60.
    lambda_minus[2] = 3100.
    lambda_plus[2] = 50.

    rhat = np.zeros((nC,))

    rhat[0] = 2. # This is the risk function
    rhat[1] = 1.5

    ubar_1C = np.zeros((nC,))  # This holds the capacity. 
    ubar_CB = np.zeros((nC,nB))
    ubar_BP = np.zeros((nB,))
    ubar_PS = np.zeros((nB,))
    ubar_SD = np.zeros((nB,nD))
    ubar_DR = np.zeros((nD,nR))

    theta = .7

    #Helper Arguments

    #Index Lists for Fast Slicing
    ind_C___C = np.arange(nC) # Creates array of integers of nC lenght) [0,1] This one is lenght 2
    ind_CB__C = np.tile(np.arange(nC),(nB,1)).T.flatten() # Lenght 4
    ind_CB__B = np.tile(np.arange(nB),nC)
    ind_CBD_C = np.tile(np.arange(nC),(nB*nD,1)).T.flatten()
    ind_CBD_B = np.tile(np.tile(np.arange(nB),(nD,1)).T.flatten(),nC)
    ind_CBD_D = np.tile(np.arange(nD),nC*nB)
    ind_CBDR_C = np.tile(np.arange(nC),(nB*nD*nR,1)).T.flatten()
    ind_CBDR_B = np.tile(np.tile(np.arange(nB),(nD*nR,1)).T.flatten(),nC)
    ind_CBDR_D = np.tile(np.tile(np.arange(nD),(nR,1)).T.flatten(),nC*nB)
    ind_CBDR_R = np.tile(np.arange(nR),nC*nB*nD)

    #Alpha Values for Both Path and Link Computation
    tile_1C = np.rollaxis(alpha_1C[ind_CB__C][None][None],2) # has link 1 and Link 2 Alpha values - twice
    tile_CB = np.rollaxis(alpha_CB[ind_CB__C,ind_CB__B][None][None],2) # Link 3,4,5,6
    tile_BP = np.rollaxis(alpha_BP[ind_CB__B][None][None],2) # BP Links twice
    tile_PS = np.rollaxis(alpha_PS[ind_CB__B][None][None],2) # PS links twice

    tile_1C2 = np.rollaxis(alpha_1C[ind_CBD_C][None],1) #the previous tiles twice
    tile_CB2 = np.rollaxis(alpha_CB[ind_CBD_C,ind_CBD_B][None],1)
    tile_BP2 = np.rollaxis(alpha_BP[ind_CBD_B][None],1)
    tile_PS2 = np.rollaxis(alpha_PS[ind_CBD_B][None],1)
    tile_SD2 = np.rollaxis(alpha_SD[ind_CBD_B,ind_CBD_D][None],1)

    alpha_CBx = np.tile(tile_1C,(1,nD,nR))
    alpha_BPx = np.tile(tile_1C,(1,nD,nR)) * np.tile(tile_CB,(1,nD,nR))
    alpha_PSx = alpha_BP
    alpha_SDx = np.tile(tile_1C,(1,nD,nR)) * \
        np.tile(tile_CB,(1,nD,nR)) * \
        np.tile(tile_BP,(1,nD,nR)) * \
        np.tile(tile_PS,(1,nD,nR))
    alpha_DRx = np.tile(tile_1C2,(1,nR)) * \
        np.tile(tile_CB2,(1,nR)) * \
        np.tile(tile_BP2,(1,nR)) * \
        np.tile(tile_PS2,(1,nR)) * \
        np.tile(tile_SD2,(1,nR))

    alpha_CBf = alpha_1C[ind_CBDR_C]
    alpha_BPf = alpha_CBf*alpha_CB[ind_CBDR_C,ind_CBDR_B]
    alpha_PSf = alpha_BPf*alpha_BP[ind_CBDR_B]
    alpha_SDf = alpha_PSf*alpha_PS[ind_CBDR_B]
    alpha_DRf = alpha_SDf*alpha_SD[ind_CBDR_B,ind_CBDR_D]
    
    
    #Mu
    mu = np.reshape(alpha_DRf*alpha_DR[ind_CBDR_D,ind_CBDR_R],(nC,nB,nD,nR))

    
    return [nC,nB,nD,nR,
            alpha_CBx,alpha_BPx,alpha_PSx,alpha_SDx,alpha_DRx,
            alpha_CBf,alpha_BPf,alpha_PSf,alpha_SDf,alpha_DRf,
            mu,
            chat_pow1_1C,chat_pow1_CB,chat_pow1_BP,
            chat_pow1_PS,chat_pow1_SD,chat_pow1_DR,
            chat_pow2_1C,chat_pow2_CB,chat_pow2_BP,
            chat_pow2_PS,chat_pow2_SD,chat_pow2_DR,
            zhat_1C,zhat_CB,zhat_BP,zhat_PS,zhat_SD,zhat_DR,
            rhat,
            pihat_pow1_1C,pihat_pow1_CB,pihat_pow1_BP,
            pihat_pow1_PS,pihat_pow1_SD,pihat_pow1_DR,
            pihat_pow2_1C,pihat_pow2_CB,pihat_pow2_BP,
            pihat_pow2_PS,pihat_pow2_SD,pihat_pow2_DR,
            ubar_1C,ubar_CB,ubar_BP,ubar_PS,ubar_SD,ubar_DR,
            ind_C___C,
            ind_CB__C,ind_CB__B,
            ind_CBD_C,ind_CBD_B,ind_CBD_D,
            ind_CBDR_C,ind_CBDR_B,ind_CBDR_D,ind_CBDR_R,
            prob_low,prob_high,
            theta,
            lambda_minus,lambda_plus]


def CreateRandomNetwork(nC,nB,nD,nR,seed):

    np.random.seed(seed)

    nP = nS = nB

    alpha_1C = .9+.1*np.random.rand(nC)
    alpha_CB = .9+.1*np.random.rand(nC,nB)
    alpha_BP = .9+.1*np.random.rand(nP)
    alpha_PS = .9+.1*np.random.rand(nS)
    alpha_SD = .9+.1*np.random.rand(nS,nD)
    alpha_DR = .9+.1*np.random.rand(nD,nR)

    chat_pow1_1C = 10.+10.*np.random.rand(nC)
    chat_pow1_CB = .5+3.5*np.random.rand(nC,nB)
    chat_pow1_BP = 1.+5.*np.random.rand(nP)
    chat_pow1_PS = 2.+8.*np.random.rand(nS)
    chat_pow1_SD = .5+2.*np.random.rand(nS,nD)
    chat_pow1_DR = .5+6.*np.random.rand(nD,nR)

    chat_pow2_1C = 5.+5.*np.random.rand(nC)
    chat_pow2_CB = .5+1.*np.random.rand(nC,nB)
    chat_pow2_BP = 1.+3.*np.random.rand(nP)
    chat_pow2_PS = .5+.5*np.random.rand(nS)
    chat_pow2_SD = 0.+1.*np.random.rand(nS,nD)
    chat_pow2_DR = .3+1.*np.random.rand(nD,nR)

    zhat_1C = .6+.3*np.random.rand(nC)
    zhat_CB = .5+.4*np.random.rand(nC,nB)
    zhat_BP = .4+.5*np.random.rand(nP)
    zhat_PS = .3+.5*np.random.rand(nS)
    zhat_SD = .2+.3*np.random.rand(nS,nD)
    zhat_DR = .3+.6*np.random.rand(nD,nR)

    pihat_pow1_1C = .5+1.*np.random.rand(nC)
    pihat_pow1_CB = .5+3.*np.random.rand(nC,nB)
    pihat_pow1_BP = 10.+15.*np.random.rand(nP)
    pihat_pow1_PS = 1.+2.*np.random.rand(nS)
    pihat_pow1_SD = .5+2.*np.random.rand(nS,nD)
    pihat_pow1_DR = .8+2.5*np.random.rand(nD,nR)

    pihat_pow2_1C = .5+.5*np.random.rand(nC)
    pihat_pow2_CB = .5+2.*np.random.rand(nC,nB)
    pihat_pow2_BP = 5.+5.*np.random.rand(nP)
    pihat_pow2_PS = 2.+6.*np.random.rand(nS)
    pihat_pow2_SD = .8+2.*np.random.rand(nS,nD)
    pihat_pow2_DR = .4+2.*np.random.rand(nD,nR)

    prob_low = 2.+48.*np.random.rand(nR)
    prob_high = 3.+17.*np.random.rand(nR)+prob_low

    lambda_minus = 2500.+1000.*np.random.rand(nR)
    lambda_plus = 25+50.*np.random.rand(nR)

    rhat = 1.+1.5*np.random.rand(nC)

    #all random networks are resdesigns from scratch
    ubar_1C = np.zeros((nC,))
    ubar_CB = np.zeros((nC,nB))
    ubar_BP = np.zeros((nB,))
    ubar_PS = np.zeros((nB,))
    ubar_SD = np.zeros((nB,nD))
    ubar_DR = np.zeros((nD,nR))

    theta = .5+.5*np.random.rand()

    #Helper Arguments

    #Index Lists for Fast Slicing
    ind_C___C = np.arange(nC)
    ind_CB__C = np.tile(np.arange(nC),(nB,1)).T.flatten()
    ind_CB__B = np.tile(np.arange(nB),nC)
    ind_CBD_C = np.tile(np.arange(nC),(nB*nD,1)).T.flatten()
    ind_CBD_B = np.tile(np.tile(np.arange(nB),(nD,1)).T.flatten(),nC)
    ind_CBD_D = np.tile(np.arange(nD),nC*nB)
    ind_CBDR_C = np.tile(np.arange(nC),(nB*nD*nR,1)).T.flatten()
    ind_CBDR_B = np.tile(np.tile(np.arange(nB),(nD*nR,1)).T.flatten(),nC)
    ind_CBDR_D = np.tile(np.tile(np.arange(nD),(nR,1)).T.flatten(),nC*nB)
    ind_CBDR_R = np.tile(np.arange(nR),nC*nB*nD)

    #Alpha Values for Both Path and Link Computation
    tile_1C = np.rollaxis(alpha_1C[ind_CB__C][None][None],2)
    tile_CB = np.rollaxis(alpha_CB[ind_CB__C,ind_CB__B][None][None],2)
    tile_BP = np.rollaxis(alpha_BP[ind_CB__B][None][None],2)
    tile_PS = np.rollaxis(alpha_PS[ind_CB__B][None][None],2)

    tile_1C2 = np.rollaxis(alpha_1C[ind_CBD_C][None],1)
    tile_CB2 = np.rollaxis(alpha_CB[ind_CBD_C,ind_CBD_B][None],1)
    tile_BP2 = np.rollaxis(alpha_BP[ind_CBD_B][None],1)
    tile_PS2 = np.rollaxis(alpha_PS[ind_CBD_B][None],1)
    tile_SD2 = np.rollaxis(alpha_SD[ind_CBD_B,ind_CBD_D][None],1)

    alpha_CBx = np.tile(tile_1C,(1,nD,nR))
    alpha_BPx = np.tile(tile_1C,(1,nD,nR)) * np.tile(tile_CB,(1,nD,nR))
    alpha_PSx = alpha_BP
    alpha_SDx = np.tile(tile_1C,(1,nD,nR)) * \
        np.tile(tile_CB,(1,nD,nR)) * \
        np.tile(tile_BP,(1,nD,nR)) * \
        np.tile(tile_PS,(1,nD,nR))
    alpha_DRx = np.tile(tile_1C2,(1,nR)) * \
        np.tile(tile_CB2,(1,nR)) * \
        np.tile(tile_BP2,(1,nR)) * \
        np.tile(tile_PS2,(1,nR)) * \
        np.tile(tile_SD2,(1,nR))

    alpha_CBf = alpha_1C[ind_CBDR_C]
    alpha_BPf = alpha_CBf*alpha_CB[ind_CBDR_C,ind_CBDR_B]
    alpha_PSf = alpha_BPf*alpha_BP[ind_CBDR_B]
    alpha_SDf = alpha_PSf*alpha_PS[ind_CBDR_B]
    alpha_DRf = alpha_SDf*alpha_SD[ind_CBDR_B,ind_CBDR_D]

    #Mu
    mu = np.reshape(alpha_DRf*alpha_DR[ind_CBDR_D,ind_CBDR_R],(nC,nB,nD,nR))

    return [nC,nB,nD,nR,
            alpha_CBx,alpha_BPx,alpha_PSx,alpha_SDx,alpha_DRx,
            alpha_CBf,alpha_BPf,alpha_PSf,alpha_SDf,alpha_DRf,
            mu,
            chat_pow1_1C,chat_pow1_CB,chat_pow1_BP,
            chat_pow1_PS,chat_pow1_SD,chat_pow1_DR,
            chat_pow2_1C,chat_pow2_CB,chat_pow2_BP,
            chat_pow2_PS,chat_pow2_SD,chat_pow2_DR,
            zhat_1C,zhat_CB,zhat_BP,zhat_PS,zhat_SD,zhat_DR,
            rhat,
            pihat_pow1_1C,pihat_pow1_CB,pihat_pow1_BP,
            pihat_pow1_PS,pihat_pow1_SD,pihat_pow1_DR,
            pihat_pow2_1C,pihat_pow2_CB,pihat_pow2_BP,
            pihat_pow2_PS,pihat_pow2_SD,pihat_pow2_DR,
            ubar_1C,ubar_CB,ubar_BP,ubar_PS,ubar_SD,ubar_DR,
            ind_C___C,
            ind_CB__C,ind_CB__B,
            ind_CBD_C,ind_CBD_B,ind_CBD_D,
            ind_CBDR_C,ind_CBDR_B,ind_CBDR_D,ind_CBDR_R,
            prob_low,prob_high,
            theta,
            lambda_minus,lambda_plus]
