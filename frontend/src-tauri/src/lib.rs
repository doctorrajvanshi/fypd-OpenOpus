use std::fs;
use std::path::{Path, PathBuf};
use std::process::{Child, Command};
use std::sync::{Arc, Mutex};
use tauri::path::BaseDirectory;
use tauri::{AppHandle, Emitter, Manager, State, Window};

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

struct AppState {
    python_process: Arc<Mutex<Option<Child>>>,
}

/// Written only after every setup step succeeds.
const SETUP_MARKER: &str = ".fypd_setup_complete";

#[tauri::command]
async fn check_factory_status(app: AppHandle) -> Result<bool, String> {
    let app_dir = app.path().app_data_dir().map_err(|e| e.to_string())?;

    // A marker file, not a directory-existence probe. The old check looked for
    // bin/magick.exe, which never exists off Windows — so macOS and Linux
    // rebuilt the venv and reinstalled every dependency on each launch — while
    // on Windows a setup that died midway still left python_env/ behind and was
    // treated as complete.
    Ok(app_dir.join(SETUP_MARKER).exists() && python_exe_path(&app_dir).exists())
}

/// Path to the interpreter inside the managed virtual environment.
fn python_exe_path(app_dir: &Path) -> PathBuf {
    if cfg!(target_os = "windows") {
        app_dir
            .join("python_env")
            .join("Scripts")
            .join("python.exe")
    } else {
        app_dir.join("python_env").join("bin").join("python")
    }
}

#[tauri::command]
async fn initialize_factory(app: AppHandle, window: Window) -> Result<(), String> {
    let app_dir = app.path().app_data_dir().map_err(|e| e.to_string())?;

    if !app_dir.exists() {
        fs::create_dir_all(&app_dir).map_err(|e| e.to_string())?;
    }

    let python_exe = if cfg!(target_os = "windows") {
        "python"
    } else {
        "python3"
    };

    // Pre-validate Python exists in system PATH
    let has_python = Command::new(python_exe).arg("--version").output().is_ok();

    if !has_python {
        return Err("Python 3.10+ is required to run the neural editing engine but was not found in your system PATH. Please download and install Python (and make sure to check the 'Add Python to PATH' option during installation) before launching fypd.".to_string());
    }

    // 1. Extract Bundled Binaries (FFmpeg/ImageMagick).
    // Windows only: the bundled bin/ holds Windows PE binaries and DLLs, which
    // are useless on macOS/Linux where ffmpeg and ImageMagick come from the
    // system package manager.
    #[cfg(target_os = "windows")]
    {
        let bin_dest = app_dir.join("bin");
        if !bin_dest.exists() {
            fs::create_dir_all(&bin_dest).map_err(|e| e.to_string())?;
        }

        if !bin_dest.join("magick.exe").exists() {
            window
                .emit("setup-progress", "Extracting core rendering binaries...")
                .unwrap();
            let resource_bin = app
                .path()
                .resolve("bin", BaseDirectory::Resource)
                .map_err(|e| e.to_string())?;

            let copy_cmd = format!(
                "Copy-Item -LiteralPath '{}\\*' -Destination '{}' -Recurse -Force",
                resource_bin.to_string_lossy().replace('\'', "''"),
                bin_dest.to_string_lossy().replace('\'', "''")
            );
            run_command(
                "powershell",
                &["-NoProfile", "-Command", &copy_cmd],
                &app_dir,
            )?;

            if !bin_dest.join("magick.exe").exists() {
                return Err(
                    "Failed to extract the bundled ImageMagick binaries. Caption rendering \
                     needs them — try reinstalling fypd, or install ImageMagick separately \
                     and add it to your PATH."
                        .to_string(),
                );
            }
        }
    }

    // 2. Create Venv
    window
        .emit("setup-progress", "Creating isolated neural environment...")
        .unwrap();
    run_command(python_exe, &["-m", "venv", "python_env"], &app_dir)?;

    // 3. Install Dependencies
    let pip_path = if cfg!(target_os = "windows") {
        app_dir.join("python_env").join("Scripts").join("pip")
    } else {
        app_dir.join("python_env").join("bin").join("pip")
    };

    window
        .emit(
            "setup-progress",
            "Installing AI dependencies (this may take a few minutes)...",
        )
        .unwrap();
    let req_path = app
        .path()
        .resolve("requirements.txt", BaseDirectory::Resource)
        .map_err(|e| e.to_string())?;
    run_command(
        pip_path.to_str().unwrap(),
        &["install", "-r", req_path.to_str().unwrap()],
        &app_dir,
    )?;

    // 4. Install Playwright
    window
        .emit(
            "setup-progress",
            "Configuring TikTok automation protocols...",
        )
        .unwrap();
    run_command(
        pip_path.to_str().unwrap(),
        &["install", "playwright"],
        &app_dir,
    )?;

    let playwright_path = if cfg!(target_os = "windows") {
        app_dir
            .join("python_env")
            .join("Scripts")
            .join("playwright")
    } else {
        app_dir.join("python_env").join("bin").join("playwright")
    };
    run_command(
        playwright_path.to_str().unwrap(),
        &["install", "chromium"],
        &app_dir,
    )?;

    // 5. Warm up Whisper.
    // Must match WHISPER_MODEL in viral_clipper.py — warming 'small' while the
    // engine loads 'base' downloaded ~460 MB that nothing ever used, and the
    // first job then paid for the 'base' download anyway.
    window
        .emit("setup-progress", "Warming up local AI models...")
        .unwrap();
    let python_env_exe = python_exe_path(&app_dir);
    run_command(
        python_env_exe.to_str().unwrap(),
        &["-c", "import whisper; whisper.load_model('base')"],
        &app_dir,
    )?;

    // Only now is setup genuinely complete.
    fs::write(app_dir.join(SETUP_MARKER), env!("CARGO_PKG_VERSION")).map_err(|e| e.to_string())?;

    window.emit("setup-progress", "Ready").unwrap();
    Ok(())
}

fn run_command(cmd: &str, args: &[&str], cwd: &PathBuf) -> Result<(), String> {
    let mut command = Command::new(cmd);
    command.args(args).current_dir(cwd);

    #[cfg(target_os = "windows")]
    command.creation_flags(0x08000000); // CREATE_NO_WINDOW

    let output = command.output().map_err(|e| e.to_string())?;
    if !output.status.success() {
        return Err(String::from_utf8_lossy(&output.stderr).to_string());
    }
    Ok(())
}

#[tauri::command]
async fn start_factory_server(app: AppHandle, state: State<'_, AppState>) -> Result<(), String> {
    // Never spawn a second backend over a live one; the duplicate would fail to
    // bind port 8000 and die, leaving the UI pointed at whichever won the race.
    {
        let mut guard = state.python_process.lock().map_err(|e| e.to_string())?;
        let still_running = guard
            .as_mut()
            .map(|child| matches!(child.try_wait(), Ok(None)))
            .unwrap_or(false);
        if still_running {
            return Ok(());
        }
        *guard = None;
    }

    let app_dir = app.path().app_data_dir().map_err(|e| e.to_string())?;
    let python_exe = python_exe_path(&app_dir);

    let server_path = app
        .path()
        .resolve("app_server.py", BaseDirectory::Resource)
        .map_err(|e| e.to_string())?;

    let mut command = Command::new(python_exe);
    command
        .arg(server_path)
        .current_dir(&app_dir)
        .env("FYPD_DATA_DIR", app_dir.to_str().unwrap_or(""));

    #[cfg(target_os = "windows")]
    command.creation_flags(0x08000000); // CREATE_NO_WINDOW

    let child = command.spawn().map_err(|e| e.to_string())?;
    *state.python_process.lock().map_err(|e| e.to_string())? = Some(child);

    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_process::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(AppState {
            python_process: Arc::new(Mutex::new(None)),
        })
        .invoke_handler(tauri::generate_handler![
            check_factory_status,
            initialize_factory,
            start_factory_server
        ])
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                let state: State<AppState> = window.state();
                let mut process_guard = state.python_process.lock().unwrap();
                if let Some(mut child) = process_guard.take() {
                    let _ = child.kill();
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
