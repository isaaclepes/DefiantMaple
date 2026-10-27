"""Pure fail-closed policy for the one-device G0 qualification candidate."""

from __future__ import annotations

import hashlib
import json
import os
import re
import base64
import stat

MIB = 1024 * 1024
NVME_BYTES = 128 * MIB
SECTOR_BYTES = 512
SECTORS = 262144
UDEV_RULE_PATH = "/usr/lib/udev/rules.d/50-udev-default.rules"
UDEV_RULE_LINE = 'SUBSYSTEM=="virtio-ports", KERNEL=="vport*", ATTR{name}=="?*", SYMLINK+="virtio-ports/$attr{name}"'
ORDINARY_ID = 12345
BINDING_TRANSPORT = "qemu-smbios-type1-product-serial-v1"
GUARD_PREFIX = b"DMG0GUARD1 "
GUARD_FRAME_MAX = 16384
GUARD_ARTIFACT_MAX = 65536
GUARD_PHASES = ("pre-unmount", "per-unmount-p2", "per-unmount-p1")
INIT_PREFIX=b"DMG0INIT1 "
INIT_MAX=2048
INIT_UDEVADM="/usr/bin/udevadm"
INIT_VERSION="255.4-1ubuntu8.18"
INIT_ORDINALS=(12,13,15)
READY_PREFIX = b"DMG0READY1 "
TOOL_PREFIX = b"DMG0TOOL1 "
QUAL_RAW_PREFIX = b"DMG0QUALRAW1 "
QUAL_RAW_MAX = 65536
QUAL_RAW_META_MAX = 4096
TOOL_RUNS_MAX = 25
TOOL_CHUNK_WIRE_MAX = 32768*4//3+4+768
RESULT_PREFIX = b"DMG0RESULT1 "
ACK_PREFIX = b"DMG0ACK1 "
QUAL_PREFIX = b"DMG0QUAL1 "
MOUNT_PREFIX = b"DMG0MOUNT1 "
FRAME_MAX = 64 * 1024
ACK_MAX = 4096
QUAL_PAYLOAD_MAX = 65400
MOUNTINFO_MAX = 32768
MOUNT_PHASES = ("initial","after-p1-mount","after-p2-mount","pre-unmount","after-p2-unmount","after-p1-unmount")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
NONCE = re.compile(r"^[0-9a-f]{32}$")

PRODUCT_ENTRIES = (
    {
        "path": "/opt/dm-g0/source/defiantmaple/__init__.py",
        "bytes": 52,
        "sha256": "dde219d920adbf1e72e092fb87a885bd472f104184427e3a2fc63be8994e95e4",
    },
    {
        "path": "/opt/dm-g0/source/defiantmaple/recovery_storage.py",
        "bytes": 10733,
        "sha256": "1076a6f45aed68bc9eba84fdd6c628ae49fe70cde4062cd70585800994eed9c3",
    },
)


def canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def loads_strict(raw: bytes | str) -> object:
    def pairs(items):
        out = {}
        for key, value in items:
            if key in out: raise ValueError("duplicate JSON key")
            out[key] = value
        return out
    return json.loads(raw, object_pairs_hook=pairs)


def product_entries() -> list[dict]:
    return [dict(entry) for entry in PRODUCT_ENTRIES]


def validate_config(value: object) -> dict:
    fields = {
        "schema", "nonce", "canonical_image_digest_sha256", "binding_transport",
        "nvme_serial", "nvme_bytes", "sector_bytes", "sectors", "ordinary_uid",
        "ordinary_gid", "mounts", "probe_name", "deadlines",
    }
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("G0 config fields")
    if value["schema"] != "dm-g0-config-v1" or value["binding_transport"] != BINDING_TRANSPORT:
        raise ValueError("G0 config schema/transport")
    if not isinstance(value["nonce"], str) or not NONCE.fullmatch(value["nonce"]):
        raise ValueError("G0 nonce")
    if not isinstance(value["canonical_image_digest_sha256"], str) or not HEX64.fullmatch(value["canonical_image_digest_sha256"]):
        raise ValueError("G0 image digest")
    if value["nvme_serial"] != "DMG0" + value["nonce"][:16]:
        raise ValueError("G0 NVMe serial")
    expected_scalars = {
        "nvme_bytes": NVME_BYTES, "sector_bytes": SECTOR_BYTES, "sectors": SECTORS,
        "ordinary_uid": ORDINARY_ID, "ordinary_gid": ORDINARY_ID,
    }
    for key, expected in expected_scalars.items():
        if not isinstance(value[key], int) or isinstance(value[key], bool) or value[key] != expected:
            raise ValueError("G0 config " + key)
    if value["mounts"] != ["/mnt/dm-g0/p1", "/mnt/dm-g0/p2"] or value["probe_name"] != "dm-g0-probe.bin":
        raise ValueError("G0 fixed paths")
    if not isinstance(value["deadlines"],dict) or any(type(item) is not int for item in value["deadlines"].values()) or value["deadlines"] != {
        "dpkg_query": 10, "sfdisk": 20, "mkfs_ext4": 60,
        "mount": 15, "umount": 15, "ordinary_child": 120, "ack": 30,
    }:
        raise ValueError("G0 deadlines")
    return value


def validate_manifest(value: object) -> dict:
    if not isinstance(value, dict) or set(value) != {"schema", "entries"} or value["schema"] != "dm-g0-seed-manifest-v1":
        raise ValueError("G0 manifest fields")
    entries = value["entries"]
    if not isinstance(entries, list) or len(entries) != 8:
        raise ValueError("G0 manifest count")
    names: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or set(entry) != {"path", "bytes", "sha256", "uid", "gid", "mode", "public"}:
            raise ValueError("G0 manifest entry fields")
        path = entry["path"]
        if not isinstance(path, str) or not path.startswith("/") or len(path) > 256 or path in names:
            raise ValueError("G0 manifest path")
        names.add(path)
        if not isinstance(entry["bytes"], int) or isinstance(entry["bytes"], bool) or not 0 <= entry["bytes"] <= MIB:
            raise ValueError("G0 manifest size")
        if not isinstance(entry["sha256"], str) or not HEX64.fullmatch(entry["sha256"]):
            raise ValueError("G0 manifest digest")
        if entry["uid"] != 0 or entry["gid"] != 0 or entry["mode"] not in (0o400, 0o444, 0o500) or not isinstance(entry["public"], bool):
            raise ValueError("G0 manifest metadata")
    exact = {
        "/var/lib/dm-direct-boot/guest_bootstrap.py": (0o500, False),
        "/var/lib/dm-direct-boot/config.json": (0o400, False),
        "/opt/dm-g0/helpers/guest_g0_setup.py": (0o500, False),
        "/opt/dm-g0/helpers/guest_g0_qualify.py": (0o444, True),
        "/opt/dm-g0/helpers/g0_policy.py": (0o400, False),
        "/opt/dm-g0/source/defiantmaple/__init__.py": (0o444, True),
        "/opt/dm-g0/source/defiantmaple/recovery_storage.py": (0o444, True),
        "/var/lib/dm-g0-private/config.json": (0o400, False),
    }
    if names != set(exact):
        raise ValueError("G0 manifest completeness")
    for item in entries:
        if (item["mode"], item["public"]) != exact[item["path"]]: raise ValueError("G0 manifest path policy")
    for expected in PRODUCT_ENTRIES:
        item = next(entry for entry in entries if entry["path"] == expected["path"])
        if any(item[key] != expected[key] for key in ("bytes", "sha256")) or item["public"] is not True:
            raise ValueError("G0 product pin")
    return value


def build_frame(prefix: bytes, value: dict, cap: int) -> bytes:
    payload = canonical(value)
    if not 0 < len(payload) <= cap:
        raise ValueError("G0 frame cap")
    frame=prefix + str(len(payload)).encode() + b" " + sha256(payload).encode() + b" " + payload + b"\n"
    # The console may map the final LF to CRLF. Reserve that one wire byte.
    if len(frame)+1>cap: raise ValueError("G0 wire frame cap")
    return frame


def decode_line(line: bytes, prefix: bytes, cap: int) -> dict:
    if len(line)>cap: raise ValueError("G0 wire frame cap")
    if not line.startswith(prefix):
        raise ValueError("G0 frame prefix")
    if line.endswith(b"\r\n"): body=line[:-2]
    elif line.endswith(b"\n"): body=line[:-1]
    else: raise ValueError("G0 incomplete wire frame")
    parts = body.split(b" ", 3)
    if len(parts) != 4 or parts[0] + b" " != prefix:
        raise ValueError("G0 frame syntax")
    try:
        length_text = parts[1].decode("ascii")
        claimed = parts[2].decode("ascii")
    except UnicodeError as exc:
        raise ValueError("G0 frame header") from exc
    payload = parts[3]
    if (
        not re.fullmatch(r"[1-9][0-9]{0,5}", length_text)
        or int(length_text) != len(payload) or not 0 < len(payload) <= cap
        or not HEX64.fullmatch(claimed) or sha256(payload) != claimed
    ):
        raise ValueError("G0 frame length/digest")
    try:
        value = loads_strict(payload)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("G0 frame JSON") from exc
    if canonical(value) != payload:
        raise ValueError("G0 frame canonical JSON")
    return value


def serial_records(stream: bytes) -> list[bytes]:
    """Split only at LF; preserve embedded CR and an incomplete final fragment."""
    parts=stream.split(b"\n")
    return [part+b"\n" for part in parts[:-1]]+([parts[-1]] if parts[-1] else [])


def parse_serial_frame(stream: bytes, prefix: bytes) -> dict:
    candidates = [line for line in serial_records(stream) if line.startswith(prefix)]
    if len(candidates) != 1:
        raise ValueError("G0 serial frame count")
    return decode_line(candidates[0], prefix, FRAME_MAX)


def build_ack(value: dict) -> bytes:
    payload = canonical(value)
    if not 0 < len(payload) <= ACK_MAX - 96:
        raise ValueError("ACK payload cap")
    header = b"DMG0ACK1 " + str(len(payload)).encode() + b" " + sha256(payload).encode() + b"\n"
    raw = header + payload
    if len(raw) > ACK_MAX:
        raise ValueError("ACK raw cap")
    return raw


def parse_ack(raw: bytes) -> dict:
    if not 0 < len(raw) <= ACK_MAX:
        raise ValueError("ACK cap")
    header, sep, payload = raw.partition(b"\n")
    parts = header.split(b" ")
    if not sep or len(parts) != 3 or parts[0] != b"DMG0ACK1":
        raise ValueError("ACK header")
    try:
        length_text = parts[1].decode("ascii")
        claimed = parts[2].decode("ascii")
    except UnicodeError as exc:
        raise ValueError("ACK header encoding") from exc
    if not re.fullmatch(r"[1-9][0-9]{0,3}", length_text) or int(length_text) != len(payload) or not HEX64.fullmatch(claimed) or sha256(payload) != claimed:
        raise ValueError("ACK length/digest")
    try:
        value = loads_strict(payload)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("ACK JSON") from exc
    if canonical(value) != payload:
        raise ValueError("ACK canonical JSON")
    return value


def parse_qualifier(raw: bytes) -> dict:
    if not 0 < len(raw) <= FRAME_MAX:
        raise ValueError("qualifier record cap")
    header, sep, payload = raw.partition(b"\n")
    parts = header.split(b" ")
    if not sep or len(parts) != 3 or parts[0] != b"DMG0QUAL1":
        raise ValueError("qualifier header")
    try:
        length_text = parts[1].decode("ascii")
        claimed = parts[2].decode("ascii")
    except UnicodeError as exc:
        raise ValueError("qualifier header encoding") from exc
    if (
        not re.fullmatch(r"[1-9][0-9]{0,5}", length_text)
        or int(length_text) != len(payload) or len(payload) > QUAL_PAYLOAD_MAX
        or not HEX64.fullmatch(claimed) or sha256(payload) != claimed
    ):
        raise ValueError("qualifier length/digest")
    try:
        value = loads_strict(payload)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("qualifier JSON") from exc
    if canonical(value) != payload:
        raise ValueError("qualifier canonical JSON")
    required = {"schema", "nonce", "seed_manifest_sha256", "uid", "gid", "product_entries", "partitions", "interpreter", "loaded_stdlib", "ordinary_identity", "fd_inventories"}
    if not isinstance(value, dict) or set(value) != required or value["schema"] != "dm-g0-qualifier-result-v1":
        raise ValueError("qualifier fields")
    if type(value["uid"]) is not int or type(value["gid"]) is not int or value["uid"] != ORDINARY_ID or value["gid"] != ORDINARY_ID or value["product_entries"] != product_entries():
        raise ValueError("qualifier identity/product")
    identities=value["ordinary_identity"]
    if not isinstance(identities,dict) or set(identities)!={"before","after"} or identities["before"]!=identities["after"]: raise ValueError("qualifier ordinary identity phases")
    identity=identities["before"]
    if (not isinstance(identity,dict) or set(identity)!={"uids","gids","supplementary_groups","capabilities","no_new_privs"}
            or identity["uids"]!=[ORDINARY_ID]*3 or identity["gids"]!=[ORDINARY_ID]*3 or any(type(item) is not int for item in identity["uids"]+identity["gids"]) or identity["supplementary_groups"]!=[]
            or type(identity["no_new_privs"]) is not int or identity["no_new_privs"] not in (0,1)): raise ValueError("qualifier ordinary IDs/groups")
    caps=identity["capabilities"]
    if not isinstance(caps,dict) or set(caps)!={"CapInh","CapPrm","CapEff","CapBnd","CapAmb"}: raise ValueError("qualifier capabilities")
    for key,cap in caps.items():
        if not isinstance(cap,str) or not re.fullmatch(r"[0-9a-f]{16}",cap) or (key!="CapBnd" and cap!="0"*16): raise ValueError("qualifier retained privilege")
    inventories=value["fd_inventories"]
    if (not isinstance(inventories,dict) or set(inventories)!={"result_fd","before","after"}
            or not _bounded_int(inventories["result_fd"],127) or inventories["result_fd"]<3
            or inventories["before"]!=inventories["after"]): raise ValueError("qualifier FD inventories")
    entries=inventories["before"]
    if not isinstance(entries,list) or len(entries)!=4: raise ValueError("qualifier FD count")
    observed=[]
    for entry in entries:
        if (not isinstance(entry,dict) or set(entry)!={"fd","mode","target","mnt_id"}
                or not _bounded_int(entry["fd"],127) or not _bounded_int(entry["mode"])
                or not _bounded_int(entry["mnt_id"]) or entry["mnt_id"]==0): raise ValueError("qualifier FD fact")
        observed.append(entry["fd"])
        if entry["fd"] in (0,1,2):
            if entry["mode"]!=stat.S_IFCHR or entry["target"]!="/dev/null": raise ValueError("qualifier stdio FD")
        elif (entry["fd"]!=inventories["result_fd"] or entry["mode"]!=stat.S_IFIFO
              or not isinstance(entry["target"],str) or not re.fullmatch(r"pipe:\[[1-9][0-9]{0,19}\]",entry["target"])):
            raise ValueError("qualifier result FD")
    if observed!=sorted({0,1,2,inventories["result_fd"]}): raise ValueError("qualifier FD membership")
    if not isinstance(value["nonce"], str) or not NONCE.fullmatch(value["nonce"]):
        raise ValueError("qualifier nonce")
    if not isinstance(value["seed_manifest_sha256"], str) or not HEX64.fullmatch(value["seed_manifest_sha256"]):
        raise ValueError("qualifier manifest")
    if not isinstance(value["partitions"], list) or len(value["partitions"]) != 2:
        raise ValueError("qualifier partitions")
    namespace = None
    namespace_fact = None
    for number, item in enumerate(value["partitions"], 1):
        fields = {"partition", "mountpoint", "filesystem", "source", "probe_inode", "probe_bytes", "probe_sha256", "absent_after", "mount_namespace", "fixture_parent_identity"}
        if not isinstance(item, dict) or set(item) != fields:
            raise ValueError("qualifier partition fields")
        match = re.fullmatch(r"/dev/(nvme[0-9]+n[0-9]+)p([12])", item["partition"] if isinstance(item["partition"], str) else "")
        if not match or int(match.group(2)) != number or item["source"] != item["partition"]:
            raise ValueError("qualifier partition identity")
        if namespace is None: namespace = match.group(1)
        if match.group(1) != namespace or item["mountpoint"] != f"/mnt/dm-g0/p{number}" or item["filesystem"] != "ext4":
            raise ValueError("qualifier mount identity")
        if (not _bounded_int(item["probe_inode"]) or item["probe_inode"] == 0 or item["probe_bytes"] != 4096
                or not isinstance(item["probe_sha256"], str) or not HEX64.fullmatch(item["probe_sha256"])
                or item["absent_after"] is not True):
            raise ValueError("qualifier probe")
        ns = item["mount_namespace"]
        if (not isinstance(ns, dict) or set(ns) != {"path", "target", "dev", "ino"}
                or ns["path"] != "/proc/self/ns/mnt" or not isinstance(ns["target"], str)
                or not re.fullmatch(r"mnt:\[[1-9][0-9]{0,19}\]", ns["target"])
                or not _bounded_int(ns["dev"]) or not _bounded_int(ns["ino"]) or ns["ino"] == 0):
            raise ValueError("qualifier mount namespace")
        if namespace_fact is None: namespace_fact = ns
        if ns != namespace_fact: raise ValueError("qualifier namespace mismatch")
        fixture=item["fixture_parent_identity"]
        if (not isinstance(fixture,list) or len(fixture)!=6 or any(not _bounded_int(field) for field in fixture)
                or fixture[1]==0 or fixture[2]!=ORDINARY_ID or fixture[3]!=ORDINARY_ID or fixture[4]!=0o700 or fixture[5]<1):
            raise ValueError("qualifier fixture parent identity")
        content = hashlib.sha256((value["nonce"] + ":" + item["partition"]).encode()).digest() * 128
        if item["probe_sha256"] != sha256(content): raise ValueError("qualifier probe digest")
    interpreter = value["interpreter"]
    if (not isinstance(interpreter, dict) or set(interpreter) != {"path", "bytes", "sha256"}
            or not isinstance(interpreter["path"], str) or not interpreter["path"].startswith("/usr/")
            or not _bounded_int(interpreter["bytes"], 64 * MIB) or interpreter["bytes"] == 0
            or not isinstance(interpreter["sha256"], str) or not HEX64.fullmatch(interpreter["sha256"])):
        raise ValueError("qualifier interpreter")
    if not isinstance(value["loaded_stdlib"], list) or not 1 <= len(value["loaded_stdlib"]) <= 128:
        raise ValueError("qualifier stdlib")
    names = set()
    for item in value["loaded_stdlib"]:
        if (not isinstance(item, dict) or set(item) != {"name", "path", "bytes", "sha256"}
                or not isinstance(item["name"], str) or not 0 < len(item["name"]) <= 256 or item["name"] in names
                or not isinstance(item["path"], str) or not item["path"].startswith("/usr/lib/python") or len(item["path"]) > 512
                or not _bounded_int(item["bytes"], 16 * MIB)
                or (item["bytes"] == 0 and item["sha256"] != sha256(b""))
                or not isinstance(item["sha256"], str) or not HEX64.fullmatch(item["sha256"])):
            raise ValueError("qualifier stdlib entry")
        names.add(item["name"])
    return value


def build_qualifier(value: dict) -> bytes:
    payload=canonical(value)
    if not 0<len(payload)<=QUAL_PAYLOAD_MAX: raise ValueError("qualifier payload cap")
    return b"DMG0QUAL1 "+str(len(payload)).encode()+b" "+sha256(payload).encode()+b"\n"+payload


def validate_qualifier_value(value: object) -> dict:
    if not isinstance(value,dict): raise ValueError("qualifier value")
    return parse_qualifier(build_qualifier(value))


def parse_mountinfo(raw: bytes) -> list[dict]:
    if not 0<len(raw)<=MOUNTINFO_MAX or b"\0" in raw or not raw.endswith(b"\n"): raise ValueError("mountinfo bytes")
    text=raw.decode("utf-8","strict"); records=[]; ids=set(); identities=set()
    def decode(item):
        if re.search(r"\\(?!040|011|012|134)",item): raise ValueError("mountinfo escape")
        return re.sub(r"\\(040|011|012|134)",lambda match:{"040":" ","011":"\t","012":"\n","134":"\\"}[match.group(1)],item)
    for line in text.splitlines():
        before,separator,after=line.partition(" - "); left=before.split(); right=after.split()
        if (not line or not separator or len(left)<6 or len(right)!=3
                or not re.fullmatch(r"[1-9][0-9]{0,19}",left[0]) or not re.fullmatch(r"[1-9][0-9]{0,19}",left[1])
                or not re.fullmatch(r"(?:0|[1-9][0-9]{0,9}):(?:0|[1-9][0-9]{0,9})",left[2])): raise ValueError("mountinfo syntax")
        major_text,minor_text=left[2].split(":")
        if int(major_text)>4294967295 or int(minor_text)>4294967295: raise ValueError("mountinfo device")
        mount_id=int(left[0]); identity=tuple(left+['-']+right)
        if mount_id in ids or identity in identities: raise ValueError("mountinfo duplicate")
        ids.add(mount_id); identities.add(identity)
        records.append({"mount_id":mount_id,"parent_id":int(left[1]),"dev":left[2],"root":decode(left[3]),"mountpoint":decode(left[4]),
                        "mount_options":left[5].split(","),"optional":left[6:],"filesystem":right[0],"source":decode(right[1]),"super_options":right[2].split(",")})
    if not records or len(records)>1024: raise ValueError("mountinfo count")
    return records


def replay_mountinfo(receipts,result,ready):
    """Replay every exact decision snapshot against the bound G0 devices/mounts."""
    if tuple(item["phase"] for item in receipts)!=MOUNT_PHASES: raise ValueError("mountinfo replay order")
    nvme=result["nvme"]; expected=[{key:value for key,value in mount.items() if key!="mounted_root_identity"} for mount in result["mounts"]]
    if ready["nvme"]!=nvme or ready["udev_rule"]!=result["udev_rule"]: raise ValueError("mountinfo NVMe/udev ready/result binding")
    if any(part["mount_namespace"]!=result["mount_namespace"] for part in ready["qualifier"]["partitions"]): raise ValueError("mountinfo qualifier/root namespace binding")
    namespace_dev=str(nvme["dev"][0])+":"+str(nvme["dev"][1])
    for receipt,present in zip(receipts,((),(0,),(0,1),(0,1),(0,),())):
        raw=base64.b64decode(receipt["raw_base64"],validate=True); records=parse_mountinfo(raw)
        if any(item["dev"]==namespace_dev or item["source"]==nvme["device"] for item in records): raise ValueError("namespace unexpectedly mounted")
        for index,(part,mount) in enumerate(zip(nvme["partitions"],expected)):
            dev=str(part["dev"][0])+":"+str(part["dev"][1])
            selected=[item for item in records if item["dev"]==dev or item["source"]==part["path"] or item["mountpoint"]==mount["mountpoint"]]
            if selected!=([mount] if index in present else []): raise ValueError("mountinfo phase replay identity")
    return receipts


def mount_receipt(phase: str, raw: bytes, *, nonce: str, binding: str, manifest_sha256: str) -> dict:
    if (phase not in MOUNT_PHASES or not NONCE.fullmatch(nonce) or not HEX64.fullmatch(binding)
            or not HEX64.fullmatch(manifest_sha256)): raise ValueError("mountinfo binding")
    parse_mountinfo(raw)
    return {"schema":"dm-g0-mountinfo-v1","phase":phase,"nonce":nonce,"binding":binding,"seed_manifest_sha256":manifest_sha256,
            "raw_base64":base64.b64encode(raw).decode("ascii"),"bytes":len(raw),"sha256":sha256(raw)}


def validate_mount_receipt(value: object, *, nonce: str, binding: str, manifest_sha256: str) -> dict:
    if (not isinstance(value,dict) or set(value)!={"schema","phase","nonce","binding","seed_manifest_sha256","raw_base64","bytes","sha256"}
            or value["schema"]!="dm-g0-mountinfo-v1" or value["phase"] not in MOUNT_PHASES
            or value["nonce"]!=nonce or value["binding"]!=binding or value["seed_manifest_sha256"]!=manifest_sha256
            or not isinstance(value["raw_base64"],str)): raise ValueError("mountinfo receipt")
    try: raw=base64.b64decode(value["raw_base64"],validate=True)
    except (ValueError,base64.binascii.Error) as exc: raise ValueError("mountinfo base64") from exc
    if base64.b64encode(raw).decode("ascii")!=value["raw_base64"]: raise ValueError("mountinfo noncanonical base64")
    if value["bytes"]!=len(raw) or value["sha256"]!=sha256(raw): raise ValueError("mountinfo receipt binding")
    parse_mountinfo(raw); return value


def parse_mount_frames(stream: bytes, *, nonce: str, binding: str, manifest_sha256: str) -> list[dict]:
    candidates=[line for line in serial_records(stream) if line.startswith(MOUNT_PREFIX)]
    if len(candidates)!=len(MOUNT_PHASES): raise ValueError("mountinfo frame count")
    receipts=[validate_mount_receipt(decode_line(line,MOUNT_PREFIX,FRAME_MAX),nonce=nonce,binding=binding,manifest_sha256=manifest_sha256) for line in candidates]
    if tuple(item["phase"] for item in receipts)!=MOUNT_PHASES: raise ValueError("mountinfo frame order")
    return receipts


def parse_tool_frames(stream,*,nonce,binding,manifest_sha256,require_complete):
    lines=[line for line in serial_records(stream) if line.startswith(TOOL_PREFIX)]
    if any(not line.endswith(b"\n") for line in lines): raise ValueError("incomplete tool wire frame")
    records=[decode_line(line,TOOL_PREFIX,TOOL_CHUNK_WIRE_MAX) for line in lines]
    cursor=0; receipts=[]
    while cursor<len(records):
        meta=records[cursor]; cursor+=1; ordinal=len(receipts)
        common={"schema":"dm-g0-tool-evidence-v1","nonce":nonce,"binding":binding,"seed_manifest_sha256":manifest_sha256,"ordinal":ordinal}
        fields=set(common)|{"kind","argv","stdin_base64","stdin_bytes","stdin_sha256","streams","returncode","child_reaped","phase","error"}
        if (not isinstance(meta,dict) or set(meta)!=fields or any(meta[key]!=value for key,value in common.items())
                or meta["kind"]!="meta" or type(meta["ordinal"]) is not int or ordinal>=TOOL_RUNS_MAX or len(build_frame(TOOL_PREFIX,meta,4096))>4096): raise ValueError("tool metadata fields")
        if (not isinstance(meta["argv"],list) or not 1<=len(meta["argv"])<=8 or any(not isinstance(item,str) or not 0<len(item.encode())<=512 for item in meta["argv"])
                or sum(len(item.encode()) for item in meta["argv"])>1024 or not _bounded_int(meta["stdin_bytes"],4096)
                or not isinstance(meta["stdin_base64"],str)): raise ValueError("tool command evidence")
        stdin=base64.b64decode(meta["stdin_base64"],validate=True)
        if base64.b64encode(stdin).decode()!=meta["stdin_base64"] or len(stdin)!=meta["stdin_bytes"] or sha256(stdin)!=meta["stdin_sha256"]: raise ValueError("tool stdin evidence")
        if not isinstance(meta["child_reaped"],bool) or meta["phase"] not in {"complete","failure-after-child-cleanup-attempt","failure-before-launch"} or (meta["returncode"] is not None and (type(meta["returncode"]) is not int or not -128<=meta["returncode"]<=255)):
            raise ValueError("tool completion evidence")
        if meta["error"] is not None and (not isinstance(meta["error"],str) or not 0<len(meta["error"])<=600): raise ValueError("tool failure evidence")
        if not isinstance(meta["streams"],dict) or set(meta["streams"])!={"stdout","stderr"}: raise ValueError("tool stream facts")
        raw_streams={}
        for name in ("stdout","stderr"):
            fact=meta["streams"][name]
            if (not isinstance(fact,dict) or set(fact)!={"bytes","sha256","observed_at_least","truncated","eof","chunks"}
                    or not _bounded_int(fact["bytes"],65536) or not _bounded_int(fact["observed_at_least"],65537)
                    or fact["observed_at_least"]<fact["bytes"] or not isinstance(fact["truncated"],bool) or not isinstance(fact["eof"],bool)
                    or fact["truncated"]!=(fact["observed_at_least"]>fact["bytes"])
                    or type(fact["chunks"]) is not int or fact["chunks"] not in (1,2)): raise ValueError("tool stream scalar")
            raw=bytearray()
            for index in range(fact["chunks"]):
                if cursor>=len(records): raise ValueError("incomplete tool chunk sequence")
                item=records[cursor];cursor+=1
                if (not isinstance(item,dict) or set(item)!=set(common)|{"kind","stream","index","raw_base64"}
                        or any(item[key]!=value for key,value in common.items()) or type(item["ordinal"]) is not int or item["kind"]!="chunk" or item["stream"]!=name
                        or type(item["index"]) is not int or item["index"]!=index or not isinstance(item["raw_base64"],str)): raise ValueError("tool chunk identity")
                block=base64.b64decode(item["raw_base64"],validate=True)
                if len(block)>32768 or base64.b64encode(block).decode()!=item["raw_base64"]: raise ValueError("tool chunk bytes")
                raw.extend(block)
            if len(raw)!=fact["bytes"] or sha256(raw)!=fact["sha256"] or fact["chunks"]!=max(1,(len(raw)+32767)//32768): raise ValueError("tool stream digest")
            raw_streams[name]=bytes(raw)
        if require_complete and (meta["phase"]!="complete" or meta["returncode"]!=0 or meta["child_reaped"] is not True or meta["error"] is not None
                or any(not fact["eof"] or fact["truncated"] or fact["observed_at_least"]!=fact["bytes"] for fact in meta["streams"].values())): raise ValueError("failed tool cannot qualify")
        receipts.append({"metadata":meta,"raw_streams":raw_streams})
    if require_complete and len(receipts)!=23: raise ValueError("tool invocation count")
    return receipts


def bind_tool_receipts(receipts,result):
    expected=[]
    for tool in result["tools"]+[result["udev_rule"]]: expected.extend((tool["owner_query"],tool["version_query"]))
    expected.extend(result["commands"])
    if len(receipts)!=len(expected) or len(expected)!=20: raise ValueError("tool receipt count")
    for receipt,value in zip(receipts,expected):
        meta=receipt["metadata"]
        if any(meta[key]!=value[key] for key in ("argv","stdin_bytes","stdin_sha256","returncode")): raise ValueError("tool receipt command binding")
        for name in ("stdout","stderr"):
            if receipt["raw_streams"][name]!=value[name+"_text"].encode(): raise ValueError("tool receipt output binding")
    return receipts


def qualifier_capture_records(raw,*,nonce,binding,manifest_sha256,eof,status,error):
    """Build exact non-success diagnostic facts; never interpret the child record."""
    observed=len(raw); retained=raw[:QUAL_RAW_MAX]
    blocks=[retained[index:index+32768] for index in range(0,len(retained),32768)] or [b""]
    common={"schema":"dm-g0-qualifier-capture-v1","nonce":nonce,"binding":binding,"seed_manifest_sha256":manifest_sha256}
    meta={**common,"kind":"meta","phase":"completed-before-parse" if error is None else "failure-after-cleanup-attempt",
          "bytes":len(retained),"sha256":sha256(retained),"observed_at_least":observed,"truncated":observed>QUAL_RAW_MAX,
          "eof":eof,"reaped":status is not None,"wait_status":status,"error":error,"chunks":len(blocks)}
    return [meta]+[{**common,"kind":"chunk","index":index,"raw_base64":base64.b64encode(block).decode("ascii")} for index,block in enumerate(blocks)]


def parse_qualifier_capture(stream,*,nonce,binding,manifest_sha256):
    lines=[line for line in serial_records(stream) if line.startswith(QUAL_RAW_PREFIX)]
    if not lines: return None
    if not 2<=len(lines)<=3: raise ValueError("qualifier capture frame count")
    meta=decode_line(lines[0],QUAL_RAW_PREFIX,QUAL_RAW_META_MAX)
    common={"schema":"dm-g0-qualifier-capture-v1","nonce":nonce,"binding":binding,"seed_manifest_sha256":manifest_sha256}
    fields=set(common)|{"kind","phase","bytes","sha256","observed_at_least","truncated","eof","reaped","wait_status","error","chunks"}
    if (not isinstance(meta,dict) or set(meta)!=fields or any(meta[key]!=value for key,value in common.items())
            or meta["kind"]!="meta" or meta["phase"] not in {"completed-before-parse","failure-after-cleanup-attempt"}
            or not _bounded_int(meta["bytes"],QUAL_RAW_MAX) or not _bounded_int(meta["observed_at_least"],QUAL_RAW_MAX+1)
            or meta["bytes"]!=min(meta["observed_at_least"],QUAL_RAW_MAX)
            or not isinstance(meta["sha256"],str) or not HEX64.fullmatch(meta["sha256"])
            or type(meta["truncated"]) is not bool or meta["truncated"]!=(meta["observed_at_least"]>QUAL_RAW_MAX)
            or type(meta["eof"]) is not bool or type(meta["reaped"]) is not bool
            or (meta["wait_status"] is not None and not _bounded_int(meta["wait_status"],65535))
            or meta["reaped"]!=(meta["wait_status"] is not None)
            or type(meta["chunks"]) is not int or meta["chunks"]!=max(1,(meta["bytes"]+32767)//32768)):
        raise ValueError("qualifier capture metadata")
    if meta["error"] is not None and (not isinstance(meta["error"],str) or not 0<len(meta["error"].encode("utf-8"))<=512): raise ValueError("qualifier capture error")
    if meta["phase"]=="completed-before-parse":
        if meta["error"] is not None or not meta["eof"] or not meta["reaped"] or meta["wait_status"]!=0 or meta["truncated"]: raise ValueError("qualifier capture completion")
    elif meta["error"] is None: raise ValueError("qualifier capture missing error")
    if len(lines)!=meta["chunks"]+1: raise ValueError("qualifier capture chunk count")
    raw=bytearray()
    for index,line in enumerate(lines[1:]):
        item=decode_line(line,QUAL_RAW_PREFIX,TOOL_CHUNK_WIRE_MAX)
        if (not isinstance(item,dict) or set(item)!=set(common)|{"kind","index","raw_base64"}
                or any(item[key]!=value for key,value in common.items()) or item["kind"]!="chunk"
                or type(item["index"]) is not int or item["index"]!=index or not isinstance(item["raw_base64"],str)):
            raise ValueError("qualifier capture chunk identity")
        block=base64.b64decode(item["raw_base64"],validate=True)
        if len(block)>32768 or base64.b64encode(block).decode("ascii")!=item["raw_base64"]: raise ValueError("qualifier capture chunk bytes")
        raw.extend(block)
    if len(raw)!=meta["bytes"] or sha256(raw)!=meta["sha256"]: raise ValueError("qualifier capture byte digest")
    return {"metadata":meta,"raw":bytes(raw)}


def guard_error(exc):
    name=type(exc).__module__+"."+type(exc).__qualname__
    if len(name.encode("utf-8"))>128: raise ValueError("guard error class cap")
    raw=str(exc).encode("utf-8"); message=raw[:512].decode("utf-8","ignore")
    number=getattr(exc,"errno",None)
    if number is not None and type(number) is not int: raise ValueError("guard error errno type")
    return {"class":name,"message":message,"errno":number,"message_truncated":len(raw)>512}


def validate_guard_error(value):
    if (not isinstance(value,dict) or set(value)!={"class","message","errno","message_truncated"}
            or not isinstance(value["class"],str) or not 0<len(value["class"].encode("utf-8"))<=128
            or not isinstance(value["message"],str) or len(value["message"].encode("utf-8"))>512
            or (value["errno"] is not None and type(value["errno"]) is not int)
            or type(value["message_truncated"]) is not bool): raise ValueError("guard error fields")
    return value


def guard_diff(saved,current):
    out=[]
    def add(path,kind):
        if len(out)>=128 or len(path.encode("utf-8"))>256: raise ValueError("guard diff cap")
        out.append({"path":path,"kind":kind})
    def walk(before,after,path):
        if type(before) is not type(after): add(path,"type_changed")
        elif isinstance(before,dict):
            if any(not isinstance(key,str) for key in list(before)+list(after)): raise ValueError("guard diff key")
            for key in sorted(set(before)|set(after)):
                child=path+"/"+key.replace("~","~0").replace("/","~1")
                if key not in before:add(child,"added")
                elif key not in after:add(child,"removed")
                else:walk(before[key],after[key],child)
        elif isinstance(before,list):
            for index in range(max(len(before),len(after))):
                child=path+"/"+str(index)
                if index>=len(before):add(child,"added")
                elif index>=len(after):add(child,"removed")
                else:walk(before[index],after[index],child)
        elif before!=after:add(path,"value_changed")
    walk(saved,current,"")
    return sorted(out,key=lambda item:(item["path"],item["kind"]))


def guard_operand(status="not_evaluated",saved=None,current=None,*,error=None):
    return {"status":status,"saved":saved,"current":current,
            "diff_paths":guard_diff(saved,current) if status in ("matched","mismatch") else [],"error":error}


def guard_overflow(record,exc):
    error=guard_error(ValueError("guard diagnostic overflow: "+type(exc).__name__))
    return {**record,"decision":"diagnostic_overflow",
            "namespace":guard_operand("not_retained_overflow",error=error),
            "nvme":guard_operand("not_retained_overflow" if record["evaluated"]["nvme"] else "not_evaluated")}


def validate_guard_record(value,*,nonce,binding,manifest_sha256):
    if (not isinstance(value,dict) or set(value)!={"schema","nonce","binding","seed_manifest_sha256","ordinal","phase","evaluated","namespace","nvme","decision"}
            or value["schema"]!="dm-g0-guard-observation-v1" or value["nonce"]!=nonce or value["binding"]!=binding
            or value["seed_manifest_sha256"]!=manifest_sha256 or type(value["ordinal"]) is not int
            or not 0<=value["ordinal"]<3 or value["phase"]!=GUARD_PHASES[value["ordinal"]]
            or not isinstance(value["evaluated"],dict) or set(value["evaluated"])!={"namespace","nvme"}
            or any(type(item) is not bool for item in value["evaluated"].values()) or value["evaluated"]["namespace"] is not True):
        raise ValueError("guard record binding/phase")
    for name in ("namespace","nvme"):
        part=value[name]
        if (not isinstance(part,dict) or set(part)!={"status","saved","current","diff_paths","error"}
                or part["status"] not in ("matched","mismatch","collection_error","not_evaluated","not_retained_overflow")
                or not isinstance(part["diff_paths"],list) or len(part["diff_paths"])>128): raise ValueError("guard operand fields")
        if part["error"] is not None:validate_guard_error(part["error"])
        status=part["status"]
        if status in ("matched","mismatch"):
            if not isinstance(part["saved"],dict) or not isinstance(part["current"],dict) or part["error"] is not None: raise ValueError("guard compared operands")
            if (part["current"]!=part["saved"])!=(status=="mismatch"):raise ValueError("guard equality decision")
            if part["diff_paths"]!=guard_diff(part["saved"],part["current"]):raise ValueError("guard exact diff")
        else:
            if part["current"] is not None or part["diff_paths"]:raise ValueError("guard unavailable current")
            if status=="collection_error":
                if not isinstance(part["saved"],dict) or part["error"] is None:raise ValueError("guard collection error")
            elif part["saved"] is not None:raise ValueError("guard unavailable saved")
            if status=="not_evaluated" and part["error"] is not None:raise ValueError("guard unattempted error")
    ns,nv,decision=value["namespace"]["status"],value["nvme"]["status"],value["decision"]
    matrix={"matched":("matched","matched",True),"namespace_mismatch":("mismatch","not_evaluated",False),
            "nvme_mismatch":("matched","mismatch",True),"namespace_error":("collection_error","not_evaluated",False),
            "nvme_error":("matched","collection_error",True)}
    if decision=="diagnostic_overflow":
        if (ns!="not_retained_overflow" or value["namespace"]["error"] is None
                or nv!=("not_retained_overflow" if value["evaluated"]["nvme"] else "not_evaluated")):
            raise ValueError("guard overflow truth")
    elif decision not in matrix or (ns,nv,value["evaluated"]["nvme"])!=matrix[decision]:raise ValueError("guard short circuit/decision")
    if len(build_frame(GUARD_PREFIX,value,GUARD_FRAME_MAX))>GUARD_FRAME_MAX:raise ValueError("guard wire cap")
    return value


def parse_guard_frames(stream,*,nonce,binding,manifest_sha256):
    tail=stream.rsplit(b"\n",1)[-1]
    if tail and GUARD_PREFIX.startswith(tail):raise ValueError("guard terminal prefix fragment")
    candidates=[line for line in serial_records(stream) if line.startswith(GUARD_PREFIX)]
    if len(candidates)>3:raise ValueError("guard record count")
    records=[]
    for index,line in enumerate(candidates):
        value=validate_guard_record(decode_line(line,GUARD_PREFIX,GUARD_FRAME_MAX),nonce=nonce,binding=binding,manifest_sha256=manifest_sha256)
        if value["ordinal"]!=index:raise ValueError("guard record order")
        records.append(value)
    return records


def bind_guard_records(records,ready,result):
    if len(records)!=3 or any(item["decision"]!="matched" for item in records):raise ValueError("guard incomplete/nonmatched success")
    expected_ns=result["mount_namespace"];expected_nv=result["nvme"]
    if ready["nvme"]!=expected_nv or any(part["mount_namespace"]!=expected_ns for part in ready["qualifier"]["partitions"]):raise ValueError("guard saved source binding")
    for index,item in enumerate(records):
        if item["ordinal"]!=index or item["phase"]!=GUARD_PHASES[index]:raise ValueError("guard success order")
        for name,expected in (("namespace",expected_ns),("nvme",expected_nv)):
            if item[name]["saved"]!=expected or item[name]["current"]!=expected:raise ValueError("guard saved/current success binding")
    return records


def check_initialization_wire(ordinal,metadata,record,wire):
    if ordinal in INIT_ORDINALS and metadata["error"] is None and metadata["returncode"]==0:
        if record["kind"]=="meta":
            if len(wire)+1>1280:raise ValueError("initialization metadata budget")
        elif len(wire)+1-len(record["raw_base64"])>448:raise ValueError("initialization chunk overhead budget")


def validate_initialization(value,*,nonce,binding,manifest_sha256,nvme=None,udev_rule=None):
    if (not isinstance(value,dict) or set(value)!={"schema","nonce","binding","seed_manifest_sha256","tool","targets","ordinals"}
            or value["schema"]!="dm-g0-initialization-v1" or value["nonce"]!=nonce or value["binding"]!=binding or value["seed_manifest_sha256"]!=manifest_sha256
            or value["ordinals"]!=list(INIT_ORDINALS) or any(type(n) is not int for n in value["ordinals"])):raise ValueError("G0 initialization binding")
    tool=value["tool"]
    if (not isinstance(tool,dict) or set(tool)!={"path","identity","sha256","package","version","architecture"} or tool["path"]!=INIT_UDEVADM
            or not isinstance(tool["identity"],list) or len(tool["identity"])!=7 or any(not _bounded_int(n) for n in tool["identity"])
            or not stat.S_ISREG(tool["identity"][2]) or tool["identity"][2]&0o022 or not tool["identity"][2]&0o111
            or tool["identity"][3:6]!=[0,0,1] or tool["identity"][6]==0 or tool["identity"][6]>64*MIB
            or not isinstance(tool["sha256"],str) or not HEX64.fullmatch(tool["sha256"]) or tool["package"] not in ("udev","udev:amd64") or tool["version"]!=INIT_VERSION or tool["architecture"]!="amd64"):raise ValueError("G0 initialization tool")
    if udev_rule is not None and any(tool[key]!=udev_rule["owner"][key] for key in ("package","version","architecture")):raise ValueError("G0 initialization package binding")
    targets=value["targets"]
    if not isinstance(targets,list) or len(targets)!=2:raise ValueError("G0 initialization targets")
    for number,item in enumerate(targets,1):
        if (not isinstance(item,dict) or set(item)!={"number","sysfs_path","dev","database_bytes","database_sha256","initialized_line_base64"}
                or type(item["number"]) is not int or item["number"]!=number or not isinstance(item["sysfs_path"],str)
                or not re.fullmatch(r"/sys/class/block/nvme(?:0|[1-9][0-9]{0,9})n(?:0|[1-9][0-9]{0,9})p"+str(number),item["sysfs_path"])
                or not isinstance(item["dev"],list) or len(item["dev"])!=2 or any(not _bounded_int(n,(1<<32)-1) for n in item["dev"])
                or not _bounded_int(item["database_bytes"],4096) or item["database_bytes"]==0 or not isinstance(item["database_sha256"],str) or not HEX64.fullmatch(item["database_sha256"])
                or not isinstance(item["initialized_line_base64"],str)):raise ValueError("G0 initialization target facts")
        line=base64.b64decode(item["initialized_line_base64"],validate=True)
        if base64.b64encode(line).decode()!=item["initialized_line_base64"] or not re.fullmatch(rb"I:[1-9][0-9]{0,19}\n",line) or len(line)>item["database_bytes"]:raise ValueError("G0 initialization positive I fact")
        if nvme is not None and (item["sysfs_path"]!="/sys/class/block/"+nvme["namespace"]+"p"+str(number) or item["dev"]!=nvme["partitions"][number-1]["dev"]):raise ValueError("G0 initialization selected baseline binding")
    if targets[0]["sysfs_path"][:-1]!=targets[1]["sysfs_path"][:-1]:raise ValueError("G0 initialization shared namespace")
    build_frame(INIT_PREFIX,value,INIT_MAX)
    return value


def parse_initialization(stream,**binding):
    lines=serial_records(stream);candidates=[(index,line) for index,line in enumerate(lines) if line.startswith(INIT_PREFIX)]
    ready=[index for index,line in enumerate(lines) if line.startswith(READY_PREFIX)]
    if len(candidates)!=1 or len(ready)!=1 or candidates[0][0]>=ready[0]:raise ValueError("G0 initialization count/order")
    return validate_initialization(decode_line(candidates[0][1],INIT_PREFIX,INIT_MAX),**binding)


def bind_initialization_tool_receipts(receipts,initialization,stream):
    if len(receipts)!=23 or any(type(item["metadata"]["ordinal"]) is not int or item["metadata"]["ordinal"]!=index for index,item in enumerate(receipts)):raise ValueError("G0 full initialization ordinal order")
    targets=[item["sysfs_path"] for item in initialization["targets"]]
    expected=(["/usr/bin/dpkg-query","-S",INIT_UDEVADM],[INIT_UDEVADM,"wait","--help"],[INIT_UDEVADM,"wait","--initialized=true","--timeout=10",*targets])
    for ordinal,argv,cap in zip(INIT_ORDINALS,expected,(512,1024,256)):
        receipt=receipts[ordinal];meta=receipt["metadata"]
        if (meta["argv"]!=argv or meta["stdin_bytes"]!=0 or meta["stdin_base64"]!="" or meta["stdin_sha256"]!=sha256(b"") or meta["returncode"]!=0 or type(meta["returncode"]) is not int
                or meta["child_reaped"] is not True or meta["phase"]!="complete" or meta["error"] is not None or any(fact["truncated"] or fact["eof"] is not True or fact["bytes"]>cap for fact in meta["streams"].values())):raise ValueError("G0 initialization exact command/completion")
    owner,help,wait=(receipts[index]["raw_streams"] for index in INIT_ORDINALS)
    if owner["stdout"]!=(initialization["tool"]["package"]+": "+INIT_UDEVADM+"\n").encode() or owner["stderr"] or help["stderr"] or any(option not in help["stdout"] for option in (b"wait",b"--initialized=",b"--timeout=")) or wait["stdout"] or wait["stderr"]:raise ValueError("G0 initialization owner/help/wait output")
    new_wire=0;positions=[];init_positions=[]
    for position,line in enumerate(serial_records(stream)):
        if line.startswith(INIT_PREFIX):new_wire+=len(line);init_positions.append(position)
        elif line.startswith(TOOL_PREFIX):
            record=decode_line(line,TOOL_PREFIX,TOOL_CHUNK_WIRE_MAX);positions.append((position,record["ordinal"]))
            if record["ordinal"] in INIT_ORDINALS:
                check_initialization_wire(record["ordinal"],receipts[record["ordinal"]]["metadata"],record,line[:-2]+b"\n" if line.endswith(b"\r\n") else line)
                new_wire+=len(line)
    if len(init_positions)!=1 or not max(position for position,ordinal in positions if ordinal<=15)<init_positions[0]<min(position for position,ordinal in positions if ordinal>=16):raise ValueError("G0 initialization full stream order")
    if new_wire>13368:raise ValueError("G0 initialization aggregate wire budget")
    return [item for index,item in enumerate(receipts) if index not in INIT_ORDINALS]


def validate_sysfs_identity(value):
    if (not isinstance(value,list) or len(value)!=5 or any(not _bounded_int(item) for item in value)
            or value[1]==0 or value[2]!=0 or value[3]!=0 or value[4]&0o022): raise ValueError("sysfs target identity")
    return value


def _validate_nvme(value: object, *, require_partitions: bool, expected_serial: str) -> dict:
    fields = {"controller", "namespace", "device", "controller_path", "namespace_path", "serial", "transport", "bytes", "sector_bytes", "sectors", "dev", "node_identity", "controller_identity", "namespace_identity"}
    if require_partitions: fields.add("partitions")
    if not isinstance(value, dict) or set(value) != fields:
        raise ValueError("G0 NVMe fields")
    for key in ("bytes","sector_bytes","sectors"):
        if not _bounded_int(value[key]): raise ValueError("G0 NVMe typed size")
    for key in ("controller_identity","namespace_identity"): validate_sysfs_identity(value[key])
    controller, namespace = value["controller"], value["namespace"]
    if (not isinstance(controller, str) or not re.fullmatch(r"nvme(?:0|[1-9][0-9]{0,9})", controller)
            or not isinstance(namespace, str) or not re.fullmatch(re.escape(controller) + r"n(?:0|[1-9][0-9]{0,9})", namespace)
            or value["device"] != "/dev/" + namespace or value["serial"] != expected_serial
            or not re.fullmatch(r"DMG0[0-9a-f]{16}", expected_serial)
            or value["transport"] != "pcie" or value["bytes"] != NVME_BYTES
            or value["sector_bytes"] != SECTOR_BYTES or value["sectors"] != SECTORS
            or not isinstance(value["controller_path"], str) or not value["controller_path"].startswith("/sys/devices/")
            or not value["controller_path"].endswith("/nvme/"+controller) or "//" in value["controller_path"] or "/../" in value["controller_path"]
            or value["namespace_path"] != value["controller_path"] + "/" + namespace
            or not isinstance(value["dev"], list) or len(value["dev"]) != 2
            or any(not _bounded_int(item, (1 << 32) - 1) for item in value["dev"])):
        raise ValueError("G0 NVMe identity")
    node=value["node_identity"]
    if (not isinstance(node,list) or len(node)!=8 or any(not _bounded_int(item) for item in node)
            or node[2]!=0 or node[4]&0o002 or node[6:]!=value["dev"] or node[5]!=1): raise ValueError("G0 NVMe node")
    if require_partitions:
        parts = value["partitions"]
        if not isinstance(parts, list) or len(parts) != 2: raise ValueError("G0 NVMe partitions")
        for number, part in enumerate(parts, 1):
            if (not isinstance(part, dict) or set(part) != {"number", "name", "path", "start", "sectors", "dev", "sysfs_path", "node_identity", "sysfs_identity"}
                    or part["number"] != number or part["name"] != namespace + "p" + str(number)
                    or part["path"] != "/dev/" + part["name"]
                    or part["start"] != (2048 if number == 1 else 124928)
                    or part["sectors"] != (122880 if number == 1 else 131072)
                    or part["sysfs_path"] != value["namespace_path"] + "/" + part["name"]
                    or not isinstance(part["dev"], list) or len(part["dev"]) != 2
                    or any(not _bounded_int(item, (1 << 32) - 1) for item in part["dev"])):
                raise ValueError("G0 NVMe partition")
            validate_sysfs_identity(part["sysfs_identity"])
            node=part["node_identity"]
            if (not isinstance(node,list) or len(node)!=8 or any(not _bounded_int(item) for item in node)
                    or node[2]!=0 or node[4]&0o002 or node[5]!=1 or node[6:]!=part["dev"]): raise ValueError("G0 NVMe partition node")
    return value


def _validate_ack_endpoint(value: object) -> dict:
    if (not isinstance(value, dict) or set(value) != {"name", "dev", "inode", "alias_target", "sysfs_canonical"}
            or not isinstance(value["name"], str) or not re.fullmatch(r"vport(?:0|[1-9][0-9]{0,9})p(?:0|[1-9][0-9]{0,9})", value["name"])
            or value["alias_target"] != "../" + value["name"]
            or not isinstance(value["dev"], list) or len(value["dev"]) != 2
            or not isinstance(value["inode"], list) or len(value["inode"]) != 2
            or any(not _bounded_int(item) for item in value["dev"] + value["inode"])
            or value["dev"][0]==0 or value["inode"][1]==0
            or not isinstance(value["sysfs_canonical"], str) or not value["sysfs_canonical"].startswith("/sys/devices/")
            or not value["sysfs_canonical"].endswith("/virtio-ports/"+value["name"])
            or "//" in value["sysfs_canonical"] or "/../" in value["sysfs_canonical"]):
        raise ValueError("G0 ACK endpoint")
    components=re.fullmatch(r"vport([0-9]+)p([0-9]+)",value["name"]).groups()
    if any(int(item)>4294967295 or str(int(item))!=item for item in components): raise ValueError("G0 ACK endpoint selector")
    return value


def validate_status_response(value: object, command_id: str) -> dict:
    expected = {"id": command_id, "return": {"running": False, "singlestep": False, "status": "prelaunch"}}
    if (value != expected or not isinstance(value,dict) or not isinstance(value.get("return"),dict)
            or value["return"].get("running") is not False or value["return"].get("singlestep") is not False):
        raise ValueError("QMP prelaunch status")
    return value


def validate_empty_response(value: object, command_id: str) -> dict:
    if value != {"id": command_id, "return": {}}:
        raise ValueError("QMP empty response")
    return value


_BLOCK_FIELDS = {"device", "qdev", "type", "removable", "locked", "tray_open", "io-status", "inserted"}
_INSERTED_FIELDS = {
    "file", "node-name", "ro", "drv", "backing_file", "backing_file_depth",
    "encrypted", "detect_zeroes", "write_threshold", "cache", "image", "group",
    "bps", "bps_rd", "bps_wr", "iops", "iops_rd", "iops_wr", "iops_size",
    "bps_max", "bps_rd_max", "bps_wr_max", "iops_max", "iops_rd_max",
    "iops_wr_max", "bps_max_length", "bps_rd_max_length", "bps_wr_max_length",
    "iops_max_length", "iops_rd_max_length", "iops_wr_max_length",
}
_IMAGE_FIELDS = {
    "filename", "format", "virtual-size", "actual-size", "dirty-flag",
    "cluster-size", "format-specific", "snapshots",
}

_RATE_FIELDS = {
    "bps", "bps_rd", "bps_wr", "iops", "iops_rd", "iops_wr", "iops_size",
    "bps_max", "bps_rd_max", "bps_wr_max", "iops_max", "iops_rd_max",
    "iops_wr_max", "bps_max_length", "bps_rd_max_length", "bps_wr_max_length",
    "iops_max_length", "iops_rd_max_length", "iops_wr_max_length",
}


def _bounded_int(value: object, upper: int = (1 << 63) - 1) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and 0 <= value <= upper


def validate_mapping_response(value: object, command_id: str, raw_path: str, *, require_full: bool = False) -> dict:
    """Validate documented query-block fields; first unobserved shape fails."""
    if (
        not isinstance(value, dict) or set(value) != {"id", "return"}
        or value["id"] != command_id or not isinstance(value["return"], list)
        or not 1 <= len(value["return"]) <= 8
    ):
        raise ValueError("QMP mapping envelope")
    matches = []
    for block in value["return"]:
        if (not isinstance(block, dict) or not set(block).issubset(_BLOCK_FIELDS)
                or not {"device", "type", "removable", "locked"}.issubset(block)):
            raise ValueError("QMP block fields")
        if not isinstance(block["device"], str) or not 0 < len(block["device"]) <= 128:
            raise ValueError("QMP block device")
        if block["type"] != "unknown" or not isinstance(block["removable"], bool) or not isinstance(block["locked"], bool):
            raise ValueError("QMP block scalar")
        if "qdev" in block and (not isinstance(block["qdev"], str) or not 0 < len(block["qdev"]) <= 256):
            raise ValueError("QMP block qdev")
        if "tray_open" in block and not isinstance(block["tray_open"], bool):
            raise ValueError("QMP tray state")
        if "io-status" in block and block["io-status"] not in {"ok", "failed", "nospace"}:
            raise ValueError("QMP io status")
        if block["device"] == "g0data":
            matches.append(block)
    if len(matches) != 1:
        raise ValueError("QMP G0 block count")
    block = matches[0]
    if block["removable"] is not False or block["locked"] is not False or "inserted" not in block:
        raise ValueError("QMP G0 block state")
    inserted = block["inserted"]
    required = {
        "file", "node-name", "ro", "drv", "encrypted", "backing_file_depth",
        "detect_zeroes", "bps", "bps_rd", "bps_wr", "iops", "iops_rd",
        "iops_wr", "image", "cache", "write_threshold",
    }
    if not isinstance(inserted, dict) or not set(inserted).issubset(_INSERTED_FIELDS) or not required.issubset(inserted):
        raise ValueError("QMP inserted fields")
    if (
        inserted["file"] != raw_path or inserted["drv"] != "raw"
        or inserted["ro"] is not False or inserted["encrypted"] is not False
        or not _bounded_int(inserted["backing_file_depth"], 0) or "backing_file" in inserted
        or inserted["detect_zeroes"] != "off" or not _bounded_int(inserted["write_threshold"], 0)
        or not isinstance(inserted["node-name"], str) or not 0 < len(inserted["node-name"]) <= 128
    ):
        raise ValueError("QMP G0 mapping")
    for field in _RATE_FIELDS & set(inserted):
        if not _bounded_int(inserted[field]) or inserted[field] != 0:
            raise ValueError("QMP throttle field")
    cache = inserted["cache"]
    if (not isinstance(cache,dict) or set(cache)!={"writeback","direct","no-flush"}
            or cache["writeback"] is not True or cache["direct"] is not True or cache["no-flush"] is not False):
        raise ValueError("QMP cache fields")
    if "group" in inserted and (not isinstance(inserted["group"], str) or not 0 < len(inserted["group"]) <= 128):
        raise ValueError("QMP throttle group")
    image = inserted["image"]
    required_image = {"filename", "format", "virtual-size", "actual-size"}
    if not isinstance(image, dict) or not set(image).issubset(_IMAGE_FIELDS) or not required_image.issubset(image):
        raise ValueError("QMP G0 image fields")
    if (image["filename"] != raw_path or image["format"] != "raw"
            or not _bounded_int(image["virtual-size"], NVME_BYTES) or image["virtual-size"] != NVME_BYTES):
        raise ValueError("QMP G0 image mapping")
    actual = image["actual-size"]
    if not isinstance(actual, int) or isinstance(actual, bool) or not 0 <= actual <= NVME_BYTES:
        raise ValueError("QMP G0 allocation")
    if require_full and actual != NVME_BYTES: raise ValueError("QMP initial G0 allocation")
    if "snapshots" in image and image["snapshots"] != []:
        raise ValueError("QMP G0 snapshots")
    if "dirty-flag" in image and image["dirty-flag"] is not False:
        raise ValueError("QMP G0 dirty flag")
    if "cluster-size" in image and not _bounded_int(image["cluster-size"], NVME_BYTES):
        raise ValueError("QMP G0 cluster size")
    if "format-specific" in image: raise ValueError("QMP raw format-specific unreviewed")
    return {"device": "g0data", "file": raw_path, "node-name": inserted["node-name"], "actual-size": actual}


def validate_mapping_identity(before,after):
    """Mapping identity is stable; exact allocation observations remain bounded."""
    fields={"device","file","node-name","actual-size"}
    for value in (before,after):
        if not isinstance(value,dict) or set(value)!=fields:raise ValueError("QMP mapping identity fields")
        if not _bounded_int(value["actual-size"],NVME_BYTES):raise ValueError("QMP mapping allocation bound")
    if before["actual-size"]!=NVME_BYTES:raise ValueError("QMP initial G0 allocation")
    keys=("device","file","node-name")
    if any(before[key]!=after[key] for key in keys):raise ValueError("QMP G0 mapping identity changed")
    return after


def validate_async_event(
    value: object, *, allow_resume: bool, allow_vserport: bool, allow_shutdown: bool,
) -> dict:
    if not isinstance(value, dict) or not isinstance(value.get("event"), str):
        raise ValueError("QMP async message")
    if not set(value).issubset({"event", "data", "timestamp"}) or "timestamp" not in value:
        raise ValueError("QMP event fields")
    timestamp = value["timestamp"]
    if not isinstance(timestamp, dict) or set(timestamp) != {"seconds", "microseconds"}:
        raise ValueError("QMP timestamp")
    if any(not isinstance(timestamp[key], int) or isinstance(timestamp[key], bool) or timestamp[key] < 0 for key in timestamp):
        raise ValueError("QMP timestamp scalar")
    if timestamp["microseconds"] > 999999: raise ValueError("QMP timestamp microseconds")
    name = value["event"]
    if name == "RESUME" and allow_resume and "data" not in value:
        return value
    if name == "VSERPORT_CHANGE" and allow_vserport:
        data=value.get("data")
        if not isinstance(data,dict) or set(data)!={"id","open"} or data["id"]!="g0port" or not isinstance(data["open"],bool):
            raise ValueError("QMP virtio-port event")
        return value
    if name == "SHUTDOWN" and allow_shutdown:
        data=value.get("data")
        if not isinstance(data,dict) or set(data)!={"guest","reason"} or data["guest"] is not True or data["reason"]!="guest-shutdown":
            raise ValueError("QMP shutdown event")
        return value
    raise ValueError("unreviewed QMP event")


def validate_ack(value: object, *, nonce: str, binding: str, ready_digest: str, pre_digest: str, post_digest: str) -> dict:
    required = {"schema", "nonce", "binding", "binding_transport", "ready_sha256", "pre_mapping_sha256", "post_mapping_sha256"}
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("ACK fields")
    if value != {
        "schema": "dm-g0-ack-v1", "nonce": nonce, "binding": binding,
        "binding_transport": BINDING_TRANSPORT, "ready_sha256": ready_digest,
        "pre_mapping_sha256": pre_digest, "post_mapping_sha256": post_digest,
    }:
        raise ValueError("ACK binding")
    return value


def validate_ready(value: object, *, nonce: str, binding: str, manifest_sha256: str, setup_sha256: str, qualify_sha256: str) -> dict:
    required = {"schema", "nonce", "binding", "binding_transport", "seed_manifest_sha256", "setup_sha256", "qualify_sha256", "product_entries", "qualifier_sha256", "qualifier_bytes", "qualifier", "nvme", "ack_endpoint", "udev_rule"}
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("G0 ready fields")
    if (value["schema"] != "dm-g0-ready-v1" or value["nonce"] != nonce or value["binding"] != binding
            or value["binding_transport"] != BINDING_TRANSPORT or value["seed_manifest_sha256"] != manifest_sha256
            or value["setup_sha256"] != setup_sha256 or value["qualify_sha256"] != qualify_sha256
            or value["product_entries"] != product_entries() or not isinstance(value["qualifier_sha256"], str)
            or not HEX64.fullmatch(value["qualifier_sha256"])):
        raise ValueError("G0 ready binding")
    qualifier=validate_qualifier_value(value["qualifier"]); raw=build_qualifier(qualifier)
    if (value["qualifier_bytes"]!=len(raw) or value["qualifier_sha256"]!=sha256(raw)
            or qualifier["nonce"]!=nonce or qualifier["seed_manifest_sha256"]!=manifest_sha256):
        raise ValueError("G0 ready qualifier binding")
    nvme=_validate_nvme(value["nvme"], require_partitions=True,expected_serial="DMG0"+nonce[:16])
    for observed,part in zip(qualifier["partitions"],nvme["partitions"]):
        if (observed["partition"]!=part["path"] or observed["mountpoint"]!="/mnt/dm-g0/p"+str(part["number"])
                or observed["fixture_parent_identity"][0]!=os.makedev(part["dev"][0],part["dev"][1])):
            raise ValueError("G0 ready qualifier/NVMe binding")
    _validate_ack_endpoint(value["ack_endpoint"])
    validate_udev_rule(value["udev_rule"])
    return value


def _validate_tool_result(value: object) -> dict:
    fields = {"argv", "stdin_sha256", "stdin_bytes", "stdout_sha256", "stdout_bytes", "stdout_text", "stderr_sha256", "stderr_bytes", "stderr_text", "returncode"}
    if (not isinstance(value, dict) or set(value) != fields or not isinstance(value["argv"], list)
            or not 1 <= len(value["argv"]) <= 8 or any(not isinstance(item, str) or not 0 < len(item) <= 512 for item in value["argv"])
            or type(value["returncode"]) is not int or value["returncode"] != 0):
        raise ValueError("G0 tool query result")
    if (not _bounded_int(value["stdin_bytes"],4096) or not isinstance(value["stdin_sha256"],str)
            or not HEX64.fullmatch(value["stdin_sha256"])): raise ValueError("G0 tool stdin")
    for prefix in ("stdout", "stderr"):
        text = value[prefix + "_text"]
        if (not isinstance(text, str) or len(text.encode("utf-8")) != value[prefix + "_bytes"]
                or not _bounded_int(value[prefix + "_bytes"], 65536)
                or not isinstance(value[prefix + "_sha256"], str) or not HEX64.fullmatch(value[prefix + "_sha256"])
                or sha256(text.encode()) != value[prefix + "_sha256"]):
            raise ValueError("G0 tool query stream")
    return value


def _validate_tool_fact(value: object) -> dict:
    fields = {"path", "bytes", "sha256", "mode", "requested", "requested_type", "requested_target", "owner", "owner_query", "version_query"}
    if (not isinstance(value, dict) or set(value) != fields or value["requested"] not in {
            "/usr/sbin/sfdisk", "/usr/sbin/mkfs.ext4", "/usr/bin/mount", "/usr/bin/umount", "/usr/bin/dpkg-query", UDEV_RULE_PATH}
            or value["requested_type"] not in {"regular", "symlink"}
            or (value["requested_type"] == "regular") != (value["requested_target"] is None)
            or (value["requested_target"] is not None and (not isinstance(value["requested_target"], str) or not 0 < len(value["requested_target"]) <= 512))
            or not isinstance(value["path"], str) or not value["path"].startswith("/usr/")
            or not _bounded_int(value["bytes"], 64 * MIB) or value["bytes"] == 0
            or not isinstance(value["sha256"], str) or not HEX64.fullmatch(value["sha256"])
            or not isinstance(value["mode"], int) or isinstance(value["mode"], bool) or value["mode"] & 0o022):
        raise ValueError("G0 tool fact")
    owner = value["owner"]
    if (not isinstance(owner, dict) or set(owner) != {"package", "version", "architecture"}
            or any(not isinstance(owner[key], str) or not 0 < len(owner[key]) <= 512 for key in owner)):
        raise ValueError("G0 tool package")
    _validate_tool_result(value["owner_query"]); _validate_tool_result(value["version_query"])
    empty=sha256(b"")
    if (value["owner_query"]["argv"] != ["/usr/bin/dpkg-query", "-S", value["path"]]
            or value["owner_query"]["stdin_bytes"]!=0 or value["owner_query"]["stdin_sha256"]!=empty or value["owner_query"]["stderr_text"]):
        raise ValueError("G0 owner query binding")
    owner_line=value["owner_query"]["stdout_text"]
    if owner_line.count("\n")!=1 or not owner_line.endswith("\n") or ": " not in owner_line: raise ValueError("G0 owner record")
    package,owned_path=owner_line.rstrip("\n").split(": ",1)
    if package!=owner["package"] or owned_path!=value["path"]: raise ValueError("G0 owner record binding")
    expected_argv=["/usr/bin/dpkg-query", "-W", "-f=${binary:Package}\t${Version}\t${Architecture}\n", package]
    version=value["version_query"]
    if (version["argv"]!=expected_argv or version["stdin_bytes"]!=0 or version["stdin_sha256"]!=empty
            or version["stderr_text"]): raise ValueError("G0 version query binding")
    fields=version["stdout_text"].rstrip("\n").split("\t")
    if version["stdout_text"].count("\n")!=1 or fields!=[owner["package"],owner["version"],owner["architecture"]]: raise ValueError("G0 version record binding")
    return value


def validate_udev_rule(value):
    if not isinstance(value,dict) or "raw_base64" not in value: raise ValueError("udev rule fields")
    fact={key:item for key,item in value.items() if key!="raw_base64"}
    _validate_tool_fact(fact)
    if fact["requested"]!=UDEV_RULE_PATH or fact["path"]!=UDEV_RULE_PATH or fact["requested_type"]!="regular" or fact["bytes"]>16384:
        raise ValueError("udev rule path/cap")
    if not isinstance(value["raw_base64"],str): raise ValueError("udev rule base64")
    try: raw=base64.b64decode(value["raw_base64"],validate=True)
    except Exception as exc: raise ValueError("udev rule bytes") from exc
    if (base64.b64encode(raw).decode("ascii")!=value["raw_base64"] or len(raw)!=fact["bytes"] or sha256(raw)!=fact["sha256"]
            or raw.splitlines().count(UDEV_RULE_LINE.encode())!=1
            or sum(b'SUBSYSTEM=="virtio-ports"' in line for line in raw.splitlines())!=1): raise ValueError("udev rule content binding")
    return value


def _validate_partition_table(value: object, device: str) -> dict:
    allowed={"label","id","device","unit","firstlba","lastlba","sectorsize","partitions"}
    if (not isinstance(value,dict) or not set(value).issubset(allowed)
            or not {"label","device","unit","sectorsize","partitions"}.issubset(value)
            or value["label"]!="gpt" or value["device"]!=device or value["unit"]!="sectors" or value["sectorsize"]!=SECTOR_BYTES):
        raise ValueError("G0 partition table")
    for field in {"firstlba","lastlba"}&set(value):
        if not _bounded_int(value[field],SECTORS): raise ValueError("G0 table LBA")
    if "id" in value and (not isinstance(value["id"],str) or not 0<len(value["id"])<=128): raise ValueError("G0 table id")
    parts=value["partitions"]
    if not isinstance(parts,list) or len(parts)!=2: raise ValueError("G0 table partition count")
    guid="0FC63DAF-8483-4772-8E79-3D69D8477DE4"
    for number,(item,start,size) in enumerate(zip(parts,(2048,124928),(122880,131072)),1):
        allowed_part={"node","start","size","type","uuid","name","attrs"}
        if (not isinstance(item,dict) or not set(item).issubset(allowed_part)
                or not {"node","start","size","type"}.issubset(item)
                or item["node"]!=device+"p"+str(number) or item["start"]!=start or item["size"]!=size
                or not isinstance(item["type"],str) or item["type"].upper()!=guid):
            raise ValueError("G0 table partition")
        for field in set(item)-{"node","start","size","type"}:
            if not isinstance(item[field],str) or len(item[field])>128: raise ValueError("G0 table partition optional")
    return value


def _validate_mount(value: object, part: dict) -> dict:
    fields={"mount_id","parent_id","dev","root","mountpoint","mount_options","optional","filesystem","source","super_options","mounted_root_identity"}
    if (not isinstance(value,dict) or set(value)!=fields or not _bounded_int(value["mount_id"]) or value["mount_id"]==0
            or not _bounded_int(value["parent_id"]) or value["parent_id"]==0
            or value["dev"]!=str(part["dev"][0])+":"+str(part["dev"][1]) or value["root"]!="/"
            or value["mountpoint"]!="/mnt/dm-g0/p"+str(part["number"]) or value["filesystem"]!="ext4"
            or value["source"]!=part["path"]):
        raise ValueError("G0 mount identity")
    optional=value["optional"]
    if optional!=[] and (not isinstance(optional,list) or len(optional)!=1 or not re.fullmatch(r"shared:[1-9][0-9]{0,9}",optional[0])):
        raise ValueError("G0 mount propagation")
    if (not isinstance(value["mount_options"],list) or len(value["mount_options"])!=len(set(value["mount_options"]))
            or not {"rw","nodev","nosuid"}.issubset(value["mount_options"])
            or not set(value["mount_options"]).issubset({"rw","nodev","nosuid","relatime"})):
        raise ValueError("G0 mount options")
    if (not isinstance(value["super_options"],list) or len(value["super_options"])!=len(set(value["super_options"]))
            or "rw" not in value["super_options"]
            or any(not isinstance(item,str) or not re.fullmatch(r"(?:rw|errors=remount-ro|stripe=[1-9][0-9]{0,9})",item) for item in value["super_options"])):
        raise ValueError("G0 mount super options")
    root_identity=value["mounted_root_identity"]
    if (not isinstance(root_identity,list) or len(root_identity)!=6 or any(not _bounded_int(item) for item in root_identity)
            or root_identity[0]!=os.makedev(part["dev"][0],part["dev"][1]) or root_identity[1]==0
            or root_identity[2]!=0 or root_identity[3]!=0 or root_identity[4]&0o022 or root_identity[5]<1):
        raise ValueError("G0 mounted root identity")
    return value


def validate_g0_result(
    value: object, *, nonce: str, binding: str, manifest_sha256: str,
    setup_sha256: str, qualify_sha256: str, ack_sha256: str, ack_bytes: int,
) -> dict:
    required = {
        "schema", "result", "scope", "nonce", "binding", "binding_transport",
        "seed_manifest_sha256", "setup_sha256", "qualify_sha256", "product_entries",
        "ack_sha256", "ack_bytes", "unmounts", "nvme", "tools", "commands",
        "partition_table", "mount_namespace", "mounts", "root_fd_inventories", "mountinfo", "udev_rule",
    }
    if not isinstance(value, dict) or set(value) != required:
        raise ValueError("G0 result fields")
    if (
        value["schema"] != "dm-g0-result-v1" or value["result"] != "qualified"
        or value["scope"] != "g0-healthy-io-only-no-fill-no-enospc"
        or value["nonce"] != nonce or value["binding"] != binding
        or value["binding_transport"] != BINDING_TRANSPORT
        or value["seed_manifest_sha256"] != manifest_sha256
        or value["setup_sha256"] != setup_sha256 or value["qualify_sha256"] != qualify_sha256
        or value["product_entries"] != product_entries() or value["ack_sha256"] != ack_sha256
        or value["ack_bytes"] != ack_bytes or not _bounded_int(value["ack_bytes"], ACK_MAX) or value["ack_bytes"] == 0
    ):
        raise ValueError("G0 result binding")
    if not isinstance(value["unmounts"], list) or len(value["unmounts"]) != 2:
        raise ValueError("G0 unmount order")
    for expected, item in zip(("p2", "p1"), value["unmounts"]):
        if (not isinstance(item, dict) or set(item) != {"partition", "mountpoint", "normal", "mount_id", "underlying_inode"}
                or item["partition"] != expected or item["mountpoint"] != "/mnt/dm-g0/" + expected
                or item["normal"] is not True or not _bounded_int(item["mount_id"]) or item["mount_id"] == 0
                or not isinstance(item["underlying_inode"], list) or len(item["underlying_inode"]) != 2
                or any(not _bounded_int(number) for number in item["underlying_inode"])):
            raise ValueError("G0 unmount receipt")
    _validate_nvme(value["nvme"], require_partitions=True,expected_serial="DMG0"+nonce[:16])
    _validate_partition_table(value["partition_table"],value["nvme"]["device"])
    validate_udev_rule(value["udev_rule"])
    namespace=value["mount_namespace"]
    if (not isinstance(namespace,dict) or set(namespace)!={"path","target","dev","ino"}
            or namespace["path"]!="/proc/self/ns/mnt" or not isinstance(namespace["target"],str)
            or not re.fullmatch(r"mnt:\[[1-9][0-9]{0,19}\]",namespace["target"])
            or not _bounded_int(namespace["dev"]) or not _bounded_int(namespace["ino"]) or namespace["ino"]==0):
        raise ValueError("G0 mount namespace")
    mounts=value["mounts"]
    if not isinstance(mounts,list) or len(mounts)!=2: raise ValueError("G0 mount count")
    for mount,part in zip(mounts,value["nvme"]["partitions"]): _validate_mount(mount,part)
    if len({mount["mount_id"] for mount in mounts})!=2: raise ValueError("G0 unique mount IDs")
    for unmount,mount in zip(value["unmounts"],reversed(mounts)):
        if unmount["mount_id"]!=mount["mount_id"]: raise ValueError("G0 unmount ID binding")
    inventories=value["root_fd_inventories"]
    both=sorted(item["mount_id"] for item in mounts)
    expected_inventories=[("pre-qualifier",both),("post-qualifier-pre-p2-unmount",both),("pre-p1-unmount",[mounts[0]["mount_id"]])]
    if not isinstance(inventories,list) or len(inventories)!=3: raise ValueError("G0 root FD inventories")
    for inventory,(phase,expected_ids) in zip(inventories,expected_inventories):
        if (not isinstance(inventory,dict) or set(inventory)!={"schema","phase","forbidden_mount_ids","clean","entries"}
                or inventory["schema"]!="dm-g0-root-fd-inventory-v1" or inventory["phase"]!=phase
                or inventory["forbidden_mount_ids"]!=expected_ids or inventory["clean"] is not True
                or not isinstance(inventory["entries"],list) or len(inventory["entries"])>128): raise ValueError("G0 root FD inventory")
        observed=[]
        for item in inventory["entries"]:
            if (not isinstance(item,dict) or set(item)!={"fd","target","type","mnt_id"}
                    or not _bounded_int(item["fd"],4096) or item["fd"] in observed or not isinstance(item["target"],str) or len(item["target"])>512
                    or not _bounded_int(item["type"]) or not _bounded_int(item["mnt_id"]) or item["mnt_id"] in expected_ids): raise ValueError("G0 root FD entry")
            observed.append(item["fd"])
    refs=value["mountinfo"]
    if (not isinstance(refs,list) or len(refs)!=len(MOUNT_PHASES)
            or tuple(item.get("phase") if isinstance(item,dict) else None for item in refs)!=MOUNT_PHASES): raise ValueError("G0 mountinfo references")
    for item in refs:
        if (set(item)!={"phase","bytes","sha256"} or not _bounded_int(item["bytes"],MOUNTINFO_MAX) or item["bytes"]==0
                or not isinstance(item["sha256"],str) or not HEX64.fullmatch(item["sha256"])): raise ValueError("G0 mountinfo reference")
    if not isinstance(value["tools"], list) or len(value["tools"]) != 5:
        raise ValueError("G0 tool result")
    if [item.get("requested") if isinstance(item, dict) else None for item in value["tools"]] != [
            "/usr/sbin/sfdisk", "/usr/sbin/mkfs.ext4", "/usr/bin/mount", "/usr/bin/umount", "/usr/bin/dpkg-query"]:
        raise ValueError("G0 tool order")
    for item in value["tools"]: _validate_tool_fact(item)
    commands=value["commands"]
    if not isinstance(commands,list) or len(commands)!=8: raise ValueError("G0 command count")
    expected=("/usr/sbin/sfdisk","/usr/sbin/sfdisk","/usr/sbin/mkfs.ext4","/usr/sbin/mkfs.ext4","/usr/bin/mount","/usr/bin/mount","/usr/bin/umount","/usr/bin/umount")
    for item in commands: _validate_tool_result(item)
    if [item["argv"][0] for item in commands] != list(expected):
        raise ValueError("G0 command order")
    device=value["nvme"]["device"]; parts=value["nvme"]["partitions"]
    expected_argv=[
        ["/usr/sbin/sfdisk",device],["/usr/sbin/sfdisk","--json",device],
        *[["/usr/sbin/mkfs.ext4","-F","-m","0","-E","lazy_itable_init=0,lazy_journal_init=0",part["path"]] for part in parts],
        *[["/usr/bin/mount","-t","ext4","-o","rw,nodev,nosuid","--",part["path"],"/mnt/dm-g0/p"+str(part["number"])] for part in parts],
        ["/usr/bin/umount","--","/mnt/dm-g0/p2"],["/usr/bin/umount","--","/mnt/dm-g0/p1"],
    ]
    if [item["argv"] for item in commands]!=expected_argv: raise ValueError("G0 exact command argv")
    table=("label: gpt\nunit: sectors\n\n"+f"{device}p1 : start=2048, size=122880, type=0FC63DAF-8483-4772-8E79-3D69D8477DE4\n"+f"{device}p2 : start=124928, size=131072, type=0FC63DAF-8483-4772-8E79-3D69D8477DE4\n").encode()
    if commands[0]["stdin_bytes"]!=len(table) or commands[0]["stdin_sha256"]!=sha256(table): raise ValueError("G0 sfdisk stdin")
    if any(item["stdin_bytes"]!=0 or item["stdin_sha256"]!=sha256(b"") for item in commands[1:]): raise ValueError("G0 unexpected command stdin")
    return value

