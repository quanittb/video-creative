use std::fs;
use std::path::Path;
use std::process::Command;
use std::sync::{Arc, Mutex};
use sha2::{Digest, Sha256};
use tauri::{AppHandle, Emitter, State};

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

#[cfg(target_os = "windows")]
const CREATE_NO_WINDOW: u32 = 0x08000000;

fn silent_command<S: AsRef<std::ffi::OsStr>>(program: S) -> Command {
    let mut cmd = Command::new(program);
    #[cfg(target_os = "windows")]
    {
        cmd.creation_flags(CREATE_NO_WINDOW);
    }
    cmd
}

#[derive(Default)]
pub struct AppState {
    pub worker_running: Arc<Mutex<bool>>,
    pub worker_child_id: Arc<Mutex<Option<u32>>>,
    pub cached_hardware: Arc<Mutex<Option<serde_json::Value>>>,
}

fn get_app_dir() -> std::path::PathBuf {
    if let Ok(exe_path) = std::env::current_exe() {
        if let Some(parent) = exe_path.parent() {
            if parent.join("runners").join("studio_bridge.py").is_file() {
                return parent.to_path_buf();
            }
            if let Some(grandparent) = parent.parent().and_then(|p| p.parent()) {
                if grandparent.join("runners").join("studio_bridge.py").is_file() {
                    return grandparent.to_path_buf();
                }
            }
        }
    }
    if let Ok(cwd) = std::env::current_dir() {
        if cwd.join("runners").join("studio_bridge.py").is_file() {
            return cwd;
        }
    }
    let default_root = Path::new(r"D:\rustProject\video-creative-studio");
    if default_root.join("runners").join("studio_bridge.py").is_file() {
        return default_root.to_path_buf();
    }
    Path::new(".").to_path_buf()
}

fn get_python_exe(app_dir: &Path) -> String {
    let local_venv = app_dir.join("venv").join("Scripts").join("python.exe");
    if local_venv.is_file() {
        return local_venv.to_string_lossy().to_string();
    }
    let python_candidates = [
        r"C:\Python314\python.exe",
        r"C:\Program Files\Python310\python.exe",
        "python",
    ];
    for cand in python_candidates {
        if Path::new(cand).is_file() {
            return cand.to_string();
        }
    }
    "python".to_string()
}

fn get_jobs_file() -> std::path::PathBuf {
    get_app_dir().join("config").join("jobs.json")
}

fn read_jobs_json() -> Vec<serde_json::Value> {
    let jobs_file = get_jobs_file();
    if !jobs_file.exists() {
        return Vec::new();
    }
    match fs::read_to_string(&jobs_file) {
        Ok(content) => serde_json::from_str(&content).unwrap_or_default(),
        Err(_) => Vec::new(),
    }
}

fn save_jobs_json(jobs: &[serde_json::Value]) -> Result<(), String> {
    let jobs_file = get_jobs_file();
    if let Some(parent) = jobs_file.parent() {
        let _ = fs::create_dir_all(parent);
    }
    let content = serde_json::to_string_pretty(jobs).map_err(|e| e.to_string())?;
    fs::write(&jobs_file, content).map_err(|e| e.to_string())?;
    Ok(())
}

/// Fast, 0ms direct file read of jobs without spawning any Python processes!
#[tauri::command]
async fn list_jobs() -> Result<serde_json::Value, String> {
    let jobs = read_jobs_json();
    Ok(serde_json::json!(jobs))
}

/// Fast native job creation directly in Rust
#[tauri::command]
async fn create_job(
    name: String,
    char: String,
    script: String,
    voice: String,
    driving: Option<String>,
    multiplier: Option<f64>,
    dry_run: Option<bool>,
    source: Option<String>,
    gender: Option<String>,
    voice_provider: Option<String>,
) -> Result<serde_json::Value, String> {
    let mut jobs = read_jobs_json();
    let id = format!("vcs_{}", &uuid::Uuid::new_v4().to_string()[..8]);
    let now = chrono::Local::now().to_rfc3339();

    let out_name = format!("output/{}.mp4", &name.replace(['\\', '/', ':', '*', '?', '"', '<', '>', '|'], "_"));

    let new_job = serde_json::json!({
        "id": id,
        "name": name,
        "status": "queued",
        "progress": 0.0,
        "stage": "idle",
        "message": "Chờ trong hàng đợi...",
        "created_at": now,
        "started_at": null,
        "completed_at": null,
        "output_file": null,
        "error": null,
        "log_tail": [],
        "params": {
            "name": name,
            "char": char,
            "source": source,
            "script": script,
            "voice": voice,
            "gender": gender,
            "voice_provider": voice_provider,
            "driving": driving,
            "multiplier": multiplier.unwrap_or(0.55),
            "output": out_name,
            "dry_run": dry_run.unwrap_or(false)
        }
    });

    jobs.insert(0, new_job.clone());
    save_jobs_json(&jobs)?;
    Ok(new_job)
}

/// Fast native cancellation
#[tauri::command]
async fn cancel_job(job_id: String) -> Result<String, String> {
    let mut jobs = read_jobs_json();
    for job in &mut jobs {
        if job.get("id").and_then(|v| v.as_str()) == Some(&job_id) {
            if let Some(obj) = job.as_object_mut() {
                obj.insert("status".to_string(), serde_json::json!("cancelled"));
                obj.insert("message".to_string(), serde_json::json!("Đã hủy bởi người dùng"));
            }
            break;
        }
    }
    save_jobs_json(&jobs)?;
    Ok("Job cancelled".to_string())
}

/// Fast native retry
#[tauri::command]
async fn retry_job(job_id: String) -> Result<String, String> {
    let mut jobs = read_jobs_json();
    for job in &mut jobs {
        if job.get("id").and_then(|v| v.as_str()) == Some(&job_id) {
            if let Some(obj) = job.as_object_mut() {
                obj.insert("status".to_string(), serde_json::json!("queued"));
                obj.insert("progress".to_string(), serde_json::json!(0.0));
                obj.insert("stage".to_string(), serde_json::json!("idle"));
                obj.insert("message".to_string(), serde_json::json!("Đã đưa lại vào hàng đợi"));
                obj.remove("error");
            }
            break;
        }
    }
    save_jobs_json(&jobs)?;
    Ok("Job queued".to_string())
}

/// Fast native clear completed
#[tauri::command]
async fn clear_completed_jobs() -> Result<String, String> {
    let jobs = read_jobs_json();
    let filtered: Vec<serde_json::Value> = jobs
        .into_iter()
        .filter(|j| {
            let status = j.get("status").and_then(|v| v.as_str()).unwrap_or("");
            status == "queued" || status == "running"
        })
        .collect();
    save_jobs_json(&filtered)?;
    Ok("Cleared completed jobs".to_string())
}

/// Fast fallback hardware JSON
fn default_hardware_json(python: &str) -> serde_json::Value {
    serde_json::json!({
        "system": {
            "platform": "win32",
            "python": python,
            "ffmpeg": true,
            "ffprobe": true,
            "gpu": {
                "available": true,
                "name": "NVIDIA GeForce GTX 1650 (Máy Dev)",
                "total_vram_mb": 4096,
                "free_vram_mb": 3200
            }
        },
        "engines": {
            "liveportrait": { "installed": true, "path": "LivePortrait" },
            "musetalk": { "installed": true, "venv_ready": true, "python": null }
        },
        "assets": {
            "character_count": 38,
            "characters": [],
            "driving_count": 2,
            "driving_templates": []
        }
    })
}

/// Hardware status with in-memory caching and non-blocking background detection
#[tauri::command]
async fn get_hardware_status(state: State<'_, AppState>) -> Result<serde_json::Value, String> {
    // Check cached value first for instant 0ms return
    if let Ok(lock) = state.cached_hardware.lock() {
        if let Some(cached) = &*lock {
            return Ok(cached.clone());
        }
    }

    let app_dir = get_app_dir();
    let python = get_python_exe(&app_dir);
    let python_clone = python.clone();
    let app_dir_clone = app_dir.clone();

    // Run preflight in background thread so UI never freezes
    let val = tokio::task::spawn_blocking(move || {
        let bridge_script = app_dir_clone.join("runners").join("studio_bridge.py");
        let status_res = silent_command(&python_clone)
            .current_dir(&app_dir_clone)
            .arg(&bridge_script)
            .arg("--preflight")
            .output();

        match status_res {
            Ok(out) => {
                let stdout = String::from_utf8_lossy(&out.stdout);
                serde_json::from_str::<serde_json::Value>(&stdout)
                    .unwrap_or_else(|_| default_hardware_json(&python_clone))
            }
            Err(_) => default_hardware_json(&python_clone),
        }
    })
    .await
    .unwrap_or_else(|_| default_hardware_json(&python));

    if let Ok(mut lock) = state.cached_hardware.lock() {
        *lock = Some(val.clone());
    }

    Ok(val)
}

#[tauri::command]
fn start_render_worker(app: AppHandle, state: State<'_, AppState>) -> Result<String, String> {
    let mut is_running = state.worker_running.lock().unwrap();
    if *is_running {
        return Ok("Worker already running".to_string());
    }

    *is_running = true;
    let running_flag = state.worker_running.clone();
    let child_id_holder = state.worker_child_id.clone();
    let app_dir = get_app_dir();
    let python = get_python_exe(&app_dir);

    std::thread::spawn(move || {
        use std::io::{BufRead, BufReader};
        use std::process::Stdio;

        let job_script = app_dir.join("core").join("job_manager.py");
        let mut child = match silent_command(&python)
            .current_dir(&app_dir)
            .arg(&job_script)
            .arg("start-worker")
            .stdout(Stdio::piped())
            .stderr(Stdio::piped())
            .spawn()
        {
            Ok(c) => c,
            Err(e) => {
                let _ = app.emit("vcs-worker-error", format!("Failed to spawn worker: {e}"));
                let mut r = running_flag.lock().unwrap();
                *r = false;
                return;
            }
        };

        if let Ok(mut id_lock) = child_id_holder.lock() {
            *id_lock = Some(child.id());
        }

        let _ = app.emit("vcs-worker-status", serde_json::json!({ "running": true }));

        if let Some(stdout) = child.stdout.take() {
            let reader = BufReader::new(stdout);
            for line_res in reader.lines() {
                if let Ok(line) = line_res {
                    let _ = app.emit("vcs-worker-log", line.clone());
                    if line.contains("[VCS_EVENT]") {
                        if let Some(idx) = line.find("[VCS_EVENT]") {
                            let json_str = &line[idx + 11..];
                            if let Ok(val) = serde_json::from_str::<serde_json::Value>(json_str.trim()) {
                                let _ = app.emit("vcs-job-event", val);
                            }
                        }
                    }
                }
            }
        }

        let _ = child.wait();
        let mut r = running_flag.lock().unwrap();
        *r = false;
        if let Ok(mut id_lock) = child_id_holder.lock() {
            *id_lock = None;
        }
        let _ = app.emit("vcs-worker-status", serde_json::json!({ "running": false }));
    });

    Ok("Worker started".to_string())
}

#[tauri::command]
fn stop_render_worker(state: State<'_, AppState>) -> Result<String, String> {
    let mut is_running = state.worker_running.lock().unwrap();
    if !*is_running {
        return Ok("Worker is not running".to_string());
    }

    if let Ok(mut id_opt) = state.worker_child_id.lock() {
        if let Some(pid) = *id_opt {
            #[cfg(target_os = "windows")]
            {
                let _ = silent_command("taskkill")
                    .args(["/F", "/T", "/PID", &pid.to_string()])
                    .output();
            }
            #[cfg(not(target_os = "windows"))]
            {
                let _ = Command::new("kill").args(["-9", &pid.to_string()]).output();
            }
            *id_opt = None;
        }
    }

    *is_running = false;
    Ok("Worker stopped".to_string())
}

#[tauri::command]
async fn import_batch_manifest(file_path: String) -> Result<String, String> {
    tokio::task::spawn_blocking(move || {
        let app_dir = get_app_dir();
        let python = get_python_exe(&app_dir);
        let job_mgr = app_dir.join("core").join("job_manager.py");
        let subcmd = if file_path.to_lowercase().ends_with(".csv") {
            "import-csv"
        } else {
            "import-json"
        };

        let output = silent_command(&python)
            .current_dir(&app_dir)
            .args([job_mgr.to_string_lossy().as_ref(), subcmd, &file_path])
            .output()
            .map_err(|e| format!("Failed to import manifest: {e}"))?;

        if output.status.success() {
            Ok(String::from_utf8_lossy(&output.stdout).to_string())
        } else {
            Err(String::from_utf8_lossy(&output.stderr).to_string())
        }
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn preview_tts_voice(text: String, voice: String, gender: Option<String>) -> Result<serde_json::Value, String> {
    tokio::task::spawn_blocking(move || {
        let app_dir = get_app_dir();
        let python = get_python_exe(&app_dir);
        let script = app_dir.join("runners").join("studio_bridge.py");

        let mut cmd = silent_command(&python);
        cmd.current_dir(&app_dir)
            .env("PYTHONUTF8", "1")
            .env("PYTHONIOENCODING", "utf-8")
            .arg(&script)
            .arg("--preview-tts")
            .arg(&text)
            .arg("--voice")
            .arg(&voice);

        if let Some(ref g) = gender {
            cmd.arg("--gender").arg(g);
        }

        let output = cmd
            .output()
            .map_err(|e| format!("Lỗi khởi động tiến trình Python ({python}): {e}"))?;

        let stdout = String::from_utf8_lossy(&output.stdout).trim().to_string();
        let stderr = String::from_utf8_lossy(&output.stderr).trim().to_string();

        if stdout.is_empty() {
            return Err(format!(
                "Tiến trình TTS không trả về kết quả (Mã thoát: {:?}). Chi tiết lỗi: {stderr}",
                output.status.code()
            ));
        }

        serde_json::from_str::<serde_json::Value>(&stdout)
            .map_err(|e| format!("Lỗi phân tích kết quả TTS: {e}. Output: {stdout}. Stderr: {stderr}"))
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn open_output_folder(path: Option<String>) -> Result<(), String> {
    #[cfg(target_os = "windows")]
    {
        if let Some(target) = path {
            if Path::new(&target).is_file() {
                let _ = Command::new("explorer").args(["/select,", &target]).spawn();
                return Ok(());
            }
        }
        let _ = Command::new("explorer").arg("output").spawn();
    }
    Ok(())
}

// =========================================================================
// SECURITY LICENSE & 30-DAY TRIAL ENFORCEMENT
// =========================================================================

const OBFUSCATED_SALT: &[u8] = b"VCS_2026_SECURITY_SALT_PEPPER_9921";
const OBFUSCATED_MASK: [u8; 32] = [
    90, 195, 113, 142, 31, 146, 212, 59, 72, 103, 46, 156, 161, 240, 53, 125,
    139, 20, 98, 233, 56, 92, 175, 112, 211, 33, 148, 133, 110, 183, 74, 19
];
const OBFUSCATED_TARGET: [u8; 32] = [
    26, 78, 92, 184, 64, 146, 74, 225, 188, 109, 96, 179, 23, 99, 86, 232,
    120, 173, 180, 174, 163, 251, 123, 114, 219, 104, 72, 230, 238, 209, 146, 68
];

fn hmac_sha256(key: &[u8], msg: &[u8]) -> [u8; 32] {
    let mut padded_key = [0u8; 64];
    if key.len() > 64 {
        let digest = Sha256::digest(key);
        padded_key[..32].copy_from_slice(&digest);
    } else {
        padded_key[..key.len()].copy_from_slice(key);
    }

    let mut o_key_pad = [0u8; 64];
    let mut i_key_pad = [0u8; 64];
    for i in 0..64 {
        o_key_pad[i] = padded_key[i] ^ 0x5c;
        i_key_pad[i] = padded_key[i] ^ 0x36;
    }

    let mut inner_hasher = Sha256::new();
    inner_hasher.update(&i_key_pad);
    inner_hasher.update(msg);
    let inner_hash = inner_hasher.finalize();

    let mut outer_hasher = Sha256::new();
    outer_hasher.update(&o_key_pad);
    outer_hasher.update(&inner_hash);
    let outer_hash = outer_hasher.finalize();

    let mut result = [0u8; 32];
    result.copy_from_slice(&outer_hash);
    result
}

fn pbkdf2_sha256(pwd: &[u8], salt: &[u8], iters: u32) -> [u8; 32] {
    let mut salt_with_counter = Vec::with_capacity(salt.len() + 4);
    salt_with_counter.extend_from_slice(salt);
    salt_with_counter.extend_from_slice(&1u32.to_be_bytes());

    let mut u = hmac_sha256(pwd, &salt_with_counter);
    let mut result = u;

    for _ in 1..iters {
        u = hmac_sha256(pwd, &u);
        for i in 0..32 {
            result[i] ^= u[i];
        }
    }
    result
}

fn verify_password_input(input_pwd: &str) -> bool {
    let trimmed = input_pwd.trim();
    if trimmed.is_empty() {
        return false;
    }
    let computed = pbkdf2_sha256(trimmed.as_bytes(), OBFUSCATED_SALT, 50000);
    let mut expected = [0u8; 32];
    for i in 0..32 {
        expected[i] = OBFUSCATED_TARGET[i] ^ OBFUSCATED_MASK[i];
    }

    let mut diff = 0u8;
    for i in 0..32 {
        diff |= computed[i] ^ expected[i];
    }
    diff == 0
}

fn get_device_id() -> String {
    #[cfg(target_os = "windows")]
    {
        let reg_out = silent_command("reg")
            .args(["query", r"HKLM\SOFTWARE\Microsoft\Cryptography", "/v", "MachineGuid"])
            .output();
        if let Ok(out) = reg_out {
            let s = String::from_utf8_lossy(&out.stdout);
            for line in s.lines() {
                if line.contains("MachineGuid") {
                    let parts: Vec<&str> = line.split_whitespace().collect();
                    if let Some(guid) = parts.last() {
                        if guid.len() >= 20 {
                            return guid.to_string();
                        }
                    }
                }
            }
        }
    }
    let comp = std::env::var("COMPUTERNAME").unwrap_or_else(|_| "DEFAULT_PC".to_string());
    let user = std::env::var("USERNAME").unwrap_or_else(|_| "DEFAULT_USER".to_string());
    hex::encode(Sha256::digest(format!("{}:{}", comp, user).as_bytes()))
}

#[derive(serde::Serialize, serde::Deserialize, Clone, Debug)]
struct LicenseStore {
    device_id: String,
    first_run_ts: i64,
    last_run_ts: i64,
    is_activated: bool,
    activated_at: Option<String>,
    sig: String,
}

fn compute_license_sig(device_id: &str, first_run_ts: i64, is_activated: bool) -> String {
    let payload = format!("VCS_LIC:{}:{}:{}", device_id, first_run_ts, is_activated);
    hex::encode(hmac_sha256(OBFUSCATED_SALT, payload.as_bytes()))
}

fn get_license_file_paths() -> Vec<std::path::PathBuf> {
    let mut paths = Vec::new();
    paths.push(get_app_dir().join("config").join(".vcs_license.dat"));
    if let Ok(appdata) = std::env::var("APPDATA") {
        paths.push(Path::new(&appdata).join("VideoCreativeStudio").join(".vcs_license.dat"));
    }
    if let Ok(localappdata) = std::env::var("LOCALAPPDATA") {
        paths.push(Path::new(&localappdata).join("VideoCreativeStudio").join(".vcs_license.dat"));
    }
    paths
}

fn load_and_sync_license(device_id: &str) -> LicenseStore {
    let now = chrono::Utc::now().timestamp();
    let paths = get_license_file_paths();
    let mut valid_records = Vec::new();

    for p in &paths {
        if p.is_file() {
            if let Ok(content) = fs::read_to_string(p) {
                if let Ok(rec) = serde_json::from_str::<LicenseStore>(&content) {
                    let expected_sig = compute_license_sig(&rec.device_id, rec.first_run_ts, rec.is_activated);
                    if rec.device_id == device_id && rec.sig == expected_sig {
                        valid_records.push(rec);
                    }
                }
            }
        }
    }

    let mut merged = if valid_records.is_empty() {
        LicenseStore {
            device_id: device_id.to_string(),
            first_run_ts: now,
            last_run_ts: now,
            is_activated: false,
            activated_at: None,
            sig: compute_license_sig(device_id, now, false),
        }
    } else {
        let is_any_activated = valid_records.iter().any(|r| r.is_activated);
        let min_first_run = valid_records.iter().map(|r| r.first_run_ts).min().unwrap_or(now);
        let max_last_run = valid_records.iter().map(|r| r.last_run_ts).max().unwrap_or(now);
        let activated_at = valid_records.iter().find_map(|r| r.activated_at.clone());

        LicenseStore {
            device_id: device_id.to_string(),
            first_run_ts: min_first_run,
            last_run_ts: now.max(max_last_run),
            is_activated: is_any_activated,
            activated_at,
            sig: compute_license_sig(device_id, min_first_run, is_any_activated),
        }
    };

    if now > merged.last_run_ts {
        merged.last_run_ts = now;
    }

    let json_content = serde_json::to_string_pretty(&merged).unwrap_or_default();
    for p in &paths {
        if let Some(parent) = p.parent() {
            let _ = fs::create_dir_all(parent);
        }
        let _ = fs::write(p, &json_content);
    }

    merged
}

#[derive(serde::Serialize, serde::Deserialize, Clone, Debug)]
pub struct LicenseStatus {
    pub is_activated: bool,
    pub is_locked: bool,
    pub status: String,
    pub device_id: String,
    pub days_remaining: u32,
    pub total_trial_days: u32,
    pub first_run_date: String,
}

#[tauri::command]
async fn get_license_status() -> Result<LicenseStatus, String> {
    let device_id = get_device_id();
    let record = load_and_sync_license(&device_id);
    let now = chrono::Utc::now().timestamp();
    let trial_duration_secs: i64 = 30 * 86400; // 30 days = 2,592,000s
    let elapsed = now - record.first_run_ts;

    let is_clock_tampered = now < record.last_run_ts - 86400;

    let (is_locked, status, days_remaining) = if record.is_activated {
        (false, "activated".to_string(), 30)
    } else if is_clock_tampered || elapsed > trial_duration_secs {
        (true, "expired".to_string(), 0)
    } else {
        let remaining = ((trial_duration_secs - elapsed) / 86400).max(0) as u32;
        (false, "trial".to_string(), remaining)
    };

    let first_run_dt = chrono::DateTime::from_timestamp(record.first_run_ts, 0)
        .map(|dt| dt.format("%d/%m/%Y %H:%M").to_string())
        .unwrap_or_else(|| "N/A".to_string());

    Ok(LicenseStatus {
        is_activated: record.is_activated,
        is_locked,
        status,
        device_id,
        days_remaining,
        total_trial_days: 30,
        first_run_date: first_run_dt,
    })
}

#[tauri::command]
async fn verify_license_key(key: String) -> Result<LicenseStatus, String> {
    tokio::time::sleep(tokio::time::Duration::from_millis(300)).await;

    if !verify_password_input(&key) {
        return Err("Mã bảo mật kích hoạt không chính xác. Vui lòng kiểm tra lại.".to_string());
    }

    let device_id = get_device_id();
    let mut record = load_and_sync_license(&device_id);
    let now = chrono::Utc::now();

    record.is_activated = true;
    record.activated_at = Some(now.to_rfc3339());
    record.sig = compute_license_sig(&device_id, record.first_run_ts, true);

    let json_content = serde_json::to_string_pretty(&record).unwrap_or_default();
    for p in get_license_file_paths() {
        if let Some(parent) = p.parent() {
            let _ = fs::create_dir_all(parent);
        }
        let _ = fs::write(p, &json_content);
    }

    let first_run_dt = chrono::DateTime::from_timestamp(record.first_run_ts, 0)
        .map(|dt| dt.format("%d/%m/%Y %H:%M").to_string())
        .unwrap_or_else(|| "N/A".to_string());

    Ok(LicenseStatus {
        is_activated: true,
        is_locked: false,
        status: "activated".to_string(),
        device_id,
        days_remaining: 30,
        total_trial_days: 30,
        first_run_date: first_run_dt,
    })
}

// =========================================================================
// REMOTE AUTO-UPDATER
// =========================================================================

#[derive(serde::Serialize, serde::Deserialize, Clone, Debug)]
pub struct UpdateInfo {
    pub has_update: bool,
    pub current_version: String,
    pub latest_version: String,
    pub mandatory: bool,
    pub release_date: Option<String>,
    pub title: Option<String>,
    pub changelog: Vec<String>,
    pub download_url: Option<String>,
    pub release_page_url: Option<String>,
}

fn parse_semver(v: &str) -> (u32, u32, u32) {
    let clean = v.trim().trim_start_matches('v').trim_start_matches('V');
    let parts: Vec<u32> = clean
        .split('.')
        .filter_map(|p| p.split('-').next().unwrap_or(p).parse().ok())
        .collect();
    (
        parts.get(0).copied().unwrap_or(0),
        parts.get(1).copied().unwrap_or(0),
        parts.get(2).copied().unwrap_or(0),
    )
}

#[tauri::command]
async fn check_app_updates() -> Result<UpdateInfo, String> {
    tokio::task::spawn_blocking(|| {
        let current_version = "1.0.0".to_string();
        let cur_parts = parse_semver(&current_version);

        // 1. Try querying version.json from raw GitHub branch
        let manifest_url = "https://raw.githubusercontent.com/quanittb/video-creative-release/main/version.json";
        let out = silent_command("curl.exe")
            .args(["-s", "-L", "--max-time", "6", "-A", "VideoCreativeStudio/1.0", manifest_url])
            .output();

        if let Ok(res) = out {
            let body = String::from_utf8_lossy(&res.stdout).trim().to_string();
            if res.status.success() && !body.is_empty() && body.starts_with('{') {
                if let Ok(json) = serde_json::from_str::<serde_json::Value>(&body) {
                    if let Some(v_str) = json.get("version").and_then(|v| v.as_str()) {
                        let remote_parts = parse_semver(v_str);
                        let has_update = remote_parts > cur_parts;
                        let mandatory = json.get("mandatory").and_then(|v| v.as_bool()).unwrap_or(false);
                        let title = json.get("title").and_then(|v| v.as_str()).map(|s| s.to_string());
                        let release_date = json.get("release_date").and_then(|v| v.as_str()).map(|s| s.to_string());
                        let download_url = json.get("download_url").and_then(|v| v.as_str()).map(|s| s.to_string());
                        let release_page_url = json.get("release_page_url").and_then(|v| v.as_str()).map(|s| s.to_string());
                        let changelog = json.get("changelog")
                            .and_then(|v| v.as_array())
                            .map(|arr| arr.iter().filter_map(|item| item.as_str().map(|s| s.to_string())).collect())
                            .unwrap_or_default();

                        return Ok(UpdateInfo {
                            has_update,
                            current_version: current_version.clone(),
                            latest_version: v_str.to_string(),
                            mandatory,
                            release_date,
                            title,
                            changelog,
                            download_url,
                            release_page_url,
                        });
                    }
                }
            }
        }

        // 2. Fallback: Query GitHub Releases API
        let api_url = "https://api.github.com/repos/quanittb/video-creative-release/releases/latest";
        let api_out = silent_command("curl.exe")
            .args(["-s", "-L", "--max-time", "6", "-A", "VideoCreativeStudio/1.0", api_url])
            .output();

        if let Ok(res) = api_out {
            let body = String::from_utf8_lossy(&res.stdout).trim().to_string();
            if res.status.success() && !body.is_empty() && body.starts_with('{') {
                if let Ok(json) = serde_json::from_str::<serde_json::Value>(&body) {
                    if let Some(tag) = json.get("tag_name").and_then(|v| v.as_str()) {
                        let remote_parts = parse_semver(tag);
                        let has_update = remote_parts > cur_parts;
                        let body_text = json.get("body").and_then(|v| v.as_str()).unwrap_or("");
                        let mandatory = body_text.to_lowercase().contains("mandatory") || body_text.to_lowercase().contains("bắt buộc");
                        let title = json.get("name").and_then(|v| v.as_str()).map(|s| s.to_string());
                        let release_page_url = json.get("html_url").and_then(|v| v.as_str()).map(|s| s.to_string());

                        let changelog = body_text.lines()
                            .filter(|l| l.trim().starts_with('-') || l.trim().starts_with('*'))
                            .map(|l| l.trim().trim_start_matches(['-', '*', ' ']).to_string())
                            .collect();

                        let download_url = json.get("assets")
                            .and_then(|a| a.as_array())
                            .and_then(|assets| assets.first())
                            .and_then(|first| first.get("browser_download_url"))
                            .and_then(|u| u.as_str())
                            .map(|s| s.to_string());

                        return Ok(UpdateInfo {
                            has_update,
                            current_version: current_version.clone(),
                            latest_version: tag.trim_start_matches('v').to_string(),
                            mandatory,
                            release_date: json.get("published_at").and_then(|v| v.as_str()).map(|s| s.to_string()),
                            title,
                            changelog,
                            download_url,
                            release_page_url,
                        });
                    }
                }
            }
        }

        // Default: No updates found or repository empty
        Ok(UpdateInfo {
            has_update: false,
            current_version: current_version.clone(),
            latest_version: current_version,
            mandatory: false,
            release_date: None,
            title: None,
            changelog: Vec::new(),
            download_url: None,
            release_page_url: Some("https://github.com/quanittb/video-creative-release".to_string()),
        })
    })
    .await
    .map_err(|e| e.to_string())?
}

#[tauri::command]
async fn open_external_url(url: String) -> Result<(), String> {
    #[cfg(target_os = "windows")]
    {
        let _ = Command::new("cmd").args(["/c", "start", "", &url]).spawn();
    }
    Ok(())
}

#[tauri::command]
async fn save_custom_character(
    name: String,
    filename: String,
    data: Vec<u8>,
) -> Result<serde_json::Value, String> {
    let app_dir = get_app_dir();
    let custom_dir = app_dir.join("assets").join("characters").join("custom");
    if let Err(e) = fs::create_dir_all(&custom_dir) {
        return Err(format!("Không thể tạo thư mục lưu nhân vật: {}", e));
    }

    let ext = Path::new(&filename)
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("png");

    let clean_stem = Path::new(&filename)
        .file_stem()
        .and_then(|s| s.to_str())
        .unwrap_or("custom")
        .chars()
        .filter(|c| c.is_alphanumeric() || *c == '_' || *c == '-')
        .collect::<String>();

    let timestamp = chrono::Local::now().format("%Y%m%d_%H%M%S").to_string();
    let unique_filename = format!("{}_{}.{}", clean_stem, timestamp, ext);
    let target_path = custom_dir.join(&unique_filename);

    if let Err(e) = fs::write(&target_path, data) {
        return Err(format!("Lỗi khi lưu ảnh nhân vật: {}", e));
    }

    let rel_path = format!("assets/characters/custom/{}", unique_filename);
    let web_path = format!("/characters/custom/{}", unique_filename);
    let display_name = if name.trim().is_empty() {
        clean_stem
    } else {
        name.trim().to_string()
    };

    Ok(serde_json::json!({
        "id": format!("custom_{}", unique_filename),
        "name": display_name,
        "filename": unique_filename,
        "relPath": rel_path,
        "webPath": web_path,
        "category": "custom",
        "desc": "Nhân vật tùy chọn đã lưu vào thư viện cục bộ",
        "gender": "male"
    }))
}

#[tauri::command]
async fn list_custom_characters() -> Result<Vec<serde_json::Value>, String> {
    let app_dir = get_app_dir();
    let custom_dir = app_dir.join("assets").join("characters").join("custom");
    if !custom_dir.is_dir() {
        return Ok(Vec::new());
    }

    let mut result = Vec::new();
    if let Ok(entries) = fs::read_dir(&custom_dir) {
        for entry in entries.flatten() {
            let path = entry.path();
            if path.is_file() {
                if let Some(ext) = path.extension().and_then(|e| e.to_str()) {
                    let ext_lower = ext.to_lowercase();
                    if ext_lower == "png" || ext_lower == "jpg" || ext_lower == "jpeg" || ext_lower == "webp" {
                        let fname = entry.file_name().to_string_lossy().to_string();
                        let stem = path.file_stem().and_then(|s| s.to_str()).unwrap_or(&fname).to_string();
                        let rel_path = format!("assets/characters/custom/{}", fname);
                        let web_path = format!("/characters/custom/{}", fname);
                        result.push(serde_json::json!({
                            "id": format!("custom_{}", fname),
                            "name": stem,
                            "filename": fname,
                            "relPath": rel_path,
                            "webPath": web_path,
                            "category": "custom",
                            "desc": "Nhân vật tùy chọn trong thư viện",
                            "gender": "male"
                        }));
                    }
                }
            }
        }
    }
    Ok(result)
}

#[tauri::command]
async fn delete_custom_character(filename: String) -> Result<bool, String> {
    let app_dir = get_app_dir();
    let file_path = app_dir.join("assets").join("characters").join("custom").join(&filename);
    if file_path.is_file() {
        fs::remove_file(&file_path).map_err(|e| e.to_string())?;
        Ok(true)
    } else {
        Ok(false)
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(AppState::default())
        .invoke_handler(tauri::generate_handler![
            get_hardware_status,
            list_jobs,
            create_job,
            start_render_worker,
            stop_render_worker,
            cancel_job,
            retry_job,
            clear_completed_jobs,
            import_batch_manifest,
            preview_tts_voice,
            open_output_folder,
            get_license_status,
            verify_license_key,
            check_app_updates,
            open_external_url,
            save_custom_character,
            list_custom_characters,
            delete_custom_character
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_security_auth() {
        let valid_token = String::from_utf8(vec![113, 117, 97, 110, 100, 101, 112, 122, 97, 105]).unwrap();
        assert!(verify_password_input(&valid_token));
        assert!(!verify_password_input("wrong_key_123"));
        assert!(!verify_password_input(""));
        assert!(!verify_password_input("  "));
    }

    #[test]
    fn test_device_id() {
        let dev_id = get_device_id();
        assert!(!dev_id.is_empty());
    }

    #[test]
    fn test_semver() {
        assert_eq!(parse_semver("1.0.1"), (1, 0, 1));
        assert_eq!(parse_semver("v1.2.3"), (1, 2, 3));
        assert!(parse_semver("1.0.1") > parse_semver("1.0.0"));
        assert!(parse_semver("2.0.0") > parse_semver("1.9.9"));
    }
}
