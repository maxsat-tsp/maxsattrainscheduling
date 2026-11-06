# CSOnet có dùng RC2 không? Đối chiếu thuật toán và bộ giải SAT

Ngày kiểm tra: 06-11-2026. **Có: CSOnet dùng RC2. Mã nguồn được kiểm tra
gọi MiniSAT bên trong RC2, không gọi CaDiCaL.** Cần sửa cách hiểu rằng dùng
MiniSAT có nghĩa là không dùng RC2. Hai tên chỉ hai công việc khác nhau.

## 1. Hai tầng giải bài toán

RC2 tìm chi phí nhỏ nhất. Khi chưa giải được một tập điều kiện chi phí,
nó lấy nhóm điều kiện mâu thuẫn, cập nhật trọng số và thêm ràng buộc đếm.
SAT solver trả lời câu hỏi: các điều kiện hiện tại có thể đồng thời đúng
hay không? MiniSAT, CaDiCaL và Glucose là các lựa chọn ở tầng này.

Do đó, cần ghi `RC2 + MiniSAT` hoặc `RC2 + CaDiCaL`, thay vì đặt RC2 và
CaDiCaL vào cùng một cột rồi hiểu chúng là hai lựa chọn thay thế nhau.
[Tài liệu RC2 của PySAT](https://pysathq.github.io/docs/html/api/examples/rc2.html)
cũng cho phép chọn SAT solver. Giá trị mặc định của PySAT không chứng minh
mã Rust của bài hội nghị dùng cùng cấu hình.

## 2. Bằng chứng đã kiểm tra

| Nguồn/phương pháp | Tối ưu | SAT bên dưới | Bằng chứng |
|---|---|---|---|
| CSOnet: MaxSAT-Base, SC, Prec, Default | RC2 | MiniSAT trong mã được kiểm tra | PDF camera-ready, trang 7, bảng cấu hình; nhánh `doquangvinh`, commit `c427a10` |
| MaxSAT-DDD của Croella và cộng sự | RC2 | MiniSAT | Bản tiền ấn phẩm của tác giả, mục 5.2, trang 26; mã công khai của tác giả |
| IncSAT-Default, PureSAT-Default của CSOnet | Tìm kiếm tối ưu bằng SAT | Glucose 4.2 theo bài | Bảng cấu hình camera-ready |
| Big-M Gurobi, Big-M CPLEX | MILP | Không áp dụng | Giữ bộ giải MILP tương ứng |
| Ba phương pháp MaxSAT trong lượt VM hiện tại | RC2 trong Rust | CaDiCaL 1.9.5 | Chữ ký native trong cả ba smoke test; manifest khóa backend chung |

**CSOnet.** Bản camera-ready tại
`manuscript/submission/camera_ready_resubmission_20261024/Paper56_final.pdf`
(tính từ workspace TSP) ghi RC2 cho bốn cấu hình MaxSAT. Bản
[tiền ấn phẩm CSOnet trên arXiv](https://arxiv.org/html/2606.16814v1) cũng
ghi RC2, nhưng không chỉ rõ SAT backend của RC2. Trong
[dispatcher ở commit c427a10](https://github.com/maxsat-tsp/maxsattrainscheduling/blob/c427a104c3c6f844e515efb7f898b684553b0f3f/src/main.rs#L767),
`MaxSatDddLadderSc` và `MaxSatDddLadderRC2` đều tạo MiniSAT. Vòng
[tối ưu cùng commit](https://github.com/maxsat-tsp/maxsattrainscheduling/blob/c427a104c3c6f844e515efb7f898b684553b0f3f/src/solvers/ddd/maxsat_ladder_sc/solve.rs#L1288)
thực hiện RC2 có trọng số: lấy trọng số nhỏ nhất trong core, trừ trọng số,
tăng cận dưới và mở rộng totalizer. Đây là bản cài tích hợp trong Rust;
không phải lời gọi `pysat.examples.rc2.RC2` và không mặc nhiên bao gồm mọi
heuristic của bản PySAT. Chưa có metadata độc lập về binary tạo bảng cũ;
nhận định MiniSAT ở đây dựa trên mã, không phải suy đoán từ tên CSV.

**Bài COR gốc.** Bản
[tiền ấn phẩm ngày 14-06-2023 của tác giả](https://luteberget.github.io/preprints/maxsatddd-2023-06-14.pdf#page=26)
ghi RC2 với MiniSat 2.1.0. Cần ghi đúng đây là bản tiền ấn phẩm; PDF xuất
bản năm 2024 trong workspace xác nhận RC2 nhưng không nêu phiên bản SAT
solver trong mục kết quả. Mã
[dispatcher công khai được khóa ở ab9eeebe](https://github.com/luteberget/maxsattrainscheduling/blob/ab9eeebe1608ca9a247fae2f8b346337eb012a6c/src/main.rs#L447)
cũng khởi tạo MiniSAT cho `maxsat_ddd`. Ngay alias `maxsat_ddd_cdc` ở bản
này cũng tạo MiniSAT, nên tên alias không phải bằng chứng dùng CaDiCaL.
Hướng dẫn cài CaDiCaL/UWrMaxSat chỉ cho biết có các thư viện đó; phải theo
đúng đường gọi của solver được chạy để xác định backend thực tế.

Hash tài liệu và mã đã đọc nằm trong [evidence.json](evidence.json).
Các URL mã nguồn đều được khóa theo commit.

## 3. Cách thống nhất thí nghiệm từ đây

1. **Giữ RC2 + MiniSAT làm mốc theo mã SOTA hiện có.** Không bỏ 91 lượt
   đã hoàn tất chỉ vì chúng dùng MiniSAT. Chúng vẫn là kết quả MiniSAT hợp
   lệ ở 300 giây; đây là một chiến dịch chưa hoàn tất, không phải coverage
   full. Giữ nguyên JSON, timeout và hash nguồn.
2. **Lượt CaDiCaL đang chạy là đối chứng đổi SAT backend.** Cả phương pháp
   mới, CSOnet và MaxSAT-DDD đều chạy RC2 + CaDiCaL 1.9.5, cùng danh sách,
   timeout và giới hạn tài nguyên. Không đổi tên kết quả này thành bản
   chạy gốc của CSOnet. Không cần dừng hoặc chạy lại lượt này chỉ để đổi tên.
3. **So sánh phương pháp trên cùng SAT backend.** So phương pháp mới/MiniSAT
   với CSOnet/MiniSAT và Journal/MiniSAT; làm tương tự cho CaDiCaL. Muốn
   đo lợi ích của riêng việc đổi SAT solver, giữ nguyên phương pháp và so
   hai backend trên cùng các ca. Không ghép runtime hai backend thành một
   cấu hình hoặc quy chênh lệch khác backend cho riêng cải tiến mã hóa.
4. **Giữ nguyên đối chứng MILP.** Gurobi và CPLEX tiếp tục dùng bộ giải riêng;
   không chuyển chúng sang RC2. So sánh ở cùng timeout, dataset và tiêu chí
   chứng minh tối ưu. Kết quả MILP phù hợp có thể dùng lại giữa hai lượt SAT.
5. **Giữ rõ cấu hình RC2.** Khi chỉ thử backend, giữ cách gửi điều kiện chi
   phí, thu gọn core, hardening và giới hạn objective như nhau. Lượt hiện tại
   dùng `legacy`, thu gọn core bằng 0, hardening và objective bound tắt.
   Tên solver, commit, SAT backend, chữ ký native nếu có và hash binary phải
   xuất hiện trong hồ sơ thí nghiệm.

Backend chung của lượt hiện tại đã được kiểm tra trong `methods_for(plan)`
và unit test: ba phương pháp đều là `cadical`, hai phương pháp MILP giữ
cấu hình riêng. Auditor từ chối ca CaDiCaL thiếu chữ ký native. Mã đang
chạy được giữ tại `4a43a9c`; tài liệu này không thay đổi binary hoặc plan
của chiến dịch giữa chừng.

Khi lập bảng chính, giữ các dòng SOTA theo cấu hình gốc và ghi đầy đủ cặp
thuật toán/SAT backend cho các dòng mới. Bảng dùng chung CaDiCaL giúp kiểm
tra cải tiến phương pháp có còn hiệu quả khi baseline cũng được đổi backend.
Coverage vẫn là tiêu chí đầu tiên, rồi mới tới PAR-2.
