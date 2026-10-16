"""Publish a read-only research-data assessment and candidate paper content."""
import sys, json, html, math, collections, shutil, os
from pathlib import Path
from review import ROOT,WORK,OUT,PREVIOUS,LABELS,PLAN_GEOMETRIES,read,write,sha,np
os.environ['MPLCONFIGDIR']=str(WORK/'matplotlib_cache')
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

def number(v,digits=2):return '—' if v is None else f'{v:.{digits}f}'
def percent(v):return number(None if v is None else v*100)
def integer(v):return f'{int(v):,}'.replace(',','.')
def table(headers,rows):
    return '<div class="scroll"><table><thead><tr>'+''.join('<th>'+html.escape(str(h))+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in r)+'</tr>' for r in rows)+'</tbody></table></div>'
def mdtable(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |',*['| '+' | '.join(str(v).replace('|','/') for v in r)+' |' for r in rows]])

READINESS=[
    ['Bảng 5.1','Đã có nội dung thiết kế; cần bổ sung bảng độ phủ thực tế','Có 123/144 điều kiện góc–cự ly–chế độ trong kế hoạch có số liệu; có số liệu không đồng nghĩa đã đo đúng quy trình.'],
    ['Bảng 5.2','Tính được 11/12 dòng','Thiếu 2 nguồn Không AI tại 10 cm. Số liệu gộp hiện tại chưa được xác nhận cùng nền yên tĩnh và cùng tập góc.'],
    ['Bảng 5.3','Tính được 12/12 dòng','2 nguồn Có AI tại 40 cm chỉ có 7 CSV, 2.100 khung, một cặp (120°,240°); không có cặp góc chung với Không AI tại 40 cm.'],
    ['Hình 5.1','CSV không cung cấp ảnh bố trí thực nghiệm','Có thể vẽ sơ đồ từ góc/cự ly; sơ đồ cần ghi rõ đây là bố trí thiết kế hoặc có nhật ký xác nhận.'],
    ['Hình 5.2','Vẽ được cho 1 nguồn tại cả 4 cự ly','Đã xuất hình theo 12 góc 0°,30°,…,330°. Hình mô tả dữ liệu hỗn hợp hiện có, cần ghi rõ nguồn/điều kiện.'],
    ['Hình 5.3','Vẽ được 23/24 điểm F1','Để trống điểm 2 nguồn Không AI tại 10 cm; số liệu hai chế độ chưa đồng nhất bố trí ở mọi nhóm.'],
    ['Bảng 5.4 và Hình 5.4','Chưa đủ căn cứ điền đối chứng đúng 4 kịch bản nhiễu','Thiếu nhật ký xác nhận loại âm, nguồn quạt/bàn phím tại 90°, hoạt động từng nguồn và cùng cấu hình ở 30 cm.'],
    ['Bảng 5.5','Chưa điền được','Hai nhánh 0sourceAI và 0sourceNOAI chưa có CSV; cần đo chỉ quạt và chỉ bàn phím.'],
    ['Bảng 5.6','Bài đã có số, chưa xác minh được cặp bản dựng','Chỉ tìm thấy một cặp build log/map hiện có. Nó cho Flash 90,46 KiB và SRAM 48,99 KiB, khác các giá trị đã ghi trong bài; chưa xác định được phiên bản/cấu hình để thay số.'],
    ['Bảng 5.7','Chưa điền được từ CSV hướng','Thiếu log thời gian xử lý từng khung, số khối DMA bỏ lỡ và sự kiện bật/tắt nguồn.'],
    ['Bảng 5.8','Chưa điền đủ được','Thiếu chuỗi điện áp/dòng hoặc phép đo trung bình gắn với từng chế độ. Giá trị 355 mW trong bài chưa xác định được dòng chế độ tương ứng.']
]

EARLIER_CHAPTERS=[
    ['Bảng 1.1, Bảng 2.1–2.6, Bảng 3.1','Đã có thông tin lý thuyết/thiết kế; CSV hướng không bổ sung được bằng chứng phần cứng','Đối chiếu tài liệu, hình học microphone, bộ đệm và phiên bản mã. Không suy ra thông số thiết kế chỉ từ phân phối góc.'],
    ['Bảng 3.2 và Hình 3.2','Không dựng lại được đầy đủ histogram từ CSV hướng','CSV lưu hướng cuối và góc mục tiêu; không chứa 360 ô của radar_histogram, accum_hist và smoothed_hist hoặc mã khung tương ứng. Giữ bản chụp DSP gốc làm căn cứ.'],
    ['Bảng 4.1–4.2','Mô tả nhãn và định dạng huấn luyện, không phải định dạng data hiện tại','CSV trong data dùng bản tin DOA, không có sound_type, label, bin_count hay 16 band. Không trộn hai loại bản ghi.'],
    ['Bảng 4.3–4.6 và Hình 4.2','Bài đã có số; không cập nhật từ CSV hướng trong data','Cần dữ liệu đặc trưng ở thư mục AI, phép chia train/validation/test và lịch sử huấn luyện tương ứng; không dùng Precision định hướng thay accuracy hay F1 phân loại KEEP/NOISE.'],
    ['Bảng 4.7','Không suy ra trọng số mạng từ CSV hướng','Xác minh bằng mô hình/scaler/header C đúng phiên bản.'],
    ['Bảng 4.8','Có điểm cần cập nhật theo phiên bản firmware được chọn','Bài mô tả cửa sổ 10 và giới hạn thiếu đặc trưng 8, mã hiện có đặt 5 và 4. Không kết luận dữ liệu đã được thu bằng một cấu hình cụ thể chỉ từ nhãn AI trong tên thư mục.'],
    ['Hình 4.3 và đánh giá phân loại tại Mục 4.8','CSV hướng không đủ để chứng minh tương đương Python–STM32 hoặc phân loại từng lớp','Cần vector chuẩn, điểm dự đoán hai môi trường, nhãn loại âm và ma trận nhầm lẫn.']
]

def figures(d):
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'axes.grid':True,'grid.alpha':.18,'figure.dpi':140})
    figdir=OUT/'figures';figdir.mkdir(exist_ok=True)
    colors={'NOAI':'#c46b16','AI':'#1769a5'};labels={'NOAI':'Không AI','AI':'Có AI'}
    lookup={(g['n_sources'],g['mode'],g['distance_cm'],tuple(g['geometry'])):g for g in d['geometries']}
    x=np.arange(0,360,30)
    fig,axes=plt.subplots(4,2,figsize=(11.8,12.4),sharex=True,layout='constrained')
    for i,dist in enumerate((10,20,30,40)):
        for j,metric in enumerate(['recall_all','matched_mae_deg']):
            ax=axes[i,j]
            for mode in ['NOAI','AI']:
                values=[lookup.get((1,mode,dist,(int(a),)),{}).get(metric) for a in x]
                values=np.array([np.nan if v is None else v*(100 if j==0 else 1) for v in values])
                ax.plot(x,values,'o-',lw=1.4,ms=3.4,color=colors[mode],label=labels[mode])
            ax.set_title(f'{dist} cm · '+('Recall tính cả khung trống' if j==0 else 'MAE trên cặp TP'))
            ax.set_ylabel('Recall (%)' if j==0 else 'MAE (°)')
            if j==0:ax.set_ylim(0,103)
            ax.set_xticks(np.arange(0,360,60));ax.legend(loc='best',fontsize=9)
            if i==3:ax.set_xlabel('Góc mục tiêu (°)')
    fig.suptitle('Hình 5.2 đề xuất · Một nguồn theo góc và cự ly\nToàn bộ CSV đang hoạt động, gồm dữ liệu mô phỏng và chưa xác minh',fontsize=13)
    for ext in ['png','svg']:fig.savefig(figdir/f'hinh_5_2_mot_nguon.{ext}',dpi=180)
    plt.close(fig)
    lookup={(r['n_sources'],r['mode'],r['distance_cm']):r for r in d['summaries']}
    x=np.array([10,20,30,40])
    fig,axes=plt.subplots(1,3,figsize=(13,4.5),layout='constrained')
    for n,ax in enumerate(axes,1):
        for mode in ['NOAI','AI']:
            rs=[lookup[n,mode,int(v)] for v in x]
            y=[100*r['f1_all'] if r['f1_all'] is not None else np.nan for r in rs]
            ax.plot(x,y,'o-',color=colors[mode],label=labels[mode],lw=1.6,ms=5)
            lo=[];hi=[]
            for r in rs:
                ci=r.get('bootstrap_ci',{}).get('intervals',{}).get('f1_all')
                lo.append(ci['low']*100 if ci else np.nan);hi.append(ci['high']*100 if ci else np.nan)
            ax.fill_between(x,lo,hi,color=colors[mode],alpha=.12)
        ax.set_title(f'{n} nguồn');ax.set_xlabel('Cự ly (cm)');ax.set_xticks(x);ax.set_ylim(0,100);ax.legend(fontsize=9)
    axes[0].set_ylabel('F1 tính cả khung trống (%)')
    axes[1].annotate('Chưa có Không AI tại 10 cm',xy=(.04,.05),xycoords='axes fraction',fontsize=8.5,color='#80521a')
    fig.suptitle('Hình 5.3 đề xuất · F1 theo cự ly\nDữ liệu hỗn hợp hiện có; vùng màu: CI 95% có điều kiện theo cụm góc/CSV',fontsize=12)
    for ext in ['png','svg']:fig.savefig(figdir/f'hinh_5_3_f1_khoang_cach.{ext}',dpi=180)
    plt.close(fig)
    fig,axes=plt.subplots(1,2,figsize=(11.8,4.2),layout='constrained')
    for mode in ['NOAI','AI']:
        rs=[lookup[3,mode,int(v)] for v in x]
        for ax,metric in zip(axes,['recall_all','full_rate']):ax.plot(x,[100*r[metric] for r in rs],'o-',color=colors[mode],label=labels[mode])
    for ax,title in zip(axes,['Recall theo từng nguồn','Khung ghép đúng đủ cả 3 nguồn']):
        ax.set_title(title);ax.set_xlabel('Cự ly (cm)');ax.set_ylabel('Tỷ lệ (%)');ax.set_xticks(x);ax.legend()
    axes[0].set_ylim(0,40);axes[1].set_ylim(0,.4)
    fig.suptitle('Ba nguồn · Recall theo nguồn khác tỷ lệ phát hiện đồng thời\nMô tả toàn bộ CSV hiện có, gồm mô phỏng',fontsize=12)
    for ext in ['png','svg']:fig.savefig(figdir/f'ba_nguon_phat_hien_dong_thoi.{ext}',dpi=180)
    plt.close(fig)

def build():
    d=read(OUT/'assessment.json');figures(d)
    S=d['summaries'];lookup={(r['n_sources'],r['mode'],r['distance_cm']):r for r in S}
    headers=['Nguồn','Cự ly (m)','MAE (°)','P (%)','R (%)','F1 (%)','CSV','Khung','Bố trí góc']
    def summary_rows(mode):return [[r['n_sources'],number(r['distance_cm']/100,1),number(r['matched_mae_deg']),percent(r['precision']),percent(r['recall_all']),percent(r['f1_all']),integer(r['files']),integer(r['frames']),integer(r['geometries'])] for r in S if r['mode']==mode]
    definition=('P, R và F1 được gộp từ tổng TP, FP, FN; ghép một–một với dung sai 15°. R và F1 chính tính cả khung trống. '
        'MAE chỉ tính trên các cặp TP trong dung sai. Giả định các nguồn tham chiếu được khai báo đều hoạt động ở mọi khung; CSV không có nhãn hoạt động thực tế. '
        'Ký hiệu — là chưa có dữ liệu/không xác định, không phải 0.')
    opening=('Tính được số liệu mô tả cho 23/24 dòng của Bảng 5.2–5.3: Không AI 11/12 dòng, Có AI 12/12 dòng. '
        'Có thể dựng Hình 5.2 và Hình 5.3 với phần thiếu được ghi rõ. Chưa đủ căn cứ coi toàn bộ các số này là kết quả đo phần cứng trong đúng điều kiện thực nghiệm của bài.')
    provenance=('Đã đối chiếu SHA-256 của toàn bộ 13.782 CSV, tổng 16.216.648 dòng, và hồ sơ nguồn với lần kiểm định 15/10/2026: '
        'không có file mới, bị xóa hay thay nội dung. Tái sử dụng kiểm định trên đúng nội dung đã xác minh, rồi tính lại các tổng TP/FP/FN và độ phủ cho lần đánh giá này. '
        'Không sửa CSV, nhãn nguồn, dấu thời gian hoặc PDF. Chỉ cộng các nhánh 0–3sourceAI/NOAI đang hoạt động; bản lưu, báo cáo, tập con và bản xử lý ngoài các nhánh này không được cộng thêm như mẫu độc lập.')
    source_rows=[[r['label'],integer(r['files']),integer(r['rows'])] for r in d['source_counts']]
    findings=[
        'Nguồn dữ liệu: 13.191 CSV có bằng chứng mô phỏng, 149 CSV khớp bản ghi thu cũ và 442 CSV chưa xác minh. Khớp hồ sơ thu không phải xác nhận độc lập việc thu trên phần cứng. Riêng ba nguồn chưa có file được phân loại khớp hồ sơ thu cũ.',
        'Khoảng cách: một nguồn suy giảm rõ ở 40 cm; hai nguồn Có AI tại 10–30 cm có Recall toàn khung 55,53% → 52,15% → 48,92% và MAE 5,19° → 7,25° → 9,27°. Điểm 40 cm dùng tập góc khác nên không nối xu hướng như cùng một thiết kế đối chứng.',
        'Ba nguồn: Recall toàn khung Có AI chỉ 22,22–28,53%; Không AI 24,85–31,30%. Tỷ lệ khung ghép đúng đủ ba nguồn khoảng 0,032–0,263% với AI và 0,036–0,333% không AI. MAE khoảng 5,88–6,80° chỉ mô tả các nguồn đã ghép đúng, không thể đại diện cho khả năng nhận đủ ba nguồn.',
        'Tác động AI: trong nhóm mô phỏng N2 dùng chung đầu vào, so sánh trọng số đều theo bố trí góc cho thấy Precision tăng khoảng 5,26 điểm % ở một nguồn 40 cm và 2,85–4,52 điểm % ở ba nguồn. Recall toàn khung giảm khoảng 3,26 điểm % và 2,29–2,59 điểm % tương ứng. F1 toàn khung tăng ở một nguồn 40 cm nhưng giảm ở ba nguồn; MAE ba nguồn không giảm nhất quán. Đây là kết quả theo giả định mô phỏng, không phải mức cải thiện đã đo lại bằng mạch.',
        'So sánh hai nguồn còn thiếu đối chứng: tại 10 cm không có Không AI; tại 40 cm hai chế độ không có cặp góc chung. Tại 20 cm chỉ chung 7 bố trí, tại 30 cm chỉ chung 2 bố trí; AI thuộc bộ mô phỏng trong khi Không AI chưa xác minh nguồn thu.',
        'Trọng số: một CSV một nguồn Có AI tại 40 cm có 26.248 khung, lớn hơn nhiều file khác. Báo cáo kèm trung bình đều theo file và theo bố trí góc để thấy mức nhạy do cơ cấu mẫu; không thay thế phép gộp TP/FP/FN bằng trung bình phần trăm mà không ghi rõ.',
        'Lịch sử chọn mẫu: hồ sơ cũ xác nhận từng loại 40 file theo ngưỡng chỉ số dưới 55%. Kết quả trên tập còn lại có nguy cơ thiên lệch lựa chọn; không dùng mức tăng sau khi loại file làm bằng chứng thuật toán tốt hơn.'
    ]
    gaps=[
        'Một nguồn: đủ 12 góc bước 30° ở cả hai chế độ và bốn cự ly trên tập đang hoạt động, nhưng nguồn gốc và điều kiện nền không đồng nhất.',
        'Hai nguồn: cấu hình (0°,45°) chưa có ở cả hai chế độ tại mọi cự ly; nhiều cặp góc khác trong kế hoạch cũng còn thiếu. Các góc (120°,240°) của nhóm AI 40 cm không thay thế bốn cặp dự kiến trong Bảng 5.1.',
        'Ba nguồn: cả hai bộ ba góc dự kiến đều có dữ liệu ở bốn cự ly, song bộ mô phỏng chủ yếu có 300 khung/CSV. Không thể coi ba file 300 khung là ba lần đo 1.000 khung như quy trình đã ghi.',
        'Đã có số liệu ở 123/144 điều kiện góc–cự ly–chế độ dự kiến. Con số này đo độ phủ dữ liệu, không chứng minh đã hoàn thành quy trình thực nghiệm hoặc độc lập giữa các lần thu.'
    ]
    quality=('Còn 8.604 khung có hướng trùng trong cùng khung, 122 chuỗi khung trống dài và 6 file chỉ có tiêu đề; tổng 14.188 dòng nằm trong các cờ nghi vấn. '
        'Các dòng được giữ nguyên. Góc giống nhau giữa các khung có thể do nguồn đứng yên, lượng tử hóa hoặc làm trơn, không tự chứng minh lỗi. '
        'Không đặt một tỷ lệ lặp mục tiêu để sửa số đo. Độ dài chuỗi lặp và tự tương quan cần được đọc cùng nhau; không xem mọi khung là phép thử độc lập. '
        'Các kiểm định phân phối, vòng tròn, chuỗi và bootstrap của lần kiểm định trước vẫn áp dụng vì nội dung giữ nguyên. P-value không được dùng để xác nhận dữ liệu là đo thật.')
    timing=('Đã ghi nhận thời điểm sửa trên ổ đĩa của mọi CSV như thông tin phụ, không dùng để phân loại nguồn dữ liệu hay loại mẫu. '
        'Không CSV nào có thời gian từng khung trong tiêu đề hiện tại. Thời điểm lưu có thể phản ánh sao chép/chỉnh định dạng, chưa đủ để suy ra thời gian thu hoặc nhịp khung thực tế. '
        'Chưa xác minh được thời lượng thu cho toàn bộ tập. Ví dụ 2.000 khung/90 giây chỉ tương đương giả định 22,22 khung/giây, không phải thời lượng đã được xác nhận cho những file này. '
        'Lần thu tiếp theo cần JSON gắn với checksum CSV, ghi thời điểm bắt đầu/kết thúc, lưu xong, số khung và mã khung mạch nếu có.')
    edits=[
        'Mục 5.1: bổ sung bảng số CSV, số khung, bố trí góc, nguồn gốc dữ liệu và cự ly thực có. Tách rõ kết quả mô phỏng có hồ sơ, khớp bản ghi thu cũ và chưa xác minh; có thể giữ bảng gộp hiện trạng như phân tích bổ sung có ghi rõ thành phần.',
        'Mục 5.1.2: ghi đúng số khung đã dùng, mức lặp và thiếu nhật ký phiên thu. Không giữ nguyên tuyên bố mọi trường hợp đã đo 1.000 khung × ít nhất ba lần nếu dữ liệu không đáp ứng.',
        'Bảng 5.2–5.3: ghi R/F1 tính cả khung trống theo quy tắc hiện tại của bài. Nếu muốn thêm R/F1 bỏ khung trống, dùng cột hoặc bảng phụ riêng. Ghi rõ nền âm thanh chưa xác minh ở nhóm nào và không gán bộ N2 mô phỏng là nền yên tĩnh.',
        'Mục 5.2.3: bổ sung tỷ lệ ghép đúng đủ số nguồn, đặc biệt với ba nguồn. Phân tích suy giảm theo độ tách góc trong cùng nguồn gốc/điều kiện, tránh trộn khác cự ly và khác bộ dữ liệu thành một quan hệ nhân quả.',
        'Mục 5.3: mô tả AI là bộ chọn hướng theo loại âm; mô phỏng N2 hiện có dùng đầu vào chung, không thay thế phép đo quạt/bàn phím cố định 90° tại 30 cm. Người dùng xác nhận mục tiêu là giọng nói; câu trong bài ghi cả âm nhạc thuộc KEEP cần đối chiếu lại nhãn huấn luyện.',
        'Mục 5.4: xác minh cặp build log/map tương ứng hai chế độ, phiên bản firmware và cấu hình. Bài mô tả lịch sử AI 10 và bước khung 256 mẫu, trong khi mã hiện tại đặt AI_WINDOW_SIZE=5, thu đủ 512 mẫu rồi đặt lại chỉ số về 0 và không thấy thao tác giữ nửa khung trong hàm thu; cần xác nhận đúng phiên bản trước khi dùng ngân sách 16 ms cho mã hiện tại.',
        'Mục 5.5–5.6: để trống các ô điện năng, độ trễ, DMA và nhiễu chưa có phép đo tương ứng. Kết luận hiện có chỉ hỗ trợ mô tả đánh đổi Precision–Recall dưới điều kiện/giả định được nêu, chưa chứng minh AI cải thiện toàn diện hoặc nhận đồng thời ba nguồn ổn định.'
    ]
    copytext=[
        'Dữ liệu được đánh giá bằng ghép một–một giữa hướng dự đoán và hướng tham chiếu, sử dụng sai số góc vòng với dung sai 15°. Precision, Recall và F1 được tổng hợp từ số đếm TP, FP và FN. Recall và F1 chính bao gồm mọi khung, kể cả khung không có hướng. MAE chỉ tính trên các cặp TP; do đó MAE được diễn giải cùng Recall và tỷ lệ khung phát hiện đúng đủ số nguồn.',
        'Tập dữ liệu hiện trạng gồm 13.782 CSV với 16.216.648 dòng; có 6 file chỉ chứa tiêu đề nên không góp khung đánh giá. Đối chiếu hồ sơ nguồn xác định 13.191 file mô phỏng có tài liệu, 149 file khớp bản ghi thu lịch sử và 442 file chưa xác minh. Các thống kê gộp mô tả tập dữ liệu hiện có; chúng không được dùng thay cho toàn bộ kết quả đo phần cứng ở nền yên tĩnh hoặc các kịch bản nhiễu chưa được xác nhận.',
        'Trong nhóm mô phỏng có chung đầu vào, bộ lọc AI làm tăng Precision nhưng đồng thời loại bỏ một phần hướng phù hợp mục tiêu, dẫn tới giảm Recall tính trên mọi khung. Với ba nguồn, tỷ lệ phát hiện đúng đủ ba nguồn còn thấp dù MAE trên các cặp TP ở mức vài độ. Vì vậy, chưa thể kết luận MAE thấp phản ánh khả năng định hướng đầy đủ hoặc AI cải thiện đồng thời mọi chỉ số.'
    ]
    aux_headers=['Nguồn','Chế độ','cm','P (%)','R toàn khung (%)','R có hướng (%)','F1 toàn khung (%)','F1 có hướng (%)','Trống (%)','Đủ nguồn (%)']
    aux_rows=[[r['n_sources'],r['mode'],r['distance_cm'],*[percent(r[k]) for k in ['precision','recall_all','recall_nonempty','f1_all','f1_nonempty','empty_rate','full_rate']]] for r in S]
    common_headers=['Nguồn','cm','Bố trí góc chung','CSV AI / Không AI','ΔP (điểm %)','ΔR (điểm %)','ΔF1 (điểm %)','ΔMAE (°)']
    common_rows=[]
    for r in d['matched_geometry_comparisons']:
        a,b=r['AI']['geometry_equal_means'],r['NOAI']['geometry_equal_means']
        delta=lambda k,scale: number((a[k]-b[k])*scale) if a[k] is not None and b[k] is not None else '—'
        common_rows.append([r['n_sources'],r['distance_cm'],r['common_geometries'],f"{r['AI']['pooled']['files']} / {r['NOAI']['pooled']['files']}",*[delta(k,100) for k in ['precision','recall_all','f1_all']],delta('matched_mae_deg',1)])
    comparison_note='Chênh lệch AI − Không AI, tính trung bình đều theo bố trí góc chung. Đây là phân tích độ nhạy thành phần mẫu; cùng góc chưa đủ bảo đảm cùng điều kiện thu. Không dùng bảng này như ước lượng tác động nhân quả trên phần cứng.'
    main_table_note='Bảng số dưới đây sử dụng toàn bộ dữ liệu đang hoạt động ở mỗi nhóm, gồm mô phỏng. Có thể dùng trong mục mô tả tập dữ liệu hỗn hợp; chưa chép thẳng vào bảng kết quả thực nghiệm nền yên tĩnh nếu chưa điều chỉnh mô tả và đối chiếu nguồn.'
    planned_missing=[r for r in d['planned_coverage'] if not r['numeric_available']]
    missing_rows=[[r['n_sources'],r['mode'],r['distance_cm'],'; '.join(map(str,r['geometry']))] for r in planned_missing]
    repeat_rows=[[r['n_sources'],r['mode'],r['distance_cm'],LABELS.get(r['origin'],r['origin']),integer(r['files']),percent(r['unchanged_fraction']),percent(r['per_file_unchanged_fraction']['median']),r['longest_nonempty_constant_run'],r['longest_empty_run']] for r in d['repeat_diagnostics']]
    repeat_headers=['Nguồn','Chế độ','cm','Nguồn gốc','CSV','Cặp góc giữ nguyên (%)','Trung vị file (%)','Chuỗi góc dài nhất','Chuỗi trống dài nhất']
    weight_rows=[[r['n_sources'],r['mode'],r['distance_cm'],percent(r['f1_all']),percent(r.get('file_equal_means',{}).get('f1_all')),percent(r.get('geometry_equal_means',{}).get('f1_all'))] for r in S]
    sections=[('Kết quả có thể điền',opening),('Kiểm tra hiện trạng',provenance)]
    md=['# Đánh giá dữ liệu và nội dung có thể bổ sung vào báo cáo NCKH','Ngày đối chiếu: 16/10/2026, múi giờ Asia/Bangkok.',*[f'## {h}\n\n{t}' for h,t in sections],mdtable(['Nguồn gốc','CSV','Dòng'],source_rows),
        '## Đối chiếu từng bảng và hình Chương 5',mdtable(['Vị trí trong bài','Mức độ sẵn sàng','Căn cứ và giới hạn'],READINESS),
        '## Các bảng và hình ở Chương 1–4',mdtable(['Vị trí trong bài','Khả năng bổ sung từ data','Căn cứ cần có'],EARLIER_CHAPTERS),
        '## Quy tắc tính',definition,'## Bảng 5.2 – số liệu mô tả Không AI',main_table_note,mdtable(headers,summary_rows('NOAI')),
        '## Bảng 5.3 – số liệu mô tả Có AI',main_table_note,mdtable(headers,summary_rows('AI')),
        '## Nhận xét từ dữ liệu',*['- '+p for p in findings],
        '## Recall, F1 và khung trống',mdtable(aux_headers,aux_rows),
        '## Đối chiếu trên bố trí góc chung',comparison_note,mdtable(common_headers,common_rows),
        '## Độ phủ thiết kế và số khung',*['- '+p for p in gaps],mdtable(['Nguồn','Chế độ','cm','Góc còn thiếu'],missing_rows),
        '## Độ nhạy với trọng số tổng hợp',mdtable(['Nguồn','Chế độ','cm','F1 gộp (%)','F1 đều file (%)','F1 đều góc (%)'],weight_rows),
        '## Chất lượng, lặp và thời gian lưu',quality,timing,
        'Tỷ lệ góc giữ nguyên dưới đây chỉ xét các cặp hướng ở hai khung kề nhau đều có hướng; ghép theo độ dịch vòng nhỏ nhất. Không xác nhận danh tính nguồn, không nối qua khung trống.',
        mdtable(repeat_headers,repeat_rows),
        '## Nội dung cần sửa trong bài',*['- '+p for p in edits],
        '## Đoạn văn có thể sử dụng sau khi ghi rõ nguồn và điều kiện',*copytext,
        '## Hình đã xuất','![Hình 5.2](figures/hinh_5_2_mot_nguon.png)','![Hình 5.3](figures/hinh_5_3_f1_khoang_cach.png)','![Ba nguồn](figures/ba_nguon_phat_hien_dong_thoi.png)',
        '## Tái kiểm tra và dữ liệu đối chứng','inventory.json lưu SHA-256 của mọi đầu vào và thông tin thời điểm sửa chỉ để đối chiếu. assessment.json chứa số đếm, kết quả và độ phủ. Kiểm định thống kê chi tiết được tham chiếu tới báo cáo kiểm định ngày 15/10/2026 vì toàn bộ nội dung CSV và hồ sơ nguồn vẫn khớp.',
        'Bài được đối chiếu: paper/Báo cáo NCKH.pdf, SHA-256 '+d['paper_sha256']+'.',
        'Không thay dữ liệu gốc, không thêm nhiễu, không thay dấu thời gian, không bổ sung mẫu hoặc xóa điểm khác phân phối.']
    (OUT/'noi_dung_dien_bao_cao.md').write_text('\n\n'.join(md)+'\n',encoding='utf-8')
    def paragraphs(ps):return ''.join('<p>'+html.escape(t)+'</p>' for t in ps)
    def bullets(ps):return '<ul>'+''.join('<li>'+html.escape(t)+'</li>' for t in ps)+'</ul>'
    compact=dict(scopes=d['scope_summaries'],labels=LABELS)
    payload=json.dumps(compact,ensure_ascii=False).replace('</','<\\/')
    body='''<!doctype html><html lang="vi"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Đánh giá dữ liệu và nội dung báo cáo NCKH · 16/10/2026</title>
<style>:root{font-family:system-ui,"Segoe UI",sans-serif;color:#213448;background:#eef3f7;font-size:16px}*{box-sizing:border-box}body{margin:0}main{max-width:1260px;margin:auto;padding:28px}header,section{background:white;border:1px solid #dce4ec;border-radius:12px;padding:26px;margin:0 0 20px}h1{font-size:29px;line-height:1.25;margin:0 0 12px}h2{font-size:22px;margin:0 0 14px}h3{font-size:19px}p,li{line-height:1.65;max-width:1100px;overflow-wrap:anywhere}li{margin:8px 0}.muted{color:#55697c;font-size:14px}.lead{font-size:18px}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:20px 0}.card{background:#edf4fa;border-radius:8px;padding:16px}.card strong{display:block;font-size:27px}.card span{font-size:14px}.scroll{overflow:auto;max-width:100%;margin:14px 0}table{border-collapse:collapse;width:100%;font-size:14px;font-variant-numeric:tabular-nums}th,td{padding:11px 12px;text-align:right;border-bottom:1px solid #dce4ec;vertical-align:top}th{background:#e8f0f7;color:#173d60;white-space:nowrap}td:first-child,th:first-child{text-align:left}tbody tr:nth-child(even){background:#f7f9fb}nav{display:flex;gap:12px;flex-wrap:wrap}a{color:#075f9e}nav a{padding:9px 12px;border:1px solid #c9d9e5;border-radius:7px;text-decoration:none}select{font:inherit;max-width:100%;padding:8px;border:1px solid #b8c9d8;border-radius:6px}img{display:block;width:100%;height:auto;margin:15px auto}.note{background:#fff7e8;padding:16px;border-left:4px solid #c1852a;border-radius:4px}details{margin-top:18px}summary{cursor:pointer;font-weight:600;padding:8px 0}#readiness td{text-align:left;min-width:130px}#readiness td:last-child{min-width:310px}.caption{font-size:14px;color:#546a7e}.copy{border-left:3px solid #aac4d9;padding-left:18px}@media(max-width:700px){main{padding:12px}header,section{padding:17px}.cards{grid-template-columns:repeat(2,1fr)}h1{font-size:24px}.card strong{font-size:23px}th,td{padding:9px}}@media print{body{background:white}main{padding:0}header,section{border:0;break-inside:avoid}nav,select{display:none}.scroll{overflow:visible}details{display:block}}</style><main>
'''
    body+='<header><p class="muted">Đối chiếu ngày 16/10/2026 · Dữ liệu đang hoạt động và Chương 5</p><h1>Điền được gì vào báo cáo NCKH?</h1><p class="lead">'+html.escape(opening)+'</p>'
    body+='<div class="cards">'+''.join(f'<div class="card"><strong>{a}</strong><span>{b}</span></div>' for a,b in [('13.782','CSV được kiểm tra'),('16.216.648','dòng dữ liệu'),('23 / 24','dòng bảng có thể tính'),('0','CSV bị thay đổi')])+'</div>'
    body+='<nav><a href="noi_dung_dien_bao_cao.md">Nội dung và bảng để chép vào bài</a><a href="assessment.json">Số liệu và căn cứ</a><a href="inventory.json">Danh mục SHA-256</a><a href="../data_quality_audit_20261015_141043_680418/index.html">Kiểm định chất lượng chi tiết</a></nav></header>'
    body+='<section><h2>Hiện trạng và nguồn dữ liệu</h2>'+paragraphs([provenance])+table(['Nguồn gốc','CSV','Dòng'],source_rows)+'<p class="note">Khớp hồ sơ thu cũ chưa xác nhận độc lập việc thu phần cứng. Phần ba nguồn hiện gồm mô phỏng có hồ sơ và dữ liệu chưa xác minh.</p></section>'
    body+='<section id="readiness"><h2>Đối chiếu từng bảng và hình Chương 5</h2>'+table(['Vị trí','Mức độ sẵn sàng','Căn cứ và giới hạn'],READINESS)+'<details><summary>Các bảng và hình ở Chương 1–4</summary>'+table(['Vị trí','Khả năng bổ sung từ data','Căn cứ cần có'],EARLIER_CHAPTERS)+'</details></section>'
    body+='<section><h2>Số liệu cho Bảng 5.2 và 5.3</h2>'+paragraphs([definition,main_table_note])+'<label>Nguồn dữ liệu hiển thị: <select id="scope"><option value="all">Toàn bộ dữ liệu hiện có</option>'+''.join('<option value="'+k+'">'+v+'</option>' for k,v in LABELS.items())+'</select></label><p id="scope_note" class="caption"></p><h3>Bảng 5.2 · Không AI</h3><div id="table52"></div><h3>Bảng 5.3 · Có AI</h3><div id="table53"></div></section>'
    body+='<section><h2>Các nhận xét quan trọng</h2>'+bullets(findings)+'</section>'
    body+='<section><h2>Hình 5.2 · Một nguồn theo góc</h2><img src="figures/hinh_5_2_mot_nguon.png" alt="Recall và MAE một nguồn tại bốn cự ly"><p class="caption">Mỗi điểm gộp các CSV có đúng góc và cự ly tương ứng, chọn 12 góc theo thiết kế. Hình sử dụng tập hỗn hợp; nguồn gốc/điều kiện phải được nêu khi chèn vào bài. <a href="figures/hinh_5_2_mot_nguon.svg">Bản SVG</a></p></section>'
    body+='<section><h2>Hình 5.3 · F1 theo cự ly</h2><img src="figures/hinh_5_3_f1_khoang_cach.png" alt="F1 theo cự ly cho một hai ba nguồn"><p class="caption">F1 tính cả khung trống, gộp từ số đếm. Vùng màu là khoảng bootstrap 95% có điều kiện theo cụm góc hoặc CSV; không xác nhận sai số suy rộng phần cứng. Điểm thiếu được giữ trống. <a href="figures/hinh_5_3_f1_khoang_cach.svg">Bản SVG</a></p></section>'
    body+='<section><h2>Khả năng phát hiện đủ ba nguồn</h2><img src="figures/ba_nguon_phat_hien_dong_thoi.png" alt="Recall nguồn và tỷ lệ khung phát hiện đủ ba nguồn"><p class="caption">Đủ nguồn nghĩa là ghép đúng cả ba nguồn trong dung sai, không chỉ detected_count bằng 3. <a href="figures/ba_nguon_phat_hien_dong_thoi.svg">Bản SVG</a></p></section>'
    body+='<section><h2>Recall, F1 và khung trống</h2>'+table(aux_headers,aux_rows)+'<details><summary>So sánh trên cùng bố trí góc</summary>'+paragraphs([comparison_note])+table(common_headers,common_rows)+'</details><details><summary>Độ nhạy với cách đặt trọng số</summary>'+table(['Nguồn','Chế độ','cm','F1 gộp (%)','F1 đều file (%)','F1 đều góc (%)'],weight_rows)+'</details></section>'
    body+='<section><h2>Độ phủ quy trình dự kiến</h2>'+bullets(gaps)+'<details><summary>21 điều kiện góc–cự ly–chế độ chưa có số liệu</summary>'+table(['Nguồn','Chế độ','cm','Góc còn thiếu'],missing_rows)+'</details></section>'
    body+='<section><h2>Chất lượng, sự lặp và thời gian lưu</h2>'+paragraphs([quality,timing])+'<details><summary>Phân bố tỷ lệ góc giữ nguyên theo nhóm</summary><p>Chỉ xét các cặp hướng ở hai khung kề nhau đều có hướng, ghép theo độ dịch vòng nhỏ nhất. Không nối qua khung trống; chưa xác nhận danh tính nguồn.</p>'+table(repeat_headers,repeat_rows)+'</details></section>'
    body+='<section><h2>Nội dung cần điều chỉnh trong bài</h2>'+bullets(edits)+'<h3>Đoạn văn tham khảo</h3><div class="copy">'+paragraphs(copytext)+'</div></section>'
    body+='<section><h2>Căn cứ và giới hạn</h2><p>Đã đọc toàn bộ nội dung liên quan trên các trang PDF 50–56 và những trang liên quan của Chương 3–4 trong Báo cáo NCKH, gồm chú thích, quy tắc ghép, điều kiện nền và số khung dự kiến. '+html.escape(d['resampling_note'])+'</p><p>Bảng tổng hợp mô tả toàn bộ tập hiện có. Kết luận thực nghiệm cần đối chứng cùng góc, cùng nội dung âm thanh, cùng nền, cùng phiên bản firmware và quy trình thu. Không dùng p-value hoặc mức độ tự nhiên của phân phối để kết luận nguồn gốc dữ liệu.</p><p class="caption">Các số liệu, thành phần nguồn, độ phủ theo bộ góc, chênh lệch theo nhóm và danh mục đầu vào có trong các tệp căn cứ ở đầu trang. PDF nguồn và dữ liệu gốc được giữ nguyên.</p></section>'
    body+='<script type="application/json" id="data">'+payload+'</script>'
    body+='''<script>const DATA=JSON.parse(document.getElementById('data').textContent);const f=(v,p=false)=>v===null||v===undefined?'—':new Intl.NumberFormat('vi-VN',{minimumFractionDigits:2,maximumFractionDigits:2}).format(v*(p?100:1));const n=v=>new Intl.NumberFormat('vi-VN').format(v);function render(){const scope=document.getElementById('scope').value;for(const mode of ['NOAI','AI']){const rows=DATA.scopes.filter(r=>r.scope===scope&&r.mode===mode);document.getElementById(mode==='NOAI'?'table52':'table53').innerHTML='<div class="scroll"><table><thead><tr>'+['Nguồn','Cự ly (m)','MAE (°)','P (%)','R (%)','F1 (%)','CSV','Khung','Bố trí góc'].map(t=>'<th>'+t+'</th>').join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+[r.n_sources,f(r.distance_cm/100),f(r.matched_mae_deg),f(r.precision,true),f(r.recall_all,true),f(r.f1_all,true),n(r.files),n(r.frames),n(r.geometries)].map(v=>'<td>'+v+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>';}document.getElementById('scope_note').textContent=scope==='all'?'Đang gộp mô tả toàn bộ tập hỗn hợp. Chưa xác nhận cùng điều kiện thực nghiệm.':scope==='CAPTURE_RECORD_MATCH'?'Chỉ các file khớp checksum bản ghi thu cũ; chưa xác nhận độc lập điều kiện thu phần cứng.':scope==='SYNTHETIC_DOCUMENTED'?'Kết quả mô phỏng có hồ sơ. Không trình bày như phép đo phần cứng.':'Chưa đủ bằng chứng xác minh nguồn gốc và điều kiện thu.';}document.getElementById('scope').addEventListener('change',render);render();</script></main></html>'''
    (OUT/'index.html').write_text(body,encoding='utf-8')
    write(OUT/'paper_readiness.json',dict(tables_and_figures=[dict(location=r[0],status=r[1],evidence=r[2]) for r in READINESS],
        earlier_chapters=[dict(location=r[0],status=r[1],evidence=r[2]) for r in EARLIER_CHAPTERS],
        numeric_rows_table_52=11,numeric_rows_table_53=12,full_hardware_protocol_validated=False,
        primary_recall_includes_empty=True,primary_f1_includes_empty=True,missing_planned_conditions=len(planned_missing),
        requested_source_file=str(ROOT/'paper/Báo cáo NCKH.pdf'),sha256=d['paper_sha256']))
    print(json.dumps(dict(status='REPORT_WRITTEN',html=str(OUT/'index.html'),markdown=str(OUT/'noi_dung_dien_bao_cao.md'),figures=3),ensure_ascii=True),flush=True)

if __name__=='__main__':build()
