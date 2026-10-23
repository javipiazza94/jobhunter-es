//! JobHunter de escritorio: ventana de Tauri + backend FastAPI congelado como proceso hijo.

mod external;
mod sidecar;
mod update;

use std::path::PathBuf;
use std::sync::Mutex;

use tauri::{AppHandle, Manager, RunEvent, WebviewUrl, WebviewWindowBuilder};
use tauri_plugin_dialog::{DialogExt, MessageDialogButtons, MessageDialogKind};
use tauri_plugin_opener::OpenerExt;

#[derive(Default)]
struct BackendState(Mutex<Option<sidecar::Backend>>);

/// Abre un enlace permitido en el navegador del sistema (ver `external::is_allowed`).
#[tauri::command]
fn open_external(app: AppHandle, url: String) -> Result<(), String> {
    if !external::is_allowed(&url) {
        return Err("Enlace no permitido".into());
    }
    app.opener().open_url(url, None::<&str>).map_err(|e| e.to_string())
}

fn backend_executable(app: &AppHandle) -> Result<(PathBuf, Option<PathBuf>), String> {
    // JH_BACKEND_EXE permite probar con otro ejecutable (p. ej. un script que lance `python backend/desktop_main.py`).
    if let Ok(custom) = std::env::var("JH_BACKEND_EXE") {
        return Ok((PathBuf::from(custom), None));
    }
    let resources = app.path().resource_dir().map_err(|e| format!("Sin carpeta de recursos: {e}"))?;
    let bin = resources.join("bin");
    Ok((sidecar::executable_path(&resources), bin.is_dir().then_some(bin)))
}

fn fail(app: &AppHandle, message: &str) {
    app.dialog()
        .message(format!("JobHunter no ha podido arrancar.\n\n{message}"))
        .title("JobHunter")
        .kind(MessageDialogKind::Error)
        .blocking_show();
    app.exit(1);
}

fn boot(app: AppHandle) {
    let (exe, bundled_bin) = match backend_executable(&app) {
        Ok(found) => found,
        Err(e) => return fail(&app, &e),
    };
    let extra_origins = cfg!(debug_assertions).then_some("http://localhost:3010");
    let backend = match sidecar::Backend::start(&exe, bundled_bin.as_deref(), extra_origins) {
        Ok(b) => b,
        Err(e) => return fail(&app, &e),
    };
    let port = backend.port;
    *app.state::<BackendState>().0.lock().unwrap() = Some(backend);

    let built = WebviewWindowBuilder::new(&app, "main", WebviewUrl::App("index.html".into()))
        .title("JobHunter")
        .inner_size(1360.0, 860.0)
        .min_inner_size(900.0, 600.0)
        .initialization_script(sidecar::init_script(port))
        .on_navigation(|url| external::is_app_url(url))
        .build();
    if let Err(e) = built {
        return fail(&app, &format!("No se pudo abrir la ventana: {e}"));
    }

    // Aviso de versión nueva; sin red no pasa nada.
    if let Some(release) = update::latest_release() {
        if update::is_newer(env!("CARGO_PKG_VERSION"), &release.tag) {
            let opener = app.clone();
            app.dialog()
                .message(format!(
                    "Hay una versión nueva de JobHunter ({}). Esta app no se actualiza sola: descárgala desde la página de la versión.",
                    release.tag
                ))
                .title("JobHunter")
                .kind(MessageDialogKind::Info)
                .buttons(MessageDialogButtons::OkCancelCustom("Ver descarga".into(), "Más tarde".into()))
                .show(move |open| {
                    if open {
                        let _ = opener.opener().open_url(release.url, None::<&str>);
                    }
                });
        }
    }
}

pub fn run() {
    let app = tauri::Builder::default()
        // Dos instancias abrirían dos backends sobre la misma base de datos.
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.unminimize();
                let _ = window.set_focus();
            }
        }))
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .manage(BackendState::default())
        .invoke_handler(tauri::generate_handler![open_external])
        .setup(|app| {
            let handle = app.handle().clone();
            std::thread::spawn(move || boot(handle));
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error al construir la aplicación");

    app.run(|handle, event| {
        if let RunEvent::Exit = event {
            if let Some(mut backend) = handle.state::<BackendState>().0.lock().unwrap().take() {
                backend.stop();
            }
        }
    });
}
