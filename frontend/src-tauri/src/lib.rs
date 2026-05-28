use std::fs;
use std::path::PathBuf;
use std::process::{Child, Command};
use std::sync::{Arc, Mutex};
use tauri::path::BaseDirectory;
use tauri::{AppHandle, Emitter, Manager, State, Window};

#[cfg(target_os = "windows")]
use std::os::windows::process::CommandExt;

struct AppState {
    python_process: Arc<Mutex<Option<Child>>>,
}

#[tauri::command]
async fn check_factory_status(app: AppHandle) -> Result<bool, String> {
    let app_dir = app.path().app_data_dir().map_err(|e| e.to_string())?;
    let env_path = app_dir.join("python_env");
    let bin_path = app_dir.join("bin").join("magick.exe");
    Ok(env_path.exists() && bin_path.exists())
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

    // 1. Extract Bundled Binaries (FFmpeg/ImageMagick)
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

        #[cfg(target_os = "windows")]
        {
            let copy_cmd = format!(
                "Copy-Item -Path '{}/*' -Destination '{}' -Recurse -Force",
                resource_bin.to_str().unwrap(),
                bin_dest.to_str().unwrap()
            );
            run_command("powershell", &["-Command", &copy_cmd], &app_dir)?;
        }

        #[cfg(not(target_os = "windows"))]
        {
            let copy_cmd = format!(
                "cp -r {}/* {}",
                resource_bin.to_str().unwrap(),
                bin_dest.to_str().unwrap()
            );
            run_command("sh", &["-c", &copy_cmd], &app_dir)?;
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

    // 5. Warm up Whisper
    window
        .emit("setup-progress", "Warming up local AI models...")
        .unwrap();
    let python_env_exe = if cfg!(target_os = "windows") {
        app_dir.join("python_env").join("Scripts").join("python")
    } else {
        app_dir.join("python_env").join("bin").join("python")
    };
    run_command(
        python_env_exe.to_str().unwrap(),
        &["-c", "import whisper; whisper.load_model('small')"],
        &app_dir,
    )?;

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
    let app_dir = app.path().app_data_dir().map_err(|e| e.to_string())?;
    let python_exe = if cfg!(target_os = "windows") {
        app_dir.join("python_env").join("Scripts").join("python")
    } else {
        app_dir.join("python_env").join("bin").join("python")
    };

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
    *state.python_process.lock().unwrap() = Some(child);

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
