# Runbook thực nghiệm AGLR

## Trạng thái

AGLR đã được cài trực tiếp trên solver CSOnet. Tên solver mới là
`maxsat_ddd_ladder_aglr`; tên cũ `maxsat_ddd_ladder_sc` vẫn chạy đúng đường
`legacy`. Các kết quả RC2+B+R trước đây chỉ dùng để chẩn đoán và không đi vào
bảng chính.

Kết quả CSOnet của bài hội nghị đã được nhập nguyên trạng từ commit dữ liệu
`c427a104c3c6f844e515efb7f898b684553b0f3f`. Auditor đã kiểm tra lại độc lập
mọi lịch có `status=ok`. Số instance đã chứng minh tối ưu lần lượt là 72/72,
68/72 và 58/72 cho `finsteps123`, `infsteps180` và `cont`. Không có lịch sai,
sai chi phí hoặc `panic`.

Các chi phí đã kiểm tra được dùng để phát hiện lỗi hồi quy. Dữ liệu hội nghị
không có manifest máy và hash binary. Với VM mới, nhóm chấp nhận giả định cùng
phần cứng và bỏ qua khác biệt nhỏ về phiên bản để so sánh thời gian.

Trong chiến dịch trên VM mới, thầy/cô chấp nhận giả định máy chạy hội nghị và
VM là cùng phần cứng. Khi gọi auditor với
`--conference-runtime-mode assumed-equivalent`, thời gian hội nghị được dùng
làm mốc PAR-2 thứ cấp. Manifest của chiến dịch phải ghi rõ giả định này.

Mỗi cấu hình ban đầu chỉ chạy một lần. Khi coverage từng objective không giảm
và tổng tăng lên ít nhất 199, chạy thêm ba lần các instance cần xác nhận.

## Việc sinh viên làm ngay

Lưới 18 cấu hình `screen` và ba cấu hình `promote` đã chạy trên VM. Không cần
chạy lại các lượt cũ. Đọc `experiment_progress_vi.md` để biết kết quả và vị trí
dữ liệu. Trước một vòng mới, chuẩn bị mã bằng các lệnh:

```bash
git fetch origin
git checkout journal-aglr
git pull --ff-only
git rev-parse HEAD
git status --short
```

`git status --short` phải không in gì. Sau khi test đạt, chạy:

```bash
cargo build --release --locked --bin ddd
CYCLE_ID=cycle-new bash run_aglr_research_cycle.sh
```

Lệnh trên thử riêng từng thành phần, chạy ba cấu hình tốt nhất ở 120 giây,
khóa cấu hình rồi chạy đủ 72 instance ở 150 giây. Nếu vượt cổng coverage,
script chạy ba lượt xác nhận. Toàn chu kỳ bị giới hạn ở 6 giờ. Nếu bị ngắt,
chạy lại đúng `CYCLE_ID`, binary và commit để dùng lại kết quả đã có.

Khi hoàn tất, gửi lại đường dẫn thư mục chiến dịch cùng `campaign.txt`,
`aglr_ranking.csv`, `aglr_summary.csv`, `aglr_audit.json` và
`latest_screen.txt`. Nếu có lỗi, gửi thêm `*.stderr.log` của instance liên
quan. Giữ và sao lưu toàn bộ `results/aglr/`; thư mục này không được commit.

## Kết quả hội nghị dùng như thế nào

Dữ liệu gốc nằm trong `results/conferences/`. Không sửa các JSON hoặc CSV trong
thư mục này. Hai file sau giải thích và ghi lại kết quả kiểm tra:

- `results/conferences/README.md`: nguồn dữ liệu và giới hạn sử dụng;
- `results/conferences/conference_audit.json`: số lịch đã kiểm tra và mọi lỗi
  phát hiện được.

Có thể chạy lại kiểm tra bằng lệnh:

```bash
python3 quick_scripts/analyze/summarize_conference.py results/conferences
```

Lệnh này kiểm tra đủ đúng 72 tên instance cho mỗi objective, dựng lại mọi lịch
`ok`, kiểm tra `cost=lb=ub`, rồi tạo lại `summary_conference.csv`. Bốn timeout
của `infsteps180` và 14 timeout của `cont` được giữ nguyên; chúng không được
đổi thành nghiệm tối ưu.

Trong giai đoạn `full`, script tự đưa thư mục này cho auditor. File
`conference_reference_comparison.csv` cho biết chi phí của mỗi nghiệm mới có
khớp với chi phí hội nghị đã kiểm tra hay không. Chế độ `assumed-equivalent`
còn sinh PAR-2 hội nghị và thời gian ghép cặp trên đúng các instance cùng giải
được; chế độ `diagnostic` chỉ dùng coverage và chi phí.

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

Trên VM 8 CPU, dùng hai worker để giữ mỗi vòng trong khoảng 6 giờ:

```bash
SCREEN_PARALLELISM=2 bash run_aglr_experiments.sh screen
```

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
nhận mẫu `results_bigm_<objective>_150s.csv` hoặc
`MILP_BigM_CPLEX_<objective>_150s.csv`. File phải chứa `name`, `status`, `lb`,
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
FULL_TIMEOUT_SECS=150 \
CONFERENCE_RUNTIME_MODE=assumed-equivalent \
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

Lượt này còn tự đối chiếu chi phí của các solver chính xác với kết quả hội nghị
trong `results/conferences/`. Nếu cần đặt dữ liệu ở nơi khác, dùng biến
`CONFERENCE_RESULTS_DIR`; không thay nội dung file để làm cho chi phí khớp.

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

Chạy khi `aglr_audit.json` có `gate.coverage_passed=true`. Trường này cho biết
đã vượt hội nghị. `gate.passed=true` còn yêu cầu đủ mọi baseline, gồm CPLEX;
nó là điều kiện chốt bảng submission.

```bash
bash run_aglr_experiments.sh confirm
```

Script chạy ba lần các instance trên 30 giây và các instance AGLR được/mất so
với baseline. Không chạy lặp toàn bộ 72 instance ở giai đoạn đầu.

## Cổng sử dụng cho submission

Auditor từ chối file thiếu, tên instance thừa/trùng, lịch sai, chi phí sai và
kết quả MILP không có cận khớp. Theo tiêu chí hiện tại, AGLR chỉ qua cổng khi:

- từng objective không thấp hơn kết quả hội nghị: 72/72, 68/72 và 58/72;
- tổng coverage lớn hơn 198, tức có ít nhất 199 optimum được chứng minh;
- đủ MaxSAT-Journal, CSOnet, BigM-Gurobi và BigM-CPLEX;
- không có `panic`, nghiệm sai hoặc lỗi dữ liệu.

Khi nhiều cấu hình cùng đạt coverage, auditor xếp hạng theo PAR-2, sau đó đến
mức tăng mô hình. `aglr_summary.csv` ghi thêm coverage hội nghị, chênh lệch
coverage, PAR-2 hội nghị và chênh lệch PAR-2.

Các file cần giữ để viết bài:

- `aglr_summary.csv`;
- `aglr_ranking.csv`;
- `aglr_audit.json`;
- `conference_reference_comparison.csv` của lượt `full`;
- `confirm_instances.txt`;
- mọi JSON, manifest và log instance trong cùng thư mục chiến dịch.

Báo cáo sau mỗi giai đoạn phải ghi commit, thông tin máy, phiên bản Gurobi/CPLEX,
thư mục kết quả, cấu hình đứng đầu và mọi lỗi trong `aglr_audit.json`.
Dùng mẫu `manuscript/journal/student_experiment_report_template_vi.md`.

Nếu cổng chưa đạt, đọc telemetry rồi chỉ đổi một thành phần. Có thể thử chế độ
rescue tính cả tiến triển mô hình:

```bash
AGLR_RESCUE_PROGRESS=model bash run_aglr_experiments.sh screen
```

Có thể giảm số lần gọi heuristic bằng `AGLR_HEURISTIC_PERIOD` hoặc chỉ gọi khi
khoảng cách cận đạt `AGLR_HEURISTIC_MIN_GAP`. Chỉ thử `BinaryObjective` sau khi
có kiểm thử bảng chân trị và bài nhỏ vét cạn; cờ tương ứng là
`AGLR_USE_OBJECTIVE_BOUND=true`.

`ablate` chạy Control và năm biến thể. Mỗi biến thể chỉ đổi đúng một thành
phần: rescue, chu kỳ heuristic, ngưỡng gap, lọc trùng hoặc giới hạn objective.
`AGLR_FILTER_DUPLICATES=true` bỏ hành động đã mã hóa trước khi tính ngân sách.

Runner ghi `process_exit_code` kể cả khi solver đã ghi JSON. Nếu mã thoát khác
0, kết quả không được tính tối ưu. JSON trước crash được giữ thành
`*.raw.json`. Các lượt screen/promote cũ thiếu thông tin này chỉ dùng để chọn
hướng; không lấy chúng làm bằng chứng rằng chương trình không crash.

Chạy riêng baseline hoặc một cấu hình đã khóa:

```bash
RUN_ID=baseline-new bash run_aglr_round.sh baseline
AGLR_MIN_GROWTH=16 AGLR_FRACTION=0.25 AGLR_MAX_WAIT=5 \
  RUN_ID=candidate-new bash run_aglr_round.sh candidate
```

Mỗi lệnh có giới hạn 6 giờ. `full` chạy tuần tự mọi solver và có thể cần nhiều
vòng 6 giờ; tiếp tục cùng `RUN_ID` để không chạy lại dữ liệu đã xong. Không đổi
commit hoặc binary khi đang chạy. Trên VM, dùng worktree và bản binary riêng
cho mỗi vòng để có thể phát triển mã mà không thay đầu vào của vòng đang chạy.
