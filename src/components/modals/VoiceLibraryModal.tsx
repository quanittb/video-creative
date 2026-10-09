import React, { useMemo } from "react";
import {
  X,
  Search,
  Volume2,
  Play,
  Star,
  Check,
  Globe,
  Radio,
  SlidersHorizontal,
  Loader2,
} from "lucide-react";
import { TtsVoice, formatLanguageDisplay, getVoiceLanguage } from "../../data/ttsVoices";

interface VoiceLibraryModalProps {
  isOpen: boolean;
  onClose: () => void;
  voices: TtsVoice[];
  selectedVoiceId: string;
  onSelectVoice: (voice: TtsVoice) => void;
  testingVoiceId: string | null;
  loadingVoiceId?: string | null;
  onTestVoice: (voice: TtsVoice, e?: React.MouseEvent, forceNativeSample?: boolean) => void;
  favoriteVoiceIds: string[];
  onToggleFavorite: (voiceId: string) => void;
  currentScriptText: string;
}

export const VoiceLibraryModal: React.FC<VoiceLibraryModalProps> = ({
  isOpen,
  onClose,
  voices,
  selectedVoiceId,
  onSelectVoice,
  testingVoiceId,
  loadingVoiceId,
  onTestVoice,
  favoriteVoiceIds,
  onToggleFavorite,
  currentScriptText,
}) => {
  const [providerFilter, setProviderFilter] = React.useState<string>("all");
  const [languageFilter, setLanguageFilter] = React.useState<string>("all");
  const [genderFilter, setGenderFilter] = React.useState<string>("all");
  const [searchQuery, setSearchQuery] = React.useState<string>("");

  // Extract unique languages
  const availableLanguages = useMemo(() => {
    const set = new Set<string>();
    for (const v of voices) {
      if (v.lang) set.add(v.lang);
    }
    return Array.from(set).sort((a, b) => {
      // Put Vietnamese first, then English, then others
      if (a.startsWith("vi")) return -1;
      if (b.startsWith("vi")) return 1;
      if (a.startsWith("en")) return -1;
      if (b.startsWith("en")) return 1;
      return a.localeCompare(b);
    });
  }, [voices]);

  // Provider counts
  const counts = useMemo(() => {
    const c = {
      all: voices.length,
      favorites: voices.filter((v) => favoriteVoiceIds.includes(v.id)).length,
      "edge-tts": voices.filter((v) => v.provider === "edge-tts").length,
      capcut: voices.filter((v) => v.provider === "capcut").length,
      vieneu: voices.filter((v) => v.provider === "vieneu").length,
    };
    return c;
  }, [voices, favoriteVoiceIds]);

  // Filtered and sorted voices
  const filteredList = useMemo(() => {
    const q = searchQuery.trim().toLowerCase();
    const list = voices.filter((v) => {
      // Provider filter
      if (providerFilter === "favorites") {
        if (!favoriteVoiceIds.includes(v.id)) return false;
      } else if (providerFilter !== "all" && v.provider !== providerFilter) {
        return false;
      }

      // Language filter
      if (languageFilter !== "all") {
        if (v.lang !== languageFilter && !v.lang?.startsWith(languageFilter)) {
          return false;
        }
      }

      // Gender filter
      if (genderFilter !== "all" && v.gender !== genderFilter) {
        return false;
      }

      // Search query
      if (q) {
        const matchName = v.name.toLowerCase().includes(q);
        const matchDesc = v.description.toLowerCase().includes(q);
        const matchRegion = v.region.toLowerCase().includes(q);
        const matchLang = (v.lang || "").toLowerCase().includes(q);
        const matchLangName = formatLanguageDisplay(v.lang || "").toLowerCase().includes(q);
        const matchTags = v.tags?.some((t) => t.toLowerCase().includes(q)) || false;
        if (!matchName && !matchDesc && !matchRegion && !matchLang && !matchLangName && !matchTags) {
          return false;
        }
      }

      return true;
    });

    // Sort: favorites first, then currently selected, then alphabetical
    return list.sort((a, b) => {
      const aFav = favoriteVoiceIds.includes(a.id);
      const bFav = favoriteVoiceIds.includes(b.id);
      if (aFav && !bFav) return -1;
      if (!aFav && bFav) return 1;
      if (a.id === selectedVoiceId) return -1;
      if (b.id === selectedVoiceId) return 1;
      return a.name.localeCompare(b.name);
    });
  }, [
    voices,
    providerFilter,
    languageFilter,
    genderFilter,
    searchQuery,
    favoriteVoiceIds,
    selectedVoiceId,
  ]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-in fade-in duration-200">
      <div className="bg-studio-bg border border-studio-border rounded-2xl w-full max-w-6xl h-[90vh] flex flex-col overflow-hidden shadow-2xl">
        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-studio-border bg-studio-card/60">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400">
              <Volume2 className="w-5 h-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-slate-100">Kho Mẫu Giọng Đọc (TTS Voice Library)</h2>
                <span className="px-2 py-0.5 rounded text-[11px] bg-studio-accent/20 text-studio-cyan font-mono border border-studio-accent/40">
                  {filteredList.length} giọng khả dụng
                </span>
              </div>
              <p className="text-xs text-slate-400">
                Tuyển tập 350+ giọng đọc AI đa ngôn ngữ từ Edge TTS, CapCut và VieNeu (Hỗ trợ hơn 140 quốc gia)
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-2 rounded-lg text-slate-400 hover:text-white hover:bg-studio-card border border-transparent hover:border-studio-border transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Filters Bar (Matching ProStudio-AI) */}
        <div className="p-4 border-b border-studio-border bg-studio-card/30 flex flex-col gap-3">
          {/* Top Row: Search + Language Dropdown + Gender Dropdown */}
          <div className="flex items-center gap-2.5 flex-wrap">
            {/* Search Input */}
            <div className="relative flex-1 min-w-[240px]">
              <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2 pointer-events-none" />
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                placeholder="Tìm theo tên giọng, ngôn ngữ, vùng miền hoặc phong cách..."
                className="w-full bg-studio-card border border-studio-border focus:border-studio-accent rounded-lg pl-9 pr-3 py-2 text-xs text-slate-100 placeholder-slate-500 outline-none transition-colors"
              />
            </div>

            {/* Language Filter Dropdown */}
            <div className="flex items-center gap-1.5 shrink-0">
              <Globe className="w-3.5 h-3.5 text-studio-cyan" />
              <select
                value={languageFilter}
                onChange={(e) => setLanguageFilter(e.target.value)}
                className="bg-studio-card border border-studio-border rounded-lg px-2.5 py-2 text-xs text-slate-200 outline-none focus:border-studio-accent min-w-[170px]"
              >
                <option value="all">🌐 Tất cả ngôn ngữ ({availableLanguages.length})</option>
                {availableLanguages.map((lang) => (
                  <option key={lang} value={lang}>
                    {formatLanguageDisplay(lang)} ({lang})
                  </option>
                ))}
              </select>
            </div>

            {/* Gender Filter Dropdown */}
            <div className="flex items-center gap-1.5 shrink-0">
              <select
                value={genderFilter}
                onChange={(e) => setGenderFilter(e.target.value)}
                className="bg-studio-card border border-studio-border rounded-lg px-2.5 py-2 text-xs text-slate-200 outline-none focus:border-studio-accent w-28"
              >
                <option value="all">Mọi giới tính</option>
                <option value="female">Nữ</option>
                <option value="male">Nam</option>
              </select>
            </div>
          </div>

          {/* Bottom Row: Technology Provider Pill Tabs */}
          <div className="flex items-center justify-between gap-2 flex-wrap">
            <div className="flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-none">
              <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider mr-1">
                Công nghệ:
              </span>

              <button
                onClick={() => setProviderFilter("all")}
                className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors flex items-center gap-1.5 ${
                  providerFilter === "all"
                    ? "bg-amber-500/15 border-amber-500/50 text-amber-400 font-semibold"
                    : "bg-studio-card border-studio-border text-slate-300 hover:text-white"
                }`}
              >
                <span>Tất cả</span>
                <span className="text-[10px] opacity-70">({counts.all})</span>
              </button>

              <button
                onClick={() => setProviderFilter("favorites")}
                className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors flex items-center gap-1.5 ${
                  providerFilter === "favorites"
                    ? "bg-amber-500/20 border-amber-500 text-amber-300 font-semibold"
                    : "bg-studio-card border-studio-border text-slate-300 hover:text-white"
                }`}
              >
                <Star className="w-3 h-3 fill-current text-amber-400" />
                <span>Yêu thích</span>
                <span className="text-[10px] opacity-70">({counts.favorites})</span>
              </button>

              <button
                onClick={() => setProviderFilter("edge-tts")}
                className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors flex items-center gap-1.5 ${
                  providerFilter === "edge-tts"
                    ? "bg-studio-accent/20 border-studio-accent text-studio-cyan font-semibold"
                    : "bg-studio-card border-studio-border text-slate-300 hover:text-white"
                }`}
              >
                <span>Edge TTS (Microsoft)</span>
                <span className="text-[10px] opacity-70">({counts["edge-tts"]})</span>
              </button>

              <button
                onClick={() => setProviderFilter("capcut")}
                className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors flex items-center gap-1.5 ${
                  providerFilter === "capcut"
                    ? "bg-pink-500/20 border-pink-500 text-pink-300 font-semibold"
                    : "bg-studio-card border-studio-border text-slate-300 hover:text-white"
                }`}
              >
                <span>CapCut (ByteDance)</span>
                <span className="text-[10px] opacity-70">({counts.capcut})</span>
              </button>

              <button
                onClick={() => setProviderFilter("vieneu")}
                className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors flex items-center gap-1.5 ${
                  providerFilter === "vieneu"
                    ? "bg-emerald-500/20 border-emerald-500 text-emerald-300 font-semibold"
                    : "bg-studio-card border-studio-border text-slate-300 hover:text-white"
                }`}
              >
                <span>VieNeu (Local Clone)</span>
                <span className="text-[10px] opacity-70">({counts.vieneu})</span>
              </button>
            </div>

            <div className="text-[11px] text-slate-400 flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-400" />
              <span>{favoriteVoiceIds.length} giọng yêu thích luôn hiển thị đầu</span>
            </div>
          </div>
        </div>

        {/* Voices Grid */}
        <div className="flex-1 overflow-y-auto p-4 scrollbar-thin">
          {filteredList.length === 0 ? (
            <div className="h-64 flex flex-col items-center justify-center text-slate-500 gap-2">
              <Volume2 className="w-10 h-10 stroke-1" />
              <p className="text-sm">Không tìm thấy giọng đọc nào phù hợp với bộ lọc.</p>
              <button
                onClick={() => {
                  setProviderFilter("all");
                  setLanguageFilter("all");
                  setGenderFilter("all");
                  setSearchQuery("");
                }}
                className="text-xs text-studio-cyan underline mt-1"
              >
                Đặt lại bộ lọc
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
              {filteredList.map((voice) => {
                const isSelected = selectedVoiceId === voice.id;
                const isTesting = testingVoiceId === voice.id;
                const isLoading = loadingVoiceId === voice.id;
                const isFav = favoriteVoiceIds.includes(voice.id);
                const langName = formatLanguageDisplay(voice.lang || "vi-VN");

                return (
                  <div
                    key={voice.id}
                    onClick={() => {
                      onSelectVoice(voice);
                    }}
                    className={`rounded-xl border p-3 flex flex-col justify-between gap-2.5 transition-all cursor-pointer relative group ${
                      isSelected
                        ? "bg-studio-card border-amber-500 ring-1 ring-amber-500/50 shadow-lg shadow-amber-500/10"
                        : "bg-studio-card/70 border-studio-border hover:border-slate-600 hover:bg-studio-elevated"
                    }`}
                  >
                    {/* Header info */}
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-center gap-2.5 min-w-0">
                        <div
                          className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 text-xs font-bold ${
                            voice.gender === "male"
                              ? "bg-blue-950/80 text-blue-300 border border-blue-700/50"
                              : "bg-pink-950/80 text-pink-300 border border-pink-700/50"
                          }`}
                        >
                          {voice.gender === "male" ? "Nam" : "Nữ"}
                        </div>

                        <div className="min-w-0">
                          <div className="flex items-center gap-1.5">
                            <h4 className="text-xs font-bold text-slate-100 truncate" title={voice.name}>
                              {voice.name}
                            </h4>
                            {isSelected && (
                              <span className="text-amber-400 font-bold text-xs" title="Đang chọn">
                                ✓
                              </span>
                            )}
                          </div>
                          <p className="text-[10px] text-slate-400 truncate" title={langName}>
                            {langName}
                          </p>
                        </div>
                      </div>

                      {/* Favorite Button */}
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onToggleFavorite(voice.id);
                        }}
                        className={`p-1 rounded-md transition-colors ${
                          isFav
                            ? "text-amber-400 hover:text-amber-300"
                            : "text-slate-600 hover:text-slate-300 opacity-60 group-hover:opacity-100"
                        }`}
                        title={isFav ? "Bỏ yêu thích" : "Thêm vào yêu thích"}
                      >
                        <Star className={`w-3.5 h-3.5 ${isFav ? "fill-current" : ""}`} />
                      </button>
                    </div>

                    {/* Tags row */}
                    <div className="flex items-center gap-1.5 flex-wrap">
                      <span
                        className={`px-1.5 py-0.5 rounded text-[9px] font-mono uppercase font-semibold ${
                          voice.provider === "vieneu"
                            ? "bg-emerald-950 text-emerald-300 border border-emerald-700/40"
                            : voice.provider === "capcut"
                            ? "bg-pink-950 text-pink-300 border border-pink-700/40"
                            : "bg-studio-accent/20 text-studio-cyan border border-studio-accent/40"
                        }`}
                      >
                        {voice.provider === "edge-tts" ? "EDGE TTS" : voice.provider.toUpperCase()}
                      </span>

                      <span className="px-1.5 py-0.5 rounded text-[9px] font-mono bg-slate-800 text-slate-300 border border-slate-700">
                        {voice.lang || "vi-VN"}
                      </span>

                      {voice.region && (
                        <span className="px-1.5 py-0.5 rounded text-[9px] bg-slate-800/80 text-slate-400 border border-slate-700 truncate max-w-[90px]">
                          {voice.region}
                        </span>
                      )}
                    </div>

                    {/* Description preview */}
                    <p className="text-[11px] text-slate-400 line-clamp-1 leading-snug">
                      {voice.description}
                    </p>

                    {/* Bottom action row: Preview + Select */}
                    <div className="flex items-center justify-between gap-2 pt-1 border-t border-white/5">
                      <button
                        onClick={(e) => onTestVoice(voice, e, true)}
                        disabled={isLoading}
                        className={`px-2.5 py-1 rounded-md text-[11px] border flex items-center gap-1.5 transition-colors font-medium ${
                          isTesting
                            ? "bg-amber-950 text-amber-300 border-amber-600/50 hover:bg-amber-900"
                            : isLoading
                            ? "bg-indigo-950 text-indigo-300 border-indigo-700/50 cursor-wait font-medium"
                            : "bg-studio-card hover:bg-studio-elevated text-slate-300 hover:text-white border-studio-border"
                        }`}
                        title={isTesting ? "Dừng nghe thử" : isLoading ? "Đang tải mẫu giọng..." : "Nghe thử mẫu giọng"}
                      >
                        {isLoading ? (
                          <>
                            <Loader2 className="w-3 h-3 animate-spin text-indigo-300" />
                            <span>Đang tải...</span>
                          </>
                        ) : isTesting ? (
                          <>
                            <span className="w-2 h-2 rounded-sm bg-amber-400 animate-pulse" />
                            <span>Dừng</span>
                          </>
                        ) : (
                          <>
                            <Play className="w-3 h-3 fill-current text-studio-cyan" />
                            <span>Nghe thử</span>
                          </>
                        )}
                      </button>

                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onSelectVoice(voice);
                          onClose();
                        }}
                        className={`px-3 py-1 rounded-md text-xs font-semibold transition-all flex items-center gap-1 ${
                          isSelected
                            ? "bg-amber-500/20 text-amber-300 border border-amber-500/40"
                            : "bg-studio-accent hover:bg-studio-accentHover text-white shadow-sm"
                        }`}
                      >
                        {isSelected ? (
                          <>
                            <Check className="w-3 h-3" />
                            <span>Đang dùng</span>
                          </>
                        ) : (
                          <span>Chọn giọng</span>
                        )}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer Summary Bar */}
        <div className="flex items-center justify-between px-6 py-3 border-t border-studio-border bg-studio-card/80 text-xs text-slate-400">
          <div className="flex items-center gap-2">
            <span>Giọng đang chọn:</span>
            <strong className="text-amber-400 font-semibold">
              {voices.find((v) => v.id === selectedVoiceId)?.name || selectedVoiceId}
            </strong>
            <span className="text-slate-600">•</span>
            <span>
              Ngôn ngữ: {formatLanguageDisplay(voices.find((v) => v.id === selectedVoiceId)?.lang || "vi-VN")}
            </span>
          </div>

          <button
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg bg-studio-elevated hover:bg-studio-hover text-slate-200 border border-studio-border text-xs font-medium transition-colors"
          >
            Đóng cửa sổ
          </button>
        </div>
      </div>
    </div>
  );
};
