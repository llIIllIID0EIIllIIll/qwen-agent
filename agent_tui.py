import os
import sys
import json
import re
import shutil
import subprocess
import time
import urllib.request
import urllib.parse
from pathlib import Path
from typing import List, Dict, Any, Tuple, Optional

import httpx
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.text import Text
from rich.live import Live
from rich.table import Table

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
PLANNER_MODEL = os.environ.get("PLANNER_MODEL", "qwen3.5:latest")
EXECUTOR_MODEL = os.environ.get("EXECUTOR_MODEL", "qwen2.5-coder:7b")

console = Console()

# Native Skills của Qwen Hybrid Agent
SKILL_DIRS = [
    Path("/mnt/c/Users/User/qwen-hybrid-agent/skills")
]

def sanitize_str(s: str) -> str:
    if not isinstance(s, str):
        return str(s)
    return s.encode("utf-8", "ignore").decode("utf-8", "ignore")

def sanitize_messages(messages: List[Dict[str, str]]) -> List[Dict[str, str]]:
    sanitized = []
    for m in messages:
        sanitized.append({
            "role": m.get("role", "user"),
            "content": sanitize_str(m.get("content", ""))
        })
    return sanitized

def discover_skills() -> Dict[str, Dict[str, str]]:
    skills = {}
    for base in SKILL_DIRS:
        if not base.exists():
            continue
        for child in base.iterdir():
            if child.is_dir():
                skill_md = child / "SKILL.md"
                if skill_md.exists():
                    try:
                        content = skill_md.read_text(encoding="utf-8", errors="ignore")
                        content = sanitize_str(content)
                        desc = ""
                        if "---" in content:
                            parts = content.split("---", 2)
                            if len(parts) >= 3:
                                header = parts[1]
                                for line in header.splitlines():
                                    if line.startswith("description:"):
                                        desc = line.split(":", 1)[1].strip()
                        skills[child.name] = {
                            "name": child.name,
                            "path": str(child),
                            "file": str(skill_md),
                            "description": desc or content[:200].replace("\n", " "),
                            "full_md": content
                        }
                    except Exception:
                        pass
    return skills

SKILLS_REGISTRY = discover_skills()

SLASH_COMMANDS = [
    ("/clear", "Xóa sạch màn hình terminal và làm mới phiên"),
    ("/model", "Hiển thị và kiểm tra trạng thái phân công Planner vs Executor"),
    ("/skills", "Xem danh sách và mô tả chi tiết tất cả Qwen Native Skills"),
    ("/system", "Chạy kiểm tra tài nguyên CPU, RAM và Disk ngay lập tức"),
    ("/history", "Xem lại số lượng tin nhắn và ngữ cảnh hiện tại"),
    ("/reset", "Đặt lại toàn bộ ngữ cảnh đoạn hội thoại"),
    ("/help", "Xem hướng dẫn chi tiết các lệnh slash commands"),
    ("/exit", "Thoát chương trình Qwen Agent")
]

class SlashCommandCompleter(Completer):
    def get_completions(self, document, complete_event):
        text_before_cursor = document.text_before_cursor
        if text_before_cursor.startswith("/"):
            for cmd, desc in SLASH_COMMANDS:
                if cmd.lower().startswith(text_before_cursor.lower()):
                    yield Completion(
                        cmd,
                        start_position=-len(text_before_cursor),
                        display=f"{cmd:<10} - {desc}",
                        display_meta="Qwen Command"
                    )

pt_style = Style.from_dict({
    "prompt": "ansicyan bold",
    "completion-menu.completion": "bg:#1e293b #e2e8f0",
    "completion-menu.completion.current": "bg:#2563eb #ffffff bold",
    "completion-menu.meta.completion": "bg:#0f172a #94a3b8 italic",
    "completion-menu.meta.completion.current": "bg:#1d4ed8 #f1f5f9 bold",
    "scrollbar.background": "bg:#1e293b",
    "scrollbar.button": "bg:#38bdf8",
})

# System Prompt dành cho Planner (Qwen3.5)
PLANNER_SYSTEM_PROMPT = f"""Bạn là Qwen Planner & Architect (Bộ não tư duy chiến lược của Qwen Hybrid Agent).
BẠN CÓ CÁNH TAY THỰC THI MẠNH MẼ: Qwen Coder (Executor) - sở hữu toàn quyền chạy lệnh shell Linux/WSL, tìm kiếm, đọc/ghi file và tương tác trực tiếp với hệ điều hành.

GIAO THỨC PHỐI HỢP TỰ CHỦ (AUTONOMOUS SYNERGY PROTOCOL):
Bạn phân tích ý định của người dùng bằng toàn bộ khả năng ngữ nghĩa tự nhiên (không phụ thuộc bất kỳ từ khóa cố định nào).
Mỗi phản hồi của bạn BẮT BUỘC kết luận trạng thái thực thi bằng 1 trong 2 thẻ chuẩn:

1. [STATUS: COMPLETED] - Khi tác vụ đã hoàn tất hoặc KHÔNG CẦN THAO TÁC MÁY TÍNH:
   - Áp dụng khi: Chào hỏi, xã giao, trả lời câu hỏi lý thuyết, khoa học, toán học, triết học, giải thích khái niệm, làm thơ, dịch thuật.
   - Hoặc khi: Đã hoàn tất mục tiêu và tổng hợp báo cáo kết quả cuối cùng cho người dùng.
   - Định dạng: Trả lời tự nhiên hoặc trình bày báo cáo Markdown ngắn gọn, kèm thẻ `[STATUS: COMPLETED]` ở cuối.
   - TUYỆT ĐỐI KHÔNG xuất khối [ACTION_PLAN].

2. [STATUS: NEED_ACTION] - Khi CẦN CODER THỰC THI TRÊN MÁY HOẶC TRA CỨU:
   - Áp dụng khi: Bất kỳ yêu cầu nào cần kiểm tra máy, liệt kê thư mục, đọc/sửa/xóa file, chạy lệnh shell, kiểm tra database, mạng, tiến trình, docker, hoặc tra cứu internet.
   - Định dạng bắt buộc:
     ### 🎯 Mục tiêu: [Mục tiêu cụ thể]
     [ACTION_PLAN]
     1. [Bước 1 cụ thể cho Coder]
     2. [Bước 2 cụ thể cho Coder]
     [STATUS: NEED_ACTION]
   - TUYỆT ĐỐI KHÔNG xuất `### 🎯 Kết quả:` ở vòng lập kế hoạch đầu tiên, vì Coder chưa thực thi công cụ nào.

3. QUY TẮC LIỆT KÊ TỆP TRONG THƯ MỤC (Downloads, Desktop, v.v.):
   - Khi người dùng hỏi "trong download có gì", "có file gì trong thư mục X", "xem danh sách file":
     -> YÊU CẦU CODER DÙNG `list_dir` hoặc lệnh shell `ls -lh <thư_mục>`.
     -> TUYỆT ĐỐI KHÔNG dùng `search_files` để liệt kê thư mục (vì search_files chỉ dùng để tìm kiếm tên file mờ).

4. QUY TẮC ĐỌC VÀ XEM NỘI DUNG TỆP (BẮT BUỘC):
   - Khi người dùng hỏi xem hoặc đọc nội dung file (ví dụ: "nội dung file có gì", "đọc file", "xem file", "file viết gì"):
     -> BẠN BẮT BUỘC PHẢI LẬP [ACTION_PLAN] ĐỂ CODER GỌI `read_file`. TUYỆT ĐỐI KHÔNG TỰ BỊA ĐẶT NỘI DUNG KHI CHƯA GỌI TOOL!

5. TÌM KIẾM TỆP THÔNG MINH (Fuzzy Search):
   - Khi tìm kiếm file cụ thể theo tên/từ khóa, yêu cầu Coder sử dụng công cụ `search_files` với cơ chế Fuzzy Search mờ siêu tốc.
   - Cơ chế Re-planning & PLAN WORK-AROUND:
     + Khi Coder báo cáo chưa tìm thấy mục tiêu hoặc gặp lỗi, tự động lập [ACTION_PLAN] bước kế tiếp để tiếp tục chạy.
     + Tuyệt đối trung thực, KHÔNG BỊA ĐẶT kết quả.

MÔI TRƯỜNG THỰC TẾ:
- Hệ thống: Linux WSL2 trên Windows 11.
- WSL User: `hoancauit` (Home: `/home/hoancauit`) | Windows User: `User` (Mount tại `/mnt/c/Users/User`).
- Thư mục dự án: `/mnt/c/Users/User/qwen-hybrid-agent`.
- Thư mục Downloads: `/mnt/c/Users/User/Downloads`.
- BẠN CÓ TOÀN QUYỀN TRUY CẬP VÀ ĐIỀU PHỐI HỆ THỐNG: đọc, sửa, tạo, xóa, di chuyển file, tra cứu log, tìm kiếm file/lỗi, quản lý tiến trình và chạy lệnh hệ thống.

CÁC KỸ NĂNG CÓ THỂ ĐƯA VÀO PLAN:
{chr(10).join([f"- {name}: {info['description']}" for name, info in SKILLS_REGISTRY.items()])}
"""

# System Prompt dành cho Executor (Qwen2.5-Coder)
EXECUTOR_SYSTEM_PROMPT = f"""Bạn là Qwen Executor & System Engineer (Cánh tay thực thi chuyên sâu).
Bạn có TOÀN QUYỀN TRUY CẬP HỆ THỐNG để đọc, sửa, xóa, di chuyển file, chẩn đoán lỗi và chạy lệnh.

Nhiệm vụ cốt lõi của bạn:
1. TUÂN THỦ PLAN: Căn cứ vào Plan của Planner, bạn PHẢI CHUYỂN HÓA THÀNH CÁC TOOL CALL CỤ THỂ để thực thi trên máy tính.
2. TÌM KIẾM FILE: Hãy ưu tiên sử dụng công cụ `search_files` vì nó hỗ trợ Fuzzy Search mờ siêu tốc quét toàn hệ thống trong 0.1s thay vì chạy lệnh find thủ công.
3. ĐỌC FILE: Khi Plan yêu cầu đọc nội dung file, sử dụng ngay `read_file`.
4. NẾU KHÔNG CÓ TÁC VỤ THỰC THI (chào hỏi, giải thích lý thuyết thuần túy):
   -> KHÔNG XUẤT BẤT KỲ KHỐI JSON TOOL CALL NÀO. Tuyệt đối KHÔNG gọi web_search vô nghĩa chỉ để tìm kiếm câu chào hỏi hay xã giao.
5. KHI CÓ TÁC VỤ CẦN CHẠY TRÊN MÁY:
   Xuất công cụ theo định dạng JSON duy nhất:
```json
[
  {{"tool": "search_files", "query": "tên_file_hoặc_từ_khóa"}},
  {{"tool": "read_file", "path": "đường_dẫn_file", "max_lines": 500}},
  {{"tool": "write_file", "path": "đường_dẫn_file", "content": "..."}},
  {{"tool": "delete_file", "path": "đường_dẫn"}},
  {{"tool": "move_file", "src": "...", "dst": "..."}},
  {{"tool": "copy_file", "src": "...", "dst": "..."}},
  {{"tool": "list_dir", "path": "đường_dẫn"}},
  {{"tool": "run_command", "cmd": "lệnh_shell"}},
  {{"tool": "grep_text", "query": "từ_khóa", "path": "."}},
  {{"tool": "diagnose_system", "target": "all"}},
  {{"tool": "inspect_process", "action": "list|find|kill", "name": "...", "pid": "..."}},
  {{"tool": "web_search", "query": "..."}},
  {{"tool": "activate_skill", "name": "..."}}
]
```
6. NGUYÊN TẮC:
- Môi trường là WSL2: dùng lệnh bash/Linux (`uname -a`, `free -h`, `cat /etc/os-release`, v.v.).
- Nếu cần can thiệp Windows, dùng `powershell.exe -NoProfile -Command "..."` hoặc `cmd.exe /c "..."`.
- Đường dẫn Windows phải mount qua `/mnt/c/...`.
- Sau khi thực thi, tổng hợp báo cáo trung thực, rõ ràng cho Planner."""

def resolve_path(raw_path: str) -> Path:
    p_str = raw_path.strip().strip("'\"")
    # Ưu tiên nhận diện download/downloads trước
    if p_str.lower() in ("download", "downloads", "~/downloads", "c:\\users\\public\\downloads", "c:/users/public/downloads"):
        candidate = Path("/mnt/c/Users/User/Downloads")
        if candidate.exists():
            return candidate
        return Path.home() / "Downloads"

    win_match = re.match(r"^([a-zA-Z]):[\\/](.*)", p_str)
    if win_match:
        drive = win_match.group(1).lower()
        sub = win_match.group(2).replace("\\", "/")
        return Path(f"/mnt/{drive}/{sub}")

    return Path(p_str).expanduser()

def perform_web_search(query: str) -> str:
    try:
        url = "https://api.duckduckgo.com/?q=" + urllib.parse.quote(query) + "&format=json"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = json.loads(resp.read().decode("utf-8", "ignore"))
            abstract = data.get("AbstractText", "")
            topics = data.get("RelatedTopics", [])
            results = []
            if abstract:
                results.append(abstract)
            for t in topics:
                if isinstance(t, dict) and "Text" in t:
                    results.append(t["Text"])
                if len(results) >= 3:
                    break
            if results:
                return "\n".join([f"- {r}" for r in results])
    except Exception as e:
        return f"Không thể tra cứu internet: {str(e)}"
    return f"Không tìm thấy kết quả tóm tắt cho '{query}'."

def robust_read_file(p: Path, max_lines: int = 500, offset: int = 0) -> str:
    if not p.exists():
        return f"Lỗi: Không tìm thấy file {p}"
    
    # 1. Đọc bằng nhiều encoding
    content = None
    for enc in ["utf-8", "utf-16", "utf-16-le", "cp1252", "latin-1"]:
        try:
            content = p.read_text(encoding=enc)
            break
        except Exception:
            continue
            
    # 2. Fallback qua cat hoặc PowerShell nếu bị Permission lock
    if content is None:
        try:
            win_m = re.match(r"^/mnt/([a-zA-Z])/(.*)", str(p))
            if win_m:
                win_path = f"{win_m.group(1).upper()}:\\{win_m.group(2).replace('/', chr(92))}"
                ps_res = subprocess.run(
                    ["powershell.exe", "-NoProfile", "-Command", f"Get-Content -Path '{win_path}' -Raw"],
                    capture_output=True, text=True, timeout=15
                )
                if ps_res.returncode == 0 and ps_res.stdout:
                    content = ps_res.stdout
            if content is None:
                cat_res = subprocess.run(f"cat '{p}'", shell=True, capture_output=True, text=True, timeout=15)
                if cat_res.returncode == 0:
                    content = cat_res.stdout
        except Exception:
            pass

    if content is None:
        return f"Lỗi: Không thể đọc file {p} (bị khóa hoặc giới hạn quyền truy cập)"

    lines = content.splitlines()
    total = len(lines)
    if total > max_lines:
        trimmed = lines[-max_lines:] if offset == 0 else lines[offset:offset+max_lines]
        header = f"[Tệp gồm {total} dòng. Trích xuất {len(trimmed)} dòng gần nhất để debug]:\n"
        return header + "\n".join(trimmed)
    return content

def robust_write_file(p: Path, content: str) -> str:
    p.parent.mkdir(parents=True, exist_ok=True)
    if p.exists():
        try:
            os.chmod(p, 0o666)
        except Exception:
            pass
    try:
        p.write_text(content, encoding="utf-8", errors="ignore")
        return f"Thành công: Đã ghi nội dung vào {p} ({len(content)} bytes)"
    except PermissionError:
        # Fallback qua PowerShell cho Windows files
        win_m = re.match(r"^/mnt/([a-zA-Z])/(.*)", str(p))
        if win_m:
            win_path = f"{win_m.group(1).upper()}:\\{win_m.group(2).replace('/', chr(92))}"
            encoded = content.replace("'", "''")
            ps_cmd = f"Set-Content -Path '{win_path}' -Value '{encoded}' -Encoding UTF8"
            res = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True, timeout=20)
            if res.returncode == 0:
                return f"Thành công (qua PowerShell): Đã ghi nội dung vào {win_path}"
        # Fallback shell tee
        res = subprocess.run(f"cat << 'EOF_AGY' > '{p}'\n{content}\nEOF_AGY", shell=True, capture_output=True, text=True, timeout=20)
        if res.returncode == 0:
            return f"Thành công: Đã ghi nội dung vào {p}"
        return f"Lỗi: Không thể ghi vào {p} (Permission denied)"
    except Exception as e:
        return f"Lỗi ghi file: {str(e)}"

def robust_delete_file(p: Path) -> str:
    if not p.exists():
        return f"Đường dẫn {p} không tồn tại."
    try:
        os.chmod(p, 0o777)
    except Exception:
        pass
    try:
        if p.is_dir():
            shutil.rmtree(str(p), ignore_errors=True)
        else:
            p.unlink(missing_ok=True)
        return f"Thành công: Đã xóa {p}"
    except Exception:
        win_m = re.match(r"^/mnt/([a-zA-Z])/(.*)", str(p))
        if win_m:
            win_path = f"{win_m.group(1).upper()}:\\{win_m.group(2).replace('/', chr(92))}"
            ps_res = subprocess.run(["powershell.exe", "-NoProfile", "-Command", f"Remove-Item -Path '{win_path}' -Force -Recurse"], capture_output=True, text=True, timeout=20)
            if ps_res.returncode == 0:
                return f"Thành công (qua PowerShell): Đã xóa {win_path}"
        res = subprocess.run(f"rm -rf '{p}'", shell=True, capture_output=True, text=True, timeout=20)
        if res.returncode == 0:
            return f"Thành công: Đã xóa {p}"
        return f"Lỗi xóa: Không thể xóa {p}"

def robust_move_file(src: Path, dst: Path) -> str:
    if not src.exists():
        return f"Lỗi: Nguồn {src} không tồn tại"
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.move(str(src), str(dst))
        return f"Thành công: Đã di chuyển {src} -> {dst}"
    except Exception:
        res = subprocess.run(f"mv -f '{src}' '{dst}'", shell=True, capture_output=True, text=True, timeout=30)
        if res.returncode == 0:
            return f"Thành công: Đã di chuyển {src} -> {dst}"
        return f"Lỗi di chuyển: {src} -> {dst}"

def robust_copy_file(src: Path, dst: Path) -> str:
    if not src.exists():
        return f"Lỗi: Nguồn {src} không tồn tại"
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        if src.is_dir():
            shutil.copytree(str(src), str(dst), dirs_exist_ok=True)
        else:
            shutil.copy2(str(src), str(dst))
        return f"Thành công: Đã sao chép {src} -> {dst}"
    except Exception:
        res = subprocess.run(f"cp -rf '{src}' '{dst}'", shell=True, capture_output=True, text=True, timeout=30)
        if res.returncode == 0:
            return f"Thành công: Đã sao chép {src} -> {dst}"
        return f"Lỗi sao chép: {src} -> {dst}"

def tool_search_files(query: str, root_path: str = None, max_results: int = 10) -> str:
    """Tìm kiếm file thông minh bằng thuật toán Fuzzy Matching (so khớp mờ) siêu tốc."""
    clean_q = str(query or "").strip().strip("'\"")
    if not clean_q:
        return "Lỗi: Cần cung cấp từ khóa hoặc tên file để tìm kiếm."

    # Nếu query truyền vào thực chất là một đường dẫn thư mục -> Tự động chuyển thành liệt kê file trong thư mục đó
    dir_candidate = resolve_path(clean_q)
    if dir_candidate.exists() and dir_candidate.is_dir():
        items = list(dir_candidate.iterdir())
        if not items:
            return f"Thư mục '{dir_candidate}' hiện đang trống (không có file nào)."
        files_info = []
        for it in items[:50]:
            try:
                sz = it.stat().st_size
                sz_str = f"{sz/1024:.1f} KB" if sz < 1024*1024 else f"{sz/(1024*1024):.1f} MB"
                mtime = time.strftime('%Y-%m-%d %H:%M', time.localtime(it.stat().st_mtime))
                files_info.append(f"- {'📁' if it.is_dir() else '📄'} {it.name} ({sz_str} | {mtime})")
            except Exception:
                files_info.append(f"- {'📁' if it.is_dir() else '📄'} {it.name}")
        return f"[Danh sách {len(items)} mục trong thư mục {dir_candidate}]:\n" + "\n".join(files_info)

    import difflib
    search_dirs = []
    if root_path and root_path not in (".", ""):
        p = resolve_path(root_path)
        if p.exists():
            search_dirs.append(str(p))

    if not search_dirs:
        candidates = [
            "/mnt/c/Users/User/qwen-hybrid-agent",
            "/home/hoancauit/.gemini/antigravity-cli/brain",
            "/mnt/c/Users/User/Downloads",
            "/mnt/c/Users/User/Desktop",
            "/mnt/c/Users/User/Documents",
            "/home/hoancauit",
            "/mnt/c/Users/User"
        ]
        for c in candidates:
            if Path(c).exists() and c not in search_dirs:
                search_dirs.append(c)

    prune_dirs = "-name '.git' -o -name 'node_modules' -o -name '.cache' -o -name 'venv' -o -name '.venv' -o -name 'AppData' -o -name '.cargo' -o -name '.rustup'"
    dirs_str = " ".join([f"'{d}'" for d in search_dirs])

    q_base = Path(clean_q).name
    tokens = [t for t in re.split(r"[-_\s\.]+", Path(clean_q).stem) if len(t) >= 2]
    token_filter = " ".join([f"-iname '*{t}*'" for t in tokens]) if tokens else f"-iname '*{clean_q}*'"

    cmd = f"find {dirs_str} -maxdepth 6 \\( {prune_dirs} \\) -prune -o -type f {token_filter} -print 2>/dev/null | head -n 120"
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=15)
    raw_files = list(set([f.strip() for f in res.stdout.splitlines() if f.strip() and not f.endswith(".metadata.json")]))

    if not raw_files:
        cmd_broad = f"find {dirs_str} -maxdepth 4 \\( {prune_dirs} \\) -prune -o -type f -print 2>/dev/null | head -n 250"
        res_b = subprocess.run(cmd_broad, shell=True, capture_output=True, text=True, timeout=15)
        raw_files = list(set([f.strip() for f in res_b.stdout.splitlines() if f.strip() and not f.endswith(".metadata.json")]))

    if not raw_files:
        return f"Không tìm thấy file nào khớp mẫu '{clean_q}' trên toàn bộ hệ thống."

    target_lower = q_base.lower()
    scored = []
    for f_path in raw_files:
        p_obj = Path(f_path)
        fname_lower = p_obj.name.lower()
        if target_lower == fname_lower:
            score = 1.0
        elif target_lower in fname_lower:
            score = 0.90 + (len(target_lower) / len(fname_lower)) * 0.09
        else:
            ratio = difflib.SequenceMatcher(None, target_lower, fname_lower).ratio()
            matched = sum(1 for t in tokens if t.lower() in fname_lower)
            bonus = (matched / len(tokens)) * 0.2 if tokens else 0
            score = min(0.89, ratio * 0.7 + bonus)
        scored.append((score, f_path, p_obj))

    scored.sort(key=lambda x: x[0], reverse=True)
    top_matches = [item for item in scored if item[0] >= 0.40][:max_results]
    if not top_matches:
        top_matches = scored[:3]

    output_lines = [f"🔍 KẾT QUẢ TÌM KIẾM MỜ (FUZZY SEARCH) CHO '{clean_q}':"]
    for rank, (score, f_path, p_obj) in enumerate(top_matches, 1):
        try:
            sz = p_obj.stat().st_size
            sz_str = f"{sz/1024:.1f} KB" if sz < 1024*1024 else f"{sz/(1024*1024):.1f} MB"
            mtime = time.strftime('%Y-%m-%d %H:%M', time.localtime(p_obj.stat().st_mtime))
        except Exception:
            sz_str = "N/A"
            mtime = "N/A"

        match_pct = int(score * 100)
        tag = "⭐ (Khớp cao)" if match_pct >= 85 else ""
        output_lines.append(f"{rank}. [{match_pct}%] {p_obj.name} {tag}")
        output_lines.append(f"   • Đường dẫn: {f_path}")
        output_lines.append(f"   • Kích thước: {sz_str} | Sửa đổi: {mtime}")

    return "\n".join(output_lines)

def tool_grep_text(query: str, path: str = ".", case_insensitive: bool = True) -> str:
    p = resolve_path(path)
    flag = "-i" if case_insensitive else ""
    cmd = f"grep -rn {flag} --exclude-dir='.git' --exclude-dir='node_modules' '{query}' '{p}' 2>/dev/null | head -n 30"
    res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=20)
    out = res.stdout.strip()
    if not out:
        return f"Không tìm thấy chuỗi '{query}' trong '{p}'."
    return f"Kết quả tìm kiếm cho '{query}' tại '{p}':\n{out}"

def tool_diagnose_system(target: str = "all") -> str:
    parts = []
    try:
        free_res = subprocess.run("free -h", shell=True, capture_output=True, text=True, timeout=10)
        parts.append(f"=== [Bộ nhớ RAM & Swap] ===\n{free_res.stdout.strip()}")
    except Exception:
        pass
    try:
        df_res = subprocess.run("df -h / /mnt/c 2>/dev/null", shell=True, capture_output=True, text=True, timeout=10)
        parts.append(f"=== [Dung lượng Disk (Root & Windows C:)] ===\n{df_res.stdout.strip()}")
    except Exception:
        pass
    try:
        ps_res = subprocess.run("ps aux --sort=-%mem | head -n 6", shell=True, capture_output=True, text=True, timeout=10)
        parts.append(f"=== [Top 5 Tiến trình tốn RAM nhất] ===\n{ps_res.stdout.strip()}")
    except Exception:
        pass
    try:
        ss_res = subprocess.run("ss -tulpn 2>/dev/null | head -n 10", shell=True, capture_output=True, text=True, timeout=10)
        if ss_res.stdout.strip():
            parts.append(f"=== [Cổng mạng đang lắng nghe] ===\n{ss_res.stdout.strip()}")
    except Exception:
        pass
    try:
        dmesg_res = subprocess.run("dmesg -T 2>/dev/null | grep -iE 'error|segfault|killed|oom' | tail -n 5", shell=True, capture_output=True, text=True, timeout=10)
        if dmesg_res.stdout.strip():
            parts.append(f"=== [Cảnh báo lỗi nhân hệ thống] ===\n{dmesg_res.stdout.strip()}")
    except Exception:
        pass
    return "\n\n".join(parts) if parts else "Không thể trích xuất thông tin chẩn đoán hệ thống."

def tool_inspect_process(action: str = "list", name: str = "", pid: str = "") -> str:
    if action == "list" or (not name and not pid):
        cmd = "ps -eo pid,ppid,%cpu,%mem,cmd --sort=-%mem | head -n 15"
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        return f"=== 15 Tiến trình hàng đầu ===\n{res.stdout.strip()}"
    elif action == "find" and name:
        cmd = f"ps aux | grep -i '{name}' | grep -v grep"
        res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=10)
        out = res.stdout.strip()
        return out if out else f"Không tìm thấy tiến trình nào khớp với tên '{name}'."
    elif action == "kill":
        target = pid or name
        if not target:
            return "Lỗi: Cần cung cấp PID hoặc tên tiến trình để dừng."
        if str(target).isdigit():
            res = subprocess.run(f"kill -9 {target}", shell=True, capture_output=True, text=True, timeout=10)
            return f"Đã gửi tín hiệu dừng tới PID {target}."
        else:
            res = subprocess.run(f"pkill -f '{target}'", shell=True, capture_output=True, text=True, timeout=10)
            return f"Đã gửi tín hiệu dừng tới các tiến trình khớp tên '{target}'."
    return f"Hành động '{action}' không được hỗ trợ."

def execute_tool(tool_call: Dict[str, Any]) -> str:
    name = tool_call.get("tool", "")
    
    if name in SKILLS_REGISTRY:
        return sanitize_str(SKILLS_REGISTRY[name]["full_md"])
    if name in ("activate_skill", "read_skill"):
        skill_name = tool_call.get("name") or tool_call.get("skill") or ""
        if skill_name in SKILLS_REGISTRY:
            return sanitize_str(SKILLS_REGISTRY[skill_name]["full_md"])
        else:
            available = ", ".join(SKILLS_REGISTRY.keys())
            return f"Lỗi: Không tìm thấy skill '{skill_name}'. Các skills có sẵn: {available}"

    if name == "web_search":
        q = tool_call.get("query", "")
        return perform_web_search(q)

    if name == "search_files":
        query_val = tool_call.get("query") or tool_call.get("pattern") or tool_call.get("name") or "*"
        root_path = tool_call.get("path")
        return tool_search_files(query_val, root_path)

    if name == "grep_text":
        query = tool_call.get("query", "")
        path = tool_call.get("path", ".")
        case_i = tool_call.get("case_insensitive", True)
        return tool_grep_text(query, path, case_i)

    if name == "diagnose_system":
        target = tool_call.get("target", "all")
        return tool_diagnose_system(target)

    if name == "inspect_process":
        action = tool_call.get("action", "list")
        p_name = tool_call.get("name", "")
        pid = tool_call.get("pid", "")
        return tool_inspect_process(action, p_name, pid)

    try:
        if name == "run_command":
            cmd = tool_call.get("cmd", "")
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=60)
            output = (res.stdout + "\n" + res.stderr).strip()
            return sanitize_str(output) or "[Lệnh thực thi thành công - Không có output]"
        elif name == "list_dir":
            raw_p = tool_call.get("path", ".")
            p = resolve_path(raw_p)
            if not p.exists():
                alt_p = Path("/mnt/c/Users/User/Downloads") if "download" in raw_p.lower() else None
                if alt_p and alt_p.exists():
                    p = alt_p
                else:
                    return f"Lỗi: Không tìm thấy đường dẫn {p} (Đã kiểm tra cả mount Windows)"
            items = [f"{'📁' if item.is_dir() else '📄'} {item.name}" for item in p.iterdir()]
            return f"[Danh sách tại {p}]:\n" + ("\n".join(items) if items else "[Thư mục trống]")
        elif name == "read_file":
            p = resolve_path(tool_call.get("path", ""))
            max_lines = int(tool_call.get("max_lines", 500))
            offset = int(tool_call.get("offset", 0))
            return robust_read_file(p, max_lines, offset)
        elif name == "write_file":
            p = resolve_path(tool_call.get("path", ""))
            content = tool_call.get("content", "")
            return robust_write_file(p, content)
        elif name == "move_file":
            src = resolve_path(tool_call.get("src", ""))
            dst = resolve_path(tool_call.get("dst", ""))
            return robust_move_file(src, dst)
        elif name == "copy_file":
            src = resolve_path(tool_call.get("src", ""))
            dst = resolve_path(tool_call.get("dst", ""))
            return robust_copy_file(src, dst)
        elif name == "delete_file":
            p = resolve_path(tool_call.get("path", ""))
            return robust_delete_file(p)
        else:
            return f"Lỗi: Không hỗ trợ công cụ '{name}'"
    except Exception as e:
        return f"Lỗi thực thi công cụ: {sanitize_str(str(e))}"

def compact_tool_output(out_str: str, max_lines: int = 25) -> str:
    lines = out_str.strip().splitlines()
    if len(lines) > max_lines:
        return "\n".join(lines[:15]) + f"\n... [Đã rút gọn {len(lines) - 25} dòng ở giữa] ...\n" + "\n".join(lines[-10:])
    return out_str

def extract_tool_calls(executor_reply: str) -> List[Dict[str, Any]]:
    """Trích xuất linh hoạt mọi định dạng tool calls từ Executor: list JSON, dict có steps/command, hoặc bash blocks."""
    tool_calls = []
    
    # 1. Tìm các block ```json ... ```
    json_blocks = re.findall(r"```json\s*(.*?)\s*```", executor_reply, re.DOTALL)
    for block in json_blocks:
        try:
            parsed = json.loads(block)
            items = parsed if isinstance(parsed, list) else [parsed]
            for item in items:
                if not isinstance(item, dict):
                    continue
                # TH 1: Định dạng chuẩn {"tool": "...", ...}
                if "tool" in item:
                    tool_calls.append(item)
                # TH 2: {"steps": [{"command": "..."}, ...]}
                elif "steps" in item and isinstance(item["steps"], list):
                    for step in item["steps"]:
                        if isinstance(step, dict):
                            cmd = step.get("command") or step.get("cmd")
                            if cmd:
                                tool_calls.append({"tool": "run_command", "cmd": cmd})
                # TH 3: {"command": "..."} hoặc {"cmd": "..."}
                elif "command" in item or "cmd" in item:
                    cmd = item.get("command") or item.get("cmd")
                    tool_calls.append({"tool": "run_command", "cmd": cmd})
                # TH 4: {"action": "run_command", ...}
                elif "action" in item:
                    item_copy = dict(item)
                    item_copy["tool"] = item_copy.pop("action")
                    tool_calls.append(item_copy)
        except Exception:
            pass

    # 2. Nếu không tìm thấy tool call nào trong json, kiểm tra block ```bash ... ``` hoặc ```sh ... ```
    if not tool_calls:
        sh_blocks = re.findall(r"```(?:bash|sh|shell)\s*(.*?)\s*```", executor_reply, re.DOTALL)
        for sh in sh_blocks:
            clean_cmd = sh.strip()
            if clean_cmd and not clean_cmd.startswith("#!/"):
                tool_calls.append({"tool": "run_command", "cmd": clean_cmd})

    return tool_calls

def stream_response(client: httpx.Client, model: str, messages: List[Dict[str, str]], title_prefix: str = "Assistant") -> str:
    full_response = ""
    thinking_content = ""

    payload = {
        "model": model,
        "messages": sanitize_messages(messages),
        "stream": True,
        "options": {"temperature": 0.2, "num_ctx": 16384}
    }

    console.print()
    border_color = "cyan" if "Plan" in title_prefix else "green"
    with Live(console=console, refresh_per_second=15) as live:
        with client.stream("POST", f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=300.0) as resp:
            if resp.status_code != 200:
                err_msg = sanitize_str(resp.read().decode("utf-8", "ignore"))
                live.update(Panel(f"[bold red]Lỗi Ollama API ({resp.status_code}):[/] {err_msg}", title="Lỗi", border_style="red"))
                return ""

            for line in resp.iter_lines():
                if not line:
                    continue
                try:
                    chunk = json.loads(line)
                    msg = chunk.get("message", {})
                    token = sanitize_str(msg.get("content", ""))
                    
                    chunk_thinking = sanitize_str(chunk.get("thinking", "") or msg.get("thinking", ""))
                    if chunk_thinking:
                        thinking_content += chunk_thinking

                    if token:
                        full_response += token

                    # Lọc sạch thẻ think kể cả khi chưa đóng
                    clean_display = re.sub(r"<think>.*?</think>", "", full_response, flags=re.DOTALL)
                    clean_display = re.sub(r"<think>.*$", "", clean_display, flags=re.DOTALL).strip()

                    if not clean_display and thinking_content:
                        short_think = thinking_content[-120:].replace("\n", " ")
                        live.update(
                            Panel(
                                f"[dim italic]💭 Suy luận: {short_think}...[/dim italic]",
                                title=f"[bold {border_color}]{title_prefix} ({model})[/bold {border_color}]",
                                border_style=border_color,
                                padding=(0, 1)
                            )
                        )
                    elif clean_display:
                        live.update(
                            Panel(
                                Markdown(clean_display),
                                title=f"[bold {border_color}]{title_prefix} ({model})[/bold {border_color}]",
                                border_style=border_color,
                                padding=(0, 1)
                            )
                        )
                except Exception:
                    pass

    final_output = re.sub(r"<think>.*?</think>", "", full_response, flags=re.DOTALL)
    final_output = re.sub(r"<think>.*$", "", final_output, flags=re.DOTALL).strip()
    return final_output

def print_welcome_banner():
    skills_names = ", ".join(list(SKILLS_REGISTRY.keys()))
    banner_text = Text()
    banner_text.append("✦ Qwen Hybrid Agent ", style="bold cyan")
    banner_text.append("• Dual-Model Synergy (Planner ⇄ Executor)\n", style="dim white")
    banner_text.append(f"• Planner (Brain):     {PLANNER_MODEL} (Plan, Logic, Re-plan)\n", style="cyan")
    banner_text.append(f"• Executor (Engineer): {EXECUTOR_MODEL} (Code, Tools, System)\n", style="green")
    banner_text.append(f"• Native Skills:       {skills_names}\n", style="dim")
    banner_text.append("• Nhập '/' để mở menu lệnh nhanh (dùng phím mũi tên ↑ ↓ để chọn)", style="italic cyan")
    
    console.print(Panel(banner_text, border_style="cyan", padding=(0, 1)))

def handle_slash_command(cmd: str, messages: List[Dict[str, str]]) -> bool:
    c = cmd.strip().lower()
    if c in ("/exit", "/quit"):
        console.print("[bold yellow]Tạm biệt! Hẹn gặp lại bạn.[/bold yellow]")
        sys.exit(0)
    elif c == "/clear":
        os.system("clear")
        print_welcome_banner()
        return True
    elif c == "/reset":
        messages.clear()
        messages.append({"role": "system", "content": PLANNER_SYSTEM_PROMPT})
        console.print("[bold green]✔ Đã làm mới toàn bộ ngữ cảnh hội thoại![/bold green]")
        return True
    elif c == "/history":
        console.print(f"[cyan]Tổng số tin nhắn trong context hiện tại: [bold]{len(messages)}[/bold][/cyan]")
        return True
    elif c == "/model":
        table = Table(title="Phân Chia Vai Trò Model Qwen", border_style="cyan")
        table.add_column("Vai trò", style="bold yellow")
        table.add_column("Model Name", style="cyan")
        table.add_column("Chức năng cốt lõi", style="white")
        table.add_row("Planner & Architect", PLANNER_MODEL, "Lập kế hoạch, suy luận, đánh giá kết quả, Re-plan")
        table.add_row("Executor & Engineer", EXECUTOR_MODEL, "Sinh code, thực thi công cụ, gọi lệnh shell, file ops")
        console.print(table)
        return True
    elif c == "/skills":
        table = Table(title="Hệ Thống Kỹ Năng Qwen Native Skills", border_style="cyan")
        table.add_column("Skill Name", style="bold green")
        table.add_column("Mô tả chuyên môn", style="white")
        for name, meta in SKILLS_REGISTRY.items():
            table.add_row(name, meta["description"])
        console.print(table)
        return True
    elif c == "/system":
        console.print("[bold cyan]📊 Đang kiểm tra tài nguyên hệ thống thực tế...[/bold cyan]")
        res = execute_tool({"tool": "run_command", "cmd": "free -h && lscpu | grep 'Model name' && df -h /mnt/c"})
        console.print(Panel(res, title="Tài Nguyên Hệ Thống", border_style="green", padding=(0, 1)))
        return True
    elif c == "/help":
        table = Table(title="Danh Sách Lệnh Nhanh (Slash Commands)", border_style="cyan")
        table.add_column("Lệnh", style="bold yellow")
        table.add_column("Chức năng", style="white")
        for s_cmd, s_desc in SLASH_COMMANDS:
            table.add_row(s_cmd, s_desc)
        console.print(table)
        return True
    else:
        console.print(f"[red]Lệnh không xác định: {cmd}. Gõ /help để xem danh sách.[/red]")
        return True

def is_pure_chitchat(text: str) -> bool:
    """Nhận diện các câu chào hỏi, cảm ơn, xã giao thuần túy không chứa bất kỳ yêu cầu kỹ thuật nào."""
    t = text.lower().strip()
    greetings = [
        "xin chào", "chào bạn", "chào", "hello", "hi", "hey", 
        "bạn là ai", "bạn tên gì", "cảm ơn", "thank", "tạm biệt", "bye",
        "good morning", "good evening", "good night", "chúc ngủ ngon", "chào buổi sáng"
    ]
    is_greeting_pattern = any(t == g or t.startswith(g + " ") or t.startswith(g + "!") or t.startswith(g + "?") for g in greetings)
    if is_greeting_pattern:
        tech_keywords = [
            "kiểm tra", "check", "chạy", "run", "tạo", "create", "sửa", "edit", "xóa", "delete",
            "file", "tệp", "máy", "ram", "cpu", "disk", "database", "db", "port", "process", "lệnh"
        ]
        if not any(k in t for k in tech_keywords):
            return True
    return False

def needs_action(text: str) -> bool:
    """Xác định nhanh câu hỏi có chứa ý định thao tác máy tính/thực thi không."""
    if is_pure_chitchat(text):
        return False

    t_lower = text.lower().strip()

    action_keywords = [
        "file", "tệp", "thư mục", "folder", "download", "tải về", "tải", "code", "lập trình", "hàm", "chạy", "thực hiện", "thực thi",
        "hệ điều hành", "ram", "cpu", "gpu", "vga", "card", "tiến trình", "process", "lệnh", "kiểm tra", "tạo", "sửa", "xóa", "copy",
        "tờ trình", "văn bản", "crash", "skill", "git", "script", "unit test", "cổng mạng", "cổng", "port", "disk", "ổ đĩa", "dung lượng", "bộ nhớ",
        "nội dung", "đọc file", "xem file", "mở file", "viết gì", "có gì",
        "database", "csdl", "mysql", "postgres", "sqlite", "mongodb", "mariadb", "redis",
        "trong máy", "trên máy", "máy mình", "máy tính", "hệ thống", "server", "wsl", "linux", "windows",
        "dịch vụ", "service", "cài đặt", "đã cài", "docker", "container", "package", "gói", "phần mềm", "ứng dụng",
        "mạng", "ping", "nhật ký", "nhiệt độ"
    ]
    
    # Word boundary regexes for short keywords to prevent false matching inside words (e.g. 'log' in 'logic')
    short_words = [r"\bos\b", r"\bdb\b", r"\bip\b", r"\blog\b", r"\blogs\b", r"\bapp\b", r"\bapps\b", r"\bmáy\b"]
    
    if any(k in t_lower for k in action_keywords):
        return True
    if any(re.search(pat, t_lower) for pat in short_words):
        return True
    if "```" in text or "{" in text:
        return True
        
    return False

def has_action_plan(user_input: str, planner_reply: str) -> bool:
    """Xác định thông minh và linh hoạt tuyệt đối xem có cần gọi Executor không (Zero-Keyword Architecture).
    Hoàn toàn dựa trên phân tích ngữ nghĩa và trạng thái tự chủ của Planner."""
    p_upper = planner_reply.upper()

    # 1. Trạng thái dứt điểm rõ ràng từ Planner
    if "[STATUS: COMPLETED]" in p_upper:
        return False
    if "[STATUS: NEED_ACTION]" in p_upper:
        return True

    # 2. Nhận diện cấu trúc thực thi (Action Plan hoặc khối JSON Tool call)
    if "[ACTION_PLAN]" in p_upper or "```json" in planner_reply:
        # Ngoại lệ an toàn duy nhất: Người dùng chỉ chào hỏi thuần túy (xin chào, hello)
        if is_pure_chitchat(user_input):
            return False
        return True

    # 3. Fallback ngôn ngữ tự nhiên: Planner phát biểu chỉ thị cho Coder hoặc liệt kê các bước
    reply_lower = planner_reply.lower()
    intent_patterns = [
        r"yêu cầu coder", r"coder chạy", r"chạy lệnh", r"bước 1[:\.]", r"bước 2[:\.]",
        r"kế hoạch thực thi", r"các bước thực hiện", r"tiến hành kiểm tra", r"tiến hành đọc",
        r"kiểm tra lại bằng", r"cần chạy lệnh", r"sẽ yêu cầu coder"
    ]
    if any(re.search(pat, reply_lower) for pat in intent_patterns):
        return True

    # Nếu Planner đề cập chạy lệnh shell cụ thể trong backtick (ví dụ: `ls -lh ...`) kèm từ khóa chỉ thị
    if re.search(r"`(ls|find|cat|grep|ps|dpkg|ss|curl|python|bash)\b", reply_lower) and any(w in reply_lower for w in ["chạy", "lệnh", "coder", "kiểm tra", "xem"]):
        return True

    return False

def main():
    print_welcome_banner()
    
    # Context chính của phiên làm việc
    messages: List[Dict[str, str]] = [
        {"role": "system", "content": PLANNER_SYSTEM_PROMPT}
    ]

    client = httpx.Client(timeout=300.0)
    session = PromptSession(
        completer=SlashCommandCompleter(),
        complete_while_typing=True,
        style=pt_style
    )

    while True:
        try:
            console.print()
            user_input = session.prompt(HTML("<b><ansicyan>❯ Bạn: </ansicyan></b>"))
            
            if not user_input.strip():
                continue
                
            clean_text = user_input.strip()

            if clean_text.startswith("/"):
                handle_slash_command(clean_text, messages)
                continue

            user_input_sanitized = sanitize_str(clean_text)
            messages.append({"role": "user", "content": user_input_sanitized})

            # BƯỚC 1: PLANNER (Qwen 3.5) LẬP KẾ HOẠCH HOẶC TRẢ LỜI CHUNG
            console.print(f"[dim cyan]🧠 Planner ({PLANNER_MODEL}) đang phân tích mục tiêu & lập kế hoạch...[/dim cyan]")
            planner_reply = stream_response(client, PLANNER_MODEL, messages, title_prefix="Planner (Chiến lược)")
            if not planner_reply:
                continue

            messages.append({"role": "assistant", "content": planner_reply})

            # BƯỚC 2: PHÂN LUỒNG THÔNG MINH SANG EXECUTOR
            # Quyết định kích hoạt Executor dựa trên phân tích kế hoạch của Planner:
            # - Tự động loại trừ các câu chào hỏi/xã giao thuần túy
            # - Tin tưởng tuyệt đối khi Planner xuất [ACTION_PLAN] hoặc các bước thực thi cụ thể
            if not has_action_plan(clean_text, planner_reply):
                continue

            # BƯỚC 2: VÒNG LẶP GIẢI PHÁP TỰ ĐỘNG (Dynamic Solution Loop - Chạy đến khi xong hoặc hết solution)
            round_no = 0
            max_safe_limit = 50  # Giới hạn bảo vệ chống treo vĩnh viễn (50 vòng)
            last_actions_signatures = []

            while round_no < max_safe_limit:
                round_no += 1
                
                # Chuyển Plan sang cho Executor (Qwen 2.5 Coder) thực thi
                console.print(f"[dim green]⚙️ [Vòng {round_no}] Triển khai Kế hoạch từ Planner sang Executor ({EXECUTOR_MODEL})...[/dim green]")
                
                executor_context = [
                    {"role": "system", "content": EXECUTOR_SYSTEM_PROMPT},
                    {"role": "user", "content": f"Yêu cầu của User:\n{clean_text}\n\nKế hoạch từ Planner:\n{planner_reply}\n\nNếu Kế hoạch trên có các bước thực thi cụ thể trên máy tính, hãy xuất khối code json các công cụ tương ứng để thực hiện (định dạng: [{{\"tool\": \"run_command\", \"cmd\": \"...\"}}]). Nếu không cần công cụ nào, hãy trả lời ngắn gọn."}
                ]

                executor_reply = stream_response(client, EXECUTOR_MODEL, executor_context, title_prefix=f"Executor (Vòng {round_no})")
                if not executor_reply:
                    break

                # Tìm và chạy các Tool calls bằng bộ trích xuất thông minh (hỗ trợ mọi định dạng JSON / steps / bash)
                tool_calls_to_run = extract_tool_calls(executor_reply)

                if not tool_calls_to_run:
                    # Executor đã trả lời xong và không cần gọi thêm tool nào
                    messages.append({"role": "assistant", "content": f"[Kết quả thực thi từ Executor]:\n{executor_reply}"})
                    break

                # Kiểm tra lặp hành động (Loop detection)
                current_sig = json.dumps(tool_calls_to_run, sort_keys=True)
                last_actions_signatures.append(current_sig)
                is_stuck_in_loop = len(last_actions_signatures) >= 3 and last_actions_signatures[-1] == last_actions_signatures[-2] == last_actions_signatures[-3]

                # Thực thi các công cụ trên máy
                console.print(f"[dim yellow]🛠️ Đang thực thi {len(tool_calls_to_run)} hành động trên hệ thống...[/dim yellow]")
                tool_outputs = []

                for call in tool_calls_to_run:
                    tool_name = call.get("tool")
                    console.print(f"[bold yellow]👉 Chạy: [cyan]{tool_name}[/cyan] {json.dumps(call, ensure_ascii=False)}...[/bold yellow]")
                    out = execute_tool(call)
                    console.print(Panel(out, title=f"Kết quả {tool_name}", border_style="yellow", padding=(0, 1)))
                    tool_outputs.append(f"Tool {tool_name} ({json.dumps(call, ensure_ascii=False)}):\n{compact_tool_output(out)}")

                tool_summary_str = "\n\n".join(tool_outputs)

                loop_warning = ""
                if is_stuck_in_loop:
                    loop_warning = "\n⚠️ CẢNH BÁO HỆ THỐNG: Hành động này đã chạy lặp lại 3 lần mà không có tiến triển mới. BẮT BUỘC bạn phải chuyển sang một giải pháp hoàn toàn mới hoặc kết luận nếu đã cạn kiệt giải pháp!\n"

                # Gửi báo cáo kết quả thực tế về Planner để đánh giá và quyết định:
                # - Nếu đã đạt được mục tiêu: Tổng hợp báo cáo hoàn tất cho User.
                # - Nếu chưa xong: Tiếp tục đề xuất giải pháp (Search-First hoặc Local Inference)
                console.print(f"[dim cyan]🧠 Planner ({PLANNER_MODEL}) đang đánh giá kết quả thực tế của Vòng {round_no}...[/dim cyan]")
                
                eval_prompt = (
                    f"BÁO CÁO KẾT QUẢ THỰC TẾ TỪ CODER (EXECUTOR) [Vòng {round_no}]:\n\n"
                    f"{tool_summary_str}\n\n"
                    f"{loop_warning}"
                    f"Mục tiêu ban đầu của User: \"{clean_text}\"\n\n"
                    "NHIỆM VỤ ĐÁNH GIÁ CỦA BẠN (PLANNER):\n"
                    "1. NẾU CHƯA ĐẠT ĐƯỢC MỤC TIÊU HOẶC CẦN CHẠY THÊM LỆNH (ví dụ: kết quả chưa đúng, cần chạy thêm lệnh `ls -lh`, `cat`, v.v.):\n"
                    "   - CHIẾN LƯỢC: Ưu tiên tra cứu internet bằng `web_search` trước nếu gặp lỗi mới/chưa rõ cách fix. Nếu tìm file nội bộ thì lập lệnh shell tương ứng.\n"
                    "   - BẮT BUỘC XUẤT KHỐI [ACTION_PLAN] với bước thực thi cụ thể tiếp theo và kết thúc bằng [STATUS: NEED_ACTION] để Coder tiếp tục chạy ngay (không giới hạn số vòng)!\n"
                    "   - TUYỆT ĐỐI KHÔNG xuất '🎯 Kết quả' khi chưa xong, và KHÔNG chỉ nói suông mà PHẢI XUẤT THẺ [ACTION_PLAN]!\n"
                    "2. NẾU MỤC TIÊU ĐÃ ĐẠT ĐƯỢC HOÀN TOÀN:\n"
                    "   -> Trình bày kết quả hoàn tất theo định dạng tinh gọn Markdown (Clean & Crisp):\n"
                    "      ### 🎯 Kết quả: [Trạng thái hoàn thành]\n"
                    "      - **Mục tiêu**: `[Nội dung]`\n"
                    "      - **Chi tiết**: [Kết quả cụ thể, trích xuất chính xác]\n"
                    "      [STATUS: COMPLETED]\n"
                    "3. NẾU ĐÃ THỬ HẾT MỌI CÁCH VÀ THẬT SỰ CẠN KIỆT GIẢI PHÁP: Hãy báo cáo trung thực và kết luận dừng lại kèm [STATUS: COMPLETED]."
                )
                
                messages.append({"role": "user", "content": eval_prompt})
                planner_eval = stream_response(client, PLANNER_MODEL, messages, title_prefix=f"Planner (Đánh giá Vòng {round_no})")
                if not planner_eval:
                    break
                messages.append({"role": "assistant", "content": planner_eval})

                # Kiểm tra nếu Planner đề xuất giải pháp tiếp theo (có [ACTION_PLAN])
                if has_action_plan(clean_text, planner_eval):
                    planner_reply = planner_eval
                    console.print(f"[bold yellow]🔄 Planner đề xuất Giải pháp tiếp theo! Tiếp tục vòng lặp tự động...[/bold yellow]")
                    continue
                else:
                    # Đã hoàn tất mục tiêu hoặc kết luận cuối cùng
                    break

        except (KeyboardInterrupt, EOFError):
            console.print("\n[bold yellow]Đã dừng phiên làm việc.[/bold yellow]")
            break
        except Exception as e:
            console.print(f"[bold red]Lỗi hệ thống:[/] {sanitize_str(str(e))}")

if __name__ == "__main__":
    main()
