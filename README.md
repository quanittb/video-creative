# Video Creative Studio

Video Creative Studio là ứng dụng desktop tạo video nhân vật dọc. Luồng render hiện tại của Studio dùng **Echo Flash → MuseTalk**: Echo tạo motion base từ ảnh nhân vật và audio, MuseTalk đồng bộ khẩu hình, sau đó core xác minh và xuất MP4 dọc 1080×1920.

## Điều kiện trước khi dùng thử

Bản desktop hiện **chưa phải installer tự chứa**. Máy chạy thử phải được chuẩn bị trước các thành phần bên ngoài ứng dụng:

- Mã nguồn Echo Flash, môi trường Python tương thích và các model cần thiết. Làm theo [hướng dẫn Echo Flash trên Windows](docs/ECHOMIMIC_V3_FLASH_WINDOWS.md).
- Mã nguồn MuseTalk, môi trường Python/dependency tương thích và model MuseTalk. Các đường dẫn phải được core tìm thấy hoặc cấu hình theo hướng dẫn vận hành.
- FFmpeg và `ffprobe` sẵn có trong `PATH`.

**Settings → Model render Echo Flash + MuseTalk** kiểm tra và quản lý các model weight thuộc catalog của ứng dụng. Phần này không cài mã nguồn Echo/MuseTalk, Python, package, FFmpeg hay driver GPU. Việc build/copy ứng dụng sang máy mới không tự cài những thành phần đó.

## Luồng dùng thử trong ứng dụng

1. Mở bản desktop đã được chuẩn bị trên máy chạy thử. `start_studio.bat` chỉ khởi chạy file `.exe` đã build; nó không cài core hoặc model.
2. Mở **Cài đặt** và kiểm tra trạng thái các model Echo Flash và MuseTalk. Tải lại hoặc xác minh weight còn thiếu/hỏng nếu cần.
3. Trong **Studio**, chọn một ảnh mẫu chính diện hoặc tải ảnh nhân vật, nhập kịch bản và chọn giọng.
4. Chọn render ngay hoặc thêm job vào **Queue**. Với Queue, bấm **Kích hoạt Queue** để chạy tuần tự.
5. Khi job hoàn tất, mở video từ hàng đợi hoặc thư mục output đã cấu hình; kiểm tra hình, âm thanh và khẩu hình trước khi bàn giao.

## Hướng dẫn Windows và kiểm thử core

- [Chuẩn bị máy dùng thử RTX 3060](HUONG_DAN_CHUYEN_MAY_RTX3060.md)
- [Cài và kiểm tra Echo Flash trên Windows](docs/ECHOMIMIC_V3_FLASH_WINDOWS.md)
- [Kiểm thử pipeline video dọc Echo Flash + MuseTalk](docs/ECHO_VERTICAL_ADS_WINDOWS.md)
- [Tái sử dụng motion base và cache cho audio dài](docs/ECHO_FLASH_LOOP_CACHE_WINDOWS.md)

Các hướng dẫn CLI là công cụ kiểm tra core, không thay cho luồng Studio và không biến ứng dụng thành bộ cài runtime. Thời gian render và chất lượng phụ thuộc GPU, ảnh đầu vào, audio, model và môi trường đã cài.
