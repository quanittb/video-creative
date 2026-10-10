# Tạo motion base Echo Flash rồi tái sử dụng trên Windows

Hướng dẫn này dùng EchoMimic V3 Flash để sinh một đoạn chuyển động thuận cho **từng ảnh nhân vật**, sau đó dùng MuseTalk lặp hình tiến/lùi và thay lời thoại. Cách này tránh chạy Echo cho mỗi kịch bản. Để giữ nguyên thân, áo và tóc theo từng ảnh, mỗi nhân vật mới vẫn cần sinh motion base và tạo MuseTalk avatar cache một lần.

## Cài bản cập nhật vào máy Windows

Sao chép `rtx3060_echo_flash_loop_v2_patch.zip` sang máy Windows, rồi giải nén **đè vào thư mục gốc dự án** `C:\Users\Admin\Downloads\video-creative-studio\video-creative-studio`, giữ nguyên các thư mục `scripts`, `tests`, `docs`. Bản vá cập nhật controller và hướng dẫn; nó không chứa model, không yêu cầu tải lại model hoặc tạo lại Echo/MuseTalk venv. Đóng các CMD đang chạy pipeline trước khi chép file.

## Chọn profile

| Profile | Echo sinh thuận | Chu kỳ MuseTalk `pingpong` | Mục đích |
|---|---:|---:|---|
| F1 | 3,24 giây | 6,48 giây | Preview đã duyệt; có thể tái sử dụng ngay |
| F10 | 5,16 giây | 10,32 giây | Profile khuyến nghị để thử nhịp lặp gần video mẫu |
| F20 | 9,96 giây | 19,92 giây | Thử nghiệm tùy chọn; nặng hơn F10, chưa benchmark |

Tên F10/F20 nói về **chu kỳ tiến-lùi danh nghĩa**, không phải độ dài clip Echo một chiều. Echo chỉ sinh lần lượt 129 hoặc 249 frame; MuseTalk đảo chiều phần motion khi lặp. Đối chiếu nhịp phần vai/áo trong `Avatar_Video.mp4` cho thấy chu kỳ khoảng 10,32 giây là điểm bắt đầu phù hợp để thử. Echo tự sinh cử chỉ theo ảnh, prompt và audio ngắn; không sao chép từng tọa độ từ video mẫu và kết quả chuyển động vẫn cần xem trước.

Profile F10 giữ độ phân giải 384×480, 8 bước và seed 42 như F1; nó sinh thêm frame nên sẽ mất thời gian hơn. Lượt F1 trước đó mất 206 giây tổng cộng, trong đó 135 giây denoise cho 81 frame. Nếu thời gian tăng gần tuyến tính theo frame, F10 có thể mất khoảng 5 phút; đây chỉ là phép ngoại suy, chưa đo F10 trên RTX 3060. RAM/VRAM và chất lượng của F10 cũng cần được xác nhận trên máy thật. F20 là tùy chọn thử sau khi F10 được duyệt.

## A. Tạo motion base F10 một lần

Mở CMD trong thư mục dự án và chỉ định GPU Python Echo đã cài:

```bat
cd /d "C:\Users\Admin\Downloads\video-creative-studio\video-creative-studio"
set "ECHO_FLASH_PYTHON=C:\Users\Admin\Downloads\EchoMimicV3\venv\Scripts\python.exe"
```

Chạy dry-run để xác nhận ảnh, audio, giới hạn frame và model:

```bat
test_echo_flash_rtx3060.bat dry-run --profile F10
```

Kết quả cần ghi `129 frame @25fps = 5.160s` và `chu kỳ danh nghĩa là 10.320s`. Không truyền `--duration`: controller dùng hết thời lượng profile đã chọn. Nếu audio ngắn hơn 5,16 giây, hãy dùng audio dài hơn; chương trình không lặp audio để đủ frame.

Khi dry-run đạt, render F10:

```bat
test_echo_flash_rtx3060.bat run --profile F10
```

Giữ CMD mở tới khi có `Backend completed 1 output(s)` và các dòng `Motion base`, `Voice preview`, `Run manifest`. Mở `voice_preview.mp4` để kiểm tra trước khi duyệt. Motion base là file im lặng dùng cho các lần lồng tiếng sau. Ví dụ profile dài hơn bằng F20:

```bat
test_echo_flash_rtx3060.bat dry-run --profile F20
test_echo_flash_rtx3060.bat run --profile F20
```

F20 sinh thuận 9,96 giây, chu kỳ ping-pong 19,92 giây. Chỉ thử sau khi F10 đạt và chấp nhận thời gian render tăng. Bộ kiểm tra từ chối `--duration` dài hơn giới hạn profile thay vì âm thầm cắt. Các lệnh cũ F1/F2/F3 vẫn giữ thời lượng profile 3,24 giây nếu bỏ `--duration`.

## B. Dùng F10 cho audio một phút và tạo avatar cache

Trong chính cửa sổ CMD, nhập lệnh sau. Khi CMD hỏi, dán **đúng đường dẫn sau chữ `Motion base:`** mà lệnh F10 vừa in; chỉ dán đường dẫn, không thêm dấu ngoặc kép:

```bat
set /p "ECHO_BASE=Dan duong dan Motion base vua in (khong kem dau ngoac kep), roi Enter: "
dir "%ECHO_BASE%"
```

Lệnh `dir` phải tìm thấy file `motion_base.mp4`. Nếu báo không tìm thấy, nhập lại đúng đường dẫn; chưa chạy MuseTalk cho tới khi tìm thấy file.

Preflight MuseTalk trên toàn bộ audio:

```bat
test_cached_musetalk.bat dry-run --base-video "%ECHO_BASE%" --audio "sample_script_1min.mp3" --duration 60 --fps 25 --batch-size 2 --cache-dir "C:\vcs_cache" --motion-policy pingpong
```

Dry-run phải báo `Audio effective` gần 55,584 giây, `ping-pong explicitly enabled`, chu kỳ danh nghĩa 10,320 giây và khoảng 6 chu kỳ (lượt cuối có thể chưa trọn). Nó không chạy backend.

Chạy MuseTalk một lần cho video:

```bat
test_cached_musetalk.bat run --base-video "%ECHO_BASE%" --audio "sample_script_1min.mp3" --duration 60 --fps 25 --batch-size 2 --cache-dir "C:\vcs_cache" --motion-policy pingpong --output "output\cached_musetalk\echo_f10_1min.mp4"
```

Lần `run` đầu tự preprocessing ảnh/video avatar, lưu cache vào `C:\vcs_cache`, rồi mới render. Không chạy `prepare` trước `run` nếu ưu tiên tổng thời gian: `prepare` rồi `run` sẽ nạp MuseTalk hai lượt. Dùng `prepare` riêng chỉ khi chủ động muốn tách thời gian preprocessing khỏi thời gian render.

Mở output sau khi lệnh báo thành công:

```bat
start "" "output\cached_musetalk\echo_f10_1min.mp4"
```

MuseTalk chỉ lặp/đảo **hình chuyển động**; audio vẫn chạy xuôi một lần và chỉ cắt ở độ dài audio có thật. Các chuyển động như chớp mắt, tóc hoặc nếp áo có thể trông lạ khi đảo chiều hoặc tại điểm nối, nên xem cả đầu/cuối và chỗ nối chu kỳ trước khi dùng hàng loạt.

## C. Tái sử dụng cho các kịch bản cùng nhân vật

Giữ lại `ECHO_BASE` và thư mục `C:\vcs_cache`. Với audio mới, dùng lại motion base và chạy `test_cached_musetalk.bat run` với đường dẫn audio/output mới, cùng `--motion-policy pingpong`. Avatar cache sẽ được tái sử dụng cho cùng một motion base; Echo không cần render lại.

Ví dụ kịch bản khác:

```bat
test_cached_musetalk.bat run --base-video "%ECHO_BASE%" --audio "assets\audio\script_02.mp3" --duration 60 --fps 25 --batch-size 2 --cache-dir "C:\vcs_cache" --motion-policy pingpong --output "output\cached_musetalk\echo_f10_script_02.mp4"
```

Thời lượng audio hữu hiệu là giá trị nhỏ hơn giữa audio thật và `--duration`. Nếu lời thoại ngắn hơn 60 giây, output có tiếng chỉ dài bằng lời thoại; pipeline không thêm đoạn im lặng để ép video đủ một phút.

## D. Nhân vật mới

Để giữ khuôn mặt, thân, áo và tóc theo **ảnh nhân vật mới**, chạy Echo F10 một lần với `--image`:

```bat
test_echo_flash_rtx3060.bat dry-run --profile F10 --image "assets\characters\duongdan\nhanvat_moi.png"
test_echo_flash_rtx3060.bat run --profile F10 --image "assets\characters\duongdan\nhanvat_moi.png"
```

Thay đường dẫn ví dụ bằng ảnh nhân vật mới trước khi chạy. Để thử bằng ảnh nữ đã có trong project, có thể dùng:

```bat
test_echo_flash_rtx3060.bat dry-run --profile F10 --image "assets\characters\nhanvatnu\ChatGPT Image Sep 14, 2026, 11_35_53 AM (1).png"
test_echo_flash_rtx3060.bat run --profile F10 --image "assets\characters\nhanvatnu\ChatGPT Image Sep 14, 2026, 11_35_53 AM (1).png"
```

Đặt `ECHO_BASE` theo `motion_base.mp4` mới được in ra, rồi chạy MuseTalk. Clip mới tạo avatar cache riêng cho nhân vật đó; các kịch bản kế tiếp của cùng nhân vật dùng lại clip/cache. Trong pipeline Echo/MuseTalk này, mỗi ảnh mới cần base/cache riêng để giữ toàn bộ ngoại hình.

## E. Dùng ngay preview F1 đã duyệt

Để đo thời gian MuseTalk một phút ngay mà không chờ Echo F10, có thể trỏ `ECHO_BASE` vào F1 đã duyệt:

```bat
set "ECHO_BASE=C:\Users\Admin\Downloads\video-creative-studio\video-creative-studio\output\echo_flash\f1_59af1f4b6182\motion_base.mp4"
```

Sau đó chạy các lệnh dry-run/run ở mục B. F1 có chu kỳ ping-pong danh nghĩa 6,48 giây, nên đây chỉ là smoke test và phép đo MuseTalk; để thử nhịp lặp gần video mẫu, tạo và duyệt F10 trước.
