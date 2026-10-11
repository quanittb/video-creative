# Hướng dẫn chuẩn bị máy dùng thử Windows (RTX 3060 12 GB)

Tài liệu này thay thế hướng dẫn chuyển máy cũ dùng LivePortrait/torso. **Không dùng `package_for_rtx3060.bat`, `setup_new_machine.*` hoặc các launcher LivePortrait cũ**: các lệnh đó không còn thuộc luồng sản phẩm hiện tại.

## 1. Hiểu đúng phạm vi bản dùng thử

Ứng dụng desktop hiện render theo luồng **Echo Flash → MuseTalk**. Bản build hiện tại chưa tự chứa mã nguồn model, Python runtime, dependency, FFmpeg và toàn bộ model weights. Vì vậy, cần chuẩn bị các runtime/core bên ngoài trước khi giao máy; chỉ chép file ứng dụng sang máy RTX 3060 là chưa đủ để render.

Trong **Cài đặt → Model render Echo Flash + MuseTalk**, có thể kiểm tra và quản lý các model weight mà catalog của ứng dụng hỗ trợ. Mục này không cài Python, package, checkout Echo/MuseTalk, FFmpeg hoặc driver NVIDIA.

## 2. Chuẩn bị máy và core

1. Cài driver NVIDIA tương thích với Windows và xác nhận RTX 3060 được nhận diện bằng `nvidia-smi`.
2. Cài FFmpeg và `ffprobe`, sau đó mở CMD mới và xác nhận cả hai lệnh có trong `PATH`.
3. Cài Echo Flash theo đúng Python/runtime và revision đã ghi trong [hướng dẫn Echo Flash trên Windows](docs/ECHOMIMIC_V3_FLASH_WINDOWS.md). Không cài requirements của Echo vào môi trường Python dùng cho MuseTalk.
4. Chuẩn bị riêng mã nguồn MuseTalk, Python/dependency tương thích và các file model MuseTalk. Core cần tìm thấy source và interpreter; hướng dẫn [kiểm thử Echo Flash + MuseTalk](docs/ECHO_VERTICAL_ADS_WINDOWS.md) mô tả cách truyền đường dẫn khi chạy CLI kiểm thử.
5. Đặt model weights ở đúng vị trí mà catalog trong Settings quản lý, rồi kiểm tra trạng thái model ở đó. Tải model có thể cần nhiều dung lượng và thời gian; không xóa hoặc thay thế file model đang dùng khi có job render.

Không dùng WanGP/Wan2GP hoặc pipeline LivePortrait cũ cho luồng Studio hiện tại. Không chạy `setup_new_machine.bat` để cài toàn bộ `requirements.txt`: cách đó không tạo đúng hai môi trường model độc lập.

Studio không gọi checkout Wan2GP; nếu không dùng ứng dụng Wan2GP riêng, có thể gỡ checkout đó. Tuy nhiên, Echo Flash vẫn cần checkpoint Wan2.1 Fun trong `EchoMimicV3\models`; không xóa nhầm checkpoint này.

## 3. Chạy một lượt dùng thử trong app

1. Mở bản desktop đã build và đã được cấu hình core. `start_studio.bat` chỉ khởi chạy executable có sẵn; script này không cài đặt runtime hay sửa cấu hình core.
2. Vào **Cài đặt**, kiểm tra model Echo Flash và MuseTalk. Nếu thiếu weight, tải hoặc sửa qua chức năng model tương ứng; nếu source/runtime chưa có thì chuẩn bị chúng riêng trước khi render.
3. Vào **Studio**, chọn ảnh nhân vật chính diện hoặc tải ảnh riêng, nhập một kịch bản ngắn và chọn giọng đọc.
4. Bấm render ngay để kiểm tra một job, hoặc thêm vào Queue rồi bấm **Kích hoạt Queue**. Queue xử lý job tuần tự.
5. Khi job báo hoàn tất, mở video từ Queue hoặc thư mục output đang cấu hình. Xem toàn bộ clip, nhất là đồng bộ môi/đoạn nghỉ, méo mặt, viền tóc/vai và tiếng trước khi đánh giá.

## 4. Nếu cần kiểm tra core bằng CMD

Các lệnh CLI dưới đây là phép thử riêng, không phải bước bắt buộc trong luồng giao diện:

- [Cài/kiểm tra Echo Flash và chạy preview](docs/ECHOMIMIC_V3_FLASH_WINDOWS.md)
- [Kiểm tra MuseTalk, lip-sync và xuất video dọc](docs/ECHO_VERTICAL_ADS_WINDOWS.md)
- [Dùng lại motion base và cache cho audio dài](docs/ECHO_FLASH_LOOP_CACHE_WINDOWS.md)

Làm theo đường dẫn và lệnh trong tài liệu tương ứng với máy thực tế; không dùng đường dẫn ví dụ từ một máy khác nếu chưa thay bằng đường dẫn của bạn. Dry-run chỉ xác nhận đầu vào và cấu hình, không xác nhận CUDA inference hoặc chất lượng hình ảnh.

## Giới hạn bàn giao

RTX 3060 12 GB là cấu hình mục tiêu đã dùng để thử core, nhưng không bảo đảm mọi ảnh, audio hoặc cấu hình đều chạy không lỗi. Thời gian và chất lượng cần được đánh giá trên chính máy nhận bàn giao. Bản ứng dụng chưa phải bộ cài tự chứa cho khách hàng mới; cần hoàn thiện quy trình cài/đóng gói runtime riêng trước khi phát hành rộng.
