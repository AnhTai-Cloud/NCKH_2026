"""Independent structural pass and sensitivity to exactly duplicate output bearings."""
import csv,re,collections,gzip
from concurrent.futures import ProcessPoolExecutor
from common import *
from statistics_audit import lines

def worker(args):
    config,items=args;result=[]
    for item in items:
        relative=item['path'];n=int(relative[0]);file=Path(config['backup'])/relative
        seen=set();extra=[];sens=dict(frames=0,tp_delta=0,fp_delta=0,error_sum_delta=0,full_delta=0)
        folder=next((float(p[:-1])*100 for p in Path(relative).parts if re.fullmatch(r'0\.[1234]m',p)),None)
        with file.open(encoding='utf-8-sig',newline='') as stream:
            reader=csv.DictReader(stream)
            for row_index,row in enumerate(reader,1):
                values=tuple(row.values())
                if values in seen:extra.append(dict(path=relative,row_start=row_index,row_end=row_index,code='EXACT_DUPLICATE_ROW',detail='Exact repeated full CSV row; retained',status='UNRESOLVED'))
                seen.add(values)
                if folder is not None and abs(float(row['distance_cm'])-folder)>1e-9:extra.append(dict(path=relative,row_start=row_index,row_end=row_index,code='FOLDER_DISTANCE_MISMATCH',detail=row['distance_cm'],status='UNRESOLVED'))
                if 'data_origin' in row and row['data_origin'] not in ['SYNTHETIC','MEASURED','PROCESSED']:extra.append(dict(path=relative,row_start=row_index,row_end=row_index,code='INVALID_DECLARED_ORIGIN',detail=row['data_origin'],status='UNRESOLVED'))
                det=tuple(int(x) for x in row['raw_angles'].split(';') if x.strip())
                if len(det)!=len(set(det)):
                    truth=tuple(int(row[f'true_angle_{j+1}']) for j in range(n));unique=tuple(dict.fromkeys(det))
                    a,b=matched(truth,det),matched(truth,unique);sens['frames']+=1
                    sens['tp_delta']+=len(b)-len(a);sens['fp_delta']+=(len(unique)-len(b))-(len(det)-len(a))
                    sens['error_sum_delta']+=sum(p[2] for p in b)-sum(p[2] for p in a);sens['full_delta']+=int(len(b)==n)-int(len(a)==n)
        result.append(dict(path=relative,extra_flags=extra,unique_direction_sensitivity=sens))
    return result

def main():
    cfg=read(WORK/'config.json');out=Path(cfg['output']);items=cfg['files'];results=[]
    chunks=[(cfg,items[i:i+160]) for i in range(0,len(items),160)]
    with ProcessPoolExecutor(max_workers=4) as pool:
        for result in pool.map(worker,chunks):
            results.extend(result)
            if len(results)%3200==0:print(f'Independent structural cross-check {len(results)}/{len(items)}',flush=True)
    extras=[f for r in results for f in r['extra_flags']]
    assert len(results)==len(items)
    lookup={r['path']:r for r in results}
    temporary=out/'file_features_before.supplemented.jsonl.gz'
    with gzip.open(temporary,'wt',encoding='utf-8') as stream:
        for r in lines(out/'file_features_before.jsonl.gz'):
            new=lookup[r['path']];r['unique_direction_sensitivity']=new['unique_direction_sensitivity']
            for code,count in collections.Counter(f['code'] for f in new['extra_flags']).items():r['issues'][code]=count
            stream.write(json.dumps(clean(r),ensure_ascii=False,separators=(',',':'))+'\n')
    (out/'file_features_before.jsonl.gz').replace(out/'file_features_before.initial_pass.jsonl.gz')
    temporary.replace(out/'file_features_before.jsonl.gz')
    with gzip.open(out/'supplementary_row_flags.jsonl.gz','wt',encoding='utf-8') as stream:
        for flag in extras:stream.write(json.dumps(flag,ensure_ascii=False,separators=(',',':'))+'\n')
    if extras:
        flags=list(lines(out/'row_flags_before.jsonl.gz'));seen={(f['path'],f['row_start'],f['row_end'],f['code']) for f in flags}
        flags.extend(f for f in extras if (f['path'],f['row_start'],f['row_end'],f['code']) not in seen)
        with gzip.open(out/'row_flags_before.supplemented.jsonl.gz','wt',encoding='utf-8') as stream:
            for flag in flags:stream.write(json.dumps(flag,ensure_ascii=False,separators=(',',':'))+'\n')
        (out/'row_flags_before.supplemented.jsonl.gz').replace(out/'row_flags_before.jsonl.gz')
    result=dict(files_cross_checked=len(results),extra_flag_counts=dict(collections.Counter(f['code'] for f in extras)),
        duplicate_bearing_frames=sum(r['unique_direction_sensitivity']['frames'] for r in results),
        sensitivity_deltas={key:sum(r['unique_direction_sensitivity'][key] for r in results) for key in ['tp_delta','fp_delta','full_delta','error_sum_delta']},
        no_observations_changed=True,sensitivity_is_analysis_only=True)
    write(out/'structural_crosscheck.json',result)
    print(json.dumps(result),flush=True)

if __name__=='__main__':main()
