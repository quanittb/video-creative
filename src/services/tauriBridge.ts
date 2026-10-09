import { HardwareStatus, RenderJob } from "../types";

// Check if running inside Tauri environment
export const isTauriEnv = (): boolean => {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
};

// Safe invoke wrapper
export async function invokeCommand<T>(cmd: string, args?: Record<string, any>): Promise<T> {
  if (isTauriEnv()) {
    const { invoke } = await import("@tauri-apps/api/core");
    return invoke<T>(cmd, args);
  }

  // Browser Fallback / Mock for Dev Mode
  console.warn(`[Browser Mode] Invoking mock for: ${cmd}`, args);

  if (cmd === "get_hardware_status") {
    return {
      system: {
        platform: "win32",
        python: "Python 3.10.11 (RTX 3060 12GB Host)",
        ffmpeg: true,
        ffprobe: true,
        gpu: {
          available: true,
          name: "NVIDIA GeForce RTX 3060 (12GB VRAM)",
          total_vram_mb: 12288,
          free_vram_mb: 9850,
        },
      },
      engines: {
        liveportrait: {
          installed: true,
          path: "D:\\rustProject\\video-creative-studio\\LivePortrait",
        },
        musetalk: {
          installed: true,
          venv_ready: true,
          python: "D:\\rustProject\\video-creative-studio\\musetalk-venv\\Scripts\\python.exe",
        },
      },
      assets: {
        character_count: 38,
        characters: [
          { name: "asian_male_office_1080p", path: "assets/characters/nhanvatnam/asian_male_office_1080p.png", group: "nhanvatnam" },
          { name: "vietnamese_female_anchor", path: "assets/characters/nhanvatnu/ChatGPT Image Sep 14, 2026, 11_35_53 AM (1).png", group: "nhanvatnu" },
          { name: "pixar_character_3d", path: "assets/characters/hoathinhnu/ChatGPT Image Sep 8, 2026, 09_49_11 AM (1).png", group: "hoathinhnu" },
        ],
        driving_count: 2,
        driving_templates: [
          { name: "reference_head_driving.mp4", path: "assets/driving_templates/reference_head_driving.mp4", size_mb: 3.05 },
          { name: "natural_driving_template.mp4", path: "assets/driving_templates/natural_driving_template.mp4", size_mb: 2.01 },
        ],
      },
    } as unknown as T;
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
    return [
      {
        id: "vcs_mock_01",
        name: "Bản tin AI Công nghệ 1 Phút",
        status: "completed",
        progress: 100,
        stage: "done",
        message: "Video đã được tạo thành công!",
        created_at: new Date(Date.now() - 3600000).toISOString(),
        completed_at: new Date(Date.now() - 3500000).toISOString(),
        output_file: "output/avatar_option_b_result.mp4",
        params: {
          char: "office",
          voice: "vi-VN-NamMinhNeural",
          script: "Xin chào quý vị và các bạn đến với bản tin công nghệ...",
          multiplier: 0.55,
        },
        log_tail: [
          "[Audio AI] Đã tạo âm thanh: vietnamese_speech.mp3 (55.58s)",
          "[Motion 3D] Đã tạo cử động nhân vật 3D hoàn tất (multiplier=0.55)",
          "[Lip-Sync] Đang xử lý đồng bộ khẩu hình AI...",
          "✅ Video đầu ra: output/avatar_option_b_result.mp4",
        ],
      },
    ] as unknown as T;
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
    return "Worker started (Browser Simulated)" as unknown as T;
  }

  if (cmd === "stop_render_worker") {
    return "Worker stopped" as unknown as T;
  }

  if (cmd === "preview_tts_voice") {
    return {
      status: "success",
      duration: 3.2,
      audio_path: "temp/preview.mp3",
    } as unknown as T;
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
    const { listen } = await import("@tauri-apps/api/event");
    const unlisten = await listen<T>(event, (e) => callback(e.payload));
    return unlisten;
  }

  // No-op for browser mode
  return () => {};
}
