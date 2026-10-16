"""Transparent, outcome-independent frame reduction with full verified originals."""
import collections,concurrent.futures,csv,gzip,hashlib,io,json,math,os,re,shutil,sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[2];WORK=Path(__file__).resolve().parent;DATA=ROOT/'data'
sys.path[:0]=[str(ROOT/'tmp/data_quality_audit_20261015'),str(ROOT/'tmp/data_quality_deps'),str(ROOT/'tmp/analysis_plot_deps')]
from common import read,write,sha,metrics,COUNT,METRICS,matched,clean
import measure_doa as doa

SEED=20261016;TARGET=35000;CEILING=40000
CONFIG=WORK/'config.json'

def rank(*parts):return int.from_bytes(hashlib.sha256(repr((SEED,*parts)).encode()).digest(),'big')
def lines(path):
    with gzip.open(path,'rt',encoding='utf-8') as f:
        for line in f:yield json.loads(line)
def groups(rows,keys):
    d=collections.defaultdict(list)
    for r in rows:d[tuple(tuple(sorted(r['truth'])) if k=='geometry' else r[k] for k in keys)].append(r)
    return d
def allocate(capacity,total):
    weights=sum(capacity.values());quota={k:total*v/weights for k,v in capacity.items()}
    a={k:min(v,max(1,int(math.floor(quota[k])))) for k,v in capacity.items()}
    assert total>=len(a) and total<=weights
    while sum(a.values())<total:
        k=max((k for k in a if a[k]<capacity[k]),key=lambda k:(quota[k]-a[k],-rank('allocation-tie',k)))
        a[k]+=1
    while sum(a.values())>total:
        k=max((k for k in a if a[k]>1),key=lambda k:(a[k]-quota[k],-rank('allocation-tie',k)))
        a[k]-=1
    return a
def active():return sorted(p for n in range(4) for m in ['AI','NOAI'] for p in (DATA/f'{n}source{m}').rglob('*.csv'))

def prepare():
    assert not CONFIG.exists(),'Reuse existing selection; never redraw based on results'
    resume=read(WORK/'snapshot_resume.json') if (WORK/'snapshot_resume.json').exists() else None
    stamp=resume['stamp'] if resume else '20261016_'+datetime.now(ZoneInfo('Asia/Bangkok')).strftime('%H%M%S_%f')
    backup=DATA/'_archive'/f'before_frame_reduction_{stamp}';stage=DATA/'_subsets'/f'frame_reduction_{stamp}';out=DATA/'_reports'/f'frame_reduction_{stamp}'
    for p in [backup,stage,out]:
        assert p.resolve().is_relative_to(DATA.resolve())
        if resume:assert p.is_dir()
        else:assert not p.exists();p.mkdir(parents=True)
    cachepath=DATA/'_reports/data_quality_audit_20261015_141043_680418/audited_file_details.jsonl.gz'
    cache={r['path']:r for r in lines(cachepath)}
    paths=active();assert {p.relative_to(DATA).as_posix() for p in paths}==set(cache)
    def snapshot(path):
        rel=path.relative_to(DATA).as_posix();digest=sha(path);assert digest==cache[rel]['sha256'],f'Changed input needs fresh audit: {rel}'
        saved=backup/rel;saved.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,saved);assert sha(saved)==digest==sha(path)
        return dict(path=rel,sha256=digest,bytes=path.stat().st_size,original_last_write_ns=path.stat().st_mtime_ns)
    if resume:
        manifest=read(backup/'snapshot_manifest.json')['files']
        def verify_saved(item):
            assert sha(DATA/item['path'])==sha(backup/item['path'])==item['sha256']==cache[item['path']]['sha256']
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:list(pool.map(verify_saved,manifest))
    else:
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:manifest=list(pool.map(snapshot,paths))
    registry=read(DATA/'_data_sources.json');registry_hash=sha(DATA/'_data_sources.json');shutil.copyfile(DATA/'_data_sources.json',backup/'_data_sources.json');assert sha(backup/'_data_sources.json')==registry_hash
    write(backup/'snapshot_manifest.json',dict(files=manifest,registry_sha256=registry_hash))
    records=list(cache.values());plan=[];summary=[]
    for key,rr in sorted(groups([r for r in records if r['frames']>0],['n_sources','mode','distance_cm']).items(),key=str):
        n,mode,d=key;total=int(sum(r['frames'] for r in rr));target=TARGET if total>CEILING else total
        strata=groups(rr,['geometry','origin','cohort']);capacity={k:int(sum(r['frames'] for r in rs)) for k,rs in strata.items()}
        allocation=allocate(capacity,target)
        for stratum,rs in sorted(strata.items(),key=str):
            g,origin,cohort=stratum;remaining=allocation[stratum]
            pair_tag='EXPLICIT_SHARED_INPUT' if cohort=='SHARED_N2_BACKGROUND_FIXED_AI_025' else mode
            ordered=sorted(rs,key=lambda r:rank('file-order',pair_tag,n,d,g,origin,cohort,Path(r['path']).name))
            for r in ordered:
                take=min(remaining,int(r['frames']));remaining-=take
                plan.append(dict(path=r['path'],n_sources=n,mode=mode,distance_cm=d,truth=r['truth'],origin=origin,cohort=cohort,
                    before_sha256=r['sha256'],original_frames=int(r['frames']),kept_frames=take,
                    action='KEEP_BYTES' if take==r['frames'] else 'PARTIAL' if take else 'ARCHIVE_ONLY',row_start=1))
            assert remaining==0
        summary.append(dict(n_sources=n,mode=mode,distance_cm=d,frames_before=total,frames_after=target,
            files_before=len(rr),geometries_before=len(groups(rr,['geometry'])),strata_preserved=len(strata)))
    for r in records:
        if not r['frames']:plan.append(dict(path=r['path'],n_sources=r['n_sources'],mode=r['mode'],distance_cm=r['distance_cm'],truth=r['truth'],origin=r['origin'],cohort=r['cohort'],before_sha256=r['sha256'],original_frames=0,kept_frames=0,action='KEEP_BYTES',row_start=1))
    # A shared seed pairs the same basename/geometry/cohort, never frame outcomes.
    pairs=collections.defaultdict(list)
    for p in plan:
        if p['action']=='PARTIAL':
            pair_tag='EXPLICIT_SHARED_INPUT' if p['cohort']=='SHARED_N2_BACKGROUND_FIXED_AI_025' else p['mode']
            pairs[pair_tag,p['n_sources'],p['distance_cm'],tuple(p['truth']),p['origin'],p['cohort'],Path(p['path']).name].append(p)
    for key,rs in pairs.items():
        original=rs[0]['original_frames'];assert all(p['original_frames']==original for p in rs)
        longest=max(p['kept_frames'] for p in rs);start=1+rank('block-start',*key)%(original-longest+1)
        for p in rs:p['row_start']=start
    for p in plan:p['row_end']=p['row_start']+p['kept_frames']-1 if p['kept_frames'] else None
    plan=sorted(plan,key=lambda r:r['path']);assert len(plan)==len(manifest)
    cfg=dict(status='SNAPSHOT_AND_PLAN_READY',root=str(ROOT),data=str(DATA),backup=str(backup),stage=str(stage),output=str(out),seed=SEED,
        target_per_group=TARGET,upper_threshold=CEILING,registry_before_sha256=registry_hash,input_files=len(plan),
        frames_before=sum(p['original_frames'] for p in plan),frames_after=sum(p['kept_frames'] for p in plan),
        files_after=sum(p['action']!='ARCHIVE_ONLY' for p in plan),partial_files=sum(p['action']=='PARTIAL' for p in plan),
        archived_only_files=sum(p['action']=='ARCHIVE_ONLY' for p in plan),
        protocol='Proportional geometry/origin/cohort allocation; deterministic file order and one contiguous block from final file; no outcome-based selection; local sample reindexed with row-range log',
        all_originals_backed_up=True,no_measurement_values_changed=True,no_noise_or_new_observations=True,
        renumbered_column='sample only in partial CSVs; original row ranges preserved',plan=plan,groups=summary)
    write(CONFIG,cfg);write(out/'selection_plan.json',cfg)
    with gzip.open(WORK/'operations.jsonl.gz','wt',encoding='utf-8') as f:
        for p in plan:
            if p['action']!='PARTIAL':continue
            path=backup/p['path'];text=path.read_text(encoding='utf-8-sig');source=list(csv.reader(io.StringIO(text,newline='')));header=source[0];sample_index=header.index('sample')
            selected=[list(r) for r in source[p['row_start']:p['row_end']+1]];assert len(selected)==p['kept_frames']
            for i,r in enumerate(selected,1):r[sample_index]=str(i)
            f.write(json.dumps(dict(path=p['path'],header=header,rows=selected,before_sha256=p['before_sha256'],row_start=p['row_start'],row_end=p['row_end'],
                newline='\r\n' if '\r\n' in path.read_bytes().decode('utf-8-sig') else '\n'),ensure_ascii=False)+'\n')
    for p in plan:
        if p['action']=='KEEP_BYTES':
            dest=stage/p['path'];dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(backup/p['path'],dest)
    print(json.dumps({k:v for k,v in cfg.items() if k not in ['plan','groups']},ensure_ascii=True),flush=True)

def registry_for_stage(cfg):
    registry=read(Path(cfg['backup'])/'_data_sources.json');files=registry['files'];stage=Path(cfg['stage'])
    for p in cfg['plan']:
        rel=p['path']
        if p['action']=='ARCHIVE_ONLY':files.pop(rel,None);continue
        if p['action']=='KEEP_BYTES':continue
        digest=sha(stage/rel);previous=files.get(rel,{})
        if p['origin']=='SYNTHETIC_DOCUMENTED':entry=dict(previous,data_origin='SYNTHETIC',sha256=digest)
        else:
            entry=dict(previous,data_origin='PROCESSED',sha256=digest)
            origin='PROCESSED_DOCUMENTED' if p['origin']=='CAPTURE_RECORD_MATCH' else p['origin']
            cohort='SUBSET_OF_HISTORICAL_CAPTURE' if p['origin']=='CAPTURE_RECORD_MATCH' else p['cohort']
            entry['quality_audit']=dict(parent_origin=dict(origin=origin,cohort=cohort,origin_evidence='Contiguous original rows verified against preserved parent '+p['before_sha256']+'; source acquisition evidence remains limited'),raw_observations_changed=False)
        entry['frame_reduction']=dict(operation='CONTIGUOUS_SUBSET',selection_seed=SEED,selection_independent_of_detection_metrics=True,
            parent_sha256=p['before_sha256'],parent_origin=p['origin'],parent_cohort=p['cohort'],original_csv=str(Path(cfg['backup'])/rel),
            original_frames=p['original_frames'],original_row_start=p['row_start'],original_row_end=p['row_end'],kept_frames=p['kept_frames'],
            sample_rule='Local output row counter 1..K; original sample is recovered from preserved parent row range',
            selected_measurement_cells_unchanged=True,report=str(Path(cfg['output'])/'index.html'))
        files[rel]=entry
    write(stage/'_data_sources.json',registry)
    return registry

def score_selected(p,cfg):
    path=Path(cfg['stage'])/p['path'];parent=Path(cfg['backup'])/p['path']
    if p['action']=='KEEP_BYTES':assert sha(path)==sha(parent)==p['before_sha256']
    original=list(csv.reader(parent.open(newline='',encoding='utf-8-sig')));saved=list(csv.reader(path.open(newline='',encoding='utf-8-sig')))
    assert saved[0]==original[0]==doa.csv_fields(p['n_sources'])
    assert len(saved)-1==p['kept_frames']
    expected=[list(r) for r in original[p['row_start']:p['row_end']+1]] if p['kept_frames'] else []
    if p['action']=='PARTIAL':
        ix=saved[0].index('sample')
        for i,r in enumerate(expected,1):r[ix]=str(i)
    assert saved[1:]==expected,p['path']
    c={k:0 for k in COUNT};dup=0
    for cells in saved[1:]:
        r=dict(zip(saved[0],cells));truth=tuple(int(r[f'true_angle_{j+1}']) for j in range(p['n_sources']));det=tuple(int(a) for a in r['raw_angles'].split(';') if a.strip())
        assert len(det)==int(r['detected_count']);assert list(truth)==p['truth'];assert float(r['distance_cm'])==p['distance_cm']
        pairs=matched(truth,det);values=[1,int(bool(det)),len(pairs),len(det)-len(pairs),sum(q[2] for q in pairs),int(len(pairs)==p['n_sources']),int(len(det)==p['n_sources'])]
        for k,v in zip(COUNT,values):c[k]+=v
        dup+=len(set(det))!=len(det)
    return dict(p,source_origin_role='Parent origin at snapshot; partial CSV is a documented processed subset, not a byte-identical complete historical capture',after_sha256=sha(path),**c,**metrics(c,p['n_sources']),duplicate_direction_frames=dup)

def verify_stage():
    cfg=read(CONFIG);assert cfg['status'] in ['SNAPSHOT_AND_PLAN_READY','CSV_AUTHORED']
    stage=Path(cfg['stage']);out=Path(cfg['output']);registry_for_stage(cfg)
    selected=[p for p in cfg['plan'] if p['action']!='ARCHIVE_ONLY'];results=[]
    for i,p in enumerate(selected,1):
        results.append(score_selected(p,cfg))
        if i%700==0:print(json.dumps(dict(verified_csvs=i,total=len(selected))),flush=True)
    assert sum(r['frames'] for r in results)==cfg['frames_after']==673000
    current=set(p.relative_to(stage).as_posix() for p in stage.rglob('*.csv'));assert current=={p['path'] for p in selected}
    summary=[];before=read(DATA/'_reports/paper_readiness_20261016/assessment.json')
    before_map={(r['n_sources'],r['mode'],r['distance_cm']):r for r in before['summaries']}
    for key,rs in sorted(groups([r for r in results if r['frames']],['n_sources','mode','distance_cm']).items(),key=str):
        n,mode,d=key;c={k:sum(r[k] for r in rs) for k in COUNT};b=before_map[n,mode,d];m=metrics(c,n)
        geo=len(groups(rs,['geometry']));assert geo==b['geometries']
        assert c['frames']==(TARGET if b['frames']>CEILING else b['frames'])
        summary.append(dict(n_sources=n,mode=mode,distance_cm=d,files=len(rs),geometries=geo,**c,**m,
            files_before=b['files'],frames_before=b['frames'],before={k:b[k] for k in METRICS},
            delta={k:m[k]-b[k] if m[k] is not None and b[k] is not None else None for k in METRICS}))
    write(out/'file_metrics_after.json',results);write(out/'summary_after.json',summary)
    write(out/'staged_verification.json',dict(status='VERIFIED',files=len(results),frames=cfg['frames_after'],
        original_selected_cells_preserved=True,sample_mapping_verified=True,all_geometries_preserved=True,no_frames_created=True,
        no_outcome_based_selection=True,header_only_files=sum(r['frames']==0 for r in results),
        partial_csvs=cfg['partial_files'],stage_registry_sha256=sha(stage/'_data_sources.json')))
    cfg['status']='STAGE_VERIFIED';write(CONFIG,cfg)
    print(json.dumps(dict(status=cfg['status'],files=len(results),frames=cfg['frames_after'],groups=len(summary)),ensure_ascii=True),flush=True)

def install():
    cfg=read(CONFIG);assert cfg['status']=='STAGE_VERIFIED'
    stage=Path(cfg['stage']);backup=Path(cfg['backup']);out=Path(cfg['output'])
    assert read(out/'native_reader_verification.json')['status']=='VERIFIED'
    assert stage.resolve().is_relative_to(DATA.resolve()) and backup.resolve().is_relative_to((DATA/'_archive').resolve())
    assert sha(DATA/'_data_sources.json')==cfg['registry_before_sha256']
    selected={p['path']:p for p in read(out/'file_metrics_after.json')}
    paths=active();assert {p.relative_to(DATA).as_posix() for p in paths}=={p['path'] for p in cfg['plan']}
    # Complete every containment, original-backup and current-content check before any mutation.
    for p in cfg['plan']:
        target=(DATA/p['path']).resolve();saved=(backup/p['path']).resolve()
        assert target.is_relative_to(DATA.resolve()) and re.fullmatch(r'[0-3]source(?:AI|NOAI)',target.relative_to(DATA.resolve()).parts[0]) and target.suffix=='.csv'
        assert saved.is_relative_to(backup.resolve()) and sha(saved)==sha(target)==p['before_sha256']
        if p['action']!='ARCHIVE_ONLY':assert sha(stage/p['path'])==selected[p['path']]['after_sha256']
    cfg['status']='INSTALLING';write(CONFIG,cfg)
    with (out/'installation_log.jsonl').open('x',encoding='utf-8') as log:
        for p in cfg['plan']:
            dest=DATA/p['path']
            if p['action']=='PARTIAL':
                tmp=dest.with_name(dest.name+'.frame_reduction_tmp');assert not tmp.exists();shutil.copyfile(stage/p['path'],tmp);os.replace(tmp,dest)
            elif p['action']=='ARCHIVE_ONLY':dest.unlink()
            log.write(json.dumps(dict(path=p['path'],action=p['action'],before_sha256=p['before_sha256'],after_sha256=selected.get(p['path'],{}).get('after_sha256'),backup=str(backup/p['path']),original_row_start=p['row_start'],original_row_end=p['row_end']),ensure_ascii=False)+'\n')
    tmp=DATA/'_data_sources.frame_reduction_tmp.json';assert not tmp.exists();shutil.copyfile(stage/'_data_sources.json',tmp);os.replace(tmp,DATA/'_data_sources.json')
    current=active();assert {p.relative_to(DATA).as_posix() for p in current}==set(selected)
    for path in current:assert sha(path)==selected[path.relative_to(DATA).as_posix()]['after_sha256']
    assert sha(DATA/'_data_sources.json')==sha(stage/'_data_sources.json')
    write(out/'installation.json',dict(status='INSTALLED_VERIFIED',files_before=cfg['input_files'],files_after=cfg['files_after'],frames_before=cfg['frames_before'],frames_after=cfg['frames_after'],
        files_rewritten=cfg['partial_files'],files_archived_out_of_active=cfg['archived_only_files'],backup=str(backup),
        all_installed_csv_sha256_verified=True,originals_preserved=True,raw_angles_unchanged=True,sample_mapping_logged=True,
        registry_before_sha256=cfg['registry_before_sha256'],registry_after_sha256=sha(DATA/'_data_sources.json')))
    cfg['status']='INSTALLED_VERIFIED';write(CONFIG,cfg)
    print(json.dumps(read(out/'installation.json'),ensure_ascii=True),flush=True)

if __name__=='__main__':
    {'prepare':prepare,'verify':verify_stage,'install':install}[sys.argv[1]]()
