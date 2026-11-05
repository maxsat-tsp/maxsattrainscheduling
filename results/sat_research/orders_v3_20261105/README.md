# Biến thứ tự dùng chung: tăng coverage phát triển nhưng chưa vượt full

Commit solver `be60148`, VM `trp`. Cấu hình `Core-orders` giữ refinement
CSOnet và cách gửi điều kiện/chi phí cũ; mỗi cặp tài nguyên chỉ tạo một biến
thứ tự rồi dùng lại ở các mốc sau.

| Giai đoạn | finsteps123 | infsteps180 | cont | Tổng |
|---|---:|---:|---:|---:|
| 30 giây, legacy | 24 | 22 | 18 | 64 |
| 30 giây, orders | 24 | 22 | 18 | 64 |
| 120 giây, orders, 24 instance | 24 | 22 | 20 | 66 |
| Full 120 giây, orders | 72 | 68 | 59 | 199 |
| Mốc hội nghị 120 giây | 72 | 68 | 60 | 200 |

Lượt promote đạt mốc phát triển nên script chạy full. Full giữ được hai
objective đầu và tăng PAR-2 ở `cont` so với mốc hội nghị, nhưng mất một
instance `cont`; cổng chưa đạt. Không chạy xác nhận ba lần vì full chưa vượt
coverage. Các JSON đã qua audit, không có nghiệm sai hoặc crash.

Các ca `cont` bị timeout ở full gồm `origA8`, `origB11`, `trackA8`,
`trackA11`, `trackA12`, `trackB12`, `stationA1`, `stationA2`, `stationA8`,
`stationA9`, `stationA11`, `stationA12`, `stationB12`. Telemetry cho thấy
`stationA9` còn cách cận 20 đơn vị ở cuối cutoff; đây là mục tiêu chẩn đoán
cho vòng tiếp theo.

SHA-256 bản raw:
`47772384ed4b6742e5bc9c7faee02c487d79d970c749872f79df282dd125010d`.

Vòng tiếp theo thử kết hợp orders với cây chi phí thưa để xem việc giảm biến
chi phí có giúp giữ coverage full. Kết quả này chưa được đưa vào bản thảo.
