---
name: system-expert
description: Quản trị và giám sát tài nguyên máy tính Windows 11 & WSL (CPU, RAM, Disk, Process, Network, Services). Tự động chạy lệnh kiểm tra hệ thống.
---

# Kỹ Năng Quản Trị Hệ Thống (System Expert)

Khi người dùng hỏi về tình trạng máy tính, tài nguyên, kiểm tra RAM, CPU, ổ cứng hoặc quản lý tiến trình:

1. **Kiểm tra Bộ nhớ RAM & Swap:**
   - Trong WSL: Chạy lệnh `free -h`
   - Xem tiến trình ngốn RAM nhất: `ps aux --sort=-%mem | head -n 10`
   - Trong Windows: Chạy PowerShell: `Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First 10 Name, Id, @{Name="RAM(MB)";Expression={[math]::Round($_.WorkingSet64/1MB,2)}}`

2. **Kiểm tra CPU & Phần cứng:**
   - Lệnh: `lscpu` hoặc `top -b -n 1 | head -n 15`
   - Windows: `Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores, NumberOfLogicalProcessors`

3. **Kiểm tra Dung lượng Ổ Cứng (Disk Space):**
   - Lệnh: `df -h /mnt/c` hoặc `df -h /`

4. **Nguyên tắc hành động:**
   - Tự động thực thi lệnh qua công cụ `run_command` để lấy số liệu thực tế trước khi kết luận cho người dùng.
