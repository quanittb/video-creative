import React from "react";
import { DownloadCloud, ExternalLink, AlertOctagon, CheckCircle2 } from "lucide-react";
import { UpdateInfo } from "../../types";

interface Props {
  updateInfo: UpdateInfo;
  invokeCommand: <T>(cmd: string, args?: Record<string, any>) => Promise<T>;
}

export const MandatoryUpdateModal: React.FC<Props> = ({ updateInfo, invokeCommand }) => {
  const handleOpenUrl = (url?: string) => {
    if (url) {
      invokeCommand("open_external_url", { url });
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/90 backdrop-blur-md flex items-center justify-center p-4 select-none font-sans">
      <div className="w-full max-w-lg bg-studio-panel border-2 border-amber-500/60 rounded-2xl p-7 shadow-2xl shadow-amber-950/50 flex flex-col gap-6 text-slate-100 animate-in fade-in zoom-in-95 duration-200">
        {/* Header */}
        <div className="flex items-center gap-4">
          <div className="w-14 h-14 rounded-2xl bg-amber-950/80 border border-amber-500/50 flex items-center justify-center text-amber-400 shrink-0 shadow-lg shadow-amber-900/40">
            <AlertOctagon className="w-8 h-8" />
          </div>
          <div>
            <span className="text-[11px] font-mono font-bold uppercase tracking-widest text-amber-400 block mb-0.5">
              Cập Nhật Bắt Buộc
            </span>
            <h2 className="text-lg font-bold text-slate-100">
              Yêu Cầu Cập Nhật Phiên Bản Mới
            </h2>
          </div>
        </div>

        {/* Message */}
        <p className="text-xs text-slate-300 leading-relaxed bg-studio-card/80 p-3.5 rounded-xl border border-studio-border/70">
          Phiên bản <strong>v{updateInfo.latest_version}</strong> đã được phát hành với các cải tiến quan trọng và tính tương thích bắt buộc. Để tiếp tục sử dụng ứng dụng một cách ổn định, vui lòng cập nhật lên phiên bản này.
        </p>

        {/* Version Compare pill */}
        <div className="p-3.5 rounded-xl bg-studio-elevated/80 border border-studio-border/60 flex items-center justify-between text-xs font-mono">
          <div>
            <span className="text-slate-400 block text-[11px]">Phiên bản hiện tại:</span>
            <span className="text-slate-300 font-semibold">v{updateInfo.current_version}</span>
          </div>
          <span className="text-slate-600 font-bold">➔</span>
          <div>
            <span className="text-amber-400 block text-[11px] font-bold">Phiên bản mới:</span>
            <span className="text-studio-cyan font-bold text-sm">v{updateInfo.latest_version}</span>
          </div>
        </div>

        {/* Changelog */}
        {updateInfo.changelog && updateInfo.changelog.length > 0 && (
          <div className="space-y-2 text-xs text-slate-300 bg-studio-card/60 p-3.5 rounded-xl border border-studio-border/50 max-h-40 overflow-y-auto">
            <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wide block">
              Nội dung cập nhật mới:
            </span>
            <ul className="list-disc list-inside space-y-1 text-slate-300 pl-1">
              {updateInfo.changelog.map((log, idx) => (
                <li key={idx} className="leading-relaxed">
                  {log}
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* Action Buttons */}
        <div className="flex flex-col gap-2.5 pt-1">
          {updateInfo.download_url && (
            <button
              onClick={() => handleOpenUrl(updateInfo.download_url)}
              className="w-full py-3 rounded-xl bg-gradient-to-r from-amber-600 to-indigo-600 hover:from-amber-500 hover:to-indigo-500 text-white text-sm font-bold flex items-center justify-center gap-2 transition-all shadow-lg shadow-amber-900/30"
            >
              <DownloadCloud className="w-4 h-4" />
              <span>Tải Bản Cập Nhật Mới Ngay</span>
            </button>
          )}

          {updateInfo.release_page_url && (
            <button
              onClick={() => handleOpenUrl(updateInfo.release_page_url)}
              className="w-full py-2.5 rounded-xl bg-studio-elevated hover:bg-slate-700 text-slate-300 text-xs font-semibold flex items-center justify-center gap-2 border border-studio-border transition-all"
            >
              <ExternalLink className="w-3.5 h-3.5" />
              <span>Xem Chi Tiết Bản Phát Hành Trên GitHub</span>
            </button>
          )}
        </div>

        <div className="text-[11px] text-slate-500 text-center font-mono">
          Nguồn cập nhật: github.com/quanittb/video-creative-release
        </div>
      </div>
    </div>
  );
};
