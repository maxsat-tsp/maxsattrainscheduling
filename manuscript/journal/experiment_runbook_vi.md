# Runbook thực nghiệm cho bản tạp chí

## Trạng thái hiện tại

Mã đã sẵn sàng cho **một lượt kiểm tra toàn bộ dataset với K=128**. Các điểm
chặn về tính đúng và ghi số liệu đã được xử lý:

- validator dùng đúng biên thời gian của DDD/MILP;
- có test cho biên `earliest`, tiếp xúc tài nguyên, suy luận cận và forced order;
- JSON ghi số biến, số mệnh đề, thời gian từng pha và diễn biến LB/UB;
- script kiểm tra đúng 72 instance, cấu hình thực tế, chi phí, manifest và hash
  dataset/dependency;
- smoke test trên `origA1/finsteps123` đã hoàn thành tối ưu ở cả bốn cấu hình
  với cùng chi phí.

Chính sách R đang chạy là greedy theo số mốc mới, kèm chống bỏ đói. Chính sách
utility-aware mô tả trong bản thảo COR chưa được cài đặt. Vì vậy không gọi kết
quả của chiến dịch này là kết quả utility-aware.

## Việc chạy ngay trên máy thực nghiệm

Từ thư mục gốc repository:

```bash
# 1. Kiểm tra môi trường và bốn cấu hình trên một instance
bash run_journal_smoke.sh 120 128 origA1 finsteps123

# 2. Chạy đúng một lần: 72 instance × 3 objective × 4 cấu hình = 864 lượt
bash run_journal_once.sh 120 128
```

Máy phải có Gurobi và license hợp lệ, `timeout` hoặc `gtimeout`, cùng hai
repository `../salvers` và `../ipamir-rs`. `run_journal_once.sh` chỉ chạy khi
cây Git chính sạch; hãy commit trước khi chạy.

Nếu chiến dịch bị ngắt, tiếp tục đúng thư mục cũ:

```bash
RUN_ID=$(cat results/improvements/journal_once_run_id.txt)
RUN_ID="$RUN_ID" bash run_journal_once.sh 120 128
```

Không đặt `RERUN_NON_OK=1` cho chiến dịch một lượt. Script sẽ giữ và dùng lại
cả timeout để không vô tình tạo lần lặp thứ hai.

## File cần lấy sau khi chạy

Thư mục `results/improvements/<RUN_ID>/` phải có:

- 12 file JSON và 12 file CSV của 4 cấu hình × 3 objective;
- `journal_summary.csv`;
- `journal_paired_comparisons.csv`;
- `journal_audit.json` với `errors` rỗng;
- `campaign.txt`, `config.txt`, manifest, stdout và stderr từng instance.

Không dùng chiến dịch nếu audit báo `panic`, `invalid_solution`, `segfault`,
`aborted`, `gurobi_error`, thiếu telemetry, khác chi phí giữa hai cấu hình cùng
hoàn thành, hoặc manifest không khớp.

## Kết quả nào dùng ngay trong bài

Lượt K=128 dùng được cho:

1. tính đúng và tính tối ưu của nghiệm;
2. số bài giải được, timeout và loại lỗi;
3. ablation B và R greedy giữa bốn cấu hình;
4. số mốc, biến, mệnh đề, forced order, LB/UB và thời gian từng pha.

Chưa dùng một lượt để đưa ra phát biểu mạnh về chênh lệch runtime ở mức vài
chục mili giây. Sau khi chốt thuật toán cuối, chạy lặp trên cùng máy và phân
tích ghép cặp theo instance.

## Các bước sau lượt K=128

1. Nhập baseline hội nghị khi được cung cấp. Giữ nguyên file gốc và kiểm tra đủ
   72 tên, 3 objective, timeout, commit, máy và số luồng.
2. Chốt phạm vi bài: cài utility-aware và so với greedy, hoặc mô tả đóng góp
   đúng là bound-guided DDD với budgeted greedy refinement.
3. Nếu cần sensitivity K=32, chỉ chạy hai cấu hình phụ thuộc K:

   ```bash
   JOURNAL_CONFIGS="RC2+R RC2+B+R" \
   RUN_ID="journal-k32-$(date +%Y-%m-%d_%H-%M-%S)" \
   bash run_journal_once.sh 120 32
   ```

4. Không chạy K=8. Chỉ thử K=256 hoặc `all` nếu K=128 còn nhiều timeout nhưng
   không còn lỗi tính đúng.
5. Khi phương pháp cuối đã ổn định, chạy lặp cho các kết luận runtime và cập
   nhật bảng/hình trong bản thảo COR từ các file audit, không chép số thủ công.
