from __future__ import annotations
import ast,base64,copy,hashlib,importlib.util,json,stat,unittest,contextlib
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
HERE=Path(__file__).resolve().parent
def load(name):
    spec=importlib.util.spec_from_file_location("test_life_"+name,HERE/(name+".py"));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
life=load("setup_lifecycle_policy");guest=load("guest_setup_lifecycle");host=load("host_controller")
fixtures=load("test_g0_policy").G0PolicyTests()
class LifecycleTests(unittest.TestCase):
    binding={"nonce":"a"*32,"binding":"b"*64,"manifest_sha256":"c"*64}
    devpath="/devices/pci0000:00/0000:00:03.0/nvme/nvme0/nvme0n1"
    def doc(self):return life.new_document(**self.binding)
    def event(self,source="KERNEL",path=None,seq=100,action="add"):
        path=self.devpath if path is None else path
        return f"{source:<6}[12.123456] {action:<8} {path} (block)\nACTION={action}\nDEVPATH={path}\nSUBSYSTEM=block\nSEQNUM={seq}\n\n".encode()
    def parser(self):
        fact=life.empty_observer();parser=life.MonitorParser(fact,self.devpath);parser.feed("stdout",life.BANNER,1);return fact,parser
    def test_separate_protocol_roundtrip_crlf_binding_and_no_G0_success(self):
        doc=self.doc();wires=life.frames(doc);value,raw,terminal=life.parse(b"".join(wires).replace(b"\n",b"\r\n"),**self.binding)
        self.assertEqual(value,doc);self.assertEqual(raw,life.canonical(doc));self.assertTrue(terminal["observation_only"]);self.assertIs(terminal["g0_qualified"],False)
        self.assertIs(terminal["product_probes_executed"],False);self.assertIs(terminal["enospc_tested"],False)
    def test_protocol_rejects_missing_duplicate_order_partial_changed_binding_and_G0_streams(self):
        wires=life.frames(self.doc());raw=b"".join(wires)
        bad=[raw[:-1],raw+raw,b"".join(wires[1:]),wires[0]+wires[-1]+wires[1],raw+b"DMG0READY1 bad\n",raw.replace(b'"scope"',b'"Scope"',1)]
        for value in bad:
            with self.assertRaises(ValueError):life.parse(value,**self.binding)
        with self.assertRaises(ValueError):life.parse(raw,**{**self.binding,"binding":"d"*64})
    def test_protocol_per_frame_counts_and_decoded_caps(self):
        self.assertLessEqual(sum(map(len,life.frames(self.doc()))),4096+64*44462+16384)
        for kind,mutate in (("snapshot",lambda d:d["snapshots"].extend([{}]*15)),("commands",lambda d:d["commands"].extend([{}]*26)),("markers",lambda d:d["markers"].extend([{}]*129))):
            doc=self.doc();mutate(doc)
            with self.assertRaises(ValueError):life.validate_document(doc,**self.binding)
    def test_observer_banner_requires_exact_complete_subscription_receipt(self):
        fact=life.empty_observer();parser=life.MonitorParser(fact,self.devpath)
        parser.feed("stdout",life.BANNER[:-1],1);self.assertFalse(fact["ready"])
        parser.feed("stdout",life.BANNER[-1:],2);self.assertTrue(fact["ready"])
        for bad in (b"ready\n",life.BANNER.replace(b"KERNEL",b"WRONG!")):
            with self.assertRaises(ValueError):life.MonitorParser(life.empty_observer(),self.devpath).feed("stdout",bad,1)
    def test_selected_raw_namespace_and_descendants_discard_unrelated_without_false_loss_claim(self):
        fact,p=self.parser();one=self.event();part=self.event("UDEV",self.devpath+"/nvme0n1p1",100);other=self.event(path="/devices/unrelated/block/vda",seq=105)
        p.feed("stdout",one+other+part,10);p.finish()
        self.assertEqual([life.unb64(x["raw_base64"],32768) for x in fact["selected"]],[one,part])
        self.assertEqual([x["source"] for x in fact["selected"]],["KERNEL","UDEV"]);self.assertEqual(fact["discarded"]["stdout_records"],1)
        self.assertEqual(fact["discarded"]["stdout_sha256"],life.sha(other));self.assertNotIn("lossless",fact)
    def test_unexpected_selected_descendant_is_retained_then_stops(self):
        fact,p=self.parser();raw=self.event(path=self.devpath+"/nvme0n1p3")
        with self.assertRaisesRegex(ValueError,"unexpected selected descendant"):p.feed("stdout",raw,10)
        self.assertEqual(life.unb64(fact["selected"][0]["raw_base64"],32768),raw);self.assertEqual(fact["selected"][0]["classification"],"unexpected-descendant")
    def test_per_stream_per_record_first_and_last_byte_receipt_interleaving(self):
        fact,p=self.parser();one=self.event();two=self.event("UDEV",seq=101)
        p.feed("stdout",one[:20],10);p.feed("stderr",b"Calling monitor\n",20);p.feed("stdout",one[20:]+two[:8],30);p.feed("stderr",b"Calling monitor\n",40);p.feed("stdout",two[8:],50)
        self.assertEqual([(x["first_ns"],x["last_ns"]) for x in fact["selected"]],[(10,30),(30,50)])
        self.assertEqual(fact["selected"][1]["start_offset"],len(life.BANNER)+len(one));p.finish()
    def test_arbitrary_single_byte_chunks_and_duplicate_sequences_preserve_receipt_order(self):
        fact,p=self.parser();raw=self.event("UDEV",seq=101)+self.event("KERNEL",seq=100)
        for index,byte in enumerate(raw):p.feed("stdout",bytes([byte]),1000+index)
        self.assertEqual([x["sequence"] for x in fact["selected"]],[101,100]);self.assertEqual([x["source"] for x in fact["selected"]],["UDEV","KERNEL"])
        self.assertLess(fact["selected"][0]["last_ns"],fact["selected"][1]["first_ns"])
    def test_parser_gaps_loss_diagnostics_and_caps_do_not_claim_complete_capture(self):
        for raw in (b"bad event\n\n",self.event().replace(b"SEQNUM=100",b"SEQNUM=oops"),self.event().replace(b"SUBSYSTEM=block",b"SUBSYSTEM=net")):
            _,p=self.parser()
            with self.assertRaises(ValueError):p.feed("stdout",raw,10)
        _,p=self.parser();p.feed("stdout",self.event()[:-1],1)
        with self.assertRaisesRegex(ValueError,"terminal fragment"):p.finish()
        _,p=self.parser()
        with self.assertRaises(ValueError):p.feed("stderr",b"Failed to receive message: No buffer space\n",1)
        fact,p=self.parser()
        with self.assertRaisesRegex(ValueError,"cap"):p.feed("stdout",b"x"*65536,1)
        self.assertEqual(fact["stdout_bytes"],65536);self.assertTrue(fact["truncated"]["stdout"]);self.assertEqual(fact["observed_at_least"]["stdout"],65537)
    def test_no_observer_or_child_operations_at_import_and_exact_passive_argv(self):
        self.assertEqual(life.MONITOR_ARGV,["/usr/bin/udevadm","--debug","monitor","--kernel","--udev","--property","--subsystem-match=block"])
        tree=ast.parse((HERE/"guest_setup_lifecycle.py").read_text())
        for node in tree.body:
            if isinstance(node,ast.Expr) and isinstance(node.value,ast.Call):self.fail("top-level runtime call")
        source=(HERE/"guest_setup_lifecycle.py").read_text()
        for forbidden in (".chmod(",".chown(","os.chmod(","os.chown(","child_qualifier(","read_ack(","ack_port(","udevadm settle","udevadm trigger"):
            self.assertNotIn(forbidden,source)
    def test_appearance_algorithm_exact_after_removing_only_drain_and_record_hooks(self):
        old=ast.parse((HERE/"guest_g0_setup.py").read_text());expected=next(x for x in old.body if isinstance(x,ast.FunctionDef) and x.name=="wait_partitions")
        tree=ast.parse((HERE/"guest_setup_lifecycle.py").read_text());actual=next(x for x in tree.body if isinstance(x,ast.FunctionDef) and x.name=="appearance")
        actual.name=expected.name;actual.args=copy.deepcopy(expected.args);removed=[]
        class Remove(ast.NodeTransformer):
            def visit_Expr(self,node):
                call=node.value
                if isinstance(call,ast.Call) and ((isinstance(call.func,ast.Attribute) and isinstance(call.func.value,ast.Name) and call.func.value.id=="observer" and call.func.attr=="drain") or (isinstance(call.func,ast.Name) and call.func.id=="record")):
                    removed.append(node);return None
                return self.generic_visit(node)
        actual=Remove().visit(actual);self.assertEqual(len(removed),2);self.assertEqual(ast.dump(actual),ast.dump(expected))
    def test_instrumented_original_functions_have_exact_read_order_and_predicates(self):
        original=ast.parse((HERE/"guest_g0_setup.py").read_text());current=ast.parse((HERE/"guest_setup_lifecycle.py").read_text())
        helpers={"held_dir","close_dir","sysfs_entry","recheck_sysfs_entry","read_attr_fd","sysfs_identity"}
        for name in helpers|{"nvme_preflight"}:
            expected=next(n for n in original.body if isinstance(n,ast.FunctionDef) and n.name==name)
            actual_names=("recorded_nvme_preflight","metadata_nvme") if name=="nvme_preflight" else ("record_"+name,)
            for actual_name in actual_names:
                actual=copy.deepcopy(next(n for n in current.body if isinstance(n,ast.FunctionDef) and n.name==actual_name));actual.name=expected.name;actual.args=copy.deepcopy(expected.args);flags=[]
                class Restore(ast.NodeTransformer):
                    def visit_Call(self,node):
                        if isinstance(node.func,ast.Name) and node.func.id in ("trace_stat","trace_bytes","trace_link"):
                            return self.visit(node.args[3])
                        node=self.generic_visit(node)
                        if isinstance(node.func,ast.Name) and node.func.id.startswith("record_") and node.func.id[7:] in helpers:
                            node.func.id=node.func.id[7:];node.keywords=[k for k in node.keywords if k.arg!="observations"]
                        return node
                    def visit_Attribute(self,node):
                        if actual_name=="metadata_nvme" and isinstance(node.value,ast.Name) and node.value.id=="os" and node.attr=="O_PATH":node.attr="O_RDONLY";flags.append(node)
                        return self.generic_visit(node)
                actual=Restore().visit(actual);self.assertEqual(len(flags),2 if actual_name=="metadata_nvme" else 0)
                self.assertEqual(ast.dump(actual),ast.dump(expected),actual_name)

    def test_snapshot_first_full_identity_change_stops_without_resetting_baseline(self):
        doc=self.doc();baseline=fixtures.nvme();namespace=fixtures.qualifier()["partitions"][0]["mount_namespace"];changed=copy.deepcopy(baseline);changed["partitions"][0]["node_identity"][3]=99
        observer=mock.Mock()
        absent={"status":"absent","path":"/fixed","before":None,"opened":None,"after":None,"raw_base64":"","error":life.error(FileNotFoundError(2,"absent"))}
        with mock.patch.object(guest.setup,"mount_namespace",return_value=namespace),mock.patch.object(guest,"metadata_nvme",return_value=changed),mock.patch.object(guest,"capture_file",return_value=absent):
            with self.assertRaises(guest.Transition):guest.snapshot(doc,"format-p1-after",baseline,namespace,"serial",observer)
        self.assertEqual(doc["snapshots"][0]["original_facts"]["nvme"],baseline);self.assertEqual(doc["snapshots"][0]["current"]["nvme"],changed)
        self.assertEqual(doc["snapshots"][0]["diff"],[{"path":"/nvme/partitions/0/node_identity/3","kind":"value_changed"}])
    def test_changed_rdev_never_follows_new_database_name(self):
        doc=self.doc();baseline=fixtures.nvme();namespace=fixtures.qualifier()["partitions"][0]["mount_namespace"];changed=copy.deepcopy(baseline);changed["partitions"][0]["dev"]=[999,999]
        absent={"status":"absent","path":"/fixed","before":None,"opened":None,"after":None,"raw_base64":"","error":None}
        with mock.patch.object(guest.setup,"mount_namespace",return_value=namespace),mock.patch.object(guest,"metadata_nvme",return_value=changed),mock.patch.object(guest,"capture_file",return_value=absent) as read:
            with self.assertRaises(guest.Transition):guest.snapshot(doc,"format-p1-after",baseline,namespace,"serial",mock.Mock())
        self.assertFalse(any("999" in str(args[0]) for args,_ in read.call_args_list));self.assertEqual(doc["snapshots"][0]["database"][1]["status"],"not_collected")
    def test_early_original_records_have_no_extra_reads_or_inferred_initialization(self):
        doc=self.doc();facts={"number":1,"dev":[259,1]}
        with mock.patch.object(guest,"capture_file",side_effect=AssertionError("no added read")),mock.patch.object(guest,"metadata_nvme",side_effect=AssertionError("no added read")):
            guest.original_record(doc,"appearance-p1",facts)
        self.assertIs(doc["snapshots"][0]["original_facts"],facts);self.assertEqual(doc["snapshots"][0]["native"],{"status":"not_collected"});self.assertEqual(doc["snapshots"][0]["initstate"],[])
    def test_owned_acquisition_failure_kills_only_unreaped_direct_child_and_reaps(self):
        streams=[mock.Mock(closed=False) for _ in range(3)]
        for stream in streams:stream.close.side_effect=lambda stream=stream:setattr(stream,"closed",True)
        proc=mock.Mock(pid=12,stdin=streams[0],stdout=streams[1],stderr=streams[2],returncode=-9);proc.poll.return_value=-9
        with mock.patch.object(guest.subprocess,"Popen",return_value=proc),mock.patch.object(guest.os,"pidfd_open",side_effect=OSError("pidfd failure")):
            with self.assertRaisesRegex(OSError,"pidfd failure"):guest.Owned([life.UDEV,"--version"])
        proc.send_signal.assert_not_called();proc.wait.assert_called_once_with(timeout=2)
        for stream in streams:stream.close.assert_called_once()
    def test_owned_cleanup_never_reaps_twice_when_already_reaped(self):
        child=guest.Owned.__new__(guest.Owned);child.proc=mock.Mock(returncode=0);child.proc.poll.return_value=0;child.reaped=True;child.pidfd=None;child.fd_cleanup_uncertain=False
        for stream in (child.proc.stdin,child.proc.stdout,child.proc.stderr):stream.closed=True
        child.close();child.proc.wait.assert_not_called()
    def test_failed_observer_readiness_prevents_mutation_in_main(self):
        self.run_main_case(observer_failure=True)
    def test_production_main_transition_stops_all_later_formats_and_cleans_safe_resources(self):
        doc,calls=self.run_main_case(transition="format-p1-after")
        self.assertEqual([x[0] for x in calls],["/usr/sbin/sfdisk","/usr/sbin/sfdisk","/usr/sbin/mkfs.ext4"])
        self.assertEqual(doc["stop"]["status"],"transition_observed");self.assertNotIn("mount-p1",[x["phase"] for x in doc["markers"]])
    def run_main_case(self,observer_failure=False,transition=None,real_cleanup=False,postsave_failure=False):
        config={"nonce":self.binding["nonce"],"nvme_serial":"DMG0"+self.binding["nonce"][:16],"mounts":["/mnt/dm-g0/p1","/mnt/dm-g0/p2"],"deadlines":{"sfdisk":20,"mkfs_ext4":60,"mount":15,"umount":15,"dpkg_query":10}}
        baseline=fixtures.nvme();namespace=fixtures.qualifier()["partitions"][0]["mount_namespace"];commands=[];documents=[];active={};directories={};post_error=RuntimeError("first post-mount snapshot");post_failed=[False]
        records=fixtures.result()["mounts"]
        for record in records:record.pop("mounted_root_identity")
        class FakePath:
            def __init__(self,value):self.value=str(value)
            def __str__(self):return self.value
            def __fspath__(self):return self.value
            def exists(self):return self.value in directories
            def is_symlink(self):return False
            def mkdir(self,mode):
                if self.exists():raise FileExistsError(self.value)
                directories[self.value]=len(directories)+10
        def path(value):return FakePath(value) if str(value).startswith("/mnt/dm-g0") else Path(value)
        def lstat(value):return SimpleNamespace(st_dev=1,st_ino=directories[str(value)],st_mode=stat.S_IFDIR|0o755,st_uid=0,st_gid=0)
        def rmdir(value):
            if str(value) in active:raise OSError("mounted")
            directories.pop(str(value))
        def stable(path,*a,**k):return (life.canonical(life.mode_config(config["nonce"])) if "setup-lifecycle-config" in str(path) else life.canonical(config)),{}
        def command(doc,argv,**kwargs):
            commands.append(argv)
            if argv[0]=="/usr/bin/mount":active[argv[-1]]=records[config["mounts"].index(argv[-1])]
            if argv[0]=="/usr/bin/umount":active.pop(argv[-1])
            return {"stdout_text":json.dumps({"partitiontable":fixtures.result()["partition_table"]}) if "--json" in argv else ""}
        def view():
            if postsave_failure and active and not post_failed[0]:post_failed[0]=True;raise post_error
            return {"records":list(active.values())}
        def observe(doc,path):
            if observer_failure:raise RuntimeError("observer readiness")
            result=mock.Mock(failure=None);doc["observer"].update(ready=True,loss_status="loss_not_detected_not_proved_lossless");return result
        real_snapshot=guest.snapshot
        def snap(doc,phase,b,n,serial,observer):
            current=copy.deepcopy(b)
            if phase==transition:current["partitions"][0]["node_identity"][1]+=1
            absent={"status":"absent","path":"/fixed","before":None,"opened":None,"after":None,"raw_base64":"","error":None}
            with mock.patch.object(guest,"metadata_nvme",return_value=current),mock.patch.object(guest,"capture_file",return_value=absent):return real_snapshot(doc,phase,b,n,serial,observer)
        patchers=[mock.patch.object(guest.os,"getuid",return_value=0),mock.patch.object(guest.os,"getgid",return_value=0),mock.patch.object(guest,"verify_seed",return_value=({},self.binding["manifest_sha256"])),
              mock.patch.object(guest.setup,"stable_file",side_effect=stable),mock.patch.object(guest.g0,"validate_config",side_effect=lambda x:x),mock.patch.object(guest.setup,"dmi_binding",return_value=(self.binding["binding"],{})),
              mock.patch.object(guest,"tool_facts",return_value=[]),mock.patch.object(guest,"observer_preflight"),mock.patch.object(guest.setup,"nvme_preflight",return_value=baseline),mock.patch.object(guest,"recorded_nvme_preflight",return_value=baseline),
              mock.patch.object(guest.setup,"mount_namespace",return_value=namespace),mock.patch.object(guest.setup,"mountinfo",side_effect=view),mock.patch.object(guest.setup,"reject_selected_nvme_mount"),
              mock.patch.object(guest,"Observer",side_effect=observe),mock.patch.object(guest,"run_tool",side_effect=command),mock.patch.object(guest,"appearance",side_effect=lambda name,deadline,obs,record:[record({"number":i}) for i in (1,2)]),
              mock.patch.object(guest,"capture_file",return_value={"status":"absent","path":"/fixed","before":None,"opened":None,"after":None,"raw_base64":"","error":None}),mock.patch.object(guest,"snapshot",side_effect=snap),mock.patch.object(guest,"emit",side_effect=lambda doc:documents.append(copy.deepcopy(doc))),
              mock.patch.object(guest,"Path",side_effect=path),mock.patch.object(guest.os,"lstat",side_effect=lstat),mock.patch.object(guest.os,"rmdir",side_effect=rmdir)]
        with contextlib.ExitStack() as stack:
            [stack.enter_context(patcher) for patcher in patchers]
            cleanup=None if real_cleanup else stack.enter_context(mock.patch.object(guest,"cleanup_mounts"))
            if observer_failure or transition or postsave_failure:
                with self.assertRaisesRegex(RuntimeError,"observer readiness" if observer_failure else "first post-mount snapshot" if postsave_failure else "identity changed") as observed:guest.main()
                if postsave_failure:self.assertIs(observed.exception,post_error)
            else:guest.main()
            if cleanup is not None:cleanup.assert_called_once()
        if observer_failure:self.assertEqual(commands,[]);self.assertFalse(documents[0]["stop"]["mutation_started"])
        if real_cleanup:self.assertFalse(active);self.assertFalse(directories)
        return documents[0],commands
    def test_reached_mounts_use_real_guarded_reverse_cleanup(self):
        doc,calls=self.run_main_case(real_cleanup=True)
        self.assertEqual([x[-1] for x in calls if x[0]=="/usr/bin/umount"],["/mnt/dm-g0/p2","/mnt/dm-g0/p1"]);self.assertFalse(doc["cleanup"]["errors"])
    def test_post_success_mount_capture_failure_is_primary_and_owned_effect_is_cleaned(self):
        doc,calls=self.run_main_case(real_cleanup=True,postsave_failure=True)
        self.assertEqual([x[-1] for x in calls if x[0]=="/usr/bin/umount"],["/mnt/dm-g0/p1"]);self.assertFalse(doc["cleanup"]["errors"]);self.assertEqual(doc["stop"]["primary_error"]["message"],"first post-mount snapshot")
    def test_foreign_or_unknown_stderr_is_counted_not_retained_and_is_incomplete(self):
        for raw in (b"foreign /devices/not-selected/block/vda details\n",b"unclassified foreign payload\n",b"\xff\n"):
            fact,parser=self.parser();before=copy.deepcopy(fact["diagnostics"])
            with self.assertRaises(ValueError):parser.feed("stderr",raw,20)
            self.assertEqual(fact["diagnostics"],before);self.assertEqual(fact["discarded"]["stderr_sha256"],life.sha(raw));self.assertEqual(fact["loss_status"],"incomplete_or_unknown")
    def test_prefix_overflow_preserves_primary_and_never_becomes_complete(self):
        primary=life.error(RuntimeError("original transition"));diagnostic=life.error(ValueError("oversize evidence"));prefix=b"x"*(life.DOC_MAX+1)
        wires=life.prefix_frames(prefix,primary,diagnostic,**self.binding);doc,raw,terminal=life.parse(b"".join(wires),**self.binding)
        self.assertIsNone(doc);self.assertEqual(raw,prefix[:life.DOC_MAX]);self.assertEqual(terminal["primary_error"],primary);self.assertTrue(terminal["truncated"]);self.assertFalse(life.complete(doc))
    def test_host_prefix_sanitizer_uses_honest_terminal_and_unknown_counts(self):
        wires=life.prefix_frames(b"partial",life.error(RuntimeError("original")),life.error(ValueError("diagnostic")),**self.binding);saved={}
        def retain(path,raw,**kwargs):saved[Path(path).name]=raw
        with mock.patch.object(host,"exclusive",side_effect=retain):self.assertFalse(host.retain_setup_observation(Path("/evidence"),b"".join(wires),**self.binding))
        receipt=json.loads(saved["setup-lifecycle-receipt.json"]);sanitized=json.loads(saved["setup-lifecycle.sanitized.json"])
        self.assertFalse(receipt["raw_is_complete_canonical_json"]);self.assertEqual(sanitized["status"],"incomplete");self.assertIsNone(sanitized["snapshot_count"]);self.assertEqual(saved["setup-lifecycle.raw.json"],b"partial")
    def test_snapshot_cap_keeps_selected_original_transition_primary(self):
        doc=self.doc();baseline=fixtures.nvme();current=copy.deepcopy(baseline);current["partitions"][0]["node_identity"][1]+=1;namespace=fixtures.qualifier()["partitions"][0]["mount_namespace"]
        original_canonical=guest.life.canonical
        def cap(value):return b"x"*(life.SNAPSHOT_MAX+1) if isinstance(value,dict) and value.get("phase")=="format-p1-after" and value.get("current") is not None else original_canonical(value)
        absent={"status":"absent","path":"/fixed","before":None,"opened":None,"after":None,"raw_base64":"","error":None}
        with mock.patch.object(guest.setup,"mount_namespace",return_value=namespace),mock.patch.object(guest,"metadata_nvme",return_value=current),mock.patch.object(guest,"capture_file",return_value=absent),mock.patch.object(guest.life,"canonical",side_effect=cap):
            with self.assertRaises(guest.Transition):guest.snapshot(doc,"format-p1-after",baseline,namespace,"serial",mock.Mock())
        self.assertIsNotNone(doc["snapshots"][0]["diagnostic_error"]);self.assertIsNone(doc["snapshots"][0]["current"])
    def test_acquisition_wait_and_close_uncertainty_cannot_report_clean(self):
        streams=[mock.Mock(closed=False) for _ in range(3)]
        streams[0].close.side_effect=OSError("close uncertain")
        for stream in streams[1:]:stream.close.side_effect=lambda stream=stream:setattr(stream,"closed",True)
        proc=mock.Mock(pid=12,stdin=streams[0],stdout=streams[1],stderr=streams[2],returncode=1);proc.poll.return_value=1;proc.wait.side_effect=TimeoutError("reap uncertain");original=OSError("pidfd unavailable")
        with mock.patch.object(guest.subprocess,"Popen",return_value=proc),mock.patch.object(guest.os,"pidfd_open",side_effect=original):
            with self.assertRaises(OSError) as observed:guest.Owned([life.UDEV,"--version"])
        self.assertIs(observed.exception,original);self.assertFalse(original._owned_cleanup["reaped"]);self.assertFalse(original._owned_cleanup["fds_closed"])
        for stream in streams:stream.close.assert_called_once()
    def io_fakes(self,stdout=b"",stderr=b"",observer_queues=None):
        class Stream:
            def __init__(self,fd):self.fd=fd;self.closed=False
            def fileno(self):return self.fd
            def close(self):self.closed=True
        streams=[Stream(n) for n in (10,11,12)];queues={11:[stdout,b""],12:[stderr,b""]} if observer_queues is None else {11:list(observer_queues[0]),12:list(observer_queues[1])}
        class Child:
            def __init__(self,argv):
                self.proc=SimpleNamespace(pid=999,stdin=streams[0],stdout=streams[1],stderr=streams[2],returncode=None);self.proc.poll=lambda:self.proc.returncode;self.proc.wait=lambda **kwargs:setattr(self.proc,"returncode",0);self.start=1;self.eof=set();self.reaped=False;self.fds_closed=False
            def same(self):return True
            def close(self,drain=None):
                self.proc.returncode=0;self.reaped=True;self.fds_closed=True;self.eof={"stdout","stderr"}
                for stream in streams:stream.close()
            def report(self):return {"acquired":True,"reaped":self.reaped,"fds_closed":self.fds_closed}
        class Selector:
            def __init__(self):self.mapping={}
            def register(self,stream,event,data):self.mapping[stream]=SimpleNamespace(fileobj=stream,data=data)
            def unregister(self,stream):self.mapping.pop(stream)
            def get_map(self):return self.mapping
            def select(self,timeout=0):return [(key,1) for stream,key in list(self.mapping.items()) if key.data=="stdin" or queues.get(stream.fd)]
            def close(self):pass
        def read(fd,count):return queues[fd].pop(0)
        return Child,Selector,read
    def test_partial_stdin_io_and_nonfatal_observer_error_leave_guarded_tool_running(self):
        child,selector,read=self.io_fakes(stdout=b"result\n");doc=self.doc();writes=[];observer=mock.Mock();observer.drain.side_effect=RuntimeError("observer capture failed")
        def write(fd,raw):writes.append(bytes(raw[:1]));return 1
        with mock.patch.object(guest,"Owned",child),mock.patch.object(guest.selectors,"DefaultSelector",selector),mock.patch.object(guest.os,"read",side_effect=read),mock.patch.object(guest.os,"write",side_effect=write),mock.patch.object(guest.setup,"direct_children",return_value=[]):
            result=guest.run_tool(doc,["/usr/bin/umount","--","/mnt/dm-g0/p1"],stdin=b"abc",timeout=15,observer=observer,observer_fatal=False)
        self.assertEqual(b"".join(writes),b"abc");self.assertEqual(result["stdout_text"],"result\n");guest.g0._validate_tool_result(result)
        self.assertIsNotNone(doc["stop"]["diagnostic_error"]);self.assertTrue(doc["commands"][0]["reaped"]);self.assertTrue(doc["commands"][0]["fds_closed"])
    def test_ready_banner_cannot_bypass_pending_or_partial_startup_stderr(self):
        for stderr in ([b"Calling monitor\n",b"unclassified startup failure\n"],[b"Calling monitor\n",b"partial"]):
            child,selector,read=self.io_fakes(observer_queues=([life.BANNER],stderr));doc=self.doc()
            with mock.patch.object(guest,"Owned",child),mock.patch.object(guest.selectors,"DefaultSelector",selector),mock.patch.object(guest.os,"read",side_effect=read),mock.patch.object(guest,"verify_observer_exec"):
                with self.assertRaises((RuntimeError,ValueError)):guest.Observer(doc,"/sys"+self.devpath)
            self.assertFalse(doc["stop"]["mutation_started"]);self.assertEqual(doc["observer"]["loss_status"],"incomplete_or_unknown")
    def test_minimal_closed_types_and_no_empty_preflight_green(self):
        self.assertFalse(life.complete(self.doc()))
        for change in (lambda d:d["cleanup"].update(fds_closed=1),lambda d:d["observer"]["truncated"].update(stderr=0),lambda d:d["observer"].update(identity={"pid":True,"start_ticks":1,"pidfd":True}),lambda d:d["snapshots"].append({"phase":"format-p1-after"})):
            doc=self.doc();change(doc)
            with self.assertRaises((ValueError,KeyError)):life.validate_document(doc,**self.binding)
    def test_guarded_cleanup_rejects_changed_mount_without_unmounting(self):
        doc=self.doc();part=fixtures.nvme()["partitions"][0];mount="/mnt/dm-g0/p1";saved=fixtures.result()["mounts"][0];view={"records":[{**saved,"source":"/dev/not-owned"}]};namespace=fixtures.qualifier()["partitions"][0]["mount_namespace"]
        with mock.patch.object(guest.setup,"mountinfo",return_value=view),mock.patch.object(guest.setup,"mount_namespace",return_value=namespace),mock.patch.object(guest,"run_tool") as tool:
            guest.cleanup_mounts(doc,[(part,mount)],{mount:[1,10]},{mount:saved},namespace,[],mock.Mock())
        tool.assert_not_called();self.assertTrue(doc["cleanup"]["errors"])
if __name__=="__main__":unittest.main()
