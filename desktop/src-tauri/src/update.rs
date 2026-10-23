//! Aviso de versión nueva. Sin actualización automática ni firma: solo avisa y enlaza a la release.

use std::time::Duration;

use serde::Deserialize;

const LATEST_URL: &str = "https://api.github.com/repos/javipiazza94/jobhunter-es/releases/latest";
const RELEASE_PREFIX: &str = "https://github.com/javipiazza94/jobhunter-es/";

#[derive(Debug, PartialEq, Eq)]
pub struct Release {
    pub tag: String,
    pub url: String,
}

#[derive(Deserialize)]
struct RawRelease {
    tag_name: String,
    html_url: String,
    #[serde(default)]
    draft: bool,
    #[serde(default)]
    prerelease: bool,
}

/// `v1.2.3`, `1.2.3-beta.1` o `1.2.3+build` → (1, 2, 3). Cualquier otra cosa → None.
pub fn parse_version(raw: &str) -> Option<(u64, u64, u64)> {
    let core = raw.trim().trim_start_matches(['v', 'V']);
    let core = core.split(['-', '+']).next()?;
    let mut parts = core.split('.');
    let major = parts.next()?.parse().ok()?;
    let minor = parts.next()?.parse().ok()?;
    let patch = parts.next()?.parse().ok()?;
    if parts.next().is_some() {
        return None;
    }
    Some((major, minor, patch))
}

pub fn is_newer(current: &str, latest: &str) -> bool {
    match (parse_version(current), parse_version(latest)) {
        (Some(c), Some(l)) => l > c,
        _ => false,
    }
}

/// Lee la respuesta de `releases/latest`. Descarta borradores, prereleases y enlaces que no sean de este repositorio.
pub fn parse_release(json: &str) -> Option<Release> {
    let raw: RawRelease = serde_json::from_str(json).ok()?;
    if raw.draft || raw.prerelease || !raw.html_url.starts_with(RELEASE_PREFIX) {
        return None;
    }
    Some(Release { tag: raw.tag_name, url: raw.html_url })
}

/// Consulta la última release. Cualquier fallo (sin red, límite de GitHub…) es `None`: nunca molesta.
pub fn latest_release() -> Option<Release> {
    let body = ureq::get(LATEST_URL)
        .set("Accept", "application/vnd.github+json")
        .set("User-Agent", "jobhunter-desktop")
        .timeout(Duration::from_secs(8))
        .call()
        .ok()?
        .into_string()
        .ok()?;
    parse_release(&body)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn lee_versiones() {
        assert_eq!(parse_version("v1.2.3"), Some((1, 2, 3)));
        assert_eq!(parse_version("0.10.0"), Some((0, 10, 0)));
        assert_eq!(parse_version("1.2.3-beta.1"), Some((1, 2, 3)));
        assert_eq!(parse_version("1.2.3+abc"), Some((1, 2, 3)));
        for bad in ["", "1.2", "1.2.3.4", "a.b.c", "latest"] {
            assert_eq!(parse_version(bad), None, "{bad}");
        }
    }

    #[test]
    fn compara_numericamente_no_como_texto() {
        assert!(is_newer("0.9.0", "v0.10.0"));
        assert!(is_newer("1.0.0", "1.0.1"));
        assert!(!is_newer("1.0.1", "1.0.1"));
        assert!(!is_newer("2.0.0", "v1.9.9"));
        assert!(!is_newer("1.0.0", "no es versión"));
    }

    #[test]
    fn solo_acepta_releases_publicadas_de_este_repositorio() {
        let ok = r#"{"tag_name":"v0.2.0","html_url":"https://github.com/javipiazza94/jobhunter-es/releases/tag/v0.2.0","draft":false,"prerelease":false}"#;
        assert_eq!(
            parse_release(ok),
            Some(Release { tag: "v0.2.0".into(), url: "https://github.com/javipiazza94/jobhunter-es/releases/tag/v0.2.0".into() })
        );
        let draft = ok.replace(r#""draft":false"#, r#""draft":true"#);
        assert_eq!(parse_release(&draft), None);
        let pre = ok.replace(r#""prerelease":false"#, r#""prerelease":true"#);
        assert_eq!(parse_release(&pre), None);
        let foreign = ok.replace("javipiazza94/jobhunter-es", "evil/phishing");
        assert_eq!(parse_release(&foreign), None);
        assert_eq!(parse_release("{}"), None);
        assert_eq!(parse_release("no es json"), None);
    }
}
