# Rà soát nội dung bản thảo COR

**Tệp được rà soát:** `manuscript/journal/cor/main.tex`  
**Ngày rà soát:** 15-10-2026  
**Phạm vi:** lập luận, mức hoàn thiện, mô hình toán, thiết kế thực nghiệm, tính dễ
đọc và thuật ngữ. Báo cáo này không thay cho kiểm tra số liệu sau khi chiến dịch
thực nghiệm hoàn tất.

## Kết luận hiện tại

Bản thảo đã có một câu hỏi nghiên cứu có tiềm năng: trong mỗi vòng DDD, nên xử
lý vi phạm nào khi chỉ cho phép mô hình MaxSAT tăng thêm một lượng giới hạn. Bài
cũng đã phân biệt được đóng góp của bài hội nghị với hướng mới và đã mô tả bốn
cấu hình ablation cần chạy.

Tuy nhiên, bản hiện tại **chưa sẵn sàng để nộp**. Đây vẫn là bản làm việc vì bốn
lý do chính:

1. Abstract còn trống và chưa có kết quả chính.
2. Phương pháp được đặt làm đóng góp trung tâm, bộ chọn theo utility, mới là mô
   hình sơ bộ và chưa có quy tắc tính điểm đủ để cài đặt.
3. Điều kiện tiến triển và kết thúc hữu hạn còn được ghi như một nghĩa vụ phải
   kiểm tra, chưa phải một kết quả đã chứng minh.
4. Phần thực nghiệm, Discussion và Conclusion đang ghi kế hoạch làm việc thay vì
   báo cáo bằng chứng của một nghiên cứu đã hoàn tất.

Bản thảo **đủ tốt để dẫn đường cho vòng thực nghiệm một lần trên toàn bộ dữ
liệu**. Kết quả của vòng này dùng để kiểm tra tính đúng, ablation B/R và phát
hiện điểm nghẽn. Chưa nên dùng vòng chạy đó để chốt một phát biểu về tốc độ nếu
nhiều lần chạy chỉ kéo dài vài chục mili giây.

## Các việc chặn submission

| Mức | Vị trí | Vấn đề | Cách giải quyết |
|---|---|---|---|
| P0 | Dòng 49--52 | Abstract trống. | Viết sau khi đã khóa phương pháp và bảng kết quả chính. |
| P0 | Dòng 406--439 | Bộ chọn theo utility chưa phải một thuật toán có thể tái lập. Chưa có công thức cụ thể cho \(w_b\), cách tạo \(R_b\), cách chọn \(\lambda\), hoặc cách xử lý nhiều phương án cùng dùng một mốc. | Chốt đặc tả, cài đặt và so sánh trực tiếp với greedy; nếu không làm, bỏ nó khỏi đóng góp và đổi phạm vi bài. |
| P0 | Dòng 530--535 | Bài chưa chứng minh rằng mỗi refinement luôn thêm thông tin mới và loại được nghiệm vi phạm hiện tại. | Chứng minh riêng cho travel-time, resource và forced-order action; thêm kiểm thử lặp để phát hiện gói không tạo tiến triển. |
| P0 | Dòng 612--697 | Chưa có chiến dịch chính và chưa có baseline có provenance. | Chạy 864 lời gọi đã chuẩn bị, kiểm toán baseline hội nghị, sau đó mới quyết định các lượt chạy lặp và sensitivity. |
| P0 | Dòng 699--750 | Discussion và Conclusion nói về kết quả dự kiến và danh sách việc còn lại. | Viết lại sau thực nghiệm để trả lời từng RQ bằng số liệu và giới hạn đã quan sát. |
| P1 | Dòng 760--770 | CRediT, competing interest và acknowledgements chưa có nội dung. | Chốt với tất cả tác giả trước khi nộp. |

## Ranh giới đóng góp cần chốt

Hiện bài đang kể đồng thời hai câu chuyện:

- **Câu chuyện đã cài đặt:** cận thời gian, thứ tự tài nguyên bắt buộc và greedy
  refinement với ngân sách số mốc;
- **Câu chuyện dự kiến:** chọn một tập vi phạm và repair plan theo utility và
  chi phí tăng mô hình.

Hai câu chuyện này không nên cùng được trình bày như một phương pháp hoàn chỉnh.
Trước khi viết Abstract, nhóm cần chọn một trong hai hướng:

### Hướng A: hoàn thành bộ chọn mới

Đóng góp trung tâm là chọn vi phạm dưới ngân sách. Bản greedy hiện tại trở thành
baseline. Bài cần có:

- định nghĩa đầy đủ repair plan, chi phí và lợi ích;
- một thuật toán chọn có thể cài đặt đúng từ bài;
- bảo đảm tiến triển/kết thúc;
- ablation so sánh bộ chọn mới, greedy và sửa tất cả vi phạm;
- bằng chứng cơ chế: mốc, clause, số vòng, thời gian MaxSAT và diễn biến cận.

Đây là hướng phù hợp hơn với khoảng trống mà Helber, Bachtler và Wüllner nêu ra:
họ tối ưu tập phép sửa cho **tất cả** xung đột quan sát được và để lại câu hỏi
chọn xung đột nào cần sửa. Công trình đó dùng các từ chuẩn như *conflict*, *fix*,
*time point*, *refinement* và *relaxation*; bài này nên bám vào cùng hệ thuật ngữ
([Helber et al., 2026](https://arxiv.org/html/2609.39269v1)).

### Hướng B: dừng ở B/R greedy

Khi đó tiêu đề, RQ và phát biểu mới phải giới hạn ở một nghiên cứu thuật toán và
thực nghiệm về trade-off refinement trong MaxSAT-DDD. Hướng này vẫn có thể tạo
một bài hữu ích nếu kết quả rất rõ và phân tích cơ chế tốt, nhưng độ mới cho COR
có rủi ro cao hơn vì các nghiên cứu DDD gần đây đã tối thiểu hóa số mốc hoặc kích
thước relaxation.

Hai tiêu đề làm việc dễ hiểu hơn:

- nếu theo Hướng A: **Budgeted Selection of Refinement Conflicts in MaxSAT-Based
  Dynamic Discretization for Train Rescheduling**;
- nếu theo Hướng B: **Bound Propagation and Budgeted Refinement in MaxSAT-Based
  Dynamic Discretization for Train Rescheduling**.

## Rà soát lập luận

### Introduction

Phần mở đầu đã đi đúng từ bài toán, DDD, bài hội nghị đến nút thắt refinement.
Ba điểm cần sửa:

1. RQ2 hiện so trực tiếp với baseline hội nghị. So sánh này trộn thay đổi về
   preprocessing/encoding với thay đổi B/R và có thể trộn cả môi trường chạy.
   Nên tách thành hai câu hỏi:
   - B và R tạo khác biệt gì trong bốn cấu hình chạy từ cùng một binary?
   - phương pháp cuối so với kết quả hội nghị như thế nào khi provenance và môi
     trường đủ tương đương?
2. Đoạn 120--130 đưa nhiều tên nội bộ (`B`, `R`, package, distinct-point budget,
   age rule, fallback) trước khi người đọc thấy một ví dụ. Nên mô tả trade-off
   bằng lời trước, sau đó mới đặt tên hai thành phần.
3. Chưa có danh sách đóng góp đã chốt. Chỉ thêm danh sách này khi biết Hướng A
   hay B là phiên bản cuối và đã có kết quả hỗ trợ.

### Related Work and Positioning

Việc đối chiếu Croella, Shu và Helber là đúng hướng. Croella là baseline trực
tiếp của mô hình MaxSAT-DDD cho train rescheduling
([Croella et al., 2024](https://doi.org/10.1016/j.cor.2024.106679)). Bài hội nghị
của nhóm dùng thuật ngữ *precedence propagation* và *hybrid AMO encodings*; đây
là prior work và không nên đổi tên thành đóng góp mới
([bản hội nghị trên arXiv](https://arxiv.org/abs/2606.16814)).

Bảng positioning hiện có một dòng phương pháp chưa cài đặt và chú thích cảnh báo
người viết không được coi nó là kết quả. Trong bản nộp, bảng chỉ nên chứa phương
pháp đã hoàn thành. Dòng dự kiến và lời nhắc nội bộ chuyển sang tài liệu kế hoạch.

Mục “Selection in iterative exact methods” mới có một ví dụ về Benders cut.
Nếu selection là đóng góp chính, cần tìm thêm công trình gần về lazy constraint,
cut selection hoặc adaptive refinement; nếu không, tiêu đề tiểu mục đang rộng
hơn bằng chứng mà mục đó cung cấp.

### Problem Definition

Phần mô hình ngắn và nhìn chung dễ theo dõi, nhưng còn bốn chỗ chưa tự chứa:

1. Ở dòng 229--236, \(p_v\) được giới thiệu cho visit không phải cuối nhưng lại
   được dùng để tính exit time của visit cuối. Cần định nghĩa \(p_v\) cho cả hai
   trường hợp: thời gian đến successor hoặc thời gian tối thiểu để giải phóng tài
   nguyên cuối.
2. Ba hàm chi phí chỉ được mô tả bằng tên trong mã. Với thời gian tính bằng giây,
   nên viết rõ
   
   \[
   c^{\mathrm{fin}}(d)=
   \begin{cases}
   0,&d=0,\\
   1,&1\le d\le180,\\
   2,&181\le d\le360,\\
   3,&d\ge361,
   \end{cases}
   \qquad
   c^{\mathrm{inf}}(d)=\left\lceil\frac d{180}\right\rceil,
   \qquad c^{\mathrm{cont}}(d)=d.
   \]
   
   Đây là đúng với `DelayCostThresholds::f123()` và
   `infinite_staircase()` trong mã hiện tại.
3. Câu “left endpoint selected in each partial partition” xuất hiện trước khi
   partial partition được định nghĩa. Hoặc định nghĩa interval ngay tại đây,
   hoặc bỏ câu này và mô tả trực tiếp cách literal \(d_v(\tau)\) mã hóa thời gian.
4. Câu cuối dòng 264--266 là lời nhắc bảo trì mã, không phải nội dung khoa học.
   Thay bằng định nghĩa chính xác và nêu verifier dùng cùng hàm chi phí trong phần
   reproducibility.

### Phương pháp và ký hiệu

Đây là phần cần sửa kỹ nhất.

#### Một “mốc” phải là cặp visit--time

Trong mã, một mốc là `(VisitId, time)`. Trong mô hình dòng 409--425, \(p\) trông
như chỉ là một giá trị thời gian. Cần định nghĩa

\[
p=(v,\tau),\qquad p\in\mathcal P_k,
\]

và \(D_k\) là tập các cặp visit--time đã có. Hai visit cùng có mốc 180 không
phải là cùng một biến và không được tính là một mốc dùng chung.

#### Đơn vị của ngân sách chưa nhất quán

Greedy hiện tại dùng \(K\) là **số mốc mới khác nhau**. Mô hình đề xuất lại dùng

\[
\sum_p c_p x_p\le K,
\]

trong đó \(c_p\) là mức tăng biến và clause dự kiến. Nếu \(c_p\ne1\), \(K\) không
còn là số mốc. Cần chọn một trong hai cách:

- giữ \(K\) theo số mốc và dùng \(c_p=1\) trong ràng buộc; hoặc
- đổi tên thành ngân sách tăng mô hình \(C\), quy định rõ cách ước lượng \(c_p\),
  và báo sai số giữa chi phí dự đoán với số biến/clause thực tế.

#### Công thức utility chưa đủ để cài đặt

\(w_b\) hiện “có thể kết hợp” tuổi, số lần lặp, mức objective và độ phủ. Cách mô
tả này cho phép nhiều cách cài đặt cho kết quả khác nhau. Bản cuối phải quy định:

- từng thành phần của điểm số và miền giá trị;
- cách chuẩn hóa để một đại lượng không lấn át các đại lượng còn lại;
- cách chọn trọng số và \(\lambda\) mà không xem trước tập test;
- điểm tuổi được gắn với một vi phạm cụ thể hay một cặp visit;
- cách tính độ phủ mà không đếm lặp lợi ích của một mốc dùng chung.

Nếu chưa đủ dữ liệu để học utility, nên bắt đầu bằng một thứ tự ưu tiên xác định
trước và thực hiện ablation cho từng thành phần của điểm số.

#### Ký hiệu đang bị dùng lại

- `B` vừa là tên Component B vừa là chi phí incumbent ở dòng 329--336;
- `R` vừa là Component R, \(R_v\) là chi phí còn lại, và \(R_b\) là tập repair
  plan;
- \(\mathcal B_k\) lại là tập vi phạm.

Nên dùng tên đầy đủ trong prose và đổi ký hiệu, chẳng hạn chi phí incumbent là
\(\bar F\), phần chi phí còn lại là \(\rho_v\), tập repair plan là
\(\mathcal R_b\), và tập vi phạm là \(\mathcal V_k\).

#### Exit bound chưa được định nghĩa

\(L_{e_v}\) ở dòng 356 và 511 chưa được định nghĩa. Nên dùng

\[
\underline e_v=
\begin{cases}
L_{s(v)},&s(v)\text{ tồn tại},\\
L_v+p_v,&v\text{ là visit cuối},
\end{cases}
\]

rồi viết điều kiện \(\underline e_v>U_w\). Cách này khớp với mã và dễ đọc hơn
việc đặt một cận dưới lên ký hiệu hàm \(e_v(t)\).

#### “Tuổi” chưa bảo đảm một cặp xung đột được xử lý

Identifier hiện chứa cả visit và thời gian hiện tại. Nếu cùng hai visit tiếp tục
xung đột ở các thời gian khác, mã coi đó là một vi phạm mới và tuổi trở về 0.
Vì vậy, phát biểu chính xác là safeguard không trì hoãn vô hạn **cùng một vi
phạm ở cùng các thời gian**. Muốn bảo đảm công bằng ở mức cặp visit, cần một khóa
tuổi ổn định hơn hoặc một chứng minh khác.

### Correctness and Complexity

Ba proposition về cận và thứ tự là nền tốt. Phần này vẫn thiếu kết quả trung tâm
cho selective refinement:

1. mỗi loại action có loại nghiệm vi phạm hiện tại hay không;
2. action đã chọn có thể trở thành clause trùng và không thêm thông tin hay
   không;
3. số trạng thái có thể refine có hữu hạn dưới horizon nào;
4. khi hết thời gian, cặp LB/UB được hiểu thế nào và điều kiện nào cho phép gọi
   nghiệm là tối ưu;
5. bộ chọn utility có giữ các bất biến trên hay chỉ giữ progress bằng fallback.

Câu mở đầu dòng 480--482 có giọng “chỉ được chấp nhận sau khi...”. Nên viết
trực tiếp: các proposition chứng minh quy tắc toán học; kiểm thử ở phần thực
nghiệm kiểm tra mã hiện thực đúng các quy tắc đó.

### Computational Study

Thiết kế 4 cấu hình và chạy toàn bộ 72 instance cho 3 objective là phù hợp cho
vòng đầu. Cần sửa các điểm sau trước khi biến mục này thành protocol cuối:

1. **Phân biệt control nội bộ và baseline hội nghị.** `RC2-Base` chạy từ binary
   mới là control tốt nhất để tách B/R. Kết quả hội nghị là baseline lịch sử và
   chỉ dùng cho runtime trực tiếp khi phần cứng, cutoff, solver và tiêu chí hoàn
   thành đủ tương đương.
2. **Định nghĩa “solved”.** Với một bài exact, PAR-2 nên dùng thời gian đến lúc
   chứng minh tối ưu. Thời gian tìm nghiệm khả thi đầu tiên báo riêng. Từ
   “completed” hiện chưa cho biết trạng thái nào được tính.
3. **Chuẩn hóa PAR-2.** Văn bản đang dùng cả `PAR2` và `PAR-2`; chọn `PAR-2` trong
   toàn bài và trong ký hiệu công thức.
4. **Không so trung vị trên tập solved khác nhau.** Bản thảo đã nêu đúng nguyên
   tắc này. Nên báo paired ratio/difference trên giao các bài solved và đồng thời
   báo coverage/PAR-2 trên toàn bộ tập.
5. **Một lần chạy chưa đủ cho runtime rất ngắn.** Vòng 864 lời gọi dùng được cho
   correctness và chênh lệch lớn. Bản cuối cần quy định số lần lặp, warm-up,
   cách lấy trung vị và khoảng bất định cho các ca chạy vài chục mili giây.
6. **Chốt baseline trước khi xem kết quả.** Câu “Croella và MILP được đưa vào nếu
   có thể làm tương đương” chưa phải protocol. Cần ghi tiêu chí đưa vào/loại ra
   từ trước và cách báo khi không tái lập được.
7. **Sensitivity chỉ chạy nơi có ý nghĩa.** \(K\) không ảnh hưởng cấu hình không
   có R. Chỉ cần \(K=32,128,\texttt{all}\) cho các cấu hình có selector; sau vòng
   đầu mới quyết định có adaptive policy hay không.
8. **Bảng pilot không thuộc bài nộp.** Nó chứa kết quả từ mã trước correctness
   gate, nhiều `panic`, và trung vị loại các ca lỗi. Giữ bảng trong runbook hoặc
   phụ lục nội bộ; xóa khỏi main text trước submission.

Danh sách commit, lockfile, checksum, stdout và stderr ở dòng 560--572 cần có
trong artifact/runbook. Trong bài chính, chỉ cần một đoạn reproducibility ngắn
và dẫn tới phụ lục hoặc repository.

## Rà soát bốn nhóm lỗi diễn đạt bắt buộc

### 1. Diễn đạt phòng thủ

Có nhiều câu nói với người viết hoặc tự bảo vệ claim thay vì nói với độc giả:

- dòng 100: “insufficient as a novelty claim”;
- dòng 190--192: “must not be presented as a completed method”;
- dòng 432: “must be computable before the test outcome is observed”;
- dòng 436--439: “research specification, not a description...”;
- dòng 480--482: “accepted only after...”;
- dòng 560: “campaign is accepted only when...”;
- dòng 586: “not rerun merely to fill...”;
- dòng 646: “cannot support a submission claim”;
- dòng 678: “the only justified reading...”;
- dòng 696--697: lời nhắc không chuyển số liệu vào Abstract;
- dòng 743--750: danh sách việc còn lại trong Conclusion.

Các quy tắc quản lý nghiên cứu này là cần thiết, nhưng nên đặt trong
`outline_brainstorm_vi.md`, runbook hoặc comment LaTeX. Main text chỉ giữ nội
dung khoa học ở thể trực tiếp và trung tính.

Ví dụ, thay:

> These developments make adding fewer time points insufficient as a novelty
> claim.

bằng:

> Recent studies already reduce the number of time points added during
> refinement. We study the complementary decision of which detected violations
> to repair in the current iteration when model growth is limited.

### 2. Quá nặng chi tiết kỹ thuật

Các chi tiết sau đúng nhưng đặt chưa đúng chỗ:

- tên flag `chain-cost-forced` trong bảng chính;
- commit, source diff, `Cargo.lock`, dependency patch, stdout/stderr trong phần
  Computational Study;
- identifier chứa thời gian hiện tại ở phần mô tả cấp cao;
- “missing objective levels” trong giả mã khi chưa giải thích người đọc cần biết
  nó để làm gì;
- cả phương pháp greedy đã cài đặt và MIP utility dự kiến trong cùng một luồng
  thuật toán.

Giữ mô hình, bất biến và các số đo cần để tái lập trong bài. Chuyển tên flag,
schema log và danh sách file vào phụ lục/artifact. Giả mã chính chỉ nên mô tả một
phiên bản thuật toán cuối cùng.

### 3. Câu khó hiểu

Các câu khó chủ yếu do chứa nhiều mệnh đề hoặc dùng danh từ trừu tượng:

- dòng 278--280: chưa rõ “left endpoint” thuộc cấu trúc nào;
- dòng 381--382: phân biệt identifier bằng “same concrete violation at the same
  times” khó hình dung và không cần ở cấp này;
- dòng 400--404: “proxy for the increase in MaxSAT difficulty” cần nói rõ proxy
  là số mốc và difficulty được đo bằng biến/clause/thời gian;
- dòng 702--707: ba lần dùng “asks what...” có thể thay bằng ba câu ngắn;
- dòng 733--741: một đoạn conclusion liệt kê quá nhiều chi tiết cài đặt.

Mỗi đoạn nên đi theo thứ tự: đối tượng là gì, quyết định nào được đưa ra, vì sao
quyết định đó hợp lệ, và đại lượng nào sẽ đo tác động.

### 4. Thuật ngữ khó hoặc ít phổ biến

| Thuật ngữ hiện tại | Đánh giá | Cách dùng đề nghị |
|---|---|---|
| Dynamic Discretization Discovery, refinement, conflict, fix, time point, relaxation | Chuẩn trong nghiên cứu DDD gần đây. | Giữ và định nghĩa lần đầu. |
| MaxSAT, RC2, at-most-one, incumbent, lower/upper bound, PAR-2 | Chuẩn với độc giả tối ưu tổ hợp nhưng không phải mọi độc giả railway đều biết. | Viết đầy đủ/giải thích ngắn ở lần đầu. |
| violation package | Tên riêng của mã, ít thấy trong các bài DDD gần. | Dùng “refinement candidate” hoặc “repair action”; có thể ghi “package in the implementation” ở phụ lục. |
| point budget / distinct-point budget | Có thể hiểu nhưng chưa nói rõ một point là visit--time. | “refinement budget measured by newly added visit--time points”. |
| utility-aware selection | `utility` quá rộng khi chưa có utility cụ thể. | Chỉ dùng sau khi định nghĩa hàm điểm; trước đó dùng “value-based selection” hoặc “budgeted conflict selection”. |
| forced resource order | Hiểu được nhưng chưa khớp thuật ngữ prior work. | “implied resource precedence” hoặc “mandatory resource precedence”; liên hệ với *precedence propagation*. |
| anti-starvation fallback | Thuật ngữ khoa học máy tính, nặng và chưa đúng hoàn toàn với khóa tuổi hiện tại. | “maximum-wait safeguard” và mô tả phạm vi bảo đảm. |
| full violation scan | Tên thao tác cài đặt. | “check all route and resource constraints” ở main text. |
| `B`, `R`, `BR`, `chain-cost-forced` | Nhãn thí nghiệm nội bộ. | Bảng đầu tiên ghi tên mô tả đầy đủ; nhãn ngắn chỉ dùng trong hình/bảng sau đó. |

## Rà soát theo từng phần

| Phần | Trạng thái | Việc chính |
|---|---|---|
| Title/Keywords | Cần chốt theo hướng A/B | Mở rộng DDD trong tiêu đề hoặc dùng “MaxSAT-based dynamic discretization”. |
| Abstract | Trống | Chờ phương pháp và kết quả. |
| Introduction | Khung tốt | Tách RQ nội bộ khỏi so sánh lịch sử; giảm tên thành phần; thêm contribution sau cùng. |
| Related Work | Khá tốt | Bổ sung selection gần; bỏ phương pháp chưa làm khỏi positioning cuối. |
| Problem Definition | Thiếu định nghĩa | Sửa \(p_v\), ba objective, interval/left endpoint và ký hiệu exit bound. |
| Method | Chưa khóa | Chọn greedy hay utility; thống nhất đơn vị ngân sách và thuật ngữ. |
| Correctness | Chưa đủ | Chứng minh action validity, progress và finite termination. |
| Computational Study | Protocol vòng đầu tốt | Phân biệt control/baseline; định nghĩa solved; bỏ pilot khỏi bản nộp. |
| Results | Chưa có | Tạo từ raw CSV sau audit. |
| Discussion | Mới là giả thuyết | Viết lại theo bốn RQ sau kết quả. |
| Conclusion | Là ghi chú dự án | Thay bằng kết quả, giới hạn và một hướng tiếp theo. |
| Declarations | Chưa hoàn tất | Chốt CRediT, competing interests, funding và artifact commit. |

## Thứ tự sửa đề nghị

1. Chọn Hướng A hoặc B và khóa tên phương pháp.
2. Sửa các định nghĩa không phụ thuộc kết quả: objective, visit--time point,
   exit bound, đơn vị ngân sách và bảng thuật ngữ.
3. Hoàn tất nghĩa vụ correctness cho ba loại repair action.
4. Chạy chiến dịch một lần trên toàn bộ dataset; dùng `RC2-Base` cùng binary làm
   control chính cho B/R.
5. Kiểm toán baseline hội nghị; chỉ so runtime trực tiếp khi điều kiện tương
   đương.
6. Từ kết quả vòng đầu, quyết định implementation cuối và các lượt sensitivity
   hoặc lặp thời gian thực sự cần.
7. Thay toàn bộ đoạn planned/pilot bằng Results; viết lại Discussion, Conclusion
   và Abstract.
8. Chạy lần cuối bốn lượt rà soát ngôn ngữ: phòng thủ, quá kỹ thuật, khó hiểu và
   thuật ngữ hiếm; sau đó mới đóng gói submission.

## Tiêu chí để gọi là bản sẵn nộp

Bản thảo chỉ nên chuyển sang trạng thái submission-ready khi có đủ các điều sau:

- một phương pháp cuối cùng khớp với mã;
- định lý và kiểm thử hỗ trợ phát biểu exact;
- raw results vượt qua validator độc lập;
- baseline có provenance và quy tắc so sánh công bằng;
- mỗi RQ được trả lời bằng một bảng/hình hoặc phân tích cụ thể;
- không còn dữ liệu pilot lỗi trong main text;
- Abstract, Discussion và Conclusion chỉ nêu kết quả đã được kiểm chứng;
- thuật ngữ nhất quán và không còn tên flag nội bộ trong lời văn chính;
- CRediT, competing interests, funding và code/data availability đã được tác giả
  xác nhận.
