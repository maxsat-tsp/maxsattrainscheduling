# Hướng dự phòng: SAT chọn thứ tự, đồ thị tính thời gian

Đây là thiết kế để xem xét nếu V20/V21 hoàn tất mà vẫn không tăng coverage.
Chưa cài solver này và chưa có kết quả hiệu năng. V17 vẫn là mốc đã kiểm
tra đủ dữ liệu, 203/216. V20/V21 đang chạy; cần đọc kết quả trước khi chuyển.

## Vì sao xem xét đổi biểu diễn

V18 và V19 đều không giải thêm trong 13 ca còn lại. Truyền cận V20 tạo
nhiều mốc và gọi SAT rất nhiều. V21 đã giảm số lời gọi trên ca đầu từ
40.606 xuống 7.893 nhưng ca đó vẫn timeout. Vì vậy, nếu hết vòng vẫn
không có gain, cần xem xét bỏ các biến thời gian không trực tiếp tạo chi
phí, thay vì tiếp tục chỉ đổi tham số RC2.

Đếm bằng parser TXT độc lập, theo cặp khác tàu dùng cùng tài nguyên:

| Instance | Số tàu | Số lần đi qua, gồm nút chờ/kết thúc | Số cặp cần thứ tự |
|---|---:|---:|---:|
| origA8 | 28 | 1.104 | 4.877 |
| trackA11 | 29 | 1.217 | 6.144 |
| stationA11 | 29 | 1.217 | 6.144 |

Các instance này chỉ tính phạt ở lần đi qua có `aimed`, chủ yếu ở cuối
tuyến. Đây là cơ sở để thử mô hình chỉ có biến thứ tự và biến chi phí.
Số biến SAT cuối cùng còn phụ thuộc bộ mã hóa chi phí; bảng trên chưa
chứng minh mô hình mới nhỏ hơn hay nhanh hơn.

## Biểu diễn dự kiến

SAT giữ một biến thứ tự cho mỗi cặp khác tàu có tài nguyên xung đột.
Một lần SAT chọn hướng cho các cặp. Dùng đúng các cạnh V20: cạnh nối tiếp
trong tàu và cạnh từ thời điểm rời của lần trước tới thời điểm vào của
lần sau. Cạnh thứ tự có literal điều kiện; cạnh tuyến cố định không cần.

Nếu có chu trình thời gian dương, thêm mệnh đề cấm các hướng trên chu
trình. Nếu không, truyền earliest qua đồ thị để có lịch sớm nhất L(o)
cho các hướng o. Nhóm chu trình thời gian 0 được xử lý như V20. Vì mọi
ràng buộc là cận dưới và chi phí không giảm theo thời gian, lịch này đồng
thời có thời điểm sớm nhất và chi phí nhỏ nhất đối với chính các hướng đó.
Phải dùng đủ các cặp xung đột để lịch đồ thị bảo đảm không chồng tài nguyên.

Chỉ các lần đi qua có chi phí mới cần biến ngưỡng trong SAT. Các lần còn
lại nằm trong đồ thị thời gian, không tạo ladder mốc thời gian trong SAT.
Gọi y(v,c) là literal chi phí ở v ít nhất c. Một đường chứng minh cận
L_v, có các literal thứ tự o1,...,om, cho mệnh đề:

    không o1 hoặc ... hoặc không om hoặc y(v, f_v(L_v)).

Có thể giữ cách tạo biến mốc ở riêng lần có chi phí và tái sử dụng
CostTree hiện có; không cần thiết kế lại số học của hàm chi phí. Với
finsteps123, hai thời điểm cùng mức phạt không cần tạo hai mức chi phí.

## Vòng tối ưu và lý do có thể kết luận tối ưu

1. RC2 giải mô hình SAT hiện tại và cho cận dưới LB.
2. Từ model đầy đủ, lấy các hướng và tính đồ thị.
3. Có chu trình dương: thêm mệnh đề cấm tổ hợp đó, tiếp tục SAT.
4. Có lịch: tính chi phí đầy đủ C của lịch sớm nhất. Chỉ cập nhật nghiệm
   tốt nhất sau khi kiểm tra lịch độc lập trong solver.
5. Nếu C=LB, trả lịch và chứng minh tối ưu. Nếu C>LB, thêm một hoặc một
   nhóm mệnh đề chi phí theo các đường chứng minh đang bị model vi phạm;
   đăng ký các khoản chi phí mới trước lần SAT tiếp theo.

Mỗi mệnh đề phải đúng với mọi lịch hợp lệ chọn các hướng trong điều kiện.
Do đó mô hình SAT vẫn là một phép nới lỏng: LB không vượt optimum thật.
Khi có lịch hợp lệ chi phí C=LB, hai phía bằng nhau. Nếu C<LB hoặc C>LB
mà không tìm được mệnh đề chi phí mới bị vi phạm, phải dừng báo lỗi;
không công bố optimum bằng cách chỉ chấp nhận lịch đang có.

## Cách tận dụng mã đã kiểm thử

- Giữ vòng RC2 của CSOnet: weighted cores, totalizers, thu gọn core và
  xử lý deadline. Tái sử dụng CostTree, không dựng một bản RC2 khác.
- Tái sử dụng các kiểm thử và xử lý chu trình/đường đi của order_paths.rs;
  tách phần phân tích để trả được cả lịch và đường chứng minh cho từng
  lần có chi phí. Tập cặp thứ tự lúc này cố định từ đầu.
- Dùng một chế độ hoặc solver alias riêng. Trong chế độ đó, bỏ bước
  phát hiện xung đột theo các mốc DDD; tính khả thi đến từ đồ thị đủ cặp.
  Đường mặc định CSOnet tiếp tục giữ nguyên.
- Mọi lịch trả về đều qua Problem::verify_solution, có cost=LB=UB.
  Thực nghiệm vẫn chỉ bắt đầu trên các ca chưa giải; chưa gán coverage full
  cho đến khi kiểm tra lại các ca cũ.

Trước thực nghiệm cần vét cạn các lịch rất nhỏ với ba objective, kiểm tra
chu trình 0/dương, chi phí ban đầu dương, mức chi phí trùng, cập nhật UB,
đăng ký chi phí sau mệnh đề mới và timeout trên hai SAT backend. Cần đo
chi phí của việc tạo đủ cặp: số cặp lớn có thể làm mất lợi ích của việc
bỏ ladder. Sau khi có bằng chứng thực nghiệm mới xem xét mô tả phương pháp
trong bài và đối chiếu các nghiên cứu liên quan.
