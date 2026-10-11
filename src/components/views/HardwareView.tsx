import React from "react";
import { Cpu, HardDrive, CheckCircle2, XCircle, AlertCircle, RefreshCw } from "lucide-react";
import { HardwareStatus, ManagedModelComponent } from "../../types";

interface Props {
  hardware: HardwareStatus | null;
  onRefresh: () => void;
  isRefreshing: boolean;
}

const StatusMark: React.FC<{ ready: boolean }> = ({ ready }) => ready
  ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
  : <XCircle className="w-3.5 h-3.5 text-rose-400" />;

const ModelSummary: React.FC<{ title: string; component?: Partial<ManagedModelComponent> }> = ({ title, component }) => {
  if (!component) {
    return <div className="p-3 rounded-lg bg-studio-elevated text-xs text-slate-400">{title}: chưa có trạng thái model.</div>;
  }
  const assetsReady = component.assets_total !== undefined && component.assets_total > 0 && component.assets_ready === component.assets_total;
  const sourceStatus = component.source?.status || "chưa kiểm tra";
  const runtimeStatus = component.runtime?.status || "chưa kiểm tra";
  const sourceReady = sourceStatus === "ready" || sourceStatus === "match";
  const runtimeReady = runtimeStatus === "ready";
  const assetsReadyCount = component.assets_ready ?? 0;
  const assetsTotal = component.assets_total ?? component.assets?.length ?? 0;
  return (
    <div className="p-3 rounded-lg bg-studio-elevated space-y-2">
      <div className="flex items-center justify-between gap-3">
        <span className="text-xs font-semibold text-slate-200">{title}</span>
        <span className={`text-[10px] font-semibold ${assetsReady ? "text-emerald-400" : "text-amber-300"}`}>
          Model {assetsReadyCount}/{assetsTotal}{assetsTotal === 0 ? " · chưa kiểm tra" : ""}
        </span>
      </div>
      {component.directory && <p className="text-[10px] text-slate-500 break-all">{component.directory}</p>}
      <div className="grid grid-cols-2 gap-2 text-[10px] text-slate-400">
        <span className="flex items-center gap-1.5"><StatusMark ready={sourceReady} /> Source: {sourceStatus}</span>
        <span className="flex items-center gap-1.5"><StatusMark ready={runtimeReady} /> Python runtime: {runtimeStatus}</span>
      </div>
    </div>
  );
};

export const HardwareView: React.FC<Props> = ({ hardware, onRefresh, isRefreshing }) => {
  const gpu = hardware?.system.gpu;
  const hostAvailable = hardware?.available !== false;
  const hasGpuMetrics = hostAvailable && !!gpu?.available && gpu.total_vram_mb > 0;
  const totalVramGb = hasGpuMetrics ? (gpu.total_vram_mb / 1024).toFixed(1) : null;
  const freeVramGb = hasGpuMetrics ? (gpu.free_vram_mb / 1024).toFixed(1) : null;
  const usedPercent = hasGpuMetrics
    ? Math.max(0, Math.min(100, Math.round(((gpu.total_vram_mb - gpu.free_vram_mb) / gpu.total_vram_mb) * 100)))
    : null;
  const engines = hardware?.engines;

  return (
    <div className="flex-1 flex flex-col overflow-y-auto bg-studio-obsidian p-6 gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-base font-bold text-slate-100 flex items-center gap-2">
            <Cpu className="w-5 h-5 text-studio-accent" /> Chẩn đoán phần cứng và model
          </h2>
          <p className="text-xs text-slate-400 mt-1">Hiển thị số liệu đọc được từ ứng dụng desktop; không suy đoán CUDA hay VRAM.</p>
        </div>
        <button
          onClick={onRefresh}
          disabled={isRefreshing}
          className="px-3 py-1.5 rounded-lg bg-studio-card border border-studio-border text-slate-300 hover:text-white text-xs font-semibold flex items-center gap-1.5 disabled:opacity-50"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${isRefreshing ? "animate-spin text-studio-cyan" : ""}`} /> Kiểm tra lại
        </button>
      </div>

      {hardware?.message && (
        <div className="p-3 rounded-lg bg-amber-950/30 border border-amber-800/50 text-xs text-amber-200 flex gap-2">
          <AlertCircle className="w-4 h-4 shrink-0" /> {hardware.message}
        </div>
      )}

      <section className="bg-studio-card border border-studio-border rounded-xl p-5 flex flex-col gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-indigo-950/60 border border-indigo-700/40 flex items-center justify-center text-studio-cyan"><Cpu className="w-5 h-5" /></div>
          <div>
            <h3 className="text-sm font-bold text-slate-100">{gpu?.available ? gpu.name : "GPU chưa được phát hiện"}</h3>
            <p className="text-xs text-slate-400">Nền tảng: {hardware?.system.platform || "Chưa kiểm tra"}</p>
          </div>
        </div>
        {hasGpuMetrics && usedPercent !== null ? (
          <div className="space-y-2 pt-3 border-t border-studio-border/60">
            <div className="flex items-center justify-between text-xs font-mono text-slate-300">
              <span>VRAM đang dùng: {((gpu.total_vram_mb - gpu.free_vram_mb) / 1024).toFixed(1)} / {totalVramGb} GB</span>
              <span>Khả dụng: {freeVramGb} GB</span>
            </div>
            <div className="w-full h-2 bg-studio-elevated rounded-full overflow-hidden">
              <div className={`h-full transition-all ${usedPercent > 85 ? "bg-rose-500" : usedPercent > 65 ? "bg-amber-400" : "bg-studio-accent"}`} style={{ width: `${usedPercent}%` }} />
            </div>
          </div>
        ) : (
          <p className="text-xs text-slate-400 border-t border-studio-border/60 pt-3">Chưa có số liệu VRAM thực tế. Hãy mở desktop app trên máy chạy core và kiểm tra lại.</p>
        )}
      </section>

      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        <section className="bg-studio-card border border-studio-border rounded-xl p-5 space-y-3">
          <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wide flex items-center gap-2"><HardDrive className="w-4 h-4" /> Công cụ hệ thống</h3>
          <div className="space-y-2 text-xs">
            <div className="flex justify-between p-2 rounded bg-studio-elevated"><span>Python</span><span className="text-slate-300 font-mono truncate max-w-[65%]" title={hardware?.system.python}>{hardware?.system.python || "Chưa phát hiện"}</span></div>
            <div className="flex justify-between p-2 rounded bg-studio-elevated"><span>FFmpeg</span><span className="flex items-center gap-1.5"><StatusMark ready={!!hardware?.system.ffmpeg} />{hardware?.system.ffmpeg ? "Sẵn sàng" : "Chưa phát hiện"}</span></div>
            <div className="flex justify-between p-2 rounded bg-studio-elevated"><span>FFprobe</span><span className="flex items-center gap-1.5"><StatusMark ready={!!hardware?.system.ffprobe} />{hardware?.system.ffprobe ? "Sẵn sàng" : "Chưa phát hiện"}</span></div>
          </div>
        </section>

        <section className="bg-studio-card border border-studio-border rounded-xl p-5 space-y-3">
          <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wide">Core render</h3>
          <ModelSummary title="Echo Flash · tạo chuyển động" component={engines?.echo} />
          <ModelSummary title="MuseTalk · đồng bộ khẩu hình" component={engines?.musetalk} />
        </section>
      </div>
    </div>
  );
};
