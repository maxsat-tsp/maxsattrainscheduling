# Runbook thực nghiệm AGLR

Mốc chính đã được sửa theo camera-ready: **120 giây**, MaxSAT-Default
`(72,68,60)`, tổng 200 optimum. Dùng ba CSV
`results/MaxSAT_Default_RC2_<objective>_120s.csv`. Bộ JSON trong
`results/conferences/` là lượt chạy khác ở 150 giây, chỉ còn dùng để chẩn đoán.
Có thể dùng lại lượt 150 giây bằng cách tạo bảng dẫn xuất ở cutoff 120 giây.
Giữ nguyên dữ liệu gốc và ghi rõ đây không phải một lượt chạy lại.

## Tái sử dụng dữ liệu 150 giây ở cutoff 120 giây

Với cùng cách đo `total_time` theo giây, lịch tối ưu hoàn tất trong 120 giây
được giữ. Lịch hoàn tất sau 120 giây và các ca còn timeout được tính chưa giải
được ở cutoff mới; PAR-2 phạt mỗi ca đó 240 giây. Không đổi panic/segfault
thành timeout. Không chọn kết quả tốt nhất của nhiều lượt rồi gọi là một lượt.

```bash
python3 quick_scripts/analyze/censor_results.py \
  results/conferences results/aglr/reused150-at120/CSOnet-censored \
  --cutoff 120 --pattern 'MaxsatScDefault_{objective}.json'
python3 quick_scripts/analyze/audit_aglr_campaign.py \
  results/aglr/reused150-at120 --timeout 120 \
  --conference-reference results --conference-profile published-csv-120 \
  --conference-runtime-mode assumed-equivalent
```

Script kiểm tra độc lập nghiệm gốc, lưu hash đầu vào và tạo
`censor_manifest.json`. Các ca bị cắt không giữ LB/UB hoặc lịch chỉ có sau
cutoff; nếu không có log tại giây 120 thì gap tại 120 được để là chưa biết.
`--allow-partial` dùng lại những objective đã có, nhưng không biến dữ liệu
thiếu thành timeout hoặc thành kết quả đầy đủ 72 instance.

Bộ JSON 150 giây đã nhập cho kết quả dẫn xuất `(72,68,57)`; PAR-2 là
`0.120001`, `15.240171`, `53.547450` giây. `trackB4/cont` hoàn tất ở
123.462673 giây nên được chuyển thành timeout. Mốc camera-ready `(72,68,60)`
vẫn được giữ riêng làm kết quả đã công bố.

## CPLEX đã cài trên VM

CPLEX Optimization Studio 22.2.0 nằm tại
`~/opt/ibm/ILOG/CPLEX_Studio2220`. Trong môi trường Conda `gurobi`, có cả lệnh
`cplex`, `cpoptimizer` và Python API `cplex`. Python API đã được nâng cấp từ
bản academic bằng `docplex config --upgrade`; thư viện native trùng hash với
bộ cài IBM. Cả CLI và Python đã giải thành công bài 1201 biến, vượt ngưỡng
Community, với objective kiểm tra bằng 1201.

```bash
source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate gurobi
cplex -c quit
python -c 'import cplex; print(cplex.Cplex().get_version())'
```

Script `quick_scripts/setup/download_ibm_academic.py` tải bộ cài bằng tùy chọn
HTTP của cổng IBM. URL có ticket chỉ truyền lúc chạy; không lưu vào Git hoặc
manifest. Manifest bộ cài và log kiểm tra nằm ở `~/installers/` và
`~/projects/experiment-audit/cplex-install/`. Việc cài xong chưa thay thế các
CSV CPLEX cần có lịch được kiểm tra và cận khớp cho bảng submission.

## Trạng thái

AGLR đã được cài trực tiếp trên solver CSOnet. Tên solver mới là
`maxsat_ddd_ladder_aglr`; tên cũ `maxsat_ddd_ladder_sc` vẫn chạy đúng đường
`legacy`. Các kết quả RC2+B+R trước đây chỉ dùng để chẩn đoán và không đi vào
bảng chính.

Một bộ kết quả CSOnet 150 giây đã được nhập nguyên trạng từ commit dữ liệu
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
so với `(72,68,60)` và tổng ít nhất 201, chạy thêm ba lần để xác nhận.

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
khóa cấu hình rồi chạy đủ 72 instance ở 120 giây. Nếu vượt cổng coverage,
script chạy ba lượt xác nhận. Toàn chu kỳ bị giới hạn ở 6 giờ. Nếu bị ngắt,
chạy lại đúng `CYCLE_ID`, binary và commit để dùng lại kết quả đã có.

Khi hoàn tất, gửi lại đường dẫn thư mục chiến dịch cùng `campaign.txt`,
`aglr_ranking.csv`, `aglr_summary.csv`, `aglr_audit.json` và
`latest_screen.txt`. Nếu có lỗi, gửi thêm `*.stderr.log` của instance liên
quan. Giữ và sao lưu toàn bộ `results/aglr/`; thư mục này không được commit.

## Kết quả hội nghị dùng như thế nào

Profile mặc định là `published-csv-120`; các CSV chứa chi phí, cận và thời
gian nhưng không có lịch. Auditor kiểm tra cấu trúc/cận của mốc cũ, đồng thời
vẫn kiểm tra độc lập lịch của mọi lần chạy mới. Không gọi các lịch cũ trong
CSV là đã được kiểm tra độc lập. Các đoạn tiếp theo mô tả riêng bộ JSON 150
giây được giữ làm mốc chi phí phụ.

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
FULL_TIMEOUT_SECS=120 \
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

- từng objective không thấp hơn kết quả đã công bố: 72/72, 68/72 và 60/72;
- tổng coverage lớn hơn 200, tức có ít nhất 201 optimum được chứng minh;
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
Các biến thể độc lập có thể chạy song song tối đa hai nhánh trên VM 8 CPU:

```bash
SCREEN_PARALLELISM=2 ABLATE_PARALLELISM=2 \
  bash run_aglr_experiments.sh ablate
```

Mỗi biến thể vẫn ghi thư mục và manifest riêng; không chạy song song ở giai
đoạn `full` để giữ thời gian so sánh công bằng.

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

## Thử cách đưa các điều kiện chi phí vào SAT

AGLR full đầu tiên đạt `(72,67,57)`, chưa vượt mốc hội nghị `(72,68,60)`.
Vòng kế tiếp dùng refinement CSOnet và chỉ thay cách gửi điều kiện chi phí:
`legacy` thêm 20 điều kiện mỗi lần, `full` gửi hết ngay, `geometric` tăng gấp
đôi từ 20. Cờ trực tiếp là `--maxsat-ladder-sc-assumptions`.

```bash
RUN_ID=core-screen-v1 timeout -k 30 21600 \
  bash run_maxsat_core_experiments.sh screen
RUN_ID=core-promote-v1 timeout -k 30 21600 \
  bash run_maxsat_core_experiments.sh promote
MAXSATDDD_ASSUMPTIONS=full RUN_ID=core-full-v1 timeout -k 30 21600 \
  bash run_maxsat_core_experiments.sh candidate
```

Lệnh thứ ba là ví dụ: chỉ chạy `candidate` sau khi đã chọn `full` hoặc
`geometric` từ bảng 120 giây. `screen` chạy 24 instance phát triển, ba
objective, timeout 30 giây, tối đa hai worker. `promote` chạy hai cấu hình thử
ở 120 giây; `candidate` chạy đủ 72 instance. Hai giai đoạn cuối chạy tuần tự.
Không so trực tiếp coverage 30 giây với mốc hội nghị 120 giây để kết luận thắng.

Kết quả nằm tại `results/aglr/<RUN_ID>/aglr_summary.csv`. Cột `assumptions`
cho biết phương án đã thử. Các thư mục `Core-*` là lượt phát triển; tag
`AGLR` trong mode `candidate` giữ tương thích với cổng đánh giá hiện có.
Manifest ghi rõ policy `legacy`, vì lượt này giữ refinement CSOnet.

Một phép thử tiếp theo chỉ thay cách biểu diễn chi phí. Mặc định, mã tạo thêm
các mức chi phí nguyên ở giữa hai mức gần nhau, dù DDD chưa cần dùng chúng.
Cờ `--maxsat-ladder-sc-sparse-costs true` giữ các mức thực sự được DDD đưa
vào. Ví dụ, khi lần lượt xuất hiện chi phí 3 và 7, có thể biểu diễn bằng hai
trọng số 3 và 4 thay vì bảy trọng số 1. Lựa chọn mức 7 vẫn phải trả đủ 7.

```bash
EXPERIMENT_SET=costs RUN_ID=cost-screen-v2 timeout -k 30 21600 \
  bash run_maxsat_core_experiments.sh screen
EXPERIMENT_SET=costs RUN_ID=cost-promote-v2 timeout -k 30 21600 \
  bash run_maxsat_core_experiments.sh promote
CORE_VARIANT=sparse RUN_ID=cost-full-v2 timeout -k 30 21600 \
  bash run_maxsat_core_experiments.sh candidate
```

Lượt này dùng cách gửi điều kiện `legacy` và refinement CSOnet để đo riêng
biểu diễn chi phí. Không kết hợp với `full`/`geometric` trước khi có đối chứng.
Trường `maxsat_cost_terms` đếm số hạng tử chi phí đã sinh. Tính đúng đắn đã
được kiểm thử trên mọi tổ hợp của các mức `[7,3,11,5,7]` với cận từ 0 đến 12,
cùng các bài lịch tàu nhỏ vét cạn. Hiệu năng vẫn cần thực nghiệm.

Để máy tự chạy một vòng tối đa 6 giờ:

```bash
EXPERIMENT_SET=costs CYCLE_ID=cost-cycle-v2 \
  bash run_maxsat_core_cycle.sh
```

Script chạy screen rồi promote. Chỉ khi một cấu hình giữ được coverage
`(24,22,20)` trên tập phát triển ở 120 giây, script mới chạy cấu hình đó trên
72 instance. Nếu full vượt cổng coverage hội nghị, script chạy ba lần các
instance cần xác nhận. Quyết định chọn cấu hình được ghi trong
`core_selection.json`; tuyệt đối không ghép các cấu hình theo từng instance.
Nếu hết 6 giờ, chạy lại với cùng `CYCLE_ID`, commit và binary để dùng lại các
lượt đã xong. Vượt cổng hội nghị vẫn cần đối chiếu đủ baseline trước khi tuyên
bố vượt SOTA.

Auditor phân biệt hai mốc: `gate.coverage_passed` kiểm tra mốc hội nghị;
`gate.baseline_comparison_passed` kiểm tra kết quả có vượt đủ bốn baseline
hay không. Phép so sánh cuối ưu tiên tổng coverage, rồi PAR-2 nếu coverage
bằng nhau, đúng tiêu chí đã chọn. Ví dụ tổng 201 vượt mốc hội nghị 200 nhưng
vẫn thua Big-M Gurobi nếu baseline đó có 206. `gate.passed` yêu cầu cả hai
mốc đều đạt và không có lỗi audit. Không dùng việc có đủ file baseline thay
cho việc vượt kết quả baseline.

Vòng `cost_v2` đã cho kết quả promote `(24,22,19)` với cách sparse, nên
script đã dừng trước full. Đây là hành vi bắt buộc: không chạy 72 instance
khi cấu hình đã mất coverage phát triển. Kết quả giữ trong
`results/sat_research/cost_v2_20261105/`.

Theo yêu cầu tái sử dụng kết quả hội nghị, auditor có cờ
`--reuse-published-baselines results`, dùng kèm cutoff 120 và
`--conference-runtime-mode assumed-equivalent`. Cờ này giữ metadata rằng
lịch cũ được báo cáo hợp lệ trong thí nghiệm công bố, còn việc kiểm tra lại
chỉ bao gồm tên, chi phí, cận và thời gian. Các lịch mới vẫn được kiểm tra
độc lập. Khi đã có kết quả mới cho một baseline/objective, auditor dùng toàn
bộ kết quả mới của objective đó.

Hiện có hai chi phí CPLEX mâu thuẫn với lịch hợp lệ đã kiểm tra; xem
`manuscript/journal/reviews/published_baselines_20261105/README.md`.
Auditor báo lỗi ở bảng tham chiếu và giữ cổng cuối chưa đạt cho đến khi
hai trường hợp này được xử lý. Không sửa trực tiếp CSV gốc.

## Phép thử thứ tự nhất quán của một cặp xung đột

Lượt tiếp theo giữ một biến thứ tự cho mỗi cặp lượt chiếm tài nguyên đã
phát hiện xung đột. Nếu SAT chọn lượt A đi trước lượt B, những ràng buộc
ở các mốc sau của cùng cặp sẽ cùng dùng quyết định đó. Mỗi cặp chỉ có một
biến, được tạo khi xuất hiện xung đột đầu tiên. Cờ là
`--maxsat-ladder-sc-resource-orders true`; mặc định tắt.

```bash
EXPERIMENT_SET=orders CYCLE_ID=orders-cycle-v3 \
  bash run_maxsat_core_cycle.sh
```

Đối chứng là CSOnet. Lượt này giữ cách gửi điều kiện `legacy`, biểu diễn chi
phí cũ và policy refinement `legacy`; không kết hợp thêm thay đổi khác.
Theo dõi `maxsat_resource_order_pairs`, `maxsat_resource_order_rows`, coverage,
PAR-2 và kích thước mô hình. Tính đúng đắn được kiểm tra bằng bảng chân trị,
lịch khả thi theo cả hai thứ tự, và so với vét cạn trên bài nhỏ. Bộ kiểm thử
Linux có 31 tests. Kết quả thực nghiệm được ghi ngay dưới đây.

Kết quả orders `be60148` đã được chạy full: `(72,68,59)`, chưa vượt mốc
`(72,68,60)`. Cấu hình giữ coverage `cont` của CSOnet chạy lại,
nhưng vẫn thiếu một instance so với dữ liệu hội nghị; không chạy xác nhận.
Raw results và danh sách timeout được lưu trong
`results/sat_research/orders_v3_20261105/`.

Vòng kết hợp orders với sparse costs cũng đã chạy full ở commit `7a1aa6d`.
Kết quả vẫn là `(72,68,59)`; mọi kết quả qua audit. Dữ liệu ở
`results/sat_research/hybrid_v4_20261105/`. Chưa chọn cấu hình này làm phương
pháp cuối và chưa đưa số liệu vào Abstract, Results hoặc Conclusion.

## Phép thử loại vòng thứ tự giữa ba lượt

Chỉ thêm tính bắc cầu khi đã có đủ ba biến thứ tự. Với `i < j < k`, thêm
`(!p_ij OR !p_jk OR p_ik)` và `(p_ij OR p_jk OR !p_ik)`. Hai mệnh đề loại
hai cách định hướng tạo vòng. Không tạo thêm biến cặp; xét số hiệu lượt thứ
ba theo thứ tự tăng dần. Đây là điều kiện cho bộ ba, chưa loại mọi vòng dài.

```bash
EXPERIMENT_SET=transitivity CYCLE_ID=orders-transitive-v5 \
  bash run_maxsat_core_cycle.sh
```

Screen đối chứng `orders` với `orders-transitive`; promote chỉ kiểm tra
cách mới. Giữ cây chi phí cũ, giả định chi phí `legacy` và refinement
`legacy`. Chỉ chạy full khi promote giữ được `(24,22,20)`. Theo dõi thêm
`maxsat_resource_order_triangles`: mỗi bộ ba tương ứng hai mệnh đề.
Mặc định CLI không thay đổi. Cờ mới là
`--maxsat-ladder-sc-order-transitivity true`, cần bật resource orders.

Đã qua 35 kiểm thử `cargo test --lib -- --test-threads=1` trên Linux,
31 kiểm thử Python, kiểm tra Bash và build release. Kiểm thử mới gồm đủ
tám định hướng của bộ ba, không thêm trùng, bảo toàn các lịch ba lượt khả
thi và optimum vét cạn bài ba tàu ở ba objective. Hướng dẫn LaTeX đã biên
dịch lại. Kiểm thử CLI cũ `samescore_all_instances` cần
`instances/Instance3.xml`, `Instance4.xml`, `Instance5.xml`; các file này
không có trong checkout, nên lượt `cargo test --bin ddd` còn lỗi thiếu
fixture. Không gọi đây là kết quả toàn bộ test suite đã qua.
