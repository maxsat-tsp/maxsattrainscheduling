# Dàn ý brainstorming cho bài tạp chí COR

**Trạng thái:** tài liệu định hướng nghiên cứu. Nội dung đã được chuyển thành bản
thảo brainstorming trong `main.tex`, nhưng chưa phải bản thảo để nộp.

**Cập nhật:** 15-10-2026.

**Bài nền của nhóm:** *An Efficient MaxSAT-DDD Approach for Train
Rescheduling via Precedence Propagation and Hybrid AMO Encodings* (bài hội
nghị đã được chấp nhận).

## 1. Nguyên tắc ngay từ đầu

Bài tạp chí phải trả lời một câu hỏi nghiên cứu mới và có bằng chứng mới. Không
chuyển nguyên phần tóm tắt, mở đầu, mô hình, thuật toán, bảng kết quả và kết luận
của bài hội nghị sang mẫu COR rồi sửa câu chữ.

Phần đã công bố ở hội nghị vẫn có thể được dùng làm **nền nghiên cứu**, theo cách
sau:

- trích dẫn rõ bài hội nghị ngay trong phần mở đầu;
- tóm tắt ngắn mô hình MaxSAT-DDD và hai cải tiến đã công bố, chỉ giữ những ký
  hiệu thật sự cần cho phần mới;
- gọi cấu hình hội nghị là một baseline trong thực nghiệm;
- dùng lại dữ liệu nếu giấy phép cho phép, nhưng phải đặt câu hỏi thực nghiệm mới,
  bổ sung cấu hình mới và công bố rõ quan hệ giữa hai bài;
- viết lại toàn bộ diễn giải theo lập luận của bài tạp chí; không thay từ đồng
  nghĩa để che sự trùng lặp;
- không dùng lại bảng hoặc hình của bài hội nghị làm kết quả chính. Nếu thật sự
  cần tái bản một hình, phải kiểm tra bản quyền, ghi nguồn và xin phép khi cần.

Không áp dụng một con số tùy ý như “phải có 30% nội dung mới”. Elsevier xem mức
độ bổ sung tri thức là quyết định biên tập; điều quan trọng là bài sau không mô tả
về cơ bản cùng một nghiên cứu. Khi nộp, cover letter phải khai báo bài hội nghị,
đính kèm bản đó nếu hệ thống yêu cầu, và liệt kê cụ thể đóng góp mới.

Nguồn cần kiểm tra lại trước ngày nộp: [Elsevier Publishing
Ethics](https://www.elsevier.com/about/policies-and-standards/publishing-ethics)
và [Guide for Authors của
COR](https://www.sciencedirect.com/journal/computers-and-operations-research/publish/guide-for-authors).

## 2. Các bài đã đọc để học cách tổ chức

Danh sách này ưu tiên bài trực tiếp về DDD, tối ưu chính xác và lập lịch đường
sắt ở các tạp chí hàng đầu trong OR. Xếp hạng Q1 thay đổi theo năm và nhóm ngành,
vì vậy chất lượng của dàn ý được đánh giá thêm bằng độ gần của bài với câu hỏi
nghiên cứu, tính chặt chẽ và thiết kế thực nghiệm.

| Công trình | Cách tổ chức chính | Điều nên học cho bài của nhóm |
|---|---|---|
| [Croella et al. (2024), COR, DOI 10.1016/j.cor.2024.106679](https://doi.org/10.1016/j.cor.2024.106679) | Bài toán và mô hình time-indexed → DDD → mô hình MaxSAT → từng bước của thuật toán → hội tụ → thực nghiệm → thảo luận | Đây là bài nền trực tiếp. Bài mới chỉ tóm tắt phần cần dùng và phải nói rõ phần nào khác Croella cũng như khác bài hội nghị của nhóm. |
| [Boland et al. (2017), Operations Research, DOI 10.1287/opre.2017.1624](https://doi.org/10.1287/opre.2017.1624) | Tổng quan → bài toán → thuật toán, tách khởi tạo/refinement/chuyển thành nghiệm khả thi → thực nghiệm về cơ chế rời rạc hóa → hiệu năng tổng thể | Trước khi báo runtime, cần chứng minh cơ chế đề xuất thật sự thay đổi số mốc, số vòng và kích thước mô hình. |
| [Van Dyk và Koenemann (2024), COR, DOI 10.1016/j.cor.2024.106715](https://doi.org/10.1016/j.cor.2024.106715) | Nền DDD dùng chung ký hiệu → mô hình thưa mới → cận dưới → cận trên và refinement → giả mã → nhiều họ instance | Một bài DDD tốt tách rõ ba nghĩa vụ: relaxation hợp lệ, tạo nghiệm khả thi và refinement. “Thưa hơn” phải được định nghĩa và đo. |
| [Leutwiler, Bonet Filella và Corman (2023), COR, DOI 10.1016/j.cor.2022.106075](https://doi.org/10.1016/j.cor.2022.106075) | Related work → mô hình đường sắt → decomposition → tái sử dụng cut → cơ chế chọn lazy cut → thực nghiệm riêng về tác hại của quá nhiều cut | Nhiều thông tin không luôn tốt hơn. Bài của nhóm nên đo trực tiếp trade-off giữa sửa nhiều xung đột và làm mô hình MaxSAT phình lớn. |
| [Leutwiler và Corman (2022), EJOR, DOI 10.1016/j.ejor.2022.02.043](https://doi.org/10.1016/j.ejor.2022.02.043) | Bài toán → disjunctive formulation → decomposition → triển khai → aggregation → thực nghiệm | Tách mô hình toán, thuật toán và chi tiết triển khai; không để một mẹo cài đặt được mô tả như định lý. |
| [van Lieshout và van der Schaft (2025), INFORMS Journal on Computing, DOI 10.1287/ijoc.2024.0698](https://doi.org/10.1287/ijoc.2024.0698) | DDD được chia thành partial network, refinement, nghiệm khả thi, tolerance và hậu xử lý → mỗi thành phần có một câu hỏi thực nghiệm tương ứng | Các tiểu mục thực nghiệm nên phản chiếu đúng các tiểu mục phương pháp: ablation, chiến lược refinement, độ nhạy và giá trị thực tế. |
| [Shu, Xu và Baldacci (bản cập nhật 2026), *New Dynamic Discretization Discovery Strategies...*](https://optimization-online.org/2025/01/new-dynamic-discretization-discovery-strategies-for-continuous-time-service-network-design/) | Tổng quan DDD → mốc khởi tạo quan trọng → tạo cận trên → refinement chung cho nhiều mẫu bất khả thi → MIP/matheuristic → ablation | Họ đã chọn chung một tập mốc nhỏ để loại bỏ các mẫu bất khả thi đã thu thập. Vì vậy “thêm ít mốc” hoặc “gộp nhiều vi phạm” không thể là phát biểu mới của bài ta. |
| [Helber, Bachtler và Wüllner (2026), arXiv:2609.39269](https://arxiv.org/abs/2609.39269) | Nền DDD → bài toán refinement tối ưu → tính chất cấu trúc → thuật toán chính xác → tích hợp vào DDD → thực nghiệm | Họ tối thiểu hóa relaxation trong khi sửa **tất cả** xung đột quan sát được, đồng thời nêu việc chọn một tập con xung đột là hướng còn mở. Đây là ranh giới gần nhất với hướng của nhóm. |
| [Dollevoet et al. (2017), COR, DOI 10.1016/j.cor.2016.08.011](https://doi.org/10.1016/j.cor.2016.08.011) | Khung lặp → tương tác giữa thành phần → mô hình từng thành phần → thực nghiệm → khía cạnh thực tiễn | Sau kết quả thuật toán cần có discussion về tình huống vận hành, phạm vi mô hình và giới hạn khi chuyển sang mạng khác. |

### Mẫu cấu trúc chung rút ra

Các bài mạnh thường đi theo chuỗi lập luận:

1. xác định đúng nút thắt tính toán;
2. đặt phương pháp mới bên cạnh công trình gần nhất;
3. định nghĩa đối tượng mới bằng toán học;
4. tách thuật toán khỏi chứng minh tính đúng;
5. thiết kế mỗi nhóm thực nghiệm để trả lời một câu hỏi;
6. giải thích cơ chế trước khi kết luận phương pháp nhanh hơn;
7. báo cả trường hợp thất bại và giới hạn áp dụng.

Đây nên là logic của bài tạp chí. Số mục cụ thể có thể thay đổi khi kết quả đã có.

## 3. Ranh giới đóng góp sau khi đối chiếu tài liệu

### Hướng chưa đủ mạnh

Các phát biểu sau không nên dùng làm đóng góp chính:

- “thêm ít mốc thời gian hơn”;
- “ưu tiên gói cần ít mốc trước”;
- “thu thập nhiều vi phạm rồi sửa chung”;
- “đặt một ngân sách cố định cho refinement”;
- “K=128 chạy tốt hơn K=8 và K=32 trên một lần chạy”.

Các ý đầu đã xuất hiện rất gần trong DDD mới. Kết quả K hiện tại chỉ là dấu hiệu
pilot, chưa có baseline hội nghị đồng bộ và chưa đủ để giải thích nguyên nhân.

### Giả thuyết đóng góp đáng theo đuổi

**Budgeted conflict selection for MaxSAT-DDD:** tại mỗi vòng DDD, không bắt buộc
xử lý mọi xung đột vừa phát hiện. Thuật toán chọn một tập xung đột và phương án
sửa dưới ngân sách kích thước mô hình, dựa trên lợi ích dự kiến đối với cận,
mức chi phí và các vi phạm lặp lại. Một cơ chế bắt buộc xử lý xung đột bị trì hoãn
và một bước fallback đầy đủ giữ cho thuật toán tiếp tục tiến triển.

Khác biệt dự kiến với hai công trình gần nhất:

- Shu, Xu và Baldacci chọn ít mốc để loại bỏ toàn bộ tập mẫu được đưa vào bài
  toán refinement;
- Helber, Bachtler và Wüllner chọn tập phép sửa nhỏ nhất để sửa toàn bộ xung đột
  quan sát được;
- bài của nhóm sẽ nghiên cứu **xung đột nào đáng được sửa ngay** khi mỗi vòng chỉ
  được phép tăng mô hình MaxSAT một lượng giới hạn.

Đây mới là giả thuyết. Trước khi viết “first” hoặc “novel”, cần tìm thêm theo ba
cụm: conflict selection in DDD, budgeted refinement và adaptive/lazy constraint
selection trong SAT/MaxSAT và decomposition.

### Biểu diễn toán sơ bộ để chốt ý tưởng

Ở vòng lặp \(k\), gọi \(\mathcal B_k\) là tập xung đột phát hiện được và \(D_k\)
là tập mốc hiện có. Mỗi xung đột \(b\in\mathcal B_k\) có một hoặc nhiều phương án
sửa hợp lệ \(r\in R_b\). Phương án \(r\) cần tập mốc mới
\(A_{br}\setminus D_k\).

Đặt:

- \(x_p=1\) nếu thêm mốc \(p\);
- \(z_{br}=1\) nếu chọn phương án sửa \(r\) của xung đột \(b\);
- \(y_b=1\) nếu quyết định xử lý xung đột \(b\) trong vòng hiện tại;
- \(c_p\) là chi phí của mốc \(p\), có thể bắt đầu bằng 1 rồi mở rộng thành số
  biến/clause dự kiến;
- \(w_b\) là lợi ích của việc xử lý \(b\), được tính từ loại vi phạm, mức độ lặp,
  tuổi chờ và tác động có thể kiểm chứng lên cận.

Một mô hình chọn sơ bộ là

\[
\max \sum_{b\in\mathcal B_k} w_b y_b-\lambda\sum_p c_p x_p
\]

với

\[
\sum_{r\in R_b}z_{br}=y_b,
\qquad
x_p\ge z_{br}\quad(p\in A_{br}\setminus D_k),
\qquad
\sum_p c_p x_p\le K,
\qquad
\sum_b y_b\ge 1.
\]

Mô hình này mới mô tả ý tưởng. Trước khi cài đặt phải làm rõ một phương án sửa
có thật sự loại bỏ xung đột hay chỉ thêm thông tin để xung đột không tái diễn ở
cùng dạng; đồng thời phải kiểm tra chiều liên kết giữa \(y_b\), \(z_{br}\) và
\(x_p\) để không nhận điểm giả. Ràng buộc cuối chỉ áp dụng khi có xung đột và tồn
tại một repair plan vừa ngân sách; nếu không, fallback phải tăng ngân sách hoặc
xử lý ít nhất một plan hợp lệ. Bản heuristic “chọn gói có ít mốc trước” hiện tại
là baseline đơn giản cho mô hình trên, không phải đóng góp cuối.

## 4. Dàn ý đề xuất cho bài COR

### 1. Introduction

**Câu hỏi của mục:** vì sao việc kiểm soát refinement quyết định khả năng mở rộng
của exact MaxSAT-DDD?

Nội dung cần viết:

1. Bối cảnh train rescheduling và yêu cầu vừa tìm nghiệm tốt sớm vừa chứng minh
   tối ưu.
2. Một đoạn ngắn về MaxSAT-DDD của Croella et al.
3. Một đoạn công khai bài hội nghị của nhóm: bài đó đã làm precedence propagation
   và hybrid AMO; các phần này trở thành baseline, không được liệt kê lại như
   đóng góp tạp chí.
4. Nút thắt mới: refinement quá ít làm nhiều vòng; refinement quá nhiều làm tăng
   biến, clause và thời gian MaxSAT.
5. Khoảng trống sau khi đối chiếu optimal/joint refinement: chưa giải quyết việc
   chọn tập con xung đột theo ngân sách trong MaxSAT-DDD cho train rescheduling.
6. Các câu hỏi nghiên cứu và danh sách đóng góp mới, chỉ viết sau khi thực nghiệm
   xác nhận.

Câu hỏi nghiên cứu dự kiến:

- **RQ1:** Chọn xung đột theo ngân sách có giữ được tính đúng và khả năng kết thúc
  của MaxSAT-DDD không?
- **RQ2:** Chính sách đề xuất có cải thiện số instance được chứng minh tối ưu và
  thời gian end-to-end so với Croella, bản hội nghị và refinement đơn giản không?
- **RQ3:** Lợi ích đến từ ít mốc/clause hơn, ít vòng hơn, hay cận tiến triển tốt
  hơn?
- **RQ4:** Hiệu quả có ổn định theo objective, kích thước instance và ngân sách
  hay không?

**Không viết lúc này:** abstract, con số cải thiện, câu “first method”, hoặc danh
sách contribution ở thì quá khứ.

### 2. Related Work and Positioning

#### 2.1 Exact train rescheduling

Tóm tắt ngắn MILP, CP, decomposition và logic-based methods. Chỉ giữ những bài
giúp đặt câu hỏi về giải chính xác, xung đột tài nguyên và thời gian chứng minh.

#### 2.2 Dynamic discretization discovery

Trình bày tiến trình từ DDD gốc đến sparse DDD, joint refinement và optimal
refinement. Tập trung vào ba lựa chọn: khởi tạo mốc, phát hiện xung đột và chọn
phép sửa.

#### 2.3 Constraint selection in iterative exact methods

Đối chiếu với lazy cuts/cut selection, đặc biệt bài của Leutwiler et al. về hậu
quả của việc đưa quá nhiều cut. Mục này dùng để xây logic “sửa có chọn lọc”.

#### 2.4 Positioning table

Bảng bắt buộc nên có các cột:

| Phương pháp | Bài toán | Solver lõi | Chọn xung đột? | Tối ưu mốc sửa? | Ngân sách tăng mô hình? | Bảo đảm kết thúc |
|---|---|---|---|---|---|---|
| Croella et al. | Train rescheduling | MaxSAT | Không | Không | Không | Có |
| Bài hội nghị của nhóm | Train rescheduling | MaxSAT | Không | Không | Không | Có |
| Shu et al. | CTSNDP | MIP | Tập mẫu đã thu thập | Có, xử lý chung | Batch trong matheuristic | Có |
| Helber et al. | CTSNDP | Exact refinement | Sửa tất cả quan sát | Có | Không phải mục tiêu chính | Có |
| Phương pháp dự kiến | Train rescheduling | MaxSAT | Có | Có thể dùng chung mốc | Có | Phải chứng minh |

Không dùng dấu kiểm nếu chưa xác minh trong bài gốc.

### 3. Problem Definition and Journal Baseline

**Mục tiêu:** cung cấp đủ ký hiệu để hiểu phần mới trong khoảng 2--3 trang, thay
vì tái bản toàn bộ mô hình hội nghị.

Nội dung:

1. Tập train, route cố định, operation, thời điểm vào resource, traversal/headway
   và ba objective.
2. Định nghĩa nghiệm khả thi và chứng nhận tối ưu.
3. Tóm tắt một vòng MaxSAT-DDD bằng sơ đồ: restricted model → lower bound → giải
   mã → kiểm tra trên bài toán gốc → refine hoặc dừng.
4. Nêu chính xác cấu hình hội nghị và dẫn bài hội nghị cho propagation/AMO.
5. Định nghĩa các số đo bottleneck: số vòng, số mốc mới, biến, hard/soft clauses,
   thời gian encode, MaxSAT, verify, và khoảng LB--UB.

**Tái sử dụng hợp lệ:** ký hiệu chuẩn và phương trình cần thiết, được viết lại và
trích dẫn.

**Không tái sử dụng:** phần giới thiệu, ví dụ, giả mã, bảng benchmark và lời kết
của bài hội nghị.

### 4. Budgeted Bound-Guided Refinement

#### 4.1 Violation bundles and valid repair plans

Định nghĩa rõ path violation, resource violation và missing cost level. Mỗi bundle
phải chỉ ra các mốc có thể thêm và vì sao từng repair plan là hợp lệ.

#### 4.2 Safe temporal bounds and forced precedence

Chỉ đưa các quy tắc cận thực sự dùng để tạo ứng viên hoặc tính điểm. Phân biệt
quy tắc an toàn với heuristic. Mọi cận phụ thuộc incumbent/cutoff phải có điều
kiện sử dụng rõ ràng.

#### 4.3 Cost and benefit of a refinement action

Chi phí nên đo mức tăng mô hình dự kiến, không chỉ đếm bundle. Lợi ích phải được
định nghĩa trước khi xem kết quả test; ví dụ conflict age, số vi phạm được phủ,
objective level liên quan và khả năng tạo propagation.

#### 4.4 Selection under a budget

Trình bày mô hình chọn, thuật toán giải chính xác hoặc heuristic và độ phức tạp.
Cần có baseline “fewest-new-points first” đúng với code hiện tại.

#### 4.5 Anti-starvation and fallback

Quy định khi nào một bundle trở thành bắt buộc, khi nào chạy full scan và khi nào
thêm toàn bộ refinement cần thiết. Không được chứng nhận tối ưu chỉ từ một lần
quét có giới hạn.

#### 4.6 Complete algorithm

Một giả mã duy nhất cho toàn vòng lặp, chỉ rõ nơi tạo LB, nơi cập nhật incumbent,
nơi verify và điều kiện dừng.

### 5. Correctness and Complexity

Các kết quả cần có:

1. **Tính an toàn của bound/precedence:** không loại nghiệm khả thi trong miền đã
   phát biểu.
2. **Tính hợp lệ của repair plan:** nếu chọn plan thì xung đột tương ứng không thể
   lặp lại dưới đúng điều kiện đã định nghĩa.
3. **Bất biến LB--UB:** restricted model cho cận dưới; nghiệm đã verify cho cận
   trên.
4. **Tiến triển:** khi chưa thể dừng, thuật toán thêm ít nhất một thông tin mới có
   ích.
5. **Kết thúc hữu hạn:** anti-starvation/fallback không thể trì hoãn vô hạn một
   refinement cần thiết trên miền thời gian nguyên hữu hạn.
6. **Độ phức tạp:** tạo bundle, chấm điểm/chọn và mức tăng kích thước MaxSAT.

Nếu chưa chứng minh được mục 4--5, bài chỉ có heuristic và phải hạ mức phát biểu.

### 6. Computational Study

#### 6.1 Reproducibility gate

Trước mọi bảng so sánh:

- chốt commit, checksum dataset, compiler, solver, seed, thread và giới hạn RAM;
- sửa khác biệt tolerance giữa solver và `verify_solution` đã nêu trong
  `code_review.md`;
- tái lập baseline hội nghị từ đúng binary/config hoặc ghi rõ dùng số đã công bố;
- kiểm tra mọi nghiệm bằng verifier độc lập;
- xuất bảng từ CSV bằng script, không chép số vào LaTeX.

#### 6.2 Instances and protocol

Dùng toàn bộ dataset cho đánh giá cuối. Tách tập tuning tham số khỏi tập báo cáo
nếu có đủ instance. Một lần chạy chỉ phù hợp để kiểm tra pipeline; với các case
rất nhanh cần chạy lặp để runtime có ý nghĩa.

#### 6.3 Methods compared

Tối thiểu:

- MaxSAT-DDD của Croella nếu tái lập được;
- đúng cấu hình bài hội nghị;
- `+B`;
- `+R` với heuristic hiện tại;
- `+B+R`;
- phương pháp chọn theo ngân sách mới;
- một exact formulation mạnh như Big-M MILP khi so sánh có cùng tiêu chí.

#### 6.4 Overall performance — RQ2

Báo solved/proved optimal, feasible, timeout/error, PAR-2, median/IQR và
solved-over-time. Không so mean runtime trên hai tập solved khác nhau như bằng
chứng phương pháp nhanh hơn.

#### 6.5 Ablation and mechanism — RQ3

Báo theo cặp trên cùng instance:

- số vòng DDD;
- số mốc mới và mốc cuối;
- biến, hard clauses, soft levels;
- thời gian encode/solve/verify/select;
- diễn biến LB, UB và gap;
- số bundle phát hiện, chọn, trì hoãn và xử lý bởi fallback.

#### 6.6 Budget sensitivity — RQ4

K=8, 32 và 128 hiện chỉ là ba điểm ban đầu. Thêm chế độ không giới hạn và ít
nhất một chính sách ngân sách thích nghi. Chọn tham số trước khi mở tập test cuối.

#### 6.7 Failure cases and objective dependence

Phân tích riêng stepwise, rounded và continuous. Nêu các trường hợp ngân sách làm
tăng số vòng, full scan tốn kém, propagation không giúp hoặc selection overhead
lớn hơn phần tiết kiệm.

### 7. Results

Chỉ tạo mục này sau khi pipeline đã qua reproducibility gate. Trật tự bảng/hình
dự kiến:

1. bảng kiểm tra đúng nghiệm và tái lập baseline;
2. ECDF hoặc solved-over-time cho hiệu năng tổng thể;
3. biểu đồ ghép cặp runtime/PAR-2;
4. bảng ablation;
5. bảng/biểu đồ cơ chế DDD;
6. sensitivity theo ngân sách;
7. bảng phân loại trường hợp thất bại.

Kết quả pilot K=8/32/128 hiện tại có thể được nhắc trong sổ thí nghiệm, chưa đưa
vào abstract hoặc conclusion.

### 8. Discussion

Trả lời lần lượt bốn RQ, giải thích vì sao phương pháp hiệu quả hoặc không hiệu
quả. So sánh lại với joint/optimal refinement. Bàn về khả năng chuyển sang mạng,
objective và MaxSAT backend khác; chỉ rõ giới hạn của route cố định, benchmark
72 instance và một môi trường máy.

### 9. Conclusion

Không tóm tắt bài hội nghị. Chỉ nêu câu hỏi mới, kết quả đã được kiểm chứng, giới
hạn chính và một hướng tiếp theo cụ thể.

### Declarations and artifact

Thêm Data and Code Availability, CRediT, funding, competing interests và tuyên bố
AI theo thông tin thật. [Mô tả chính thức của
COR](https://shop.elsevier.com/journals/computers-and-operations-research/0305-0548)
coi kết quả có thể tái lập đầy đủ là yêu cầu cốt lõi, nên artifact phải chứa code,
cấu hình, manifest dữ liệu, raw CSV và script tạo bảng/hình.

## 5. Ma trận bằng chứng trước khi bắt đầu viết

| Phát biểu dự kiến | Bằng chứng tối thiểu | Trạng thái hiện tại |
|---|---|---|
| Phương pháp giữ đúng nghiệm tối ưu | Định lý + exhaustive tests bài nhỏ + verifier độc lập | Chưa đủ; `code_review.md` còn vấn đề tolerance |
| Selection tốt hơn heuristic ít mốc trước | Ablation ghép cặp trên toàn bộ dataset | Chưa chạy |
| Ngân sách kiểm soát kích thước mô hình | Mốc/biến/clause theo vòng và tổng | Code đã có một số counter; cần kiểm tra schema/output |
| Nhanh hơn baseline hội nghị | Cùng máy, cùng cutoff, đúng commit/config; hoặc dùng số công bố với giới hạn rõ | Chưa nhận baseline hội nghị |
| Tổng quát qua objective | Kết quả Step/Round/Cont và phân tích failure | Pilot một lần cho K=8/32/128, chưa đủ |
| Khác optimal refinement gần đây | Bảng positioning và định nghĩa selection rõ | Có giả thuyết; cần tìm tài liệu bổ sung |

## 6. Tiêu chí go/no-go cho hướng bài báo

Chỉ chuyển từ bản thảo brainstorming hiện tại sang bản có các phát biểu kết quả
dùng cho submission khi đồng thời đạt:

1. verifier và tolerance đã thống nhất;
2. bài nhỏ xác nhận mọi cấu hình cho cùng optimum;
3. baseline hội nghị được truy nguyên;
4. phương pháp selection được đặc tả rõ hơn heuristic hiện tại;
5. pilot cho thấy lợi ích ở ít nhất một nhóm khó mà không làm hỏng rõ rệt hai
   objective còn lại;
6. số đo cơ chế giải thích được lợi ích;
7. literature search bổ sung không tìm thấy phương pháp trùng ý.

Nếu selection không vượt heuristic hiện tại, vẫn có thể viết một nghiên cứu thực
nghiệm về trade-off refinement, nhưng không nên trình bày như một thuật toán COR
mới. Nếu chỉ K=128 tốt hơn K=8/32, kết luận phù hợp là “ngân sách quá nhỏ gây bỏ
sót và panic”, chưa phải đóng góp khoa học.

## 7. Công việc tiếp theo theo thứ tự

1. Sửa correctness gate trong code và test theo `code_review.md`.
2. Bổ sung log theo từng vòng cho cost/benefit, bundle age, fallback, biến/clause,
   LB/UB và thời gian từng pha.
3. Định nghĩa một selection model tối thiểu và giữ heuristic hiện tại làm baseline.
4. Chạy một smoke test toàn dataset để kiểm tra pipeline, không dùng làm kết quả
   runtime cuối.
5. Nhận baseline hội nghị; khóa commit, dữ liệu và cấu hình.
6. Chạy pilot ablation, rồi mới quyết định công thức/chính sách cuối.
7. Sau khi qua tiêu chí go/no-go, thay các đoạn planned/pilot trong `main.tex`
   bằng phương pháp đã chốt và kết quả có thể truy nguyên; sau đó mới viết
   Abstract, highlights, contribution list và Conclusion cuối cùng.

## 8. Ghi chú thư mục và tài liệu tham khảo

- `main.tex` trong thư mục này đã có phần đặt vấn đề, related work, mô hình,
  phương pháp, nghĩa vụ chứng minh, thiết kế thực nghiệm, bảng pilot và
  discussion sơ bộ. Nội dung hội nghị chỉ được tóm tắt và trích dẫn như prior
  work; các kết quả cũ không được trình bày như đóng góp của bài tạp chí.
- Abstract và highlights vẫn để trống. Các phát biểu kết quả trong bản thảo đều
  được đánh dấu là pilot, planned evaluation hoặc claim cần bằng chứng.
- `student_implementation_guide_vi.tex` là hướng dẫn cài đặt hiện tại; cần cập
  nhật sau khi selection model được chốt.
- `upgrade_plan_vi.md` ghi audit và kế hoạch trước đó; dàn ý này thay thế phần
  “dàn bài dự kiến” rất ngắn trong tài liệu đó.
- Ba DOI trong `references.bib` đã được sửa khi rà soát: Bettinelli et al.
  `10.1016/j.trb.2017.10.005`, Mannino--Nakkerud
  `10.1016/j.omega.2022.102796`, và Leutwiler--Corman
  `10.1016/j.ejor.2022.02.043`.
