---
name: troubleshoot-crash
description: Chẩn đoán nguyên nhân ứng dụng bị crash, freeze, mã lỗi Windows Event ID 1000, WER, Access Violation (0xC0000005) và crash dump (.dmp).
---

# Kỹ Năng Chẩn Đoán Lỗi & Crash Ứng Dụng (Troubleshoot Crash)

Kích hoạt khi người dùng gặp lỗi chương trình bị văng, crash, treo, hoặc cần đọc log lỗi hệ thống.

## 1. Điều Tra Windows Event Viewer
Chạy lệnh PowerShell qua `run_command` để lọc 5 sự kiện lỗi Crash gần nhất:
```powershell
powershell.exe -NoProfile -Command "Get-WinEvent -FilterHashtable @{LogName='Application'; Level=2} -MaxEvents 5 | Select-Object TimeCreated, Id, Message | Format-List"
```

## 2. Các Mã Lỗi Phổ Biến & Hướng Xử Lý
- **0xC0000005 (Access Violation):** Lỗi truy cập vùng nhớ không hợp lệ (thường do con trỏ NULL, bộ nhớ bị giải phóng sớm, hoặc xung đột driver/DLL).
- **0xC00000FD (Stack Overflow):** Tràn ngăn xếp do đệ quy vô tận hoặc cấp phát mảng quá lớn trên Stack.
- **Event ID 1000:** Lỗi ứng dụng bị treo/dừng đột ngột. Kiểm tra module gây lỗi (`Faulting module name`).
