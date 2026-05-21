use tauri::{Manager, WindowBuilder, WindowUrl, PhysicalPosition};

#[tauri::command]
fn spawn_pet_window(app: tauri::AppHandle, species: String) {
    if let Some(old) = app.get_window("pet") {
        let _ = old.close();
    }

    let window = match WindowBuilder::new(&app, "pet", WindowUrl::App("pet.html".into()))
        .title("")
        .inner_size(160.0, 160.0)
        .position(1000.0, 500.0)
        .always_on_top(true)
        .decorations(false)
        .transparent(true)
        .skip_taskbar(true)
        .resizable(false)
        .focused(false)
        .visible(false)
        .build()
    {
        Ok(w) => w,
        Err(e) => {
            eprintln!("Failed to create pet window: {}", e);
            return;
        }
    };

    let win = window.clone();
    window.once("tauri://created", move |_| {
        let _ = win.eval(&format!(
            r#"window.__PET_INIT__ = {{ species: "{}" }};
               window.dispatchEvent(new Event('pet-init'));"#,
            species
        ));
        let _ = win.show();
    });
}

#[tauri::command]
fn move_pet_window(app: tauri::AppHandle, x: f64, y: f64) {
    if let Some(win) = app.get_window("pet") {
        let _ = win.set_position(PhysicalPosition::new(x, y));
    }
}

#[tauri::command]
fn pet_speak_bubble(app: tauri::AppHandle, text: String) {
    if let Some(win) = app.get_window("pet") {
        let _ = win.eval(&format!(
            r#"window.__PET_SPEAK__("{}");"#,
            text.replace('"', "\\\"").replace('\n', "\\n")
        ));
    }
}

#[tauri::command]
fn hide_pet_window(app: tauri::AppHandle) {
    if let Some(win) = app.get_window("pet") {
        let _ = win.close();
    }
}

#[tauri::command]
fn switch_pet_species(app: tauri::AppHandle, species: String) {
    if let Some(win) = app.get_window("pet") {
        let _ = win.eval(&format!(
            r#"window.__PET_SWITCH__ = {{ species: "{}" }};
               window.dispatchEvent(new Event('pet-switch'));"#,
            species
        ));
        let _ = win.show();
        let _ = win.set_focus();
    } else {
        spawn_pet_window(app, species);
    }
}
