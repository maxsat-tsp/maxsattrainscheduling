# Tiến độ thử nghiệm trên VM, cập nhật 06-11-2026

## Trạng thái mới nhất

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
