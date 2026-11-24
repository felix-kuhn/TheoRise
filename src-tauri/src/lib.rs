use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;

use serde::Serialize;
use tauri::{AppHandle, Manager, RunEvent, State};

struct RunningBackend {
    child: Child,
    port: u16,
    token: String,
}

#[derive(Default)]
struct ManagedBackend {
    inner: Mutex<Option<RunningBackend>>,
}

impl ManagedBackend {
    fn info(&self) -> Option<BackendInfo> {
        let guard = self.inner.lock().ok()?;
        guard.as_ref().map(|backend| BackendInfo {
            base_url: format!("http://127.0.0.1:{}", backend.port),
            token: backend.token.clone(),
        })
    }

    fn stop(&self) {
        if let Ok(mut guard) = self.inner.lock() {
            if let Some(mut backend) = guard.take() {
                let _ = backend.child.kill();
                let _ = backend.child.wait();
            }
        }
    }
}

impl Drop for ManagedBackend {
    fn drop(&mut self) {
        self.stop();
    }
}

#[derive(Serialize)]
#[serde(rename_all = "camelCase")]
struct BackendInfo {
    base_url: String,
    token: String,
}

/// Resolve the interpreter of the existing `poc-backend` conda env.
///
/// `POC_BACKEND_PYTHON` overrides the lookup so the app never relies on a
/// bare `python` in PATH (see docs/plan/00_OVERVIEW.md).
fn resolve_dev_python() -> Result<PathBuf, String> {
    if let Ok(path) = std::env::var("POC_BACKEND_PYTHON") {
        let path = path.trim();
        if !path.is_empty() {
            return Ok(PathBuf::from(path));
        }
    }

    let home = std::env::var("HOME").unwrap_or_default();
    let mut candidates = vec!["conda".to_string()];
    if !home.is_empty() {
        candidates.push(format!("{home}/miniconda3/bin/conda"));
        candidates.push(format!("{home}/miniconda/bin/conda"));
    }

    let mut last_error = String::new();
    for conda in candidates {
        let output = Command::new(&conda)
            .args([
                "run",
                "-n",
                "poc-backend",
                "python",
                "-c",
                "import sys;print(sys.executable)",
            ])
            .output();

        match output {
            Ok(output) if output.status.success() => {
                let path = String::from_utf8_lossy(&output.stdout).trim().to_string();
                if !path.is_empty() {
                    return Ok(PathBuf::from(path));
                }
                last_error = format!("{conda}: returned an empty interpreter path");
            }
            Ok(output) => {
                last_error = format!(
                    "{conda}: {}",
                    String::from_utf8_lossy(&output.stderr).trim()
                );
            }
            Err(err) => {
                last_error = format!("{conda}: {err}");
            }
        }
    }

    Err(format!(
        "could not resolve the backend interpreter: {last_error}"
    ))
}

fn read_port(child: &mut Child) -> Result<u16, String> {
    let stdout = child
        .stdout
        .take()
        .ok_or_else(|| "backend stdout was not captured".to_string())?;
    let mut reader = BufReader::new(stdout);
    let mut line = String::new();
    let read = reader
        .read_line(&mut line)
        .map_err(|err| format!("failed to read backend port line: {err}"))?;

    if read == 0 || line.trim().is_empty() {
        return Err("backend exited before printing its port line".to_string());
    }

    let payload: serde_json::Value = serde_json::from_str(line.trim())
        .map_err(|err| format!("invalid backend port line: {err}"))?;
    let port = payload
        .get("port")
        .and_then(|value| value.as_u64())
        .and_then(|value| u16::try_from(value).ok())
        .filter(|value| *value > 0)
        .ok_or_else(|| "backend did not report a valid port".to_string())?;
    Ok(port)
}

fn spawn_dev_backend(token: &str) -> Result<(Child, u16), String> {
    let python = resolve_dev_python()?;
    let backend_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("src-backend");

    let mut child = Command::new(&python)
        .args(["-m", "app", "--port", "0", "--token", token])
        .current_dir(&backend_dir)
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit())
        .spawn()
        .map_err(|err| format!("failed to start backend: {err}"))?;

    let port = read_port(&mut child)?;
    Ok((child, port))
}

fn spawn_sidecar_backend(data_dir: &Path, token: &str) -> Result<(Child, u16), String> {
    let binary = std::env::var("POC_BACKEND_BINARY").map_err(|_| {
        "production mode requires POC_BACKEND_BINARY (sidecar packaging lands in increment 13)"
            .to_string()
    })?;
    let data_dir = data_dir
        .to_str()
        .ok_or_else(|| "data directory is not valid UTF-8".to_string())?;

    let mut child = Command::new(binary)
        .args(["--port", "0", "--token", token, "--data-dir", data_dir])
        .stdout(Stdio::piped())
        .stderr(Stdio::inherit())
        .spawn()
        .map_err(|err| format!("failed to start sidecar backend: {err}"))?;

    let port = read_port(&mut child)?;
    Ok((child, port))
}

fn backend_mode() -> String {
    std::env::var("POC_BACKEND_MODE").unwrap_or_else(|_| {
        if cfg!(debug_assertions) {
            "dev".to_string()
        } else {
            "prod".to_string()
        }
    })
}

fn spawn_backend(app: &AppHandle, token: &str) -> Result<(Child, u16), String> {
    match backend_mode().as_str() {
        "prod" => {
            let data_dir = app.path().app_data_dir().map_err(|err| err.to_string())?;
            spawn_sidecar_backend(&data_dir, token)
        }
        _ => spawn_dev_backend(token),
    }
}

#[tauri::command]
async fn start_backend(
    app: AppHandle,
    state: State<'_, ManagedBackend>,
) -> Result<BackendInfo, String> {
    if let Some(info) = state.info() {
        return Ok(info);
    }

    let token = uuid::Uuid::new_v4().simple().to_string();
    let spawn_token = token.clone();
    let (child, port) =
        tauri::async_runtime::spawn_blocking(move || spawn_backend(&app, &spawn_token))
            .await
            .map_err(|err| format!("backend startup task failed: {err}"))??;

    let mut guard = state
        .inner
        .lock()
        .map_err(|_| "backend state lock is poisoned".to_string())?;

    if let Some(existing) = guard.as_ref() {
        // Another call started the backend while this one was spawning.
        let mut extra = child;
        let _ = extra.kill();
        let _ = extra.wait();
        return Ok(BackendInfo {
            base_url: format!("http://127.0.0.1:{}", existing.port),
            token: existing.token.clone(),
        });
    }

    guard.replace(RunningBackend {
        child,
        port,
        token: token.clone(),
    });

    Ok(BackendInfo {
        base_url: format!("http://127.0.0.1:{port}"),
        token,
    })
}

#[tauri::command]
fn get_backend_info(state: State<'_, ManagedBackend>) -> Result<BackendInfo, String> {
    state
        .info()
        .ok_or_else(|| "backend has not been started".to_string())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_http::init())
        .manage(ManagedBackend::default())
        .invoke_handler(tauri::generate_handler![start_backend, get_backend_info])
        .build(tauri::generate_context!())
        .expect("error while building tauri application");

    app.run(|app_handle, event| {
        if let RunEvent::Exit = event {
            app_handle.state::<ManagedBackend>().stop();
        }
    });
}

#[cfg(test)]
mod tests {
    use super::BackendInfo;

    #[test]
    fn backend_info_uses_camel_case_json_keys() {
        let info = BackendInfo {
            base_url: "http://127.0.0.1:1234".to_string(),
            token: "secret".to_string(),
        };

        let value = serde_json::to_value(info).expect("backend info should serialize");
        assert_eq!(value["baseUrl"], "http://127.0.0.1:1234");
        assert!(value.get("base_url").is_none());
        assert_eq!(value["token"], "secret");
    }
}
