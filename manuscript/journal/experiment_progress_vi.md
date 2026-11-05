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

## Chu kỳ 120 giây đã khởi động

Commit `20bd54d` đã chạy lại 25 Rust tests; 60 lần chạy ngắn xen kẽ legacy và
AGLR đều thoát bình thường. Sửa lỗi khởi tạo môi trường Gurobi thừa đã được áp
dụng cho cả worker cũ, giữ nguyên phép tính heuristic và cách refinement.

VM đang chạy dịch vụ `aglr-paper120-20bd54d`: baseline 120 giây, sau đó ablation
từng thành phần, promote, một cấu hình khóa trên toàn bộ tập và xác nhận nếu
đạt coverage. Toàn dịch vụ giới hạn 6 giờ. Worktree và binary được giữ riêng.

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

CPLEX trên VM chưa có; các CSV CPLEX cũ là 120 giây nhưng thiếu lịch/\`valid\`.
Cổng submission đầy đủ cần nghiệm được kiểm tra và cận khớp. Không yêu cầu
chạy CPLEX 150 giây. Liên kết IBM Academic đã được cung cấp; đây là cổng web
chứ chưa phải file cài đặt Linux.
