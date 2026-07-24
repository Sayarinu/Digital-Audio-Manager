use serde_json::{json, Value};
use std::{
    path::PathBuf,
    process::Command,
    sync::atomic::{AtomicBool, Ordering},
};
use tauri::Manager;

static QUEUE_RUNNING: AtomicBool = AtomicBool::new(false);

fn worker_path(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    let development_path = PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../python/worker.py");
    if development_path.is_file() {
        return Ok(development_path);
    }
    let resources = app.path().resource_dir().map_err(|error| error.to_string())?;
    // Tauri preserves the source-relative resource path in a bundled app.
    // Accept both that layout and the flat layout used by custom packagers.
    for candidate in [resources.join("_up_/python/worker.py"), resources.join("worker.py")] {
        if candidate.is_file() {
            return Ok(candidate);
        }
    }
    Ok(resources.join("worker.py"))
}

fn run_worker_command(app: tauri::AppHandle, method: String, payload: Value) -> Result<Value, String> {
    let worker = worker_path(&app)?;
    if !worker.is_file() {
        return Err(format!("Digital Audio Manager worker was not found at {}", worker.display()));
    }
    let input = serde_json::to_string(&json!({ "method": method, "payload": payload })).map_err(|error| error.to_string())?;
    // The worker consumes a single JSON request. Supplying it through stdin keeps
    // user data out of process arguments and avoids a network surface.
    let python = if PathBuf::from("/opt/homebrew/bin/python3").is_file() { "/opt/homebrew/bin/python3" } else { "/usr/bin/python3" };
    let child = Command::new(python)
        .arg(worker)
        .env("MP3_MAKER_REQUEST", input)
        .output()
        .map_err(|error| format!("Could not launch local worker: {error}"))?;
    let output = child;
    let response: Value = serde_json::from_slice(&output.stdout)
        .map_err(|error| format!("Worker returned invalid JSON ({error}): {}", String::from_utf8_lossy(&output.stderr)))?;
    if response.get("ok").and_then(Value::as_bool) == Some(true) {
        Ok(response.get("data").cloned().unwrap_or(Value::Null))
    } else {
        Err(response.get("error").and_then(Value::as_str).unwrap_or("Unknown worker failure").to_string())
    }
}

#[tauri::command]
fn worker_command(app: tauri::AppHandle, method: String, payload: Value) -> Result<Value, String> {
    run_worker_command(app, method, payload)
}

/// Start the serial downloader on a worker thread and return immediately so
/// the WebView can keep handling input and polling SQLite-backed progress.
#[tauri::command]
fn start_queue(app: tauri::AppHandle) -> Result<Value, String> {
    if QUEUE_RUNNING
        .compare_exchange(false, true, Ordering::AcqRel, Ordering::Acquire)
        .is_ok()
    {
        let queue_app = app.clone();
        std::thread::spawn(move || {
            if let Err(error) = run_worker_command(queue_app, "run_queue".to_string(), json!({})) {
                eprintln!("Digital Audio Manager background queue stopped: {error}");
            }
            QUEUE_RUNNING.store(false, Ordering::Release);
        });
    }
    run_worker_command(app, "dashboard".to_string(), json!({}))
}

#[tauri::command]
fn open_library(app: tauri::AppHandle) -> Result<Value, String> {
    let health = run_worker_command(app.clone(), "health_check".to_string(), json!({}))?;
    let path = health
        .get("library_root")
        .and_then(Value::as_str)
        .ok_or_else(|| "The local library path is unavailable.".to_string())?;
    let library = PathBuf::from(path);
    std::fs::create_dir_all(&library).map_err(|error| format!("Could not create the local library: {error}"))?;

    #[cfg(target_os = "macos")]
    let mut command = Command::new("open");
    #[cfg(target_os = "windows")]
    let mut command = Command::new("explorer");
    #[cfg(all(unix, not(target_os = "macos")))]
    let mut command = Command::new("xdg-open");

    command.arg(&library).spawn().map_err(|error| format!("Could not open the local library: {error}"))?;
    run_worker_command(app, "dashboard".to_string(), json!({}))
}

pub fn run() {
    tauri::Builder::default()
        .invoke_handler(tauri::generate_handler![worker_command, start_queue, open_library])
        .run(tauri::generate_context!())
        .expect("error while running Digital Audio Manager");
}
