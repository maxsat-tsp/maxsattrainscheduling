# Kết quả tuần 5 được giữ lại để làm gì?

Thư mục này lưu bản kiểm tra độc lập của kết quả tại commit sinh viên
`aae0dd67fd1caf76bb8be57c7a7cd0f8b7fffb0c` trong repository
`Viing3107/maxsattrainscheduling`.

`audit_results.py` đã đọc 18 tệp JSON và CSV, tương ứng 1.296 lượt chạy trên
72 instance. Kết quả kiểm tra không phát hiện:

- sai khác giữa JSON và CSV;
- sai khác giữa bảng tổng hợp và dữ liệu gốc;
- trường hợp `status=ok` nhưng `cost`, `lb` và `ub` khác nhau;
- sai chi phí trên các instance mà hai cấu hình đều chạy xong;
- sai chi phí so với kết quả MaxSAT của bài hội nghị trên các instance chung.

Các tệp đi kèm:

- `audit_summary.csv`: số bài thành công, lỗi và thời gian theo cấu hình;
- `matched_comparisons.csv`: so sánh thời gian trên đúng tập instance chung;
- `audit_evidence.json`: checksum, danh sách lỗi và bằng chứng chi tiết;
- `audit_results.py`: script chỉ đọc dùng để tạo lại ba tệp trên.

Các kết quả này được dùng lại để chọn ngân sách 128, giữ ngân sách 32 cho
ablation và bỏ ngân sách 8 khỏi thí nghiệm chính. Chúng được tạo trước các sửa
lỗi quét vi phạm và kiểm tra nghiệm cuối, nên không được ghi là kết quả hiệu
năng của phiên bản mã mới.

Để kiểm tra lại khi đã có checkout của repository sinh viên:

```bash
python3 audit_results.py /duong/dan/toi/maxsattrainscheduling-cua-sinh-vien
```
