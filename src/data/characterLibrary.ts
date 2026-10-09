export interface CharacterOption {
  id: string;
  name: string;
  category: "male" | "female" | "anime" | "angle" | "custom";
  filename: string;
  relPath: string;
  webPath: string;
  desc: string;
  gender: "male" | "female";
}

export const CHARACTER_LIBRARY: CharacterOption[] = [
  // =========================================================================
  // MC NAM (CHÍNH DIỆN, CHUẨN ĐỘ NÉT CAO)
  // =========================================================================
  {
    id: "male_asian_office_1080p",
    name: "MC Nam Công Sở 1080p",
    category: "male",
    filename: "asian_male_office_1080p.png",
    relPath: "assets/characters/nhanvatnam/asian_male_office_1080p.png",
    webPath: "/characters/nhanvatnam/asian_male_office_1080p.png",
    desc: "MC Nam văn phòng, áo sơ mi lịch lãm, độ nét cao 1080p",
    gender: "male",
  },
  {
    id: "male_studio_modern_front",
    name: "MC Nam Studio Trẻ Trung",
    category: "male",
    filename: "ChatGPT Image Sep 8, 2026, 08_46_26 AM (1).png",
    relPath: "assets/characters/nhanvatnam/ChatGPT Image Sep 8, 2026, 08_46_26 AM (1).png",
    webPath: "/characters/nhanvatnam/ChatGPT Image Sep 8, 2026, 08_46_26 AM (1).png",
    desc: "Chân dung nam thanh lịch, ánh sáng studio chuyên nghiệp",
    gender: "male",
  },
  {
    id: "male_business_leader",
    name: "MC Nam Doanh Nhân Đĩnh Đạc",
    category: "male",
    filename: "ChatGPT Image Sep 8, 2026, 08_46_51 AM.png",
    relPath: "assets/characters/nhanvatnam/ChatGPT Image Sep 8, 2026, 08_46_51 AM.png",
    webPath: "/characters/nhanvatnam/ChatGPT Image Sep 8, 2026, 08_46_51 AM.png",
    desc: "Nam MC phong thái tự tin, phù hợp bản tin tài chính, phân tích",
    gender: "male",
  },
  {
    id: "male_tech_host",
    name: "MC Nam Bản Tin Công Nghệ",
    category: "male",
    filename: "ChatGPT Image Sep 8, 2026, 08_46_42 AM (1).png",
    relPath: "assets/characters/nhanvatnam/ChatGPT Image Sep 8, 2026, 08_46_42 AM (1).png",
    webPath: "/characters/nhanvatnam/ChatGPT Image Sep 8, 2026, 08_46_42 AM (1).png",
    desc: "Nam MC hiện đại, phong cách podcast công nghệ, giáo dục",
    gender: "male",
  },

  // =========================================================================
  // MC NỮ (CHÍNH DIỆN, THANH LỊCH)
  // =========================================================================
  {
    id: "female_news_anchor_front",
    name: "MC Nữ Thời Sự Truyền Hình",
    category: "female",
    filename: "ChatGPT Image Sep 14, 2026, 11_35_53 AM (1).png",
    relPath: "assets/characters/nhanvatnu/ChatGPT Image Sep 14, 2026, 11_35_53 AM (1).png",
    webPath: "/characters/nhanvatnu/ChatGPT Image Sep 14, 2026, 11_35_53 AM (1).png",
    desc: "Nữ MC thanh lịch, gương mặt khả ái, phù hợp bản tin chính luận",
    gender: "female",
  },
  {
    id: "female_modern_lifestyle",
    name: "MC Nữ Phong Cách Hiện Đại",
    category: "female",
    filename: "ChatGPT Image Sep 14, 2026, 11_35_53 AM (4).png",
    relPath: "assets/characters/nhanvatnu/ChatGPT Image Sep 14, 2026, 11_35_53 AM (4).png",
    webPath: "/characters/nhanvatnu/ChatGPT Image Sep 14, 2026, 11_35_53 AM (4).png",
    desc: "Nữ MC trẻ trung, phong cách năng động, sáng tạo",
    gender: "female",
  },
  {
    id: "female_broadcast_host",
    name: "MC Nữ Giới Thiệu Sản Phẩm",
    category: "female",
    filename: "ChatGPT Image Sep 14, 2026, 11_35_54 AM (7).png",
    relPath: "assets/characters/nhanvatnu/ChatGPT Image Sep 14, 2026, 11_35_54 AM (7).png",
    webPath: "/characters/nhanvatnu/ChatGPT Image Sep 14, 2026, 11_35_54 AM (7).png",
    desc: "Nụ cười tự tin, truyền cảm hứng, phù hợp video review, showcase",
    gender: "female",
  },

  // =========================================================================
  // NHÂN VẬT 3D HOẠT HÌNH PIXAR
  // =========================================================================
  {
    id: "anime_pixar_girl_front",
    name: "Nhân Vật 3D Hoạt Hình Pixar",
    category: "anime",
    filename: "ChatGPT Image Sep 8, 2026, 09_49_11 AM (1).png",
    relPath: "assets/characters/hoathinhnu/ChatGPT Image Sep 8, 2026, 09_49_11 AM (1).png",
    webPath: "/characters/hoathinhnu/ChatGPT Image Sep 8, 2026, 09_49_11 AM (1).png",
    desc: "Nhân vật nữ hoạt hình 3D phong cách Pixar, biểu cảm sống động",
    gender: "female",
  },
  {
    id: "anime_pixar_modern_style",
    name: "Nhân Vật 3D Trẻ Trung Năng Động",
    category: "anime",
    filename: "ChatGPT Image Sep 8, 2026, 09_51_29 AM (1).png",
    relPath: "assets/characters/hoathinhnu/ChatGPT Image Sep 8, 2026, 09_51_29 AM (1).png",
    webPath: "/characters/hoathinhnu/ChatGPT Image Sep 8, 2026, 09_51_29 AM (1).png",
    desc: "Hoạt hình 3D phong cách hiện đại, phù hợp nội dung giáo dục, mạng xã hội",
    gender: "female",
  },
  {
    id: "anime_pixar_smile",
    name: "Nhân Vật 3D Biểu Cảm Thân Thiện",
    category: "anime",
    filename: "ChatGPT Image Sep 8, 2026, 09_49_13 AM (4).png",
    relPath: "assets/characters/hoathinhnu/ChatGPT Image Sep 8, 2026, 09_49_13 AM (4).png",
    webPath: "/characters/hoathinhnu/ChatGPT Image Sep 8, 2026, 09_49_13 AM (4).png",
    desc: "Nhân vật 3D cười tươi, tạo cảm giác gần gũi và thu hút",
    gender: "female",
  },

  // =========================================================================
  // GÓC QUAY ĐẶC TẢ & GÓC NGHIÊNG (ANGLE SELECTION)
  // =========================================================================
  {
    id: "angle_front_standard",
    name: "Góc Chính Diện Chuẩn (0° Front)",
    category: "angle",
    filename: "angle_front.jpg",
    relPath: "assets/characters/angle_front.jpg",
    webPath: "/characters/angle_front.jpg",
    desc: "Góc quay chân dung trực diện tiêu chuẩn studio",
    gender: "male",
  },
  {
    id: "angle_45_deg",
    name: "Góc Nghiêng 3/4 (45° Angle)",
    category: "angle",
    filename: "angle_45.jpg",
    relPath: "assets/characters/angle_45.jpg",
    webPath: "/characters/angle_45.jpg",
    desc: "Góc quay nghiêng nghệ thuật, tạo chiều sâu thị giác",
    gender: "male",
  },
  {
    id: "angle_closeup_view",
    name: "Cận Cảnh Gương Mặt (Close-Up)",
    category: "angle",
    filename: "angle_closeup.jpg",
    relPath: "assets/characters/angle_closeup.jpg",
    webPath: "/characters/angle_closeup.jpg",
    desc: "Góc quay cận cảnh biểu cảm cảm xúc và khẩu hình",
    gender: "male",
  },
  {
    id: "angle_male_15_deg",
    name: "MC Nam - Góc Nghiêng Nhẹ 15°",
    category: "angle",
    filename: "ChatGPT Image Sep 8, 2026, 08_46_26 AM (2).png",
    relPath: "assets/characters/nhanvatnam/ChatGPT Image Sep 8, 2026, 08_46_26 AM (2).png",
    webPath: "/characters/nhanvatnam/ChatGPT Image Sep 8, 2026, 08_46_26 AM (2).png",
    desc: "Góc quay nam hướng nhìn lệch phải nhẹ nhàng",
    gender: "male",
  },
  {
    id: "angle_female_15_deg",
    name: "MC Nữ - Góc Nghiêng Nhẹ 15°",
    category: "angle",
    filename: "ChatGPT Image Sep 14, 2026, 11_35_53 AM (2).png",
    relPath: "assets/characters/nhanvatnu/ChatGPT Image Sep 14, 2026, 11_35_53 AM (2).png",
    webPath: "/characters/nhanvatnu/ChatGPT Image Sep 14, 2026, 11_35_53 AM (2).png",
    desc: "Góc quay nữ nghiêng nhẹ, nét mặt tự nhiên",
    gender: "female",
  },
];
