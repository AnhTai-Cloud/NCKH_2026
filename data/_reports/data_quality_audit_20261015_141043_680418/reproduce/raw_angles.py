"""Temporal statistics for every raw bearing, including unmatched/false directions."""
import csv,gzip,collections,itertools
from concurrent.futures import ProcessPoolExecutor
from common import *

def worker(args):
    cfg,items=args;results=[]
    for item in items:
        with (Path(cfg['backup'])/item['path']).open(encoding='utf-8-sig',newline='') as stream:
            seq=[tuple(int(v) for v in r['raw_angles'].split(';') if v.strip()) for r in csv.DictReader(stream)]
        T=len(seq);counts=np.array(list(map(len,seq)));a=np.full((T,3),np.nan)
        for i,v in enumerate(seq):a[i,:len(v)]=v
        z=np.full(T,complex(np.nan,np.nan));nonempty=counts>0
        if np.any(nonempty):z[nonempty]=np.nansum(np.exp(1j*np.deg2rad(a[nonempty])),axis=1)/counts[nonempty]
        steps=[];assignments=0
        for p in [1,2,3]:
            for q in [1,2,3]:
                index=np.flatnonzero((counts[:-1]==p)&(counts[1:]==q))
                if not len(index):continue
                left,right=a[index,:p],a[index+1,:q]
                if p>q:left,right=right,left
                u,v=left.shape[1],right.shape[1]
                perms=np.array(list(itertools.permutations(range(v),u)),int)
                delta=abs((left[:,None,:]-right[:,perms]+180)%360-180)
                best=delta.sum(axis=2).argmin(axis=1);chosen=delta[np.arange(len(index)),best,:]
                steps.extend(chosen.ravel().tolist());assignments+=chosen.size
        result=dict(path=item['path'],frames=T,adjacent_nearest_direction_pairs=assignments,raw_minimum_assignment_step_statistics=describe(steps),
            zero_step_fraction=float(np.mean(np.asarray(steps)==0)) if steps else None,
            raw_mean_unit_vector_real_acf=acf(z.real),raw_mean_unit_vector_imag_acf=acf(z.imag),
            frames_with_near_zero_resultant=int(np.sum(abs(z)<1e-10)),
            interpretation='All raw directions, including unmatched ones. Frame-pair matching minimizes total circular displacement; it does not establish source identity. Unit-vector ACF omits empty endpoint pairs without closing time gaps.')
        results.append(result)
    return results

def main():
    cfg=read(WORK/'config.json');out=Path(cfg['output']);items=cfg['files'];chunks=[(cfg,items[i:i+160]) for i in range(0,len(items),160)];done=0
    with gzip.open(out/'raw_angle_temporal_features.jsonl.gz','wt',encoding='utf-8') as dst,ProcessPoolExecutor(max_workers=4) as pool:
        for results in pool.map(worker,chunks):
            for r in results:dst.write(json.dumps(clean(r),ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n')
            done+=len(results)
            if done%3200==0 or done==len(items):print(f'All-raw circular temporal statistics {done}/{len(items)} CSV',flush=True)
    write(out/'raw_angle_temporal_verification.json',dict(files=done,includes_false_and_unmatched_directions=True,observations_edited=False,
        before_after_equality_basis='All per-file semantic hashes and core observation values were verified unchanged after header-only corrections'))

if __name__=='__main__':main()
