import os,sys,json,subprocess,shutil,argparse
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--source');a=p.parse_args()
here=Path(__file__).resolve().parent;c=json.loads((here/'config.json').read_text(encoding='utf-8'));o=Path(a.output).resolve();assert not o.exists();o.mkdir(parents=True);w=o/'work';w.mkdir();c['output']=str(o);c['status']='SNAPSHOT_COMPLETE'
if a.source:c['backup']=str(Path(a.source).resolve())
(w/'config.json').write_text(json.dumps(c,ensure_ascii=False),encoding='utf-8');shutil.copyfile(here/'historical_evidence.json',w/'historical_evidence.json');env={**os.environ,'DOA_AUDIT_ROOT':c['root'],'DOA_AUDIT_WORK':str(w)}
for script,args in [('scan.py',[]),('supplement.py',[]),('raw_angles.py',[]),('statistics_audit.py',['before']),('duplicates.py',[])]:subprocess.run([sys.executable,str(here/script),*args],env=env,check=True)
print('Reproduced analysis of original snapshot; active observations were not modified.')
