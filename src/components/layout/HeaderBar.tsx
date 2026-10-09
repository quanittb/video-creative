import React from "react";
import { Play, Square, Folder, RefreshCw, Cpu, FlaskConical, Zap, ShieldCheck, DownloadCloud, Clock } from "lucide-react";
import { HardwareStatus, LicenseStatus, UpdateInfo } from "../../types";

interface Props {
  hardware: HardwareStatus | null;
  license?: LicenseStatus | null;
  updateInfo?: UpdateInfo | null;
  onNavigateSettings?: () => void;
  isWorkerRunning: boolean;
  isTestMode: boolean;
  onToggleTestMode: () => void;
  onToggleWorker: () => void;
  onOpenOutputFolder: () => void;
  onRefresh: () => void;
  isRefreshing: boolean;
}

export const HeaderBar: React.FC<Props> = ({
  hardware,
  license,
  updateInfo,
  onNavigateSettings,
  isWorkerRunning,
  isTestMode,
  onToggleTestMode,
  onToggleWorker,
  onOpenOutputFolder,
  onRefresh,
  isRefreshing,
}) => {
  const gpu = hardware?.system.gpu;
  const isGpuLow = gpu ? gpu.total_vram_mb < 6000 : false;
  const totalVramGb = gpu ? (gpu.total_vram_mb / 1024).toFixed(1) : "12.0";
  const freeVramGb = gpu ? (gpu.free_vram_mb / 1024).toFixed(1) : "9.8";
  const usedPercent = gpu && gpu.total_vram_mb > 0
    ? Math.round(((gpu.total_vram_mb - gpu.free_vram_mb) / gpu.total_vram_mb) * 100)
    : 18;

  return (
    <header className="h-14 bg-studio-panel border-b border-studio-border px-4 flex items-center justify-between select-none z-10 shrink-0">
      {/* Left: Project & Breadcrumbs */}
      <div className="flex items-center gap-3">
        <h1 className="text-sm font-bold tracking-wider text-slate-100 flex items-center gap-2">
          <span>VIDEO CREATIVE STUDIO</span>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-studio-elevated text-studio-cyan border border-studio-border">
            LOCAL v1.0
          </span>
        </h1>

        {/* License Pill */}
        {license && (
          <button
            onClick={onNavigateSettings}
            title={
              license.is_activated
                ? "Thiết bị đã được kích hoạt bản quyền vĩnh viễn"
                : `Bản dùng thử: Còn ${license.days_remaining} ngày. Nhấp để xem cài đặt bản quyền.`
            }
            className={`px-2 py-0.5 rounded text-[10px] font-semibold flex items-center gap-1 border transition-colors ${
              license.is_activated
                ? "bg-emerald-950/60 text-emerald-300 border-emerald-700/60 hover:bg-emerald-900/60"
                : "bg-amber-950/60 text-amber-300 border-amber-700/60 hover:bg-amber-900/60"
            }`}
          >
            {license.is_activated ? (
              <>
                <ShieldCheck className="w-3 h-3 text-emerald-400" />
                <span>Bản quyền Vĩnh viễn</span>
              </>
            ) : (
              <>
                <Clock className="w-3 h-3 text-amber-400" />
                <span>Dùng thử: {license.days_remaining} ngày</span>
              </>
            )}
          </button>
        )}

        {/* Optional Update Banner Pill */}
        {updateInfo?.has_update && !updateInfo.mandatory && (
          <button
            onClick={onNavigateSettings}
            title="Có bản cập nhật mới! Nhấp để xem chi tiết."
            className="px-2 py-0.5 rounded text-[10px] font-semibold bg-indigo-950/70 text-studio-cyan border border-indigo-600/60 hover:bg-indigo-900/70 flex items-center gap-1 animate-pulse"
          >
            <DownloadCloud className="w-3 h-3" />
            <span>Có bản mới v{updateInfo.latest_version}</span>
          </button>
        )}

        <span className="text-slate-600">/</span>
        <span className="text-xs text-slate-400 font-medium">Studio Video AI</span>
      </div>

      {/* Right: Hardware Monitor & Queue Actions */}
      <div className="flex items-center gap-3">
        {/* Test Mode / Production Mode Toggle */}
        <button
          onClick={onToggleTestMode}
          title={
            isTestMode
              ? "Đang ở chế độ Thử nghiệm: Không dùng VRAM thật, mô phỏng các chặng an toàn để bạn kiểm tra giao diện và batch trên máy này."
              : "Đang ở chế độ Render Thật: Kích hoạt GPU inference đầy đủ (dành cho máy trạm RTX 3060 12GB)."
          }
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-all border ${
            isTestMode
              ? "bg-amber-950/40 text-amber-300 border-amber-600/50 hover:bg-amber-900/40"
              : "bg-emerald-950/40 text-emerald-300 border-emerald-600/50 hover:bg-emerald-900/40"
          }`}
        >
          {isTestMode ? (
            <>
              <FlaskConical className="w-3.5 h-3.5 text-amber-400" />
              <span>Chế độ Test (Máy hiện tại)</span>
            </>
          ) : (
            <>
              <Zap className="w-3.5 h-3.5 text-emerald-400 fill-current" />
              <span>Render Thật (RTX 3060)</span>
            </>
          )}
        </button>

        {/* GPU & VRAM Pill */}
        <div className="flex items-center gap-2 bg-studio-card border border-studio-border rounded-lg px-3 py-1.5 shadow-sm">
          <Cpu className="w-4 h-4 text-studio-accent" />
          <div className="flex flex-col">
            <div className="flex items-center gap-1.5 text-[11px] font-mono">
              <span className="text-slate-300 font-semibold">{gpu?.name || "NVIDIA GPU"}</span>
              <span className="text-slate-500">|</span>
              <span className={isGpuLow ? "text-studio-amber" : "text-studio-emerald"}>
                {freeVramGb}GB Free {isGpuLow ? "(Máy Test)" : ""}
              </span>
            </div>
            {/* Mini VRAM Bar */}
            <div className="w-28 h-1 bg-studio-elevated rounded-full overflow-hidden mt-0.5">
              <div
                className={`h-full transition-all duration-300 ${
                  usedPercent > 85 ? "bg-studio-rose" : usedPercent > 65 ? "bg-studio-amber" : "bg-studio-accent"
                }`}
                style={{ width: `${usedPercent}%` }}
              />
            </div>
          </div>
        </div>

        {/* Worker Control Button */}
        <button
          onClick={onToggleWorker}
          className={`px-3 py-1.5 rounded-lg text-xs font-semibold flex items-center gap-2 transition-all shadow-sm ${
            isWorkerRunning
              ? "bg-studio-rose/20 text-rose-300 border border-studio-rose/40 hover:bg-studio-rose/30"
              : "bg-studio-accent text-white hover:bg-studio-accentHover shadow-indigo-500/20"
          }`}
        >
          {isWorkerRunning ? (
            <>
              <Square className="w-3.5 h-3.5 fill-current" />
              <span>Dừng Queue</span>
            </>
          ) : (
            <>
              <Play className="w-3.5 h-3.5 fill-current" />
              <span>Chạy Queue Tuần Tự</span>
            </>
          )}
        </button>

        {/* Open Output Folder */}
        <button
          onClick={onOpenOutputFolder}
          title="Mở thư mục video đầu ra (output)"
          className="p-2 rounded-lg bg-studio-card border border-studio-border text-slate-300 hover:text-white hover:bg-studio-elevated transition-colors"
        >
          <Folder className="w-4 h-4" />
        </button>

        {/* Refresh button */}
        <button
          onClick={onRefresh}
          disabled={isRefreshing}
          title="Làm mới trạng thái"
          className="p-2 rounded-lg bg-studio-card border border-studio-border text-slate-400 hover:text-white hover:bg-studio-elevated transition-colors disabled:opacity-50"
        >
          <RefreshCw className={`w-4 h-4 ${isRefreshing ? "animate-spin text-studio-cyan" : ""}`} />
        </button>
      </div>
    </header>
  );
};
