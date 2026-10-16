"""Current data/paper assessment. Never writes or retimestamps active observations."""
import collections, concurrent.futures, csv, gzip, hashlib, json, os, re, sys
from pathlib import Path
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[2]
WORK=Path(__file__).resolve().parent
OUT=ROOT/'data/_reports/paper_readiness_20261016'
PREVIOUS=ROOT/'data/_reports/data_quality_audit_20261015_141043_680418'
sys.path[:0]=[str(ROOT/'tmp/data_quality_audit_20261015'),str(ROOT/'tmp/data_quality_deps'),str(ROOT/'tmp/analysis_plot_deps')]
from common import clean, read, write, sha, metrics, COUNT, METRICS, describe
from pypdf import PdfReader
import numpy as np

LABELS={'SYNTHETIC_DOCUMENTED':'Mô phỏng có hồ sơ','CAPTURE_RECORD_MATCH':'Khớp bản ghi thu cũ','UNVERIFIED':'Chưa xác minh'}
PLAN_GEOMETRIES={1:[(a,) for a in range(0,360,30)],2:[(0,45),(0,60),(0,90),(0,180)],3:[(0,120,240),(0,60,180)]}

def jl(path):
    with gzip.open(path,'rt',encoding='utf-8') as stream:
        for line in stream: yield json.loads(line)

def file_item(path):
    st=path.stat()
    return dict(path=path.relative_to(ROOT/'data').as_posix(),sha256=sha(path),bytes=st.st_size,
                last_write_utc=datetime.fromtimestamp(st.st_mtime,timezone.utc).isoformat(),
                last_write_local=datetime.fromtimestamp(st.st_mtime,ZoneInfo('Asia/Bangkok')).isoformat(),
                timestamp_role='Filesystem observation only; not acquisition time or origin evidence')

def inventory():
    OUT.mkdir(parents=True,exist_ok=True)
    cached={r['path']:r for r in jl(PREVIOUS/'audited_file_details.jsonl.gz')}
    paths=sorted(p for n in range(4) for mode in ('AI','NOAI') for p in (ROOT/'data'/f'{n}source{mode}').rglob('*.csv'))
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool: items=list(pool.map(file_item,paths))
    previous_registry=read(PREVIOUS/'installation.json')
    registry=ROOT/'data/_data_sources.json'
    manifest=dict(client_date='2026-10-16',timezone='Asia/Bangkok',files=items,files_checked=len(items),
        bytes_checked=sum(r['bytes'] for r in items),registry_sha256=sha(registry),
        previous_registry_sha256=previous_registry.get('main_registry_after_sha256'),
        unchanged=[r['path'] for r in items if r['path'] in cached and r['sha256']==cached[r['path']]['sha256']],
        changed=[r['path'] for r in items if r['path'] in cached and r['sha256']!=cached[r['path']]['sha256']],
        new=[r['path'] for r in items if r['path'] not in cached],
        removed=sorted(set(cached)-{r['path'] for r in items}),
        inputs_modified_by_review=False)
    write(OUT/'inventory.json',manifest)
    paper=ROOT/'paper/Báo cáo NCKH.pdf'
    reader=PdfReader(paper)
    pages=[dict(page=i+1,text=p.extract_text()) for i,p in enumerate(reader.pages)]
    write(WORK/'paper_pages.json',pages)
    write(OUT/'paper_evidence.json',dict(path=str(paper),sha256=sha(paper),pages=len(pages),
        relevant_pages=[p for p in pages if 49<=p['page']<=56 or p['page'] in [36,38,40,41,43,44,46,47,48]]))
    print(json.dumps({k:v for k,v in manifest.items() if k not in ['files','unchanged']},ensure_ascii=True),flush=True)
    print(json.dumps(dict(unchanged=len(manifest['unchanged']),paper_pages=len(pages),paper_sha256=sha(paper)),ensure_ascii=True),flush=True)

def grouped(rows,keys):
    result=collections.defaultdict(list)
    for r in rows:
        result[tuple(tuple(sorted(r['truth'])) if k=='geometry' else r[k] for k in keys)].append(r)
    return result

def summed(rows,n):
    totals={k:sum(r.get(k,0) for r in rows) for k in COUNT}
    return dict(files=len(rows),rows=sum(r['rows'] for r in rows),**totals,**metrics(totals,n))

def analyze():
    inv=read(OUT/'inventory.json')
    inv['previous_registry_sha256']=read(PREVIOUS/'installation.json')['main_registry_after_sha256']
    write(OUT/'inventory.json',inv)
    assert not inv['changed'] and not inv['new'] and not inv['removed'], 'Changed data must be re-audited before reusing prior statistical results'
    assert inv['registry_sha256']==inv['previous_registry_sha256']==sha(ROOT/'data/_data_sources.json')
    cached={r['path']:r for r in jl(PREVIOUS/'audited_file_details.jsonl.gz')}
    rows=[cached[item['path']] for item in inv['files']]
    assert all(cached[item['path']]['sha256']==item['sha256'] for item in inv['files'])
    usable=[r for r in rows if r['frames']>0 and r['truth'] and not r['invalid_rows']]
    previous_stats=read(PREVIOUS/'statistics_after.json')
    previous_summary={(r['n_sources'],r['mode'],r['distance_cm']):r for r in previous_stats['summary'] if r['scope']=='all'}
    by_config=grouped(usable,['n_sources','mode','distance_cm'])
    summaries=[]; source_summaries=[]; geometries=[]; planned=[]
    for n in (1,2,3):
        for mode in ('NOAI','AI'):
            for distance in (10,20,30,40):
                rr=by_config.get((n,mode,distance),[])
                geometry_groups=grouped(rr,['geometry'])
                origins=collections.Counter(r['origin'] for r in rr)
                required=PLAN_GEOMETRIES[n]
                present={k[0] for k in geometry_groups}
                summary=dict(n_sources=n,mode=mode,distance_cm=distance,**summed(rr,n),
                    geometries=len(present),source_files=dict(origins),
                    source_frames={k:sum(r['frames'] for r in rr if r['origin']==k) for k in origins},
                    planned_geometries_found=sum(g in present for g in required),planned_geometries_total=len(required),
                    missing_planned_geometries=[g for g in required if g not in present],
                    status='NUMERICALLY_AVAILABLE' if rr else 'NO_ACTIVE_DATA',
                    candidate_use='Descriptive current mixed dataset; acquisition/background/protocol evidence must be stated')
                if rr:
                    old=previous_summary[n,mode,float(distance)]
                    assert all(summary[k]==old[k] for k in [*COUNT,*METRICS])
                    summary['bootstrap_ci']=old['bootstrap_ci']
                    summary['file_equal_means']=old['file_equal_means']
                    summary['geometry_equal_means']=old['geometry_equal_means']
                summaries.append(summary)
                for g in required:
                    gg=geometry_groups.get((g,),[])
                    planned.append(dict(n_sources=n,mode=mode,distance_cm=distance,geometry=g,
                        **summed(gg,n),files_at_least_1000_frames=sum(r['frames']>=1000 for r in gg),
                        files_at_least_1000_capture_match=sum(r['frames']>=1000 and r['origin']=='CAPTURE_RECORD_MATCH' for r in gg),
                        source_files=dict(collections.Counter(r['origin'] for r in gg)),
                        numeric_available=bool(gg),
                        size_rule_at_least_3_times_1000=sum(r['frames']>=1000 for r in gg)>=3,
                        size_rule_is_not_hardware_or_session_verification=True))
                for (g,),gg in geometry_groups.items():
                    geometries.append(dict(n_sources=n,mode=mode,distance_cm=distance,geometry=g,**summed(gg,n),
                        source_files=dict(collections.Counter(r['origin'] for r in gg)),
                        file_paths=[r['path'] for r in gg],minimum_frames=min(r['frames'] for r in gg),maximum_frames=max(r['frames'] for r in gg)))
                for (origin,cohort),gg in grouped(rr,['origin','cohort']).items():
                    source_summaries.append(dict(n_sources=n,mode=mode,distance_cm=distance,origin=origin,cohort=cohort,**summed(gg,n),geometries=len(grouped(gg,['geometry']))))
    comparisons=[]
    for n in (1,2,3):
        for d in (10,20,30,40):
            modes={m:grouped(by_config.get((n,m,d),[]),['geometry']) for m in ['AI','NOAI']}
            common=set(modes['AI'])&set(modes['NOAI'])
            result=dict(n_sources=n,distance_cm=d,common_geometries=len(common),geometry_list=[g[0] for g in sorted(common)])
            for m in ['AI','NOAI']:
                rr=[r for g in sorted(common) for r in modes[m][g]]
                stats=[summed(modes[m][g],n) for g in sorted(common)]
                result[m]=dict(pooled=summed(rr,n),
                    geometry_equal_means={metric:float(np.mean([g[metric] for g in stats if g[metric] is not None])) if any(g[metric] is not None for g in stats) else None for metric in METRICS},
                    origins=dict(collections.Counter(r['origin'] for r in rr)))
            result['controlled_hardware_comparison_confirmed']=False
            result['interpretation']='Matching geometry alone does not match acoustic background, recording session, firmware, source origin or replicate weights'
            comparisons.append(result)
    source_counts=[dict(origin=k,label=LABELS.get(k,k),files=len(rr),rows=sum(r['rows'] for r in rr)) for (k,),rr in sorted(grouped(rows,['origin']).items())]
    temporal={r['path']:r for r in jl(PREVIOUS/'raw_angle_temporal_features.jsonl.gz')}
    repeats=[]
    for key,rr in sorted(grouped(usable,['n_sources','mode','distance_cm','origin']).items(),key=str):
        values=[temporal[r['path']] for r in rr]
        pairs=sum(r['adjacent_nearest_direction_pairs'] for r in values)
        zeros=sum(round(r['zero_step_fraction']*r['adjacent_nearest_direction_pairs']) for r in values if r['zero_step_fraction'] is not None)
        repeats.append(dict(zip(['n_sources','mode','distance_cm','origin'],key),files=len(rr),
            adjacent_direction_pairs=pairs,unchanged_pairs=zeros,unchanged_fraction=zeros/pairs if pairs else None,
            per_file_unchanged_fraction=describe([r['zero_step_fraction'] for r in values if r['zero_step_fraction'] is not None]),
            longest_nonempty_constant_run=max(r['longest_raw_run'] for r in rr),longest_empty_run=max(r['longest_empty_run'] for r in rr),
            interpretation='Adjacent frame directions matched by minimum circular displacement; source identity is not established. Empty endpoint pairs excluded. No target repetition percentage is imposed.'))
    stamp_counts=collections.Counter(r['last_write_utc'] for r in inv['files'])
    timestamp_summary=dict(files_observed=len(inv['files']),files_with_per_frame_timestamps=sum(any('time' in h.lower() for h in r['header']) for r in rows),
        distinct_last_write_times=len(stamp_counts),largest_equal_last_write_group=max(stamp_counts.values(),default=0),
        earliest_observed_last_write_utc=min(stamp_counts,default=None),latest_observed_last_write_utc=max(stamp_counts,default=None),
        role='Context only. Save/copy/processing timestamps do not establish acquisition duration, packet independence or origin.',
        duration_for_entire_dataset='UNVERIFIED',timestamps_changed_by_review=False)
    audit=read(PREVIOUS/'results.json')
    evidence_paths=[ROOT/'paper/Báo cáo NCKH.pdf',ROOT/'Python/measure_doa.py',ROOT/'FFT/B1/src/main.c',ROOT/'FFT/B1/Listings/B1.map',ROOT/'FFT/B1/Objects/B1.build_log.htm']
    evidence=[dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size) for p in evidence_paths]
    build_text=(ROOT/'FFT/B1/Objects/B1.build_log.htm').read_text(encoding='utf-8',errors='replace')
    match=re.search(r'Program Size:\s*Code=(\d+)\s+RO-data=(\d+)\s+RW-data=(\d+)\s+ZI-data=(\d+)',build_text)
    memory=dict(paired_ai_noai_builds_identified=False,configuration_and_source_commit_linked_to_binary=False)
    if match:
        code,ro,rw,zi=map(int,match.groups());memory.update(code_bytes=code,ro_bytes=ro,rw_bytes=rw,zi_bytes=zi,flash_kib=(code+ro+rw)/1024,sram_kib=(rw+zi)/1024,
            interpretation='One existing build log/map only; these totals cannot populate both AI/control columns or validate paper numbers without build/configuration linkage')
    scope_summaries=[]
    for scope in ['all',*LABELS]:
        for s in summaries:
            rr=by_config.get((s['n_sources'],s['mode'],s['distance_cm']),[])
            if scope!='all':rr=[r for r in rr if r['origin']==scope]
            scope_summaries.append(dict(scope=scope,n_sources=s['n_sources'],mode=s['mode'],distance_cm=s['distance_cm'],
                **summed(rr,s['n_sources']),geometries=len(grouped(rr,['geometry'])),source_files=dict(collections.Counter(r['origin'] for r in rr))))
    result=dict(status='ANALYSED',client_date='2026-10-16',timezone='Asia/Bangkok',files_checked=len(rows),rows_checked=sum(r['rows'] for r in rows),
        usable_files=len(usable),header_only_files=sum(r['rows']==0 for r in rows),invalid_rows=sum(r['invalid_rows'] for r in rows),
        reused_after_sha256_validation=len(inv['unchanged']),new_files=len(inv['new']),changed_files=len(inv['changed']),removed_files=len(inv['removed']),
        main_csvs_modified=0,registry_modified=False,paper_modified=False,source_counts=source_counts,
        summaries=summaries,scope_summaries=scope_summaries,source_summaries=source_summaries,geometries=geometries,planned_coverage=planned,
        planned_geometry_mode_distance_conditions=len(planned),planned_conditions_with_numeric_data=sum(r['numeric_available'] for r in planned),
        matched_geometry_comparisons=comparisons,within_origin_cohort_comparisons=previous_stats['comparisons'],
        repeat_diagnostics=repeats,filesystem_time_context=timestamp_summary,
        audit_flags= {k:audit[k] for k in ['remaining_flag_events','unique_rows_with_remaining_flags','files_with_remaining_row_flags','flags_after','duplicate_sequence_summary']},
        previous_statistical_tests=previous_stats['tests_count'],previous_tests_reused_only_for_identical_content=True,
        source_registry_sha256=inv['registry_sha256'],paper_sha256=read(OUT/'paper_evidence.json')['sha256'],
        memory_build_evidence=memory,evidence_files=evidence,
        metric_protocol=dict(tolerance_deg=15,matching='One-to-one maximum TP then minimum total circular error',
            precision='TP/(TP+FP)',recall_all='TP/(N*all frames)',recall_nonempty='TP/(N*nonempty frames)',
            f1_all='2TP/(TP+FP+N*all frames)',f1_nonempty='2TP/(TP+FP+N*nonempty frames)',
            matched_mae_deg='sum circular error of TP pairs / TP; conditioned on <=15 degrees',full_rate='Frames with TP=N / all frames',
            reference_activity_assumption='All declared reference sources active in every frame; CSV does not contain voice-activity ground truth',
            paper_primary_recall='recall_all',paper_primary_f1='f1_all',
            missing_groups='Missing values, never zero',aggregation='Micro pooling of TP/FP/FN within each N/mode/distance; not arithmetic averaging of per-file percentages',
            no_archived_or_derived_copies_counted=True),
        resampling_note='Existing moving-block per-file and geometry-cluster 95% bootstrap CIs reused after identical SHA-256. Conditional on clusters/stationarity, not independent frame trials or hardware validation.',
        known_selection_bias=read(PREVIOUS/'historical_selection_bias.json'))
    write(OUT/'assessment.json',result)
    print(json.dumps(dict(status=result['status'],files=result['files_checked'],rows=result['rows_checked'],numeric_table_rows=sum(s['files']>0 for s in summaries),
        planned_conditions_with_data=result['planned_conditions_with_numeric_data'],planned_conditions_total=len(planned),memory=memory),ensure_ascii=True),flush=True)

if __name__=='__main__':
    if sys.argv[1]=='inventory':inventory()
    elif sys.argv[1]=='analyze':analyze()
