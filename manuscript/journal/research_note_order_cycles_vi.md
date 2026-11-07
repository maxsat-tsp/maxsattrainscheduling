# Hướng dự phòng: loại chu trình thứ tự giữa các tàu

V18 (chu trình) và V19 (tách chi phí) đều đã chạy đủ 13 ca chưa giải,
qua kiểm toán độc lập và chưa giải thêm ca. Mốc tốt nhất vẫn là V17,
203/216. V20 đã cài truyền cận theo cả đường đi ở mã `8898caf`, mặc định
tắt; 73 test Rust và 97 test Python đã đạt native trên VM. Build release, hai lịch có optimum 5526 và timeout đã đạt.
Dịch vụ V20 bắt đầu đo 13 ca khó lúc 11:40:00 ngày 07/11, giờ Việt Nam.

## Vấn đề cần kiểm tra

Các ca còn timeout dành gần hết thời gian cho SAT. Phương án hiện tại đã
dùng chung biến thứ tự của từng cặp và cấm chu trình giữa ba biến đã có.
Nếu thiếu một cạnh nối giữa hai đỉnh, chu trình dài hơn vẫn có thể tồn tại
trong mô hình SAT gần đúng. Chu trình cũng có thể đi qua nhiều khu vực,
với các cạnh nối tiếp trong tuyến của tàu.

Ví dụ: tàu A phải đi qua khu vực thứ nhất trước khu vực thứ hai. Tàu B
cũng có hai lần đi qua liên tiếp. Hai lựa chọn thứ tự có thể làm A chờ B
ở một nơi, trong khi B lại chờ A ở nơi khác. Nếu chuỗi chờ quay về điểm
ban đầu và có thời gian di chuyển dương, không thể có lịch thực hiện nó.

## Biểu diễn và lý do ràng buộc đúng

Mỗi đỉnh là một lần tàu đi qua một khu vực, có thời điểm vào là $t_v$ và
thời gian di chuyển tối thiểu là $d_v\geq0$.

- Hai lần đi qua nối tiếp của cùng tàu cho cạnh cố định
  $t_v\geq t_u+d_u$.
- Nếu biến thứ tự chọn lần $u$ trước lần $v$, thời điểm vào $v$ phải không
  sớm hơn thời điểm rời $u$. Khi $u$ có lần đi qua kế tiếp $s(u)$, dùng
  cạnh $s(u)\to v$ trọng số 0, tức $t_v\geq t_{s(u)}$. Khi $u$ là lần
  cuối, dùng cạnh $u\to v$ trọng số $d_u$. Cách này dùng đúng thời điểm
  rời trong mô hình hiện tại, thay vì chỉ dùng thời gian di chuyển tối thiểu.

Viết mỗi cạnh dưới dạng $t_v\geq t_u+\delta_e$, với $\delta_e\geq0$.
Xét một chu trình $C$ trong các cạnh đã chọn. Cộng các bất đẳng thức trên
chu trình cho

\[
0\geq\sum_{e\in C}\delta_e.
\]

Nếu tổng bên phải dương, tổ hợp thứ tự đó không thể xảy ra trong lịch hợp
lệ. Gọi $o_1,\ldots,o_m$ là các literal thứ tự đã chọn trên chu trình;
các cạnh cố định không cần literal. Có thể thêm mệnh đề

\[
\neg o_1\lor\cdots\lor\neg o_m.
\]

Đây là ràng buộc suy ra từ bài toán lịch tàu đầy đủ. Mô hình SAT gần đúng
có thể chưa chứa nó. Với một lịch hợp lệ bất kỳ, chọn các biến thứ tự
theo thứ tự thực hiện trong lịch đó sẽ không tạo chu trình có tổng thời
gian dương. Vì vậy ràng buộc giữ được một cách biểu diễn SAT của mọi lịch
hợp lệ và không loại mất optimum theo các thời điểm của lịch.

Chu trình có tổng thời gian bằng 0 cần được giữ lại trong phép thử này.
Không kết luận nó bất khả thi chỉ vì là chu trình. Nếu có thời gian di
chuyển âm, phải xử lý giả định đầu vào trước khi dùng lập luận trên.

## Cách thử mà không làm mô hình lớn ngay từ đầu

Chỉ dùng các biến thứ tự đã được tạo, cùng các cạnh nối tiếp của tàu.
Không tạo hàng loạt cặp mới. Sau một lần SAT thỏa đủ các điều kiện chi
phí, đọc các hướng thứ tự được chọn và tìm một chu trình có tổng thời gian
dương. Nếu tìm thấy, thêm một mệnh đề cấm tổ hợp đó rồi gọi SAT lại, với
cùng điều kiện chi phí. Chỉ chuyển sang phát hiện xung đột theo thời gian
khi không tìm thấy chu trình như vậy.

Với trọng số cạnh không âm, có thể tìm nhóm đỉnh đi tới được lẫn nhau.
Nếu bên trong một nhóm có cạnh trọng số dương, cạnh đó cùng đường quay
về tạo một chu trình cần loại. Chọn cạnh và đường đi theo thứ tự cố định
để có thể tái tạo. Loại mệnh đề trùng và giới hạn một chu trình cho mỗi
lần kiểm tra đầu tiên.

Điểm cài là `resource_orders.rs` và nhánh nhận nghiệm SAT đầy đủ
trong `maxsat_ladder_sc/solve.rs`. Cần đọc xong model rồi thả model trước
khi thêm mệnh đề mới vào solver. Không dùng model của lần gọi SAT chỉ có
một phần điều kiện chi phí để cập nhật lịch.

## Kiểm thử bắt buộc trước thực nghiệm

- Chu trình bốn đỉnh không có đường chéo: quy tắc bộ ba hiện tại không đủ
  để loại, ràng buộc mới phải loại đúng hướng tạo chu trình.
- Chu trình đi qua hai tuyến tàu và hai lựa chọn thứ tự ở hai khu vực.
- Chu trình toàn thời gian 0 được giữ; chu trình có ít nhất một cạnh dương
  được phát hiện dù các cạnh khác bằng 0.
- Với lịch nhỏ vét cạn, mọi lịch hợp lệ vẫn có cách chọn các biến thứ tự
  thỏa các mệnh đề mới, và optimum giữ nguyên trên cả ba objective.
- Mệnh đề không trùng, thứ tự tìm xác định, timeout vẫn được tôn trọng.

V17 đã tăng coverage nhưng còn 13 ca chưa giải. V18 giữ cấu hình RC2 đã
kiểm tra và chỉ thêm thành phần này; đo số chu
trình bị loại, thời gian tìm, số mệnh đề, mức tăng mô hình và số ca giải
thêm. Trước khi gọi đây là đóng góp mới trong bài báo, cần đối chiếu các
nghiên cứu liên quan về mô hình thứ tự và ràng buộc chu trình.

## Giới hạn phát hiện khi thêm kiểm thử

Bài nhỏ ban đầu có lịch sớm nhất đã hợp lệ nhưng chi phí dương. Đường
refinement legacy có thể kết thúc trước khi mã hóa các chi phí ban đầu
đang chờ; kiểm tra cuối trả lỗi chi phí. Lỗi này xuất hiện khi tắt cả cờ
chu trình, nên được lưu riêng, chưa sửa chung trong vòng thử một thành
phần này. Tất cả 72 instance TXT có xung đột trong lịch sớm nhất, đã kiểm
tra bằng parser độc lập; từng kết quả tối ưu V17 cũng được kiểm tra chi phí.
Cần xử lý giới hạn này trước khi mở rộng sang dữ liệu tùy ý.

Heuristic legacy dùng resource 0 cho phần kết thúc không xung đột và bỏ
lần đi qua cuối khi tìm xung đột. Vì vậy bài nhỏ đối chứng dùng tài nguyên
1,2 và một lần kết thúc thời gian 0 ở resource 0, theo dữ liệu TXT. Các
kiểm thử kernel vẫn xét cả trường hợp lần đi qua cuối có thời gian dương.
Hai lần kiểm thử dừng được lưu nguyên log; chưa chạy ca hiệu năng nào
trước khi chúng được giải quyết.

## Phép thử V19 tách chi phí ban đầu

Đã cài cờ riêng, mặc định tắt, ở mã `20e24a9`. Cộng phần chi phí chắc
chắn ở lịch sớm nhất vào LB một lần và chỉ mã hóa phần tăng thêm. Nếu dùng
giới hạn objective, cũng trừ khoản này khỏi UB. Cờ bật xử lý đúng ví dụ
lịch ban đầu hợp lệ có chi phí dương; đường baseline khi tắt vẫn giữ nguyên.
Hai kiểm thử mới bao phủ ví dụ này và lịch nhỏ vét cạn cùng các tùy chọn
RC2/giới hạn objective. Native đã đạt 65 test Rust và 96 test Python; cả 13 ca thực nghiệm
vẫn timeout ở 300 giây. Xem công thức và ví dụ dễ đọc trong hướng dẫn sinh viên.
Controller chỉ thử hiệu năng V19 nếu V18 đã hoàn tất mà không có ca mới.

## V20: truyền cận theo cả đường đi, đã cài và kiểm thử

Có thể dùng chính đồ thị thứ tự để suy ra thời điểm sớm nhất theo cả chuỗi,
không chỉ tìm chu trình bất khả thi. Với một đường đi từ lần s tới lần v,
các cạnh đều bật bởi các lựa chọn thứ tự o1,...,om, ta có:

    (o1 và ... và om) suy ra t_v >= earliest_s + tổng thời gian trên đường.

Nếu model hiện tại chọn v sớm hơn mức đó, thêm một mốc tại v và một mệnh
đề có điều kiện tương ứng. Ví dụ A phải đi ít nhất 3 giây tới chỗ gặp B,
và thứ tự chọn A rời trước B vào, thì có thể truyền cả cận này tới B ngay.
Điểm mới ở phép thử dự kiến là truyền một chuỗi đầy đủ thay vì đợi DDD
phát hiện từng vi phạm ở từng cặp mốc. Mã đã cài trong `order_paths.rs`. Các literal trên đúng đường đi tạo
điều kiện cho mệnh đề; cận đầu đường là earliest cứng, không lấy thời điểm
model hiện tại làm một giả định không được ghi lại.

Với các nhóm đỉnh đi tới được lẫn nhau, nếu còn cạnh dương bên trong thì
cấm chu trình trước. Các cạnh bên trong nhóm còn lại có trọng số 0.
Chọn cận lớn nhất đi vào nhóm hoặc earliest lớn nhất của nhóm, giữ đường
chứng minh tới đỉnh đó rồi truyền qua các cạnh 0. Các đường chứng minh là
các liên kết không bị sửa sau khi tạo, nên cập nhật một cận không làm sai
đường đã dùng ở một đỉnh khác.

Chỉ thêm một mệnh đề đường đi sau mỗi model đầy đủ. Ưu tiên tăng chi phí,
rồi tăng thời gian, rồi chỉ số visit. Mốc mới nhận chi phí trước lần SAT
kế tiếp, và model vừa bị loại không đi vào kiểm tra lịch DDD. Kiểm thử
vét cạn ba tàu đã kích hoạt mệnh đề đường đi và vẫn giữ optimum trên cả
ba objective với MiniSAT/CaDiCaL; tùy chọn bound được kiểm tra riêng khi
có nghiệm đầu vào hợp lệ. V20 giữ tách chi phí tắt để sàng lọc một thành
phần trên V17. Chưa có kết quả hiệu năng V20 khi khởi chạy.
