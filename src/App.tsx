import React, { useState, useEffect, useCallback } from "react";
import { ActivityBar } from "./components/layout/ActivityBar";
import { HeaderBar } from "./components/layout/HeaderBar";
import { StudioView } from "./components/views/StudioView";
import { BatchView } from "./components/views/BatchView";
import { QueueView } from "./components/views/QueueView";
import { AssetsView } from "./components/views/AssetsView";
import { HardwareView } from "./components/views/HardwareView";
import { SettingsView } from "./components/views/SettingsView";
import { ActivationLockModal } from "./components/modals/ActivationLockModal";
import { MandatoryUpdateModal } from "./components/modals/MandatoryUpdateModal";
import { ActiveTab, HardwareStatus, RenderJob, LicenseStatus, UpdateInfo } from "./types";
import { invokeCommand, listenToEvent } from "./services/tauriBridge";

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<ActiveTab>("studio");
  const [hardware, setHardware] = useState<HardwareStatus | null>(null);
  const [jobs, setJobs] = useState<RenderJob[]>([]);
  const [isWorkerRunning, setIsWorkerRunning] = useState<boolean>(false);
  const [workerLogs, setWorkerLogs] = useState<string[]>([]);
  const [isRefreshing, setIsRefreshing] = useState<boolean>(false);
  // Default to Test Mode on development machine to prevent GPU OOM
  const [isTestMode, setIsTestMode] = useState<boolean>(true);

  // License & Remote Updater State
  const [license, setLicense] = useState<LicenseStatus | null>(null);
  const [updateInfo, setUpdateInfo] = useState<UpdateInfo | null>(null);
  const [isCheckingUpdate, setIsCheckingUpdate] = useState<boolean>(false);

  // Refresh License status
  const refreshLicense = useCallback(async () => {
    try {
      const lic = await invokeCommand<LicenseStatus>("get_license_status");
      setLicense(lic);
    } catch (err) {
      console.error("Lỗi kiểm tra bản quyền:", err);
    }
  }, []);

  // Check remote updates
  const checkUpdates = useCallback(async () => {
    setIsCheckingUpdate(true);
    try {
      const up = await invokeCommand<UpdateInfo>("check_app_updates");
      setUpdateInfo(up);
    } catch (err) {
      console.error("Lỗi kiểm tra cập nhật:", err);
    } finally {
      setIsCheckingUpdate(false);
    }
  }, []);

  // Fetch hardware and initial jobs
  const refreshState = useCallback(async () => {
    setIsRefreshing(true);
    try {
      const hw = await invokeCommand<HardwareStatus>("get_hardware_status");
      setHardware(hw);

      const jobList = await invokeCommand<RenderJob[]>("list_jobs");
      setJobs(jobList || []);
    } catch (err) {
      console.error("Lỗi cập nhật trạng thái:", err);
    } finally {
      setIsRefreshing(false);
    }
  }, []);

  useEffect(() => {
    refreshState();
    refreshLicense();
    checkUpdates();

    // Listen to worker logs
    let unlistenLogs: (() => void) | undefined;
    let unlistenStatus: (() => void) | undefined;
    let unlistenEvents: (() => void) | undefined;

    (async () => {
      unlistenLogs = await listenToEvent<string>("vcs-worker-log", (line) => {
        setWorkerLogs((prev) => [...prev.slice(-200), line]);
      });

      unlistenStatus = await listenToEvent<{ running: boolean }>("vcs-worker-status", (payload) => {
        setIsWorkerRunning(payload.running);
        refreshState();
      });

      unlistenEvents = await listenToEvent<any>("vcs-job-event", (event) => {
        // Refresh job list on job state transitions
        if (event.type === "job_started" || event.type === "job_completed" || event.type === "job_failed") {
          refreshState();
        }
      });
    })();

    // Polling job list every 3s via fast 0ms native Rust file read
    const timer = setInterval(() => {
      invokeCommand<RenderJob[]>("list_jobs")
        .then((jList) => setJobs(jList || []))
        .catch(() => {});
    }, 3000);

    return () => {
      clearInterval(timer);
      if (unlistenLogs) unlistenLogs();
      if (unlistenStatus) unlistenStatus();
      if (unlistenEvents) unlistenEvents();
    };
  }, [refreshState]);

  // Worker controls
  const handleToggleWorker = async () => {
    if (isWorkerRunning) {
      await invokeCommand("stop_render_worker");
      setIsWorkerRunning(false);
    } else {
      await invokeCommand("start_render_worker");
      setIsWorkerRunning(true);
    }
    refreshState();
  };

  const handleCancelJob = async (id: string) => {
    await invokeCommand("cancel_job", { jobId: id });
    refreshState();
  };

  const handleRetryJob = async (id: string) => {
    await invokeCommand("retry_job", { jobId: id });
    refreshState();
  };

  const handleClearCompleted = async () => {
    await invokeCommand("clear_completed_jobs");
    refreshState();
  };

  const handleOpenOutputFolder = async (path?: string) => {
    await invokeCommand("open_output_folder", { path });
  };

  const queuedCount = jobs.filter((j) => j.status === "queued").length;

  return (
    <div className="flex h-screen w-screen overflow-hidden bg-studio-obsidian text-slate-100 font-sans">
      {/* Left Vertical Activity Bar */}
      <ActivityBar
        activeTab={activeTab}
        onTabChange={setActiveTab}
        queuedCount={queuedCount}
        isWorkerRunning={isWorkerRunning}
      />

      {/* Main Workspace Column */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Top Header Bar */}
        <HeaderBar
          hardware={hardware}
          license={license}
          updateInfo={updateInfo}
          onNavigateSettings={() => setActiveTab("settings")}
          isWorkerRunning={isWorkerRunning}
          isTestMode={isTestMode}
          onToggleTestMode={() => setIsTestMode(!isTestMode)}
          onToggleWorker={handleToggleWorker}
          onOpenOutputFolder={() => handleOpenOutputFolder()}
          onRefresh={refreshState}
          isRefreshing={isRefreshing}
        />

        {/* Dynamic View Tab */}
        <main className="flex-1 flex overflow-hidden">
          {activeTab === "studio" && (
            <StudioView
              hardware={hardware}
              onJobCreated={refreshState}
              onStartWorker={() => {
                if (!isWorkerRunning) handleToggleWorker();
              }}
              invokeCommand={invokeCommand}
              isTestMode={isTestMode}
            />
          )}

          {activeTab === "batch" && (
            <BatchView
              onBatchQueued={refreshState}
              invokeCommand={invokeCommand}
              isTestMode={isTestMode}
            />
          )}

          {activeTab === "queue" && (
            <QueueView
              jobs={jobs}
              isWorkerRunning={isWorkerRunning}
              workerLogs={workerLogs}
              onStartWorker={handleToggleWorker}
              onStopWorker={handleToggleWorker}
              onCancelJob={handleCancelJob}
              onRetryJob={handleRetryJob}
              onClearCompleted={handleClearCompleted}
              onOpenVideo={handleOpenOutputFolder}
            />
          )}

          {activeTab === "assets" && (
            <AssetsView
              hardware={hardware}
              onOpenFolder={() => handleOpenOutputFolder()}
            />
          )}

          {activeTab === "hardware" && (
            <HardwareView
              hardware={hardware}
              onRefresh={refreshState}
              isRefreshing={isRefreshing}
            />
          )}

          {activeTab === "settings" && (
            <SettingsView
              license={license}
              onRefreshLicense={refreshLicense}
              updateInfo={updateInfo}
              isCheckingUpdate={isCheckingUpdate}
              onCheckUpdate={checkUpdates}
              invokeCommand={invokeCommand}
              onOpenFolder={() => handleOpenOutputFolder()}
            />
          )}
        </main>
      </div>

      {/* Mandatory Update Modal (Blocks app until updated) */}
      {updateInfo?.has_update && updateInfo.mandatory && (
        <MandatoryUpdateModal
          updateInfo={updateInfo}
          invokeCommand={invokeCommand}
        />
      )}

      {/* 30-Day Expiration / Activation Lock Modal (Blocks app until valid key is entered) */}
      {license?.is_locked && (
        <ActivationLockModal
          license={license}
          onUnlockSuccess={refreshLicense}
          invokeCommand={invokeCommand}
        />
      )}
    </div>
  );
};

export default App;
