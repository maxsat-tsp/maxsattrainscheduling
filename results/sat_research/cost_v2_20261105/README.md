# Biểu diễn chi phí thưa: chưa tăng coverage

Commit solver `27b6859`, VM `trp`, timeout 30 giây cho screen và 120 giây cho
promote. Cả hai cấu hình giữ refinement CSOnet và cách gửi điều kiện `legacy`;
`Core-sparse` chỉ bỏ các mức chi phí trung gian chưa được DDD tạo.

| Giai đoạn | Cách mã hóa | finsteps123 | infsteps180 | cont |
|---|---|---:|---:|---:|
| 30 giây, 24 instance | legacy | 24 | 22 | 17 |
| 30 giây, 24 instance | sparse | 24 | 22 | 17 |
| 120 giây, 24 instance | sparse | 24 | 22 | 19 |
| Hội nghị, 120 giây | CSOnet | 24 | 22 | 20 |

`Core-sparse` dùng ít hạng tử chi phí hơn, nhưng vẫn mất một instance
`cont` trong tập phát triển. `core_selection.json` ghi rõ không chọn cấu hình
để chạy full 72 instance. Mọi kết quả đã qua auditor; không có lỗi nghiệm,
panic hoặc mã thoát sai.

SHA-256 bản raw:
`5cb028fe17b27e4f8e9450ebfbc33f68413e4628b47db676f63db7fc43dc136a`.

Vòng kế tiếp là phép thử biến thứ tự tài nguyên; nó không kết hợp với cách
mã hóa chi phí thưa.
