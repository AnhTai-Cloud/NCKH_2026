"""Exploratory clustered inference. No test result is used to edit observations."""
import gzip,collections,itertools,math,json,argparse
from common import *
from scipy.special import gammaln,logsumexp

def runs_conditional_p(n1,n0,observed):
    """Exact conditional binary-runs distribution, two-sided by distance from its expectation."""
    N=n1+n0;rv=np.arange(2,min(N,2*min(n1,n0)+1)+1);k=rv//2
    def lc(n,k):
        k=np.asarray(k);valid=(k>=0)&(k<=n);out=np.full(k.shape,-np.inf)
        out[valid]=gammaln(n+1)-gammaln(k[valid]+1)-gammaln(n-k[valid]+1)
        return out
    denominator=float(gammaln(N+1)-gammaln(n1+1)-gammaln(n0+1))
    even=np.log(2)+lc(n1-1,k-1)+lc(n0-1,k-1)
    odd=np.logaddexp(lc(n1-1,k)+lc(n0-1,k-1),lc(n1-1,k-1)+lc(n0-1,k))
    logprob=np.where(rv%2==0,even,odd)-denominator
    expected=1+2*n1*n0/N;extreme=abs(rv-expected)>=abs(observed-expected)-1e-10
    logp=min(0.,float(logsumexp(logprob[extreme])))
    return max(float(np.exp(logp)),float(np.finfo(float).tiny)),logp

def lines(path):
    with gzip.open(path,'rt',encoding='utf-8') as stream:
        for line in stream:yield json.loads(line)
def sum_record(rows):
    totals={k:sum(r.get(k,0) for r in rows) for k in COUNT};n=rows[0]['n_sources']
    return dict(n_sources=n,files=len(rows),rows=sum(r['rows'] for r in rows),**totals,**metrics(totals,n))
def key_geo(r):return tuple(sorted(r['truth'])) if r['truth'] else ()
def group(rows,keys):
    groups=collections.defaultdict(list)
    for r in rows:groups[tuple(key_geo(r) if k=='geometry' else r[k] for k in keys)].append(r)
    return groups
def agg_rows(rows,keys):return [dict(zip(keys,k),**sum_record(v)) for k,v in sorted(group(rows,keys).items(),key=lambda p:str(p[0]))]
def geomeans(rows):return {k:sum_record(v) for k,v in group(rows,['geometry']).items()}
def cluster_ci(rows,key,B=2000):
    units=list(group(rows,['geometry']).values());unit='geometry'
    if len(units)==1:units=[[r] for r in rows];unit='CSV_within_one_geometry'
    if len(units)==1:return dict(unit='single_file_moving_blocks',clusters=1,**rows[0]['bootstrap_ci'])
    a=np.array([[sum(r[c] for r in unit_rows) for c in COUNT] for unit_rows in units]);n=rows[0]['n_sources'];rng=np.random.default_rng(seed('cluster-CI',key))
    result={k:[] for k in METRICS}
    for begin in range(0,B,100):
        draws=a[rng.integers(0,len(a),size=(min(100,B-begin),len(a)))].sum(axis=1)
        for v in draws:
            m=metrics(dict(zip(COUNT,v)),n)
            for k in METRICS:
                if m[k] is not None:result[k].append(m[k])
    return dict(unit=unit,clusters=len(units),replicates=B,intervals={k:dict(low=float(np.quantile(v,.025)),high=float(np.quantile(v,.975))) if v else None for k,v in result.items()})
def ks_stat(x,y):
    support=np.unique(np.concatenate([x,y]));difference=np.searchsorted(np.sort(x),support,side='right')/len(x)-np.searchsorted(np.sort(y),support,side='right')/len(y)
    return float(np.max(abs(difference)))
def permutation_two(x,y,func,key,B=1999):
    x=np.asarray(x);y=np.asarray(y);observed=func(x,y);allv=np.concatenate([x,y]);N=len(allv);nx=len(x);total=math.comb(N,nx)
    if total<=B:
        values=[]
        for indices in itertools.combinations(range(N),nx):
            mask=np.zeros(N,bool);mask[list(indices)]=True;values.append(func(allv[mask],allv[~mask]))
        return observed,float(np.mean(np.asarray(values)>=observed-1e-12)),total,'EXACT_LABEL_PERMUTATION'
    rng=np.random.default_rng(seed('permutation',key));extreme=0
    for _ in range(B):
        order=rng.permutation(N);extreme+=func(allv[order[:nx]],allv[order[nx:]])>=observed-1e-12
    return observed,(extreme+1)/(B+1),B,'MONTE_CARLO_LABEL_PERMUTATION'
def kuiper_hist(x,y):
    difference=np.cumsum(x.mean(axis=0)-y.mean(axis=0));return float(difference.max()-difference.min())

def run(stage='before'):
    config=read(WORK/'config.json');out=Path(config['output'])
    allrows=list(lines(out/f'file_features_{stage}.jsonl.gz'))
    rows=[r for r in allrows if r['frames']>0 and r['truth'] is not None and not r['invalid_rows'] and not r['issues'].get('CONFIGURATION_CHANGES')]
    summary=[];columns_stats=[]
    for tag,keys in [('all',['n_sources','mode','distance_cm']),('origin',['n_sources','mode','distance_cm','origin']),('cohort',['n_sources','mode','distance_cm','origin','cohort'])]:
        for key,subset in sorted(group(rows,keys).items(),key=lambda p:str(p[0])):
            row={'scope':tag,**dict(zip(keys,key)),**sum_record(subset)};row['bootstrap_ci']=cluster_ci(subset,(tag,key))
            row['file_equal_means']={k:float(np.mean([r[k] for r in subset if r[k] is not None])) if any(r[k] is not None for r in subset) else None for k in METRICS}
            gm=list(geomeans(subset).values());row['geometry_equal_means']={k:float(np.mean([r[k] for r in gm if r[k] is not None])) if any(r[k] is not None for r in gm) else None for k in METRICS}
            summary.append(row)
            for metric in METRICS:columns_stats.append(dict(scope=tag,**dict(zip(keys,key)),metric=metric,**describe([r[metric] for r in subset if r[metric] is not None])))
    geometry=agg_rows(rows,['n_sources','mode','distance_cm','origin','cohort','geometry'])
    lengths=collections.Counter(r['rows'] for r in allrows)
    tests=[];comparisons=[];skipped=[]
    for r in allrows:
        for test in r['sequence_tests']:
            test=dict(test);n1=int(r['full'] if test['series']=='full_detection' else r['nonempty']);n0=int(r['frames'])-n1
            p,logp=runs_conditional_p(n1,n0,test['runs']);test.update(test='EXACT_CONDITIONAL_BINARY_RUNS',p=p,log_p=logp,calibration='Exact distribution conditional on observed counts; two-sided distance from expected runs')
            tests.append(dict(scope='WITHIN_FILE_IID_DIAGNOSTIC',path=r['path'],n_sources=r['n_sources'],mode=r['mode'],distance_cm=r['distance_cm'],origin=r['origin'],**test))
    def add_test(**kwargs):
        kwargs.setdefault('scope','EXPLORATORY_CONDITIONAL_ON_INDEPENDENT_GEOMETRIES');tests.append(kwargs)
    # Compare length and documented-origin cohorts under identical geometry; do not compare unmatched angle distributions.
    for config_key,subset in group(rows,['n_sources','mode','distance_cm','geometry']).items():
        for grouping in ['origin','row_length_200_300']:
            cohorts=collections.defaultdict(list)
            for r in subset:
                if grouping=='row_length_200_300' and r['rows'] not in [200,300]:continue
                cohorts[str(r['rows']) if grouping=='row_length_200_300' else r['origin']].append(r)
            for a,b in itertools.combinations(sorted(cohorts),2):
                left,right=cohorts[a],cohorts[b]
                if min(len(left),len(right))<3:
                    skipped.append(dict(test='KS_MWU_KUIPER',configuration=config_key,grouping=grouping,a=a,b=b,n_a=len(left),n_b=len(right),reason='Fewer than three CSV replicates in a group; insufficient independent replication'))
                    continue
                context=dict(configuration=config_key,grouping=grouping,a=a,b=b,unit='CSV within exact n/mode/distance/unordered target geometry',n_a=len(left),n_b=len(right))
                for metric in ['recall_all','full_rate','matched_mae_deg','empty_rate']:
                    x=np.array([r[metric] for r in left if r[metric] is not None]);y=np.array([r[metric] for r in right if r[metric] is not None])
                    if min(len(x),len(y))<3:continue
                    small=min(len(x),len(y))<8
                    method=stats.PermutationMethod(n_resamples=1999,rng=np.random.default_rng(seed('mwu',config_key,grouping,a,b,metric))) if small else 'asymptotic'
                    u=stats.mannwhitneyu(x,y,method=method)
                    add_test(test='MANN_WHITNEY_U',metric=metric,statistic=float(u.statistic),p=float(u.pvalue),effect_rank_biserial=float(2*u.statistic/(len(x)*len(y))-1),
                        validity=('Tie-aware label permutation for small groups' if small else 'Tie-corrected asymptotic')+'; unknown session independence limits inference',**context)
                    D,p,reps,method=permutation_two(x,y,ks_stat,('ks',config_key,grouping,a,b,metric))
                    add_test(test='KS_D_PERMUTATION',metric=metric,statistic=D,p=p,replicates=reps,calibration=method,
                        validity='No continuous-KS asymptotic p-value: tied/discrete file statistics use label permutation',**context)
                lh=np.array([r['tp_error_histogram'] for r in left if sum(r['tp_error_histogram'])]);rh=np.array([r['tp_error_histogram'] for r in right if sum(r['tp_error_histogram'])])
                if min(len(lh),len(rh))>=3:
                    lh=lh/lh.sum(axis=1,keepdims=True);rh=rh/rh.sum(axis=1,keepdims=True)
                    D,p,reps,method=permutation_two(lh,rh,kuiper_hist,('kuiper',config_key,grouping,a,b))
                    add_test(test='CIRCULAR_KUIPER_CLUSTER_PERMUTATION',metric='signed matched error circle, file-normalized histogram',statistic=D,p=p,replicates=reps,calibration=method,**context)
        # Nonparametric replicate comparison: KW is appropriate only with three disjoint replicate cohorts.
        length_groups=group(subset,['rows']);eligible=[v for v in length_groups.values() if len(v)>=3]
        if len(eligible)>=3:
            for metric in ['recall_all','full_rate','matched_mae_deg']:
                vals=[[r[metric] for r in v if r[metric] is not None] for v in eligible]
                if min(map(len,vals))>=3 and len(set(itertools.chain.from_iterable(vals)))>1:
                    k=stats.kruskal(*vals);add_test(test='KRUSKAL_WALLIS_INDEPENDENT_CSV_COHORTS',metric=metric,configuration=config_key,statistic=float(k.statistic),p=float(k.pvalue),validity='Exploratory; recording session identities are unavailable')
    # Matched-geometry AI/NOAI contrasts, separately by source evidence and generation cohort.
    for key,subset in group(rows,['n_sources','distance_cm','origin','cohort']).items():
        modes=group(subset,['mode']);left=geomeans(modes.get(('NOAI',),[]));right=geomeans(modes.get(('AI',),[]));common=sorted(set(left)&set(right))
        for metric in METRICS:
            pairs=[(left[k][metric],right[k][metric]) for k in common if left[k][metric] is not None and right[k][metric] is not None]
            if len(pairs)<5:continue
            x,y=np.array(pairs).T;delta=y-x
            method=stats.PermutationMethod(n_resamples=1999,rng=np.random.default_rng(seed('wilcoxon-mode',key,metric))) if len(pairs)<30 else 'asymptotic'
            w=stats.wilcoxon(delta,zero_method='wilcox',method=method) if np.any(delta) else None
            add_test(test='WILCOXON_MATCHED_GEOMETRY_AI_NOAI',metric=metric,configuration=key,statistic=float(w.statistic) if w else 0.,p=float(w.pvalue) if w else 1.,
                paired_geometries=len(pairs),mean_delta=float(delta.mean()),median_delta=float(np.median(delta)),validity='Paired conditions, not necessarily simultaneous recordings; differences assumed symmetric')
            rng=np.random.default_rng(seed('paired-CI',key,metric));draw=delta[rng.integers(0,len(delta),size=(2000,len(delta)))].mean(axis=1)
            comparisons.append(dict(configuration=key,metric=metric,paired_geometries=len(pairs),ai_minus_noai=float(delta.mean()),ci_low=float(np.quantile(draw,.025)),ci_high=float(np.quantile(draw,.975))))
    # Distance comparisons: report nominal KW, but use repeated-condition Friedman/Wilcoxon as primary.
    distance=[]
    for key,subset in group(rows,['n_sources','mode','origin','cohort']).items():
        ds=group(subset,['distance_cm']);geo={d[0]:geomeans(v) for d,v in ds.items()};distances=sorted(geo)
        if len(distances)<2:continue
        for metric in ['recall_all','full_rate','matched_mae_deg','precision']:
            values=[[v[metric] for v in geo[d].values() if v[metric] is not None] for d in distances]
            if min(map(len,values))>=5 and len(set(itertools.chain.from_iterable(values)))>1:
                kw=stats.kruskal(*values)
                add_test(test='KRUSKAL_WALLIS_DISTANCE_NOMINAL_ONLY',configuration=key,metric=metric,statistic=float(kw.statistic),p=None,p_nominal=float(kw.pvalue),
                    scope='DESCRIPTIVE_NOT_INFERENTIAL',validity='Repeated geometries violate independent-group assumption; use matched tests below')
            common=set.intersection(*(set(geo[d]) for d in distances))
            full=[g for g in sorted(common) if all(geo[d][g][metric] is not None for d in distances)]
            if len(distances)>=3 and len(full)>=5:
                arrays=[np.array([geo[d][g][metric] for g in full]) for d in distances]
                if np.any(np.ptp(np.stack(arrays),axis=0)>0):
                    f=stats.friedmanchisquare(*arrays)
                    add_test(test='FRIEDMAN_MATCHED_DISTANCE',configuration=key,metric=metric,distances_cm=distances,statistic=float(f.statistic),p=float(f.pvalue),paired_geometries=len(full),validity='Large-sample chi-square approximation; exact geometry ties retained')
            for d1,d2 in itertools.combinations(distances,2):
                common=sorted(set(geo[d1])&set(geo[d2]));pairs=[(geo[d1][g][metric],geo[d2][g][metric]) for g in common if geo[d1][g][metric] is not None and geo[d2][g][metric] is not None]
                if len(pairs)<5:continue
                x,y=np.array(pairs).T;delta=y-x
                method=stats.PermutationMethod(n_resamples=1999,rng=np.random.default_rng(seed('wilcoxon-distance',key,metric,d1,d2))) if len(pairs)<30 else 'asymptotic'
                w=stats.wilcoxon(delta,method=method) if np.any(delta) else None
                add_test(test='WILCOXON_MATCHED_DISTANCE',configuration=key,metric=metric,distance_a_cm=d1,distance_b_cm=d2,paired_geometries=len(pairs),
                    statistic=float(w.statistic) if w else 0.,p=float(w.pvalue) if w else 1.,mean_delta=float(delta.mean()),median_delta=float(np.median(delta)))
                distance.append(dict(configuration=key,metric=metric,distance_a_cm=d1,distance_b_cm=d2,paired_geometries=len(pairs),mean_delta=float(delta.mean()),
                    fraction_increase=float(np.mean(delta>0)),fraction_decrease=float(np.mean(delta<0))))
    # Correlation is descriptive: rates share counts, and MAE is conditional on detected TP.
    correlations=[]
    for key,subset in group(geometry,['n_sources','mode','distance_cm','origin','cohort']).items():
        for a,b in itertools.combinations(['precision','recall_all','full_rate','matched_mae_deg','empty_rate'],2):
            pairs=[(r[a],r[b]) for r in subset if r[a] is not None and r[b] is not None]
            if len(pairs)>=5:
                x,y=np.array(pairs).T
                if x.std()>0 and y.std()>0:correlations.append(dict(configuration=key,x=a,y=b,n_geometries=len(pairs),pearson=float(stats.pearsonr(x,y).statistic),spearman=float(stats.spearmanr(x,y).statistic),interpretation='Descriptive, not causal; ratios share numerators/denominators'))
    # Within-condition robust outlier flags never remove or alter records.
    outliers=[]
    for key,subset in group(rows,['n_sources','mode','distance_cm','geometry','origin','cohort']).items():
        if len(subset)<5:continue
        for metric in ['recall_all','full_rate','matched_mae_deg']:
            rr=[r for r in subset if r[metric] is not None];v=np.array([r[metric] for r in rr]);med=np.median(v);mad=np.median(abs(v-med))
            if mad>0:
                for r,z in zip(rr,.67448975*(v-med)/mad):
                    if abs(z)>3.5:outliers.append(dict(path=r['path'],metric=metric,value=r[metric],robust_z=float(z),configuration=key,action='FLAG_ONLY'))
    valid=[i for i,t in enumerate(tests) if t.get('p') is not None and math.isfinite(t['p'])]
    adjusted=stats.false_discovery_control([tests[i]['p'] for i in valid],method='by')
    for i,q in zip(valid,adjusted):tests[i].update(q_by=float(q),reject_iid_or_equal_distribution_at_005=bool(q<.05))
    nominal=[i for i,t in enumerate(tests) if t.get('p_nominal') is not None and math.isfinite(t['p_nominal'])]
    if nominal:
        for i,q in zip(nominal,stats.false_discovery_control([tests[i]['p_nominal'] for i in nominal],method='by')):tests[i]['q_nominal_by_not_valid_for_repeated_groups']=float(q)
    for test in tests:
        if test.get('p') is not None and not math.isfinite(test['p']):test.update(p=None,inference_status='UNAVAILABLE_NUMERIC_OR_DEGENERATE_TEST_NO_CONCLUSION')
    for i,t in enumerate(tests):t['test_id']=i+1
    result=dict(stage=stage,active_files=len(allrows),analysable_files=len(rows),rows=sum(r['rows'] for r in allrows),
        files_by_origin=dict(collections.Counter(r['origin'] for r in allrows)),files_by_frame_count=dict(sorted(lengths.items())),
        summary=summary,geometry=geometry,descriptive_file_metric_distributions=columns_stats,comparisons=comparisons,distance=distance,correlations=correlations,
        robust_outliers=outliers,tests=tests,skipped_tests=skipped,tests_count=len(tests),inferential_tests_count=len(valid),
        multiplicity='Global Benjamini-Yekutieli FDR .05 across all valid exploratory and IID-null p-values; nominal KW excluded',
        limitations=['No acquisition-session IDs, audio waveform, per-source activity labels, SNR or clock timestamps. Geometry/CSV-level inference is conditional and exploratory.',
          'Frame runs tests test IID exchangeability itself. Frame observations are not treated as independent replicates for performance comparisons.',
          'Moving-block and geometry bootstrap assume local stationarity and exchangeability of chosen clusters; these assumptions cannot be proven from CSV alone.',
          'Synthetic versus unresolved origin is classified only by content-linked source evidence; no p-value or pattern establishes genuine measurement.',
          'MAE includes matched true-positive directions within 15 degrees; row mean_error uses all complete-count assigned directions without that cutoff.',
          'Distance does not have to be monotone for every layout or matched-TP MAE. Unknown acoustics cannot be diagnosed uniquely from directions alone.'])
    write(out/f'statistics_{stage}.json',result)
    print(json.dumps(dict(stage=stage,files=len(allrows),rows=result['rows'],tests=len(tests),inference=len(valid),rejections=sum(t.get('q_by',1)<.05 for t in tests))),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('stage',choices=['before','after']);args=p.parse_args();run(args.stage)
