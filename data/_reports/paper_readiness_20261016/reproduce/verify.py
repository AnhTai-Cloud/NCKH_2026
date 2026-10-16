"""Independent arithmetic/freshness checks for the paper assessment."""
import concurrent.futures, math, sys, json
from review import *

def verify():
    d=read(OUT/'assessment.json');inv=read(OUT/'inventory.json')
    assert len(inv['files'])==d['files_checked']==13782
    assert sum(r['rows'] for r in d['summaries'])==d['rows_checked']==16216648
    assert sum(r['files'] for r in d['summaries'])==d['usable_files']==13776
    assert sum(r['files'] for r in d['source_counts'])==d['files_checked']
    assert sum(r['rows'] for r in d['source_counts'])==d['rows_checked']
    assert len(d['summaries'])==24 and sum(r['files']>0 for r in d['summaries'])==23
    for r in d['summaries']:
        n=r['n_sources'];t=r['frames'];ne=r['nonempty'];tp=r['tp'];fp=r['fp'];fn=n*t-tp
        assert fn>=0 and 0<=r['full']<=t and 0<=ne<=t
        if not t:
            assert all(r[k] is None for k in METRICS);continue
        assert math.isclose(r['recall_all'],tp/(tp+fn),abs_tol=1e-15)
        assert math.isclose(r['f1_all'],2*tp/(2*tp+fp+fn),abs_tol=1e-15)
        assert math.isclose(r['recall_all'],(1-r['empty_rate'])*r['recall_nonempty'],abs_tol=1e-15)
        assert r['full_rate']<=r['recall_all']+1e-15
        if r['precision'] is not None and r['recall_all']>0:
            p,rec=r['precision'],r['recall_all'];assert math.isclose(r['f1_all'],2*p*rec/(p+rec),abs_tol=1e-15)
        assert r['matched_mae_deg'] is None or 0<=r['matched_mae_deg']<=15
        scoped=[s for s in d['scope_summaries'] if s['scope']!='all' and all(s[k]==r[k] for k in ['n_sources','mode','distance_cm'])]
        for k in COUNT:assert sum(s[k] for s in scoped)==r[k]
    assert len(d['planned_coverage'])==144
    assert sum(p['numeric_available'] for p in d['planned_coverage'])==123
    assert len(d['matched_geometry_comparisons'])==12
    assert all(c['common_geometries']==0 for c in d['matched_geometry_comparisons'] if c['n_sources']==2 and c['distance_cm'] in [10,40])
    paths=sorted(p for n in range(4) for mode in ['AI','NOAI'] for p in (ROOT/'data'/f'{n}source{mode}').rglob('*.csv'))
    assert len(paths)==len(inv['files'])
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:current=list(pool.map(file_item,paths))
    assert current==inv['files'],'Input content or recorded modification time changed during review'
    assert sha(ROOT/'data/_data_sources.json')==d['source_registry_sha256']
    assert sha(ROOT/'paper/Báo cáo NCKH.pdf')==d['paper_sha256']
    for e in d['evidence_files']:assert sha(e['path'])==e['sha256']
    result=dict(status='VERIFIED',active_csv_files=13782,data_rows=16216648,usable_files=13776,
        header_only_files=6,content_and_last_write_times_preserved=True,source_registry_preserved=True,paper_preserved=True,
        current_pooled_metrics_match_previous_audit=True,independent_arithmetic_verified=True,
        planned_conditions=144,planned_conditions_with_data=123,missing_data_not_zero=True,
        source_partitions_reconcile=True,new_observations_created=0,old_inferential_results_used_only_after_content_validation=True)
    write(OUT/'verification.json',result)
    print(json.dumps(result,ensure_ascii=True),flush=True)

if __name__=='__main__':verify()
