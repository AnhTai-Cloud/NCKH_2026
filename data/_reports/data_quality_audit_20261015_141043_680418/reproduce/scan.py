"""Full row/column audit. Statistical abnormalities never trigger corrections."""
import csv, io, gzip, json, re, hashlib, math, collections, os
from concurrent.futures import ProcessPoolExecutor,as_completed
from common import *

CFG=None;REG=None;HISTORY=None
def init(config):
    global CFG,REG,HISTORY
    CFG=config;REG=read(Path(config['backup'])/'_data_sources.json');HISTORY=read(WORK/'historical_evidence.json')
def number(value):
    try:
        v=float(value)
        return v if math.isfinite(v) else None
    except (ValueError,TypeError):return None
def integer(value):
    v=number(value)
    return int(v) if v is not None and v.is_integer() else None
def origin(relative,digest):
    entry=REG['files'].get(relative,{})
    if entry and entry.get('sha256')==digest:
        if entry.get('quality_audit',{}).get('parent_origin'):
            parent=entry['quality_audit']['parent_origin']
            return parent['origin'],parent['cohort'],parent['origin_evidence']+'; derived/format correction is separately documented'
        label=entry.get('data_origin')
        if label=='SYNTHETIC':return 'SYNTHETIC_DOCUMENTED',entry.get('dataset_kind','HISTORICAL_SIMULATION'), 'Matching external JSON SHA-256'
        if label=='MEASURED':return 'MEASURED_DOCUMENTED','REGISTERED_CAPTURE','Matching measured manifest; hardware acquisition not independently witnessed'
        if label=='PROCESSED':return 'PROCESSED_DOCUMENTED','REGISTERED_PROCESSING','Matching processed manifest; parent origin retained in manifest'
    if digest in HISTORY['synthetic']:return 'SYNTHETIC_DOCUMENTED','HISTORICAL_SIMULATION','Matching historical simulation SHA-256'
    if digest in HISTORY['captures']:return 'CAPTURE_RECORD_MATCH','HISTORICAL_CAPTURE','Byte-identical to historical capture record; physical acquisition not independently witnessed'
    return 'UNVERIFIED','UNVERIFIED','No matching source evidence; distribution is not proof of origin'

def audit_file(item,include_bootstrap=True):
    relative=item['path'];path=Path(CFG['backup'])/relative;content=path.read_bytes()
    assert hashlib.sha256(content).hexdigest()==item['sha256']
    n=int(relative[0]);mode='NOAI' if relative.split('/')[0].endswith('NOAI') else 'AI'
    category,cohort,proof=origin(relative,item['sha256'])
    text=content.decode('utf-8-sig');reader=csv.reader(io.StringIO(text,newline=''));header=next(reader,[])
    if category=='UNVERIFIED' and 'data_origin' not in header:
        lines=text.splitlines()
        for ending in ('\r\n','\n'):
            restored=ending.join([lines[0]+',data_origin']+[line+',SYNTHETIC' for line in lines[1:]])+ending if lines else ''
            if hashlib.sha256(restored.encode()).hexdigest() in HISTORY['synthetic']:
                category,cohort,proof='SYNTHETIC_DOCUMENTED','HISTORICAL_SIMULATION','Exact historical synthetic SHA-256 reconstructed by restoring the formerly removed origin column'
                break
    canonical=doa.csv_fields(n);hindex={v:i for i,v in enumerate(header)}
    record=dict(path=relative,sha256=item['sha256'],bytes=len(content),n_sources=n,mode=mode,origin=category,cohort=cohort,origin_evidence=proof,
                header=header,rows=0,valid_frames=0,invalid_rows=0,issues={},fixable_rows=0,fixable_cells=0,header_reorder=False,truth=None,distance_cm=None)
    record.update(**{k:0 for k in COUNT},sequence_tests=[],bootstrap_ci=None,semantic_sha256=None,
        tp_error_histogram=[0]*31,source_tp=[0]*n,**metrics({},n))
    flags=[];changes=[];rows=[];columns=collections.defaultdict(list);all_angles=[];residuals=[];detected_states=[];aligned=[];per_frame=[];hist=np.zeros(31,int);valid_row_ids=[]
    seen_sample=set();seen_rows=set();configuration=None;counts=collections.Counter();source_tp=[0]*n;before_mean=[];expected_mean=[]
    name=re.fullmatch(r'(\d+)_((?:\d+_)*\d+)dis(\d+)\.csv',Path(relative).name)
    file_truth=tuple(map(int,name[2].split('_'))) if name else None
    file_distance=int(name[3])*10 if name else None
    folder_match=next((re.fullmatch(r'(0\.[1234])m',part) for part in Path(relative).parts if re.fullmatch(r'(0\.[1234])m',part)),None)
    folder_distance=float(folder_match[1])*100 if folder_match else None
    def flag(code,row,detail,kind='UNRESOLVED'):
        counts[code]+=1;flags.append(dict(path=relative,row_start=row,row_end=row,code=code,detail=detail,status=kind))
    if len(set(header))!=len(header) or set(header) not in [set(canonical),set(canonical+['data_origin'])]:
        record.update(status='UNSUPPORTED_HEADER',issues={'UNSUPPORTED_HEADER':1});flags.append(dict(path=relative,row_start=0,row_end=0,code='UNSUPPORTED_HEADER',detail=header,status='UNRESOLVED'));return record,flags,changes,None,[],{}
    target_header=canonical+(['data_origin'] if 'data_origin' in header else [])
    record['header_reorder']=header!=target_header
    if record['header_reorder']:
        flags.append(dict(path=relative,row_start=0,row_end=0,code='HEADER_COLUMN_ORDER',status='FIX_PLANNED',detail='Same named columns reordered to Python/measure_doa.py:csv_fields/valid_csv_header; no observation values changed'))
        counts['HEADER_COLUMN_ORDER']=1
    if REG['files'].get(relative,{}).get('sha256') not in (None,item['sha256']):flag('REGISTRY_HASH_MISMATCH',0,'Content differs from registered checksum; preserve and investigate')
    for row_index,cells in enumerate(reader,1):
        record['rows']+=1;rows.append(cells)
        if len(cells)!=len(header):flag('COLUMN_COUNT',row_index,f'{len(cells)} cells; expected {len(header)}');record['invalid_rows']+=1;continue
        row=dict(zip(header,cells));new={};reasons={}
        raw_row=tuple(cells)
        if raw_row in seen_rows:flag('EXACT_DUPLICATE_ROW',row_index,'Identical recorded CSV row; retained')
        seen_rows.add(raw_row)
        if 'data_origin' in row:
            if row['data_origin'] not in ['SYNTHETIC','MEASURED','PROCESSED']:flag('INVALID_DECLARED_ORIGIN',row_index,row['data_origin'])
            elif category=='SYNTHETIC_DOCUMENTED' and row['data_origin']!='SYNTHETIC':flag('CONFLICTING_ORIGIN_METADATA',row_index,row['data_origin'])
        def set_cell(col,value,reason):
            if row[col]!=value:new[col]=value;reasons[col]=reason
        for col,value in row.items():
            if col not in ['raw_angles','data_origin']:
                val=number(value)
                if val is not None:columns[col].append(val)
                elif value.strip():flag('NONNUMERIC_CELL',row_index,col)
        sample=integer(row['sample'])
        if sample is None or sample<1:flag('SAMPLE_INVALID',row_index,row['sample'])
        else:
            if sample in seen_sample:flag('SAMPLE_DUPLICATE',row_index,str(sample))
            seen_sample.add(sample)
            if sample!=row_index:flag('SAMPLE_SEQUENCE',row_index,f'recorded={sample}; row={row_index}; no automatic renumbering')
        truth=tuple(integer(row[f'true_angle_{j+1}']) for j in range(n));distance=number(row['distance_cm'])
        try:
            tokens=row['raw_angles'].split(';') if row['raw_angles'].strip() else []
            assert all(token.strip() for token in tokens)
            det=tuple(integer(token) for token in tokens)
            assert all(a is not None and 0<=a<360 for a in det) and len(det)<=3
        except (ValueError,AssertionError):det=None;flag('RAW_ANGLES_INVALID',row_index,row['raw_angles'])
        truth_ok=all(a is not None and 0<=a<360 for a in truth) and len(set(truth))==n
        if not truth_ok:flag('TRUE_ANGLES_INVALID',row_index,str(truth))
        if distance not in (10,20,30,40):flag('DISTANCE_INVALID_OR_UNEXPECTED',row_index,str(distance))
        if truth_ok and file_truth is not None and sorted(truth)!=sorted(file_truth):flag('FILENAME_TRUTH_MISMATCH',row_index,str(truth))
        if distance is not None and file_distance is not None and abs(distance-file_distance)>1e-9:flag('FILENAME_DISTANCE_MISMATCH',row_index,str(distance))
        if distance is not None and folder_distance is not None and abs(distance-folder_distance)>1e-9:flag('FOLDER_DISTANCE_MISMATCH',row_index,str(distance))
        current=(truth,distance)
        if configuration is None:configuration=current;record.update(truth=truth,distance_cm=distance)
        elif current!=configuration:flag('CONFIGURATION_CHANGES',row_index,str(current))
        old_count=integer(row['detected_count'])
        if det is not None and old_count!=len(det):
            # Raw directions are never reconstructed. A blank raw field with a positive count is ambiguous data loss.
            if len(det)>0 or old_count in (None,0):
                set_cell('detected_count',str(len(det)),'DERIVED_COUNT_FROM_VALID_RAW_ANGLES')
            else:flag('COUNT_WITH_MISSING_RAW_AMBIGUOUS',row_index,f'count={old_count}, raw field empty')
        if det is not None and len(set(det))!=len(det):flag('DUPLICATE_DIRECTIONS_WITHIN_FRAME',row_index,str(det))
        if det is None or not truth_ok or distance is None:
            record['invalid_rows']+=1
        else:
            record['valid_frames']+=1;detected_states.append(det);all_angles.extend(det);valid_row_ids.append(row_index)
            pairs=matched(truth,det);tp=len(pairs);err=sum(v[2] for v in pairs);success=int(tp==n)
            per_frame.append((1,int(bool(det)),tp,len(det)-tp,err,success,int(len(det)==n)))
            al=[float('nan')]*n
            for j,k,e in pairs:source_tp[j]+=1;al[j]=signed(det[k],truth[j]);residuals.append(al[j]);hist[al[j]+15]+=1
            aligned.append(al)
            if len(det)==n:
                opts=optimal(truth,det);stored=tuple(integer(row[f'detected_angle_{j+1}']) for j in range(n))
                chosen=stored if stored in opts else opts[0]
                errors=[circ(a,t) for a,t in zip(chosen,truth)];mean=sum(errors)/n
                expected_mean.append(mean)
                existing_mean=number(row['mean_error'])
                if existing_mean is not None:before_mean.append(existing_mean)
                for j,(a,e) in enumerate(zip(chosen,errors),1):
                    if integer(row[f'detected_angle_{j}'])!=a:set_cell(f'detected_angle_{j}',str(a),'MINIMUM_TOTAL_CIRCULAR_ERROR_ONE_TO_ONE')
                    if number(row[f'error_{j}']) is None or abs(number(row[f'error_{j}'])-e)>1e-9:set_cell(f'error_{j}',str(e),'CIRCULAR_ERROR_FROM_UNCHANGED_RAW_AND_TRUTH')
                if existing_mean is None or abs(existing_mean-mean)>.00500001:set_cell('mean_error',f'{mean:.2f}','MEAN_OF_ALL_COMPLETE_COUNT_CIRCULAR_ERRORS_ROUNDED_2DP')
            elif any(row[col].strip() for col in [*[f'detected_angle_{j+1}' for j in range(n)],*[f'error_{j+1}' for j in range(n)],'mean_error']):
                flag('PARTIAL_DERIVED_NONEMPTY_UNCERTAIN',row_index,'Partial-count derived fields may reflect another processing convention; retained')
        if new:
            record['fixable_rows']+=1;record['fixable_cells']+=len(new)
            changes.append(dict(path=relative,row=row_index,original_sample=row['sample'],before_sha256=item['sha256'],
                                cells=[dict(column=col,old=row[col],new=val,rule=reasons[col]) for col,val in new.items()]))
            for col,val in new.items():cells[hindex[col]]=val;counts['FIX_'+reasons[col]]+=1
    record['issues']=dict(counts)
    if not record['rows']:record.update(status='HEADER_ONLY');flag('HEADER_ONLY',0,'No samples; retained without padding')
    elif record['invalid_rows']:record['status']='HAS_INVALID_ROWS_RETAINED'
    else:record['status']='READABLE'
    record['issues']=dict(counts)
    array=np.asarray(per_frame,dtype=float)
    totals=dict(zip(COUNT,array.sum(axis=0))) if len(array) else {k:0 for k in COUNT}
    record.update(**totals,source_tp=source_tp,**metrics(totals,n))
    record['full_count_mean_error_before']=describe(before_mean);record['full_count_mean_error_recomputed']=describe(expected_mean)
    record['row_count_short_200']=record['rows']==200
    record['column_statistics']={col:dict(linear=describe(values),**({'circular':circular(values)} if 'angle_' in col else {})) for col,values in columns.items()}
    record['raw_angle_circular']=circular(all_angles);record['signed_tp_error_circular']=circular(residuals);record['signed_tp_error_stats']=describe(residuals)
    record['tp_error_histogram']=hist.tolist()
    record['minimum_separation_deg']=min((circ(a,b) for a,b in itertools.combinations(record['truth'],2)),default=None) if record['truth'] else None
    raw_runs=runs(detected_states);nonempty_runs=[r for r in raw_runs if r[3]];empty_runs=[r for r in raw_runs if not r[3]]
    record.update(unique_raw_states=len(set(detected_states)),longest_raw_run=max((r[2] for r in nonempty_runs),default=0),
        longest_empty_run=max((r[2] for r in empty_runs),default=0),raw_run_lengths=describe([r[2] for r in nonempty_runs]),
        repeated_raw_fraction=sum(max(0,r[2]-1) for r in nonempty_runs)/max(1,sum(bool(v) for v in detected_states)))
    for start,end,length,value in raw_runs:
        if length>=max(20,math.ceil(max(1,len(detected_states))*.1)):
            flags.append(dict(path=relative,row_start=valid_row_ids[start-1],row_end=valid_row_ids[end-1],code='LONG_CONSTANT_DIRECTIONS' if value else 'LONG_EMPTY_RUN',
                              detail=dict(length=length,raw_angles=value),status='STATISTICAL_FLAG_NO_EDIT'))
    if len(array):
        record['acf_full_detection']=acf(array[:,5]);record['acf_empty']=acf(1-array[:,1]);record['acf_tp']=acf(array[:,2])
        al=np.asarray(aligned);record['source_acf']=[acf(al[:,j]) for j in range(n)]
        steps=[];zero_steps=0;valid_steps=0;per_source=[]
        for j in range(n):
            x=al[:,j];valid=np.isfinite(x[:-1])&np.isfinite(x[1:]);diff=(x[1:]-x[:-1]+180)%360-180;v=diff[valid]
            steps.extend(abs(v));zero_steps+=int(np.sum(v==0));valid_steps+=len(v)
            per_source.append(dict(source=j+1,adjacent_valid_pairs=len(v),unchanged_fraction=float(np.mean(v==0)) if len(v) else None))
        record['angle_step_stats']=describe(steps);record['per_source_repetition']=per_source;record['zero_angle_step_fraction']=zero_steps/valid_steps if valid_steps else None
        tests=[]
        for label,y in [('full_detection',array[:,5]),('nonempty',array[:,1])]:
            n1=int(y.sum());n0=len(y)-n1;nr=int(1+np.sum(np.diff(y)!=0));mean=1+2*n1*n0/len(y)
            variance=2*n1*n0*(2*n1*n0-len(y))/(len(y)**2*(len(y)-1)) if len(y)>1 else 0
            if min(n0,n1)>=10 and variance>0:
                z=(nr-mean)/math.sqrt(variance);p=float(2*stats.norm.sf(abs(z)))
                tests.append(dict(test='WALD_WOLFOWITZ_RUNS',series=label,statistic=z,p=p,runs=nr,expected_runs=mean,
                                  null='IID exchangeability of binary frame sequence',unit='frame positions; test is specifically for serial dependence'))
        record['sequence_tests']=tests
        record['bootstrap_ci']=bootstrap_counts(array,n,relative) if include_bootstrap else None
    else:record.update(sequence_tests=[],bootstrap_ci=None,acf_full_detection={},acf_empty={},acf_tp={},source_acf=[],angle_step_stats=describe([]),zero_angle_step_fraction=None)
    record['semantic_sha256']=hashlib.sha256(json.dumps([record['truth'],record['distance_cm'],detected_states],separators=(',',':')).encode()).hexdigest()
    record['raw_sequence_sha256']=hashlib.sha256(json.dumps(detected_states,separators=(',',':')).encode()).hexdigest()
    record['normalized_tp_error_sequence_sha256']=hashlib.sha256(json.dumps(clean(aligned),separators=(',',':'),allow_nan=False).encode()).hexdigest()
    unique_angles=sorted(set(all_angles));increments=np.diff(unique_angles).astype(int)
    record['observed_angle_lattice_gcd_deg']=int(np.gcd.reduce(increments)) if len(increments) else None
    record['integer_angles_only']=True
    record['angle_modulo_10_counts']=[int(sum(a%10==j for a in all_angles)) for j in range(10)]
    blocks=[]
    for start in range(0,len(detected_states)-19,20):
        block=detected_states[start:start+20]
        if sum(bool(v) for v in block)>=5 and len(set(block))>=5:
            h=hashlib.sha256(json.dumps(block,separators=(',',':')).encode()).hexdigest()
            blocks.append(dict(hash=h,start=valid_row_ids[start],end=valid_row_ids[start+19],method='fixed_20_frame_blocks'))
    # Winnowing adds offset-independent candidates for long copied sequences; constant windows are excluded.
    tokens=[int.from_bytes(hashlib.blake2b(repr(v).encode(),digest_size=8).digest(),'little') for v in detected_states]
    base=1000003;mask=(1<<64)-1;power=pow(base,20,1<<64);rolling=[];v=0
    for i,token in enumerate(tokens):
        v=(v*base+token)&mask
        if i>=20:v=(v-tokens[i-20]*power)&mask
        if i>=19:rolling.append(v)
    queue=collections.deque();chosen=set()
    for i,value in enumerate(rolling):
        while queue and rolling[queue[-1]]>=value:queue.pop()
        queue.append(i)
        while queue and queue[0]<i-63:queue.popleft()
        if i>=63:chosen.add(queue[0])
    for start in sorted(chosen):
        block=detected_states[start:start+20]
        if sum(bool(v) for v in block)>=5 and len(set(block))>=5:
            h=hashlib.sha256(json.dumps(block,separators=(',',':')).encode()).hexdigest()
            blocks.append(dict(hash=h,start=valid_row_ids[start],end=valid_row_ids[start+19],method='winnowed_20_frame_windows_span_64'))
    operation=None
    if changes or record['header_reorder']:
        if len(text.splitlines())!=len(rows)+1 or any(len(r)!=len(header) for r in rows):
            flags.append(dict(path=relative,row_start=0,row_end=0,code='MULTILINE_CSV_NO_AUTO_EDIT',detail='Requires manual review',status='UNRESOLVED'))
        else:
            operation=dict(path=relative,header=target_header,rows=[[r[hindex[h]] for h in target_header] for r in rows],
                before_sha256=item['sha256'],row_changes=changes,header_reorder=record['header_reorder'])
    return record,flags,changes,operation,blocks,dict(n=n,mode=mode)

def chunk_worker(args):
    chunk_id,items=args;folder=WORK/'parts';folder.mkdir(exist_ok=True)
    names=['features','flags','changes','operations','blocks'];streams={name:gzip.open(folder/f'{chunk_id:04d}_{name}.jsonl.gz','wt',encoding='utf-8') for name in names}
    for item in items:
        try:
            rec,flags,changes,op,blocks,_=audit_file(item)
            for name,values in [('features',[rec]),('flags',flags),('changes',changes),('operations',[op] if op else []),('blocks',[dict(path=item['path'],**b) for b in blocks])]:
                for value in values:streams[name].write(json.dumps(clean(value),ensure_ascii=False,separators=(',',':'),allow_nan=False)+'\n')
        except Exception as e:
            import traceback
            for stream in streams.values():stream.close()
            raise RuntimeError(item['path']+'\n'+traceback.format_exc()) from e
    for stream in streams.values():stream.close()
    return len(items)

def main():
    config=read(WORK/'config.json');assert config['status']=='SNAPSHOT_COMPLETE'
    if not (WORK/'historical_evidence.json').exists():
        sys.path.insert(0,str(ROOT/'tmp/paper_assessment'))
        import analyze_data as old
        synthetic,captures,evidence=old.origin_evidence()
        write(WORK/'historical_evidence.json',dict(synthetic=sorted(synthetic),captures=sorted(captures),evidence=evidence))
    items=config['files'];chunks=[(i//80,items[i:i+80]) for i in range(0,len(items),80)]
    assert not (WORK/'scan_complete.json').exists()
    done=0
    with ProcessPoolExecutor(max_workers=4,initializer=init,initargs=(config,)) as pool:
        futures=[pool.submit(chunk_worker,c) for c in chunks]
        for future in as_completed(futures):
            done+=future.result()
            if done%800==0 or done==len(items):print(f'Inspected full rows, columns, sequences and bootstrap: {done}/{len(items)} CSV',flush=True)
    output=Path(config['output'])
    counts={}
    for name,target in [('features','file_features_before'),('flags','row_flags_before'),('changes','row_changes'),('operations','operations'),('blocks','sequence_blocks')]:
        count=0
        with gzip.open(output/f'{target}.jsonl.gz','wt',encoding='utf-8') as dst:
            for part in sorted((WORK/'parts').glob(f'*_{name}.jsonl.gz')):
                with gzip.open(part,'rt',encoding='utf-8') as src:
                    for line in src:dst.write(line);count+=1
        counts[target]=count
    assert counts['file_features_before']==len(items)
    write(WORK/'scan_complete.json',dict(status='COMPLETE',counts=counts,versions=dict(python=sys.version,numpy=np.__version__,scipy=__import__('scipy').__version__)))
    print(json.dumps(counts),flush=True)

if __name__=='__main__':main()
