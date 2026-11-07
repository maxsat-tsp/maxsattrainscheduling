# Hướng dự phòng: SAT chọn thứ tự, đồ thị tính thời gian

Biểu diễn này đã cài ở `38f9aea`. Native đạt 76 test Rust và 106 test
Python, nhưng V22 dừng tại thử nhanh: finsteps123 có optimum đúng ở 18,72
giây, infsteps180 timeout hợp lệ ở 30 giây. Chưa chạy ca khó. Mốc full tốt
nhất vẫn là V17, 203/216.

V23 ở mã `d8e2509` chuẩn hóa các thời điểm có cùng mức phạt về mốc đầu
bậc. Đã qua 77 test Rust và 107 test Python, nhưng bài thử infsteps180 timeout
ở 30 giây nên chưa chạy ca khó. Đây là sửa biểu diễn
chi phí trong master, không cùng lúc thay RC2 hoặc cách gửi điều kiện.

## Vì sao xem xét đổi biểu diễn

V18 và V19 đều không giải thêm trong 13 ca còn lại. Truyền cận V20 tạo
nhiều mốc và gọi SAT rất nhiều. V21 đã giảm số lời gọi trên ca đầu từ
40.606 xuống 7.893 nhưng ca đó vẫn timeout. Cả 13 ca: V20 có 297.623
lời gọi, V21 có 60.813; vẫn không có optimum mới. Vì vậy cần thử bỏ các biến thời gian không trực tiếp tạo chi
phí, thay vì tiếp tục chỉ đổi tham số RC2.

Đếm bằng parser TXT độc lập, theo cặp khác tàu dùng cùng tài nguyên:

| Instance | Số tàu | Số lần đi qua, gồm nút chờ/kết thúc | Số cặp cần thứ tự |
|---|---:|---:|---:|
| origA8 | 28 | 1.104 | 4.877 |
| trackA11 | 29 | 1.217 | 6.144 |
| stationA11 | 29 | 1.217 | 6.144 |

Các instance TXT này chỉ tính phạt ở lần đi qua có `aimed`, chủ yếu ở cuối
tuyến. Đây là cơ sở để thử mô hình chỉ có biến thứ tự và biến chi phí.
Số biến SAT cuối cùng còn phụ thuộc bộ mã hóa chi phí; bảng trên chưa
chứng minh mô hình mới nhỏ hơn hay nhanh hơn.

## Biểu diễn đã cài

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

## Chi tiết bản cài V22

Chế độ này tạo đủ biến thứ tự cho các cặp xung đột khác tàu, không tạo
các hàng xung đột theo mốc và không dùng các mệnh đề bộ ba trong khởi tạo.
Giá trị cờ bộ ba của cấu hình gốc được giữ để truy vết, nhưng số hàng và
bộ ba thực sự trong chế độ master là 0; phải đọc cả cờ master và số đo.
Nó tái sử dụng nguyên vòng weighted RC2, CostTree, core minimization và
core exhaustion; không thay đổi đường mặc định CSOnet.

Đồ thị trả về cả lịch và đường chứng minh tới từng đỉnh. Chỉ chọn đường
có mức tăng chi phí dương; không thêm mốc chỉ vì một lần đi qua không
có phạt bị model chọn sớm. Mốc mới vẫn được CostTree mã hóa trước lần
SAT tiếp theo. Lịch đồ thị cải thiện UB hoặc đạt LB được kiểm tra đầy đủ
trước khi giữ. Khi RC2 LB bằng chi phí lịch đã kiểm tra thì trả optimum.
Không sử dụng lịch/chi phí từ dữ liệu hội nghị trong solver.

Luồng heuristic đồ thị cũ được tắt trong chế độ master, vì mỗi model
không có chu trình đã cung cấp một lịch ứng viên; tránh dùng heuristic
có giả định resource-0/terminal chỉ phù hợp TXT để xử lý bài tổng quát.
Greedy ban đầu chỉ là một nguồn UB và vẫn phải kiểm tra hợp lệ. Không
đổi luồng heuristic của CSOnet khi cờ master tắt.

Kiểm thử mới so master với vét cạn trên ba tàu có occupation cuối dương,
chi phí ban đầu dương, các tổ hợp sparse/UB/extract offset, cả MiniSAT và
CaDiCaL. Bài ba tuyến giao nhau kiểm tra 6 cặp thứ tự đầy đủ, không có hàng
xung đột theo thời gian, và cùng optimum vét cạn trên ba hàm mục tiêu.
Kernel còn kiểm tra cách lấy lịch và giữ đường chứng minh qua chu trình 0.

Runner dự kiến tự xác nhận ba lần các ca mới sau khi sàng lọc đủ và audit.
Chỉ khi mọi ca mới lặp lại thành công mới chạy hồi quy 203 ca V17 đã giải,
giữ đúng một binary/cấu hình. Các ca mất được báo riêng. Một service giới
hạn tổng 6 giờ; nếu hết giờ, giữ phần đã xong và chưa báo coverage full.

## V23: một ngưỡng đại diện cho mỗi mức phạt

Bản thử V22 đã chứng minh đúng optimum finsteps123, nhưng thêm hàng nghìn
mốc trong các bậc chi phí. Cận L=200 và L=280 với aimed=0 đều tương ứng
chi phí làm tròn 180 giây bằng 2, có thể dùng cùng mốc 181. Một đường
chứng minh t>=L cũng chứng minh t>=181; mức chi phí giữ nguyên. V23 tìm
mốc đầu tiên cùng mức phạt trên đoạn [earliest,L] bằng tìm kiếm nhị phân
với chính hàm chi phí gốc. CostTree và vòng RC2 giữ nguyên. Cờ mặc định
tắt `order_master_cost_levels`, yêu cầu master bật. Continuous không đổi
mốc khi chi phí dương. Các kiểm thử master chạy bật/tắt chuẩn hóa, cộng
với kiểm thử ngưỡng trên miền nhỏ và cả biên i32.


## V24--V26: kết quả và bước kiểm tra tiếp

V24 dùng nguyên binary V23, chỉ gửi đủ điều kiện chi phí. origA1 có
optimum finsteps123=11 ở 15,62 giây, infsteps180=34 ở 13,73 giây; cont
timeout hợp lệ ở 30 giây. Các lịch tối ưu đều qua kiểm tra độc lập, nhưng
lượt này dừng trước ca khó. V25 giữ đúng cấu hình và chỉ sàng lọc bốn ca
infsteps180 V17 chưa giải; không suy rộng sang cont.

V26 ở mã 984e221 bổ sung tất cả đường chi phí bị vi phạm từ mỗi lịch,
thay vì một đường. Mỗi đường vẫn có các lựa chọn thứ tự làm điều kiện
và cận từ đồ thị; không suy ra cận từ model thời gian của SAT. Chuẩn hóa
mốc và đăng ký chi phí của tất cả mốc mới trước truy vấn SAT kế tiếp.
Cờ mặc định tắt. Kiểm thử nhân nhỏ so các mệnh đề với mọi lịch nhỏ hợp
lệ và kiểm tra thứ tự chọn; kiểm thử đầy đủ cần chạy native trên VM
trước khi sàng lọc. Bài thử thật timeout hợp lệ không còn tự chặn lượt
sàng lọc chỉ vì chậm; validator ghi rõ điều kiện mới. Chưa có số liệu
nào thay thế bảng full V17.
