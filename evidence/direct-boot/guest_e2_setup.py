"""Root-only setup and teardown for the bounded G0 storage qualification."""
from __future__ import annotations
import select
import base64, hashlib, importlib.util, json, os, re, resource, selectors, signal, stat, subprocess, sys, time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("dm_g0_policy", HERE / "e2_policy.py")
if SPEC is None or SPEC.loader is None: raise RuntimeError("G0 policy loader")
g0 = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(g0)

CONFIG = Path("/var/lib/dm-g0-private/config.json")
MANIFEST = Path("/opt/dm-g0/seed-manifest.json")
DMI = Path("/sys/class/dmi/id/product_serial")
SERIAL = Path("/dev/ttyS0")
ACK_ALIAS = Path("/dev/virtio-ports/dm.g0.ack")
TOOLS = ("/usr/sbin/sfdisk", "/usr/sbin/mkfs.ext4", "/usr/bin/mount", "/usr/bin/umount", "/usr/bin/dpkg-query")
GUID = "0FC63DAF-8483-4772-8E79-3D69D8477DE4"

def stable_file(path, cap, *, mode=None, public=False):
    before = os.lstat(path)
    if not stat.S_ISREG(before.st_mode) or before.st_uid != 0 or before.st_gid != 0 or before.st_nlink != 1:
        raise RuntimeError("file metadata: " + str(path))
    if mode is not None and stat.S_IMODE(before.st_mode) != mode: raise RuntimeError("file mode: " + str(path))
    if public and before.st_mode & 0o022: raise RuntimeError("public file writable")
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        opened = os.fstat(fd); data = bytearray()
        while True:
            block = os.read(fd, min(65536, cap + 1 - len(data)))
            if not block: break
            data.extend(block)
            if len(data) > cap: raise RuntimeError("file cap")
        after_fd = os.fstat(fd)
    finally: os.close(fd)
    after = os.lstat(path)
    ident = lambda st: (st.st_dev, st.st_ino, st.st_mode, st.st_uid, st.st_gid, st.st_nlink, st.st_size)
    if ident(before) != ident(opened) or ident(opened) != ident(after_fd) or ident(opened) != ident(after):
        raise RuntimeError("file changed: " + str(path))
    return bytes(data), {"path": str(path), "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(), "mode": stat.S_IMODE(opened.st_mode)}

SEED_DIR_MODES={
    Path("/var/lib/dm-direct-boot"):0o555,
    Path("/var/lib/dm-g0-private"):0o700,
    Path("/opt/dm-g0"):0o555,
    Path("/opt/dm-g0/helpers"):0o555,
    Path("/opt/dm-g0/source"):0o555,
    Path("/opt/dm-g0/source/defiantmaple"):0o555,
}

def secure_dir(path, *, prepare=False, desired=None):
    if not path.is_absolute(): raise RuntimeError("seed directory absolute path")
    fd=os.open("/",os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        for component in path.parts[1:]:
            st=os.stat(component,dir_fd=fd,follow_symlinks=False)
            if not stat.S_ISDIR(st.st_mode) or st.st_uid!=0 or st.st_gid!=0 or st.st_mode&0o022:
                raise RuntimeError("seed directory boundary: "+str(path))
            child=os.open(component,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd)
            opened=os.fstat(child)
            if _identity(st)!=_identity(opened): os.close(child); raise RuntimeError("seed directory identity")
            os.close(fd); fd=child
        if desired is not None:
            if prepare: os.fchmod(fd,desired)
            if stat.S_IMODE(os.fstat(fd).st_mode)!=desired: raise RuntimeError("seed directory mode: "+str(path))
        opened=os.fstat(fd)
        return fd,[opened.st_dev,opened.st_ino,stat.S_IMODE(opened.st_mode)]
    except BaseException:
        os.close(fd); raise

def prepare_seed_tree():
    facts={}
    for path,mode in SEED_DIR_MODES.items():
        fd,fact=secure_dir(path,prepare=True,desired=mode); os.close(fd); facts[str(path)]=fact
    return facts

def stable_seed_file(path,cap,*,mode,public,expected_dirs=None):
    parent_fd,parent_fact=secure_dir(path.parent,desired=SEED_DIR_MODES.get(path.parent))
    try:
        before=os.stat(path.name,dir_fd=parent_fd,follow_symlinks=False)
        if not stat.S_ISREG(before.st_mode) or before.st_uid!=0 or before.st_gid!=0 or before.st_nlink!=1 or stat.S_IMODE(before.st_mode)!=mode:
            raise RuntimeError("seed file metadata: "+str(path))
        if public and before.st_mode&0o022: raise RuntimeError("public seed file writable")
        fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent_fd)
        try:
            opened=os.fstat(fd); data=bytearray()
            while True:
                block=os.read(fd,min(65536,cap+1-len(data)))
                if not block: break
                data.extend(block)
                if len(data)>cap: raise RuntimeError("seed file cap")
            after_fd=os.fstat(fd)
        finally: os.close(fd)
        after=os.stat(path.name,dir_fd=parent_fd,follow_symlinks=False)
        ident=lambda st:(st.st_dev,st.st_ino,st.st_mode,st.st_uid,st.st_gid,st.st_nlink,st.st_size)
        if ident(before)!=ident(opened) or ident(opened)!=ident(after_fd) or ident(opened)!=ident(after): raise RuntimeError("seed file changed")
        if expected_dirs is not None and expected_dirs.get(str(path.parent))!=parent_fact: raise RuntimeError("seed directory changed")
        return bytes(data),{"path":str(path),"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest(),"mode":stat.S_IMODE(opened.st_mode)}
    finally: os.close(parent_fd)

def dmi_binding():
    raw, fact = stable_file(DMI, 256, mode=0o400)
    if len(raw) != 65 or raw[-1:] != b"\n" or not re.fullmatch(rb"[0-9a-f]{64}", raw[:64]): raise RuntimeError("DMI binding bytes")
    return raw[:64].decode(), fact

def proc_start(pid):
    raw = Path(f"/proc/{pid}/stat").read_text(); end = raw.rfind(")")
    if end < 0: raise RuntimeError("child proc stat")
    fields = raw[end + 2:].split()
    if len(fields) < 20: raise RuntimeError("child proc fields")
    return int(fields[19])

def child_same(pid, start):
    try: return proc_start(pid) == start
    except (FileNotFoundError, ProcessLookupError): return False

def direct_children(pid):
    path=f"/proc/{pid}/task/{pid}/children"
    try: fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    except FileNotFoundError: return []
    try:
        raw=os.read(fd,4097)
        if len(raw)>4096 or os.read(fd,1): raise RuntimeError("child list cap")
    finally: os.close(fd)
    if not raw.strip(): return []
    text=raw.decode("ascii","strict")
    if not re.fullmatch(r"[0-9]+(?: [0-9]+)* ?",text): raise RuntimeError("child list syntax")
    values=[int(item) for item in text.split()]
    if len(values)>32 or any(item<=0 for item in values): raise RuntimeError("child list count")
    return values

def pidfd_signal(pidfd, sig):
    signal.pidfd_send_signal(pidfd,sig,None,0)

def capture_tool(argv, *, stdin=b"", timeout, output_cap=65536, capture):
    if (not argv or argv[0] not in (*TOOLS,g0.INIT_UDEVADM) or len(argv)>8 or any(not isinstance(item,str) or not 0<len(item.encode())<=512 for item in argv)
            or sum(len(item.encode()) for item in argv)>1024 or len(stdin) > 4096): raise RuntimeError("tool runner contract")
    proc = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        cwd="/", env={"PATH":"/usr/sbin:/usr/bin:/sbin:/bin", "LANG":"C.UTF-8", "LC_ALL":"C.UTF-8", "HOME":"/nonexistent"},
        close_fds=True, start_new_session=False, preexec_fn=lambda: (resource.setrlimit(resource.RLIMIT_CORE,(0,0)), resource.setrlimit(resource.RLIMIT_FSIZE,(g0.MIB,g0.MIB)), resource.setrlimit(resource.RLIMIT_NOFILE,(64,64))))
    start=pidfd=sel=None; out,err,sent=capture["stdout"],capture["stderr"],0; status=None
    try:
        start=proc_start(proc.pid); pidfd=os.pidfd_open(proc.pid,0)
        for stream in (proc.stdin,proc.stdout,proc.stderr): os.set_blocking(stream.fileno(),False)
        sel=selectors.DefaultSelector()
        sel.register(proc.stdout,selectors.EVENT_READ,"out"); sel.register(proc.stderr,selectors.EVENT_READ,"err")
        if stdin: sel.register(proc.stdin,selectors.EVENT_WRITE,"in")
        else: proc.stdin.close()
        deadline=time.monotonic()+timeout
        while sel.get_map() and time.monotonic()<deadline:
            if direct_children(proc.pid): raise RuntimeError("tool descendant observed")
            for key,mask in sel.select(max(0,min(.1,deadline-time.monotonic()))):
                if key.data=="in":
                    try: count=os.write(key.fileobj.fileno(),stdin[sent:])
                    except BlockingIOError: continue
                    if count<=0: raise RuntimeError("tool stdin write")
                    sent+=count
                    if sent==len(stdin): sel.unregister(key.fileobj); key.fileobj.close()
                else:
                    target=out if key.data=="out" else err
                    try: block=os.read(key.fileobj.fileno(),min(65536,output_cap+1-len(target)))
                    except BlockingIOError: continue
                    if not block:
                        capture["stdout_eof" if key.data=="out" else "stderr_eof"]=True
                        sel.unregister(key.fileobj); key.fileobj.close(); continue
                    target.extend(block)
                    if len(target)>output_cap: raise RuntimeError("tool output cap")
        if sel.get_map(): raise TimeoutError("tool deadline")
        if direct_children(proc.pid): raise RuntimeError("tool descendant observed")
        status=proc.wait(timeout=max(0,deadline-time.monotonic())); rc=proc.returncode; capture["returncode"]=rc;capture["child_reaped"]=True
    except BaseException as original:
        try:
            if pidfd is None:
                proc.kill()
            elif child_same(proc.pid,start): pidfd_signal(pidfd,signal.SIGTERM)
            try: status=proc.wait(timeout=1);capture["child_reaped"]=True
            except subprocess.TimeoutExpired:
                if pidfd is not None and child_same(proc.pid,start): pidfd_signal(pidfd,signal.SIGKILL)
                status=proc.wait(timeout=1);capture["child_reaped"]=True
        except BaseException as cleanup: original.add_note("tool child cleanup: "+type(cleanup).__name__+": "+str(cleanup)[:256])
        if capture["child_reaped"]: capture["returncode"]=proc.returncode
        raise
    finally:
        capture["child_cleanup_attempted"]=True
        if sel is not None: sel.close()
        if pidfd is not None: os.close(pidfd)
        for stream in (proc.stdin,proc.stdout,proc.stderr):
            if not stream.closed: stream.close()
    if status is None or rc!=0: raise RuntimeError("tool failed: "+argv[0]+":"+str(rc))
    return {"argv":argv,"stdout_sha256":hashlib.sha256(out).hexdigest(),"stdout_bytes":len(out),"stdout_text":bytes(out),
            "stderr_sha256":hashlib.sha256(err).hexdigest(),"stderr_bytes":len(err),"stderr_text":bytes(err),
            "stdin_bytes":len(stdin),"stdin_sha256":hashlib.sha256(stdin).hexdigest(),"returncode":rc}


def emit_tool_capture(context,argv,stdin,capture,error,phase):
    ordinal=context["tool_count"]
    if ordinal>=g0.TOOL_RUNS_MAX: raise RuntimeError("tool evidence invocation cap")
    context["tool_count"]+=1
    common={"schema":"dm-g0-tool-evidence-v1","nonce":context["nonce"],"binding":context["binding"],
            "seed_manifest_sha256":context["manifest_sha256"],"ordinal":ordinal}
    streams={}; chunks=[]
    for name in ("stdout","stderr"):
        observed=bytes(capture[name]); retained=observed[:65536]
        blocks=[retained[i:i+32768] for i in range(0,len(retained),32768)] or [b""]
        streams[name]={"bytes":len(retained),"sha256":g0.sha256(retained),"observed_at_least":len(observed),
                       "truncated":len(observed)>65536,"eof":capture[name+"_eof"],"chunks":len(blocks)}
        chunks.extend({**common,"kind":"chunk","stream":name,"index":index,"raw_base64":base64.b64encode(block).decode("ascii")} for index,block in enumerate(blocks))
    metadata={**common,"kind":"meta","argv":argv,"stdin_base64":base64.b64encode(stdin).decode("ascii"),"stdin_bytes":len(stdin),
              "stdin_sha256":g0.sha256(stdin),"streams":streams,"returncode":capture["returncode"],"child_reaped":capture["child_reaped"],"phase":phase,"error":error}
    records=[metadata]+chunks
    for index,record in enumerate(records):
        limit=4096 if index==0 else g0.TOOL_CHUNK_WIRE_MAX
        wire=g0.build_frame(g0.TOOL_PREFIX,record,limit)
        g0.check_initialization_wire(ordinal,metadata,record,wire)
        serial_frame(g0.TOOL_PREFIX,record)


def run_tool(argv, *, stdin=b"", timeout, output_cap=65536, diagnostics=None):
    capture={"stdout":bytearray(),"stderr":bytearray(),"stdout_eof":False,"stderr_eof":False,"returncode":None,"child_reaped":False}
    emitted=False
    def emit_failure(original):
        nonlocal emitted
        if diagnostics is not None and not emitted:
            emitted=True
            emit_tool_capture(diagnostics,argv,stdin,capture,type(original).__name__+": "+str(original)[:512],"failure-after-child-cleanup-attempt" if capture.get("child_cleanup_attempted") else "failure-before-launch")
    try:
        value=capture_tool(argv,stdin=stdin,timeout=timeout,output_cap=output_cap,capture=capture)
    except BaseException as original:
        try: emit_failure(original)
        except BaseException as diagnostic: original.add_note("tool evidence: "+type(diagnostic).__name__+": "+str(diagnostic)[:256])
        raise
    if diagnostics is not None:
        emit_tool_capture(diagnostics,argv,stdin,capture,None,"complete")
    value["stdout_text"]=value["stdout_text"].decode("utf-8","strict")
    value["stderr_text"]=value["stderr_text"].decode("utf-8","strict")
    return value


def verify_manifest(expected_dirs=None):
    raw, _ = stable_seed_file(MANIFEST,g0.MIB,mode=0o444,public=True,expected_dirs=expected_dirs); value = g0.validate_manifest(g0.loads_strict(raw))
    for entry in value["entries"]:
        data, fact = stable_seed_file(Path(entry["path"]),g0.MIB,mode=entry["mode"],public=entry["public"],expected_dirs=expected_dirs)
        if len(data) != entry["bytes"] or fact["sha256"] != entry["sha256"]: raise RuntimeError("manifest entry digest")
    return value, hashlib.sha256(raw).hexdigest()

def tool_facts(deadlines,paths=TOOLS,diagnostics=None):
    facts=[]
    for raw in paths:
        path=Path(raw); requested=os.lstat(path); resolved=path.resolve(strict=True); data,fact=stable_file(resolved,64*g0.MIB,public=True)
        if stat.S_ISLNK(requested.st_mode):
            target=os.readlink(path)
            if not 0<len(target)<=512: raise RuntimeError("tool link target")
        elif stat.S_ISREG(requested.st_mode): target=None
        else: raise RuntimeError("tool requested type")
        owner=run_tool(["/usr/bin/dpkg-query","-S",str(resolved)],timeout=deadlines["dpkg_query"],diagnostics=diagnostics)
        if owner["stderr_text"] or owner["stdout_text"].count("\n")!=1 or ": " not in owner["stdout_text"]: raise RuntimeError("tool owner output")
        package,owned_path=owner["stdout_text"].rstrip("\n").split(": ",1)
        if owned_path!=str(resolved) or not re.fullmatch(r"[a-z0-9][a-z0-9+.-]*(?::[a-z0-9][a-z0-9-]*)?",package): raise RuntimeError("tool owner identity")
        version=run_tool(["/usr/bin/dpkg-query","-W","-f=${binary:Package}\t${Version}\t${Architecture}\n",package],timeout=deadlines["dpkg_query"],diagnostics=diagnostics)
        fields=version["stdout_text"].rstrip("\n").split("\t")
        if version["stderr_text"] or version["stdout_text"].count("\n")!=1 or len(fields)!=3 or fields[0]!=package or not all(0<len(item)<=512 for item in fields): raise RuntimeError("tool package identity")
        requested_after=os.lstat(path)
        if _identity(requested)!=_identity(requested_after) or (target is not None and os.readlink(path)!=target): raise RuntimeError("tool requested path changed")
        fact.update({"requested":raw,"requested_type":"symlink" if target is not None else "regular","requested_target":target,
                     "owner":{"package":package,"version":fields[1],"architecture":fields[2]},"owner_query":owner,"version_query":version}); facts.append(fact)
    return facts

def udev_rule_fact(deadlines,diagnostics=None):
    fact=tool_facts(deadlines,(g0.UDEV_RULE_PATH,),diagnostics=diagnostics)[0]
    raw,_=stable_file(Path(g0.UDEV_RULE_PATH),16384,public=True)
    fact["raw_base64"]=base64.b64encode(raw).decode("ascii")
    return g0.validate_udev_rule(fact)


def read_attr(path, cap=256):
    raw,_=stable_file(path,cap,public=True)
    if not raw.endswith(b"\n") or b"\0" in raw: raise RuntimeError("sysfs attribute")
    return raw[:-1].decode("ascii")

def _identity(st):
    return (st.st_dev, st.st_ino, st.st_mode, st.st_uid, st.st_gid, st.st_nlink)

def held_dir(path, cap):
    before=os.lstat(path)
    if not stat.S_ISDIR(before.st_mode) or before.st_uid!=0 or before.st_gid!=0 or before.st_mode&0o022:
        raise RuntimeError("directory boundary")
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        opened=os.fstat(fd); names=os.listdir(fd)
        if len(names)>cap or any(not isinstance(name,str) or len(name)>128 or name in (".","..") for name in names): raise RuntimeError("directory entry cap")
        if _identity(before)!=_identity(opened): raise RuntimeError("directory identity")
        return fd,before,sorted(names)
    except BaseException: os.close(fd); raise

def close_dir(path,fd,before):
    try: after_fd=os.fstat(fd); after=os.lstat(path)
    finally: os.close(fd)
    if _identity(before)!=_identity(after_fd) or _identity(before)!=_identity(after): raise RuntimeError("directory changed")

def sysfs_entry(root,root_fd,name):
    before=os.stat(name,dir_fd=root_fd,follow_symlinks=False)
    if not stat.S_ISLNK(before.st_mode) or before.st_uid!=0: raise RuntimeError("sysfs class entry type")
    target=os.readlink(name,dir_fd=root_fd)
    if not 0<len(target)<=512 or target.startswith("/"): raise RuntimeError("sysfs link target")
    canonical=(root/name).resolve(strict=True)
    if not str(canonical).startswith("/sys/devices/"): raise RuntimeError("sysfs link escape")
    fd=os.open(canonical,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try: recheck_sysfs_entry(root_fd,name,before,target,fd)
    except BaseException: os.close(fd); raise
    return fd,before,target,canonical

def recheck_sysfs_entry(root_fd,name,before,target,fd):
    after=os.stat(name,dir_fd=root_fd,follow_symlinks=False)
    if (_identity(before)!=_identity(after) or os.readlink(name,dir_fd=root_fd)!=target or not stat.S_ISDIR(os.fstat(fd).st_mode)
            or _identity(os.fstat(fd))!=_identity(os.stat(name,dir_fd=root_fd,follow_symlinks=True))):
        raise RuntimeError("sysfs entry changed")

def sysfs_identity(fd):
    opened=os.fstat(fd)
    if not stat.S_ISDIR(opened.st_mode) or opened.st_uid!=0 or opened.st_gid!=0 or opened.st_mode&0o022: raise RuntimeError("sysfs target metadata")
    return [opened.st_dev,opened.st_ino,opened.st_uid,opened.st_gid,stat.S_IMODE(opened.st_mode)]


def read_attr_fd(dirfd,name,cap=256):
    before=os.stat(name,dir_fd=dirfd,follow_symlinks=False)
    if not stat.S_ISREG(before.st_mode) or before.st_uid!=0 or before.st_gid!=0: raise RuntimeError("sysfs attr metadata")
    fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=dirfd)
    try:
        if _identity(os.fstat(fd))!=_identity(before): raise RuntimeError("sysfs attr open identity")
        data=bytearray()
        while True:
            block=os.read(fd,cap+1-len(data))
            if not block: break
            data.extend(block)
            if len(data)>cap: raise RuntimeError("sysfs attr cap")
        after_fd=os.fstat(fd)
    finally: os.close(fd)
    after=os.stat(name,dir_fd=dirfd,follow_symlinks=False)
    if _identity(before)!=_identity(after_fd) or _identity(before)!=_identity(after) or not data.endswith(b"\n") or b"\0" in data:
        raise RuntimeError("sysfs attr changed/format")
    return data[:-1].decode("ascii")

def nvme_preflight(serial, *, partitions_present=False):
    nvme_root,block_root=Path("/sys/class/nvme"),Path("/sys/class/block")
    nfd,nbefore,controllers=held_dir(nvme_root,64)
    try: bfd,bbefore,blocks=held_dir(block_root,512)
    except BaseException: os.close(nfd); raise
    try:
        nvme_controllers=[name for name in controllers if re.fullmatch(r"nvme(0|[1-9][0-9]{0,9})",name)]
        nvme_blocks=[name for name in blocks if re.fullmatch(r"nvme[0-9]+n[0-9]+(?:p[0-9]+)?",name)]
        if len(nvme_controllers)!=1: raise RuntimeError("NVMe controller count")
        expected_count=3 if partitions_present else 1
        namespaces=[item for item in nvme_blocks if "p" not in item]
        if len(nvme_blocks)!=expected_count or len(namespaces)!=1: raise RuntimeError("NVMe namespace/partition count")
        ctrl,name=nvme_controllers[0],namespaces[0]
        expected_names={name} | ({name+"p1",name+"p2"} if partitions_present else set())
        if set(nvme_blocks)!=expected_names: raise RuntimeError("NVMe partition names")
        if not re.fullmatch(re.escape(ctrl)+r"n(0|[1-9][0-9]{0,9})",name): raise RuntimeError("NVMe namespace/controller name")
        cfd,cbefore,ctarget,ccanonical=sysfs_entry(nvme_root,nfd,ctrl)
        try: sfd,sbefore,starget,scanonical=sysfs_entry(block_root,bfd,name)
        except BaseException: os.close(cfd); raise
        try:
            if read_attr_fd(cfd,"serial")!=serial or read_attr_fd(cfd,"transport")!="pcie" or "/pci" not in str(ccanonical): raise RuntimeError("NVMe serial/transport/PCI")
            if ccanonical not in scanonical.parents: raise RuntimeError("NVMe namespace ancestry")
            if int(read_attr_fd(sfd,"size"))!=g0.SECTORS: raise RuntimeError("NVMe sector count")
            qfd=os.open("queue",os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=sfd)
            try:
                if int(read_attr_fd(qfd,"logical_block_size"))!=g0.SECTOR_BYTES: raise RuntimeError("NVMe logical sector")
            finally: os.close(qfd)
            major,minor=map(int,read_attr_fd(sfd,"dev").split(":"))
            devroot,devbefore,_=held_dir(Path("/dev"),512)
            try:
                before=os.stat(name,dir_fd=devroot,follow_symlinks=False); dfd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=devroot)
                try:
                    opened=os.fstat(dfd)
                    if (_identity(before)!=_identity(opened) or not stat.S_ISBLK(opened.st_mode) or opened.st_uid!=0 or opened.st_mode&0o002
                            or (os.major(opened.st_rdev),os.minor(opened.st_rdev))!=(major,minor)): raise RuntimeError("NVMe device identity")
                finally: os.close(dfd)
                if _identity(os.stat(name,dir_fd=devroot,follow_symlinks=False))!=_identity(before): raise RuntimeError("NVMe device changed")
                partition_facts=[]
                if partitions_present:
                    for number,(start,sectors) in enumerate(((2048,122880),(124928,131072)),1):
                        pname=name+"p"+str(number); pfd,pbefore,ptarget,pcanonical=sysfs_entry(block_root,bfd,pname)
                        try:
                            if scanonical not in pcanonical.parents or int(read_attr_fd(pfd,"start"))!=start or int(read_attr_fd(pfd,"size"))!=sectors:
                                raise RuntimeError("NVMe partition geometry")
                            pmajor,pminor=map(int,read_attr_fd(pfd,"dev").split(":")); pnode=os.stat(pname,dir_fd=devroot,follow_symlinks=False)
                            pdevice=os.open(pname,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=devroot)
                            try:
                                popened=os.fstat(pdevice)
                                if (_identity(pnode)!=_identity(popened) or not stat.S_ISBLK(popened.st_mode) or popened.st_uid!=0 or popened.st_mode&0o002
                                        or (os.major(popened.st_rdev),os.minor(popened.st_rdev))!=(pmajor,pminor)):
                                    raise RuntimeError("NVMe partition node")
                                recheck_sysfs_entry(bfd,pname,pbefore,ptarget,pfd)
                                if _identity(os.stat(pname,dir_fd=devroot,follow_symlinks=False))!=_identity(pnode): raise RuntimeError("NVMe partition node changed")
                                partition_facts.append({"number":number,"name":pname,"path":"/dev/"+pname,"start":start,"sectors":sectors,
                                                        "dev":[pmajor,pminor],"sysfs_path":str(pcanonical),
                                                        "node_identity":[popened.st_dev,popened.st_ino,popened.st_uid,popened.st_gid,stat.S_IMODE(popened.st_mode),popened.st_nlink,pmajor,pminor],"sysfs_identity":sysfs_identity(pfd)})
                            finally: os.close(pdevice)
                        finally: os.close(pfd)
            finally: close_dir(Path("/dev"),devroot,devbefore)
            recheck_sysfs_entry(nfd,ctrl,cbefore,ctarget,cfd); recheck_sysfs_entry(bfd,name,sbefore,starget,sfd)
            result={"controller":ctrl,"namespace":name,"device":"/dev/"+name,"controller_path":str(ccanonical),"namespace_path":str(scanonical),"serial":serial,"transport":"pcie","bytes":g0.NVME_BYTES,"sector_bytes":g0.SECTOR_BYTES,"sectors":g0.SECTORS,"dev":[major,minor],
                    "node_identity":[opened.st_dev,opened.st_ino,opened.st_uid,opened.st_gid,stat.S_IMODE(opened.st_mode),opened.st_nlink,major,minor],
                    "controller_identity":sysfs_identity(cfd),"namespace_identity":sysfs_identity(sfd)}
            if partitions_present: result["partitions"]=partition_facts
            return result
        finally: os.close(cfd); os.close(sfd)
    finally:
        try: close_dir(nvme_root,nfd,nbefore)
        finally: close_dir(block_root,bfd,bbefore)

def mountinfo():
    raw,_=stable_file(Path("/proc/self/mountinfo"),g0.MOUNTINFO_MAX,public=True)
    records=g0.parse_mountinfo(raw)
    return {"raw":raw,"bytes":len(raw),"sha256":hashlib.sha256(raw).hexdigest(),"records":records}

def emit_mountinfo(phase,snapshot,config,binding,manifest_sha):
    receipt=g0.mount_receipt(phase,snapshot["raw"],nonce=config["nonce"],binding=binding,manifest_sha256=manifest_sha); serial_frame(g0.MOUNT_PREFIX,receipt)
    return {"phase":phase,"bytes":receipt["bytes"],"sha256":receipt["sha256"]}

def exact_mount(snapshot,mountpoint):
    matches=[item for item in snapshot["records"] if item["mountpoint"]==mountpoint]
    if len(matches)>1: raise RuntimeError("duplicate mountpoint")
    return matches[0] if matches else None

def reject_selected_nvme_mount(snapshot,nvme):
    namespace_dev=str(nvme["dev"][0])+":"+str(nvme["dev"][1])
    if any(item["dev"]==namespace_dev or item["source"]==nvme["device"]
            or item["source"].startswith(nvme["device"]+"p") for item in snapshot["records"]):
        raise RuntimeError("selected NVMe already mounted")

def mount_namespace():
    path=Path("/proc/self/ns/mnt"); before=os.lstat(path)
    if not stat.S_ISLNK(before.st_mode) or before.st_uid!=0: raise RuntimeError("mount namespace locator")
    target=os.readlink(path)
    if not re.fullmatch(r"mnt:\[[1-9][0-9]{0,19}\]",target): raise RuntimeError("mount namespace target")
    fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC); opened=os.fstat(fd); after=os.lstat(path)
    try:
        if _identity(before)!=_identity(after) or os.readlink(path)!=target or not stat.S_ISREG(opened.st_mode):
            raise RuntimeError("mount namespace changed")
        return {"path":str(path),"target":target,"dev":opened.st_dev,"ino":opened.st_ino}
    finally: os.close(fd)

ROOT_FD_PHASES=("pre-qualifier","post-qualifier-pre-p2-unmount","pre-p1-unmount")

def validate_root_fd_facts(facts, forbidden_mount_ids, phase):
    if phase not in ROOT_FD_PHASES: raise RuntimeError("root fd inventory phase")
    observed=set()
    for item in facts:
        if (not isinstance(item,dict) or set(item)!={"fd","target","type","mnt_id"}
                or not isinstance(item["fd"],int) or isinstance(item["fd"],bool) or not 0<=item["fd"]<=4096
                or item["fd"] in observed or not isinstance(item["target"],str) or len(item["target"])>512
                or not isinstance(item["type"],int) or isinstance(item["type"],bool) or item["type"]<0
                or not isinstance(item["mnt_id"],int) or isinstance(item["mnt_id"],bool) or item["mnt_id"]<0):
            raise RuntimeError("root fd inventory fact")
        observed.add(item["fd"])
        if item["mnt_id"] in forbidden_mount_ids: raise RuntimeError("mount-backed root descriptor remains")
    return {"schema":"dm-g0-root-fd-inventory-v1","phase":phase,"forbidden_mount_ids":sorted(forbidden_mount_ids),"clean":True,
            "entries":sorted(facts,key=lambda item:item["fd"])}

def live_fd_names(names,excluded):
    result=set()
    for name in names:
        if not name.isdecimal(): raise RuntimeError("root fd name")
        number=int(name)
        if number in excluded: continue
        try: os.fstat(number)
        except OSError as exc:
            if exc.errno==9: continue  # os.listdir's own already-closed descriptor
            raise
        result.add(name)
    return result

def root_fd_inventory(forbidden_mount_ids,phase):
    root=Path("/proc/self/fd"); fd,before,names=held_dir(root,128); facts=[]
    try:
        info_fd,info_before,info_names=held_dir(Path("/proc/self/fdinfo"),128)
        try:
            live_names=live_fd_names(names,{fd,info_fd}); live_info=live_fd_names(info_names,{fd,info_fd})
            if live_names!=live_info: raise RuntimeError("root fd inventory mismatch")
            for name in sorted(live_names,key=int):
                if not name.isdecimal(): raise RuntimeError("root fd name")
                number=int(name)
                if number in {fd,info_fd}: continue
                try:
                    target=os.readlink(name,dir_fd=fd); opened=os.fstat(number)
                except (FileNotFoundError,OSError):
                    if number==fd: continue
                    raise RuntimeError("root fd inventory race")
                if len(target)>512: raise RuntimeError("root fd target cap")
                raw_fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=info_fd)
                try:
                    raw=os.read(raw_fd,4097)
                    if len(raw)>4096 or os.read(raw_fd,1): raise RuntimeError("root fdinfo cap")
                finally: os.close(raw_fd)
                matches=re.findall(rb"(?m)^mnt_id:\s*([0-9]+)$",raw)
                if len(matches)!=1: raise RuntimeError("root fdinfo mnt_id")
                mount_id=int(matches[0])
                facts.append({"fd":number,"target":target,"type":stat.S_IFMT(opened.st_mode),"mnt_id":mount_id})
        finally: close_dir(Path("/proc/self/fdinfo"),info_fd,info_before)
    finally: close_dir(root,fd,before)
    return validate_root_fd_facts(facts,forbidden_mount_ids,phase)

def validate_mount_entry(snapshot,mountpoint,part):
    item=exact_mount(snapshot,mountpoint)
    if item is None: raise RuntimeError("mount entry absent")
    expected_dev=str(part["dev"][0])+":"+str(part["dev"][1])
    optional=item["optional"]
    if optional!=[] and (not isinstance(optional,list) or len(optional)!=1 or not re.fullmatch(r"shared:[1-9][0-9]{0,9}",optional[0])):
        raise RuntimeError("mount propagation")
    if (item["dev"]!=expected_dev or item["root"]!="/" or item["filesystem"]!="ext4"
            or item["source"]!=part["path"]):
        raise RuntimeError("mount entry identity")
    options=set(item["mount_options"]); super_options=set(item["super_options"])
    if not {"rw","nodev","nosuid"}.issubset(options) or not options.issubset({"rw","nodev","nosuid","relatime"}):
        raise RuntimeError("mount options")
    if "rw" not in super_options or any(not re.fullmatch(r"(?:rw|errors=remount-ro|stripe=[1-9][0-9]{0,9})",entry) for entry in super_options):
        raise RuntimeError("mount super options")
    return item

def mountpoint_identity(mountpoint):
    before=os.lstat(mountpoint)
    if not stat.S_ISDIR(before.st_mode) or before.st_uid!=0 or before.st_gid!=0 or before.st_mode&0o022:
        raise RuntimeError("mounted root metadata")
    fd=os.open(mountpoint,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try: opened=os.fstat(fd)
    finally: os.close(fd)
    after=os.lstat(mountpoint)
    if _identity(before)!=_identity(opened) or _identity(opened)!=_identity(after): raise RuntimeError("mounted root changed")
    return [opened.st_dev,opened.st_ino,opened.st_uid,opened.st_gid,stat.S_IMODE(opened.st_mode),opened.st_nlink]

def check_pre_unmount_mount(snapshot,mountpoint,part,saved,probe_name):
    current=validate_mount_entry(snapshot,mountpoint,part)
    if current!=saved: raise RuntimeError("mount entry changed")
    try: os.lstat(Path(mountpoint)/"fixture"/probe_name)
    except FileNotFoundError: pass
    else: raise RuntimeError("probe remains")
    return current

def require_mounted_root_identity(observed,expected):
    if observed!=expected: raise RuntimeError("mounted root identity changed")

def recheck_mounted_root(mountpoint,expected):
    require_mounted_root_identity(mountpoint_identity(mountpoint),expected)

def wait_partitions(namespace, deadline):
    out=[]
    for number,(start,size) in enumerate(((2048,122880),(124928,131072)),1):
        name=f"{namespace}p{number}"; path=Path("/dev")/name; sysfs=Path("/sys/class/block")/name; end=time.monotonic()+deadline
        while time.monotonic()<end:
            try:
                if int(read_attr(sysfs/"start"))==start and int(read_attr(sysfs/"size"))==size:
                    major,minor=map(int,read_attr(sysfs/"dev").split(":")); st=os.lstat(path)
                    if stat.S_ISBLK(st.st_mode) and (os.major(st.st_rdev),os.minor(st.st_rdev))==(major,minor):
                        out.append({"number":number,"name":name,"path":str(path),"start":start,"sectors":size,"dev":[major,minor]}); break
            except FileNotFoundError: pass
            time.sleep(.05)
        else: raise RuntimeError("partition appearance deadline")
    return out

def validate_partition_table(raw,device):
    value=g0.loads_strict(raw)
    if not isinstance(value,dict) or set(value)!={"partitiontable"}: raise RuntimeError("sfdisk JSON envelope")
    table=value["partitiontable"]; allowed={"label","id","device","unit","firstlba","lastlba","sectorsize","partitions"}
    if not isinstance(table,dict) or not set(table).issubset(allowed) or not {"label","device","unit","sectorsize","partitions"}.issubset(table): raise RuntimeError("sfdisk table fields")
    if table["label"]!="gpt" or table["device"]!=device or table["unit"]!="sectors" or table["sectorsize"]!=g0.SECTOR_BYTES: raise RuntimeError("sfdisk table identity")
    parts=table["partitions"]
    if not isinstance(parts,list) or len(parts)!=2: raise RuntimeError("sfdisk partition count")
    for index,(part,start,size) in enumerate(zip(parts,(2048,124928),(122880,131072)),1):
        allowed_part={"node","start","size","type","uuid","name","attrs"}
        if not isinstance(part,dict) or not set(part).issubset(allowed_part) or not {"node","start","size","type"}.issubset(part): raise RuntimeError("sfdisk partition fields")
        if part["node"]!=device+"p"+str(index) or part["start"]!=start or part["size"]!=size or str(part["type"]).upper()!=GUID: raise RuntimeError("sfdisk partition geometry")
        for key in set(part)-{"node","start","size","type"}:
            if not isinstance(part[key],str) or len(part[key])>128: raise RuntimeError("sfdisk partition optional field")
    return table

def stop_and_reap_qualifier(pid,pidfd,start,status):
    """Stop only the identity-bound ordinary child and return its sole wait status."""
    if status is not None: return status
    if child_same(pid,start): pidfd_signal(pidfd,signal.SIGTERM)
    stop=time.monotonic()+1
    while status is None and time.monotonic()<stop:
        waited,observed=os.waitpid(pid,os.WNOHANG)
        if waited==pid: status=observed; break
        time.sleep(.01)
    if status is None and child_same(pid,start): pidfd_signal(pidfd,signal.SIGKILL)
    if status is None:
        waited,status=os.waitpid(pid,0)
        if waited!=pid: raise RuntimeError("qualifier reap identity")
    return status

def emit_qualifier_capture(config,manifest_sha,binding,data,eof,status,primary):
    error=None if primary is None else (type(primary).__name__+": "+str(primary)).encode("utf-8","replace")[:512].decode("utf-8","ignore")
    records=g0.qualifier_capture_records(bytes(data),nonce=config["nonce"],binding=binding,manifest_sha256=manifest_sha,eof=eof,status=status,error=error)
    for index,record in enumerate(records):
        limit=g0.QUAL_RAW_META_MAX if index==0 else g0.TOOL_CHUNK_WIRE_MAX
        g0.build_frame(g0.QUAL_RAW_PREFIX,record,limit)
        serial_frame(g0.QUAL_RAW_PREFIX,record)


def child_e2(config,manifest_sha,binding,parts,mount_ids):
    deadline=time.monotonic()+config['deadlines']['ordinary_child']
    read_fd=write_fd=pidfd=pid=start=None; data=bytearray();status=None;eof=False;primary=None;descendants={}
    try:
        read_fd,write_fd=os.pipe2(os.O_CLOEXEC)
        pid=os.fork()
        if pid==0:
            try:
                os.close(read_fd)
                for fd in range(3,128):
                    if fd!=write_fd:
                        try: os.close(fd)
                        except OSError: pass
                os.setgroups([]); os.setresgid(g0.ORDINARY_ID,g0.ORDINARY_ID,g0.ORDINARY_ID); os.setresuid(g0.ORDINARY_ID,g0.ORDINARY_ID,g0.ORDINARY_ID); os.umask(0o077)
                null=os.open("/dev/null",os.O_RDWR)
                for target in (0,1,2): os.dup2(null,target)
                if null>2: os.close(null)
                os.set_inheritable(write_fd,True)
                argv=["/usr/bin/python3","-I","-B","-S","/opt/dm-g0/helpers/guest_e2_case.py",str(write_fd),config["nonce"],binding,manifest_sha,config["mounts"][0]+"/fixture",config["mounts"][1]+"/fixture",str(mount_ids[1]),str(deadline)]
                os.execve(argv[0],argv,{"PATH":"/usr/bin:/bin","LANG":"C.UTF-8","HOME":"/nonexistent"})
            except BaseException: os._exit(126)
        os.close(write_fd);write_fd=None
        os.set_blocking(read_fd,False);start=proc_start(pid);pidfd=os.pidfd_open(pid,0)
        while time.monotonic()<deadline:
            children=direct_children(pid)
            if len(children)>2:raise RuntimeError("E2 owned descendant count")
            for descendant in children:
                try:
                    if descendant not in descendants:
                        observed_start=proc_start(descendant);descendants[descendant]=(observed_start,os.pidfd_open(descendant,0))
                    status_fd=os.open('/proc/'+str(descendant)+'/status',os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
                    try:status_raw=os.read(status_fd,65537)
                    finally:os.close(status_fd)
                except (FileNotFoundError,ProcessLookupError):continue
                if len(status_raw)>65536 or re.findall(rb'(?m)^Uid:\s*([0-9]+)\s+([0-9]+)\s+([0-9]+)\s+([0-9]+)$',status_raw)!=[(b'12345',)*4]:raise RuntimeError("E2 descendant ordinary identity")
            if not eof:
                try: block=os.read(read_fd,g0.QUAL_RAW_MAX-len(data)+1)
                except BlockingIOError: block=None
                if block==b"": eof=True
                elif block:
                    data.extend(block)
                    if len(data)>g0.CASE_MAX: raise RuntimeError("E2 case capture over64KiB; exact prefix retained")
            if status is None:
                waited,observed=os.waitpid(pid,os.WNOHANG)
                if waited==pid: status=observed
            if status is not None and eof: break
            select.select([read_fd,pidfd],[],[],min(.01,max(0,deadline-time.monotonic())))
        else: raise TimeoutError("qualifier deadline")
        if status is None or not eof: raise RuntimeError("qualifier completion state")
        if not os.WIFEXITED(status) or os.WEXITSTATUS(status)!=0: raise RuntimeError("qualifier exit")
    except BaseException as original:
        primary=original
        if pid is not None and pid>0 and status is None:
            try:
                if pidfd is not None: status=stop_and_reap_qualifier(pid,pidfd,start,status)
                else:
                    try: os.kill(pid,signal.SIGKILL)
                    except ProcessLookupError: pass
                    waited,status=os.waitpid(pid,0)
                    if waited!=pid: status=None;raise RuntimeError("qualifier startup reap identity")
            except BaseException as cleanup: original.add_note("qualifier child cleanup: "+type(cleanup).__name__+": "+str(cleanup)[:256])
    finally:
        for owned in (read_fd,write_fd,pidfd):
            if owned is not None:
                try:os.close(owned)
                except BaseException as exc:
                    if primary is None:primary=exc
                    else:primary.add_note("E2 capture FD close: "+type(exc).__name__)
        for descendant,(observed_start,held) in descendants.items():
            try:
                if child_same(descendant,observed_start):
                    if primary is not None:
                        pidfd_signal(held,signal.SIGKILL)
                        if not select.select([held],[],[],max(0,min(1,deadline-time.monotonic())))[0]:raise RuntimeError("E2 descendant exit remains uncertain after forced stop")
                    raise RuntimeError("E2 descendant remains after ordinary exit; forced stop is not normal cleanup")
            except BaseException as exc:
                if primary is None:primary=exc
                else:primary.add_note("E2 descendant: "+type(exc).__name__)
            finally:os.close(held)
    try:
        serial_case_capture(bytes(data[:g0.CASE_MAX]))
        records=g0.parse_case(bytes(data),nonce=config['nonce'],binding=binding,manifest_sha256=manifest_sha)
    except BaseException as diagnostic:
        if primary is None:primary=diagnostic
        else:primary.add_note("E2 prefix capture: "+type(diagnostic).__name__)
    if primary is not None:raise primary
    if len(records)!=4:raise RuntimeError("E2 ordinary result incomplete")
    return records,bytes(data)


def ack_port():
    sysroot=Path("/sys/class/virtio-ports"); sysfd,sys_before,names=held_dir(sysroot,64); matches=[]; devfd=aliasfd=fd=None
    try:
        for name in names:
            match=re.fullmatch(r"vport(0|[1-9][0-9]{0,9})p(0|[1-9][0-9]{0,9})",name)
            if not match or any(int(item)>4294967295 for item in match.groups()): continue
            entryfd,entry_before,entry_target,canonical=sysfs_entry(sysroot,sysfd,name)
            try:
                if read_attr_fd(entryfd,"name") == "dm.g0.ack": matches.append((name,entryfd,entry_before,entry_target,str(canonical)))
                else: recheck_sysfs_entry(sysfd,name,entry_before,entry_target,entryfd); os.close(entryfd)
            except BaseException:
                if not any(item[1]==entryfd for item in matches): os.close(entryfd)
                raise
        if len(matches)!=1: raise RuntimeError("ACK sysfs name count")
        name,entryfd,entry_before,entry_target,canonical=matches[0]
        dev_text=read_attr_fd(entryfd,"dev"); major,minor=map(int,dev_text.split(":"))
        devfd,dev_before,_=held_dir(Path("/dev"),512); aliasfd,alias_parent_before,_=held_dir(Path("/dev/virtio-ports"),64)
        alias_before=os.stat("dm.g0.ack",dir_fd=aliasfd,follow_symlinks=False)
        if not stat.S_ISLNK(alias_before.st_mode) or alias_before.st_uid!=0 or alias_before.st_gid!=0 or alias_before.st_nlink!=1: raise RuntimeError("ACK alias metadata")
        target=os.readlink("dm.g0.ack",dir_fd=aliasfd)
        if target!="../"+name: raise RuntimeError("ACK locator target")
        node_before=os.stat(name,dir_fd=devfd,follow_symlinks=False)
        fd=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC|os.O_NONBLOCK,dir_fd=devfd); opened=os.fstat(fd)
        if (_identity(node_before)!=_identity(opened) or not stat.S_ISCHR(opened.st_mode) or opened.st_uid!=0 or opened.st_gid!=0
                or opened.st_nlink!=1 or opened.st_mode&0o022 or (os.major(opened.st_rdev),os.minor(opened.st_rdev))!=(major,minor)):
            raise RuntimeError("ACK char identity")
        fact={"name":name,"dev":[major,minor],"inode":[opened.st_dev,opened.st_ino],"alias_target":target,"sysfs_canonical":canonical}
        state={"sysroot":sysroot,"sysfd":sysfd,"sys_before":sys_before,"entryfd":entryfd,"entry_before":entry_before,"entry_target":entry_target,
               "devfd":devfd,"dev_before":dev_before,"aliasfd":aliasfd,"alias_parent_before":alias_parent_before,"alias_before":alias_before,
               "node_before":node_before,"name":name,"target":target,"dev_text":dev_text}
        return fd,fact,state
    except BaseException:
        for owned in [fd,aliasfd,devfd]+[item[1] for item in matches]+[sysfd]:
            if owned is not None:
                try: os.close(owned)
                except OSError: pass
        raise

def ack_check(fd,state):
    if os.readlink("dm.g0.ack",dir_fd=state["aliasfd"])!=state["target"] or _identity(os.stat("dm.g0.ack",dir_fd=state["aliasfd"],follow_symlinks=False))!=_identity(state["alias_before"]):
        raise RuntimeError("ACK alias changed")
    if _identity(os.stat(state["name"],dir_fd=state["devfd"],follow_symlinks=False))!=_identity(state["node_before"]) or _identity(os.fstat(fd))!=_identity(state["node_before"]):
        raise RuntimeError("ACK node changed")
    if read_attr_fd(state["entryfd"],"name")!="dm.g0.ack" or read_attr_fd(state["entryfd"],"dev")!=state["dev_text"]:
        raise RuntimeError("ACK sysfs changed")
    recheck_sysfs_entry(state["sysfd"],state["name"],state["entry_before"],state["entry_target"],state["entryfd"])

def ack_close(state):
    errors=[]
    for close in (lambda:os.close(state["entryfd"]),lambda:close_dir(state["sysroot"],state["sysfd"],state["sys_before"]),
                  lambda:close_dir(Path("/dev"),state["devfd"],state["dev_before"]),
                  lambda:close_dir(Path("/dev/virtio-ports"),state["aliasfd"],state["alias_parent_before"])):
        try: close()
        except BaseException as exc: errors.append(exc)
    if errors: raise RuntimeError("ACK directory cleanup failed") from errors[0]

def read_ack(fd,config,binding,ready_digest):
    deadline=time.monotonic()+config["deadlines"]["ack"]; data=bytearray(); selector=selectors.DefaultSelector(); selector.register(fd,selectors.EVENT_READ)
    try:
        while time.monotonic()<deadline:
            if not selector.select(min(.1,deadline-time.monotonic())): continue
            try: block=os.read(fd,g0.ACK_MAX+1-len(data))
            except BlockingIOError: continue
            if not block: break
            data.extend(block)
            if len(data)>g0.ACK_MAX: raise RuntimeError("ACK cap")
        else: raise TimeoutError("ACK deadline")
    finally: selector.close()
    value=g0.parse_ack(bytes(data))
    g0.validate_ack(value,nonce=config["nonce"],binding=binding,ready_digest=ready_digest,pre_digest=value["pre_mapping_sha256"],post_digest=value["post_mapping_sha256"])
    return value,bytes(data)

def serial_frame(prefix,value):
    raw=g0.build_frame(prefix,value,g0.FRAME_MAX); fd=os.open(SERIAL,os.O_WRONLY|os.O_NOCTTY|os.O_CLOEXEC)
    try:
        offset=0
        while offset<len(raw): offset+=os.write(fd,raw[offset:])
    finally: os.close(fd)

def observe_unmount_guard(namespace,nvme,serial,*,phase,context):
    ordinal=context["guard_count"]; context["guard_count"]+=1
    record={"schema":"dm-g0-guard-observation-v1","nonce":context["nonce"],"binding":context["binding"],
            "seed_manifest_sha256":context["manifest_sha256"],"ordinal":ordinal,"phase":phase,
            "evaluated":{"namespace":True,"nvme":False},"namespace":g0.guard_operand(),"nvme":g0.guard_operand(),"decision":"namespace_error"}
    original=None; original_tb=None; collecting="namespace"; current_namespace=current_nvme=None
    message="pre-unmount device/namespace changed" if phase=="pre-unmount" else "per-unmount device/namespace changed"
    try:
        current_namespace=mount_namespace()
        if current_namespace!=namespace:
            record["decision"]="namespace_mismatch"; original=RuntimeError(message)
        else:
            collecting="nvme";record["evaluated"]["nvme"]=True
            current_nvme=nvme_preflight(serial,partitions_present=True)
            if current_nvme!=nvme:record["decision"]="nvme_mismatch";original=RuntimeError(message)
            else:record["decision"]="matched"
    except BaseException as exc:
        original=exc; original_tb=exc.__traceback__;record["decision"]=collecting+"_error"
    diagnostic=None
    try:
        try:
            if record["decision"]=="namespace_error":record["namespace"]=g0.guard_operand("collection_error",namespace,error=g0.guard_error(original))
            else:
                record["namespace"]=g0.guard_operand("mismatch" if record["decision"]=="namespace_mismatch" else "matched",namespace,current_namespace)
                if record["evaluated"]["nvme"]:
                    if record["decision"]=="nvme_error":record["nvme"]=g0.guard_operand("collection_error",nvme,error=g0.guard_error(original))
                    else:record["nvme"]=g0.guard_operand("mismatch" if record["decision"]=="nvme_mismatch" else "matched",nvme,current_nvme)
            g0.validate_guard_record(record,nonce=context["nonce"],binding=context["binding"],manifest_sha256=context["manifest_sha256"])
        except BaseException as exc:
            diagnostic=exc;record=g0.guard_overflow(record,exc)
            g0.validate_guard_record(record,nonce=context["nonce"],binding=context["binding"],manifest_sha256=context["manifest_sha256"])
        serial_frame(g0.GUARD_PREFIX,record)
    except BaseException as exc:
        if diagnostic is not None:exc.add_note("guard diagnostic encoding: "+type(diagnostic).__name__)
        diagnostic=exc
    if original is not None:
        if diagnostic is not None:original.add_note("guard diagnostic failure: "+type(diagnostic).__name__)
        raise original.with_traceback(original_tb)
    if diagnostic is not None:raise RuntimeError("G0 guard diagnostic failure") from diagnostic
    return record


def initialization_identity(info):
    return [info.st_dev,info.st_ino,info.st_mode,info.st_uid,info.st_gid,info.st_nlink,info.st_size]


def close_initialization_tool(state):
    fd=state.get("fd")
    if fd is not None:state["fd"]=None;os.close(fd)


def check_initialization_executable(state):
    held=os.fstat(state["fd"]);named=os.stat(g0.INIT_UDEVADM,follow_symlinks=False)
    if initialization_identity(held)!=state["fact"]["identity"] or initialization_identity(named)!=state["fact"]["identity"]:raise RuntimeError("initialization executable changed")


def prepare_initialization_tool(udev_rule,context):
    path=Path(g0.INIT_UDEVADM);before=os.lstat(path)
    if (not stat.S_ISREG(before.st_mode) or before.st_uid!=0 or before.st_gid!=0 or before.st_mode&0o022 or not before.st_mode&0o111 or before.st_nlink!=1):raise RuntimeError("initialization executable metadata")
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC);state={"fd":fd,"fact":None}
    try:
        opened=os.fstat(fd)
        if initialization_identity(before)!=initialization_identity(opened):raise RuntimeError("initialization executable open identity")
        digest=hashlib.sha256();size=0
        while True:
            block=os.read(fd,65536)
            if not block:break
            size+=len(block)
            if size>64*g0.MIB:raise RuntimeError("initialization executable cap")
            digest.update(block)
        if size!=opened.st_size:raise RuntimeError("initialization executable size changed")
        package=udev_rule["owner"]
        if package["package"] not in ("udev","udev:amd64") or package["version"]!=g0.INIT_VERSION or package["architecture"]!="amd64":raise RuntimeError("initialization package version")
        fact={"path":g0.INIT_UDEVADM,"identity":initialization_identity(opened),"sha256":digest.hexdigest(),"package":package["package"],"version":package["version"],"architecture":package["architecture"]};state["fact"]=fact
        check_initialization_executable(state)
        owner=run_tool(["/usr/bin/dpkg-query","-S",g0.INIT_UDEVADM],timeout=10,output_cap=512,diagnostics=context)
        if owner["stdout_text"]!=package["package"]+": "+g0.INIT_UDEVADM+"\n" or owner["stderr_text"]:raise RuntimeError("initialization executable package owner")
        help=run_tool([g0.INIT_UDEVADM,"wait","--help"],timeout=10,output_cap=1024,diagnostics=context)
        if help["stderr_text"] or any(option not in help["stdout_text"] for option in ("wait","--initialized=","--timeout=")):raise RuntimeError("initialization wait options")
        check_initialization_executable(state);return state
    except BaseException as primary:
        try:close_initialization_tool(state)
        except BaseException as cleanup:primary.add_note("initialization FD cleanup: "+type(cleanup).__name__)
        raise


def wait_selected_initialization(state,appearances,config,binding,manifest_sha,context):
    targets=["/sys/class/block/"+item["name"] for item in appearances]
    if len(appearances)!=2 or [item["number"] for item in appearances]!=[1,2]:raise RuntimeError("initialization selected appearances")
    check_initialization_executable(state)
    receipt=run_tool([g0.INIT_UDEVADM,"wait","--initialized=true","--timeout=10",*targets],timeout=10,output_cap=256,diagnostics=context)
    if receipt["stdout_text"] or receipt["stderr_text"]:raise RuntimeError("initialization wait unexpected output")
    check_initialization_executable(state);facts=[]
    for item,target in zip(appearances,targets):
        dev=list(map(int,read_attr(Path(target)/"dev").split(":")))
        if dev!=item["dev"]:raise RuntimeError("initialization selected rdev changed")
        path=Path("/run/udev/data/b"+str(dev[0])+":"+str(dev[1]));raw,_=stable_file(path,4096,public=True)
        lines=[line for line in raw.splitlines(keepends=True) if line.startswith(b"I:")]
        if len(lines)!=1 or not re.fullmatch(rb"I:[1-9][0-9]{0,19}\n",lines[0]):raise RuntimeError("initialization positive I fact unavailable")
        facts.append({"number":item["number"],"sysfs_path":target,"dev":dev,"database_bytes":len(raw),"database_sha256":g0.sha256(raw),"initialized_line_base64":base64.b64encode(lines[0]).decode()})
    value={"schema":"dm-g0-initialization-v1","nonce":config["nonce"],"binding":binding,"seed_manifest_sha256":manifest_sha,"tool":state["fact"],"targets":facts,"ordinals":list(g0.INIT_ORDINALS)}
    return g0.validate_initialization(value,nonce=config["nonce"],binding=binding,manifest_sha256=manifest_sha)


def serial_case_capture(raw):
    if len(raw)>g0.CASE_MAX:raise RuntimeError('E2 raw capture cap')
    fd=os.open(SERIAL,os.O_WRONLY|os.O_NOCTTY|os.O_CLOEXEC)
    try:
        offset=0
        while offset<len(raw):
            count=os.write(fd,raw[offset:])
            if count<=0:raise RuntimeError('E2 raw capture write')
            offset+=count
    finally:os.close(fd)

def fixture_identity(path):
    info=os.lstat(path)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=g0.ORDINARY_ID or info.st_gid!=g0.ORDINARY_ID or stat.S_IMODE(info.st_mode)!=0o700:raise RuntimeError('E2 ordinary fixture identity')
    return [info.st_dev,info.st_ino,info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode),info.st_nlink]

def main():
    if os.getuid()!=0 or os.getgid()!=0: raise RuntimeError("G0 root identity")
    seed_dirs=prepare_seed_tree()
    config_raw,_=stable_seed_file(CONFIG,8192,mode=0o400,public=False,expected_dirs=seed_dirs); config=g0.validate_config(g0.loads_strict(config_raw)); manifest,manifest_sha=verify_manifest(seed_dirs); binding,_=dmi_binding()
    tool_context={"nonce":config["nonce"],"binding":binding,"manifest_sha256":manifest_sha,"tool_count":0,"guard_count":0}
    tools=tool_facts(config["deadlines"],diagnostics=tool_context); udev_rule=udev_rule_fact(config["deadlines"],diagnostics=tool_context); initial_nvme=nvme_preflight(config["nvme_serial"]); namespace=mount_namespace(); initial_mountinfo=mountinfo()
    if any(exact_mount(initial_mountinfo,path) is not None for path in config["mounts"]): raise RuntimeError("G0 preexisting mount")
    reject_selected_nvme_mount(initial_mountinfo,initial_nvme)
    mount_refs=[emit_mountinfo("initial",initial_mountinfo,config,binding,manifest_sha)]
    mount_root=Path("/mnt/dm-g0")
    if mount_root.exists() or mount_root.is_symlink(): raise RuntimeError("G0 mount root preexists")
    device=initial_nvme["device"]
    table=("label: gpt\nunit: sectors\n\n"+f"{device}p1 : start=2048, size=122880, type={GUID}\n"+f"{device}p2 : start=124928, size=131072, type={GUID}\n").encode()
    commands=[]; mounted=[]; created=[]; ack_fd=None; ack_state=None; primary=None; result=None; initialization_tool=None
    try:
        initialization_tool=prepare_initialization_tool(udev_rule,tool_context)
        commands.append(run_tool(["/usr/sbin/sfdisk",device],stdin=table,timeout=config["deadlines"]["sfdisk"],diagnostics=tool_context))
        appearances=wait_partitions(initial_nvme["namespace"],10)
        initialization=wait_selected_initialization(initialization_tool,appearances,config,binding,manifest_sha,tool_context)
        close_initialization_tool(initialization_tool);initialization_tool=None
        serial_frame(g0.INIT_PREFIX,initialization)
        nvme=nvme_preflight(config["nvme_serial"],partitions_present=True); parts=nvme["partitions"]
        table_result=run_tool(["/usr/sbin/sfdisk","--json",device],timeout=config["deadlines"]["sfdisk"],diagnostics=tool_context)
        partition_table=validate_partition_table(table_result["stdout_text"].encode(),device); commands.append(table_result)
        for part in parts: commands.append(run_tool(["/usr/sbin/mkfs.ext4","-F","-m","0","-E","lazy_itable_init=0,lazy_journal_init=0",part["path"]],timeout=config["deadlines"]["mkfs_ext4"],diagnostics=tool_context))
        mount_root.mkdir(mode=0o755); mount_root.chmod(0o755); created.append(mount_root); underlying={}; saved_mounts={}; mounted_roots={}
        for part,mount in zip(parts,config["mounts"]):
            path=Path(mount); path.mkdir(mode=0o755); path.chmod(0o755); created.append(path); before=os.lstat(path)
            if not stat.S_ISDIR(before.st_mode) or before.st_uid!=0 or before.st_gid!=0 or stat.S_IMODE(before.st_mode)!=0o755: raise RuntimeError("mountpoint metadata")
            underlying[mount]=[before.st_dev,before.st_ino]
            try:
                commands.append(run_tool(["/usr/bin/mount","-t","ext4","-o","rw,nodev,nosuid","--",part["path"],mount],timeout=config["deadlines"]["mount"],diagnostics=tool_context))
            except BaseException as original:
                try:
                    observed=mountinfo()
                    if exact_mount(observed,mount) is not None:
                        saved_mounts[mount]=validate_mount_entry(observed,mount,part); mounted.append((part,mount))
                except BaseException as discovery: original.add_note("mount effect discovery: "+type(discovery).__name__)
                raise
            mounted.append((part,mount)); snapshot=mountinfo(); saved_mounts[mount]=validate_mount_entry(snapshot,mount,part)
            mounted_roots[mount]=mountpoint_identity(mount)
            mount_refs.append(emit_mountinfo("after-p"+str(part["number"])+"-mount",snapshot,config,binding,manifest_sha))
            fixture=path/"fixture"; fixture.mkdir(mode=0o700); os.chown(fixture,g0.ORDINARY_ID,g0.ORDINARY_ID)
        fd_inventories=[root_fd_inventory({saved_mounts[path]["mount_id"] for path in config["mounts"]},"pre-qualifier")]
        verify_manifest(seed_dirs)
        ack_fd,ack_identity,ack_state=ack_port()
        ready={"schema":"dm-e2-ready-v1","nonce":config["nonce"],"binding":binding,"binding_transport":g0.BINDING_TRANSPORT,
               "seed_manifest_sha256":manifest_sha,"setup_sha256":next(e["sha256"] for e in manifest["entries"] if e["path"]==str(Path(__file__))),
               "qualify_sha256":next(e["sha256"] for e in manifest["entries"] if e["path"]=="/opt/dm-g0/helpers/guest_e2_case.py"),
               "product_entries":g0.product_entries(),"mount_namespace":namespace,"fixture_identities":[fixture_identity(Path(mount)/'fixture') for mount in config['mounts']],
               "mount_ids":[saved_mounts[mount]['mount_id'] for mount in config['mounts']],"nvme":nvme,"ack_endpoint":ack_identity,"udev_rule":udev_rule}
        g0.validate_ready(ready,nonce=config["nonce"],binding=binding,manifest_sha256=manifest_sha,setup_sha256=ready["setup_sha256"],qualify_sha256=ready["qualify_sha256"])
        ready_payload=g0.canonical(ready); ready_digest=hashlib.sha256(ready_payload).hexdigest(); serial_frame(g0.READY_PREFIX,ready)
        ack_check(ack_fd,ack_state); ack,ack_raw=read_ack(ack_fd,config,binding,ready_digest); ack_check(ack_fd,ack_state)
        ack_close(ack_state); ack_state=None; os.close(ack_fd); ack_fd=None
        case_records,case_raw=child_e2(config,manifest_sha,binding,parts,ready['mount_ids'])
        if [fixture_identity(Path(mount)/'fixture') for mount in config['mounts']]!=ready['fixture_identities']:raise RuntimeError('E2 fixture parents changed')
        verify_manifest(seed_dirs)
        observe_unmount_guard(namespace,nvme,config["nvme_serial"],phase="pre-unmount",context=tool_context)
        pre_unmount=mountinfo(); mount_refs.append(emit_mountinfo("pre-unmount",pre_unmount,config,binding,manifest_sha))
        for part,mount in zip(parts,config["mounts"]):
            check_pre_unmount_mount(pre_unmount,mount,part,saved_mounts[mount],config["probe_name"])
            os.rmdir(Path(mount)/"fixture")
            recheck_mounted_root(mount,mounted_roots[mount])
        unmounts=[]
        for part,mount in reversed(mounted.copy()):
            verify_manifest(seed_dirs)
            observe_unmount_guard(namespace,nvme,config["nvme_serial"],phase="per-unmount-p"+str(part["number"]),context=tool_context)
            immediate=mountinfo()
            check_pre_unmount_mount(immediate,mount,part,saved_mounts[mount],config["probe_name"])
            recheck_mounted_root(mount,mounted_roots[mount])
            if part["number"]==2:
                if immediate!=pre_unmount:
                    emit_mountinfo("pre-unmount",immediate,config,binding,manifest_sha)
                    raise RuntimeError("pre-p2 mountinfo changed after decision snapshot")
                phase="post-qualifier-pre-p2-unmount"
            else:
                if immediate!=after_unmount:
                    emit_mountinfo("after-p2-unmount",immediate,config,binding,manifest_sha)
                    raise RuntimeError("pre-p1 mountinfo changed after decision snapshot")
                phase="pre-p1-unmount"
            fd_inventories.append(root_fd_inventory({saved_mounts[path]["mount_id"] for _,path in mounted},phase))
            saved=saved_mounts[mount]; commands.append(run_tool(["/usr/bin/umount","--",mount],timeout=config["deadlines"]["umount"],diagnostics=tool_context))
            mounted.pop()
            after_unmount=mountinfo()
            if exact_mount(after_unmount,mount) is not None: raise RuntimeError("unmount proof")
            mount_refs.append(emit_mountinfo("after-p"+str(part["number"])+"-unmount",after_unmount,config,binding,manifest_sha))
            after=os.lstat(mount)
            if [after.st_dev,after.st_ino]!=underlying[mount]: raise RuntimeError("underlying mountpoint changed")
            unmounts.append({"partition":"p"+str(part["number"]),"mountpoint":mount,"normal":True,"mount_id":saved["mount_id"],"underlying_inode":underlying[mount]})
        for path in reversed(created): os.rmdir(path)
        created=[]
        result={"schema":"dm-e2-root-result-v1","result":case_records[-1]["data"]["outcome"],"scope":"e2-original-completion-ledger-enospc-only","nonce":config["nonce"],"binding":binding,
                "binding_transport":g0.BINDING_TRANSPORT,"seed_manifest_sha256":manifest_sha,"setup_sha256":ready["setup_sha256"],"qualify_sha256":ready["qualify_sha256"],
                "product_entries":g0.product_entries(),"ack_sha256":hashlib.sha256(ack_raw).hexdigest(),"ack_bytes":len(ack_raw),"unmounts":unmounts,"nvme":nvme,"tools":tools,"commands":commands,
                "partition_table":partition_table,"mount_namespace":namespace,"mounts":[{**saved_mounts[path],"mounted_root_identity":mounted_roots[path]} for path in config["mounts"]],"root_fd_inventories":fd_inventories,"mountinfo":mount_refs,"udev_rule":udev_rule,"case_sha256":g0.sha256(g0.canonical(case_records)),"case_result":case_records[-1]["data"]}
        g0.validate_g0_result(result,nonce=config["nonce"],binding=binding,manifest_sha256=manifest_sha,setup_sha256=ready["setup_sha256"],qualify_sha256=ready["qualify_sha256"],ack_sha256=result["ack_sha256"],ack_bytes=len(ack_raw))
    except BaseException as exc: primary=exc
    cleanup=[]
    if initialization_tool is not None:
        try:close_initialization_tool(initialization_tool)
        except BaseException as exc:cleanup.append("initialization-fd:"+type(exc).__name__)
    if ack_fd is not None:
        try: os.close(ack_fd)
        except OSError as exc: cleanup.append("ack-fd:"+type(exc).__name__)
    if ack_state is not None:
        try: ack_close(ack_state)
        except BaseException as exc: cleanup.append("ack-state:"+type(exc).__name__)
    for part,mount in reversed(mounted):
        try:
            snapshot=mountinfo()
            if mount_namespace()!=namespace: raise RuntimeError("cleanup namespace identity")
            if exact_mount(snapshot,mount) is None:
                after=os.lstat(mount)
                if [after.st_dev,after.st_ino]!=underlying[mount]: raise RuntimeError("cleanup already-unmounted identity")
                continue
            if validate_mount_entry(snapshot,mount,part)!=saved_mounts[mount]: raise RuntimeError("cleanup mount identity")
            run_tool(["/usr/bin/umount","--",mount],timeout=config["deadlines"]["umount"],diagnostics=tool_context)
            if exact_mount(mountinfo(),mount) is not None: raise RuntimeError("cleanup unmount proof")
            after=os.lstat(mount)
            if [after.st_dev,after.st_ino]!=underlying[mount]: raise RuntimeError("cleanup underlying mountpoint")
        except BaseException as exc: cleanup.append("umount-"+mount+":"+type(exc).__name__)
    for path in reversed(created):
        try:
            fixture=path/"fixture"
            if fixture.exists(): os.rmdir(fixture)
            os.rmdir(path)
        except BaseException as exc: cleanup.append("rmdir-"+str(path)+":"+type(exc).__name__)
    if primary is not None:
        if cleanup: primary.add_note("G0 cleanup failed: "+",".join(cleanup))
        raise primary
    if cleanup: raise RuntimeError("G0 cleanup failed: "+",".join(cleanup))
    if result is None: raise RuntimeError("G0 result absent")
    serial_frame(g0.RESULT_PREFIX,result)

if __name__=="__main__": main()
