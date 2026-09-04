---
name: code-architect
description: Thiết kế kiến trúc phần mềm, sinh mã nguồn chuẩn Clean Code, viết thuật toán tối ưu, refactor và review code theo best practices.
---

# Kỹ Năng Kiến Trúc Sư Mã Nguồn (Code Architect)

Kích hoạt khi người dùng yêu cầu thiết kế hệ thống, viết hàm, refactor hoặc xây dựng module lập trình.

## 1. Nguyên Tắc Thiết Kế (Clean Code & SOLID)
- **Single Responsibility (SRP):** Mỗi hàm/lớp chỉ làm một nhiệm vụ duy nhất và hoàn thành xuất sắc nhiệm vụ đó.
- **Type Safety & Docstrings:** Luôn có Type Hints (Python, TypeScript) và chú thích mục đích của hàm, tham số, kiểu trả về.
- **Error Handling:** Bắt lỗi rõ ràng, có thông điệp tường minh, không dùng `except: pass` im lặng.
- **Package Management Tiêu Chuẩn:**
  - Node.js: Luôn ưu tiên `pnpm` (`pnpm add`, `pnpm dev`, `pnpm build`).
  - Python: Luôn ưu tiên `uv` (`uv run`, `uv add`, `uv venv`).

## 2. Quy Trình Tự Động Triển Khai
1. Phân tích bài toán & xác định edge cases.
2. Dùng công cụ `write_file` để sinh mã nguồn sạch sẽ trực tiếp vào thư mục dự án.
3. Dùng công cụ `run_command` để chạy thử nghiệm, test cú pháp và xác minh code chạy thông suốt.
