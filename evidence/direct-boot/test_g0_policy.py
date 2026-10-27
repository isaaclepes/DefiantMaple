from __future__ import annotations

import ast
import base64
import copy
import contextlib
import hashlib
import importlib.util
import json
import unittest
import os
import stat
import tempfile
import socket
import threading
from unittest import mock
import sys
from pathlib import Path
from types import SimpleNamespace

HERE=Path(__file__).resolve().parent

def load(name):
    spec=importlib.util.spec_from_file_location("test_"+name,HERE/(name+".py")); module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module); return module

g0=load("g0_policy")
host=load("host_controller")
setup=load("guest_g0_setup")
qualify=load("guest_g0_qualify")
finalize=load("finalize")


def strip_v27_setup(tree):
    additions={"initialization_identity","close_initialization_tool","check_initialization_executable","prepare_initialization_tool","wait_selected_initialization"}
    tree.body=[node for node in tree.body if not isinstance(node,ast.FunctionDef) or node.name not in additions]
    class Restore(ast.NodeTransformer):
        def visit_Compare(self,node):
            node=self.generic_visit(node)
            expected=ast.parse('argv[0] not in (*TOOLS,g0.INIT_UDEVADM)',mode="eval").body
            if ast.dump(node)==ast.dump(expected):return ast.parse('argv[0] not in TOOLS',mode="eval").body
            return node
        def visit_Assign(self,node):
            if len(node.targets)==1 and isinstance(node.targets[0],ast.Name):
                name=node.targets[0].id
                if name=="initialization_tool" or name=="initialization":return None
                if name=="appearances":return ast.Expr(value=node.value)
            return self.generic_visit(node)
        def visit_If(self,node):
            if ast.dump(node.test)==ast.dump(ast.parse('initialization_tool is not None',mode="eval").body):return None
            return self.generic_visit(node)
        def visit_Expr(self,node):
            call=node.value
            if isinstance(call,ast.Call):
                if isinstance(call.func,ast.Name) and call.func.id=="close_initialization_tool":return None
                if isinstance(call.func,ast.Attribute) and call.func.attr=="check_initialization_wire":return None
                if isinstance(call.func,ast.Name) and call.func.id=="serial_frame" and ast.dump(call.args[0])==ast.dump(ast.parse('g0.INIT_PREFIX',mode="eval").body):return None
            return self.generic_visit(node)
    return Restore().visit(tree)

def strip_v27_policy(tree):
    additions={"check_initialization_wire","validate_initialization","parse_initialization","bind_initialization_tool_receipts"}
    constants={"INIT_PREFIX","INIT_MAX","INIT_UDEVADM","INIT_VERSION","INIT_ORDINALS"}
    tree.body=[node for node in tree.body if not (isinstance(node,ast.FunctionDef) and node.name in additions) and not (isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) and node.targets[0].id in constants)]
    for node in tree.body:
        if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) and node.targets[0].id=="TOOL_RUNS_MAX":
            assert isinstance(node.value,ast.Constant) and node.value.value==25;node.value.value=22
        if isinstance(node,ast.FunctionDef) and node.name=="parse_tool_frames":
            for child in ast.walk(node):
                if isinstance(child,ast.Compare) and isinstance(child.left,ast.Call) and isinstance(child.left.func,ast.Name) and child.left.func.id=="len" and isinstance(child.left.args[0],ast.Name) and child.left.args[0].id=="receipts" and child.comparators==[]:pass
                if ast.dump(child)==ast.dump(ast.parse('len(receipts)!=23',mode="eval").body):child.comparators[0].value=20
    return tree

class G0PolicyTests(unittest.TestCase):
    nonce="a"*32
    binding="b"*64
    manifest_sha="c"*64
    setup_sha="d"*64
    qualify_sha="e"*64

    def qualifier(self):
        namespace={"path":"/proc/self/ns/mnt","target":"mnt:[42]","dev":4,"ino":42}
        parts=[]
        for number in (1,2):
            partition=f"/dev/nvme0n1p{number}"
            content=hashlib.sha256((self.nonce+":"+partition).encode()).digest()*128
            parts.append({"partition":partition,"mountpoint":f"/mnt/dm-g0/p{number}","filesystem":"ext4","source":partition,
                          "probe_inode":100+number,"probe_bytes":4096,"probe_sha256":hashlib.sha256(content).hexdigest(),
                          "absent_after":True,"mount_namespace":namespace,
                          "fixture_parent_identity":[os.makedev(259,number),200+number,g0.ORDINARY_ID,g0.ORDINARY_ID,0o700,2]})
        return {"schema":"dm-g0-qualifier-result-v1","nonce":self.nonce,"seed_manifest_sha256":self.manifest_sha,
                "uid":g0.ORDINARY_ID,"gid":g0.ORDINARY_ID,"product_entries":g0.product_entries(),"partitions":parts,
                "interpreter":{"path":"/usr/bin/python3.12","bytes":1000,"sha256":"1"*64},
                "ordinary_identity":{phase:{"uids":[g0.ORDINARY_ID]*3,"gids":[g0.ORDINARY_ID]*3,"supplementary_groups":[],
                                                   "capabilities":{key:"0"*16 for key in ("CapInh","CapPrm","CapEff","CapBnd","CapAmb")},"no_new_privs":0} for phase in ("before","after")},
                "fd_inventories":{"result_fd":4,**{phase:[{"fd":fd,"mode":stat.S_IFCHR if fd<3 else stat.S_IFIFO,
                    "target":"/dev/null" if fd<3 else "pipe:[42]","mnt_id":1} for fd in (0,1,2,4)] for phase in ("before","after")}},
                "loaded_stdlib":[ {"name":"hashlib","path":"/usr/lib/python3.12/hashlib.py","bytes":10,"sha256":"2"*64}]}

    def nvme(self):
        return {"controller":"nvme0","namespace":"nvme0n1","device":"/dev/nvme0n1","controller_path":"/sys/devices/pci0000:00/0000:00:03.0/nvme/nvme0",
                "namespace_path":"/sys/devices/pci0000:00/0000:00:03.0/nvme/nvme0/nvme0n1","serial":"DMG0"+self.nonce[:16],"transport":"pcie",
                "controller_identity":[4,20,0,0,0o755],"namespace_identity":[4,21,0,0,0o755],"bytes":g0.NVME_BYTES,"sector_bytes":g0.SECTOR_BYTES,"sectors":g0.SECTORS,"dev":[259,0],"node_identity":[1,10,0,6,0o660,1,259,0],
                "partitions":[
                    {"number":1,"name":"nvme0n1p1","path":"/dev/nvme0n1p1","start":2048,"sectors":122880,"dev":[259,1],"sysfs_path":"/sys/devices/pci0000:00/0000:00:03.0/nvme/nvme0/nvme0n1/nvme0n1p1","node_identity":[1,11,0,6,0o660,1,259,1],"sysfs_identity":[4,22,0,0,0o755]},
                    {"number":2,"name":"nvme0n1p2","path":"/dev/nvme0n1p2","start":124928,"sectors":131072,"dev":[259,2],"sysfs_path":"/sys/devices/pci0000:00/0000:00:03.0/nvme/nvme0/nvme0n1/nvme0n1p2","node_identity":[1,12,0,6,0o660,1,259,2],"sysfs_identity":[4,23,0,0,0o755]},
                ]}

    def ready(self):
        qualifier=self.qualifier(); raw=g0.build_qualifier(qualifier)
        return {"schema":"dm-g0-ready-v1","nonce":self.nonce,"binding":self.binding,"binding_transport":g0.BINDING_TRANSPORT,
                "seed_manifest_sha256":self.manifest_sha,"setup_sha256":self.setup_sha,"qualify_sha256":self.qualify_sha,
                "product_entries":g0.product_entries(),"qualifier_sha256":g0.sha256(raw),"qualifier_bytes":len(raw),"qualifier":qualifier,
                "nvme":self.nvme(),"udev_rule":self.udev_rule(),"ack_endpoint":{"name":"vport0p1","dev":[250,1],"inode":[4,50],"alias_target":"../vport0p1","sysfs_canonical":"/sys/devices/pci0000:00/virtio0/virtio-ports/vport0p1"}}

    def tool_result(self,argv,stdin=b"",stdout="",stderr=""):
        return {"argv":argv,"stdin_bytes":len(stdin),"stdin_sha256":g0.sha256(stdin),"stdout_bytes":len(stdout.encode()),"stdout_sha256":g0.sha256(stdout.encode()),"stdout_text":stdout,
                "stderr_bytes":len(stderr.encode()),"stderr_sha256":g0.sha256(stderr.encode()),"stderr_text":stderr,"returncode":0}

    def tool_fact(self,path,package):
        owner=self.tool_result(["/usr/bin/dpkg-query","-S",path],stdout=f"{package}: {path}\n")
        version=self.tool_result(["/usr/bin/dpkg-query","-W","-f=${binary:Package}\t${Version}\t${Architecture}\n",package],stdout=f"{package}\t1.0-1\tamd64\n")
        return {"path":path,"bytes":100,"sha256":"3"*64,"mode":0o755,"requested":path,"requested_type":"regular","requested_target":None,
                "owner":{"package":package,"version":"1.0-1","architecture":"amd64"},"owner_query":owner,"version_query":version}

    def udev_rule(self):
        raw=(g0.UDEV_RULE_LINE+"\n").encode()
        fact=self.tool_fact(g0.UDEV_RULE_PATH,"udev");fact.update(mode=0o644,bytes=len(raw),sha256=g0.sha256(raw),raw_base64=base64.b64encode(raw).decode())
        return fact

    def result(self):
        nvme=self.nvme(); device=nvme["device"]
        table={"label":"gpt","device":device,"unit":"sectors","sectorsize":512,"partitions":[
            {"node":device+"p1","start":2048,"size":122880,"type":"0FC63DAF-8483-4772-8E79-3D69D8477DE4"},
            {"node":device+"p2","start":124928,"size":131072,"type":"0FC63DAF-8483-4772-8E79-3D69D8477DE4"}]}
        mounts=[]
        for part in nvme["partitions"]:
            mounts.append({"mount_id":40+part["number"],"parent_id":1,"dev":f"{part['dev'][0]}:{part['dev'][1]}","root":"/","mountpoint":f"/mnt/dm-g0/p{part['number']}",
                           "mount_options":["rw","nosuid","nodev","relatime"],"optional":[],"filesystem":"ext4","source":part["path"],"super_options":["rw"],
                           "mounted_root_identity":[os.makedev(*part["dev"]),300+part["number"],0,0,0o755,3]})
        tools=[self.tool_fact(path,"pkg"+str(i)) for i,path in enumerate(("/usr/sbin/sfdisk","/usr/sbin/mkfs.ext4","/usr/bin/mount","/usr/bin/umount","/usr/bin/dpkg-query"))]
        table_input=("label: gpt\nunit: sectors\n\n"+f"{device}p1 : start=2048, size=122880, type=0FC63DAF-8483-4772-8E79-3D69D8477DE4\n"+f"{device}p2 : start=124928, size=131072, type=0FC63DAF-8483-4772-8E79-3D69D8477DE4\n").encode()
        commands=[self.tool_result(["/usr/sbin/sfdisk",device],stdin=table_input),self.tool_result(["/usr/sbin/sfdisk","--json",device])]
        commands += [self.tool_result(["/usr/sbin/mkfs.ext4","-F","-m","0","-E","lazy_itable_init=0,lazy_journal_init=0",part["path"]]) for part in nvme["partitions"]]
        commands += [self.tool_result(["/usr/bin/mount","-t","ext4","-o","rw,nodev,nosuid","--",part["path"],f"/mnt/dm-g0/p{part['number']}"]) for part in nvme["partitions"]]
        commands += [self.tool_result(["/usr/bin/umount","--","/mnt/dm-g0/p2"]),self.tool_result(["/usr/bin/umount","--","/mnt/dm-g0/p1"])]
        value={"schema":"dm-g0-result-v1","result":"qualified","scope":"g0-healthy-io-only-no-fill-no-enospc","nonce":self.nonce,"binding":self.binding,
                "binding_transport":g0.BINDING_TRANSPORT,"seed_manifest_sha256":self.manifest_sha,"setup_sha256":self.setup_sha,"qualify_sha256":self.qualify_sha,
                "product_entries":g0.product_entries(),"ack_sha256":"4"*64,"ack_bytes":100,"unmounts":[
                    {"partition":"p2","mountpoint":"/mnt/dm-g0/p2","normal":True,"mount_id":42,"underlying_inode":[1,12]},
                    {"partition":"p1","mountpoint":"/mnt/dm-g0/p1","normal":True,"mount_id":41,"underlying_inode":[1,11]}],
                "nvme":nvme,"tools":tools,"commands":commands,"udev_rule":self.udev_rule(),"partition_table":table,"mount_namespace":{"path":"/proc/self/ns/mnt","target":"mnt:[42]","dev":4,"ino":42},"mounts":mounts}
        value["root_fd_inventories"]=[{"schema":"dm-g0-root-fd-inventory-v1","phase":phase,"forbidden_mount_ids":ids,"clean":True,
                                      "entries":[{"fd":0,"target":"/dev/null","type":8192,"mnt_id":1}]}
                                     for phase,ids in (("pre-qualifier",[41,42]),("post-qualifier-pre-p2-unmount",[41,42]),("pre-p1-unmount",[41]))]
        value["mountinfo"]=[{"phase":phase,"bytes":10,"sha256":str(index)*64} for index,phase in enumerate(g0.MOUNT_PHASES,1)]
        return value

    def mapping(self):
        cache={"writeback":True,"direct":True,"no-flush":False}
        inserted={"file":"nvme.raw","node-name":"node-g0","ro":False,"drv":"raw","backing_file_depth":0,"encrypted":False,"detect_zeroes":"off",
                  "bps":0,"bps_rd":0,"bps_wr":0,"iops":0,"iops_rd":0,"iops_wr":0,"image":{"filename":"nvme.raw","format":"raw","virtual-size":g0.NVME_BYTES,"actual-size":g0.NVME_BYTES,"dirty-flag":False},
                  "cache":cache,"write_threshold":0}
        return {"id":"map","return":[{"device":"g0data","type":"unknown","removable":False,"locked":False,"inserted":inserted}]}

    def test_mapping_requires_documented_mandatory_typed_fields(self):
        value=self.mapping(); self.assertEqual(g0.validate_mapping_response(value,"map","nvme.raw")["device"],"g0data")
        for mutation in (
            lambda x:x["return"][0].update(type="raw"),
            lambda x:x["return"][0]["inserted"].pop("cache"),
            lambda x:x["return"][0]["inserted"].update({"bps":True}),
            lambda x:x["return"][0]["inserted"]["cache"].update({"direct":False}),
            lambda x:x["return"][0]["inserted"]["image"].update({"children":[]}),
            lambda x:x["return"][0]["inserted"]["image"].update({"format-specific":{"type":"raw","data":{}}}),
        ):
            bad=copy.deepcopy(value); mutation(bad)
            with self.assertRaises(ValueError): g0.validate_mapping_response(bad,"map","nvme.raw")

    def test_duplicate_json_keys_and_extra_ack_bytes_fail(self):
        with self.assertRaises(ValueError): g0.loads_strict('{"id":1,"id":2}')
        ack={"schema":"dm-g0-ack-v1","nonce":self.nonce,"binding":self.binding,"binding_transport":g0.BINDING_TRANSPORT,
             "ready_sha256":"1"*64,"pre_mapping_sha256":"2"*64,"post_mapping_sha256":"3"*64}
        raw=g0.build_ack(ack); self.assertEqual(g0.parse_ack(raw),ack)
        with self.assertRaises(ValueError): g0.parse_ack(raw+b"x")

    def test_live_ready_waits_for_newline_under_arbitrary_chunks(self):
        ready=self.ready(); frame=g0.build_frame(g0.READY_PREFIX,ready,g0.FRAME_MAX)
        observed=bytearray()
        for byte in frame[:-1]:
            observed.append(byte)
            self.assertEqual(host.complete_serial_prefix(bytes(observed)),b"")
        observed.append(frame[-1]); self.assertEqual(host.complete_serial_prefix(bytes(observed)),frame)
        duplicate=frame+frame
        self.assertEqual(sum(line.startswith(g0.READY_PREFIX) for line in host.complete_serial_prefix(duplicate).splitlines()),2)

    def test_qualifier_digest_namespace_and_nested_fields_are_bound(self):
        value=self.qualifier(); raw=g0.build_qualifier(value); self.assertEqual(g0.parse_qualifier(raw),value)
        for path,replacement in ((["partitions",0,"probe_sha256"],"0"*64),(["partitions",0,"mount_namespace","ino"],0),(["interpreter","bytes"],True)):
            bad=copy.deepcopy(value); target=bad
            for key in path[:-1]: target=target[key]
            target[path[-1]]=replacement
            with self.assertRaises(ValueError): g0.validate_qualifier_value(bad)
        for index,replacement in ((2,0),(4,0o755),(5,0)):
            bad=copy.deepcopy(value); bad["partitions"][0]["fixture_parent_identity"][index]=replacement
            with self.assertRaises(ValueError): g0.validate_qualifier_value(bad)

    def test_ready_exposes_and_binds_exact_qualifier(self):
        value=self.ready(); g0.validate_ready(value,nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest_sha,setup_sha256=self.setup_sha,qualify_sha256=self.qualify_sha)
        bad=copy.deepcopy(value); bad["qualifier_bytes"]+=1
        with self.assertRaises(ValueError): g0.validate_ready(bad,nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest_sha,setup_sha256=self.setup_sha,qualify_sha256=self.qualify_sha)

    def test_result_binds_full_commands_table_mounts_and_ack_length(self):
        value=self.result(); g0.validate_g0_result(value,nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest_sha,setup_sha256=self.setup_sha,qualify_sha256=self.qualify_sha,ack_sha256="4"*64,ack_bytes=100)
        for mutate in (
            lambda x:x["commands"][0].update(stdin_sha256="0"*64),
            lambda x:x["commands"][4]["argv"].append("extra"),
            lambda x:x["mounts"][0].update(source="/dev/other"),
            lambda x:x["partition_table"]["partitions"][0].update(start=4096),
            lambda x:x.update(ack_bytes=99),
            lambda x:x["unmounts"][0].update(mount_id=999),
            lambda x:x["mounts"][1].update(mount_id=41),
        ):
            bad=copy.deepcopy(value); mutate(bad)
            with self.assertRaises(ValueError): g0.validate_g0_result(bad,nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest_sha,setup_sha256=self.setup_sha,qualify_sha256=self.qualify_sha,ack_sha256="4"*64,ack_bytes=100)

    def test_mountinfo_raw_frames_are_replayable_ordered_and_strict(self):
        raw=(b"1 1 8:1 / / rw,relatime shared:1 - ext4 /dev/root rw\n"
             b"41 1 259:1 / /mnt/dm-g0/p1 rw,nosuid,nodev,relatime shared:41 - ext4 /dev/nvme0n1p1 rw\n")
        self.assertEqual(len(g0.parse_mountinfo(raw)),2)
        receipts=[g0.mount_receipt(phase,raw,nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest_sha) for phase in g0.MOUNT_PHASES]
        stream=b"".join(g0.build_frame(g0.MOUNT_PREFIX,item,g0.FRAME_MAX) for item in receipts)
        self.assertEqual(g0.parse_mount_frames(stream,nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest_sha),receipts)
        with self.assertRaises(ValueError): g0.parse_mount_frames(stream.rstrip(b"\n"),nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest_sha)
        for bad in (raw.rstrip(b"\n"),raw+raw.splitlines(keepends=True)[0],raw.replace(b"41 1",b"1 1")):
            with self.assertRaises(ValueError): g0.parse_mountinfo(bad)

    def test_nvme_root_disk_group_is_bound_but_world_write_and_wrong_owner_fail(self):
        ready=self.ready(); g0.validate_ready(ready,nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest_sha,setup_sha256=self.setup_sha,qualify_sha256=self.qualify_sha)
        for mutate in (
            lambda value:value["nvme"]["node_identity"].__setitem__(2,1000),
            lambda value:value["nvme"]["node_identity"].__setitem__(4,0o662),
            lambda value:value["nvme"]["partitions"][0]["node_identity"].__setitem__(7,99),
            lambda value:value["nvme"].update(serial="DMG0"+"f"*16),
            lambda value:value["nvme"].update(controller="nvme00"),
        ):
            bad=copy.deepcopy(ready); mutate(bad)
            with self.assertRaises(ValueError): g0.validate_ready(bad,nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest_sha,setup_sha256=self.setup_sha,qualify_sha256=self.qualify_sha)

    def test_root_fd_inventory_rejects_a_deliberately_forbidden_mount_id(self):
        facts=[{"fd":7,"target":"/mnt/dm-g0/p1/fixture/leaked","type":32768,"mnt_id":41}]
        with self.assertRaisesRegex(RuntimeError,"mount-backed root descriptor"):
            setup.validate_root_fd_facts(facts,{41,42},"pre-qualifier")
        receipt=setup.validate_root_fd_facts(facts,{42},"pre-qualifier")
        self.assertTrue(receipt["clean"]); self.assertEqual(receipt["forbidden_mount_ids"],[42])

    def test_selected_nvme_mounted_at_an_unrelated_path_fails_pre_mutation(self):
        snapshot={"records":[{"dev":"259:0","source":"/dev/nvme0n1","mountpoint":"/srv/other"}]}
        with self.assertRaisesRegex(RuntimeError,"selected NVMe already mounted"):
            setup.reject_selected_nvme_mount(snapshot,{"dev":[259,0],"device":"/dev/nvme0n1"})

    def test_second_unmount_rejects_changed_p1_or_new_mount_backed_fd(self):
        part={"number":1,"path":"/dev/nvme0n1p1","dev":[259,1]}
        saved={"mount_id":41,"parent_id":1,"dev":"259:1","root":"/","mountpoint":"/mnt/dm-g0/p1",
               "mount_options":["rw","nosuid","nodev","relatime"],"optional":[],"filesystem":"ext4",
               "source":"/dev/nvme0n1p1","super_options":["rw"]}
        changed=copy.deepcopy(saved); changed["source"]="/dev/other"
        with self.assertRaises((RuntimeError,ValueError)):
            setup.check_pre_unmount_mount({"records":[changed]},"/mnt/dm-g0/p1",part,saved,"dm-g0-probe.bin")
        with self.assertRaisesRegex(RuntimeError,"mount-backed root descriptor"):
            setup.validate_root_fd_facts([{"fd":9,"target":"/mnt/dm-g0/p1/new-leak","type":32768,"mnt_id":41}],{41},"pre-p1-unmount")

    def test_fixture_link_count_must_return_to_saved_mounted_root_before_unmount(self):
        saved=[os.makedev(259,1),300,0,0,0o755,2]
        with_fixture=saved[:-1]+[3]
        with self.assertRaisesRegex(RuntimeError,"mounted root identity changed"):
            setup.require_mounted_root_identity(with_fixture,saved)
        setup.require_mounted_root_identity(saved,saved)

    def test_ordinary_identity_rejects_a_retained_saved_root_id(self):
        with (mock.patch.object(qualify.os,"getuid",return_value=g0.ORDINARY_ID),
              mock.patch.object(qualify.os,"geteuid",return_value=g0.ORDINARY_ID),
              mock.patch.object(qualify.os,"getgid",return_value=g0.ORDINARY_ID),
              mock.patch.object(qualify.os,"getegid",return_value=g0.ORDINARY_ID),
              mock.patch.object(qualify.os,"getresuid",return_value=(g0.ORDINARY_ID,g0.ORDINARY_ID,0)),
              mock.patch.object(qualify.os,"getresgid",return_value=(g0.ORDINARY_ID,)*3)):
            with self.assertRaisesRegex(RuntimeError,"qualifier identity"): qualify.ordinary_identity()

    def test_exact_product_module_set_rejects_a_third_module(self):
        prefix={key:value for key,value in sys.modules.items() if key=="defiantmaple" or key.startswith("defiantmaple.")}
        for key in prefix: sys.modules.pop(key,None)
        try:
            sys.modules["defiantmaple"]=object(); sys.modules["defiantmaple.recovery_storage"]=object()
            qualify.exact_product_modules()
            sys.modules["defiantmaple.extra"]=object()
            with self.assertRaisesRegex(RuntimeError,"unexpected product module set"): qualify.exact_product_modules()
        finally:
            for key in tuple(sys.modules):
                if key=="defiantmaple" or key.startswith("defiantmaple."): sys.modules.pop(key,None)
            sys.modules.update(prefix)

    def test_original_private_parent_must_yield_the_saved_fixture_directory(self):
        class Recovery:
            def __init__(self,wrong): self.wrong=wrong
            def _mount_type(self,path): return "ext4","/dev/nvme0n1p1"
            def _direct_local_block(self,name): return True
            def _local_backing(self,kind,source): return True
            @contextlib.contextmanager
            def private_local_parent(self,leaf):
                fd=os.open(self.wrong,os.O_RDONLY|os.O_DIRECTORY)
                try: yield leaf,fd
                finally: os.close(fd)
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); mount=root/"mount"; fixture=mount/"fixture"; wrong=root/"wrong"
            mount.mkdir(); fixture.mkdir(mode=0o700); wrong.mkdir(mode=0o700)
            with mock.patch.object(qualify,"UID",os.getuid()):
                with self.assertRaisesRegex(RuntimeError,"private parent descriptor"):
                    qualify.probe(Recovery(wrong),"/dev/nvme0n1p1",mount,"dm-g0-probe.bin",self.nonce,{"path":"/proc/self/ns/mnt"})
                fixture.rmdir(); fixture.symlink_to(wrong,target_is_directory=True)
                with self.assertRaisesRegex(RuntimeError,"fixture parent identity"):
                    qualify.probe(Recovery(wrong),"/dev/nvme0n1p1",mount,"dm-g0-probe.bin",self.nonce,{"path":"/proc/self/ns/mnt"})

    def test_seed_parent_walk_rejects_symlink_and_writable_components(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); target=root/"target"; target.mkdir(mode=0o755)
            linked=root/"linked"; linked.symlink_to(target,target_is_directory=True)
            writable=root/"writable"; writable.mkdir(mode=0o777); writable.chmod(0o777)
            for function,path in ((setup.secure_dir,linked),(setup.secure_dir,writable),(qualify.secure_dir,linked),(qualify.secure_dir,writable)):
                with self.assertRaisesRegex(RuntimeError,"directory boundary"): function(path)

    def test_forced_qualifier_cleanup_reaps_the_owned_child_once(self):
        pid=os.fork()
        if pid==0:
            signal=__import__("signal"); signal.signal(signal.SIGTERM,signal.SIG_IGN)
            while True: signal.pause()
        pidfd=None
        try:
            start=setup.proc_start(pid); pidfd=os.pidfd_open(pid,0); reaps=[]; real_waitpid=os.waitpid
            def observed_waitpid(child,options):
                result=real_waitpid(child,options)
                if result[0]==pid: reaps.append(result)
                return result
            with mock.patch.object(setup.os,"waitpid",side_effect=observed_waitpid):
                status=setup.stop_and_reap_qualifier(pid,pidfd,start,None)
            self.assertTrue(os.WIFSIGNALED(status)); self.assertEqual(len(reaps),1)
        finally:
            if pidfd is not None: os.close(pidfd)
            try: os.kill(pid,9)
            except ProcessLookupError: pass
            try: os.waitpid(pid,0)
            except ChildProcessError: pass

    def test_finalizer_requires_g0_and_removal_not_boot_alone(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary); (root/"evidence").mkdir()
            (root/"cgroup-destroy.json").write_text('{"removed":true}')
            base={"schema":"dm-direct-boot-intermediate-v1","boot_success":True,"g0_qualified":True,"g0_file_removed":True}
            for field in ("g0_qualified","g0_file_removed"):
                bad=dict(base); bad[field]=False; (root/"boot-result.json").write_text(json.dumps(bad))
                with mock.patch.object(sys,"argv",["finalize.py","--root",str(root),"--status","success"]),self.assertRaises(RuntimeError): finalize.main()
            (root/"boot-result.json").write_text(json.dumps(base))
            with mock.patch.object(sys,"argv",["finalize.py","--root",str(root),"--status","success"]): finalize.main()
            receipt=json.loads((root/"evidence/receipt.json").read_text())
            self.assertEqual(receipt["schema"],"dm-g0-receipt-v1"); self.assertTrue(receipt["success"])
            self.assertIn("no fill, ENOSPC, E1, or E2",receipt["claim"])

    def test_qmp_numeric_booleans_unknown_events_and_wrong_ids_fail(self):
        for field in ("running","singlestep"):
            value={"id":"status","return":{"running":False,"singlestep":False,"status":"prelaunch"}}
            value["return"][field]=0
            with self.assertRaises(ValueError): g0.validate_status_response(value,"status")
        for field in ("direct","writeback","no-flush"):
            value=self.mapping(); value["return"][0]["inserted"]["cache"][field]=0 if field=="no-flush" else 1
            with self.assertRaises(ValueError): g0.validate_mapping_response(value,"map","nvme.raw")
        for event,data in (("VSERPORT_CHANGE",{"id":"g0port","open":1}),("SHUTDOWN",{"guest":1,"reason":"guest-shutdown"})):
            with self.assertRaises(ValueError): g0.validate_async_event({"event":event,"data":data,"timestamp":{"seconds":0,"microseconds":0}},allow_resume=True,allow_vserport=True,allow_shutdown=True)

    def test_qmp_buffered_resume_after_cont_reply_is_consumed_once(self):
        resume={"event":"RESUME","timestamp":{"seconds":0,"microseconds":0}}
        raw=g0.canonical(resume)+b"\r\n"; events=[]
        self.assertEqual(host.consume_runtime_qmp(bytearray(raw),events),b"")
        self.assertEqual(events,[resume])
        with self.assertRaises(ValueError): host.consume_runtime_qmp(bytearray(raw),events)
        with self.assertRaises(ValueError): host.consume_runtime_qmp(bytearray(b'{"return":{},"id":"wrong"}\r\n'),[])

    def test_ordinary_retained_identity_and_fd_facts_reject_privilege_or_leak(self):
        for mutate in (
            lambda x:x["ordinary_identity"]["before"]["gids"].__setitem__(2,0),
            lambda x:x["ordinary_identity"]["before"]["supplementary_groups"].append(0),
            lambda x:x["ordinary_identity"]["before"]["capabilities"].update(CapEff="0000000000000001"),
            lambda x:x["fd_inventories"]["before"][0].update(target="/mnt/dm-g0/p1/leak"),
            lambda x:x["fd_inventories"]["after"].append({"fd":5,"mode":stat.S_IFREG,"target":"/secret","mnt_id":42}),
        ):
            bad=self.qualifier(); mutate(bad)
            with self.assertRaises(ValueError): g0.validate_qualifier_value(bad)

    def test_transient_listdir_fd_is_filtered_but_real_mount_fd_is_rejected(self):
        def fstat(fd):
            if fd==5: raise OSError(9,"closed listdir descriptor")
            return SimpleNamespace(st_mode=stat.S_IFCHR)
        with mock.patch.object(setup.os,"fstat",side_effect=fstat):
            self.assertEqual(setup.live_fd_names(["0","1","2","4"],{3,4}),{"0","1","2"})
            self.assertEqual(setup.live_fd_names(["0","1","2","3","4","5"],{3,4}),{"0","1","2"})

    def test_sysfs_recheck_rejects_canonical_target_replacement(self):
        link=SimpleNamespace(st_dev=1,st_ino=2,st_mode=stat.S_IFLNK|0o777,st_uid=0,st_gid=0,st_nlink=1)
        held=SimpleNamespace(st_dev=2,st_ino=3,st_mode=stat.S_IFDIR|0o755,st_uid=0,st_gid=0,st_nlink=2)
        replaced=SimpleNamespace(**{**vars(held),"st_ino":4})
        with (mock.patch.object(setup.os,"stat",side_effect=[link,replaced]),mock.patch.object(setup.os,"readlink",return_value="../../devices/node"),mock.patch.object(setup.os,"fstat",return_value=held)):
            with self.assertRaisesRegex(RuntimeError,"sysfs entry changed"): setup.recheck_sysfs_entry(10,"nvme0",link,"../../devices/node",11)

    def test_ack_cleanup_attempts_every_owned_directory_even_after_error(self):
        state={"entryfd":1,"sysroot":Path("/sys/example"),"sysfd":2,"sys_before":object(),"devfd":3,"dev_before":object(),"aliasfd":4,"alias_parent_before":object()}
        with mock.patch.object(setup.os,"close") as close,mock.patch.object(setup,"close_dir",side_effect=[RuntimeError("changed"),None,None]) as close_dir:
            with self.assertRaisesRegex(RuntimeError,"ACK directory cleanup failed"): setup.ack_close(state)
            close.assert_called_once_with(1); self.assertEqual(close_dir.call_count,3)

    def test_tool_post_launch_setup_failure_kills_reaps_and_closes_without_masking(self):
        for failure in ("nonblocking","selector"):
            streams=[mock.Mock(closed=False) for _ in range(3)]
            for index,stream in enumerate(streams): stream.fileno.return_value=10+index
            proc=mock.Mock(pid=100,stdin=streams[0],stdout=streams[1],stderr=streams[2],returncode=-9)
            proc.wait.return_value=-9; selector=mock.Mock()
            block=RuntimeError("injected setup failure")
            with (mock.patch.object(setup.subprocess,"Popen",return_value=proc),mock.patch.object(setup,"proc_start",return_value=42),
                  mock.patch.object(setup.os,"pidfd_open",return_value=20),mock.patch.object(setup.os,"set_blocking",side_effect=block if failure=="nonblocking" else None),
                  mock.patch.object(setup.selectors,"DefaultSelector",return_value=selector),mock.patch.object(setup,"child_same",return_value=True),
                  mock.patch.object(setup,"pidfd_signal") as signal,mock.patch.object(setup.os,"close") as close):
                if failure=="selector": selector.register.side_effect=block
                with self.assertRaisesRegex(RuntimeError,"injected setup failure") as observed: setup.run_tool(["/usr/bin/mount"],timeout=1)
                self.assertIs(observed.exception,block); proc.wait.assert_called_once(); signal.assert_called_once(); close.assert_called_once_with(20)
                for stream in streams: stream.close.assert_called_once()

    def test_udev_rule_raw_bytes_and_package_binding_are_required(self):
        value=self.udev_rule(); g0.validate_udev_rule(value)
        for mutate in (lambda x:x.update(raw_base64=base64.b64encode(b"wrong rule\n").decode()),
                       lambda x:x["owner_query"].update(argv=["/usr/bin/dpkg-query","-S","/other"]),
                       lambda x:x.update(sha256="0"*64)):
            bad=copy.deepcopy(value); mutate(bad)
            with self.assertRaises(ValueError): g0.validate_udev_rule(bad)

    def test_mountinfo_replay_requires_every_expected_phase_and_no_tail_fields(self):
        result=self.result(); ready=self.ready()
        def record(item):
            return (f"{item['mount_id']} {item['parent_id']} {item['dev']} {item['root']} {item['mountpoint']} "+",".join(item["mount_options"])+" - "+item["filesystem"]+" "+item["source"]+" "+",".join(item["super_options"])+"\n").encode()
        root=b"1 1 8:1 / / rw - ext4 /dev/root rw\n"
        raws=[root+b"".join(record(result["mounts"][i]) for i in present) for present in ((),(0,),(0,1),(0,1),(0,),())]
        receipts=[g0.mount_receipt(phase,raw,nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest_sha) for phase,raw in zip(g0.MOUNT_PHASES,raws)]
        g0.replay_mountinfo(receipts,result,ready)
        changed=copy.deepcopy(result);changed["mount_namespace"]["ino"]=99
        with self.assertRaises(ValueError):g0.replay_mountinfo(receipts,changed,ready)
        for index in range(6):
            bad=copy.deepcopy(receipts); wrong=raws[index].replace(b"259:1",b"259:9") if index in (1,2,3,4) else root+b"41 1 259:1 / /wrong rw - ext4 /dev/nvme0n1p1 rw\n"
            bad[index]=g0.mount_receipt(g0.MOUNT_PHASES[index],wrong,nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest_sha)
            with self.assertRaises(ValueError): g0.replay_mountinfo(bad,result,ready)
        with self.assertRaises(ValueError): g0.parse_mountinfo(root.rstrip(b"\n")+b" ignored\n")

    def test_full_wire_frame_cap_includes_framing_overhead(self):
        value={"padding":"x"*100}; payload=g0.canonical(value)
        with self.assertRaisesRegex(ValueError,"wire frame cap"): g0.build_frame(g0.READY_PREFIX,value,len(payload))
        raw=g0.build_frame(g0.READY_PREFIX,value,1000)
        with self.assertRaisesRegex(ValueError,"wire frame cap"): g0.decode_line(raw,g0.READY_PREFIX,len(raw)-1)
        self.assertEqual(g0.decode_line(raw,g0.READY_PREFIX,len(raw)),value)

    def exercise_mocked_guest_main(self,fail_mount=False,guard_failure=None,diagnostic_failure=False,initialization_failure=False):
        # Production orchestration runs with every storage/product/device boundary mocked.
        # Only disposable ordinary directories are created to exercise real mkdir/rmdir nlink changes.
        with tempfile.TemporaryDirectory() as temporary,contextlib.ExitStack() as stack:
            root=Path(temporary)/"mount-root"; mounts=[str(root/"p1"),str(root/"p2")]
            config={"nonce":self.nonce,"mounts":mounts,"nvme_serial":"DMG0"+self.nonce[:16],"probe_name":"dm-g0-probe.bin",
                    "deadlines":{"sfdisk":1,"mkfs_ext4":1,"mount":1,"umount":1,"ack":1,"ordinary_child":1}}
            namespace=self.qualifier()["partitions"][0]["mount_namespace"]; nvme=self.nvme(); active={}; calls=[]; frames=[]; guard_phases=[]; current_phase=[None]
            original_guard=setup.observe_unmount_guard
            def traced_guard(*args,**kwargs):
                guard_phases.append(kwargs["phase"]);current_phase[0]=kwargs["phase"]
                try:return original_guard(*args,**kwargs)
                finally:current_phase[0]=None
            def namespace_read():
                return {**namespace,"ino":99} if guard_failure is not None and current_phase[0]==guard_failure else namespace
            def serial_emit(prefix,value):
                if diagnostic_failure and prefix==g0.GUARD_PREFIX:raise OSError("diagnostic transport failure")
                frames.append((prefix,value))
            saved=self.result()["mounts"]
            for item,mount in zip(saved,mounts): item.pop("mounted_root_identity"); item["mountpoint"]=mount
            def snapshot(): return {"records":list(active.values()),"raw":b"mocked evidence","bytes":15,"sha256":"f"*64}
            def command(argv,**kwargs):
                calls.append(argv)
                if argv[0]=="/usr/bin/mount":
                    index=mounts.index(argv[-1]); active[argv[-1]]=saved[index]
                    if fail_mount and index==0: raise RuntimeError("mount output capture failure after side effect")
                if argv[0]=="/usr/bin/umount": active.pop(argv[-1])
                stdout=json.dumps({"partitiontable":self.result()["partition_table"]}) if argv[:2]==["/usr/sbin/sfdisk","--json"] else ""
                return self.tool_result(argv,stdin=kwargs.get("stdin",b""),stdout=stdout)
            def path(value): return root if value=="/mnt/dm-g0" else Path(value)
            manifest={"entries":[{"path":str(Path(setup.__file__)),"sha256":self.setup_sha},{"path":"/opt/dm-g0/helpers/guest_g0_qualify.py","sha256":self.qualify_sha}]}
            def patch(name,**kwargs): return stack.enter_context(mock.patch.object(setup,name,**kwargs))
            patch("Path",side_effect=path); patch("prepare_seed_tree",return_value={}); patch("stable_seed_file",return_value=(b"{}",{}))
            stack.enter_context(mock.patch.object(setup.g0,"validate_config",return_value=config))
            stack.enter_context(mock.patch.object(setup.g0,"validate_ready",return_value={}))
            stack.enter_context(mock.patch.object(setup.g0,"validate_g0_result",return_value={}))
            patch("verify_manifest",return_value=(manifest,self.manifest_sha)); patch("dmi_binding",return_value=(self.binding,{}))
            patch("tool_facts",return_value=[]); patch("udev_rule_fact",return_value=self.udev_rule()); nvme_calls=patch("nvme_preflight",return_value=nvme)
            patch("prepare_initialization_tool",return_value={"fd":None});patch("close_initialization_tool")
            patch("wait_selected_initialization",side_effect=TimeoutError("selected initialization timeout") if initialization_failure else None,return_value=self.initialization_record())
            patch("mount_namespace",side_effect=namespace_read); patch("observe_unmount_guard",side_effect=traced_guard); patch("mountinfo",side_effect=snapshot); patch("run_tool",side_effect=command)
            patch("wait_partitions",return_value=[{"number":part["number"],"name":part["name"],"dev":part["dev"]} for part in nvme["partitions"]]); patch("root_fd_inventory",side_effect=lambda ids,phase:{"phase":phase})
            patch("child_qualifier",return_value=(self.qualifier(),g0.build_qualifier(self.qualifier())))
            patch("emit_mountinfo",side_effect=lambda phase,*args:{"phase":phase,"bytes":15,"sha256":"f"*64})
            stack.enter_context(mock.patch.object(setup.os,"getuid",return_value=0));stack.enter_context(mock.patch.object(setup.os,"getgid",return_value=0))
            stack.enter_context(mock.patch.object(setup.os,"chown"))
            real_lstat=os.lstat
            def owned_lstat(path,*args,**kwargs):
                observed=real_lstat(path,*args,**kwargs)
                if str(path).startswith(str(root)):
                    values=list(observed);values[4]=values[5]=0
                    return os.stat_result(values)
                return observed
            stack.enter_context(mock.patch.object(setup.os,"lstat",side_effect=owned_lstat))
            real_fstat=os.fstat
            def owned_fstat(fd):
                values=list(real_fstat(fd));values[4]=values[5]=0;return os.stat_result(values)
            stack.enter_context(mock.patch.object(setup.os,"fstat",side_effect=owned_fstat))
            ack_fd=os.open("/dev/null",os.O_RDONLY)
            patch("ack_port",return_value=(ack_fd,{},{})); patch("ack_check"); patch("ack_close")
            patch("read_ack",return_value=({},b"mock ack")); patch("serial_frame",side_effect=serial_emit)
            try:
                if fail_mount:
                    with self.assertRaisesRegex(RuntimeError,"mount output capture failure after side effect"): setup.main()
                    os.close(ack_fd)  # acquisition was mocked but main never reached ACK on this path
                elif initialization_failure:
                    with self.assertRaisesRegex(TimeoutError,"selected initialization timeout"):setup.main()
                    self.assertEqual(nvme_calls.call_count,1);os.close(ack_fd)
                elif guard_failure or diagnostic_failure:
                    expected="device/namespace changed" if guard_failure else "guard diagnostic failure"
                    with self.assertRaisesRegex(RuntimeError,expected) as observed:setup.main()
                    if guard_failure and diagnostic_failure:self.assertIn("guard diagnostic failure",str(observed.exception.__notes__))
                else: setup.main()
            finally:
                self.assertEqual(active,{})
            self.assertFalse(root.exists())
            unmounts=[argv[-1] for argv in calls if argv[0]=="/usr/bin/umount"]
            self.assertEqual(unmounts,[] if initialization_failure else [mounts[0]] if fail_mount else list(reversed(mounts)))
            self.assertEqual(sum(prefix==g0.RESULT_PREFIX for prefix,_ in frames),0 if fail_mount or guard_failure or diagnostic_failure or initialization_failure else 1)
            expected_phases=[] if fail_mount or initialization_failure else list(g0.GUARD_PHASES)
            if guard_failure:expected_phases=expected_phases[:expected_phases.index(guard_failure)+1]
            elif diagnostic_failure:expected_phases=expected_phases[:1]
            self.assertEqual(guard_phases,expected_phases)

    def test_production_guest_main_normal_cleanup_restores_nlink_before_each_unmount(self):
        self.exercise_mocked_guest_main()

    def test_production_guest_main_cleans_owned_mount_after_capture_failure(self):
        self.exercise_mocked_guest_main(fail_mount=True)

    def qmp_exchange(self,command,identifier,reply,*,initial=b"",events=None,**flags):
        left,right=socket.socketpair();left.setblocking(False);right.settimeout(2); requests=[];errors=[]
        def responder():
            try:
                raw=bytearray()
                while b"\n" not in raw:
                    block=right.recv(4096)
                    if not block: raise RuntimeError("request EOF")
                    raw.extend(block)
                requests.append(g0.loads_strict(bytes(raw)))
                for block in reply: right.sendall(block)
                right.shutdown(socket.SHUT_WR)
            except BaseException as exc: errors.append(exc)
        worker=threading.Thread(target=responder);worker.start()
        try:
            value=host.qmp_command(left,command=command,command_id=identifier,qmp_buffer=bytearray(initial),qmp_total=0,
                transcript=bytearray(),transcript_state={"truncated":False,"bytes_observed_at_least":0,"transport_eof":False},events=events if events is not None else [],
                stderr_fd=-1,stderr_prefix=bytearray(),stderr_state={"truncated":False},stderr_open=False,**flags)
            self.assertEqual(requests,[{"execute":command,"id":identifier}]);return value
        finally:
            left.close();worker.join(3);right.close();self.assertFalse(worker.is_alive())
            if errors: raise errors[0]

    def test_production_qmp_command_exact_id_event_order_eof_and_cap(self):
        status={"id":"status","return":{"running":False,"singlestep":False,"status":"prelaunch"}}
        raw=g0.canonical(status)+b"\r\n"
        value,*_=self.qmp_exchange("query-status","status",[raw[:7],raw[7:]])
        g0.validate_status_response(value,"status")
        with self.assertRaisesRegex(RuntimeError,"uncorrelated"):
            self.qmp_exchange("query-status","status",[b'{"id":"other","return":{}}\r\n'])
        with self.assertRaisesRegex(RuntimeError,"closed"):
            self.qmp_exchange("query-status","status",[b'{"id":"status"'])
        resume={"event":"RESUME","timestamp":{"seconds":1,"microseconds":0}}; event=g0.canonical(resume)+b"\r\n"; events=[]
        self.qmp_exchange("cont","cont",[event+b'{"id":"cont","return":{}}\r\n'],events=events,allow_resume=True)
        self.assertEqual(events,[resume])
        events=[];mapping=self.mapping();mapping["id"]="post"
        result=self.qmp_exchange("query-block","post",[g0.canonical(mapping)+b"\r\n"],initial=event,events=events,allow_resume=True,allow_vserport=True)
        g0.validate_mapping_response(result[0],"post","nvme.raw");self.assertEqual(events,[resume])
        with mock.patch.object(host.policy,"STREAM_MAX",4),self.assertRaisesRegex(RuntimeError,"transcript cap"):
            self.qmp_exchange("query-status","status",[raw])

    def test_live_ready_requires_valid_complete_boot_frame_before_ack(self):
        ready=g0.build_frame(g0.READY_PREFIX,self.ready(),g0.FRAME_MAX);boot=b"DMFRAME3 validated-by-original-parser\n"
        with mock.patch.object(host.policy,"parse_frame",return_value={"accepted":True}) as parser:
            self.assertEqual(host.validate_pre_ready_boot(boot+ready,nonce=self.nonce,binding=self.binding,source_sha=self.setup_sha),{"accepted":True})
            parser.assert_called_once()
            for raw in (ready,ready+boot,boot.rstrip(b"\n")+ready,boot+boot+ready):
                with self.assertRaises(RuntimeError): host.validate_pre_ready_boot(raw,nonce=self.nonce,binding=self.binding,source_sha=self.setup_sha)
        with mock.patch.object(host.policy,"parse_frame",side_effect=ValueError("bad original frame")),self.assertRaisesRegex(ValueError,"bad original frame"):
            host.validate_pre_ready_boot(boot+ready,nonce=self.nonce,binding=self.binding,source_sha=self.setup_sha)

    def test_tool_evidence_replays_exact_twenty_commands_and_failure_prefixes(self):
        result=self.result(); expected=[]
        for value in result["tools"]+[result["udev_rule"]]: expected.extend((value["owner_query"],value["version_query"]))
        expected+=result["commands"]; records=[]
        context={"nonce":self.nonce,"binding":self.binding,"manifest_sha256":self.manifest_sha,"tool_count":0}
        device=result["nvme"]["device"];stdin=("label: gpt\nunit: sectors\n\n"+f"{device}p1 : start=2048, size=122880, type=0FC63DAF-8483-4772-8E79-3D69D8477DE4\n"+f"{device}p2 : start=124928, size=131072, type=0FC63DAF-8483-4772-8E79-3D69D8477DE4\n").encode()
        with mock.patch.object(setup,"serial_frame",side_effect=lambda prefix,value:records.append(g0.build_frame(prefix,value,g0.FRAME_MAX))):
            for value in expected:
                capture={"stdout":bytearray(value["stdout_text"].encode()),"stderr":bytearray(value["stderr_text"].encode()),"stdout_eof":True,"stderr_eof":True,"returncode":0,"child_reaped":True}
                setup.emit_tool_capture(context,value["argv"],stdin if value["stdin_bytes"] else b"",capture,None,"complete")
        stream=b"".join(records); receipts=g0.parse_tool_frames(stream,nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest_sha,require_complete=False)
        g0.bind_tool_receipts(receipts,result)
        bad=copy.deepcopy(result);bad["commands"][-1]["argv"][1]="--force"
        with self.assertRaises(ValueError): g0.bind_tool_receipts(receipts,bad)
        with self.assertRaises(ValueError): g0.parse_tool_frames(stream.rstrip(b"\n"),nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest_sha,require_complete=True)
        with self.assertRaises(ValueError): g0.parse_tool_frames(b"".join(records[:-1]),nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest_sha,require_complete=True)
        records=[];context["tool_count"]=0
        capture={"stdout":bytearray(b"x"*65537),"stderr":bytearray(b"\xff"),"stdout_eof":False,"stderr_eof":True,"returncode":None,"child_reaped":False}
        with mock.patch.object(setup,"serial_frame",side_effect=lambda prefix,value:records.append(g0.build_frame(prefix,value,g0.FRAME_MAX))):
            setup.emit_tool_capture(context,["/usr/bin/mount"],b"",capture,"RuntimeError: cap","failure-after-child-cleanup-attempt")
        receipt=g0.parse_tool_frames(b"".join(records),nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest_sha,require_complete=False)[0]
        self.assertEqual(receipt["raw_streams"]["stdout"],b"x"*65536);self.assertEqual(receipt["raw_streams"]["stderr"],b"\xff")
        self.assertTrue(receipt["metadata"]["streams"]["stdout"]["truncated"])
        self.assertEqual(receipt["metadata"]["streams"]["stdout"]["observed_at_least"],65537)
        with self.assertRaises(ValueError): g0.parse_tool_frames(b"".join(records),nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest_sha,require_complete=True)

    def test_typed_ordinary_and_nvme_numbers_reject_float_equivalents(self):
        for mutate in (lambda x:x.update(uid=float(g0.ORDINARY_ID)),lambda x:x["ordinary_identity"]["before"].update(uids=[float(g0.ORDINARY_ID)]*3)):
            value=self.qualifier();mutate(value)
            with self.assertRaises(ValueError):g0.validate_qualifier_value(value)
        for field in ("bytes","sector_bytes","sectors"):
            value=self.ready();value["nvme"][field]=float(value["nvme"][field])
            with self.assertRaises(ValueError):g0.validate_ready(value,nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest_sha,setup_sha256=self.setup_sha,qualify_sha256=self.qualify_sha)

    def test_diagnostic_budget_and_full_raw_mount_frame_fit_unchanged_serial_cap(self):
        raw=b"1 1 8:1 / /"+b"x"*(g0.MOUNTINFO_MAX-len(b"1 1 8:1 / / rw - ext4 /dev/root rw\n"))+b" rw - ext4 /dev/root rw\n"
        self.assertEqual(len(raw),g0.MOUNTINFO_MAX)
        for phase in g0.MOUNT_PHASES:
            value=g0.mount_receipt(phase,raw,nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest_sha)
            self.assertLessEqual(len(g0.build_frame(g0.MOUNT_PREFIX,value,g0.FRAME_MAX)),g0.TOOL_CHUNK_WIRE_MAX)
        subtotal=20*(4096+4*g0.TOOL_CHUNK_WIRE_MAX)+6*g0.TOOL_CHUNK_WIRE_MAX+2*g0.FRAME_MAX
        self.assertEqual(subtotal,4036724);self.assertLess(subtotal,host.policy.SERIAL_MAX)
        with self.assertRaises(ValueError): host.policy.charge_stream(subtotal,host.policy.SERIAL_MAX-subtotal+1,host.policy.SERIAL_MAX)

    def test_host_failed_allocation_and_removal_do_not_unlink_replaced_inode(self):
        parent=SimpleNamespace(st_dev=1,st_ino=2,st_uid=os.getuid(),st_gid=os.getgid(),st_mode=stat.S_IFDIR|0o700,st_nlink=2,st_size=4096,st_blocks=8)
        created=SimpleNamespace(st_dev=1,st_ino=3,st_uid=os.getuid(),st_gid=os.getgid(),st_mode=stat.S_IFREG|0o600,st_nlink=1,st_size=0,st_blocks=0)
        replacement=SimpleNamespace(**{**vars(created),"st_ino":4})
        def fstat(fd): return parent if fd==11 else created
        primary=RuntimeError("allocation failed")
        with (mock.patch.object(host.os,"lstat",return_value=parent),mock.patch.object(host.os,"open",side_effect=[10,11]),
              mock.patch.object(host.os,"posix_fallocate",side_effect=primary),mock.patch.object(host.os,"fstat",side_effect=fstat),
              mock.patch.object(host.os,"stat",return_value=replacement),mock.patch.object(host.os,"unlink") as unlink,mock.patch.object(host.os,"close")):
            with self.assertRaisesRegex(RuntimeError,"allocation failed") as observed:host.create_g0_file(Path("/sandbox"))
            self.assertIs(observed.exception,primary);unlink.assert_not_called();self.assertTrue(primary.__notes__)
        expected={"identity":[1,3,os.getuid(),os.getgid(),0o600,1,0,0],"parent_identity":[1,2,os.getuid(),os.getgid(),0o700,2]}
        with (mock.patch.object(host.os,"lstat",return_value=created),mock.patch.object(host.os,"open",return_value=11),
              mock.patch.object(host.os,"fstat",side_effect=fstat),mock.patch.object(host.os,"stat",return_value=replacement),
              mock.patch.object(host.os,"unlink") as unlink,mock.patch.object(host.os,"close")):
            with self.assertRaisesRegex(RuntimeError,"unlink identity changed"):host.remove_g0_file(Path("/sandbox/nvme.raw"),10,expected)
            unlink.assert_not_called()

    def test_failure_tool_serial_evidence_waits_for_child_reap_and_all_pipe_closes(self):
        streams=[mock.Mock(closed=False) for _ in range(3)]
        for index,stream in enumerate(streams):stream.fileno.return_value=10+index
        proc=mock.Mock(pid=100,stdin=streams[0],stdout=streams[1],stderr=streams[2],returncode=-9);proc.wait.return_value=-9
        primary=RuntimeError("setup failure");observed=[]
        def serial(prefix,value):
            self.assertTrue(proc.wait.called)
            self.assertTrue(all(stream.close.called for stream in streams))
            observed.append(value)
        with (mock.patch.object(setup.subprocess,"Popen",return_value=proc),mock.patch.object(setup,"proc_start",return_value=42),
              mock.patch.object(setup.os,"pidfd_open",return_value=20),mock.patch.object(setup.os,"set_blocking",side_effect=primary),
              mock.patch.object(setup,"child_same",return_value=True),mock.patch.object(setup,"pidfd_signal"),mock.patch.object(setup.os,"close"),
              mock.patch.object(setup,"serial_frame",side_effect=serial)):
            context={"nonce":self.nonce,"binding":self.binding,"manifest_sha256":self.manifest_sha,"tool_count":0}
            with self.assertRaisesRegex(RuntimeError,"setup failure") as caught:setup.run_tool(["/usr/bin/mount"],timeout=1,diagnostics=context)
            self.assertIs(caught.exception,primary)
        self.assertEqual(observed[0]["phase"],"failure-after-child-cleanup-attempt");self.assertTrue(observed[0]["child_reaped"])

    def test_completed_non_utf8_tool_raw_is_emitted_before_strict_decode(self):
        frames=[]
        def captured(argv,*,capture,**kwargs):
            capture.update(stdout=bytearray(b"\xff"),stderr=bytearray(),stdout_eof=True,stderr_eof=True,returncode=0,child_reaped=True)
            return {"stdout_text":b"\xff","stderr_text":b""}
        context={"nonce":self.nonce,"binding":self.binding,"manifest_sha256":self.manifest_sha,"tool_count":0}
        with mock.patch.object(setup,"capture_tool",side_effect=captured),mock.patch.object(setup,"serial_frame",side_effect=lambda prefix,value:frames.append(g0.build_frame(prefix,value,g0.FRAME_MAX))):
            with self.assertRaises(UnicodeDecodeError):setup.run_tool(["/usr/bin/mount"],timeout=1,diagnostics=context)
        receipts=g0.parse_tool_frames(b"".join(frames),nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest_sha,require_complete=False)
        self.assertEqual(receipts[0]["raw_streams"]["stdout"],b"\xff");self.assertEqual(receipts[0]["metadata"]["phase"],"complete")

    def test_all_non_g0_qemu_argv_tokens_are_byte_structurally_preserved_from_v21(self):
        expected=ast.parse('[\n        qemu, "-nodefaults", "-no-user-config", "-machine", "pc", "-accel", "tcg,thread=single",\n        "-cpu", "max", "-m", "2048", "-smp", "2", "-bios", str(bios), "-display", "none", "-nic", "none",\n        "-monitor", "none", "-parallel", "none", "-no-reboot", "-boot", "strict=on",\n        "-drive", "if=none,id=root,file=" + str(overlay) + ",format=qcow2,cache=none,aio=threads",\n        "-device", "virtio-blk-pci,drive=root,bootindex=1",\n        "-drive", "if=none,id=seed,file=" + str(seed) + ",format=raw,readonly=on",\n        "-device", "virtio-blk-pci,drive=seed",\n        "-chardev", "socket,id=serial0,path=" + str(serial_socket) + ",server=on,wait=off",\n        "-serial", "chardev:serial0", "-qmp", "unix:" + str(qmp_socket) + ",server=on,wait=off",\n        "-smbios", "type=1,serial=<CONFIG_BINDING>",\n    ]',mode="eval").body
        tree=ast.parse((HERE/"host_controller.py").read_text())
        actual=next(node.value for node in ast.walk(tree) if isinstance(node,ast.Assign) and any(isinstance(target,ast.Name) and target.id=="argv_template" for target in node.targets))
        elements=[];index=0;removed=0
        while index<len(actual.elts):
            item=actual.elts[index]
            if isinstance(item,ast.Constant) and item.value=="-S":index+=1;removed+=1;continue
            if isinstance(item,ast.Constant) and item.value in ("-drive","-device","-chardev") and index+1<len(actual.elts):
                argument=ast.unparse(actual.elts[index+1])
                if any(prefix in argument for prefix in ("if=none,id=g0data,","nvme,id=g0nvme,","virtio-serial-pci,id=g0virtio","socket,id=g0ack,","virtserialport,id=g0port,")):
                    index+=2;removed+=2;continue
            elements.append(item);index+=1
        self.assertEqual(removed,11)
        self.assertEqual([ast.dump(item) for item in elements],[ast.dump(item) for item in expected.elts])

    def qualifier_capture_stream(self,raw=None,*,eof=True,status=0,error=None,crlf=False):
        raw=g0.build_qualifier(self.qualifier()) if raw is None else raw
        records=g0.qualifier_capture_records(raw,nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest_sha,eof=eof,status=status,error=error)
        frames=[g0.build_frame(g0.QUAL_RAW_PREFIX,value,g0.QUAL_RAW_META_MAX if index==0 else g0.TOOL_CHUNK_WIRE_MAX) for index,value in enumerate(records)]
        return b"".join(frame[:-1]+b"\r\n" if crlf else frame for frame in frames)

    def test_v23_exact_terminal_lf_crlf_preserves_payload_and_embedded_cr(self):
        value={"text":"escaped\rcarriage"};lf=g0.build_frame(g0.READY_PREFIX,value,g0.FRAME_MAX);crlf=lf[:-1]+b"\r\n"
        self.assertEqual(g0.decode_line(lf,g0.READY_PREFIX,g0.FRAME_MAX),value)
        self.assertEqual(g0.decode_line(crlf,g0.READY_PREFIX,g0.FRAME_MAX),value)
        self.assertEqual(g0.parse_serial_frame(crlf,g0.READY_PREFIX),value)
        for raw in (lf[:-1],lf[:-1]+b"\r",lf[:-1]+b"\r\r\n",lf[:-1]+b" \n"):
            with self.assertRaises(ValueError):g0.decode_line(raw,g0.READY_PREFIX,g0.FRAME_MAX)
        embedded=lf.replace(b'"text"',b'"te\rxt"')
        self.assertEqual(len(g0.serial_records(embedded)),1)
        with self.assertRaises(ValueError):g0.parse_serial_frame(embedded,g0.READY_PREFIX)
        with self.assertRaises(ValueError):g0.parse_serial_frame(lf+lf[:-1],g0.READY_PREFIX)

    def test_v23_live_crlf_split_at_every_boundary_and_wire_cr_byte_cap(self):
        value=self.ready();lf=g0.build_frame(g0.READY_PREFIX,value,g0.FRAME_MAX);wire=lf[:-1]+b"\r\n"
        for offset in range(len(wire)):
            first=host.complete_serial_prefix(wire[:offset])
            self.assertEqual(first,b"")
            full=host.complete_serial_prefix(wire[:offset]+wire[offset:])
            self.assertEqual(g0.parse_serial_frame(full,g0.READY_PREFIX),value)
        cap=len(lf)+1
        self.assertEqual(g0.build_frame(g0.READY_PREFIX,value,cap),lf)
        with self.assertRaisesRegex(ValueError,"wire frame cap"):g0.build_frame(g0.READY_PREFIX,value,cap-1)
        with self.assertRaisesRegex(ValueError,"wire frame cap"):g0.decode_line(wire,g0.READY_PREFIX,len(lf))
        self.assertEqual(g0.decode_line(wire,g0.READY_PREFIX,cap),value)

    def test_v23_exact_raw_qualifier_capture_lf_crlf_and_maximum_cap(self):
        for raw in (b"",b"\0\r\n\xff",b"x"*65536):
            for crlf in (False,True):
                error="RuntimeError: empty" if not raw else None
                stream=self.qualifier_capture_stream(raw,error=error,crlf=crlf)
                captured=g0.parse_qualifier_capture(stream,nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest_sha)
                self.assertEqual(captured["raw"],raw)
                self.assertLessEqual(sum(len(line) for line in g0.serial_records(stream)),93020)
                self.assertFalse(captured["metadata"]["truncated"])
        raw=b"x"*65537
        captured=g0.parse_qualifier_capture(self.qualifier_capture_stream(raw,eof=False,status=9,error="RuntimeError: cap"),nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest_sha)
        self.assertEqual(captured["raw"],raw[:65536]);self.assertTrue(captured["metadata"]["truncated"])
        self.assertEqual(captured["metadata"]["observed_at_least"],65537)

    def test_v23_capture_rejects_missing_reordered_changed_and_partial_chunks(self):
        stream=self.qualifier_capture_stream(b"x"*65536);lines=g0.serial_records(stream)
        for raw in (b"".join(lines[:-1]),b"".join([lines[0],lines[2],lines[1]]),stream.rstrip(b"\n"),stream+lines[1],stream.replace(b'"index":0',b'"index":9')):
            with self.assertRaises(ValueError):g0.parse_qualifier_capture(raw,nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest_sha)
        with self.assertRaises(ValueError):g0.parse_qualifier_capture(stream,nonce="f"*32,binding=self.binding,manifest_sha256=self.manifest_sha)
        self.assertIsNone(g0.parse_qualifier_capture(b"ordinary noise\r\n",nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest_sha))

    def exercise_qualifier_capture(self,*,raw=None,status=0,read_error=None,cap=False,emit_error=None,setup_error=None,cleanup_error=None):
        data=g0.build_qualifier(self.qualifier()) if raw is None else raw
        if cap:data=b"x"*65537
        config={"nonce":self.nonce,"probe_name":"dm-g0-probe.bin","mounts":["/mnt/dm-g0/p1","/mnt/dm-g0/p2"],"deadlines":{"ordinary_child":120}}
        records=[];closed=[];waits=[];order=[]
        def read(fd,count):
            if read_error is not None:raise read_error
            return reads.pop(0)
        reads=[data,b""]
        def wait(pid,flags):waits.append((pid,flags));return pid,status
        def serial(prefix,value):
            self.assertTrue({80,81,90}.issubset(closed) if setup_error is None else {80,81}.issubset(closed))
            order.append("emit")
            if emit_error is not None:raise emit_error
            records.append(g0.build_frame(prefix,value,g0.FRAME_MAX))
        real_parse=setup.g0.parse_qualifier
        def parse(raw):self.assertTrue(records);order.append("parse");return real_parse(raw)
        with (mock.patch.object(setup.os,"pipe2",return_value=(80,81)),mock.patch.object(setup.os,"fork",return_value=100),
              mock.patch.object(setup.os,"close",side_effect=lambda fd:closed.append(fd)),mock.patch.object(setup.os,"set_blocking"),
              mock.patch.object(setup,"proc_start",return_value=42),mock.patch.object(setup.os,"pidfd_open",side_effect=setup_error if setup_error else lambda *args:90),
              mock.patch.object(setup,"direct_children",return_value=[]),mock.patch.object(setup.os,"read",side_effect=read),
              mock.patch.object(setup.os,"waitpid",side_effect=wait),mock.patch.object(setup.os,"kill"),
              mock.patch.object(setup,"stop_and_reap_qualifier",return_value=9,side_effect=cleanup_error),mock.patch.object(setup,"serial_frame",side_effect=serial),
              mock.patch.object(setup.g0,"parse_qualifier",side_effect=parse) as parser):
            error=None
            try:value=setup.child_qualifier(config,self.manifest_sha,self.binding,self.nvme()["partitions"])
            except BaseException as exc:error=exc;value=None
            return value,error,records,closed,waits,order,parser.call_count

    def test_v23_production_child_raw_precedes_parse_after_one_reap_and_fd_close(self):
        value,error,frames,closed,waits,order,calls=self.exercise_qualifier_capture()
        self.assertIsNone(error);self.assertEqual(value[0],self.qualifier());self.assertEqual(calls,1)
        self.assertEqual(len(waits),1);self.assertEqual(closed.count(80),1);self.assertEqual(closed.count(81),1);self.assertEqual(closed.count(90),1)
        self.assertEqual(order[-1],"parse")
        record=g0.parse_qualifier_capture(b"".join(frames),nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest_sha)
        self.assertTrue(record["metadata"]["reaped"]);self.assertTrue(record["metadata"]["eof"])

    def test_v23_invalid_semantic_qualifier_is_retained_without_stdlib_rule_relaxation(self):
        value=self.qualifier();value["loaded_stdlib"][0]["bytes"]=0;raw=g0.build_qualifier(value)
        _,error,frames,_,waits,_,calls=self.exercise_qualifier_capture(raw=raw)
        self.assertIsInstance(error,ValueError);self.assertIn("stdlib entry",str(error));self.assertEqual(len(waits),1);self.assertEqual(calls,1)
        captured=g0.parse_qualifier_capture(b"".join(frames),nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest_sha)
        self.assertEqual(captured["raw"],raw)

    def test_v23_nonzero_cap_setup_and_io_errors_keep_honest_raw_capture(self):
        cases=[{"status":256},{"cap":True},{"setup_error":PermissionError(1,"pidfd denied")},{"read_error":OSError(5,"pipe read failed")}]
        for case in cases:
            with self.subTest(case=case):
                _,error,frames,_,_,_,calls=self.exercise_qualifier_capture(**case)
                self.assertIsNotNone(error);self.assertEqual(calls,0)
                capture=g0.parse_qualifier_capture(b"".join(frames),nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest_sha)
                self.assertEqual(capture["metadata"]["phase"],"failure-after-cleanup-attempt")
                if case.get("cap"):self.assertEqual(len(capture["raw"]),65536);self.assertTrue(capture["metadata"]["truncated"])
                if case.get("setup_error") or case.get("read_error"):self.assertFalse(capture["metadata"]["eof"])

    def test_v23_primary_child_error_survives_serial_diagnostic_failure_and_byte_bound(self):
        primary=OSError(5,"original read error")
        _,error,_,_,_,_,_=self.exercise_qualifier_capture(read_error=primary,emit_error=OSError(28,"diagnostic full"))
        self.assertIs(error,primary);self.assertTrue(error.__notes__)
        records=[];config={"nonce":self.nonce}
        with mock.patch.object(setup,"serial_frame",side_effect=lambda prefix,value:records.append(value)):
            setup.emit_qualifier_capture(config,self.manifest_sha,self.binding,b"",False,None,RuntimeError("é"*1000))
        self.assertLessEqual(len(records[0]["error"].encode()),512)

    def test_v23_host_retains_exact_invalid_record_before_semantic_acceptance(self):
        value=self.qualifier();value["loaded_stdlib"][0]["bytes"]=0;raw=g0.build_qualifier(value)
        binding={"nonce":self.nonce,"binding":self.binding,"manifest_sha256":self.manifest_sha}
        with tempfile.TemporaryDirectory() as temporary:
            evidence=Path(temporary);stream=self.qualifier_capture_stream(raw,crlf=True)
            receipt=host.retain_qualifier_capture(evidence,stream,binding)
            self.assertEqual((evidence/"g0-qualifier.raw").read_bytes(),raw);self.assertFalse(receipt["qualifier_qualified"])
            sanitized=(evidence/"g0-diagnostics.sanitized.json").read_text()
            self.assertNotIn(self.nonce,sanitized);self.assertNotIn(self.binding,sanitized)
            with self.assertRaises(ValueError):g0.parse_qualifier(raw)
        ready=self.ready();stream=self.qualifier_capture_stream()
        host.require_ready_capture(stream,ready,**binding)
        with self.assertRaises(RuntimeError):host.require_ready_capture(b"",ready,**binding)
        other=self.qualifier();other["loaded_stdlib"][0]["bytes"]+=1
        with self.assertRaises(RuntimeError):host.require_ready_capture(self.qualifier_capture_stream(g0.build_qualifier(other)),ready,**binding)

    def test_v23_partial_diagnostic_leaves_only_original_raw_stream_and_invalid_metadata(self):
        binding={"nonce":self.nonce,"binding":self.binding,"manifest_sha256":self.manifest_sha};stream=self.qualifier_capture_stream()[:-1]
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);evidence=root/"evidence";evidence.mkdir()
            state={"truncated":False,"bytes_observed_at_least":len(stream),"transport_eof":True};qmp_state={"truncated":False,"bytes_observed_at_least":0,"transport_eof":True}
            host.retain_guest_streams(root,evidence,stream,state,b"",qmp_state,[],"fixture",binding)
            self.assertEqual((evidence/"serial.raw").read_bytes(),stream);self.assertFalse((evidence/"g0-qualifier.raw").exists())
            self.assertEqual(json.loads((evidence/"g0-qualifier-capture.json").read_bytes())["status"],"invalid")

    def file_snapshot_fixture(self):
        file=SimpleNamespace(st_dev=1,st_ino=3,st_uid=os.getuid(),st_gid=os.getgid(),st_mode=stat.S_IFREG|0o600,st_nlink=1,st_size=134217728,st_blocks=262144)
        parent=SimpleNamespace(st_dev=1,st_ino=2,st_uid=os.getuid(),st_gid=os.getgid(),st_mode=stat.S_IFDIR|0o700,st_nlink=2,st_size=4096,st_blocks=8)
        expected={"identity":host.g0_file_identity(file),"parent_identity":host.g0_parent_identity(parent)}
        return file,parent,expected

    @contextlib.contextmanager
    def snapshot_environment(self,*,file=None,parent=None,write_error=False,open_error=None,named_error=None):
        original_file,original_parent,expected=self.file_snapshot_fixture();file=file or original_file;parent=parent or original_parent
        state={"removed":False};snapshots=[];order=[]
        def lstat(path):return parent if str(path)=="/fixture" else file
        def fstat(fd):
            if fd==11:return parent
            return SimpleNamespace(**{**vars(file),"st_nlink":0}) if state["removed"] else file
        def named(*args,**kwargs):
            if named_error is not None:raise named_error
            if state["removed"]:raise FileNotFoundError(2,"removed")
            return file
        def exclusive(path,data,**kwargs):
            order.append("snapshot:"+path.name);snapshots.append((path.name,json.loads(data)))
            if write_error:raise OSError(28,"snapshot write full")
        def unlink(*args,**kwargs):order.append("unlink");state["removed"]=True
        config={"nonce":self.nonce,"binding":self.binding,"g0_manifest_sha256":self.manifest_sha,"guest_source_sha256":self.setup_sha}
        with (mock.patch.object(host.os,"lstat",side_effect=lstat),mock.patch.object(host.os,"fstat",side_effect=fstat),
              mock.patch.object(host.os,"stat",side_effect=named),mock.patch.object(host.os,"open",side_effect=open_error if open_error else lambda *args,**kwargs:11),
              mock.patch.object(host.os,"close") as close,mock.patch.object(host.os,"fsync"),mock.patch.object(host.os,"unlink",side_effect=unlink),
              mock.patch.object(host,"load_fixed_receipt",return_value=(b"{}",config)),mock.patch.object(host,"exclusive",side_effect=exclusive)):
            yield file,parent,expected,state,snapshots,order,close

    def test_v23_real_generated_boot_config_binds_snapshot_before_guard(self):
        with tempfile.TemporaryDirectory() as temporary:
            evidence=Path(temporary);config={"nonce":self.nonce,"binding":self.binding,"g0_manifest_sha256":self.manifest_sha,"guest_source_sha256":self.setup_sha}
            host.json_write(evidence/"boot-config.json",config);calls=[]
            def guard():
                raw=json.loads((evidence/"g0-file-pre-cont.json").read_bytes());self.assertEqual(raw["capture_binding"],config);calls.append("guard")
            host.persist_g0_decision(evidence,"pre-cont",None,{"opened":{"raw":[1,2,3,4,stat.S_IFREG|0o600,1,0,0]}},guard)
            self.assertEqual(calls,["guard"])

    def test_v23_normal_snapshot_retains_full_native_modes_and_safe_unlink_order(self):
        with self.snapshot_environment() as (file,parent,expected,state,snapshots,order,close):
            result=host.remove_g0_file(Path("/fixture/nvme.raw"),10,expected,evidence=Path("/evidence"))
            self.assertTrue(state["removed"]);self.assertEqual(result["diagnostic_errors"],[]);host.require_g0_removal_diagnostics(result)
            self.assertEqual([name for name,_ in snapshots],["g0-file-normal-removal.json","g0-file-normal-unlink.json","g0-file-normal-after-unlink.json"])
            before=snapshots[1][1]["observations"]["before"]["raw"]
            self.assertEqual(before[4],file.st_mode);self.assertNotEqual(before[4],0o600)
            self.assertLess(order.index("snapshot:g0-file-normal-unlink.json"),order.index("unlink"))
            self.assertEqual(snapshots[-1][1]["observations"]["opened"]["raw"][5],0)
            close.assert_any_call(10);close.assert_any_call(11)
            self.assertTrue(all(len(g0.canonical(value))<=2048 for _,value in snapshots))

    def test_v24_each_changed_immutable_file_field_is_retained_before_unchanged_rejection(self):
        original,parent,expected=self.file_snapshot_fixture()
        for field,replacement in (("st_dev",99),("st_ino",99),("st_uid",99),("st_gid",99),("st_mode",stat.S_IFREG|0o640),("st_nlink",2),("st_size",134217727)):
            changed=SimpleNamespace(**{**vars(original),field:replacement})
            with self.snapshot_environment(file=changed) as (_,_,_,state,snapshots,order,_):
                with self.assertRaisesRegex(RuntimeError,"G0 host file changed"):host.remove_g0_file(Path("/fixture/nvme.raw"),10,expected,evidence=Path("/evidence"))
                self.assertFalse(state["removed"]);self.assertEqual(len(snapshots),1)
                actual=snapshots[0][1]["observations"]["opened"]["raw"]
                self.assertEqual(actual,[changed.st_dev,changed.st_ino,changed.st_uid,changed.st_gid,changed.st_mode,changed.st_nlink,changed.st_size,changed.st_blocks*512])
        changed_parent=SimpleNamespace(**{**vars(parent),"st_ino":99})
        with self.snapshot_environment(parent=changed_parent) as (_,_,_,state,snapshots,_,_):
            with self.assertRaisesRegex(RuntimeError,"G0 parent changed"):host.remove_g0_file(Path("/fixture/nvme.raw"),10,expected,evidence=Path("/evidence"))
            self.assertFalse(state["removed"]);self.assertEqual(snapshots[-1][1]["observations"]["parent_opened"]["raw"][1],99)

    def test_v23_snapshot_io_failure_keeps_safe_cleanup_but_fails_acceptance(self):
        for failure in (False,True):
            with self.snapshot_environment(write_error=True) as (_,_,expected,state,snapshots,_,_):
                result=host.remove_g0_file(Path("/fixture/nvme.raw"),10,expected,evidence=Path("/evidence"),failure=failure)
                self.assertTrue(state["removed"]);self.assertEqual(len(result["diagnostic_errors"]),3)
                with self.assertRaisesRegex(RuntimeError,"tuple snapshot"):host.require_g0_removal_diagnostics(result)
        file,_,expected=self.file_snapshot_fixture();file.st_ino=99
        with self.snapshot_environment(file=file,write_error=True) as (_,_,_,state,_,_,_):
            with self.assertRaisesRegex(RuntimeError,"G0 host file changed") as error:host.remove_g0_file(Path("/fixture/nvme.raw"),10,expected,evidence=Path("/evidence"),failure=True)
            self.assertFalse(state["removed"]);self.assertTrue(error.exception.__notes__)
        with self.snapshot_environment(write_error=True) as (_,_,expected,_,_,_,_):
            with self.assertRaisesRegex(RuntimeError,"snapshot persistence failed"):host.recheck_g0_file(Path("/fixture/nvme.raw"),10,expected,evidence=Path("/evidence"))

    def test_v23_open_and_named_stat_errors_are_distinct_snapshot_facts(self):
        primary=PermissionError(13,"parent open denied")
        with self.snapshot_environment(open_error=primary) as (_,_,expected,state,snapshots,_,_):
            with self.assertRaises(PermissionError) as error:host.remove_g0_file(Path("/fixture/nvme.raw"),10,expected,evidence=Path("/evidence"))
            self.assertIs(error.exception,primary);self.assertFalse(state["removed"])
            self.assertEqual(snapshots[-1][1]["observations"]["parent_opened"]["error"],["PermissionError",13])
        primary=FileNotFoundError(2,"named leaf missing")
        with self.snapshot_environment(named_error=primary) as (_,_,expected,state,snapshots,_,_):
            with self.assertRaises(FileNotFoundError) as error:host.remove_g0_file(Path("/fixture/nvme.raw"),10,expected,evidence=Path("/evidence"))
            self.assertIs(error.exception,primary);self.assertFalse(state["removed"])
            self.assertIn("raw",snapshots[-1][1]["observations"]["opened"])
            self.assertEqual(snapshots[-1][1]["observations"]["named"]["error"],["FileNotFoundError",2])

    def test_v23_creation_open_error_retained_and_thirteen_phases_are_fixed(self):
        primary=PermissionError(13,"raw creation denied")
        with self.snapshot_environment(open_error=primary) as (_,_,_,state,snapshots,_,_):
            with self.assertRaises(PermissionError) as error:host.create_g0_file(Path("/fixture"),evidence=Path("/evidence"))
            self.assertIs(error.exception,primary);self.assertFalse(state["removed"])
            self.assertEqual([name for name,_ in snapshots],["g0-file-creation-parent.json","g0-file-creation-allocated.json"])
            self.assertEqual(snapshots[-1][1]["observations"]["opened"]["error"],["PermissionError",13])
        self.assertEqual(len(host.G0_FILE_PHASES),13);self.assertEqual(len(set(host.G0_FILE_PHASES)),13)
        for phase in host.G0_FILE_PHASES:self.assertEqual(host.ALLOWED_EVIDENCE["g0-file-"+phase+".json"],2048)
        self.assertEqual(4096+2*g0.TOOL_CHUNK_WIRE_MAX,93020)
        self.assertEqual(4036724+93020,4129744)
        self.assertEqual(65536+8192+13*2048+4096,104448)
        with self.assertRaises(ValueError):host.policy.charge_stream(4129744,64561,host.policy.SERIAL_MAX)

    def test_v23_final_capture_recheck_rejects_late_duplicates_or_fragments(self):
        ready=self.ready();stream=self.qualifier_capture_stream();binding={"nonce":self.nonce,"binding":self.binding,"manifest_sha256":self.manifest_sha}
        host.require_ready_capture(stream,ready,**binding)  # Original live READY prefix is valid.
        for suffix in (stream,g0.serial_records(stream)[0][:-1]):
            full=stream+suffix
            with tempfile.TemporaryDirectory() as temporary:
                report=host.retain_qualifier_capture(Path(temporary),full,binding);self.assertEqual(report["status"],"invalid")
                with self.assertRaises(ValueError):host.require_ready_capture(full,ready,**binding)
        source=(HERE/"host_controller.py").read_text()
        self.assertIn('require_ready_capture(complete_serial,g0_ready',source)
        self.assertIn('require_ready_capture(bytes(serial),g0_ready',source)

    def test_v23_fstat_error_and_allocation_cleanup_snapshot_keep_original_error(self):
        primary=OSError(5,"held fd unavailable")
        with self.snapshot_environment() as (_,parent,expected,state,snapshots,_,_):
            with mock.patch.object(host.os,"fstat",side_effect=lambda fd:parent if fd==11 else (_ for _ in ()).throw(primary)):
                with self.assertRaises(OSError) as error:host.recheck_g0_file(Path("/fixture/nvme.raw"),10,expected,evidence=Path("/evidence"))
            self.assertIs(error.exception,primary);self.assertFalse(state["removed"])
            self.assertEqual(snapshots[-1][1]["observations"]["opened"]["error"],["OSError",5])
            self.assertIn("raw",snapshots[-1][1]["observations"]["named"])
        primary=OSError(28,"allocation unavailable")
        with self.snapshot_environment() as (_,_,_,state,snapshots,order,close):
            with mock.patch.object(host.os,"open",side_effect=[10,11]),mock.patch.object(host.os,"posix_fallocate",side_effect=primary):
                with self.assertRaises(OSError) as error:host.create_g0_file(Path("/fixture"),evidence=Path("/evidence"))
            self.assertIs(error.exception,primary);self.assertTrue(state["removed"])
            self.assertEqual([name for name,_ in snapshots],["g0-file-creation-parent.json","g0-file-allocation-failure-unlink.json","g0-file-allocation-failure-after-unlink.json"])
            self.assertLess(order.index("snapshot:g0-file-allocation-failure-unlink.json"),order.index("unlink"))
            close.assert_any_call(10);close.assert_any_call(11)

    def test_v23_uncertain_child_cleanup_is_not_reported_as_reaped_or_complete(self):
        primary=OSError(5,"original pipe failure")
        _,error,frames,_,_,_,calls=self.exercise_qualifier_capture(read_error=primary,cleanup_error=RuntimeError("reap uncertain"))
        self.assertIs(error,primary);self.assertTrue(error.__notes__);self.assertEqual(calls,0)
        capture=g0.parse_qualifier_capture(b"".join(frames),nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest_sha)
        self.assertFalse(capture["metadata"]["reaped"]);self.assertIsNone(capture["metadata"]["wait_status"])
        self.assertEqual(capture["metadata"]["phase"],"failure-after-cleanup-attempt")
        with self.assertRaises(RuntimeError):host.require_ready_capture(b"".join(frames),self.ready(),nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest_sha)

    def test_v24_ordinary_source_and_only_authorized_empty_file_clause_change(self):
        tree=ast.parse((HERE/"g0_policy.py").read_text())
        parser=next(node for node in tree.body if isinstance(node,ast.FunctionDef) and node.name=="parse_qualifier")
        allowed=ast.parse('item["bytes"] == 0 and item["sha256"] != sha256(b"")',mode="eval").body
        original=ast.parse('item["bytes"] == 0',mode="eval").body;changes=0
        for node in ast.walk(parser):
            if isinstance(node,ast.BoolOp) and isinstance(node.op,ast.Or):
                for index,part in enumerate(node.values):
                    if ast.dump(part)==ast.dump(allowed):node.values[index]=original;changes+=1
        self.assertEqual(changes,1)
        self.assertEqual(hashlib.sha256(ast.dump(parser,include_attributes=False).encode()).hexdigest(),"1485db4d72b84486b698ff004507b0822e62189393a2f1935d9603d751fe9af2")
        self.assertEqual(hashlib.sha256((HERE/"guest_g0_qualify.py").read_bytes()).hexdigest(),"611be6027e60be78f3724eb525e098ddbd39c5127fb20bdfd19ebaef412137e5")

    def empty_stdlib_qualifier(self):
        value=self.qualifier();value["loaded_stdlib"].append({"name":"urllib","path":"/usr/lib/python3.12/urllib/__init__.py","bytes":0,"sha256":g0.sha256(b"")})
        return value

    def test_v24_exact_empty_stdlib_entry_is_valid_and_raw_capture_stays_exact(self):
        value=self.empty_stdlib_qualifier();raw=g0.build_qualifier(value)
        self.assertEqual(g0.parse_qualifier(raw),value)
        capture=g0.parse_qualifier_capture(self.qualifier_capture_stream(raw,crlf=True),nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest_sha)
        self.assertEqual(capture["raw"],raw)
        ready=self.ready();ready.update(qualifier=value,qualifier_bytes=len(raw),qualifier_sha256=g0.sha256(raw))
        g0.validate_ready(ready,nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest_sha,setup_sha256=self.setup_sha,qualify_sha256=self.qualify_sha)
        host.require_ready_capture(self.qualifier_capture_stream(raw),ready,nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest_sha)

    def test_v24_zero_stdlib_type_bound_digest_path_and_duplicate_negatives_survive(self):
        for mutate in (
            lambda x:x["loaded_stdlib"][-1].update(sha256="0"*64),
            lambda x:x["loaded_stdlib"][-1].update(bytes=-1),
            lambda x:x["loaded_stdlib"][-1].update(bytes=False),
            lambda x:x["loaded_stdlib"][-1].update(bytes=0.0),
            lambda x:x["loaded_stdlib"][-1].update(bytes=16*g0.MIB+1),
            lambda x:x["loaded_stdlib"][-1].update(path="/outside/urllib/__init__.py"),
            lambda x:x["loaded_stdlib"][-1].update(name="hashlib"),
            lambda x:x["loaded_stdlib"][-1].update(extra=True),
            lambda x:x["interpreter"].update(bytes=0),
        ):
            value=self.empty_stdlib_qualifier();mutate(value)
            with self.assertRaises(ValueError):g0.validate_qualifier_value(value)

    def test_v24_unchanged_collector_handles_empty_regular_but_rejects_redirect_type_and_race(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);empty=root/"__init__.py";empty.write_bytes(b"")
            self.assertEqual(qualify.sha_file(empty,16*g0.MIB),(g0.sha256(b""),0))
            alias=root/"alias.py";alias.symlink_to(empty)
            with self.assertRaises(OSError):qualify.sha_file(alias,16*g0.MIB)
            with self.assertRaisesRegex(RuntimeError,"type/cap"):qualify.sha_file(root,16*g0.MIB)
            actual=os.fstat
            def replaced(fd):
                observed=actual(fd);fields=list(observed);fields[1]+=1;return os.stat_result(fields)
            with mock.patch.object(qualify.os,"fstat",side_effect=replaced):
                with self.assertRaisesRegex(RuntimeError,"file changed"):qualify.sha_file(empty,16*g0.MIB)

    def test_v24_initial_and_precont_allocation_are_exactly_the_existing_limit(self):
        file,_,_=self.file_snapshot_fixture()
        for blocks in (0,1,262143,262145,-1,False,262144.0):
            changed=SimpleNamespace(**{**vars(file),"st_blocks":blocks})
            with self.assertRaises(RuntimeError):host.g0_allocation_observation(changed,full=True)
            with self.snapshot_environment(file=changed) as (_,_,expected,state,snapshots,_,_):
                with self.assertRaisesRegex(RuntimeError,"allocation"):host.recheck_g0_file(Path("/fixture/nvme.raw"),10,expected,evidence=Path("/evidence"),phase="pre-cont")
                self.assertFalse(state["removed"]);self.assertEqual(snapshots[0][0],"g0-file-pre-cont.json")
        self.assertEqual(host.g0_allocation_observation(file,full=True),g0.NVME_BYTES)
        for blocks in (1,262145):
            changed=SimpleNamespace(**{**vars(file),"st_blocks":blocks})
            with self.snapshot_environment(file=changed) as (_,_,_,state,snapshots,_,_):
                with mock.patch.object(host.os,"open",side_effect=[10,11]),mock.patch.object(host.os,"posix_fallocate"):
                    with self.assertRaisesRegex(RuntimeError,"allocation"):host.create_g0_file(Path("/fixture"),evidence=Path("/evidence"))
                self.assertTrue(state["removed"])
                self.assertIn("g0-file-creation-allocated.json",[name for name,_ in snapshots])

    def test_v24_later_allocation_variation_keeps_exact_identity_and_observation(self):
        original,_,_=self.file_snapshot_fixture()
        for blocks in (0,1,229944,262143,262144):
            changed=SimpleNamespace(**{**vars(original),"st_blocks":blocks})
            for phase in ("ready-before-map","ready-after-map"):
                with self.snapshot_environment(file=changed) as (_,_,expected,state,snapshots,_,_):
                    observed=host.recheck_g0_file(Path("/fixture/nvme.raw"),10,expected,evidence=Path("/evidence"),phase=phase)
                    self.assertEqual(observed["identity"][:7],expected["identity"][:7]);self.assertEqual(observed["identity"][7],blocks*512)
                    self.assertEqual(snapshots[-1][1]["expected"]["initial_allocated_bytes"],134217728)
                    self.assertEqual(snapshots[-1][1]["observations"]["opened"]["raw"][7],blocks*512)
            with self.snapshot_environment(file=changed) as (_,_,expected,state,snapshots,_,_):
                result=host.remove_g0_file(Path("/fixture/nvme.raw"),10,expected,evidence=Path("/evidence"))
                self.assertTrue(state["removed"]);self.assertEqual(result["allocation_errors"],[]);host.require_g0_removal_diagnostics(result)
                self.assertEqual(result["before"]["identity"][7],blocks*512)

    def test_v24_invalid_late_allocation_fails_acceptance_without_blocking_safe_cleanup(self):
        original,_,_=self.file_snapshot_fixture()
        for blocks in (-1,False,229944.0,262145):
            changed=SimpleNamespace(**{**vars(original),"st_blocks":blocks})
            with self.snapshot_environment(file=changed) as (_,_,expected,state,snapshots,_,_):
                with self.assertRaisesRegex(RuntimeError,"allocation"):host.recheck_g0_file(Path("/fixture/nvme.raw"),10,expected,evidence=Path("/evidence"),phase="ready-before-map")
            for failure in (False,True):
                with self.snapshot_environment(file=changed) as (_,_,expected,state,snapshots,_,close):
                    result=host.remove_g0_file(Path("/fixture/nvme.raw"),10,expected,evidence=Path("/evidence"),failure=failure)
                    self.assertTrue(state["removed"]);self.assertTrue(result["allocation_errors"])
                    with self.assertRaisesRegex(RuntimeError,"allocation"):host.require_g0_removal_diagnostics(result)
                    close.assert_any_call(10);close.assert_any_call(11)

    def test_v24_immutable_and_regular_type_changes_never_authorize_unlink(self):
        file,parent,expected=self.file_snapshot_fixture()
        for change in ({"st_mode":stat.S_IFCHR|0o600},{"st_ino":99,"st_blocks":229944},{"st_size":134217727,"st_blocks":-1}):
            changed=SimpleNamespace(**{**vars(file),**change})
            with self.snapshot_environment(file=changed) as (_,_,_,state,_,_,_):
                with self.assertRaisesRegex(RuntimeError,"host file changed"):host.remove_g0_file(Path("/fixture/nvme.raw"),10,expected,evidence=Path("/evidence"),failure=True)
                self.assertFalse(state["removed"])
        for field,value in (("st_dev",99),("st_ino",99),("st_uid",99),("st_gid",99),("st_mode",stat.S_IFDIR|0o750),("st_nlink",3)):
            changed=SimpleNamespace(**{**vars(parent),field:value})
            with self.snapshot_environment(parent=changed) as (_,_,_,state,_,_,_):
                with self.assertRaisesRegex(RuntimeError,"parent changed"):host.remove_g0_file(Path("/fixture/nvme.raw"),10,expected,evidence=Path("/evidence"),failure=True)
                self.assertFalse(state["removed"])

    def test_v24_bound_and_diagnostic_errors_preserve_safe_cleanup_and_both_failure_reasons(self):
        file,_,_=self.file_snapshot_fixture();file.st_blocks=262145
        with self.snapshot_environment(file=file,write_error=True) as (_,_,expected,state,_,_,_):
            result=host.remove_g0_file(Path("/fixture/nvme.raw"),10,expected,evidence=Path("/evidence"),failure=True)
            self.assertTrue(state["removed"]);self.assertTrue(result["diagnostic_errors"]);self.assertTrue(result["allocation_errors"])
            with self.assertRaises(RuntimeError) as error:host.require_g0_removal_diagnostics(result)
            self.assertIn("snapshot",str(error.exception));self.assertIn("allocation",str(error.exception))

    def test_v24_qmp_only_bounded_actual_size_varies_and_precont_stays_full(self):
        before=self.mapping();pre=g0.validate_mapping_response(before,"map","nvme.raw",require_full=True)
        for size in (0,512,117731328,g0.NVME_BYTES):
            after=copy.deepcopy(before);after["id"]="post";after["return"][0]["inserted"]["image"]["actual-size"]=size
            post=g0.validate_mapping_response(after,"post","nvme.raw")
            self.assertIs(g0.validate_mapping_identity(pre,post),post);self.assertEqual(post["actual-size"],size)
            if size!=g0.NVME_BYTES:
                with self.assertRaises(ValueError):g0.validate_mapping_response(after,"post","nvme.raw",require_full=True)
        for size in (-1,False,0.0,g0.NVME_BYTES+1):
            after=copy.deepcopy(before);after["return"][0]["inserted"]["image"]["actual-size"]=size
            with self.assertRaises(ValueError):g0.validate_mapping_response(after,"map","nvme.raw")
            with self.assertRaises(ValueError):g0.validate_mapping_identity(pre,{**pre,"actual-size":size})
        for key,value in (("device","other"),("file","other.raw"),("node-name","other-node")):
            with self.assertRaises(ValueError):g0.validate_mapping_identity(pre,{**pre,key:value,"actual-size":117731328})
        for mutate in (lambda x:x["return"][0]["inserted"].update(drv="qcow2"),lambda x:x["return"][0]["inserted"].update(backing_file_depth=1),lambda x:x["return"][0]["inserted"]["cache"].update(direct=False),lambda x:x["return"][0]["inserted"].update(encrypted=True)):
            after=copy.deepcopy(before);mutate(after)
            with self.assertRaises(ValueError):g0.validate_mapping_response(after,"map","nvme.raw")

    def test_v24_raw_mapping_and_ack_digests_preserve_allocation_values(self):
        before=self.mapping();after=copy.deepcopy(before);after["id"]="post";after["return"][0]["inserted"]["image"]["actual-size"]=117731328
        pre_raw=g0.canonical(before)+b"\r\n";post_raw=g0.canonical(after)+b"\r\n"
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);evidence=root/"evidence";evidence.mkdir()
            pre=host.retain_private_mapping(root,evidence,"pre",pre_raw,before);post=host.retain_private_mapping(root,evidence,"post",post_raw,after)
            self.assertEqual((evidence/"g0-qmp-map-pre.raw.json").read_bytes(),pre_raw)
            self.assertEqual((evidence/"g0-qmp-map-post.raw.json").read_bytes(),post_raw)
            self.assertNotEqual(pre["raw_sha256"],post["raw_sha256"])
            self.assertEqual(post["response"]["return"][0]["inserted"]["image"]["actual-size"],117731328)
            ack={"schema":"dm-g0-ack-v1","nonce":self.nonce,"binding":self.binding,"binding_transport":g0.BINDING_TRANSPORT,"ready_sha256":"1"*64,"pre_mapping_sha256":g0.sha256(pre_raw),"post_mapping_sha256":g0.sha256(post_raw)}
            g0.validate_ack(g0.parse_ack(g0.build_ack(ack)),nonce=self.nonce,binding=self.binding,ready_digest="1"*64,pre_digest=g0.sha256(pre_raw),post_digest=g0.sha256(post_raw))
            with self.assertRaises(ValueError):g0.validate_ack(ack,nonce=self.nonce,binding=self.binding,ready_digest="1"*64,pre_digest=g0.sha256(pre_raw),post_digest=g0.sha256(pre_raw))

    def guard_context(self):
        return {"nonce":self.nonce,"binding":self.binding,"manifest_sha256":self.manifest_sha,"guard_count":0}

    def guard_binding(self):
        return {"nonce":self.nonce,"binding":self.binding,"manifest_sha256":self.manifest_sha}

    def guard_record(self,index=0,namespace=None,nvme=None):
        ns=namespace if namespace is not None else self.qualifier()["partitions"][0]["mount_namespace"]
        nv=nvme if nvme is not None else self.nvme()
        return {"schema":"dm-g0-guard-observation-v1","nonce":self.nonce,"binding":self.binding,"seed_manifest_sha256":self.manifest_sha,
                "ordinal":index,"phase":g0.GUARD_PHASES[index],"evaluated":{"namespace":True,"nvme":True},
                "namespace":g0.guard_operand("matched",copy.deepcopy(ns),copy.deepcopy(ns)),
                "nvme":g0.guard_operand("matched",copy.deepcopy(nv),copy.deepcopy(nv)),"decision":"matched"}

    def guard_wire(self,records):
        return b"".join(g0.build_frame(g0.GUARD_PREFIX,item,g0.GUARD_FRAME_MAX) for item in records)

    def test_v25_guard_reads_once_in_original_order_and_short_circuits_namespace(self):
        ns=self.guard_record()["namespace"]["saved"];nv=self.nvme();events=[];frames=[]
        for changed in (False,True):
            events.clear();frames.clear();current={**ns,"ino":99} if changed else copy.deepcopy(ns)
            with (mock.patch.object(setup,"mount_namespace",side_effect=lambda:(events.append("namespace"),current)[1]) as nsread,
                  mock.patch.object(setup,"nvme_preflight",side_effect=lambda *a,**k:(events.append("nvme"),nv)[1]) as nvread,
                  mock.patch.object(setup,"serial_frame",side_effect=lambda p,v:frames.append(v))):
                if changed:
                    with self.assertRaisesRegex(RuntimeError,"pre-unmount device/namespace changed"):
                        setup.observe_unmount_guard(ns,nv,"serial",phase=g0.GUARD_PHASES[0],context=self.guard_context())
                else:setup.observe_unmount_guard(ns,nv,"serial",phase=g0.GUARD_PHASES[0],context=self.guard_context())
                nsread.assert_called_once_with()
                if changed:nvread.assert_not_called()
                else:nvread.assert_called_once_with("serial",partitions_present=True)
            self.assertEqual(events,["namespace"] if changed else ["namespace","nvme"])
            frame=frames[0];g0.validate_guard_record(frame,**self.guard_binding())
            self.assertEqual(frame["nvme"]["status"],"not_evaluated" if changed else "matched")
            if changed:self.assertIsNone(frame["nvme"]["saved"]);self.assertEqual(frame["namespace"]["diff_paths"],[{"path":"/ino","kind":"value_changed"}])

    def test_v25_guard_full_nvme_security_and_list_index_diffs_are_retained(self):
        ns=self.guard_record()["namespace"]["saved"];before=self.nvme();after=copy.deepcopy(before);frames=[]
        after["partitions"][1]["node_identity"][3]=99;after["partitions"][0]["node_identity"][4]=0o600
        after["controller_identity"][2]=1
        with (mock.patch.object(setup,"mount_namespace",return_value=ns),mock.patch.object(setup,"nvme_preflight",return_value=after),
              mock.patch.object(setup,"serial_frame",side_effect=lambda p,v:frames.append(v))):
            with self.assertRaisesRegex(RuntimeError,"pre-unmount device/namespace changed"):
                setup.observe_unmount_guard(ns,before,"serial",phase=g0.GUARD_PHASES[0],context=self.guard_context())
        record=frames[0];self.assertEqual(record["nvme"]["saved"],before);self.assertEqual(record["nvme"]["current"],after)
        self.assertEqual([item["path"] for item in record["nvme"]["diff_paths"]],["/controller_identity/2","/partitions/0/node_identity/4","/partitions/1/node_identity/3"])
        g0.validate_guard_record(record,**self.guard_binding())

    def test_v25_diff_added_removed_types_escaping_and_finite_bounds(self):
        self.assertEqual(g0.guard_diff({"a/b":[1,2],"gone":0,"n":1},{"a/b":[1],"new~":2,"n":True}),[
            {"path":"/a~1b/1","kind":"removed"},{"path":"/gone","kind":"removed"},{"path":"/n","kind":"type_changed"},{"path":"/new~0","kind":"added"}])
        for before,after in (({},dict.fromkeys(map(str,range(129)),0)),({}, {"x"*256:0})):
            with self.assertRaisesRegex(ValueError,"diff cap"):g0.guard_diff(before,after)
        numeric=self.guard_record();numeric["nvme"]["current"]["bytes"]=float(g0.NVME_BYTES)
        numeric["nvme"]["diff_paths"]=g0.guard_diff(numeric["nvme"]["saved"],numeric["nvme"]["current"])
        g0.validate_guard_record(numeric,**self.guard_binding());self.assertEqual(numeric["decision"],"matched")

    def test_v25_collection_exception_identity_traceback_and_diagnostic_secondary(self):
        ns=self.guard_record()["namespace"]["saved"];nv=self.nvme()
        for where in ("namespace","nvme"):
            for diagnostic_failure in (False,True):
                original=OSError(5,"collection failure");frames=[]
                def original_collection(*args,**kwargs):raise original
                with (mock.patch.object(setup,"mount_namespace",side_effect=original_collection if where=="namespace" else lambda:ns),
                      mock.patch.object(setup,"nvme_preflight",side_effect=original_collection if where=="nvme" else lambda *a,**k:nv) as nvr,
                      mock.patch.object(setup,"serial_frame",side_effect=OSError("wire failure") if diagnostic_failure else lambda p,v:frames.append(v))):
                    try:setup.observe_unmount_guard(ns,nv,"serial",phase=g0.GUARD_PHASES[0],context=self.guard_context())
                    except OSError as observed:
                        self.assertIs(observed,original);names=[];tb=observed.__traceback__
                        while tb:names.append(tb.tb_frame.f_code.co_name);tb=tb.tb_next
                        self.assertIn("original_collection",names)
                        if diagnostic_failure:self.assertIn("guard diagnostic failure",str(observed.__notes__))
                    else:self.fail("collection exception lost")
                    if where=="namespace":nvr.assert_not_called()
                if frames:
                    frame=frames[0];g0.validate_guard_record(frame,**self.guard_binding());self.assertEqual(frame["decision"],where+"_error")
                    self.assertIsNone(frame[where]["current"]);self.assertEqual(frame[where]["error"]["errno"],5)

    def test_v25_diagnostic_overflow_and_emission_failure_never_green_or_mask_mismatch(self):
        ns=self.guard_record()["namespace"]["saved"];before=self.nvme()
        for matched in (False,True):
            after={**before,"padding":"x"*20000};saved=after if matched else before;frames=[]
            with (mock.patch.object(setup,"mount_namespace",return_value=ns),mock.patch.object(setup,"nvme_preflight",return_value=after),
                  mock.patch.object(setup,"serial_frame",side_effect=lambda p,v:frames.append(v))):
                expected="guard diagnostic failure" if matched else "device/namespace changed"
                with self.assertRaisesRegex(RuntimeError,expected):setup.observe_unmount_guard(ns,saved,"serial",phase=g0.GUARD_PHASES[0],context=self.guard_context())
            record=frames[0];g0.validate_guard_record(record,**self.guard_binding());self.assertEqual(record["decision"],"diagnostic_overflow")
            self.assertEqual(record["evaluated"],{"namespace":True,"nvme":True});self.assertIsNone(record["nvme"]["current"])
        with (mock.patch.object(setup,"mount_namespace",return_value=ns),mock.patch.object(setup,"nvme_preflight",return_value=before),mock.patch.object(setup,"serial_frame",side_effect=OSError("wire failure"))):
            with self.assertRaisesRegex(RuntimeError,"guard diagnostic failure"):setup.observe_unmount_guard(ns,before,"serial",phase=g0.GUARD_PHASES[0],context=self.guard_context())

    def test_v25_production_main_all_guard_failure_phases_and_transport_failure_cleanup(self):
        for phase in g0.GUARD_PHASES:
            self.exercise_mocked_guest_main(guard_failure=phase)
        self.exercise_mocked_guest_main(diagnostic_failure=True)
        self.exercise_mocked_guest_main(guard_failure=g0.GUARD_PHASES[0],diagnostic_failure=True)

    def test_v25_guard_error_utf8_byte_bounds_are_truthful(self):
        error=g0.guard_error(OSError(5,"é"*400));g0.validate_guard_error(error)
        self.assertEqual(len(error["message"].encode()),512);self.assertTrue(error["message_truncated"]);self.assertEqual(error["class"],"builtins.OSError")
        for mutate in (lambda x:x.update(message="é"*257),lambda x:x.update(errno=False),lambda x:x.update(message_truncated=1),lambda x:x.update(extra=0)):
            bad=copy.deepcopy(error);mutate(bad)
            with self.assertRaises(ValueError):g0.validate_guard_error(bad)

    def test_v25_guard_parser_strict_shape_order_binding_diff_and_complete_lines(self):
        records=[self.guard_record(i) for i in range(3)];raw=self.guard_wire(records)
        self.assertEqual(g0.parse_guard_frames(raw,**self.guard_binding()),records)
        for invalid in (raw+raw,raw+b"DMG0GUA",self.guard_wire([records[1]]),self.guard_wire([records[0],records[0]]),raw[:-1],raw.replace(b'"matched"',b'"changed"',1)):
            with self.assertRaises(ValueError):g0.parse_guard_frames(invalid,**self.guard_binding())
        for mutate in (lambda x:x.update(ordinal=False),lambda x:x.update(nonce="0"*32),lambda x:x.update(extra=0),
                       lambda x:x["evaluated"].update(nvme=False),lambda x:x["nvme"].update(diff_paths=[{"path":"/bytes","kind":"value_changed"}]),
                       lambda x:x["nvme"]["current"].update(bytes=0)):
            bad=self.guard_record();mutate(bad)
            with self.assertRaises(ValueError):g0.validate_guard_record(bad,**self.guard_binding())

    def test_v25_guard_whole_wire_boundary_reserves_crlf_and_chunk_reassembly(self):
        record=self.guard_record();base=copy.deepcopy(record)
        low,high=0,g0.GUARD_FRAME_MAX
        while low<high:
            middle=(low+high+1)//2;candidate=copy.deepcopy(base)
            for side in ("saved","current"):candidate["nvme"][side]["padding"]="x"*middle
            try:g0.build_frame(g0.GUARD_PREFIX,candidate,g0.GUARD_FRAME_MAX);low=middle
            except ValueError:high=middle-1
        for side in ("saved","current"):record["nvme"][side]["padding"]="x"*low
        wire=self.guard_wire([record]);crlf=wire[:-1]+b"\r\n";self.assertLessEqual(len(crlf),g0.GUARD_FRAME_MAX)
        self.assertEqual(g0.parse_guard_frames(crlf,**self.guard_binding()),[record])
        pieces=[crlf[:11],crlf[11:-1],crlf[-1:]];self.assertEqual(g0.parse_guard_frames(b"".join(pieces),**self.guard_binding()),[record])
        for side in ("saved","current"):record["nvme"][side]["padding"]+="x"
        with self.assertRaises(ValueError):self.guard_wire([record])

    def test_v25_host_artifact_invalid_sequence_never_exports_selected_subset(self):
        records=[self.guard_record(i) for i in range(3)]
        for stream,status,count in ((b"","partial",0),(self.guard_wire(records[:2]),"partial",2),(self.guard_wire(records),"complete",3),
                                    (self.guard_wire(records+records[:1]),"invalid",0),(self.guard_wire(records)[:-1],"invalid",0),
                                    (self.guard_wire([records[1]]),"invalid",0)):
            with tempfile.TemporaryDirectory() as temporary:
                receipt=host.retain_guard_observations(Path(temporary),stream,self.guard_binding())
                self.assertEqual(receipt["status"],status);self.assertEqual(len(receipt["records"]),count)
                self.assertEqual(json.loads((Path(temporary)/"g0-guard-observations.json").read_bytes()),receipt)
                if status=="invalid":self.assertIsNotNone(receipt["error"])

    def test_v25_artifact_overflow_persists_invalid_then_raises_and_primary_survives(self):
        records=[self.guard_record(i) for i in range(3)]
        with tempfile.TemporaryDirectory() as temporary,mock.patch.object(host.g0,"parse_guard_frames",return_value=records):
            original=host.canonical
            def too_large(value):
                return b"x"*(g0.GUARD_ARTIFACT_MAX+1) if value.get("records") else original(value)
            with mock.patch.object(host,"canonical",side_effect=too_large):
                with self.assertRaisesRegex(RuntimeError,"guard artifact overflow"):host.retain_guard_observations(Path(temporary),b"",self.guard_binding())
            receipt=json.loads((Path(temporary)/"g0-guard-observations.json").read_bytes());self.assertEqual(receipt["status"],"invalid");self.assertEqual(receipt["records"],[])
        error=RuntimeError("original failure")
        def failing_retention():raise OSError("diagnostic persistence")
        result=host.preserve_primary_during_diagnostic(str(error),"guard observation",failing_retention)
        self.assertTrue(result.startswith("original failure"));self.assertIn("OSError",result)

    def test_v25_guard_success_mandatory_three_and_saved_current_crossbinding(self):
        ready=self.ready();result=self.result();records=[self.guard_record(i) for i in range(3)]
        g0.bind_guard_records(records,ready,result)
        for mutate in (lambda x:x.pop(),lambda x:x.reverse(),lambda x:x[1]["namespace"]["saved"].update(ino=99),
                       lambda x:x[1]["nvme"]["current"]["node_identity"].__setitem__(3,99),lambda x:x[2].update(decision="diagnostic_overflow")):
            bad=copy.deepcopy(records);mutate(bad)
            with self.assertRaises(ValueError):g0.bind_guard_records(bad,ready,result)
        bad=copy.deepcopy(ready);bad["qualifier"]["partitions"][1]["mount_namespace"]["ino"]=99
        with self.assertRaises(ValueError):g0.bind_guard_records(records,bad,result)

    def test_v25_setup_ast_restores_exactly_two_old_guards_and_one_context_field(self):
        tree=strip_v27_setup(ast.parse((HERE/"guest_g0_setup.py").read_text()));tree.body=[node for node in tree.body if not isinstance(node,ast.FunctionDef) or node.name!="observe_unmount_guard"]
        restored=0;context_removed=0
        class Restore(ast.NodeTransformer):
            def visit_Expr(inner,node):
                nonlocal restored
                if isinstance(node.value,ast.Call) and isinstance(node.value.func,ast.Name) and node.value.func.id=="observe_unmount_guard":
                    phase=node.value.keywords[0].value
                    message="pre-unmount device/namespace changed" if isinstance(phase,ast.Constant) else "per-unmount device/namespace changed"
                    restored+=1
                    return ast.parse('if mount_namespace()!=namespace or nvme_preflight(config["nvme_serial"],partitions_present=True)!=nvme: raise RuntimeError('+repr(message)+')').body[0]
                return inner.generic_visit(node)
            def visit_Dict(inner,node):
                nonlocal context_removed
                for index,key in reversed(list(enumerate(node.keys))):
                    if isinstance(key,ast.Constant) and key.value=="guard_count":node.keys.pop(index);node.values.pop(index);context_removed+=1
                return inner.generic_visit(node)
        tree=Restore().visit(tree);self.assertEqual((restored,context_removed),(2,1))
        self.assertEqual(hashlib.sha256(ast.dump(tree,include_attributes=False).encode()).hexdigest(),"7b2219a7016d9362bcda035aac3302e7472629b6b870b0c52babb7776cde2baa")
        source=ast.parse((HERE/"host_controller.py").read_text());boot=next(node for node in source.body if isinstance(node,ast.FunctionDef) and node.name=="boot")
        calls=[node for node in ast.walk(boot) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=="bind_guard_records"]
        self.assertEqual(len(calls),1)

    def test_v25_original_policy_ast_unchanged_outside_new_guard_protocol(self):
        tree=strip_v27_policy(ast.parse((HERE/"g0_policy.py").read_text()))
        functions={"guard_error","validate_guard_error","guard_diff","guard_operand","guard_overflow","validate_guard_record","parse_guard_frames","bind_guard_records"}
        constants={"GUARD_PREFIX","GUARD_FRAME_MAX","GUARD_ARTIFACT_MAX","GUARD_PHASES"}
        def new(node):
            return ((isinstance(node,ast.FunctionDef) and node.name in functions) or
                    (isinstance(node,ast.Assign) and len(node.targets)==1 and isinstance(node.targets[0],ast.Name) and node.targets[0].id in constants))
        removed=[node for node in tree.body if new(node)];self.assertEqual(len(removed),12)
        tree.body=[node for node in tree.body if not new(node)]
        self.assertEqual(hashlib.sha256(ast.dump(tree,include_attributes=False).encode()).hexdigest(),"256013c29d52020caaa445056c0747cc9d22d4ebe0b361a329103cc273206fa4")

    def initialization_record(self):
        targets=[]
        for part in self.nvme()["partitions"]:
            raw=b"I:100\nE:generated=1\n";targets.append({"number":part["number"],"sysfs_path":"/sys/class/block/"+part["name"],"dev":part["dev"],"database_bytes":len(raw),"database_sha256":g0.sha256(raw),"initialized_line_base64":base64.b64encode(b"I:100\n").decode()})
        return {"schema":"dm-g0-initialization-v1","nonce":self.nonce,"binding":self.binding,"seed_manifest_sha256":self.manifest_sha,"tool":{"path":g0.INIT_UDEVADM,"identity":[1,2,stat.S_IFREG|0o755,0,0,1,3],"sha256":g0.sha256(b"elf"),"package":"udev","version":g0.INIT_VERSION,"architecture":"amd64"},"targets":targets,"ordinals":[12,13,15]}

    def initialization_stream(self):
        result=self.result();rule=result["udev_rule"];rule["owner"]["version"]=g0.INIT_VERSION
        rule["version_query"]=self.tool_result(rule["version_query"]["argv"],stdout="udev\t"+g0.INIT_VERSION+"\tamd64\n")
        values=[]
        for tool in result["tools"]+[rule]:values.extend((tool["owner_query"],tool["version_query"]))
        owner=self.tool_result(["/usr/bin/dpkg-query","-S",g0.INIT_UDEVADM],stdout="udev: "+g0.INIT_UDEVADM+"\n")
        help=self.tool_result([g0.INIT_UDEVADM,"wait","--help"],stdout="udevadm wait --initialized=BOOL --timeout=SEC\n")
        init=self.initialization_record();wait=self.tool_result([g0.INIT_UDEVADM,"wait","--initialized=true","--timeout=10",*[item["sysfs_path"] for item in init["targets"]]])
        values.extend((owner,help,result["commands"][0],wait));values.extend(result["commands"][1:]);records=[];context={"nonce":self.nonce,"binding":self.binding,"manifest_sha256":self.manifest_sha,"tool_count":0}
        with mock.patch.object(setup,"serial_frame",side_effect=lambda prefix,value:records.append(g0.build_frame(prefix,value,g0.FRAME_MAX))):
            for index,value in enumerate(values):
                capture={"stdout":bytearray(value["stdout_text"].encode()),"stderr":bytearray(value["stderr_text"].encode()),"stdout_eof":True,"stderr_eof":True,"returncode":0,"child_reaped":True}
                setup.emit_tool_capture(context,value["argv"],b"" if index!=14 else self.partition_input(),capture,None,"complete")
                if index==15:records.append(g0.build_frame(g0.INIT_PREFIX,init,g0.INIT_MAX))
        records.append(g0.build_frame(g0.READY_PREFIX,self.ready(),g0.FRAME_MAX));return b"".join(records),init,result

    def partition_input(self):
        return ("label: gpt\nunit: sectors\n\n"+f"/dev/nvme0n1p1 : start=2048, size=122880, type={setup.GUID}\n"+f"/dev/nvme0n1p2 : start=124928, size=131072, type={setup.GUID}\n").encode()

    def test_v27_full_raw23_order_and_exact_three_new_calls_before_unchanged20_binder(self):
        stream,init,result=self.initialization_stream();value=g0.parse_initialization(stream,nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest_sha,nvme=result["nvme"],udev_rule=result["udev_rule"])
        receipts=g0.parse_tool_frames(stream,nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest_sha,require_complete=True)
        projected=g0.bind_initialization_tool_receipts(receipts,value,stream);self.assertEqual([item["metadata"]["ordinal"] for item in projected],[i for i in range(23) if i not in g0.INIT_ORDINALS]);g0.bind_tool_receipts(projected,result)
        for ordinal in g0.INIT_ORDINALS:
            bad=copy.deepcopy(receipts);bad[ordinal]["metadata"]["argv"]=[g0.INIT_UDEVADM,"settle"]
            with self.assertRaises(ValueError):g0.bind_initialization_tool_receipts(bad,init,stream)
        lines=g0.serial_records(stream);line=next(item for item in lines if item.startswith(g0.INIT_PREFIX));lines.remove(line);lines.insert(0,line)
        with self.assertRaisesRegex(ValueError,"full stream order"):g0.bind_initialization_tool_receipts(receipts,init,b"".join(lines))

    def test_v27_ready_facts_reject_missing_target_changed_rdev_zero_I_and_wrong_version(self):
        for mutate in (lambda x:x["targets"].pop(),lambda x:x["targets"][1].update(dev=[259,99]),lambda x:x["targets"][0].update(initialized_line_base64=base64.b64encode(b"I:0\n").decode()),lambda x:x["tool"].update(version="other"),lambda x:x.update(ordinals=[12,13,16])):
            value=self.initialization_record();mutate(value)
            with self.assertRaises(ValueError):g0.validate_initialization(value,nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest_sha,nvme=self.nvme())

    def test_v27_selected_wait_once_and_actual_positive_I_facts_before_baseline(self):
        init=self.initialization_record();state={"fd":44,"fact":init["tool"]};parts=[{"number":i["number"],"name":i["sysfs_path"].rsplit("/",1)[1],"dev":i["dev"]} for i in init["targets"]];context={}
        with mock.patch.object(setup,"check_initialization_executable") as check,mock.patch.object(setup,"run_tool",return_value=self.tool_result([])) as command,mock.patch.object(setup,"read_attr",side_effect=["259:1","259:2"]),mock.patch.object(setup,"stable_file",return_value=(b"I:100\nE:generated=1\n",{})):
            actual=setup.wait_selected_initialization(state,parts,{"nonce":self.nonce},self.binding,self.manifest_sha,context)
        self.assertEqual(actual,init);command.assert_called_once_with([g0.INIT_UDEVADM,"wait","--initialized=true","--timeout=10",*[p["sysfs_path"] for p in init["targets"]]],timeout=10,output_cap=256,diagnostics=context);self.assertEqual(check.call_count,2)
        with mock.patch.object(setup,"check_initialization_executable"),mock.patch.object(setup,"run_tool",side_effect=TimeoutError("selected wait")),mock.patch.object(setup,"stable_file") as database:
            with self.assertRaises(TimeoutError):setup.wait_selected_initialization(state,parts,{"nonce":self.nonce},self.binding,self.manifest_sha,context)
            database.assert_not_called()

    def test_v27_timeout_does_not_capture_first_partition_baseline_or_probe(self):
        self.exercise_mocked_guest_main(initialization_failure=True)

    def test_v27_actual_owner_help_preflight_and_FD_cleanup_on_unsupported_options(self):
        st=SimpleNamespace(st_dev=1,st_ino=2,st_mode=stat.S_IFREG|0o755,st_uid=0,st_gid=0,st_nlink=1,st_size=3)
        rule={"owner":{"package":"udev","version":g0.INIT_VERSION,"architecture":"amd64"}}
        for supported in (True,False):
            def command(argv,**kwargs):return self.tool_result(argv,stdout="udev: "+g0.INIT_UDEVADM+"\n" if argv[0]=="/usr/bin/dpkg-query" else "wait --initialized=BOOL --timeout=SEC\n" if supported else "unsupported\n")
            with mock.patch.object(setup.os,"lstat",return_value=st),mock.patch.object(setup.os,"stat",return_value=st),mock.patch.object(setup.os,"open",return_value=44),mock.patch.object(setup.os,"fstat",return_value=st),mock.patch.object(setup.os,"read",side_effect=[b"elf",b""]),mock.patch.object(setup.os,"close") as close,mock.patch.object(setup,"run_tool",side_effect=command) as run:
                if supported:
                    state=setup.prepare_initialization_tool(rule,{});self.assertEqual(state["fact"],self.initialization_record()["tool"]);setup.close_initialization_tool(state)
                else:
                    with self.assertRaisesRegex(RuntimeError,"options"):setup.prepare_initialization_tool(rule,{})
                close.assert_called_once_with(44);self.assertEqual([call.kwargs["output_cap"] for call in run.call_args_list],[512,1024])

    def test_v27_changed_executable_and_database_fail_without_retry(self):
        init=self.initialization_record();state={"fd":44,"fact":init["tool"]};st=SimpleNamespace(st_dev=1,st_ino=3,st_mode=stat.S_IFREG|0o755,st_uid=0,st_gid=0,st_nlink=1,st_size=3)
        with mock.patch.object(setup.os,"fstat",return_value=st),mock.patch.object(setup.os,"stat",return_value=st):
            with self.assertRaisesRegex(RuntimeError,"executable changed"):setup.check_initialization_executable(state)
        parts=[{"number":i["number"],"name":i["sysfs_path"].rsplit("/",1)[1],"dev":i["dev"]} for i in init["targets"]]
        for raw in (b"",b"I:0\n",b"I:1\nI:2\n"):
            with mock.patch.object(setup,"check_initialization_executable"),mock.patch.object(setup,"run_tool",return_value=self.tool_result([])),mock.patch.object(setup,"read_attr",return_value="259:1"),mock.patch.object(setup,"stable_file",return_value=(raw,{})):
                with self.assertRaisesRegex(RuntimeError,"positive I"):setup.wait_selected_initialization(state,parts,{"nonce":self.nonce},self.binding,self.manifest_sha,{})

    def test_v27_new_wire_bound_and_unchanged_global_caps(self):
        self.assertEqual(3*1280+6*448+4792+2048,13368);self.assertLessEqual(4178896+13368,host.policy.SERIAL_MAX)
        value=self.initialization_record();self.assertLessEqual(len(g0.build_frame(g0.INIT_PREFIX,value,g0.INIT_MAX))+1,2048)
        stream,init,result=self.initialization_stream();self.assertLess(sum(len(line) for line in g0.serial_records(stream) if line.startswith(g0.INIT_PREFIX)),2048)
        self.assertEqual((host.policy.SERIAL_MAX,host.policy.STREAM_MAX),(4194304,1048576))

    def test_v27_only_readiness_plumbing_changes_whole_setup_and_policy_AST(self):
        self.assertEqual(hashlib.sha256(ast.dump(strip_v27_setup(ast.parse((HERE/"guest_g0_setup.py").read_text()))).encode()).hexdigest(),"47324471ba10d64770c6fb699817e2face483a3e35d2cc544263a0fdf865c91d")
        self.assertEqual(hashlib.sha256(ast.dump(strip_v27_policy(ast.parse((HERE/"g0_policy.py").read_text()))).encode()).hexdigest(),"584722703cf6b45cbdf85381fbd3b1b2f94c1351a6c7943dd0a48af28a6202b4")

    def test_source_keeps_one_paused_nvme_and_no_forbidden_storage_paths(self):
        host=(HERE/"host_controller.py").read_text(); setup=(HERE/"guest_g0_setup.py").read_text(); qualifier=(HERE/"guest_g0_qualify.py").read_text()
        self.assertIn('"-accel", "tcg,thread=single", "-S"',host)
        self.assertIn('"if=none,id=g0data,file=nvme.raw,format=raw,cache=none,aio=threads"',host)
        self.assertNotIn("-fw_cfg",host); self.assertNotIn("modprobe",setup); self.assertNotIn("subprocess",qualifier)
        self.assertIn("os.O_NONBLOCK",setup); self.assertIn("pidfd_send_signal",setup)


if __name__=="__main__": unittest.main()
