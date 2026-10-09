import React, { useState } from "react";
import {
  ShieldCheck,
  Lock,
  Unlock,
  Key,
  Eye,
  EyeOff,
  RefreshCw,
  DownloadCloud,
  CheckCircle2,
  AlertTriangle,
  ExternalLink,
  Cpu,
  Folder,
  Sparkles,
  Clock,
  Terminal,
} from "lucide-react";
import { LicenseStatus, UpdateInfo } from "../../types";
import {
  getStoredGeminiKey,
  setStoredGeminiKey,
  getStoredGeminiModel,
  setStoredGeminiModel,
  fetchAvailableGeminiModels,
} from "../../services/geminiOptimizer";

interface Props {
  license: LicenseStatus | null;
  onRefreshLicense: () => Promise<void>;
  updateInfo: UpdateInfo | null;
  isCheckingUpdate: boolean;
  onCheckUpdate: () => Promise<void>;
  invokeCommand: <T>(cmd: string, args?: Record<string, any>) => Promise<T>;
  onOpenFolder: () => void;
}

export const SettingsView: React.FC<Props> = ({
  license,
  onRefreshLicense,
  updateInfo,
  isCheckingUpdate,
  onCheckUpdate,
  invokeCommand,
  onOpenFolder,
}) => {
  // Key input state
  const [activationKey, setActivationKey] = useState("");
  const [showKeyPassword, setShowKeyPassword] = useState(false);
  const [isActivating, setIsActivating] = useState(false);
  const [licenseMessage, setLicenseMessage] = useState<{
    type: "success" | "error";
    text: string;
  } | null>(null);

  // Gemini Key & Model state
  const [geminiKey, setGeminiKey] = useState(getStoredGeminiKey());
  const [geminiModel, setGeminiModel] = useState(getStoredGeminiModel());
  const [showGeminiKey, setShowGeminiKey] = useState(false);
  const [geminiSaved, setGeminiSaved] = useState(false);
  const [isDetectingModels, setIsDetectingModels] = useState(false);
  const [modelDetectMessage, setModelDetectMessage] = useState<string | null>(null);
  const [detectedModelList, setDetectedModelList] = useState<string[]>([]);

  // Handle license activation
  const handleActivate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activationKey.trim()) {
      setLicenseMessage({ type: "error", text: "Vui lòng nhập mã bảo mật." });
      return;
    }

    setIsActivating(true);
    setLicenseMessage(null);

    try {
      await invokeCommand<LicenseStatus>("verify_license_key", { key: activationKey.trim() });
      setLicenseMessage({
        type: "success",
        text: "Kích hoạt bản quyền thiết bị thành công! Ứng dụng đã được mở khóa vĩnh viễn.",
      });
      setActivationKey("");
      await onRefreshLicense();
    } catch (err: any) {
      setLicenseMessage({
        type: "error",
        text: typeof err === "string" ? err : err.message || "Mã kích hoạt không chính xác.",
      });
    } finally {
      setIsActivating(false);
    }
  };

  // Save Gemini Key & Model
  const handleSaveGeminiKey = (e: React.FormEvent) => {
    e.preventDefault();
    setStoredGeminiKey(geminiKey.trim());
    if (geminiModel.trim()) {
      setStoredGeminiModel(geminiModel.trim());
    }
    setGeminiSaved(true);
    setTimeout(() => setGeminiSaved(false), 3000);
  };

  // Auto-detect models from Google API
  const handleDetectModels = async () => {
    const key = geminiKey.trim() || getStoredGeminiKey();
    if (!key) {
      setModelDetectMessage("Vui lòng nhập API Key trước khi dò tìm model.");
      return;
    }
    setIsDetectingModels(true);
    setModelDetectMessage(null);
    try {
      const models = await fetchAvailableGeminiModels(key);
      if (models.length === 0) {
        setModelDetectMessage("Không tìm thấy model nào hỗ trợ generateContent hoặc API Key không hợp lệ.");
      } else {
        setDetectedModelList(models);
        // Find best flash model
        const flashModels = models.filter((m) => m.toLowerCase().includes("flash"));
        flashModels.sort((a, b) => b.localeCompare(a));
        const picked = flashModels[0] || models[0];
        setGeminiModel(picked);
        setStoredGeminiModel(picked);
        setModelDetectMessage(`Đã tìm thấy ${models.length} model. Đã tự động chọn "${picked}".`);
      }
    } catch (err: any) {
      setModelDetectMessage(`Lỗi kết nối Google API: ${err.message || err}`);
    } finally {
      setIsDetectingModels(false);
    }
  };

  const handleOpenUrl = (url?: string) => {
    if (url) {
      invokeCommand("open_external_url", { url });
    }
  };

  const isActivated = license?.is_activated ?? false;
  const daysRemaining = license?.days_remaining ?? 30;
  const totalDays = license?.total_trial_days ?? 30;
  const usedDays = Math.max(0, totalDays - daysRemaining);
  const progressPercent = Math.min(100, Math.round((usedDays / totalDays) * 100));

  return (
    <div className="flex-1 flex flex-col overflow-y-auto bg-studio-obsidian p-6 gap-6 font-sans">
      {/* View Header */}
      <div>
        <h2 className="text-base font-bold text-slate-100 flex items-center gap-2">
          <ShieldCheck className="w-5 h-5 text-studio-accent" />
          <span>Cài đặt Hệ thống & Bảo mật Bản quyền</span>
        </h2>
        <p className="text-xs text-slate-400 mt-1">
          Quản lý bản quyền kích hoạt máy trạm, cấu hình bộ cập nhật từ xa và tích hợp Google AI.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* ========================================================================= */}
        {/* CARD 1: BẢN QUYỀN & MẬT KHẨU KÍCH HOẠT */}
        {/* ========================================================================= */}
        <div className="bg-studio-card border border-studio-border rounded-xl p-5 flex flex-col gap-4 shadow-sm">
          <div className="flex items-center justify-between pb-3 border-b border-studio-border/60">
            <div className="flex items-center gap-2.5">
              <div
                className={`w-9 h-9 rounded-lg flex items-center justify-center ${
                  isActivated
                    ? "bg-emerald-950/60 border border-emerald-700/40 text-emerald-400"
                    : "bg-amber-950/60 border border-amber-700/40 text-amber-400"
                }`}
              >
                {isActivated ? <CheckCircle2 className="w-5 h-5" /> : <Lock className="w-5 h-5" />}
              </div>
              <div>
                <h3 className="text-sm font-bold text-slate-100">Bản quyền & Kích hoạt Thiết bị</h3>
                <p className="text-xs text-slate-400">
                  {isActivated ? "Giấy phép vĩnh viễn" : "Bản quyền dùng thử 30 ngày"}
                </p>
              </div>
            </div>

            <span
              className={`px-2.5 py-1 rounded-full text-xs font-semibold border ${
                isActivated
                  ? "bg-emerald-950/80 text-emerald-300 border-emerald-700"
                  : "bg-amber-950/80 text-amber-300 border-amber-700"
              }`}
            >
              {isActivated ? "Đã Kích Hoạt Vĩnh Viễn" : `Dùng thử: Còn ${daysRemaining} ngày`}
            </span>
          </div>

          {/* Device info */}
          <div className="space-y-2.5 text-xs font-mono bg-studio-elevated/60 p-3.5 rounded-lg border border-studio-border/40">
            <div className="flex items-center justify-between">
              <span className="text-slate-400">Mã Thiết bị (Hardware ID):</span>
              <span className="text-slate-200 font-semibold truncate max-w-[220px]" title={license?.device_id}>
                {license?.device_id || "Đang nhận diện..."}
              </span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-400">Ngày kích hoạt lần đầu:</span>
              <span className="text-slate-300">{license?.first_run_date || "Hôm nay"}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-400">Trạng thái bảo vệ:</span>
              <span className="text-emerald-400 font-semibold flex items-center gap-1">
                <ShieldCheck className="w-3.5 h-3.5" />
                <span>Mã hóa phần cứng đa tầng</span>
              </span>
            </div>
          </div>

          {/* Trial progress bar if not activated */}
          {!isActivated && (
            <div className="flex flex-col gap-1.5 pt-1">
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400 flex items-center gap-1">
                  <Clock className="w-3.5 h-3.5 text-amber-400" />
                  <span>Thời hạn sử dụng thử:</span>
                </span>
                <span className="text-amber-300 font-semibold font-mono">
                  {usedDays} / {totalDays} ngày đã dùng
                </span>
              </div>
              <div className="w-full h-2 bg-studio-elevated rounded-full overflow-hidden">
                <div
                  className={`h-full transition-all duration-300 ${
                    progressPercent > 80 ? "bg-studio-rose" : "bg-studio-amber"
                  }`}
                  style={{ width: `${progressPercent}%` }}
                />
              </div>
              <p className="text-[11px] text-slate-500 italic mt-0.5">
                * Nếu không kích hoạt, sau 30 ngày ứng dụng sẽ tự động khóa lại trên thiết bị này.
              </p>
            </div>
          )}

          {/* Activation Form */}
          {!isActivated ? (
            <form onSubmit={handleActivate} className="flex flex-col gap-3 pt-2">
              <label className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
                <Key className="w-3.5 h-3.5 text-studio-cyan" />
                <span>Mật khẩu kích hoạt bản quyền:</span>
              </label>

              <div className="relative">
                <input
                  type={showKeyPassword ? "text" : "password"}
                  value={activationKey}
                  onChange={(e) => setActivationKey(e.target.value)}
                  placeholder="Nhập mã bảo mật để kích hoạt vĩnh viễn..."
                  className="w-full bg-studio-elevated border border-studio-border focus:border-studio-accent rounded-lg px-3.5 py-2.5 text-xs text-slate-100 placeholder-slate-500 outline-none pr-10 font-mono"
                />
                <button
                  type="button"
                  onClick={() => setShowKeyPassword(!showKeyPassword)}
                  className="absolute right-2.5 top-2.5 text-slate-400 hover:text-slate-200"
                >
                  {showKeyPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>

              {licenseMessage && (
                <div
                  className={`p-2.5 rounded-lg text-xs flex items-center gap-2 border ${
                    licenseMessage.type === "success"
                      ? "bg-emerald-950/40 border-emerald-600/50 text-emerald-300"
                      : "bg-rose-950/40 border-rose-600/50 text-rose-300"
                  }`}
                >
                  {licenseMessage.type === "success" ? (
                    <CheckCircle2 className="w-4 h-4 shrink-0" />
                  ) : (
                    <AlertTriangle className="w-4 h-4 shrink-0" />
                  )}
                  <span>{licenseMessage.text}</span>
                </div>
              )}

              <button
                type="submit"
                disabled={isActivating || !activationKey.trim()}
                className="w-full py-2.5 rounded-lg bg-studio-accent hover:bg-studio-accentHover disabled:opacity-50 text-white text-xs font-semibold flex items-center justify-center gap-2 transition-all shadow-md shadow-indigo-600/20"
              >
                {isActivating ? (
                  <>
                    <RefreshCw className="w-4 h-4 animate-spin" />
                    <span>Đang xác thực mã...</span>
                  </>
                ) : (
                  <>
                    <Unlock className="w-4 h-4" />
                    <span>Kích Hoạt Bản Quyền Vĩnh Viễn</span>
                  </>
                )}
              </button>
            </form>
          ) : (
            <div className="bg-emerald-950/30 border border-emerald-600/40 rounded-lg p-3.5 flex items-center gap-3">
              <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0" />
              <div className="text-xs">
                <p className="text-emerald-200 font-semibold">
                  Thiết bị này đã được kích hoạt bản quyền vĩnh viễn
                </p>
                <p className="text-slate-400 mt-0.5">
                  Tất cả các tính năng kết xuất AI, batch và giọng đọc đã được mở khóa đầy đủ.
                </p>
              </div>
            </div>
          )}
        </div>

        {/* ========================================================================= */}
        {/* CARD 2: CẬP NHẬT TỪ XA (REMOTE AUTO-UPDATER) */}
        {/* ========================================================================= */}
        <div className="bg-studio-card border border-studio-border rounded-xl p-5 flex flex-col gap-4 shadow-sm">
          <div className="flex items-center justify-between pb-3 border-b border-studio-border/60">
            <div className="flex items-center gap-2.5">
              <div className="w-9 h-9 rounded-lg bg-indigo-950/60 border border-indigo-700/40 text-studio-cyan flex items-center justify-center">
                <DownloadCloud className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-sm font-bold text-slate-100">Cập nhật Phần mềm Từ xa</h3>
                <p className="text-xs text-slate-400">Kết nối repository quanittb/video-creative-release</p>
              </div>
            </div>

            <button
              onClick={onCheckUpdate}
              disabled={isCheckingUpdate}
              className="px-3 py-1.5 rounded-lg bg-studio-elevated hover:bg-slate-700 border border-studio-border text-slate-200 text-xs font-semibold flex items-center gap-1.5 transition-all disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isCheckingUpdate ? "animate-spin text-studio-cyan" : ""}`} />
              <span>Kiểm tra bản mới</span>
            </button>
          </div>

          {/* Current version info */}
          <div className="space-y-2 text-xs font-mono bg-studio-elevated/60 p-3.5 rounded-lg border border-studio-border/40">
            <div className="flex items-center justify-between">
              <span className="text-slate-400">Phiên bản hiện tại:</span>
              <span className="text-studio-cyan font-bold">v{updateInfo?.current_version || "1.0.0"}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-400">Kênh phát hành:</span>
              <span className="text-slate-200">GitHub Release (Chính thức)</span>
            </div>
          </div>

          {/* Update detection state */}
          {updateInfo?.has_update ? (
            <div
              className={`p-4 rounded-xl border flex flex-col gap-3 ${
                updateInfo.mandatory
                  ? "bg-rose-950/30 border-rose-600/60"
                  : "bg-indigo-950/30 border-indigo-600/60"
              }`}
            >
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <span
                    className={`px-2 py-0.5 rounded text-[10px] font-bold uppercase ${
                      updateInfo.mandatory
                        ? "bg-rose-900 text-rose-200"
                        : "bg-indigo-900 text-indigo-200"
                    }`}
                  >
                    {updateInfo.mandatory ? "Bắt buộc cập nhật" : "Bản cập nhật mới"}
                  </span>
                  <span className="text-xs font-bold text-slate-100 font-mono">
                    v{updateInfo.latest_version}
                  </span>
                </div>

                {updateInfo.release_date && (
                  <span className="text-[11px] text-slate-400 font-mono">
                    {updateInfo.release_date}
                  </span>
                )}
              </div>

              {updateInfo.title && (
                <h4 className="text-xs font-bold text-slate-200">{updateInfo.title}</h4>
              )}

              {/* Changelog */}
              {updateInfo.changelog && updateInfo.changelog.length > 0 && (
                <div className="space-y-1 text-xs text-slate-300">
                  <span className="text-[11px] text-slate-400 font-semibold block">Những điểm mới:</span>
                  <ul className="list-disc list-inside space-y-0.5 text-slate-300 pl-1">
                    {updateInfo.changelog.map((log: string, idx: number) => (
                      <li key={idx} className="leading-relaxed">
                        {log}
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Action buttons */}
              <div className="flex items-center gap-2 pt-1">
                {updateInfo.download_url && (
                  <button
                    onClick={() => handleOpenUrl(updateInfo.download_url)}
                    className="flex-1 py-2 rounded-lg bg-studio-accent hover:bg-studio-accentHover text-white text-xs font-semibold flex items-center justify-center gap-2 shadow-sm"
                  >
                    <DownloadCloud className="w-3.5 h-3.5" />
                    <span>Tải Bản Cập Nhật</span>
                  </button>
                )}
                {updateInfo.release_page_url && (
                  <button
                    onClick={() => handleOpenUrl(updateInfo.release_page_url)}
                    className="px-3 py-2 rounded-lg bg-studio-elevated hover:bg-slate-700 text-slate-300 text-xs font-semibold flex items-center gap-1.5"
                  >
                    <ExternalLink className="w-3.5 h-3.5" />
                    <span>Trang Release</span>
                  </button>
                )}
              </div>
            </div>
          ) : (
            <div className="bg-studio-elevated/40 border border-studio-border/50 rounded-lg p-3.5 flex items-center gap-3">
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
              <div className="text-xs text-slate-300">
                <span>Ứng dụng đang ở phiên bản mới nhất (v{updateInfo?.current_version || "1.0.0"}). Không có bản cập nhật nào đang chờ.</span>
              </div>
            </div>
          )}

          {/* Repo Link */}
          <div className="mt-auto pt-2 flex items-center justify-between text-xs text-slate-500">
            <span>Repository: quanittb/video-creative-release</span>
            <button
              onClick={() => handleOpenUrl("https://github.com/quanittb/video-creative-release")}
              className="text-studio-cyan hover:underline flex items-center gap-1 text-[11px]"
            >
              <span>Mở GitHub</span>
              <ExternalLink className="w-3 h-3" />
            </button>
          </div>
        </div>

        {/* ========================================================================= */}
        {/* CARD 3: CẤU HÌNH GOOGLE AI GEMINI */}
        {/* ========================================================================= */}
        <div className="bg-studio-card border border-studio-border rounded-xl p-5 flex flex-col gap-4 shadow-sm">
          <div className="flex items-center gap-2.5 pb-3 border-b border-studio-border/60">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-tr from-indigo-600 to-cyan-500 flex items-center justify-center text-white">
              <Sparkles className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-100">Google Gemini API Key</h3>
              <p className="text-xs text-slate-400">Hỗ trợ tối ưu hóa kịch bản và gợi ý phong cách</p>
            </div>
          </div>

          <form onSubmit={handleSaveGeminiKey} className="flex flex-col gap-3">
            <label className="text-xs font-semibold text-slate-300">
              API Key (Google AI Studio):
            </label>

            <div className="relative">
              <input
                type={showGeminiKey ? "text" : "password"}
                value={geminiKey}
                onChange={(e) => setGeminiKey(e.target.value)}
                placeholder="AIzaSy..."
                className="w-full bg-studio-elevated border border-studio-border focus:border-studio-accent rounded-lg px-3.5 py-2.5 text-xs text-slate-100 placeholder-slate-500 outline-none pr-10 font-mono"
              />
              <button
                type="button"
                onClick={() => setShowGeminiKey(!showGeminiKey)}
                className="absolute right-2.5 top-2.5 text-slate-400 hover:text-slate-200"
              >
                {showGeminiKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>

            <div className="flex flex-col gap-1.5 pt-1">
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold text-slate-300">
                  Model Gemini (Tự động thích ứng):
                </label>
                <button
                  type="button"
                  onClick={handleDetectModels}
                  disabled={isDetectingModels}
                  className="text-[11px] text-studio-cyan hover:underline flex items-center gap-1 font-semibold disabled:opacity-50"
                  title="Gọi Google ModelService.ListModels để tìm model hoạt động tốt nhất"
                >
                  <RefreshCw className={`w-3 h-3 ${isDetectingModels ? "animate-spin" : ""}`} />
                  <span>{isDetectingModels ? "Đang dò tìm..." : "Dò tìm Model từ API"}</span>
                </button>
              </div>

              {detectedModelList.length > 0 ? (
                <select
                  value={geminiModel}
                  onChange={(e) => setGeminiModel(e.target.value)}
                  className="w-full bg-studio-elevated border border-studio-border focus:border-studio-accent rounded-lg px-3.5 py-2 text-xs text-slate-100 font-mono outline-none"
                >
                  {detectedModelList.map((m) => (
                    <option key={m} value={m}>
                      {m}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  type="text"
                  value={geminiModel}
                  onChange={(e) => setGeminiModel(e.target.value)}
                  placeholder="gemini-2.5-flash hoặc gemini-2.0-flash..."
                  className="w-full bg-studio-elevated border border-studio-border focus:border-studio-accent rounded-lg px-3.5 py-2 text-xs text-slate-100 placeholder-slate-500 outline-none font-mono"
                />
              )}

              {modelDetectMessage && (
                <span className="text-[11px] text-studio-cyan font-mono leading-tight">
                  {modelDetectMessage}
                </span>
              )}
            </div>

            <div className="flex items-center justify-between pt-1">
              <button
                type="button"
                onClick={() => handleOpenUrl("https://aistudio.google.com/app/apikey")}
                className="text-xs text-studio-cyan hover:underline flex items-center gap-1"
              >
                <span>Lấy API Key miễn phí tại Google AI</span>
                <ExternalLink className="w-3 h-3" />
              </button>

              <button
                type="submit"
                className="px-4 py-2 rounded-lg bg-studio-accent hover:bg-studio-accentHover text-white text-xs font-semibold transition-all shadow-sm"
              >
                {geminiSaved ? "Đã lưu thành công!" : "Lưu Cấu Hình"}
              </button>
            </div>
          </form>
        </div>

        {/* ========================================================================= */}
        {/* CARD 4: LƯU TRỮ VÀ TIỆN ÍCH */}
        {/* ========================================================================= */}
        <div className="bg-studio-card border border-studio-border rounded-xl p-5 flex flex-col gap-4 shadow-sm">
          <div className="flex items-center gap-2.5 pb-3 border-b border-studio-border/60">
            <div className="w-9 h-9 rounded-lg bg-studio-elevated text-slate-300 flex items-center justify-center">
              <Folder className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-sm font-bold text-slate-100">Lưu trữ & Thư mục Dự án</h3>
              <p className="text-xs text-slate-400">Đường dẫn tệp xuất và tài nguyên</p>
            </div>
          </div>

          <div className="space-y-3 text-xs">
            <div className="flex items-center justify-between p-3 rounded-lg bg-studio-elevated">
              <div>
                <span className="text-slate-200 font-bold block">Thư mục Video Đầu Ra</span>
                <span className="text-[11px] text-slate-400 font-mono">./output/</span>
              </div>
              <button
                onClick={onOpenFolder}
                className="px-3 py-1.5 rounded-lg bg-studio-card hover:bg-studio-border border border-studio-border text-slate-200 font-semibold text-xs flex items-center gap-1.5"
              >
                <Folder className="w-3.5 h-3.5" />
                <span>Mở Thư Mục</span>
              </button>
            </div>

            <div className="flex items-center justify-between p-3 rounded-lg bg-studio-elevated">
              <div>
                <span className="text-slate-200 font-bold block">Thư viện Giọng đọc Cục bộ</span>
                <span className="text-[11px] text-slate-400 font-mono">VieNeu ONNX, CapCut API, Edge-TTS (350+ giọng)</span>
              </div>
              <span className="text-emerald-400 font-bold font-mono">350+ Voices</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
