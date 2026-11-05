# Cách gửi điều kiện chi phí vào SAT: chưa tăng coverage

Solver ở commit `fb85033`, chạy trên VM `trp`. Giữ refinement CSOnet;
chỉ đổi số điều kiện chi phí được gửi trong một lời gọi SAT.

| Giai đoạn | Cách gửi | finsteps123 | infsteps180 | cont |
|---|---|---:|---:|---:|
| 30 giây, 24 instance | legacy, tăng 20 | 24 | 22 | 17 |
| 30 giây, 24 instance | full, gửi hết | 24 | 22 | 17 |
| 30 giây, 24 instance | geometric, tăng gấp đôi | 24 | 22 | 18 |
| 120 giây, 24 instance | full | 24 | 22 | 18 |
| 120 giây, 24 instance | geometric | 24 | 22 | 18 |
| Hội nghị, 120 giây, cùng tập | CSOnet | 24 | 22 | 20 |

Không cấu hình nào giữ được coverage phát triển ở 120 giây; không chạy full
hướng này. Auditor không phát hiện lỗi trong 360 kết quả sinh ra. Ít lời gọi
SAT hơn không đồng nghĩa giải được nhiều instance hơn.

Trên `stationA3/cont`, lượt 30 giây có 4.737 lời gọi SAT ở legacy và 568
ở full; cả hai vẫn timeout. Dùng số này để chẩn đoán, không tuyên bố cải
thiện hiệu năng chung chỉ từ số lời gọi.

`screen_summary.csv` và `promote_summary.csv` là bảng gốc; `core_selection.json`
ghi quyết định không chọn cấu hình để full. `raw_results.tar.gz` giữ JSON,
cấu hình, bảng và manifest từng objective. Đã bỏ log stdout/stderr và JSON
từng instance bị lặp lại trong JSON tổng. Dữ liệu gốc ở VM vẫn được giữ.

SHA-256:
`dead1ca3effbad875617629b74e0a0b40e6cc501c7a88b7a2d368a4bcbbc01b3`.

Các thời gian ở đây là thời gian phát triển, gồm screen hai worker;
không đưa vào bảng thực nghiệm chính. Vòng tiếp theo thử riêng việc bỏ
các mức chi phí trung gian trong cây chi phí.
