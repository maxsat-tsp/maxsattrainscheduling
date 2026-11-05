# Tiến độ thử nghiệm trên VM, 05-11-2026

Đối chiếu lại camera-ready theo ý kiến của thầy/cô: mốc đúng là **120 giây**,
`(72,68,60)`, tổng 200 optimum. Bộ JSON 150 giây `(72,68,58)` là lượt khác;
không dùng làm mốc chính. Tiêu chí: không giảm coverage ở từng objective và tổng ít nhất 201;
PAR-2 là tiêu chí xếp hạng tiếp theo. Đây là cổng thực nghiệm nội bộ, không
phải bảo đảm bài được tạp chí chấp nhận.

## Kết quả phát triển đã có

Các số dưới đây là số optimum trong **24 instance phát triển**, theo thứ tự
`finsteps123`, `infsteps180`, `cont`; chưa phải kết quả toàn bộ 72 instance.

| Lượt | Giới hạn mỗi instance | Coverage tốt nhất | Cấu hình |
|---|---:|---|---|
| Screen 18 cấu hình | 30 s | `(24, 22, 19)` | K=16, rho=0.25, W=5 |
| Promote ba cấu hình | 120 s | `(24, 22, 19)` | K=16, rho=0.25, W=5 |
| Rescue theo mô hình + heuristic period=2, gap=1 | 30 s | `(24, 22, 19)` | K=16, rho=0.25, W=5 |

Lượt tổ hợp cuối giảm số ứng viên được chọn còn khoảng một phần ba. Coverage
chưa tăng; không thể gán riêng hiệu quả này cho rescue hay heuristic vì cả hai
đã đổi trong cùng lượt. Chu kỳ mới dùng đối chứng một thành phần mỗi lần.

Dữ liệu cũ ở VM:

```text
~/projects/maxsattrainscheduling/results/aglr/screen-20261105-vm/
~/projects/maxsattrainscheduling/results/aglr/promote-20261105-vm/
~/projects/maxsattrainscheduling/results/aglr/model-rescue-20261105-vm/
```

## Lỗi phát hiện và cách xử lý

Hai lần chạy cũ có segfault sau khi ghi JSON. Runner cũ nhìn thấy JSON rồi
bỏ qua mã thoát, nên auditor không nhận ra crash. Log kernel có lỗi trong
Gurobi khi luồng heuristic khởi tạo môi trường; heuristic này thực tế chỉ xử
lý đồ thị và không dùng Gurobi.

Đường AGLR đã bỏ khởi tạo thừa. Runner mới ghi mã thoát thật; nghiệm từ tiến
trình crash không được tính thành công. Sau sửa, 40 lần chạy ngắn trên
`origA3/finsteps123`, xen kẽ bật/tắt objective bound, đều có mã thoát 0 và
`cost=lb=ub=10`. Đây là kiểm tra hồi quy ngắn; mọi campaign sau vẫn phải kiểm
tra mã thoát trên từng instance.

## Lượt 150 giây đã dừng để sửa mốc so sánh

Baseline ở commit `8226f5a`, timeout 150 giây, đã được giữ lại làm chẩn đoán.
Hai objective đầu hoàn tất `(72,68)`, mọi mã thoát bằng 0; `cont` đang chạy
thì được dừng khi phát hiện camera-ready dùng 120 giây. Không đổi nhãn bộ dữ
liệu này thành 120 giây. Lượt AGLR 150 giây xếp hàng đã được hủy trước khi chạy.

Hai thư mục này chứa kết quả mới trên VM:

```text
~/projects/experiment-audit/rounds/baseline-20261105-8226f5a/
~/projects/experiment-audit/rounds/cycle-20261105-cb839c7-*/
```

## Chu kỳ 120 giây đã hoàn tất

Commit `20bd54d` đã chạy lại 25 Rust tests; 60 lần chạy ngắn xen kẽ legacy và
AGLR đều thoát bình thường. Sửa lỗi khởi tạo môi trường Gurobi thừa đã được áp
dụng cho cả worker cũ, giữ nguyên phép tính heuristic và cách refinement.

Dịch vụ `aglr-paper120-20bd54d` đã kết thúc. Mọi lịch tối ưu trong lượt mới
đã qua auditor; không có lỗi nghiệm hoặc mã thoát. Kết quả full:

| Phương pháp | finsteps123 | infsteps180 | cont | Tổng |
|---|---:|---:|---:|---:|
| Mốc hội nghị 120 giây | 72 | 68 | 60 | 200 |
| CSOnet chạy lại trên VM | 72 | 68 | 59 | 199 |
| AGLR, rescue theo mô hình | 72 | 67 | 57 | 196 |

AGLR dùng `K_min=16`, `rho=0.25`, `W=5`; không bật giới hạn objective hay lọc
trùng. PAR-2 của AGLR lần lượt là `0.1200`, `16.9869`, `52.1276` giây; chưa
đạt tiêu chí. AGLR giải được `trackB12/cont` trong 40.35 giây, nhưng mất các
instance khác. Không ghép nghiệm từ nhiều cấu hình thành kết quả của một solver.

Trên 24 instance phát triển, sáu ablation đều không tăng coverage. Rescue
theo mô hình đạt `(24,22,19)` ở cả 30 và 120 giây; các biến thể heuristic,
lọc trùng và giới hạn objective không tốt hơn. Kết quả này được giữ làm bằng
chứng để chọn hướng tiếp theo.

```text
~/projects/experiment-audit/rounds/baseline-paper120-20bd54d/
~/projects/experiment-audit/rounds/cycle-paper120-20bd54d-*/
```

Mốc 120 giây có coverage `(72,68,60)` và PAR-2 lần lượt khoảng
`0.0230`, `13.7854`, `44.0667` giây. Đây là thời gian từ CSV đã công bố,
được so sánh theo giả định cùng phần cứng của nhóm. CSV không có lịch để kiểm
tra độc lập. Trên 24 instance phát triển, mốc này là `(24,22,20)`; vì vậy các
lượt cũ đạt `(24,22,19)` chưa vượt mốc chính dù giải thêm được `trackB12/cont`.

Objective bound đã qua bảng chân trị, kiểm tra tổng trọng số khi giảm UB,
và bài toán nhỏ vét cạn. Bộ kiểm thử Linux có 25 Rust tests; bộ Python sau
sửa profile 120 giây có 16 tests.
Chưa điền số AGLR mới vào Abstract, Results hoặc Conclusion.

## Hướng tiếp theo: cách đưa chi phí vào SAT

Ở các instance khó, hơn 98% thời gian của AGLR nằm trong SAT; phần kiểm tra
nghiệm và chọn xung đột rất nhỏ. Vòng tiếp theo giữ refinement CSOnet và chỉ
đổi cách gửi các điều kiện chi phí vào SAT:

- `legacy`: thêm 20 điều kiện sau mỗi lời gọi SAT có nghiệm;
- `full`: gửi toàn bộ điều kiện ngay;
- `geometric`: thử 20, 40, 80, ... cho đến khi đủ.

Đây là giả thuyết cần đo, chưa phải một cải tiến đã được chứng minh bằng số
liệu. Mọi cách đều phải kiểm tra toàn bộ điều kiện trước khi dùng nghiệm SAT
để refinement. Trường `maxsat_sat_calls` đếm số lời gọi SAT, còn
`maxsat_partial_sat_calls` đếm các lần có nghiệm khi mới gửi một phần điều kiện.
Script `run_maxsat_core_experiments.sh` ghi cấu hình, commit, hash binary,
hash dữ liệu và mã thoát; dùng cùng auditor để kiểm tra lịch và chi phí.

Đã triển khai thêm một phép thử độc lập: biểu diễn chi phí chỉ bằng các mức
DDD đã tạo, không tự thêm các mức nguyên trung gian. Mặc định của baseline
giữ nguyên. Ví dụ hai mức 3 và 7 có thể dùng trọng số 3 và 4 thay vì bảy
trọng số 1. Bộ kiểm thử Linux có 28 tests, gồm mọi tổ hợp của các mức
`[7,3,11,5,7]` với cận 0..12 và bài lịch tàu nhỏ với ba objective. Phép thử
hiệu năng dùng `EXPERIMENT_SET=costs`; chưa có số liệu để kết luận thắng.

Đã khóa mã vòng kế tiếp tại commit `27b6859`. Dịch vụ
`maxsat-cost-v2-27b6859` đợi `maxsat-core-v1-fb85033` kết thúc rồi mới build
và chạy. Hai vòng không chạy solver cùng lúc. Vòng mới tự chọn một cấu hình
đạt mốc phát triển trước khi chạy full; chỉ chạy xác nhận sau khi full vượt
coverage hội nghị.

Đã sửa cổng cuối: có đủ baseline chưa đủ để báo PASS. Auditor phải so tổng
coverage với từng baseline, rồi PAR-2 nếu coverage bằng nhau. Bước này tách
khỏi cổng coverage hội nghị; các kết quả và bảng từng objective vẫn giữ riêng.

Tái sử dụng bảng hội nghị cho biết Big-M Gurobi có tổng 206 optimum. Tuy
nhiên hai dòng CPLEX báo chi phí không khớp: `trackA1/finsteps123` là 24 thay
vì 23, `stationB12/infsteps180` là 120 thay vì 98. Đã có lịch mới hợp lệ chi
phí 23 và 98, nên không dùng hai cận CPLEX này làm oracle. Báo cáo ở
`reviews/published_baselines_20261105/README.md`; dữ liệu gốc giữ nguyên.
Việc này không dừng các vòng cải tiến SAT đang chạy.

## CPLEX và tái sử dụng dữ liệu đã hoàn tất

Đã dùng ticket IBM Academic để tải qua HTTP bộ cài CPLEX Optimization Studio
22.2.0 cho Linux x86-64 (part `M113NML`). Cài tại
`~/opt/ibm/ILOG/CPLEX_Studio2220`; CLI và Python API đều chạy trong Conda
environment `gurobi`. `docplex config --upgrade` đã dùng thư viện từ bản cài
academic; native library và Python library có cùng SHA-256. CLI giải bài 1201
biến/1201 ràng buộc, Python giải bài 1201 biến, cả hai cho optimum 1201.

Installer SHA-256:
`34963192dabe3b5fad22272a3b10a8207629c5674766da1b345f858d2d667f1b`.
Ticket và signed download URL không được đưa vào manifest hoặc Git.

Đã thêm phép cắt cutoff 150 xuống 120 giây, có kiểm tra nghiệm và hash nguồn.
Kết quả từ bộ JSON nhập là `(72,68,57)`, PAR-2 `(0.120001,15.240171,53.547450)`
giây. `trackB4/cont` mất 123.462673 giây nên bị chuyển thành timeout. LB/UB
sau cutoff được bỏ khỏi các ca bị cắt. Các CSV CPLEX cũ vẫn thiếu lịch/`valid`;
cài xong phần mềm chưa có nghĩa đã hoàn tất bảng thực nghiệm CPLEX mới.
