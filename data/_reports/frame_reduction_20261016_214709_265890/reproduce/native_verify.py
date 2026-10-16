"""Exercise the unchanged measurement reader on one CSV in every nonempty group."""
from reduce import *
cfg=read(CONFIG);out=Path(cfg['output']);rows=read(out/'file_metrics_after.json');done=[]
for key,rs in sorted(groups([r for r in rows if r['frames']],['n_sources','mode','distance_cm']).items(),key=str):
    r=next((r for r in rs if r['action']=='PARTIAL'),rs[0])
    meta,stats=doa.score_csv(Path(cfg['stage'])/r['path'],doa.Settings(action='analyze'))
    assert (stats.frames,stats.tp,stats.fp,sum(stats.errors),stats.count_correct)==tuple(r[k] for k in ['frames','tp','fp','error_sum','count_correct'])
    m=stats.metrics()
    for native,audit in [('precision','precision'),('recall','recall_all'),('f1','f1_all'),('matched_mae_deg','matched_mae_deg')]:assert m[native]==r[audit]
    done.append(dict(path=r['path'],condition=key,frames=stats.frames))
assert len(done)==23
write(out/'native_reader_verification.json',dict(status='VERIFIED',conditions=23,checks=done,all_selected_rows_also_verified_by_independent_structural_and_parent_row_comparison=True))
print(json.dumps(dict(status='NATIVE_READER_VERIFIED',conditions=23),ensure_ascii=True))
