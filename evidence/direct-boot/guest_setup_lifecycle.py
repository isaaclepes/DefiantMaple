"""One setup-only observation. No qualifier, product import, ACK or G0 acceptance."""
from __future__ import annotations
import base64,copy,hashlib,importlib.util,json,os,re,resource,selectors,signal,stat,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent

def load(name):
    spec=importlib.util.spec_from_file_location("lifecycle_"+name,HERE/(name+".py"));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
setup=load("guest_g0_setup");life=load("setup_lifecycle_policy");g0=setup.g0
held_dir=setup.held_dir;close_dir=setup.close_dir;sysfs_entry=setup.sysfs_entry;recheck_sysfs_entry=setup.recheck_sysfs_entry
read_attr_fd=setup.read_attr_fd;sysfs_identity=setup.sysfs_identity;_identity=setup._identity

def tick():return time.monotonic_ns()
def native(st):return [st.st_dev,st.st_ino,st.st_mode,st.st_uid,st.st_gid,st.st_nlink,st.st_rdev,st.st_size]
def mark(document,phase,edge):
    if len(document["markers"])>=128:raise RuntimeError("lifecycle marker cap")
    document["stop"]["phase"]=phase
    document["markers"].append({"ordinal":len(document["markers"]),"phase":phase,"edge":edge,"at_ns":tick()})

class Owned:
    def __init__(self,argv):
        self.proc=None;self.pidfd=None;self.start=None;self.reaped=False;self.eof=set();self.fds_closed=False;self.fd_cleanup_uncertain=False
        try:
            self.proc=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,cwd="/",env={"PATH":"/usr/sbin:/usr/bin:/sbin:/bin","HOME":"/nonexistent","LANG":"C","LC_ALL":"C","SYSTEMD_COLORS":"0","SYSTEMD_URLIFY":"0"},close_fds=True,start_new_session=False,preexec_fn=lambda:(resource.setrlimit(resource.RLIMIT_CORE,(0,0)),resource.setrlimit(resource.RLIMIT_FSIZE,(g0.MIB,g0.MIB)),resource.setrlimit(resource.RLIMIT_NOFILE,(64,64))))
            self.pidfd=os.pidfd_open(self.proc.pid,0);self.start=setup.proc_start(self.proc.pid)
            for stream in (self.proc.stdin,self.proc.stdout,self.proc.stderr):os.set_blocking(stream.fileno(),False)
        except BaseException as exc:
            try:self.close()
            except BaseException as cleanup:exc.add_note("owned acquisition cleanup: "+type(cleanup).__name__)
            exc._owned_child=self;exc._owned_cleanup=self.report();raise
    def report(self):return {"acquired":self.proc is not None,"reaped":self.reaped,"fds_closed":self.fds_closed}
    def same(self):return self.proc is not None and self.start is not None and setup.child_same(self.proc.pid,self.start)
    def signal(self,sig):
        if self.proc is None or self.reaped:raise RuntimeError("owned process unavailable/already reaped")
        if self.start is not None and not self.same():raise RuntimeError("owned process identity changed")
        # Before start-ticks acquisition, this is still our unreaped direct Popen child:
        # its PID cannot be reused, and no other code reaps it.
        if self.pidfd is not None:setup.pidfd_signal(self.pidfd,sig)
        else:self.proc.send_signal(sig)
    def close(self,drain=None):
        primary=None;close_errors=[]
        try:
            if self.proc is not None and self.proc.poll() is None:
                self.signal(signal.SIGTERM);end=time.monotonic()+5
                while self.proc.poll() is None and time.monotonic()<end:
                    if drain:drain(.05,check=False)
                    else:
                        with selectors.DefaultSelector() as selector:
                            if self.pidfd is not None:selector.register(self.pidfd,selectors.EVENT_READ)
                            selector.select(min(.05,max(0,end-time.monotonic())))
                if self.proc.poll() is None:self.signal(signal.SIGKILL)
            if self.proc is not None and not self.reaped:self.proc.wait(timeout=2);self.reaped=True
            if drain and self.proc is not None:
                end=time.monotonic()+2
                while self.eof!={"stdout","stderr"} and time.monotonic()<end:drain(.01,check=False)
                if self.eof!={"stdout","stderr"}:raise RuntimeError("observer postexit EOF uncertain")
        except BaseException as exc:primary=exc
        finally:
            if self.proc is not None:
                for stream in (self.proc.stdin,self.proc.stdout,self.proc.stderr):
                    try:
                        if not stream.closed:stream.close()
                        if not stream.closed:raise RuntimeError("owned stream close unproved")
                    except BaseException as exc:close_errors.append(type(exc).__name__)
            if self.pidfd is not None:
                fd=self.pidfd;self.pidfd=None
                try:os.close(fd)
                except BaseException as exc:close_errors.append(type(exc).__name__)
            if close_errors:self.fd_cleanup_uncertain=True
            self.fds_closed=not self.fd_cleanup_uncertain and self.pidfd is None
        if close_errors:
            if primary is None:primary=RuntimeError("owned FD cleanup uncertain: "+",".join(close_errors))
            else:primary.add_note("owned FD cleanup uncertain: "+",".join(close_errors))
        if primary:raise primary

def verify_observer_exec(child,fact):
    if fact is None or not child.same():raise RuntimeError("observer executable preflight/owner unavailable")
    path=Path(f"/proc/{child.proc.pid}/exe")
    if os.readlink(path)!=fact["canonical"]:raise RuntimeError("observer live executable path")
    fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC)
    try:
        before=os.fstat(fd)
        if native(before)!=fact["identity"]:raise RuntimeError("observer live executable identity")
        digest=hashlib.sha256();total=0
        while True:
            raw=os.read(fd,65536)
            if not raw:break
            total+=len(raw)
            if total>64*g0.MIB:raise RuntimeError("observer executable cap")
            digest.update(raw)
        if native(os.fstat(fd))!=native(before) or digest.hexdigest()!=fact["sha256"] or total!=fact["bytes"]:raise RuntimeError("observer executable digest changed")
    finally:os.close(fd)
    if not child.same() or os.readlink(path)!=fact["canonical"]:raise RuntimeError("observer process changed across executable proof")

class Observer:
    def __init__(self,document,namespace):
        self.document=document;self.fact=document["observer"];self.child=None;self.selector=selectors.DefaultSelector();self.deadline=time.monotonic()+240;self.parser=life.MonitorParser(self.fact,namespace.removeprefix("/sys"));self.failure=None
        try:
            self.child=Owned(life.MONITOR_ARGV);self.document["cleanup"]["monitor_reaped"]=False;self.child.proc.stdin.close();self.fact["started_ns"]=tick()
            verify_observer_exec(self.child,document["preflight"]["observer_tool"])
            self.fact["identity"]={"pid":self.child.proc.pid,"start_ticks":self.child.start,"pidfd":True}
            self.selector.register(self.child.proc.stdout,selectors.EVENT_READ,"stdout");self.selector.register(self.child.proc.stderr,selectors.EVENT_READ,"stderr")
            end=self.deadline-240+5
            while not self.fact["ready"] and time.monotonic()<end:self.drain(min(.05,max(0,end-time.monotonic())))
            self.drain()
            if self.parser.buffers["stderr"]:raise RuntimeError("observer incomplete startup stderr")
            if not self.fact["ready"] or not self.child.same() or self.child.proc.poll() is not None:raise RuntimeError("observer subscription readiness unavailable")
            self.fact["loss_status"]="loss_not_detected_not_proved_lossless"
        except BaseException as exc:
            self.failure=exc;self.fact["error"]=life.error(exc);self.fact["loss_status"]="incomplete_or_unknown"
            if self.child is None:self.child=getattr(exc,"_owned_child",None)
            try:self.close()
            except BaseException as cleanup:exc.add_note("observer cleanup: "+type(cleanup).__name__)
            raise
    def drain(self,timeout=0,*,check=True):
        try:
            if check and time.monotonic()>self.deadline:raise TimeoutError("observer lifetime deadline")
            pending=self.selector.select(timeout);rounds=0
            while pending:
                rounds+=1
                if rounds>64:raise RuntimeError("observer ready-drain budget")
                for key,_ in pending:
                    try:raw=os.read(key.fileobj.fileno(),4096)
                    except BlockingIOError:continue
                    if not raw:self.selector.unregister(key.fileobj);self.child.eof.add(key.data);continue
                    self.parser.feed(key.data,raw,tick())
                pending=self.selector.select(0)
            if check and (self.child.proc.poll() is not None or self.child.eof):raise RuntimeError("observer early exit/EOF")
        except BaseException as exc:
            self.failure=exc;self.fact["error"]=life.error(exc);self.fact["loss_status"]="incomplete_or_unknown"
            if check:raise
    def close(self):
        primary=None
        try:
            if self.child is not None:
                try:self.child.close(drain=self.drain)
                except BaseException as exc:primary=exc
                finally:
                    report=self.child.report()
                    self.fact["exit"]={"returncode":None if self.child.proc is None else self.child.proc.returncode,"reaped":report["reaped"],"eof":sorted(self.child.eof),"fds_closed":report["fds_closed"]}
                    self.document["cleanup"]["monitor_reaped"]=not report["acquired"] or report["reaped"]
                    if not report["fds_closed"]:self.document["cleanup"]["fds_closed"]=False
            try:self.parser.finish()
            except BaseException as exc:
                if primary is None:primary=exc
                else:primary.add_note("observer parser finish: "+type(exc).__name__)
        finally:
            self.fact["stopped_ns"]=tick()
            try:self.selector.close()
            except BaseException as exc:
                self.document["cleanup"]["fds_closed"]=False
                if primary is None:primary=exc
                else:primary.add_note("observer selector close: "+type(exc).__name__)
        if primary:
            self.fact["error"]=life.error(primary);self.fact["loss_status"]="incomplete_or_unknown";raise primary

def run_tool(document,argv,*,stdin=b"",timeout,observer=None,observer_fatal=True):
    if argv[0] not in (*setup.TOOLS,life.UDEV) or len(argv)>8 or any(not isinstance(x,str) or not 0<len(x.encode())<=512 for x in argv) or len(stdin)>4096 or len(document["commands"])>=23:raise RuntimeError("lifecycle exact tool contract")
    item={"ordinal":len(document["commands"]),"argv":list(argv),"stdin_base64":life.b64(stdin),"stdout_base64":"","stderr_base64":"","deadline":timeout,"output_cap":65536,"returncode":None,"reaped":False,"fds_closed":False,"eof":[False,False],"truncated":False,"error":None,"start_ns":tick(),"end_ns":0}
    out={"stdout":bytearray(),"stderr":bytearray()};child=None;sel=None;sent=0;primary=None
    try:
        sel=selectors.DefaultSelector();child=Owned(argv);sel.register(child.proc.stdout,selectors.EVENT_READ,"stdout");sel.register(child.proc.stderr,selectors.EVENT_READ,"stderr")
        if stdin:sel.register(child.proc.stdin,selectors.EVENT_WRITE,"stdin")
        else:child.proc.stdin.close()
        end=time.monotonic()+timeout
        while sel.get_map() and time.monotonic()<end:
            if observer:
                try:observer.drain(check=observer_fatal)
                except BaseException as diagnostic:
                    if observer_fatal:raise
                    document["stop"]["diagnostic_error"]=life.error(diagnostic)
            if setup.direct_children(child.proc.pid):raise RuntimeError("tool descendant")
            for key,_ in sel.select(min(.05,max(0,end-time.monotonic()))):
                if key.data=="stdin":
                    try:sent+=os.write(key.fileobj.fileno(),stdin[sent:])
                    except BrokenPipeError:raise RuntimeError("tool stdin early close")
                    if sent==len(stdin):sel.unregister(key.fileobj);key.fileobj.close()
                else:
                    raw=os.read(key.fileobj.fileno(),4096)
                    if not raw:sel.unregister(key.fileobj);child.eof.add(key.data);continue
                    buf=out[key.data]
                    used=sum(len(life.unb64(x[k],65536)) for x in document["commands"] for k in ("stdout_base64","stderr_base64"))+sum(len(x) for x in out.values())
                    if used+len(raw)>life.TOOL_AGGREGATE:
                        buf.extend(raw[:max(0,life.TOOL_AGGREGATE-used)]);item["truncated"]=True;raise RuntimeError("tool aggregate overflow")
                    if len(buf)+len(raw)>65536:buf.extend(raw[:65536-len(buf)]);item["truncated"]=True;raise RuntimeError("tool stream cap")
                    buf.extend(raw)
        if sel.get_map():raise TimeoutError("tool deadline")
        child.proc.wait(timeout=max(.001,end-time.monotonic()));child.reaped=True
        if child.proc.returncode:raise RuntimeError("tool nonzero exit")
    except BaseException as exc:
        primary=exc
        if child is None:child=getattr(exc,"_owned_child",None)
    finally:
        if child is not None:
            try:child.close()
            except BaseException as exc:
                document["cleanup"]["tools_reaped"]=False
                if primary is None:primary=exc
                else:primary.add_note("tool cleanup: "+type(exc).__name__)
            item["returncode"]=None if child.proc is None else child.proc.returncode;item["reaped"]=child.reaped;item["fds_closed"]=child.fds_closed;
            if not child.fds_closed:document["cleanup"]["fds_closed"]=False
            if child.proc is not None and not child.reaped:document["cleanup"]["tools_reaped"]=False
            item["eof"]=[name in child.eof for name in ("stdout","stderr")]
        if sel is not None:
            try:sel.close()
            except BaseException as exc:
                document["cleanup"]["fds_closed"]=False
                if primary is None:primary=exc
                else:primary.add_note("tool selector close: "+type(exc).__name__)
        item["end_ns"]=tick();item["stdout_base64"]=life.b64(out["stdout"]);item["stderr_base64"]=life.b64(out["stderr"]);item["error"]=None if primary is None else life.error(primary);document["commands"].append(item)
    total=sum(len(life.unb64(x[k],65536)) for x in document["commands"] for k in ("stdout_base64","stderr_base64"))
    if total>life.TOOL_AGGREGATE:
        if primary:primary.add_note("tool aggregate overflow")
        else:primary=RuntimeError("tool aggregate overflow")
    if primary:raise primary
    return {"argv":argv,"stdin_bytes":len(stdin),"stdin_sha256":life.sha(stdin),"stdout_bytes":len(out["stdout"]),"stdout_sha256":life.sha(bytes(out["stdout"])),"stdout_text":bytes(out["stdout"]).decode("utf-8","strict"),"stderr_bytes":len(out["stderr"]),"stderr_sha256":life.sha(bytes(out["stderr"])),"stderr_text":bytes(out["stderr"]).decode("utf-8","strict"),"returncode":0}

def trace_item(observations,role,stage,*,info=None,raw=None):
    values=observations.setdefault("trace",[])
    if len(values)>=256 or len(role.encode())>512:raise RuntimeError("metadata trace cap")
    values.append({"role":role,"stage":stage,"stat":None if info is None else native(info),"raw_base64":None if raw is None else life.b64(raw)})

def trace_stat(observations,role,stage,info):
    trace_item(observations,role,stage,info=info);return info

def trace_bytes(observations,role,stage,raw):
    trace_item(observations,role,stage,raw=raw);return raw

def trace_link(observations,role,stage,value):
    trace_item(observations,role,stage,raw=os.fsencode(value));return value

def record_held_dir(path, cap, *, observations):
    before = trace_stat(observations, str(path), 'held_dir:282', os.lstat(path))
    if not stat.S_ISDIR(before.st_mode) or before.st_uid != 0 or before.st_gid != 0 or before.st_mode & 18:
        raise RuntimeError('directory boundary')
    fd = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        opened = trace_stat(observations, str(path), 'held_dir:287', os.fstat(fd))
        names = os.listdir(fd)
        if len(names) > cap or any((not isinstance(name, str) or len(name) > 128 or name in ('.', '..') for name in names)):
            raise RuntimeError('directory entry cap')
        if _identity(before) != _identity(opened):
            raise RuntimeError('directory identity')
        return (fd, before, sorted(names))
    except BaseException:
        os.close(fd)
        raise

def record_close_dir(path, fd, before, *, observations):
    try:
        after_fd = trace_stat(observations, str(path), 'close_dir:294', os.fstat(fd))
        after = trace_stat(observations, str(path), 'close_dir:294', os.lstat(path))
    finally:
        os.close(fd)
    if _identity(before) != _identity(after_fd) or _identity(before) != _identity(after):
        raise RuntimeError('directory changed')

def record_recheck_sysfs_entry(root_fd, name, before, target, fd, *, observations):
    after = trace_stat(observations, str(name), 'recheck_sysfs_entry:311', os.stat(name, dir_fd=root_fd, follow_symlinks=False))
    if _identity(before) != _identity(after) or trace_link(observations, str(name), 'recheck_sysfs_entry:312', os.readlink(name, dir_fd=root_fd)) != target or (not stat.S_ISDIR(trace_stat(observations, str(name), 'recheck_sysfs_entry:312', os.fstat(fd)).st_mode)) or (_identity(trace_stat(observations, str(name), 'recheck_sysfs_entry:313', os.fstat(fd))) != _identity(trace_stat(observations, str(name), 'recheck_sysfs_entry:313', os.stat(name, dir_fd=root_fd, follow_symlinks=True)))):
        raise RuntimeError('sysfs entry changed')

def record_sysfs_entry(root, root_fd, name, *, observations):
    before = trace_stat(observations, str(name), 'sysfs_entry:299', os.stat(name, dir_fd=root_fd, follow_symlinks=False))
    if not stat.S_ISLNK(before.st_mode) or before.st_uid != 0:
        raise RuntimeError('sysfs class entry type')
    target = trace_link(observations, str(name), 'sysfs_entry:301', os.readlink(name, dir_fd=root_fd))
    if not 0 < len(target) <= 512 or target.startswith('/'):
        raise RuntimeError('sysfs link target')
    canonical = (root / name).resolve(strict=True)
    if not str(canonical).startswith('/sys/devices/'):
        raise RuntimeError('sysfs link escape')
    fd = os.open(canonical, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        record_recheck_sysfs_entry(root_fd, name, before, target, fd, observations=observations)
    except BaseException:
        os.close(fd)
        raise
    return (fd, before, target, canonical)

def record_read_attr_fd(dirfd, name, cap=256, *, observations):
    before = trace_stat(observations, str(dirfd) + ':' + str(name), 'read_attr_fd:323', os.stat(name, dir_fd=dirfd, follow_symlinks=False))
    if not stat.S_ISREG(before.st_mode) or before.st_uid != 0 or before.st_gid != 0:
        raise RuntimeError('sysfs attr metadata')
    fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=dirfd)
    try:
        if _identity(trace_stat(observations, str(dirfd) + ':' + str(name), 'read_attr_fd:327', os.fstat(fd))) != _identity(before):
            raise RuntimeError('sysfs attr open identity')
        data = bytearray()
        while True:
            block = trace_bytes(observations, str(dirfd) + ':' + str(name), 'read_attr_fd:330', os.read(fd, cap + 1 - len(data)))
            if not block:
                break
            data.extend(block)
            if len(data) > cap:
                raise RuntimeError('sysfs attr cap')
        after_fd = trace_stat(observations, str(dirfd) + ':' + str(name), 'read_attr_fd:334', os.fstat(fd))
    finally:
        os.close(fd)
    after = trace_stat(observations, str(dirfd) + ':' + str(name), 'read_attr_fd:336', os.stat(name, dir_fd=dirfd, follow_symlinks=False))
    if _identity(before) != _identity(after_fd) or _identity(before) != _identity(after) or (not data.endswith(b'\n')) or (b'\x00' in data):
        raise RuntimeError('sysfs attr changed/format')
    return data[:-1].decode('ascii')

def record_sysfs_identity(fd, *, observations):
    opened = trace_stat(observations, str(fd), 'sysfs_identity:317', os.fstat(fd))
    if not stat.S_ISDIR(opened.st_mode) or opened.st_uid != 0 or opened.st_gid != 0 or opened.st_mode & 18:
        raise RuntimeError('sysfs target metadata')
    return [opened.st_dev, opened.st_ino, opened.st_uid, opened.st_gid, stat.S_IMODE(opened.st_mode)]

def recorded_nvme_preflight(serial, *, partitions_present=False, observations):
    nvme_root, block_root = (Path('/sys/class/nvme'), Path('/sys/class/block'))
    nfd, nbefore, controllers = record_held_dir(nvme_root, 64, observations=observations)
    try:
        bfd, bbefore, blocks = record_held_dir(block_root, 512, observations=observations)
    except BaseException:
        os.close(nfd)
        raise
    try:
        nvme_controllers = [name for name in controllers if re.fullmatch('nvme(0|[1-9][0-9]{0,9})', name)]
        nvme_blocks = [name for name in blocks if re.fullmatch('nvme[0-9]+n[0-9]+(?:p[0-9]+)?', name)]
        if len(nvme_controllers) != 1:
            raise RuntimeError('NVMe controller count')
        expected_count = 3 if partitions_present else 1
        namespaces = [item for item in nvme_blocks if 'p' not in item]
        if len(nvme_blocks) != expected_count or len(namespaces) != 1:
            raise RuntimeError('NVMe namespace/partition count')
        ctrl, name = (nvme_controllers[0], namespaces[0])
        expected_names = {name} | ({name + 'p1', name + 'p2'} if partitions_present else set())
        if set(nvme_blocks) != expected_names:
            raise RuntimeError('NVMe partition names')
        if not re.fullmatch(re.escape(ctrl) + 'n(0|[1-9][0-9]{0,9})', name):
            raise RuntimeError('NVMe namespace/controller name')
        cfd, cbefore, ctarget, ccanonical = record_sysfs_entry(nvme_root, nfd, ctrl, observations=observations)
        try:
            sfd, sbefore, starget, scanonical = record_sysfs_entry(block_root, bfd, name, observations=observations)
        except BaseException:
            os.close(cfd)
            raise
        try:
            if record_read_attr_fd(cfd, 'serial', observations=observations) != serial or record_read_attr_fd(cfd, 'transport', observations=observations) != 'pcie' or '/pci' not in str(ccanonical):
                raise RuntimeError('NVMe serial/transport/PCI')
            if ccanonical not in scanonical.parents:
                raise RuntimeError('NVMe namespace ancestry')
            if int(record_read_attr_fd(sfd, 'size', observations=observations)) != g0.SECTORS:
                raise RuntimeError('NVMe sector count')
            qfd = os.open('queue', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=sfd)
            try:
                if int(record_read_attr_fd(qfd, 'logical_block_size', observations=observations)) != g0.SECTOR_BYTES:
                    raise RuntimeError('NVMe logical sector')
            finally:
                os.close(qfd)
            major, minor = map(int, record_read_attr_fd(sfd, 'dev', observations=observations).split(':'))
            devroot, devbefore, _ = record_held_dir(Path('/dev'), 512, observations=observations)
            try:
                before = trace_stat(observations, str(serial), 'nvme_preflight:371', os.stat(name, dir_fd=devroot, follow_symlinks=False))
                dfd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=devroot)
                try:
                    opened = trace_stat(observations, str(serial), 'nvme_preflight:373', os.fstat(dfd))
                    if _identity(before) != _identity(opened) or not stat.S_ISBLK(opened.st_mode) or opened.st_uid != 0 or opened.st_mode & 2 or ((os.major(opened.st_rdev), os.minor(opened.st_rdev)) != (major, minor)):
                        raise RuntimeError('NVMe device identity')
                finally:
                    os.close(dfd)
                if _identity(trace_stat(observations, str(serial), 'nvme_preflight:377', os.stat(name, dir_fd=devroot, follow_symlinks=False))) != _identity(before):
                    raise RuntimeError('NVMe device changed')
                partition_facts = []
                if partitions_present:
                    for number, (start, sectors) in enumerate(((2048, 122880), (124928, 131072)), 1):
                        pname = name + 'p' + str(number)
                        pfd, pbefore, ptarget, pcanonical = record_sysfs_entry(block_root, bfd, pname, observations=observations)
                        try:
                            if scanonical not in pcanonical.parents or int(record_read_attr_fd(pfd, 'start', observations=observations)) != start or int(record_read_attr_fd(pfd, 'size', observations=observations)) != sectors:
                                raise RuntimeError('NVMe partition geometry')
                            pmajor, pminor = map(int, record_read_attr_fd(pfd, 'dev', observations=observations).split(':'))
                            pnode = trace_stat(observations, str(serial), 'nvme_preflight:385', os.stat(pname, dir_fd=devroot, follow_symlinks=False))
                            pdevice = os.open(pname, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=devroot)
                            try:
                                popened = trace_stat(observations, str(serial), 'nvme_preflight:388', os.fstat(pdevice))
                                if _identity(pnode) != _identity(popened) or not stat.S_ISBLK(popened.st_mode) or popened.st_uid != 0 or popened.st_mode & 2 or ((os.major(popened.st_rdev), os.minor(popened.st_rdev)) != (pmajor, pminor)):
                                    raise RuntimeError('NVMe partition node')
                                record_recheck_sysfs_entry(bfd, pname, pbefore, ptarget, pfd, observations=observations)
                                if _identity(trace_stat(observations, str(serial), 'nvme_preflight:393', os.stat(pname, dir_fd=devroot, follow_symlinks=False))) != _identity(pnode):
                                    raise RuntimeError('NVMe partition node changed')
                                partition_facts.append({'number': number, 'name': pname, 'path': '/dev/' + pname, 'start': start, 'sectors': sectors, 'dev': [pmajor, pminor], 'sysfs_path': str(pcanonical), 'node_identity': [popened.st_dev, popened.st_ino, popened.st_uid, popened.st_gid, stat.S_IMODE(popened.st_mode), popened.st_nlink, pmajor, pminor], 'sysfs_identity': record_sysfs_identity(pfd, observations=observations)})
                            finally:
                                os.close(pdevice)
                        finally:
                            os.close(pfd)
            finally:
                record_close_dir(Path('/dev'), devroot, devbefore, observations=observations)
            record_recheck_sysfs_entry(nfd, ctrl, cbefore, ctarget, cfd, observations=observations)
            record_recheck_sysfs_entry(bfd, name, sbefore, starget, sfd, observations=observations)
            result = {'controller': ctrl, 'namespace': name, 'device': '/dev/' + name, 'controller_path': str(ccanonical), 'namespace_path': str(scanonical), 'serial': serial, 'transport': 'pcie', 'bytes': g0.NVME_BYTES, 'sector_bytes': g0.SECTOR_BYTES, 'sectors': g0.SECTORS, 'dev': [major, minor], 'node_identity': [opened.st_dev, opened.st_ino, opened.st_uid, opened.st_gid, stat.S_IMODE(opened.st_mode), opened.st_nlink, major, minor], 'controller_identity': record_sysfs_identity(cfd, observations=observations), 'namespace_identity': record_sysfs_identity(sfd, observations=observations)}
            if partitions_present:
                result['partitions'] = partition_facts
            return result
        finally:
            os.close(cfd)
            os.close(sfd)
    finally:
        try:
            record_close_dir(nvme_root, nfd, nbefore, observations=observations)
        finally:
            record_close_dir(block_root, bfd, bbefore, observations=observations)

def metadata_nvme(serial, *, partitions_present=False, observations):
    nvme_root, block_root = (Path('/sys/class/nvme'), Path('/sys/class/block'))
    nfd, nbefore, controllers = record_held_dir(nvme_root, 64, observations=observations)
    try:
        bfd, bbefore, blocks = record_held_dir(block_root, 512, observations=observations)
    except BaseException:
        os.close(nfd)
        raise
    try:
        nvme_controllers = [name for name in controllers if re.fullmatch('nvme(0|[1-9][0-9]{0,9})', name)]
        nvme_blocks = [name for name in blocks if re.fullmatch('nvme[0-9]+n[0-9]+(?:p[0-9]+)?', name)]
        if len(nvme_controllers) != 1:
            raise RuntimeError('NVMe controller count')
        expected_count = 3 if partitions_present else 1
        namespaces = [item for item in nvme_blocks if 'p' not in item]
        if len(nvme_blocks) != expected_count or len(namespaces) != 1:
            raise RuntimeError('NVMe namespace/partition count')
        ctrl, name = (nvme_controllers[0], namespaces[0])
        expected_names = {name} | ({name + 'p1', name + 'p2'} if partitions_present else set())
        if set(nvme_blocks) != expected_names:
            raise RuntimeError('NVMe partition names')
        if not re.fullmatch(re.escape(ctrl) + 'n(0|[1-9][0-9]{0,9})', name):
            raise RuntimeError('NVMe namespace/controller name')
        cfd, cbefore, ctarget, ccanonical = record_sysfs_entry(nvme_root, nfd, ctrl, observations=observations)
        try:
            sfd, sbefore, starget, scanonical = record_sysfs_entry(block_root, bfd, name, observations=observations)
        except BaseException:
            os.close(cfd)
            raise
        try:
            if record_read_attr_fd(cfd, 'serial', observations=observations) != serial or record_read_attr_fd(cfd, 'transport', observations=observations) != 'pcie' or '/pci' not in str(ccanonical):
                raise RuntimeError('NVMe serial/transport/PCI')
            if ccanonical not in scanonical.parents:
                raise RuntimeError('NVMe namespace ancestry')
            if int(record_read_attr_fd(sfd, 'size', observations=observations)) != g0.SECTORS:
                raise RuntimeError('NVMe sector count')
            qfd = os.open('queue', os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=sfd)
            try:
                if int(record_read_attr_fd(qfd, 'logical_block_size', observations=observations)) != g0.SECTOR_BYTES:
                    raise RuntimeError('NVMe logical sector')
            finally:
                os.close(qfd)
            major, minor = map(int, record_read_attr_fd(sfd, 'dev', observations=observations).split(':'))
            devroot, devbefore, _ = record_held_dir(Path('/dev'), 512, observations=observations)
            try:
                before = trace_stat(observations, str(serial), 'nvme_preflight:371', os.stat(name, dir_fd=devroot, follow_symlinks=False))
                dfd = os.open(name, os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=devroot)
                try:
                    opened = trace_stat(observations, str(serial), 'nvme_preflight:373', os.fstat(dfd))
                    if _identity(before) != _identity(opened) or not stat.S_ISBLK(opened.st_mode) or opened.st_uid != 0 or opened.st_mode & 2 or ((os.major(opened.st_rdev), os.minor(opened.st_rdev)) != (major, minor)):
                        raise RuntimeError('NVMe device identity')
                finally:
                    os.close(dfd)
                if _identity(trace_stat(observations, str(serial), 'nvme_preflight:377', os.stat(name, dir_fd=devroot, follow_symlinks=False))) != _identity(before):
                    raise RuntimeError('NVMe device changed')
                partition_facts = []
                if partitions_present:
                    for number, (start, sectors) in enumerate(((2048, 122880), (124928, 131072)), 1):
                        pname = name + 'p' + str(number)
                        pfd, pbefore, ptarget, pcanonical = record_sysfs_entry(block_root, bfd, pname, observations=observations)
                        try:
                            if scanonical not in pcanonical.parents or int(record_read_attr_fd(pfd, 'start', observations=observations)) != start or int(record_read_attr_fd(pfd, 'size', observations=observations)) != sectors:
                                raise RuntimeError('NVMe partition geometry')
                            pmajor, pminor = map(int, record_read_attr_fd(pfd, 'dev', observations=observations).split(':'))
                            pnode = trace_stat(observations, str(serial), 'nvme_preflight:385', os.stat(pname, dir_fd=devroot, follow_symlinks=False))
                            pdevice = os.open(pname, os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=devroot)
                            try:
                                popened = trace_stat(observations, str(serial), 'nvme_preflight:388', os.fstat(pdevice))
                                if _identity(pnode) != _identity(popened) or not stat.S_ISBLK(popened.st_mode) or popened.st_uid != 0 or popened.st_mode & 2 or ((os.major(popened.st_rdev), os.minor(popened.st_rdev)) != (pmajor, pminor)):
                                    raise RuntimeError('NVMe partition node')
                                record_recheck_sysfs_entry(bfd, pname, pbefore, ptarget, pfd, observations=observations)
                                if _identity(trace_stat(observations, str(serial), 'nvme_preflight:393', os.stat(pname, dir_fd=devroot, follow_symlinks=False))) != _identity(pnode):
                                    raise RuntimeError('NVMe partition node changed')
                                partition_facts.append({'number': number, 'name': pname, 'path': '/dev/' + pname, 'start': start, 'sectors': sectors, 'dev': [pmajor, pminor], 'sysfs_path': str(pcanonical), 'node_identity': [popened.st_dev, popened.st_ino, popened.st_uid, popened.st_gid, stat.S_IMODE(popened.st_mode), popened.st_nlink, pmajor, pminor], 'sysfs_identity': record_sysfs_identity(pfd, observations=observations)})
                            finally:
                                os.close(pdevice)
                        finally:
                            os.close(pfd)
            finally:
                record_close_dir(Path('/dev'), devroot, devbefore, observations=observations)
            record_recheck_sysfs_entry(nfd, ctrl, cbefore, ctarget, cfd, observations=observations)
            record_recheck_sysfs_entry(bfd, name, sbefore, starget, sfd, observations=observations)
            result = {'controller': ctrl, 'namespace': name, 'device': '/dev/' + name, 'controller_path': str(ccanonical), 'namespace_path': str(scanonical), 'serial': serial, 'transport': 'pcie', 'bytes': g0.NVME_BYTES, 'sector_bytes': g0.SECTOR_BYTES, 'sectors': g0.SECTORS, 'dev': [major, minor], 'node_identity': [opened.st_dev, opened.st_ino, opened.st_uid, opened.st_gid, stat.S_IMODE(opened.st_mode), opened.st_nlink, major, minor], 'controller_identity': record_sysfs_identity(cfd, observations=observations), 'namespace_identity': record_sysfs_identity(sfd, observations=observations)}
            if partitions_present:
                result['partitions'] = partition_facts
            return result
        finally:
            os.close(cfd)
            os.close(sfd)
    finally:
        try:
            record_close_dir(nvme_root, nfd, nbefore, observations=observations)
        finally:
            record_close_dir(block_root, bfd, bbefore, observations=observations)

read_attr=setup.read_attr
def appearance(namespace, deadline, observer, record):
    out=[]
    for number,(start,size) in enumerate(((2048,122880),(124928,131072)),1):
        name=f"{namespace}p{number}"; path=Path("/dev")/name; sysfs=Path("/sys/class/block")/name; end=time.monotonic()+deadline
        while time.monotonic()<end:
            observer.drain()
            try:
                if int(read_attr(sysfs/"start"))==start and int(read_attr(sysfs/"size"))==size:
                    major,minor=map(int,read_attr(sysfs/"dev").split(":")); st=os.lstat(path)
                    if stat.S_ISBLK(st.st_mode) and (os.major(st.st_rdev),os.minor(st.st_rdev))==(major,minor):
                        out.append({"number":number,"name":name,"path":str(path),"start":start,"sectors":size,"dev":[major,minor]}); record(out[-1]); break
            except FileNotFoundError: pass
            time.sleep(.05)
        else: raise RuntimeError("partition appearance deadline")
    return out

stable_file=setup.stable_file
def tool_facts(document,deadlines,paths=setup.TOOLS):
    facts=[]
    for raw in paths:
        path=Path(raw); requested=os.lstat(path); resolved=path.resolve(strict=True); data,fact=stable_file(resolved,64*g0.MIB,public=True)
        if stat.S_ISLNK(requested.st_mode):
            target=os.readlink(path)
            if not 0<len(target)<=512: raise RuntimeError("tool link target")
        elif stat.S_ISREG(requested.st_mode): target=None
        else: raise RuntimeError("tool requested type")
        owner=run_tool(document,["/usr/bin/dpkg-query","-S",str(resolved)],timeout=deadlines["dpkg_query"])
        if owner["stderr_text"] or owner["stdout_text"].count("\n")!=1 or ": " not in owner["stdout_text"]: raise RuntimeError("tool owner output")
        package,owned_path=owner["stdout_text"].rstrip("\n").split(": ",1)
        if owned_path!=str(resolved) or not re.fullmatch(r"[a-z0-9][a-z0-9+.-]*(?::[a-z0-9][a-z0-9-]*)?",package): raise RuntimeError("tool owner identity")
        version=run_tool(document,["/usr/bin/dpkg-query","-W","-f=${binary:Package}\t${Version}\t${Architecture}\n",package],timeout=deadlines["dpkg_query"])
        fields=version["stdout_text"].rstrip("\n").split("\t")
        if version["stderr_text"] or version["stdout_text"].count("\n")!=1 or len(fields)!=3 or fields[0]!=package or not all(0<len(item)<=512 for item in fields): raise RuntimeError("tool package identity")
        requested_after=os.lstat(path)
        if _identity(requested)!=_identity(requested_after) or (target is not None and os.readlink(path)!=target): raise RuntimeError("tool requested path changed")
        fact.update({"requested":raw,"requested_type":"symlink" if target is not None else "regular","requested_target":target,
                     "owner":{"package":package,"version":fields[1],"architecture":fields[2]},"owner_query":owner,"version_query":version}); facts.append(fact)
    return facts

class Transition(RuntimeError):pass

def capture_file(path,cap=8192):
    value={"status":"error","path":str(path),"before":None,"opened":None,"after":None,"raw_base64":"","error":None};fd=parent_fd=None
    try:
        parent_fd,_=setup.secure_dir(path.parent)
        before=os.stat(path.name,dir_fd=parent_fd,follow_symlinks=False);value["before"]=native(before)
        if not stat.S_ISREG(before.st_mode) or before.st_uid!=0 or before.st_gid!=0 or before.st_mode&0o022 or before.st_nlink!=1:raise RuntimeError("observation file metadata")
        fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent_fd);opened=os.fstat(fd);value["opened"]=native(opened);raw=bytearray()
        while True:
            block=os.read(fd,min(4096,cap+1-len(raw)))
            if not block:break
            raw.extend(block)
            if len(raw)>cap:
                value["raw_base64"]=life.b64(bytes(raw[:cap]));raise RuntimeError("observation file cap; retained prefix")
        after_fd=os.fstat(fd);after=os.stat(path.name,dir_fd=parent_fd,follow_symlinks=False);value["after"]=native(after);value["raw_base64"]=life.b64(bytes(raw))
        if native(before)!=native(opened) or native(opened)!=native(after_fd) or native(opened)!=native(after):value["status"]="unstable";raise RuntimeError("observation file changed")
        value["status"]="present"
    except FileNotFoundError as exc:value["status"]="absent";value["error"]=life.error(exc)
    except BaseException as exc:value["error"]=life.error(exc)
    finally:
        for acquired in (fd,parent_fd):
            if acquired is not None:
                try:os.close(acquired)
                except BaseException as exc:
                    value["status"]="error"
                    if value["error"] is None:value["error"]=life.error(exc)
    return value

def snapshot(document,phase,baseline,namespace,serial,observer):
    document["stop"]["phase"]=phase
    observer.drain();start=tick();record={"ordinal":len(document["snapshots"]),"phase":phase,"start_ns":start,"end_ns":start,"original_facts":{"namespace":namespace,"nvme":baseline},"current":None,"native":{"trace":[]},"initstate":[],"database":[],"diff":[],"error":None,"diagnostic_error":None};primary=None
    try:
        current_ns=setup.mount_namespace();current=metadata_nvme(serial,partitions_present=True,observations=record["native"])
        record["current"]={"namespace":current_ns,"nvme":current};record["diff"]=g0.guard_diff(record["original_facts"],record["current"])
        if current_ns!=namespace or current!=baseline:primary=Transition("setup lifecycle original device/namespace identity changed")
        entries=[current,*current["partitions"]];expected=[baseline,*baseline["partitions"]]
        for part,saved in zip(entries,expected):
            path=part.get("sysfs_path",part.get("namespace_path"));record["initstate"].append(capture_file(Path(path)/"initstate",256))
            if part["dev"]!=saved["dev"]:
                record["database"].append({"status":"not_collected","path":"","before":None,"opened":None,"after":None,"raw_base64":"","error":life.error(RuntimeError("rdev changed; database not followed"))});continue
            major,minor=saved["dev"];record["database"].append(capture_file(Path(f"/run/udev/data/b{major}:{minor}")))
        if any(item["status"] in ("unstable","error") for item in record["initstate"]+record["database"]):
            if primary is None:primary=RuntimeError("setup snapshot field unavailable/unstable")
    except BaseException as exc:
        if primary is None:primary=exc
        else:
            primary.add_note("supplementary snapshot diagnostic: "+type(exc).__name__);record["diagnostic_error"]=life.error(exc)
    finally:
        record["end_ns"]=tick();record["error"]=None if primary is None else life.error(primary)
        if len(document["snapshots"])>=14 or len(life.canonical(record))>life.SNAPSHOT_MAX:
            diagnostic=RuntimeError("setup snapshot cap; exact operands unavailable")
            if primary is None:primary=diagnostic
            else:primary.add_note("snapshot diagnostic cap; original error preserved")
            record.update(original_facts=None,current=None,native={"status":"not_collected"},initstate=[],database=[],diff=[],error=life.error(primary),diagnostic_error=life.error(diagnostic))
            if len(document["snapshots"])>=14:
                document["stop"]["diagnostic_error"]=life.error(diagnostic)
            else:document["snapshots"].append(record)
        else:document["snapshots"].append(record)
    if primary:raise primary
    observer.drain();return record

def capture_baseline(document,namespace,serial,observer):
    phase="original-partition-baseline";document["stop"]["phase"]=phase;mark(document,phase,"before");start=tick();trace={"trace":[]};baseline=None;primary=None
    record={"ordinal":len(document["snapshots"]),"phase":phase,"start_ns":start,"end_ns":start,"original_facts":None,"current":None,"native":trace,"initstate":[],"database":[],"diff":[],"error":None,"diagnostic_error":None}
    try:
        baseline=recorded_nvme_preflight(serial,partitions_present=True,observations=trace)
        document["stop"]["baseline_captured"]=True
        record["original_facts"]={"namespace":namespace,"nvme":baseline};record["current"]=record["original_facts"]
        # Extra init/database reads occur only AFTER the original baseline returned.
        for part in (baseline,*baseline["partitions"]):
            path=part.get("sysfs_path",part.get("namespace_path"));record["initstate"].append(capture_file(Path(path)/"initstate",256))
            major,minor=part["dev"];record["database"].append(capture_file(Path(f"/run/udev/data/b{major}:{minor}")))
        if any(item["status"] in ("unstable","error") for item in record["initstate"]+record["database"]):raise RuntimeError("baseline supplementary field unavailable/unstable")
    except BaseException as exc:primary=exc
    finally:
        record["end_ns"]=tick();record["error"]=None if primary is None else life.error(primary)
        if len(life.canonical(record))>life.SNAPSHOT_MAX:
            diagnostic=RuntimeError("baseline snapshot cap; exact operands unavailable")
            if primary is None:primary=diagnostic
            else:primary.add_note("baseline diagnostic cap")
            record.update(original_facts=None,current=None,native={"status":"not_collected"},initstate=[],database=[],error=life.error(primary),diagnostic_error=life.error(diagnostic))
        document["snapshots"].append(record)
    if primary:raise primary
    mark(document,phase,"after");observer.drain();return baseline

def original_record(document,phase,facts):
    at=tick();record={"ordinal":len(document["snapshots"]),"phase":phase,"start_ns":at,"end_ns":at,"original_facts":facts,"current":None,"native":{"status":"not_collected"},"initstate":[],"database":[],"diff":[],"error":None,"diagnostic_error":None}
    if len(document["snapshots"])>=14:raise RuntimeError("setup snapshot cap")
    document["snapshots"].append(record)

def verify_seed():
    path=Path("/opt/dm-g0/setup-lifecycle-manifest.json");raw,_=setup.stable_file(path,g0.MIB,mode=0o444,public=True);manifest=g0.loads_strict(raw)
    life.validate_seed_manifest(manifest)
    for item in manifest["entries"]:
        fd,_=setup.secure_dir(Path(item["path"]).parent)
        try:
            data,fact=setup.stable_file(Path(item["path"]),g0.MIB,mode=item["mode"],public=item["public"])
            if len(data)!=item["bytes"] or fact["sha256"]!=item["sha256"]:raise RuntimeError("lifecycle seed digest")
        finally:os.close(fd)
    return manifest,life.sha(raw)

def observer_preflight(document,deadlines):
    canonical_before=Path(life.UDEV).resolve(strict=True);identity_before=native(os.stat(canonical_before,follow_symlinks=False))
    fact=tool_facts(document,deadlines,(life.UDEV,))[0];owner=fact["owner"]
    if owner["version"]!=life.UDEV_VERSION:raise RuntimeError("unsupported observer package version")
    version=run_tool(document,[life.UDEV,"--version"],timeout=10)
    if version["stderr_text"] or not re.fullmatch(r"255(?: \([^\n]*255\.4-1ubuntu8\.18[^\n]*\))?\n",version["stdout_text"]):raise RuntimeError("observer version shape")
    for argv,required in (([life.UDEV,"--help"],("--debug","--version","--help")),([life.UDEV,"monitor","--help"],("--kernel","--udev","--property","--subsystem-match"))):
        receipt=run_tool(document,argv,timeout=10)
        if receipt["stderr_text"] or any(word not in receipt["stdout_text"] for word in required):raise RuntimeError("observer options unavailable")
    resolved=Path(fact["path"]);st=os.stat(resolved,follow_symlinks=False)
    if native(st)!=identity_before or str(resolved)!=str(canonical_before) or not stat.S_ISREG(st.st_mode) or not st.st_mode&0o111 or st.st_mode&0o022:raise RuntimeError("observer executable mode")
    document["preflight"]["observer_tool"]={"requested":life.UDEV,"canonical":str(resolved),"identity":native(st),"sha256":fact["sha256"],"bytes":fact["bytes"],"package":owner["package"],"version":owner["version"],"architecture":owner["architecture"]}

def cleanup_mounts(document,mounted,underlying,saved_mounts,namespace,created,observer):
    for part,mount in reversed(mounted):
        try:
            view=setup.mountinfo()
            if setup.mount_namespace()!=namespace:raise RuntimeError("cleanup namespace identity")
            if setup.exact_mount(view,mount) is None:
                after=os.lstat(mount)
                if [after.st_dev,after.st_ino]!=underlying[mount]:raise RuntimeError("cleanup already-unmounted identity")
                continue
            current=setup.validate_mount_entry(view,mount,part)
            if mount in saved_mounts:
                if current!=saved_mounts[mount]:raise RuntimeError("cleanup mount identity")
            else:
                # The owned mount command succeeded but its first receipt failed.
                # This exact source/namespace/mount validation is cleanup-only discovery;
                # it never resets the NVMe baseline or resumes setup.
                saved_mounts[mount]=current
            run_tool(document,["/usr/bin/umount","--",mount],timeout=15,observer=observer,observer_fatal=False)
            if setup.exact_mount(setup.mountinfo(),mount) is not None:raise RuntimeError("cleanup unmount proof")
            after=os.lstat(mount)
            if [after.st_dev,after.st_ino]!=underlying[mount]:raise RuntimeError("cleanup underlying mountpoint")
            document["cleanup"]["unmounts"].append({"mount":mount,"normal_guarded":True})
        except BaseException as exc:document["cleanup"]["errors"].append(life.error(exc))
    for path in reversed(created):
        try:os.rmdir(path)
        except BaseException as exc:document["cleanup"]["directories_removed"]=False;document["cleanup"]["errors"].append(life.error(exc))

def emit(document):
    try:wires=life.frames(document)
    except BaseException as diagnostic:
        document["stop"]["diagnostic_error"]=life.error(diagnostic)
        try:prefix=life.canonical(document)
        except BaseException:prefix=b""
        wires=life.prefix_frames(prefix,document["stop"]["primary_error"],life.error(diagnostic),nonce=document["nonce"],binding=document["binding"],manifest_sha256=document["manifest_sha256"])
    fd=os.open(setup.SERIAL,os.O_WRONLY|os.O_NOCTTY|os.O_CLOEXEC)
    try:
        for raw in wires:
            offset=0
            while offset<len(raw):offset+=os.write(fd,raw[offset:])
    finally:os.close(fd)

def main():
    if os.getuid()!=0 or os.getgid()!=0:raise RuntimeError("setup observation root identity")
    manifest,manifest_sha=verify_seed();raw,_=setup.stable_file(Path("/var/lib/dm-g0-private/config.json"),8192,mode=0o400);config=g0.validate_config(g0.loads_strict(raw));binding,_=setup.dmi_binding()
    mode_raw,_=setup.stable_file(Path("/var/lib/dm-g0-private/setup-lifecycle-config.json"),4096,mode=0o400);life.validate_mode_config(g0.loads_strict(mode_raw),config["nonce"])
    document=life.new_document(nonce=config["nonce"],binding=binding,manifest_sha256=manifest_sha);observer=None;mounted=[];created=[];underlying={};saved_mounts={};namespace=None;primary=None;baseline=None
    try:
        mark(document,"preflight","before");document["preflight"]["tools"]=tool_facts(document,config["deadlines"])
        observer_preflight(document,config["deadlines"])
        initial=setup.nvme_preflight(config["nvme_serial"]);namespace=setup.mount_namespace();initial_mount=setup.mountinfo()
        if any(setup.exact_mount(initial_mount,path) is not None for path in config["mounts"]):raise RuntimeError("G0 preexisting mount")
        setup.reject_selected_nvme_mount(initial_mount,initial);original_record(document,"pre-partition",{"nvme":initial,"namespace":namespace});mark(document,"preflight","after")
        observer=Observer(document,initial["namespace_path"]);mark(document,"observer-ready","observed")
        device=initial["device"];table=("label: gpt\nunit: sectors\n\n"+f"{device}p1 : start=2048, size=122880, type={setup.GUID}\n"+f"{device}p2 : start=124928, size=131072, type={setup.GUID}\n").encode()
        mark(document,"partition-write","before");document["stop"]["mutation_started"]=True
        run_tool(document,["/usr/sbin/sfdisk",device],stdin=table,timeout=config["deadlines"]["sfdisk"],observer=observer);mark(document,"partition-write","after")
        appearance(initial["namespace"],10,observer,lambda facts:original_record(document,"appearance-p"+str(facts["number"]),facts))
        baseline=capture_baseline(document,namespace,config["nvme_serial"],observer)
        phase="table-dump";snapshot(document,phase+"-before",baseline,namespace,config["nvme_serial"],observer);mark(document,phase,"before")
        result=run_tool(document,["/usr/sbin/sfdisk","--json",device],timeout=config["deadlines"]["sfdisk"],observer=observer)
        setup.validate_partition_table(result["stdout_text"].encode(),device);mark(document,phase,"after");snapshot(document,phase+"-after",baseline,namespace,config["nvme_serial"],observer)
        for part in baseline["partitions"]:
            phase="format-p"+str(part["number"]);snapshot(document,phase+"-before",baseline,namespace,config["nvme_serial"],observer);mark(document,phase,"before")
            run_tool(document,["/usr/sbin/mkfs.ext4","-F","-m","0","-E","lazy_itable_init=0,lazy_journal_init=0",part["path"]],timeout=config["deadlines"]["mkfs_ext4"],observer=observer)
            mark(document,phase,"after");snapshot(document,phase+"-after",baseline,namespace,config["nvme_serial"],observer)
        root=Path("/mnt/dm-g0")
        if root.exists() or root.is_symlink():raise RuntimeError("G0 mount root preexists")
        root.mkdir(mode=0o755);created.append(root);st=os.lstat(root)
        if not stat.S_ISDIR(st.st_mode) or st.st_uid!=0 or st.st_gid!=0 or stat.S_IMODE(st.st_mode)!=0o755:raise RuntimeError("mount root metadata")
        for part,mount in zip(baseline["partitions"],config["mounts"]):
            phase="mount-p"+str(part["number"]);path=Path(mount);path.mkdir(mode=0o755);created.append(path);before=os.lstat(path)
            if not stat.S_ISDIR(before.st_mode) or before.st_uid!=0 or before.st_gid!=0 or stat.S_IMODE(before.st_mode)!=0o755:raise RuntimeError("mountpoint metadata")
            underlying[mount]=[before.st_dev,before.st_ino];snapshot(document,phase+"-before",baseline,namespace,config["nvme_serial"],observer);mark(document,phase,"before")
            try:
                run_tool(document,["/usr/bin/mount","-t","ext4","-o","rw,nodev,nosuid","--",part["path"],mount],timeout=config["deadlines"]["mount"],observer=observer)
                mounted.append((part,mount))
                saved_mounts[mount]=setup.validate_mount_entry(setup.mountinfo(),mount,part)
            except BaseException as original:
                if not any(saved_mount==mount for _,saved_mount in mounted):
                    try:
                        view=setup.mountinfo()
                        if setup.exact_mount(view,mount) is not None:saved_mounts[mount]=setup.validate_mount_entry(view,mount,part);mounted.append((part,mount))
                    except BaseException as discovery:
                        original.add_note("mount effect discovery: "+type(discovery).__name__)
                        document["cleanup"]["errors"].append(life.error(discovery))
                raise
            mark(document,phase,"after");snapshot(document,phase+"-after",baseline,namespace,config["nvme_serial"],observer)
        document["stop"].update(status="end_of_setup_no_transition",phase="mount-p2-after")
    except BaseException as exc:
        primary=exc;document["stop"].update(status="transition_observed" if isinstance(exc,Transition) else "preflight_stop" if not document["stop"]["mutation_started"] else "failed",phase=document["stop"]["phase"],primary_error=life.error(exc))
    finally:
        cleanup_mounts(document,mounted,underlying,saved_mounts,namespace,created,observer)
        if observer:
            try:observer.close()
            except BaseException as exc:document["cleanup"]["errors"].append(life.error(exc))
        if document["cleanup"]["errors"]:document["stop"]["status"]="incomplete"
        try:emit(document)
        except BaseException as exc:
            if primary is not None:primary.add_note("setup observation export: "+type(exc).__name__)
            else:primary=exc
    if primary:raise primary

if __name__=="__main__":main()
