---
name: fullstack-dev
description: Xây dựng ứng dụng Fullstack hiện đại (React/Vue/Next.js, FastAPI/Node.js, SQLite/PostgreSQL, TailwindCSS). Hướng dẫn khởi tạo và deploy dự án hoàn chỉnh.
---

# Kỹ Năng Phát Triển Ứng Dụng Fullstack (Fullstack Dev)

Kích hoạt khi người dùng muốn xây dựng website, API, dashboard hoặc ứng dụng hoàn chỉnh từ đầu đến cuối.

## 1. Khởi Tạo Dự Án Chuẩn
- **Backend FastAPI (Python):**
  - Khởi tạo: `uv init --app my-backend && cd my-backend && uv add fastapi uvicorn[standard]`
  - Chạy dev: `uv run uvicorn main:app --reload`
- **Frontend React / Next.js (TypeScript):**
  - Khởi tạo: `pnpm create next-app@latest my-frontend --typescript --tailwind --app`

## 2. Quy Trình Phối Hợp Của Agent
1. Lập sơ đồ cấu trúc thư mục rõ ràng.
2. Dùng `write_file` tạo mã nguồn API backend và giao diện frontend.
3. Cung cấp file README và lệnh chạy một bước cho người dùng.
