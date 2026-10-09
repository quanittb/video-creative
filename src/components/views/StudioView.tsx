import React, { useState, useMemo, useRef } from "react";
import {
  Sparkles,
  Volume2,
  Sliders,
  Layers,
  Play,
  CheckCircle,
  FileText,
  User,
  Film,
  RotateCcw,
  BookOpen,
  ChevronRight,
  Info,
  Upload,
  Image as ImageIcon,
  Search,
  Key,
  Check,
  Copy,
  ArrowRight,
  Settings,
  RefreshCw,
  Eye,
  SlidersHorizontal,
  Star,
  Globe,
  Loader2,
  Trash2,
} from "lucide-react";
import { HardwareStatus, PresentationStyle } from "../../types";
import { PRESENTATION_STYLES } from "../../data/presentationStyles";
import { TTS_VOICES, TtsVoice, getVoiceLanguage, formatLanguageDisplay, getSampleTextForVoice } from "../../data/ttsVoices";
import { CHARACTER_LIBRARY, CharacterOption } from "../../data/characterLibrary";
import {
  optimizeScriptWithGemini,
  OptimizationResult,
  getStoredGeminiKey,
  setStoredGeminiKey,
} from "../../services/geminiOptimizer";
import { VoiceLibraryModal } from "../modals/VoiceLibraryModal";

interface Props {
  hardware: HardwareStatus | null;
  onJobCreated: () => void;
  onStartWorker: () => void;
  invokeCommand: <T>(cmd: string, args?: Record<string, any>) => Promise<T>;
  isTestMode: boolean;
}

export const StudioView: React.FC<Props> = ({
  hardware,
  onJobCreated,
  onStartWorker,
  invokeCommand,
  isTestMode,
}) => {
  // =========================================================================
  // 1. PRESENTATION STYLE STATE
  // =========================================================================
  const [selectedStyleId, setSelectedStyleId] = useState<string>("news_anchor");
  const currentStyle = useMemo(
    () => PRESENTATION_STYLES.find((s) => s.id === selectedStyleId) || PRESENTATION_STYLES[0],
    [selectedStyleId]
  );
  const [showStyleGuide, setShowStyleGuide] = useState(true);

  // =========================================================================
  // 2. FORM STATE (TITLE, SCRIPT, RATIO, MOTION)
  // =========================================================================
  const [title, setTitle] = useState("Bản tin AI Video Studio");
  const [script, setScript] = useState(currentStyle.sampleScript);
  const [originalDraftScript, setOriginalDraftScript] = useState("");
  const [aspectRatio, setAspectRatio] = useState<"16:9" | "9:16" | "1:1">(currentStyle.defaultAspectRatio);
  const [multiplier, setMultiplier] = useState(currentStyle.recommendedMultiplier);
  const [selectedDriving, setSelectedDriving] = useState("reference_head_driving.mp4");
  const [drivingPolicy, setDrivingPolicy] = useState<"hold" | "loop">(currentStyle.drivingPolicy);
  const [torsoMotion, setTorsoMotion] = useState(currentStyle.torsoMotion);
  const [dryRun, setDryRun] = useState(isTestMode);

  React.useEffect(() => {
    setDryRun(isTestMode);
  }, [isTestMode]);

  // =========================================================================
  // 3. GEMINI AI OPTIMIZATION STATE
  // =========================================================================
  const [isOptimizing, setIsOptimizing] = useState(false);
  const [optimizationResult, setOptimizationResult] = useState<OptimizationResult | null>(null);
  const [geminiApiKey, setGeminiApiKey] = useState(getStoredGeminiKey());
  const [showApiKeyModal, setShowApiKeyModal] = useState(false);
  const [tempApiKey, setTempApiKey] = useState(geminiApiKey);

  // =========================================================================
  // 4. CHARACTER SELECTION & AUTO-SAVED CUSTOM CHARACTERS
  // =========================================================================
  const [customCharacters, setCustomCharacters] = useState<CharacterOption[]>([]);
  const [selectedCharOption, setSelectedCharOption] = useState<CharacterOption>(CHARACTER_LIBRARY[0]);
  const [customUploadedPhoto, setCustomUploadedPhoto] = useState<{
    name: string;
    previewUrl: string;
    path: string;
  } | null>(null);
  const [charCategoryFilter, setCharCategoryFilter] = useState<string>("all");
  const [charSearchQuery, setCharSearchQuery] = useState("");
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Load custom characters from disk on mount
  React.useEffect(() => {
    let isMounted = true;
    const loadCustom = async () => {
      try {
        const saved = await invokeCommand<CharacterOption[]>("list_custom_characters");
        if (isMounted && Array.isArray(saved) && saved.length > 0) {
          setCustomCharacters(saved);
        }
      } catch (e) {
        console.warn("Could not load custom characters:", e);
      }
    };
    loadCustom();
    return () => {
      isMounted = false;
    };
  }, [invokeCommand]);

  // =========================================================================
  // 5. TTS PROVIDER & VOICE SELECTION (FROM PROSTUDIO-AI)
  // =========================================================================
  const [selectedVoiceId, setSelectedVoiceId] = useState<string>(currentStyle.recommendedVoice);
  const selectedVoice = useMemo(
    () => TTS_VOICES.find((v) => v.id === selectedVoiceId) || TTS_VOICES[0],
    [selectedVoiceId]
  );
  const [showVoiceModal, setShowVoiceModal] = useState<boolean>(false);
  const [voiceProviderFilter, setVoiceProviderFilter] = useState<string>("all");
  const [voiceLanguageFilter, setVoiceLanguageFilter] = useState<string>("all");
  const [voiceGenderFilter, setVoiceGenderFilter] = useState<string>("all");
  const [voiceCategoryFilter, setVoiceCategoryFilter] = useState<string>("all");
  const [voiceSearchQuery, setVoiceSearchQuery] = useState("");
  const [testingVoiceId, setTestingVoiceId] = useState<string | null>(null);
  const [loadingVoiceId, setLoadingVoiceId] = useState<string | null>(null);

  // Favorites state persisted in localStorage
  const [favoriteVoiceIds, setFavoriteVoiceIds] = useState<string[]>(() => {
    try {
      const raw = localStorage.getItem("VCS_FAVORITE_VOICES");
      return raw ? JSON.parse(raw) : ["vi-VN-NamMinhNeural", "vi-VN-HoaiMyNeural", "vieneu-vntm-leminh", "vieneu-vntm-quynhanh"];
    } catch {
      return ["vi-VN-NamMinhNeural", "vi-VN-HoaiMyNeural"];
    }
  });

  const handleToggleFavoriteVoice = (voiceId: string) => {
    setFavoriteVoiceIds((prev) => {
      const next = prev.includes(voiceId)
        ? prev.filter((id) => id !== voiceId)
        : [...prev, voiceId];
      try {
        localStorage.setItem("VCS_FAVORITE_VOICES", JSON.stringify(next));
      } catch (e) {
        console.warn("Could not save favorites to localStorage", e);
      }
      return next;
    });
  };

  // Available unique languages in TTS catalog
  const availableLanguages = useMemo(() => {
    const set = new Set<string>();
    for (const v of TTS_VOICES) {
      if (v.lang) set.add(v.lang);
    }
    return Array.from(set).sort((a, b) => {
      if (a.startsWith("vi")) return -1;
      if (b.startsWith("vi")) return 1;
      if (a.startsWith("en")) return -1;
      if (b.startsWith("en")) return 1;
      return a.localeCompare(b);
    });
  }, []);

  // Active right column tab: 'character' | 'voice' | 'motion'
  const [rightTab, setRightTab] = useState<"character" | "voice" | "motion">("character");

  // Notifications
  const [successBanner, setSuccessBanner] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  // =========================================================================
  // HANDLERS: STYLE SWITCHING
  // =========================================================================
  const handleSelectStyle = (style: PresentationStyle) => {
    setSelectedStyleId(style.id);
    setMultiplier(style.recommendedMultiplier);
    setAspectRatio(style.defaultAspectRatio);
    setDrivingPolicy(style.drivingPolicy);
    setTorsoMotion(style.torsoMotion);
    setTitle(`${style.number}. ${style.name} — ${style.vietnameseTitle}`);

    // If style recommends a voice from our catalog, sync it
    if (TTS_VOICES.some((v) => v.id === style.recommendedVoice)) {
      setSelectedVoiceId(style.recommendedVoice);
    }

    setSuccessBanner(`Đã áp dụng phong cách: ${style.name} (${style.vietnameseTitle})`);
    setTimeout(() => setSuccessBanner(null), 2500);
  };

  const handleApplySampleScript = () => {
    const langInfo = getVoiceLanguage(selectedVoice);
    if (langInfo.isEnglish && currentStyle.sampleScriptEn) {
      setScript(currentStyle.sampleScriptEn);
      setSuccessBanner(`Đã nạp kịch bản mẫu Tiếng Anh (${selectedVoice.name}) cho phong cách #${currentStyle.number}!`);
    } else {
      setScript(currentStyle.sampleScript);
      setSuccessBanner(`Đã nạp kịch bản mẫu Tiếng Việt (${selectedVoice.name}) cho phong cách #${currentStyle.number}!`);
    }
    setTimeout(() => setSuccessBanner(null), 2500);
  };

  // =========================================================================
  // HANDLERS: GEMINI SCRIPT OPTIMIZATION (VOICE & LANGUAGE AWARE)
  // =========================================================================
  const handleOptimizeWithGemini = async () => {
    if (!script.trim()) {
      alert("Vui lòng nhập kịch bản trước khi yêu cầu Gemini tối ưu.");
      return;
    }
    const langInfo = getVoiceLanguage(selectedVoice);
    setIsOptimizing(true);
    setOriginalDraftScript(script);
    try {
      const result = await optimizeScriptWithGemini(script, currentStyle.id, selectedVoice, geminiApiKey);
      setOptimizationResult(result);
      setSuccessBanner(
        result.source === "gemini_api"
          ? `✨ Gemini AI đã tối ưu kịch bản sang ${langInfo.name} cho giọng "${selectedVoice.name}" thành công!`
          : `Đã tối ưu kịch bản theo khuôn mẫu ${langInfo.name} (Chế độ Offline).`
      );
      setTimeout(() => setSuccessBanner(null), 4000);
    } catch (err: any) {
      alert(`Lỗi tối ưu kịch bản: ${err.message || err}`);
    } finally {
      setIsOptimizing(false);
    }
  };

  const handleApplyOptimizedScript = () => {
    if (optimizationResult) {
      setScript(optimizationResult.optimizedScript);
      setSuccessBanner(`Đã áp dụng kịch bản tối ưu (${optimizationResult.targetLanguageName}) vào trình soạn thảo!`);
      setOptimizationResult(null);
      setTimeout(() => setSuccessBanner(null), 2500);
    }
  };

  const handleRevertToOriginalScript = () => {
    if (originalDraftScript) {
      setScript(originalDraftScript);
      setSuccessBanner("Đã khôi phục lại kịch bản ban đầu.");
      setTimeout(() => setSuccessBanner(null), 2000);
    }
  };

  const handleSaveApiKey = () => {
    setGeminiApiKey(tempApiKey.trim());
    setStoredGeminiKey(tempApiKey.trim());
    setShowApiKeyModal(false);
    setSuccessBanner("Đã lưu Google Gemini API Key!");
    setTimeout(() => setSuccessBanner(null), 2000);
  };

  // =========================================================================
  // HANDLERS: CHARACTER SELECTION, AUTO-SAVE & CUSTOM PERSISTENCE
  // =========================================================================
  const handleCustomFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    try {
      const previewUrl = URL.createObjectURL(file);
      const buffer = await file.arrayBuffer();
      const bytes = Array.from(new Uint8Array(buffer));
      const cleanName = file.name.replace(/\.[^/.]+$/, "");

      const savedChar = await invokeCommand<CharacterOption>("save_custom_character", {
        name: cleanName,
        filename: file.name,
        data: bytes,
      });

      const newCharOption: CharacterOption = {
        ...savedChar,
        webPath: previewUrl, // immediate browser display
      };

      setCustomCharacters((prev) => [
        newCharOption,
        ...prev.filter((c) => c.filename !== savedChar.filename),
      ]);
      setSelectedCharOption(newCharOption);
      setCustomUploadedPhoto(null);
      setCharCategoryFilter("custom");
      setSuccessBanner(`Đã lưu ảnh nhân vật "${cleanName}" vào thư viện thành công!`);
      setTimeout(() => setSuccessBanner(null), 3000);
    } catch (err: any) {
      alert(`Lỗi khi lưu ảnh nhân vật: ${err.message || err}`);
    } finally {
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  const handleDeleteCustomCharacter = async (char: CharacterOption, e: React.MouseEvent) => {
    e.stopPropagation();
    if (!confirm(`Bạn có chắc muốn xóa nhân vật "${char.name}" khỏi thư viện?`)) return;
    try {
      await invokeCommand("delete_custom_character", { filename: char.filename });
      setCustomCharacters((prev) => prev.filter((c) => c.id !== char.id));
      if (selectedCharOption.id === char.id) {
        setSelectedCharOption(CHARACTER_LIBRARY[0]);
      }
      setSuccessBanner(`Đã xóa nhân vật "${char.name}" khỏi thư viện.`);
      setTimeout(() => setSuccessBanner(null), 2500);
    } catch (err: any) {
      alert(`Lỗi xóa nhân vật: ${err.message || err}`);
    }
  };

  const handleSelectLibraryCharacter = (char: CharacterOption) => {
    setSelectedCharOption(char);
    setCustomUploadedPhoto(null);
  };

  // Combined character library: custom uploaded characters + builtin library
  const allCharacters = useMemo(() => {
    return [...customCharacters, ...CHARACTER_LIBRARY];
  }, [customCharacters]);

  // Filtered characters
  const filteredCharacters = useMemo(() => {
    return allCharacters.filter((char) => {
      const matchCat =
        charCategoryFilter === "all" || char.category === charCategoryFilter;
      const matchSearch =
        !charSearchQuery.trim() ||
        char.name.toLowerCase().includes(charSearchQuery.toLowerCase()) ||
        char.desc.toLowerCase().includes(charSearchQuery.toLowerCase());
      return matchCat && matchSearch;
    });
  }, [allCharacters, charCategoryFilter, charSearchQuery]);

  // Current active character display
  const activeCharacterDisplay = useMemo(() => {
    return {
      name: selectedCharOption.name,
      previewUrl: selectedCharOption.webPath,
      path: selectedCharOption.relPath,
      isCustom: selectedCharOption.category === "custom",
      tag:
        selectedCharOption.category === "custom"
          ? "Ảnh tự tải (Đã lưu)"
          : selectedCharOption.gender === "male"
          ? "MC Nam"
          : "MC Nữ / 3D",
    };
  }, [selectedCharOption]);

  // =========================================================================
  // HANDLERS: TTS VOICES (PROSTUDIO-AI)
  // =========================================================================
  const filteredVoices = useMemo(() => {
    return TTS_VOICES.filter((v) => {
      // Favorite filter or provider tab filter
      if (voiceProviderFilter === "favorites") {
        if (!favoriteVoiceIds.includes(v.id)) return false;
      } else if (voiceProviderFilter !== "all" && v.provider !== voiceProviderFilter) {
        return false;
      }

      const matchGender =
        voiceGenderFilter === "all" || v.gender === voiceGenderFilter;
      const matchCategory =
        voiceCategoryFilter === "all" ||
        v.category === voiceCategoryFilter ||
        v.region === voiceCategoryFilter;
      const matchLanguage =
        voiceLanguageFilter === "all" ||
        (v.lang && (v.lang === voiceLanguageFilter || v.lang.startsWith(voiceLanguageFilter)));
      const matchSearch =
        !voiceSearchQuery.trim() ||
        v.name.toLowerCase().includes(voiceSearchQuery.toLowerCase()) ||
        v.description.toLowerCase().includes(voiceSearchQuery.toLowerCase()) ||
        (v.lang && v.lang.toLowerCase().includes(voiceSearchQuery.toLowerCase())) ||
        (v.region && v.region.toLowerCase().includes(voiceSearchQuery.toLowerCase())) ||
        (v.tags && v.tags.some((t) => t.toLowerCase().includes(voiceSearchQuery.toLowerCase())));
      return matchGender && matchCategory && matchLanguage && matchSearch;
    }).sort((a, b) => {
      // Put favorites first
      const aFav = favoriteVoiceIds.includes(a.id);
      const bFav = favoriteVoiceIds.includes(b.id);
      if (aFav && !bFav) return -1;
      if (!aFav && bFav) return 1;
      return 0;
    });
  }, [voiceProviderFilter, voiceGenderFilter, voiceCategoryFilter, voiceLanguageFilter, voiceSearchQuery, favoriteVoiceIds]);

  const audioRef = useRef<HTMLAudioElement | null>(null);

  const handleTestVoiceAudio = async (
    voice: TtsVoice,
    e?: React.MouseEvent,
    forceNativeSample: boolean = false
  ) => {
    if (e) e.stopPropagation();

    // If currently playing or loading this voice, stop it
    if (testingVoiceId === voice.id || loadingVoiceId === voice.id) {
      if (audioRef.current) {
        audioRef.current.pause();
        audioRef.current = null;
      }
      setTestingVoiceId(null);
      setLoadingVoiceId(null);
      return;
    }

    // Stop any previous audio
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current = null;
    }

    setLoadingVoiceId(voice.id);
    setTestingVoiceId(null);
    try {
      const sampleText = forceNativeSample
        ? getSampleTextForVoice(voice)
        : getSampleTextForVoice(voice, script);

      const res: any = await invokeCommand("preview_tts_voice", {
        text: sampleText,
        voice: voice.id,
        gender: voice.gender,
      });
      if (res?.status === "error") {
        throw new Error(res.message || "Không thể tạo âm thanh giọng đọc");
      }

      if (res?.audio_base64) {
        const mime = res.audio_path && res.audio_path.endsWith(".wav") ? "audio/wav" : "audio/mp3";
        const audio = new Audio(`data:${mime};base64,${res.audio_base64}`);
        audioRef.current = audio;
        audio.onended = () => {
          setTestingVoiceId(null);
          setLoadingVoiceId(null);
          audioRef.current = null;
        };
        audio.onerror = () => {
          setTestingVoiceId(null);
          setLoadingVoiceId(null);
          audioRef.current = null;
        };
        await audio.play();
        setLoadingVoiceId(null);
        setTestingVoiceId(voice.id);
        setSuccessBanner(`Đang phát mẫu giọng: ${voice.name} (${getVoiceLanguage(voice).name})`);
      } else {
        setSuccessBanner(`Đã tổng hợp âm thanh giọng: ${voice.name}`);
        setLoadingVoiceId(null);
        setTestingVoiceId(null);
      }
      setTimeout(() => setSuccessBanner(null), 3500);
    } catch (err: any) {
      setLoadingVoiceId(null);
      setTestingVoiceId(null);
      alert(`Lỗi nghe thử giọng: ${err.message || err}`);
    }
  };

  // =========================================================================
  // HANDLERS: SUBMIT JOB
  // =========================================================================
  const handleCreateJob = async (startImmediately: boolean = false) => {
    if (!script.trim()) {
      alert("Vui lòng nhập kịch bản lời thoại.");
      return;
    }
    setIsSubmitting(true);
    try {
      await invokeCommand("create_job", {
        name: title || "Video Render",
        char: activeCharacterDisplay.name,
        source: activeCharacterDisplay.path,
        script: script,
        voice: selectedVoiceId,
        gender: selectedVoice?.gender,
        voice_provider: selectedVoice?.provider,
        driving: selectedDriving,
        multiplier: multiplier,
        dry_run: dryRun || isTestMode,
      });

      onJobCreated();
      setSuccessBanner(
        startImmediately
          ? "Đã thêm vào hàng đợi và kích hoạt render!"
          : "Đã thêm job vào hàng đợi thành công!"
      );

      if (startImmediately) {
        onStartWorker();
      }

      setTimeout(() => setSuccessBanner(null), 3000);
    } catch (err: any) {
      alert(`Lỗi tạo job: ${err}`);
    } finally {
      setIsSubmitting(false);
    }
  };

  // Script metrics
  const charCount = script.length;
  const wordCount = script.trim() ? script.trim().split(/\s+/).length : 0;
  const estimatedSeconds = wordCount > 0 ? ((wordCount / 140) * 60).toFixed(1) : "0.0";

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-studio-obsidian">
      {/* Top Banner Alert */}
      {successBanner && (
        <div className="bg-emerald-950/90 border-b border-emerald-500/40 px-6 py-2.5 flex items-center justify-between text-emerald-200 text-xs animate-in fade-in slide-in-from-top duration-200 z-30">
          <div className="flex items-center gap-2 font-medium">
            <CheckCircle className="w-4 h-4 text-emerald-400 shrink-0" />
            <span>{successBanner}</span>
          </div>
          <button
            onClick={() => setSuccessBanner(null)}
            className="text-emerald-400 hover:text-white px-2 py-0.5 rounded"
          >
            ✕
          </button>
        </div>
      )}

      {/* TOP BAR: 10 PRESENTATION STYLE PRESETS */}
      <div className="bg-studio-panel border-b border-studio-border px-6 py-3 shrink-0">
        <div className="flex items-center justify-between mb-2">
          <div className="flex items-center gap-2 text-xs font-bold text-slate-300 uppercase tracking-wider">
            <Sparkles className="w-4 h-4 text-studio-cyan" />
            <span>10 Phong cách Thuyết trình & Bối cảnh Studio Tương ứng</span>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setShowStyleGuide(!showStyleGuide)}
              className="text-[11px] text-slate-400 hover:text-studio-cyan flex items-center gap-1 transition-colors"
            >
              <Info className="w-3.5 h-3.5" />
              <span>{showStyleGuide ? "Thu gọn bối cảnh" : "Hiện bối cảnh Studio"}</span>
            </button>
          </div>
        </div>

        {/* Style Preset Buttons Scrollable Bar */}
        <div className="flex items-center gap-2 overflow-x-auto pb-1.5 scrollbar-thin">
          {PRESENTATION_STYLES.map((style) => {
            const isSelected = selectedStyleId === style.id;
            return (
              <button
                key={style.id}
                onClick={() => handleSelectStyle(style)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium whitespace-nowrap flex items-center gap-2 border transition-all ${
                  isSelected
                    ? "bg-studio-accent text-white border-studio-accent shadow-md shadow-indigo-600/30 font-semibold scale-[1.02]"
                    : "bg-studio-card border-studio-border text-slate-300 hover:bg-studio-elevated hover:text-white"
                }`}
              >
                <span className="font-mono text-[10px] opacity-70">#{style.number}</span>
                <span>{style.vietnameseTitle}</span>
                <span className="text-[10px] opacity-60 font-mono">({style.defaultAspectRatio})</span>
              </button>
            );
          })}
        </div>

        {/* Selected Style's Studio Background Visual Card */}
        {showStyleGuide && (
          <div
            className={`mt-2.5 rounded-xl p-3.5 border bg-gradient-to-r ${currentStyle.backgroundTheme} flex items-center justify-between gap-4 text-xs transition-all`}
          >
            <div className="flex items-center gap-4 flex-1">
              {/* Studio Backdrop Visual Badge */}
              <div className="w-24 h-16 rounded-lg bg-black/40 border border-white/10 flex flex-col items-center justify-center p-2 text-center shrink-0 relative overflow-hidden shadow-inner">
                <Film className="w-4 h-4 text-studio-cyan mb-1" />
                <span className="text-[10px] font-mono text-slate-300 font-semibold truncate w-full text-center">
                  {currentStyle.defaultAspectRatio}
                </span>
                <span className="text-[8px] text-slate-400 uppercase tracking-wider">Studio</span>
              </div>

              {/* Background Details & Prompt Highlights */}
              <div className="flex-1 flex flex-col gap-1">
                <div className="flex items-center gap-2">
                  <h4 className="font-semibold text-slate-100 text-sm">
                    {currentStyle.backgroundTitle}
                  </h4>
                  <div className="flex items-center gap-1">
                    {currentStyle.backgroundTags.map((t, idx) => (
                      <span
                        key={idx}
                        className="px-1.5 py-0.5 rounded text-[10px] bg-white/10 text-slate-300 border border-white/5"
                      >
                        {t}
                      </span>
                    ))}
                  </div>
                </div>
                <p className="text-slate-300 text-[11px] leading-relaxed line-clamp-2">
                  {currentStyle.backgroundDescription}
                </p>
                <div className="flex items-center gap-4 mt-0.5 text-[11px] text-slate-400">
                  <span>
                    Chuyển động đầu: <strong className="text-studio-cyan font-mono">{currentStyle.recommendedMultiplier.toFixed(2)}x</strong>
                  </span>
                  <span>•</span>
                  <span>
                    Khuyên dùng: <span className="text-amber-300">{currentStyle.voiceGuideline}</span>
                  </span>
                </div>
              </div>
            </div>

            {/* Quick Actions */}
            <div className="flex flex-col gap-2 shrink-0 border-l border-white/10 pl-4">
              <button
                onClick={handleApplySampleScript}
                className="px-3 py-1.5 rounded-lg bg-white/10 hover:bg-white/20 border border-white/10 text-white text-xs font-medium whitespace-nowrap flex items-center gap-1.5 transition-colors"
                title="Điền kịch bản mẫu phù hợp với phong cách này"
              >
                <FileText className="w-3.5 h-3.5 text-studio-cyan" />
                <span>Nạp kịch bản mẫu</span>
              </button>

              <button
                onClick={handleOptimizeWithGemini}
                disabled={isOptimizing}
                className="px-3 py-1.5 rounded-lg bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-500 hover:to-purple-500 text-white text-xs font-semibold whitespace-nowrap flex items-center gap-1.5 shadow-md shadow-purple-600/20 transition-all disabled:opacity-50"
                title={`Tối ưu hóa kịch bản theo ngôn ngữ ${getVoiceLanguage(selectedVoice).name}`}
              >
                <Sparkles className="w-3.5 h-3.5 text-amber-300 animate-pulse" />
                <span>
                  {isOptimizing
                    ? "Gemini đang tối ưu..."
                    : `Tối ưu Gemini (${getVoiceLanguage(selectedVoice).code.toUpperCase()})`}
                </span>
              </button>
            </div>
          </div>
        )}
      </div>

      {/* MAIN 2-COLUMN STUDIO WORKBENCH */}
      <div className="flex-1 flex overflow-hidden">
        {/* =========================================================================
            LEFT COLUMN: SCRIPT EDITOR & GEMINI SCRIPT OPTIMIZATION (50%)
        ========================================================================= */}
        <div className="flex-1 border-r border-studio-border flex flex-col p-6 overflow-y-auto gap-5">
          {/* Section: Title & Style Header */}
          <div className="flex flex-col gap-2">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-slate-300 tracking-wide uppercase">
                Tiêu đề Video & Kịch bản Lời thoại
              </label>
              <span className="text-[11px] text-studio-cyan font-mono bg-studio-card px-2.5 py-0.5 rounded border border-studio-border">
                Phong cách: #{currentStyle.number} {currentStyle.vietnameseTitle}
              </span>
            </div>
            <input
              type="text"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
              placeholder="Nhập tiêu đề video..."
              className="w-full bg-studio-card border border-studio-border focus:border-studio-accent rounded-lg px-3.5 py-2 text-sm text-slate-100 placeholder-slate-500 outline-none transition-colors"
            />
          </div>

          {/* Script Textarea & Editor */}
          <div className="flex-1 flex flex-col min-h-[220px]">
            <div className="flex items-center justify-between mb-1.5 flex-wrap gap-2">
              <div className="flex items-center gap-2">
                <FileText className="w-3.5 h-3.5 text-studio-accent" />
                <span className="text-xs text-slate-400 font-medium">Kịch bản lời thoại</span>
                <span className="text-[10px] px-2 py-0.5 rounded bg-studio-accent/20 text-studio-cyan font-mono border border-studio-accent/30 flex items-center gap-1">
                  <span>🌐</span>
                  <span>Ngôn ngữ giọng: <strong>{getVoiceLanguage(selectedVoice).name}</strong></span>
                </span>
              </div>

              {/* Gemini Trigger Button & API Key Setup */}
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setShowApiKeyModal(true)}
                  className="text-[11px] text-slate-400 hover:text-studio-cyan flex items-center gap-1 transition-colors"
                  title="Cấu hình Google Gemini API Key"
                >
                  <Settings className="w-3 h-3" />
                  <span>{geminiApiKey ? "API Key: Đã lưu" : "Cấu hình Gemini Key"}</span>
                </button>

                <button
                  onClick={handleOptimizeWithGemini}
                  disabled={isOptimizing}
                  className="px-2.5 py-1 rounded-md bg-studio-accent/20 hover:bg-studio-accent/30 text-studio-cyan border border-studio-accent/40 text-xs font-medium flex items-center gap-1.5 transition-all disabled:opacity-50"
                  title={`Tối ưu kịch bản theo ngôn ngữ ${getVoiceLanguage(selectedVoice).name}`}
                >
                  <Sparkles className="w-3.5 h-3.5 text-amber-300" />
                  <span>
                    {isOptimizing
                      ? "Đang gửi Gemini..."
                      : `✨ Tối ưu kịch bản (${getVoiceLanguage(selectedVoice).code.toUpperCase()})`}
                  </span>
                </button>
              </div>
            </div>

            <textarea
              value={script}
              onChange={(e) => setScript(e.target.value)}
              placeholder="Nhập kịch bản thô của bạn tại đây, sau đó bấm 'Tối ưu kịch bản với Gemini' để AI viết lại chuẩn phong cách đã chọn..."
              className="flex-1 w-full bg-studio-card border border-studio-border focus:border-studio-accent rounded-lg p-3.5 text-sm text-slate-100 placeholder-slate-500 resize-none outline-none leading-relaxed transition-colors font-sans"
            />

            {/* Script Metrics Bar */}
            <div className="flex items-center justify-between mt-2 px-1 text-xs text-slate-400 font-mono">
              <div className="flex items-center gap-4">
                <span>
                  Ký tự: <strong className="text-slate-200">{charCount}</strong>
                </span>
                <span>
                  Từ: <strong className="text-slate-200">{wordCount}</strong>
                </span>
                {originalDraftScript && (
                  <button
                    onClick={handleRevertToOriginalScript}
                    className="text-amber-400 hover:underline flex items-center gap-1 font-sans text-[11px]"
                  >
                    <RotateCcw className="w-3 h-3" />
                    <span>Khôi phục bản gốc</span>
                  </button>
                )}
              </div>
              <div className="flex items-center gap-1.5 text-studio-cyan font-medium">
                <span>Thời lượng ước tính:</span>
                <strong className="text-slate-100 font-mono">~{estimatedSeconds}s</strong>
              </div>
            </div>
          </div>

          {/* Gemini Optimization Comparison Card (If Available) */}
          {optimizationResult && (
            <div className="bg-gradient-to-br from-indigo-950/70 to-purple-950/70 border border-purple-500/30 rounded-xl p-4 flex flex-col gap-3 animate-in fade-in slide-in-from-bottom duration-200">
              <div className="flex items-center justify-between flex-wrap gap-2">
                <div className="flex items-center gap-2 flex-wrap">
                  <Sparkles className="w-4 h-4 text-amber-400" />
                  <span className="font-semibold text-xs text-purple-200">
                    Bản tối ưu ({optimizationResult.styleName})
                  </span>
                  <span className="px-1.5 py-0.5 rounded text-[10px] bg-cyan-500/20 text-cyan-300 font-mono border border-cyan-500/30">
                    🌐 {optimizationResult.targetLanguageName} • {optimizationResult.voiceName}
                  </span>
                  <span className="px-1.5 py-0.5 rounded text-[10px] bg-purple-500/20 text-purple-300 font-mono">
                    {optimizationResult.source === "gemini_api" ? (optimizationResult.modelUsed || "Gemini AI") : "Template Engine"}
                  </span>
                </div>
                <div className="flex items-center gap-2 text-xs">
                  <span className="text-slate-300 font-mono">
                    {optimizationResult.wordCountOptimized} từ (~{optimizationResult.estimatedSecOptimized}s)
                  </span>
                </div>
              </div>

              <p className="text-xs text-slate-200 bg-black/40 border border-white/10 rounded-lg p-3 leading-relaxed whitespace-pre-wrap max-h-36 overflow-y-auto">
                {optimizationResult.optimizedScript}
              </p>

              <div className="flex items-center justify-end gap-2 pt-1">
                <button
                  onClick={() => setOptimizationResult(null)}
                  className="px-3 py-1.5 rounded-lg bg-studio-card hover:bg-studio-elevated text-slate-300 text-xs font-medium border border-studio-border"
                >
                  Bỏ qua
                </button>
                <button
                  onClick={handleApplyOptimizedScript}
                  className="px-4 py-1.5 rounded-lg bg-studio-accent hover:bg-studio-accentHover text-white text-xs font-semibold flex items-center gap-1.5 shadow-md shadow-indigo-600/30"
                >
                  <Check className="w-3.5 h-3.5" />
                  <span>Áp dụng vào kịch bản chính</span>
                </button>
              </div>
            </div>
          )}

          {/* Spoken Voice Summary Card */}
          <div className="bg-studio-card border border-studio-border rounded-xl p-3.5 flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div className="w-10 h-10 rounded-xl bg-studio-accent/20 border border-studio-accent/40 flex items-center justify-center text-studio-cyan shrink-0">
                <Volume2 className="w-5 h-5" />
              </div>
              <div>
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="text-xs font-semibold text-slate-100">
                    {selectedVoice.name}
                  </span>
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-studio-accent/20 border border-studio-accent/40 text-studio-cyan">
                    🌐 {getVoiceLanguage(selectedVoice).name}
                  </span>
                  <span className="px-1.5 py-0.5 rounded text-[10px] font-mono bg-studio-elevated border border-studio-border text-slate-300 uppercase">
                    {selectedVoice.provider}
                  </span>
                </div>
                <p className="text-[11px] text-slate-400 truncate max-w-sm">
                  {selectedVoice.description}
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2">
              <button
                onClick={(e) => handleTestVoiceAudio(selectedVoice, e)}
                disabled={loadingVoiceId === selectedVoice.id}
                className={`px-3 py-1.5 rounded-lg text-xs border flex items-center gap-1.5 transition-colors ${
                  testingVoiceId === selectedVoice.id
                    ? "bg-amber-950/80 text-amber-300 border-amber-600/50 hover:bg-amber-900 font-semibold"
                    : loadingVoiceId === selectedVoice.id
                    ? "bg-indigo-950 text-indigo-300 border-indigo-700/50 cursor-wait font-medium"
                    : "bg-studio-elevated hover:bg-studio-hover text-studio-cyan border-studio-border"
                }`}
              >
                {loadingVoiceId === selectedVoice.id ? (
                  <>
                    <Loader2 className="w-3.5 h-3.5 animate-spin text-indigo-300" />
                    <span>Đang tải...</span>
                  </>
                ) : testingVoiceId === selectedVoice.id ? (
                  <>
                    <span className="w-2 h-2 rounded-sm bg-amber-400 animate-pulse" />
                    <span>Dừng nghe</span>
                  </>
                ) : (
                  <>
                    <Play className="w-3 h-3 fill-current" />
                    <span>Nghe thử</span>
                  </>
                )}
              </button>
              <button
                onClick={() => setShowVoiceModal(true)}
                className="px-3 py-1.5 rounded-lg bg-studio-accent/20 hover:bg-studio-accent/30 text-xs text-studio-cyan border border-studio-accent/40 font-semibold flex items-center gap-1.5 transition-colors shadow-sm"
                title="Mở Kho Mẫu Giọng ProStudio AI đầy đủ 370+ giọng, bộ lọc ngôn ngữ, yêu thích"
              >
                <Sparkles className="w-3.5 h-3.5 text-studio-cyan" />
                <span>Kho Mẫu Giọng</span>
              </button>
            </div>
          </div>
        </div>

        {/* =========================================================================
            RIGHT COLUMN: CHARACTER PHOTO PICKER, PROSTUDIO TTS & CONTROLS (50%)
        ========================================================================= */}
        <div className="flex-1 flex flex-col p-6 overflow-y-auto gap-4">
          {/* Sub-Navigation Tabs */}
          <div className="flex items-center bg-studio-card border border-studio-border rounded-xl p-1 gap-1 shrink-0">
            <button
              onClick={() => setRightTab("character")}
              className={`flex-1 py-2 px-3 rounded-lg text-xs font-semibold flex items-center justify-center gap-2 transition-all ${
                rightTab === "character"
                  ? "bg-studio-accent text-white shadow-md shadow-indigo-600/30"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <User className="w-3.5 h-3.5" />
              <span>Ảnh Nhân vật ({CHARACTER_LIBRARY.length}+)</span>
            </button>

            <button
              onClick={() => setRightTab("voice")}
              className={`flex-1 py-2 px-3 rounded-lg text-xs font-semibold flex items-center justify-center gap-2 transition-all ${
                rightTab === "voice"
                  ? "bg-studio-accent text-white shadow-md shadow-indigo-600/30"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <Volume2 className="w-3.5 h-3.5" />
              <span>Giọng đọc TTS ProStudio ({TTS_VOICES.length})</span>
            </button>

            <button
              onClick={() => setRightTab("motion")}
              className={`flex-1 py-2 px-3 rounded-lg text-xs font-semibold flex items-center justify-center gap-2 transition-all ${
                rightTab === "motion"
                  ? "bg-studio-accent text-white shadow-md shadow-indigo-600/30"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              <SlidersHorizontal className="w-3.5 h-3.5" />
              <span>Cử động & Render</span>
            </button>
          </div>

          {/* TAB 1: CHARACTER PORTRAIT SELECTION */}
          {rightTab === "character" && (
            <div className="flex-1 flex flex-col gap-4">
              {/* Active Portrait Preview Card */}
              <div className="bg-studio-card border border-studio-border rounded-xl p-3.5 flex items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <div className="w-14 h-14 rounded-xl bg-slate-800 border border-studio-accent/40 overflow-hidden relative shrink-0 shadow-md">
                    <img
                      src={activeCharacterDisplay.previewUrl}
                      alt={activeCharacterDisplay.name}
                      className="w-full h-full object-cover"
                      onError={(e) => {
                        // Fallback placeholder icon if local path fails to load directly
                        (e.target as HTMLElement).style.display = "none";
                      }}
                    />
                    <div className="absolute inset-0 bg-gradient-to-t from-black/60 to-transparent flex items-end justify-center pb-0.5">
                      <span className="text-[9px] text-white font-mono">1080p</span>
                    </div>
                  </div>
                  <div className="flex flex-col gap-0.5">
                    <div className="flex items-center gap-2">
                      <h4 className="text-xs font-bold text-slate-100 truncate max-w-[220px]">
                        {activeCharacterDisplay.name}
                      </h4>
                      <span className="px-1.5 py-0.5 rounded text-[9px] bg-studio-emerald/20 text-studio-emerald font-semibold border border-studio-emerald/30">
                        {activeCharacterDisplay.tag}
                      </span>
                    </div>
                    <span className="text-[11px] text-slate-400 truncate max-w-[280px]">
                      {activeCharacterDisplay.path}
                    </span>
                    <span className="text-[10px] text-studio-cyan font-mono flex items-center gap-1">
                      <Check className="w-3 h-3 text-studio-cyan" />
                      <span>Sẵn sàng tạo cử động chân dung</span>
                    </span>
                  </div>
                </div>

                {/* Upload Button */}
                <div>
                  <input
                    type="file"
                    ref={fileInputRef}
                    onChange={handleCustomFileUpload}
                    accept="image/png,image/jpeg,image/jpg,image/webp"
                    className="hidden"
                  />
                  <button
                    onClick={() => fileInputRef.current?.click()}
                    className="px-3 py-2 rounded-xl bg-studio-elevated hover:bg-studio-hover border border-studio-border text-studio-cyan text-xs font-semibold flex items-center gap-1.5 transition-colors whitespace-nowrap"
                  >
                    <Upload className="w-3.5 h-3.5" />
                    <span>Tải ảnh từ máy...</span>
                  </button>
                </div>
              </div>

              {/* Character Library Browser */}
              <div className="bg-studio-card border border-studio-border rounded-xl p-3.5 flex-1 flex flex-col gap-3 min-h-[300px]">
                <div className="flex items-center justify-between gap-2">
                  <div className="flex items-center gap-1 overflow-x-auto scrollbar-none">
                    {[
                      { id: "all", label: `Tất cả (${allCharacters.length})` },
                      { id: "custom", label: `Tự tải lên (${customCharacters.length})` },
                      {
                        id: "male",
                        label: `MC Nam (${allCharacters.filter((c) => c.category === "male").length})`,
                      },
                      {
                        id: "female",
                        label: `MC Nữ (${allCharacters.filter((c) => c.category === "female").length})`,
                      },
                      {
                        id: "anime",
                        label: `3D Pixar (${allCharacters.filter((c) => c.category === "anime").length})`,
                      },
                      {
                        id: "angle",
                        label: `Góc quay (${allCharacters.filter((c) => c.category === "angle").length})`,
                      },
                    ].map((tab) => (
                      <button
                        key={tab.id}
                        onClick={() => setCharCategoryFilter(tab.id)}
                        className={`px-2.5 py-1 rounded-md text-[11px] font-medium whitespace-nowrap transition-colors ${
                          charCategoryFilter === tab.id
                            ? "bg-studio-accent text-white"
                            : "bg-studio-elevated text-slate-400 hover:text-white"
                        }`}
                      >
                        {tab.label}
                      </button>
                    ))}
                  </div>

                  {/* Search Character */}
                  <div className="relative w-36">
                    <Search className="w-3 h-3 text-slate-500 absolute left-2 top-2" />
                    <input
                      type="text"
                      value={charSearchQuery}
                      onChange={(e) => setCharSearchQuery(e.target.value)}
                      placeholder="Tìm ảnh..."
                      className="w-full bg-studio-elevated border border-studio-border rounded-md pl-6 pr-2 py-1 text-[11px] text-slate-200 placeholder-slate-500 outline-none focus:border-studio-accent"
                    />
                  </div>
                </div>

                {/* Character Thumbnails Grid */}
                <div className="grid grid-cols-4 gap-2.5 overflow-y-auto max-h-[320px] pr-1 scrollbar-thin">
                  {filteredCharacters.map((char) => {
                    const isSelected = selectedCharOption.id === char.id;
                    return (
                      <div
                        key={char.id}
                        onClick={() => handleSelectLibraryCharacter(char)}
                        className={`cursor-pointer rounded-xl border p-2 flex flex-col gap-1.5 transition-all group relative ${
                          isSelected
                            ? "bg-studio-card border-studio-accent ring-2 ring-studio-accent shadow-md shadow-indigo-600/30 scale-[1.02]"
                            : "bg-studio-elevated/70 border-studio-border hover:border-slate-500 hover:bg-studio-elevated"
                        }`}
                      >
                        <div className="w-full aspect-square rounded-lg bg-slate-800 overflow-hidden relative">
                          <img
                            src={char.webPath}
                            alt={char.name}
                            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-200"
                            loading="lazy"
                          />
                          {char.category === "custom" && (
                            <button
                              onClick={(e) => handleDeleteCustomCharacter(char, e)}
                              title="Xóa nhân vật khỏi thư viện"
                              className="absolute top-1 left-1 w-5 h-5 rounded-full bg-rose-950/80 hover:bg-rose-700 text-rose-300 hover:text-white flex items-center justify-center transition-colors shadow z-10"
                            >
                              <Trash2 className="w-3 h-3" />
                            </button>
                          )}
                          {isSelected && (
                            <div className="absolute top-1 right-1 w-4 h-4 rounded-full bg-studio-accent text-white flex items-center justify-center text-[10px] shadow">
                              ✓
                            </div>
                          )}
                        </div>
                        <div className="flex flex-col">
                          <span className="text-[11px] font-semibold text-slate-200 truncate">
                            {char.name}
                          </span>
                          <span className="text-[9px] text-slate-500 truncate">
                            {char.desc}
                          </span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              </div>
            </div>
          )}

          {/* TAB 2: TTS PROVIDER & VOICE SELECTION (PROSTUDIO-AI) */}
          {rightTab === "voice" && (
            <div className="flex-1 flex flex-col gap-3 min-h-[360px]">
              {/* Header with full modal launcher */}
              <div className="flex items-center justify-between pb-1">
                <div className="flex items-center gap-2">
                  <span className="text-xs font-semibold text-slate-200">
                    Danh sách giọng đọc ({filteredVoices.length}/{TTS_VOICES.length})
                  </span>
                </div>
                <button
                  onClick={() => setShowVoiceModal(true)}
                  className="px-3 py-1.5 rounded-lg bg-indigo-600/30 hover:bg-indigo-600/50 text-indigo-300 border border-indigo-500/40 text-xs font-semibold flex items-center gap-1.5 transition-all shadow-sm"
                  title="Mở Kho Mẫu Giọng ProStudio AI toàn màn hình (370+ giọng, bộ lọc ngôn ngữ, yêu thích)"
                >
                  <Sparkles className="w-3.5 h-3.5 text-indigo-300" />
                  <span>Mở Kho Mẫu Giọng (370+ Giọng)</span>
                </button>
              </div>

              {/* Provider Filter Tabs */}
              <div className="flex items-center gap-1.5 overflow-x-auto scrollbar-none pb-1">
                {[
                  { id: "all", label: `Tất cả (${TTS_VOICES.length})` },
                  { id: "favorites", label: `⭐ Yêu thích (${favoriteVoiceIds.length})` },
                  { id: "vieneu", label: `VieNeu-TTS (${TTS_VOICES.filter((v) => v.provider === "vieneu").length})` },
                  { id: "edge-tts", label: `Edge-TTS (${TTS_VOICES.filter((v) => v.provider === "edge-tts").length})` },
                  { id: "capcut", label: `CapCut (${TTS_VOICES.filter((v) => v.provider === "capcut").length})` },
                ].map((p) => (
                  <button
                    key={p.id}
                    onClick={() => setVoiceProviderFilter(p.id)}
                    className={`px-3 py-1.5 rounded-lg text-xs font-semibold whitespace-nowrap transition-colors ${
                      voiceProviderFilter === p.id
                        ? "bg-studio-accent text-white shadow-sm"
                        : "bg-studio-card text-slate-400 hover:text-white border border-studio-border"
                    }`}
                  >
                    {p.label}
                  </button>
                ))}
              </div>

              {/* Sub-Filters: Gender & Language & Categories & Search */}
              <div className="flex items-center justify-between gap-2 flex-wrap">
                <div className="flex items-center gap-1.5 flex-wrap">
                  {/* Gender Filter */}
                  <div className="flex items-center bg-studio-card border border-studio-border rounded-lg p-0.5 text-[11px]">
                    <button
                      onClick={() => setVoiceGenderFilter("all")}
                      className={`px-2 py-0.5 rounded ${voiceGenderFilter === "all" ? "bg-studio-elevated text-white font-medium" : "text-slate-400"}`}
                    >
                      Tất cả
                    </button>
                    <button
                      onClick={() => setVoiceGenderFilter("male")}
                      className={`px-2 py-0.5 rounded ${voiceGenderFilter === "male" ? "bg-studio-elevated text-white font-medium" : "text-slate-400"}`}
                    >
                      Nam
                    </button>
                    <button
                      onClick={() => setVoiceGenderFilter("female")}
                      className={`px-2 py-0.5 rounded ${voiceGenderFilter === "female" ? "bg-studio-elevated text-white font-medium" : "text-slate-400"}`}
                    >
                      Nữ
                    </button>
                  </div>

                  {/* Language Filter */}
                  <select
                    value={voiceLanguageFilter}
                    onChange={(e) => setVoiceLanguageFilter(e.target.value)}
                    className="bg-studio-card border border-studio-border rounded-lg px-2 py-1 text-[11px] text-slate-200 outline-none max-w-[150px]"
                  >
                    <option value="all">Mọi ngôn ngữ ({availableLanguages.length})</option>
                    {availableLanguages.map((langCode) => (
                      <option key={langCode} value={langCode}>
                        {formatLanguageDisplay(langCode)}
                      </option>
                    ))}
                  </select>

                  {/* Region / Category Filter */}
                  <select
                    value={voiceCategoryFilter}
                    onChange={(e) => setVoiceCategoryFilter(e.target.value)}
                    className="bg-studio-card border border-studio-border rounded-lg px-2.5 py-1 text-[11px] text-slate-200 outline-none"
                  >
                    <option value="all">Mọi thể loại & vùng miền</option>
                    <option value="north">Miền Bắc</option>
                    <option value="south">Miền Nam</option>
                    <option value="central">Miền Trung</option>
                    <option value="news">Bản tin / Thời sự</option>
                    <option value="story">Kể chuyện / Audio Book</option>
                    <option value="social">TikTok / Vui nhộn / Meme</option>
                    <option value="natural">Tâm sự / Thân mật</option>
                    <option value="buddhist">Trầm ấm / Tĩnh tâm</option>
                    <option value="tech">Công nghệ / Lập trình</option>
                  </select>
                </div>

                {/* Search */}
                <div className="relative w-36">
                  <Search className="w-3 h-3 text-slate-500 absolute left-2 top-2" />
                  <input
                    type="text"
                    value={voiceSearchQuery}
                    onChange={(e) => setVoiceSearchQuery(e.target.value)}
                    placeholder="Tìm tên, tone..."
                    className="w-full bg-studio-card border border-studio-border rounded-lg pl-6 pr-2 py-1 text-[11px] text-slate-200 placeholder-slate-500 outline-none focus:border-studio-accent"
                  />
                </div>
              </div>

              {/* Voice Cards Gallery List */}
              <div className="flex-1 overflow-y-auto max-h-[380px] flex flex-col gap-2 pr-1 scrollbar-thin">
                {filteredVoices.map((voice) => {
                  const isSelected = selectedVoiceId === voice.id;
                  const isTesting = testingVoiceId === voice.id;
                  const isFavorite = favoriteVoiceIds.includes(voice.id);
                  const langInfo = getVoiceLanguage(voice);

                  return (
                    <div
                      key={voice.id}
                      onClick={() => setSelectedVoiceId(voice.id)}
                      className={`cursor-pointer rounded-xl border p-3 flex items-center justify-between gap-3 transition-all ${
                        isSelected
                          ? "bg-studio-card border-studio-accent ring-1 ring-studio-accent shadow-md shadow-indigo-600/20"
                          : "bg-studio-card/80 border-studio-border hover:border-slate-600 hover:bg-studio-elevated"
                      }`}
                    >
                      <div className="flex items-center gap-3">
                        <div
                          className={`w-9 h-9 rounded-lg flex items-center justify-center font-bold text-xs shrink-0 ${
                            voice.gender === "male"
                              ? "bg-blue-950 text-blue-300 border border-blue-700/50"
                              : "bg-pink-950 text-pink-300 border border-pink-700/50"
                          }`}
                        >
                          {voice.gender === "male" ? "Nam" : "Nữ"}
                        </div>

                        <div className="flex flex-col gap-0.5">
                          <div className="flex items-center gap-1.5 flex-wrap">
                            <span className="text-xs font-bold text-slate-100">
                              {voice.name}
                            </span>
                            <span
                              className={`px-1.5 py-0.2 rounded text-[9px] font-mono uppercase ${
                                voice.provider === "vieneu"
                                  ? "bg-indigo-950 text-indigo-300 border border-indigo-700/40"
                                  : voice.provider === "capcut"
                                  ? "bg-pink-950 text-pink-300 border border-pink-700/40"
                                  : "bg-emerald-950 text-emerald-300 border border-emerald-700/40"
                              }`}
                            >
                              {voice.provider}
                            </span>
                            <span className="px-1.5 py-0.2 rounded text-[9px] font-mono bg-studio-accent/20 border border-studio-accent/30 text-studio-cyan">
                              🌐 {langInfo.name}
                            </span>
                            {(voice.tags || []).slice(0, 2).map((t, idx) => (
                              <span
                                key={idx}
                                className="px-1.5 py-0.2 rounded text-[9px] bg-slate-800 text-slate-400 border border-slate-700"
                              >
                                {t}
                              </span>
                            ))}
                          </div>
                          <p className="text-[11px] text-slate-400 line-clamp-1">
                            {voice.description}
                          </p>
                        </div>
                      </div>

                      <div className="flex items-center gap-2 shrink-0">
                        {/* Star Favorite Toggle */}
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleToggleFavoriteVoice(voice.id);
                          }}
                          className={`p-1.5 rounded-lg border transition-colors ${
                            isFavorite
                              ? "bg-amber-500/20 text-amber-400 border-amber-500/40"
                              : "bg-studio-card text-slate-500 border-transparent hover:text-slate-300 hover:border-studio-border"
                          }`}
                          title={isFavorite ? "Bỏ yêu thích" : "Lưu vào yêu thích"}
                        >
                          <Star className={`w-3.5 h-3.5 ${isFavorite ? "fill-amber-400" : ""}`} />
                        </button>

                        <button
                          onClick={(e) => handleTestVoiceAudio(voice, e, true)}
                          disabled={loadingVoiceId === voice.id}
                          className={`px-2.5 py-1 rounded-md text-[11px] border flex items-center gap-1 transition-colors ${
                            testingVoiceId === voice.id
                              ? "bg-amber-950/80 text-amber-300 border-amber-600/50 hover:bg-amber-900 font-semibold"
                              : loadingVoiceId === voice.id
                              ? "bg-indigo-950 text-indigo-300 border-indigo-700/50 cursor-wait font-medium"
                              : "bg-studio-elevated hover:bg-studio-hover text-studio-cyan border-studio-border"
                          }`}
                          title={testingVoiceId === voice.id ? "Dừng phát âm thanh" : loadingVoiceId === voice.id ? "Đang tạo âm thanh..." : "Nghe thử giọng này"}
                        >
                          {loadingVoiceId === voice.id ? (
                            <>
                              <Loader2 className="w-3 h-3 animate-spin text-indigo-300" />
                              <span>Đang tải...</span>
                            </>
                          ) : testingVoiceId === voice.id ? (
                            <>
                              <span className="w-2 h-2 rounded-sm bg-amber-400 animate-pulse" />
                              <span>Dừng</span>
                            </>
                          ) : (
                            <>
                              <Play className="w-3 h-3 fill-current" />
                              <span>Nghe thử</span>
                            </>
                          )}
                        </button>
                        {isSelected && (
                          <div className="w-5 h-5 rounded-full bg-studio-accent text-white flex items-center justify-center text-xs">
                            ✓
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}

          {/* TAB 3: MOTION & RENDERING CONTROLS */}
          {rightTab === "motion" && (
            <div className="bg-studio-card border border-studio-border rounded-xl p-4 flex flex-col gap-4">
              <label className="text-xs font-semibold text-slate-300 uppercase tracking-wide flex items-center gap-2">
                <Sliders className="w-4 h-4 text-studio-accent" />
                <span>Tham số chuyển động ({currentStyle.name} Tuned)</span>
              </label>

              {/* Driving Template */}
              <div className="flex flex-col gap-1.5">
                <span className="text-xs text-slate-400">Mẫu chuyển động đầu (Driving Template):</span>
                <select
                  value={selectedDriving}
                  onChange={(e) => setSelectedDriving(e.target.value)}
                  className="w-full bg-studio-elevated border border-studio-border rounded-lg px-3 py-2 text-xs text-slate-100 outline-none focus:border-studio-accent"
                >
                  <option value="reference_head_driving.mp4">
                    reference_head_driving.mp4 (Gật gù đĩnh đạc, ổn định vai - Khuyến nghị)
                  </option>
                  <option value="natural_driving_template.mp4">
                    natural_driving_template.mp4 (Phong cách tự nhiên, chớp mắt sinh học)
                  </option>
                </select>
              </div>

              {/* Multiplier Slider */}
              <div className="flex flex-col gap-2">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-400">Hệ số biên độ lắc đầu (Multiplier):</span>
                  <span className="font-mono font-bold text-studio-cyan">{multiplier.toFixed(2)}x</span>
                </div>
                <input
                  type="range"
                  min="0.30"
                  max="0.85"
                  step="0.01"
                  value={multiplier}
                  onChange={(e) => setMultiplier(parseFloat(e.target.value))}
                  className="w-full accent-indigo-500 cursor-pointer"
                />
                <div className="flex justify-between text-[10px] text-slate-500 font-mono">
                  <span>0.30x (Calm & Mindful)</span>
                  <span>0.40x (News/Doc)</span>
                  <span>0.55x (Chuẩn MC)</span>
                  <span>0.68x (Social/TikTok)</span>
                </div>
              </div>

              {/* Framing & Driving Policy */}
              <div className="grid grid-cols-2 gap-3 pt-1">
                <div>
                  <span className="text-xs text-slate-400 block mb-1">Chính sách Driving:</span>
                  <select
                    value={drivingPolicy}
                    onChange={(e) => setDrivingPolicy(e.target.value as "hold" | "loop")}
                    className="w-full bg-studio-elevated border border-studio-border rounded-lg px-3 py-2 text-xs text-slate-100 outline-none focus:border-studio-accent"
                  >
                    <option value="hold">Hold (Giữ pose cuối tự nhiên)</option>
                    <option value="loop">Loop (Lặp lại mượt)</option>
                  </select>
                </div>

                <div>
                  <span className="text-xs text-slate-400 block mb-1">Tỷ lệ khung hình:</span>
                  <div className="grid grid-cols-3 gap-1">
                    {(["16:9", "9:16", "1:1"] as const).map((ratio) => (
                      <button
                        key={ratio}
                        type="button"
                        onClick={() => setAspectRatio(ratio)}
                        className={`py-1.5 rounded text-xs font-mono font-medium border ${
                          aspectRatio === ratio
                            ? "bg-studio-accent text-white border-studio-accent"
                            : "bg-studio-elevated border-studio-border text-slate-300 hover:bg-studio-hover"
                        }`}
                      >
                        {ratio}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* Checkboxes */}
              <div className="flex items-center gap-6 pt-2 border-t border-studio-border/60">
                <label className="flex items-center gap-2 cursor-pointer text-xs text-slate-300 select-none">
                  <input
                    type="checkbox"
                    checked={torsoMotion}
                    onChange={(e) => setTorsoMotion(e.target.checked)}
                    className="rounded bg-studio-elevated border-studio-border text-indigo-500 focus:ring-0"
                  />
                  <span>Đồng bộ nhịp thở thân trên (Torso Kinematics)</span>
                </label>

                <label className="flex items-center gap-2 cursor-pointer text-xs text-slate-300 select-none">
                  <input
                    type="checkbox"
                    checked={dryRun}
                    onChange={(e) => setDryRun(e.target.checked)}
                    className="rounded bg-studio-elevated border-studio-border text-indigo-500 focus:ring-0"
                  />
                  <span className="text-studio-amber">Dry-Run (Kiểm tra an toàn máy hiện tại)</span>
                </label>
              </div>
            </div>
          )}

          {/* Action Buttons: Add to Queue & Render Now */}
          <div className="mt-auto pt-3 flex items-center gap-3">
            <button
              onClick={() => handleCreateJob(false)}
              disabled={isSubmitting}
              className="flex-1 py-3 px-4 rounded-xl bg-studio-card border border-studio-border hover:border-slate-500 text-slate-200 text-sm font-semibold flex items-center justify-center gap-2 transition-all hover:bg-studio-elevated disabled:opacity-50"
            >
              <Layers className="w-4 h-4 text-studio-cyan" />
              <span>Thêm vào Hàng đợi</span>
            </button>

            <button
              onClick={() => handleCreateJob(true)}
              disabled={isSubmitting}
              className="flex-1 py-3 px-4 rounded-xl bg-studio-accent hover:bg-studio-accentHover text-white text-sm font-semibold flex items-center justify-center gap-2 shadow-lg shadow-indigo-600/30 transition-all disabled:opacity-50"
            >
              <Play className="w-4 h-4 fill-current" />
              <span>Render ngay (Sequential)</span>
            </button>
          </div>
        </div>
      </div>

      {/* =========================================================================
          MODAL: GEMINI API KEY SETUP
      ========================================================================= */}
      {showApiKeyModal && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm flex items-center justify-center p-4 z-50 animate-in fade-in duration-150">
          <div className="bg-studio-panel border border-studio-border rounded-2xl w-full max-w-md p-6 flex flex-col gap-4 shadow-2xl">
            <div className="flex items-center justify-between border-b border-studio-border pb-3">
              <div className="flex items-center gap-2 font-bold text-slate-100 text-sm">
                <Sparkles className="w-4 h-4 text-studio-cyan" />
                <span>Cấu hình Google Gemini API Key</span>
              </div>
              <button
                onClick={() => setShowApiKeyModal(false)}
                className="text-slate-400 hover:text-white"
              >
                ✕
              </button>
            </div>

            <p className="text-xs text-slate-300 leading-relaxed">
              Nhập API Key của Google Gemini để kích hoạt tính năng tối ưu kịch bản tự động theo 10 phong cách dẫn dắt. Khóa API được lưu cục bộ trên máy của bạn.
            </p>

            <div className="flex flex-col gap-1.5">
              <label className="text-xs font-medium text-slate-400">Gemini API Key:</label>
              <input
                type="password"
                value={tempApiKey}
                onChange={(e) => setTempApiKey(e.target.value)}
                placeholder="AIzaSy..."
                className="w-full bg-studio-card border border-studio-border focus:border-studio-accent rounded-lg px-3 py-2 text-sm text-slate-100 font-mono outline-none"
              />
              <span className="text-[11px] text-slate-500">
                Chưa có khóa? Lấy miễn phí tại:{" "}
                <a
                  href="https://aistudio.google.com/app/apikey"
                  target="_blank"
                  rel="noreferrer"
                  className="text-studio-cyan hover:underline"
                >
                  Google AI Studio
                </a>
              </span>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-studio-border">
              <button
                onClick={() => setShowApiKeyModal(false)}
                className="px-4 py-2 rounded-lg bg-studio-card hover:bg-studio-elevated text-slate-300 text-xs font-medium"
              >
                Hủy
              </button>
              <button
                onClick={handleSaveApiKey}
                className="px-4 py-2 rounded-lg bg-studio-accent hover:bg-studio-accentHover text-white text-xs font-semibold"
              >
                Lưu cấu hình
              </button>
            </div>
          </div>
        </div>
      )}



      {/* =========================================================================
          MODAL: KHO MẪU GIỌNG PROSTUDIO AI (370+ GIỌNG, ĐA NGÔN NGỮ)
      ========================================================================= */}
      <VoiceLibraryModal
        isOpen={showVoiceModal}
        onClose={() => setShowVoiceModal(false)}
        voices={TTS_VOICES}
        selectedVoiceId={selectedVoiceId}
        onSelectVoice={(voice) => {
          setSelectedVoiceId(voice.id);
          const lang = getVoiceLanguage(voice);
          setSuccessBanner(`Đã chọn giọng: ${voice.name} (${lang.name} • ${voice.provider.toUpperCase()})`);
          setTimeout(() => setSuccessBanner(null), 2500);
        }}
        testingVoiceId={testingVoiceId}
        loadingVoiceId={loadingVoiceId}
        onTestVoice={handleTestVoiceAudio}
        favoriteVoiceIds={favoriteVoiceIds}
        onToggleFavorite={handleToggleFavoriteVoice}
        currentScriptText={script}
      />
    </div>
  );
};
