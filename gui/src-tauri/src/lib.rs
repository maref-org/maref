use portable_pty::{native_pty_system, PtySize, CommandBuilder};
use std::io::Write;
use std::process::{Command, Child};
use std::sync::Mutex;
use tauri::{Manager, State, WebviewWindowBuilder, PhysicalPosition, Listener};

pub struct PtyState {
    pub master: Option<Box<dyn portable_pty::MasterPty + Send>>,
    pub writer: Option<Box<dyn Write + Send>>,
    pub pid: u32,
}

pub struct SidecarState {
    pub process: Option<Child>,
}

pub struct AppState {
    pub pty: Mutex<PtyState>,
    pub sidecar: Mutex<SidecarState>,
}

// ── PTY Commands ──

#[tauri::command]
fn pty_spawn(state: State<AppState>, shell: Option<String>, rows: Option<u16>, cols: Option<u16>) -> Result<u32, String> {
    let mut pty = state.pty.lock().map_err(|e| e.to_string())?;
    if pty.master.is_some() {
        return Ok(pty.pid);
    }

    let sys = native_pty_system();
    let size = PtySize { rows: rows.unwrap_or(24), cols: cols.unwrap_or(80), pixel_width: 0, pixel_height: 0 };

    let pair = sys.openpty(size).map_err(|e| e.to_string())?;
    let shell_path = shell.unwrap_or_else(|| std::env::var("SHELL").unwrap_or_else(|_| "/bin/zsh".into()));
    let cmd = CommandBuilder::new(&shell_path);
    let child = pair.slave.spawn_command(cmd).map_err(|e| e.to_string())?;

    let writer = pair.master.take_writer().map_err(|e| e.to_string())?;
    let pid = child.process_id().unwrap_or(0);

    pty.master = Some(pair.master);
    pty.writer = Some(Box::new(writer));
    pty.pid = pid;

    Ok(pid)
}

#[tauri::command]
fn pty_write(state: State<AppState>, data: String) -> Result<(), String> {
    let mut pty = state.pty.lock().map_err(|e| e.to_string())?;
    if let Some(ref mut writer) = pty.writer {
        writer.write_all(data.as_bytes()).map_err(|e| e.to_string())?;
        writer.flush().map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[tauri::command]
fn pty_resize(state: State<AppState>, rows: u16, cols: u16) -> Result<(), String> {
    let pty = state.pty.lock().map_err(|e| e.to_string())?;
    if let Some(ref master) = pty.master {
        master.resize(PtySize { rows, cols, pixel_width: 0, pixel_height: 0 }).map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[tauri::command]
fn pty_kill(state: State<AppState>) -> Result<(), String> {
    let mut pty = state.pty.lock().map_err(|e| e.to_string())?;
    pty.master = None;
    pty.writer = None;
    pty.pid = 0;
    Ok(())
}

// ── Sidecar Commands ──

#[tauri::command]
fn sidecar_start(state: State<AppState>) -> Result<(), String> {
    let mut s = state.sidecar.lock().map_err(|e| e.to_string())?;
    if s.process.is_some() {
        return Ok(());
    }

    let child = Command::new("maref")
        .args(["serve", "--port", "8000", "--gui"])
        .spawn()
        .map_err(|e| format!("Failed to start maref serve: {}", e))?;

    s.process = Some(child);
    Ok(())
}

#[tauri::command]
fn sidecar_stop(state: State<AppState>) -> Result<(), String> {
    let mut s = state.sidecar.lock().map_err(|e| e.to_string())?;
    if let Some(mut child) = s.process.take() {
        let _ = child.kill();
    }
    Ok(())
}

// ── Shell / Dialog Commands ──

#[tauri::command]
async fn open_external(url: String) -> Result<(), String> {
    open::that(url).map_err(|e| e.to_string())
}

// ── Pet Window Commands ──

#[tauri::command]
fn spawn_pet_window(app: tauri::AppHandle, species: String) -> Result<(), String> {
    if let Some(old) = app.get_webview_window("pet") {
        let _ = old.close();
    }

    let win = WebviewWindowBuilder::new(&app, "pet", tauri::WebviewUrl::App("pet.html".into()))
        .title("")
        .inner_size(160.0, 180.0)
        .position(1000.0, 400.0)
        .always_on_top(true)
        .decorations(false)
        .transparent(true)
        .skip_taskbar(true)
        .resizable(false)
        .visible(false)
        .build()
        .map_err(|e| e.to_string())?;

    let species_clone = species.clone();
    let w = win.clone();
    win.once("tauri://created", move |_| {
        let _ = w.eval(&format!(
            r#"window.__PET_INIT__ = {{ species: "{}" }};
               window.dispatchEvent(new Event('pet-init'));"#,
            species_clone
        ));
        let _ = w.show();
        let _ = w.set_focus();
    });

    Ok(())
}

#[tauri::command]
fn move_pet_window(app: tauri::AppHandle, x: f64, y: f64) -> Result<(), String> {
    if let Some(win) = app.get_webview_window("pet") {
        win.set_position(PhysicalPosition::new(x, y)).map_err(|e| e.to_string())?;
    }
    Ok(())
}

#[tauri::command]
fn pet_speak_bubble(app: tauri::AppHandle, text: String) -> Result<(), String> {
    if let Some(win) = app.get_webview_window("pet") {
        let escaped = text.replace('"', "\\\"").replace('\n', "\\n");
        let _ = win.eval(&format!(r#"window.__PET_SPEAK__("{}");"#, escaped));
    }
    Ok(())
}

#[tauri::command]
fn hide_pet_window(app: tauri::AppHandle) -> Result<(), String> {
    if let Some(win) = app.get_webview_window("pet") {
        let _ = win.close();
    }
    Ok(())
}

#[tauri::command]
fn switch_pet_species(app: tauri::AppHandle, species: String) -> Result<(), String> {
    if let Some(win) = app.get_webview_window("pet") {
        let _ = win.eval(&format!(
            r#"window.__PET_SWITCH__ = {{ species: "{}" }};
               window.dispatchEvent(new Event('pet-switch'));"#,
            species
        ));
        let _ = win.show();
        let _ = win.set_focus();
    } else {
        return spawn_pet_window(app, species);
    }
    Ok(())
}

// ── App Setup ──

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_updater::Builder::new().build())
        .manage(AppState {
            pty: Mutex::new(PtyState {
                master: None, writer: None, pid: 0,
            }),
            sidecar: Mutex::new(SidecarState { process: None }),
        })
        .invoke_handler(tauri::generate_handler![
            pty_spawn, pty_write, pty_resize, pty_kill,
            sidecar_start, sidecar_stop,
            open_external,
            spawn_pet_window, move_pet_window, pet_speak_bubble, hide_pet_window, switch_pet_species,
        ])
        .setup(|app| {
            let sidecar_state = app.state::<AppState>();
            if let Ok(mut s) = sidecar_state.sidecar.lock() {
                s.process = Command::new("maref")
                    .args(["serve", "--port", "8000", "--gui"])
                    .spawn()
                    .ok();
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("MAREF Agent failed to start");
}
