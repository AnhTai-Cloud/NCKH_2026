import sys, json, hashlib, math, itertools, os
from pathlib import Path
from functools import lru_cache
ROOT=Path(os.environ.get('DOA_AUDIT_ROOT',Path(__file__).resolve().parents[2]))
WORK=Path(os.environ.get('DOA_AUDIT_WORK',Path(__file__).resolve().parent))
sys.path[:0]=[str(ROOT/'tmp/data_quality_deps'),str(ROOT/'tmp/analysis_plot_deps'),str(ROOT/'Python')]
import numpy as np
from scipy import stats
import measure_doa as doa

def read(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def clean(value):
    if isinstance(value,dict):return {str(k):clean(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [clean(v) for v in value]
    if isinstance(value,np.ndarray):return clean(value.tolist())
    if isinstance(value,(np.integer,np.floating)):value=value.item()
    if isinstance(value,float) and not math.isfinite(value):return None
    return value
def write(path,obj):Path(path).write_text(json.dumps(clean(obj),ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')
def sha(path):
    with Path(path).open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def seed(*parts):return int.from_bytes(hashlib.sha256(repr((20261015,parts)).encode()).digest()[:8],'little')
def circ(a,b):return abs((a-b+180)%360-180)
def signed(a,b):return (a-b+180)%360-180
@lru_cache(maxsize=131072)
def matched(truth,det):return doa.match_sources(truth,det,15)
@lru_cache(maxsize=131072)
def optimal(truth,det):
    perms=list(itertools.permutations(det));totals=[sum(circ(a,t) for a,t in zip(p,truth)) for p in perms]
    minimum=min(totals)
    return tuple(p for p,v in zip(perms,totals) if v==minimum)
def describe(values):
    x=np.asarray(values,dtype=float);x=x[np.isfinite(x)]
    if not len(x):return dict(n=0,mean=None,median=None,variance=None,sd=None,min=None,q05=None,q25=None,q75=None,q95=None,max=None)
    return dict(n=len(x),mean=float(x.mean()),median=float(np.median(x)),variance=float(x.var(ddof=1)) if len(x)>1 else None,
        sd=float(x.std(ddof=1)) if len(x)>1 else None,min=float(x.min()),max=float(x.max()),
        **dict(zip(['q05','q25','q75','q95'],map(float,np.quantile(x,[.05,.25,.75,.95])))))
def circular(values):
    x=np.asarray(values,dtype=float);x=x[np.isfinite(x)]
    if not len(x):return dict(n=0,mean_deg=None,resultant=None,variance=None,sd_deg=None)
    z=np.exp(1j*np.deg2rad(x)).mean();r=float(abs(z))
    return dict(n=len(x),mean_deg=float(np.rad2deg(np.angle(z))) if r>1e-12 else None,resultant=r,variance=1-r,
        sd_deg=float(np.rad2deg(np.sqrt(-2*np.log(min(r,1))))) if r>0 else None)
COUNT=('frames','nonempty','tp','fp','error_sum','full','count_correct')
METRICS=('precision','recall_all','recall_nonempty','f1_all','f1_nonempty','matched_mae_deg','full_rate','empty_rate')
def metrics(c,n):
    t,ne,tp,fp,err,full,cc=[float(c.get(k,0)) for k in COUNT]
    div=lambda a,b:a/b if b else None
    return dict(precision=div(tp,tp+fp),recall_all=div(tp,n*t),recall_nonempty=div(tp,n*ne),
        f1_all=div(2*tp,tp+fp+n*t),f1_nonempty=div(2*tp,tp+fp+n*ne),matched_mae_deg=div(err,tp),
        full_rate=div(full,t),empty_rate=div(t-ne,t),count_accuracy=div(cc,t))
def acf(x,lags=(1,2,3,5,10,20,30)):
    x=np.asarray(x,dtype=float);out={}
    for lag in lags:
        if len(x)<=lag:out[str(lag)]=None;continue
        a,b=x[:-lag],x[lag:];m=np.isfinite(a)&np.isfinite(b);a,b=a[m],b[m]
        out[str(lag)]=float(np.corrcoef(a,b)[0,1]) if len(a)>3 and a.std()>0 and b.std()>0 else None
    return out
def runs(values):
    if not len(values):return []
    out=[];start=0
    for i in range(1,len(values)+1):
        if i==len(values) or values[i]!=values[start]:
            out.append((start+1,i,i-start,values[start]));start=i
    return out
def bootstrap_counts(array,n,key,B=499):
    """Circular moving-block bootstrap; every replicate has exactly T frames."""
    a=np.asarray(array,float);t=len(a)
    if t<8:return dict(status='TOO_SHORT',replicates=0)
    y=a[:,2];rho=acf(y,tuple(range(1,min(31,t//4))))
    lag=next((int(k) for k,v in rho.items() if v is not None and abs(v)<.1),min(30,max(1,t//4)))
    length=min(max(int(np.ceil(t**(1/3))),lag),max(1,t//4))
    padded=np.concatenate([a,a[:length]],axis=0);prefix=np.concatenate([np.zeros((1,a.shape[1])),np.cumsum(padded,axis=0)])
    starts=np.arange(t);whole=prefix[starts+length]-prefix[starts]
    k=int(np.ceil(t/length));rem=t-(k-1)*length;tail=prefix[starts+rem]-prefix[starts]
    rng=np.random.default_rng(seed('file-bootstrap',key));samples=np.zeros((B,a.shape[1]))
    for begin in range(0,B,100):
        size=min(100,B-begin);idx=rng.integers(0,t,size=(size,k))
        samples[begin:begin+size]=whole[idx[:,:-1]].sum(axis=1)+tail[idx[:,-1]]
    draws=[]
    for row in samples:draws.append(metrics(dict(zip(COUNT,row)),n))
    result=dict(status='CONDITIONAL_STATIONARY_BLOCK_BOOTSTRAP',replicates=B,block_length=length)
    for name in METRICS:
        v=[r[name] for r in draws if r[name] is not None]
        result[name]=dict(low=float(np.quantile(v,.025)),high=float(np.quantile(v,.975)),valid_replicates=len(v)) if v else None
    return result
