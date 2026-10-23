//! El backend (FastAPI congelado con PyInstaller) como proceso hijo.
//!
//! Protocolo: el backend abre su puerto en 127.0.0.1, imprime `JH_READY port=N` por stdout y, si se
//! cierra su stdin (la app murió), se apaga solo. Ver `backend/desktop_main.py`.

use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::mpsc;
use std::time::{Duration, Instant};

pub const READY_PREFIX: &str = "JH_READY port=";
const STARTUP_TIMEOUT: Duration = Duration::from_secs(90);
const STOP_GRACE: Duration = Duration::from_secs(5);

pub fn parse_ready(line: &str) -> Option<u16> {
    line.trim().strip_prefix(READY_PREFIX)?.trim().parse::<u16>().ok().filter(|p| *p > 0)
}

pub fn api_url(port: u16) -> String {
    format!("http://127.0.0.1:{port}")
}

pub fn executable_path(resources: &Path) -> PathBuf {
    let name = if cfg!(windows) { "jobhunter-api.exe" } else { "jobhunter-api" };
    resources.join("jobhunter-api").join(name)
}

/// Script que se ejecuta en la ventana antes que la página: URL de la API, marca de escritorio y
/// apertura de enlaces externos en el navegador del sistema (lista blanca en `external.rs`).
pub fn init_script(port: u16) -> String {
    format!(
        r#"window.__JH_API_URL__ = "{url}";
window.__JH_DESKTOP__ = true;
document.addEventListener("click", function (e) {{
  var a = e.target && e.target.closest ? e.target.closest("a[href]") : null;
  if (!a) return;
  var u; try {{ u = new URL(a.href, location.href); }} catch (_) {{ return; }}
  if (u.protocol === "https:" || u.protocol === "http:") {{
    if (u.hostname === "tauri.localhost" || u.hostname === location.hostname) return;
    e.preventDefault();
    window.__TAURI_INTERNALS__.invoke("open_external", {{ url: u.href }}).catch(function () {{}});
  }}
}}, true);"#,
        url = api_url(port)
    )
}

/// Lee líneas hasta encontrar la de aviso; `forward` recibe cada línea (para el registro).
pub fn read_until_ready<R: BufRead>(reader: R, mut forward: impl FnMut(&str)) -> Option<u16> {
    for line in reader.lines().map_while(Result::ok) {
        forward(&line);
        if let Some(port) = parse_ready(&line) {
            return Some(port);
        }
    }
    None
}

pub struct Backend {
    child: Child,
    pub port: u16,
}

impl Backend {
    pub fn start(exe: &Path, bundled_bin: Option<&Path>, extra_origins: Option<&str>) -> Result<Backend, String> {
        if !exe.exists() {
            return Err(format!("No se encuentra el backend en {}", exe.display()));
        }
        let mut cmd = Command::new(exe);
        cmd.env("JH_PARENT_WATCH", "1")
            .stdin(Stdio::piped())
            .stdout(Stdio::piped())
            .stderr(Stdio::piped());
        if let Some(bin) = bundled_bin {
            cmd.env("JH_BUNDLED_BIN", bin);
        }
        if let Some(origins) = extra_origins {
            cmd.env("JH_DESKTOP_EXTRA_ORIGINS", origins);
        }
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            cmd.creation_flags(0x0800_0000); // CREATE_NO_WINDOW
        }
        let mut child = cmd.spawn().map_err(|e| format!("No se pudo lanzar el backend: {e}"))?;

        let stdout = child.stdout.take().ok_or("El backend no tiene stdout")?;
        let stderr = child.stderr.take().ok_or("El backend no tiene stderr")?;
        let (tx, rx) = mpsc::channel();
        std::thread::spawn(move || {
            let mut reader = BufReader::new(stdout);
            if let Some(port) = read_until_ready(&mut reader, |l| eprintln!("[backend] {l}")) {
                let _ = tx.send(port);
            }
            // Sigue leyendo para que el backend no se bloquee con la tubería llena.
            for line in reader.lines().map_while(Result::ok) {
                eprintln!("[backend] {line}");
            }
        });
        std::thread::spawn(move || {
            for line in BufReader::new(stderr).lines().map_while(Result::ok) {
                eprintln!("[backend] {line}");
            }
        });

        match rx.recv_timeout(STARTUP_TIMEOUT) {
            Ok(port) => Ok(Backend { child, port }),
            Err(err) => {
                let _ = child.kill();
                let _ = child.wait();
                Err(match err {
                    mpsc::RecvTimeoutError::Timeout => "El backend tardó demasiado en arrancar.".to_string(),
                    mpsc::RecvTimeoutError::Disconnected => "El backend se cerró antes de arrancar.".to_string(),
                })
            }
        }
    }

    /// Cierra stdin (parada ordenada) y, si no termina a tiempo, lo mata.
    pub fn stop(&mut self) {
        drop(self.child.stdin.take());
        let deadline = Instant::now() + STOP_GRACE;
        while Instant::now() < deadline {
            if matches!(self.child.try_wait(), Ok(Some(_))) {
                return;
            }
            std::thread::sleep(Duration::from_millis(100));
        }
        let _ = self.child.kill();
        let _ = self.child.wait();
    }

    #[cfg_attr(not(test), allow(dead_code))]
    pub fn is_running(&mut self) -> bool {
        matches!(self.child.try_wait(), Ok(None))
    }
}

impl Drop for Backend {
    fn drop(&mut self) {
        self.stop();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Cursor;

    #[test]
    fn lee_la_linea_de_aviso() {
        assert_eq!(parse_ready("JH_READY port=54321"), Some(54321));
        assert_eq!(parse_ready("  JH_READY port=8020\r\n"), Some(8020));
        for bad in ["", "JH_READY port=0", "JH_READY port=70000", "JH_READY port=abc", "INFO: Started server", "xJH_READY port=1"] {
            assert_eq!(parse_ready(bad), None, "{bad}");
        }
    }

    #[test]
    fn salta_el_ruido_hasta_el_aviso_y_lo_reenvia() {
        let salida = "INFO Iniciando\nWARN algo\nJH_READY port=4242\nINFO listo\n";
        let mut vistas = Vec::new();
        let port = read_until_ready(Cursor::new(salida), |l| vistas.push(l.to_string()));
        assert_eq!(port, Some(4242));
        assert_eq!(vistas, vec!["INFO Iniciando", "WARN algo", "JH_READY port=4242"]);
    }

    #[test]
    fn sin_aviso_no_hay_puerto() {
        assert_eq!(read_until_ready(Cursor::new("solo ruido\n"), |_| {}), None);
    }

    #[test]
    fn el_script_de_inicio_fija_la_url_y_la_marca() {
        let js = init_script(53211);
        assert!(js.contains(r#"window.__JH_API_URL__ = "http://127.0.0.1:53211";"#));
        assert!(js.contains("window.__JH_DESKTOP__ = true;"));
        assert!(js.contains("open_external"));
    }

    #[test]
    fn la_ruta_del_ejecutable_cuelga_de_los_recursos() {
        let p = executable_path(Path::new("/opt/app/resources"));
        assert!(p.starts_with("/opt/app/resources/jobhunter-api"));
        assert!(p.file_name().unwrap().to_string_lossy().starts_with("jobhunter-api"));
    }

    #[test]
    fn sin_ejecutable_el_error_es_claro() {
        let err = Backend::start(Path::new("/no/existe/jobhunter-api"), None, None).err().unwrap();
        assert!(err.contains("No se encuentra el backend"));
    }

    /// Un «backend» de mentira: anuncia el puerto y se queda leyendo stdin hasta que se cierre.
    #[cfg(unix)]
    fn falso_backend(dir: &Path, cuerpo: &str) -> PathBuf {
        use std::os::unix::fs::PermissionsExt;
        let path = dir.join("falso-backend");
        std::fs::write(&path, format!("#!/bin/sh\n{cuerpo}\n")).unwrap();
        std::fs::set_permissions(&path, std::fs::Permissions::from_mode(0o755)).unwrap();
        path
    }

    #[cfg(unix)]
    #[test]
    fn arranca_anuncia_el_puerto_y_se_para_al_cerrar_stdin() {
        let dir = std::env::temp_dir().join(format!("jh-sidecar-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let exe = falso_backend(&dir, "echo 'ruido'\necho \"JH_READY port=${JH_FAKE_PORT:-4321}\"\ncat > /dev/null");
        let mut backend = Backend::start(&exe, None, None).unwrap();
        assert_eq!(backend.port, 4321);
        assert!(backend.is_running());
        backend.stop();
        assert!(!backend.is_running());
        let _ = std::fs::remove_dir_all(dir);
    }

    /// Con el backend congelado de verdad: `JH_FROZEN_BACKEND=<ruta a jobhunter-api> cargo test -- --ignored`.
    #[test]
    #[ignore]
    fn con_el_backend_congelado_real() {
        let exe = PathBuf::from(std::env::var("JH_FROZEN_BACKEND").expect("define JH_FROZEN_BACKEND"));
        let home = std::env::temp_dir().join(format!("jh-real-{}", std::process::id()));
        std::env::set_var("JH_HOME", &home);
        let mut backend = Backend::start(&exe, None, None).unwrap();
        assert!(backend.port > 0 && backend.is_running());
        backend.stop();
        assert!(!backend.is_running());
        let _ = std::fs::remove_dir_all(home);
    }

    #[cfg(unix)]
    #[test]
    fn si_el_backend_muere_antes_de_avisar_se_informa() {
        let dir = std::env::temp_dir().join(format!("jh-sidecar-muerto-{}", std::process::id()));
        std::fs::create_dir_all(&dir).unwrap();
        let exe = falso_backend(&dir, "echo 'fallo de arranque' >&2\nexit 3");
        let err = Backend::start(&exe, None, None).err().unwrap();
        assert!(err.contains("se cerró antes de arrancar"), "{err}");
        let _ = std::fs::remove_dir_all(dir);
    }
}
