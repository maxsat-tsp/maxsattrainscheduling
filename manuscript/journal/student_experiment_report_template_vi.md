# Báo cáo một giai đoạn thực nghiệm AGLR

Không sửa các file kết quả trước khi lập báo cáo. Điền ngắn gọn từng mục dưới
đây và gửi kèm toàn bộ thư mục chiến dịch.

## 1. Mã và môi trường

- Người chạy:
- Ngày bắt đầu và kết thúc:
- Giai đoạn: `screen` / `promote` / `full` / `confirm`
- Commit từ `git rev-parse HEAD`:
- Kết quả `git status --short` trước khi chạy: phải trống
- Hệ điều hành:
- CPU và RAM:
- Phiên bản Rust:
- Phiên bản Gurobi:
- Phiên bản CPLEX, nếu dùng:

## 2. Lệnh đã chạy

```bash
# Chép nguyên lệnh ở đây.
```

- `RUN_ID`:
- Thư mục chiến dịch trong `results/aglr/`:
- Đây là lượt chạy mới hay tiếp tục một lượt bị ngắt:

## 3. Kiểm tra trước khi chạy

- `cargo check`: đạt / không đạt
- `cargo test -p ddd aglr --lib`: đạt / không đạt
- Gurobi license: đạt / không đạt
- GNU `timeout`: tìm thấy / không tìm thấy

Nếu một mục không đạt, dừng tại đây và đính kèm toàn bộ thông báo lỗi.

## 4. Kết quả chính

- Auditor kết thúc bình thường: có / không
- Số lỗi trong `aglr_audit.json`:
- `gate.passed`, nếu là lượt `full`:
- Cấu hình đứng đầu:
- `K_min`:
- `rho`:
- `W`:
- Tổng số optimum trên ba objective:
- Tổng PAR-2 trên ba objective:
- Mức tăng mô hình được báo cáo:

Không tự diễn giải rằng phương pháp đã tốt hơn baseline nếu cổng chưa đạt.

## 5. Bất thường cần xem xét

Liệt kê instance có `panic`, lỗi dữ liệu, lịch sai, timeout bất thường hoặc log
khác với các instance còn lại. Với mỗi trường hợp, ghi:

- objective và instance;
- phương pháp hoặc cấu hình;
- trạng thái;
- đường dẫn `stdout.log` và `stderr.log`;
- vài dòng lỗi cuối, không sửa nội dung log.

## 6. File gửi kèm

- [ ] `campaign.txt`
- [ ] `aglr_ranking.csv`
- [ ] `aglr_summary.csv`
- [ ] `aglr_audit.json`
- [ ] `confirm_instances.txt`, nếu đã được sinh
- [ ] file `latest_<giai-doan>.txt`
- [ ] toàn bộ JSON, manifest và log của thư mục chiến dịch
- [ ] ba CSV CPLEX có `valid=true`, nếu là lượt `full`
