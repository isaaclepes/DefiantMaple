use rusqlite::{params, Connection, OpenFlags};
use serde::Serialize;
use serde_json::Value;
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, AtomicU64, AtomicUsize, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;
use sysinfo::{Pid, System};
use tauri::{AppHandle, State};

const REVIEW_STATES: [&str; 6] = [
    "new",
    "needs_review",
    "reviewed",
    "organized",
    "ignored",
    "error",
];
const TAURI_VERSION: &str = "2.11.6";

#[derive(Clone, Debug, Serialize)]
struct Asset {
    asset_id: String,
    current_path: String,
    media_type: String,
    sha256: String,
    byte_size: i64,
    workflow_state: String,
    discovered_at: String,
}

#[derive(Serialize)]
struct BenchmarkConfig {
    enabled: bool,
    launch_time_ms: Option<f64>,
}

#[derive(Serialize)]
struct BackendInfo {
    framework_version: &'static str,
    rust_version: &'static str,
    platform: String,
    machine: &'static str,
    processor: String,
    cpu_count: usize,
    ci_environment: &'static str,
}

#[derive(Serialize)]
struct TaskSnapshot {
    progress: usize,
    done: bool,
    canceled: bool,
}

struct WorkerTask {
    cancel: Arc<AtomicBool>,
    progress: Arc<AtomicUsize>,
    done: Arc<AtomicBool>,
    canceled: Arc<AtomicBool>,
}

#[derive(Default)]
struct TaskRegistry {
    next_id: AtomicU64,
    tasks: Mutex<HashMap<u64, WorkerTask>>,
}

impl TaskRegistry {
    fn start(&self, units: u32) -> Result<u64, String> {
        if !(1..=100_000).contains(&units) {
            return Err("background task units must be 1..100000".to_string());
        }
        let id = self.next_id.fetch_add(1, Ordering::Relaxed) + 1;
        let cancel = Arc::new(AtomicBool::new(false));
        let progress = Arc::new(AtomicUsize::new(0));
        let done = Arc::new(AtomicBool::new(false));
        let canceled = Arc::new(AtomicBool::new(false));
        self.tasks
            .lock()
            .map_err(|_| "background task registry is poisoned".to_string())?
            .insert(
                id,
                WorkerTask {
                    cancel: Arc::clone(&cancel),
                    progress: Arc::clone(&progress),
                    done: Arc::clone(&done),
                    canceled: Arc::clone(&canceled),
                },
            );
        thread::spawn(move || {
            for unit in 0..units {
                if cancel.load(Ordering::Relaxed) {
                    canceled.store(true, Ordering::Relaxed);
                    done.store(true, Ordering::Release);
                    return;
                }
                let mut value = unit;
                for _ in 0..2_000 {
                    value = value
                        .wrapping_mul(1_664_525)
                        .wrapping_add(1_013_904_223);
                }
                std::hint::black_box(value);
                progress.store(((unit + 1) as usize * 100) / units as usize, Ordering::Relaxed);
                thread::sleep(Duration::from_millis(1));
            }
            progress.store(100, Ordering::Relaxed);
            done.store(true, Ordering::Release);
        });
        Ok(id)
    }

    fn snapshot(&self, id: u64) -> Result<TaskSnapshot, String> {
        let tasks = self
            .tasks
            .lock()
            .map_err(|_| "background task registry is poisoned".to_string())?;
        let task = tasks
            .get(&id)
            .ok_or_else(|| format!("unknown background task {id}"))?;
        Ok(TaskSnapshot {
            progress: task.progress.load(Ordering::Relaxed),
            done: task.done.load(Ordering::Acquire),
            canceled: task.canceled.load(Ordering::Relaxed),
        })
    }

    fn cancel(&self, id: u64) -> Result<(), String> {
        let tasks = self
            .tasks
            .lock()
            .map_err(|_| "background task registry is poisoned".to_string())?;
        let task = tasks
            .get(&id)
            .ok_or_else(|| format!("unknown background task {id}"))?;
        task.cancel.store(true, Ordering::Release);
        Ok(())
    }
}

struct AppState {
    catalog: PathBuf,
    metrics_path: Option<PathBuf>,
    launch_time_ms: Option<f64>,
    tasks: TaskRegistry,
}

impl AppState {
    fn from_environment() -> Result<Self, String> {
        let catalog = std::env::var_os("DEFIANTMAPLE_CATALOG")
            .map(PathBuf::from)
            .or_else(|| {
                let args: Vec<_> = std::env::args_os().collect();
                args.windows(2)
                    .find(|pair| pair[0] == std::ffi::OsStr::new("--catalog"))
                    .map(|pair| PathBuf::from(&pair[1]))
            })
            .ok_or_else(|| {
                "set DEFIANTMAPLE_CATALOG or pass --catalog with a generated catalog".to_string()
            })?;
        let catalog = catalog
            .canonicalize()
            .map_err(|error| format!("cannot open catalog {}: {error}", catalog.display()))?;
        count_assets_at(&catalog, None)?;
        let metrics_path = std::env::var_os("DEFIANTMAPLE_METRICS").map(PathBuf::from);
        let launch_time_ms = std::env::var("DEFIANTMAPLE_LAUNCH_TIME_NS")
            .ok()
            .and_then(|value| value.parse::<f64>().ok())
            .map(|value| value / 1_000_000.0);
        Ok(Self {
            catalog,
            metrics_path,
            launch_time_ms,
            tasks: TaskRegistry::default(),
        })
    }
}

fn validate_state(workflow_state: Option<&str>) -> Result<(), String> {
    if workflow_state.is_some_and(|state| !REVIEW_STATES.contains(&state)) {
        return Err(format!(
            "unknown review state: {}",
            workflow_state.unwrap_or_default()
        ));
    }
    Ok(())
}

fn open_catalog(path: &Path) -> Result<Connection, String> {
    let connection = Connection::open_with_flags(
        path,
        OpenFlags::SQLITE_OPEN_READ_WRITE | OpenFlags::SQLITE_OPEN_NO_MUTEX,
    )
    .map_err(|error| error.to_string())?;
    let version: i64 = connection
        .query_row("PRAGMA user_version", [], |row| row.get(0))
        .map_err(|error| error.to_string())?;
    if version != 2 {
        return Err(format!("unsupported catalog schema {version}"));
    }
    Ok(connection)
}

fn count_assets_at(path: &Path, workflow_state: Option<&str>) -> Result<i64, String> {
    validate_state(workflow_state)?;
    let connection = open_catalog(path)?;
    match workflow_state {
        Some(state) => connection
            .query_row(
                "SELECT COUNT(*) FROM assets WHERE workflow_state=?1",
                [state],
                |row| row.get(0),
            )
            .map_err(|error| error.to_string()),
        None => connection
            .query_row("SELECT COUNT(*) FROM assets", [], |row| row.get(0))
            .map_err(|error| error.to_string()),
    }
}

fn page_assets_at(
    path: &Path,
    workflow_state: Option<&str>,
    offset: i64,
    limit: i64,
) -> Result<Vec<Asset>, String> {
    validate_state(workflow_state)?;
    if offset < 0 || !(1..=1_000).contains(&limit) {
        return Err("offset must be nonnegative and limit must be 1..1000".to_string());
    }
    let connection = open_catalog(path)?;
    let fields = "asset_id,current_path,media_type,sha256,byte_size,workflow_state,discovered_at";
    let mut assets = Vec::new();
    if let Some(state) = workflow_state {
        let mut statement = connection
            .prepare(&format!(
                "SELECT {fields} FROM assets WHERE workflow_state=?1 \
                 ORDER BY discovered_at,asset_id LIMIT ?2 OFFSET ?3"
            ))
            .map_err(|error| error.to_string())?;
        let rows = statement
            .query_map(params![state, limit, offset], asset_from_row)
            .map_err(|error| error.to_string())?;
        for row in rows {
            assets.push(row.map_err(|error| error.to_string())?);
        }
    } else {
        let mut statement = connection
            .prepare(&format!(
                "SELECT {fields} FROM assets ORDER BY discovered_at,asset_id LIMIT ?1 OFFSET ?2"
            ))
            .map_err(|error| error.to_string())?;
        let rows = statement
            .query_map(params![limit, offset], asset_from_row)
            .map_err(|error| error.to_string())?;
        for row in rows {
            assets.push(row.map_err(|error| error.to_string())?);
        }
    }
    Ok(assets)
}

fn asset_from_row(row: &rusqlite::Row<'_>) -> rusqlite::Result<Asset> {
    Ok(Asset {
        asset_id: row.get(0)?,
        current_path: row.get(1)?,
        media_type: row.get(2)?,
        sha256: row.get(3)?,
        byte_size: row.get(4)?,
        workflow_state: row.get(5)?,
        discovered_at: row.get(6)?,
    })
}

fn update_asset_at(path: &Path, asset_id: &str, workflow_state: &str) -> Result<Asset, String> {
    validate_state(Some(workflow_state))?;
    let connection = open_catalog(path)?;
    let changed = connection
        .execute(
            "UPDATE assets SET workflow_state=?1 WHERE asset_id=?2",
            params![workflow_state, asset_id],
        )
        .map_err(|error| error.to_string())?;
    if changed != 1 {
        return Err(format!("unknown asset: {asset_id}"));
    }
    connection
        .query_row(
            "SELECT asset_id,current_path,media_type,sha256,byte_size,workflow_state,discovered_at \
             FROM assets WHERE asset_id=?1",
            [asset_id],
            asset_from_row,
        )
        .map_err(|error| error.to_string())
}

#[tauri::command]
fn count_assets(state: State<'_, AppState>, workflow_state: Option<String>) -> Result<i64, String> {
    count_assets_at(&state.catalog, workflow_state.as_deref())
}

#[tauri::command]
fn page_assets(
    state: State<'_, AppState>,
    workflow_state: Option<String>,
    offset: i64,
    limit: i64,
) -> Result<Vec<Asset>, String> {
    page_assets_at(&state.catalog, workflow_state.as_deref(), offset, limit)
}

#[tauri::command]
fn update_asset_state(
    state: State<'_, AppState>,
    asset_id: String,
    workflow_state: String,
) -> Result<Asset, String> {
    update_asset_at(&state.catalog, &asset_id, &workflow_state)
}

#[tauri::command]
fn start_background_task(state: State<'_, AppState>, units: Option<u32>) -> Result<u64, String> {
    state.tasks.start(units.unwrap_or(400))
}

#[tauri::command]
fn poll_background_task(state: State<'_, AppState>, task_id: u64) -> Result<TaskSnapshot, String> {
    state.tasks.snapshot(task_id)
}

#[tauri::command]
fn cancel_background_task(state: State<'_, AppState>, task_id: u64) -> Result<(), String> {
    state.tasks.cancel(task_id)
}

#[tauri::command]
fn benchmark_config(state: State<'_, AppState>) -> BenchmarkConfig {
    BenchmarkConfig {
        enabled: state.metrics_path.is_some(),
        launch_time_ms: state.launch_time_ms,
    }
}

#[tauri::command]
fn backend_info() -> BackendInfo {
    let system = System::new_all();
    BackendInfo {
        framework_version: TAURI_VERSION,
        rust_version: env!("DEFIANTMAPLE_RUSTC_VERSION"),
        platform: System::long_os_version().unwrap_or_else(|| std::env::consts::OS.to_string()),
        machine: std::env::consts::ARCH,
        processor: system
            .cpus()
            .first()
            .map_or_else(String::new, |cpu| cpu.brand().to_string()),
        cpu_count: thread::available_parallelism().map_or(1, usize::from),
        ci_environment: if std::env::var_os("GITHUB_ACTIONS").is_some() {
            "github-actions"
        } else {
            "local"
        },
    }
}

#[tauri::command]
fn process_rss_bytes() -> Option<u64> {
    let system = System::new_all();
    system
        .process(Pid::from_u32(std::process::id()))
        .map(|process| process.memory())
}

#[tauri::command]
fn write_benchmark_metrics(state: State<'_, AppState>, metrics: Value) -> Result<(), String> {
    let path = state
        .metrics_path
        .as_ref()
        .ok_or_else(|| "benchmark output is not configured".to_string())?;
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent).map_err(|error| error.to_string())?;
    }
    let serialized = serde_json::to_string_pretty(&metrics).map_err(|error| error.to_string())?;
    std::fs::write(path, format!("{serialized}\n")).map_err(|error| error.to_string())
}

#[tauri::command]
fn finish_benchmark(app: AppHandle) {
    app.exit(0);
}

fn main() {
    let state = AppState::from_environment().unwrap_or_else(|error| {
        eprintln!("{error}");
        std::process::exit(2);
    });
    tauri::Builder::default()
        .manage(state)
        .invoke_handler(tauri::generate_handler![
            count_assets,
            page_assets,
            update_asset_state,
            start_background_task,
            poll_background_task,
            cancel_background_task,
            benchmark_config,
            backend_info,
            process_rss_bytes,
            write_benchmark_metrics,
            finish_benchmark,
        ])
        .run(tauri::generate_context!())
        .expect("error while running DefiantMaple Tauri prototype");
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::tempdir;

    fn fixture() -> (tempfile::TempDir, PathBuf) {
        let directory = tempdir().expect("temporary directory");
        let path = directory.path().join("catalog.sqlite3");
        let mut connection = Connection::open(&path).expect("create fixture database");
        connection
            .execute_batch(
                "CREATE TABLE assets (
                    asset_id TEXT PRIMARY KEY,
                    current_path TEXT NOT NULL UNIQUE,
                    media_type TEXT NOT NULL,
                    sha256 TEXT NOT NULL,
                    byte_size INTEGER NOT NULL,
                    workflow_state TEXT NOT NULL,
                    discovered_at TEXT NOT NULL
                );
                CREATE INDEX assets_inbox ON assets(workflow_state, discovered_at);
                PRAGMA user_version = 2;",
            )
            .expect("schema");
        let transaction = connection.transaction().expect("transaction");
        for index in 0..1_001 {
            transaction
                .execute(
                    "INSERT INTO assets VALUES(?1,?2,'image/png',?3,32768,?4,?5)",
                    params![
                        format!("asset-{index:04}"),
                        format!("/synthetic/asset-{index:04}.png"),
                        format!("sha-{index:04}"),
                        REVIEW_STATES[index % REVIEW_STATES.len()],
                        format!("2026-01-01T00:00:{:02}Z", index % 60),
                    ],
                )
                .expect("insert fixture row");
        }
        transaction.commit().expect("commit fixture");
        (directory, path)
    }

    #[test]
    fn pages_filters_and_updates_catalog() {
        let (_directory, path) = fixture();
        assert_eq!(count_assets_at(&path, None).unwrap(), 1_001);
        let first = page_assets_at(&path, None, 0, 256).unwrap();
        assert_eq!(first.len(), 256);
        let before = count_assets_at(&path, Some("new")).unwrap();
        let updated = update_asset_at(&path, &first[0].asset_id, "reviewed").unwrap();
        assert_eq!(updated.workflow_state, "reviewed");
        assert_eq!(count_assets_at(&path, Some("new")).unwrap(), before - 1);
        assert!(count_assets_at(&path, Some("invalid")).is_err());
    }

    #[test]
    fn rejects_invalid_page_bounds() {
        let (_directory, path) = fixture();
        assert!(page_assets_at(&path, None, -1, 10).is_err());
        assert!(page_assets_at(&path, None, 0, 1_001).is_err());
    }
}
