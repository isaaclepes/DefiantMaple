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

    def exercise_mocked_guest_main(self,fail_mount=False):
        # Production orchestration runs with every storage/product/device boundary mocked.
        # Only disposable ordinary directories are created to exercise real mkdir/rmdir nlink changes.
        with tempfile.TemporaryDirectory() as temporary,contextlib.ExitStack() as stack:
            root=Path(temporary)/"mount-root"; mounts=[str(root/"p1"),str(root/"p2")]
            config={"nonce":self.nonce,"mounts":mounts,"nvme_serial":"DMG0"+self.nonce[:16],"probe_name":"dm-g0-probe.bin",
                    "deadlines":{"sfdisk":1,"mkfs_ext4":1,"mount":1,"umount":1,"ack":1,"ordinary_child":1}}
            namespace=self.qualifier()["partitions"][0]["mount_namespace"]; nvme=self.nvme(); active={}; calls=[]; frames=[]
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
            patch("tool_facts",return_value=[]); patch("udev_rule_fact",return_value=self.udev_rule()); patch("nvme_preflight",return_value=nvme)
            patch("mount_namespace",return_value=namespace); patch("mountinfo",side_effect=snapshot); patch("run_tool",side_effect=command)
            patch("wait_partitions",return_value=[]); patch("root_fd_inventory",side_effect=lambda ids,phase:{"phase":phase})
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
            patch("read_ack",return_value=({},b"mock ack")); patch("serial_frame",side_effect=lambda prefix,value:frames.append((prefix,value)))
            try:
                if fail_mount:
                    with self.assertRaisesRegex(RuntimeError,"mount output capture failure after side effect"): setup.main()
                    os.close(ack_fd)  # acquisition was mocked but main never reached ACK on this path
                else: setup.main()
            finally:
                self.assertEqual(active,{})
            self.assertFalse(root.exists())
            unmounts=[argv[-1] for argv in calls if argv[0]=="/usr/bin/umount"]
            self.assertEqual(unmounts,[mounts[0]] if fail_mount else list(reversed(mounts)))
            self.assertEqual(sum(prefix==g0.RESULT_PREFIX for prefix,_ in frames),0 if fail_mount else 1)

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
        stream=b"".join(records); receipts=g0.parse_tool_frames(stream,nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest_sha,require_complete=True)
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
        parent=SimpleNamespace(st_dev=1,st_ino=2,st_uid=os.getuid(),st_gid=os.getgid(),st_mode=stat.S_IFDIR|0o700,st_nlink=2)
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

    def test_source_keeps_one_paused_nvme_and_no_forbidden_storage_paths(self):
        host=(HERE/"host_controller.py").read_text(); setup=(HERE/"guest_g0_setup.py").read_text(); qualifier=(HERE/"guest_g0_qualify.py").read_text()
        self.assertIn('"-accel", "tcg,thread=single", "-S"',host)
        self.assertIn('"if=none,id=g0data,file=nvme.raw,format=raw,cache=none,aio=threads"',host)
        self.assertNotIn("-fw_cfg",host); self.assertNotIn("modprobe",setup); self.assertNotIn("subprocess",qualifier)
        self.assertIn("os.O_NONBLOCK",setup); self.assertIn("pidfd_send_signal",setup)


if __name__=="__main__": unittest.main()
