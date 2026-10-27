"""One generated E1 case. Product/native code runs only inside the authorized guest."""
from __future__ import annotations
import base64, hashlib, importlib, importlib.util, json, os, re, select, signal, socket, stat, struct, sys, threading, time
from pathlib import Path
HERE=Path(__file__).resolve().parent
SOURCE=Path('/opt/dm-g0/source')
def load_helper(name):
    spec=importlib.util.spec_from_file_location('dm_e1_'+name,HERE/(name+'.py'))
    if spec is None or spec.loader is None:raise RuntimeError('E1 helper loader')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
policy=load_helper('e1_policy');ordinary=load_helper('guest_g0_qualify')
CASE_MAX=65536; IPC_MAX=32768; FILL_MAX=64*1024*1024

def ident(st):return [st.st_dev,st.st_ino,st.st_mode,st.st_uid,st.st_gid,st.st_nlink,st.st_size]
def error(exc):return (type(exc).__name__+': '+str(exc)).encode('utf-8','replace')[:256].decode('utf-8','ignore')
def bounded_file(path,cap,*,root=False):
    before=os.lstat(path);fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        opened=os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink!=1 or (root and (opened.st_uid!=0 or opened.st_gid!=0 or opened.st_mode&0o022)) or ident(before)!=ident(opened):raise RuntimeError('E1 file metadata')
        data=bytearray()
        while True:
            block=os.read(fd,min(65536,cap+1-len(data)))
            if not block:break
            data.extend(block)
            if len(data)>cap:raise RuntimeError('E1 file cap')
        if ident(opened)!=ident(os.fstat(fd)) or ident(opened)!=ident(os.lstat(path)):raise RuntimeError('E1 file changed')
        return bytes(data),ident(opened)
    finally:os.close(fd)

def blob(raw,identity=None):
    return {'bytes':len(raw),'sha256':policy.sha256(raw),'raw_base64':base64.b64encode(raw).decode(),'identity':identity}
def source_pins():
    for entry in policy.product_entries():
        raw,_=bounded_file(Path(entry['path']),1024*1024,root=True)
        if len(raw)!=entry['bytes'] or policy.sha256(raw)!=entry['sha256']:raise RuntimeError('E1 product source pin')
    return policy.product_entries()
def proc_start(pid):
    raw=Path('/proc/'+str(pid)+'/stat').read_bytes()
    if len(raw)>4096:raise RuntimeError('E1 process stat cap')
    return int(raw[raw.rfind(b')')+2:].split()[19])
def remaining(deadline):
    value=deadline-time.monotonic()
    if value<=0:raise TimeoutError('E1 remaining deadline')
    return value

def send_message(sock,value,deadline):
    data=policy.canonical(value)
    if len(data)>IPC_MAX:raise RuntimeError('E1 IPC cap')
    sock.settimeout(remaining(deadline));sock.sendall(struct.pack('!I',len(data))+data)
def receive_message(sock,deadline):
    def read(n):
        data=bytearray()
        while len(data)<n:
            sock.settimeout(remaining(deadline));block=sock.recv(n-len(data))
            if not block:raise EOFError('E1 IPC EOF')
            data.extend(block)
        return bytes(data)
    size=struct.unpack('!I',read(4))[0]
    if not 0<size<=IPC_MAX:raise RuntimeError('E1 IPC length')
    return policy.loads_strict(read(size))
def descriptor_fact(fd,buffer):
    import fcntl
    st=os.fstat(fd);raw=Path('/proc/self/fdinfo/'+str(fd)).read_bytes()
    if len(raw)>4096:raise RuntimeError('E1 fdinfo cap')
    match=re.findall(rb'(?m)^mnt_id:\s*([0-9]+)$',raw)
    if len(match)!=1:raise RuntimeError('E1 mnt_id')
    return {'fd':fd,'identity':ident(st),'flags':fcntl.fcntl(fd,fcntl.F_GETFL),'mnt_id':int(match[0]),'path':os.readlink('/proc/self/fd/'+str(fd)),
            'buffer_bytes':len(buffer),'buffer_sha256':policy.sha256(bytes(buffer)),'builtin_write':os.write.__module__=='posix' and os.write.__name__=='write','builtin_fsync':os.fsync.__module__=='posix' and os.fsync.__name__=='fsync'}

def send_observation_now(sock,value):
    data=policy.canonical(value)
    if len(data)>8192:raise RuntimeError('E1 observation cap')
    packet=struct.pack('!I',len(data))+data
    sock.setblocking(False)
    if sock.send(packet)!=len(packet):raise RuntimeError('E1 partial observation send')

def worker_entry(operation,arguments,send,cancel):
    """Spawn entry adapter: the original receives the original four objects once."""
    source_pins();sys.path.insert(0,str(SOURCE))
    recovery=importlib.import_module('defiantmaple.recovery');original=recovery._worker_main;backup=recovery._backup_worker
    source_raw,_=bounded_file(SOURCE/'defiantmaple/recovery.py',1024*1024,root=True)
    source_lines=source_raw.splitlines(keepends=True)
    if original.__code__.co_filename!=str(SOURCE/'defiantmaple/recovery.py') or original.__code__.co_firstlineno!=484:raise RuntimeError('E1 original worker code identity')
    sock=None;gate=False;fault=False;trace_error=None
    deadline=float(os.environ['DM_E1_CASE_DEADLINE']);phase_deadline=None
    def trace(frame,event,arg):
        nonlocal gate,fault,phase_deadline,trace_error
        if frame.f_code is not backup.__code__:return None
        try:
            if frame.f_code.co_filename!=str(SOURCE/'defiantmaple/recovery.py') or frame.f_code.co_firstlineno!=316:raise RuntimeError('E1 original code origin')
            if event=='line' and frame.f_lineno==395 and not gate:
                gate=True;phase_deadline=min(time.monotonic()+30,deadline)
                send_message(sock,{'kind':'gate','nonce':os.environ['DM_E1_NONCE'],'pid':os.getpid(),'start':proc_start(os.getpid()),'ppid':os.getppid(),
                    'operation':operation,'arguments_sha256':policy.sha256(policy.canonical([str(x) if isinstance(x,Path) else list(map(str,x)) if isinstance(x,tuple) else x for x in arguments])),
                    'manifest_base64':base64.b64encode(frame.f_locals['raw']).decode(),'snapshot_bytes':frame.f_locals['length'],'line':395,'source_sha256':next(e['sha256'] for e in policy.PRODUCT_ENTRIES if e['path'].endswith('/recovery.py')),
                    'stage':descriptor_fact(frame.f_locals['package_fd'],frame.f_locals['view']),'phase_deadline':phase_deadline,'adapter_calls':1},phase_deadline)
                reply=receive_message(sock,phase_deadline)
                if reply!={'kind':'resume','nonce':os.environ['DM_E1_NONCE']}:raise RuntimeError('E1 gate release')
            elif event=='exception' and frame.f_lineno in (395,401,402) and gate and not fault:
                fault=True;exc=arg[1]
                data={'kind':'fault','nonce':os.environ['DM_E1_NONCE'],'line':frame.f_lineno,'source_sha256':next(e['sha256'] for e in policy.PRODUCT_ENTRIES if e['path'].endswith('/recovery.py')),
                      'source_path':frame.f_code.co_filename,'function_firstlineno':frame.f_code.co_firstlineno,'source_line_base64':base64.b64encode(source_lines[frame.f_lineno-1]).decode(),'module':type(exc).__module__,'class':type(exc).__name__,'errno':getattr(exc,'errno',None),'strerror':getattr(exc,'strerror',None),
                      'sqlite_errorcode':getattr(exc,'sqlite_errorcode',None),'sqlite_errorname':getattr(exc,'sqlite_errorname',None),'stage':descriptor_fact(frame.f_locals['package_fd'],frame.f_locals.get('view',b'')),'adapter_calls':1}
                send_observation_now(sock,data)
        except BaseException as exc:
            trace_error=error(exc)
            try:cancel.set()
            except BaseException:pass
        return trace
    try:
        sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);sock.settimeout(remaining(deadline));sock.connect(os.environ['DM_E1_SOCKET'])
        if sys.gettrace() is not None:raise RuntimeError('E1 preexisting worker trace')
        sys.settrace(trace)
    except BaseException as exc:
        trace_error=error(exc);cancel.set()
    primary=None;cleanup_errors=[]
    try:
        return original(operation,arguments,send,cancel)
    except BaseException as original_error:
        primary=original_error
        raise
    finally:
        try:sys.settrace(None)
        except BaseException as cleanup:cleanup_errors.append(error(cleanup))
        if sock is not None:
            try:send_observation_now(sock,{'kind':'done','nonce':os.environ['DM_E1_NONCE'],'gate':gate,'fault':fault,'trace_error':trace_error or (';'.join(cleanup_errors) if cleanup_errors else None),'adapter_calls':1})
            except BaseException as cleanup:cleanup_errors.append(error(cleanup))
            try:sock.close()
            except BaseException as cleanup:cleanup_errors.append(error(cleanup))
        if cleanup_errors:
            if primary is not None:primary.add_note('E1 adapter cleanup: '+';'.join(cleanup_errors))
            else:raise RuntimeError('E1 adapter cleanup INCONCLUSIVE: '+';'.join(cleanup_errors))

def verify_original_gate(gate,expected_args,expected_header,expected_stage_path,expected_device,expected_mount_id):
    stage=gate['stage'];policy.stage_fact(stage)
    if (gate['kind']!='gate' or gate['operation']!='backup' or gate['line']!=395 or gate['source_sha256']!=policy.RECOVERY_SHA or type(gate['adapter_calls']) is not int or gate['adapter_calls']!=1
            or gate['arguments_sha256']!=policy.sha256(policy.canonical(expected_args)) or stage['path']!=str(expected_stage_path) or stage['identity'][0]!=expected_device
            or stage['identity'][6]!=0 or stage['buffer_bytes']!=20 or len(expected_header)!=20 or stage['buffer_sha256']!=policy.sha256(expected_header) or stage['mnt_id']!=expected_mount_id):
        raise RuntimeError('E1 exact original arguments/header/mount binding')

def statvfs_fact(path):
    st=os.statvfs(path);return {'bavail':st.f_bavail,'bfree':st.f_bfree,'favail':st.f_favail,'frsize':st.f_frsize}
class Pressure:
    def __init__(self,path):self.path=path;self.fd=None;self.parent=None;self.identity=None;self.fact=None
    def fill(self,deadline):
        self.parent=os.open(self.path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
        try:self.fd=os.open(self.path.name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=self.parent)
        except BaseException as primary:
            try:self.close()
            except BaseException as cleanup:primary.add_note('E1 filler acquisition cleanup: '+error(cleanup))
            raise
        initial=os.fstat(self.fd);self.identity=ident(initial)[:6]
        if not stat.S_ISREG(initial.st_mode) or initial.st_uid!=12345 or initial.st_gid!=12345 or stat.S_IMODE(initial.st_mode)!=0o600 or initial.st_nlink!=1:raise RuntimeError('E1 filler metadata')
        written=0;errno=None;flush_errno=None;next_flush=1024*1024;block=b'F'*65536
        try:
            while written<FILL_MAX:
                remaining(deadline);count=os.write(self.fd,block[:min(len(block),FILL_MAX-written)])
                if count<=0:raise RuntimeError('E1 filler no progress')
                written+=count
                if written>=next_flush:
                    os.fsync(self.fd);next_flush=(written//(1024*1024)+1)*1024*1024
        except OSError as exc:
            errno=exc.errno
            if errno!=28:raise
        # A final flush is attempted even when write itself reported ENOSPC.
        remaining(deadline)
        try:os.fsync(self.fd)
        except OSError as exc:
            flush_errno=exc.errno
            if flush_errno!=28:raise
            if errno is None:errno=flush_errno
        info=os.fstat(self.fd);space=statvfs_fact(self.path.parent)
        self.fact={'written':written,'allocated':info.st_blocks*512,'identity':ident(info),'space':space,'errno':errno,'final_flush_errno':flush_errno}
        if errno!=28 or space['bavail']!=0 or space['favail']<=0:raise RuntimeError('E1 pressure not established within bound')
        return self.fact
    def remove(self):
        if self.fd is None:return False
        opened=os.fstat(self.fd);named=os.stat(self.path.name,dir_fd=self.parent,follow_symlinks=False)
        if ident(opened)[:6]!=self.identity or ident(named)[:6]!=self.identity:raise RuntimeError('E1 filler unlink identity')
        os.unlink(self.path.name,dir_fd=self.parent)
        if os.fstat(self.fd).st_nlink!=0:raise RuntimeError('E1 filler held unlink')
        try:os.stat(self.path.name,dir_fd=self.parent,follow_symlinks=False)
        except FileNotFoundError:pass
        else:raise RuntimeError('E1 filler name remains')
        self.close();return True
    def close(self):
        failures=[]
        for name in ('fd','parent'):
            fd=getattr(self,name);setattr(self,name,None)
            if fd is not None:
                try:os.close(fd)
                except BaseException as exc:failures.append(error(exc))
        if failures:raise RuntimeError(';'.join(failures))

def ledger(managed,version):
    raw,identity=bounded_file(managed/'schedule.json',8192)
    if version is not None and (list(version.identity)!=identity[:2] or version.sha256!=policy.sha256(raw)):raise RuntimeError('E1 original Version/ledger mismatch')
    value=policy.loads_strict(raw)
    if value.get('schema')!='defiantmaple.schedule-state.v1':raise RuntimeError('E1 ledger schema')
    return {**blob(raw,identity),'version':None if version is None else {'identity':list(version.identity),'sha256':version.sha256}}
def catalog_fact(path,sqlite):
    raw,identity=bounded_file(path,1024*1024)
    db=sqlite.connect(path.as_uri()+'?mode=ro',uri=True)
    try:
        schema=db.execute('PRAGMA user_version').fetchone()[0];library=db.execute('SELECT library_id FROM library_identity WHERE singleton=1').fetchone()[0]
        rows={name:db.execute('SELECT COUNT(*) FROM '+name).fetchone()[0] for name in ('assets','sources','source_entries','provenance')}
    finally:db.close()
    sidecars=[]
    for suffix in ('-wal','-shm','-journal'):
        try:data,st=bounded_file(Path(str(path)+suffix),1024*1024)
        except FileNotFoundError:sidecars.append({'suffix':suffix,'absent':True});continue
        sidecars.append({'suffix':suffix,'absent':False,'identity':st,'bytes':len(data),'sha256':policy.sha256(data)})
    return {'identity':identity,'sha256':policy.sha256(raw),'schema':schema,'library_id':library,'rows':rows,'sidecars':sidecars}
def fixture_identity(path):
    st=os.lstat(path)
    if not stat.S_ISDIR(st.st_mode) or st.st_uid!=12345 or st.st_gid!=12345 or stat.S_IMODE(st.st_mode)!=0o700:raise RuntimeError('E1 fixture parent')
    return [st.st_dev,st.st_ino,st.st_uid,st.st_gid,stat.S_IMODE(st.st_mode),st.st_nlink]
def remove_generated(path,expected_dev):
    count=[0];parent=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    def remove_at(parent_fd,name,depth):
        count[0]+=1
        if depth>6 or count[0]>128:raise RuntimeError('E1 generated cleanup bound')
        before=os.stat(name,dir_fd=parent_fd,follow_symlinks=False)
        if before.st_dev!=expected_dev or before.st_uid!=12345 or before.st_gid!=12345 or stat.S_ISLNK(before.st_mode):raise RuntimeError('E1 generated cleanup metadata')
        directory=stat.S_ISDIR(before.st_mode)
        if not directory and (not stat.S_ISREG(before.st_mode) or before.st_nlink!=1):raise RuntimeError('E1 generated cleanup type')
        flags=os.O_RDONLY|os.O_DIRECTORY if directory else os.O_PATH
        fd=os.open(name,flags|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent_fd)
        try:
            # Directory link count changes when its owned child directories are removed.
            width=5 if directory else 7
            if ident(os.fstat(fd))[:width]!=ident(before)[:width]:raise RuntimeError('E1 generated opened identity')
            if directory:
                names=os.listdir(fd)
                if len(names)>64:raise RuntimeError('E1 generated child bound')
                for child in names:remove_at(fd,child,depth+1)
            named=os.stat(name,dir_fd=parent_fd,follow_symlinks=False)
            if ident(os.fstat(fd))[:width]!=ident(before)[:width] or ident(named)[:width]!=ident(before)[:width]:raise RuntimeError('E1 generated unlink identity')
            if directory:os.rmdir(name,dir_fd=parent_fd)
            else:os.unlink(name,dir_fd=parent_fd)
            if os.fstat(fd).st_nlink!=0:raise RuntimeError('E1 generated held unlink proof')
        finally:os.close(fd)
    try:remove_at(parent,path.name,0)
    finally:os.close(parent)

def unlink_owned_socket(path,expected):
    parent=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC);held=None
    try:
        named=os.stat(path.name,dir_fd=parent,follow_symlinks=False)
        if ident(named)!=expected or not stat.S_ISSOCK(named.st_mode) or named.st_uid!=12345 or named.st_gid!=12345:raise RuntimeError('E1 IPC socket replacement')
        held=os.open(path.name,os.O_PATH|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
        if ident(os.fstat(held))!=expected or ident(os.stat(path.name,dir_fd=parent,follow_symlinks=False))!=expected:raise RuntimeError('E1 held IPC socket replacement')
        os.unlink(path.name,dir_fd=parent)
        if os.fstat(held).st_nlink!=0:raise RuntimeError('E1 held IPC socket unlink')
    finally:
        if held is not None:os.close(held)
        os.close(parent)

def rejected_origin_message(name,path):
    # Both values were already observed by the unchanged origin guard.
    prefix='E1 external standard-library import origin'
    origin=str(path)
    if len(name)<=256 and len(origin)<=256:
        message=prefix+' module='+repr(name)+' origin='+repr(origin)
        if len(('RuntimeError: '+message).encode('utf-8','replace'))<=256:return message
    # Never present a truncated module/path as the complete diagnostic.
    return prefix+' diagnostic_overflow module_chars='+str(len(name))+' origin_chars='+str(len(origin))

def runtime_preflight(result_fd):
    pins=source_pins();before=ordinary.ordinary_identity();fds=ordinary.fd_inventory(result_fd)
    sys.path.insert(0,str(SOURCE))
    modules=[importlib.import_module('defiantmaple.'+Path(e['path']).stem) for e in pins if not e['path'].endswith('/__init__.py')]
    sqlite=importlib.import_module('sqlite3');importlib.import_module('ctypes');importlib.import_module('multiprocessing')
    native=[]
    for name in ('_sqlite3','_ctypes'):
        module=importlib.import_module(name);path=Path(module.__file__).resolve(strict=True);data,identity=bounded_file(path,64*1024*1024,root=True)
        if not str(path).startswith('/usr/lib/') or not path.name.endswith('.so'):raise RuntimeError('E1 native origin')
        native.append({'name':name,'path':str(path),'identity':identity,'bytes':len(data),'sha256':policy.sha256(data)})
    loaded=[];stdlib_origins=[]
    for name,module in sorted(sys.modules.items()):
        if name=='defiantmaple' or name.startswith('defiantmaple.'):
            path=Path(module.__file__).resolve(strict=True)
            if str(path) not in {e['path'] for e in pins}:raise RuntimeError('E1 external product dependency')
            loaded.append(str(path))
        elif getattr(module,'__file__',None) is not None:
            path=Path(module.__file__).resolve(strict=True)
            if str(path).startswith('/usr/lib/python3.12/'):
                stdlib_origins.append([name,str(path)])
                if len(stdlib_origins)>256:raise RuntimeError('E1 stdlib origin count')
            elif path not in (Path(__file__).resolve(strict=True),HERE/'e1_policy.py',HERE/'guest_g0_qualify.py'):
                raise RuntimeError(rejected_origin_message(name,path))
    interp=Path('/usr/bin/python3.12');data,identity=bounded_file(interp,64*1024*1024,root=True)
    return sqlite,{'source_pins':pins,'loaded_product':loaded,'interpreter':{'path':str(interp),'identity':identity,'bytes':len(data),'sha256':policy.sha256(data)},'native':native,'sqlite_version':sqlite.sqlite_version,'stdlib_origins':{'checked':True,'count':len(stdlib_origins),'sha256':policy.sha256(policy.canonical(stdlib_origins))},'ordinary':before,'fd_before':fds}

def stop_tracker(deadline):
    # Only the standard-library tracker created by this original spawn, after product ownership closes.
    module=importlib.import_module('multiprocessing.resource_tracker');tracker=module._resource_tracker
    pid,fd=tracker._pid,tracker._fd
    if pid is None and fd is None:return {'present':False,'reaped':True}
    if type(pid) is not int or type(fd) is not int or pid<=0:raise RuntimeError('E1 tracker shape')
    start=proc_start(pid);pidfd=os.pidfd_open(pid,0)
    try:
        os.close(fd);tracker._fd=None
        ready=select.select([pidfd],[],[],remaining(deadline))[0]
        if not ready:raise TimeoutError('E1 tracker EOF reap')
        waited,status=os.waitpid(pid,os.WNOHANG)
        if waited!=pid or not os.WIFEXITED(status) or os.WEXITSTATUS(status)!=0:raise RuntimeError('E1 tracker exit')
        tracker._pid=None
        return {'present':True,'pid':pid,'start':start,'status':status,'reaped':True}
    finally:os.close(pidfd)

def run_case(result_fd,nonce,binding,manifest_sha,p1,p2,p2_mount_id,deadline):
    started_at=time.monotonic();remaining(deadline);os.environ['DM_E1_CASE_DEADLINE']=str(deadline);os.environ['DM_E1_NONCE']=nonce
    records=[];errors=[];result=None;actor=None;pressure=None;listener=None;thread=None;owner_context=None;original_entry=None;recovery=None;socket_path=None;socket_identity=None
    captured={};worker_messages=[];pending_error=None;start_event=threading.Event();fixture_before=[fixture_identity(p1),fixture_identity(p2)];outcome='INCONCLUSIVE'
    def record(phase,data):
        value={'schema':'dm-e1-case-v1','case':'original-package-stage-enospc','nonce':nonce,'binding':binding,'seed_manifest_sha256':manifest_sha,'ordinal':len(records),'phase':phase,'data':data}
        wire=policy.build_frame(policy.CASE_PREFIX,value,policy.CASE_CAPS[len(records)])
        if sum(len(x) for x in records)+len(wire)>CASE_MAX:raise RuntimeError('E1 records aggregate cap')
        records.append(wire)
    try:
        sqlite,preflight=runtime_preflight(result_fd)
        root1=p1/'case';root2=p2/'case';root1.mkdir(mode=0o700);root2.mkdir(mode=0o700)
        for name in ('catalog','profile','registry-parent','cache'):(root1/name).mkdir(mode=0o700)
        database=root1/'catalog'/'empty.sqlite3';managed=root2/'managed'
        catalog=importlib.import_module('defiantmaple.catalog');admission=importlib.import_module('defiantmaple.admission')
        configurations=importlib.import_module('defiantmaple.snapshot_configuration');controlled=importlib.import_module('defiantmaple.controlled_configuration')
        schedules=importlib.import_module('defiantmaple.scheduled_snapshots');operations=importlib.import_module('defiantmaple.snapshot_operations');recovery=importlib.import_module('defiantmaple.recovery')
        catalog.initialize(database);source_before=catalog_fact(database,sqlite);preflight['source_before']=source_before;preflight['fixtures']=fixture_before
        if source_before['schema']!=7 or any(source_before['rows'].values()):raise RuntimeError('E1 nonempty source fixture')
        record('preflight',preflight)
        owner_context=admission.admission_session(database,_registry_path=root1/'registry-parent'/'admission-v1');owner=owner_context.__enter__()
        config=configurations.SnapshotConfiguration(owner,root1/'profile',cache_roots=(root1/'cache',),locator_profile='custom')
        enable=controlled.ControlledEnableOperation(config,controlled.EnableRequest.capture(None,None))
        try:enable.run(schedules.Policy(enabled=True,retention_enabled=False,keep_count=1),managed_directory=managed)
        finally:
            if not enable.finish_thread():raise RuntimeError('E1 enable cleanup incomplete')
        actor=operations.SnapshotOperations(config);pressure=Pressure(root2/'filler.raw')
        socket_path=root1/'gate.sock';listener=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM);listener.bind(str(socket_path));socket_identity=ident(os.lstat(socket_path));listener.listen(1);os.environ['DM_E1_SOCKET']=str(socket_path)
        def trace(frame,event,arg):
            if frame.f_code is not operations.SnapshotOperations._save.__code__:return None
            try:
                incoming=frame.f_locals['state'];self=frame.f_locals['self']
                if incoming.audit and incoming.audit[-1].event=='attempt_started':
                    if event=='call':captured['initial']=ledger(managed,self.version)
                    elif event=='return':
                        if arg is not None or self.state!=incoming:raise RuntimeError('E1 completed original _save state')
                        captured['started']=ledger(managed,self.version);captured['operation_id']=incoming.audit[-1].operation_id;start_event.set()
            except BaseException as exc:errors.append(error(exc));actor.request_cancel();start_event.set()
            return trace
        def fill_at_gate():
            conn=None
            try:
                listener.settimeout(remaining(deadline));conn,_=listener.accept();gate=receive_message(conn,deadline)
                creds=struct.unpack('3i',conn.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
                if gate.get('kind')!='gate' or gate.get('nonce')!=nonce or creds!=(gate.get('pid'),12345,12345) or gate.get('ppid')!=os.getpid() or gate.get('start')!=proc_start(gate['pid']):raise RuntimeError('E1 gate peer binding')
                if not start_event.wait(remaining(deadline)) or 'started' not in captured:raise RuntimeError('E1 durable attempt_started unavailable')
                owned=[r for r in actor.records if r['operation']=='backup' and r['pid']==gate['pid']]
                if len(owned)!=1 or gate['stage']['identity'][0]!=fixture_before[1][0] or gate['stage']['identity'][6]!=0 or gate['line']!=395 or not all(gate['stage'][k] is True for k in ('builtin_write','builtin_fsync')):raise RuntimeError('E1 original owned stage gate')
                stage=gate['stage'];expected=owned[0]['stages'][1]
                if stage['path']!=str(expected) or gate['adapter_calls']!=1 or not stat.S_ISREG(stage['identity'][2]) or stage['identity'][3:6]!=[12345,12345,1]:raise RuntimeError('E1 stage identity')
                snapshot,stage_path=owned[0]['stages']
                started_doc=policy.loads_strict(base64.b64decode(captured['started']['raw_base64']))
                schedule=started_doc['locator']['schedule_id'];sequence=started_doc['next_sequence']-1
                package=managed/('snapshot-'+schedule+'-'+str(sequence)+'-'+captured['operation_id']+'.dmbackup')
                expected_args=[str(database),str(package),str(snapshot),str(stage_path),[str(root1/'cache')],120]
                manifest_raw=base64.b64decode(gate['manifest_base64'],validate=True)
                manifest=policy.loads_strict(manifest_raw)
                expected_header=recovery.HEADER.pack(recovery.MAGIC,len(manifest_raw),gate['snapshot_bytes'])
                snapshot_st=os.lstat(snapshot)
                if (gate['arguments_sha256']!=policy.sha256(policy.canonical(expected_args)) or len(manifest_raw)>4096 or manifest.get('library_id')!=source_before['library_id'] or manifest.get('catalog_schema')!=7
                        or manifest.get('snapshot_bytes')!=gate['snapshot_bytes'] or snapshot_st.st_size!=gate['snapshot_bytes'] or snapshot_st.st_dev!=fixture_before[1][0]
                        ):raise RuntimeError('E1 original manifest/snapshot binding')
                verify_original_gate(gate,expected_args,expected_header,expected,fixture_before[1][0],p2_mount_id)
                phase_deadline=min(gate['phase_deadline'],deadline,time.monotonic()+30)
                fill=pressure.fill(phase_deadline);captured['gate']=gate;captured['filler']=fill
                record('start',{'initial':captured['initial'],'started':captured['started'],'operation_id':captured['operation_id'],'worker':gate,'filler':fill,'ordering':['durable_attempt_started','original_stage_gate','pressure_established','resume_once']})
                send_message(conn,{'kind':'resume','nonce':nonce},phase_deadline)
                while True:
                    message=receive_message(conn,deadline);worker_messages.append(message)
                    if message.get('kind')=='done':break
            except BaseException as exc:
                errors.append(error(exc));actor.request_cancel()
                if conn is not None:
                    try:send_message(conn,{'kind':'resume','nonce':nonce},deadline)
                    except BaseException:pass
            finally:
                if conn is not None:conn.close()
        thread=threading.Thread(target=fill_at_gate,name='E1-owned-pressure',daemon=True);thread.start()
        original_entry=recovery._worker_main;recovery._worker_main=worker_entry
        if sys.gettrace() is not None:raise RuntimeError('E1 preexisting coordinator trace')
        sys.settrace(trace)
        try:result=actor.backup()
        finally:sys.settrace(None);recovery._worker_main=original_entry;original_entry=None
        thread.join(remaining(deadline))
        if thread.is_alive():raise RuntimeError('E1 pressure thread remains')
        fault=[m for m in worker_messages if m.get('kind')=='fault'];done=[m for m in worker_messages if m.get('kind')=='done']
        if len(records)!=2:raise RuntimeError('E1 missing durable/gate evidence')
        record('fault',{'observed':len(fault)==1,'exception':fault[0] if len(fault)==1 else None,'worker_done':done[0] if len(done)==1 else None,'kernel_trace_observed':False})
        final_ledger=ledger(managed,actor.version);source_after=catalog_fact(database,sqlite)
        packages=sorted(p.name for p in managed.iterdir() if p.suffix=='.dmbackup');stages=[str(p) for r in actor.records for p in r['stages'] if p.exists()]
        state=policy.loads_strict(base64.b64decode(final_ledger['raw_base64']));source_unchanged={k:source_before[k] for k in ('identity','sha256','schema','library_id','rows')}=={k:source_after[k] for k in ('identity','sha256','schema','library_id','rows')}
        real_fault=len(fault)==1 and type(fault[0].get('errno')) is int and fault[0]['errno']==28 and fault[0].get('module')=='builtins' and fault[0].get('class')=='OSError' and fault[0].get('line') in (395,401,402) and fault[0]['stage']['identity'][:6]==captured['gate']['stage']['identity'][:6]
        exits=[{'operation':r['operation'],'pid':r['pid'],'status':r['exit'],'reaped':not r['process'].is_alive(),'cleanup_errors':r['cleanup_errors']} for r in actor.records]
        if result.success_currently_verified or packages or state['packages'] or state['last_success'] is not None:outcome='FAIL'
        elif real_fault and len(done)==1 and done[0]['trace_error'] is None and done[0]['adapter_calls']==1 and not errors and not result.cleanup_pending and not stages and source_unchanged and len(exits)==1 and all(r['reaped'] and r['status']==0 and not r['cleanup_errors'] for r in exits):outcome='PASS'
        removed=pressure.remove()
        owner_context.__exit__(None,None,None);owner_context=None
        for r in actor.records:r['process'].close()
        tracker=stop_tracker(deadline)
        listener.close();listener=None;unlink_owned_socket(socket_path,socket_identity);socket_path=None
        ordinary_after=ordinary.ordinary_identity();fd_after=ordinary.fd_inventory(result_fd)
        record('result',{'outcome':outcome,'product_operation_success':False if not result.success_currently_verified else True,'operation':{'status':result.status,'success_currently_verified':result.success_currently_verified,'cleanup_pending':result.cleanup_pending,'error':result.error},
            'final_ledger':final_ledger,'source_after':source_after,'source_unchanged':source_unchanged,'published_packages':packages,'remaining_stages':stages,'worker_exits':exits,'filler_removed':removed,'thread_joined':True,'tracker':tracker,'ordinary_after':ordinary_after,'fd_after':fd_after,'errors':errors})
    except BaseException as exc:
        errors.append(error(exc));outcome='INCONCLUSIVE';pending_error=error(exc)
    finally:
        sys.settrace(None)
        if recovery is not None and original_entry is not None:recovery._worker_main=original_entry
        if actor is not None and (thread is not None and thread.is_alive()):actor.request_cancel()
        if listener is not None:listener.close()
        if thread is not None and thread.is_alive():thread.join(max(0,deadline-time.monotonic()))
        quiescent=not (thread is not None and thread.is_alive()) and not (actor is not None and actor.active)
        if not quiescent:errors.append('E1 owners not quiescent; fixture cleanup withheld')
        if pressure is not None and quiescent:
            try:
                if pressure.fd is not None:pressure.remove()
            except BaseException as exc:
                errors.append(error(exc))
                try:pressure.close()
                except BaseException as cleanup:errors.append(error(cleanup))
            finally:
                try:pressure.close()
                except BaseException as cleanup:errors.append(error(cleanup))
        if actor is not None and actor.active:
            try:
                actor.request_cancel()
                if not actor.reap_owned_cleanup():errors.append('E1 original owned cleanup remains pending')
            except BaseException as exc:errors.append(error(exc))
        if owner_context is not None and quiescent:
            try:owner_context.__exit__(None,None,None)
            except BaseException as exc:errors.append(error(exc))
        if socket_path is not None:
            try:unlink_owned_socket(socket_path,socket_identity)
            except FileNotFoundError:pass
            except BaseException as exc:errors.append(error(exc))
        if actor is not None and quiescent:
            for owned in actor.records:
                try:owned['process'].close()
                except BaseException as cleanup:errors.append(error(cleanup))
            try:stop_tracker(deadline)
            except BaseException as cleanup:errors.append(error(cleanup))
        # Diagnostics are serialized in memory earlier; persistence/transport cannot delay owned process/filler cleanup.
        if pending_error is not None and len(records)<4:
            try:record(policy.CASE_PHASES[len(records)],{'incomplete':pending_error})
            except BaseException as diagnostic:errors.append(error(diagnostic))
        if quiescent and records:
            try:
                evidence=p1/'evidence';evidence.mkdir(mode=0o700,exist_ok=True)
                for index,wire in enumerate(records):
                    fd=os.open(evidence/(policy.CASE_PHASES[index]+'.raw'),os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
                    try:ordinary.write_all(fd,wire);os.fsync(fd)
                    finally:os.close(fd)
            except BaseException as diagnostic:errors.append(error(diagnostic))
        # Only these freshly created generated subtrees, after all captured facts.
        for fixture in ((p1,p2) if quiescent else ()):
            for name in ('case','evidence'):
                path=fixture/name
                if path.exists():
                    try:remove_generated(path,fixture_before[0 if fixture==p1 else 1][0])
                    except BaseException as exc:errors.append(error(exc))
        if [fixture_identity(p1),fixture_identity(p2)]!=fixture_before:errors.append('E1 fixture parents changed')
    raw=b''.join(records)
    if len(raw)>CASE_MAX:raise RuntimeError('E1 final capture cap')
    try:
        offset=0;os.set_blocking(result_fd,False)
        while offset<len(raw):
            if not select.select([],[result_fd],[],remaining(deadline))[1]:raise TimeoutError('E1 record transport deadline')
            try:count=os.write(result_fd,raw[offset:])
            except BlockingIOError:continue
            if count<=0:raise RuntimeError('E1 record transport no progress')
            offset+=count
    except BaseException as diagnostic:errors.append(error(diagnostic))
    if len(records)!=4 or errors:raise RuntimeError('E1 INCONCLUSIVE: '+';'.join(errors)[:1024])
    return outcome

def main():
    if len(sys.argv)!=9:raise RuntimeError('E1 arguments')
    result_fd=int(sys.argv[1]);os.set_inheritable(result_fd,False);nonce,binding,manifest_sha=sys.argv[2:5]
    run_case(result_fd,nonce,binding,manifest_sha,Path(sys.argv[5]),Path(sys.argv[6]),int(sys.argv[7]),float(sys.argv[8]))
if __name__=='__main__':main()
