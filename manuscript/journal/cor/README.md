# Khung nghiên cứu cho *Computers & Operations Research*

Thư mục này chứa mẫu Elsevier và khung làm việc cho một bài COR có đóng góp mới.
Nội dung của bài hội nghị đã được loại khỏi `main.tex` để tránh tạo một bản thảo
trùng lặp trước khi câu hỏi nghiên cứu mới được chốt.

## Tệp làm việc

- `outline_brainstorm_vi.md`: dàn ý nghiên cứu, đối chiếu cấu trúc các bài liên
  quan và tiêu chí go/no-go. Đây là tệp cần đọc trước.
- `main.tex`: skeleton LaTeX bám theo dàn ý; chưa phải bản thảo để nộp.
- `references.bib`: dữ liệu tài liệu tham khảo.
- `elsarticle.cls`: lớp LaTeX chính thức của Elsevier.
- `elsarticle-harv.bst`: kiểu tài liệu tham khảo Harvard mà COR sử dụng.
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

`main.tex` chỉ chứa tiêu đề làm việc, front matter và các heading dự kiến. Tóm
tắt, highlights và mọi phát biểu kết quả đều để trống cho đến khi phương pháp mới
qua tiêu chí go/no-go trong `outline_brainstorm_vi.md`.

Bài hội nghị được xem là prior work của chính nhóm: phải trích dẫn và mô tả rõ
trong manuscript/cover letter, nhưng không chuyển nguyên văn hoặc dùng lại kết
quả cũ như đóng góp chính. Baseline hội nghị chỉ được đưa vào bảng sau khi đã
truy nguyên đúng binary, commit, cấu hình và tiêu chí kiểm tra nghiệm.

## Nguồn mẫu

Mẫu được tải từ trang hướng dẫn LaTeX chính thức của Elsevier ngày 15-10-2026:

<https://www.elsevier.com/researcher/author/policies-and-guidelines/latex-instructions>

Gói tải về: `elsarticle.zip`, phiên bản lớp 3.4 (04-04-2024).

SHA-256 của gói gốc:

```text
0b093093e84db49f99bcc9a7c3f69ed1fb61b0147c6d296427aff7963e7f50f6
```
