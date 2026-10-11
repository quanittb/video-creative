export interface CharacterOption {
  id: string;
  name: string;
  category: "male" | "female" | "anime" | "angle" | "custom";
  filename: string;
  relPath: string;
  webPath: string;
  previewPath?: string;
  desc: string;
  gender: "male" | "female";
}

// The sample library intentionally contains only the two front-facing personas.
// Uploaded/custom characters are stored separately at runtime.
export const CHARACTER_LIBRARY: CharacterOption[] = [
  {
    id: "male_front",
    name: "Nhân vật nam",
    category: "male",
    filename: "ChatGPT Image Sep 8, 2026, 08_46_26 AM (1).png",
    relPath: "assets/characters/nhanvatnam/ChatGPT Image Sep 8, 2026, 08_46_26 AM (1).png",
    webPath: "/characters/nhanvatnam/ChatGPT Image Sep 8, 2026, 08_46_26 AM (1).png",
    desc: "Ảnh nam chính diện dùng làm nhân vật mẫu.",
    gender: "male",
  },
  {
    id: "female_front",
    name: "Nhân vật nữ",
    category: "female",
    filename: "ChatGPT Image Sep 14, 2026, 11_35_53 AM (1).png",
    relPath: "assets/characters/nhanvatnu/ChatGPT Image Sep 14, 2026, 11_35_53 AM (1).png",
    webPath: "/characters/nhanvatnu/ChatGPT Image Sep 14, 2026, 11_35_53 AM (1).png",
    desc: "Ảnh nữ chính diện dùng làm nhân vật mẫu.",
    gender: "female",
  },
];
