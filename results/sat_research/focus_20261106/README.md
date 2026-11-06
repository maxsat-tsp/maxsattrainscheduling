# Nhóm instance để thử ý tưởng mới

Danh sách cố định ở `selection.json`, chọn từ các lượt full đã kiểm toán:

- Bộ ba, solver commit `eaf0316`: `(72,68,60)`.
- Giới hạn chi phí, solver commit `6ba1b71`: `(72,68,59)`.
- CSOnet đã công bố, 120 giây: `(72,68,60)`.

Lấy hợp các ca chưa chứng minh tối ưu trong ít nhất một lượt. Như vậy nhóm
thử giữ cả ca vừa giải được và ca bị mất, thay vì bỏ các ca bị mất ra khỏi
phép so sánh. Mỗi tên chỉ chạy với objective được ghi trong danh sách.

| Objective | Số ca |
|---|---:|
| finsteps123 | 0 |
| infsteps180 | 4 |
| cont | 14 |
| Tổng cặp instance–objective | 18 |

`reused_transitivity.json` và `reused_bounds.json` được tính từ dữ liệu full
đã có. Không có lượt chạy mới khi tạo hai báo cáo này. Chúng giữ số full
thực tế riêng với phép tính trên nhóm khó. Hash các JSON nguồn và dataset
được ghi trong file lựa chọn.

Ví dụ chạy trên Linux, sau khi build release từ cây Git sạch:

```bash
FOCUS_MANIFEST=results/sat_research/focus_20261106/selection.json \
BIN=./target/release/ddd CORE_VARIANT=orders-transitive-glucose \
RUN_ID=focus-glucose-v7 bash run_maxsat_focused_experiments.sh
```

Script chỉ chạy 18 cặp ở 120 giây, tuần tự; cả vòng giới hạn 6 giờ. Báo cáo
`focus_comparison.json` tách ca giải thêm và ca bị mất với từng đối chứng.
Coverage ước tính của nhóm khó không thay thế lượt full mới. Script không
tự chạy toàn dataset. Chỉ chọn một cấu hình có tiến triển để xác nhận và
chạy full trước khi lập bảng cho bài báo.
