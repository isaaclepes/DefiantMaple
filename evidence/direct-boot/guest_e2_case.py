"""One generated E2 case. Product/native code runs only inside the authorized guest."""
from __future__ import annotations
import base64, hashlib, importlib, importlib.util, json, os, re, select, signal, socket, stat, struct, sys, threading, time
from pathlib import Path
HERE=Path(__file__).resolve().parent
SOURCE=Path('/opt/dm-g0/source')
def load_helper(name):
    spec=importlib.util.spec_from_file_location('dm_e2_'+name,HERE/(name+'.py'))
    if spec is None or spec.loader is None:raise RuntimeError('E2 helper loader')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
policy=load_helper('e2_policy');ordinary=load_helper('guest_g0_qualify')
CASE_MAX=65536; IPC_MAX=32768; FILL_MAX=64*1024*1024

def ident(st):return [st.st_dev,st.st_ino,st.st_mode,st.st_uid,st.st_gid,st.st_nlink,st.st_size]
def error(exc):return (type(exc).__name__+': '+str(exc)).encode('utf-8','replace')[:256].decode('utf-8','ignore')
def bounded_file(path,cap,*,root=False):
    before=os.lstat(path);fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        opened=os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink!=1 or (root and (opened.st_uid!=0 or opened.st_gid!=0 or opened.st_mode&0o022)) or ident(before)!=ident(opened):raise RuntimeError('E2 file metadata')
        data=bytearray()
        while True:
            block=os.read(fd,min(65536,cap+1-len(data)))
            if not block:break
            data.extend(block)
            if len(data)>cap:raise RuntimeError('E2 file cap')
        if ident(opened)!=ident(os.fstat(fd)) or ident(opened)!=ident(os.lstat(path)):raise RuntimeError('E2 file changed')
        return bytes(data),ident(opened)
    finally:os.close(fd)

def blob(raw,identity=None):
    return {'bytes':len(raw),'sha256':policy.sha256(raw),'raw_base64':base64.b64encode(raw).decode(),'identity':identity}
def source_pins():
    for entry in policy.product_entries():
        raw,_=bounded_file(Path(entry['path']),1024*1024,root=True)
        if len(raw)!=entry['bytes'] or policy.sha256(raw)!=entry['sha256']:raise RuntimeError('E2 product source pin')
    return policy.product_entries()
def proc_start(pid):
    raw=Path('/proc/'+str(pid)+'/stat').read_bytes()
    if len(raw)>4096:raise RuntimeError('E2 process stat cap')
    return int(raw[raw.rfind(b')')+2:].split()[19])
def remaining(deadline):
    value=deadline-time.monotonic()
    if value<=0:raise TimeoutError('E2 remaining deadline')
    return value

def send_message(sock,value,deadline):
    data=policy.canonical(value)
    if len(data)>IPC_MAX:raise RuntimeError('E2 IPC cap')
    sock.settimeout(remaining(deadline));sock.sendall(struct.pack('!I',len(data))+data)
def receive_message(sock,deadline):
    def read(n):
        data=bytearray()
        while len(data)<n:
            sock.settimeout(remaining(deadline));block=sock.recv(n-len(data))
            if not block:raise EOFError('E2 IPC EOF')
            data.extend(block)
        return bytes(data)
    size=struct.unpack('!I',read(4))[0]
    if not 0<size<=IPC_MAX:raise RuntimeError('E2 IPC length')
    return policy.loads_strict(read(size))
def descriptor_fact(fd,buffer):
    import fcntl
    st=os.fstat(fd);raw=Path('/proc/self/fdinfo/'+str(fd)).read_bytes()
    if len(raw)>4096:raise RuntimeError('E2 fdinfo cap')
    match=re.findall(rb'(?m)^mnt_id:\s*([0-9]+)$',raw)
    if len(match)!=1:raise RuntimeError('E2 mnt_id')
    return {'fd':fd,'identity':ident(st),'flags':fcntl.fcntl(fd,fcntl.F_GETFL),'mnt_id':int(match[0]),'path':os.readlink('/proc/self/fd/'+str(fd)),
            'buffer_bytes':len(buffer),'buffer_sha256':policy.sha256(bytes(buffer)),'builtin_write':os.write.__module__=='posix' and os.write.__name__=='write','builtin_fsync':os.fsync.__module__=='posix' and os.fsync.__name__=='fsync'}

def expected_backup_cache_roots(cache):
    # SnapshotConfiguration, then backup_metadata each retain lexical+resolved.
    roots=(Path(cache),)
    for _ in range(2):
        roots=tuple(item for root in roots for item in (Path(root),Path(root).resolve(strict=False)))
    return [str(root) for root in roots]

def verify_manifest_snapshot_binding(gate,expected_args,manifest_raw,manifest,source_before,snapshot_st,expected_device):
    if (gate['arguments_sha256']!=policy.sha256(policy.canonical(expected_args)) or len(manifest_raw)>4096 or manifest.get('library_id')!=source_before['library_id'] or manifest.get('catalog_schema')!=7
            or manifest.get('snapshot_bytes')!=gate['snapshot_bytes'] or snapshot_st.st_size!=gate['snapshot_bytes'] or snapshot_st.st_dev!=expected_device
            ):raise RuntimeError('E2 original manifest/snapshot binding')

def verify_original_gate(gate,expected_args,expected_header,expected_stage_path,expected_device,expected_mount_id):
    stage=gate['stage'];policy.stage_fact(stage)
    if (gate['kind']!='gate' or gate['operation']!='backup' or gate['line']!=395 or gate['source_sha256']!=policy.RECOVERY_SHA or type(gate['adapter_calls']) is not int or gate['adapter_calls']!=1
            or gate['arguments_sha256']!=policy.sha256(policy.canonical(expected_args)) or stage['path']!=str(expected_stage_path) or stage['identity'][0]!=expected_device
            or stage['identity'][6]!=0 or stage['buffer_bytes']!=20 or len(expected_header)!=20 or stage['buffer_sha256']!=policy.sha256(expected_header) or stage['mnt_id']!=expected_mount_id):
        raise RuntimeError('E2 exact original arguments/header/mount binding')

def statvfs_fact(path):
    st=os.statvfs(path);return {'bavail':st.f_bavail,'bfree':st.f_bfree,'favail':st.f_favail,'frsize':st.f_frsize}
class Pressure:
    def __init__(self,path):self.path=path;self.fd=None;self.parent=None;self.identity=None;self.fact=None
    def fill(self,deadline):
        self.parent=os.open(self.path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
        try:self.fd=os.open(self.path.name,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW|os.O_CLOEXEC,0o600,dir_fd=self.parent)
        except BaseException as primary:
            try:self.close()
            except BaseException as cleanup:primary.add_note('E2 filler acquisition cleanup: '+error(cleanup))
            raise
        initial=os.fstat(self.fd);self.identity=ident(initial)[:6]
        if not stat.S_ISREG(initial.st_mode) or initial.st_uid!=12345 or initial.st_gid!=12345 or stat.S_IMODE(initial.st_mode)!=0o600 or initial.st_nlink!=1:raise RuntimeError('E2 filler metadata')
        written=0;errno=None;flush_errno=None;next_flush=1024*1024;block=b'F'*65536
        try:
            while written<FILL_MAX:
                remaining(deadline);count=os.write(self.fd,block[:min(len(block),FILL_MAX-written)])
                if count<=0:raise RuntimeError('E2 filler no progress')
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
        if errno!=28 or space['bavail']!=0 or space['favail']<=0:raise RuntimeError('E2 pressure not established within bound')
        return self.fact
    def remove(self):
        if self.fd is None:return False
        opened=os.fstat(self.fd);named=os.stat(self.path.name,dir_fd=self.parent,follow_symlinks=False)
        if ident(opened)[:6]!=self.identity or ident(named)[:6]!=self.identity:raise RuntimeError('E2 filler unlink identity')
        os.unlink(self.path.name,dir_fd=self.parent)
        if os.fstat(self.fd).st_nlink!=0:raise RuntimeError('E2 filler held unlink')
        try:os.stat(self.path.name,dir_fd=self.parent,follow_symlinks=False)
        except FileNotFoundError:pass
        else:raise RuntimeError('E2 filler name remains')
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
    if version is not None and (list(version.identity)!=identity[:2] or version.sha256!=policy.sha256(raw)):raise RuntimeError('E2 original Version/ledger mismatch')
    value=policy.loads_strict(raw)
    if value.get('schema')!='defiantmaple.schedule-state.v1':raise RuntimeError('E2 ledger schema')
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
    if not stat.S_ISDIR(st.st_mode) or st.st_uid!=12345 or st.st_gid!=12345 or stat.S_IMODE(st.st_mode)!=0o700:raise RuntimeError('E2 fixture parent')
    return [st.st_dev,st.st_ino,st.st_uid,st.st_gid,stat.S_IMODE(st.st_mode),st.st_nlink]
def remove_generated(path,expected_dev):
    count=[0];parent=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    def remove_at(parent_fd,name,depth):
        count[0]+=1
        if depth>6 or count[0]>128:raise RuntimeError('E2 generated cleanup bound')
        before=os.stat(name,dir_fd=parent_fd,follow_symlinks=False)
        if before.st_dev!=expected_dev or before.st_uid!=12345 or before.st_gid!=12345 or stat.S_ISLNK(before.st_mode):raise RuntimeError('E2 generated cleanup metadata')
        directory=stat.S_ISDIR(before.st_mode)
        if not directory and (not stat.S_ISREG(before.st_mode) or before.st_nlink!=1):raise RuntimeError('E2 generated cleanup type')
        flags=os.O_RDONLY|os.O_DIRECTORY if directory else os.O_PATH
        fd=os.open(name,flags|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent_fd)
        try:
            # Directory link count changes when its owned child directories are removed.
            width=5 if directory else 7
            if ident(os.fstat(fd))[:width]!=ident(before)[:width]:raise RuntimeError('E2 generated opened identity')
            if directory:
                names=os.listdir(fd)
                if len(names)>64:raise RuntimeError('E2 generated child bound')
                for child in names:remove_at(fd,child,depth+1)
            named=os.stat(name,dir_fd=parent_fd,follow_symlinks=False)
            if ident(os.fstat(fd))[:width]!=ident(before)[:width] or ident(named)[:width]!=ident(before)[:width]:raise RuntimeError('E2 generated unlink identity')
            if directory:os.rmdir(name,dir_fd=parent_fd)
            else:os.unlink(name,dir_fd=parent_fd)
            if os.fstat(fd).st_nlink!=0:raise RuntimeError('E2 generated held unlink proof')
        finally:os.close(fd)
    try:remove_at(parent,path.name,0)
    finally:os.close(parent)

def unlink_owned_socket(path,expected):
    parent=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC);held=None
    try:
        named=os.stat(path.name,dir_fd=parent,follow_symlinks=False)
        if ident(named)!=expected or not stat.S_ISSOCK(named.st_mode) or named.st_uid!=12345 or named.st_gid!=12345:raise RuntimeError('E2 IPC socket replacement')
        held=os.open(path.name,os.O_PATH|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
        if ident(os.fstat(held))!=expected or ident(os.stat(path.name,dir_fd=parent,follow_symlinks=False))!=expected:raise RuntimeError('E2 held IPC socket replacement')
        os.unlink(path.name,dir_fd=parent)
        if os.fstat(held).st_nlink!=0:raise RuntimeError('E2 held IPC socket unlink')
    finally:
        if held is not None:os.close(held)
        os.close(parent)

def rejected_origin_message(name,path):
    # Both values were already observed by the unchanged origin guard.
    prefix='E2 external standard-library import origin'
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
        if not str(path).startswith('/usr/lib/') or not path.name.endswith('.so'):raise RuntimeError('E2 native origin')
        native.append({'name':name,'path':str(path),'identity':identity,'bytes':len(data),'sha256':policy.sha256(data)})
    loaded=[];stdlib_origins=[]
    for name,module in sorted(sys.modules.items()):
        if name=='defiantmaple' or name.startswith('defiantmaple.'):
            path=Path(module.__file__).resolve(strict=True)
            if str(path) not in {e['path'] for e in pins}:raise RuntimeError('E2 external product dependency')
            loaded.append(str(path))
        elif getattr(module,'__file__',None) is not None:
            path=Path(module.__file__).resolve(strict=True)
            if str(path).startswith('/usr/lib/python3.12/'):
                stdlib_origins.append([name,str(path)])
                if len(stdlib_origins)>256:raise RuntimeError('E2 stdlib origin count')
            elif path not in (Path(__file__).resolve(strict=True),HERE/'e2_policy.py',HERE/'guest_g0_qualify.py'):
                raise RuntimeError(rejected_origin_message(name,path))
    interp=Path('/usr/bin/python3.12');data,identity=bounded_file(interp,64*1024*1024,root=True)
    return sqlite,{'source_pins':pins,'loaded_product':loaded,'interpreter':{'path':str(interp),'identity':identity,'bytes':len(data),'sha256':policy.sha256(data)},'native':native,'sqlite_version':sqlite.sqlite_version,'stdlib_origins':{'checked':True,'count':len(stdlib_origins),'sha256':policy.sha256(policy.canonical(stdlib_origins))},'ordinary':before,'fd_before':fds}

def stop_tracker(deadline):
    # Only the standard-library tracker created by this original spawn, after product ownership closes.
    module=importlib.import_module('multiprocessing.resource_tracker');tracker=module._resource_tracker
    pid,fd=tracker._pid,tracker._fd
    if pid is None and fd is None:return {'present':False,'reaped':True}
    if type(pid) is not int or type(fd) is not int or pid<=0:raise RuntimeError('E2 tracker shape')
    start=proc_start(pid);pidfd=os.pidfd_open(pid,0)
    try:
        os.close(fd);tracker._fd=None
        ready=select.select([pidfd],[],[],remaining(deadline))[0]
        if not ready:raise TimeoutError('E2 tracker EOF reap')
        waited,status=os.waitpid(pid,os.WNOHANG)
        if waited!=pid or not os.WIFEXITED(status) or os.WEXITSTATUS(status)!=0:raise RuntimeError('E2 tracker exit')
        tracker._pid=None
        return {'present':True,'pid':pid,'start':start,'status':status,'reaped':True}
    finally:os.close(pidfd)

def version(value):
    return None if value is None else {'identity':list(value.identity),'sha256':value.sha256}

def raw_blob(raw):
    if len(raw)>8192:raise RuntimeError('E2 candidate evidence bound')
    return {'bytes':len(raw),'sha256':policy.sha256(raw),'raw_base64':base64.b64encode(raw).decode()}

def published_fact(path,report,held_fd=None):
    # One selected published file only, streamed; never retain package payload.
    before=os.lstat(path);fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC) if held_fd is None else held_fd
    try:
        os.lseek(fd,0,os.SEEK_SET)
        opened=os.fstat(fd);policy.file_identity(ident(opened),12345)
        signature=lambda st:(ident(st),st.st_mtime_ns,st.st_ctime_ns)
        if signature(before)!=signature(opened) or not 0<opened.st_size<=64*1024*1024:raise RuntimeError('E2 package metadata/size')
        digest=hashlib.sha256();count=0
        while True:
            block=os.read(fd,65536)
            if not block:break
            count+=len(block)
            if count>64*1024*1024:raise RuntimeError('E2 package grew')
            digest.update(block)
        if count!=opened.st_size or signature(opened)!=signature(os.fstat(fd)) or signature(opened)!=signature(os.lstat(path)):raise RuntimeError('E2 package changed during read')
        result={'path':str(path),'identity':ident(opened),'sha256':digest.hexdigest(),'bytes':count,'manifest':report['manifest'],'catalog':report['catalog']}
        policy.package_fact(result);return result
    finally:
        if held_fd is None:os.close(fd)

class CompletionObserver:
    """Passive coordinator tracing only; no replacement product/spawn entry."""
    def __init__(self,actor,operations,schedules,recovery,managed,pre,mount_id,pressure,deadline):
        self.actor=actor;self.operations=operations;self.schedules=schedules;self.recovery=recovery;self.managed=managed;self.pre=pre;self.mount_id=mount_id;self.pressure=pressure;self.deadline=deadline
        self.captured={};self.errors=[];self.saves=[];self.workers=[];self.fault=None;self.gated=False;self.thread=None;self.release=threading.Event();self.report=None;self.inspected=None;self.write_frame=None;self.package_fd=None
    def trace(self,frame,event,arg):
        # No diagnostic exception may be raised into an original product frame.
        if frame.f_code not in (self.recovery._run.__code__,self.operations.SnapshotOperations._inspect.__code__,self.operations.SnapshotOperations._save.__code__,self.schedules.LockedDirectory.write.__code__):return None
        try:self.observe(frame,event,arg)
        except BaseException as exc:
            if len(self.errors)<16:self.errors.append(error(exc))
            try:self.actor.request_cancel()
            except BaseException:pass
            self.release.set()
        return self.trace
    def observe(self,frame,event,arg):
        code=frame.f_code;local=frame.f_locals
        if code is self.recovery._run.__code__:
            if event=='call':
                if len(self.workers)>=2:raise RuntimeError('E2 unexpected original worker call')
                args=[str(v) if isinstance(v,Path) else list(map(str,v)) if isinstance(v,tuple) else v for v in local['arguments']]
                self.workers.append({'operation':local['operation'],'arguments':args})
            elif event=='return' and local['operation']=='inspect' and isinstance(arg,dict):self.report=arg
        elif code is self.operations.SnapshotOperations._inspect.__code__ and event=='return' and isinstance(arg,tuple):self.inspected=arg
        elif code is self.operations.SnapshotOperations._save.__code__ and local['self'] is self.actor:
            incoming=local['state'];role=incoming.audit[-1].event if incoming.audit else None
            if role=='attempt_started':
                if event=='call':self.captured['initial']=ledger(self.managed,self.actor.version)
                elif event=='return' and self.actor.state is incoming:
                    self.captured['started']=ledger(self.managed,self.actor.version);self.captured['operation_id']=incoming.audit[-1].operation_id
        elif code is self.schedules.LockedDirectory.write.__code__ and local.get('self') is self.actor.managed:
            if event=='call':
                if len(self.saves)>=3:raise RuntimeError('E2 extra original ledger save')
                role=local['value'].audit[-1].event
                self.saves.append({'role':role,'expected':version(local['expected']),'returned':None,'exception':None})
            elif event=='exception':
                self.saves[-1]['exception']=error(arg[1])
                if self.write_frame is frame and frame.f_lineno in (489,493) and self.fault is None:
                    exc=arg[1]
                    self.fault={'line':frame.f_lineno,'source_sha256':policy.LEDGER_SHA,'source_path':code.co_filename,'function_firstlineno':code.co_firstlineno,'source_line_base64':policy.LEDGER_LINES[frame.f_lineno],
                        'module':type(exc).__module__,'class':type(exc).__name__,'errno':getattr(exc,'errno',None),'strerror':getattr(exc,'strerror',None),'error':error(exc),'stage':descriptor_fact(local['fd'],local.get('data',b''))}
            elif event=='return' and arg is not None:self.saves[-1]['returned']=version(arg)
            elif event=='line' and frame.f_lineno==489 and local['value'].audit[-1].event=='verified' and not self.gated:
                self.gated=True;self.write_frame=frame
                if code.co_filename!=str(SOURCE/'defiantmaple/scheduled_snapshots.py') or code.co_firstlineno!=472 or frame.f_back.f_code is not self.operations.SnapshotOperations._save.__code__ or frame.f_back.f_lineno!=137 or frame.f_back.f_back.f_code is not self.operations.SnapshotOperations.backup.__code__ or frame.f_back.f_back.f_lineno!=318 or local['leaf']!='schedule.json':raise RuntimeError('E2 original completion stack')
                if self.report is None or self.inspected is None or 'started' not in self.captured:raise RuntimeError('E2 missing original publication/inspection/start')
                raw=bytes(local['raw']);candidate=raw_blob(raw);point=local['value'].last_success
                path=self.managed/point.leaf;self.package_fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
                package=published_fact(path,self.report,self.package_fd)
                if self.inspected!=(tuple(package['identity'][:2]),package['bytes'],package['sha256']):raise RuntimeError('E2 original inspect/package facts')
                gate={'line':489,'source_sha256':policy.LEDGER_SHA,'source_path':code.co_filename,'function_firstlineno':code.co_firstlineno,'caller_lines':[frame.f_back.f_lineno,frame.f_back.f_back.f_lineno],
                    'expected':version(local['expected']),'current':version(local['current']),'stage':descriptor_fact(local['fd'],local['data']),'candidate_sha256':candidate['sha256'],'candidate_bytes':candidate['bytes']}
                start={'initial':self.captured['initial'],'started':self.captured['started'],'operation_id':self.captured['operation_id'],'gate':gate,'package':package,'workers':self.workers,
                    'ordering':['durable_attempt_started','original_package_authenticated','completion_stage_gate','pressure_established','resume_once']}
                policy.completion_stage(gate['stage'])
                if gate['stage']['mnt_id']!=self.mount_id or gate['stage']['identity'][0]!=self.pre['fixtures'][1][0]:raise RuntimeError('E2 selected completion stage')
                policy.verify_completion_bindings(self.pre,start,candidate)
                self.captured.update(start=start,candidate=candidate,package=package)
                phase_deadline=min(time.monotonic()+30,self.deadline)
                def fill():
                    try:self.captured['filler']=self.pressure.fill(phase_deadline)
                    except BaseException as exc:
                        self.errors.append(error(exc));self.actor.request_cancel()
                    finally:self.release.set()
                self.thread=threading.Thread(target=fill,name='E2-owned-pressure',daemon=True);self.thread.start()
                if not self.release.wait(remaining(phase_deadline)):raise TimeoutError('E2 pressure barrier deadline')
                if self.errors or 'filler' not in self.captured:raise RuntimeError('E2 pressure unavailable')
                start['filler']=self.captured['filler']
                self.captured['resumed_once']=True

def case_wire(index,data,nonce,binding,manifest_sha):
    value={'schema':'dm-e2-case-v1','case':'original-completion-ledger-enospc','nonce':nonce,'binding':binding,'seed_manifest_sha256':manifest_sha,'ordinal':index,'phase':policy.CASE_PHASES[index],'data':data}
    policy.case_record(value,nonce=nonce,binding=binding,manifest_sha256=manifest_sha,index=index)
    return policy.build_frame(policy.CASE_PREFIX,value,policy.CASE_CAPS[index])

def run_case(result_fd,nonce,binding,manifest_sha,p1,p2,p2_mount_id,deadline):
    remaining(deadline);records=[];errors=[];actor=None;owner_context=None;pressure=None;observer=None;pending=None;outcome='INCONCLUSIVE';result=None
    fixture_before=[fixture_identity(p1),fixture_identity(p2)]
    def record(data):records.append(case_wire(len(records),data,nonce,binding,manifest_sha))
    try:
        sqlite,pre=runtime_preflight(result_fd)
        root1=p1/'case';root2=p2/'case';root1.mkdir(mode=0o700);root2.mkdir(mode=0o700)
        for name in ('catalog','profile','registry-parent','cache'):(root1/name).mkdir(mode=0o700)
        database=root1/'catalog'/'empty.sqlite3';managed=root2/'managed'
        catalog=importlib.import_module('defiantmaple.catalog');admission=importlib.import_module('defiantmaple.admission')
        configurations=importlib.import_module('defiantmaple.snapshot_configuration');controlled=importlib.import_module('defiantmaple.controlled_configuration')
        schedules=importlib.import_module('defiantmaple.scheduled_snapshots');operations=importlib.import_module('defiantmaple.snapshot_operations');recovery=importlib.import_module('defiantmaple.recovery')
        catalog.initialize(database);source_before=catalog_fact(database,sqlite);pre.update(source_before=source_before,fixtures=fixture_before)
        if source_before['schema']!=7 or any(source_before['rows'].values()):raise RuntimeError('E2 nonempty source fixture')
        record(pre)
        owner_context=admission.admission_session(database,_registry_path=root1/'registry-parent'/'admission-v1');owner=owner_context.__enter__()
        config=configurations.SnapshotConfiguration(owner,root1/'profile',cache_roots=(root1/'cache',),locator_profile='custom')
        enable=controlled.ControlledEnableOperation(config,controlled.EnableRequest.capture(None,None))
        try:enable.run(schedules.Policy(enabled=True,retention_enabled=False,keep_count=1),managed_directory=managed)
        finally:
            if not enable.finish_thread():raise RuntimeError('E2 enable cleanup incomplete')
        actor=operations.SnapshotOperations(config);pressure=Pressure(root2/'filler.raw')
        observer=CompletionObserver(actor,operations,schedules,recovery,managed,pre,p2_mount_id,pressure,deadline)
        if sys.gettrace() is not None:raise RuntimeError('E2 preexisting coordinator trace')
        sys.settrace(observer.trace)
        try:result=actor.backup()
        finally:sys.settrace(None)
        if observer.thread is not None:observer.thread.join(remaining(deadline))
        errors.extend(observer.errors)
        if observer.thread is not None and observer.thread.is_alive():raise RuntimeError('E2 pressure thread remains')
        captured=observer.captured
        if not captured.get('resumed_once') or 'start' not in captured:raise RuntimeError('E2 missing completion gate evidence')
        record(captured['start'])
        record({'observed':observer.fault is not None,'exception':observer.fault,'saves':observer.saves,'kernel_trace_observed':False})
        # Counterproofs while pressure remains; no further product operation.
        final_ledger=ledger(managed,actor.version);after=published_fact(Path(captured['package']['path']),observer.report,observer.package_fd);source_after=catalog_fact(database,sqlite)
        stages=[str(path) for r in actor.records for path in r['stages'] if path.exists()]+[str(path) for path in managed.iterdir() if path.name.startswith('.schedule-')]
        exits=[{'operation':r['operation'],'pid':r['pid'],'status':r['exit'],'reaped':not r['process'].is_alive(),'cleanup_errors':r['cleanup_errors']} for r in actor.records]
        unchanged=all(source_before[k]==source_after[k] for k in ('identity','sha256','schema','library_id','rows'))
        os.close(observer.package_fd);observer.package_fd=None
        removed=pressure.remove()
        owner_context.__exit__(None,None,None);owner_context=None
        for r in actor.records:r['process'].close()
        tracker=stop_tracker(deadline)
        finish={'outcome':'PASS','product_operation_success':result.success_currently_verified,'operation':{'status':result.status,'success_currently_verified':result.success_currently_verified,'cleanup_pending':result.cleanup_pending,'error':result.error},
            'final_ledger':final_ledger,'candidate':captured['candidate'],'package_after':after,'source_after':source_after,'source_unchanged':unchanged,'remaining_stages':stages,'worker_exits':exits,
            'filler_removed':removed,'thread_joined':True,'tracker':tracker,'ordinary_after':ordinary.ordinary_identity(),'fd_after':ordinary.fd_inventory(result_fd),'errors':errors}
        record(finish)
        try:policy.parse_case(b''.join(records),nonce=nonce,binding=binding,manifest_sha256=manifest_sha,require_pass=True);outcome='PASS'
        except (ValueError,KeyError,TypeError) as proof:
            outcome='FAIL' if result.success_currently_verified or after!=captured['package'] else 'INCONCLUSIVE';records.pop();finish['outcome']=outcome;finish['errors']=errors+[error(proof)];record(finish)
    except BaseException as exc:
        pending=error(exc);errors.append(pending)
    finally:
        sys.settrace(None)
        if actor is not None and actor.active:
            try:
                actor.request_cancel()
                if not actor.reap_owned_cleanup():errors.append('E2 original owned cleanup pending')
            except BaseException as exc:errors.append(error(exc))
        if observer is not None and observer.thread is not None and observer.thread.is_alive():
            observer.release.set();observer.thread.join(max(0,deadline-time.monotonic()))
        if observer is not None and observer.package_fd is not None:
            try:os.close(observer.package_fd);observer.package_fd=None
            except BaseException as cleanup:errors.append(error(cleanup))
        quiescent=not (actor is not None and actor.active) and not (observer is not None and observer.thread is not None and observer.thread.is_alive())
        if not quiescent:errors.append('E2 owners not quiescent; fixture cleanup withheld')
        if quiescent:
            if pressure is not None:
                try:
                    if pressure.fd is not None:pressure.remove()
                except BaseException as exc:errors.append(error(exc))
                finally:
                    try:pressure.close()
                    except BaseException as exc:errors.append(error(exc))
            if owner_context is not None:
                try:owner_context.__exit__(None,None,None)
                except BaseException as exc:errors.append(error(exc))
            if actor is not None:
                for r in actor.records:
                    try:r['process'].close()
                    except BaseException as exc:errors.append(error(exc))
                try:stop_tracker(deadline)
                except BaseException as exc:errors.append(error(exc))
        if pending is not None and len(records)<4:
            try:record({'incomplete':pending})
            except BaseException as diagnostic:errors.append(error(diagnostic))
        if quiescent and records:
            try:
                evidence=p1/'evidence';evidence.mkdir(mode=0o700,exist_ok=True)
                for index,wire in enumerate(records):
                    fd=os.open(evidence/(policy.CASE_PHASES[index]+'.raw'),os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
                    try:ordinary.write_all(fd,wire);os.fsync(fd)
                    finally:os.close(fd)
            except BaseException as diagnostic:errors.append(error(diagnostic))
        for fixture in ((p1,p2) if quiescent else ()):
            for name in ('case','evidence'):
                path=fixture/name
                if path.exists():
                    try:remove_generated(path,fixture_before[0 if fixture==p1 else 1][0])
                    except BaseException as exc:errors.append(error(exc))
        try:
            if [fixture_identity(p1),fixture_identity(p2)]!=fixture_before:errors.append('E2 fixture parents changed')
        except BaseException as cleanup:errors.append(error(cleanup))
    raw=b''.join(records)
    if len(raw)>CASE_MAX:raise RuntimeError('E2 capture cap')
    try:
        offset=0;os.set_blocking(result_fd,False)
        while offset<len(raw):
            if not select.select([],[result_fd],[],remaining(deadline))[1]:raise TimeoutError('E2 record transport deadline')
            try:count=os.write(result_fd,raw[offset:])
            except BlockingIOError:continue
            if count<=0:raise RuntimeError('E2 transport no progress')
            offset+=count
    except BaseException as exc:errors.append(error(exc))
    if len(records)!=4 or errors:raise RuntimeError('E2 INCONCLUSIVE: '+';'.join(errors)[:1024])
    return outcome

def main():
    if len(sys.argv)!=9:raise RuntimeError('E2 arguments')
    result_fd=int(sys.argv[1]);os.set_inheritable(result_fd,False);nonce,binding,manifest_sha=sys.argv[2:5]
    run_case(result_fd,nonce,binding,manifest_sha,Path(sys.argv[5]),Path(sys.argv[6]),int(sys.argv[7]),float(sys.argv[8]))
if __name__=='__main__':main()
