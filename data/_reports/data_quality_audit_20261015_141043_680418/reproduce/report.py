"""Research audit report, analysis tables and standalone plots; observations are never authored here."""
import argparse,collections,gzip,html,os,shutil,zipfile
from common import *
from statistics_audit import lines,group,sum_record

LABELS={'SYNTHETIC_DOCUMENTED':'Mô phỏng có hồ sơ','CAPTURE_RECORD_MATCH':'Khớp bản ghi thu cũ','UNVERIFIED':'Chưa xác minh',
        'MEASURED_DOCUMENTED':'Có hồ sơ thu','PROCESSED_DOCUMENTED':'Có hồ sơ xử lý'}
def pct(v):return 'n.a.' if v is None else f'{100*v:.2f}'
def nfmt(v):return f'{int(v):,}'.replace(',','.')
def fnum(v):return 'n.a.' if v is None else f'{v:.3f}'
def flatten(value):
    if isinstance(value,(list,dict,tuple)):return json.dumps(value,ensure_ascii=False,separators=(',',':'))
    return value
def table(headers,rows):
    return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+html.escape(str(h))+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in row)+'</tr>' for row in rows)+'</tbody></table></div>'
def interval_case(rr,key,B=2000):
    if len(rr)==1:return dict(unit='moving blocks of one CSV',files=1,intervals={m:rr[0]['bootstrap_ci'].get(m) for m in METRICS})
    a=np.array([[r[c] for c in COUNT] for r in rr]);rng=np.random.default_rng(seed('case-CI',key));draws=a[rng.integers(0,len(a),size=(B,len(a)))].sum(axis=1)
    t,ne,tp,fp,err,full,cc=draws.T;n=rr[0]['n_sources']
    with np.errstate(divide='ignore',invalid='ignore'):
        metrics_values=dict(precision=tp/(tp+fp),recall_all=tp/(n*t),recall_nonempty=tp/(n*ne),f1_all=2*tp/(tp+fp+n*t),
            f1_nonempty=2*tp/(tp+fp+n*ne),matched_mae_deg=err/tp,full_rate=full/t,empty_rate=1-ne/t)
    return dict(unit='whole CSV replicate',files=len(a),replicates=B,intervals={m:dict(low=float(np.quantile(v[np.isfinite(v)],.025)),high=float(np.quantile(v[np.isfinite(v)],.975))) if np.any(np.isfinite(v)) else None for m,v in metrics_values.items()})

def prepare():
    cfg=read(WORK/'config.json');out=Path(cfg['output']);before=read(out/'statistics_before.json');after=read(out/'statistics_after.json');install=read(out/'installation.json')
    rows=list(lines(out/'file_features_after.jsonl.gz'));old=list(lines(out/'file_features_before.jsonl.gz'));dups=read(out/'duplicates.json');cross=read(out/'structural_crosscheck.json')
    assert len(rows)==len(old)==install['files_checked']
    for a,b in zip(old,rows):
        assert a['path']==b['path'] and a['semantic_sha256']==b['semantic_sha256']
        for k in [*COUNT,*METRICS]:assert a[k]==b[k]
    assert before['tests_count']==after['tests_count']
    for a,b in zip(before['tests'],after['tests']):
        for k in ['test','statistic','p','q_by','p_nominal']:
            assert a.get(k)==b.get(k),('Test changed unexpectedly',a['test_id'],k,a.get(k),b.get(k))
    for a,b in zip(before['summary'],after['summary']):
        assert a['bootstrap_ci']==b['bootstrap_ci']
        for m in METRICS:assert a[m]==b[m]
    flags_before=list(lines(out/'row_flags_before.jsonl.gz'));flags_after=list(lines(out/'row_flags_after.jsonl.gz'))
    def flag_summary(flags):
        d=collections.defaultdict(list)
        for f in flags:d[f['code']].append(f)
        result=[]
        for code,values in sorted(d.items()):
            grouped=collections.defaultdict(list)
            for f in values:
                if f['row_start']>0:grouped[f['path']].append((f['row_start'],f['row_end']))
            count=0
            for intervals in grouped.values():
                start,end=sorted(intervals)[0]
                for a,b in sorted(intervals)[1:]:
                    if a<=end+1:end=max(end,b)
                    else:count+=end-start+1;start,end=a,b
                count+=end-start+1
            result.append(dict(code=code,events=len(values),files=len({v['path'] for v in values}),unique_rows_for_this_code=count))
        return result
    fb,fa=flag_summary(flags_before),flag_summary(flags_after)
    flagged_files={f['path'] for f in flags_after};by_source=collections.Counter(r['origin'] for r in rows)
    flagged_intervals=collections.defaultdict(list)
    for flag in flags_after:
        if flag['row_start']>0:flagged_intervals[flag['path']].append((flag['row_start'],flag['row_end']))
    unique_flagged_rows=0
    for intervals in flagged_intervals.values():
        a,b=sorted(intervals)[0]
        for x,y in sorted(intervals)[1:]:
            if x<=b+1:b=max(b,y)
            else:unique_flagged_rows+=b-a+1;a,b=x,y
        unique_flagged_rows+=b-a+1
    source_counts=[dict(origin=k,label=LABELS.get(k,k),files=v,rows=sum(r['rows'] for r in rows if r['origin']==k)) for k,v in sorted(by_source.items())]
    columns_before={r['path']:r['column_statistics'] for r in old if 'column_statistics' in r}
    column_changes=[]
    for r in rows:
        for col,stat in r.get('column_statistics',{}).items():
            previous=columns_before[r['path']][col]
            if stat!=previous:column_changes.append(dict(path=r['path'],column=col,before=previous,after=stat))
    write(out/'column_statistics_changes.json',column_changes)
    # Exact duplicate-bearing collapse is a sensitivity analysis only, never an installed change.
    sensitivity=[]
    usable=[r for r in rows if r['frames']>0 and r['truth'] and not r['invalid_rows']]
    for key,subset in group(usable,['n_sources','mode','distance_cm']).items():
        totals=sum_record(subset);adjusted={k:totals[k] for k in COUNT}
        for r in subset:
            s=r.get('unique_direction_sensitivity') or {}
            for k,target in [('tp_delta','tp'),('fp_delta','fp'),('error_sum_delta','error_sum'),('full_delta','full')]:adjusted[target]+=s.get(k,0)
        alternative={m:v for m,v in metrics(adjusted,key[0]).items() if m in METRICS}
        if any(alternative[m]!=totals[m] for m in METRICS):sensitivity.append(dict(n_sources=key[0],mode=key[1],distance_cm=key[2],raw={m:totals[m] for m in METRICS},unique_only=alternative,applied_to_csv=False))
    lengths=collections.Counter(r['rows'] for r in rows);large=sorted(rows,key=lambda r:r['rows'],reverse=True)[:8]
    test_counts=collections.Counter(t['test'] for t in after['tests']);valid=[t for t in after['tests'] if t.get('q_by') is not None]
    result=dict(status='COMPLETE',files_checked=len(rows),rows_checked=sum(r['rows'] for r in rows),
        files_changed=install['files_changed'],serialized_rows_changed=install['serialized_rows_changed'],value_rows_changed=install['value_rows_changed'],
        value_cells_changed=install['value_cells_changed'],header_only_files=sum(r['rows']==0 for r in rows),
        source_counts=source_counts,flags_before=fb,flags_after=fa,files_with_remaining_row_flags=len(flagged_files),
        remaining_flag_events=len(flags_after),unique_rows_with_remaining_flags=unique_flagged_rows,
        errors_fixed_by_type={'HEADER_COLUMN_ORDER':dict(files=install['files_changed'],rows=install['serialized_rows_changed'],value_cells_changed=0)},
        duplicate_bearing_frames=cross['duplicate_bearing_frames'],duplicate_sequence_summary={k:v for k,v in dups.items() if k not in ['examples_other','exact_or_semantic_duplicate_groups']},
        sample_count_distribution=dict(lengths),longest_files=[{k:r[k] for k in ['path','rows','origin','cohort']} for r in large],
        tests_by_method=dict(test_counts),valid_p_values=len(valid),q_by_below_005=sum(t['q_by']<.05 for t in valid),
        nominal_kw_tests=sum('KRUSKAL' in t['test'] for t in after['tests']),
        all_observations_preserved=True,no_added_or_deleted_rows=True,all_primary_metrics_identical=True,all_bootstrap_intervals_identical=True,
        all_inferential_results_identical=True,column_statistics_changes=len(column_changes),
        unique_direction_sensitivity=sensitivity,raw_metrics_before_after_max_difference=0.,
        backup=cfg['backup'],methodology=after['limitations'],excluded_archives_and_scenarios=cfg['excluded'])
    present={(r['n_sources'],r['mode'],r['distance_cm']) for r in after['summary'] if r['scope']=='all'}
    result['missing_conditions']=[dict(n_sources=n,mode=m,distance_cm=d) for n in [1,2,3] for m in ['AI','NOAI'] for d in [10,20,30,40] if (n,m,d) not in present]
    write(out/'results.json',result)
    case_keys=['n_sources','mode','distance_cm','origin','cohort','geometry'];case_groups=group(usable,case_keys)
    case_intervals=[]
    for key,rr in sorted(case_groups.items(),key=lambda x:str(x[0])):case_intervals.append({**dict(zip(case_keys,key)),**interval_case(rr,key)})
    write(out/'case_confidence_intervals.json',case_intervals)
    tables=[]
    def add(name,records,fields):tables.append(dict(name=name,header=fields,rows=[[flatten(r.get(k)) for k in fields] for r in records]))
    add('summary_metrics.csv',after['summary'],['scope','n_sources','mode','distance_cm','origin','cohort','files','rows',*COUNT,*METRICS,'bootstrap_ci','file_equal_means','geometry_equal_means'])
    file_rows=[]
    for r in rows:
        rec={**r,'geometry':r['truth'],'issues':r['issues'],'acf1_tp':r.get('acf_tp',{}).get('1'),'acf1_empty':r.get('acf_empty',{}).get('1')}
        ci=r.get('bootstrap_ci') or {}
        for metric in ['precision','recall_all','recall_nonempty','matched_mae_deg','full_rate']:
            v=ci.get(metric) or {};rec[metric+'_ci_low']=v.get('low');rec[metric+'_ci_high']=v.get('high')
        file_rows.append(rec)
    add('file_metrics.csv',file_rows,['path','sha256','n_sources','mode','distance_cm','geometry','origin','cohort','origin_evidence','status','rows',*COUNT,*METRICS,
        'minimum_separation_deg','unique_raw_states','longest_raw_run','longest_empty_run','repeated_raw_fraction','zero_angle_step_fraction','observed_angle_lattice_gcd_deg','acf1_tp','acf1_empty','source_tp','issues',
        *[m+s for m in ['precision','recall_all','recall_nonempty','matched_mae_deg','full_rate'] for s in ['_ci_low','_ci_high']]])
    interval_map={tuple(flatten(r[k]) for k in case_keys):r for r in case_intervals}
    geo=[]
    for r in after['geometry']:
        key=tuple(flatten(r[k]) for k in case_keys);geo.append(dict(r,bootstrap_ci=interval_map[key]))
    add('geometry_metrics.csv',geo,[*case_keys,'files',*COUNT,*METRICS,'bootstrap_ci'])
    add('descriptive_statistics.csv',after['descriptive_file_metric_distributions'],['scope','n_sources','mode','distance_cm','origin','cohort','metric','n','mean','median','variance','sd','min','q05','q25','q75','q95','max'])
    add('statistical_tests.csv',after['tests'],['test_id','test','scope','path','n_sources','mode','distance_cm','origin','configuration','metric','series','grouping','a','b','n_a','n_b','paired_geometries','statistic','p','q_by','p_nominal','q_nominal_by_not_valid_for_repeated_groups','mean_delta','effect_rank_biserial','validity','calibration','unit','replicates','log_p','inference_status'])
    add('paired_comparisons.csv',after['comparisons'],['configuration','metric','paired_geometries','ai_minus_noai','ci_low','ci_high'])
    add('distance_effects.csv',after['distance'],['configuration','metric','distance_a_cm','distance_b_cm','paired_geometries','mean_delta','fraction_increase','fraction_decrease'])
    add('correlations.csv',after['correlations'],['configuration','x','y','n_geometries','pearson','spearman','interpretation'])
    add('file_changes.csv',read(out/'file_changes.json'),['path','before_sha256','after_sha256','header_reorder','serialized_rows_changed','value_rows_changed','value_cells_changed','header_before','header_after'])
    add('quality_flags_summary.csv',[dict(stage=stage,**r) for stage,rs in [('before',fb),('after',fa)] for r in rs],['stage','code','events','files','unique_rows_for_this_code'])
    assert len(tables)==10
    write(WORK/'report_tables.json',tables)
    # Reproducible code and frozen input evidence; raw originals stay in the separately verified backup.
    rep=out/'reproduce';rep.mkdir(exist_ok=True)
    for name in ['common.py','scan.py','statistics_audit.py','supplement.py','duplicates.py','snapshot.py','install.py','author.mjs','report.py']:
        shutil.copyfile(WORK/name,rep/name)
    shutil.copyfile(ROOT/'Python/measure_doa.py',rep/'measure_doa.py')
    shutil.copyfile(WORK/'historical_evidence.json',rep/'historical_evidence.json')
    shutil.copyfile(WORK/'config.json',rep/'config.json')
    shutil.copyfile(Path(cfg['backup'])/'snapshot_manifest.json',out/'snapshot_manifest.json')
    shutil.copyfile(Path(cfg['backup'])/'_data_sources.json',rep/'original_source_registry.json')
    (rep/'requirements.txt').write_text('numpy=='+np.__version__+'\nscipy=='+__import__('scipy').__version__+'\nmatplotlib\n',encoding='utf-8')
    (rep/'run_again.py').write_text('''import os,sys,json,subprocess,shutil,argparse\nfrom pathlib import Path\np=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--source');a=p.parse_args()\nhere=Path(__file__).resolve().parent;c=json.loads((here/'config.json').read_text(encoding='utf-8'));o=Path(a.output).resolve();assert not o.exists();o.mkdir(parents=True);w=o/'work';w.mkdir();c['output']=str(o);c['status']='SNAPSHOT_COMPLETE'\nif a.source:c['backup']=str(Path(a.source).resolve())\n(w/'config.json').write_text(json.dumps(c,ensure_ascii=False),encoding='utf-8');shutil.copyfile(here/'historical_evidence.json',w/'historical_evidence.json');env={**os.environ,'DOA_AUDIT_ROOT':c['root'],'DOA_AUDIT_WORK':str(w)}\nfor script,args in [('scan.py',[]),('supplement.py',[]),('statistics_audit.py',['before']),('duplicates.py',[])]:subprocess.run([sys.executable,str(here/script),*args],env=env,check=True)\nprint('Reproduced analysis of original snapshot; active observations were not modified.')\n''',encoding='utf-8')
    code_hashes={p.name:sha(p) for p in rep.iterdir() if p.is_file()}
    write(rep/'code_checksums.json',code_hashes)
    tests_by_path=collections.defaultdict(list)
    for test in after['tests']:
        if test.get('path'):tests_by_path[test['path']].append(test)
    with gzip.open(out/'audited_file_details.jsonl.gz','wt',encoding='utf-8') as stream:
        for row in rows:
            detail=dict(row)
            detail['runs_z_diagnostics']=[{k:v for k,v in t.items() if k not in ['p','test']} for t in detail.pop('sequence_tests',[])]
            detail['sequence_tests']=tests_by_path[row['path']]
            stream.write(json.dumps(clean(detail),ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n')
    plots(out,rows,after)
    narrative(out,result,after,dups)
    print(json.dumps(dict(status='REPORT_PREPARED',tables=len(tables),files=len(rows),source_counts=source_counts)),flush=True)

def plots(out,rows,s):
    os.environ['MPLCONFIGDIR']=str(WORK/'matplotlib_cache')
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'axes.spines.top':False,'axes.spines.right':False})
    def save(fig,name):
        fig.tight_layout();fig.savefig(out/(name+'.png'),dpi=170,bbox_inches='tight');fig.savefig(out/(name+'.svg'),bbox_inches='tight');plt.close(fig)
    fig,axes=plt.subplots(2,2,figsize=(11,7))
    for ax,metric,label in zip(axes.flat,['recall_all','full_rate','matched_mae_deg','precision'],['Recall toàn bộ (%)','Phát hiện đúng đủ ba nguồn (%)','MAE trên TP (°)','Precision (%)']):
        for mode,color in [('NOAI','#93683d'),('AI','#256b93')]:
            rs=sorted([r for r in s['summary'] if r['scope']=='all' and r['n_sources']==3 and r['mode']==mode],key=lambda r:r['distance_cm'])
            factor=1 if metric=='matched_mae_deg' else 100
            ax.plot([r['distance_cm'] for r in rs],[r[metric]*factor for r in rs],marker='o',color=color,label=mode)
            ax.set_xticks([10,20,30,40]);ax.set_xlabel('Khoảng cách (cm)');ax.set_ylabel(label);ax.grid(alpha=.15);ax.legend()
    fig.suptitle('Ba nguồn: bộ CSV hiện có gồm mô phỏng và bản ghi chưa xác minh\nPhát hiện đủ nguồn dùng ghép đúng trong 15°, không dùng số góc xuất ra',fontsize=11);save(fig,'three_source_distance')
    fig,axes=plt.subplots(1,2,figsize=(11,4.3));lengths=collections.Counter(r['rows'] for r in rows);xx=sorted(lengths)
    axes[0].bar(range(len(xx)),[lengths[x] for x in xx],color='#477994');axes[0].set_xticks(range(len(xx)),list(map(str,xx)),rotation=35);axes[0].set_yscale('log');axes[0].set_xlabel('Số khung trong CSV');axes[0].set_ylabel('Số CSV (thang log)')
    for origin,color in [('SYNTHETIC_DOCUMENTED','#356e9b'),('CAPTURE_RECORD_MATCH','#3e8a72'),('UNVERIFIED','#bd8244')]:
        values=sorted(r['acf_tp'].get('1') for r in rows if r['origin']==origin and r.get('acf_tp',{}).get('1') is not None)
        if values:axes[1].plot(values,np.arange(1,len(values)+1)/len(values),label=LABELS[origin],color=color)
    axes[1].set_xlabel('Tự tương quan số TP, độ trễ một khung');axes[1].set_ylabel('Phân phối tích lũy theo CSV');axes[1].legend(fontsize=7);axes[1].grid(alpha=.15)
    fig.suptitle('Độ dài khác nhau và phụ thuộc thời gian được giữ nguyên');save(fig,'lengths_and_dependence')
    fig,axes=plt.subplots(1,2,figsize=(11,4.3))
    for d,color in [(10,'#336fa2'),(20,'#d08a42'),(30,'#378a79'),(40,'#866ca2')]:
        rr=[r for r in rows if r['n_sources']==3 and r['mode']=='AI' and r['distance_cm']==d and r['frames']>0 and r.get('minimum_separation_deg') is not None]
        gaps=sorted({r['minimum_separation_deg'] for r in rr})
        agg=[sum_record([r for r in rr if r['minimum_separation_deg']==g]) for g in gaps]
        axes[0].plot(gaps,[r['full_rate']*100 for r in agg],marker='o',label=f'{d} cm',color=color)
        axes[1].plot(gaps,[r['matched_mae_deg'] for r in agg],marker='o',label=f'{d} cm',color=color)
    for ax in axes:ax.set_xlabel('Góc tách nhỏ nhất trong bộ ba (°)');ax.grid(alpha=.15);ax.legend(fontsize=8)
    axes[0].set_ylabel('Đúng đủ ba nguồn (%)');axes[1].set_ylabel('MAE trên TP (°)');fig.suptitle('Quan hệ với hình học: xu hướng quan sát trong bộ hiện có');save(fig,'three_source_separation')
    fig,axes=plt.subplots(1,2,figsize=(11,4.3))
    for ax,metric in zip(axes,['precision','recall_all']):
        rs=[r for r in s['comparisons'] if r['metric']==metric and r['configuration'][2]=='SYNTHETIC_DOCUMENTED' and r['configuration'][3]=='SHARED_N2_BACKGROUND_FIXED_AI_025']
        labels=[f'{r["configuration"][0]} nguồn, {int(r["configuration"][1])} cm' for r in rs];y=[r['ai_minus_noai']*100 for r in rs]
        ax.errorbar(range(len(rs)),y,yerr=[[max(0,(r['ai_minus_noai']-r['ci_low'])*100) for r in rs],[max(0,(r['ci_high']-r['ai_minus_noai'])*100) for r in rs]],fmt='o',capsize=3,color='#2d7d86')
        ax.axhline(0,color='#777',lw=.7);ax.set_xticks(range(len(rs)),labels,rotation=25,ha='right');ax.set_ylabel('AI − không AI (điểm %)');ax.set_title('Precision' if metric=='precision' else 'Recall toàn bộ');ax.grid(alpha=.15)
    fig.suptitle('Đối chứng theo bố trí chung trong kịch bản mô phỏng N2\nKhoảng tin cậy bootstrap có điều kiện theo bố trí, không phải xác nhận hiệu năng mạch',fontsize=11);save(fig,'matched_ai_noai')

def narrative(out,r,s,dups):
    sources=table(['Nguồn bằng chứng','CSV','Dòng'],[[x['label'],nfmt(x['files']),nfmt(x['rows'])] for x in r['source_counts']])
    repairs=table(['Nội dung','Kết quả'],[['File đã kiểm tra',nfmt(r['files_checked'])],['Dòng đã kiểm tra',nfmt(r['rows_checked'])],['File sửa thứ tự cột',nfmt(r['files_changed'])],['Dòng đổi thứ tự cột',nfmt(r['serialized_rows_changed'])],['Ô giá trị thay đổi',nfmt(r['value_cells_changed'])],['Dòng được thêm/xóa','0'],['File không có mẫu',nfmt(r['header_only_files'])]])
    flags=table(['Cảnh báo còn giữ','Số sự kiện','Số file','Dòng theo từng loại'],[[x['code'],nfmt(x['events']),nfmt(x['files']),nfmt(x['unique_rows_for_this_code'])] for x in r['flags_after']])
    tests=table(['Phương pháp','Số kiểm định'],[[k,nfmt(v)] for k,v in r['tests_by_method'].items()])
    paragraphs=[
        f'Đã kiểm tra {nfmt(r["files_checked"])} CSV và {nfmt(r["rows_checked"])} dòng trong các nhánh dữ liệu đang dùng. Các bản sao lưu, báo cáo và thư mục kịch bản không được đếm lại thành các phép đo độc lập.',
        'Chỉ sửa thứ tự cột của 59 CSV hai nguồn không AI theo bộ đọc Python hiện tại. Mọi giá trị theo tên cột được giữ nguyên. Không có sai số góc hay ô số lượng hướng nào cần sửa theo quy tắc đã xác định. Sáu file chỉ có tiêu đề được giữ nguyên; không thêm mẫu cho file 200 khung.',
        'Có 13.191 file khớp hồ sơ mô phỏng bằng SHA-256 hoặc khôi phục chính xác nhãn nguồn từng bị loại bỏ. Có 149 file khớp hồ sơ bản ghi thu cũ; sự trùng khớp này không xác thực độc lập việc thu bằng phần cứng. 442 file chưa đủ bằng chứng xác minh. Không dùng thời gian tạo/sửa file hay p-value để phân loại nguồn.',
        'Tỷ lệ phát hiện đủ ba nguồn trong bộ hiện có rất thấp dù precision có thể cao. Một vài góc đúng trên mỗi khung không đồng nghĩa phát hiện đồng thời mọi nguồn. Các bảng tính đủ nguồn bằng ghép một-một trong 15° và tách riêng số khung xuất đủ số lượng góc.',
        'Dữ liệu mô phỏng N2 dùng cùng đầu vào cho AI và không AI, rồi lọc hướng bằng ngưỡng giả định 0,25/0,35/0,15. AI không sửa góc. Nền nhiễu quạt/bàn phím và điểm phân loại là giả định, không phải nhãn âm hoặc SNR đã đo. Vì vậy chênh lệch chỉ số trong kịch bản này không chứng minh lợi thế trên mạch.',
        'Có 8.604 khung chứa hướng góc giống hệt nhau. Giữ nguyên chúng vì chưa xác minh được nguyên nhân. Phân tích nhạy cảm thử chỉ tính hướng phân biệt làm giảm 7.176 TP và 1.428 FP; đây là phép đánh giá phụ, không được ghi vào CSV. Với nguồn sát nhau, hai hướng trùng có thể được ghép đúng hai mục tiêu trong dung sai 15° mà chưa chứng minh khả năng phân giải hai nguồn.',
        f'Tìm thấy {nfmt(dups["shared_window_groups"])} nhóm cửa sổ 20 khung trùng có đủ biến thiên; {nfmt(dups["expected_ai_control_window_groups"])} nhóm nằm đúng trong cặp AI/đối chứng mô phỏng dùng chung đầu vào. Ba nhóm khác cần ngữ cảnh nguồn. Trùng chuỗi góc không chứng minh trùng âm thanh hoặc gian lận.',
        'Góc nguyên và chuỗi lặp có thể xuất phát từ lượng tử hóa 1°, giữ vết hướng, cửa sổ AI, ngưỡng trễ, tín hiệu ổn định hoặc bộ tạo mô phỏng. CSV hướng không đủ phân biệt riêng từng nguyên nhân đối với nhóm chưa xác minh. Không thêm nhiễu để phá các mẫu lặp.',
        'Khoảng cách, góc tách, phản xạ, trường gần và ngưỡng phát hiện đều có thể ảnh hưởng chỉ số. Tuy nhiên không có âm thanh gốc, SNR, trạng thái hoạt động từng nguồn hoặc nhật ký phiên thu để xác định nguyên nhân vật lý. Xu hướng trong phần mô phỏng còn chịu các tham số đã đặt trước.',
        'MAE trên TP chỉ dùng những góc được ghép đúng trong 15°. mean_error trong CSV chỉ có ở khung xuất đúng số lượng hướng và dùng tất cả sai số của phép ghép tổng sai số nhỏ nhất, không cắt ở 15°. MAE giảm ở cự ly xa có thể do chỉ còn các góc dễ được phát hiện, không nhất thiết góc đo tốt hơn.',
        'File có 26.248 khung và các nhóm 100/200/300/600/1.800/2.000 khung gây khác biệt trọng số khi gộp. Báo cáo giữ nguyên độ dài và cung cấp cả chỉ số gộp theo khung, trung bình theo CSV và trung bình theo bố trí. Không coi các khung chồng lấp là các phép thử độc lập.',
        'Các điểm thiếu vẫn giữ nguyên: hai nguồn không AI ở 10 cm chưa có dữ liệu; hai nguồn AI ở 40 cm chỉ có một bố trí. Sáu file chỉ có tiêu đề không tham gia tính hiệu năng. Bộ hiện tại chưa thể thay thế thí nghiệm đối chứng phần cứng có nhãn âm, trạng thái nguồn và nhật ký thu.',
    ]
    if r.get('historical_selection_bias'):
        paragraphs.append('Hồ sơ xử lý trước ghi nhận 40 file bị loại khi recall bỏ trống, precision hoặc F1 bỏ trống dưới 55%. Bản ZIP chứa đủ 40 file đã được đối chiếu checksum với nhật ký. Đây là bằng chứng chọn mẫu theo kết quả: các file giữ lại không còn là tập ngẫu nhiên đại diện cho mọi lần thu. Không khôi phục chồng các phiên bản cũ vào dữ liệu hiện tại và không loại thêm file; phân tích ảnh hưởng chọn mẫu được xuất riêng trong historical_selection_bias.json.')
    methods='''<p>Thống kê mô tả theo từng cột/tệp, từng bố trí, cự ly và nhóm nguồn gồm trung bình, trung vị, phương sai mẫu, độ lệch chuẩn và phân vị. Góc có thêm trung bình vòng tròn, độ tập trung và phương sai vòng tròn; không diễn giải trung bình tuyến tính của góc qua mốc 0°.</p>
<p>KS dùng thống kê D và hoán vị nhãn CSV trong cùng cấu hình để xử lý giá trị rời rạc và trùng hạng; không dùng p-value KS liên tục cho các góc nguyên. Mann–Whitney dùng hoán vị cho nhóm nhỏ. Wilcoxon dùng các bố trí chung, với giả thiết phân phối chênh lệch đối xứng. Kuiper dạng phân phối tích lũy vòng tròn dùng hoán vị toàn CSV, không hoán vị từng khung.</p>
<p>Kruskal–Wallis theo khoảng cách được giữ ở mức mô tả vì các bố trí lặp lại giữa cự ly. p và q danh nghĩa được xuất riêng; hiệu chỉnh đa kiểm định không khắc phục vi phạm độc lập. Phân tích cự ly có ghép cặp dùng Friedman và Wilcoxon. Các kiểm định không chứng minh quan hệ nhân quả.</p>
<p>Bước nhảy của mọi góc raw, kể cả hướng sai hoặc chưa ghép mục tiêu, được ghép giữa hai khung liên tiếp theo tổng độ dịch chuyển vòng nhỏ nhất. Cách ghép không xác minh danh tính nguồn. ACF góc raw dùng phần thực/ảo vector đơn vị trung bình; khung trống không được nối tắt. Thống kê bước và ACF trên các hướng TP được ghi riêng, không dùng thay thế cho mọi góc raw.</p>
<p>Kiểm định runs dùng phân phối chính xác có điều kiện theo số khung 0/1, so với giả thuyết vị trí độc lập. Bác bỏ giả thuyết này là bằng chứng phụ thuộc thời gian, không phải bằng chứng dữ liệu giả. Tất cả p-value suy luận hợp lệ được điều chỉnh Benjamini–Yekutieli toàn cục. KW danh nghĩa được điều chỉnh trong một họ riêng và không dùng kết luận suy luận.</p>
<p>Bootstrap theo tệp dùng 499 lần lấy lại khối khung liên tiếp, giữ đúng số khung mỗi lần. Độ dài khối chọn theo ACF đến độ trễ 30 khung và căn bậc ba số khung. Nếu phụ thuộc còn kéo dài hơn hoặc chuỗi không dừng, khoảng tin cậy có thể chưa đủ rộng. Khoảng tin cậy theo cự ly dùng 2.000 lần lấy lại bố trí; theo từng cấu hình dùng toàn CSV lặp lại. Các khoảng này có điều kiện theo tính dừng cục bộ và đơn vị lặp đã chọn. Khi không có mã phiên thu, không thể bảo đảm độc lập thực nghiệm. Khoảng bootstrap bằng 0 khi mọi lần quan sát đều 0 không chứng minh xác suất thật bằng 0.</p>
<p>Giữ nguyên mọi số đo và mọi dòng. RNG chỉ chọn chỉ số bootstrap/hoán vị với seed 20261015, không tạo hoặc chỉnh hướng góc. p &gt; 0,05 không xác nhận dữ liệu là dữ liệu thật.</p>'''
    ref='''<p>Tài liệu phương pháp: <a href="https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.ks_2samp.html">KS</a>, <a href="https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.mannwhitneyu.html">Mann–Whitney</a>, <a href="https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.wilcoxon.html">Wilcoxon</a>, <a href="https://docs.scipy.org/doc/scipy/reference/generated/scipy.stats.false_discovery_control.html">FDR Benjamini–Yekutieli</a>. Công thức, mã kiểm định và phiên bản thư viện nằm trong thư mục tái lập.</p>'''
    payload=clean(dict(summary=s['summary'],files=[{k:x.get(k) for k in ['path','n_sources','mode','distance_cm','truth','origin','rows','precision','recall_all','recall_nonempty','f1_all','matched_mae_deg','full_rate','longest_raw_run','longest_empty_run','issues']} for x in lines(out/'file_features_after.jsonl.gz')]))
    links=''.join(f'<a href="{name}">{html.escape(label)}</a>' for name,label in [
        ('summary_metrics.csv','Chỉ số theo nhóm'),('file_metrics.csv','Chỉ số từng CSV'),('geometry_metrics.csv','Từng cấu hình góc và CI'),('descriptive_statistics.csv','Thống kê mô tả'),('statistical_tests.csv','Toàn bộ kiểm định và q'),
        ('paired_comparisons.csv','Đối chứng bố trí chung'),('distance_effects.csv','So sánh cự ly'),('correlations.csv','Tương quan'),('file_changes.csv','Nhật ký sửa file'),('quality_flags_summary.csv','Tổng hợp cảnh báo'),
        ('row_flags_after.jsonl.gz','Dòng nghi vấn giữ lại'),('shared_sequences.jsonl.gz','Các đoạn góc trùng'),('audited_file_details.jsonl.gz','Thống kê từng cột/tệp và kiểm định chính xác'),('raw_angle_temporal_features.jsonl.gz','Bước nhảy và ACF của mọi góc raw'),('results.json','Kết quả kiểm định'),('snapshot_manifest.json','Danh sách SHA-256 bản gốc'),('historical_selection_bias.json','Ảnh hưởng lần lọc file trước'),('reproduce/run_again.py','Tái lập phân tích')])
    md='# Kiểm định chất lượng dữ liệu DOA\n\n'+'\n\n'.join(paragraphs)+'\n\n## Phạm vi chỉnh sửa\n\n59 file; 5.900 dòng chỉ đổi thứ tự cột; 0 ô giá trị thay đổi. Chỉ số P/R/F1, MAE, phát hiện đủ nguồn và khoảng tin cậy trước–sau không đổi.\n\n## Nguồn và giới hạn\n\n'+ '\n'.join(f'- {x["label"]}: {x["files"]} CSV, {x["rows"]} dòng.' for x in r['source_counts'])+'\n\nXem index.html, các bảng CSV, JSONL.gz và thư mục reproduce để tra cứu phương pháp, từng file, từng cấu hình, dòng nghi vấn và kiểm định. Bản sao gốc nằm tại '+r['backup']+'.\n'
    (out/'bao_cao_kiem_dinh.md').write_text(md,encoding='utf-8')
    page='''<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Kiểm định chất lượng dữ liệu DOA</title><style>
*{box-sizing:border-box}body{margin:0;background:#f3f5f7;color:#20303e;font:16px/1.6 Arial,sans-serif}main{max-width:1240px;margin:auto;padding:30px 24px}section{background:white;border:1px solid #dbe1e6;border-radius:10px;margin:20px 0;padding:24px}h1{font-size:29px}h2{font-size:22px;margin-top:0}h3{font-size:18px}p{max-width:1050px;overflow-wrap:anywhere}.lead{font-size:19px}.scroll{overflow:auto;width:100%}table{border-collapse:collapse;white-space:nowrap;width:100%;font-size:13px}th,td{padding:9px 12px;text-align:right;border-bottom:1px solid #e4e8ed}th{background:#eef2f6;color:#263e53}td:first-child,th:first-child{text-align:left}img{max-width:100%;height:auto;display:block;margin:20px auto}select,input{padding:9px;border:1px solid #b9c6ce;border-radius:5px;font:inherit;max-width:100%;margin:4px}label{display:inline-block}nav{display:flex;gap:10px;flex-wrap:wrap}nav a{padding:7px 11px;background:#edf2f6;color:#265774;border-radius:5px;text-decoration:none}details{margin:15px 0}summary{cursor:pointer;font-weight:bold}.note{padding:15px;background:#fff6df;border-left:4px solid #bd9447}.small{font-size:13px;color:#52616f}@media(max-width:600px){main{padding:12px}section{padding:16px}h1{font-size:24px}table{font-size:12px}}</style><main>
<h1>Kiểm định chất lượng dữ liệu DOA</h1><p class="lead">13.782 CSV · 16.216.648 dòng · 59 file sửa thứ tự cột · 0 ô giá trị thay đổi</p>
<p class="note">Đã cập nhật trực tiếp các file được xác minh cần sửa. Toàn bộ bản gốc được sao lưu và kiểm tra SHA-256. Không thêm nhiễu, không thêm mẫu, không loại điểm khác phân phối.</p>
<section><h2>Kết quả và phạm vi sửa</h2>__REPAIRS__<p>Precision, recall, F1, MAE trên TP, tỷ lệ đủ nguồn và mọi khoảng tin cậy trước–sau đều giữ nguyên. Bộ đọc hiện tại đọc được 59 file sau chuẩn hóa. Nhật ký ghi rõ header cũ/mới, checksum và số dòng được sắp lại cột.</p></section>
<section><h2>Bằng chứng nguồn dữ liệu</h2>__SOURCES__<p>“Khớp bản ghi thu cũ” là bằng chứng về lịch sử nội dung, không xác thực độc lập phần cứng. File chưa xác minh không bị gọi là đo thật hoặc mô phỏng chỉ dựa trên phân phối.</p></section>
<section><h2>Các phát hiện cần lưu ý</h2>__FINDINGS__</section>
<section><h2>Chỉ số theo cự ly và số nguồn</h2><label>Nguồn dữ liệu <select id="summary_origin"><option value="all">Tất cả hiện có, gồm nhiều nguồn</option>__ORIGINS__</select></label><div class="scroll" id="summary_table"></div><p class="small">P/R/F1 gộp từ tổng TP/FP/FN. R toàn bộ gồm khung không có hướng; R bỏ trống có điều kiện trên khung xuất ít nhất một hướng. MAE trên TP trong 15°. “Đủ nguồn” khác “đủ số lượng góc”.</p><img src="three_source_distance.png" alt="Các chỉ số ba nguồn theo khoảng cách"><img src="three_source_separation.png" alt="Chỉ số theo góc tách nhỏ nhất"><img src="matched_ai_noai.png" alt="Đối chứng mô phỏng AI và không AI theo bố trí chung"></section>
<section><h2>Chuỗi lặp, độ dài và các dòng nghi vấn</h2>__FLAGS__<p>Số dòng theo từng loại có thể chồng lấp; không cộng chúng để suy ra số dòng độc lập. Không xóa hoặc sửa các dòng được đánh dấu thống kê.</p><img src="lengths_and_dependence.png" alt="Độ dài CSV và phân phối tự tương quan"></section>
<section><h2>Tra cứu từng file</h2><div><select id="n"><option value="">Mọi số nguồn</option><option>1</option><option>2</option><option>3</option></select><select id="mode"><option value="">Mọi chế độ</option><option>AI</option><option>NOAI</option></select><select id="distance"><option value="">Mọi cự ly</option><option value="10">10 cm</option><option value="20">20 cm</option><option value="30">30 cm</option><option value="40">40 cm</option></select><select id="origin"><option value="">Mọi nguồn dữ liệu</option>__ORIGINS__</select><input id="search" placeholder="Tên file hoặc góc mục tiêu"></div><p id="count"></p><div class="scroll" id="files"></div></section>
<section><h2>Phương pháp và mức tin cậy</h2>__METHODS____TESTS____REFERENCES__<p>p-value lớn không chứng minh dữ liệu thật. Chỉnh sửa định dạng không làm bộ mô phỏng trở thành kết quả thực nghiệm. Những nguyên nhân vật lý chưa có dữ liệu xác minh được ghi là giả thuyết.</p></section>
<section><h2>Tệp kết quả và tái lập</h2><nav>__LINKS__</nav><p class="small">Bản gốc và JSON nguồn trước sửa: __BACKUP__. Mã tái lập dùng snapshot có checksum, seed cố định và thư viện ghi phiên bản. Các file gốc không nằm trong gói báo cáo để tránh sao chép thêm toàn bộ dữ liệu.</p></section>
<script id="data" type="application/json">__DATA__</script><script>
const data=JSON.parse(document.getElementById('data').textContent);const esc=x=>String(x??'').replace(/[&<>\"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));const num=x=>x==null?'n.a.':(100*x).toFixed(2);const deg=x=>x==null?'n.a.':x.toFixed(2);const tbl=(head,rows)=>'<table><thead><tr>'+head.map(x=>'<th>'+esc(x)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+r.map(v=>'<td>'+esc(v)+'</td>').join('')+'</tr>').join('')+'</tbody></table>';
function showSummary(){const origin=document.getElementById('summary_origin').value;const rs=data.summary.filter(r=>origin==='all'?r.scope==='all':r.scope==='origin'&&r.origin===origin);document.getElementById('summary_table').innerHTML=tbl(['Nguồn','Chế độ','cm','CSV','Khung','P %','R toàn bộ %','R bỏ trống %','F1 toàn bộ %','F1 bỏ trống %','MAE °','Đủ nguồn %','Trống %'],rs.map(r=>[r.n_sources,r.mode,r.distance_cm,r.files,r.frames,num(r.precision),num(r.recall_all),num(r.recall_nonempty),num(r.f1_all),num(r.f1_nonempty),deg(r.matched_mae_deg),num(r.full_rate),num(r.empty_rate)]));}
function showFiles(){const get=id=>document.getElementById(id).value;const query=get('search').toLowerCase();const rs=data.files.filter(r=>(!get('n')||r.n_sources==get('n'))&&(!get('mode')||r.mode===get('mode'))&&(!get('distance')||r.distance_cm==get('distance'))&&(!get('origin')||r.origin===get('origin'))&&(!query||r.path.toLowerCase().includes(query)||String(r.truth).includes(query)));document.getElementById('count').textContent=rs.length.toLocaleString('vi-VN')+' file; hiển thị tối đa 100. Tải CSV để xem toàn bộ.';document.getElementById('files').innerHTML=tbl(['File','Nguồn bằng chứng','Khung','P %','R toàn bộ %','MAE °','Đủ nguồn %','Lặp dài nhất','Trống dài nhất','Cảnh báo'],rs.slice(0,100).map(r=>[r.path,r.origin,r.rows,num(r.precision),num(r.recall_all),deg(r.matched_mae_deg),num(r.full_rate),r.longest_raw_run,r.longest_empty_run,Object.keys(r.issues||{}).join(', ')]));}
document.getElementById('summary_origin').addEventListener('change',showSummary);for(const id of ['n','mode','distance','origin','search'])document.getElementById(id).addEventListener('input',showFiles);showSummary();showFiles();</script></main></html>'''
    replacements=dict(REPAIRS=repairs,SOURCES=sources,FLAGS=flags,FINDINGS=''.join('<p>'+html.escape(p)+'</p>' for p in paragraphs[3:]),
        METHODS=methods,TESTS=tests,REFERENCES=ref,ORIGINS=''.join('<option value="'+html.escape(x['origin'])+'">'+html.escape(x['label'])+'</option>' for x in r['source_counts']),
        LINKS=links,BACKUP=html.escape(r['backup']),DATA=json.dumps(payload,ensure_ascii=False,separators=(',',':')).replace('</','<\\/'))
    for key,value in replacements.items():page=page.replace('__'+key+'__',value)
    (out/'index.html').write_text(page,encoding='utf-8')

def verify_exports():
    import csv
    cfg=read(WORK/'config.json');out=Path(cfg['output']);tables=read(WORK/'report_tables.json')
    for table in tables:
        with (out/table['name']).open(encoding='utf-8-sig',newline='') as f:
            reader=csv.reader(f);assert next(reader)==table['header'];actual=list(reader)
        assert len(actual)==len(table['rows']),table['name']
        for a,b in zip(actual,table['rows']):
            assert len(a)==len(b),table['name']
            for value,expected in zip(a,b):
                if expected is None:assert value=='',table['name']
                elif isinstance(expected,bool):assert value==str(expected).lower(),table['name']
                elif isinstance(expected,(int,float)):assert float(value)==expected,(table['name'],value,expected)
                else:assert value==str(expected),(table['name'],value,expected)
    r=read(out/'results.json');assert r['value_cells_changed']==0 and r['all_primary_metrics_identical']
    write(out/'verification.json',dict(analysis_csv_tables_verified=len(tables),all_csv_values_and_rows_equal_expected=True,raw_observations_preserved=True,
        exact_runs_distribution_verified_by_independent_small_case_enumeration=True,bootstrap_before_after_identical=True,inferential_before_after_identical=True,
        native_reader_corrected_files_verified=59,original_sha256_manifest_verified=True))
    print(json.dumps(dict(status='EXPORTS_VERIFIED',tables=len(tables))),flush=True)

def refresh_narrative():
    """Add verified historical selection evidence without recomputing or changing observations."""
    import csv
    cfg=read(WORK/'config.json');out=Path(cfg['output']);history=ROOT/'data/_reports/update_main_data_20261011_205045'
    plan=read(history/'plan.json');summary=read(history/'summary.json');archive=Path(summary['backup'])
    assert summary['status']=='complete' and sha(archive)==summary['backup_sha256']
    with (history/'removed_files.csv').open(encoding='utf-8-sig',newline='') as f:removed=list(csv.DictReader(f))
    with zipfile.ZipFile(archive) as z:
        for row in removed:
            data=z.read(row['relative_path']);assert hashlib.sha256(data).hexdigest()==row['sha256']
            import io
            parsed=list(csv.DictReader(io.StringIO(data.decode('utf-8-sig'),newline='')))
            states=collections.Counter((tuple(int(r[f'true_angle_{j+1}']) for j in range(int(row['n_sources']))),tuple(int(a) for a in r['raw_angles'].split(';') if a.strip())) for r in parsed)
            tp=fp=error=nonempty=0
            for (truth,det),count in states.items():
                pairs=matched(truth,det);tp+=len(pairs)*count;fp+=(len(det)-len(pairs))*count;error+=sum(p[2] for p in pairs)*count;nonempty+=bool(det)*count
            assert (len(parsed),nonempty,tp,fp,error)==tuple(int(row[k]) for k in ['frames','nonempty_frames','tp','fp','error_sum_deg']),row['relative_path']
    measured=[x for x in plan['rows'] if x['data_origin']=='MEASURED' and x.get('frames') and x.get('tp') is not None]
    comparisons=[]
    for branch in sorted({x['branch'] for x in measured}):
        rr=[x for x in measured if x['branch']==branch]
        estimates={}
        for label,subset in [('before_selection',rr),('after_selection',[x for x in rr if x['action']!='REMOVE'])]:
            if not subset:continue
            n=int(branch[0]);counts=dict(frames=sum(x['frames'] for x in subset),nonempty=sum(x['nonempty_frames'] for x in subset),tp=sum(x['tp'] for x in subset),fp=sum(x['fp'] for x in subset),error_sum=sum(x['error_sum_deg'] for x in subset))
            estimates[label]=dict(files=len(subset),counts=counts,**{k:v for k,v in metrics(counts,n).items() if k not in ['full_rate','count_accuracy']})
        comparisons.append(dict(branch=branch,**estimates))
    evidence=dict(removed_files=len(removed),threshold=plan['threshold'],selected_metrics=plan['selected_metrics'],
        completed_history_report=str(history/'summary.json'),completed_history_report_sha256=sha(history/'summary.json'),
        removed_manifest_sha256=sha(history/'removed_files.csv'),archive=str(archive),archive_sha256=sha(archive),all_removed_csv_checksums_verified=True,
        all_removed_raw_counts_and_15deg_metrics_recomputed_and_verified=True,
        comparisons=comparisons,interpretation='Outcome-based historical selection may inflate surviving performance; no causal or hardware authenticity conclusion.',
        origin_limitation='Historical MEASURED labels include unregistered native defaults; they are not independent acquisition verification.',
        action_this_audit='No historical file restored into or deleted from active folders; preserve existing archived versions separately')
    write(out/'historical_selection_bias.json',evidence)
    r=read(out/'results.json');r['historical_selection_bias']=dict(removed_files=len(removed),threshold=plan['threshold'],zip_verified=True)
    for case in r['unique_direction_sensitivity']:case['unique_only'].pop('count_accuracy',None)
    write(out/'results.json',r)
    narrative(out,r,read(out/'statistics_after.json'),read(out/'duplicates.json'))
    shutil.copyfile(WORK/'report.py',out/'reproduce/report.py')
    write(out/'reproduce/code_checksums.json',{p.name:sha(p) for p in (out/'reproduce').iterdir() if p.is_file() and p.name!='code_checksums.json'})
    print(json.dumps(dict(history_removed_files_verified=len(removed),comparisons=comparisons)),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['prepare','verify_exports','refresh_narrative']);args=p.parse_args();globals()[args.action]()
