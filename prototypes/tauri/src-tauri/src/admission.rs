//! Same-user participating executable coordination, not a Core API security boundary.
use std::{fs::File, path::{Path, PathBuf}, sync::{Arc, Mutex, OnceLock, Weak}};
use sha2::{Digest, Sha256};

type Result<T> = std::result::Result<T, String>;
const BUSY: &str = "Library is in use. Close the other application using this library and retry.";
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
struct Identity(u64, u128);

pub fn key(kind: &str, platform: &str, first: u64, second: u128, leaf: &[u8]) -> String {
    let hex: String = leaf.iter().map(|byte| format!("{byte:02x}")).collect();
    format!("dm-admission-v1\n{kind}\n{platform}\n{first}\n{second}\n{hex}\n")
}
pub fn key_hash(value: &str) -> String { format!("{:x}", Sha256::digest(value.as_bytes())) }
fn native_error(error: std::io::Error) -> String { format!("Library admission failed: {error}") }

struct Owner {
    // Retained for RAII ownership only; field order releases reservations before
    // closing pinned identity handles.
    _leases: Vec<native::Lease>,
    pid: u32,
    path: PathBuf,
    parent: PathBuf,
    directory: File,
    catalog: File,
    parent_id: Identity,
    file_id: Identity,
}
impl Owner {
    fn validate(&self) -> Result<()> {
        if self.pid != std::process::id() { return Err("Inherited admission session is invalid".into()); }
        let directory = native::identity_open(&self.parent, true)?;
        let catalog = native::identity_open(&self.path, false)?;
        if native::identity(&directory)? != self.parent_id
            || native::identity(&catalog)? != self.file_id
            || native::identity(&self.directory)? != self.parent_id
            || native::identity(&self.catalog)? != self.file_id {
            return Err("Library path changed. Close this application and reopen the library.".into());
        }
        Ok(())
    }
}
#[derive(Clone)]
pub struct Admission(Arc<Owner>);
static OWNERS: OnceLock<Mutex<Vec<Weak<Owner>>>> = OnceLock::new();
impl Admission {
    pub fn acquire(path: &Path) -> Result<Self> { Self::at_registry(path, native::registry()?) }
    fn at_registry(path: &Path, registry: PathBuf) -> Result<Self> {
        let path = path.canonicalize().map_err(native_error)?;
        let parent = path.parent().ok_or("Catalog has no parent")?.to_path_buf();
        let mut owners = OWNERS.get_or_init(|| Mutex::new(Vec::new())).lock()
            .map_err(|_| "Library admission manager is poisoned")?;
        owners.retain(|entry| entry.strong_count() > 0);
        for owner in owners.iter().filter_map(Weak::upgrade) {
            if owner.path == path {
                owner.validate()?;
                return Ok(Self(owner));
            }
        }
        native::prepare_registry(&registry)?;
        let directory = native::identity_open(&parent, true)?;
        let parent_id = native::identity(&directory)?;
        let make_key = |kind, id: Identity, leaf: &[u8]| key(kind, native::PLATFORM, id.0, id.1, leaf);
        let gate = native::Lease::acquire(&registry.join(format!("{}.lock", key_hash(&make_key("directory", parent_id, &[])))))?;
        let path_lease = native::Lease::acquire(&registry.join(format!("{}.lock", key_hash(&make_key("path", parent_id, &native::leaf(&path)?)))))?;
        let catalog = native::identity_open(&path, false)?;
        let file_id = native::identity(&catalog)?;
        let file_lease = native::Lease::acquire(&registry.join(format!("{}.lock", key_hash(&make_key("file", file_id, &[])))))?;
        let owner = Arc::new(Owner { pid: std::process::id(), path, parent, directory, catalog,
            parent_id, file_id, _leases: vec![file_lease, path_lease] });
        owner.validate()?;
        drop(gate);
        owners.push(Arc::downgrade(&owner));
        Ok(Self(owner))
    }
    pub fn validate(&self) -> Result<()> { self.0.validate() }
}

#[cfg(any(target_os = "linux", target_os = "macos"))]
mod native {
    use super::*;
    use std::{ffi::CStr, os::unix::{ffi::OsStrExt, fs::{MetadataExt, OpenOptionsExt, DirBuilderExt}, io::AsRawFd}};
    pub const PLATFORM: &str = "posix";
    pub fn registry() -> Result<PathBuf> {
        unsafe {
            let uid = libc::getuid();
            if uid != libc::geteuid() { return Err("Admission refuses differing real/effective user IDs".into()); }
            let mut size = 1024usize;
            loop {
                let mut buffer = vec![0u8; size];
                let mut record: libc::passwd = std::mem::zeroed();
                let mut found = std::ptr::null_mut();
                let status = libc::getpwuid_r(uid, &mut record, buffer.as_mut_ptr().cast(), size, &mut found);
                if status == libc::ERANGE && size < 1_048_576 { size *= 2; continue; }
                if status != 0 || found.is_null() || record.pw_dir.is_null() {
                    return Err("Cannot determine OS account home for admission".into());
                }
                let home = PathBuf::from(std::ffi::OsStr::from_bytes(CStr::from_ptr(record.pw_dir).to_bytes()));
                if !home.is_absolute() { return Err("OS account home is not absolute".into()); }
                return Ok(home.join(".defiantmaple/admission-v1"));
            }
        }
    }
    fn check(path: &Path, directory: bool) -> Result<()> {
        let metadata = std::fs::symlink_metadata(path).map_err(native_error)?;
        if metadata.file_type().is_symlink() || metadata.uid() != unsafe { libc::getuid() }
            || metadata.mode() & 0o077 != 0 || (if directory { !metadata.is_dir() } else { !metadata.is_file() }) {
            return Err("Unsafe library admission registry path".into());
        }
        Ok(())
    }
    pub fn prepare_registry(path: &Path) -> Result<()> {
        let base = path.parent().ok_or("Invalid registry path")?;
        for directory in [base, path] {
            match std::fs::DirBuilder::new().mode(0o700).create(directory) {
                Ok(()) => (), Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => (),
                Err(error) => return Err(native_error(error)),
            }
            check(directory, true)?;
        }
        Ok(())
    }
    pub fn identity_open(path: &Path, directory: bool) -> Result<File> {
        let file = std::fs::OpenOptions::new().read(true)
            .custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW | libc::O_NONBLOCK | if directory { libc::O_DIRECTORY } else { 0 })
            .open(path).map_err(native_error)?;
        let metadata = file.metadata().map_err(native_error)?;
        if if directory { !metadata.is_dir() } else { !metadata.is_file() } { return Err("Invalid catalog identity file type".into()); }
        Ok(file)
    }
    pub fn identity(file: &File) -> Result<Identity> {
        let metadata = file.metadata().map_err(native_error)?;
        if metadata.ino() == 0 { return Err("Unavailable catalog inode".into()); }
        Ok(Identity(metadata.dev(), metadata.ino() as u128))
    }
    pub fn leaf(path: &Path) -> Result<Vec<u8>> { Ok(path.file_name().ok_or("Missing catalog basename")?.as_bytes().to_vec()) }
    // Retain the descriptor until Drop closes it and releases ownership. Never
    // explicitly unlock an inherited flock open-file description.
    pub struct Lease { _file: File }
    impl Lease {
        pub fn acquire(path: &Path) -> Result<Self> {
            let file = std::fs::OpenOptions::new().read(true).write(true).create(true).truncate(false)
                .mode(0o600).custom_flags(libc::O_CLOEXEC | libc::O_NOFOLLOW).open(path).map_err(native_error)?;
            check(path, false)?;
            let metadata = file.metadata().map_err(native_error)?;
            let named = std::fs::symlink_metadata(path).map_err(native_error)?;
            if metadata.uid() != unsafe { libc::getuid() } || metadata.mode() & 0o077 != 0
                || !metadata.is_file() || metadata.dev() != named.dev() || metadata.ino() != named.ino() { return Err("Registry lock path changed".into()); }
            if unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) } != 0 {
                let error = std::io::Error::last_os_error();
                return Err(if error.kind() == std::io::ErrorKind::WouldBlock { BUSY.into() } else { native_error(error) });
            }
            Ok(Self { _file: file })
        }
    }
}

#[cfg(windows)]
mod native {
    use super::*;
    use std::os::windows::{ffi::{OsStrExt, OsStringExt}, io::{AsRawHandle, FromRawHandle}};
    use windows_sys::Win32::{Foundation::*, Storage::FileSystem::*, System::{IO::OVERLAPPED, Com::CoTaskMemFree}, UI::Shell::{SHGetKnownFolderPath, FOLDERID_LocalAppData}};
    pub const PLATFORM: &str = "windows";
    fn wide(path: &Path) -> Vec<u16> { path.as_os_str().encode_wide().chain(Some(0)).collect() }
    pub fn registry() -> Result<PathBuf> {
        unsafe {
            let mut pointer = std::ptr::null_mut();
            let status = SHGetKnownFolderPath(&FOLDERID_LocalAppData, 0, std::ptr::null_mut(), &mut pointer);
            if status < 0 || pointer.is_null() { return Err("Cannot determine native LocalAppData for admission".into()); }
            let mut length = 0;
            while *pointer.add(length) != 0 { length += 1; }
            let path = PathBuf::from(std::ffi::OsString::from_wide(std::slice::from_raw_parts(pointer, length)));
            CoTaskMemFree(pointer.cast());
            if !path.is_absolute() { return Err("Native LocalAppData is not absolute".into()); }
            Ok(path.join("DefiantMaple/admission-v1"))
        }
    }
    fn open(path: &Path, access: u32, share: u32, creation: u32, flags: u32) -> Result<File> {
        let handle = unsafe { CreateFileW(wide(path).as_ptr(), access, share, std::ptr::null(), creation,
            flags | FILE_FLAG_OPEN_REPARSE_POINT, std::ptr::null_mut()) };
        if handle == INVALID_HANDLE_VALUE { return Err(native_error(std::io::Error::last_os_error())); }
        Ok(unsafe { File::from_raw_handle(handle.cast()) })
    }
    fn info(file: &File) -> Result<BY_HANDLE_FILE_INFORMATION> {
        let mut information = unsafe { std::mem::zeroed() };
        if unsafe { GetFileInformationByHandle(file.as_raw_handle().cast(), &mut information) } == 0 {
            return Err(native_error(std::io::Error::last_os_error()));
        }
        if information.dwFileAttributes & FILE_ATTRIBUTE_REPARSE_POINT != 0 {
            return Err("Admission registry or catalog is a reparse point".into());
        }
        if unsafe { GetFileType(file.as_raw_handle().cast()) } != FILE_TYPE_DISK { return Err("Admission requires disk files".into()); }
        Ok(information)
    }
    pub fn prepare_registry(path: &Path) -> Result<()> {
        for directory in [path.parent().ok_or("Invalid registry path")?, path] {
            match std::fs::create_dir(directory) {
                Ok(()) => (), Err(error) if error.kind() == std::io::ErrorKind::AlreadyExists => (),
                Err(error) => return Err(native_error(error)),
            }
            identity_open(directory, true)?;
        }
        Ok(())
    }
    pub fn identity_open(path: &Path, directory: bool) -> Result<File> {
        let file = open(path, FILE_READ_ATTRIBUTES, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
            OPEN_EXISTING, if directory { FILE_FLAG_BACKUP_SEMANTICS } else { 0 })?;
        let information = info(&file)?;
        if (information.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY != 0) != directory {
            return Err("Invalid catalog identity file type".into());
        }
        Ok(file)
    }
    pub fn identity(file: &File) -> Result<Identity> {
        // Attribute/type validation uses BY_HANDLE_FILE_INFORMATION only; identity
        // never falls back to its truncated 64-bit nFileIndex on ReFS.
        info(file)?;
        let mut information: FILE_ID_INFO = unsafe { std::mem::zeroed() };
        if unsafe { GetFileInformationByHandleEx(file.as_raw_handle().cast(), FileIdInfo,
            (&mut information as *mut FILE_ID_INFO).cast(), std::mem::size_of::<FILE_ID_INFO>() as u32) } == 0 {
            return Err(native_error(std::io::Error::last_os_error()));
        }
        // The opaque byte array has no API numeric endianness. This reversible
        // little-endian interpretation is the shared Python/Rust key protocol.
        let index = u128::from_le_bytes(information.FileId.Identifier);
        if information.VolumeSerialNumber == 0 || index == 0 { return Err("Unavailable native catalog file identity".into()); }
        Ok(Identity(information.VolumeSerialNumber, index))
    }
    pub fn leaf(path: &Path) -> Result<Vec<u8>> {
        Ok(path.file_name().ok_or("Missing catalog basename")?.encode_wide().flat_map(u16::to_le_bytes).collect())
    }
    pub struct Lease { file: File, overlapped: Box<OVERLAPPED> }
    // OVERLAPPED has zero hEvent and no asynchronous operation; access is immutable
    // until exclusive Drop. Its stable heap address is retained through unlock.
    unsafe impl Send for Lease {}
    unsafe impl Sync for Lease {}
    impl Lease {
        pub fn acquire(path: &Path) -> Result<Self> {
            let file = open(path, GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, OPEN_ALWAYS, 0)?;
            if info(&file)?.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY != 0 { return Err("Registry lock is not a regular file".into()); }
            let mut overlapped = Box::new(unsafe { std::mem::zeroed() });
            if unsafe { LockFileEx(file.as_raw_handle().cast(), LOCKFILE_EXCLUSIVE_LOCK | LOCKFILE_FAIL_IMMEDIATELY,
                0, 1, 0, &mut *overlapped) } == 0 {
                let error = std::io::Error::last_os_error();
                return Err(if error.raw_os_error() == Some(ERROR_LOCK_VIOLATION as i32) { BUSY.into() } else { native_error(error) });
            }
            Ok(Self { file, overlapped })
        }
    }
    impl Drop for Lease {
        fn drop(&mut self) {
            // Close still releases on an unexpected unlock failure; never reuse the handle.
            unsafe { UnlockFileEx(self.file.as_raw_handle().cast(), 0, 1, 0, &mut *self.overlapped); }
        }
    }
}

#[cfg(not(any(target_os = "linux", target_os = "macos", windows)))]
compile_error!("No native library admission adapter for this target");

#[cfg(test)]
mod tests {
    use super::*;
    #[cfg(windows)]
    #[test]
    fn native_file_id_info_layout() {
        use windows_sys::Win32::Storage::FileSystem::FILE_ID_INFO;
        assert_eq!(std::mem::size_of::<FILE_ID_INFO>(), 24);
        assert_eq!(std::mem::align_of::<FILE_ID_INFO>(), 8);
    }
    #[test]
    fn protocol_golden_vectors() {
        for (kind, platform, first, second, leaf, digest) in [
            ("directory", "posix", 1, 2, vec![], "8e99209d350b394ded05dbd1f9f281b9fd421f3bae6642f36a7659d6c5d8549f"),
            ("path", "posix", 1, 2, b"catalog.sqlite3".to_vec(), "bd3c832253fb07ad885e70666342fd13dd338c33c7831d7c582cd90ffa8bd720"),
            ("file", "posix", 2049, 42, vec![], "e47e1098063088c7e0f0ded0dcde98f82a32104718af475e9bfcf628bf9ecba7"),
            ("path", "windows", 123456789, u64::MAX as u128, "Catalog.sqlite3".encode_utf16().flat_map(u16::to_le_bytes).collect(), "04a1f2261f67e44a13a82aed50f8b5a03d88356f5bfcf490587475f21f244b9e"),
            ("file", "windows", u64::MAX, u128::MAX, vec![], "f17b74909787c9e81a1cdffd2c59b68085b6dd5b9ff43e6d91cf91a692318377"),
            ("directory", "windows", 123456789, 20011376718272490338853433276725592320u128, vec![], "dedc302e7e9278dafe33c908f1f1ba47ca6df6c7cbff6b2e4a8ae719e54a33b0"),
            ("path", "windows", 123456789, 20011376718272490338853433276725592320u128, "Catalog.sqlite3".encode_utf16().flat_map(u16::to_le_bytes).collect(), "da38d0e2cca6a7a9dc2d771350519e1ef0b212327720116b322a50d47161dcdf"),
        ] { assert_eq!(key_hash(&key(kind, platform, first, second, &leaf)), digest); }
        assert_eq!(u128::from_le_bytes(std::array::from_fn(|index| index as u8)),
                   20011376718272490338853433276725592320u128);
    }
    #[test]
    fn borrow_alias_refusal_release_and_replacement() {
        let directory = tempfile::tempdir().unwrap();
        let registry = directory.path().join("private/admission-v1");
        let path = directory.path().join("catalog");
        std::fs::write(&path, b"fixture").unwrap();
        let owner = Admission::at_registry(&path, registry.clone()).unwrap();
        let borrowed = Admission::at_registry(&path, registry.clone()).unwrap();
        let alias = directory.path().join("alias");
        std::fs::hard_link(&path, &alias).unwrap();
        assert!(Admission::at_registry(&alias, registry.clone()).is_err());
        drop(owner);
        assert!(Admission::at_registry(&alias, registry.clone()).is_err());
        drop(borrowed);
        let alias_owner = Admission::at_registry(&alias, registry.clone()).unwrap();
        drop(alias_owner);
        let owner = Admission::at_registry(&path, registry.clone()).unwrap();
        std::fs::rename(&path, directory.path().join("old")).unwrap();
        std::fs::write(&path, b"replacement").unwrap();
        assert!(owner.validate().is_err());
    }
}
