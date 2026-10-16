"""Sequence fingerprints detect overlap; provenance determines its interpretation."""
import sqlite3,collections,gzip
from common import *
from statistics_audit import lines

def main():
    cfg=read(WORK/'config.json');out=Path(cfg['output']);rows=list(lines(out/'file_features_before.jsonl.gz'));lookup={r['path']:r for r in rows}
    exact=[]
    for field in ['sha256','semantic_sha256','raw_sequence_sha256','normalized_tp_error_sequence_sha256']:
        groups=collections.defaultdict(list)
        for r in rows:
            if r.get(field) and r['frames']>0:groups[r[field]].append(r['path'])
        for digest,paths in groups.items():
            if len(paths)>1:exact.append(dict(kind=field,hash=digest,files=paths,action='RETAIN_ALL',interpretation='Content overlap; not by itself proof of copying or simulation'))
    db=WORK/'sequence_index.sqlite';assert not db.exists()
    con=sqlite3.connect(db);con.execute('PRAGMA journal_mode=OFF');con.execute('PRAGMA synchronous=OFF')
    con.execute('CREATE TABLE blocks(hash TEXT,path TEXT,start INTEGER,end INTEGER,method TEXT)')
    batch=[];count=0
    for b in lines(out/'sequence_blocks.jsonl.gz'):
        batch.append((b['hash'],b['path'],b['start'],b['end'],b['method']))
        if len(batch)==10000:con.executemany('INSERT INTO blocks VALUES(?,?,?,?,?)',batch);count+=len(batch);batch=[]
    con.executemany('INSERT INTO blocks VALUES(?,?,?,?,?)',batch);count+=len(batch);con.execute('CREATE INDEX idx_hash ON blocks(hash)');con.commit()
    shared=[];expected_controls=0;other=0;files=set()
    candidates=con.execute('SELECT hash,COUNT(DISTINCT path) FROM blocks GROUP BY hash HAVING COUNT(DISTINCT path)>1').fetchall()
    with gzip.open(out/'shared_sequences.jsonl.gz','wt',encoding='utf-8') as stream:
        for digest,num in candidates:
            matches=con.execute('SELECT DISTINCT path,start,end FROM blocks WHERE hash=? ORDER BY path,start',(digest,)).fetchall()
            parents={p for p,s,e in matches};expected=False
            if len(parents)==2:
                a,b=sorted(parents);ra,rb=lookup[a],lookup[b]
                expected=(ra['cohort']==rb['cohort']=='SHARED_N2_BACKGROUND_FIXED_AI_025' and ra['mode']!=rb['mode'] and
                    ra['distance_cm']==rb['distance_cm'] and Path(a).name==Path(b).name and sorted(ra['truth'])==sorted(rb['truth']))
            if expected:expected_controls+=1
            else:other+=1
            files.update(parents)
            obj=dict(hash=digest,frames=20,matches=[dict(path=p,row_start=s,row_end=e) for p,s,e in matches],
                interpretation='EXPECTED_PAIRED_SIMULATION_INPUT_OVERLAP' if expected else 'SHARED_DIRECTIONS_REQUIRES_CONTEXT_NOT_PROOF_OF_FABRICATION',action='RETAIN_ALL')
            stream.write(json.dumps(obj,ensure_ascii=False,separators=(',',':'))+'\n')
            if len(shared)<50 and not expected:shared.append(obj)
    con.close()
    result=dict(exact_or_semantic_duplicate_groups=exact,indexed_informative_windows=count,shared_window_groups=len(candidates),
        expected_ai_control_window_groups=expected_controls,other_shared_window_groups=other,files_with_shared_informative_windows=len(files),
        examples_other=shared,limitations=[
            '20-frame fixed-grid windows plus winnowing of 20-frame rolling hashes in a 64-window span. Long exact overlaps of at least 83 frames are candidates regardless of offset; shorter unaligned overlaps can be missed.',
            'Windows require at least five nonempty frames and five unique direction states; blank/constant segments are analysed separately as runs.',
            'SHA-256 fingerprints compare direction sequences, not audio waveforms. Equal directions do not prove equal recorded sounds or a dishonest origin.',
            'Paired AI/control simulations intentionally share their input. Such overlap is reported separately and never removed.'])
    write(out/'duplicates.json',result)
    print(json.dumps({k:v for k,v in result.items() if k not in ['exact_or_semantic_duplicate_groups','examples_other','limitations']}),flush=True)

if __name__=='__main__':main()
