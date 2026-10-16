"""Publication figure pack from the verified, reduced current DOA data."""
import os,sys,json,math,collections,concurrent.futures,hashlib,html,zipfile,shutil
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];WORK=Path(__file__).resolve().parent
OUT=ROOT/'paper/bieu_do_du_lieu_rut_gon_20261016'
OUT.mkdir(parents=True,exist_ok=True);(OUT/'figures').mkdir(exist_ok=True)
os.environ['MPLCONFIGDIR']=str(WORK/'matplotlib_cache')
sys.path[:0]=[str(ROOT/'tmp/data_quality_audit_20261015'),str(ROOT/'tmp/data_quality_deps'),str(ROOT/'tmp/analysis_plot_deps')]
from common import read,write,sha,metrics,COUNT,METRICS,circ
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

REDUCED=Path(read(ROOT/'tmp/frame_reduction_20261016/final_result.json')['report']).parent
MODE_COLOR={'NOAI':'#b75d11','AI':'#1769a5'}
MODE_LABEL={'NOAI':'Không AI','AI':'Có AI'}
DIST_COLOR={10:'#2765a8',20:'#df861c',30:'#168a73',40:'#8755aa'}
DISTANCES=[10,20,30,40]
RECORDS=[];PLOT_DATA={};FILES=[]
FOOTER='Tập CSV hiện có gồm mô phỏng và dữ liệu chưa xác minh; kết quả mô tả tập rút gọn.'

def grouping(rows,keys):
    result=collections.defaultdict(list)
    for r in rows:result[tuple(tuple(sorted(r['truth'])) if k=='geometry' else r[k] for k in keys)].append(r)
    return result

def agg(rows,n):
    c={k:sum(r[k] for r in rows) for k in COUNT}
    return dict(files=sum(r.get('files',1) for r in rows),**c,**metrics(c,n))

def rng_for(key):
    s=int.from_bytes(hashlib.sha256(repr((20261016,key)).encode()).digest()[:8],'little')
    return np.random.default_rng(s)

def fresh_cluster_interval(rows,key,B=2000):
    # Resample complete geometry units; no individual-frame independence assumption.
    units=list(grouping(rows,['geometry']).values());unit='geometry'
    if len(units)==1:units=[[r] for r in rows];unit='CSV fragments within one geometry'
    assert len(units)>1,'Single CSV would require an explicit moving-block procedure'
    a=np.array([[sum(r[c] for r in u) for c in COUNT] for u in units],dtype=float);n=rows[0]['n_sources'];rng=rng_for(key)
    values={m:[] for m in METRICS}
    for begin in range(0,B,100):
        draws=a[rng.integers(0,len(a),size=(min(100,B-begin),len(a)))].sum(axis=1)
        t,ne,tp,fp,err,full,cc=draws.T
        with np.errstate(divide='ignore',invalid='ignore'):
            result=dict(precision=tp/(tp+fp),recall_all=tp/(n*t),recall_nonempty=tp/(n*ne),f1_all=2*tp/(tp+fp+n*t),
                f1_nonempty=2*tp/(tp+fp+n*ne),matched_mae_deg=err/tp,full_rate=full/t,empty_rate=1-ne/t)
        for m,x in result.items():values[m].extend(x[np.isfinite(x)].tolist())
    return dict(unit=unit,clusters=len(units),replicates=B,
        intervals={m:dict(low=float(np.quantile(x,.025)),high=float(np.quantile(x,.975))) if x else None for m,x in values.items()},
        interpretation='Marginal conditional bootstrap intervals on the selected geometry/CSV units; not independent recording-session uncertainty or proof of hardware performance')

def init():
    global FILES
    FILES=read(REDUCED/'file_metrics_after.json')
    paths=sorted(p for n in range(4) for mode in ['AI','NOAI'] for p in (ROOT/'data'/f'{n}source{mode}').rglob('*.csv'))
    expected={r['path']:r for r in FILES};assert len(paths)==len(expected)==4123
    def check(p):
        rel=p.relative_to(ROOT/'data').as_posix();assert sha(p)==expected[rel]['after_sha256']
        return dict(path=rel,sha256=expected[rel]['after_sha256'],bytes=p.stat().st_size,last_write_ns=p.stat().st_mtime_ns)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:manifest=list(pool.map(check,paths))
    assert sha(ROOT/'data/_data_sources.json')==read(REDUCED/'installation.json')['registry_after_sha256']
    write(OUT/'input_manifest.json',dict(files=manifest,registry_sha256=sha(ROOT/'data/_data_sources.json'),paper_sha256=sha(ROOT/'paper/Báo cáo NCKH.pdf'),
        frames=sum(r['frames'] for r in FILES),files_checked=len(FILES),last_write_role='Preservation check only; not an acquisition/origin criterion'))
    usable=[r for r in FILES if r['frames']>0]
    G=grouping(usable,['n_sources','mode','distance_cm'])
    summary=[]
    known={(r['n_sources'],r['mode'],r['distance_cm']):r for r in read(REDUCED/'summary_after.json')}
    for key,rows in sorted(G.items(),key=str):
        n,mode,d=key;r=dict(n_sources=n,mode=mode,distance_cm=d,**agg(rows,n))
        assert all(r[k]==known[key][k] for k in [*COUNT,*METRICS])
        r['bootstrap']=fresh_cluster_interval(rows,key);summary.append(r)
    geometry=[]
    for key,rows in grouping(usable,['n_sources','mode','distance_cm','geometry']).items():
        n,mode,d,g=key;geometry.append(dict(n_sources=n,mode=mode,distance_cm=d,geometry=g,**agg(rows,n)))
    separation=[]
    for n in [2,3]:
        selected=[r for r in geometry if r['n_sources']==n]
        for r in selected:r['separation_deg']=min(circ(a,b) for i,a in enumerate(r['geometry']) for b in r['geometry'][i+1:])
        for key,rows in grouping(selected,['mode','distance_cm','separation_deg']).items():
            mode,d,sep=key;pooled=agg(rows,n)
            separation.append(dict(n_sources=n,mode=mode,distance_cm=d,separation_deg=sep,geometries=len(rows),**pooled,
                geometry_percentiles={m:dict(low=float(np.quantile([r[m] for r in rows if r[m] is not None],.1)),high=float(np.quantile([r[m] for r in rows if r[m] is not None],.9))) if any(r[m] is not None for r in rows) else None for m in METRICS}))
    PLOT_DATA.update(summary=summary,geometry=geometry,separation=separation,
        protocol=dict(tolerance_deg=15,matching='One-to-one max TP then minimum circular error',recall_main='Includes every frame including empty output',
            mae='Only correctly matched TP directions within 15 degrees',reference_activity='All declared reference sources assumed active in every frame; no frame voice-activity ground truth',
            no_smoothing_or_interpolation=True,missing_points='NaN/gaps, never zero-filled',
            percentile_band='P10–P90 across target-angle geometries, not confidence intervals or independently repeated recordings',
            bootstrap='Fresh 2000 geometry-cluster bootstrap draws on reduced data; old full-data CIs not reused'))
    write(OUT/'plot_data.json',PLOT_DATA)
    print(json.dumps(dict(status='INPUTS_VERIFIED',files=len(FILES),frames=sum(r['frames'] for r in FILES),groups=len(summary),geometry_groups=len(geometry)),ensure_ascii=True),flush=True)

def style():
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.titlesize':11,'axes.labelsize':10,'legend.fontsize':9,
        'axes.spines.top':False,'axes.spines.right':False,'axes.grid':True,'grid.alpha':.16,'grid.linewidth':.7,
        'figure.dpi':120,'savefig.dpi':240,'svg.fonttype':'none','axes.unicode_minus':False})

def save(fig,name,title,section,caption,paper_ref=None):
    for ext in ['png','svg']:fig.savefig(OUT/'figures'/f'{name}.{ext}',dpi=240,bbox_inches='tight',facecolor='white')
    plt.close(fig)
    RECORDS.append(dict(id=name,title=title,section=section,paper_ref=paper_ref,caption=caption,png=f'figures/{name}.png',svg=f'figures/{name}.svg'))
    print(json.dumps(dict(figure=name,status='EXPORTED'),ensure_ascii=True),flush=True)

def summarize_lookup():return {(r['n_sources'],r['mode'],r['distance_cm']):r for r in PLOT_DATA['summary']}
def series(rs,metric,scale=100):return np.array([np.nan if r is None or r.get(metric) is None else scale*r[metric] for r in rs])
def distance_axes(ax):ax.set_xticks(DISTANCES);ax.set_xlabel('Cự ly (cm)')

def schematic():
    fig,axes=plt.subplots(1,3,figsize=(12.8,4.7),layout='constrained')
    for ax,angles in zip(axes,[(0,),(0,90),(0,120,240)]):
        for r in [10,20,30,40]:ax.add_patch(plt.Circle((0,0),r,fill=False,color='#c3cdd6',lw=.7,ls='--'))
        a=2.75
        ax.plot([-a,a,a,-a,-a],[-a,-a,a,a,-a],color='#4c5e6b',lw=1)
        ax.scatter([-a,a,a,-a],[-a,-a,a,a],s=20,color='#263c50',zorder=4)
        ax.scatter([0],[0],s=10,color='black',zorder=5)
        for k,angle in enumerate(angles,1):
            rad=np.deg2rad(angle);x,y=20*np.cos(rad),20*np.sin(rad)
            ax.plot([0,x],[0,y],color='#1769a5',lw=1,alpha=.8)
            ax.scatter([x],[y],s=70,color='#168a73',edgecolors='white',zorder=6)
            ax.annotate(f'KEEP {k}\n{angle}°',(x,y),xytext=(5,7),textcoords='offset points',fontsize=9)
        ax.annotate('0°',xy=(44,0),fontsize=9,ha='right',va='bottom');ax.annotate('90°',xy=(0,43),fontsize=9,ha='left')
        ax.axhline(0,color='#9daebb',lw=.7);ax.axvline(0,color='#9daebb',lw=.7)
        ax.set_xlim(-45,45);ax.set_ylim(-45,45);ax.set_aspect('equal');ax.set_xticks([-40,-20,0,20,40]);ax.set_yticks([-40,-20,0,20,40])
        ax.set_xlabel('x (cm)');ax.set_ylabel('y (cm)');ax.set_title(f'{len(angles)} nguồn · ví dụ ở 20 cm')
    fig.suptitle('Hình 5.1 · Sơ đồ minh họa bố trí nguồn theo thiết kế\nCác vòng: 10, 20, 30, 40 cm; mảng vuông cạnh 5,5 cm',fontsize=13)
    save(fig,'H14','Hình 5.1 · Sơ đồ bố trí nguồn','paper','Sơ đồ theo thiết kế, không phải ảnh hoặc hồ sơ xác nhận bố trí đã đo. Minh họa 0° theo +x và 90° theo +y; cần đối chiếu quy ước lắp đặt thực tế. Ba ví dụ cùng cự ly 20 cm.','Hình 5.1')

def single_source():
    lookup={(r['mode'],r['distance_cm'],tuple(r['geometry'])):r for r in PLOT_DATA['geometry'] if r['n_sources']==1}
    x=np.arange(0,360,30);fig,axes=plt.subplots(4,2,figsize=(12.4,12.2),sharex=True,layout='constrained')
    for i,d in enumerate(DISTANCES):
        for j,m in enumerate(['recall_all','matched_mae_deg']):
            ax=axes[i,j]
            for mode in ['NOAI','AI']:
                rs=[lookup.get((mode,d,(int(a),))) for a in x]
                ax.plot(x,series(rs,m,100 if j==0 else 1),'o-',color=MODE_COLOR[mode],lw=1.5,ms=3.5,label=MODE_LABEL[mode])
            ax.set_title(f'{d} cm · '+('Recall toàn khung' if j==0 else 'MAE trên cặp TP'))
            ax.set_ylabel('Recall (%)' if j==0 else 'MAE (°)');ax.set_ylim(0,102 if j==0 else 15)
            ax.set_xticks(np.arange(0,360,60));ax.legend(loc='best')
            if i==3:ax.set_xlabel('Góc mục tiêu (°)')
    fig.suptitle('Hình 5.2 · Một nguồn theo góc phương vị\nTập rút gọn hiện có; Recall tính cả khung trống, MAE chỉ tính TP',fontsize=13)
    save(fig,'H15','Hình 5.2 · MAE và Recall theo góc','paper',FOOTER+' Mỗi điểm gộp số đếm tại đúng góc/cự ly. Chọn 12 góc bước 30° theo kế hoạch; không làm mượt.','Hình 5.2')

def f1_distance():
    lookup=summarize_lookup();fig,axes=plt.subplots(1,3,figsize=(13.2,4.6),layout='constrained')
    for n,ax in enumerate(axes,1):
        for mode in ['NOAI','AI']:
            rs=[lookup.get((n,mode,d)) for d in DISTANCES];color=MODE_COLOR[mode]
            ax.plot(DISTANCES,series(rs,'f1_all'),'o-',color=color,label=MODE_LABEL[mode],lw=1.6,ms=4.5)
            lo=[100*r['bootstrap']['intervals']['f1_all']['low'] if r else np.nan for r in rs]
            hi=[100*r['bootstrap']['intervals']['f1_all']['high'] if r else np.nan for r in rs]
            ax.fill_between(DISTANCES,lo,hi,color=color,alpha=.13)
        ax.set_title(f'{n} nguồn');ax.set_ylim(0,100);distance_axes(ax);ax.legend()
    axes[0].set_ylabel('F1 toàn khung (%)')
    axes[1].text(.03,.04,'Thiếu Không AI tại 10 cm',transform=axes[1].transAxes,color='#80521a',fontsize=9)
    fig.suptitle('Hình 5.3 · F1 theo khoảng cách và số nguồn\nVùng màu: khoảng bootstrap 95% theo cụm góc/CSV, tính lại trên tập rút gọn',fontsize=12.5)
    save(fig,'H16','Hình 5.3 · F1 theo khoảng cách','paper',FOOTER+' CI có điều kiện trên các cụm được giữ, không phải độ biến thiên của các phiên đo phần cứng độc lập. Không nội suy điểm hai nguồn Không AI tại 10 cm.','Hình 5.3')

def distance_metrics():
    lookup=summarize_lookup();fig,axes=plt.subplots(3,4,figsize=(15,9.5),sharex=True,layout='constrained')
    metrics_list=[('precision','Precision (%)'),('recall_all','Recall toàn khung (%)'),('f1_all','F1 toàn khung (%)'),('matched_mae_deg','MAE trên TP (°)')]
    for i,n in enumerate([1,2,3]):
        for j,(m,label) in enumerate(metrics_list):
            ax=axes[i,j]
            for mode in ['NOAI','AI']:
                rs=[lookup.get((n,mode,d)) for d in DISTANCES]
                ax.plot(DISTANCES,series(rs,m,1 if j==3 else 100),'o-',color=MODE_COLOR[mode],lw=1.5,ms=4,label=MODE_LABEL[mode])
            ax.set_title(f'{n} nguồn · '+label);ax.set_ylim(0,15 if j==3 else 100);ax.set_xticks(DISTANCES)
            if j==0:ax.set_ylabel('Tỷ lệ (%)')
            if j==3:ax.set_ylabel('Độ (°)')
            if i==2:ax.set_xlabel('Cự ly (cm)')
            if i==0 and j==0:ax.legend()
    fig.suptitle('Precision, Recall, F1 và MAE theo cự ly\nTập CSV rút gọn hiện có, gồm dữ liệu mô phỏng',fontsize=13)
    save(fig,'S01_chi_so_theo_cu_ly','Bổ sung · Bốn chỉ số theo cự ly','extra',FOOTER+' Hai chế độ có thể khác tập góc và điều kiện nền; đây là mô tả các nhóm hiện có, không phải đối chứng đã kiểm soát hoàn toàn.')

def full_sources():
    lookup=summarize_lookup();fig,axes=plt.subplots(1,2,figsize=(11.8,4.6),layout='constrained')
    for n,ax in zip([2,3],axes):
        upper=0
        for mode in ['NOAI','AI']:
            rs=[lookup.get((n,mode,d)) for d in DISTANCES];ys=series(rs,'full_rate')
            ax.plot(DISTANCES,ys,'o-',color=MODE_COLOR[mode],lw=1.6,label=MODE_LABEL[mode])
            lo=[100*r['bootstrap']['intervals']['full_rate']['low'] if r else np.nan for r in rs]
            hi=[100*r['bootstrap']['intervals']['full_rate']['high'] if r else np.nan for r in rs]
            upper=max(upper,max(v for v in hi if math.isfinite(v)));ax.fill_between(DISTANCES,lo,hi,color=MODE_COLOR[mode],alpha=.12)
            for x,y in zip(DISTANCES,ys):
                if math.isfinite(y):ax.annotate(f'{y:.2f}',(x,y),xytext=(0,7 if mode=='NOAI' else -14),textcoords='offset points',ha='center',fontsize=8,color=MODE_COLOR[mode])
        ax.set_title(f'Ghép đúng đủ {n} nguồn');ax.set_ylabel('Khung đủ nguồn (%)');distance_axes(ax);ax.legend()
        ax.set_ylim(0,100 if n==2 else max(.4,upper*1.25))
    fig.suptitle('Khả năng phát hiện đồng thời\nĐủ nguồn khi TP bằng số nguồn mục tiêu; vùng màu: bootstrap 95% có điều kiện',fontsize=12.5)
    save(fig,'S02_phat_hien_du_nguon','Bổ sung · Phát hiện đúng đủ hai/ba nguồn','extra',FOOTER+' TP=N khác với detected_count=N. Hai ô dùng thang tung khác nhau để đọc được tỷ lệ rất thấp của ba nguồn.')

def separation_plot(n):
    selected=[r for r in PLOT_DATA['separation'] if r['n_sources']==n]
    lookup={(r['mode'],r['distance_cm'],r['separation_deg']):r for r in selected}
    x=np.arange(10,181,10) if n==2 else np.array(sorted({r['separation_deg'] for r in selected}))
    metrics_list=[('precision','Precision (%)'),('recall_all','Recall toàn khung (%)'),('f1_all','F1 toàn khung (%)'),('matched_mae_deg','MAE trên TP (°)')]
    fig,axes=plt.subplots(4,2,figsize=(12.4,12.2),sharex=True,layout='constrained')
    for j,mode in enumerate(['NOAI','AI']):
        for i,(m,label) in enumerate(metrics_list):
            ax=axes[i,j];ax.axvspan(0,40,color='#d8c7b1',alpha=.2)
            for d in DISTANCES:
                rs=[lookup.get((mode,d,int(a))) for a in x]
                if not any(rs):continue
                scale=1 if i==3 else 100
                ax.plot(x,series(rs,m,scale),'o-',color=DIST_COLOR[d],lw=1.3,ms=3.5,label=f'{d} cm')
                lows=[];highs=[]
                for r in rs:
                    b=r['geometry_percentiles'].get(m) if r and r['geometries']>=5 else None
                    lows.append(scale*b['low'] if b else np.nan);highs.append(scale*b['high'] if b else np.nan)
                ax.fill_between(x,lows,highs,color=DIST_COLOR[d],alpha=.07)
            ax.set_ylabel(label);ax.set_ylim(0,15 if i==3 else 100);ax.set_xlim(0,185 if n==2 else 125)
            ax.set_title(MODE_LABEL[mode]+' · '+label);ax.legend(ncol=2,loc='best')
            ax.set_xticks(np.arange(0,181,30) if n==2 else [30,60,90,120])
            if i==3:ax.set_xlabel('Góc tách vòng giữa hai nguồn (°)' if n==2 else 'Góc tách nhỏ nhất trong bộ ba (°)')
    fig.suptitle(f'{n} nguồn · Chỉ số theo độ tách góc\nVùng màu: P10–P90 giữa bố trí góc; vùng xám: độ tách ≤40°',fontsize=13)
    save(fig,f'S0{n+1}_{n}_nguon_theo_goc_tach',f'Bổ sung · {n} nguồn theo độ tách góc','extra',FOOTER+' Đường gộp từ số đếm; vùng P10–P90 là phân tán giữa bố trí góc, không phải CI. Chỉ vẽ vùng khi có ít nhất năm bố trí; không điền các góc tách thiếu dữ liệu.')

def empty_recall():
    lookup=summarize_lookup();fig,axes=plt.subplots(3,2,figsize=(12.2,10),sharex=True,layout='constrained')
    for i,n in enumerate([1,2,3]):
        for mode in ['NOAI','AI']:
            rs=[lookup.get((n,mode,d)) for d in DISTANCES];color=MODE_COLOR[mode]
            axes[i,0].plot(DISTANCES,series(rs,'empty_rate'),'o-',color=color,label=MODE_LABEL[mode])
            axes[i,1].plot(DISTANCES,series(rs,'recall_all'),'o-',color=color,label=MODE_LABEL[mode]+' · mọi khung')
            axes[i,1].plot(DISTANCES,series(rs,'recall_nonempty'),'s--',color=color,label=MODE_LABEL[mode]+' · có hướng')
        for j in [0,1]:
            ax=axes[i,j];ax.set_title(f'{n} nguồn · '+('Khung không có hướng' if j==0 else 'Hai cách tính Recall'))
            ax.set_ylim(0,100);ax.set_ylabel('Tỷ lệ (%)');ax.set_xticks(DISTANCES);ax.legend(fontsize=8.5)
            if i==2:ax.set_xlabel('Cự ly (cm)')
    fig.suptitle('Khung trống và tác động lên Recall\nRecall toàn khung = (1 − tỷ lệ trống) × Recall trên khung có hướng',fontsize=13)
    save(fig,'S05_khung_trong_va_recall','Bổ sung · Khung trống và Recall có điều kiện','extra',FOOTER+' Nét đứt dùng mẫu số chỉ gồm khung có ít nhất một hướng. Đây không phải nhãn tiếng nói/im lặng hoặc chỉ số phân loại KEEP/NOISE.')

def coverage():
    lookup=summarize_lookup();keys=[(n,d) for n in [1,2,3] for d in DISTANCES];x=np.arange(len(keys));width=.34
    fig,axes=plt.subplots(2,1,figsize=(13,7.8),sharex=True,layout='constrained')
    for mode,offset in [('NOAI',-width/2),('AI',width/2)]:
        rs=[lookup.get((n,mode,d)) for n,d in keys]
        frames=[r['frames'] if r else np.nan for r in rs]
        geos=[len({tuple(g['geometry']) for g in PLOT_DATA['geometry'] if (g['n_sources'],g['mode'],g['distance_cm'])==(n,mode,d)}) if r else np.nan for (n,d),r in zip(keys,rs)]
        for ax,values in zip(axes,[frames,geos]):
            bars=ax.bar(x+offset,values,width,color=MODE_COLOR[mode],label=MODE_LABEL[mode])
            for b,v in zip(bars,values):
                if math.isfinite(v):ax.annotate(f'{int(v):,}'.replace(',','.'),(b.get_x()+b.get_width()/2,v),xytext=(0,4),textcoords='offset points',ha='center',fontsize=7.3,rotation=90 if ax==axes[0] else 0)
    axes[0].set_ylabel('Số khung');axes[0].set_ylim(0,43000)
    axes[1].set_ylabel('Số bố trí góc khác nhau');axes[1].set_ylim(0,740)
    axes[1].legend(ncol=2,loc='upper left')
    axes[1].set_xticks(x,[f'{n} nguồn\n{d} cm' for n,d in keys]);axes[0].set_title('Quy mô tập con đang dùng');axes[1].set_title('Độ phủ bố trí góc')
    fig.suptitle('Số khung và độ phủ dữ liệu\nKhông AI hai nguồn tại 10 cm chưa có dữ liệu; các nhóm nhỏ được giữ nguyên',fontsize=13)
    save(fig,'S06_quy_mo_va_do_phu','Bổ sung · Số khung và độ phủ góc','extra','Số đếm của tập đang hoạt động. Không cộng các bản sao lưu hay tập xử lý ngoài nhánh chính. Độ phủ và số khung không chứng minh độc lập giữa các lần thu.')

def gallery():
    missing=[dict(figure='Hình 5.4 (H17)',status='Chưa đủ dữ liệu đúng kịch bản',reason='Cần hai chế độ ở 30 cm với một giọng nói/quạt 90°, hai giọng nói 0°/180° và quạt 90°, một giọng nói/bàn phím 90°, cùng nhật ký nền và hoạt động nguồn. CSV hiện tại không xác nhận được các kịch bản này.'),
        dict(figure='Histogram Hình 3.2 và đồ thị Chương 4',status='Không tái tạo từ CSV hướng hiện tại',reason='Cần các histogram trung gian, lịch sử huấn luyện hoặc vector/điểm dự đoán chuẩn tương ứng. Đây là loại đầu vào khác; các hình đã có trong PDF không được suy ngược thành dữ liệu mới.')]
    write(OUT/'figures.json',dict(figures=RECORDS,unavailable=missing,inputs='input_manifest.json',numerical_values='plot_data.json'))
    intro='Bộ hình dùng 673.000 khung trong 4.123 CSV đang hoạt động. Các biểu đồ mô tả tập hỗn hợp gồm mô phỏng, khung đối chiếu bản ghi thu cũ và nguồn chưa xác minh; chưa xác nhận mọi nhóm có cùng nền âm thanh và phiên bản firmware.'
    body='''<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Biểu đồ cho báo cáo NCKH · tập dữ liệu rút gọn</title><style>*{box-sizing:border-box}body{margin:0;background:#eef3f7;color:#23384a;font:16px system-ui,"Segoe UI",sans-serif}main{max-width:1280px;margin:auto;padding:26px}header,section,article{padding:24px;background:white;border:1px solid #dce5ec;border-radius:12px;margin-bottom:20px}h1{font-size:29px;line-height:1.25}h2{font-size:22px}p,li{line-height:1.65;overflow-wrap:anywhere}nav{display:flex;gap:10px;flex-wrap:wrap}a{color:#075f9e}nav a,.downloads a{display:inline-block;border:1px solid #c9d9e5;border-radius:6px;padding:8px 12px;text-decoration:none}img{display:block;width:100%;height:auto;margin:15px 0}.caption{font-size:14px;color:#506579}.downloads{display:flex;gap:10px;flex-wrap:wrap}select{padding:9px;font:inherit;max-width:100%;border:1px solid #bbcddc;border-radius:6px}.note{background:#fff7e8;padding:14px;border-left:4px solid #bd8b38}article[hidden]{display:none}table{border-collapse:collapse;width:100%;font-size:14px}th,td{padding:12px;border-bottom:1px solid #dce5ec;text-align:left;vertical-align:top}.scroll{overflow:auto}code{overflow-wrap:anywhere}@media(max-width:700px){main{padding:12px}header,section,article{padding:17px}h1{font-size:24px}h2{font-size:20px}}</style><main>'''
    body+='<header><p>Ngày xuất hình: 16/10/2026 · Dữ liệu sau rút gọn</p><h1>Các biểu đồ để bổ sung báo cáo NCKH</h1><p>'+intro+'</p><nav><a href="bieu_do_nckh.zip">Tải toàn bộ PNG và SVG</a><a href="chu_thich_chen_bao_cao.md">Chú thích để chèn vào bài</a><a href="plot_data.json">Số liệu trên biểu đồ</a><a href="../../data/_reports/frame_reduction_20261016_214709_265890/index.html">Báo cáo rút gọn</a></nav></header>'
    body+='<section><label>Hiển thị: <select id="filter"><option value="all">Tất cả 9 hình</option><option value="paper">Hình 5.1–5.3 trong bài</option><option value="extra">Biểu đồ phân tích bổ sung</option></select></label><p class="caption">Màu cam: Không AI; xanh lam: Có AI. Với biểu đồ tách góc, màu phân biệt cự ly theo chú giải. R/F1 chính tính cả khung trống; MAE chỉ tính TP trong 15°.</p></section>'
    captions=['# Chú thích hình cho báo cáo NCKH','Dữ liệu đang dùng: 673.000 khung, 4.123 CSV. '+intro,
        'Mỗi hình có PNG 240 dpi và SVG. SVG giữ chữ dạng văn bản; cần phông hỗ trợ tiếng Việt khi chỉnh trong phần mềm đồ họa. Không thay nội dung dữ liệu để tạo hình.']
    for r in RECORDS:
        body+='<article data-section="'+r['section']+'" id="'+r['id']+'"><h2>'+html.escape(r['title'])+'</h2><a href="'+r['png']+'" target="_blank" title="Mở ảnh đầy đủ"><img src="'+r['png']+'" alt="'+html.escape(r['title'])+'"></a><p class="caption">'+html.escape(r['caption'])+'</p><div class="downloads"><a href="'+r['png']+'" download>Tải PNG</a><a href="'+r['svg']+'" download>Tải SVG</a></div></article>'
        captions+=['## '+r['title'],r['caption'],f"Ảnh: {r['png']}. Bản vector: {r['svg']}."]
    body+='<section><h2>Phần chưa có dữ liệu phù hợp để vẽ</h2>'
    for r in missing:body+='<h3>'+html.escape(r['figure'])+'</h3><p class="note">'+html.escape(r['status']+'. '+r['reason'])+'</p>';captions+=['## '+r['figure'],r['status']+'. '+r['reason']]
    body+='<p>Đã tính lại khoảng bootstrap trên chính tập rút gọn. Đây là khoảng 95% riêng lẻ có điều kiện theo cụm, không phải xác nhận độ tin cậy của các phép đo độc lập hoặc khoảng đồng thời cho mọi biểu đồ. Không dùng các hình để khẳng định hiệu quả trên nền nhiễu chưa được xác nhận.</p></section>'
    body+='''<script>document.getElementById('filter').addEventListener('change',e=>{for(const a of document.querySelectorAll('article'))a.hidden=e.target.value!=='all'&&a.dataset.section!==e.target.value;});</script></main></html>'''
    (OUT/'index.html').write_text(body,encoding='utf-8');(OUT/'chu_thich_chen_bao_cao.md').write_text('\n\n'.join(captions)+'\n',encoding='utf-8')
    write(WORK/'config.json',dict(root=str(ROOT),output=str(OUT),figures=len(RECORDS),status='FIGURES_EXPORTED'))

def main():
    init();style();schematic();single_source();f1_distance();distance_metrics();full_sources();separation_plot(2);separation_plot(3);empty_recall();coverage();gallery()
    print(json.dumps(dict(status='GALLERY_WRITTEN',output=str(OUT),figures=len(RECORDS)),ensure_ascii=True),flush=True)

if __name__=='__main__':main()
