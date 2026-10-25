# Rà soát nội dung bản thảo COR

**Tệp:** `manuscript/journal/cor/main.tex`

**Ngày rà soát:** 25-10-2026

**Trạng thái:** Methods đã khớp với mã AGLR; chưa có kết quả để nộp.

## Kết luận hiện tại

Bản thảo đã tách rõ đóng góp hội nghị và hướng mới. AGLR hiện là một thuật toán
cụ thể, có công thức, quy tắc hòa, điều kiện chống chờ vô hạn và ba chế độ đối
chứng. Phần Methods không còn mô tả một mô hình utility dự kiến chưa được cài.

Bản thảo vẫn chưa sẵn sàng để nộp vì Abstract để trống, phần Results chưa có
chiến dịch AGLR và Conclusion chỉ được phép ghi trạng thái tạm thời. Đây là chủ
ý đúng: không được biến kết quả RC2+B+R cũ thành bằng chứng cho AGLR.

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
| P0 | Chưa có kết quả AGLR trên máy thực nghiệm. | Chạy `screen`, `promote`, `full`, rồi `confirm` nếu qua cổng. |
| P0 | Chưa xác nhận `legacy` tái tạo CSOnet trên môi trường cuối. | So objective và trạng thái tối ưu; lưu commit, binary hash và log. |
| P0 | Baseline CPLEX có thể thiếu hoặc khác môi trường. | Chạy lại hoặc chỉ dùng dữ liệu có provenance, `valid=true`, cận khớp và giới hạn tài nguyên tương đương. |
| P0 | Chưa có baseline hội nghị với provenance đầy đủ. | Nhập file khi nhóm cung cấp; không ghép thời gian từ máy khác. |
| P0 | Abstract và Results trống. | Chỉ viết sau khi `gate.passed=true` và lượt xác nhận hoàn tất. |
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

Nếu AGLR chưa đạt 72/72 và PAR-2 tốt hơn baseline ở `finsteps123`, 69/72 ở
`infsteps180`, hoặc 68/72 ở `cont`, bản thảo phải tiếp tục ở trạng thái làm việc.
Không hạ ngưỡng sau khi đã xem kết quả.
