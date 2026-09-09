# Chính sách bảo mật

## Nguyên tắc

1. Quyền tối thiểu: workspace mới mặc định `read-only`.
2. Phạm vi nhỏ: chỉ thêm thư mục dự án, không thêm gốc ổ đĩa.
3. Đường dẫn xác định: mọi path tool đều tương đối và phải nằm trong workspace.
4. Ghi có điều kiện: exact edit kiểm tra số lần khớp trước khi thay đổi.
5. Xác minh: đọc lại file và xem Git diff sau khi sửa.

## Cơ chế bảo vệ

- Server bind `127.0.0.1` và kiểm tra Host để giảm DNS rebinding.
- `/mcp` yêu cầu Bearer token; `/setup` chỉ khả dụng qua localhost.
- So sánh token constant-time.
- Chặn `..`, absolute path, symlink và reparse point ở mọi thành phần đã tồn tại.
- Chặn `.env`, `.ssh`, `.git`, `.aws`, `.azure`, `.kube`, `.gnupg`, các phần mở rộng
  khóa/chứng thư và tên credential phổ biến.
- Giới hạn nội dung 1 MiB cho mỗi lần đọc/ghi.
- `git status` và `git diff` gọi executable trực tiếp bằng argv cố định, không qua shell.

## Token

Token được tạo bằng CSPRNG và lưu trong `%LOCALAPPDATA%\AI_Actuator\config.json`.
Không commit file cấu hình hoặc token vào Git. Nếu token từng xuất hiện trong ảnh/log, hãy
regenerate tại `/setup` và cập nhật MCP client.

## Báo cáo lỗ hổng

Không đăng token, đường dẫn cá nhân hoặc file nhạy cảm vào issue công khai. Hãy rotate token
trước khi chia sẻ log phục vụ debug.

