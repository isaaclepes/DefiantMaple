"""Pure mocked/source tests: never import or execute product/native/device code."""
import ast,base64,copy,hashlib,importlib.util,json,os,stat,struct,sys,unittest
from pathlib import Path,PurePosixPath
from types import SimpleNamespace
from unittest import mock
HERE=Path(__file__).resolve().parent

def load(name):
    spec=importlib.util.spec_from_file_location('e1_test_'+name,HERE/(name+'.py'));module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module
p=load('e1_policy');case=load('guest_e1_case');root=load('guest_e1_setup');host=load('host_e1_controller');finalize=load('finalize_e1')
class E1Tests(unittest.TestCase):
    nonce='a'*32;binding='b'*64;manifest='c'*64
    def fixture(self):
        old=load('test_g0_policy').G0PolicyTests();ready=old.ready();result=old.result()
        ready={k:v for k,v in ready.items() if k not in ('qualifier','qualifier_sha256','qualifier_bytes')};ready.update(schema='dm-e1-ready-v1',product_entries=p.product_entries(),mount_namespace=old.qualifier()['partitions'][0]['mount_namespace'],fixture_identities=[r['fixture_parent_identity'] for r in old.qualifier()['partitions']],mount_ids=[r['mount_id'] for r in result['mounts']])
        return old,ready,result
    def ident(self,dev=1,ino=10,size=0,mode=0o600):return [dev,ino,stat.S_IFREG|mode,12345,12345,1,size]
    def ledger(self,doc,ino=10):
        raw=p.canonical(doc)+b'\n';return {**case.blob(raw,self.ident(ino=ino,size=len(raw))),'version':{'identity':[1,ino],'sha256':p.sha256(raw)}}
    def records(self):
        old,ready,_=self.fixture();dev1,dev2=[x[0] for x in ready['fixture_identities']];identity=old.qualifier()['ordinary_identity']['before'];fds=old.qualifier()['fd_inventories']['before']
        source={'identity':self.ident(dev=dev1,size=4096),'sha256':'1'*64,'schema':7,'library_id':'1'*8+'-'+'1'*4+'-'+'1'*4+'-'+'1'*4+'-'+'1'*12,'rows':{k:0 for k in ('assets','sources','source_entries','provenance')},'sidecars':[{'suffix':s,'absent':True} for s in ('-wal','-shm','-journal')]}
        executable={'path':'/usr/bin/python3.12','identity':[1,2,stat.S_IFREG|0o755,0,0,1,3],'bytes':3,'sha256':p.sha256(b'elf')}
        native=[{'name':name,**{**executable,'path':'/usr/lib/python3.12/'+name+'.so'}} for name in ('_sqlite3','_ctypes')]
        pre={'source_pins':p.product_entries(),'loaded_product':sorted(e['path'] for e in p.PRODUCT_ENTRIES),'interpreter':executable,'native':native,'sqlite_version':'3.45.1','stdlib_origins':{'checked':True,'count':50,'sha256':'9'*64},'ordinary':identity,'fd_before':fds,'source_before':source,'fixtures':ready['fixture_identities']}
        operation='2'*8+'-'+'2'*4+'-'+'2'*4+'-'+'2'*4+'-'+'2'*12;loc={'schedule_id':'3'*36,'binding':{'catalog_path':'/mnt/dm-g0/p1/fixture/case/catalog/empty.sqlite3','directory_path':'/mnt/dm-g0/p2/fixture/case/managed'}}
        initial={'schema':'defiantmaple.schedule-state.v1','audit':[],'packages':[],'last_success':None,'next_sequence':1,'status':{'outcome':'idle'},'locator':loc}
        started=copy.deepcopy(initial);started.update(next_sequence=2,status={'outcome':'in_progress'},audit=[{'event':'attempt_started','operation_id':operation}])
        manifest={'snapshot_bytes':4096,'catalog_schema':7,'library_id':source['library_id']};manifest_raw=p.canonical(manifest);header=struct.pack('>8sIQ',b'DMETA1\0\0',len(manifest_raw),4096)
        stage={'fd':5,'identity':self.ident(dev=dev2,ino=30),'flags':os.O_WRONLY,'mnt_id':ready['mount_ids'][1],'path':'/mnt/dm-g0/p2/fixture/case/managed/.recovery-'+('4'*32)+'.package','buffer_bytes':20,'buffer_sha256':p.sha256(header),'builtin_write':True,'builtin_fsync':True}
        arguments=[loc['binding']['catalog_path'],loc['binding']['directory_path']+'/snapshot-'+loc['schedule_id']+'-1-'+operation+'.dmbackup',stage['path'].replace('.package','.snapshot'),stage['path'],['/mnt/dm-g0/p1/fixture/case/cache']*4,120]
        gate={'kind':'gate','nonce':self.nonce,'pid':100,'start':200,'ppid':90,'operation':'backup','arguments_sha256':p.sha256(p.canonical(arguments)),'manifest_base64':base64.b64encode(manifest_raw).decode(),'snapshot_bytes':4096,'line':395,'source_sha256':p.RECOVERY_SHA,'stage':stage,'phase_deadline':30.0,'adapter_calls':1}
        filler={'written':1048576,'allocated':1048576,'identity':self.ident(dev=dev2,size=1048576),'space':{'bavail':0,'bfree':0,'favail':100,'frsize':4096},'errno':28,'final_flush_errno':None}
        start={'initial':self.ledger(initial),'started':self.ledger(started,11),'operation_id':operation,'worker':gate,'filler':filler,'ordering':['durable_attempt_started','original_stage_gate','pressure_established','resume_once']}
        exc={'kind':'fault','nonce':self.nonce,'line':395,'source_sha256':p.RECOVERY_SHA,'source_path':'/opt/dm-g0/source/defiantmaple/recovery.py','function_firstlineno':316,'source_line_base64':p.RECOVERY_LINES[395],'module':'builtins','class':'OSError','errno':28,'strerror':'No space left on device','sqlite_errorcode':None,'sqlite_errorname':None,'stage':copy.deepcopy(stage),'adapter_calls':1}
        done={'kind':'done','nonce':self.nonce,'gate':True,'fault':True,'trace_error':None,'adapter_calls':1}
        fault={'observed':True,'exception':exc,'worker_done':done,'kernel_trace_observed':False}
        final=copy.deepcopy(started);final['status']={'outcome':'failed'};final['audit'].append({'event':'failed','operation_id':operation})
        finish={'outcome':'PASS','product_operation_success':False,'operation':{'status':'failed','success_currently_verified':False,'cleanup_pending':False,'error':'OSError: no space'},'final_ledger':self.ledger(final,12),'source_after':copy.deepcopy(source),'source_unchanged':True,'published_packages':[],'remaining_stages':[],'worker_exits':[{'operation':'backup','pid':100,'status':0,'reaped':True,'cleanup_errors':[]}],'filler_removed':True,'thread_joined':True,'tracker':{'present':False,'reaped':True},'ordinary_after':identity,'fd_after':fds,'errors':[]}
        values=[{'schema':'dm-e1-case-v1','case':'original-package-stage-enospc','nonce':self.nonce,'binding':self.binding,'seed_manifest_sha256':self.manifest,'ordinal':i,'phase':phase,'data':value} for i,(phase,value) in enumerate(zip(p.CASE_PHASES,(pre,start,fault,finish)))]
        return values,ready,arguments,header
    def wire(self,values,ready=None):
        raw=b''.join(p.build_frame(p.CASE_PREFIX,v,p.CASE_CAPS[i]) for i,v in enumerate(values))
        if ready is not None:raw=p.build_frame(p.READY_PREFIX,ready,p.FRAME_MAX)+raw+p.build_frame(p.RESULT_PREFIX,{'placeholder':True},p.FRAME_MAX)
        return raw
    def parse(self,values,ready=None):return p.parse_case(self.wire(values,ready),nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest,ready=ready,require_pass=True)
    def test_expected_failure_pass_is_distinct_from_product_success(self):
        values,ready,_,_=self.records();self.assertEqual(len(self.parse(values,ready)),4);self.assertFalse(values[-1]['data']['product_operation_success'])
    def test_filler_failure_alone_SQLITE_FULL_and_wrong_original_line_cannot_pass(self):
        for mutate in (lambda v:v[2]['data'].update(observed=False,exception=None),lambda v:v[2]['data']['exception'].update(errno=13,sqlite_errorcode=13),lambda v:v[2]['data']['exception'].update(line=361),lambda v:v[2]['data']['exception'].update(errno=28.0)):
            values,ready,_,_=self.records();mutate(values)
            with self.assertRaises(ValueError):self.parse(values,ready)
    def test_durable_start_ledger_or_source_change_cannot_pass(self):
        for mutate in (lambda v:v[1]['data']['started'].update(sha256='0'*64),lambda v:v[3]['data'].update(source_unchanged=False),lambda v:v[3]['data']['source_after'].update(sha256='0'*64),lambda v:v[1]['data'].update(ordering=['pressure_established'])):
            values,ready,_,_=self.records();mutate(values)
            with self.assertRaises(ValueError):self.parse(values,ready)
    def test_original_failure_ledger_save_or_remaining_attempt_started_both_truthful(self):
        values,ready,_,_=self.records();self.parse(values,ready);values[3]['data']['final_ledger']=copy.deepcopy(values[1]['data']['started']);values[3]['data']['operation']['status']='uncertain';self.parse(values,ready)
    def test_unreaped_worker_or_forced_product_success_cannot_pass(self):
        for mutate in (lambda v:v[3]['data']['worker_exits'][0].update(reaped=False),lambda v:v[3]['data']['operation'].update(success_currently_verified=True),lambda v:v[3]['data'].update(product_operation_success=True),lambda v:v[3]['data'].update(filler_removed=False),lambda v:v[2]['data']['worker_done'].update(trace_error='broken observer')):
            values,ready,_,_=self.records();mutate(values)
            with self.assertRaises(ValueError):self.parse(values,ready)
    def test_exact_gate_arguments_header_mode_flags_and_selected_mount_before_fill(self):
        values,_,args,header=self.records();gate=values[1]['data']['worker'];case.verify_original_gate(gate,args,header,Path(gate['stage']['path']),gate['stage']['identity'][0],gate['stage']['mnt_id'])
        for mutate in (lambda x:x.update(arguments_sha256='0'*64),lambda x:x['stage'].update(buffer_sha256='0'*64),lambda x:x['stage'].update(flags=os.O_RDONLY),lambda x:x['stage']['identity'].__setitem__(2,stat.S_IFREG|0o640),lambda x:x['stage'].update(mnt_id=999),lambda x:x['stage'].update(builtin_write=False)):
            bad=copy.deepcopy(gate);mutate(bad)
            with self.assertRaises((RuntimeError,ValueError)):case.verify_original_gate(bad,args,header,Path(gate['stage']['path']),gate['stage']['identity'][0],gate['stage']['mnt_id'])
    def test_native_import_or_unknown_field_or_fragment_incomplete_never_pass(self):
        values,ready,_,_=self.records();values[0]['data']={'incomplete':'ModuleNotFoundError: _sqlite3'}
        raw=self.wire(values[:1]);self.assertEqual(len(p.parse_case(raw,nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest)),1)
        with self.assertRaises(ValueError):p.parse_case(raw,nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest,require_pass=True)
        values,ready,_,_=self.records();values[2]['data']['extra']=1
        with self.assertRaises(ValueError):self.parse(values,ready)
        values,ready,_,_=self.records()
        with self.assertRaises(ValueError):p.parse_case(self.wire(values)+b'DME1CA',nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest,require_pass=True)
    def test_fixed_four_caps_and_existing_global_caps(self):
        self.assertEqual(p.CASE_CAPS,(8192,16384,8192,32768));self.assertEqual(p.CASE_MAX,65536);self.assertEqual(4192264-93020+65536,4164780)
        self.assertEqual((host.policy.SERIAL_MAX,host.policy.STREAM_MAX,host.policy.EVIDENCE_MAX),(4194304,1048576,8388608))
    def test_one_owned_filler_final_flush_after_actual_write_ENOSPC(self):
        pressure=case.Pressure(Path('/generated/filler'));st=SimpleNamespace(st_dev=1,st_ino=2,st_mode=stat.S_IFREG|0o600,st_uid=12345,st_gid=12345,st_nlink=1,st_size=0,st_blocks=8)
        with mock.patch.object(case.os,'open',side_effect=[10,11]),mock.patch.object(case.os,'fstat',return_value=st),mock.patch.object(case.os,'write',side_effect=OSError(28,'full')) as write,mock.patch.object(case.os,'fsync') as flush,mock.patch.object(case,'remaining',return_value=1),mock.patch.object(case,'statvfs_fact',return_value={'bavail':0,'bfree':0,'favail':1,'frsize':4096}):
            fact=pressure.fill(30);self.assertEqual(fact['errno'],28);write.assert_called_once();flush.assert_called_once_with(11)
    def test_filler_flush_failure_is_not_hidden_and_deadline_no_writes(self):
        pressure=case.Pressure(Path('/generated/filler'));st=SimpleNamespace(st_dev=1,st_ino=2,st_mode=stat.S_IFREG|0o600,st_uid=12345,st_gid=12345,st_nlink=1,st_size=0,st_blocks=8)
        with mock.patch.object(case.os,'open',side_effect=[10,11]),mock.patch.object(case.os,'fstat',return_value=st),mock.patch.object(case.os,'write',side_effect=OSError(28,'full')),mock.patch.object(case.os,'fsync',side_effect=OSError(28,'flush full')),mock.patch.object(case,'remaining',return_value=1),mock.patch.object(case,'statvfs_fact',return_value={'bavail':0,'bfree':0,'favail':1,'frsize':4096}):self.assertEqual(pressure.fill(30)['final_flush_errno'],28)
        with mock.patch.object(case.os,'open',side_effect=[10,11]),mock.patch.object(case.os,'fstat',return_value=st),mock.patch.object(case.os,'write') as write,mock.patch.object(case,'remaining',side_effect=TimeoutError()):
            with self.assertRaises(TimeoutError):pressure.fill(30)
            write.assert_not_called()
    def test_filler_cleanup_never_unlinks_replaced_inode(self):
        pressure=case.Pressure(Path('/generated/filler'));pressure.fd=11;pressure.parent=10;pressure.identity=self.ident()[:6]
        a=SimpleNamespace(st_dev=1,st_ino=10,st_mode=stat.S_IFREG|0o600,st_uid=12345,st_gid=12345,st_nlink=1,st_size=0)
        b=SimpleNamespace(**{**a.__dict__,'st_ino':99})
        with mock.patch.object(case.os,'fstat',return_value=a),mock.patch.object(case.os,'stat',return_value=b),mock.patch.object(case.os,'unlink') as unlink:
            with self.assertRaises(RuntimeError):pressure.remove()
            unlink.assert_not_called()
    def test_original_worker_adapter_exact_call_and_no_write_fsync_or_local_patching(self):
        tree=ast.parse((HERE/'guest_e1_case.py').read_text());worker=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='worker_entry')
        calls=[n for n in ast.walk(worker) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='original']
        self.assertEqual(len(calls),1);self.assertEqual([ast.dump(x) for x in calls[0].args],[ast.dump(ast.Name(id=x,ctx=ast.Load())) for x in ('operation','arguments','send','cancel')]);self.assertEqual(calls[0].keywords,[])
        for n in ast.walk(tree):
            if isinstance(n,(ast.Assign,ast.AugAssign,ast.AnnAssign)):
                targets=n.targets if isinstance(n,ast.Assign) else [n.target]
                self.assertFalse(any(isinstance(t,ast.Attribute) and (t.attr in ('f_locals','f_lineno') or (isinstance(t.value,ast.Name) and t.value.id=='os' and t.attr in ('write','fsync'))) for t in targets))
    def test_g0_and_fifteen_original_source_bytes_preserved(self):
        prior=HERE.parent/'enospc-direct-boot-source-proposal-v27'
        for name in ('guest_g0_setup.py','guest_g0_qualify.py','g0_policy.py','host_controller.py','finalize.py','guest_bootstrap.py','policy.py'):
            self.assertEqual((HERE/name).read_bytes(),(prior/name).read_bytes())
        for entry in p.PRODUCT_ENTRIES:
            data=(HERE/'product-source/defiantmaple'/Path(entry['path']).name).read_bytes();self.assertEqual((len(data),p.sha256(data)),(entry['bytes'],entry['sha256']))
    def test_new_root_route_contains_no_g0_probe_and_readiness_before_first_baseline(self):
        source=(HERE/'guest_e1_setup.py').read_text();tree=ast.parse(source);main=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='main')
        calls=[n for n in ast.walk(main) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name)]
        self.assertNotIn('child_qualifier',[n.func.id for n in calls]);self.assertEqual(sum(n.func.id=='child_e1' for n in calls),1)
        self.assertLess(next(n.lineno for n in calls if n.func.id=='wait_selected_initialization'),next(n.lineno for n in calls if n.func.id=='nvme_preflight' and n.keywords))
    def test_host_success_requires_four_case_records_and_normal_cleanup(self):
        source=(HERE/'host_e1_controller.py').read_text();self.assertIn('require_pass=True',source);self.assertIn("g0_result['case_result']!=e1_records[-1]['data']",source);self.assertIn('"g0_qualified": False',source)
        final=(HERE/'finalize_e1.py').read_text();self.assertIn('boot.get("e1_expected_failure_verified") is not True',final);self.assertIn('boot.get("product_operation_success") is not False',final)
    def test_child_clock_is_inherited_and_observer_send_never_blocks_fault_cleanup(self):
        source=(HERE/'guest_e1_case.py').read_text();self.assertNotIn('started_at+120',source);self.assertIn('min(time.monotonic()+30,deadline)',source)
        with mock.patch.object(case,'policy') as policy,mock.patch.object(case.struct,'pack',return_value=b'H'):
            policy.canonical.return_value=b'data';sock=mock.Mock();sock.send.return_value=1
            with self.assertRaises(RuntimeError):case.send_observation_now(sock,{})
            sock.setblocking.assert_called_once_with(False)
    def adapter_fixture(self,broken=False,original_error=None,close_error=None):
        original_path='/opt/dm-g0/source/defiantmaple/recovery.py';namespace={};calls=[];trace_slot=[];sent=[]
        exec(compile('\n'*315+'def backup():\n    pass\n',original_path,'exec'),namespace)
        backup=namespace['backup'];values,_,_,_=self.records();stage=values[1]['data']['worker']['stage'];arguments=(Path('/generated/catalog'),Path('/generated/package'),Path('/generated/snapshot'),Path('/generated/stage'),(),120);send=object();cancel=mock.Mock();returned=object()
        def invoke(*args):
            calls.append(args);trace=trace_slot[-1];frame=SimpleNamespace(f_code=backup.__code__,f_lineno=395,f_locals={'raw':b'{}','length':4096,'package_fd':5,'view':memoryview(b'X'*20)})
            trace(frame,'line',None);trace(frame,'exception',(OSError,OSError(28,'No space left on device'),None))
            if original_error is not None:raise original_error
            return returned
        namespace['invoke']=invoke
        exec(compile('\n'*483+'def original(operation,arguments,send,cancel):\n    return invoke(operation,arguments,send,cancel)\n',original_path,'exec'),namespace)
        recovery=SimpleNamespace(_worker_main=namespace['original'],_backup_worker=backup)
        def settrace(value):
            if value is not None:trace_slot.append(value)
        def message(sock,value,*args):
            if broken:raise RuntimeError('diagnostic failure')
            sent.append(value)
        raw=(HERE/'product-source/defiantmaple/recovery.py').read_bytes();sock=mock.Mock();sock.close.side_effect=close_error
        with mock.patch.object(case,'source_pins'),mock.patch.object(case,'bounded_file',return_value=(raw,[])),mock.patch.object(case.importlib,'import_module',return_value=recovery),mock.patch.object(case.socket,'socket',return_value=sock),mock.patch.object(case,'remaining',return_value=30),mock.patch.object(case.time,'monotonic',return_value=0),mock.patch.object(case,'proc_start',return_value=200),mock.patch.object(case.os,'getpid',return_value=100),mock.patch.object(case.os,'getppid',return_value=90),mock.patch.object(case,'descriptor_fact',return_value=stage),mock.patch.object(case,'send_message',side_effect=message),mock.patch.object(case,'send_observation_now',side_effect=lambda sock,value:sent.append(value)),mock.patch.object(case,'receive_message',return_value={'kind':'resume','nonce':self.nonce}),mock.patch.object(case.sys,'gettrace',return_value=None),mock.patch.object(case.sys,'settrace',side_effect=settrace),mock.patch.object(case.sys,'path',[]),mock.patch.dict(case.os.environ,{'DM_E1_CASE_DEADLINE':'120','DM_E1_NONCE':self.nonce,'DM_E1_SOCKET':'/generated/socket'}):
            if original_error is not None:
                with self.assertRaises(type(original_error)) as observed:case.worker_entry('backup',arguments,send,cancel)
                self.assertIs(observed.exception,original_error);self.assertIn('E1 adapter cleanup',str(observed.exception.__notes__))
            elif close_error is not None:
                with self.assertRaisesRegex(RuntimeError,'adapter cleanup INCONCLUSIVE'):case.worker_entry('backup',arguments,send,cancel)
            else:self.assertIs(case.worker_entry('backup',arguments,send,cancel),returned)
        self.assertEqual(len(calls),1);self.assertEqual(calls[0],('backup',arguments,send,cancel));self.assertIs(calls[0][1],arguments);self.assertIs(calls[0][2],send);self.assertIs(calls[0][3],cancel)
        return sent,cancel
    def test_actual_adapter_calls_original_once_and_captures_errno_before_stringification(self):
        sent,cancel=self.adapter_fixture();fault=next(v for v in sent if v['kind']=='fault');self.assertEqual(fault['errno'],28);self.assertEqual(fault['line'],395);self.assertEqual(fault['source_line_base64'],p.RECOVERY_LINES[395]);self.assertIsNone(sent[-1]['trace_error']);cancel.set.assert_not_called()
    def test_trace_diagnostic_error_does_not_raise_synthetic_error_in_original(self):
        sent,cancel=self.adapter_fixture(broken=True);self.assertIn('diagnostic failure',sent[-1]['trace_error']);self.assertTrue(cancel.set.called)
    def test_failure_receipt_preserves_observed_true_and_unknown_product_outcome(self):
        for observed in (True,None):
            args=SimpleNamespace(root=Path('/virtual'),status='failure',reason='case failed',source_hashes=None,apt_plan=None);writes=[]
            def exists(path):return path.name=='boot-result.json'
            with mock.patch.object(finalize.argparse.ArgumentParser,'parse_args',return_value=args),mock.patch.object(Path,'mkdir'),mock.patch.object(Path,'exists',exists),mock.patch.object(Path,'read_bytes',return_value=json.dumps({'product_operation_success':observed}).encode()),mock.patch.object(finalize,'exclusive',side_effect=lambda path,value:writes.append((path,value))):finalize.main()
            receipt=next(value for path,value in writes if path.name=='receipt.json');self.assertIs(receipt['product_operation_success'],observed);self.assertFalse(receipt['success'])
    def test_wrong_argument_receipt_cannot_pass_even_with_real_errno28(self):
        values,ready,_,_=self.records();values[1]['data']['worker']['arguments_sha256']='0'*64
        with self.assertRaises(ValueError):self.parse(values,ready)

    def test_actual_seed_injects_all_fifteen_pins_and_only_executes_e1_route(self):
        writes={}
        with mock.patch.object(Path,'mkdir'),mock.patch.object(Path,'stat',return_value=SimpleNamespace(st_size=3)),mock.patch.object(Path,'chmod'),mock.patch.object(host,'exclusive',side_effect=lambda path,data,**kwargs:writes.update({path.name:data})),mock.patch.object(host,'command') as command:
            _,seed=host.make_seed(Path('/virtual'),self.nonce,b'boot',p.sha256(b'boot'))
        self.assertEqual(len(seed['manifest']['entries']),24);self.assertEqual(sum(item['path'].startswith('/opt/dm-g0/source/') for item in seed['manifest']['entries']),15)
        self.assertIn(b'guest_e1_setup.py ]',writes['user-data']);self.assertNotIn(b'guest_g0_setup.py ]',writes['user-data']);command.assert_called_once()
    def capture_root_child(self,failed=False):
        values,ready,_,_=self.records();raw=self.wire(values);first=p.build_frame(p.CASE_PREFIX,values[0],p.CASE_CAPS[0]);error=OSError(5,'original pipe read');captured=[];events=[]
        blocks=iter([first,raw[len(first):],b''])
        def read(fd,n):
            if failed:raise error
            return next(blocks)
        config={'nonce':self.nonce,'mounts':['/mnt/dm-g0/p1','/mnt/dm-g0/p2'],'deadlines':{'ordinary_child':120}}
        with mock.patch.object(root.os,'pipe2',return_value=(10,11)),mock.patch.object(root.os,'fork',return_value=123),mock.patch.object(root.os,'close',side_effect=lambda fd:events.append(('close',fd))),mock.patch.object(root.os,'set_blocking'),mock.patch.object(root.os,'pidfd_open',return_value=44),mock.patch.object(root,'proc_start',return_value=20),mock.patch.object(root,'direct_children',return_value=[]),mock.patch.object(root.os,'read',side_effect=read),mock.patch.object(root.os,'waitpid',side_effect=[(0,0),(123,0)]) as wait,mock.patch.object(root.select,'select',return_value=([],[],[])),mock.patch.object(root,'stop_and_reap_qualifier',side_effect=lambda *a:events.append(('cleanup',123)) or 0),mock.patch.object(root,'serial_case_capture',side_effect=lambda data:captured.append(data)):
            if failed:
                with self.assertRaises(OSError) as actual:root.child_e1(config,self.manifest,self.binding,[],ready['mount_ids'])
                self.assertIs(actual.exception,error);self.assertIn(('cleanup',123),events)
            else:
                records,observed=root.child_e1(config,self.manifest,self.binding,[],ready['mount_ids']);self.assertEqual(observed,raw);self.assertEqual(records,values);self.assertEqual(wait.call_count,2)
        self.assertEqual(captured,[b'' if failed else raw]);self.assertIn(('close',44),events);self.assertIn(('close',10),events)
    def test_production_root_capture_drains_partial_io_reaps_and_forwards_exact_four_records(self):self.capture_root_child()
    def test_production_root_capture_preserves_primary_pipe_error_and_closes_owned_fds(self):self.capture_root_child(failed=True)
    def test_all_original_root_guard_helper_ASTs_preserved_and_case_records_do_no_blocking_io(self):
        original=ast.parse((HERE/'guest_g0_setup.py').read_text());new=ast.parse((HERE/'guest_e1_setup.py').read_text())
        functions={n.name:n for n in new.body if isinstance(n,ast.FunctionDef)}
        for node in original.body:
            if isinstance(node,ast.FunctionDef) and node.name not in ('main','child_qualifier'):
                self.assertEqual(ast.dump(node),ast.dump(functions[node.name]),node.name)
        case_tree=ast.parse((HERE/'guest_e1_case.py').read_text());run=next(n for n in case_tree.body if isinstance(n,ast.FunctionDef) and n.name=='run_case');record=next(n for n in run.body if isinstance(n,ast.FunctionDef) and n.name=='record')
        forbidden={'open','write','fsync','send','sendall','select','wait','join'}
        self.assertFalse(any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr in forbidden for n in ast.walk(record)))

    def test_partial_filler_acquisition_closes_parent_and_preserves_original_error(self):
        pressure=case.Pressure(Path('/generated/filler'));primary=OSError(13,'open refused')
        with mock.patch.object(case.os,'open',side_effect=[10,primary]),mock.patch.object(case.os,'close') as close:
            with self.assertRaises(OSError) as actual:pressure.fill(30)
            self.assertIs(actual.exception,primary);close.assert_called_once_with(10);self.assertIsNone(pressure.parent)
    def test_socket_cleanup_rejects_replacement_and_closes_parent(self):
        expected=[1,2,stat.S_IFSOCK|0o700,12345,12345,1,0];replacement=SimpleNamespace(st_dev=1,st_ino=99,st_mode=expected[2],st_uid=12345,st_gid=12345,st_nlink=1,st_size=0)
        with mock.patch.object(case.os,'open',return_value=10),mock.patch.object(case.os,'stat',return_value=replacement),mock.patch.object(case.os,'unlink') as unlink,mock.patch.object(case.os,'close') as close:
            with self.assertRaises(RuntimeError):case.unlink_owned_socket(Path('/generated/gate.sock'),expected)
            unlink.assert_not_called();close.assert_called_once_with(10)

    def test_adapter_close_error_never_replaces_original_and_normal_return_becomes_inconclusive(self):
        self.adapter_fixture(original_error=OSError(7,'original worker error'),close_error=OSError(5,'diagnostic close'))
        self.adapter_fixture(close_error=OSError(5,'diagnostic close'))

    def test_production_host_ACK_bytes_parse_and_bind_in_production_guest_parser(self):
        value={'schema':'dm-e1-ack-v1','nonce':self.nonce,'binding':self.binding,'binding_transport':p.BINDING_TRANSPORT,'ready_sha256':'d'*64,'pre_mapping_sha256':'e'*64,'post_mapping_sha256':'f'*64}
        binding={'nonce':self.nonce,'binding':self.binding,'ready_digest':'d'*64,'pre_digest':'e'*64,'post_digest':'f'*64}
        exact=host.g0.build_ack(value)
        self.assertTrue(exact.startswith(b'DME1ACK1 '));self.assertEqual(root.g0.parse_ack(exact),value)
        root.g0.validate_ack(root.g0.parse_ack(exact),**binding)
        with self.assertRaisesRegex(ValueError,'ACK header'):root.g0.parse_ack(exact.replace(b'DME1ACK1 ',b'DMG0ACK1 ',1))
        for key in ('schema','binding_transport','nonce','binding','ready_sha256','pre_mapping_sha256','post_mapping_sha256'):
            wrong={**value,key:'0'*len(value[key])};parsed=root.g0.parse_ack(host.g0.build_ack(wrong))
            with self.assertRaisesRegex(ValueError,'ACK binding'):root.g0.validate_ack(parsed,**binding)

class CacheArgumentPath(PurePosixPath):
 mapping={};resolutions=[]
 def resolve(self,strict=False):
  self.resolutions.append(str(self));return CacheArgumentPath(self.mapping.get(str(self),str(self)))
def original_cache_definitions(path,names,ns):
 tree=ast.parse(path.read_text());body=[n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name in names];assert len(body)==len(names);exec(compile(ast.Module(body=body,type_ignores=[]),str(path),'exec'),ns)
class CacheArgumentHandoffTests(unittest.TestCase):
 def handoff(self,lexical,resolved):
  CacheArgumentPath.mapping={lexical:resolved};CacheArgumentPath.resolutions=[];product=HERE/'product-source/defiantmaple';calls=[];sentinel=object()
  def run(*args,**kwargs):calls.append((args,kwargs));return sentinel
  ns={'Path':CacheArgumentPath,'RecoveryError':RuntimeError,'uuid':SimpleNamespace(uuid4=lambda:SimpleNamespace(hex='4'*32)),'_outside_catalog_family':lambda *a:None,'_run':run}
  original_cache_definitions(product/'recovery.py',('_cache_roots','backup_metadata'),ns)
  tree=ast.parse((product/'snapshot_configuration.py').read_text());cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='SnapshotConfiguration');init=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name=='__init__')
  config_ns={'Path':CacheArgumentPath,'_cache_roots':ns['_cache_roots'],'locator_directory':lambda path:path,'_path':lambda path:path,'locator_leaf':lambda path:'fixed','time':SimpleNamespace(time=lambda:0)}
  exec(compile(ast.fix_missing_locations(ast.Module(body=[ast.ClassDef(name='OriginalConfiguration',bases=[],keywords=[],body=[init],decorator_list=[])],type_ignores=[])),str(product/'snapshot_configuration.py'),'exec'),config_ns)
  config=config_ns['OriginalConfiguration'](SimpleNamespace(path=CacheArgumentPath('/generated/catalog')),CacheArgumentPath('/generated/profile'),cache_roots=(CacheArgumentPath(lexical),))
  values,ready,expected,header=E1Tests().records();database,package=map(CacheArgumentPath,expected[:2])
  returned=ns['backup_metadata'](database,package,cache_roots=config.caches)
  self.assertIs(returned,sentinel);self.assertEqual(len(calls),1);self.assertEqual(calls[0][0][0],'backup')
  self.assertEqual(CacheArgumentPath.resolutions,[lexical,lexical,resolved]);CacheArgumentPath.resolutions=[]
  actual=calls[0][0][1];self.assertEqual(actual[4],tuple(map(CacheArgumentPath,(lexical,resolved,resolved,resolved))));self.assertEqual(actual[5],120);self.assertIs(type(actual[5]),int)
  tree=ast.parse((HERE/'guest_e1_case.py').read_text());worker=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='worker_entry')
  # Execute the exact production digest expression against the ORIGINAL captured _run arguments.
  expr=next(v for n in ast.walk(worker) if isinstance(n,ast.Dict) for k,v in zip(n.keys,n.values) if isinstance(k,ast.Constant) and k.value=='arguments_sha256')
  digest=eval(compile(ast.Expression(expr),str(HERE/'guest_e1_case.py'),'eval'),{'policy':p,'Path':CacheArgumentPath,'arguments':actual})
  with mock.patch.object(case,'Path',CacheArgumentPath):guest_caches=case.expected_backup_cache_roots(CacheArgumentPath(lexical))
  self.assertEqual(CacheArgumentPath.resolutions,[lexical,lexical,resolved]);self.assertEqual(guest_caches,[lexical,resolved,resolved,resolved]);self.assertEqual(p.expected_backup_cache_roots(lexical,resolved),guest_caches)
  run_case=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run_case')
  assignment=next(n for n in ast.walk(run_case) if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='expected_args' for t in n.targets))
  class CacheRoot:
   def __truediv__(self,name):
    assert name=='cache';return CacheArgumentPath(lexical)
  guest_ns={'database':database,'package':package,'snapshot':CacheArgumentPath(expected[2]),'stage_path':CacheArgumentPath(expected[3]),'root1':CacheRoot(),'expected_backup_cache_roots':case.expected_backup_cache_roots}
  with mock.patch.object(case,'Path',CacheArgumentPath):exec(compile(ast.Module(body=[assignment],type_ignores=[]),str(HERE/'guest_e1_case.py'),'exec'),guest_ns)
  expected=guest_ns['expected_args'];self.assertEqual(digest,p.sha256(p.canonical(expected)))
  gate=values[1]['data']['worker'];gate['arguments_sha256']=digest
  return values,ready,expected,header
 def guest_check(self,values,expected,header,manifest_raw=None,manifest=None,size=4096,device=None):
  gate=values[1]['data']['worker'];raw=base64.b64decode(gate['manifest_base64']) if manifest_raw is None else manifest_raw;doc=p.loads_strict(raw) if manifest is None else manifest
  expected_device=gate['stage']['identity'][0]
  case.verify_manifest_snapshot_binding(gate,expected,raw,doc,values[0]['data']['source_before'],SimpleNamespace(st_size=size,st_dev=expected_device if device is None else device),expected_device)
  case.verify_original_gate(gate,expected,header,Path(gate['stage']['path']),expected_device,gate['stage']['mnt_id'])
 def host_check(self,values,ready):
  fixture=E1Tests();return fixture.parse(values,ready)
 def test_full_original_handoff_canonical_through_guest_and_host(self):
  cache='/mnt/dm-g0/p1/fixture/case/cache';values,ready,args,header=self.handoff(cache,cache);self.guest_check(values,args,header);self.assertEqual(len(self.host_check(values,ready)),4)
 def test_full_original_handoff_lexical_and_resolved_not_deduplicated(self):
  values,ready,args,header=self.handoff('/generated/lexical-cache','/generated/resolved-cache');self.guest_check(values,args,header)
  # Actual host normalization + binding predicate; full host acceptance still requires its fixed canonical recipe.
  host_expected=[*args[:4],p.expected_backup_cache_roots('/generated/lexical-cache','/generated/resolved-cache'),120]
  location=p.ledger_fact(values[1]['data']['started'])['locator']
  p.verify_backup_arguments(values[1]['data']['worker'],host_expected,location)
  with self.assertRaisesRegex(ValueError,'argument binding'):self.host_check(values,ready)
  self.assertEqual(args[4],['/generated/lexical-cache','/generated/resolved-cache','/generated/resolved-cache','/generated/resolved-cache'])
 def test_each_compound_operand_rejects_independently(self):
  cache='/mnt/dm-g0/p1/fixture/case/cache';values,ready,args,header=self.handoff(cache,cache);gate=values[1]['data']['worker'];raw=base64.b64decode(gate['manifest_base64']);doc=p.loads_strict(raw)
  for change in ('digest','manifest_bytes','library','schema','snapshot_length','file_size','device'):
   v=copy.deepcopy(values);r=raw;d=copy.deepcopy(doc);size=4096;device=None
   if change=='digest':v[1]['data']['worker']['arguments_sha256']='0'*64
   elif change=='manifest_bytes':r=raw+b' '*4097
   elif change=='library':d['library_id']='0'*36
   elif change=='schema':d['catalog_schema']=8
   elif change=='snapshot_length':d['snapshot_bytes']=4097
   elif change=='file_size':size=4097
   elif change=='device':device=gate['stage']['identity'][0]+1
   with self.subTest(change=change),self.assertRaises(RuntimeError):self.guest_check(v,args,header,manifest_raw=r,manifest=d,size=size,device=device)
 def test_wrong_cache_and_timeout_representations_reject_in_both_bindings(self):
  cache='/mnt/dm-g0/p1/fixture/case/cache';values,ready,args,header=self.handoff(cache,cache)
  for cache_args,timeout in (([cache],120),([cache]*2,120),([cache]*4,120.0),([cache]*4,'120')):
   v=copy.deepcopy(values);wrong=[*args[:4],cache_args,timeout];v[1]['data']['worker']['arguments_sha256']=p.sha256(p.canonical(wrong))
   with self.assertRaises(RuntimeError):self.guest_check(v,args,header)
   with self.assertRaisesRegex(ValueError,'argument binding'):self.host_check(v,ready)
 def test_manifest_representation_header_binding_unchanged(self):
  cache='/mnt/dm-g0/p1/fixture/case/cache';values,_,args,header=self.handoff(cache,cache);gate=values[1]['data']['worker'];raw=base64.b64decode(gate['manifest_base64'])+b' '
  # Re-encoding the same semantic manifest changes original header length; the retained original header hash must reject it.
  changed_header=header[:8]+len(raw).to_bytes(4,'big')+header[12:]
  with self.assertRaisesRegex(RuntimeError,'exact original'):self.guest_check(values,args,changed_header,manifest_raw=raw)

if __name__=='__main__':unittest.main()
