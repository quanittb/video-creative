export interface AdCopyStyle {
  id: string;
  label: string;
  guidance: string;
}

export const AD_COPY_STYLES: AdCopyStyle[] = [
  { id: "ugc_creator", label: "UGC tự nhiên", guidance: "Lời chia sẻ gần gũi như người sáng tạo nội dung, không giả làm khách hàng thật và không tự nhận đã trải nghiệm." },
  { id: "problem_solution", label: "Vấn đề → giải pháp", guidance: "Mở bằng nhu cầu có thật trong brief, giải thích giải pháp bằng thông tin đã cung cấp, rồi CTA rõ ràng." },
  { id: "product_demo", label: "Demo sản phẩm", guidance: "Tập trung vào cách dùng và lợi ích đã được xác nhận; câu ngắn, dễ theo dõi như đang xem demo." },
  { id: "offer_cta", label: "Ưu đãi & CTA", guidance: "Đưa ưu đãi chỉ khi brief cung cấp chính xác; nêu điều kiện nếu có và kết bằng một CTA cụ thể." },
  { id: "educational_ad", label: "Quảng cáo giáo dục", guidance: "Giải thích một điểm hữu ích, dễ hiểu, sau đó kết nối tự nhiên với sản phẩm và CTA." },
  { id: "brand_story", label: "Câu chuyện thương hiệu", guidance: "Kể ngắn gọn động lực hoặc giá trị thương hiệu dựa trên dữ kiện trong brief, không bịa lịch sử hay lời chứng thực." },
];

export const AD_OBJECTIVES = [
  { id: "awareness", label: "Nhận biết thương hiệu" },
  { id: "consideration", label: "Cân nhắc / tìm hiểu" },
  { id: "conversion", label: "Chuyển đổi / mua hàng" },
  { id: "lead", label: "Thu thập khách hàng tiềm năng" },
  { id: "app_install", label: "Cài đặt ứng dụng" },
] as const;

export const AD_MARKETS = [
  { id: "VN", label: "Việt Nam" },
  { id: "US", label: "Hoa Kỳ" },
  { id: "GB", label: "Vương quốc Anh" },
  { id: "SG", label: "Singapore" },
  { id: "JP", label: "Nhật Bản" },
  { id: "KR", label: "Hàn Quốc" },
  { id: "TH", label: "Thái Lan" },
  { id: "ID", label: "Indonesia" },
  { id: "PH", label: "Philippines" },
  { id: "other", label: "Quốc gia / khu vực khác" },
] as const;

export interface VoiceExpression {
  id: string;
  label: string;
  guidance: string;
  fit: string;
}

export const VOICE_EXPRESSIONS: VoiceExpression[] = [
  { id: "natural_clear", label: "Tự nhiên, rõ ràng", guidance: "Clear, conversational, balanced emphasis; avoid exaggerated performance.", fit: "Phù hợp mặc định với đa số quảng cáo." },
  { id: "warm_friendly", label: "Ấm áp, thân thiện", guidance: "Warm, approachable, lightly smiling delivery with relaxed phrasing.", fit: "Hợp nội dung gần gũi, chăm sóc hoặc hướng dẫn." },
  { id: "confident_trustworthy", label: "Tự tin, đáng tin cậy", guidance: "Steady, assured, credible delivery; confident without sounding pushy.", fit: "Hợp giới thiệu giá trị hoặc lời mời hành động rõ ràng." },
  { id: "energetic_upbeat", label: "Năng lượng, tươi vui", guidance: "Upbeat, lively, brisk delivery with controlled enthusiasm; never shout.", fit: "Hợp video ngắn, demo nhanh, nội dung giải trí." },
  { id: "calm_reassuring", label: "Điềm tĩnh, trấn an", guidance: "Calm, measured, reassuring delivery with gentle emphasis.", fit: "Hợp hướng dẫn hoặc sản phẩm cần giải thích cẩn thận." },
  { id: "empathetic", label: "Đồng cảm, chân thành", guidance: "Empathetic, sincere, respectful delivery; avoid manufactured intimacy.", fit: "Hợp chủ đề đời sống và nhu cầu cá nhân." },
  { id: "playful_light", label: "Hóm hỉnh, nhẹ nhàng", guidance: "Light, playful delivery with subtle humor only where culturally appropriate.", fit: "Hợp nội dung vui, không dùng với chủ đề nhạy cảm." },
  { id: "authoritative", label: "Chuyên nghiệp, điềm đạm", guidance: "Composed, precise, professional delivery with restrained emphasis.", fit: "Hợp dịch vụ chuyên môn hoặc thương hiệu doanh nghiệp." },
];

export interface AdCopyBrief {
  styleId: string;
  marketId: string;
  marketName: string;
  customMarket?: string;
  audience: string;
  objective: string;
  durationSeconds: number;
  productFacts: string;
  callToAction: string;
}
