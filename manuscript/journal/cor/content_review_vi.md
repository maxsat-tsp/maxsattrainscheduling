# Rà soát nội dung bản thảo COR

**Tệp:** `manuscript/journal/cor/main.tex`

**Ngày cập nhật tình trạng thực nghiệm:** 07-11-2026

**Trạng thái:** chưa đủ căn cứ kết luận vượt toàn bộ SOTA. Kết quả full tốt
nhất là V17 `(72,68,63)` ở 300 giây, đã kiểm toán đủ 216 ca. V17 cải tiến
RC2/ràng buộc thứ tự trên nhánh refinement legacy, không phải bằng chứng
hiệu quả của bộ chọn AGLR trong Methods hiện tại.

**Mốc mới ngày 07-11-2026:** trên cùng 31 ca khó ở 300 giây, V17 giải
18, Journal 17, CSOnet 16; không mất ca so với hai đối chứng MaxSAT. Tính
ở 120 giây, V17 đạt `(72,68,62)`, tổng 202; bảng Gurobi hội nghị là
`(72,67,67)`, tổng 206. Vì vậy chưa dùng kết quả này để viết rằng đã vượt
mọi baseline. Bộ MiniSAT/CaDiCaL đã có đối chứng chung cho ba phương
pháp; giữ RC2 và SAT backend là hai thành phần khác nhau.

V18--V21 hoàn tất 13 ca chưa giải mỗi lượt, chưa tăng coverage. V22--V24
dừng tại bài thử thật trước ca khó; lịch tối ưu trả về đều qua kiểm tra.
V25 đã xong bốn ca infsteps180, đều timeout hợp lệ và chưa có gain. V26
đã xong 13/13 ca và kiểm toán độc lập, chưa tăng coverage. V27 đã qua
79 test Rust và 113 Python trên VM, đã chạy đủ bốn ca infsteps180
nhưng chưa giải thêm ca nào. V28 đã chạy xong 4/4 ca cho cả MiniSAT và CaDiCaL; đều timeout hợp lệ,
không có gain và kết luận backend hòa. Runtime song song vẫn chỉ chẩn đoán;
không dùng trong bảng thời gian chính.
V28 tắt đường tăng cận MiniSAT-only để hai backend thực sự dùng cùng ngân sách.
Số liệu tạm thời không thay thế bảng full. Chi tiết, công thức và lệnh
chạy nằm trong `../experiment_progress_vi.md`, `../experiment_runbook_vi.md`
và hướng dẫn sinh viên phiên bản 5.22.

Theo yêu cầu đã chốt, runtime hội nghị có thể dùng theo giả định cùng
phần cứng, bỏ qua khác biệt nhỏ về phiên bản; vẫn giữ rõ nguồn và timeout.
Đây là cập nhật quy tắc sử dụng số liệu, không suy đoán metadata còn thiếu.
Abstract, Results, Conclusion trong main.tex chưa sửa trong đợt này.

Các mục dưới giữ lịch sử rà soát ngày 05-11; những nhận xét chưa có lượt
chạy hoặc chưa dùng runtime hội nghị được thay thế bởi tình trạng trên.

**Cập nhật thực nghiệm 05-11-2026:** đã chạy screen/promote trên 24 instance
phát triển, tốt nhất `(24,22,19)`. Hai lượt cũ có crash sau khi ghi JSON mà
runner chưa phát hiện; chúng chỉ còn giá trị chẩn đoán. Runner mới kiểm tra mã
thoát thật. Chi tiết nằm trong `../experiment_progress_vi.md`.

Đã sửa mốc theo camera-ready: timeout 120 giây, coverage từng objective không
thấp hơn `(72,68,60)` và tổng ít nhất 201; PAR-2 dùng sau coverage. Bộ JSON
150 giây có `(72,68,58)` là dữ liệu chẩn đoán khác với số đã công bố. Chế độ
`assumed-equivalent` ghi rõ giả định cùng phần cứng khi dùng runtime hội nghị.
Chưa sửa Abstract, Results hoặc Conclusion theo các số thử nghiệm này.

## Kết luận hiện tại

Bản thảo đã tách rõ đóng góp hội nghị và hướng mới. AGLR hiện là một thuật toán
cụ thể, có công thức, quy tắc hòa, điều kiện chống chờ vô hạn và ba chế độ đối
chứng. Phần Methods không còn mô tả một mô hình utility dự kiến chưa được cài.

Bản thảo vẫn chưa sẵn sàng để nộp vì Abstract để trống, phần Results chưa có
chiến dịch AGLR và Conclusion chỉ được phép ghi trạng thái tạm thời. Đây là chủ
ý đúng: không được biến kết quả RC2+B+R cũ thành bằng chứng cho AGLR.

Kết quả CSOnet của bài hội nghị đã được nhập từ commit dữ liệu `c427a10` và
kiểm tra độc lập. Số instance tối ưu đã xác nhận là 72/72, 68/72 và 58/72. Toàn
bộ 198 lịch `ok` hợp lệ và có `cost=lb=ub`. Các chi phí này được dùng làm mốc
phát hiện lỗi hồi quy. Thời gian chạy chưa được dùng trong bản thảo vì thiếu
thông tin máy và hash của tệp chạy.

## Những phần đã đạt

- Tên tác giả đã dùng **Vinh Quang Do** và email `25020428@vnu.edu.vn`.
- Introduction giải thích nút thắt tăng mô hình trước khi đưa công thức.
- Related Work phân biệt MaxSAT-DDD trước đây, bài hội nghị và AGLR.
- Methods khớp với mã ở bốn điểm: khóa ổn định, chi phí tăng biên, điểm ưu tiên
  và bước cứu sau `2W` vòng không tiến bộ.
- Công thức nói rõ `g` là ước lượng tăng chính, không phải tổng số clause CNF.
- Correctness chỉ khẳng định những gì mã bảo đảm: refinement hợp lệ, mỗi vòng có
  tiến triển và xung đột không bị chờ vô hạn.
- Computational Study đã ghi baseline bắt buộc, cách chọn tham số, PAR-2 và quy
  tắc MILP phải có cận dưới bằng cận trên.
- Bảng RC2+B+R được ghi là chẩn đoán và loại khỏi kết luận submission.

## Các điểm chặn submission

| Mức | Vấn đề | Việc cần hoàn tất |
|---|---|---|
| P0 | Phương pháp Methods và bằng chứng tốt nhất chưa cùng một cấu hình. | V17 là cải tiến RC2/legacy; chỉ viết kết luận theo phương pháp đã có kết quả full, hoặc hoàn tất chứng cứ riêng cho bộ chọn AGLR. |
| P0 | Bảng so sánh cùng 300 giây chưa đủ bốn baseline. | Hoàn tất/kiểm toán Journal, CSOnet, Big-M Gurobi và CPLEX tại cùng cutoff; giữ riêng bảng hội nghị 120 giây. |
| P0 | Chưa vượt toàn bộ SOTA theo coverage. | V17 full 203 ở 300 giây, còn Gurobi công bố 206 ở 120 giây; chưa tuyên bố vượt mọi MILP. |
| P0 | V25/V26 chưa có bảng full và xác nhận. | Chạy ca chưa giải; chỉ xác nhận/hồi quy nếu có gain, rồi kiểm toán bảng đủ 216 ca của cấu hình đã khóa. |
| P0 | Abstract và Results chưa có bằng chứng cuối. | Chỉ viết sau khi đủ bảng đối chứng và xác nhận; không dùng kết quả thử nhanh hoặc ghép cấu hình theo từng ca. |
| P1 | CRediT, competing interests, funding và acknowledgements chưa xác nhận. | Các tác giả chốt trước khi nộp. |

## Kiểm tra diễn đạt

Phần mới dùng các từ phổ biến trong tối ưu tổ hợp: *conflict*, *time point*,
*model growth*, *incumbent*, *lower bound* và *refinement*. Mỗi khái niệm được
giải thích ở lần đầu. Các tên nội bộ như `CandidateHistory`, `VisitTime` và tên
trường JSON không đi vào lời văn chính.

Ba chỗ cần giữ cách viết thận trọng khi bổ sung kết quả:

1. Không gọi `g(b|S)` là số clause thực tế. Đây là một ước lượng gồm một clause
   refinement chính và số mốc mới; encoding phụ được đo riêng.
2. Không kết luận nhanh hơn từ median của các tập solved khác nhau. Dùng PAR-2
   cho toàn bộ tập và speedup ghép cặp trên các instance cùng giải được.
3. Không dùng 72 biến thể như 72 mẫu thống kê độc lập. Đơn vị độc lập là 24 base
   case; các lượt lặp là phép đo kỹ thuật.

## Nội dung cần điền sau thực nghiệm

Khi cổng submission đã qua, cập nhật theo thứ tự:

1. Bảng coverage và PAR-2 cho ba objective và mọi baseline.
2. Ablation `legacy` / `all-scanned` / `adaptive`.
3. Bảng hoặc hình về số mốc, biến, clause, vòng DDD và thời gian từng pha.
4. Danh sách instance AGLR được thêm, bị mất hoặc vẫn timeout.
5. Kết quả ba lượt xác nhận cho các instance trên 30 giây hoặc đổi coverage.
6. Abstract, Discussion và Conclusion, mỗi phát biểu đều truy về một bảng hoặc
   hình đã sinh tự động.

Theo cổng mới đã chốt, nếu AGLR giảm coverage của bất kỳ objective nào so với
`(72,68,60)`, hoặc tổng chưa đạt 201, bản thảo vẫn ở trạng thái làm việc. Sau
khi vượt coverage còn phải xác nhận ba lần và bổ sung đầy đủ các baseline.
