//! Native subprocess oracle: hold until one stdin line/EOF, without SQLite or GUI.
#[path = "../../src-tauri/src/admission.rs"]
mod admission;
use std::io::{self, Write};
fn main() {
    let result = (|| -> Result<(), String> {
        let path = std::env::args_os().nth(1).ok_or("catalog path required")?;
        let owner = admission::Admission::acquire(std::path::Path::new(&path))?;
        println!("ADMITTED");
        io::stdout().flush().map_err(|e| e.to_string())?;
        let mut command = String::new();
        io::stdin().read_line(&mut command).map_err(|e| e.to_string())?;
        owner.validate()?;
        Ok(())
    })();
    if let Err(error) = result { eprintln!("{error}"); std::process::exit(2); }
}
