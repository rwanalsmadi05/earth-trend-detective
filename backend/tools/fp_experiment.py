import sys, warnings; sys.path.insert(0,'.'); sys.path.insert(0,'tests'); warnings.filterwarnings('ignore')
import numpy as np, pandas as pd, pymannkendall as mk
from app import stats
from test_stats import series

def annual(a):  # annual mean of monthly anomalies, >=6 months
    g=a.groupby(a.index.year); m=g.mean(); c=g.count(); return m[c>=6].to_numpy()
def pv(f,v):
    try: p=f(v).p
    except Exception: return np.nan
    return p
M={ # before: monthly
 'BEFORE monthly HR default lags':('m',lambda v:mk.hamed_rao_modification_test(v)),
 'interim monthly HR lag=12':('m',lambda v:mk.hamed_rao_modification_test(v,lag=12)),
 # after: annual means
 'annual HR default lags':('a',lambda v:mk.hamed_rao_modification_test(v)),
 'annual HR lag=5':('a',lambda v:mk.hamed_rao_modification_test(v,lag=5)),
 'annual TFPW':('a',lambda v:mk.trend_free_pre_whitening_modification_test(v)),
 'annual Yue-Wang':('a',lambda v:mk.yue_wang_modification_test(v)),
 'annual plain MK':('a',lambda v:mk.original_test(v)),
}
def run(phi,slope=0.0):
    P={k:[] for k in M}; P['IMPLEMENTED stats.trend()']=[]
    for s in range(300,400):
        an=stats.deseasonalize(series(slope,noise=0.4,seed=s,phi=phi)).dropna()
        ann=annual(an); mon=an.to_numpy()
        for k,(kind,f) in M.items(): P[k].append(pv(f, mon if kind=='m' else ann))
        P['IMPLEMENTED stats.trend()'].append(stats.trend(series(slope,noise=0.4,seed=s,phi=phi)).p)
    return {k:(np.mean(np.array(x)<0.05), np.isnan(x).mean()) for k,x in P.items()}
phis=(0.0,0.6,0.9)
res={ph:run(ph) for ph in phis}; pw=run(0.6,0.01)
print('False-positive rate, 100 seeds, nominal 5%  (NaN share in brackets)')
print(f'{"method":34s}'+''.join(f'phi={p:<5}  ' for p in phis)+'| power slope=.01/yr phi=.6')
for k in list(M)+['IMPLEMENTED stats.trend()']:
    print(f'{k:34s}'+''.join(f'{res[p][k][0]:4.0%} ({res[p][k][1]:.0%})  ' for p in phis)+f'| {pw[k][0]:4.0%}')
