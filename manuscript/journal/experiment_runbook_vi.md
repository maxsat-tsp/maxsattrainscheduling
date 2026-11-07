# Runbook thực nghiệm AGLR

## Quyết định backend hiện tại

CaDiCaL đã được chạy và audit trong các lượt trước, gồm V28. Các kết quả
đó chỉ là hồ sơ lịch sử. Từ bây giờ không chạy lại CaDiCaL, không khởi động
dịch vụ CaDiCaL và không lập thêm bảng so sánh backend. Các script/lệnh
CaDiCaL bên dưới chỉ để tái tạo lịch sử; sinh viên phải dùng MiniSAT cho
mọi lượt mới.

Mốc chính đã được sửa theo camera-ready: **120 giây**, MaxSAT-Default
`(72,68,60)`, tổng 200 optimum. Dùng ba CSV
`results/MaxSAT_Default_RC2_<objective>_120s.csv`. Bộ JSON trong
`results/conferences/` là lượt chạy khác ở 150 giây, chỉ còn dùng để chẩn đoán.
Có thể dùng lại lượt 150 giây bằng cách tạo bảng dẫn xuất ở cutoff 120 giây.
Giữ nguyên dữ liệu gốc và ghi rõ đây không phải một lượt chạy lại.

## Vòng kéo dài V17: đã dừng sau 600 giây

Ngày 07-11-2026, V17 được chạy lại bằng MiniSAT trên đúng 13 cặp chưa giải
ở cutoff 300 giây (4 `infsteps180`, 9 `cont`) với cutoff 600 giây. Cả 13
cặp đều timeout hợp lệ, không tăng coverage; kết quả kiểm toán nằm ở
`results/sat_research/v17_extended600_20261107/`. Không chạy lại cutoff cao
hơn cho cùng cấu hình. Nếu thử tiếp, phải thay một thành phần thuật toán,
ghi test và telemetry trước khi chạy; không khởi động CaDiCaL.

V29 đã thử verified objective bound cùng transitivity của V17 và không giải
thêm ca nào. V30 đã cố định tie-break của các giả định RC2 cùng trọng số để
loại phụ thuộc vào thứ tự `HashMap`; smoke test tái lập được, nhưng hard set
vẫn 0/13. Hai archive nằm trong `results/sat_research/`; V30 giữ trong mã
nguồn vì giúp các lượt sau tái lập, còn V29 chỉ là ablation thất bại.

## Đối chứng MiniSAT và CaDiCaL: đã hoàn tất

**Đã kiểm toán đủ 186/186 ca**, kết thúc lúc 22:33:58 ngày 06/11/2026,
giờ Việt Nam. MiniSAT xong 93/93, CaDiCaL xong 93/93. Giữ nguyên 174 ca
hợp lệ từ lượt trước, chạy bổ sung 12 ca sau khi sửa timeout CaDiCaL.
Ca lỗi mã 124 của lượt cũ được giữ trong lịch sử, không tính là kết quả hợp lệ.
Bản chụp cuối ở `results/sat_research/backend_comparison_20261106/complete_186/`.

Lượt này chạy hai nhánh backend cùng lúc để chọn hướng tốt hơn.
Mỗi nhánh chạy ba phương pháp: Orders-Transitive, CSOnet và MaxSAT-Journal,
trên cùng 31 cặp instance--objective ở 300 giây. Tổng là **186 ca SAT**.
Chỉ chạy phần còn thiếu; nhập nguyên byte các ca SAT đã hoàn tất và đã audit.
Gurobi/CPLEX không phụ thuộc SAT backend nên không chạy lại trong vòng này.

VM có 4 lõi vật lý, 8 vCPU và khoảng 16 GB RAM. Phân bổ:

| Nhánh | CPU logic | Lõi vật lý | Giới hạn RAM mỗi ca |
|---|---|---|---|
| MiniSAT | 0,1,4,5 | 0,1 | 6.000.000 KB |
| CaDiCaL | 2,3,6,7 | 2,3 | 6.000.000 KB |

Hai nhánh không chia sẻ lõi vật lý hoặc hai luồng của cùng một lõi. Mỗi
nhánh chạy một ca tại một thời điểm. Các ca mới của cả hai nhánh dùng cùng
binary từ commit `4a43a9c` trong V13. V14 dùng bản sửa timeout ở `1908b22`
cho các ca còn thiếu. Giữ riêng commit, binary hash và điều kiện chạy
của các ca cũ được nhập; không đổi nhãn chúng thành ca chạy mới.

```bash
BIN=/home/tuyenkv/projects/deadline-v14/maxsattrainscheduling/target/release/ddd \
MINISAT_REFERENCE=/home/tuyenkv/projects/core-v9/maxsattrainscheduling/results/aglr/extended300-b6a4370-20261106 \
CADICAL_REFERENCE=/home/tuyenkv/projects/cadical-v12/maxsattrainscheduling/results/aglr/cadical300-v12-4a43a9c \
SOLVER_MANIFEST=/home/tuyenkv/projects/deadline-v14/maxsattrainscheduling/results/aglr/deadline-v14-build/manifest.json \
COMPLETED_BACKEND_TRIAL=/home/tuyenkv/projects/backends-v13/maxsattrainscheduling/results/aglr/backends300-v13-fabcc5a \
RUN_ID=backends300-v14-1908b22 bash run_sat_backend_comparison.sh
```

Kích hoạt môi trường Gurobi trước. Chạy trong worktree
`~/projects/deadline-v14/maxsattrainscheduling`. Một vòng tối đa 6 giờ;
giữ cùng RUN_ID để tiếp tục. Hai thư mục reference đã dừng và được giữ
nguyên. Không chạy đồng thời lệnh này và dịch vụ đang thực hiện cùng RUN_ID.

Đọc `backend_comparison.json` và `backend_comparison.csv`. Mỗi dòng so đúng
cùng phương pháp, objective và các instance đã hoàn tất ở **cả hai backend**.
Ưu tiên số optimum, sau đó PAR-2. `preferred_backend` chỉ áp dụng trên mẫu
đã so sánh; `complete_for_objective=false` nghĩa là vẫn thiếu ca của nhóm đó.
`complete=true` chỉ có nghĩa đủ 186 ca nhóm khó, không phải full dataset.

`backend_parallel_same_binary.csv` chỉ dùng những ca mới đã chạy với cùng
binary trong chế độ song song. Các ca cũ có thời gian tuần tự được ghi riêng
nguồn trong `manifest.json` và `measurement.json`; không coi mọi thời gian là
cùng điều kiện. Sau khi chọn được backend và phương pháp tốt hơn, chạy xác
nhận tuần tự các ca quyết định trước khi chốt runtime cho bài báo.

Kiểm toán lại bất kỳ lúc nào bằng bản auditor chỉ đọc của V14. Không sửa
worktree đang chạy để cập nhật công cụ:

```bash
python3 quick_scripts/analyze/compare_sat_backends.py audit \
  results/aglr/backends300-v14-1908b22
```

Nếu một worker lỗi, cả vòng dừng và lưu `failure.json`; kiểm tra thêm
`minisat.log`/`cadical.log`. Lịch sai, cận mâu thuẫn và dữ liệu bị sửa không
được bỏ qua để chạy tiếp. Không cần chạy lại những ca đã hoàn tất hợp lệ.

## V16 đã hoàn tất: thu gọn core trên 15 ca chưa giải

Trên đủ 26 ca cont của nhóm khó, MiniSAT chứng minh tối ưu nhiều hơn:
Orders-Transitive 15 so với 14, CSOnet 15 so với 14, Journal 16 so với 12.
Vì vậy bước thử tiếp theo giữ MiniSAT và mô hình bộ ba, chỉ thay bước thu
gọn core. Core là một tập điều kiện SAT đã chứng minh không thể đồng thời
thỏa. Thử bỏ một điều kiện; chỉ chấp nhận nếu SAT chứng minh tập còn lại vẫn
mâu thuẫn. Mỗi core được thử thêm tối đa bốn lần.

V15 chỉ giới hạn số lần thử. Nó hoàn tất hai timeout hợp lệ rồi ca thứ ba
bị ngắt bên ngoài, mã 124. Không dùng ca lỗi; giữ dữ liệu ở
`results/sat_research/core_minimization_v15_20261106/stopped_2/`.
V16 sửa hai điểm cần thiết để tiếp tục thử:

- MiniSAT tự dừng truy vấn đang chạy khi hết 300 giây của instance; trả
  `timeout`, không coi là vô nghiệm.
- Mỗi lần thử thu gọn core có ngân sách riêng: 100 hoặc 1.000 xung đột SAT.
  Hết ngân sách mà chưa kết luận thì giữ core đã chứng minh trước đó.
  Đây là giới hạn công việc tìm kiếm, không phải số mili giây. Lời gọi SAT
  chính không chịu ngân sách này.

Script `quick_scripts/analyze/targeted_core_minimization.py` đọc 93 ca MiniSAT
đã hoàn tất, chọn đúng **4 ca infsteps180 và 11 ca cont** chưa chứng minh tối
ưu của phương án bộ ba. Không chọn lại các ca đã giải hoặc chạy lại baseline.
Hai cấu hình V16 chỉ khác `core_minimize_conflicts=100|1000`, đều có
`core_minimize_checks=4`. Lịch mới được kiểm tra độc lập và đối chiếu chi phí
tối ưu với reference nếu có.

Lệnh cho cấu hình 1.000 trên VM, trong worktree
`~/projects/limited-core-v16/maxsattrainscheduling`, sau khi kích hoạt môi
trường Gurobi:

```bash
taskset -c 0,1,4,5 python3 quick_scripts/analyze/targeted_core_minimization.py \
  --reference /home/tuyenkv/projects/deadline-v14/maxsattrainscheduling/results/aglr/backends300-v14-1908b22 \
  --binary ./target/release/ddd \
  --build-manifest results/aglr/limited-core-v16-build/manifest.json \
  --core-conflicts 1000 \
  --results results/aglr/core-v16-conflicts1000-unresolved300 \
  --ram-kb 6000000 --round-seconds 21600
```

Với cấu hình 100, đổi `--core-conflicts` thành `100`, thư mục kết quả thành
`core-v16-conflicts100-unresolved300`, CPU thành `2,3,6,7`. Hai cấu hình
dùng cùng binary từ `57aa220`, mỗi cấu hình có 2 lõi vật lý riêng và tối đa
6 giờ. Không chạy thêm lệnh nếu dịch vụ tương ứng đang hoạt động:

```bash
systemctl status maxsat-core-v16-conflicts1000.service --no-pager
systemctl status maxsat-core-v16-conflicts100.service --no-pager
```

Trước khi khởi chạy, 54 test Rust và 69 test Python đã đạt trên VM. Ba
cấu hình kiểm tra nhỏ đều có optimum 5526; ca khó ở hạn 2 giây trả timeout
đúng, mã thoát 0. Không sửa mã hoặc build lại binary của worktree đang chạy.
Muốn tiếp tục sau gián đoạn, dùng lại đúng lệnh và thư mục kết quả; script
từ chối nếu binary, mã nguồn, tham số hoặc dataset thay đổi.

Đọc `core_minimization_audit.json`: `completed_runs` là số đã xong;
`newly_solved` liệt kê ca mới chứng minh tối ưu. Kiểm tra cả `failure.json`
và trạng thái dịch vụ: báo cáo viết sau ca trước không chứng minh ca đang
chạy sau đó đã thành công. Khi lỗi, giữ dữ liệu và dừng tìm nguyên nhân.

Trong JSON từng ca, theo dõi số điều kiện bỏ được, thời gian thu gọn core,
`maxsat_native_budgeted_calls` và `maxsat_native_inconclusive_calls`.
Hai trường native vẫn được ghi khi hết timeout. Thời gian thu gọn đã nằm
trong thời gian SAT, không cộng hai trường để tính tổng.

Lượt này chưa kiểm tra các ca đã giải trước đây, nên chưa thể kết luận không
mất ca cũ. Nếu có cải thiện, chọn một cấu hình, chạy xác nhận ba lần các ca
mới và kiểm tra hồi quy trước khi đánh giá full. Không ghép ca tốt nhất
của hai ngân sách thành kết quả của một cấu hình.

Công cụ sau tạo bản chụp chỉ gồm các ca đã hoàn tất; không dừng dịch vụ,
không lấy JSON còn đang viết. Gọi từ một bản mã riêng nếu worktree thí
nghiệm đang khóa ở commit cũ:

```bash
python3 quick_scripts/analyze/audit_targeted_core_minimization.py snapshot \
  results/aglr/core-v16-conflicts1000-unresolved300 /tmp/core-v16-c1000.tar.gz
```

Sau khi giải nén vào thư mục mới, kiểm tra độc lập trên máy local:

```bash
python3 quick_scripts/analyze/audit_targeted_core_minimization.py audit \
  /thu/muc/ban-chup-v16 --reference /thu/muc/doi-chung-186 \
  > /tmp/core-v16-independent-audit.json
```

Thư mục đối chứng phải là bản gốc V14, giữ nguyên manifest và report để
khớp hash đã khóa. Auditor kiểm tra hash bản chụp, nguồn của từng ca, tham
số, lịch, chi phí, cận và dựng lại summary. `audit_passed=true` chỉ xác
nhận các ca trong bản chụp; đọc cả `complete` để biết đã đủ 15 ca chưa.
Nếu có lỗi dịch vụ được lưu trong `failure.json`, auditor trả mã lỗi dù
các ca trước đó hợp lệ. Sau khi thêm công cụ chụp, kiểm toán và xác nhận,
82 test Python đạt trên VM; số test lúc khởi chạy V16 vẫn là 69 như manifest
ghi nhận.

### Xác nhận V16 đã hoàn tất

Dịch vụ `maxsat-core-v16-confirm-v2.service` đã hoàn tất sáu lượt: hai ca
giải thêm, mỗi ca ba lần, đều chứng minh lại đúng optimum. Công cụ chọn
ngân sách 100 theo coverage rồi PAR-2 sau khi kiểm toán đủ hai lượt 15/15.
Các lần xác nhận chạy tuần tự, cùng binary, timeout 300 giây và 6.000.000 KB
RAM. Median là 182,25 giây cho `origB11/cont`, 5,67 giây cho
`stationB12/cont`. Sáu JSON đã được tải về và kiểm toán độc lập trong
`results/sat_research/limited_core_v16_20261106/confirmation_complete/`.

```bash
systemctl status maxsat-core-v16-confirm-v2.service --no-pager
journalctl -u maxsat-core-v16-confirm-v2.service -n 25 --no-pager
```

Worktree riêng: `~/projects/limited-core-confirm-v16/maxsattrainscheduling`,
runner `cfdcccc`, binary giữ nguyên từ `57aa220`. Không build lại solver.
Kết quả ở `results/aglr/core-v16-confirm-selected/confirmation_audit.json`.
`confirmed=true` nghĩa là mọi ca đã chọn đều được chứng minh cùng chi phí
ở cả ba lần. Nếu có timeout thì giữ kết quả đó và báo chưa xác nhận được;
không chạy lặp để chọn ba lần tốt nhất. Nếu có nghiệm sai hoặc chi phí tối
ưu mâu thuẫn, dịch vụ dừng. Vẫn cần kiểm tra hồi quy và full; bước xác nhận
này không tự cho phép kết luận thắng SOTA.

## V17: đã hoàn tất 216 cặp, đạt 203 optimum

Mã `43cae76` bổ sung core exhaustion: nếu nhóm điều kiện đã biết phải vi
phạm ít nhất một phần tử, thử chứng minh phải vi phạm ít nhất hai, ba phần
tử ngay trên bộ đếm của nhóm đó. Chỉ tăng cận sau một chứng minh UNSAT mới;
SAT hoặc hết ngân sách thì giữ mức đã chứng minh. Đây là bước tối ưu RC2
tham khảo [tài liệu PySAT](https://pysathq.github.io/docs/html/api/examples/rc2.html#pysat.examples.rc2.RC2.exhaust_core).
Ví dụ và công thức bảo toàn chi phí ở cuối hướng dẫn sinh viên, bản 5.18.

Cờ `--maxsat-ladder-sc-core-exhaust-checks` mặc định 0. V17 đặt 4; mỗi lời
gọi thêm dùng ngân sách xung đột của cấu hình V16 được chọn. CLI yêu cầu
MiniSAT, thu gọn core đang bật và ngân sách xung đột dương. Mặc định CSOnet
vẫn giữ nguyên. Biến Bash tương ứng là `MAXSATDDD_CORE_EXHAUST_CHECKS`.

Cả hai lượt V16 đã hoàn tất. Ngân sách 100 được chọn theo PAR-2 và hai ca
giải thêm đã lặp lại thành công đủ ba lần. Hồi quy giữ 15/16 ca cũ, mất
`stationA9/cont`. Trên 31 cặp khó, V16 đạt 17 optimum, bằng Journal; chưa
vượt baseline mạnh nhất.

Lượt chuẩn bị `maxsat-core-exhaust-v17.service` đã qua **56 test Rust**,
85 test Python, ba lịch nhỏ có optimum 5526 và kiểm tra timeout. Nó dừng
ở cổng hồi quy, trước khi chạy V17 trên ca khó. Dữ liệu hồi quy ở
`results/aglr/core-v16-regression-selected/` trong worktree chuẩn bị.

Runner `438129f` bổ sung kiểm toán hồi quy và đưa ca mất trở lại danh sách
cần thử. Nó đã qua **90 test Python trên VM**. Lượt hiện tại là
`maxsat-core-exhaust-v17-followup.service`, dùng lại binary đã kiểm tra của
solver `43cae76`; hash `ca8fef89fb275803ec1934950f509dab2e4e1bf42321a01e7e9d2df18d9f0a88`.
Worktree: `~/projects/core-exhaust-v17-followup/maxsattrainscheduling`.
Kết quả: `results/aglr/core-exhaust-v17-followup300/`.

Lượt đầu gồm **14 cặp**: bốn `infsteps180`, mười `cont`, gồm cả
`stationA9`. Lượt này đã xong: khôi phục `stationA9/cont` ở 45,46 giây;
13 ca còn lại timeout. Cả 14 JSON đã qua kiểm toán độc lập. Giới hạn
300 giây mỗi ca, 6.000.000 KB RAM; cả vòng tối đa khoảng 6 giờ. Mọi ca
được chạy một lần. Baseline dùng lại, không chạy thêm trong vòng này.

```bash
systemctl status maxsat-core-exhaust-v17-followup.service --no-pager
journalctl -u maxsat-core-exhaust-v17-followup.service -n 30 --no-pager
```

Lệnh tái tạo hoặc tiếp tục sau gián đoạn, khi dịch vụ đã dừng:

```bash
taskset -c 0,1,4,5 python3 quick_scripts/analyze/targeted_core_minimization.py \
  --reference /home/tuyenkv/projects/deadline-v14/maxsattrainscheduling/results/aglr/backends300-v14-1908b22 \
  --previous-trials \
    /home/tuyenkv/projects/limited-core-v16/maxsattrainscheduling/results/aglr/core-v16-conflicts1000-unresolved300 \
    /home/tuyenkv/projects/limited-core-v16/maxsattrainscheduling/results/aglr/core-v16-conflicts100-unresolved300 \
  --regression-reference /home/tuyenkv/projects/core-exhaust-v17/maxsattrainscheduling/results/aglr/core-v16-regression-selected \
  --binary /home/tuyenkv/projects/core-exhaust-v17/maxsattrainscheduling/target/release/ddd \
  --build-manifest /home/tuyenkv/projects/core-exhaust-v17/maxsattrainscheduling/results/aglr/core-exhaust-v17-build/manifest.json \
  --core-exhaust-checks 4 \
  --results results/aglr/core-exhaust-v17-followup300 \
  --ram-kb 6000000 --round-seconds 21600
```

Script giữ cấu hình V16 đã chọn, chỉ bật thêm core exhaustion. Nó kiểm
toán lại đủ 16 ca hồi quy, xác minh mọi lịch và chi phí, rồi hợp các ca
timeout cũ với các ca bị mất. Hash của lượt nguồn, hồi quy, binary và tham
số được khóa để tiếp tục an toàn. Không ghép các ca tốt nhất của nhiều
cấu hình. Nghiệm sai, chi phí mâu thuẫn hoặc dữ liệu thiếu sẽ làm dừng
vòng chạy; timeout hợp lệ được giữ làm kết quả chưa giải được.

Khi audit bản chụp V17, thêm `--previous-trials` với hai thư mục dữ liệu
V16 đã giải nén và `--regression-reference` với bản hồi quy đã giải nén.
Auditor kiểm tra lại hash, cách chọn cấu hình và đầy đủ các ca bị mất.
Báo cáo sau thực nghiệm là `core-exhaust-v17-followup-independent-audit.json`
ở `results/aglr/`. V17 đã được đánh giá đủ 31 ca khó (18 optimum), sau đó
đủ 216 cặp (203 optimum: 72,68,63). Dữ liệu gốc ở `complete_31/` và
`full_216/` trong `results/sat_research/core_exhaustion_v17_20261107/`.
Lượt full giữ nguyên 31 ca và chỉ chạy thêm 185. Chưa đạt cổng toàn bộ SOTA.

Sau khi giải nén mỗi `raw_snapshot.tar.gz` vào một thư mục mới, kiểm toán:

```bash
python3 results/sat_research/core_exhaustion_v17_20261107/audit_completion.py \
  /thu/muc/giai/nen/31-ca --parent /thu/muc/giai/nen/14-ca \
  --reference /thu/muc/giai/nen/186-ca-backend
python3 results/sat_research/core_exhaustion_v17_20261107/audit_completion.py \
  /thu/muc/giai/nen/216-ca --parent /thu/muc/giai/nen/31-ca \
  --reference /thu/muc/giai/nen/186-ca-backend
```

## V18: đã xong 13 ca, không giải thêm

Nguồn `ca96ae5` thêm cờ `--maxsat-ladder-sc-order-cycle-cuts true`, mặc định
false. Cờ yêu cầu `resource_orders=true`. Thuật toán chỉ dùng các biến thứ
tự đã có; sau một model SAT đầy đủ, nếu các hướng được chọn tạo chu trình
có tổng thời gian dương thì thêm một mệnh đề loại tổ hợp đó. Chu trình
thời gian 0 vẫn được giữ. Cạnh thứ tự dùng thời điểm rời thật của lần đi
qua, tức thời điểm vào lần kế tiếp nếu chưa phải lần cuối.

Dịch vụ `maxsat-order-cycles-v18-v3.service` bắt đầu lúc 08:18:58 ngày 07/11,
giờ Việt Nam. Worktree `~/projects/order-cycles-v18/maxsattrainscheduling`.
Controller giữ nguyên binary V17 trong worktree cũ, kiểm thử Rust/Python,
build release mới rồi kiểm tra optimum 5526 và timeout native trước thí nghiệm.
Tối đa 6 giờ gồm cả kiểm thử/build; 300 giây và 6.000.000 KB mỗi ca, chạy
lần lượt trên nhóm CPU `0,1,4,5`.

```bash
systemctl status maxsat-order-cycles-v18-v3.service --no-pager
journalctl -u maxsat-order-cycles-v18-v3.service -n 30 --no-pager
```

Lệnh tái tạo/tiếp tục chỉ dùng khi không còn dịch vụ đang chạy vào cùng
thư mục. Cần kích hoạt môi trường Gurobi và build từ cùng commit đã ghi:

```bash
taskset -c 0,1,4,5 python3 quick_scripts/analyze/targeted_order_cycles.py run \
  --reference /home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216 \
  --binary ./target/release/ddd \
  --build-manifest results/aglr/order-cycles-v18-build/manifest.json \
  --results results/aglr/order-cycles-v18-unresolved300 --round-seconds 21000
python3 quick_scripts/analyze/targeted_order_cycles.py audit \
  --reference /home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216 \
  --results results/aglr/order-cycles-v18-unresolved300
```

Runner kiểm tra lại đủ 216 ca nguồn, chọn đúng 13 ca chưa chứng minh tối ưu,
khóa hash của từng JSON nguồn, binary, commit, dependency, dữ liệu và tham
số. Resume chỉ dùng lại ca đã xong khi toàn bộ cấu hình khớp. Dữ liệu đầu
ra là `order_cycles_audit.json`, `summary.csv` và các JSON/log từng ca.
Đọc cả `failure.json` nếu có; báo cáo `complete=false` chưa phải kết quả cuối.
Theo dõi `maxsat_order_cycle_checks`, `maxsat_order_cycles_blocked` và
`maxsat_order_cycle_time` để biết cơ chế có hoạt động và tốn bao lâu.

`newly_solved` chỉ nói về 13 ca thử. Có ca mới thì xác nhận ba lần và chạy
hồi quy các ca V17 đã giải trước khi tính coverage full của V18. V18 đã hoàn tất 13/13, tất cả timeout hợp lệ. Dữ liệu ở
`results/sat_research/order_cycles_v18_20261107/complete_13/`. Không ghép kết quả tốt nhất của
V17 và V18 thành một solver.

## V19: đã xong 13 ca, không giải thêm

Mã `20e24a9`, cờ `--maxsat-ladder-sc-extract-initial-cost true`, mặc định
false. Tại mỗi lần đi qua, tính chi phí ở thời điểm sớm nhất đã truyền
dọc tuyến. Tổng này là phần chắc chắn phải trả; cộng một lần vào LB và
chỉ mã hóa phần tăng thêm. Khi dùng giới hạn objective, trừ cùng phần
bắt buộc khỏi UB trước khi giới hạn phần chi phí còn lại. Công thức và
ví dụ số nằm trong hướng dẫn sinh viên.

Worktree riêng `~/projects/initial-cost-v19/maxsattrainscheduling`, dịch vụ
`maxsat-initial-cost-v19.service`. Controller chờ V18 kết thúc và kiểm toán
lại đủ 13 ca. Chỉ tiếp tục nếu V18 không có ca mới. Nếu có ca mới, ghi quyết
định giữ để xác nhận vào `initial-cost-v19-decision.json` rồi kết thúc;
không chạy một cải tiến mới trước khi xử lý kết quả tốt hơn.

Sau điều kiện trên, chạy toàn bộ test Rust/Python, build release, kiểm tra
optimum 5526 trên `origA1/cont` khi bật/tắt tách chi phí, kiểm tra phần
chi phí ban đầu tương ứng 4799/0, và kiểm tra timeout native. Chỉ khi tất
cả đạt mới chạy 13 ca V17 chưa giải ở 300 giây. Biến thứ tự, core và các
tham số V17 giữ nguyên; không bật chu trình V18 trong phép thử này.

```bash
systemctl status maxsat-initial-cost-v19.service --no-pager
journalctl -u maxsat-initial-cost-v19.service -n 30 --no-pager
```

Lệnh chạy riêng khi không còn dịch vụ ghi vào cùng thư mục:

```bash
taskset -c 0,1,4,5 python3 quick_scripts/analyze/targeted_order_cycles.py run \
  --component initial-cost \
  --reference /home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216 \
  --binary ./target/release/ddd \
  --build-manifest results/aglr/initial-cost-v19-build/manifest.json \
  --results results/aglr/initial-cost-v19-unresolved300 --round-seconds 14000
python3 quick_scripts/analyze/targeted_order_cycles.py audit \
  --reference /home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216 \
  --results results/aglr/initial-cost-v19-unresolved300
```

Tên script được giữ để dùng chung phần chọn ca và kiểm toán; tham số
`--component initial-cost` khóa phép thử mới và ghi `initial_cost_audit.json`.
Lệnh `audit` tự đọc loại phép thử từ manifest. Resume giữ cùng commit,
binary, dependency, dữ liệu, CPU, RAM và tham số. Cả dịch vụ tối đa 6 giờ
kể cả thời gian chờ; không chạy đồng thời hai solver của V18 và V19.
V19 đã hoàn tất và qua kiểm toán độc lập cả 13 ca: tất cả timeout, chưa
có ca mới. Native đạt 65 test Rust và 96 test Python; build, hai smoke và
kiểm tra timeout đều đạt. Dữ liệu đầy đủ ở
`results/sat_research/initial_cost_v19_20261107/complete_13/`.

## V20: truyền thời điểm sớm nhất qua cả chuỗi thứ tự

Mã `8898caf`, cờ `--maxsat-ladder-sc-order-path-cuts true`, mặc định false.
Giữ cấu hình V17, chỉ bật cờ này; tách chi phí V19 tắt. Dùng các cạnh
nối tiếp của tàu và biến thứ tự đã tạo để truyền cận từ earliest tới các
lần đi qua sau. Nếu model SAT chọn một lần đi qua trước cận đã suy ra,
thêm một mốc cùng mệnh đề có điều kiện theo đúng đường đi chứng minh.
Một lần chỉ thêm một mệnh đề; chi phí mốc mới được đăng ký trước lần SAT
kế tiếp. Kiểm tra chu trình dương và xử lý chu trình thời gian 0 nằm trong
cùng bước này. Hướng dẫn sinh viên bản 5.18 có công thức và ví dụ.

Native đã đạt **73 test Rust, 97 test Python**. Test lịch ba tàu đã thực
sự tạo mệnh đề đường đi, kiểm tra optimum vét cạn trên ba objective với
MiniSAT/CaDiCaL; các tùy chọn objective bound dùng bài có nghiệm sớm hợp lệ.
Mã trước khi commit và mã release được đối chiếu hash từng file nguồn.

Worktree `~/projects/order-paths-v20/maxsattrainscheduling`. Dịch vụ
`maxsat-order-paths-v20.service` bắt đầu lúc **11:39:29 ngày 07/11**, giờ
Việt Nam. Controller build release từ commit cố định, kiểm tra optimum
5526 khi bật/tắt path cuts, kiểm tra timeout native rồi mới chạy ca khó.
Mỗi ca 300 giây, 6.000.000 KB RAM, chạy lần lượt trên CPU `0,1,4,5`;
cả vòng tối đa 6 giờ. Không chạy lại 203 ca đã giải hoặc baseline trong
vòng sàng lọc này. Dữ liệu khởi chạy ở
`results/sat_research/order_paths_v20_20261107/`.

```bash
systemctl status maxsat-order-paths-v20.service --no-pager
journalctl -u maxsat-order-paths-v20.service -n 30 --no-pager
```

Lệnh tái tạo/tiếp tục khi dịch vụ đã dừng, sau khi kích hoạt môi trường
Gurobi và giữ đúng commit/binary đã kiểm tra:

```bash
taskset -c 0,1,4,5 python3 quick_scripts/analyze/targeted_order_cycles.py run \
  --component order-paths \
  --reference /home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216 \
  --binary ./target/release/ddd \
  --build-manifest results/aglr/order-paths-v20-build/manifest.json \
  --results results/aglr/order-paths-v20-unresolved300 --round-seconds 21000
python3 quick_scripts/analyze/targeted_order_cycles.py audit \
  --reference /home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216 \
  --results results/aglr/order-paths-v20-unresolved300
```

Runner kiểm tra lại 216 ca nguồn và chọn đúng 13 ca chưa giải. Đọc
`order_paths_audit.json`, `summary.csv`, `failure.json` nếu có. Cờ và tham
số phải khớp trong JSON lẫn manifest. Các trường cần theo dõi:
`maxsat_order_path_checks`, `maxsat_order_paths_added`,
`maxsat_order_path_new_points`, `maxsat_order_path_guards`,
`maxsat_order_path_time`; đối chiếu thêm `maxsat_native_sat_time`, số biến
và số mệnh đề. Có ca mới thì xác nhận ba lần và kiểm tra các ca V17 từng
giải trước khi thay coverage full. Khởi chạy và đạt test chưa phải kết quả
hiệu năng V20.

## V21: cùng binary V20, gửi toàn bộ điều kiện chi phí

Trên ca đầu, V20 cần 40.606 lời gọi SAT so với 1.542 của V17, nhưng tìm
đường chỉ tốn 1,61 giây. V21 đổi đúng lịch gửi điều kiện: `legacy` thành
`full`. Cơ chế đường đi, RC2, ngân sách core và binary giữ nguyên. Đây là
phép thử trên tải công việc mới của V20; kết quả thử lịch gửi trên cách
mã hóa cũ vẫn được giữ và chưa chứng minh cách gửi nào luôn tốt hơn.

Solver source `8898caf`, runner `4b4d80f`. Tái sử dụng binary có hash
`b888e424572ad22cfa145a8f57381eab9354e81a2dcd13b059bb8564535bf340`.
Tham số `--reuse-build` giữ commit solver thật thay vì gán commit của
script mới cho binary cũ. Native V20 đã qua 73 test Rust; runner V21 qua
99 test Python trên VM. Smoke hai cách gửi đều có cost=LB=UB=5526; cách
`full` có `maxsat_partial_sat_calls=0`. Timeout probe đạt trước sàng lọc.

Dịch vụ `maxsat-order-paths-full-v21.service` bắt đầu **11:50:15 ngày
07/11**, đo từ 11:50:20, giờ Việt Nam. Worktree riêng
`~/projects/order-paths-full-v21/maxsattrainscheduling`. Chỉ 13 ca chưa
giải, 300 giây và 6.000.000 KB mỗi ca, nhóm lõi vật lý `2,3,6,7` tách
nhóm V20. Mỗi lượt tối đa 6 giờ. Thời gian sàng lọc song song chỉ dùng
chẩn đoán; full cho bảng chính vẫn chạy tuần tự.

```bash
systemctl status maxsat-order-paths-full-v21.service --no-pager
journalctl -u maxsat-order-paths-full-v21.service -n 30 --no-pager
```

Khi dịch vụ đã dừng, lệnh tái tạo/tiếp tục là:

```bash
taskset -c 2,3,6,7 python3 quick_scripts/analyze/targeted_order_cycles.py run \
  --component order-paths-full --reuse-build \
  --reference /home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216 \
  --binary /home/tuyenkv/projects/order-paths-v20/maxsattrainscheduling/target/release/ddd \
  --build-manifest /home/tuyenkv/projects/order-paths-v20/maxsattrainscheduling/results/aglr/order-paths-v20-build/manifest.json \
  --results results/aglr/order-paths-full-v21-unresolved300 --round-seconds 21000
python3 quick_scripts/analyze/targeted_order_cycles.py audit \
  --reference /home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216 \
  --results results/aglr/order-paths-full-v21-unresolved300
```

Đọc `order_paths_full_audit.json`. Không ghép ca tốt nhất của V20 và V21
để báo coverage của một solver. Chọn cấu hình sau khi đủ ca và qua audit;
có ca mới thì xác nhận ba lần và hồi quy trước khi thay mốc 203/216.

Có thể chụp các ca đã xong mà không dừng lượt chạy bằng
`results/sat_research/order_paths_v20_20261107/snapshot_trial.py`, truyền
thư mục RUN và đường dẫn archive mới. Script chỉ lấy số ca đã ghi hoàn
tất, kèm manifest và hash từng file. Sau khi giải nén vào thư mục mới,
lệnh `audit` ở trên kiểm tra cả hash bản chụp và nội dung kết quả. Bản
chụp V20 đầu tiên có 2/13 ca và đã qua kiểm toán độc lập trong `progress_2/`;
hai ca đều timeout, không phải kết quả cuối của V20.

## V22: SAT chọn thứ tự, đồ thị tính lịch

**Trạng thái cuối:** native đạt 76 test Rust và 106 test Python. Smoke
`origA1/finsteps123` chứng minh đúng cost 11 ở 18,72 giây; `infsteps180`
timeout hợp lệ ở 30 giây. Controller dừng trước ca khó. Dữ liệu ở
`results/sat_research/order_master_v22_20261107/stopped_validation/`;
không ghi thành 0/13. Các lệnh dưới giữ để tái tạo, không chạy trùng với
lượt mới. V23 phía sau sửa cách dùng chung ngưỡng chi phí.

V20 và V21 đã hoàn tất 13/13 ca, không giải thêm. Dữ liệu đã qua kiểm toán
độc lập, ở `complete_13/` trong hai thư mục thực nghiệm tương ứng. Mốc tốt
nhất full vẫn là V17 (72,68,63), tổng 203/216.

Mã V22 `38f9aea` bật một biểu diễn riêng: `order_master=true`. SAT có đủ
biến thứ tự cho các cặp khác tàu dùng tài nguyên xung đột; đồ thị tính
lịch sớm nhất theo các hướng. Chỉ thêm ngưỡng ở lần đi qua có mức phạt
tăng, không thêm mốc chỉ vì thời gian của một nút không có phạt tăng.
Vòng RC2, CostTree và xử lý core được tái sử dụng. Nếu lịch hợp lệ có chi
phí bằng LB thì chứng minh tối ưu; dữ liệu hội nghị chỉ được script đọc
sau khi solver chạy xong. Hướng dẫn sinh viên 5.18 có công thức và ví dụ.

Cờ `--maxsat-ladder-sc-order-master true` mặc định false, biến Bash
`MAXSATDDD_ORDER_MASTER=true`; alias `maxsat_order_graph` tự bật master
và biến thứ tự. Baseline mặc định giữ nguyên. Chế độ master không tạo
hàng xung đột theo thời gian hoặc bộ ba ban đầu; số đo rows/triangles
bằng 0 dù cờ bộ ba từ cấu hình nguồn còn được ghi để truy vết. Nó cũng
tắt luồng heuristic cũ; lịch đồ thị mới là nguồn UB và phải được kiểm tra.

76 test Rust đã đạt native trên VM. Có vét cạn ba hàm mục tiêu với
MiniSAT/CaDiCaL, occupation cuối dương, chi phí ban đầu dương, sparse và
giới hạn objective. Controller chạy lại 106 test Python, build release,
kiểm tra `origA1` ở ba objective, alias và timeout trước ca khó. Hash các
file Rust trong release phải khớp bản đã chạy native.

Worktree `~/projects/order-master-v22/maxsattrainscheduling`, dịch vụ
`maxsat-order-master-v22.service`. Mỗi ca 300 giây, 6.000.000 KB RAM,
chạy lần lượt trên CPU `0,1,4,5`; cả service tối đa 6 giờ.

```bash
systemctl status maxsat-order-master-v22.service --no-pager
journalctl -u maxsat-order-master-v22.service -n 30 --no-pager
```

Khi dịch vụ đã dừng, lệnh chạy tiếp giữ đúng source/binary/manifest là:

```bash
taskset -c 0,1,4,5 python3 quick_scripts/analyze/targeted_order_cycles.py run \
  --component order-master \
  --reference /home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216 \
  --binary ./target/release/ddd \
  --build-manifest results/aglr/order-master-v22-build/manifest.json \
  --results results/aglr/order-master-v22-unresolved300 --round-seconds 7200
python3 quick_scripts/analyze/targeted_order_cycles.py audit \
  --reference /home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216 \
  --results results/aglr/order-master-v22-unresolved300
```

Đọc `order_master_audit.json` và `failure.json` nếu có. Theo dõi
`maxsat_order_master_models`, `maxsat_order_master_schedules`, số cặp thứ
tự, số mệnh đề đường đi, biến SAT, thời gian đồ thị và SAT. Sàng lọc chỉ
có 13 ca; chưa chạy full lại trong bước này.

Controller tự chuyển sang `confirm_component_gains.py` sau khi đủ 13 ca
và audit đạt. Không có ca mới thì ghi quyết định và kết thúc. Có ca mới
thì xác nhận ba lần với đúng binary/cấu hình; chỉ khi tất cả lặp lại
thành công mới hồi quy 203 ca V17 đã giải. Mọi ca bị mất vẫn giữ trong
báo cáo. Thời gian chờ, build, sàng lọc, xác nhận và hồi quy cùng chịu
giới hạn 6 giờ; không đủ thời gian thì giữ phần đã xong và chưa báo full.

Lệnh xác nhận/hồi quy riêng, khi không còn dịch vụ đang ghi dữ liệu:

```bash
taskset -c 0,1,4,5 python3 quick_scripts/analyze/confirm_component_gains.py \
  --trial results/aglr/order-master-v22-unresolved300 \
  --reference /home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216 \
  --binary ./target/release/ddd \
  --results results/aglr/order-master-v22-followup --round-seconds 14000
python3 quick_scripts/analyze/confirm_component_gains.py --audit \
  --trial results/aglr/order-master-v22-unresolved300 \
  --reference /home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216 \
  --results results/aglr/order-master-v22-followup
```

Đọc `followup_audit.json`: `confirmed`, `regression_complete`,
`regression_passed`, `lost`, `complete`. Auditor dựng lại kế hoạch từ
trial nguồn, kiểm tra hash, provenance và từng nghiệm; không chỉ tin số
đếm tổng. Cả hai báo cáo vẫn để `submission_passed=false`. Sau khi có
bằng chứng mới đủ và audit độc lập, dựng bảng full 216 cặp của một cấu
hình, không ghép ca tốt nhất của nhiều cấu hình.

## V23: dùng chung một ngưỡng cho mỗi mức phạt trong master

**Trạng thái cuối:** test native đạt 77 Rust, 107 Python; smoke
finsteps123 có đúng cost 11 ở 27,78 giây, nhưng infsteps180 timeout hợp lệ
ở 30 giây. Dừng trước 13 ca khó. Giữ các lệnh và dữ liệu để tái tạo;
V24 dùng nguyên binary, chỉ đổi lịch gửi điều kiện.

Mã `d8e2509`, cờ `--maxsat-ladder-sc-order-master-cost-levels true`, mặc
định false và yêu cầu master bật. Mỗi đường chứng minh cận L chỉ tạo biến
ở thời điểm đầu tiên có cùng chi phí với L, chặn dưới bởi earliest. Ví dụ
aimed=0, `infsteps180`: L=200 và L=280 đều dùng mốc 181. Với chi phí liên
tục dương, mốc vẫn là L. Giữ RC2 và lịch gửi `legacy` của V22 để đối chứng
đúng một thay đổi. Công thức và ví dụ ở hướng dẫn sinh viên 5.22.

Native đã qua **77 test Rust và 107 test Python**. Mốc đại diện được kiểm
tra trên mọi thời điểm nhỏ của ba dạng chi phí, earliest nằm trong bậc,
biên i32; master bật/tắt chuẩn hóa vẫn giữ optimum vét cạn với cả MiniSAT
và CaDiCaL. Controller tiếp tục kiểm tra `origA1` ở cả ba objective, alias
và timeout native trước khi chạy bất kỳ ca khó nào.

Worktree `~/projects/master-levels-v23/maxsattrainscheduling`, dịch vụ
`maxsat-master-levels-v23.service`, bắt đầu **13:34:56 ngày 07/11**, giờ
Việt Nam. Mỗi ca 300 giây, 6.000.000 KB RAM,
chạy lần lượt trên CPU `0,1,4,5`. Cả service tối đa 6 giờ, gồm build,
kiểm tra, sàng lọc và xác nhận/hồi quy nếu có ca mới. Nếu thử nhanh không
đạt thì dừng, giữ bản ghi và không báo thành 0/13.

```bash
systemctl status maxsat-master-levels-v23.service --no-pager
journalctl -u maxsat-master-levels-v23.service -n 30 --no-pager
```

Khi service đã dừng, lệnh tái tạo/tiếp tục với cùng nguồn và binary là:

```bash
taskset -c 0,1,4,5 python3 quick_scripts/analyze/targeted_order_cycles.py run \
  --component order-master-levels \
  --reference /home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216 \
  --binary ./target/release/ddd \
  --build-manifest results/aglr/master-levels-v23-build/manifest.json \
  --results results/aglr/master-levels-v23-unresolved300 --round-seconds 7200
python3 quick_scripts/analyze/targeted_order_cycles.py audit \
  --reference /home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216 \
  --results results/aglr/master-levels-v23-unresolved300
```

Đọc `order_master_levels_audit.json`. Xác nhận/hồi quy dùng script và
quy tắc V22, đổi đường dẫn trial thành `master-levels-v23-unresolved300`,
thư mục followup thành `master-levels-v23-followup`. Chỉ khi ba lần xác
nhận mọi gain đạt mới chạy 203 ca hồi quy. Theo dõi `confirmed`,
`regression_passed`, `lost` và `complete`; báo cáo không tự báo submission
PASS. Không ghép thời gian hoặc ca tốt nhất giữa V22 và V23.

## V24: master dùng ngưỡng đại diện và gửi đủ điều kiện chi phí

Runner `080edb7` dùng lại solver `d8e2509` và build manifest của V23.
Chỉ đổi `assumptions=legacy` thành `full`; không build một bản Rust mới.
77 test Rust của binary V23 vẫn áp dụng, runner chạy thêm 108 test Python.
V24 đã dừng trước ca khó: finsteps123 và infsteps180 giải đúng ở 15,62
và 13,73 giây; cont timeout hợp lệ ở 30 giây. Raw và kiểm toán riêng ở
`results/sat_research/master_full_v24_20261107/stopped_validation/`.
Các smoke V23 vẫn giữ, không đổi nhãn thành V24.

Worktree `~/projects/master-full-v24/maxsattrainscheduling`, dịch vụ
`maxsat-master-full-v24.service`. Controller và validator được giữ trong
`results/sat_research/master_full_v24_20261107/`. Cùng 300 giây và
6.000.000 KB mỗi ca, chạy tuần tự trên CPU `0,1,4,5`; cả service tối đa
6 giờ. Nếu có gain thì xác nhận ba lần và hồi quy trong thời gian còn lại.

```bash
systemctl status maxsat-master-full-v24.service --no-pager
journalctl -u maxsat-master-full-v24.service -n 30 --no-pager
```

Lệnh tái tạo sàng lọc V24, nếu chủ động mở lượt đủ ba objective. Lượt đã
chạy thực tế dừng tại thử nhanh; lệnh dưới chưa được chạy cho V24:

```bash
taskset -c 0,1,4,5 python3 quick_scripts/analyze/targeted_order_cycles.py run \
  --component order-master-levels-full --reuse-build \
  --reference /home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216 \
  --binary /home/tuyenkv/projects/master-levels-v23/maxsattrainscheduling/target/release/ddd \
  --build-manifest /home/tuyenkv/projects/master-levels-v23/maxsattrainscheduling/results/aglr/master-levels-v23-build/manifest.json \
  --results results/aglr/master-full-v24-unresolved300 --round-seconds 7200
python3 quick_scripts/analyze/targeted_order_cycles.py audit \
  --reference /home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216 \
  --results results/aglr/master-full-v24-unresolved300
```

Báo cáo `order_master_levels_full_audit.json` giữ đúng commit binary và
commit runner riêng. Xác nhận/hồi quy đọc `followup_audit.json` như V22.
Trạng thái khởi chạy không chứng minh hiệu năng hoặc coverage mới.

## V25: chỉ bốn ca infsteps180 chưa giải

Runner `7b752c4`, solver source `d8e2509`; giữ nguyên binary, cost-levels
và assumptions=full của V24. Không build lại. Bài thử infsteps180 V24
được kiểm tra và dùng lại đúng hash. Probe timeout native đã có raw,
validator chỉ kiểm tra lại khi resume thay vì ghi đè. Lượt đo thật là
`maxsat-master-rounded-v25-screen.service`, bắt đầu 14:01:46 ngày 07/11,
giờ Việt Nam, trong `~/projects/master-rounded-v25/maxsattrainscheduling`.
Lượt đã xong 4/4 ca, đều timeout hợp lệ, chưa có gain; raw và kiểm toán
local nằm trong `results/sat_research/master_rounded_v25_20261107/complete_4/`.
Hai lần lỗi thiết lập trước đó không có ca khó; giữ `preflight-failed/`
và log dịch vụ để truy vết.

```bash
taskset -c 0,1,4,5 python3 quick_scripts/analyze/targeted_order_cycles.py run \
  --component order-master-levels-full --reuse-build --objectives infsteps180 \
  --reference /home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216 \
  --binary /home/tuyenkv/projects/master-levels-v23/maxsattrainscheduling/target/release/ddd \
  --build-manifest /home/tuyenkv/projects/master-levels-v23/maxsattrainscheduling/results/aglr/master-levels-v23-build/manifest.json \
  --results results/aglr/master-rounded-v25-unresolved300 --round-seconds 7200
python3 quick_scripts/analyze/targeted_order_cycles.py audit \
  --reference /home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216 \
  --results results/aglr/master-rounded-v25-unresolved300
```

Manifest có `objective_filter=["infsteps180"]`; hai objective còn lại có
danh sách rỗng. Bộ kiểm toán vẫn đọc đủ 216 raw V17 để xác định chính xác
bốn ca chưa giải. Không đổi danh sách khi resume và không tự xem những
ca bị loại là đã giải được.

Nếu có gain, `confirm_component_gains.py` chạy ba lần xác nhận rồi hồi
quy 68 ca infsteps180 đã giải. Báo cáo giữ
`full_reference_regression=false`, `submission_passed=false`. Chưa được
cộng gain vào 203 hoặc dùng thời gian ghép từ nhiều cấu hình để báo full.

## V26: thêm nhiều điều kiện chi phí từ cùng một lịch

Mã `984e221` thêm cờ mặc định tắt
`--maxsat-ladder-sc-order-master-batch-cuts true`; biến Bash
`MAXSATDDD_ORDER_MASTER_BATCH_CUTS=true`. Mỗi lần đồ thị cho lịch hợp lệ,
bổ sung mọi lần đi qua có chi phí cao hơn model SAT. Các mệnh đề đều có
chứng minh đường đi riêng, giữ chuẩn hóa ngưỡng V23 và assumptions=full
của V24. Chi phí mọi mốc mới được đăng ký trước SAT kế tiếp. Không đổi
đường mặc định CSOnet.

Controller `maxsat-master-batch-v26.service` ở worktree
`~/projects/master-batch-v26/maxsattrainscheduling`, đã bắt đầu test native/build sau khi V25 kết thúc. Native đã đạt 78 test Rust và 111 Python. Hai bài thử bậc thang có
đúng optimum ở 5,48 và 7,82 giây; cont timeout hợp lệ. Dữ liệu và kiểm
toán local ở `master_batch_v26_20261107/native_validation/` trong
`results/sat_research/`. Validator đã sửa việc đọc trường telemetry thiếu
khi native timeout; dùng lại raw đã có, không suy đoán counter bằng 0.
Cả service tối đa 6 giờ, kể cả thời gian chờ. Đo tuần tự CPU 0,1,4,5,
300 giây và 6.000.000 KB mỗi ca.

Validator V26 ghi rõ cách kiểm tra: bộ test vét cạn phải đạt; mọi bài
thử thật phải có trạng thái hợp lệ; mọi bài có chứng minh tối ưu phải
khớp đáp án; ít nhất một bài thử có optimum; việc thêm nhiều điều kiện
phải thực sự xảy ra. Timeout hợp lệ ở bài thử thật được giữ là kết quả
hiệu năng, không tự báo lỗi thuật toán. Khác biệt so với cổng dừng sớm
V22--V24 được lưu trong `validation.json`; không sửa các kết quả cũ.

```bash
systemctl status maxsat-master-batch-v26.service --no-pager
journalctl -u maxsat-master-batch-v26.service -n 20 --no-pager
taskset -c 0,1,4,5 python3 quick_scripts/analyze/targeted_order_cycles.py run \
  --component order-master-batch \
  --reference /home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216 \
  --binary ./target/release/ddd \
  --build-manifest results/aglr/master-batch-v26-build/manifest.json \
  --results results/aglr/master-batch-v26-unresolved300 --round-seconds 7200
```

Chỉ dùng lệnh run sau khi validation đạt, service đã dừng và ở đúng
commit/binary đã khóa. Báo cáo `order_master_batch_audit.json` không thể
báo submission PASS. Theo dõi số lời gọi SAT, mệnh đề đường đi, mốc mới,
thời gian SAT/đồ thị và `maxsat_order_master_max_batch`. Nếu có gain,
controller tự xác nhận ba lần rồi hồi quy 203 ca; đủ dữ liệu mới lập
bảng full. Không cộng thời gian các lần chạy khác nhau.

## V27 dự phòng: đưa điều kiện chi phí theo một thứ tự vào từ đầu

Mã `c1b046f`, mặc định `order_master_seed_costs=false`. Bật bằng
`--maxsat-ladder-sc-order-master-seed-costs true` hoặc
`MAXSATDDD_ORDER_MASTER_SEED_COSTS=true`. Chỉ thêm một thành phần trên
V26. Mỗi hướng của một cặp có điều kiện chi phí được chứng minh từ cận
cứng trên tuyến và thời điểm rời thật; không biến chúng thành thứ tự
bắt buộc. Mốc chuẩn hóa và CostTree giữ nguyên. Công thức, ví dụ và
kiểm thử bắt buộc nằm trong hướng dẫn sinh viên 5.22.

V27 được xếp sau V26. `decide_vm_round.py` kiểm toán lại đủ 13 raw V26
và 216 raw V17; chỉ mở V27 nếu V26 hoàn tất, không lỗi và không có gain.
Nếu V26 có gain, ghi quyết định bỏ qua V27 và kết thúc service bình thường;
ưu tiên xác nhận/hồi quy V26. Nếu V26 lỗi hoặc chưa đủ dữ liệu, không mở
V27. Không chạy đo hoặc build cạnh tranh với V26.

Local V27 đạt 37 test nhân SAT, 113 test Python, Rust typecheck và Bash
syntax; native chưa được coi là đạt khi service còn chờ. V27 chạy riêng
bốn ca infsteps180 ở 300 giây, 6.000.000 KB, CPU 0,1,4,5. Cả service tối
đa 6 giờ kể cả thời gian chờ. Nếu có gain thì ba lần xác nhận và hồi quy
68 ca cùng objective, chưa báo full-reference hoặc submission PASS.

```bash
systemctl status maxsat-master-seeds-v27.service --no-pager
journalctl -u maxsat-master-seeds-v27.service -n 20 --no-pager
# Chỉ chạy thủ công sau khi đã qua quyết định mở lượt và test native.
taskset -c 0,1,4,5 python3 quick_scripts/analyze/targeted_order_cycles.py run \
  --component order-master-seeds --objectives infsteps180 \
  --reference /home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216 \
  --binary ./target/release/ddd \
  --build-manifest results/aglr/master-seeds-v27-build/manifest.json \
  --results results/aglr/master-seeds-v27-unresolved300 --round-seconds 7200
```

Manifest và `order_master_seeds_audit.json` giữ phạm vi objective và binary
riêng. Chưa cộng các ca mới của một lượt thử vào bảng full V17 khi chưa
khóa cách chọn cấu hình và kiểm toán các objective còn lại.

## V28: đối chứng backend cùng binary và cùng ngân sách kiểm tra

Runner `23591b3`, cùng binary V27 (solver source `c1b046f`). Hai dịch vụ
`maxsat-master-v28-minisat` và `maxsat-master-v28-cadical` chờ V27 hoàn tất,
kiểm toán đủ bốn ca rồi mới kiểm tra binary/hash và chạy thêm các bài thử
thật. Không build lại Rust. Nếu V27 lỗi hoặc thiếu dữ liệu, chưa mở V28.

Hai backend cùng `core_minimize_checks=4`, `core_exhaust_checks=4` và
`core_minimize_conflicts=0`. Giá trị 0 bỏ giới hạn xung đột riêng trong
mỗi truy vấn phụ; deadline toàn instance vẫn là 300 giây. Giới hạn 100
của V27 chỉ được adapter MiniSAT thực hiện, nên không giả định rằng
CaDiCaL/100 và MiniSAT/100 có cùng giới hạn thực tế.

```bash
# Từ worktree ~/projects/master-backends-v28/maxsattrainscheduling,
# sau khi preflight và validation đúng backend đã đạt.
backend=minisat  # lượt còn lại: cadical
python3 quick_scripts/analyze/targeted_order_cycles.py run \
 --component order-master-seeds --objectives infsteps180 \
 --backend "$backend" --core-minimize-conflicts 0 \
 --measurement-context paired-screen --paired-run-id master-backends-v28 \
 --reuse-build \
 --reference /home/tuyenkv/projects/core-exhaust-v17-followup/maxsattrainscheduling/results/aglr/core-exhaust-v17-full216 \
 --binary /home/tuyenkv/projects/master-seeds-v27/maxsattrainscheduling/target/release/ddd \
 --build-manifest /home/tuyenkv/projects/master-seeds-v27/maxsattrainscheduling/results/aglr/master-seeds-v27-build/manifest.json \
 --results "results/aglr/master-backends-v28-$backend-unresolved300" --round-seconds 7200
```

Controller pin MiniSAT vào 0,1,4,5 và CaDiCaL vào 2,3,6,7. VM xác nhận
core/socket bằng `lscpu`: nhóm đầu dùng lõi vật lý 0,1; nhóm sau dùng 2,3.
Cùng 6.000.000 KB mỗi backend; tối đa 6 giờ mỗi service, gồm thời gian chờ.
Các phép đo song song và followup mang `paired-screen`, chưa dùng làm
runtime chính. V27 MiniSAT/100 vẫn giữ riêng để đối chứng thay giới hạn.

Bộ so sánh ở mã `296199d` kiểm toán lại raw trước khi xếp hạng:

```bash
python3 quick_scripts/analyze/compare_targeted_backends.py \
 --reference results/aglr/core-e4-full216-complete-local \
 --minisat results/aglr/v28-minisat-local \
 --cadical results/aglr/v28-cadical-local \
 --output results/aglr/v28-backend-comparison.json
```

Lệnh trên dùng snapshot đã tải về và giải nén đúng thư mục. Chỉ thêm
`--allow-partial` khi chủ động xem tiến độ; báo cáo chưa đủ không có bên
thắng hoặc danh sách ca bị mất. Mỗi lượt có gain sẽ tự xác nhận ba lần,
sau đó hồi quy 68 ca infsteps180 đã giải. Kết quả cần được khóa theo
objective và kiểm toán bảng đầy đủ trước mọi kết luận submission.

## Đối chiếu RC2 và lịch sử lượt năm phương pháp ở 300 giây

**Đã xác nhận CSOnet dùng RC2, với MiniSAT trong mã được kiểm tra.** RC2 xử
lý tối ưu; MiniSAT/CaDiCaL xử lý các truy vấn SAT bên trong. Bản tiền ấn
phẩm của tác giả bài COR gốc cũng ghi RC2 + MiniSat 2.1.0. Vì vậy, giữ
RC2 + MiniSAT làm mốc theo mã SOTA hiện có. Không bỏ kết quả MiniSAT chỉ
vì tên này khác RC2. Nguồn và cách thống nhất ở
[báo cáo kiểm tra bộ giải](reviews/solver_stack_20261106/README.md).

Lượt trước dùng **RC2 + CaDiCaL** cho cả ba phương pháp MaxSAT, để đo
ảnh hưởng khi đổi SAT backend cho cả phương pháp mới và baseline. Đây là
đối chứng bổ sung; không phải bằng chứng CSOnet gốc dùng CaDiCaL. So sánh
hiệu quả phương pháp trong từng backend, còn ảnh hưởng của backend được
so bằng cùng một phương pháp trên MiniSAT/CaDiCaL. Không trộn hai lượt.
Hai baseline MILP tiếp tục dùng Gurobi/CPLEX. Chiến dịch MiniSAT đã dừng
ở 91 lượt nhưng dữ liệu hợp lệ vẫn được giữ để dùng lại; lượt thu gọn core
từng xếp hàng đã hủy. Chưa có metadata riêng của binary hội nghị để xác
nhận backend độc lập với mã nguồn.

Chưa có ca mới được giải ở 120 giây. Theo yêu cầu của thầy/cô, thử 300 giây
cho cả phương án bộ ba V5 và CSOnet, MaxSAT-Journal, Big-M Gurobi, Big-M CPLEX.
Danh sách mới có 31 cặp: 5 infsteps180, 26 cont, không có finsteps123. Đây là
hợp những ca chưa giải trong danh sách cũ hoặc trong bốn bảng baseline.
Mỗi phương pháp chạy đúng danh sách này. Không đổi timeout của kết quả cũ.

```bash
BIN=./target/release/ddd EXPORT_BIN=./target/release/export_lp \
CPLEX_BIN=/home/tuyenkv/opt/ibm/ILOG/CPLEX_Studio2220/cplex/bin/x86-64_linux/cplex \
EXTENDED_PLAN=results/sat_research/cadical_300_20261106/plan.json \
EXTENDED_REUSE_MILP_FROM=/home/tuyenkv/projects/core-v9/maxsattrainscheduling/results/aglr/extended300-b6a4370-20261106 \
RUN_ID=cadical300-20261106 bash run_extended_timeout_experiments.sh
```

Lượt trước trên VM dùng commit `4a43a9c`, worktree
`~/projects/cadical-v12/maxsattrainscheduling`, RUN_ID
`cadical300-v12-4a43a9c`, dịch vụ `maxsat-cadical300-v12-4a43a9c.service`.
Dịch vụ này đã được dừng để chuyển sang hai backend. Xem log cũ bằng
`journalctl -u maxsat-cadical300-v12-4a43a9c.service -n 30 --no-pager`.

Kích hoạt môi trường Gurobi đã cài trước khi chạy. Lệnh giới hạn một vòng
6 giờ, chạy tuần tự, xen kẽ thứ tự phương pháp có seed cố định. Chạy lại cùng
lệnh để tiếp tục; nguồn, binary, dependency, máy và danh sách phải khớp.
Mỗi ca hoàn tất được kiểm tra lịch độc lập và lưu trước khi chuyển sang ca
tiếp. Nếu có lỗi, giữ dữ liệu và sửa nguyên nhân, không chạy lặp để chọn kết
quả đẹp hơn. CPLEX dùng Big-M eager, 4 luồng và gap bằng 0; chỉ tính tối ưu
khi có lịch hợp lệ và cận khớp.

Đọc `extended_audit.json` và `extended_summary.csv` trong thư mục RUN_ID.
Trong lúc chưa đủ lượt, dùng `comparable_summary` hoặc
`extended_comparable_summary.csv` để so trên các cặp đã chạy đủ năm phương pháp.
`complete=false` nghĩa là còn ca chưa chạy; dùng `missing` để biết phần còn
lại. `gained` và `lost` so sánh các cặp đã chạy đủ cả hai phương pháp ở
**cùng 300 giây**. Chỉ kết luận về nhóm khó; cần kiểm tra toàn bộ dataset
sau khi chọn được cấu hình. Nếu 300 giây chưa giúp phân biệt, xem cận và
thời gian trước khi quyết định vòng 600 giây cho cả năm phương pháp.

Mỗi kết quả CaDiCaL phải có `maxsat_backend=cadical` và chữ ký
`maxsat_backend_signature` từ solver native. `maxsat_ddd_cdc` đã được sửa
để gọi CaDiCaL thật. Lệnh mặc định cũ vẫn giữ để tái tạo mã lịch sử; chiến dịch
mới dùng cờ backend tường minh. Toàn bộ 93 ca SAT chạy lại. Chỉ 37 ca MILP đã
hoàn tất được dùng lại nguyên byte; 25 ca MILP còn thiếu chạy mới.

Có thể lấy bản chụp các ca đã hoàn tất mà không dừng chiến dịch:
`python3 quick_scripts/analyze/snapshot_extended_timeout.py <RUN_DIR> <archive.tar.gz>`.
Chạy script từ một bản mã riêng nếu worktree thí nghiệm đã khóa commit cũ.
Sau khi giải nén trên máy local, kiểm tra lại bằng
`python3 quick_scripts/analyze/extended_timeout_experiments.py audit-saved <snapshot_dir>`.
Auditor xác minh hash từng file, kiểm tra lịch độc lập và dựng lại báo cáo.
Chỉ các thống kê thời gian tính lại được chấp nhận sai khác làm tròn cỡ máy;
chi phí, số ca tối ưu và dữ liệu đầu vào vẫn phải khớp.

## Lệnh cũ cho thử thu gọn core sau đủ năm đối chứng

Tính năng `--maxsat-ladder-sc-core-minimize-checks 4` thử bỏ điều kiện có
trọng số nhỏ trước; chỉ bỏ khi một lời gọi SAT mới chứng minh tập còn lại
vẫn mâu thuẫn. Mặc định là 0. Giới hạn bốn lời gọi bổ sung cho mỗi core,
ngừng thử mới khi hết timeout. Hướng hiện tại là V16 trên 15 ca chưa giải,
đã nêu ở trên. Phần này giữ lệnh cũ để tra cứu; không phải việc cần chạy ngay.

Khi chiến dịch năm phương pháp ở trên kết thúc, chạy kiểm thử Rust/Python
và build release trong một worktree khác. Sau đó:

```bash
EXTENDED_REFERENCE=/home/tuyenkv/projects/cadical-v12/maxsattrainscheduling/results/aglr/cadical300-v12-4a43a9c \
BIN=./target/release/ddd EXPORT_BIN=./target/release/export_lp \
CPLEX_BIN=/home/tuyenkv/opt/ibm/ILOG/CPLEX_Studio2220/cplex/bin/x86-64_linux/cplex \
RUN_ID=mincore300-cadical bash run_core_minimization_trial.sh
```

Script kiểm toán lại đối chứng và chỉ chạy nếu đủ 155/155 lượt, không lỗi.
Chạy mới 31 lượt của `Orders-Transitive-Mincore`; dùng lại nguyên 124 lượt
của bốn baseline ở cùng cutoff 300 giây. `reused_from.json` ghi nguồn,
hash dữ liệu và manifest. Không được thay runtime hoặc chọn lượt tốt hơn.
`measured_runs`/`reused_baseline_runs` cho biết số lượt đo mới/dùng lại.
Mỗi vòng tối đa 6 giờ; cùng RUN_ID để tiếp tục.

Trên VM, 46 test Rust và 59 test Python đã đạt, gồm core với CaDiCaL thật
và lịch nhỏ so với vét cạn. Ba phương pháp MaxSAT đã qua smoke test với
chữ ký `cadical-1.9.5`. Chưa có số liệu hiệu năng của thu gọn core.

## Quy trình nhóm 120 giây đã chạy

Từ 06/11/2026, mỗi ý tưởng mới chạy trên danh sách đã lọc theo objective.
Không chạy lại toàn bộ dataset ở mỗi vòng. Hai lượt full mới nhất đã xong:
bộ ba đạt `(72,68,60)`, giới hạn chi phí đạt `(72,68,59)`; cả hai qua audit
và chưa vượt baseline tốt nhất. Raw results được giữ trong
`results/sat_research/transitivity_v5_20261105/` và `bounds_v6_20261105/`.

Danh sách cố định: `results/sat_research/focus_20261106/selection.json`.

| Objective | Số ca cần thử | Cách xử lý |
|---|---:|---|
| finsteps123 | 0 | Bỏ qua trong vòng ý tưởng |
| infsteps180 | 4 | Chạy đúng bốn ca trong danh sách |
| cont | 14 | Gồm các ca timeout và các ca có kết quả chưa ổn định |

Tập này là hợp các ca chưa chứng minh tối ưu trong các lượt full bộ ba,
giới hạn chi phí và hội nghị. Giữ cả ca mới giải được và ca bị mất để theo
dõi hai chiều. Không chạy mỗi tên với cả ba objective; tổng là **18 cặp**.
Hash nguồn và hash dataset nằm trong file lựa chọn. Không sửa file này giữa
một vòng; nếu cần nhóm khác, tạo một file có tên mới.

Glucose đã chạy xong trên nhóm này: 0/4 `infsteps180`, 2/14 `cont`, không
tăng số ca giải được so với phương án bộ ba. Kết quả đã kiểm toán và push
ở `results/sat_research/focus_v7_20261106/`; không chạy lại lượt đó.

Vòng V8 đã giữ MiniSAT và thêm quy tắc loại lựa chọn quá đắt:

```bash
FOCUS_MANIFEST=results/sat_research/focus_20261106/selection.json \
BIN=./target/release/ddd CORE_VARIANT=orders-transitive-harden \
RUN_ID=focus-harden-v8 bash run_maxsat_focused_experiments.sh
```

Lệnh chạy tuần tự, mỗi ca 120 giây, cả vòng tối đa 6 giờ. Kết quả ở
`results/aglr/focus-harden-v8/`. Giữ cùng `RUN_ID`, binary, mã và file lựa
chọn để tiếp tục sau gián đoạn. Dữ liệu cũ của một cấu hình được tái sử dụng
làm đối chứng; không chạy lại chỉ để tạo bảng nhóm khó.

Đọc `aglr_audit.json`, rồi `Focus-orders-transitive-harden/focus_comparison.json`.
`gained`/`lost` là danh sách giải thêm/bị mất so với từng đối chứng.
`projected_coverage` là ước tính nếu các ca chưa chạy lại vẫn giữ kết quả cũ,
không phải coverage full đã đo. `submission_passed` luôn là false ở báo cáo
nhóm khó. Script không tự chạy full. Khi có tiến triển và xác nhận được các
ca mới, mới chọn một cấu hình để đánh giá đầy đủ và lập bảng bài báo.

Glucose trong phép thử này là bộ native RustSAT, không dùng alias tương thích
trong salvers. Kiểm thử xác nhận dấu của các literal trong UNSAT core đúng
với bản đồ chi phí MaxSAT và optimum khớp vét cạn trên bài ba tàu.
Giá trị mặc định CLI vẫn là MiniSAT để giữ hành vi của mã lịch sử;
không dùng điều này để suy ra backend binary hội nghị. Cờ chọn hiện tại là
`--maxsat-ladder-sc-backend minisat|cadical|glucose`. Chiến dịch mới luôn
ghi backend tường minh. Đối chứng hai backend đã hoàn tất; V16 giữ MiniSAT
theo coverage trên nhóm khó.

Ở lượt hardening, nếu trọng số còn lại của một điều kiện lớn hơn `UB-LB`,
thêm mệnh đề đơn để điều kiện đó luôn được thỏa và bỏ nó khỏi danh sách mềm.
Không tăng LB. Dùng dấu `>`; trường hợp bằng ngân sách vẫn được phép.
Dùng trọng số RC2 còn lại, không dùng trọng số ban đầu. UB chỉ đến từ một
lịch hợp lệ do solver tìm được, không từ bảng hội nghị. Nếu UB nhỏ hơn LB
thì báo lỗi. Mặc định cờ `--maxsat-ladder-sc-residual-hardening` là false.
Theo dõi `maxsat_hardening_scans`, `maxsat_hardened_primary`,
`maxsat_hardened_totalizer`, `maxsat_hardening_time`, coverage và kích thước
mô hình. Quy tắc thêm mệnh đề đơn; không tạo bộ cộng nhị phân.

Các lệnh `screen`/`promote` ở các phần sau mô tả các chiến dịch đã chạy và
phục vụ tái tạo. Khi thử ý tưởng mới, dùng quy trình nhóm khó ở trên.

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

## Chuẩn bị máy và tái tạo chiến dịch AGLR ban đầu

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

## Phương án dự phòng: giới hạn tổng chi phí bằng nghiệm hợp lệ

`EXPERIMENT_SET=bounds` so orders với orders-bound. Cách mới thêm điều kiện
`sum(original_weight * cost_literal) <= verified_UB`, dùng bộ mã nhị phân
`BinaryObjective` đã có. Mỗi hạng tử gốc chỉ thêm một lần; không dùng trọng
số RC2 đã bị giảm và không đưa đáp án hội nghị vào solver. Khi có lịch hợp
lệ tốt hơn thì giảm UB. Cây chi phí và giả định vẫn là `legacy`; không kết
hợp thêm điều kiện bộ ba trong phép thử này.

Cờ mới `--maxsat-ladder-sc-use-objective-bound true` mặc định tắt.
Config, fingerprint, manifest và auditor đều ghi/kiểm tra cờ này. Theo dõi
`maxsat_objective_bound_terms`, `maxsat_objective_bound_updates`,
`maxsat_objective_bound_time`, số biến/mệnh đề và coverage. Phải chạy lại
kiểm thử Linux trước khi khởi động vòng bounds. Việc kiểm thử được xếp sau
vòng transitivity để tránh ảnh hưởng phép đo runtime.

Telemetry cũng ghi kích thước các tập điều kiện chi phí gây mâu thuẫn:
`maxsat_core_literals` là tổng số điều kiện qua các lần xử lý,
`maxsat_core_max_size` là kích thước lớn nhất, và
`maxsat_unit_weight_cores` đếm các lần chỉ tăng được cận dưới một đơn vị.
Các số này giúp quyết định có cần thu nhỏ tập mâu thuẫn ở vòng sau; chưa
thay đổi cách RC2 xử lý chúng trong vòng bounds.
