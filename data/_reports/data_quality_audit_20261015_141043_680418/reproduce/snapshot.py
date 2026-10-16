"""Immutable content snapshot of active DOA CSVs; no file times used as evidence."""
import hashlib, json, shutil, re, sys
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[2]
WORK=Path(__file__).resolve().parent
CONFIG=WORK/'config.json'

def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream,'sha256').hexdigest()

def main():
    assert not CONFIG.exists(), 'Snapshot already exists; reuse it instead of restarting.'
    stamp=datetime.now(ZoneInfo('Asia/Bangkok')).strftime('%Y%m%d_%H%M%S_%f')
    data=ROOT/'data'
    backup=data/'_archive'/('data_quality_before_'+stamp)
    output=data/'_reports'/('data_quality_audit_'+stamp)
    for p in [backup,output]:
        assert p.resolve().is_relative_to(data.resolve()) and not p.exists()
        p.mkdir(parents=True)
    registry=data/'_data_sources.json'
    raw_registry=registry.read_bytes()
    (backup/'_data_sources.json').write_bytes(raw_registry)
    config=dict(root=str(ROOT),data=str(data),backup=str(backup),output=str(output),
        seed=20261015,status='SNAPSHOTTING',registry_before_sha256=sha(registry),
        protocol=dict(match_tolerance_deg=15,source_angles_preserved=True,
            no_file_timestamps_used=True,no_synthetic_samples_added=True,
            statistical_seed_role='Resampling only; never changes observation values',
            bootstrap_replicates=2000,permutation_replicates=1999,
            primary_unit='Geometry cluster / recorded CSV, not individual overlapping frames',
            fdr_method='Benjamini-Yekutieli across all valid inferential p-values',
            derived_columns_rule='Only complete-count rows: one-to-one minimum total circular error; preserve any existing tied optimum. Partial-count native rows keep derived cells empty.',
            no_truth_based_correction_to_raw_directions=True))
    CONFIG.write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
    manifest=[]
    files=sorted(p for n in range(4) for mode in ('AI','NOAI') for p in (data/f'{n}source{mode}').rglob('*.csv'))
    assert files
    for i,path in enumerate(files):
        relative=path.relative_to(data).as_posix();before=sha(path)
        saved=backup/relative;saved.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(path,saved)
        assert sha(saved)==sha(path)==before, relative
        manifest.append(dict(path=relative,sha256=before,bytes=saved.stat().st_size))
        if (i+1)%1500==0: print(f'Snapshotted {i+1}/{len(files)} CSV',flush=True)
    assert sha(registry)==config['registry_before_sha256']
    excluded=[]
    for folder in sorted(data.iterdir()):
        if folder.is_dir() and not re.fullmatch(r'[0-3]source(?:AI|NOAI)',folder.name):
            if folder in [backup.parent,output.parent]:
                # Record archive/report directories as supporting evidence, not independent experiments.
                excluded.append(dict(path=folder.name,role='Historical archive/report; excluded from active sample totals'))
            else:
                excluded.append(dict(path=folder.name,role='Derived or scenario copy; excluded to avoid duplicate observations',csv_files=sum(1 for _ in folder.rglob('*.csv'))))
        elif folder.is_file() and folder.suffix.lower()=='.zip':
            excluded.append(dict(path=folder.name,role='Archive, preserved unchanged',sha256=sha(folder)))
    (backup/'snapshot_manifest.json').write_text(json.dumps(dict(files=manifest,registry_sha256=sha(registry)),ensure_ascii=False,indent=2),encoding='utf-8')
    config.update(status='SNAPSHOT_COMPLETE',files=manifest,excluded=excluded,
        snapshot_manifest_sha256=sha(backup/'snapshot_manifest.json'))
    CONFIG.write_text(json.dumps(config,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'protocol.json').write_text(json.dumps({k:v for k,v in config.items() if k!='files'},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(dict(status=config['status'],files=len(files),bytes=sum(r['bytes'] for r in manifest),backup=str(backup),output=str(output)),ensure_ascii=True),flush=True)

if __name__=='__main__':main()
