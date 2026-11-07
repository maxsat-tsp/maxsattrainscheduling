# Tiến độ thử nghiệm trên VM, cập nhật 07-11-2026

## Quyết định backend từ ngày 07-11-2026

Các lượt CaDiCaL đã hoàn tất và được giữ làm đối chứng lịch sử. Từ đây
không mở thêm dịch vụ, sàng lọc hoặc hồi quy CaDiCaL. Mọi thử nghiệm mới
dùng MiniSAT, vì đây là backend đã thống nhất với đường chạy CSOnet. Raw
CaDiCaL không bị xóa; chỉ không dùng chúng để chọn thêm ý tưởng hoặc ghép
runtime mới.

**Vòng kéo dài V17 ở 600 giây (07-11-2026) không tạo thêm coverage.**
Tôi chạy lại đúng 13 ca mà V17 chưa chứng minh được ở 300 giây: bốn ca
`infsteps180` và chín ca `cont`. Cả 13 ca đều đạt giới hạn SAT 600 giây;
không ca nào có `status=ok`, nghiệm mới hoặc cận mới đủ để chứng minh tối
ưu. Kiểm toán độc lập không phát hiện lỗi. Coverage vẫn là
`(72,68,63)`, tổng `203/216`. Raw JSON, log, hash binary và manifest được
lưu trong `results/sat_research/v17_extended600_20261107/`.

Kết quả này cho thấy tăng thời gian chạy một mình không giải quyết nút thắt:
telemetry ghi thời gian MiniSAT gần 600 giây ở mọi ca. Vì vậy không mở thêm
lượt tăng cutoff cho cùng cấu hình; vòng kế tiếp phải thay đúng một thành
phần mã đã kiểm thử, vẫn dùng MiniSAT. CaDiCaL không được khởi động lại.

**V29 và V30 cũng không tăng coverage.** V29 bật verified objective bound
cùng transitivity của V17; 13/13 ca khó ở 300 giây đều timeout hợp lệ. V30
cố định thứ tự các mệnh đề RC2 có cùng trọng số theo literal; hai smoke test
cho kết quả giống hệt nhau, nhưng 13/13 ca khó vẫn timeout. Raw và audit của
hai vòng nằm trong `v29_objective_bound_20261107/` và
`v30_deterministic_assumptions_20261107/`. V30 được giữ vì tính tái lập,
không được xem là tăng hiệu năng.

**V31 (08-11-2026) tắt core exhaustion và cũng không có gain.** Bốn ca
`infsteps180` và chín ca `cont` còn lại đều timeout hợp lệ ở 300 giây. Việc
bỏ bốn lần kiểm tra phụ không tạo ca tối ưu mới; coverage vẫn `203/216`.
Archive và kiểm toán ở `results/sat_research/v31_no_core_exhaust_20261108/`.

**V33 giảm tần suất heuristic cũng không có gain.** Lượt chạy đúng alias
AGLR với `aglr_policy=legacy`, `heuristic_period=8` và telemetry đã khóa đủ
13 ca khó ở 300 giây; tất cả timeout hợp lệ, coverage vẫn `203/216`.
Archive ở `results/sat_research/v33_heuristic_period8_20261108/`. Lượt V32
không được tính vì dùng alias không nhận tham số period.

## Trạng thái mới nhất

**V17 đã chạy đủ toàn bộ dữ liệu và qua kiểm tra độc lập:**

| Hàm mục tiêu | Chứng minh tối ưu | PAR-2, timeout 300 giây |
|---|---:|---:|
| `finsteps123` | 72/72 | 0,031 giây |
| `infsteps180` | 68/72 | 34,095 giây |
| `cont` | 63/72 | 80,071 giây |
| Tổng | **203/216** | — |

Trên cùng 31 ca khó ở 300 giây, V17 đạt **18/31**, Journal **17/31**,
CSOnet **16/31**; không mất ca nào mà hai đối chứng đã giải. So với Journal,
ca giải thêm là `trackB12/cont`, chi phí 15.182. Toàn bộ 216 JSON được
kiểm tra lại trên máy local; nghiệm hợp lệ và các dòng tối ưu có
`cost=lb=ub`. Khi hoàn tất dataset, giữ nguyên 31 ca đã đo, chỉ chạy mới
185 ca còn thiếu. Dữ liệu, mã kiểm toán và hash đã push trong
`results/sat_research/core_exhaustion_v17_20261107/full_216/`.

Nếu chỉ tính những nghiệm được chứng minh trong 120 giây, V17 còn
**(72,68,62), tổng 202**; `origB11/cont` mất 197,59 giây nên không được tính
ở mốc 120 giây. Bảng hội nghị được tái sử dụng cho Journal (72,68,59),
CSOnet (72,68,60), Gurobi (72,67,67). Như vậy đã có tiến bộ so với hai
mốc MaxSAT, nhưng chưa vượt tổng 206 của Gurobi ngay ở mốc 120 giây.
Không so trực tiếp PAR-2 của bảng 120 với bảng 300 giây. Đối chứng cùng
300 giây và xác nhận các ca quan trọng vẫn cần hoàn tất trước bảng chính.

**V18 và V19 đã hoàn tất, chưa giải thêm ca:**

| Phép thử trên 13 ca V17 chưa giải | Số ca đã chạy | Giải thêm | Kiểm toán |
|---|---:|---:|---|
| V18: cấm chu trình thứ tự có thời gian dương | 13/13 | 0 | Đạt |
| V19: tách chi phí bắt buộc của lịch sớm nhất | 13/13 | 0 | Đạt |

Đã tải về toàn bộ JSON và log, xác minh hash rồi dựng lại báo cáo độc lập.
Cả 26 ca đều timeout hợp lệ ở 300 giây, không có lỗi lịch hoặc chi phí.
V19 đã qua **65 test Rust, 96 test Python**, hai lịch có optimum 5526 và
kiểm tra timeout native. Lưu dữ liệu trong `complete_13/` của từng thư mục
`order_cycles_v18_20261107/` và `initial_cost_v19_20261107/`, thuộc
`results/sat_research/`. Không cộng các phép thử này vào coverage V17.

SAT vẫn dùng gần hết 300 giây mỗi ca. V18 đã cấm nhiều chu trình nhưng
chưa khép khoảng cách giữa cận và nghiệm. Tách chi phí V19 cũng chưa giúp
chứng minh thêm optimum. Bảng `v18_v19_diagnostics.csv` giữ các số đo và
cận đọc từ log; các cận này chỉ dùng chẩn đoán, không sửa JSON gốc.

**V20 và V21 đều đã hoàn tất 13/13 ca, chưa giải thêm.** Toàn bộ 26
kết quả đã tải về, xác minh hash và kiểm toán độc lập; đều timeout hợp lệ.
Dữ liệu ở `complete_13/` trong `order_paths_v20_20261107/` và
`order_paths_full_v21_20261107/`, thuộc `results/sat_research/`.

Gửi toàn bộ điều kiện giảm tổng lời gọi SAT trên 13 ca từ **297.623**
(V20) xuống **60.813** (V21), nhưng vẫn không tăng coverage. Hai lượt tạo
16.137 và 21.386 mệnh đề đường đi; thời gian phân tích đường đi lần lượt
6,19 và 8,49 giây trong cả bộ ca. Phần lớn thời gian còn nằm ở SAT. Các
số đo và cận chẩn đoán được giữ trong `v20_v21_diagnostics.csv`, không sửa
JSON gốc. Timings của sàng lọc song song được giữ riêng.

**V22 đã cài và qua 76 test Rust, 106 test Python, nhưng dừng ở thử
nhanh trước ca khó.** `origA1/finsteps123` chứng minh đúng cost=LB=UB=11
ở 18,72 giây; `origA1/infsteps180` timeout hợp lệ ở 30 giây. Controller
dừng trước sàng lọc, nên không ghi thành 0/13. Hai bản ghi đã kiểm toán
độc lập trong `results/sat_research/order_master_v22_20261107/stopped_validation/`.

Biểu diễn V22 để SAT chọn đủ các thứ tự và đồ thị tính lịch, chỉ thêm
ngưỡng ở lần đi qua có chi phí; vẫn dùng RC2 của CSOnet. Số đo cho thấy
nhiều mốc thời gian khác nhau cùng mang một mức phạt bậc thang.

**V23 đã qua 77 test Rust và 107 test Python, nhưng cũng dừng tại thử nhanh:** với mỗi mức chi phí c, dùng mốc đầu tiên
đạt c thay vì mốc thời gian bất kỳ trên cùng bậc. Ví dụ hàm làm tròn
180 giây: thời điểm 200 và 280 đều có mức phạt 2, cùng dùng mốc 181
khi aimed=0. Mọi mệnh đề vẫn được chứng minh bởi đường thời gian và giữ
đúng chi phí. Chỉ thay cách dùng chung mốc trên V22, chưa đổi lịch gửi
điều kiện hay tham số RC2. Cờ mặc định tắt. Native đạt 77 test Rust và 107 test Python. Mã
`d8e2509`, dịch vụ `maxsat-master-levels-v23.service`, bắt đầu **13:34:56
ngày 07/11**, giờ Việt Nam. Worktree riêng
`~/projects/master-levels-v23/maxsattrainscheduling`. Smoke `finsteps123` chứng minh đúng cost 11 ở 27,78 giây, nhưng
`infsteps180` timeout hợp lệ ở 30 giây. Chưa chạy ca khó; cùng 300 giây, 6.000.000 KB và tối đa 6 giờ mỗi vòng.

**V24 đã dừng trước ca khó.** Dùng nguyên binary V23 và chỉ gửi đủ điều
kiện chi phí, V24 chứng minh đúng optimum hai bài thử: finsteps123=11 ở
15,62 giây, infsteps180=34 ở 13,73 giây. Bài cont timeout hợp lệ ở 30 giây.
Cả ba bản ghi được kiểm toán độc lập và lưu trong
`results/sat_research/master_full_v24_20261107/stopped_validation/`.
Không có lượt hard-case nào của V24, nên không ghi thành 0/13.

**V25 đã xong 4/4 ca infsteps180, chưa giải thêm.** Runner `7b752c4`
giữ nguyên binary V24; mọi ca timeout hợp lệ ở 300 giây. Toàn bộ raw,
nguồn binary, phạm vi chọn ca và hash đã được kiểm toán độc lập trên local,
lưu tại `results/sat_research/master_rounded_v25_20261107/complete_4/`.
Không có gain nên không chạy xác nhận hoặc hồi quy; báo cáo followup không
được hiểu là PASS. Hai lần lỗi thiết lập ban đầu được giữ riêng cùng probe.

Trên trackA11, V25 tạo 132.265 đường trong 300 giây, với cận chẩn đoán
LB=30, UB=244; khoảng 144,56 giây SAT và 148,61 giây phân tích đồ thị.
Các cận đọc từ stdout được để riêng trong CSV, không sửa JSON gốc. Số
đường và thời gian đồ thị cho thấy cần giảm số lần giải lại và đưa thêm
thông tin chi phí vào SAT sớm hơn; chưa có bằng chứng coverage mới.

**V26 đã hoàn tất 13/13 ca, chưa giải thêm.** Mọi kết quả là timeout hợp
lệ ở 300 giây, đã tải về và kiểm toán độc lập, gồm đủ bốn ca bậc thang
và chín ca liên tục. Raw và hash tại
`results/sat_research/master_batch_v26_20261107/complete_13/`.
Không có gain nên followup không chạy xác nhận/hồi quy và không báo PASS.

Việc thêm nhiều điều kiện một lúc đã giảm thời gian đồ thị: trackA11/
infsteps180 có 5.642 lời gọi SAT, 5,74 giây đồ thị, so với 134.327 và
148,61 giây của V25. Nhưng SAT vẫn dùng 293,64 giây, chưa chứng minh
optimum. Với các ca cont, mô hình có khoảng 0,94--4,10 triệu biến và
4,56--13,99 triệu mệnh đề. Giảm chi phí kiểm tra đồ thị chưa khắc phục
được quy mô mô hình còn lớn. Cần kiểm tra thêm cách biểu diễn chi phí. CSV diagnostics giữ riêng cận đọc từ stdout;
không điền counter hoặc cận thiếu vào JSON gốc.

**V27 đã qua 79 test Rust, 113 test Python trên VM và đã chạy đủ bốn ca infsteps180, đều timeout hợp lệ và chưa có gain.
Raw/audit ở `master_seeds_v27_20261107/complete_4/`. Solver source `c1b046f`; sàng lọc bắt đầu 15:37:45 ngày
07/11, giờ Việt Nam. Ba bài thử origA1 có đúng cost=LB=UB: finsteps123=11
ở 0,043 giây, infsteps180=34 ở 0,089 giây, cont=5526 ở 0,170 giây. Đây
là kết quả bài thử dễ, chưa phải bằng chứng tăng coverage trên ca khó.
Mốc thời gian và mệnh đề khởi tạo được chia sẻ đúng như công thức đã cài.
Native timeout probe cũng đạt. Không đổi binary trong lượt đang chạy.

**V28 đã hoàn tất đối chiếu backend cùng binary.** Runner `9f32564`
giữ nguyên phương pháp V27, chạy MiniSAT và CaDiCaL trên cùng bốn ca.
Hai backend dùng cùng ngân sách: bốn lượt thu gọn, bốn lượt tăng cận,
bỏ giới hạn xung đột riêng (giá trị 0), mỗi instance vẫn 300 giây. Giới
hạn 100 chỉ được adapter MiniSAT áp dụng nên không giả định hai backend
đã có cùng giới hạn khi cùng ghi 100. V27 MiniSAT/100 giữ làm đối chứng
riêng; V28 MiniSAT/0 tách tác dụng giới hạn, CaDiCaL/0 tách tác dụng backend.

Hai service `maxsat-master-v28-minisat` và `maxsat-master-v28-cadical`
được pin vào hai nhóm lõi vật lý riêng, cùng 6.000.000 KB. Mỗi service
tối đa 6 giờ kể cả thời gian chờ. Source/binary gốc và hash được giữ;
không rebuild. Runtime song song và followup mang `paired-screen`, chỉ
chẩn đoán. Công cụ so sánh `296199d` kiểm toán lại raw, chặn khác cấu
hình/binary/chi phí, không tuyên bố bên thắng khi dữ liệu còn thiếu.
Kiểm thử công cụ trên local đạt 121 Python. Hướng dẫn sinh viên 5.22
và runbook ghi rõ cách chạy, xác nhận ba lần, hồi quy 68 ca theo objective
và điều kiện trước khi lập bảng full. Mốc full vẫn là 203/216 ở 300 giây.

**V28 đã hoàn tất đối chứng MiniSAT/CaDiCaL.** Cả hai backend chạy cùng
binary V27, cùng bốn ca infsteps180 và cùng ngân sách `core_minimize_checks=4`,
`core_exhaust_checks=0`, `core_minimize_conflicts=0`. Mỗi backend timeout
4/4; comparator độc lập kết luận hòa, không có ca cùng giải để ghép runtime.
Các thời gian smoke đã biết đúng cost nhưng không phải ca khó. Raw/audit
và `paired_comparison.json` ở `master_backends_v28_20261107/`; runtime chạy
song song chỉ là chẩn đoán, chưa đưa vào bảng chính.

**CPLEX baseline đang được kiểm tra lại.** Exporter Big-M đã bỏ trần thời gian
43.200 giây và dùng hệ số động theo release time/tổng travel. Hai vòng đầu
bị loại: một nghiệm CPLEX còn overlap tài nguyên; vòng sau dừng vì test hồi
quy hệ số động chưa đúng. Raw lỗi được giữ riêng, không tính là baseline.
Vòng thứ ba đã qua 3 test exporter và hai ca: `trackA1/finsteps123`
cost=lb=ub=23, `stationB12/infsteps180` cost=lb=ub=98 ở 120 giây.
Đây chỉ là kiểm tra correctness hai ca, chưa phải full CPLEX table; raw và
manifest ở `results/sat_research/cplex_domain_validation_20261107/`.

**`trackB12/cont` của V17 đã xác nhận thành công 3/3 lần.** Mọi lịch đều
hợp lệ và có cost=LB=UB=15.182. Thời gian 10,65; 4,64; 11,86 giây, median
10,65 giây. Đã tải về và kiểm toán lại độc lập. Đây là ca giải thêm so với
Journal trong nhóm 31 cặp. Dùng đúng binary/tham số V17, nhóm lõi vật lý
`2,3,6,7` tách khỏi nhóm V18. Thời gian xác nhận song song chỉ chẩn đoán,
không ghép vào PAR-2 cuối. Dữ liệu ở
`core_exhaustion_v17_20261107/trackB12_confirmation/` trong `results/sat_research/`.

Các phiên bản V17--V28 giữ refinement `legacy`, cải tiến RC2 hoặc ràng
buộc thứ tự, nên chưa dùng kết quả làm bằng chứng cho bộ chọn AGLR thích
nghi. Mốc tốt nhất hiện tại vẫn là **203/216**. Chưa cập nhật Abstract,
Results hoặc Conclusion thành kết luận vượt toàn bộ SOTA.

## Diễn biến V16 và V17 đã hoàn tất

**V16 giải thêm hai ca nhưng mất một ca cũ khi hồi quy.** Hai cấu hình
ngân sách 100 và 1.000 đều đã xong 15/15 ca và qua kiểm toán độc lập.
Ngân sách 100 được chọn theo PAR-2, sau khi cùng giải thêm hai ca.

Sáu lượt xác nhận của cấu hình 100 đều chứng minh lại đúng optimum:

| Ca | Chi phí = LB = UB | Median ba lần xác nhận |
|---|---:|---:|
| `origB11/cont` | 75.494 | 182,25 giây |
| `stationB12/cont` | 16.909 | 5,67 giây |

Đã tải về và kiểm toán độc lập cả sáu lượt. Thời gian thay đổi đáng kể,
nên giữ toàn bộ số đo, không chọn riêng lần nhanh nhất. Thứ tự các điều
kiện cùng trọng số khi lấy từ HashMap là một khả năng gây dao động; chưa
cô lập được nguyên nhân. Dữ liệu xác nhận ở
`results/sat_research/limited_core_v16_20261106/confirmation_complete/`.

Hồi quy trên 16 ca khó mà phương án cũ đã giải được giữ **15/16**. Ca
`stationA9/cont` timeout ở 300 giây, trong khi mốc cũ giải được. Toàn bộ
dữ liệu vẫn hợp lệ, không có nghiệm sai hoặc chi phí mâu thuẫn. Kiểm toán
và bảng coverage ở `limited_core_v16_20261106/regression_complete/`, trong
`results/sat_research/`.

| Trên cùng 31 cặp khó ở 300 giây | infsteps180 / 5 | cont / 26 | Tổng / 31 |
|---|---:|---:|---:|
| Bộ ba cũ | 1 | 15 | 16 |
| CSOnet | 1 | 15 | 16 |
| MaxSAT-Journal | 1 | 16 | 17 |
| V16 ngân sách 100, sau hồi quy | 1 | 16 | 17 |

V16 tăng ròng một ca so với bộ ba cũ và đang hòa Journal trong nhóm này.
Đây là coverage của 31 cặp đã đo, không phải coverage full 72 instance.
Các phép đo thời gian sàng lọc và hồi quy được giữ riêng điều kiện chạy.

**V17 đã xong và qua kiểm toán đủ 14 ca:** khôi phục `stationA9/cont`
ở 45,46 giây, chi phí 7.655; 13 ca còn lại vẫn timeout. Dữ liệu ở
`results/sat_research/core_exhaustion_v17_20261107/complete_14/`.
Chỉ thêm bước thử tăng cận ngay trên core, tối đa bốn lần có ngân sách;
chỉ tăng cận sau chứng minh UNSAT. Cấu hình giữ
`aglr_policy=legacy`, biến thứ tự và quy tắc bộ ba; thành phần thay đổi
nằm trong RC2.

Solver `43cae76` đã qua **56 test Rust**, ba lịch nhỏ có optimum 5526 và
kiểm tra timeout trên VM. Runner `438129f` qua **90 test Python**, dùng
lại binary đã kiểm tra, hash
`ca8fef89fb275803ec1934950f509dab2e4e1bf42321a01e7e9d2df18d9f0a88`.

Lượt chuẩn bị `maxsat-core-exhaust-v17.service` dừng ở cổng hồi quy vì mất
`stationA9`, trước khi chạy V17 trên ca khó. Sau khi kiểm toán đủ 16 ca,
runner mới đưa ca mất vào danh sách chưa giải và tiếp tục bằng dịch vụ
`maxsat-core-exhaust-v17-followup.service`, bắt đầu lúc **01:36:12 ngày
07/11**, giờ Việt Nam. Mỗi ca 300 giây, cả vòng tối đa khoảng 6 giờ. Script
và hash ở `results/sat_research/core_exhaustion_v17_20261107/`.

**Đánh giá 31 cặp khó đã hoàn tất:** giữ nguyên 14 ca đầu và đo thêm
17 ca, đạt 18/31. Sau đó đã hoàn tất 216 cặp bằng cách chỉ đo thêm 185 ca.
Hai bản chụp `complete_31/` và `full_216/` đã qua kiểm toán độc lập. Lượt
full kết thúc lúc **07:56:57 ngày 07/11**, giờ Việt Nam.

Telemetry cho thấy bước tăng cận có hoạt động ở một số ca `cont`, nhưng
không tăng cận lần nào trên bốn ca `infsteps180` hoặc ca `stationA9` vừa
khôi phục. Vì vậy chưa quy kết việc khôi phục chỉ cho cơ chế tăng cận.
Hướng dự phòng về chu trình thứ tự được ghi trong
`research_note_order_cycles_vi.md`; mã đã cài và kiểm thử; V18 chưa có kết quả hiệu năng khi khởi chạy.

Hướng dẫn sinh viên bản 5.18 có công thức, ví dụ và lệnh chạy hiện tại.
Bản thảo COR giữ số liệu chính cho đến khi hoàn tất kiểm tra và đánh giá full.

## Chi tiết các lượt V16 và đối chứng backend

**Đối chứng hai backend đã hoàn tất: 186/186 ca hợp lệ.** Lượt V14 kết
thúc lúc 22:33:58 ngày 06/11, giờ Việt Nam. Đã lấy dữ liệu về máy local và
kiểm toán lại độc lập; không có lỗi lịch hoặc chi phí. Giữ nguyên 174 ca
đã chạy đúng, chỉ đo mới 12 ca còn thiếu. Dữ liệu và bảng cuối nằm ở
`results/sat_research/backend_comparison_20261106/complete_186/`.

| Phương pháp | infsteps180, MiniSAT | infsteps180, CaDiCaL | cont, MiniSAT | cont, CaDiCaL |
|---|---:|---:|---:|---:|
| Bộ ba (Orders-Transitive) | 1/5 | 1/5 | 15/26 | 14/26 |
| CSOnet | 1/5 | 1/5 | 15/26 | 14/26 |
| MaxSAT-Journal | 1/5 | 1/5 | 16/26 | 12/26 |

MiniSAT giải được nhiều ca `cont` hơn ở cả ba phương pháp, nên vòng kế
tiếp giữ MiniSAT. Ở `infsteps180`, coverage bằng nhau; CaDiCaL có PAR-2
thấp hơn với CSOnet và Journal. Chưa có căn cứ nói một backend luôn nhanh
hơn. Đây là kết quả trên nhóm khó, chưa phải full 72 instance hoặc thắng SOTA.

**V15 dừng sau hai timeout hợp lệ và một lượt lỗi.** Hai ca `trackA11` và
`trackA12` của `infsteps180` chưa chứng minh tối ưu. Ca thứ ba,
`stationA11/infsteps180`, bị ngắt từ bên ngoài với mã 124; 12 ca còn lại chưa
chạy. Không ghi lượt này thành 0/15. Bản chụp và kết quả kiểm tra ở
`results/sat_research/core_minimization_v15_20261106/stopped_2/`.

**V16 giới hạn công việc của từng lần thử thu gọn core.** Mỗi core vẫn
được thử thêm tối đa bốn lần. Có hai cấu hình, chỉ khác ngân sách của mỗi
lần thử: 100 hoặc 1.000 xung đột SAT. Nếu ngân sách hết mà chưa có kết luận,
giữ tập mâu thuẫn đã chứng minh trước đó. Ngân sách này không áp dụng cho
lời gọi SAT chính. Mọi lời gọi SAT cùng chịu timeout 300 giây của instance,
được MiniSAT kiểm tra ngay trong quá trình tìm kiếm.

Hai cấu hình chạy song song trên hai nhóm lõi vật lý riêng, dùng cùng mã
`57aa220` và cùng binary. Chỉ chạy **15 cặp chưa giải được** của phương án
bộ ba: 4 `infsteps180`, 11 `cont`; dùng lại toàn bộ đối chứng đã có. Nhánh
1.000 bắt đầu lúc 23:40:53, nhánh 100 lúc 23:53:12 ngày 06/11, giờ Việt Nam.
Mỗi ca có 6.000.000 KB RAM; mỗi vòng tối đa 6 giờ. Trước khi chạy, 54 test
Rust, 69 test Python, ba kiểm tra lịch nhỏ và kiểm tra dừng SAT đều đạt.

Lệnh chạy và cách đọc báo cáo ở `experiment_runbook_vi.md`; thông tin
khởi chạy ở `results/sat_research/limited_core_v16_20261106/`. Khi có ca
mới, phải xác nhận lại và kiểm tra các ca cũ trước khi đánh giá full.
Không ghép kết quả các cấu hình để công bố coverage của một phương pháp.

**Tín hiệu đầu tiên, bản chụp lúc 00:12:48 ngày 07/11:** nhánh 1.000 đã
xong 6/15, nhánh 100 xong 3/15; cả chín ca đã qua kiểm toán độc lập sau
khi tải về. Nhánh 1.000 giải được `origB11/cont` ở 153,39 giây, chi phí
75.494 và `cost=lb=ub`. Phương án bộ ba cũ timeout ở 300 giây. Mô hình mới
có 49.890 biến, so với 66.414 ở lượt cũ; đã bỏ được 2.905 điều kiện khỏi
các core. Tuy nhiên CSOnet và Journal đã giải được ca này. Đây là tiến
triển của phương án mới, chưa phải thắng SOTA hoặc kết quả full.
Dữ liệu gốc, hash và báo cáo độc lập ở `limited_core_v16_20261106/progress_6_3/`
trong thư mục `results/sat_research/`.

Đã xếp hàng bước xác nhận bằng dịch vụ `maxsat-core-v16-confirm-v2.service`,
bắt đầu chờ lúc **00:19:10 ngày 07/11**, giờ Việt Nam. Sau khi hai cấu hình
hoàn tất và qua kiểm toán, chọn một cấu hình theo coverage rồi PAR-2 và chạy
lại ba lần các ca giải thêm, tuần tự. Dùng nguyên binary V16; không chạy
thêm SAT trong lúc hai lượt còn hoạt động. Công cụ đã qua 82 test Python
trên VM. Thông tin và script ở `limited_core_v16_20261106/confirmation_queue.json`
và `run_confirmation_after_trials.sh`. Đây là trạng thái xếp hàng, chưa có
kết quả xác nhận.

Bản chụp tiếp theo lúc **00:22:31 ngày 07/11** cho thấy nhánh 100 cũng
giải được `origB11/cont`, ở **114,71 giây**, cùng chi phí 75.494. Đã tải
về và kiểm toán độc lập đủ 6 ca trong bản chụp của nhánh này. Dữ liệu ở
`results/sat_research/limited_core_v16_20261106/c100_first_gain/`.
Đợi đủ hai lượt để chọn cấu hình; chưa coi phép đo một lần là kết quả xác
nhận hoặc cải thiện trên toàn bộ dataset.

## Lịch sử trước lượt V16

Các đoạn dưới ghi trạng thái tại từng thời điểm trước đó. Trạng thái mới
nhất và vị trí dữ liệu cuối nằm ở phần trên.

**Đã lấy và kiểm toán 174/186 ca:** MiniSAT xong 93/93; CaDiCaL xong 81/93
rồi bị ngắt từ bên ngoài ở Orders-Transitive/stationA12/infsteps180. Giữ
nguyên dữ liệu và lỗi ở `results/sat_research/backend_comparison_20261106/progress_174/`.
174 ca có receipt đều hợp lệ; ca lỗi không được đổi thành timeout bình thường.

Trên cùng 25 ca cont: bộ ba đạt 15/25 với MiniSAT và 14/25 với CaDiCaL;
CSOnet 15/25 và 14/25; Journal 16/25 và 12/25. Chưa đủ để chốt backend
cuối cùng hoặc tuyên bố vượt SOTA. Đây là số liệu nhóm khó, không phải full.

V14 đã sửa việc dừng truy vấn SAT bên trong CaDiCaL. 49 test Rust, 67 test
Python và sáu ca smoke native đều đạt trên VM. Thử lại ca khó với hạn ngắn
đã trả `timeout`, mã thoát 0 và xác nhận bộ đếm trong SAT thực sự kích hoạt.
Lượt `maxsat-backends300-v14-1908b22.service` bắt đầu lúc **21:45 ngày 06/11**,
giữ lại toàn bộ 174 ca và chỉ chạy 12 ca thiếu. Ca gây lỗi trước đó đã hoàn
tất thành timeout hợp lệ ở vòng mới; tiến độ đã lên 175/186.

Nhánh MiniSAT chuyển sang V15: thử thu gọn core, tối đa bốn kiểm tra mới,
trên đúng 15 cặp chưa giải của phương án bộ ba (4 infsteps180, 11 cont).
Không chạy lại baseline hoặc các ca đã giải. Mã script và lựa chọn có 68
test Python đạt; kết quả chưa có để kết luận hiệu năng. Xem runbook để chạy
và đọc `core_minimization_audit.json`.

**Hai backend chạy song song theo yêu cầu mới.** Dùng
`run_sat_backend_comparison.sh` để thử MiniSAT và CaDiCaL với cùng ba phương
pháp MaxSAT và 31 cặp khó, timeout 300 giây: tổng 186 ca SAT. Dùng lại các ca
đã hoàn tất; chỉ chạy phần còn thiếu. Hai nhóm CPU không chung lõi vật lý:
MiniSAT `0,1,4,5`, CaDiCaL `2,3,6,7`; mỗi nhánh có 2 lõi thật và giới hạn
6.000.000 KB RAM mỗi ca. Không chạy thêm MILP trong vòng chọn backend này.

Các ca chạy mới dùng cùng binary từ `4a43a9c`. Các ca nhập lại giữ nguồn,
hash và thời gian cũ; bản mã khác nhau được chấp nhận để sàng lọc theo quyết
định trước của nhóm. Bảng cùng binary/song song được tách riêng. So coverage
trên các ca chung trước, rồi PAR-2; xác nhận runtime tuần tự khi khóa cấu hình.
Lượt mới bắt đầu lúc **18:07 ngày 06/11/2026 (giờ Việt Nam)**, dịch vụ
`maxsat-backends300-v13-fabcc5a.service`, worktree `~/projects/backends-v13/maxsattrainscheduling`.
Đã nhập 54 ca MiniSAT và 15 ca CaDiCaL, còn 117 ca chạy mới. 65 test Python
và sáu smoke test native chạy đồng thời đạt trên VM; cả sáu chứng minh
optimum 5526 của origA1/cont. CPU affinity của hai tiến trình thực tế cũng
đã được kiểm tra. Bản auditor chỉ đọc bổ sung sau đó có 66 test đạt.
Thông tin khởi chạy ở `results/sat_research/backend_comparison_20261106/launch.json`.

**Đối chiếu lại CSOnet và SOTA:** CSOnet dùng RC2 được cài trong Rust;
mã `c427a10` gọi MiniSAT bên trong. Bài COR gốc có bản tiền ấn phẩm của tác
giả ghi RC2 + MiniSat 2.1.0, và mã công khai cũng dùng MiniSAT. RC2 là thuật
toán tối ưu, không phải tên thay thế MiniSAT/CaDiCaL ở tầng SAT. Bằng chứng
và cách so sánh ở `reviews/solver_stack_20261106/README.md`.

Lượt MiniSAT vẫn có giá trị làm mốc theo mã hiện có; không loại kết quả
chỉ vì backend này. Lượt CaDiCaL đang chạy là **đối chứng đổi SAT backend
cho cả ba phương pháp MaxSAT**, không phải tái tạo cấu hình gốc của CSOnet.
So cải tiến phương pháp trong cùng backend; đo riêng việc đổi backend bằng
cùng phương pháp. Không thay đổi plan hoặc binary đang chạy.

**Điều chỉnh backend theo yêu cầu mới:** dừng chiến dịch MiniSAT sau
91/155 lượt hoàn tất và hủy lượt thu gọn core đang chờ. Mã nguồn sinh viên
`c427a10` gọi MiniSAT cho MaxSAT-Default; bản hội nghị chỉ ghi RC2, chưa xác
minh được backend của binary đã tạo bảng. Những lượt MiniSAT được giữ làm
mốc theo mã nguồn, không gọi là tái tạo chính xác binary CSOnet.

Đã bổ sung CaDiCaL thật cho SC/AGLR và MaxSAT-DDD, sửa alias `maxsat_ddd_cdc`,
ghi chữ ký runtime và kiểm tra chữ ký trong auditor. Kế hoạch mới ở
`results/sat_research/cadical_300_20261106/plan.json`: cả ba phương pháp MaxSAT
dùng CaDiCaL, cùng 31 cặp và timeout 300 giây; chưa bật thu gọn core.
Dùng lại 37 kết quả MILP đã kiểm toán, chạy mới 93 ca SAT và 25 ca MILP còn
thiếu. Không đổi nhãn hoặc thời gian của dữ liệu MiniSAT thành CaDiCaL.

Chiến dịch CaDiCaL bắt đầu lúc **17:33 ngày 06/11/2026 (giờ Việt Nam)**,
từ commit `4a43a9c`, dịch vụ `maxsat-cadical300-v12-4a43a9c.service`.
Trước khi chạy, 46 kiểm thử Rust, 59 kiểm thử Python, kiểm tra Bash và build
release đều đạt. Cả năm phương pháp cùng giải đúng origA1/cont với optimum
5526; ba phương pháp MaxSAT ghi chữ ký native `cadical-1.9.5`.
Thư mục VM: `~/projects/cadical-v12/maxsattrainscheduling/results/aglr/cadical300-v12-4a43a9c/`.
Tối đa ba vòng, mỗi vòng tối đa 6 giờ, chạy tuần tự và tiếp tục từ checkpoint.
Thông tin khởi chạy ở `results/sat_research/cadical_300_20261106/launch.json`.
Đây là trạng thái khởi chạy, chưa có kết quả để kết luận CaDiCaL tốt hơn.

Bản chụp **82/155 lượt ở 300 giây** đã được lấy về và kiểm toán độc lập:
không có lỗi lịch hoặc chi phí mâu thuẫn. Trên cùng 16 cặp cont đã hoàn tất
đủ năm phương pháp, bộ ba V5 đạt 10/16, CSOnet 10/16, MaxSAT-Journal 10/16,
Gurobi 13/16, CPLEX 13/16. Bộ ba cần 216,23 giây cho stationA9 và 132,12
giây cho trackB12; các baseline SAT cũng giải thêm được ca khi tăng timeout.
Vì vậy chưa vượt SOTA. Dữ liệu nguyên bản và bảng cùng mẫu ở
`results/sat_research/extended_300_20261106/progress_82/`.
Đây là bản chụp giữa chiến dịch, không phải kết quả cuối hoặc coverage full.

Đã chuẩn bị thử nghiệm thu gọn core: tối đa bốn truy vấn bổ sung, ưu tiên
bỏ điều kiện có trọng số thấp, chỉ chấp nhận sau chứng minh UNSAT mới.
Kiểm thử core với MiniSAT/CaDiCaL thật và bài lịch nhỏ vét cạn đã đạt trên
VM trong bộ 46 test. Nếu thử tính năng này sau đối chứng CaDiCaL, chỉ chạy
31 ca candidate ở 300 giây và dùng lại nguyên 124 kết quả baseline đã kiểm
toán ở cùng backend và cutoff. Chưa có kết quả hiệu năng của tính năng này.

Dịch vụ `maxsat-mincore300-v11-86cdc5f.service` từng được xếp hàng lúc
17:15 ngày 06/11 (giờ Việt Nam), nhưng đã hủy trước khi build hoặc chạy SAT
để chuyển sang đối chứng CaDiCaL. Không còn lượt MiniSAT tự động đang chờ.
Trạng thái lúc xếp hàng và thông tin hủy ở
`results/sat_research/extended_300_20261106/mincore_v11_queue.json`.

Theo yêu cầu ngày 06/11, vòng kế tiếp tăng timeout chung lên **300 giây**
cho phương án bộ ba V5 và bốn đối chứng: CSOnet, MaxSAT-Journal, Big-M Gurobi,
Big-M CPLEX. Danh sách mở rộng là hợp những ca các phương pháp chưa giải ở
120 giây: **5 cặp infsteps180, 26 cặp cont**, không chạy finsteps123.
Cả năm phương pháp đều chạy lại cùng 31 cặp, tuần tự, mỗi vòng tối đa 6 giờ.
Kết quả cũ không được đổi nhãn thành kết quả 300 giây. Lựa chọn đã khóa tại
`results/sat_research/extended_300_20261106/plan.json`.

Chiến dịch bắt đầu lúc **14:15 ngày 06/11/2026 (giờ Việt Nam)**, từ commit
`b6a4370`, dịch vụ `maxsat-extended300-b6a4370.service`. Tối đa ba vòng có
checkpoint, mỗi vòng tối đa 6 giờ, không chạy song song. Trước khi chạy:
41 test thư viện Rust, 47 test Python và build release đều đạt; cả năm
solver cùng giải đúng origA1/cont với optimum 5526. Hai cặp đầu đã hoàn tất
đủ năm solver và chưa có lỗi audit; đây là cập nhật lúc khởi chạy, chưa
phải kết quả cuối. Hash binary và đường dẫn VM nằm trong `launch.json` cùng
thư mục kế hoạch. Chưa cập nhật số liệu vào bản thảo COR.

V10 đã được kiểm toán lại độc lập: giả định `full` đạt 0/4 infsteps180 và
0/14 cont; `geometric` đạt 0/4 và 1/14. Không giải thêm ca mới. V9 có một
nghiệm không hợp lệ ở stationB1/cont, đã bị loại và revert; nguyên nhân
chính xác chưa được cô lập. Lưu cả dữ liệu lỗi để truy vết tại
`results/sat_research/rejected_v9_and_assumptions_v10_20261106/`.

Vòng focus `270d1ce` đã hoàn tất và được kiểm toán lại độc lập: infsteps180 giải 0/4, cont giải 2/14 trong nhóm khó; không chạy finsteps123. Dữ liệu ở `results/sat_research/hardening_v8_20261106/`. Đây là kết quả nhóm đã lọc, chưa phải một lượt full của mã mới.

Vòng focus `b7160db` đã hoàn tất và được kiểm toán lại độc lập: infsteps180 giải 0/4, cont giải 2/14 trong nhóm khó; không chạy finsteps123. Dữ liệu ở `results/sat_research/focus_v7_20261106/`. Đây là kết quả nhóm đã lọc, chưa phải một lượt full của mã mới.

| Lượt full 120 giây | finsteps123 | infsteps180 | cont | Tổng |
|---|---:|---:|---:|---:|
| Bộ ba, `eaf0316` | 72 | 68 | 60 | 200 |
| Giới hạn chi phí, `6ba1b71` | 72 | 68 | 59 | 199 |

Hai lượt đều qua audit, chưa vượt mốc hội nghị 200 hoặc Big-M Gurobi 206.
Theo yêu cầu mới, từ nay thử ý tưởng trên nhóm khó theo từng objective:
0 ca finsteps123, 4 ca infsteps180, 14 ca cont. Danh sách gồm mọi ca chưa
giải được trong ít nhất một trong hai lượt này hoặc ở mốc hội nghị; giữ cả
ca mới giải được và ca bị mất. Dữ liệu cũ làm đối chứng, không chạy lại.

Danh sách và hash nguồn ở `results/sat_research/focus_20261106/selection.json`.
Sau Glucose, vòng V8 đã giữ MiniSAT và phương án bộ ba, chỉ thêm quy
tắc loại lựa chọn có trọng số còn lại lớn hơn `UB-LB`. Đã dùng
`CORE_VARIANT=orders-transitive-harden` với
`run_maxsat_focused_experiments.sh`, không tự chạy full. Kết quả nhóm khó
không được ghép với các ca dễ cũ để công bố coverage full của mã mới.

Vòng `maxsat-focus-v7-b7160db` đã bắt đầu trên VM vào sáng 06/11/2026
(giờ Việt Nam), từ mã `b7160db`. Manifest xác nhận backend Glucose,
finsteps123 rỗng, infsteps180 đúng 4 ca, cont đúng 14 ca. Không có lượt full
được xếp tự động sau vòng này. Đã qua 36 test thư viện Rust, 40 test Python,
kiểm tra Bash và build release trên VM; tài liệu LaTeX biên dịch không tràn
lề. Thư mục kết quả:
`~/projects/experiment-audit/rounds/maxsat-focus-v7-b7160db/`.

Quy tắc hardening đã qua 41 kiểm thử thư viện Rust trên VM, gồm bảo toàn
mọi phép gán trong ngân sách, điểm biên bằng ngân sách, phần trọng số còn
lại sau xử lý core, và các bài lịch nhỏ vét cạn trên ba objective với cả
MiniSAT/Glucose. Bài hai tàu xác nhận thực tế có điều kiện chi phí được cố
định và optimum vẫn đúng. 41 kiểm thử Python và build release đã đạt.
V8 đã chạy trên nhóm 18 cặp ở 120 giây và chưa tăng coverage.

Vòng `maxsat-harden-v8-270d1ce` đã bắt đầu trên VM sáng 06/11/2026, từ
mã `270d1ce`. Config xác nhận MiniSAT, bộ ba và residual hardening bật,
objective bound nhị phân tắt; vẫn chỉ có 4 ca infsteps180 và 14 ca cont.
Thư mục: `~/projects/experiment-audit/rounds/maxsat-harden-v8-270d1ce/`.
Mã, kiểm thử, hướng dẫn và kết quả cuối đã push; xem phần cập nhật đầu tài liệu.

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

Vòng `fb85033` đã xong. Ở 30 giây, legacy/full/geometric lần lượt đạt
`(24,22,17)`, `(24,22,17)`, `(24,22,18)`. Cả full và geometric chỉ đạt
`(24,22,18)` khi tăng lên 120 giây, dưới mốc `(24,22,20)`. 360 kết quả đều
qua audit; không chạy full hướng này. Dữ liệu và manifest đã lưu trong
`results/sat_research/core_v1_20261105/`.

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

Đã chuẩn bị phép thử thứ ba: dùng chung biến thứ tự qua các mốc của một cặp
xung đột. Chỉ tạo biến cho cặp đã xung đột; refinement CSOnet, cách gửi điều
kiện và cây chi phí cũ được giữ làm đối chứng. 31 Rust tests đã qua, gồm
bảng chân trị tương đương mệnh đề cũ ở một mốc, tính đúng khi dùng nhiều
mốc và bài lịch tàu nhỏ vét cạn. Chỉ chạy sau khi xem kết quả vòng chi phí.

Vòng chi phí `27b6859` đã kết thúc. Cách mã hóa thưa đạt `(24,22,19)` ở
120 giây trên tập phát triển, dưới mốc `(24,22,20)`; không chạy full. Bản
đối chứng legacy ở 30 giây là `(24,22,17)`, sparse cũng `(24,22,17)`. Mọi
JSON đã qua audit. Dữ liệu nằm trong `results/sat_research/cost_v2_20261105/`
và `core_selection.json` ghi quyết định không chọn cấu hình.

Vòng orders `be60148` đã chạy full vì promote đạt `(24,22,20)`. Full đạt
`(72,68,59)`, tổng 199; mốc hội nghị là tổng 200. Vì thiếu một instance
`cont`, chưa chạy ba lượt xác nhận và chưa đưa số vào bài. Dữ liệu raw nằm
trong `results/sat_research/orders_v3_20261105/`. Vòng kế tiếp thử orders
ghép với cây chi phí thưa, giữ mọi thành phần khác cố định.

Vòng kết hợp `7a1aa6d` đã xong: promote đạt `(24,22,20)`, nhưng full vẫn
chỉ đạt `(72,68,59)`. PAR-2 full lần lượt là `0.02984`, `14.36371`,
`46.92008` giây. Mọi lịch, chi phí, cận và mã thoát đều qua kiểm tra.
Không chạy xác nhận vì chưa vượt coverage hội nghị. Dữ liệu nằm trong
`results/sat_research/hybrid_v4_20261105/`.

Đã bổ sung các gói dữ liệu raw và bảng CSV của vòng cost_v2/orders_v3 vào
đúng thư mục Git; trước đó chúng nằm ở thư mục cha của repository. Hash
đều khớp báo cáo ban đầu. Không cần chạy lại các thí nghiệm này.

Vòng tiếp theo thêm điều kiện bắc cầu cho bộ ba biến thứ tự đã có, không
tạo hàng loạt cặp mới. Giữ orders, chi phí cũ và giả định `legacy` để đo
riêng tác động. 35 kiểm thử thư viện Rust và 31 kiểm thử Python đã qua,
release build thành công. Chưa có số liệu hiệu năng của cơ chế bộ ba.

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

Vòng bộ ba `eaf0316` đã kết thúc; bảng và dữ liệu raw ở
`results/sat_research/transitivity_v5_20261105/`. Đã kiểm tra
35 test thư viện Rust và 32 test Python cho phương án giới hạn chi phí;
mã đã push tại `6ba1b71`. Phương án này được xếp sau vòng bộ ba,
mỗi vòng có giới hạn 6 giờ và full chạy tuần tự. Chưa kết luận vượt SOTA.
