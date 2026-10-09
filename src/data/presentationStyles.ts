import { PresentationStyle } from "../types";

export const PRESENTATION_STYLES: PresentationStyle[] = [
  {
    id: "news_anchor",
    number: 1,
    name: "News Anchor",
    vietnameseTitle: "Bản tin chuyên nghiệp",
    tagline: "Trường quay thời sự xanh dương, màn hình LED, đĩnh đạc và uy tín",
    background: "Trường quay thời sự xanh dương, màn hình LED",
    backgroundTitle: "Trường quay Thời sự Quốc gia (Blue LED Studio)",
    backgroundDescription: "Màn hình LED cong xanh dương sapphire 180°, dải tin tức chạy chân, ánh sáng key-light đĩnh đạc chuẩn truyền hình trung ương.",
    backgroundTheme: "from-blue-950 via-slate-900 to-indigo-950 border-blue-600/40",
    backgroundTags: ["Thời sự", "LED Studio", "Chính luận", "Xanh Sapphire"],
    scriptGuideline: "Kịch bản súc tích, khách quan; thông tin cô đọng, rõ nguồn, cấu trúc kim tự tháp ngược",
    sampleScript:
      "Xin chào quý vị và các bạn. Đây là bản tin công nghệ cập nhật những bước tiến quan trọng nhất trong ngày. Hôm nay, trung tâm nghiên cứu trí tuệ nhân tạo chính thức công bố giải pháp số hóa phong thái thuyết trình của người dẫn số với độ chính xác và tính biểu cảm vượt trội.",
    sampleScriptEn:
      "Good evening. Welcome to today's prime tech briefing. Artificial intelligence researchers have officially released a groundbreaking talking-avatar synthesis framework, delivering ultra-realistic lip synchronization and lifelike non-verbal expressions for digital broadcasters.",
    voiceGuideline: "Rõ ràng, tự tin, tốc độ vừa phải, ngữ điệu chuẩn mực phát thanh",
    recommendedVoice: "vieneu_Thái Duy Bình",
    recommendedMultiplier: 0.40,
    recommendedAspectRatios: ["16:9", "9:16"],
    defaultAspectRatio: "16:9",
    kinematicsGuideline: "Đầu và vai cử động tối thiểu, duy trì ánh nhìn tập trung vào camera",
    drivingPolicy: "hold",
    torsoMotion: false,
    useCase: "Tin tức, thời sự, cập nhật thông tin",
    badgeColor: "bg-blue-950 text-blue-300 border-blue-700/50",
    geminiPrompt: `Bạn là biên tập viên thời sự truyền hình quốc gia kỳ cựu. Hãy viết lại và tối ưu kịch bản nói sau thành một bản tin thời sự tiếng Việt chuẩn mực:
1. Phong cách: Khách quan, trung thực, trang trọng, uy tín cao.
2. Cấu trúc kim tự tháp ngược: Đưa sự kiện quan trọng nhất và thông điệp then chốt lên 2 câu đầu tiên; theo sau là số liệu, bối cảnh và kết luận.
3. Câu cú: Ngắn gọn, gãy gọn, dứt khoát, loại bỏ hoàn toàn các từ cảm thán, văn nói suồng sã hoặc liên từ rườm rà.
4. Mở đầu chuẩn mực: 'Xin kính chào quý vị và các bạn...', kết thúc súc tích.
5. Chỉ trả về duy nhất nội dung kịch bản lời thoại đã tối ưu, không kèm lời bình hay giải thích thừa.`,
  },
  {
    id: "educational_explainer",
    number: 2,
    name: "Educational Explainer",
    vietnameseTitle: "Giảng giải kiến thức",
    tagline: "Phòng học hoặc studio sáng, mạch lạc, dễ hiểu",
    background: "Phòng học hoặc studio sáng, bảng tương tác",
    backgroundTitle: "Studio Giảng dạy Hiện đại (Nordic Tech Lab)",
    backgroundDescription: "Không gian studio ánh sáng tự nhiên Scandinavia, bảng tương tác kính thông minh, tone màu be và xanh bạc hà kích thích tư duy.",
    backgroundTheme: "from-amber-950/60 via-slate-900 to-emerald-950/60 border-amber-600/40",
    backgroundTags: ["Giáo dục", "Studio Sáng", "Bảng tương tác", "Tư duy"],
    scriptGuideline: "Chia thành từng ý dễ hiểu, thêm câu chuyển tiếp và khoảng nghỉ giữa các ý",
    sampleScript:
      "Chào mừng các bạn đến với bài học hôm nay. Để hiểu cách một mô hình AI video vận hành, chúng ta chỉ cần nắm rõ ba giai đoạn chính: thứ nhất là giải mã âm vị giọng nói, thứ hai là tạo chuyển động đầu tự nhiên, và thứ ba là đồng bộ khẩu hình chính xác từng mili-giây.",
    sampleScriptEn:
      "Welcome back to today's masterclass. To understand how modern neural video generation works, we only need to grasp three core stages: first, phoneme-level audio decomposition; second, natural head kinematics prediction; and third, sub-millisecond audio-to-lip blending.",
    voiceGuideline: "Thân thiện, mạch lạc, chuyển động đầu nhẹ khi nhấn ý quan trọng",
    recommendedVoice: "vieneu_Ban Mai",
    recommendedMultiplier: 0.50,
    recommendedAspectRatios: ["16:9"],
    defaultAspectRatio: "16:9",
    kinematicsGuideline: "Gật đầu nhẹ nhàng theo nhịp giải thích, chuyển động đầu hỗ trợ việc nhấn mạnh ý",
    drivingPolicy: "hold",
    torsoMotion: true,
    useCase: "Giáo dục, hướng dẫn, giải thích công nghệ",
    badgeColor: "bg-amber-950 text-amber-300 border-amber-700/50",
    geminiPrompt: `Bạn là giảng viên đại học và chuyên gia truyền đạt kiến thức công nghệ xuất sắc. Hãy tối ưu kịch bản nói sau thành một bài giảng giải thích cực kỳ mạch lạc và lôi cuốn:
1. Bố cục sư phạm: Chia nội dung thành 3 ý cốt lõi (Thứ nhất..., Thứ hai..., và điều quan trọng nhất là...).
2. Đơn giản hóa: Dùng hình ảnh ẩn dụ, so sánh đời thường để người nghe không chuyên cũng hiểu ngay nguyên lý phức tạp.
3. Nhịp điệu & Chuyển ý: Thêm các câu nối mềm mại, tự nhiên ('Các bạn hãy hình dung...', 'Chính vì thế...').
4. Giọng điệu: Thân thiện, kiên nhẫn, gần gũi, khích lệ tinh thần người học.
5. Chỉ trả về duy nhất nội dung kịch bản lời thoại đã tối ưu, không kèm lời bình hay giải thích thừa.`,
  },
  {
    id: "cinematic_storytelling",
    number: 3,
    name: "Cinematic Storytelling",
    vietnameseTitle: "Kể chuyện cảm xúc",
    tagline: "Điện ảnh, ánh sáng ấm, chiều sâu và giàu cảm xúc",
    background: "Điện ảnh, ánh sáng ấm và chiều sâu không gian",
    backgroundTitle: "Không gian Điện ảnh Nghệ thuật (Cinematic Bokeh)",
    backgroundDescription: "Ánh sáng vàng hổ phách tương phản mềm mại, phông nền mờ ảo bokeh điện ảnh, tạo chiều sâu thị giác và không khí tự sự lắng đọng.",
    backgroundTheme: "from-purple-950 via-slate-900 to-amber-950/80 border-purple-600/40",
    backgroundTags: ["Điện ảnh", "Bokeh ấm", "Nghệ thuật", "Chiều sâu"],
    scriptGuideline: "Có mở đầu thu hút, cao trào và kết thúc; văn phong giàu hình tượng",
    sampleScript:
      "Trong một đêm mùa đông tĩnh lặng, khi những ánh đèn thành phố dần chìm vào giấc ngủ, một ý tưởng đột phá đã ra đời. Không ai nghĩ rằng chỉ từ một dòng mã giản đơn, cả một thế giới sáng tạo số đã được khai sinh và thay đổi mãi mãi cách con người kể câu chuyện của mình.",
    sampleScriptEn:
      "In the dead of a quiet winter night, as the city lights flickered into slumber, a quiet revelation was born... No one could have predicted that a single line of elegant code would ignite a digital renaissance and reshape how we share human stories.",
    voiceGuideline: "Linh hoạt, có những khoảng dừng giàu cảm xúc; ngữ điệu trầm bổng",
    recommendedVoice: "vieneu_Bích Ngọc",
    recommendedMultiplier: 0.50,
    recommendedAspectRatios: ["9:16", "16:9"],
    defaultAspectRatio: "9:16",
    kinematicsGuideline: "Ánh mắt và biểu cảm thay đổi nhẹ theo nội dung, cử động chậm rãi có chiều sâu",
    drivingPolicy: "hold",
    torsoMotion: true,
    useCase: "Truyện ngắn, câu chuyện đời sống, lịch sử",
    badgeColor: "bg-purple-950 text-purple-300 border-purple-700/50",
    geminiPrompt: `Bạn là nhà biên kịch điện ảnh bậc thầy và người kể chuyện truyền cảm. Hãy chuyển hóa kịch bản nói sau thành một câu chuyện điện ảnh chạm tới trái tim người nghe:
1. Cấu trúc 3 hồi: Khởi đầu gợi mở tò mò -> Phát triển cao trào cảm xúc -> Kết thúc sâu lắng đọng lại dư ba.
2. Ngôn ngữ hình ảnh: Sử dụng từ ngữ giàu tính gợi hình, gợi cảm, khơi gợi cả xúc giác và thị giác.
3. Nhịp thở nghệ thuật: Chèn các dấu chấm lửng (...) tại những khoảng lặng đắt giá để giọng đọc có thời gian lắng lại.
4. Ngữ điệu: Trầm bổng, tâm sự, giàu tính nhạc và sự đồng cảm sâu sắc.
5. Chỉ trả về duy nhất nội dung kịch bản lời thoại đã tối ưu, không kèm lời bình hay giải thích thừa.`,
  },
  {
    id: "documentary_narrator",
    number: 4,
    name: "Documentary Narrator",
    vietnameseTitle: "Thuyết minh tài liệu",
    tagline: "Lịch sử, tư liệu lưu trữ, giọng kể trầm ổn có chủ đích",
    background: "Lịch sử, lưu trữ hoặc studio tài liệu cổ điển",
    backgroundTitle: "Studio Tư liệu Lịch sử (Archive Vault Studio)",
    backgroundDescription: "Kệ sách gỗ sồi cổ điển, bản đồ cổ và hiện vật lưu trữ, ánh sáng vàng trầm ấm chiếu nghiêng tạo cảm giác tôn nghiêm thời gian.",
    backgroundTheme: "from-stone-950 via-slate-900 to-amber-950/70 border-stone-600/40",
    backgroundTags: ["Tài liệu", "Lưu trữ", "Lịch sử", "Trang nghiêm"],
    scriptGuideline: "Giàu thông tin, chuyển ý chậm và có chiều sâu thời gian",
    sampleScript:
      "Hàng triệu năm trước, những dấu chân đầu tiên của nền văn minh đã bắt đầu từ những thung lũng nguyên sinh. Qua từng thời kỳ thăng trầm của lịch sử, con người luôn khao khát ghi lại hình ảnh và tiếng nói của chính mình để truyền lại cho các thế hệ mai sau.",
    sampleScriptEn:
      "Across centuries of human innovation, history remembers those rare moments when imagination bridged into reality. The archival evidence reveals a continuous pursuit of lifelike digital presence, echoing the eternal human desire to communicate beyond physical limits.",
    voiceGuideline: "Giọng kể trầm ổn, nhịp có chủ đích, tôn trọng sự tĩnh tại",
    recommendedVoice: "vieneu_Ngọc Tuấn",
    recommendedMultiplier: 0.35,
    recommendedAspectRatios: ["16:9"],
    defaultAspectRatio: "16:9",
    kinematicsGuideline: "Hạn chế chuyển động cơ thể không cần thiết, tư thế điềm tĩnh uy nghiêm",
    drivingPolicy: "hold",
    torsoMotion: false,
    useCase: "Lịch sử, khoa học, khám phá, kiến thức",
    badgeColor: "bg-stone-950 text-stone-300 border-stone-700/50",
    geminiPrompt: `Bạn là người thuyết minh phim tài liệu khoa học và lịch sử kỳ cựu của các đài truyền hình danh tiếng (như Discovery, BBC). Hãy tối ưu kịch bản nói sau thành lời bình tài liệu đắt giá:
1. Phong thái: Trầm ổn, tôn nghiêm, chiêm nghiệm, mang sức nặng của thời gian và tri thức.
2. Kết cấu thời gian: Dẫn dắt người nghe qua dòng chảy lịch sử, gắn kết hiện tượng với quy luật nhân quả sâu xa.
3. Từ ngữ: Chọn lọc, khúc chiết, giàu tính biểu tượng, không dùng từ ngữ vội vã hay nông cạn.
4. Khoảng lặng: Câu văn có trường đoạn, ngắt nhịp đĩnh đạc để người nghe suy ngẫm.
5. Chỉ trả về duy nhất nội dung kịch bản lời thoại đã tối ưu, không kèm lời bình hay giải thích thừa.`,
  },
  {
    id: "podcast_host",
    number: 5,
    name: "Podcast Host",
    vietnameseTitle: "Trò chuyện tự nhiên",
    tagline: "Phòng podcast ấm cúng, gần gũi, câu ngắn như đang trò chuyện trực tiếp",
    background: "Phòng podcast ấm cúng, micro chuyên nghiệp, đèn neon dịu",
    backgroundTitle: "Phòng Thu Podcast Acoustic (Neon Lounge Studio)",
    backgroundDescription: "Tường ốp gỗ tiêu âm hiện đại, micro phòng thu Shure SM7B, ánh đèn neon màu hổ phách dịu nhẹ tạo bầu không khí tâm tình chân thật.",
    backgroundTheme: "from-teal-950 via-slate-900 to-slate-950 border-teal-600/40",
    backgroundTags: ["Podcast", "Micro Studio", "Gỗ tiêu âm", "Ấm cúng"],
    scriptGuideline: "Văn nói tự nhiên, câu ngắn, ít thuật ngữ cứng nhắc, xưng hô gần gũi",
    sampleScript:
      "Thực ra lúc mới bắt đầu, mình cũng từng bối rối không biết nên tiếp cận công nghệ này ra sao. Nhưng khi bạn ngồi lại và tự tay trải nghiệm quy trình tạo một video hoàn chỉnh từ một bức ảnh tĩnh, bạn sẽ nhận ra mọi thứ thú vị hơn rất nhiều so với những gì chúng ta tưởng tượng.",
    sampleScriptEn:
      "Hey everyone, welcome back to the studio! Today I want to dive into something that honestly blew my mind when I first tried it. Imagine taking a single still portrait and turning it into a fluent, expressive video in less than a minute. What do you think? Let's break it down.",
    voiceGuideline: "Thoải mái, khoảng nghỉ giống hội thoại đời thường",
    recommendedVoice: "vieneu_Tưởng Vy",
    recommendedMultiplier: 0.58,
    recommendedAspectRatios: ["16:9", "9:16"],
    defaultAspectRatio: "16:9",
    kinematicsGuideline: "Ánh mắt đôi lúc thay đổi tự nhiên, gật gù thân mật như trò chuyện trước mặt bạn bè",
    drivingPolicy: "hold",
    torsoMotion: true,
    useCase: "Podcast, chia sẻ, bình luận, tâm sự",
    badgeColor: "bg-teal-950 text-teal-300 border-teal-700/50",
    geminiPrompt: `Bạn là host của một kênh podcast trò chuyện triệu lượt nghe. Hãy viết lại kịch bản nói sau thành một đoạn chia sẻ podcast tự nhiên, gần gũi như hai người bạn thân đang ngồi uống trà:
1. 100% Văn nói tự nhiên: Dùng câu ngắn, từ ngữ đời thường, xưng hô gần gũi ('mình', 'bạn', 'các bạn').
2. Trải nghiệm chân thật: Thêm những bộc bạch cảm xúc, sự do dự tự nhiên ('Thực lòng mà nói...', 'Bạn có bao giờ tự hỏi...?').
3. Nhịp điệu hội thoại: Tự do, không gò ép, có câu hỏi mở để người nghe cảm thấy như đang được đối thoại trực tiếp.
4. Tuyệt đối tránh: Văn phong báo cáo khô cứng, khẩu hiệu sáo rỗng hoặc thuật ngữ mang tính giảng dạy đạo lý.
5. Chỉ trả về duy nhất nội dung kịch bản lời thoại đã tối ưu, không kèm lời bình hay giải thích thừa.`,
  },
  {
    id: "product_showcase",
    number: 6,
    name: "Product Showcase",
    vietnameseTitle: "Giới thiệu sản phẩm",
    tagline: "Showroom hiện đại, tập trung lợi ích nổi bật và kêu gọi hành động",
    background: "Showroom hoặc studio tối giản, bối cảnh công nghệ cao",
    backgroundTitle: "Showroom Công nghệ Tối giản (Minimalist High-Tech)",
    backgroundDescription: "Không gian trưng bày tối giản bê tông xám thanh lịch, ánh sáng diffuse bao phủ, bục trưng bày sản phẩm chuẩn flagship store toàn cầu.",
    backgroundTheme: "from-cyan-950 via-slate-900 to-blue-950 border-cyan-600/40",
    backgroundTags: ["Showroom", "Flagship", "Công nghệ cao", "Tối giản"],
    scriptGuideline: "Tập trung vào vấn đề, lợi ích nổi bật và lời kêu gọi hành động (CTA)",
    sampleScript:
      "Bạn mất hàng giờ mỗi ngày để quay và dựng video? Hãy khám phá Video Creative Studio: giải pháp tự động hóa biến văn bản thành video người dẫn 1080p chỉ trong vài phút. Trải nghiệm ngay hôm nay để nâng tầm tốc độ sản xuất nội dung của bạn lên một đẳng cấp hoàn toàn mới!",
    sampleScriptEn:
      "Are you still spending hours editing talking-head videos? Here is the breakthrough solution you have been waiting for. Meet Video Creative Studio: generate studio-grade AI presentations with real-time lip-sync in just three clicks. Supercharge your content workflow today!",
    voiceGuideline: "Tự tin, tốc độ hơi nhanh; biểu cảm tích cực nhưng không khoa trương",
    recommendedVoice: "vieneu_Đăng Quân",
    recommendedMultiplier: 0.55,
    recommendedAspectRatios: ["9:16", "16:9"],
    defaultAspectRatio: "9:16",
    kinematicsGuideline: "Nét mặt sáng, ánh mắt tự tin, đầu chuyển động dứt khoát theo từng luận điểm",
    drivingPolicy: "hold",
    torsoMotion: true,
    useCase: "Marketing, quảng cáo, giới thiệu ứng dụng",
    badgeColor: "bg-cyan-950 text-cyan-300 border-cyan-700/50",
    geminiPrompt: `Bạn là Giám đốc Marketing và chuyên gia giới thiệu sản phẩm công nghệ cao cấp. Hãy tối ưu kịch bản nói sau thành bài pitching bán hàng sắc bén:
1. Công thức PAS/AIDA:
   - Hook vấn đề: Đi thẳng vào nỗi đau hoặc sự lãng phí thời gian lớn nhất của khách hàng.
   - Giải pháp vượt trội: Trình bày giải pháp độc đáo mà sản phẩm mang lại.
   - 2-3 Lợi ích định lượng: Nhấn mạnh giá trị thực tế (tiết kiệm thời gian, nhân đôi hiệu suất, chuẩn 1080p).
   - Kêu gọi hành động (CTA): Lời kêu gọi hành động dứt khoát, thuyết phục và khó cưỡng.
2. Ngữ điệu: Tự tin, tràn đầy năng lượng, dứt điểm từng câu chữ.
3. Chỉ trả về duy nhất nội dung kịch bản lời thoại đã tối ưu, không kèm lời bình hay giải thích thừa.`,
  },
  {
    id: "motivational_speaker",
    number: 7,
    name: "Motivational Speaker",
    vietnameseTitle: "Truyền cảm hứng",
    tagline: "Sân khấu ánh sáng ấm, giàu nhịp điệu, truyền lửa và năng lượng",
    background: "Sân khấu ánh sáng ấm hoặc không gian mạnh mẽ, spotlight",
    backgroundTitle: "Đại Sân khấu Diễn thuyết (Grand Summit Stage)",
    backgroundDescription: "Sân khấu hội nghị nghìn người với luồng spotlight vàng kim hội tụ, hậu cảnh mái vòm kiến trúc hoành tráng, tạo xung lực truyền lửa mãnh liệt.",
    backgroundTheme: "from-orange-950 via-slate-900 to-amber-950 border-orange-600/40",
    backgroundTags: ["Sân khấu", "Spotlight", "Hội nghị", "Truyền lửa"],
    scriptGuideline: "Giàu nhịp điệu, có câu ngắn để nhấn ý chính, thúc đẩy hành động",
    sampleScript:
      "Đừng chờ đợi cho đến khi mọi điều kiện trở nên hoàn hảo. Cơ hội tốt nhất chính là ngay giây phút này. Khi bạn dám bắt đầu và kiên trì hành động mỗi ngày, bạn không chỉ chinh phục mục tiêu, mà còn kiến tạo nên phiên bản mạnh mẽ nhất của chính mình!",
    sampleScriptEn:
      "Stop waiting for the perfect moment. The greatest opportunity to redefine your trajectory is right here, right now! Champions do not hesitate when the landscape shifts; they step up and execute. Take ownership and build your future today!",
    voiceGuideline: "Truyền năng lượng, nhấn trọng tâm, âm vực vang và dứt khoát",
    recommendedVoice: "vieneu_Alexander Cường",
    recommendedMultiplier: 0.65,
    recommendedAspectRatios: ["9:16"],
    defaultAspectRatio: "9:16",
    kinematicsGuideline: "Chuyển động đầu rõ hơn nhưng không lắc liên tục, biểu cảm quyết đoán",
    drivingPolicy: "hold",
    torsoMotion: true,
    useCase: "Phát triển bản thân, thông điệp tích cực",
    badgeColor: "bg-orange-950 text-orange-300 border-orange-700/50",
    geminiPrompt: `Bạn là diễn giả truyền cảm hứng hàng đầu thế giới (phong cách Tony Robbins, Les Brown). Hãy viết lại kịch bản nói sau thành bài phát biểu truyền lửa rực lửa:
1. Nhịp điệu dồn dập: Sử dụng điệp từ điệp ngữ tạo xung lực tăng tiến ('Hãy dám...', 'Chính giây phút này...', 'Không phải ngày mai, mà là ngay bây giờ!').
2. Câu từ ngắn & mạnh: Cắt bỏ các câu phụ dài dòng, dùng mệnh đề khẳng định dứt khoát như lời tuyên thệ.
3. Đánh thức nội lực: Chạm thẳng vào khát vọng bứt phá, phá tan sự tự ti và trì hoãn của người nghe.
4. Năng lượng: Mạnh mẽ, vang dội, bùng cháy quyết tâm hành động ngay lập tức.
5. Chỉ trả về duy nhất nội dung kịch bản lời thoại đã tối ưu, không kèm lời bình hay giải thích thừa.`,
  },
  {
    id: "corporate_briefing",
    number: 8,
    name: "Corporate Briefing",
    vietnameseTitle: "Báo cáo doanh nghiệp",
    tagline: "Văn phòng hiện đại, phòng họp điều hành, ưu tiên số liệu và kết luận",
    background: "Văn phòng hiện đại hoặc phòng họp điều hành cấp cao",
    backgroundTitle: "Phòng Họp Điều hành Cấp cao (Boardroom Skyline)",
    backgroundDescription: "Vách kính cách âm nhìn ra toàn cảnh đường chân trời thành phố hiện đại, bàn hội nghị gỗ mun cao cấp, chuẩn mực phong thái quản trị tập đoàn.",
    backgroundTheme: "from-indigo-950 via-slate-900 to-slate-950 border-indigo-600/40",
    backgroundTags: ["Boardroom", "Skyline", "Quản trị", "Chuyên nghiệp"],
    scriptGuideline: "Ngắn gọn, có cấu trúc, ưu tiên số liệu, tiến độ và kết luận thực thi",
    sampleScript:
      "Kính thưa ban lãnh đạo và các đồng nghiệp. Trong quý vừa qua, hiệu suất vận hành hệ thống đã tăng trưởng ba mươi lăm phần trăm, trong khi chi phí sản xuất giảm thiểu đáng kể. Chúng tôi xin tóm tắt ba chỉ số trọng yếu và kế hoạch triển khai cho giai đoạn tiếp theo như sau.",
    sampleScriptEn:
      "Good morning, executive committee. Over the past quarter, our operational throughput has increased by thirty-five percent, while production turnaround dropped substantially. Here is the concise summary of three core KPI milestones and the upcoming strategic roadmap.",
    voiceGuideline: "Trang trọng, chính xác, nhịp đều; biểu cảm tiết chế, tập trung sự tin cậy",
    recommendedVoice: "vi-VN-NamMinhNeural",
    recommendedMultiplier: 0.42,
    recommendedAspectRatios: ["16:9"],
    defaultAspectRatio: "16:9",
    kinematicsGuideline: "Biểu cảm tiết chế, cử động đầu chuẩn mực tạo sự đáng tin cậy tối đa",
    drivingPolicy: "hold",
    torsoMotion: false,
    useCase: "Báo cáo, thông báo, đào tạo nội bộ",
    badgeColor: "bg-indigo-950 text-indigo-300 border-indigo-700/50",
    geminiPrompt: `Bạn là Giám đốc Chiến lược báo cáo trước Hội đồng Quản trị cấp cao. Hãy viết lại kịch bản nói sau theo đúng định dạng Executive Briefing:
1. Bố cục thực thi:
   - Thông điệp tóm tắt điều hành (Executive Summary).
   - Các chỉ số hiệu suất & tăng trưởng định lượng (Metrics & KPIs).
   - Kế hoạch hành động và kết luận chiến lược (Next Steps).
2. Ngôn từ quản trị: Trang trọng, chính xác, gãy gọn, không cảm tính, không lan man.
3. Độ tin cậy: Nhấn mạnh vào kết quả thực thi và tính bền vững của tổ chức.
4. Chỉ trả về duy nhất nội dung kịch bản lời thoại đã tối ưu, không kèm lời bình hay giải thích thừa.`,
  },
  {
    id: "social_creator",
    number: 9,
    name: "Social Creator",
    vietnameseTitle: "Video ngắn năng động",
    tagline: "Studio trẻ trung, hook ngay đầu video, giàu năng lượng cho Reels/TikTok",
    background: "Studio trẻ trung với màu sắc nổi bật, đèn RGB hiện đại",
    backgroundTitle: "Studio Sáng tạo RGB (Cyberpunk Creator Lab)",
    backgroundDescription: "Dải đèn LED RGB chuyển màu động, background phong cách trẻ trung năng động của Gen Z, tối ưu hóa thị giác cho khung hình dọc 9:16.",
    backgroundTheme: "from-pink-950 via-slate-900 to-purple-950 border-pink-600/40",
    backgroundTags: ["TikTok", "Reels", "RGB Light", "Gen Z"],
    scriptGuideline: "Hook mạnh ngay đầu video, câu ngắn, nhịp dồn, vào thẳng nội dung",
    sampleScript:
      "Dừng lại ba giây nếu bạn vẫn đang làm video AI theo cách cũ! Đây là bí quyết giúp bạn biến ảnh chân dung thành người dẫn thuyết trình khớp từng khẩu hình tiếng Việt chỉ bằng một click chuột. Lưu lại ngay kẻo bỏ lỡ nhé!",
    sampleScriptEn:
      "Stop scrolling right now if you are still making videos the old manual way! Here is the secret creators use to turn a single still photo into a hyper-realistic talking presenter in seconds. Double tap and save this video before it is gone!",
    voiceGuideline: "Gần gũi và giàu năng lượng; nhịp nhanh, cuốn hút",
    recommendedVoice: "vieneu_Mai Bé Phương",
    recommendedMultiplier: 0.68,
    recommendedAspectRatios: ["9:16"],
    defaultAspectRatio: "9:16",
    kinematicsGuideline: "Cử động đầu sinh động, chớp mắt tự nhiên, biểu cảm thân thiện giàu biểu cảm",
    drivingPolicy: "loop",
    torsoMotion: true,
    useCase: "TikTok, Reels, Shorts, giới thiệu mẹo nhanh",
    badgeColor: "bg-pink-950 text-pink-300 border-pink-700/50",
    geminiPrompt: `Bạn là nhà sáng tạo nội dung hàng đầu có hàng triệu người theo dõi trên TikTok, Reels và Shorts. Hãy viết lại kịch bản nói sau thành video ngắn triệu view:
1. Hook 3 giây đầu: Bắt buộc mở đầu bằng câu giật gân, khơi gợi tò mò hoặc phá vỡ định kiến ngay lập tức ('Dừng lại 3 giây...', 'Đây là bí mật mà ít ai nói cho bạn biết...').
2. Nhịp độ siêu nhanh: Câu siêu ngắn (dưới 8-10 từ), nhịp dồn dập, gãy gọn, không một từ ngữ thừa thãi.
3. Giá trị tức thì: Cung cấp giải pháp hoặc mẹo hữu ích ngay trong 15-30 giây.
4. Kêu gọi tương tác tự nhiên: Kết thúc thúc đẩy thả tim, lưu video hoặc bình luận thảo luận.
5. Chỉ trả về duy nhất nội dung kịch bản lời thoại đã tối ưu, không kèm lời bình hay giải thích thừa.`,
  },
  {
    id: "calm_mindful",
    number: 10,
    name: "Calm & Mindful",
    vietnameseTitle: "Nhẹ nhàng, thư giãn",
    tagline: "Thiên nhiên hoặc không gian tối giản, khoảng nghỉ dài, chữa lành",
    background: "Thiên nhiên, vườn thiền hoặc không gian tối giản với màu dịu",
    backgroundTitle: "Vườn Thiền Yên Bình (Zen Oasis Sanctuary)",
    backgroundDescription: "Không gian vườn Nhật tối giản với tre trúc xanh mát, tiếng nước róc rách và ánh sáng ban mai êm dịu, mang lại cảm giác bình an vô tận.",
    backgroundTheme: "from-emerald-950 via-slate-900 to-teal-950 border-emerald-600/40",
    backgroundTags: ["Thiền định", "Chữa lành", "Bình an", "Vườn Nhật"],
    scriptGuideline: "Giàu tính chia sẻ, dùng câu nhẹ nhàng, khoảng nghỉ dài hơn bình thường",
    sampleScript:
      "Hãy hít một hơi thật sâu... và thả lỏng toàn bộ cơ thể. Sau một ngày dài bận rộn, đây là khoảnh khắc để bạn trở về với sự bình yên trong tâm trí. Mọi lo toan hãy tạm gác lại, chỉ còn sự tĩnh lặng và an nhiên hiện diện ngay tại đây.",
    sampleScriptEn:
      "Take a slow, deep breath in... and gently release all tension from your shoulders. After a demanding day, this is your sanctuary to reconnect with calm clarity. Let go of every worry, and allow yourself to simply be present in this quiet moment.",
    voiceGuideline: "Chậm, ấm áp, giọng thì thầm êm dịu, không vội vã",
    recommendedVoice: "vieneu_Thiền Tâm Đức",
    recommendedMultiplier: 0.32,
    recommendedAspectRatios: ["16:9", "9:16"],
    defaultAspectRatio: "16:9",
    kinematicsGuideline: "Chuyển động đầu và vai rất ít, mắt nhìn dịu dàng, tạo cảm giác an bình",
    drivingPolicy: "hold",
    torsoMotion: false,
    useCase: "Thiền, thư giãn, kể chuyện nhẹ nhàng",
    badgeColor: "bg-emerald-950 text-emerald-300 border-emerald-700/50",
    geminiPrompt: `Bạn là bậc thầy hướng dẫn thiền định và chữa lành tâm thức. Hãy viết lại kịch bản nói sau thành lời dẫn thiền thư giãn, thanh lọc tâm hồn:
1. Nhịp điệu chậm rãi: Dùng câu từ mềm mại, buông lỏng, có các chỉ dẫn hít thở sâu và khoảng lặng (...) để người nghe thả lỏng các cơ.
2. Năng lượng chữa lành: Từ ngữ ấm áp, dịu nhẹ, bao dung, đưa người nghe về trạng thái an nhiên của hiện tại.
3. Giải tỏa căng thẳng: Giúp người nghe buông xả mọi lo âu, cảm nhận sự nhẹ nhõm và biết ơn cuộc sống.
4. Tuyệt đối không: Không dùng từ ngữ gay gắt, nhịp điệu dồn dập hay câu mệnh lệnh thô ráp.
5. Chỉ trả về duy nhất nội dung kịch bản lời thoại đã tối ưu, không kèm lời bình hay giải thích thừa.`,
  },
];
