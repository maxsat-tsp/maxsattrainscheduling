# Bản thảo brainstorming cho *Computers & Operations Research*

Thư mục này chứa mẫu Elsevier và bản thảo làm việc cho một bài COR có đóng góp
mới. `main.tex` đã được điền bằng lập luận, mô hình toán, thuật toán dự kiến và
thiết kế thực nghiệm. Bài hội nghị chỉ được tóm tắt và trích dẫn như prior work;
không chuyển nguyên văn hay dùng lại bảng kết quả hội nghị làm đóng góp mới.

## Tệp làm việc

- `outline_brainstorm_vi.md`: dàn ý nghiên cứu, đối chiếu cấu trúc các bài liên
  quan và tiêu chí go/no-go. Đây là tệp cần đọc trước.
- `content_review_vi.md`: rà soát bản thảo hiện tại theo mức ưu tiên, gồm lập
  luận, mô hình toán, thực nghiệm, tính dễ đọc và thuật ngữ.
- `main.tex`: bản thảo brainstorming bằng tiếng Anh; đã có nội dung để tiếp tục
  phát triển nhưng chưa phải bản sẵn nộp.
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

`main.tex` hiện phân biệt rõ bốn lớp nội dung: prior work đã được chấp nhận ở hội
nghị, thành phần B+R đã cài đặt, selection model đang đề xuất, và kết quả pilot
một lần. Abstract và highlights vẫn để trống; conclusion chỉ mô tả trạng thái
nghiên cứu và việc phải hoàn thành, không đưa ra phát biểu thắng baseline.

Bảng pilot K=8/32/128 được giữ như dữ liệu chẩn đoán để giải thích quyết định
chạy tiếp với K=128. Bảng này bị loại khỏi evidence chính của bài vì được tạo
trước full-scan repair và correctness gate cuối cùng, đồng thời chưa có baseline
hội nghị đồng bộ.

Bản thảo chỉ có thể chuyển sang trạng thái submission sau khi thống nhất verifier
với mô hình chính xác, hoàn thành kiểm thử bài nhỏ, truy nguyên baseline hội nghị,
chạy ablation ghép cặp và thay các placeholder về tác giả/venue/artifact bằng
thông tin thật. Baseline hội nghị chỉ được đưa vào bảng so sánh sau khi đã truy
nguyên đúng binary, commit, cấu hình và tiêu chí kiểm tra nghiệm.

## Nguồn mẫu

Mẫu được tải từ trang hướng dẫn LaTeX chính thức của Elsevier ngày 15-10-2026:

<https://www.elsevier.com/researcher/author/policies-and-guidelines/latex-instructions>

Gói tải về: `elsarticle.zip`, phiên bản lớp 3.4 (04-04-2024).

SHA-256 của gói gốc:

```text
0b093093e84db49f99bcc9a7c3f69ed1fb61b0147c6d296427aff7963e7f50f6
```
