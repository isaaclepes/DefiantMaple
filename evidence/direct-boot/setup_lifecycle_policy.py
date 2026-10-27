"""Pure finite evidence contract for setup observation; never G0 qualification."""
from __future__ import annotations
import base64, hashlib, importlib.util, json, re
from pathlib import Path
_spec=importlib.util.spec_from_file_location("life_g0_envelope",Path(__file__).with_name("g0_policy.py"))
g0=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(g0)
PREFIX=b"DMSETUPLIFE1 ";SCOPE="setup-lifecycle-observation-only-v1"
DOC_MAX=2*1024*1024;SNAPSHOT_MAX=48*1024;TOOL_AGGREGATE=512*1024;STREAM_MAX=65536
MONITOR_MAX=65536;CHUNK_MAX=32768;CHUNK_WIRE_MAX=44462;CHUNKS_MAX=64
UDEV="/usr/bin/udevadm";UDEV_VERSION="255.4-1ubuntu8.18"
MONITOR_ARGV=[UDEV,"--debug","monitor","--kernel","--udev","--property","--subsystem-match=block"]
BANNER=b"monitor will print the received events for:\nUDEV - the event which udev sends out after rule processing\nKERNEL - the kernel uevent\n\n"
STATUSES=("transition_observed","end_of_setup_no_transition","preflight_stop","incomplete","failed")
SCHEMAS={
"document":{"schema","scope","nonce","binding","manifest_sha256","preflight","observer","markers","snapshots","commands","stop","cleanup"},
"preflight":{"tools","observer_tool","budget"},
"observer":{"argv","identity","ready","started_ns","stopped_ns","stdout_bytes","stderr_bytes","observed_at_least","truncated","selected","diagnostics","discarded","exit","loss_status","error"},
"discarded":{"stdout_bytes","stdout_records","stdout_sha256","stderr_bytes","stderr_records","stderr_sha256","first_ns","last_ns"},
"marker":{"ordinal","phase","edge","at_ns"},
"snapshot":{"ordinal","phase","start_ns","end_ns","original_facts","current","native","initstate","database","diff","error","diagnostic_error"},
"command":{"ordinal","argv","stdin_base64","stdout_base64","stderr_base64","deadline","output_cap","returncode","reaped","fds_closed","eof","truncated","error","start_ns","end_ns"},
"stop":{"status","phase","primary_error","diagnostic_error","mutation_started","baseline_captured"},
"cleanup":{"monitor_reaped","tools_reaped","fds_closed","unmounts","directories_removed","errors"},
"error":{"class","message","errno","message_truncated"},
"event":{"ordinal","source","action","devpath","classification","sequence","timestamp_us","first_ns","last_ns","start_offset","end_offset","raw_base64"},
"diagnostic":{"at_ns","raw_base64"},
"file":{"status","path","before","opened","after","raw_base64","error"},
"tool":{"requested","canonical","identity","sha256","bytes","package","version","architecture"},
"budget":{"tool_invocations","tool_output_aggregate","monitor_stdout","monitor_stderr","snapshots","snapshot_bytes","document_bytes","serial_bytes","qmp_bytes","artifact_bytes"},
}
def canonical(value):return g0.canonical(value)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def integer(value,upper=(1<<63)-1):return type(value) is int and 0<=value<=upper
def fields(value,schema):
    if not isinstance(value,dict) or set(value)!=SCHEMAS[schema]:raise ValueError("lifecycle "+schema+" fields")
    return value
def error(exc):return g0.guard_error(exc)
def check_error(value):
    if value is not None:g0.validate_guard_error(value)
def b64(raw):return base64.b64encode(raw).decode("ascii")
def unb64(value,cap):
    if not isinstance(value,str):raise ValueError("lifecycle base64 type")
    raw=base64.b64decode(value,validate=True)
    if len(raw)>cap or b64(raw)!=value:raise ValueError("lifecycle base64 bound")
    return raw
def common(nonce,binding,manifest_sha256):
    if not g0.NONCE.fullmatch(nonce) or not g0.HEX64.fullmatch(binding) or not g0.HEX64.fullmatch(manifest_sha256):raise ValueError("lifecycle binding")
    return {"scope":SCOPE,"nonce":nonce,"binding":binding,"manifest_sha256":manifest_sha256}
def check_binding(value,expected):
    if any(value.get(key)!=item for key,item in expected.items()):raise ValueError("lifecycle binding mismatch")
def empty_observer():
    return {"argv":list(MONITOR_ARGV),"identity":None,"ready":False,"started_ns":None,"stopped_ns":None,"stdout_bytes":0,"stderr_bytes":0,"observed_at_least":{"stdout":0,"stderr":0},"truncated":{"stdout":False,"stderr":False},
            "selected":[],"diagnostics":[],"discarded":{"stdout_bytes":0,"stdout_records":0,"stdout_sha256":sha(b""),"stderr_bytes":0,"stderr_records":0,"stderr_sha256":sha(b""),"first_ns":None,"last_ns":None},"exit":None,"loss_status":"not_started","error":None}
def new_document(**binding):
    return {"schema":"dm-setup-lifecycle-document-v1",**common(**binding),"preflight":{"tools":[],"observer_tool":None,"budget":{"tool_invocations":23,"tool_output_aggregate":TOOL_AGGREGATE,"monitor_stdout":MONITOR_MAX,"monitor_stderr":MONITOR_MAX,"snapshots":14,"snapshot_bytes":SNAPSHOT_MAX,"document_bytes":DOC_MAX,"serial_bytes":4194304,"qmp_bytes":1048576,"artifact_bytes":8388608}},"observer":empty_observer(),"markers":[],"snapshots":[],"commands":[],"stop":{"status":"preflight_stop","phase":"preflight","primary_error":None,"diagnostic_error":None,"mutation_started":False,"baseline_captured":False},"cleanup":{"monitor_reaped":True,"tools_reaped":True,"fds_closed":True,"unmounts":[],"directories_removed":True,"errors":[]}}
def validate_file(value):
    fields(value,"file");check_error(value["error"])
    if value["status"] not in ("present","absent","error","unstable","not_collected"):raise ValueError("lifecycle file status")
    if not isinstance(value["path"],str) or len(value["path"].encode())>4096:raise ValueError("lifecycle file path")
    unb64(value["raw_base64"],8192)
    for key in ("before","opened","after"):
        if value[key] is not None and (not isinstance(value[key],list) or len(value[key])!=8 or any(not integer(n) for n in value[key])):raise ValueError("lifecycle stat tuple")
def validate_document(value,**binding):
    fields(value,"document");check_binding(value,common(**binding))
    if len(canonical({"preflight":value["preflight"],"markers":value["markers"]}))>65536:raise ValueError("lifecycle metadata budget")
    if value["schema"]!="dm-setup-lifecycle-document-v1" or len(canonical(value))>DOC_MAX:raise ValueError("lifecycle document cap/schema")
    fields(value["preflight"],"preflight");fields(value["preflight"]["budget"],"budget")
    if value["preflight"]["budget"]!=new_document(**binding)["preflight"]["budget"]:raise ValueError("lifecycle budget")
    if not isinstance(value["preflight"]["tools"],list) or len(value["preflight"]["tools"])>5:raise ValueError("lifecycle tools")
    # Original tool facts have their unchanged G0 schema; observer has its own finite schema.
    for fact in value["preflight"]["tools"]:g0._validate_tool_fact(fact)
    fact=value["preflight"]["observer_tool"]
    if fact is not None:
        fields(fact,"tool")
        if (fact["requested"]!=UDEV or fact["version"]!=UDEV_VERSION or not g0.HEX64.fullmatch(fact["sha256"])
                or not integer(fact["bytes"],64*1024*1024) or not isinstance(fact["identity"],list) or len(fact["identity"])!=8):raise ValueError("lifecycle observer tool")
    observer=fields(value["observer"],"observer");fields(observer["discarded"],"discarded");check_error(observer["error"])
    if observer["argv"]!=MONITOR_ARGV or type(observer["ready"]) is not bool or any(not integer(observer[key],MONITOR_MAX) for key in ("stdout_bytes","stderr_bytes")):raise ValueError("lifecycle observer bounds")
    if observer["loss_status"] not in ("not_started","loss_not_detected_not_proved_lossless","incomplete_or_unknown"):raise ValueError("lifecycle loss status")
    if len(canonical(observer))>178864:raise ValueError("lifecycle observer serialized cap")
    if len(observer["selected"])>256:raise ValueError("lifecycle events cap")
    for index,item in enumerate(observer["selected"]):
        fields(item,"event");raw=unb64(item["raw_base64"],32768)
        if item["ordinal"]!=index or type(item["ordinal"]) is not int or item["source"] not in ("KERNEL","UDEV") or item["classification"] not in ("namespace","partition-p1","partition-p2","unexpected-descendant"):raise ValueError("lifecycle event order/source")
        if not isinstance(item["devpath"],str) or not item["devpath"].startswith("/devices/") or not integer(item["timestamp_us"]) or not integer(item["first_ns"]) or not integer(item["last_ns"]) or item["last_ns"]<item["first_ns"]:raise ValueError("lifecycle event clock/path")
    if len(observer["diagnostics"])>256:raise ValueError("lifecycle diagnostics count")
    for item in observer["diagnostics"]:fields(item,"diagnostic");unb64(item["raw_base64"],MONITOR_MAX)
    if sum(len(unb64(x["raw_base64"],MONITOR_MAX)) for x in observer["diagnostics"])>MONITOR_MAX:raise ValueError("lifecycle diagnostic cap")
    if not isinstance(value["markers"],list) or len(value["markers"])>128:raise ValueError("lifecycle marker cap")
    last=0
    for index,item in enumerate(value["markers"]):
        fields(item,"marker")
        if type(item["ordinal"]) is not int or item["ordinal"]!=index or not integer(item["at_ns"]) or item["at_ns"]<last or item["edge"] not in ("before","after","observed","stop") or not isinstance(item["phase"],str) or len(item["phase"])>64:raise ValueError("lifecycle marker order")
        last=item["at_ns"]
    if len(value["snapshots"])>14:raise ValueError("lifecycle snapshot count")
    for index,item in enumerate(value["snapshots"]):
        fields(item,"snapshot");check_error(item["error"]);check_error(item["diagnostic_error"])
        if item["ordinal"]!=index or type(item["ordinal"]) is not int or len(canonical(item))>SNAPSHOT_MAX or not integer(item["start_ns"]) or not integer(item["end_ns"]) or item["end_ns"]<item["start_ns"]:raise ValueError("lifecycle snapshot bounds")
        for name in ("initstate","database"):
            if not isinstance(item[name],list) or len(item[name])>3:raise ValueError("lifecycle snapshot files")
            for file in item[name]:validate_file(file)
        if not isinstance(item["diff"],list) or len(item["diff"])>128:raise ValueError("lifecycle snapshot diff")
    if len(value["commands"])>23:raise ValueError("lifecycle command count")
    total=0
    for index,item in enumerate(value["commands"]):
        fields(item,"command");check_error(item["error"])
        if type(item["ordinal"]) is not int or item["ordinal"]!=index or not isinstance(item["argv"],list) or not 1<=len(item["argv"])<=8 or any(not isinstance(x,str) or len(x.encode())>512 for x in item["argv"]):raise ValueError("lifecycle command argv")
        unb64(item["stdin_base64"],4096)
        total+=sum(len(unb64(item[key],STREAM_MAX)) for key in ("stdout_base64","stderr_base64"))
        if type(item["output_cap"]) is not int or item["output_cap"]!=STREAM_MAX or type(item["reaped"]) is not bool or type(item["truncated"]) is not bool or not isinstance(item["eof"],list) or len(item["eof"])!=2 or any(type(x) is not bool for x in item["eof"]):raise ValueError("lifecycle command completion")
        metadata={k:v for k,v in item.items() if k not in ("stdout_base64","stderr_base64")}
        if len(canonical(metadata))>4096:raise ValueError("lifecycle command metadata cap")
    if total>TOOL_AGGREGATE:raise ValueError("lifecycle command aggregate")
    stop=fields(value["stop"],"stop");fields(value["cleanup"],"cleanup")
    if stop["status"] not in STATUSES or type(stop["mutation_started"]) is not bool or type(stop["baseline_captured"]) is not bool:raise ValueError("lifecycle stop status")
    check_error(stop["primary_error"]);check_error(stop["diagnostic_error"])
    validate_reached_prefix(value,**binding)
    return value

def wire_frames(raw,*,binding,status,primary,diagnostic,payload_form):
    observed=min(len(raw),DOC_MAX+1);retained=raw[:DOC_MAX];chunks=max(1,(len(retained)+CHUNK_MAX-1)//CHUNK_MAX)
    details={"payload_form":payload_form,"observed_at_least":observed,"truncated":len(raw)>DOC_MAX}
    meta={"schema":"dm-setup-lifecycle-wire-v1",**common(**binding),"kind":"meta","bytes":len(retained),"sha256":sha(retained),"chunks":chunks,**details}
    out=[g0.build_frame(PREFIX,meta,4096)]
    for index in range(chunks):out.append(g0.build_frame(PREFIX,{"schema":"dm-setup-lifecycle-wire-v1",**common(**binding),"kind":"chunk","index":index,"raw_base64":b64(retained[index*CHUNK_MAX:(index+1)*CHUNK_MAX])},CHUNK_WIRE_MAX))
    terminal={"schema":"dm-setup-lifecycle-wire-v1",**common(**binding),"kind":"terminal","sha256":sha(retained),"chunks":chunks,"status":status,"observation_only":True,"g0_qualified":False,"product_probes_executed":False,"enospc_tested":False,"primary_error":primary,"diagnostic_error":diagnostic,**details}
    out.append(g0.build_frame(PREFIX,terminal,16384));return out

def frames(value):
    binding={key:value[key] for key in ("nonce","binding","manifest_sha256")};validate_document(value,**binding)
    return wire_frames(canonical(value),binding=binding,status=value["stop"]["status"],primary=value["stop"]["primary_error"],diagnostic=value["stop"]["diagnostic_error"],payload_form="canonical-document")

def prefix_frames(raw,primary,diagnostic,**binding):
    check_error(primary);check_error(diagnostic)
    return wire_frames(raw,binding=binding,status="incomplete",primary=primary,diagnostic=diagnostic,payload_form="incomplete-prefix")

def parse(stream,**binding):
    forbidden=(g0.READY_PREFIX,g0.TOOL_PREFIX,g0.QUAL_RAW_PREFIX,g0.RESULT_PREFIX,g0.ACK_PREFIX,g0.QUAL_PREFIX,g0.MOUNT_PREFIX,g0.GUARD_PREFIX)
    if any(line.startswith(forbidden) for line in g0.serial_records(stream)):raise ValueError("G0 stream in setup-only observation")
    tail=stream.rsplit(b"\n",1)[-1]
    if tail and PREFIX.startswith(tail):raise ValueError("lifecycle terminal prefix fragment")
    lines=[line for line in g0.serial_records(stream) if line.startswith(PREFIX)]
    if not 3<=len(lines)<=66:raise ValueError("lifecycle wire count")
    expected=common(**binding);meta=g0.decode_line(lines[0],PREFIX,4096)
    if set(meta)!={"schema",*expected,"kind","bytes","sha256","chunks","payload_form","observed_at_least","truncated"} or meta["schema"]!="dm-setup-lifecycle-wire-v1" or meta["kind"]!="meta":raise ValueError("lifecycle wire metadata")
    check_binding(meta,expected)
    if (not integer(meta["chunks"],CHUNKS_MAX) or meta["chunks"]<1 or not integer(meta["bytes"],DOC_MAX) or len(lines)!=meta["chunks"]+2
            or meta["payload_form"] not in ("canonical-document","incomplete-prefix") or not integer(meta["observed_at_least"],DOC_MAX+1) or meta["observed_at_least"]<meta["bytes"]
            or type(meta["truncated"]) is not bool or meta["truncated"]!=(meta["observed_at_least"]>meta["bytes"])):raise ValueError("lifecycle wire bounds")
    raw=bytearray()
    for index,line in enumerate(lines[1:-1]):
        item=g0.decode_line(line,PREFIX,CHUNK_WIRE_MAX);check_binding(item,expected)
        if set(item)!={"schema",*expected,"kind","index","raw_base64"} or item["schema"]!=meta["schema"] or item["kind"]!="chunk" or type(item["index"]) is not int or item["index"]!=index:raise ValueError("lifecycle chunk order")
        raw.extend(unb64(item["raw_base64"],CHUNK_MAX))
    if len(raw)!=meta["bytes"] or sha(raw)!=meta["sha256"] or meta["chunks"]!=max(1,(len(raw)+CHUNK_MAX-1)//CHUNK_MAX):raise ValueError("lifecycle raw digest/count")
    terminal=g0.decode_line(lines[-1],PREFIX,16384);document=None
    if meta["payload_form"]=="canonical-document":
        if meta["truncated"]:raise ValueError("truncated canonical lifecycle document")
        document=g0.loads_strict(bytes(raw))
        if canonical(document)!=raw:raise ValueError("lifecycle canonical document")
        validate_document(document,**binding)
        expected_terminal=g0.decode_line(frames(document)[-1],PREFIX,16384)
    else:
        if terminal.get("status")!="incomplete" or terminal.get("diagnostic_error") is None:raise ValueError("lifecycle prefix must remain incomplete")
        check_error(terminal.get("primary_error"));check_error(terminal.get("diagnostic_error"))
        expected_terminal=g0.decode_line(prefix_frames(bytes(raw)+(b"x" if meta["truncated"] else b""),terminal.get("primary_error"),terminal["diagnostic_error"],**binding)[-1],PREFIX,16384)
    if terminal!=expected_terminal or any(terminal.get(key) is not expected_value for key,expected_value in (("observation_only",True),("g0_qualified",False),("product_probes_executed",False),("enospc_tested",False))):raise ValueError("lifecycle terminal binding")
    return document,bytes(raw),terminal

SNAPSHOT_PHASES=("pre-partition","appearance-p1","appearance-p2","original-partition-baseline","table-dump-before","table-dump-after","format-p1-before","format-p1-after","format-p2-before","format-p2-after","mount-p1-before","mount-p1-after","mount-p2-before","mount-p2-after")
def namespace_shape(value):
    if (not isinstance(value,dict) or set(value)!={"path","target","dev","ino"} or value["path"]!="/proc/self/ns/mnt" or not isinstance(value["target"],str)
            or not re.fullmatch(r"mnt:\[[1-9][0-9]{0,19}\]",value["target"]) or not integer(value["dev"]) or not integer(value["ino"]) or value["ino"]==0):raise ValueError("lifecycle namespace shape")
def validate_reached_prefix(value,**binding):
    observer=value["observer"];stop=value["stop"];cleanup=value["cleanup"];snapshots=value["snapshots"]
    if any(type(number) is not int for number in value["preflight"]["budget"].values()):raise ValueError("lifecycle typed budget")
    for key in ("tools_reaped","monitor_reaped","fds_closed","directories_removed"):
        if type(cleanup[key]) is not bool:raise ValueError("lifecycle cleanup booleans")
    if not isinstance(cleanup["errors"],list) or len(cleanup["errors"])>16 or not isinstance(cleanup["unmounts"],list) or len(cleanup["unmounts"])>2:raise ValueError("lifecycle cleanup bounds")
    for error_value in cleanup["errors"]:check_error(error_value)
    for item in cleanup["unmounts"]:
        if not isinstance(item,dict) or set(item)!={"mount","normal_guarded"} or item["mount"] not in ("/mnt/dm-g0/p1","/mnt/dm-g0/p2") or item["normal_guarded"] is not True:raise ValueError("lifecycle cleanup mount receipt")
    for key in ("observed_at_least","truncated"):
        if not isinstance(observer[key],dict) or set(observer[key])!={"stdout","stderr"}:raise ValueError("lifecycle observed stream keys")
    for name in ("stdout","stderr"):
        if (not integer(observer["observed_at_least"][name],MONITOR_MAX+1) or observer["observed_at_least"][name]<observer[name+"_bytes"]
                or type(observer["truncated"][name]) is not bool or observer["truncated"][name]!=(observer["observed_at_least"][name]>observer[name+"_bytes"])):raise ValueError("lifecycle observed stream truth")
    for key in ("started_ns","stopped_ns"):
        if observer[key] is not None and not integer(observer[key]):raise ValueError("lifecycle observer clock")
    if observer["identity"] is not None:
        identity=observer["identity"]
        if not isinstance(identity,dict) or set(identity)!={"pid","start_ticks","pidfd"} or not integer(identity["pid"]) or identity["pid"]==0 or not integer(identity["start_ticks"]) or identity["pidfd"] is not True:raise ValueError("lifecycle owned observer identity")
    if observer["exit"] is not None:
        exited=observer["exit"]
        if (not isinstance(exited,dict) or set(exited)!={"returncode","reaped","eof","fds_closed"} or any(type(exited[k]) is not bool for k in ("reaped","fds_closed"))
                or (exited["returncode"] is not None and (type(exited["returncode"]) is not int or not -128<=exited["returncode"]<=255)) or not isinstance(exited["eof"],list) or len(exited["eof"])>2 or len(set(exited["eof"]))!=len(exited["eof"]) or any(k not in ("stdout","stderr") for k in exited["eof"])):raise ValueError("lifecycle observer exit truth")
    discarded=observer["discarded"]
    for name in ("stdout","stderr"):
        if not integer(discarded[name+"_bytes"],MONITOR_MAX) or not integer(discarded[name+"_records"],MONITOR_MAX) or not isinstance(discarded[name+"_sha256"],str) or not g0.HEX64.fullmatch(discarded[name+"_sha256"]):raise ValueError("lifecycle discard bounds")
    for key in ("first_ns","last_ns"):
        if discarded[key] is not None and not integer(discarded[key]):raise ValueError("lifecycle discarded clock")
    if [item["phase"] for item in snapshots]!=list(SNAPSHOT_PHASES[:len(snapshots)]):raise ValueError("lifecycle snapshot reached prefix")
    initial=None;baseline=None;basepath=None
    if snapshots:
        initial=snapshots[0]["original_facts"]
        if not isinstance(initial,dict) or set(initial)!={"namespace","nvme"}:raise ValueError("lifecycle unpartitioned facts")
        namespace_shape(initial["namespace"]);g0._validate_nvme(initial["nvme"],require_partitions=False,expected_serial="DMG0"+binding["nonce"][:16]);basepath=initial["nvme"]["namespace_path"].removeprefix("/sys")
    if len(snapshots)>=4 and snapshots[3]["original_facts"] is not None:
        baseline=snapshots[3]["original_facts"]
        if not isinstance(baseline,dict) or set(baseline)!={"namespace","nvme"}:raise ValueError("lifecycle original baseline facts")
        namespace_shape(baseline["namespace"]);g0._validate_nvme(baseline["nvme"],require_partitions=True,expected_serial="DMG0"+binding["nonce"][:16])
        if baseline["namespace"]!=initial["namespace"]:raise ValueError("lifecycle namespace baseline replacement")
    for index,item in enumerate(snapshots):
        if index<3:
            if item["current"] is not None or item["native"]!={"status":"not_collected"} or item["initstate"] or item["database"] or item["diff"]:raise ValueError("lifecycle extra early reads")
        else:
            if item["original_facts"] is not None and item["original_facts"]!=baseline:raise ValueError("lifecycle baseline recaptured")
            native=item["native"]
            if native!={"status":"not_collected"}:
                if not isinstance(native,dict) or set(native)!={"trace"} or not isinstance(native["trace"],list) or len(native["trace"])>256:raise ValueError("lifecycle bounded native trace")
                for row in native["trace"]:
                    if not isinstance(row,dict) or set(row)!={"role","stage","stat","raw_base64"} or not isinstance(row["role"],str) or len(row["role"].encode())>512 or not isinstance(row["stage"],str) or len(row["stage"])>128:raise ValueError("lifecycle trace fields")
                    if row["stat"] is not None and (not isinstance(row["stat"],list) or len(row["stat"])!=8 or any(not integer(n) for n in row["stat"])):raise ValueError("lifecycle trace native integers")
                    if row["raw_base64"] is not None:unb64(row["raw_base64"],4096)
            if item["current"] is not None:
                if not isinstance(item["current"],dict) or set(item["current"])!={"namespace","nvme"}:raise ValueError("lifecycle current facts")
                namespace_shape(item["current"]["namespace"])
                if item["diff"]!=g0.guard_diff(item["original_facts"],item["current"]):raise ValueError("lifecycle exact diff")
            elif item["error"] is None:raise ValueError("lifecycle unavailable current without error")
        if item["diff"] and index!=len(snapshots)-1:raise ValueError("lifecycle continued after transition")
    if stop["baseline_captured"]!=(baseline is not None) and stop["diagnostic_error"] is None and not any(item["diagnostic_error"] is not None for item in snapshots):raise ValueError("lifecycle baseline capture truth")
    for item in observer["selected"]:
        if basepath is None or not (item["devpath"]==basepath or item["devpath"].startswith(basepath+"/")):raise ValueError("lifecycle foreign selected event")
        raw=unb64(item["raw_base64"],32768);lines=raw.split(b"\n")
        head=re.fullmatch(rb"(KERNEL|UDEV) *\[([0-9]+)\.([0-9]{6})\] +([a-z]+) +(/devices/[^ ]+) \(block\)",lines[0]);properties={}
        if head is None or not raw.endswith(b"\n\n"):raise ValueError("lifecycle selected raw header")
        for line in lines[1:-2]:
            key,sep,data=line.partition(b"=")
            if not sep or key in properties:raise ValueError("lifecycle selected raw properties")
            properties[key]=data
        source,sec,usec,action,path=[x.decode("ascii") for x in head.groups()]
        if (source!=item["source"] or action!=item["action"] or path!=item["devpath"] or properties.get(b"DEVPATH")!=path.encode() or properties.get(b"SUBSYSTEM")!=b"block"
                or not re.fullmatch(rb"[0-9]+",properties.get(b"SEQNUM",b"")) or type(item["sequence"]) is not int or int(properties[b"SEQNUM"])!=item["sequence"] or int(sec)*1000000+int(usec)!=item["timestamp_us"]):raise ValueError("lifecycle selected exact raw binding")
    for item in observer["diagnostics"]:
        raw=unb64(item["raw_base64"],MONITOR_MAX)
        paths=re.findall(r"/devices/[^\s\"'()\[\]]+",raw.decode("utf-8","strict"))
        if raw not in (BANNER,b"Calling monitor\n") and (not paths or basepath is None or any(not (path==basepath or path.startswith(basepath+"/")) for path in paths)):raise ValueError("lifecycle unclassified raw stderr")
    for command in value["commands"]:
        if type(command["fds_closed"]) is not bool or not integer(command["deadline"],60) or command["deadline"]==0 or not integer(command["start_ns"]) or not integer(command["end_ns"]) or command["end_ns"]<command["start_ns"] or (command["returncode"] is not None and (type(command["returncode"]) is not int or not -128<=command["returncode"]<=255)):raise ValueError("lifecycle typed command outcome")
    if stop["mutation_started"]:
        if initial is None or len(value["commands"])<16 or value["commands"][15]["argv"]!=["/usr/sbin/sfdisk",initial["nvme"]["device"]]:raise ValueError("lifecycle preflight-before-mutation prefix")
    if stop["mutation_started"]:
        if len(value["preflight"]["tools"])!=5 or value["preflight"]["observer_tool"] is None or observer["ready"] is not True:raise ValueError("lifecycle missing pre-mutation facts")
        for index,fact in enumerate(value["preflight"]["tools"]):
            for offset,key in enumerate(("owner_query","version_query")):
                command=value["commands"][index*2+offset];query=fact[key]
                if command["argv"]!=query["argv"] or unb64(command["stdout_base64"],STREAM_MAX)!=query["stdout_text"].encode() or unb64(command["stderr_base64"],STREAM_MAX)!=query["stderr_text"].encode():raise ValueError("lifecycle original tool query binding")
        tool=value["preflight"]["observer_tool"]
        expected_queries=(["/usr/bin/dpkg-query","-S",tool["canonical"]],["/usr/bin/dpkg-query","-W","-f=${binary:Package}\t${Version}\t${Architecture}\n",tool["package"]],[UDEV,"--version"],[UDEV,"--help"],[UDEV,"monitor","--help"])
        if [item["argv"] for item in value["commands"][10:15]]!=list(expected_queries):raise ValueError("lifecycle observer query prefix")
        if any(item["returncode"]!=0 or type(item["returncode"]) is not int or item["reaped"] is not True or item["fds_closed"] is not True or item["eof"]!=[True,True] or item["truncated"] or item["error"] is not None for item in value["commands"][:15]):raise ValueError("lifecycle incomplete pre-mutation query")
        device=initial["nvme"]["device"];parts=(device+"p1",device+"p2");mounts=("/mnt/dm-g0/p1","/mnt/dm-g0/p2")
        normal=[["/usr/sbin/sfdisk",device],["/usr/sbin/sfdisk","--json",device]]+[["/usr/sbin/mkfs.ext4","-F","-m","0","-E","lazy_itable_init=0,lazy_journal_init=0",part] for part in parts]+[["/usr/bin/mount","-t","ext4","-o","rw,nodev,nosuid","--",part,mount] for part,mount in zip(parts,mounts)]
        cursor=0;cleanup_started=False;last_cleanup=-1;attempted=[]
        for command in value["commands"][15:]:
            argv=command["argv"]
            if argv[0]=="/usr/bin/umount":
                cleanup_started=True
                if len(argv)!=3 or argv[1]!="--" or argv[2] not in attempted:raise ValueError("lifecycle cleanup target")
                order=list(reversed(attempted)).index(argv[2])
                if order<=last_cleanup:raise ValueError("lifecycle cleanup order")
                last_cleanup=order
            else:
                if cleanup_started or cursor>=len(normal) or argv!=normal[cursor]:raise ValueError("lifecycle command reached prefix")
                if argv[0]=="/usr/bin/mount":attempted.append(argv[-1])
                cursor+=1
    elif any(item["argv"][0] not in ("/usr/bin/dpkg-query",UDEV) for item in value["commands"]):raise ValueError("lifecycle mutation without flag")
    if stop["status"]=="transition_observed" and (not snapshots or not snapshots[-1]["diff"] or stop["primary_error"] is None):raise ValueError("lifecycle transition without exact diff")
    if stop["status"]=="end_of_setup_no_transition" and (len(snapshots)!=14 or stop["primary_error"] is not None):raise ValueError("lifecycle premature endpoint")

def complete(document):
    if document is None:return False
    observer=document["observer"];clean=document["cleanup"];stop=document["stop"]
    return (stop["diagnostic_error"] is None and stop["status"] in ("transition_observed","end_of_setup_no_transition")
            and clean["monitor_reaped"] is True and clean["tools_reaped"] is True and clean["fds_closed"] is True and clean["directories_removed"] is True and not clean["errors"]
            and observer["ready"] is True and observer["identity"] is not None and observer["exit"] is not None and observer["exit"]["reaped"] is True and observer["exit"]["fds_closed"] is True
            and observer["exit"]["returncode"] in (0,-15) and set(observer["exit"]["eof"])=={"stdout","stderr"} and observer["error"] is None and observer["loss_status"]=="loss_not_detected_not_proved_lossless"
            and all(not flag for flag in observer["truncated"].values())
            and not any(item["diagnostic_error"] is not None or any(file["status"] in ("error","unstable") for file in item["initstate"]+item["database"]) for item in document["snapshots"]))

class MonitorParser:
    """Bounded text decoder; receipt order is never rewritten into causality."""
    def __init__(self,observer,namespace_devpath):
        if not namespace_devpath.startswith("/devices/") or ".." in namespace_devpath.split("/"):raise ValueError("selected DEVPATH")
        self.fact=observer;self.path=namespace_devpath;self.buffers={"stdout":bytearray(),"stderr":bytearray()};self.hashes={name:hashlib.sha256() for name in self.buffers};self.offset=0;self.spans={name:[] for name in self.buffers}
    def selected(self,path):return path==self.path or path.startswith(self.path+"/")
    def discard(self,name,raw,at,first=None):
        fact=self.fact["discarded"];fact[name+"_bytes"]+=len(raw);fact[name+"_records"]+=1;self.hashes[name].update(raw);fact[name+"_sha256"]=self.hashes[name].hexdigest()
        if fact["first_ns"] is None:fact["first_ns"]=at if first is None else first
        fact["last_ns"]=at
    def take(self,name,count):
        raw=bytes(self.buffers[name][:count]);del self.buffers[name][:count]
        spans=self.spans[name];first=spans[0][1];last=first;remaining=count
        while remaining:
            length,at=spans[0];used=min(length,remaining);last=at;remaining-=used
            if used==length:spans.pop(0)
            else:spans[0]=(length-used,at)
        return raw,first,last
    def feed(self,name,raw,at):
        key=name+"_bytes";seen=self.fact[key]+len(raw)
        self.fact["observed_at_least"][name]=min(MONITOR_MAX+1,seen)
        if seen>MONITOR_MAX:
            self.fact[key]=MONITOR_MAX;self.fact["truncated"][name]=True
            raise ValueError("monitor "+name+" cap")
        self.fact[key]=seen
        buf=self.buffers[name]
        if raw:self.spans[name].append((len(raw),at))
        buf.extend(raw)
        if name=="stderr":
            while b"\n" in buf:
                line,first,last=self.take(name,buf.index(b"\n")+1)
                try:text=line.decode("utf-8","strict")
                except UnicodeError:
                    self.discard(name,line,last,first);self.fact["loss_status"]="incomplete_or_unknown";raise ValueError("unclassified observer stderr encoding")
                paths=re.findall(r"/devices/[^\s\"'()\[\]]+",text)
                selected=bool(paths) and all(self.selected(path) for path in paths)
                generic_startup=line==b"Calling monitor\n"
                if not selected and not generic_startup:
                    self.discard(name,line,last,first);self.fact["loss_status"]="incomplete_or_unknown";raise ValueError("unrelated or unclassified observer stderr")
                if len(self.fact["diagnostics"])>=256:raise ValueError("monitor diagnostic count")
                self.fact["diagnostics"].append({"at_ns":last,"raw_base64":b64(line)})
                if re.search(r"Failed|truncated|Invalid|No sender|not from host|disabling|Cannot|Permission denied|No buffer space",text):raise ValueError("monitor receiver error/unknown loss")
            return
        if not self.fact["ready"]:
            prefix=bytes(buf[:len(BANNER)])
            if not BANNER.startswith(prefix) and prefix!=BANNER:raise ValueError("monitor startup banner")
            if len(buf)<len(BANNER):return
            _,_,last=self.take(name,len(BANNER));self.offset=len(BANNER);self.fact["ready"]=True
            self.fact["diagnostics"].append({"at_ns":last,"raw_base64":b64(BANNER)})
        while b"\n\n" in buf:
            record,first,last=self.take(name,buf.index(b"\n\n")+2);start=self.offset;self.offset+=len(record)
            if len(record)>32768:raise ValueError("monitor record cap")
            lines=record[:-2].split(b"\n");header=re.fullmatch(rb"(KERNEL|UDEV) *\[([0-9]+)\.([0-9]{6})\] +([a-z]+) +(/devices/[^ ]+) \(block\)",lines[0])
            if header is None:raise ValueError("monitor event header attribution unavailable")
            source,seconds,micros,action,path=[x.decode("ascii") for x in header.groups()];props={}
            for line in lines[1:]:
                key,sep,value=line.partition(b"=")
                if not sep or not key or key in props:raise ValueError("monitor property shape")
                props[key]=value
            if props.get(b"DEVPATH")!=path.encode() or props.get(b"SUBSYSTEM")!=b"block" or not re.fullmatch(rb"[0-9]+",props.get(b"SEQNUM",b"")):raise ValueError("monitor property binding")
            if not self.selected(path):self.discard(name,record,last,first);continue
            if len(self.fact["selected"])>=256:raise ValueError("monitor selected count")
            classification="namespace" if path==self.path else "partition-p1" if path==self.path+"/"+self.path.rsplit("/",1)[1]+"p1" else "partition-p2" if path==self.path+"/"+self.path.rsplit("/",1)[1]+"p2" else "unexpected-descendant"
            self.fact["selected"].append({"ordinal":len(self.fact["selected"]),"source":source,"action":action,"devpath":path,"classification":classification,"sequence":int(props[b"SEQNUM"]),"timestamp_us":int(seconds)*1000000+int(micros),"first_ns":first,"last_ns":last,"start_offset":start,"end_offset":self.offset,"raw_base64":b64(record)})
            if len(canonical(self.fact))>178864:raise ValueError("monitor serialized evidence cap")
            if classification=="unexpected-descendant":raise ValueError("monitor unexpected selected descendant")
        if len(buf)>32768:raise ValueError("monitor incomplete record cap")
    def finish(self):
        if any(self.buffers.values()):raise ValueError("monitor terminal fragment/parser gap")

SEED_PATHS={"/var/lib/dm-direct-boot/guest_bootstrap.py":(0o500,False),"/var/lib/dm-direct-boot/config.json":(0o400,False),
            "/opt/dm-g0/helpers/guest_g0_setup.py":(0o500,False),"/opt/dm-g0/helpers/g0_policy.py":(0o400,False),
            "/opt/dm-g0/helpers/guest_setup_lifecycle.py":(0o500,False),"/opt/dm-g0/helpers/setup_lifecycle_policy.py":(0o400,False),
            "/var/lib/dm-g0-private/config.json":(0o400,False),"/var/lib/dm-g0-private/setup-lifecycle-config.json":(0o400,False)}
def mode_config(nonce):return {"schema":"dm-setup-lifecycle-config-v1","scope":SCOPE,"nonce":nonce,"observer_seconds":240,"observer_start_seconds":5,"observer_term_seconds":5,"observer_kill_seconds":2}
def validate_mode_config(value,nonce):
    if value!=mode_config(nonce) or any(type(value.get(key)) is not int for key in ("observer_seconds","observer_start_seconds","observer_term_seconds","observer_kill_seconds")):raise ValueError("lifecycle mode configuration")
    return value
def validate_seed_manifest(value):
    if not isinstance(value,dict) or set(value)!={"schema","scope","entries"} or value["schema"]!="dm-setup-lifecycle-seed-manifest-v1" or value["scope"]!=SCOPE or not isinstance(value["entries"],list) or len(value["entries"])!=len(SEED_PATHS):raise ValueError("lifecycle seed manifest")
    seen=set()
    for item in value["entries"]:
        if not isinstance(item,dict) or set(item)!={"path","bytes","sha256","uid","gid","mode","public"} or item["path"] not in SEED_PATHS or item["path"] in seen:raise ValueError("lifecycle seed entry")
        seen.add(item["path"])
        if (not integer(item["bytes"],1048576) or not isinstance(item["sha256"],str) or not g0.HEX64.fullmatch(item["sha256"]) or type(item["uid"]) is not int or item["uid"]!=0 or type(item["gid"]) is not int or item["gid"]!=0
                or type(item["mode"]) is not int or type(item["public"]) is not bool or (item["mode"],item["public"])!=SEED_PATHS[item["path"]]):raise ValueError("lifecycle seed metadata")
    return value
