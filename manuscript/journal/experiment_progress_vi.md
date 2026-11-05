# Tiến độ thử nghiệm trên VM, 05-11-2026

Mốc hội nghị là `(72, 68, 58)`, tổng 198 optimum. Tiêu chí được nhóm chốt
trước chu kỳ mới: không giảm coverage ở từng objective và tổng ít nhất 199;
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

## Chu kỳ đang triển khai

Baseline riêng ở commit `8226f5a`, timeout 150 giây. Binary và worktree được
giữ cố định; mã `legacy` vẫn dùng quy trình của CSOnet. Chu kỳ sau ở commit
`cb839c7` đợi baseline kết thúc rồi thử sáu cấu hình, promote ba cấu hình,
khóa một cấu hình và chạy toàn bộ 72 instance. Chỉ lặp xác nhận nếu vượt
coverage. Các cờ mới mặc định tắt hoặc giữ hành vi ban đầu.

Hai thư mục này chứa kết quả mới trên VM:

```text
~/projects/experiment-audit/rounds/baseline-20261105-8226f5a/
~/projects/experiment-audit/rounds/cycle-20261105-cb839c7-*/
```

Objective bound đã qua bảng chân trị, kiểm tra tổng trọng số khi giảm UB,
và bài toán nhỏ vét cạn. Bộ kiểm thử Linux hiện có 24 Rust tests và 14 Python
tests. Chưa điền số AGLR mới vào Abstract, Results hoặc Conclusion.

CPLEX trên VM chưa có; các CSV CPLEX cũ là 120 giây. Không đổi tên chúng thành
150 giây. Cổng submission đầy đủ cần kết quả CPLEX đúng timeout, có nghiệm
được kiểm tra và cận khớp.
