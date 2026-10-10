# Test ads dọc, khẩu hình và thời gian trên RTX 3060 Windows

Bộ này giữ EchoMimic V3 Flash + MuseTalk v1.5 đã chạy được. Khung cuối là 1080×1920, 9:16, 25 FPS, MP4 H.264/AAC. Với ảnh hiện tại 4:5, sinh nền ở 512×640 rồi dựng dọc sau lip-sync giúp giữ toàn bộ hai vai và giảm số pixel AI cần sinh. Phần ảnh nhân vật được scale đồng đều trên nền mờ từ chính video; không kéo giãn hoặc crop phần nhân vật. Lanczos tăng kích thước xuất, không tạo thêm chi tiết như model super-resolution.

TikTok khuyến nghị video dọc 9:16, ít nhất 540×960: [thông số chính thức](https://ads.tiktok.com/resources/help/article/tiktok-auction-in-feed-ads?lang=en-GB-8). Khổ xuất đáp ứng kích thước đó; bộ này chưa thêm phụ đề, sản phẩm, CTA hoặc đăng quảng cáo.

## Cập nhật core trên Windows

Đóng pipeline đang chạy rồi cập nhật source dự án có phiên bản mới của `scripts\test_vertical_ads.py`. Không cần cài lại venv, tải model hay xóa cache MuseTalk/Echo. Các thay đổi chỉ nằm trong controller/exporter của dự án; không sửa repo MuseTalk/WanGP hoặc checkpoint.

```bat
cd /d "C:\Users\Admin\Downloads\video-creative-studio\video-creative-studio"
set "ECHO_FLASH_PYTHON=C:\Users\Admin\Downloads\EchoMimicV3\venv\Scripts\python.exe"
```

Các lệnh chạy trong CMD này. Nếu dùng CMD mới, vào lại project và đặt lại biến cần dùng.

## 1. Sinh nền 10,32 giây theo chu kỳ tiến/lùi

| Profile | Native Echo | Số frame gốc | Chu kỳ MuseTalk tiến/lùi |
|---|---:|---:|---:|
| F10 | 384×480 | 129 = 5,16s | 10,32s |
| A10 — nên thử trước | 512×640 | 129 = 5,16s | 10,32s |
| A10HQ — thử sau | 640×800 | 129 = 5,16s | 10,32s |

A10/A10HQ giữ 8 steps, seed 42 và tham số model cũ. Độ phân giải cao hơn có thể chậm hơn hoặc thiếu VRAM; chưa có benchmark các profile mới trên GPU của người dùng. Không tự hạ chất lượng khi lỗi. Giữ ảnh gốc có đủ đầu, cổ, vai và không cắt thân ngoài khung ảnh; các ảnh hiện có gần tỷ lệ 4:5 phù hợp đường sinh nền này.

Motion base dùng làm nền quảng cáo cần **speech**: Echo nhận audio thật để tạo chuyển động. Prompt speech hiện giữ đầu thẳng, ở giữa và hướng camera; tránh xoay/lắc trái-phải lặp lại; chỉ cho phép gật rất nhẹ cùng chuyển động vai vừa phải. Đây là mode mặc định và là mode nên dùng để tạo motion base có chuyển động.

Không dùng **neutral** để tạo motion base cho quảng cáo chuyển động. Mode này thay conditioning audio bằng tín hiệu im lặng và giữ đầu gần tĩnh; video có thể gần như đứng yên. `Voice preview` của neutral cũng im lặng. Chế độ này không tạo lời thoại và không nên dùng làm nền chuyển động.

```bat
test_echo_flash_rtx3060.bat dry-run --profile A10 --mouth-mode speech
```

Khi dry-run đạt, chạy:

```bat
test_echo_flash_rtx3060.bat run --profile A10 --mouth-mode speech
```

Mở `Motion base` vừa được in, xem cả hai vai, cổ và đầu. Kiểm tra đầu giữ tương đối thẳng, không lắc trái-phải liên tục, trong khi vai/thân vẫn chuyển động tự nhiên theo audio. Đây là motion base sinh bằng speech conditioning; MuseTalk sẽ tạo khẩu hình cuối ở bước sau. Nếu chưa đạt, chỉnh ảnh/prompt rồi sinh nền mới; không dùng lại nền cũ để đánh giá tác dụng của prompt mới.

Lấy đường dẫn Motion base:

```bat
set /p "ECHO_BASE=Dan duong dan Motion base (khong kem dau ngoac kep), roi Enter: "
dir "%ECHO_BASE%"
```

Chỉ tiếp tục khi `dir` tìm thấy file. Muốn test khẩu hình ngay trên F10 đã duyệt để tránh chờ sinh nền mới, dùng đường dẫn F10 cũ ở bước này; phần nâng độ phân giải native chỉ có sau khi tạo A10/A10HQ.

## 2. Duyệt khẩu hình trước khi chạy dài

MuseTalk upstream tạo Whisper audio features ở **50 Hz**, rồi lấy context tương ứng cho video **25 FPS** (khoảng 40 ms mỗi frame); mỗi frame dùng feature context gồm nhiều bước kề nhau. Vì vậy audio đã im lặng không đảm bảo mọi frame miệng sẽ tự khép đúng ngay tại ranh giới pause. Pipeline giờ tạo một bản conditioning riêng: dò pause bằng RMS PCM/hysteresis, rồi đặt mẫu PCM16 trong vùng đủ tin cậy về digital zero **trước** khi MuseTalk trích Whisper features. `auto` mute pause dài từ 0,32 giây; `force` từ 0,16 giây. Ngưỡng RMS và bảo vệ giọng nhỏ giữ phần speech ngoài các khoảng đã nhận diện nguyên vẹn. Đây chỉ là gate audio cho MuseTalk: không thay frame motion base, không làm đứng hình đầu/vai, không thêm model hay tải dữ liệu, chỉ thêm lượt scan/ghi WAV CPU.

Offset `-40/0/+40 ms` được áp dụng **sau gate**, vì vậy khoảng pause trong conditioning audio dịch cùng lời nói. Final MP4 luôn nhận lại audio chuẩn hóa gốc, không gate và không dịch. Nếu gate làm thay đổi waveform hoặc chọn offset khác 0, pipeline remux audio gốc sau MuseTalk trước các bước correction/export.

Sau inference, bước correction bằng frame motion base vẫn là lớp phụ: chỉ crossfade khi **cả** frame output lẫn thời điểm nguồn của frame được ánh xạ đều nằm trong pause. Cách này giữ chuyển động đầu/vai liên tục và không chạy inference thêm. `auto` correction cần Echo manifest xác nhận mode `speech` cùng SHA-256 audio trùng; `force` bỏ qua cổng mode/hash nhưng vẫn cần xác minh source-time pause. Motion base 5,16 giây được lặp tiến/lùi trong chu kỳ khoảng 10,32 giây, nên pause muộn có thể không có frame nguồn im lặng tương ứng. Report tách các pause được yêu cầu, được correction và chưa được correction.

Report `motion_audio_alignment` so SHA-256 audio Echo dùng để tạo cử chỉ với audio hiện tại. Khi mismatch hoặc không có manifest, cảnh báo rằng gate/correction chỉ tác động khẩu hình, không đồng bộ lại gesture đầu/vai; hãy tạo Echo speech base mới nếu cần cử chỉ theo đúng kịch bản. `--pause-mouth-closure off` tắt cả gate và post-render correction. Không thể cam kết lip-sync hoàn hảo bằng ngưỡng pause: Whisper context, giới hạn 25 FPS và sai số của model vẫn có thể làm khẩu hình lệch; phải nghe/xem A/B video thật trước khi chạy dài.

Tham chiếu upstream: [MuseTalk `audio_processor.py`](https://github.com/TMElyralab/MuseTalk/blob/main/musetalk/utils/audio_processor.py) (16 kHz input, 50 Hz Whisper features và cách ánh xạ sang FPS output).

Kiểm tra cấu hình trước:

```bat
test_vertical_ads.bat dry-run --base-video "%ECHO_BASE%" --duration 3.24 --audio-offset-ms 0
```

Khi đạt, tạo hai clip ngắn cùng nền/audio:

```bat
test_vertical_ads.bat calibrate --base-video "%ECHO_BASE%" --duration 3.24 --audio-offset-ms 0
```

CMD in `output\vertical_ads\job_<timestamp>_<id>` và hai đường dẫn MP4 1080×1920:

- `vertical_ad_1080x1920_baseline.mp4`: bbox shift 0, mask jaw (mode hiện tại).
- `vertical_ad_1080x1920_raw_mask.mp4`: bbox shift 0, mask raw.

Log Windows xác nhận MuseTalk v1.5 đặt `bbox_shift` về 0 dù cấu hình truyền giá trị khác. Adapter giờ từ chối giá trị khác 0 trong dry-run, trước khi nạp model; hiệu chỉnh chỉ so sánh jaw/raw. Mỗi parsing mode tạo avatar cache riêng; cache cũ không bị ghi đè.

Nghe và xem lời nói rồi khoảng nghỉ: miệng nên ngừng nói khi ngừng tiếng, đóng/mở theo âm, không rung hoặc méo môi. `calibrate` tối đa 6s và không chấm điểm SyncNet/phoneme giả. Kiểm tra codec, FPS, duration pass **không đồng nghĩa** lip-sync đã đạt. `lip_calibration_report.json` ghi các cấu hình và thời gian.

Chọn cấu hình sau khi xem. `LIP_SHIFT` luôn là 0 trên MuseTalk v1.5; chọn mask trong CMD:

```bat
set "LIP_SHIFT=0"
set "LIP_MASK=jaw"
```

Nếu baseline tốt hơn, giữ `LIP_MASK=jaw`. Nếu clip `raw_mask` khớp môi hơn, đổi `LIP_MASK=raw`. Nếu cả hai chưa đạt, gửi các clip ngắn để đánh giá tiếp; chưa chạy video dài.

Để `--pause-mouth-closure auto` mặc định cho preview và render. Gate conditioning `auto` chạy trên audio hiện tại, kể cả khi base được tái sử dụng; riêng correction frame sau render yêu cầu manifest Echo có mode `speech` và SHA-256 audio trùng file hiện tại. Base neutral, khác audio, thiếu hash hoặc không tìm được manifest sẽ bỏ qua correction an toàn. Kể cả khi khớp, chỉ frame nguồn nằm trong pause của audio conditioning mới được dùng; các pause muộn không có frame nguồn tương ứng được ghi là chưa xử lý.

`force` đặt ngưỡng gate/correction xuống pause từ 0,16 giây. Nó bỏ qua cổng mode/hash của correction, ví dụ khi audio đầu ra khác audio đã dùng tạo base, nhưng vẫn **không** lấy frame nguồn tại thời điểm Echo đang nghe lời nói: cần đọc và xác minh được file `source_audio` cùng SHA-256 trong manifest; nếu thiếu thì report ghi các pause chưa xử lý và không blend frame nào. `off` tắt gate conditioning lẫn correction frame sau render.

Offset mặc định là 0ms và không tự đoán. Nếu khẩu hình có vẻ sớm/trễ, dùng preview A/B quanh 0 bằng jaw mask:

```bat
test_vertical_ads.bat calibrate --base-video "%ECHO_BASE%" --duration 3.24 --audio-offset-sweep
```

Lệnh tạo ba preview ở -40/0/+40ms; mỗi preview mở tiến trình MuseTalk riêng và nạp lại model nên thời gian tăng đáng kể. Xem kèm audio, chọn bản khẩu hình khớp phụ âm/nguyên âm tốt nhất; sweep chỉ là A/B nghe/nhìn, không phải điểm SyncNet/phoneme. Offset dương làm miệng trễ audio; âm làm miệng đi trước. Chỉ áp dụng cho MuseTalk conditioning. Final MP4 luôn nhận lại WAV chuẩn hóa không dịch; với offset khác 0, WAV đó được mã hóa AAC một lần rồi stream-copy qua bước pause/export.

Ba output nằm trong thư mục job: `vertical_ad_1080x1920_jaw_offset_m40ms.mp4`, `vertical_ad_1080x1920_jaw_offset_0ms.mp4`, `vertical_ad_1080x1920_jaw_offset_p40ms.mp4`.

Thử trước đoạn đầu 3,24 giây (mẫu hiện có chứa pause khoảng 1,8–2,9 giây):

```bat
test_vertical_ads.bat run --base-video "%ECHO_BASE%" --audio "sample_script_1min.mp3" --duration 3.24 --cache-dir "C:\vcs_cache" --batch-size 2 --bbox-shift 0 --parsing-mode jaw --audio-offset-ms 0
```

Xem output `vertical_ad_1080x1920.mp4` trong job mới. Xác nhận miệng khép trong khoảng nghỉ, đầu/vai vẫn đi theo chuyển động nền và phần speech không bị dịch tiếng. Report ghi rõ khoảng pause đã xử lý, hash/path motion-base tham chiếu, offset và audio restore. Nếu preview đạt, chạy đầy đủ:

```bat
test_vertical_ads.bat run --base-video "%ECHO_BASE%" --audio "sample_script_1min.mp3" --duration 60 --cache-dir "C:\vcs_cache" --batch-size 2 --bbox-shift 0 --parsing-mode jaw --audio-offset-ms 0
```

Để giảm các cú lắc đầu trái-phải trong toàn clip, cần tạo **motion base speech mới** bằng prompt đã cập nhật ở Bước 1, rồi đặt `%ECHO_BASE%` thành đường dẫn mới. Đổi prompt không thay đổi motion base đã render trước đó.

## 3. Đo ads 15 giây, lần đầu và lần cache

```bat
test_vertical_ads.bat benchmark --base-video "%ECHO_BASE%" --duration 15 --bbox-shift %LIP_SHIFT% --parsing-mode %LIP_MASK% --audio-offset-ms 0
```

Lệnh tạo **hai video mới** trên cùng nền/audio, mỗi lượt đều chạy MuseTalk và export. Lượt đầu có thể `CREATE` hoặc đã `REUSE`; báo cáo ghi đúng thực tế, không xóa cache để giả lập cold run. Lượt thứ hai phải `REUSE` nếu cache hợp lệ. Cả hai đều nạp lại weights MuseTalk; đây là cache preprocessing/avatar, không phải GPU process nóng còn giữ weights.

Mỗi job giữ riêng native intermediate và hai file `vertical_ad_1080x1920_first.mp4`, `vertical_ad_1080x1920_cached.mp4`. Đọc:

- `benchmark_report.json`: duration thật, native/output resolution, crop/mask, trạng thái cache, thời gian từng lượt, model reload và hash output.
- `phase_timings.csv`: preflight, Echo nếu có, MuseTalk từng lượt, export+verification từng lượt và tổng các phase render.
- `whole_job_wall_seconds`: từ lúc workflow bắt đầu đến hoàn tất, gồm preflight và các bước thực hiện; không gồm khởi động Python/import trước workflow.

Thời gian `export_wall_seconds` gồm đọc/probe intermediate, FFmpeg CPU encode, probe và hash xác minh. `encoder_process_seconds` chỉ là FFmpeg. Tổng các phase render có tên `render_phase_sum`, không giả là toàn bộ wall time. Không dùng lại MP4 cũ để tính tốc độ render. Khi dùng `--base-video`, Echo được ghi `REUSED` với 0s; thời gian tạo nền trước đó nằm trong `run_manifest.json` của nền.

`audio_alignment.pause_gated_conditioning_audio` ghi WAV gating thực tế, SHA-256, thời lượng, số interval và số sample đã mute; `conditioning_variant_details` ghi hash/interval của từng offset sau gate, còn `conditioning_variants` giữ nguyên bản đồ đường dẫn cũ. `motion_audio_alignment` so SHA audio Echo với audio hiện tại và cảnh báo khi cử chỉ đầu/vai đang dựa trên audio khác. `pause_mouth_closure_wall_seconds` ghi riêng thời gian dò pause và blend frame sau render; gate thêm scan/ghi WAV CPU, không chạy thêm MuseTalk hay tải model. Audio normalization/gate/offset/remux AAC được tách thành field trong report; MuseTalk vẫn reload weights mỗi lần.

## 4. Một video production hoặc các mốc 30/60 giây

`run` chỉ tạo một video, phù hợp sản xuất sau khi đã duyệt khẩu hình:

```bat
test_vertical_ads.bat run --base-video "%ECHO_BASE%" --duration 30 --bbox-shift %LIP_SHIFT% --parsing-mode %LIP_MASK% --audio-offset-ms 0
```

```bat
test_vertical_ads.bat run --base-video "%ECHO_BASE%" --duration 60 --bbox-shift %LIP_SHIFT% --parsing-mode %LIP_MASK% --audio-offset-ms 0
```

Mặc định dùng `sample_script_1min.mp3`. Audio hiện tại dài 55,584s, nên cap 60 tạo output khoảng 55,584s; không chèn im lặng, không đảo audio hoặc lặp tiếng. Báo cáo phân biệt duration thật với chỉ số `normalized_wall_seconds_per_60_audio_seconds_extrapolation` (ngoại suy tuyến tính khi audio không dài đúng 60s). Muốn đo đúng 60s cần audio thực dài ít nhất 60s.

Đổi kịch bản bằng `--audio "duong_dan_audio_that.mp3"`, giữ nền và crop/mask đã duyệt. Mỗi job có output folder mới nên giữ lại output cũ. Nếu CMD mới, đặt lại `ECHO_BASE`, `LIP_SHIFT`, `LIP_MASK` trước khi chạy.

## 5. Đo cả chi phí tạo nền mới

Sau khi duyệt motion base speech và lip settings, có thể dùng một lệnh benchmark **không truyền base-video**:

```bat
test_vertical_ads.bat benchmark --profile A10 --mouth-mode speech --duration 15 --bbox-shift %LIP_SHIFT% --parsing-mode %LIP_MASK% --audio-offset-ms 0
```

Lệnh sinh Echo 5,16s mới trong thư mục job riêng, rồi hai lượt MuseTalk+export. Không lấy output cache Echo để giả số đo. `echo_generation_wall_seconds` đo cả chuẩn bị input, model load, conditioning, denoise, encode và xác minh. Timers/GPU peak của worker được chép từ Echo manifest; không lấy timer denoise làm tổng render và không đo thêm nhiệt độ/RAM hệ thống.

Nhân vật khác dùng `--image "duong_dan_anh_that.png"` khi tạo nền. Mỗi ảnh cần nền/cache riêng một lần; những kịch bản tiếp theo của nhân vật đó dùng lại nền và lip settings đã duyệt.

## Giới hạn và xử lý lỗi

Không thể kiểm chứng chất lượng/speed GPU mới trên máy Mac hiện tại. Test cục bộ chỉ xác nhận controller, waveform im lặng, cache isolation, mapping frame/codec/timestamp và export bằng FFmpeg. Miệng trung tính, A10/A10HQ, hai cấu hình mask và tốc độ Windows cần output thật để duyệt. Chế độ sinh nền cao hơn không bảo đảm nâng độ khớp âm-miệng của MuseTalk.

Nếu lỗi/Ctrl+C, log, report partial, intermediate và cache đã tạo được giữ lại. Không xuất báo cáo `complete` khi kiểm tra output thất bại. Offset ngoài bội số 40ms hoặc vượt ±160ms bị từ chối; không đổi FPS ngầm. Muốn xem log, mở đường dẫn `logs\vertical_ads.log` dưới job mà CMD vừa in.
