# HƯỚNG DẪN CHUYỂN VÀ VẬN HÀNH TRÊN MÁY RTX 3060 (12GB VRAM)

Tài liệu này hướng dẫn bạn cách chuyển bộ phần mềm **Video Creative Studio** từ máy phát triển hiện tại (GTX 1650 4GB) sang máy trạm sản xuất **NVIDIA RTX 3060 (12GB VRAM)** để render video hàng loạt với chất lượng cao nhất.

---

## 1. CƠ CHẾ HOẠT ĐỘNG GIỮA 2 MÁY

| Thành phần | Máy phát triển (Máy hiện tại - GTX 1650 4GB) | Máy trạm sản xuất (Máy RTX 3060 12GB) |
| :--- | :--- | :--- |
| **Giao diện Desktop** | Chạy file `video-creative-studio.exe` mượt mà 60 FPS, 0% CPU lúc nghỉ. | Chạy file `video-creative-studio.exe`. |
| **Chế độ hoạt động** | **Chế độ Test (Máy hiện tại)**: Mô phỏng đầy đủ quy trình 4 chặng (Edge-TTS, LivePortrait, MuseTalk, Verifying), kiểm tra batch và giao diện mà không tốn VRAM. | **Chế độ Render Thật (RTX 3060)**: Chạy pipeline GPU thực tế (`test_option_b_avatar.py`), FP16 inference kết hợp LivePortrait 3D + MuseTalk 1.5. |
| **Tiêu tốn VRAM** | 0% VRAM (An toàn tuyệt đối, không đơ lag). | ~6.5GB - 8.5GB VRAM (Hoàn toàn nằm trong ngưỡng 12GB của RTX 3060). |

---

## 2. QUY TRÌNH CHUYỂN SANG MÁY RTX 3060

### Bước 1: Đóng gói trên máy hiện tại
Tại thư mục `d:\rustProject\video-creative-studio`:
- Nhấp đúp chuột vào file: `package_for_rtx3060.bat`.
- File sẽ tự động xuất một thư mục sạch sẽ tại `D:\video-creative-studio-rtx3060-package` (đã loại bỏ hơn 15GB thư mục tạm `target` và `node_modules`).
- Bạn có thể nén thư mục này thành file `.zip` hoặc chép trực tiếp vào USB/ổ cứng ngoài.

### Bước 2: Thiết lập trên máy RTX 3060
1. Giải nén/sao chép thư mục vào máy RTX 3060 (ví dụ `D:\video-creative-studio`).
2. Cài đặt Python 3.10 và các thư viện cần thiết:
   ```cmd
   pip install -r requirements.txt
   ```
   *(Nếu máy RTX 3060 đã có sẵn môi trường conda/venv của bạn, chỉ cần trỏ python vào môi trường đó).*
3. Đảm bảo máy đã cài đặt FFmpeg (đã có trong PATH hệ thống).

### Bước 3: Vận hành Render hàng loạt
1. Nhấp đúp vào `video-creative-studio.exe` hoặc chạy `start_studio.bat`.
2. Trên thanh tiêu đề (HeaderBar), chuyển nút toggle sang:
   **🚀 Render Thật (RTX 3060)**
3. Tại tab **Studio**:
   - Chọn bất kỳ trong 10 phong cách thuyết trình.
   - Bấm **"Thêm vào Hàng đợi"** hoặc **"Render ngay"**.
4. Tại tab **Batch AI**:
   - Nhập file manifest CSV (`sample_10_styles_batch.csv`) hoặc JSON.
   - Bấm **"Thêm vào Hàng đợi Render"**.
5. Bấm **"Bắt đầu Render Queue"** trong tab Hàng đợi (Queue):
   - Worker tuần tự sẽ xử lý từng video một (tránh tràn 12GB VRAM).
   - Tiến trình hiển thị thời gian thực theo từng stage.
   - Video đầu ra tự động lưu vào thư mục `output/`.
