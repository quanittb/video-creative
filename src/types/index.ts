export interface GpuInfo {
  available: boolean;
  name: string;
  total_vram_mb: number;
  free_vram_mb: number;
}

export interface CharacterAsset {
  name: string;
  path: string;
  group: string;
}

export interface DrivingAsset {
  name: string;
  path: string;
  size_mb: number;
}

export interface HardwareStatus {
  system: {
    platform: string;
    python: string;
    ffmpeg: boolean;
    ffprobe: boolean;
    gpu: GpuInfo;
  };
  engines: {
    liveportrait: {
      installed: boolean;
      path: string;
    };
    musetalk: {
      installed: boolean;
      venv_ready: boolean;
      python: string | null;
    };
  };
  assets: {
    character_count: number;
    characters: CharacterAsset[];
    driving_count: number;
    driving_templates: DrivingAsset[];
  };
}

export interface JobParams {
  name?: string;
  char?: string;
  source?: string;
  script?: string;
  voice?: string;
  driving?: string;
  duration?: number;
  multiplier?: number;
  fps?: number;
  driving_policy?: string;
  motion_mode?: string;
  batch_size?: number;
  offset_ms?: number;
  output?: string;
  dry_run?: boolean;
}

export interface RenderJob {
  id: string;
  name: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  progress: number;
  stage: string;
  message: string;
  params: JobParams;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  output_file?: string | null;
  error?: string | null;
  log_tail?: string[];
}

export interface PresentationStyle {
  id: string;
  number: number;
  name: string;
  vietnameseTitle: string;
  tagline: string;
  background: string;
  backgroundTitle: string;
  backgroundDescription: string;
  backgroundTheme: string;
  backgroundTags: string[];
  scriptGuideline: string;
  sampleScript: string;
  sampleScriptEn?: string;
  voiceGuideline: string;
  recommendedVoice: string;
  recommendedMultiplier: number;
  recommendedAspectRatios: ("16:9" | "9:16" | "1:1")[];
  defaultAspectRatio: "16:9" | "9:16" | "1:1";
  kinematicsGuideline: string;
  drivingPolicy: "hold" | "loop";
  torsoMotion: boolean;
  useCase: string;
  badgeColor: string;
  geminiPrompt: string;
}

export type ActiveTab = "studio" | "batch" | "queue" | "assets" | "hardware" | "settings";

export interface LicenseStatus {
  is_activated: boolean;
  is_locked: boolean;
  status: "activated" | "trial" | "expired";
  device_id: string;
  days_remaining: number;
  total_trial_days: number;
  first_run_date: string;
}

export interface UpdateInfo {
  has_update: boolean;
  current_version: string;
  latest_version: string;
  mandatory: boolean;
  release_date?: string;
  title?: string;
  changelog?: string[];
  download_url?: string;
  release_page_url?: string;
}

export type { TtsVoice } from "../data/ttsVoices";
export type { CharacterOption } from "../data/characterLibrary";
