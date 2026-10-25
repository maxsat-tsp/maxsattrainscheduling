# Runbook thực nghiệm AGLR

## Trạng thái

AGLR đã được cài trực tiếp trên solver CSOnet. Tên solver mới là
`maxsat_ddd_ladder_aglr`; tên cũ `maxsat_ddd_ladder_sc` vẫn chạy đúng đường
`legacy`. Các kết quả RC2+B+R trước đây chỉ dùng để chẩn đoán và không đi vào
bảng chính.

Chiến dịch đầu chỉ chạy mỗi cấu hình một lần. Các lượt lặp chỉ bắt đầu sau khi
AGLR vượt ngưỡng coverage và PAR-2.

## Việc sinh viên làm ngay

Trước mắt chỉ chạy giai đoạn `screen`. Không sửa tham số, không sửa JSON/CSV và
chưa chạy `full`. Chuẩn bị mã bằng các lệnh:

```bash
git fetch origin
git checkout journal-aglr
git pull --ff-only
git rev-parse HEAD
git status --short
```

`git status --short` phải không in gì. Sau khi test đạt, chạy:

```bash
bash run_aglr_experiments.sh screen
```

Khi hoàn tất, gửi lại đường dẫn thư mục chiến dịch cùng `campaign.txt`,
`aglr_ranking.csv`, `aglr_summary.csv`, `aglr_audit.json` và
`latest_screen.txt`. Nếu có lỗi, gửi thêm `*.stderr.log` của instance liên
quan. Giữ và sao lưu toàn bộ `results/aglr/`; thư mục này không được commit.

## Chuẩn bị máy

Máy cần Rust, Python 3, GNU `timeout`, Gurobi có license và hai repository
`../salvers`, `../ipamir-rs`. Lượt so sánh đầy đủ cần thêm kết quả Big-M CPLEX
từ cùng điều kiện chạy hoặc một môi trường đủ tương đương.

```bash
git checkout journal-aglr
git pull --ff-only
cargo check -p ddd --all-targets
cargo test -p ddd aglr --lib
```

Cây Git phải sạch trước khi chạy. Script tự build một binary release, ghi commit,
hash binary, hash dữ liệu, môi trường, tham số, thứ tự instance, stdout và stderr.

## 1. Sàng lọc 18 cấu hình

```bash
bash run_aglr_experiments.sh screen
```

Lệnh này chạy một lần trên 24 instance phát triển, giới hạn 30 giây. Lưới tham
số là:

- `K_min`: 16, 32, 64;
- `rho`: 0.25, 0.5, 0.75;
- `W`: 5, 10.

Có 18 cấu hình, ba objective và 24 instance, tức 1296 lời gọi solver. Tổng
timeout nội bộ tối đa khoảng 10.8 giờ nếu chạy tuần tự và mọi lời gọi đều hết
30 giây. Thời gian thực tế có thể khác vì nhiều instance kết thúc sớm và mỗi
lời gọi còn có chi phí khởi động.

Kết quả gần nhất được ghi trong `results/aglr/latest_screen.txt`. Xem
`aglr_ranking.csv` trong thư mục được chỉ ra bởi file này.

Nếu tiến trình bị ngắt, chạy lại với đúng `RUN_ID`:

```bash
RUN_ID=screen-YYYY-MM-DD_HH-MM-SS \
  bash run_aglr_experiments.sh screen
```

Các instance đã có JSON hợp lệ sẽ được dùng lại.

## 2. Chạy ba cấu hình tốt nhất ở 120 giây

```bash
bash run_aglr_experiments.sh promote
```

Script tự đọc ba dòng đầu của ranking. Thứ tự xếp hạng là số optimum, PAR-2,
rồi mức tăng mô hình. Có thể chỉ rõ kết quả sàng lọc:

```bash
SCREEN_DIR=results/aglr/<screen-run> \
  bash run_aglr_experiments.sh promote
```

## 3. Khóa cấu hình và chạy đủ 72 instance

Chuẩn bị ba CSV Big-M CPLEX cho `finsteps123`, `infsteps180` và `cont`. Script
nhận mẫu `results_bigm_<objective>_120s.csv` hoặc
`MILP_BigM_CPLEX_<objective>_120s.csv`. File phải chứa `name`, `status`, `lb`,
`ub`, thời gian chạy và `valid`. Giá trị `valid=true` xác nhận lịch đã qua bộ
kiểm tra nghiệm. `status=ok` chỉ được tính tối ưu khi `valid=true` và `lb`, `ub`
khớp. CSV cũ thiếu `valid` chỉ dùng tham khảo, không dùng mở cổng submission.

Ví dụ một CSV tối thiểu:

```csv
name,status,lb,ub,total_time,valid
originalA1,ok,11,11,0.446,true
```

`valid=true` phải do chương trình kiểm tra lịch sinh ra, không được điền tay từ
trạng thái tối ưu của CPLEX.

```bash
CPLEX_RESULTS_DIR=/absolute/path/to/cplex_csv \
  bash run_aglr_experiments.sh full
```

Lượt đầy đủ chạy và kiểm tra:

- MaxSAT-DDD của bài tạp chí trước;
- CSOnet `legacy`;
- AGLR `all-scanned`;
- AGLR `adaptive` với tham số đã khóa;
- Big-M Gurobi;
- Big-M CPLEX nhập từ thư mục trên.

Có thể khóa tham số bằng tay nếu cần tái tạo một cấu hình đã chọn:

```bash
AGLR_MIN_GROWTH=32 \
AGLR_FRACTION=0.5 \
AGLR_MAX_WAIT=5 \
CPLEX_RESULTS_DIR=/absolute/path/to/cplex_csv \
  bash run_aglr_experiments.sh full
```

Không dùng thời gian CPLEX cũ nếu máy, phiên bản solver, timeout, số luồng hoặc
cách xác nhận tối ưu khác với chiến dịch chính. Chi phí tối ưu cũ vẫn có thể
dùng làm mốc kiểm tra.

## 4. Xác nhận các instance quan trọng

Chỉ làm bước này sau khi `aglr_audit.json` của lượt đầy đủ có `gate.passed=true`.

```bash
bash run_aglr_experiments.sh confirm
```

Script chạy ba lần các instance trên 30 giây và các instance AGLR được/mất so
với baseline. Không chạy lặp toàn bộ 72 instance ở giai đoạn đầu.

## Cổng sử dụng cho submission

Auditor từ chối file thiếu, tên instance thừa/trùng, lịch sai, chi phí sai và
kết quả MILP không có cận khớp. AGLR chỉ qua cổng khi:

- `finsteps123`: 72/72 và PAR-2 thấp hơn baseline hoàn chỉnh tốt nhất;
- `infsteps180`: ít nhất 69/72;
- `cont`: ít nhất 68/72;
- đủ MaxSAT-Journal, CSOnet, BigM-Gurobi và BigM-CPLEX;
- không có `panic`, nghiệm sai hoặc lỗi dữ liệu.

Các file cần giữ để viết bài:

- `aglr_summary.csv`;
- `aglr_ranking.csv`;
- `aglr_audit.json`;
- `confirm_instances.txt`;
- mọi JSON, manifest và log instance trong cùng thư mục chiến dịch.

Báo cáo sau mỗi giai đoạn phải ghi commit, thông tin máy, phiên bản Gurobi/CPLEX,
thư mục kết quả, cấu hình đứng đầu và mọi lỗi trong `aglr_audit.json`.
Dùng mẫu `manuscript/journal/student_experiment_report_template_vi.md`.

Nếu cổng chưa đạt, đọc telemetry rồi chỉ đổi một thành phần: giảm `W` hoặc tăng
`rho` khi nhiều ứng viên chờ; giảm `rho` hoặc `K_min` khi mô hình tăng nhanh;
kiểm tra cache khi thời gian validation lớn. Chỉ thử `BinaryObjective` sau khi
có kiểm thử bảng chân trị và bài nhỏ vét cạn.
