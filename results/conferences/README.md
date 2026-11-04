# Kết quả CSOnet của bài hội nghị

Thư mục này giữ nguyên dữ liệu được nhập từ commit nguồn
`c427a104c3c6f844e515efb7f898b684553b0f3f` trên nhánh `origin/doquangvinh`.
Commit này là nguồn của các file kết quả, không phải bằng chứng về commit đã
dùng để biên dịch binary chạy thực nghiệm.

## Những gì đã được kiểm tra

Chạy:

```bash
python3 quick_scripts/analyze/summarize_conference.py results/conferences
```

Auditor kiểm tra đúng 72 tên instance cho mỗi objective, dựng lại độc lập mọi
lịch có `status=ok`, và yêu cầu `cost=lb=ub`. Kết quả đã xác nhận là:

| Objective | Tối ưu đã kiểm tra | Timeout | PAR-2 từ `total_time` |
|---|---:|---:|---:|
| `finsteps123` | 72/72 | 0 | 0.120 s |
| `infsteps180` | 68/72 | 4 | 18.574 s |
| `cont` | 58/72 | 14 | 63.596 s |

Chi tiết kiểm tra máy đọc được nằm trong `conference_audit.json`; bảng tổng hợp
nằm trong `summary_conference.csv`.

## Giới hạn sử dụng

Có thể dùng coverage và chi phí tối ưu đã kiểm tra làm mốc phát hiện lỗi hồi
quy. Chưa được dùng thời gian này để tuyên bố phương pháp mới nhanh hơn, vì dữ
liệu không có bản ghi về máy, môi trường và hash của tệp chạy. Bảng so sánh
thời gian chính phải dùng CSOnet được chạy lại cùng điều kiện với AGLR.

Không sửa dữ liệu gốc bằng tay. Nếu auditor phát hiện khác biệt chi phí, giữ
nguyên cả hai kết quả và tìm nguyên nhân từ mã, instance hoặc cấu hình chạy.
