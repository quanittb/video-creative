# Kế hoạch kiểm thử ảnh thành video trên RTX 3060 12 GB

Tài liệu này hướng dẫn so sánh pipeline LivePortrait → MuseTalk bằng cùng một ảnh, driving clip và audio. Output B cho thấy chuyển động đầu đã ổn, nhưng vai còn ít chuyển động: optical flow theo dõi feature mặt dịch chuyển khoảng 20 px trên ảnh chiếu, trong khi vùng áo được đo chỉ dịch 1–2 px. Các con số này là chuyển động 2D trên ảnh, không phải quãng đường vật lý của đầu/vai. B1/B2 thử tăng phản ứng vai và cho phép mask tác động nhẹ qua đường viền thân. Chất lượng thực tế còn phụ thuộc ảnh nguồn, driving clip, mô hình và môi trường GPU; các thiết lập dưới đây là điểm bắt đầu để đo trên máy RTX 3060 12 GB, không phải cam kết kết quả.

## Dữ liệu và giới hạn của lượt thử

- Ảnh nguồn: `assets/characters/nhanvatnam/asian_male_office_1080p.png`, kích thước 1024×1280.
- Audio: `sample_script_1min.mp3`, dài khoảng 55,584 giây.
- Driving clip kiểm thử: `assets/driving_templates/reference_head_driving.mp4`, 512×512, 25 fps, dài khoảng 38 giây. Clip được crop từ video mẫu bằng vùng `crop=512:512:300:620` và bỏ audio gốc.
- Mỗi lượt trong launcher chỉ xử lý 12 giây đầu, vì thế mọi lượt dùng cùng một đoạn hình và tiếng, không bị ảnh hưởng bởi phần cuối driving clip.

Không nên render audio 55,584 giây với driving clip 38 giây và `hold`: LivePortrait sẽ giữ frame chuyển động cuối trong khoảng 17,584 giây còn lại. Chính sách `loop` cũng có thể làm chuyển động lặp lại lộ rõ. Muốn đánh giá video đủ một phút, hãy chuẩn bị driving clip tự nhiên dài ít nhất bằng thời lượng audio rồi dùng cùng chính sách cho mọi cấu hình so sánh.

## Thay đổi so với launcher cũ

Chạy `test_rtx3060.bat` ở thư mục dự án. Launcher mới không đọc Dropbox, không chép đè mã nguồn hoặc asset, không cài/cập nhật package. Nó truyền tường minh ảnh, driving, audio và output; lưu video cùng log ở `output\rtx3060\`. `all` vẫn chạy 4 cấu hình baseline A1/A2/A3/B rồi dừng ở lượt lỗi đầu tiên. Có thể chạy riêng một cấu hình bằng `test_rtx3060.bat A2`; hai lượt vai mới chạy bằng `test_rtx3060.bat shoulders` (hoặc riêng `B1`, `B2`). `test_rtx3060.bat dry-run` kiểm tra ma trận cũ; `test_rtx3060.bat shoulders dry-run` chỉ kiểm tra hai lượt vai. Dry-run không chạy GPU hoặc tạo video. Chạy lại cùng cấu hình sẽ thay file video và log cùng tên trong thư mục test.

Không dùng launcher cũ `test_option_b.bat` cho các lượt này: file đó có đoạn tự chép file từ Dropbox lên mã nguồn trong project.

Dùng `output/rtx3060_pipeline_patch_v3.zip` (14 file) và giải nén vào thư mục gốc của project hiện có, giữ nguyên các đường dẫn tương đối trong ZIP. Gói gồm pipeline/test, tài liệu, launcher, helper `scripts/generate_office_torso_silhouette_mask.py`, ảnh nguồn `assets/characters/nhanvatnam/asian_male_office_1080p.png`, audio `sample_script_1min.mp3`, driving clip và cả hai mask (`office_torso_motion_mask.png`, `office_torso_silhouette_mask.png`). Không cần chạy helper để test vì mask đã có sẵn; helper chỉ hiệu chuẩn mask cho ảnh office mẫu đi kèm, không phải công cụ phân đoạn dùng chung cho ảnh chân dung khác. Gói không chứa video mẫu hoặc model weights. Launcher ưu tiên ảnh ở đường dẫn `assets/characters/nhanvatnam/`; nếu thiếu, nó dùng `asian_male_office_1080p.png` nằm ngay thư mục gốc project. Hãy giải nén gói vào đúng thư mục chứa `test_rtx3060.bat`, không giải nén thành một thư mục lồng thêm. Ví dụ với bản tải xuống, thư mục đó có thể là `C:\Users\Admin\Downloads\video-creative-studio\video-creative-studio`. Sau khi giải nén, chạy:

```bat
test_rtx3060.bat dry-run
test_rtx3060.bat A2
test_rtx3060.bat shoulders dry-run
test_rtx3060.bat shoulders
```

`A1`, `A2`, `A3` chạy với motion thân `off`, nên không cần mask. `B` dùng mask thân bên trong cũ; `B1`/`B2` dùng mask silhouette mới. `all` và `dry-run` giữ nguyên 4 lượt baseline A1/A2/A3/B; `shoulders` chạy B1/B2. Nếu báo thiếu ảnh hoặc mask, hãy kiểm tra gói V3 đã được giải nén vào thư mục chứa launcher và ảnh/mask nằm đúng các đường dẫn nêu trên. Lỗi asset ở bước preflight chưa phải lỗi CUDA hay RTX 3060. Nếu lỗi xảy ra ở bước preflight, launcher chưa tạo log cho lượt chạy đó.

Dùng môi trường Python 3.10 đã thiết lập cho LivePortrait; MuseTalk tiếp tục dùng Python riêng nếu cấu hình hiện tại yêu cầu. Không cần chạy lệnh cài package để áp dụng gói này.

## Ma trận cấu hình khởi đầu

Các biến giữ cố định giữa những lượt: 25 fps, `source-max-dim=1280`, batch MuseTalk 2, offset 0 ms, `driving-policy=hold`, tắt eye retargeting và tắt legacy vendor patches. Tất cả đầu ra dùng cùng 12 giây đầu của audio và driving clip.

| Mã | LivePortrait multiplier | Motion thân | Output | Mục đích |
|---|---:|---|---|---|
| A1 | 0.40 | `off` | `output/rtx3060/A1.mp4` | Chuyển động đầu nhẹ, làm mốc bảo thủ. |
| A2 | 0.55 | `off` | `output/rtx3060/A2.mp4` | Mức mặc định để so sánh với output hiện tại. |
| A3 | 0.70 | `off` | `output/rtx3060/A3.mp4` | Kiểm tra driving có tạo chuyển động đầu quá mạnh hay không. |
| B | 0.55 | `coupled` | `output/rtx3060/B.mp4` | Thêm phản ứng vai nhỏ theo dịch chuyển đầu thực đo được. |
| B1 | 0.55 | `coupled` + `silhouette` | `output/rtx3060/B1.mp4` | Thử vai rõ hơn, giới hạn dịch 4 px, coupling 0.65, thời gian đáp ứng 0.18 giây. |
| B2 | 0.55 | `coupled` + `silhouette` | `output/rtx3060/B2.mp4` | So với B1 ở giới hạn dịch 6 px; cùng coupling 0.65 và thời gian đáp ứng 0.18 giây. |

Tất cả lượt vai giữ nguyên chuyển động đầu đã chốt ở multiplier 0.55. B giữ mode `interior` hiện tại: mask chỉ tác động lên vùng áo bên trong và giới hạn dịch tối đa 2,5 px ở chiều cao 1280 px. Trong output B, feature mặt theo dõi bằng optical flow dịch khoảng 20 px trên ảnh chiếu, còn ROI áo dịch khoảng 1–2 px; đây là hai phép đo 2D ở các vùng khác nhau, không phải tỷ lệ chuyển động vật lý của đầu so với vai. B1/B2 giữ nguyên feature mặt, tăng coupling strength lên 0.65 và dùng thời gian đáp ứng 0.18 giây để chuyển động áo bám theo feature mặt mượt hơn. Chúng dùng mask `silhouette` và lần lượt giới hạn dịch 4 px/6 px. Mask silhouette được hiệu chuẩn cho ảnh văn phòng 1024×1280. Nền được inpaint một lần từ frame đầu, rồi chỉ ghép vào dải hẹp mà chuyển động làm hở ở biên; vùng đáy được neo dần để giảm trượt thân. Đây là phép biến dạng 2D nhỏ, không tạo hình học 3D, không suy ra phần vai bị khuất, và có thể để lộ viền hoặc kéo nền/áo nếu biên độ quá mạnh. ROI bảo vệ mặt là `360 490 320 460`. Giữ nguyên ảnh nguồn và `source-max-dim=1280`; khi đổi ảnh hoặc kích thước output phải hiệu chuẩn lại mask/ROI trước khi dùng các mode này.

Hai video xem trước ở link bên dưới chỉ biến đổi vùng thân trên video B có sẵn. Video B đã chứa chuyển động vai `interior` cũ; preview cộng thêm hiệu ứng biên silhouette để so mức 4 px/6 px. Đây là preview thân, không phải render mới của LivePortrait/MuseTalk hay kết quả từ RTX 3060. Pipeline B1/B2 thực tế sẽ áp dụng silhouette một lần lên Stage 1 trước MuseTalk. Các preview chỉ có trong workspace review, không nằm trong gói V3.

- [B1 preview — silhouette 4 px](../output/shoulder_review/B1_shoulders_4px.mp4)
- [B2 preview — silhouette 6 px](../output/shoulder_review/B2_shoulders_6px.mp4)

## Cách chạy và đọc kết quả

1. Mở Command Prompt tại thư mục dự án, kiểm tra `python`, `ffmpeg`, `ffprobe`, LivePortrait, MuseTalk và các weight đã sẵn có. Lệnh `test_rtx3060.bat dry-run` ghi báo cáo dò đường dẫn vào `output\rtx3060\*_dryrun.log`, không chạy GPU hoặc tạo video.
2. Mở một cửa sổ terminal thứ hai và chạy `nvidia-smi -l 1` để quan sát VRAM trong lúc render. Ghi lại mức VRAM cao nhất thấy được; pipeline chưa đo và chưa xác nhận mức peak trên RTX 3060 trong môi trường này.
3. Vì A2/B cho thấy đầu ổn nhưng vai quá tĩnh, chạy `test_rtx3060.bat shoulders` để render B1 và B2. Mỗi video dài 12 giây. Có thể gọi `test_rtx3060.bat B1` hoặc `B2` để chạy lại riêng. `test_rtx3060.bat` (không đối số) vẫn chỉ chạy 4 baseline cũ.
4. So B1/B2 với B ở cùng thời điểm. Kiểm tra vai có bám theo feature mặt một cách mượt và tự nhiên không, cổ áo có bị trượt khỏi cổ không, đường viền mask có nhấp nháy/halo không, nền có bị kéo hoặc inpaint lộ không, và vải có giãn bất thường không. B2 là mức thử mạnh hơn; chọn theo video, không mặc định rằng dịch nhiều hơn sẽ tự nhiên hơn. Dùng log để xác nhận các lượt dùng cùng input, FPS và thời lượng.

Nếu `dry-run` báo không tìm thấy thư mục LivePortrait/MuseTalk, hãy truyền đường dẫn cài đặt tương ứng khi gọi Python trực tiếp, ví dụ:

```bat
python test_option_b_avatar.py --char office --source assets\characters\nhanvatnam\asian_male_office_1080p.png --driving assets\driving_templates\reference_head_driving.mp4 --audio sample_script_1min.mp3 --duration 12 --output output\rtx3060\A2.mp4 --fps 25 --source-max-dim 1280 --multiplier 0.55 --driving-policy hold --motion-mode off --batch-size 2 --offset-ms 0 --liveportrait-dir "D:\AI\LivePortrait" --musetalk-dir "D:\AI\MuseTalk" --musetalk-python "D:\AI\musetalk-venv\Scripts\python.exe"
```

Nếu `python` trong PATH trỏ nhầm môi trường, đặt `VCS_PYTHON` trong Command Prompt trước khi chạy launcher, ví dụ:

```bat
set "VCS_PYTHON=C:\AI\video-venv\Scripts\python.exe"
test_rtx3060.bat A2
```

Python đó cần import được các dependency của pipeline/LivePortrait. MuseTalk có thể dùng Python riêng qua `--musetalk-python` như ví dụ trên.

## Tinh chỉnh sau khi chọn chuyển động đầu

Chuyển động đầu ở mức A2/B đã được đánh giá ổn; bước tiếp theo là so B1/B2 để chọn phản ứng vai tự nhiên mà không lộ mask. Sau đó mới so offset khẩu hình, giữ nguyên tất cả thông số khác và xuất mỗi offset ra file riêng. Ví dụ với cấu hình A2:

```bat
python test_option_b_avatar.py --char office --source assets\characters\nhanvatnam\asian_male_office_1080p.png --driving assets\driving_templates\reference_head_driving.mp4 --audio sample_script_1min.mp3 --duration 12 --output output\rtx3060\A2_offset_m080.mp4 --fps 25 --source-max-dim 1280 --multiplier 0.55 --driving-policy hold --motion-mode off --batch-size 2 --offset-ms -80
python test_option_b_avatar.py --char office --source assets\characters\nhanvatnam\asian_male_office_1080p.png --driving assets\driving_templates\reference_head_driving.mp4 --audio sample_script_1min.mp3 --duration 12 --output output\rtx3060\A2_offset_000.mp4 --fps 25 --source-max-dim 1280 --multiplier 0.55 --driving-policy hold --motion-mode off --batch-size 2 --offset-ms 0
python test_option_b_avatar.py --char office --source assets\characters\nhanvatnam\asian_male_office_1080p.png --driving assets\driving_templates\reference_head_driving.mp4 --audio sample_script_1min.mp3 --duration 12 --output output\rtx3060\A2_offset_p080.mp4 --fps 25 --source-max-dim 1280 --multiplier 0.55 --driving-policy hold --motion-mode off --batch-size 2 --offset-ms 80
```

Offset dịch feature audio trong MuseTalk; nó không dịch audio mux cuối. Chọn bằng cách xem miệng ở vài phụ âm/nguyên âm rõ và nghe lại trên cùng đoạn. Nếu khác biệt khó nhận ra, giữ 0 ms. Sau khi chốt chuyển động và offset cơ bản, có thể thử thêm `--flag-eye-retargeting` trong một lượt riêng; tùy chọn này được upstream đánh dấu WIP. Để `--legacy-vendor-patches` tắt trong các so sánh này vì custom smoothing/blink cũ có thể làm thay đổi nhịp chuyển động.

## Giới hạn và xử lý lỗi VRAM

- Pipeline chạy LivePortrait rồi mới khởi chạy MuseTalk ở tiến trình riêng, giúp giải phóng bộ nhớ GPU giữa hai stage. Cả hai stage vẫn cần weight và CUDA environment hợp lệ.
- Bắt đầu với MuseTalk batch 2. Nếu log báo CUDA out-of-memory, đóng tiến trình GPU khác, chạy lại với `--batch-size 1` và output tên khác. Không thể khẳng định mức VRAM hoặc thời gian render cụ thể trước khi đo trên chính máy.
- `source-max-dim=1280` giữ kích thước pasteback của ảnh văn phòng. Giảm xuống 720 có thể giảm tải cho ảnh/output và làm ảnh mềm hơn; nó không nhất thiết giảm VRAM MuseTalk theo cùng tỷ lệ vì vùng mặt xử lý nội bộ ở kích thước 256 px. Giảm kích thước này cũng làm hai mask 1024×1280 hiện có không còn phù hợp cho mode `coupled`.
- MuseTalk làm việc trên vùng mặt nội bộ 256 px; video/pasteback kích thước lớn không tương đương chi tiết khuôn mặt thật 1080p.
- Nếu B/B1/B2 lỗi kiểm tra mask/ROI, quay về A2 (`motion-mode off`) để xác nhận LivePortrait/MuseTalk độc lập trước. Không nới lỏng kiểm tra kích thước mask hoặc vùng bảo vệ mặt để ép lượt chạy.
- Ảnh đơn không chứa dữ liệu hình học/chuyển động vai thật. Chuyển động head vẫn bị giới hạn bởi driving clip; coupling vai chỉ là phản ứng nhỏ trong mask. Cần đánh giá trực quan, không thể suy ra tự nhiên chỉ từ file render chạy thành công.
