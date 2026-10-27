"""Ordinary-UID G0 probe using only the two reviewed product files."""
from __future__ import annotations
import hashlib, json, os, re, stat, sys
from pathlib import Path

UID = 12345
SOURCE = Path("/opt/dm-g0/source")
MANIFEST = Path("/opt/dm-g0/seed-manifest.json")
PRODUCT = (
    (SOURCE / "defiantmaple/__init__.py", 52, "dde219d920adbf1e72e092fb87a885bd472f104184427e3a2fc63be8994e95e4"),
    (SOURCE / "defiantmaple/recovery_storage.py", 10733, "1076a6f45aed68bc9eba84fdd6c628ae49fe70cde4062cd70585800994eed9c3"),
)

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()

def sha_file(path, cap):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) or opened.st_size > cap:
            raise RuntimeError("qualifier file type/cap")
        digest, total = hashlib.sha256(), 0
        while True:
            block = os.read(fd, min(65536, cap + 1 - total))
            if not block: break
            total += len(block)
            if total > cap: raise RuntimeError("qualifier file growth")
            digest.update(block)
        after = os.fstat(fd)
    finally: os.close(fd)
    named = os.lstat(path)
    identity = lambda st: (st.st_dev, st.st_ino, st.st_mode, st.st_uid, st.st_gid, st.st_nlink, st.st_size)
    if identity(opened) != identity(after) or identity(opened) != identity(named):
        raise RuntimeError("qualifier file changed")
    return digest.hexdigest(), total

def identity(st):
    return (st.st_dev,st.st_ino,st.st_mode,st.st_uid,st.st_gid,st.st_nlink)

def secure_dir(path):
    desired={Path("/opt/dm-g0"):0o555,Path("/opt/dm-g0/helpers"):0o555,Path("/opt/dm-g0/source"):0o555,Path("/opt/dm-g0/source/defiantmaple"):0o555}
    fd=os.open("/",os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        for component in path.parts[1:]:
            before=os.stat(component,dir_fd=fd,follow_symlinks=False)
            if not stat.S_ISDIR(before.st_mode) or before.st_uid!=0 or before.st_gid!=0 or before.st_mode&0o022: raise RuntimeError("public directory boundary")
            child=os.open(component,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=fd); opened=os.fstat(child)
            if identity(before)!=identity(opened): os.close(child); raise RuntimeError("public directory identity")
            os.close(fd); fd=child
        if path in desired and stat.S_IMODE(os.fstat(fd).st_mode)!=desired[path]: raise RuntimeError("public directory mode")
        opened=os.fstat(fd); return fd,[opened.st_dev,opened.st_ino,stat.S_IMODE(opened.st_mode)]
    except BaseException: os.close(fd); raise

def public_file(path,cap,mode):
    parent,parent_fact=secure_dir(path.parent)
    try:
        before=os.stat(path.name,dir_fd=parent,follow_symlinks=False)
        if (not stat.S_ISREG(before.st_mode) or before.st_uid!=0 or before.st_gid!=0 or before.st_nlink!=1
                or stat.S_IMODE(before.st_mode)!=mode or before.st_mode&0o022): raise RuntimeError("public file metadata")
        fd=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC,dir_fd=parent)
        try:
            opened=os.fstat(fd); data=bytearray()
            while True:
                block=os.read(fd,min(65536,cap+1-len(data)))
                if not block: break
                data.extend(block)
                if len(data)>cap: raise RuntimeError("public file cap")
            after_fd=os.fstat(fd)
        finally: os.close(fd)
        after=os.stat(path.name,dir_fd=parent,follow_symlinks=False)
        full=lambda st:(identity(st),st.st_size)
        if full(before)!=full(opened) or full(opened)!=full(after_fd) or full(opened)!=full(after): raise RuntimeError("public file changed")
        return bytes(data),{"path":str(path),"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest(),"mode":mode,"parent":parent_fact}
    finally: os.close(parent)

def strict_json(raw):
    def pairs(items):
        out={}
        for key,value in items:
            if key in out: raise RuntimeError("duplicate manifest key")
            out[key]=value
        return out
    return json.loads(raw,object_pairs_hook=pairs)

def verify_public_manifest():
    raw,_=public_file(MANIFEST,1024*1024,0o444); value=strict_json(raw)
    if not isinstance(value,dict) or set(value)!={"schema","entries"} or value["schema"]!="dm-g0-seed-manifest-v1" or not isinstance(value["entries"],list) or len(value["entries"])!=8:
        raise RuntimeError("public manifest schema")
    expected={str(path):(size,digest) for path,size,digest in PRODUCT}
    expected["/opt/dm-g0/helpers/guest_g0_qualify.py"]=None
    public={}
    for item in value["entries"]:
        if not isinstance(item,dict) or set(item)!={"path","bytes","sha256","uid","gid","mode","public"}: raise RuntimeError("public manifest entry")
        if item["public"] is True: public[item["path"]]=item
    if set(public)!=set(expected): raise RuntimeError("public manifest membership")
    facts=[]
    for path,pin in expected.items():
        item=public[path]
        size,digest=(item["bytes"],item["sha256"]) if pin is None else pin
        if item!={"path":path,"bytes":size,"sha256":digest,"uid":0,"gid":0,"mode":0o444,"public":True}: raise RuntimeError("public manifest pin")
        data,fact=public_file(Path(path),65536,0o444)
        if len(data)!=size or fact["sha256"]!=digest: raise RuntimeError("public manifest digest")
        facts.append(fact)
    return hashlib.sha256(raw).hexdigest(),facts

def fd_inventory(result_fd):
    out = []
    names = os.listdir("/proc/self/fd")
    if len(names) > 16: raise RuntimeError("qualifier descriptor count")
    for raw in names:
        if not raw.isdecimal(): raise RuntimeError("qualifier descriptor name")
        fd = int(raw)
        try: st = os.fstat(fd)
        except OSError: continue
        target = os.readlink("/proc/self/fd/" + raw)
        if len(target) > 512: raise RuntimeError("qualifier descriptor target")
        info=os.open("/proc/self/fdinfo/"+raw,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
        try:
            fdinfo=os.read(info,4097)
            if len(fdinfo)>4096 or os.read(info,1): raise RuntimeError("qualifier fdinfo cap")
        finally: os.close(info)
        matches=re.findall(rb"(?m)^mnt_id:\s*([0-9]+)$",fdinfo)
        if len(matches)!=1: raise RuntimeError("qualifier fdinfo mount id")
        if fd in (0,1,2):
            null=os.stat("/dev/null")
            if target!="/dev/null" or not stat.S_ISCHR(st.st_mode) or st.st_rdev!=null.st_rdev: raise RuntimeError("qualifier stdio descriptor")
        elif fd==result_fd:
            if not stat.S_ISFIFO(st.st_mode) or not re.fullmatch(r"pipe:\[[1-9][0-9]*\]",target): raise RuntimeError("qualifier result descriptor")
        out.append({"fd": fd, "mode": stat.S_IFMT(st.st_mode), "target": target,"mnt_id":int(matches[0])})
    if {item["fd"] for item in out} != {0, 1, 2, result_fd}:
        raise RuntimeError("qualifier descriptor leak")
    return sorted(out, key=lambda item: item["fd"])

def write_all(fd, data):
    offset = 0
    while offset < len(data):
        count = os.write(fd, data[offset:])
        if count <= 0: raise RuntimeError("qualifier write")
        offset += count

def ordinary_identity():
    if ((os.getuid(),os.geteuid(),os.getgid(),os.getegid())!=(UID,UID,UID,UID)
            or os.getresuid()!=(UID,UID,UID) or os.getresgid()!=(UID,UID,UID) or os.getgroups()!=[]):
        raise RuntimeError("qualifier identity")
    fd=os.open("/proc/self/status",os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        raw=os.read(fd,65537)
        if len(raw)>65536 or os.read(fd,1): raise RuntimeError("qualifier status cap")
    finally: os.close(fd)
    caps={}
    for key in ("CapInh","CapPrm","CapEff","CapBnd","CapAmb"):
        values=re.findall(rb"(?m)^"+key.encode()+rb":\s*([0-9a-f]{16})$",raw)
        if len(values)!=1 or (key!="CapBnd" and int(values[0],16)!=0): raise RuntimeError("qualifier retained capability")
        caps[key]=values[0].decode("ascii")
    privileges=re.findall(rb"(?m)^NoNewPrivs:\s*([01])$",raw)
    if len(privileges)!=1: raise RuntimeError("qualifier no-new-privileges observation")
    return {"uids":list(os.getresuid()),"gids":list(os.getresgid()),"supplementary_groups":os.getgroups(),
            "capabilities":caps,"no_new_privs":int(privileges[0])}

def exact_product_modules():
    observed={name for name in sys.modules if name=="defiantmaple" or name.startswith("defiantmaple.")}
    if observed!={"defiantmaple","defiantmaple.recovery_storage"}: raise RuntimeError("unexpected product module set")

def mount_namespace():
    path="/proc/self/ns/mnt"; before=os.lstat(path)
    if not stat.S_ISLNK(before.st_mode) or before.st_uid!=UID: raise RuntimeError("qualifier namespace locator")
    target=os.readlink(path)
    if len(target)>64 or not target.startswith("mnt:[") or not target.endswith("]"): raise RuntimeError("qualifier namespace target")
    fd=os.open(path,os.O_RDONLY|os.O_CLOEXEC)
    try: opened=os.fstat(fd)
    finally: os.close(fd)
    after=os.lstat(path)
    identity=lambda st:(st.st_dev,st.st_ino,st.st_mode,st.st_uid,st.st_gid,st.st_nlink)
    if identity(before)!=identity(after) or os.readlink(path)!=target or not stat.S_ISREG(opened.st_mode): raise RuntimeError("qualifier namespace changed")
    return {"path":path,"target":target,"dev":opened.st_dev,"ino":opened.st_ino}

def probe(recovery, partition, mountpoint, probe_name, nonce, namespace):
    fixture, leaf = mountpoint / "fixture", mountpoint / "fixture" / probe_name
    fixture_before=os.lstat(fixture)
    if (not stat.S_ISDIR(fixture_before.st_mode) or fixture_before.st_uid!=UID or fixture_before.st_gid!=UID
            or stat.S_IMODE(fixture_before.st_mode)!=0o700 or fixture_before.st_nlink<1):
        raise RuntimeError("fixture parent identity")
    fixture_identity=[fixture_before.st_dev,fixture_before.st_ino,fixture_before.st_uid,fixture_before.st_gid,
                      stat.S_IMODE(fixture_before.st_mode),fixture_before.st_nlink]
    kind, source = recovery._mount_type(fixture)
    if kind != "ext4" or source != partition: raise RuntimeError("original mount qualifier")
    name = Path(partition).name
    if not recovery._direct_local_block(name) or not recovery._local_backing(kind, source):
        raise RuntimeError("original local-block qualifier")
    content = hashlib.sha256((nonce + ":" + partition).encode()).digest() * 128
    with recovery.private_local_parent(leaf) as (admitted, dirfd):
        if admitted != leaf: raise RuntimeError("original admitted path")
        opened=os.fstat(dirfd)
        if [opened.st_dev,opened.st_ino,opened.st_uid,opened.st_gid,stat.S_IMODE(opened.st_mode),opened.st_nlink]!=fixture_identity:
            raise RuntimeError("original private parent descriptor")
        try: os.stat(leaf.name, dir_fd=dirfd, follow_symlinks=False)
        except FileNotFoundError: pass
        else: raise RuntimeError("probe preexists")
        write_fd = recovery.create_stage(leaf, dirfd)
        try:
            write_all(write_fd, content); os.fsync(write_fd); created = os.fstat(write_fd)
        finally: os.close(write_fd)
        read_fd, opened = recovery.regular_existing(leaf, dirfd)
        try:
            if (opened.st_dev, opened.st_ino, opened.st_size) != (created.st_dev, created.st_ino, 4096):
                raise RuntimeError("probe identity")
            observed = bytearray()
            while len(observed) <= 4096:
                block = os.read(read_fd, 4097 - len(observed))
                if not block: break
                observed.extend(block)
            if bytes(observed) != content: raise RuntimeError("probe readback")
        finally: os.close(read_fd)
        named = os.stat(leaf.name, dir_fd=dirfd, follow_symlinks=False)
        if (named.st_dev, named.st_ino) != (created.st_dev, created.st_ino): raise RuntimeError("probe name identity")
        os.unlink(leaf.name, dir_fd=dirfd); os.fsync(dirfd)
        try: os.stat(leaf.name, dir_fd=dirfd, follow_symlinks=False)
        except FileNotFoundError: pass
        else: raise RuntimeError("probe unlink")
    fixture_after=os.lstat(fixture)
    if [fixture_after.st_dev,fixture_after.st_ino,fixture_after.st_uid,fixture_after.st_gid,
            stat.S_IMODE(fixture_after.st_mode),fixture_after.st_nlink]!=fixture_identity:
        raise RuntimeError("fixture parent changed")
    return {"partition": partition, "mountpoint": str(mountpoint), "filesystem": kind, "source": source,
            "probe_inode": created.st_ino, "probe_bytes": 4096, "probe_sha256": hashlib.sha256(content).hexdigest(), "absent_after": True,
            "mount_namespace":namespace,"fixture_parent_identity":fixture_identity}

def main():
    if len(sys.argv) != 10: raise RuntimeError("qualifier argv")
    result_fd = int(sys.argv[1]); nonce, manifest_sha, probe_name = sys.argv[2:5]
    partitions, mounts, binding = (sys.argv[5], sys.argv[7]), (Path(sys.argv[6]), Path(sys.argv[8])), sys.argv[9]
    if not 3 <= result_fd <= 127 or len(nonce) != 32 or len(manifest_sha) != 64 or len(binding) != 64 or probe_name != "dm-g0-probe.bin":
        raise RuntimeError("qualifier binding argv")
    identity_before=ordinary_identity()
    os.set_inheritable(result_fd, False); before_fds = fd_inventory(result_fd)
    observed_manifest,public_before=verify_public_manifest()
    if observed_manifest!=manifest_sha: raise RuntimeError("qualifier manifest binding")
    for path, size, digest in PRODUCT:
        if sha_file(path, 65536) != (digest, size): raise RuntimeError("product source pin")
    sys.path.insert(0, str(SOURCE))
    import defiantmaple
    import defiantmaple.recovery_storage as recovery
    exact_product_modules()
    if Path(defiantmaple.__file__).resolve(strict=True) != PRODUCT[0][0] or Path(recovery.__file__).resolve(strict=True) != PRODUCT[1][0]:
        raise RuntimeError("product import origin")
    namespace=mount_namespace()
    results = [probe(recovery, part, mount, probe_name, nonce, namespace) for part, mount in zip(partitions, mounts)]
    exact_product_modules()
    for path, size, digest in PRODUCT:
        if sha_file(path, 65536) != (digest, size): raise RuntimeError("product source changed after qualification")
    observed_manifest_after,public_after=verify_public_manifest()
    if observed_manifest_after!=manifest_sha or public_after!=public_before: raise RuntimeError("public seed tree changed")
    exe = Path(sys.executable).resolve(strict=True); exe_sha, exe_bytes = sha_file(exe, 64 * 1024 * 1024)
    modules = []
    for name, module in sorted(sys.modules.items()):
        path = getattr(module, "__file__", None)
        if not isinstance(path, str) or name.startswith("defiantmaple"): continue
        resolved = Path(path).resolve(strict=True)
        if not str(resolved).startswith("/usr/lib/python"): continue
        digest, size = sha_file(resolved, 16 * 1024 * 1024)
        modules.append({"name": name, "path": str(resolved), "bytes": size, "sha256": digest})
        if len(modules) > 128: raise RuntimeError("stdlib count")
    receipt = {"schema": "dm-g0-qualifier-result-v1", "nonce": nonce, "seed_manifest_sha256": manifest_sha,
               "uid": UID, "gid": UID, "product_entries": [{"path": str(p), "bytes": s, "sha256": d} for p,s,d in PRODUCT],
               "partitions": results, "interpreter": {"path": str(exe), "bytes": exe_bytes, "sha256": exe_sha}, "loaded_stdlib": modules}
    identity_after=ordinary_identity(); after_fds=fd_inventory(result_fd)
    if identity_before!=identity_after or before_fds!=after_fds: raise RuntimeError("qualifier record invariant")
    receipt["ordinary_identity"]={"before":identity_before,"after":identity_after}
    receipt["fd_inventories"]={"result_fd":result_fd,"before":before_fds,"after":after_fds}
    payload = canonical(receipt)
    if not 0 < len(payload) <= 65400: raise RuntimeError("qualifier record cap")
    raw = b"DMG0QUAL1 " + str(len(payload)).encode() + b" " + hashlib.sha256(payload).hexdigest().encode() + b"\n" + payload
    if len(raw) > 65536: raise RuntimeError("qualifier record cap")
    write_all(result_fd, raw); os.close(result_fd)

if __name__ == "__main__": main()
