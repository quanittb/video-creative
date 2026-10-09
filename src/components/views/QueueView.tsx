import React, { useState, useRef, useEffect } from "react";
import {
  Terminal,
  Play,
  RotateCcw,
  XCircle,
  ExternalLink,
  Trash2,
  CheckCircle2,
  Clock,
  AlertTriangle,
  Flame,
  ChevronDown,
} from "lucide-react";
import { RenderJob } from "../../types";

interface Props {
  jobs: RenderJob[];
  isWorkerRunning: boolean;
  workerLogs: string[];
  onStartWorker: () => void;
  onStopWorker: () => void;
  onCancelJob: (id: string) => void;
  onRetryJob: (id: string) => void;
  onClearCompleted: () => void;
  onOpenVideo: (path?: string) => void;
}

export const QueueView: React.FC<Props> = ({
  jobs,
  isWorkerRunning,
  workerLogs,
  onStartWorker,
  onStopWorker,
  onCancelJob,
  onRetryJob,
  onClearCompleted,
  onOpenVideo,
}) => {
  const [autoScroll, setAutoScroll] = useState(true);
  const logContainerRef = useRef<HTMLDivElement>(null);

  // Find active running job or first queued
  const activeJob = jobs.find((j) => j.status === "running");
  const queuedJobs = jobs.filter((j) => j.status === "queued");
  const completedOrFailedJobs = jobs.filter(
    (j) => j.status === "completed" || j.status === "failed" || j.status === "cancelled"
  );

  // Auto-scroll logs
  useEffect(() => {
    if (autoScroll && logContainerRef.current) {
      logContainerRef.current.scrollTop = logContainerRef.current.scrollHeight;
    }
  }, [workerLogs, autoScroll]);

  // Stage steps
  const stages = [
    { id: "audio_tts", label: "1. Tổng hợp Giọng đọc" },
    { id: "liveportrait", label: "2. Cử động nhân vật 3D" },
    { id: "musetalk", label: "3. Đồng bộ khẩu hình Lip-Sync" },
    { id: "verifying", label: "4. Kiểm định Chất lượng" },
  ];

  const getStageStep = (stageName: string): number => {
    if (stageName.includes("audio")) return 1;
    if (stageName.includes("liveportrait") || stageName.includes("torso")) return 2;
    if (stageName.includes("musetalk") || stageName.includes("lip")) return 3;
    if (stageName.includes("verify") || stageName.includes("final")) return 4;
    return 0;
  };

  const activeStep = activeJob ? getStageStep(activeJob.stage) : 0;

  return (
    <div className="flex-1 flex flex-col overflow-hidden bg-studio-obsidian">
      {/* Top Hero Section: Active Render Status */}
      <div className="bg-studio-panel border-b border-studio-border p-6 flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div
              className={`w-3.5 h-3.5 rounded-full ${
                activeJob
                  ? "bg-studio-cyan animate-ping"
                  : isWorkerRunning
                  ? "bg-studio-emerald animate-pulse"
                  : "bg-slate-600"
              }`}
            />
            <h2 className="text-sm font-bold text-slate-100 uppercase tracking-wide">
              {activeJob
                ? `Đang Render: ${activeJob.name}`
                : isWorkerRunning
                ? "Worker đang chờ Job mới trong hàng đợi..."
                : "Hàng đợi đang tạm dừng"}
            </h2>
            {activeJob && (
              <span className="text-xs font-mono px-2 py-0.5 rounded bg-indigo-950/80 text-studio-cyan border border-indigo-700/40">
                Job ID: {activeJob.id}
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            {!isWorkerRunning ? (
              <button
                onClick={onStartWorker}
                className="px-3.5 py-1.5 rounded-lg bg-studio-accent hover:bg-studio-accentHover text-white text-xs font-semibold flex items-center gap-2 shadow-sm"
              >
                <Play className="w-3.5 h-3.5 fill-current" />
                <span>Kích hoạt Queue</span>
              </button>
            ) : (
              <button
                onClick={onStopWorker}
                className="px-3.5 py-1.5 rounded-lg bg-studio-rose/20 text-rose-300 border border-studio-rose/40 hover:bg-studio-rose/30 text-xs font-semibold flex items-center gap-2"
              >
                <span>Tạm dừng Worker</span>
              </button>
            )}

            {activeJob && (
              <button
                onClick={() => onCancelJob(activeJob.id)}
                className="px-3.5 py-1.5 rounded-lg bg-studio-rose/20 text-rose-300 border border-studio-rose/40 hover:bg-studio-rose/30 text-xs font-semibold flex items-center gap-1.5"
              >
                <XCircle className="w-3.5 h-3.5" />
                <span>Hủy Job này</span>
              </button>
            )}
          </div>
        </div>

        {/* Progress Bar & Stage Indicator */}
        {activeJob ? (
          <div className="bg-studio-card border border-studio-border rounded-xl p-4 flex flex-col gap-3">
            {/* Stage Pills */}
            <div className="grid grid-cols-4 gap-2 text-xs">
              {stages.map((st, idx) => {
                const stepNum = idx + 1;
                const isPassed = activeStep > stepNum;
                const isCurrent = activeStep === stepNum;

                return (
                  <div
                    key={st.id}
                    className={`rounded-lg px-3 py-2 flex items-center justify-between border transition-all ${
                      isPassed
                        ? "bg-emerald-950/30 border-emerald-500/40 text-emerald-300"
                        : isCurrent
                        ? "bg-indigo-950/50 border-studio-accent text-white shadow-sm shadow-indigo-500/20"
                        : "bg-studio-elevated/40 border-studio-border/60 text-slate-500"
                    }`}
                  >
                    <span className="font-medium text-[11px]">{st.label}</span>
                    {isPassed ? (
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                    ) : isCurrent ? (
                      <span className="w-2 h-2 rounded-full bg-studio-cyan animate-ping" />
                    ) : (
                      <span className="w-2 h-2 rounded-full bg-slate-700" />
                    )}
                  </div>
                );
              })}
            </div>

            {/* Overall Progress Bar */}
            <div className="flex flex-col gap-1.5">
              <div className="flex items-center justify-between text-xs font-mono">
                <span className="text-slate-300">{activeJob.message}</span>
                <span className="font-bold text-studio-cyan text-sm">{activeJob.progress.toFixed(0)}%</span>
              </div>
              <div className="w-full h-2.5 bg-studio-elevated rounded-full overflow-hidden p-0.5 border border-studio-border/60">
                <div
                  className="h-full bg-gradient-to-r from-indigo-500 via-cyan-400 to-emerald-400 rounded-full transition-all duration-300 shadow-sm"
                  style={{ width: `${Math.max(3, activeJob.progress)}%` }}
                />
              </div>
            </div>
          </div>
        ) : (
          <div className="bg-studio-card border border-dashed border-studio-border rounded-xl p-6 text-center text-xs text-slate-400 flex items-center justify-center gap-2">
            <Clock className="w-4 h-4 text-slate-500" />
            <span>
              {queuedJobs.length > 0
                ? `Có ${queuedJobs.length} video đang chờ trong hàng đợi. Bấm "Kích hoạt Queue" để bắt đầu render tuần tự.`
                : "Hàng đợi trống. Hãy tạo video mới trong Studio hoặc nạp danh sách trong Batch AI."}
            </span>
          </div>
        )}
      </div>

      {/* Bottom 2-Column Split: Left Table / Right Live Terminal Logs */}
      <div className="flex-1 flex overflow-hidden">
        {/* Left: Job History Table (55%) */}
        <div className="flex-[55] border-r border-studio-border flex flex-col overflow-y-auto p-4 gap-4">
          <div className="flex items-center justify-between px-1">
            <h3 className="text-xs font-bold text-slate-300 uppercase tracking-wide">
              Danh sách hàng đợi & Lịch sử ({jobs.length})
            </h3>
            {completedOrFailedJobs.length > 0 && (
              <button
                onClick={onClearCompleted}
                className="text-xs text-slate-400 hover:text-slate-200 flex items-center gap-1 transition-colors"
              >
                <Trash2 className="w-3.5 h-3.5" />
                <span>Dọn dẹp đã hoàn tất</span>
              </button>
            )}
          </div>

          <div className="bg-studio-card border border-studio-border rounded-xl overflow-hidden">
            <table className="w-full text-left border-collapse text-xs">
              <thead>
                <tr className="bg-studio-panel border-b border-studio-border text-slate-400 font-semibold text-[11px]">
                  <th className="p-3 w-40">Tên video</th>
                  <th className="p-3 w-28">Trạng thái</th>
                  <th className="p-3 w-24">Tiến độ</th>
                  <th className="p-3 w-32">Thời gian</th>
                  <th className="p-3 text-right">Thao tác</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-studio-border/60">
                {jobs.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="p-8 text-center text-slate-500">
                      Chưa có job nào trong hệ thống.
                    </td>
                  </tr>
                ) : (
                  jobs.map((job) => {
                    const isRunning = job.status === "running";
                    const isCompleted = job.status === "completed";
                    const isFailed = job.status === "failed";
                    const isQueued = job.status === "queued";

                    return (
                      <tr key={job.id} className="hover:bg-studio-elevated/40 transition-colors">
                        <td className="p-3">
                          <div className="font-semibold text-slate-200">{job.name}</div>
                          <div className="text-[10px] text-slate-500 font-mono">{job.id}</div>
                        </td>
                        <td className="p-3">
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-semibold uppercase ${
                              isRunning
                                ? "bg-cyan-950 text-studio-cyan border border-cyan-800"
                                : isCompleted
                                ? "bg-emerald-950 text-emerald-400 border border-emerald-800"
                                : isFailed
                                ? "bg-rose-950 text-rose-400 border border-rose-800"
                                : "bg-amber-950 text-amber-400 border border-amber-800"
                            }`}
                          >
                            {job.status}
                          </span>
                        </td>
                        <td className="p-3 font-mono text-slate-300">
                          {job.progress.toFixed(0)}%
                        </td>
                        <td className="p-3 text-[11px] text-slate-400 font-mono">
                          {new Date(job.created_at).toLocaleTimeString()}
                        </td>
                        <td className="p-3 text-right">
                          <div className="flex items-center justify-end gap-1.5">
                            {isCompleted && (
                              <button
                                onClick={() => onOpenVideo(job.output_file || undefined)}
                                title="Mở video kết quả"
                                className="p-1 rounded bg-studio-elevated hover:bg-studio-hover text-studio-cyan"
                              >
                                <ExternalLink className="w-3.5 h-3.5" />
                              </button>
                            )}

                            {isFailed && (
                              <button
                                onClick={() => onRetryJob(job.id)}
                                title="Thử lại job này"
                                className="p-1 rounded bg-studio-elevated hover:bg-studio-hover text-studio-amber"
                              >
                                <RotateCcw className="w-3.5 h-3.5" />
                              </button>
                            )}

                            {isQueued && (
                              <button
                                onClick={() => onCancelJob(job.id)}
                                title="Hủy bỏ"
                                className="p-1 rounded bg-studio-elevated hover:bg-studio-hover text-rose-400"
                              >
                                <XCircle className="w-3.5 h-3.5" />
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>

        {/* Right: Live Terminal stdout Log Viewer (45%) */}
        <div className="flex-[45] flex flex-col bg-[#07090e] overflow-hidden">
          {/* Terminal Title Bar */}
          <div className="bg-studio-panel border-b border-studio-border px-4 py-2 flex items-center justify-between text-xs">
            <div className="flex items-center gap-2 font-mono text-slate-400">
              <Terminal className="w-3.5 h-3.5 text-studio-cyan" />
              <span>Live Console Stream (stdout / stderr)</span>
            </div>
            <label className="flex items-center gap-1.5 cursor-pointer text-slate-400 hover:text-slate-200 select-none">
              <input
                type="checkbox"
                checked={autoScroll}
                onChange={(e) => setAutoScroll(e.target.checked)}
                className="rounded bg-studio-elevated border-studio-border text-indigo-500 focus:ring-0"
              />
              <span className="text-[11px] font-mono">Auto-scroll</span>
            </label>
          </div>

          {/* Terminal Content */}
          <div
            ref={logContainerRef}
            className="flex-1 p-4 font-mono text-[11px] leading-relaxed text-slate-300 overflow-y-auto space-y-1 select-text"
          >
            {workerLogs.length === 0 ? (
              <div className="text-slate-600 italic">
                Chưa có dữ liệu log. Khi render bắt đầu, toàn bộ thông điệp tiến trình xử lý video sẽ hiển thị tại đây.
              </div>
            ) : (
              workerLogs.map((log, idx) => (
                <div
                  key={idx}
                  className={`break-words ${
                    log.includes("❌") || log.includes("ERROR")
                      ? "text-rose-400 bg-rose-950/20 px-1 rounded"
                      : log.includes("✅") || log.includes("Hoàn tất")
                      ? "text-emerald-400"
                      : log.includes("[LivePortrait]") || log.includes("[MuseTalk]")
                      ? "text-studio-cyan"
                      : "text-slate-400"
                  }`}
                >
                  <span className="text-slate-600 select-none mr-2">[{idx + 1}]</span>
                  <span>{log}</span>
                </div>
              ))
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
