import { HardwareStatus, RenderJob } from "../types";
import { convertFileSrc, invoke } from "@tauri-apps/api/core";
import { listen } from "@tauri-apps/api/event";

// Check if running inside Tauri environment
export const isTauriEnv = (): boolean => {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
};

export const getLocalFilePreviewSrc = (path: string): string =>
  isTauriEnv() ? convertFileSrc(path) : path;

// Safe invoke wrapper
export async function invokeCommand<T>(cmd: string, args?: Record<string, any>): Promise<T> {
  if (isTauriEnv()) {
    return invoke<T>(cmd, args);
  }

  // Browser Fallback / Mock for Dev Mode
  console.warn(`[Browser Mode] Invoking mock for: ${cmd}`, args);

  if (cmd === "get_hardware_status") {
    return {
      available: false,
      message: "Trình duyệt không thể đọc phần cứng hoặc model trên máy. Mở ứng dụng desktop để kiểm tra.",
      system: {
        platform: typeof navigator !== "undefined" ? navigator.platform : "browser",
        python: "Chỉ phát hiện trong ứng dụng desktop",
        ffmpeg: false,
        ffprobe: false,
        gpu: {
          available: false,
          name: "Không khả dụng trong trình duyệt",
          total_vram_mb: 0,
          free_vram_mb: 0,
        },
      },
      engines: {
        musetalk: {
          source: { status: "unknown" },
          runtime: { status: "unknown" },
          assets_ready: 0,
          assets_total: 0,
        },
      },
      assets: {
        character_count: 0,
        characters: [],
        driving_count: 0,
        driving_templates: [],
      },
    } as unknown as T;
  }

  if (cmd === "get_pipeline_model_status") {
    return {
      available: false,
      message: "Trình duyệt không thể kiểm tra model trên máy. Mở ứng dụng desktop để xem trạng thái.",
      components: {},
    } as unknown as T;
  }

  if (cmd === "manage_pipeline_models") {
    throw new Error("Tải, sửa hoặc xóa model chỉ khả dụng trong ứng dụng desktop.");
  }

  if (cmd === "list_jobs") {
    const raw = localStorage.getItem("vcs_browser_jobs");
    if (raw) {
      try {
        return JSON.parse(raw);
      } catch {
        // ignore
      }
    }
    return [] as unknown as T;
  }

  if (cmd === "create_job") {
    const newJob: RenderJob = {
      id: `vcs_${Math.random().toString(36).substring(2, 9)}`,
      name: args?.name || "Render Job",
      status: "queued",
      progress: 0,
      stage: "idle",
      message: "Chờ trong hàng đợi...",
      created_at: new Date().toISOString(),
      params: {
        char: args?.char || "office",
        script: args?.script,
        voice: args?.voice,
        output: args?.output,
        driving: args?.driving,
        multiplier: args?.multiplier,
        dry_run: args?.dry_run,
      },
      log_tail: [],
    };
    const raw = localStorage.getItem("vcs_browser_jobs");
    const jobs: RenderJob[] = raw ? JSON.parse(raw) : [];
    jobs.unshift(newJob);
    localStorage.setItem("vcs_browser_jobs", JSON.stringify(jobs));
    return newJob as unknown as T;
  }

  if (cmd === "start_render_worker") {
    throw new Error("Render video chỉ chạy trong ứng dụng desktop Tauri; trình duyệt không thực thi GPU core.");
  }

  if (cmd === "stop_render_worker") {
    return "Worker stopped" as unknown as T;
  }

  if (cmd === "preview_tts_voice") {
    throw new Error("Nghe thử TTS cần ứng dụng desktop chạy local bridge.");
  }

  if (cmd === "get_license_status") {
    const raw = localStorage.getItem("vcs_browser_license_activated");
    const isAct = raw === "true";
    return {
      is_activated: isAct,
      is_locked: false,
      status: isAct ? "activated" : "trial",
      device_id: "BROWSER-SIMULATED-DEVICE-98X",
      days_remaining: isAct ? 30 : 29,
      total_trial_days: 30,
      first_run_date: "09/10/2026 10:00",
    } as unknown as T;
  }

  if (cmd === "verify_license_key") {
    // In browser mode, verify via hash check or mock
    if (args?.key === "quandepzai") {
      localStorage.setItem("vcs_browser_license_activated", "true");
      return {
        is_activated: true,
        is_locked: false,
        status: "activated",
        device_id: "BROWSER-SIMULATED-DEVICE-98X",
        days_remaining: 30,
        total_trial_days: 30,
        first_run_date: "09/10/2026 10:00",
      } as unknown as T;
    } else {
      throw new Error("Mã bảo mật kích hoạt không chính xác. Vui lòng kiểm tra lại.");
    }
  }

  if (cmd === "check_app_updates") {
    return {
      has_update: false,
      check_status: "unavailable",
      current_version: "1.0.0",
      latest_version: "1.0.0",
      mandatory: false,
      changelog: [],
      release_page_url: "https://github.com/quanittb/video-creative-release",
    } as unknown as T;
  }

  if (cmd === "open_external_url") {
    if (args?.url) window.open(args.url, "_blank");
    return {} as T;
  }

  if (cmd === "list_custom_characters") {
    try {
      const raw = localStorage.getItem("VCS_CUSTOM_CHARACTERS");
      return (raw ? JSON.parse(raw) : []) as unknown as T;
    } catch {
      return [] as unknown as T;
    }
  }

  if (cmd === "save_custom_character") {
    const raw = localStorage.getItem("VCS_CUSTOM_CHARACTERS");
    const list = raw ? JSON.parse(raw) : [];
    const uniqueName = `${Date.now()}_${args?.filename || "custom.png"}`;
    const newChar = {
      id: `custom_${uniqueName}`,
      name: args?.name || "Nhân vật tùy chọn",
      filename: uniqueName,
      relPath: `assets/characters/custom/${uniqueName}`,
      webPath: `/characters/custom/${uniqueName}`,
      category: "custom",
      desc: "Nhân vật tùy chọn trong thư viện",
      gender: "male",
    };
    list.push(newChar);
    localStorage.setItem("VCS_CUSTOM_CHARACTERS", JSON.stringify(list));
    return newChar as unknown as T;
  }

  if (cmd === "delete_custom_character") {
    const raw = localStorage.getItem("VCS_CUSTOM_CHARACTERS");
    if (raw) {
      const list = JSON.parse(raw).filter((c: any) => c.filename !== args?.filename);
      localStorage.setItem("VCS_CUSTOM_CHARACTERS", JSON.stringify(list));
    }
    return true as unknown as T;
  }

  return {} as T;
}

// Event listener wrapper
export async function listenToEvent<T>(
  event: string,
  callback: (payload: T) => void
): Promise<() => void> {
  if (isTauriEnv()) {
    const unlisten = await listen<T>(event, (e) => callback(e.payload));
    return unlisten;
  }

  // No-op for browser mode
  return () => {};
}
