"""Before/after assessment of frame reduction; never changes observations."""
import html,os,sys,collections,json
from reduce import *
os.environ['MPLCONFIGDIR']=str(WORK/'matplotlib_cache')
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def pct(v):return '—' if v is None else f'{100*v:.2f}'
def num(v):return '—' if v is None else f'{v:.2f}'
def count(v):return f'{int(v):,}'.replace(',','.')
def table(headers,rows):return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+html.escape(str(h))+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in r)+'</tr>' for r in rows)+'</tbody></table></div>'

def build():
    cfg=read(CONFIG);out=Path(cfg['output']);stage=Path(cfg['stage']);summary=read(out/'summary_after.json');rows=read(out/'file_metrics_after.json')
    lookup={(r['n_sources'],r['mode'],r['distance_cm']):r for r in summary}
    labels={'AI':'Có AI','NOAI':'Không AI'}
    counts=[[r['n_sources'],labels[r['mode']],r['distance_cm'],count(r['frames_before']),count(r['frames']),r['files_before'],r['files'],r['geometries']] for r in summary]
    metrics_rows=[[r['n_sources'],labels[r['mode']],r['distance_cm'],pct(r['precision']),pct(r['recall_all']),pct(r['recall_nonempty']),pct(r['f1_all']),pct(r['f1_nonempty']),num(r['matched_mae_deg']),pct(r['full_rate'])] for r in summary]
    delta_rows=[[r['n_sources'],labels[r['mode']],r['distance_cm'],*[num(100*r['delta'][m]) if r['delta'][m] is not None else '—' for m in ['precision','recall_all','recall_nonempty','f1_all']],num(r['delta']['matched_mae_deg'])] for r in summary]
    impact={m:max((abs(r['delta'][m]) for r in summary if r['delta'][m] is not None),default=0) for m in METRICS}
    header_only=sum(r['frames']==0 for r in rows)
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.grid':True,'grid.alpha':.18,'axes.spines.top':False,'axes.spines.right':False})
    fig,axes=plt.subplots(1,3,figsize=(13,4.2),layout='constrained')
    for n,ax in enumerate(axes,1):
        for mode,color in [('NOAI','#c46b16'),('AI','#1769a5')]:
            rs=[lookup.get((n,mode,d)) for d in [10,20,30,40]]
            ax.plot([10,20,30,40],[100*r['f1_all'] if r else np.nan for r in rs],'o-',color=color,label=labels[mode])
            ax.plot([10,20,30,40],[100*r['before']['f1_all'] if r else np.nan for r in rs],'--',color=color,alpha=.45)
        ax.set_title(f'{n} nguồn');ax.set_xticks([10,20,30,40]);ax.set_ylim(0,100);ax.set_xlabel('Cự ly (cm)');ax.legend(fontsize=9)
    axes[0].set_ylabel('F1 tính cả khung trống (%)')
    fig.suptitle('Rút gọn khung · Nét liền: sau, nét đứt: trước\nTập hiện có gồm mô phỏng và dữ liệu chưa xác minh',fontsize=12)
    for ext in ['png','svg']:fig.savefig(out/f'f1_before_after.{ext}',dpi=180)
    plt.close(fig)
    coverage=[]
    plans={1:[(a,) for a in range(0,360,30)],2:[(0,45),(0,60),(0,90),(0,180)],3:[(0,120,240),(0,60,180)]}
    by_group=groups([r for r in rows if r['frames']],['n_sources','mode','distance_cm'])
    for key,rr in by_group.items():
        n,mode,d=key;present=set(groups(rr,['geometry']));coverage.append(dict(n_sources=n,mode=mode,distance_cm=d,geometries=len(present),
            planned_found=sum((g,) in present for g in plans[n]),planned_total=len(plans[n])))
    notes=[
        '19 nhóm vượt 40.000 khung được rút về 35.000. Bốn nhóm nhỏ giữ nguyên số khung; nhóm hai nguồn Không AI tại 10 cm vẫn chưa có dữ liệu. Không tạo khung để đạt chỉ tiêu.',
        'Chia hạn mức tỷ lệ theo tổng khung gốc của từng bố trí góc × hồ sơ nguồn × nhóm thu. Mỗi tầng không rỗng giữ ít nhất một khung. Thứ tự file và vị trí đoạn lấy được xác định bằng SHA-256 với seed 20261016, trước khi đánh giá chỉ số.',
        'Giữ các file đầy đủ theo thứ tự đã chọn, sau đó lấy một đoạn liên tiếp trong file cuối nếu cần. Quy tắc không xem góc đo, lỗi, TP/FP, khung trống hay mức lặp khi chọn. Tất cả bố trí góc hiện có được giữ.',
        'Góc, số hướng, góc mục tiêu, cự ly và các cột sai số của từng khung được giữ nguyên. Chỉ đánh lại sample từ 1 cho file bị cắt để tương thích chương trình đọc; JSON ghi checksum và khoảng dòng trong bản gốc để truy ngược.',
        'Các đầu vào mô phỏng AI/Không AI dùng cùng quy tắc xếp file và điểm bắt đầu khi có cùng nguồn chung. Nếu hạn mức khác nhau, các đoạn cùng file có phần đầu trùng nhau; không xem hai tập con là các phép đo phần cứng độc lập.',
        'Chỉ số có thể thay đổi do chọn ít file và khung hơn. Không chạy lại seed để tìm kết quả tốt hơn. Không tái sử dụng khoảng tin cậy hoặc p-value cũ cho tập đã rút gọn; độ bất định cần được ước lượng trên tập mới khi dùng suy luận thống kê.',
        'Tập rút gọn không đáp ứng mặc nhiên quy trình 1.000 khung × ba lần đo mỗi cấu hình. Với hai nguồn AI có 630 bố trí mỗi cự ly, hạn mức 35.000 chỉ cho trung bình khoảng 56 khung/bố trí; cần ghi đúng quy mô này trong bài.',
        'Nguồn gốc dữ liệu được giữ trong JSON bên ngoài CSV. Rút gọn không thay mô phỏng thành kết quả thực nghiệm; các hạn chế về nhiễu, thời lượng thu, phiên bản firmware và đối chứng trong báo cáo trước vẫn còn.',
        'Bản gốc đầy đủ được giữ trong thư mục sao lưu. Thời điểm sửa của file bị cắt là lúc xử lý tập con, không phải thời điểm thu; không sửa dấu thời gian để mô phỏng thời gian đo.'
    ]
    def paper_rows(mode):
        a=[]
        for n in [1,2,3]:
            for d in [10,20,30,40]:
                r=lookup.get((n,mode,d));a.append([n,f'{d/100:.1f}',num(r['matched_mae_deg']) if r else '—',pct(r['precision']) if r else '—',pct(r['recall_all']) if r else '—',pct(r['f1_all']) if r else '—'])
        return a
    paper_headers=['Số nguồn','r (m)','MAE (°)','P (%)','R (%)','F1 (%)']
    body='''<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Dữ liệu sau khi rút gọn khung</title><style>*{box-sizing:border-box}body{margin:0;background:#eef3f7;color:#213448;font:16px system-ui,"Segoe UI",sans-serif}main{max-width:1240px;margin:auto;padding:24px}section,header{padding:25px;background:white;border:1px solid #dce4ec;border-radius:12px;margin-bottom:20px}h1{font-size:29px}h2{font-size:22px}p,li{line-height:1.65;overflow-wrap:anywhere}li{margin-bottom:8px}.scroll{max-width:100%;overflow:auto}table{border-collapse:collapse;width:100%;font-size:14px;font-variant-numeric:tabular-nums}td,th{padding:10px;text-align:right;border-bottom:1px solid #dce4ec;white-space:nowrap}th{background:#e8f0f7}td:first-child,th:first-child{text-align:left}tr:nth-child(even){background:#f7f9fb}a{color:#08649d}img{width:100%;height:auto}.note{padding:15px;background:#fff7e8;border-left:4px solid #c1852a}nav{display:flex;gap:14px;flex-wrap:wrap}nav a{padding:8px;border:1px solid #d6e1eb;border-radius:5px}@media(max-width:700px){main{padding:12px}header,section{padding:17px}h1{font-size:24px}}</style><main>'''
    body+='<header><p>Rút gọn ngày 16/10/2026 · Mỗi số nguồn × chế độ × cự ly</p><h1>'+count(cfg['frames_before'])+' → '+count(cfg['frames_after'])+' khung</h1><p>'+count(cfg['input_files'])+' → '+count(cfg['files_after'])+' CSV đang hoạt động. Giảm '+f"{100*(1-cfg['frames_after']/cfg['frames_before']):.2f}"+'% số khung. Sáu file chỉ có tiêu đề được giữ nguyên.</p><nav><a href="noi_dung_dien_bao_cao.md">Bảng và nhận xét cho bài</a><a href="summary_after.json">Số liệu trước–sau</a><a href="selection_plan.json">Quy tắc và dòng gốc</a><a href="installation.json">Kết quả cập nhật thư mục chính</a></nav></header>'
    body+='<section><h2>Số khung và độ phủ góc</h2>'+table(['Nguồn','Chế độ','cm','Khung trước','Khung sau','CSV trước','CSV sau','Bố trí góc giữ'],counts)+'</section>'
    body+='<section><h2>Chỉ số sau rút gọn</h2><p>P/R/F1 gộp từ số đếm, ghép một–một trong 15°. R toàn khung bao gồm khung trống; R có hướng là chỉ số có điều kiện. MAE chỉ tính cặp TP.</p>'+table(['Nguồn','Chế độ','cm','P (%)','R toàn khung (%)','R có hướng (%)','F1 toàn khung (%)','F1 có hướng (%)','MAE (°)','Đủ nguồn (%)'],metrics_rows)+'</section>'
    body+='<section><h2>Mức thay đổi so với tập đầy đủ</h2><p>Các tỷ lệ dưới đây là chênh lệch theo điểm phần trăm; MAE theo độ. Đây là ảnh hưởng của rút mẫu, không phải thay đổi thuật toán.</p>'+table(['Nguồn','Chế độ','cm','ΔP','ΔR toàn khung','ΔR có hướng','ΔF1 toàn khung','ΔMAE (°)'],delta_rows)+'<img src="f1_before_after.png" alt="F1 trước và sau khi giảm số khung"></section>'
    body+='<section><h2>Bảng 5.2 · Không AI</h2><p class="note">Các bảng mô tả tập hỗn hợp đã rút gọn, cần ghi rõ thành phần nguồn và điều kiện khi đưa vào bài.</p>'+table(paper_headers,paper_rows('NOAI'))+'<h2>Bảng 5.3 · Có AI</h2>'+table(paper_headers,paper_rows('AI'))+'</section>'
    body+='<section><h2>Phương pháp và giới hạn</h2><ul>'+''.join('<li>'+html.escape(t)+'</li>' for t in notes)+'</ul><p>Bản đầy đủ: <a href="'+Path(cfg['backup']).as_uri()+'">Thư mục đối chứng</a>. Phân tích trước rút gọn: <a href="../paper_readiness_20261016/index.html">Đánh giá toàn bộ và độ sẵn sàng của bài</a>.</p></section></main></html>'
    (out/'index.html').write_text(body,encoding='utf-8')
    md=['# Dữ liệu rút gọn và số liệu bổ sung báo cáo','Ngày xử lý: 16/10/2026.',f"Tổng khung: {count(cfg['frames_before'])} → {count(cfg['frames_after'])}. Tổng CSV đang hoạt động: {count(cfg['input_files'])} → {count(cfg['files_after'])}.",*notes]
    for mode,label in [('NOAI','Bảng 5.2 · Không AI'),('AI','Bảng 5.3 · Có AI')]:
        md+=['## '+label,'Bảng mô tả tập hỗn hợp hiện có. R/F1 tính cả khung trống.','| '+' | '.join(paper_headers)+' |','| '+' | '.join(['---']*len(paper_headers))+' |',*['| '+' | '.join(map(str,r))+' |' for r in paper_rows(mode)]]
    md+=['## Tác động của rút gọn','| Nguồn | Chế độ | cm | ΔP (điểm %) | ΔR toàn khung | ΔR có hướng | ΔF1 toàn khung | ΔMAE (°) |','| --- | --- | --- | --- | --- | --- | --- | --- |',*['| '+' | '.join(map(str,r))+' |' for r in delta_rows],
        'Chỉ tính được 23/24 dòng của Bảng 5.2–5.3; thiếu hai nguồn Không AI tại 10 cm. Các bảng nhiễu, thời gian thực thi, điện năng và đối chứng phiên bản firmware vẫn cần bằng chứng theo đánh giá toàn bộ trước đó.']
    (out/'noi_dung_dien_bao_cao.md').write_text('\n\n'.join(md)+'\n',encoding='utf-8')
    write(out/'comparison.json',dict(frames_before=cfg['frames_before'],frames_after=cfg['frames_after'],files_before=cfg['input_files'],files_after=cfg['files_after'],
        group_target=TARGET,groups_reduced=19,groups_kept_small=4,all_geometry_coverage_preserved=True,
        max_absolute_metric_change=impact,header_only_files=header_only,
        old_intervals_or_p_values_not_reused=True,coverage=coverage))
    print(json.dumps(dict(status='REPORT_READY',report=str(out/'index.html'),max_absolute_metric_change=impact),ensure_ascii=True),flush=True)

if __name__=='__main__':build()
