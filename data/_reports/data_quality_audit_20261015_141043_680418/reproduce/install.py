"""Transactional minimal corrections, immutable observations and explicit provenance."""
import csv,gzip,io,shutil,copy,os,argparse
from common import *
from statistics_audit import lines
import scan

CORE=('sample','distance_cm','raw_angles')
def csv_values(path):
    with Path(path).open(encoding='utf-8-sig',newline='') as stream:
        reader=csv.DictReader(stream);return reader.fieldnames,list(reader)
def main(action):
    cfg=read(WORK/'config.json');out=Path(cfg['output']);backup=Path(cfg['backup']);data=Path(cfg['data'])
    before={r['path']:r for r in lines(out/'file_features_before.jsonl.gz')};changes=read(out/'file_changes.json')
    original_registry=read(backup/'_data_sources.json');updated=copy.deepcopy(original_registry)
    change_lookup={r['path']:r for r in changes};assert len(change_lookup)==len(changes)
    for change in changes:
        relative=change['path'];parent=before[relative]
        old=original_registry['files'].get(relative,{})
        valid_old=old.get('sha256')==change['before_sha256']
        entry=copy.deepcopy(old) if valid_old else {}
        entry.update(data_origin='SYNTHETIC' if parent['origin']=='SYNTHETIC_DOCUMENTED' else 'PROCESSED',
            sha256=change['after_sha256'],previous_sha256=change['before_sha256'],previous_csv_backup=str(backup/relative),
            quality_audit=dict(report=str(out/'index.html'),change_log=str(out/'row_changes.jsonl.gz'),file_change_log=str(out/'file_changes.json'),
                input_sha256=change['before_sha256'],output_sha256=change['after_sha256'],processing='FORMAT_OR_DERIVED_COLUMNS_ONLY',
                parent_origin={k:parent[k] for k in ['origin','cohort','origin_evidence']},
                raw_observations_changed=False,acquisition_verified_by_this_processing=False))
        updated['files'][relative]=entry
    write(out/'registry_after.proposed.json',updated)
    scan.CFG={**cfg,'backup':str(out/'corrected_files')};scan.REG=updated;scan.HISTORY=read(WORK/'historical_evidence.json')
    staged_records={};staged_flags=[]
    for change in changes:
        rel=change['path'];old=backup/rel;new=out/'corrected_files'/rel
        assert sha(old)==change['before_sha256'] and sha(new)==change['after_sha256']
        old_header,old_rows=csv_values(old);new_header,new_rows=csv_values(new)
        assert set(old_header)==set(new_header) and len(old_rows)==len(new_rows)
        assert new_header==doa.csv_fields(before[rel]['n_sources'])+(['data_origin'] if 'data_origin' in old_header else [])
        logged={r['row']:{c['column']:(c['old'],c['new']) for c in r['cells']} for op in lines(out/'operations.jsonl.gz') if op['path']==rel for r in op['row_changes']}
        for i,(a,b) in enumerate(zip(old_rows,new_rows),1):
            assert all(a[k]==b[k] for k in [*CORE,*[x for x in old_header if x.startswith('true_angle_')]])
            actual={key:(a[key],b[key]) for key in a if a[key]!=b[key]}
            assert actual==logged.get(i,{}),(rel,i,actual,logged.get(i))
            assert all(k=='detected_count' or k=='mean_error' or k.startswith(('detected_angle_','error_')) for k in actual)
        rec,flags,remaining,operation,blocks,_=scan.audit_file(dict(path=rel,sha256=change['after_sha256']))
        rec['unique_direction_sensitivity']=before[rel].get('unique_direction_sensitivity')
        assert not operation and not remaining,('Unresolved fixable error after staging',rel)
        assert rec['semantic_sha256']==before[rel]['semantic_sha256']
        for key in [*COUNT,*METRICS,'source_tp']:
            assert rec[key]==before[rel][key],('Raw metrics changed',rel,key)
        staged_records[rel]=rec;staged_flags.extend(flags)
    write(out/'staged_verification.json',dict(files=len(changes),all_core_cells_byte_equal=True,all_changes_exactly_logged=True,
        all_raw_direction_metrics_equal=True,no_padding_or_deletion=True,original_rows=sum(r['rows'] for r in before.values())))
    if action=='verify':print(json.dumps(dict(status='STAGED_VERIFIED',files=len(changes))),flush=True);return
    assert action=='apply' and not (out/'installation.json').exists()
    assert sha(data/'_data_sources.json')==cfg['registry_before_sha256']
    expected={f['path']:f for f in cfg['files']}
    inventory={p.relative_to(data).as_posix() for n in range(4) for m in ('AI','NOAI') for p in (data/f'{n}source{m}').rglob('*.csv')}
    assert inventory==set(expected)
    for i,(rel,item) in enumerate(expected.items()):
        assert sha(data/rel)==sha(backup/rel)==item['sha256'],('Concurrent change before install',rel)
        if (i+1)%3000==0:print(f'Checked live inputs and original backups {i+1}/{len(expected)}',flush=True)
    written=[];staged=None;old_registry_bytes=(data/'_data_sources.json').read_bytes()
    try:
        for change in changes:
            rel=change['path'];target=data/rel
            assert target.resolve().is_relative_to(data.resolve()) and target.is_file()
            assert sha(target)==change['before_sha256']
            staged=target.with_name(target.name+'.quality_installing');assert not staged.exists()
            shutil.copyfile(out/'corrected_files'/rel,staged);assert sha(staged)==change['after_sha256']
            os.replace(staged,target);written.append(change);staged=None
        staged=data/'_data_sources.json.quality_installing';assert not staged.exists()
        staged.write_bytes((out/'registry_after.proposed.json').read_bytes());os.replace(staged,data/'_data_sources.json');staged=None
        for i,(rel,item) in enumerate(expected.items()):
            expected_hash=change_lookup.get(rel,{}).get('after_sha256',item['sha256'])
            assert sha(data/rel)==expected_hash and sha(backup/rel)==item['sha256'],rel
            if (i+1)%3000==0:print(f'Verified installed files and immutable backups {i+1}/{len(expected)}',flush=True)
        # Actual current files are re-read after installation; unchanged records are reused only after SHA validation above.
        scan.CFG={**cfg,'backup':str(data)};scan.REG=read(data/'_data_sources.json')
        after_records={};after_flags=[];native=[]
        for change in changes:
            rel=change['path'];rec,flags,remaining,operation,blocks,_=scan.audit_file(dict(path=rel,sha256=change['after_sha256']))
            rec['unique_direction_sensitivity']=before[rel].get('unique_direction_sensitivity')
            assert not remaining and not operation
            assert rec['semantic_sha256']==before[rel]['semantic_sha256']
            for key in [*COUNT,*METRICS,'source_tp']:assert rec[key]==before[rel][key]
            meta,s=doa.score_csv(data/rel,doa.Settings(action='analyze'))
            assert (s.frames,s.tp,s.fp,sum(s.errors))==(rec['frames'],rec['tp'],rec['fp'],rec['error_sum'])
            after_records[rel]=rec;after_flags.extend(flags);native.append(rel)
        with gzip.open(out/'file_features_after.jsonl.gz','wt',encoding='utf-8') as stream:
            for rec in lines(out/'file_features_before.jsonl.gz'):
                stream.write(json.dumps(clean(after_records.get(rec['path'],rec)),ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n')
        with gzip.open(out/'row_flags_after.jsonl.gz','wt',encoding='utf-8') as stream:
            for flag in itertools.chain((f for f in lines(out/'row_flags_before.jsonl.gz') if f['path'] not in after_records),after_flags):
                stream.write(json.dumps(flag,ensure_ascii=False,separators=(',',':'))+'\n')
        result=dict(status='INSTALLED_VERIFIED',files_checked=len(expected),rows_checked=sum(r['rows'] for r in before.values()),
            files_changed=len(changes),serialized_rows_changed=sum(c['serialized_rows_changed'] for c in changes),
            value_rows_changed=sum(c['value_rows_changed'] for c in changes),value_cells_changed=sum(c['value_cells_changed'] for c in changes),
            header_order_files=sum(c['header_reorder'] for c in changes),native_reader_files_verified=len(native),
            unchanged_file_features_reused_after_sha256_validation=len(expected)-len(changes),
            all_original_csvs_preserved=True,all_raw_observations_preserved=True,no_rows_added_or_deleted=True,
            raw_metrics_before_after_equal=True,backup=str(backup),main_registry_after_sha256=sha(data/'_data_sources.json'))
        write(out/'installation.json',result);write(WORK/'installation.json',result)
        print(json.dumps(result,ensure_ascii=True),flush=True)
    except Exception:
        for change in reversed(written):
            target=data/change['path'];assert sha(target)==change['after_sha256'],'Concurrent edit prevents safe automatic rollback'
            shutil.copyfile(backup/change['path'],target)
        current_registry_sha=sha(data/'_data_sources.json')
        assert current_registry_sha in [cfg['registry_before_sha256'],sha(out/'registry_after.proposed.json')]
        (data/'_data_sources.json').write_bytes(old_registry_bytes)
        if staged and staged.exists():staged.unlink()
        raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['verify','apply']);args=p.parse_args();main(args.action)
