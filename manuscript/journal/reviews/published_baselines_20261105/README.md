# Tái sử dụng baseline và hai ca CPLEX cần kiểm tra lại

Bảng dưới là số optimum **được báo cáo trong CSV hội nghị 120 giây**.
Phần mềm kiểm tra tên instance, objective, chi phí, LB/UB và `total_time`.
CSV không có lịch; không gọi đây là kiểm tra độc lập lịch cũ.

| Baseline | finsteps123 | infsteps180 | cont | Tổng |
|---|---:|---:|---:|---:|
| MaxSAT-Journal, bản chạy trong hội nghị | 72 | 68 | 59 | 199 |
| CSOnet | 72 | 68 | 60 | 200 |
| Big-M Gurobi | 72 | 67 | 67 | 206 |
| Big-M CPLEX | 72 | 68 | 47 | 187 |

`status=ok` của MILP có thể chỉ là một lịch khả thi. Chỉ các dòng có
`cost=UB` và `LB=UB` theo sai số `1e-6` mới được đếm ở bảng này.

Hai số CPLEX mâu thuẫn với lịch mới đã kiểm tra độc lập:

| Instance/objective | CPLEX: cost=LB=UB | Chi phí lịch khả thi đã kiểm tra |
|---|---:|---:|
| `trackA1/finsteps123` | 24 | 23 |
| `stationB12/infsteps180` | 120 | 98 |

Một cận dưới đúng không thể cao hơn chi phí một lịch khả thi. Vì vậy, hai
dòng này chưa thể dùng làm chứng cứ tối ưu. Không sửa số trong CSV gốc,
không lấy các giá trị CPLEX đang bị tranh chấp làm oracle cho SAT mới.

Lịch chứng cứ nằm trong bản nén đã lưu tại
`results/sat_research/vm_paper120_20261105/raw_results.tar.gz`, phần
`baseline-paper120-20bd54d/CSOnet/{objective}.json`. Hai lịch đều được kiểm tra
bằng `audit_journal_campaign.independently_verify_solution` và không có lỗi.
Các baseline MaxSAT và Gurobi cùng báo cáo chi phí 23 và 98.

Mã xuất LP hiện tại còn đặt mọi thời điểm không quá 43.200, trong khi lịch
`stationB12` nói trên có mốc 44.203. Giới hạn đó loại bỏ ít nhất lịch chứng
cứ này. Đây là vấn đề cần xử lý khi chạy lại CPLEX; chưa đủ bằng chứng để
kết luận nó giải thích cả hai dòng CSV cũ, vì chưa biết binary đã tạo CSV.

Chạy so sánh với bảng đã công bố:

```bash
python3 quick_scripts/analyze/audit_aglr_campaign.py <campaign-dir> \
  --timeout 120 --conference-reference results \
  --conference-profile published-csv-120 \
  --conference-runtime-mode assumed-equivalent \
  --reuse-published-baselines results
```

Auditor chỉ điền các baseline/objective chưa có kết quả mới, không trộn các
instance cũ và mới trong cùng một objective. Metadata giữ hash từng CSV,
phạm vi kiểm tra và giả định runtime. Khi còn mâu thuẫn ở bảng tham chiếu,
cổng cuối vẫn là `NOT YET`; các phép thử SAT độc lập vẫn tiếp tục.

Việc tiếp theo cho baseline: chạy lại hai ca CPLEX từ mô hình đã kiểm tra,
giữ nguyên các lịch chứng cứ, rồi xác định có cần chạy lại objective liên
quan hay không. Những số cũ còn lại được bảo toàn để tái sử dụng tối đa.
