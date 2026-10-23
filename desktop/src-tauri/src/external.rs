//! Enlaces que la app puede abrir en el navegador del sistema.
//!
//! El dashboard solo enlaza a la descarga de Ollama y a este repositorio. Cualquier otra cosa se ignora:
//! una oferta o un correo con un enlace raro no debe poder abrir nada desde la app.

use tauri::Url;

const REPO_PATH: &str = "/javipiazza94/jobhunter-es";
const OLLAMA_HOSTS: [&str; 2] = ["ollama.com", "www.ollama.com"];

pub fn is_allowed(raw: &str) -> bool {
    let Ok(url) = Url::parse(raw) else { return false };
    if url.scheme() != "https" || !url.username().is_empty() || url.password().is_some() {
        return false;
    }
    match url.host_str() {
        Some(host) if OLLAMA_HOSTS.contains(&host) => true,
        Some("github.com") => {
            let path = url.path();
            path == REPO_PATH || path.starts_with(&format!("{REPO_PATH}/"))
        }
        _ => false,
    }
}

/// ¿Es una página de la propia app? Solo esas pueden cargarse en la ventana.
pub fn is_app_url(url: &Url) -> bool {
    match (url.scheme(), url.host_str()) {
        ("tauri", Some("localhost")) => true,
        ("http" | "https", Some("tauri.localhost")) => true,
        ("about", _) => true,
        // `tauri dev` sirve el dashboard desde Next.js.
        ("http", Some("localhost")) => cfg!(debug_assertions) && url.port() == Some(3010),
        _ => false,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn permite_ollama_y_este_repositorio() {
        assert!(is_allowed("https://ollama.com/download"));
        assert!(is_allowed("https://github.com/javipiazza94/jobhunter-es/releases/tag/v0.1.0"));
        assert!(is_allowed("https://github.com/javipiazza94/jobhunter-es"));
    }

    #[test]
    fn rechaza_todo_lo_demas() {
        for bad in [
            "http://ollama.com/download",
            "https://ollama.com.evil.example/",
            "https://evil.example/ollama.com",
            "https://github.com/otro/repo",
            "https://github.com/javipiazza94/jobhunter-es-fake",
            "https://user:pw@ollama.com/",
            "file:///etc/passwd",
            "javascript:alert(1)",
            "no es una url",
        ] {
            assert!(!is_allowed(bad), "{bad}");
        }
    }

    #[test]
    fn solo_las_paginas_de_la_app_cargan_en_la_ventana() {
        let ok = |s: &str| is_app_url(&Url::parse(s).unwrap());
        assert!(ok("tauri://localhost/index.html"));
        assert!(ok("http://tauri.localhost/"));
        assert!(ok("https://tauri.localhost/"));
        assert!(!ok("https://ollama.com/"));
        assert!(!ok("http://127.0.0.1:8020/api/stats"));
        assert!(!ok("http://localhost:8020/"));
        assert!(!ok("tauri://evil/"));
    }
}
