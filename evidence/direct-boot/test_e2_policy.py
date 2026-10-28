"""Focused E2 production wire/binding and original-function mocks; no guest/native/worker I/O."""
import ast,base64,copy,importlib.util,os,stat,sys,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock
HERE=Path(__file__).resolve().parent

def load(name):
    spec=importlib.util.spec_from_file_location('e2_test_'+name,HERE/(name+'.py'));m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
p=load('e2_policy');case=load('guest_e2_case');old=load('test_e1_policy')

_STATE_TYPES=None
def original_state_types():
    # Exact immutable, non-I/O dataclasses/validators/codec, compiled from pins.
    global _STATE_TYPES
    if _STATE_TYPES is not None:return _STATE_TYPES
    import dataclasses,json,re,uuid
    ns={'__name__':__name__,'dataclass':dataclasses.dataclass,'asdict':dataclasses.asdict,'json':json,'re':re,'uuid':uuid,'os':os,'Path':Path}
    catalog=ast.parse((HERE/'product-source/defiantmaple/catalog.py').read_text())
    node=next(n for n in catalog.body if isinstance(n,ast.FunctionDef) and n.name=='validate_library_id')
    exec(compile(ast.Module(body=[node],type_ignores=[]),'/opt/dm-g0/source/defiantmaple/catalog.py','exec'),ns)
    source=ast.parse((HERE/'product-source/defiantmaple/scheduled_snapshots.py').read_text())
    names={'ScheduleError','StateUncertainError','_fields','_integer','_uuid','_path','_identity','Binding','Policy','Locator','ConfigurationTransition','PhaseStatus','PackageRecord','AuditRecord','ScheduleState','encode_document','decode_document','Version'}
    nodes=[n for n in source.body if isinstance(n,(ast.ClassDef,ast.FunctionDef)) and n.name in names]
    assert len(nodes)==len(names)
    exec(compile(ast.Module(body=nodes,type_ignores=[]),'/opt/dm-g0/source/defiantmaple/scheduled_snapshots.py','exec'),ns)
    _STATE_TYPES=ns;return ns

class E2Tests(unittest.TestCase):
    nonce='a'*32;binding='b'*64;manifest='c'*64
    def fixture(self,fallback=True):
        e1=old.E1Tests();_,ready,_=e1.fixture();values=e1.records()[0];pre=values[0]['data'];s=values[1]['data'];operation=s['operation_id'];dev=pre['fixtures'][1][0]
        import dataclasses
        model=original_state_types();operation='22222222-2222-4222-8222-222222222222';schedule='33333333-3333-4333-8333-333333333333';library='11111111-1111-4111-8111-111111111111';pre['source_before']['library_id']=library
        binding=model['Binding']('/mnt/dm-g0/p1/fixture/case/catalog/empty.sqlite3',(1,1),(1,2),library,p.MANAGED,(dev,3))
        locator=model['Locator'](schedule,1,binding);initial_obj=model['ScheduleState'](locator,model['Policy'](enabled=True,retention_enabled=False,keep_count=1))
        started_obj=dataclasses.replace(initial_obj,next_sequence=2,status=model['PhaseStatus'](10,None,'in_progress'),audit=(model['AuditRecord'](1,operation,1,10,'attempt_started'),))
        def ledger_object(document,ino):
            raw=model['encode_document'](document);identity=e1.ident(dev=dev,ino=ino,size=len(raw));return {**case.blob(raw,identity),'version':{'identity':identity[:2],'sha256':p.sha256(raw)}}
        first=ledger_object(initial_obj,100);second=ledger_object(started_obj,101);loc=p.ledger_fact(second)['locator'];leaf='snapshot-'+schedule+'-1-'+operation+'.dmbackup';path=p.MANAGED+'/'+leaf
        package={'path':path,'identity':e1.ident(dev=dev,ino=55,size=4200),'bytes':4200,'sha256':'5'*64,
            'manifest':{'kind':'metadata-only','package_version':2,'catalog_schema':7,'library_id':library,'snapshot_bytes':4096,'snapshot_sha256':'6'*64,'created_utc':'2026-01-01T00:00:00+00:00','omissions':[],'source_paths_unverified':True},'catalog':{'schema_version':7,'library_id':library}}
        point=model['PackageRecord'](schedule,1,operation,leaf,tuple(package['identity'][:2]),package['bytes'],package['sha256'],11)
        candidate_obj=dataclasses.replace(started_obj,packages=(point,),last_success=point,status=model['PhaseStatus'](11,11,'verified'),audit=(*started_obj.audit,model['AuditRecord'](2,operation,1,11,'verified',package=point)))
        raw=model['encode_document'](candidate_obj);rawblob=case.raw_blob(raw)
        stage={'fd':5,'identity':e1.ident(dev=dev,ino=60),'flags':os.O_WRONLY,'mnt_id':ready['mount_ids'][1],'path':p.MANAGED+'/.schedule-'+('4'*32)+'.stage','buffer_bytes':len(raw),'buffer_sha256':p.sha256(raw),'builtin_write':True,'builtin_fsync':True}
        gate={'line':489,'source_sha256':p.LEDGER_SHA,'source_path':'/opt/dm-g0/source/defiantmaple/scheduled_snapshots.py','function_firstlineno':472,'caller_lines':[137,318],'expected':second['version'],'current':second['version'],'stage':stage,'candidate_sha256':p.sha256(raw),'candidate_bytes':len(raw)}
        backup=s['worker'];backup_args=[loc['binding']['catalog_path'],path,p.MANAGED+'/.recovery-'+('7'*32)+'.snapshot',p.MANAGED+'/.recovery-'+('7'*32)+'.package',[ '/mnt/dm-g0/p1/fixture/case/cache']*4,120]
        start={'initial':first,'started':second,'operation_id':operation,'gate':gate,'package':package,'workers':[{'operation':'backup','arguments':backup_args},{'operation':'inspect','arguments':[path,p.MANAGED+'/.recovery-'+('8'*32)+'.inspect']}],'filler':s['filler'],'ordering':['durable_attempt_started','original_package_authenticated','completion_stage_gate','pressure_established','resume_once']}
        err=case.error(OSError(28,'No space left on device'))
        exc={'line':489,'source_sha256':p.LEDGER_SHA,'source_path':gate['source_path'],'function_firstlineno':472,'source_line_base64':p.LEDGER_LINES[489],'module':'builtins','class':'OSError','errno':28,'strerror':'No space left on device','error':err,'stage':copy.deepcopy(stage)}
        final_obj=started_obj
        if fallback:final_obj=dataclasses.replace(started_obj,status=dataclasses.replace(started_obj.status,outcome='uncertain'),audit=(*started_obj.audit,model['AuditRecord'](2,operation,1,12,'uncertain',error_code='publication_unregistered')))
        last=ledger_object(final_obj,102) if fallback else second
        saves=[{'role':'attempt_started','expected':first['version'],'returned':second['version'],'exception':None},{'role':'verified','expected':second['version'],'returned':None,'exception':err},{'role':'uncertain','expected':second['version'],'returned':last['version'] if fallback else None,'exception':None if fallback else err}]
        fault={'observed':True,'exception':exc,'saves':saves,'kernel_trace_observed':False}
        finish=copy.deepcopy(values[3]['data']);finish['source_after']=copy.deepcopy(pre['source_before']);finish.pop('published_packages');finish.update(operation={'status':'uncertain','success_currently_verified':False,'cleanup_pending':False,'error':'[Errno 28] No space left on device'},final_ledger=last,candidate=rawblob,package_after=copy.deepcopy(package),worker_exits=[{'operation':op,'pid':100+i,'status':0,'reaped':True,'cleanup_errors':[]} for i,op in enumerate(('backup','inspect'))])
        ready['schema']='dm-e2-ready-v1'
        return [pre,start,fault,finish],ready
    def wires(self,data):return b''.join(case.case_wire(i,d,self.nonce,self.binding,self.manifest) for i,d in enumerate(data))
    def parse(self,data):return p.parse_case(self.wires(data),nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest,require_pass=True)
    def test_production_producer_parser_both_fallback_outcomes(self):
        for fallback in (True,False):
            with self.subTest(fallback=fallback):
                data,ready=self.fixture(fallback);self.assertEqual(len(self.parse(data)),4)
                stream=p.build_frame(p.READY_PREFIX,{},65536)+self.wires(data)+p.build_frame(p.RESULT_PREFIX,{},65536)
                self.assertEqual(len(p.parse_case(stream,nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest,ready=ready,require_pass=True)),4)
                self.assertLessEqual(len(self.wires(data)),65536)
    def test_independent_binding_mutations(self):
        changes=[(1,'gate.line',488),(1,'gate.source_sha256','0'*64),(1,'gate.caller_lines',[137,306]),(1,'gate.expected.sha256','0'*64),(1,'gate.current.sha256','0'*64),(1,'gate.stage.buffer_sha256','0'*64),(1,'gate.stage.builtin_write',False),(1,'gate.stage.mnt_id',0),(1,'package.sha256','0'*64),(1,'package.identity.0',999),(1,'package.manifest.library_id','bad'),(1,'workers.0.arguments.5',120.0),(1,'workers.0.arguments.4',[]),(1,'operation_id','0'*36),(2,'exception.stage.fd',9),(2,'exception.stage.mnt_id',999),(2,'exception.stage.path',p.MANAGED+'/.schedule-'+('9'*32)+'.stage'),(2,'exception.stage.flags',os.O_WRONLY|os.O_APPEND),(2,'exception.errno',13),(2,'exception.line',501),(2,'exception.source_line_base64','bad'),(2,'saves.1.returned',{'identity':[1,2],'sha256':'0'*64}),(3,'product_operation_success',True),(3,'operation.success_currently_verified',True),(3,'filler_removed',False),(3,'package_after.sha256','0'*64),(3,'source_after.sha256','0'*64),(3,'worker_exits.1.reaped',False),(3,'candidate.bytes',1)]
        for ordinal,path,value in changes:
            with self.subTest(path=path):
                data,_=self.fixture();target=data[ordinal];parts=path.split('.')
                for key in parts[:-1]:target=target[int(key)] if isinstance(target,list) else target[key]
                key=parts[-1];target[int(key) if isinstance(target,list) else key]=value
                with self.assertRaises((ValueError,KeyError,TypeError)):self.parse(data)
    def test_candidate_and_final_ledger_mutations(self):
        for target,key,value in [('candidate','next_sequence',3),('candidate','last_success',None),('final_ledger','last_success',{'fake':True}),('final_ledger','packages',[{'fake':True}]),('final_ledger','next_sequence',3)]:
            with self.subTest(target=target,key=key):
                data,_=self.fixture();blob=data[3][target];doc=p.loads_strict(base64.b64decode(blob['raw_base64']));doc[key]=value;raw=p.canonical(doc)+b'\n'
                if target=='candidate':
                    data[3][target]=case.raw_blob(raw);data[1]['gate'].update(candidate_bytes=len(raw),candidate_sha256=p.sha256(raw));data[1]['gate']['stage'].update(buffer_bytes=len(raw),buffer_sha256=p.sha256(raw))
                else:
                    blob.update(bytes=len(raw),sha256=p.sha256(raw),raw_base64=base64.b64encode(raw).decode());blob['identity'][6]=len(raw);blob['version']['sha256']=p.sha256(raw)
                with self.assertRaises((ValueError,TypeError)):self.parse(data)
    def test_closed_caps_incomplete_and_binding(self):
        data,_=self.fixture()
        for bad in ({'incomplete':'failure'},{'incomplete':'x'*257}):
            if len(bad['incomplete'])<=256:
                raw=case.case_wire(0,bad,self.nonce,self.binding,self.manifest);self.assertEqual(len(p.parse_case(raw,nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest)),1)
                with self.assertRaises(ValueError):p.parse_case(raw,nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest,require_pass=True)
            else:
                with self.assertRaises(ValueError):case.case_wire(0,bad,self.nonce,self.binding,self.manifest)
        data[1]['gate']['extra']='bad'
        with self.assertRaises(ValueError):self.wires(data)
        with self.assertRaises((ValueError,RuntimeError)):case.raw_blob(b'x'*8193)
        raw=self.wires(self.fixture()[0])
        with self.assertRaises(ValueError):p.parse_case(raw,nonce='d'*32,binding=self.binding,manifest_sha256=self.manifest)
        with self.assertRaises(ValueError):p.parse_case(raw[:-1],nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest)
    def test_production_ready_ack_roundtrip_and_rejections(self):
        _,ready=self.fixture();oldcase=old.E1Tests();g,_,_=oldcase.fixture()
        # Exercise actual READY validator using a valid root READY fixture.
        ready.update(nonce=self.nonce,binding=self.binding,seed_manifest_sha256=self.manifest,setup_sha256='d'*64,qualify_sha256='e'*64,product_entries=p.product_entries())
        p.validate_ready(ready,nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest,setup_sha256='d'*64,qualify_sha256='e'*64)
        ack={'schema':'dm-e2-ack-v1','nonce':self.nonce,'binding':self.binding,'binding_transport':p.BINDING_TRANSPORT,'ready_sha256':p.sha256(p.canonical(ready)),'pre_mapping_sha256':'1'*64,'post_mapping_sha256':'2'*64}
        ready_wire=p.build_frame(p.READY_PREFIX,ready,p.FRAME_MAX);self.assertEqual(p.parse_serial_frame(ready_wire,p.READY_PREFIX),ready)
        raw=p.build_ack(ack)
        kwargs={'nonce':self.nonce,'binding':self.binding,'ready_digest':ack['ready_sha256'],'pre_digest':'1'*64,'post_digest':'2'*64}
        self.assertEqual(p.validate_ack(p.parse_ack(raw),**kwargs),ack)
        for key in ('nonce','binding','ready_sha256','pre_mapping_sha256','post_mapping_sha256'):
            bad={**ack,key:'wrong'}
            with self.assertRaises(ValueError):p.validate_ack(p.parse_ack(p.build_ack(bad)),**kwargs)
        with self.assertRaises(ValueError):p.parse_ack(raw.replace(b'DME2ACK1',b'DME1ACK1',1))
    def test_passive_observer_exception_does_not_replace_product_error(self):
        def f():pass
        actor=SimpleNamespace(request_cancel=mock.Mock(side_effect=RuntimeError('cancel failed')))
        operations=SimpleNamespace(SnapshotOperations=SimpleNamespace(_inspect=f,_save=f,backup=f));schedules=SimpleNamespace(LockedDirectory=SimpleNamespace(write=f));recovery=SimpleNamespace(_run=f)
        observer=case.CompletionObserver(actor,operations,schedules,recovery,None,None,1,None,30)
        observer.observe=mock.Mock(side_effect=RuntimeError('diagnostic failure'))
        self.assertEqual(observer.trace(SimpleNamespace(f_code=f.__code__),'line',None),observer.trace);self.assertTrue(observer.errors);self.assertTrue(observer.release.is_set())
    def test_product_pins_setup_guards_and_original_write_point(self):
        import hashlib
        for entry in p.product_entries():
            raw=(HERE/'product-source'/'defiantmaple'/Path(entry['path']).name).read_bytes();self.assertEqual(len(raw),entry['bytes']);self.assertEqual(hashlib.sha256(raw).hexdigest(),entry['sha256'])
        source=(HERE/'product-source/defiantmaple/scheduled_snapshots.py').read_bytes().splitlines(keepends=True)
        for line in (489,493):self.assertEqual(base64.b64encode(source[line-1]).decode(),p.LEDGER_LINES[line])
        self.assertIn('\"-I\",\"-B\",\"-S\"',(HERE/'guest_e2_setup.py').read_text())
        self.assertNotIn('recovery._worker_main=',(HERE/'guest_e2_case.py').read_text())

    def test_original_save_write_handoff_with_passive_gate(self):
        # Execute the exact pinned _save/write bodies under OS mocks. The tiny
        # caller models only backup's line318; no worker/native/storage runs.
        import types
        data,ready=self.fixture();pre,start,fault,finish=data
        def compiled(relative,classname,name,namespace):
            filename='/opt/dm-g0/source/defiantmaple/'+relative
            tree=ast.parse((HERE/'product-source/defiantmaple'/relative).read_text())
            cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name==classname)
            node=copy.deepcopy(next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name==name))
            exec(compile(ast.Module(body=[node],type_ignores=[]),filename,'exec'),namespace);return namespace[name]
        raw=base64.b64decode(finish['candidate']['raw_base64']);stage=start['gate']['stage'];st=SimpleNamespace(st_dev=stage['identity'][0],st_ino=stage['identity'][1])
        osmock=SimpleNamespace(O_CREAT=os.O_CREAT,O_EXCL=os.O_EXCL,O_WRONLY=os.O_WRONLY,O_NOFOLLOW=os.O_NOFOLLOW,open=mock.Mock(return_value=5),fstat=mock.Mock(return_value=st),stat=mock.Mock(return_value=st),close=mock.Mock(),unlink=mock.Mock(),write=mock.Mock(side_effect=OSError(28,'No space left on device')),fsync=mock.Mock())
        ns={'os':osmock,'uuid':SimpleNamespace(uuid4=lambda:SimpleNamespace(hex='4'*32)),'Locator':original_state_types()['Locator'],'ConfigurationTransition':original_state_types()['ConfigurationTransition'],'_leaf':lambda _:None,'encode_document':original_state_types()['encode_document'],'_stat_identity':lambda st:(st.st_dev,st.st_ino),'ScheduleError':ValueError,'StateUncertainError':RuntimeError}
        write=compiled('scheduled_snapshots.py','LockedDirectory','write',ns)
        save=compiled('snapshot_operations.py','SnapshotOperations','_save',{})
        caller=ast.parse('def backup(self):\n    return self._save(self.complete)\n');ast.increment_lineno(caller,316)
        # Function's call statement is exactly source line318.
        space={};exec(compile(caller,'/opt/dm-g0/source/defiantmaple/snapshot_operations.py','exec'),space)
        def unused():pass
        cls=type('MockBoundary',(),{'_save':save,'backup':space['backup'],'_inspect':unused})
        actor=cls();actor.owner=SimpleNamespace(validate=mock.Mock());actor.config=SimpleNamespace(_placement=mock.Mock());actor.request_cancel=mock.Mock()
        model=original_state_types();actor.state=model['decode_document'](base64.b64decode(start['started']['raw_base64']));actor.complete=model['decode_document'](raw);actor.version=model['Version'](tuple(start['started']['version']['identity']),start['started']['version']['sha256'])
        managed=SimpleNamespace(directory=Path(p.MANAGED),fd=40,lock_leaf='schedule.lock',validate=mock.Mock());managed.read=mock.Mock(return_value=(None,actor.version));managed.write=types.MethodType(write,managed);actor.managed=managed
        pressure=SimpleNamespace(fill=mock.Mock(return_value=start['filler']))
        observer=case.CompletionObserver(actor,SimpleNamespace(SnapshotOperations=cls),SimpleNamespace(LockedDirectory=SimpleNamespace(write=write)),SimpleNamespace(_run=unused),Path(p.MANAGED),pre,ready['mount_ids'][1],pressure,case.time.monotonic()+30)
        observer.captured={k:start[k] for k in ('initial','started','operation_id')};observer.saves=[copy.deepcopy(fault['saves'][0])];observer.workers=copy.deepcopy(start['workers']);observer.report={'manifest':start['package']['manifest'],'catalog':start['package']['catalog']};observer.inspected=(tuple(start['package']['identity'][:2]),start['package']['bytes'],start['package']['sha256'])
        with mock.patch.object(case.os,'open',return_value=77),mock.patch.object(case,'published_fact',return_value=start['package']),mock.patch.object(case,'descriptor_fact',return_value=copy.deepcopy(stage)):
            sys.settrace(observer.trace)
            try:
                with self.assertRaises(OSError) as error:actor.backup()
            finally:sys.settrace(None)
        if observer.thread is not None:observer.thread.join(1)
        self.assertEqual(error.exception.errno,28);self.assertEqual(observer.errors,[]);self.assertTrue(observer.captured['resumed_once']);pressure.fill.assert_called_once();osmock.write.assert_called_once();osmock.fsync.assert_not_called();osmock.close.assert_called_once_with(5);osmock.unlink.assert_called_once();actor.request_cancel.assert_not_called()
        self.assertEqual(observer.captured['candidate'],finish['candidate']);self.assertEqual(observer.captured['start']['gate'],start['gate']);self.assertEqual(observer.fault,fault['exception'])
        # Production producer/parser consume the actually observed gate/fault.
        data[1]=observer.captured['start'];data[2]['exception']=observer.fault;data[2]['saves'][1]=observer.saves[1]
        self.assertEqual(len(self.parse(data)),4)

    def test_early_incomplete_cleanup_and_diagnostic_precedence(self):
        for persistence_failure in (False,True):
            with self.subTest(persistence_failure=persistence_failure):
                sent=[];order=[]
                def identity(path):order.append('identity');return [1,2,12345,12345,0o700,2]
                def write(fd,raw):order.append('transport');sent.append(bytes(raw));return len(raw)
                with mock.patch.object(case,'runtime_preflight',side_effect=RuntimeError('original preflight failure')),mock.patch.object(case,'fixture_identity',side_effect=identity),mock.patch.object(case.Path,'exists',return_value=False),mock.patch.object(case.Path,'mkdir',return_value=None),mock.patch.object(case.os,'open',return_value=64),mock.patch.object(case.os,'close'),mock.patch.object(case.os,'fsync'),mock.patch.object(case.ordinary,'write_all',side_effect=OSError('diagnostic persistence') if persistence_failure else None),mock.patch.object(case.os,'set_blocking'),mock.patch.object(case.os,'write',side_effect=write),mock.patch.object(case.select,'select',side_effect=lambda r,w,x,t:(r,w,x)):
                    with self.assertRaisesRegex(RuntimeError,'original preflight failure'):
                        case.run_case(50,self.nonce,self.binding,self.manifest,Path('/mock/p1'),Path('/mock/p2'),10,case.time.monotonic()+5)
                records=p.parse_case(b''.join(sent),nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest)
                self.assertEqual(len(records),1);self.assertIn('original preflight failure',records[0]['data']['incomplete']);self.assertEqual(order[-1],'transport');self.assertIsNone(sys.gettrace())
                with self.assertRaises(ValueError):p.parse_case(b''.join(sent),nonce=self.nonce,binding=self.binding,manifest_sha256=self.manifest,require_pass=True)

    def test_selected_package_fd_is_held_and_reused(self):
        data,_=self.fixture();package=data[1]['package'];identity=package['identity'];payload=b'package'
        info=SimpleNamespace(st_dev=identity[0],st_ino=identity[1],st_mode=identity[2],st_uid=12345,st_gid=12345,st_nlink=1,st_size=len(payload),st_mtime_ns=10,st_ctime_ns=20)
        report={'manifest':package['manifest'],'catalog':package['catalog']}
        with mock.patch.object(case.os,'lstat',return_value=info),mock.patch.object(case.os,'fstat',return_value=info),mock.patch.object(case.os,'open') as opened,mock.patch.object(case.os,'close') as closed,mock.patch.object(case.os,'lseek') as seek,mock.patch.object(case.os,'read',side_effect=[payload,b'',payload,b'']):
            before=case.published_fact(Path(package['path']),report,77);after=case.published_fact(Path(package['path']),report,77)
        self.assertEqual(before,after);opened.assert_not_called();closed.assert_not_called();self.assertEqual(seek.call_args_list,[mock.call(77,0,os.SEEK_SET)]*2)

    def test_exact_original_partial_write_and_fsync_progress(self):
        for fsync in (False,True):
            with self.subTest(fsync=fsync):
                data,_=self.fixture();raw=base64.b64decode(data[3]['candidate']['raw_base64']);exc=data[2]['exception'];written=len(raw) if fsync else 20
                exc['stage']['identity'][6]=written;exc['stage']['buffer_bytes']=len(raw)-written;exc['stage']['buffer_sha256']=p.sha256(raw[written:])
                if fsync:exc.update(line=493,source_line_base64=p.LEDGER_LINES[493])
                self.assertEqual(len(self.parse(data)),4)
                for key,value in [('size',0 if fsync else written+1),('buffer_sha256','0'*64),('buffer_bytes',1 if fsync else len(raw))]:
                    bad=copy.deepcopy(data);stage=bad[2]['exception']['stage']
                    if key=='size':stage['identity'][6]=value
                    else:stage[key]=value
                    with self.assertRaises(ValueError):self.parse(bad)

if __name__=='__main__':unittest.main()
