use std::sync::{Arc, Mutex};
use std::time::Duration;
use tauri::Manager;
use tauri_plugin_shell::process::CommandChild;
use tauri_plugin_shell::ShellExt;

struct BackendProcess(Arc<Mutex<Option<CommandChild>>>);

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_dialog::init())
        .setup(|app| {
            // In release builds, start the bundled Python backend as a sidecar.
            // In development, the backend should be started manually with:
            //   python backend.py
            #[cfg(not(debug_assertions))]
            {
                let handle = app.handle().clone();
                let sidecar = handle
                    .shell()
                    .sidecar("abvme-server")
                    .expect("abvme-server sidecar not found");

                let (_rx, child) = sidecar.spawn().expect("Failed to start backend");
                app.manage(BackendProcess(Arc::new(Mutex::new(Some(child)))));

                // Brief pause to let the backend initialise before the webview loads
                std::thread::sleep(Duration::from_millis(1500));
            }
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                // Kill the sidecar when the window closes
                if let Some(state) = window.try_state::<BackendProcess>() {
                    if let Ok(mut guard) = state.0.lock() {
                        if let Some(child) = guard.take() {
                            let _ = child.kill();
                        }
                    }
                }
            }
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
