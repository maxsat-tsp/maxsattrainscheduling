# VM, 120 giây: AGLR chưa đạt coverage

Nguồn: dịch vụ `aglr-paper120-20bd54d` trên VM `trp`, commit solver `20bd54d`.
Mốc hội nghị là các CSV 120 giây trong `results/`, nguồn dữ liệu commit
`db0b16f20d97045501e63e4b432a879218a0c180`. Runtime được so sánh theo giả định
cùng phần cứng đã thống nhất.

| Cấu hình | finsteps123 | infsteps180 | cont | Tổng |
|---|---:|---:|---:|---:|
| Hội nghị | 72 | 68 | 60 | 200 |
| CSOnet chạy lại | 72 | 68 | 59 | 199 |
| AGLR, rescue theo mô hình | 72 | 67 | 57 | 196 |

Auditor của lượt gốc không báo lỗi. AGLR chưa đạt coverage; không dùng các số
này làm kết luận đã vượt baseline. Big-M Gurobi trong bảng hội nghị còn đạt
67 instance `cont`, nên vượt CSOnet cũng chưa đủ để kết luận vượt mọi baseline.

`raw_results.tar.gz` giữ nguyên JSON, CSV, cấu hình và các báo cáo của bốn
giai đoạn: baseline, ablate, promote, candidate. Không có log stdout/stderr
trong bản nén; log và manifest chi tiết vẫn ở VM, tại
`/home/tuyenkv/projects/experiment-audit/rounds/`. Manifest cấp campaign trong
bản nén ghi hash binary và commit. Không suy đoán provenance cho kết quả cũ.

SHA-256 của bản nén:
`f17663fb16298cf51127b9a970c2b3ba9a401da2933b6c1d37f585934a0a8259`.

Chạy lại kiểm toán từ thư mục gốc repo:

```bash
mkdir -p results/aglr/paper120-archived
tar -xzf results/sat_research/vm_paper120_20261105/raw_results.tar.gz \
  -C results/aglr/paper120-archived
python3 quick_scripts/analyze/audit_aglr_campaign.py \
  results/aglr/paper120-archived/cycle-paper120-20bd54d-candidate \
  --timeout 120 --conference-reference results \
  --conference-profile published-csv-120 \
  --conference-runtime-mode assumed-equivalent
```

Các báo cáo trong bản nén là bản gốc. Phiên bản auditor mới ghi cả coverage
khi chưa đạt target, nên `gate.total_coverage` sẽ là 196 thay cho 0 trong báo
cáo gốc. Giá trị nghiệm, trạng thái và thời gian không thay đổi.
