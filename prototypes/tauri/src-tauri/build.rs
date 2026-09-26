use std::process::Command;

fn main() {
    let rustc = Command::new("rustc")
        .arg("--version")
        .output()
        .ok()
        .filter(|output| output.status.success())
        .and_then(|output| String::from_utf8(output.stdout).ok())
        .unwrap_or_else(|| "rustc version unavailable".to_string());
    println!("cargo:rustc-env=DEFIANTMAPLE_RUSTC_VERSION={}", rustc.trim());
    tauri_build::build();
}
