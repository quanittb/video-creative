import React, { useState } from "react";
import { Folder, User, Copy, Check, Sparkles } from "lucide-react";
import { HardwareStatus } from "../../types";
import { PRESENTATION_STYLES } from "../../data/presentationStyles";
import { CHARACTER_LIBRARY } from "../../data/characterLibrary";

interface Props {
  hardware: HardwareStatus | null;
  onOpenFolder: (path?: string) => void;
}

export const AssetsView: React.FC<Props> = ({ onOpenFolder }) => {
  const [activeCategory, setActiveCategory] = useState<"characters" | "styles">("styles");
  const [copiedPath, setCopiedPath] = useState<string | null>(null);

  const characters = CHARACTER_LIBRARY;

  const handleCopyText = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedPath(id);
    setTimeout(() => setCopiedPath(null), 2000);
  };

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-studio-obsidian">
      {/* Category Tabs */}
      <div className="bg-studio-panel border-b border-studio-border px-6 py-3 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <button
            onClick={() => setActiveCategory("styles")}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-2 transition-colors ${
              activeCategory === "styles"
                ? "bg-studio-accent text-white"
                : "bg-studio-elevated text-slate-400 hover:text-white"
            }`}
          >
            <Sparkles className="w-3.5 h-3.5 text-studio-cyan" />
            <span>10 Phong cách Sản xuất ({PRESENTATION_STYLES.length})</span>
          </button>

          <button
            onClick={() => setActiveCategory("characters")}
            className={`px-3.5 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-2 transition-colors ${
              activeCategory === "characters"
                ? "bg-studio-accent text-white"
                : "bg-studio-elevated text-slate-400 hover:text-white"
            }`}
          >
            <User className="w-3.5 h-3.5" />
            <span>Thư viện Nhân vật ({characters.length})</span>
          </button>

        </div>

        <button
          onClick={() => onOpenFolder()}
          className="text-xs text-studio-cyan hover:underline flex items-center gap-1"
        >
          <Folder className="w-3.5 h-3.5" />
          <span>Mở thư mục assets</span>
        </button>
      </div>

      {/* Grid Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {/* TAB 1: 10 PRESENTATION STYLES */}
        {activeCategory === "styles" && (
          <div className="grid grid-cols-2 gap-5">
            {PRESENTATION_STYLES.map((st) => (
              <div
                key={st.id}
                className="bg-studio-card border border-studio-border hover:border-slate-600 rounded-xl p-5 flex flex-col gap-3.5 transition-all shadow-sm"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2.5">
                    <span className="w-6 h-6 rounded-md bg-studio-accent text-white font-mono text-xs font-bold flex items-center justify-center">
                      {st.number}
                    </span>
                    <div>
                      <h3 className="text-sm font-bold text-slate-100 flex items-center gap-2">
                        <span>{st.name}</span>
                        <span className="text-slate-500 font-normal">/</span>
                        <span className="text-studio-cyan font-medium">{st.vietnameseTitle}</span>
                      </h3>
                    </div>
                  </div>

                  <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-semibold border ${st.badgeColor}`}>
                    9:16
                  </span>
                </div>

                <p className="text-xs text-slate-300 font-medium">{st.tagline}</p>

                <div className="space-y-2 text-xs border-y border-studio-border/60 py-3 font-sans">
                  <div className="flex items-start gap-2">
                    <span className="text-slate-500 text-[11px] w-24 shrink-0 uppercase tracking-wide">Background:</span>
                    <span className="text-slate-300 font-medium">{st.background}</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="text-slate-500 text-[11px] w-24 shrink-0 uppercase tracking-wide">Giọng & Nhịp:</span>
                    <span className="text-slate-300 font-medium">{st.voiceGuideline}</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="text-slate-500 text-[11px] w-24 shrink-0 uppercase tracking-wide">Chuyển động:</span>
                    <span className="text-slate-300 font-medium">Echo Flash tự tạo chuyển động theo lời thoại.</span>
                  </div>
                </div>

                {/* Sample Script Snippet */}
                <div className="bg-studio-elevated/70 rounded-lg p-3 text-xs text-slate-300 italic relative group">
                  <span className="text-[10px] text-slate-500 font-mono not-italic block mb-1 uppercase font-semibold">
                    Kịch bản mẫu chuẩn phong cách:
                  </span>
                  "{st.sampleScript}"

                  <button
                    onClick={() => handleCopyText(st.sampleScript, st.id)}
                    className="absolute top-2.5 right-2.5 p-1 rounded bg-studio-card border border-studio-border text-slate-400 hover:text-white text-xs opacity-0 group-hover:opacity-100 transition-opacity"
                    title="Sao chép kịch bản mẫu"
                  >
                    {copiedPath === st.id ? (
                      <Check className="w-3.5 h-3.5 text-emerald-400" />
                    ) : (
                      <Copy className="w-3.5 h-3.5" />
                    )}
                  </button>
                </div>

                <div className="mt-auto pt-1 flex items-center justify-between text-[11px] text-slate-500 font-mono">
                  <span>Phù hợp: {st.useCase}</span>
                  <span>Giọng: {st.recommendedVoice}</span>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* TAB 2: CHARACTERS */}
        {activeCategory === "characters" && (
          <div className="grid grid-cols-4 gap-4">
            {characters.length === 0 ? (
              <div className="col-span-4 p-12 text-center text-slate-500 text-xs">
                Không tìm thấy ảnh nhân vật trong assets/characters/
              </div>
            ) : (
              characters.map((c, idx) => (
                <div
                  key={idx}
                  className="bg-studio-card border border-studio-border hover:border-slate-600 rounded-xl p-3 flex flex-col gap-2 group transition-all"
                >
                  <div className="w-full aspect-[4/3] rounded-lg bg-gradient-to-tr from-slate-900 to-slate-800 flex items-center justify-center text-slate-400 font-mono text-xs overflow-hidden relative">
                    <img src={c.webPath} alt={c.name} className="absolute inset-0 w-full h-full object-cover" loading="lazy" />
                    <span className="absolute top-2 right-2 text-[10px] font-mono px-1.5 py-0.5 rounded bg-black/60 text-studio-cyan">
                      {c.gender === "male" ? "Nam" : "Nữ"}
                    </span>
                  </div>

                  <div className="flex items-center justify-between text-xs mt-1">
                    <span className="font-semibold text-slate-200 truncate" title={c.name}>
                      {c.name}
                    </span>
                    <button
                      onClick={() => handleCopyText(c.relPath, `char_${idx}`)}
                      title="Sao chép đường dẫn file"
                      className="p-1 rounded bg-studio-elevated hover:bg-studio-hover text-slate-400 hover:text-white"
                    >
                      {copiedPath === `char_${idx}` ? (
                        <Check className="w-3.5 h-3.5 text-emerald-400" />
                      ) : (
                        <Copy className="w-3.5 h-3.5" />
                      )}
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        )}

      </div>
    </div>
  );
};
