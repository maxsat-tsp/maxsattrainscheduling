# Bản thảo cho *Computers & Operations Research*

Thư mục này chứa bản LaTeX đã chuyển từ bài hội nghị sang mẫu của Elsevier dành
cho *Computers & Operations Research* (COR).

## Tệp dùng để nộp

- `main.tex`: bản thảo chính.
- `references.bib`: dữ liệu tài liệu tham khảo.
- `elsarticle.cls`: lớp LaTeX chính thức của Elsevier.
- `elsarticle-harv.bst`: kiểu tài liệu tham khảo Harvard mà COR sử dụng.
- `highlights.txt`: bốn điểm nổi bật, mỗi dòng không quá 85 ký tự.
- `elsarticle-template-harv.tex`: mẫu Harvard trong gói chính thức để đối chiếu.

Các tệp được đặt cùng một cấp vì hệ thống nộp bài của Elsevier xử lý gói nguồn
LaTeX ổn định nhất khi không có thư mục con.

## Cách biên dịch

Chạy lệnh sau ngay trong thư mục này:

```bash
latexmk -pdf -interaction=nonstopmode -halt-on-error main.tex
```

Để xóa các tệp trung gian:

```bash
latexmk -C main.tex
```

## Trạng thái nội dung

`main.tex` hiện chứa đầy đủ nội dung và kết quả của bản hội nghị đã được chấp
nhận. Việc chuyển mẫu không thay đổi số liệu, kết luận hoặc phạm vi thực nghiệm.
Bản này biên dịch được và có thể dùng ngay làm nền để viết bài tạp chí, nhưng
chưa nên nộp như một bài báo mới vì chưa thể hiện đủ phần mở rộng so với bài hội
nghị.

Trước khi nộp COR, cần cập nhật các phần sau sau khi có kết quả thực nghiệm mới:

1. Thay tiêu đề, tóm tắt và danh sách đóng góp để phản ánh đúng phương pháp mở
   rộng đã được kiểm chứng.
2. Bổ sung phương pháp tinh chỉnh có chọn lọc, lập luận về tính đúng đắn và độ
   phức tạp.
3. Bổ sung thực nghiệm mới, phân tích độ nhạy và so sánh công bằng với bản hội
   nghị. Các bảng hiện tại chỉ chứa kết quả đã công bố ở hội nghị.
4. Thêm đoạn nói rõ quan hệ với bài hội nghị và trích dẫn bài đó khi thông tin
   xuất bản chính thức đã có.
5. Kiểm tra lại CRediT, nguồn tài trợ, xung đột lợi ích và tuyên bố sử dụng công
   cụ AI theo thông tin do các tác giả xác nhận.

## Nguồn mẫu

Mẫu được tải từ trang hướng dẫn LaTeX chính thức của Elsevier ngày 15-10-2026:

<https://www.elsevier.com/researcher/author/policies-and-guidelines/latex-instructions>

Gói tải về: `elsarticle.zip`, phiên bản lớp 3.4 (04-04-2024).

SHA-256 của gói gốc:

```text
0b093093e84db49f99bcc9a7c3f69ed1fb61b0147c6d296427aff7963e7f50f6
```
