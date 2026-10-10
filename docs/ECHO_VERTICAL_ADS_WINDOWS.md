# Test ads dọc, khẩu hình và thời gian trên RTX 3060 Windows

Bộ này giữ EchoMimic V3 Flash + MuseTalk v1.5 đã chạy được. Khung cuối là 1080×1920, 9:16, 25 FPS, MP4 H.264/AAC. Với ảnh hiện tại 4:5, sinh nền ở 512×640 rồi dựng dọc sau lip-sync giúp giữ toàn bộ hai vai và giảm số pixel AI cần sinh. Phần ảnh nhân vật được scale đồng đều trên nền mờ từ chính video; không kéo giãn hoặc crop phần nhân vật. Lanczos tăng kích thước xuất, không tạo thêm chi tiết như model super-resolution.

TikTok khuyến nghị video dọc 9:16, ít nhất 540×960: [thông số chính thức](https://ads.tiktok.com/resources/help/article/tiktok-auction-in-feed-ads?lang=en-GB-8). Khổ xuất đáp ứng kích thước đó; bộ này chưa thêm phụ đề, sản phẩm, CTA hoặc đăng quảng cáo.

## Đánh giá chất lượng và tiêu chí phát hành

Mỗi output có `quality_assessment/<tên-video>.json`; riêng bước đo khẩu độ miệng sau khi ghép có artifact `quality_assessment/<tên-intermediate>_pause_mouth_qc.json`. `vertical_ad_report.json` cũng nhúng cùng trạng thái đánh giá. Các kiểm tra ffprobe/audio/frame và phép đo khẩu độ môi là **kiểm tra khách quan có phạm vi hẹp**. Kể cả khi chúng đều đạt, trường `certification_status` vẫn là `not_certified`: pipeline hiện không chấm độ khớp phoneme, độ tự nhiên/chuyển động liền mạch, độ giống video tham khảo hay khả năng tổng quát hóa.

Khi chạy render với `--pause-correction-region mouth-only`, controller kiểm tra import và khởi tạo detector 68 điểm trong đúng Python của MuseTalk **trước khi bắt đầu sinh Echo/MuseTalk** (`dry-run` chỉ kiểm tra cấu hình). Nếu detector không sẵn sàng, job dừng sớm và ghi `logs\mouth_qc_detector_preflight.log`; không chờ đến sau một lượt render dài mới phát hiện thiếu dependency. Chế độ `full-frame`, `pause-mouth-closure off` và workflow khác giữ nguyên hành vi.

Để phát hành cho nhiều nhân vật/ngôn ngữ, duyệt tối thiểu ma trận coverage riêng cho từng tập sản phẩm mục tiêu; không suy rộng kết quả từ một video hoặc một người:

| Chiều kiểm tra | Bộ mẫu phải có | Điều kiện duyệt |
| --- | --- | --- |
| Nhân vật/diện mạo | Mỗi danh tính được hỗ trợ, gồm khác biệt về tông da, hình dạng mặt, râu/tóc và phụ kiện nếu có | Miệng không méo/nhòe; identity giữ ổn định trong toàn clip |
| Ngôn ngữ/phát âm | Người nói bản ngữ cho từng ngôn ngữ quảng bá; mẫu âm vị, phụ âm môi, tốc độ và giọng khác nhau | Xem-nghe đồng bộ trên toàn câu, không chỉ trên nguyên âm hoặc một câu mẫu |
| Tư thế/chuyển động | Chính diện, góc quay dự kiến dùng, cử động đầu/vai, vùng miệng bị che nếu nằm trong phạm vi hỗ trợ | Không nhòe/nhảy ở môi; frame chuyển tiếp và chu kỳ lặp không giật hoặc đứng hình |
| Âm thanh/ngắt nghỉ | Mỗi voice/accent được hỗ trợ; câu nói, plosive, khoảng nghỉ ngắn/dài và nền âm thực tế | Miệng theo tiếng nói; đóng trong khoảng nghỉ; tiếng không bị lệch hoặc cắt |
| So với video tham khảo | Cùng ảnh/audio/khung hình test, chấm độc lập ở tốc độ bình thường và từng frame rủi ro | Người duyệt chấp nhận chuyển động, chi tiết mặt, màu và độ liền mạch; ghi lại lỗi theo từng mẫu |

Release chỉ được tuyên bố cho những tổ hợp nhân vật × ngôn ngữ × tư thế/âm thanh đã chạy và được duyệt. MuseTalk upstream mô tả hỗ trợ các ngôn ngữ ví dụ như Trung, Anh, Nhật nhưng cũng công khai giới hạn jitter do sinh từng frame và khả năng giữ chi tiết nhận dạng môi; vì vậy không thể coi một lần chạy đạt hình dạng môi lúc im lặng là chứng nhận tự nhiên hoặc hỗ trợ mọi ngôn ngữ. Xem [tài liệu MuseTalk chính thức](https://github.com/TMElyralab/MuseTalk#limitations).

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

Theo mặc định, sau inference pause correction khôi phục đúng frame Echo mà MuseTalk đã chọn tại thời điểm đó bằng chu kỳ `frame_list + frame_list[::-1]`. Chỉ làm khi cả frame output và frame nguồn tương ứng nằm trọn trong các khoảng im lặng đã xác minh. Nhờ vậy thân, đầu và nền giữ đúng chuyển động của timestamp trong chu kỳ gốc. Các pause không trùng thời điểm nguồn im lặng được giữ nguyên và ghi vào `uncovered_intervals`. Fade ngắn chỉ áp dụng bên trong những run khớp nguồn; audio AAC được stream-copy. Đây là correction toàn khung và vẫn là mặc định để giữ tương thích.

Có thêm chế độ **thử nghiệm** `mouth-only` để so A/B mà không thay toàn khung: dùng FaceParsing để đọc nhãn môi 11/12/13, kiểm tra donor môi khép bằng parser và landmark, căn theo hình học mặt/miệng, rồi chỉ ghép vùng môi. Nếu không donor nào đạt kiểm tra, helper ghi diagnostics rồi dừng trước khi chạy parser trên toàn bộ frame pause. Frame target hoặc donor không đạt ngưỡng sẽ được bỏ qua và ghi lý do. Core mới yêu cầu phủ đủ mọi frame pause trong phần video và QC khẩu độ trên video đã encode trước khi cho phép xuất HD; coverage `none` hoặc `partial` sẽ dừng job, giữ intermediate/report và không công bố output như đã sửa. Đây là kiểm tra hình học, không bảo đảm cảm quan hoàn hảo; cần xem video trên máy RTX 3060. Audio giữ nguyên qua stream-copy. Vì kết quả cuối là H.264 4:2:0, mép feather vẫn có thể khác màu nhẹ do nén/chroma subsampling.

Correction này không làm dịu đầu khi đang nói. Chế độ mặc định `full-frame` chỉ phủ pause khớp frame nguồn; phần còn lại có thể vẫn mấp máy và được ghi trong `uncovered_intervals`. Với `mouth-only`, coverage không đủ sẽ chặn xuất HD; đây là quality gate để tránh nhầm một video chưa sửa thành output đạt. Ngay cả khi phép đo aperture qua ngưỡng, cần xem video vì số đo không chứng nhận độ tự nhiên chủ quan.

Report `motion_audio_alignment` so SHA-256 audio Echo dùng để tạo cử chỉ với audio hiện tại. Khi mismatch hoặc không có manifest, auto bỏ qua pause correction; hãy tạo Echo speech base mới nếu cần cử chỉ bám audio. `--pause-mouth-closure off` tắt cả conditioning gate và correction sau render. Full-frame chỉ phủ pause khớp frame nguồn, nên phần còn lại có thể vẫn mấp máy; report phải được xem cùng `uncovered_intervals`. Whisper context, giới hạn 25 FPS và sai số model vẫn khiến khẩu hình lệch; hãy nghe/xem A/B trước khi chạy dài.

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

Để `--pause-mouth-closure auto` mặc định cho preview và render. Gate conditioning `auto` chạy trên audio hiện tại, kể cả khi base được tái sử dụng. Pause correction yêu cầu manifest Echo có mode `speech`, SHA-256 audio trùng file hiện tại và frame nguồn tại ping-pong timestamp cũng nằm trong khoảng im lặng. Report ghi các run khớp và thời lượng pause chưa thể khôi phục; các frame không khớp được giữ nguyên.

`force` đặt ngưỡng gate/correction xuống pause từ 0,16 giây. Nó bỏ qua cổng mode/hash giữa Echo và audio đầu ra, nhưng vẫn cần xác minh `source_audio` theo SHA trong manifest; chỉ các frame exact-mapped có source silence mới được khôi phục. `off` tắt gate conditioning lẫn correction frame sau render.

### Reprocess job đã render mà không chạy lại model

Nếu job đã có MuseTalk intermediate và các WAV trung gian, dùng script offline dưới đây. Script xác minh SHA-256 motion base, normalized output audio, Echo reference WAV và danh tính audio trong report trước khi ghi file; nó không chạy Echo hoặc MuseTalk. Nếu có `audio_unshifted_video_1.mp4`, script dùng file đó; nếu thiếu, nó ghép WAV unshifted vào MuseTalk intermediate trước khi sửa. Phải có motion base gốc đúng SHA để tái tạo ping-pong frame mapping. Script từ chối dùng `pause_closed_video_1.mp4` cũ làm donor vì file đó có thể chứa frame thay thế toàn khung từ policy trước.

```bat
python -u scripts\reprocess_pause_correction.py --job-dir "output\vertical_ads\job_20261010_125846_9dadea01" --motion-base "%ECHO_BASE%"
```

Kết quả mới được ghi trong đúng job folder, không ghi đè file cũ:

- `intermediate\pause_source_aligned_reprocessed_video_1.mp4`: intermediate 512×640 đã khôi phục các frame có ping-pong source silence khớp.
- `vertical_ad_1080x1920_pause_source_aligned_reprocessed.mp4`: output 9:16 1080×1920.
- `pause_reprocess_report.json`: xác minh hash, exact-source coverage, `uncovered_intervals`, export và thời gian.

Nếu tên job hoặc motion base khác, thay đường dẫn tương ứng. Lệnh chỉ reprocess được khi job cũ còn đủ intermediate, report, Echo reference WAV và motion base gốc đúng SHA.

### A/B tùy chọn: thử ghép riêng vùng môi khi pause

Chỉ chạy sau khi có một lần render/job hoàn chỉnh. Lệnh này không chạy Echo hoặc MuseTalk lip-sync lại; nó dùng Python và checkpoint FaceParsing đã cài cho MuseTalk, nạp parser để phân tích frame. Trong CMD đã vào thư mục dự án, đặt đúng job và motion base gốc. Đường dẫn bên dưới là đường dẫn trong job đã nêu ở trao đổi trước; nếu job của bạn trỏ tới base khác, sửa `ECHO_BASE`. Script xác minh SHA-256 với report và dừng nếu chọn nhầm file.

```bat
set "JOB=output\vertical_ads\job_20261010_125846_9dadea01"
set "ECHO_BASE=C:\Users\Admin\Downloads\video-creative-studio\video-creative-studio\output\echo_flash\a10_0682611f141d\motion_base.mp4"
dir "%JOB%\vertical_ad_report.json"
dir "%ECHO_BASE%"
```

Sau khi cả hai lệnh `dir` tìm thấy file, chạy:

```bat
python -u scripts\reprocess_pause_correction.py --job-dir "%JOB%" --motion-base "%ECHO_BASE%" --pause-correction-region mouth-only
```

Nếu tự dò không chọn đúng MuseTalk Python/checkout, thêm `--musetalk-dir "C:\Users\Admin\Downloads\video-creative-studio\video-creative-studio\musetalk" --musetalk-python "C:\Program Files\Python310\python.exe"` trỏ tới đúng môi trường đang dùng cho MuseTalk. Đọc report trước khi xem video:

- `pause_mouth_only_reprocess_report.json`: hash nguồn, mask coverage, số frame được sửa, donor được chọn, pause chưa sửa và lý do skip.
- `intermediate\pause_mouth_only_reprocessed_video_1.mp4`: native 512×640.
- `vertical_ad_1080x1920_pause_mouth_only_reprocessed.mp4`: bản xem 9:16.
- `logs\mouth_mask_extraction_reprocess.log`: log parser/helper.

So bản này với `vertical_ad_1080x1920.mp4` gốc của job. Chuyển động đầu/vai ngoài vùng môi phải tiếp tục chạy. Nếu coverage không đủ hoặc không có donor đạt kiểm tra, core mới ghi report thất bại và không xuất video final; không hạ ngưỡng bằng tay. Report và test hiện tại chỉ xác nhận hợp đồng dữ liệu/compositing trên synthetic clip; chưa xác nhận chất lượng hình ảnh hay thời gian trên RTX 3060. Giữ `--pause-correction-region` mặc định `full-frame` cho các lệnh `test_vertical_ads.bat` cho đến khi duyệt A/B.

### Preview donor cùng pose từ full render

Trước khi tạo lại video dài, có thể thử speech-pose-bank trên một preview ngắn. Chế độ này dùng toàn bộ video MuseTalk đã có làm donor bank, nhưng chỉ xuất prefix vài giây để kiểm tra. Candidate donor phải là frame không rơi vào pause của audio unshifted và có đúng source-frame index theo chu kỳ ping-pong của motion base. Lệnh không chạy lại Echo hoặc sinh lip-sync MuseTalk; nó vẫn chạy FaceParsing và face-landmark inference cục bộ để chọn donor và QC. Mask thay các nhãn môi 11/12/13; căn chỉnh chỉ tịnh tiến, không co giãn dọc/ngang. Mọi donor vẫn phải qua parser, landmark closure, geometry, coverage và QC trên video đã mã hóa.

Trong CMD tại thư mục dự án, dùng job đã render:

```bat
set "JOB=output\vertical_ads\job_20261010_224236_c886c7c9"
set "ECHO_BASE=output\echo_flash\a10_0682611f141d\motion_base.mp4"
dir "%JOB%\intermediate\audio_unshifted_16k_mono.wav"
dir "%JOB%\intermediate\musetalk_video_1.mp4"
dir "%JOB%\vertical_ad_report.json"
dir "%ECHO_BASE%"
python -u scripts\reprocess_pause_correction.py --job-dir "%JOB%" --motion-base "%ECHO_BASE%" --pause-correction-region mouth-only --mouth-donor-mode speech-pose-bank --preview-seconds 10 --output-label speechpose_preview
```

Script tự dùng `audio_unshifted_video_1.mp4` nếu có; nếu không, nó lấy `musetalk_video_1.mp4` và ghép audio unshifted đã xác minh trước khi xây donor bank. Không cần phải có riêng file `audio_unshifted_video_1.mp4`. Output dự kiến là `%JOB%\vertical_ad_1080x1920_pause_mouth_only_speechpose_preview_reprocessed.mp4` cùng report `%JOB%\pause_mouth_only_speechpose_preview_reprocess_report.json`. Preview chỉ dài tối đa 10 giây; audio là prefix không đổi nội dung của AAC nguồn. Nếu bất kỳ pause frame nào không có donor cùng pose đủ kín/đạt geometry, hoặc final-frame QC không đạt, lệnh dừng và không promote HD output. Đọc report trước khi mở video. Nếu báo cáo không tạo final, đừng nới gate: nó có nghĩa là chính render hiện tại không có đủ donor cùng pose đạt chuẩn.

### Pass cũ: donor MuseTalk im lặng

Nếu report cũ ghi `no_confident_mouth_donor_alignment`, `valid_closed_donor_frames=0` và `corrected_pause_frame_count=0`, video HD cũ thực chất chưa được sửa môi nghỉ. Không chạy lại toàn bộ 55 giây. Dùng chế độ `silence-conditioned` để tạo một donor pass ngắn từ chính motion base, sau đó thử ghép trên intermediate speech đã có; avatar cache trong job được tái sử dụng. Lượt donor vẫn có thể không đạt nếu MuseTalk không khép môi đủ ở frame tương ứng; khi đó report sẽ nêu lý do và không tạo final.

Với job đang được kiểm tra:

```bat
set "JOB=output\vertical_ads\job_20261010_224236_c886c7c9"
set "ECHO_BASE=output\echo_flash\a10_0682611f141d\motion_base.mp4"
dir "%JOB%\vertical_ad_report.json"
dir "%JOB%\intermediate\audio_unshifted_video_1.mp4"
dir "%JOB%\intermediate\audio_unshifted_16k_mono.wav"
dir "%JOB%\intermediate\echo_reference_audio_16k_mono.wav"
dir "%ECHO_BASE%"
python -u scripts\reprocess_pause_correction.py --job-dir "%JOB%" --motion-base "%ECHO_BASE%" --pause-correction-region mouth-only --mouth-donor-mode silence-conditioned --output-label silence_v1
```

Lệnh này không chạy lại Echo hay MuseTalk cho toàn bộ lời thoại; chỉ tạo một pass MuseTalk im lặng trên motion base 5,16 giây, rồi dùng cache và intermediate hiện có. Đọc `%JOB%\pause_mouth_only_silence_v1_reprocess_report.json`. Chỉ khi report báo coverage `full` và `output_mouth_closure_qc.status` là `passed` mới mở `%JOB%\vertical_ad_1080x1920_pause_mouth_only_silence_v1_reprocessed.mp4`. Nếu lệnh dừng, không có final là đúng: gửi report thất bại để xem frame donor nào còn mở hoặc lệch geometry.

### Dùng lại donor MuseTalk đã render nhưng bị thiếu một frame cuối

Nếu lượt `silence-conditioned` trước đã xử lý đủ **129 PNG frames** nhưng file MP4 chỉ giải mã được 128 frame và lệnh dừng ở bước validation, không chạy MuseTalk lại. Dùng lại cùng bộ MP4/WAV/log theo nhãn cũ, đồng thời chọn nhãn output mới. Bản core đã sửa sẽ xác minh cache manifest (base SHA), MuseTalk render manifest (đúng donor MP4 và silence WAV), WAV PCM16 16 kHz digital-zero đúng 129-frame duration, log báo đủ 129 PNG, cùng PTS donor bắt đầu tại 0 và tăng liên tiếp mỗi 1/25 giây. Chỉ trường hợp thiếu đúng frame cuối cùng mới được chấp nhận; frame được map sang index 128 sẽ giữ nguyên và ghi lý do `exact_mapped_donor_frame_missing_trailing_truncation`. Không đệm, dịch, nội suy hoặc chọn donor thay thế. Mismatch nào khác sẽ dừng trước inference/composite.

Trong CMD tại thư mục dự án, dùng chính job, motion base và donor label đã chạy. Với job trong ví dụ và donor `sameframe_v1`:

```bat
set "JOB=output\vertical_ads\job_20261010_125846_9dadea01_mouth_quality_retry"
set "ECHO_BASE=output\echo_flash\a10_0682611f141d\motion_base.mp4"
set "DONOR_LABEL=sameframe_v1"
set "OUTPUT_LABEL=sameframe_retry_2"
dir "%JOB%\intermediate\pause_silence_conditioned_musetalk_donor_%DONOR_LABEL%.mp4"
dir "%JOB%\intermediate\pause_silence_conditioning_%DONOR_LABEL%_16k_mono.wav"
dir "%JOB%\logs\pause_silence_conditioned_musetalk_donor_%DONOR_LABEL%.log"
dir "%JOB%\vertical_ad_report.json"
dir "%ECHO_BASE%"
```

Mỗi lệnh `dir` phải tìm đúng một file. Nếu base nằm ở đường dẫn khác, thay `ECHO_BASE` bằng đường dẫn gốc của máy bạn. Sau đó chạy:

```bat
python -u scripts\reprocess_pause_correction.py --job-dir "%JOB%" --motion-base "%ECHO_BASE%" --pause-correction-region mouth-only --mouth-donor-mode silence-conditioned --reuse-silence-donor-label "%DONOR_LABEL%" --output-label "%OUTPUT_LABEL%"
```

Lệnh này tái sử dụng MP4/WAV/log đã có, không chạy lại Echo hoặc MuseTalk inference. Nó ghi intermediate, report và final với nhãn `sameframe_retry_2`, giữ nguyên donor cũ. Xem báo cáo và mở video bằng:

```bat
type "%JOB%\pause_mouth_only_%OUTPUT_LABEL%_reprocess_report.json"
start "" "%JOB%\vertical_ad_1080x1920_pause_mouth_only_%OUTPUT_LABEL%_reprocessed.mp4"
```

Trong report, xác nhận `frame_timeline_validation.status` là `verified_trailing_frame_truncation`, `models_rerun` là `false`, và xem `uncorrected_output_pause_frame_indices`/`frame_diagnostics` để biết pause nào bị bỏ qua do frame 128 không có trong donor. Nếu lệnh báo thiếu manifest, WAV hoặc log, hoặc timestamp/base SHA không khớp, dừng và gửi nguyên thông báo lỗi; không đổi tên/tạo file giả để vượt kiểm tra. Khi gõ đường dẫn video vào CMD, dùng `start "" "đường_dẫn.mp4"` để mở; không chạy đường dẫn như một lệnh.

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
