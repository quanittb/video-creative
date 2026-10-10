# Test EchoMimic V3 Flash trên RTX 3060 Windows

Nhánh này tạo chuyển động mới từ ảnh và audio/prompt bằng EchoMimic V3 Flash; không dùng clip guide vai. F1 là preview 3,24 giây; profile F10 sinh thuận 5,16 giây để khi MuseTalk ping-pong thành chu kỳ danh nghĩa 10,32 giây. F20 là lựa chọn thử nghiệm 9,96 giây thuận/19,92 giây ping-pong. Kiểm tra F1 trước để duyệt mặt, tóc, cổ áo, hai vai và độ đồng bộ miệng. Model có thể làm sai chi tiết nhận dạng hoặc quần áo; đây là phép thử chất lượng, chưa phải bảo đảm giữ nguyên nhân vật. Hướng dẫn tạo cache và lặp cho video dài nằm ở [ECHO_FLASH_LOOP_CACHE_WINDOWS.md](ECHO_FLASH_LOOP_CACHE_WINDOWS.md).

## 1. Điều kiện máy và thư mục

Nếu bạn nhận bộ test dạng ZIP, hãy giải nén các file bên trong vào đúng thư mục gốc dự án `C:\Users\Admin\Downloads\video-creative-studio\video-creative-studio`, giữ nguyên cấu trúc `scripts`, `tests`, `docs` và file `.bat`. ZIP không chứa checkpoint/model weights; lệnh tải model ở bước 2 mới lấy các file đó.

Quy trình dành cho Windows 10 64-bit, Python 3.11 x64, Git, driver NVIDIA hiện có và RTX 3060 12GB. WanGP/MuseTalk đang dùng venv riêng; các lệnh dưới đây không cài package vào hai môi trường đó. Cần FFmpeg và `ffprobe` trong `PATH`; tải một bản Windows từ [trang FFmpeg](https://ffmpeg.org/download.html), giải nén và thêm thư mục `bin` có hai file `.exe` vào `PATH`, rồi mở CMD mới.

Đảm bảo ổ đĩa còn ít nhất 50GB trống. Bộ weight được cố định theo revision và gồm khoảng **20,77GB** (khoảng 19,34GiB); venv, cache và file staging cần thêm chỗ. Máy có 32GB RAM nên việc nạp weight vẫn khá sát giới hạn khi Windows và ứng dụng khác đang chạy. Trước render, đóng ứng dụng đang chiếm RAM/VRAM. Không cài CUDA Toolkit hoặc driver Linux; PyTorch Windows wheel bên dưới mang runtime CUDA 12.4, dùng driver NVIDIA của Windows.

Ví dụ dùng đúng các thư mục hiện có của bạn:

```bat
cd /d "C:\Users\Admin\Downloads\video-creative-studio\video-creative-studio"
git clone https://github.com/antgroup/echomimic_v3.git "C:\Users\Admin\Downloads\EchoMimicV3"
git -C "C:\Users\Admin\Downloads\EchoMimicV3" checkout 7e89489ca51c0d008fc1963ec6c03fc5bd0b9397
py -3.11 -m venv "C:\Users\Admin\Downloads\EchoMimicV3\venv"
set "ECHO_PY=C:\Users\Admin\Downloads\EchoMimicV3\venv\Scripts\python.exe"
"%ECHO_PY%" -m pip install --upgrade pip
"%ECHO_PY%" -m pip install torch==2.5.1 torchvision==0.20.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cu124
"%ECHO_PY%" -m pip install -r "C:\Users\Admin\Downloads\video-creative-studio\video-creative-studio\scripts\echo_flash_requirements.txt"
```

Các bản Torch/torchvision/torchaudio phải cùng bộ CUDA 12.4. Bộ requirements riêng chỉ cài dependency mà adapter dùng; không cài toàn bộ `requirements.txt` upstream (có các package nặng không cần cho đường inference này). Không cài FlashAttention hoặc xformers; adapter dùng attention SDPA của PyTorch. Giữ nguyên venv này tách biệt với WanGP/MuseTalk.

Nếu thư mục `EchoMimicV3` đã tồn tại, không chạy lại `git clone`; kiểm tra commit bằng:

```bat
git -C "C:\Users\Admin\Downloads\EchoMimicV3" rev-parse HEAD
```

Kết quả phải là `7e89489ca51c0d008fc1963ec6c03fc5bd0b9397`. Nếu đang ở commit khác, dùng lệnh `git -C ... checkout 7e89489ca51c0d008fc1963ec6c03fc5bd0b9397` phía trên.

## 2. Kiểm tra runtime rồi tải checkpoint

Mở CMD mới ở thư mục project. Nếu batch không tự tìm đúng GPU Python, khai báo đường dẫn tuyệt đối:

```bat
cd /d "C:\Users\Admin\Downloads\video-creative-studio\video-creative-studio"
set "ECHO_FLASH_PYTHON=C:\Users\Admin\Downloads\EchoMimicV3\venv\Scripts\python.exe"
test_echo_flash_rtx3060.bat check --runtime-only
```

Lệnh `check --runtime-only` xác nhận import, version package, CUDA/GPU, BF16 và FFmpeg; nó không truy vấn riêng phiên bản driver, đọc hoặc tải model. Nếu báo thiếu package, cài lại bằng hai lệnh pip tương ứng ở bước 1 trong đúng `venv\Scripts\python.exe`. Không cài `musetalk` vào venv này để xử lý lỗi import.

Sau đó xác nhận ảnh và audio project đã có:

```bat
test_echo_flash_rtx3060.bat dry-run
```

Mặc định dùng ảnh `assets\characters\nhanvatnam\asian_male_office_1080p.png` và audio `sample_script_1min.mp3` trong project. Dry-run chỉ probe media/độ phủ thời lượng và commit source; chưa dùng CUDA, chưa tạo video. Nếu bỏ `--duration`, mỗi profile dùng hết cửa sổ frame: F1/F2/F3 là 81 frame tại 25fps = 3,24 giây; F10 là 129 frame = 5,16 giây; F20 là 249 frame = 9,96 giây. Số frame được làm tròn xuống dạng `4n+1` để khớp temporal compression của VAE; lệnh từ chối clip dưới 13 frame (0,52 giây) để loudness normalization chạy ổn định và từ chối duration vượt giới hạn profile để tránh cắt ngầm. Audio phải phủ gần hết thời lượng video (sai số tối đa 0,02 giây); audio ngắn hơn thì lệnh dừng, không lặp audio. Dòng `Motion base Echo` cho biết thời lượng clip đi thuận; MuseTalk với `--motion-policy pingpong` tạo chu kỳ danh nghĩa gấp đôi.

Tải model một cách rõ ràng bằng lệnh:

```bat
test_echo_flash_rtx3060.bat fetch-models
```

Downloader lấy file từ revision cố định, ghi tiến trình trực tiếp ra CMD, kiểm size và SHA-256 rồi mới đổi tên file hoàn chỉnh. Nếu mạng ngắt, file `.part` được giữ để tiếp tục. File đã tồn tại nhưng sai hash được giữ nguyên và báo lỗi; không tự xóa checkpoint của bạn. Lệnh này tải 12 file gồm Flash-Pro, VAE, CLIP, T5, tokenizer và Wav2Vec2; không tải transformer base 3,13GB vì adapter nạp trực tiếp Flash-Pro.

Sau khi tải xong, chạy:

```bat
test_echo_flash_rtx3060.bat check --verify-sha
```

`--verify-sha` đọc toàn bộ khoảng 20,77GB để xác nhận nội dung. Việc này chỉ cần thiết sau khi tải hoặc khi nghi file hỏng; các lần render bình thường chỉ kiểm tra đường dẫn và kích thước để tránh đọc lại toàn bộ weights.

## 3. Chạy clip kiểm tra đầu tiên

Chỉ chạy F1 trước:

```bat
test_echo_flash_rtx3060.bat run --profile F1
```

F1 sinh 384×480, 81 frame, 25fps, 8 bước, seed 42, CFG 6 và audio CFG 3. Prompt yêu cầu chuyển động thân trên nhỏ, bất đối xứng, gật cổ nhẹ và giữ khung hình ổn định; không yêu cầu cử chỉ tay lớn. Ảnh được scale đồng đều và thêm viền nếu cần, không kéo giãn. Adapter giữ TeaCache và Riflex tắt, nạp model theo thứ tự CLIP → VAE → Flash transformer → T5, và dùng sequential CPU offload. Không gọi `pipeline.to(cuda)` sau khi gắn offload hook. Người dùng đã chạy F1 thành công trên RTX 3060 trong 206 giây; đây là một lượt đo, không phải benchmark tổng quát. F10/F20 chưa được đo trên máy đó.

Trong CMD sẽ hiện tiến độ `Render 1/8` … `Render 8/8`. Log đầy đủ nằm dưới `output\echo_flash\logs\`. Nếu tiến trình lỗi, lệnh giữ log và thư mục `.work-*` để kiểm tra, không xuất MP4 giả và không tự hạ độ phân giải/chất lượng.

Khi thành công, CMD in chính xác ba đường dẫn: `Motion base`, `Voice preview`, `Run manifest`. Motion base là video im lặng để dùng tiếp với MuseTalk; voice preview đã ghép audio test ngắn. Mở đúng đường dẫn vừa in, ví dụ:

```bat
start "" "output\echo_flash\f1_<fingerprint>\motion_base.mp4"
start "" "output\echo_flash\f1_<fingerprint>\voice_preview.mp4"
```

Thay `<fingerprint>` bằng tên thư mục thực tế từ CMD. Kiểm tra mặt có đổi dạng không, tóc/áo/cổ áo có nhấp nháy không, hai vai có cùng chuyển động tự nhiên với đầu không và miệng có bám tiếng không. Model sinh chuyển động theo prompt/audio; nó không chép tọa độ chuyển động từ video mẫu và không khóa tuyệt đối danh tính/texture quần áo.

Nếu F1 đạt chất lượng chấp nhận được, mới thử F2 ở 512×640:

```bat
test_echo_flash_rtx3060.bat run --profile F2
```

F3 dùng cùng độ phân giải với seed khác để xem độ ổn định:

```bat
test_echo_flash_rtx3060.bat run --profile F3
```

Mỗi profile/run có fingerprint riêng; cùng ảnh, audio, model, source và prompt sẽ tái sử dụng output chỉ khi manifest, hash và ffprobe đều hợp lệ. Để ép render lại cùng cấu hình nhưng giữ output cũ, thêm `--no-output-cache`; nó tạo thư mục run mới. `--overwrite` giữ thư mục cũ thành backup trước khi tạo lại. Không chạy F1, F2, F3 nối tiếp tự động trước khi xem F1.

## 4. Benchmark tùy chọn

Benchmark chạy hai lần render mới trong cùng một process để chia sẻ lần nạp model. Không truyền `--image-b` thì benchmark render lại cùng ảnh hai lần; để so hai nguồn ảnh, truyền ảnh B rõ ràng:

```bat
test_echo_flash_rtx3060.bat benchmark --profile F1 --image-b "assets\characters\nhanvatnu\ChatGPT Image Sep 14, 2026, 11_35_53 AM (1).png"
```

Hai clip được lưu riêng dưới thư mục `benchmark_*`, cùng `benchmark_report.json`. Đây là so sánh hai lượt trong cùng process, không phải cam kết tốc độ RTX 3060 hay phép đo warm-GPU tuyệt đối; mỗi lượt vẫn gọi pipeline và denoise lại.

## 5. Chuyển motion base đã duyệt sang MuseTalk

Chỉ sau khi xem và chấp nhận `motion_base.mp4`, lấy đúng đường dẫn được in trong CMD (không dùng `voice_preview.mp4`) rồi chạy preflight MuseTalk với đoạn thoại ngắn. Để dùng đoạn đã duyệt cho kịch bản đầy đủ và tái sử dụng avatar cache, theo hướng dẫn [ECHO_FLASH_LOOP_CACHE_WINDOWS.md](ECHO_FLASH_LOOP_CACHE_WINDOWS.md); không bật ping-pong cho preview F1 khi chỉ kiểm tra đồng bộ ngắn:

```bat
set "ECHO_BASE=PASTE_FULL_PATH_TO_motion_base.mp4"
test_cached_musetalk.bat dry-run --base-video "%ECHO_BASE%" --audio "sample_script_1min.mp3" --duration 3.2 --fps 25 --batch-size 2 --cache-dir "C:\vcs_cache"
```

Nếu dry-run hợp lệ, render lip-sync:

```bat
test_cached_musetalk.bat run --base-video "%ECHO_BASE%" --audio "sample_script_1min.mp3" --duration 3.2 --fps 25 --batch-size 2 --cache-dir "C:\vcs_cache" --output "output\cached_musetalk\echo_flash_f1_voice.mp4"
```

Motion base Echo ở đây chỉ dài 3,24 giây; không bật ping-pong cho clip kiểm tra này vì nó sẽ lặp chuyển động sinh ra thay vì tạo motion mới cho toàn bài. MuseTalk vẫn chạy trong venv riêng theo script hiện có.

## Ghi chú vận hành

- Batch chỉ gọi Python controller chuẩn thư viện; GPU worker luôn dùng venv riêng EchoMimic. Nếu cần chỉ định controller Python, đặt `VCS_ECHO_CONTROLLER_PYTHON` thành đường dẫn `python.exe`; `ECHO_FLASH_PYTHON` chỉ tới venv GPU.
- Có thể chỉ định FFmpeg không nằm trong `PATH` bằng `--ffmpeg "D:\tools\ffmpeg\bin\ffmpeg.exe" --ffprobe "D:\tools\ffmpeg\bin\ffprobe.exe"`.
- Nếu gặp `CUDA out of memory`, lưu log, đóng ứng dụng đang dùng GPU rồi thử lại profile F1; chưa có fallback tự động. F2/F3 nhiều pixel hơn và có thể nặng hơn.
- Đây là nhánh thử nghiệm độc lập trên Windows native. Người dùng đã chạy F1 thành công trên RTX 3060 trong 206 giây và duyệt chất lượng preview; F10/F20 chưa benchmark trên máy đó. Test cục bộ trên CPU chỉ kiểm tra controller/FFmpeg, không xác nhận tốc độ GPU hay chất lượng hình ảnh.
