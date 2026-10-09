import React from "react";
import { Video, Layers, Terminal, FolderOpen, Cpu, Sparkles, Settings } from "lucide-react";
import { ActiveTab } from "../../types";

interface Props {
  activeTab: ActiveTab;
  onTabChange: (tab: ActiveTab) => void;
  queuedCount: number;
  isWorkerRunning: boolean;
}

export const ActivityBar: React.FC<Props> = ({
  activeTab,
  onTabChange,
  queuedCount,
  isWorkerRunning,
}) => {
  const tabs = [
    { id: "studio" as ActiveTab, label: "Studio", icon: Video },
    { id: "batch" as ActiveTab, label: "Batch AI", icon: Layers, badge: queuedCount > 0 ? queuedCount : undefined },
    { id: "queue" as ActiveTab, label: "Hàng đợi", icon: Terminal, pulse: isWorkerRunning },
    { id: "assets" as ActiveTab, label: "Tài nguyên", icon: FolderOpen },
    { id: "hardware" as ActiveTab, label: "Hệ thống", icon: Cpu },
    { id: "settings" as ActiveTab, label: "Cài đặt", icon: Settings },
  ];

  return (
    <div className="w-16 bg-studio-panel border-r border-studio-border flex flex-col items-center py-4 select-none z-20 shrink-0">
      {/* Brand Icon */}
      <div className="w-10 h-10 rounded-xl bg-gradient-to-tr from-indigo-600 to-cyan-500 flex items-center justify-center text-white shadow-lg shadow-indigo-500/20 mb-8 cursor-pointer group">
        <Sparkles className="w-5 h-5 group-hover:rotate-12 transition-transform duration-300" />
      </div>

      {/* Nav Tabs */}
      <div className="flex-1 flex flex-col gap-3 w-full px-2">
        {tabs.map((tab) => {
          const Icon = tab.icon;
          const isActive = activeTab === tab.id;

          return (
            <button
              key={tab.id}
              onClick={() => onTabChange(tab.id)}
              title={tab.label}
              className={`relative w-full aspect-square rounded-xl flex flex-col items-center justify-center transition-all duration-200 group ${
                isActive
                  ? "bg-studio-accent text-white shadow-md shadow-indigo-600/30"
                  : "text-slate-400 hover:text-slate-100 hover:bg-studio-elevated"
              }`}
            >
              <Icon className="w-5 h-5" />
              <span className="text-[9px] mt-1 font-medium tracking-tight">
                {tab.label}
              </span>

              {/* Badge for queue */}
              {tab.badge !== undefined && (
                <span className="absolute -top-1 -right-1 bg-studio-amber text-slate-900 text-[10px] font-bold px-1.5 py-0.5 rounded-full ring-2 ring-studio-panel">
                  {tab.badge}
                </span>
              )}

              {/* Pulse dot for worker */}
              {tab.pulse && (
                <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-studio-emerald animate-ping" />
              )}
            </button>
          );
        })}
      </div>

      {/* Bottom Live Health Pill */}
      <div className="flex flex-col items-center gap-1.5 mt-auto">
        <div
          title={isWorkerRunning ? "Worker đang chạy" : "Worker đang nghỉ"}
          className={`w-3 h-3 rounded-full transition-colors ${
            isWorkerRunning ? "bg-studio-emerald animate-pulse" : "bg-slate-600"
          }`}
        />
        <span className="text-[9px] text-slate-500 font-mono">RTX</span>
      </div>
    </div>
  );
};
