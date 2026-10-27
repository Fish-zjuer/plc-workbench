from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from plc_agent.backend_r4 import info
from plc_agent.backend_capabilities import preflight
from plc_agent.bank_contracts import questions
from plc_agent.config import ROOT
from plc_agent.duration_checks import test_durations as execute_durations
from plc_agent.reference_checks import test_references as execute_refs
from plc_probe.backend import _command,BackendError
from plc_probe.config import base_cache_dir,cache_dir,toolchain_dir


class R4Tests(unittest.TestCase):
    def setUp(self):
        if not info():self.skipTest('Requires explicitly built/selected R4 backend')
        self.temp=tempfile.TemporaryDirectory(dir=cache_dir());self.addCleanup(self.temp.cleanup)
        self.folder=Path(self.temp.name)

    def native(self,text,name='test'):
        source=self.folder/(name+'.cpp');source.write_text(text,encoding='utf-8')
        exe=self.folder/(name+'.exe')
        include=os.path.relpath(toolchain_dir()/'runtime/include',self.folder)
        try:_command([shutil.which('g++'),'-std=c++17','-O1','-static','-I',include,source.name,'-o',exe.name],self.folder,'native_'+name)
        except BackendError as exc:self.fail(exc.result.get('stderr','')[:4000])
        return subprocess.run([str(exe)],capture_output=True,text=True,encoding='utf-8',timeout=10)

    def test_duration_conversions_and_large_literal_are_exact(self):
        # A compiler conformance fixture, not a generated course answer.
        (self.folder/'feature.st').write_text('''FUNCTION_BLOCK Feature
VAR_OUTPUT ms : LINT; ns : LINT; duration : LTIME; exact : LINT; END_VAR
ms := TIME_TO_LINT(T#1s);
ns := LTIME_TO_LINT(TIME_TO_LTIME(T#1s));
duration := LINT_TO_LTIME(1000000000);
exact := LTIME_TO_LINT(LTIME#123d4h5m6s7ms8us9ns);
END_FUNCTION_BLOCK''',encoding='utf-8')
        _command([str(toolchain_dir()/'strucpp.exe'),'feature.st','-o','feature.cpp'],self.folder,'st_feature')
        result=self.native('''#include "feature.hpp"
#include "feature.cpp"
#include <iostream>
int main(){strucpp::FEATURE f;f();std::cout<<static_cast<long long>(f.MS)<<" "<<static_cast<long long>(f.NS)<<" "<<static_cast<long long>(f.DURATION)<<" "<<static_cast<long long>(f.EXACT);}''')
        self.assertEqual(result.returncode,0)
        exact=123*86400000000000+4*3600000000000+5*60000000000+6*1000000000+7000000+8000+9
        self.assertEqual(list(map(int,result.stdout.split())),[1000,1000000000,1000000000,exact])

    def test_open_array_aliases_caller_retains_bounds_and_rejects_unbound_access(self):
        result=self.native('''#include "iec_array.hpp"
#include <stdexcept>
int main(){using namespace strucpp;IEC_INT storage[3]{};ArrayView1D<IEC_INT> a(storage,-7,-5);a.at(-6)=42;
if(static_cast<int>(storage[1])!=42||a.lower_bound()!=-7||a.upper_bound()!=-5)return 1;
auto b=a;b.at(-5)=91;if(static_cast<int>(storage[2])!=91)return 2;
try{ArrayView1D<IEC_INT> unbound;unbound.at(0)=1;return 3;}catch(const std::out_of_range&){}
try{a.at(-4)=1;return 4;}catch(const std::out_of_range&){}
return 0;}''')
        self.assertEqual(result.returncode,0,result.stderr)

    def test_variant_references_copy_values_and_reject_bad_types_and_bounds(self):
        result=self.native('''#include "iec_variant.hpp"
struct Record{int id=0;double value=0;};
int main(){using namespace strucpp;Record array[2]{};Record value{17,2.75};IEC_VARIANT buffer,item;
buffer.bind_array(array,2);item.bind_scalar(value);
if(static_cast<int>(PV_COUNT(buffer))!=2||!PV_COMPATIBLE(buffer,item))return 1;
if(!PV_WRITE(buffer,1,item)||array[1].id!=17||array[1].value!=2.75)return 2;
value={99,18};if(!PV_READ(buffer,1,item)||value.id!=17||value.value!=2.75)return 3;
if(PV_WRITE(buffer,2,item)||PV_READ(buffer,-1,item)||value.id!=17)return 4;
double wrong=44;IEC_VARIANT mismatch;mismatch.bind_scalar(wrong);
if(PV_COMPATIBLE(buffer,mismatch)||PV_WRITE(buffer,0,mismatch)||PV_READ(buffer,0,mismatch)||wrong!=44)return 5;
IEC_VARIANT empty;if(static_cast<int>(PV_COUNT(empty))!=0||PV_READ(empty,0,item))return 6;
return 0;}''')
        self.assertEqual(result.returncode,0,result.stderr)

    def test_original_analog_candidate_passes_and_readonly_mutation_is_caught(self):
        source=ROOT/'experiments/workflow_r2/tasks/08/final.st'
        self.assertEqual(execute_refs(source,'08')['status'],'pass')
        code=source.read_text(encoding='utf-8')
        mutant=self.folder/'mutant.st';mutant.write_text(code.replace('FOR i := 0 TO nProc - 1 DO','FOR i := 0 TO nProc - 1 DO\n analogValues[aLower+i] := 0;'),encoding='utf-8')
        result=execute_refs(mutant,'08')
        self.assertEqual(result['status'],'fail')
        self.assertEqual(result['first_failure'].get('property'),'readonly_input')

    def test_fifo_count_only_mutant_is_caught_by_real_payload_checks(self):
        source=ROOT/'experiments/backend_r4/tasks/18/final.st'
        if not source.exists():self.skipTest('Live candidate not yet available')
        self.assertEqual(execute_refs(source,'18')['status'],'pass')
        code=source.read_text(encoding='utf-8')
        self.assertIn('PV_WRITE(buffer, diTail, item)',code)
        mutant=self.folder/'mutant.st';mutant.write_text(code.replace('PV_WRITE(buffer, diTail, item)','TRUE'),encoding='utf-8')
        result=execute_refs(mutant,'18')
        self.assertEqual(result['status'],'fail')
        self.assertEqual(result['first_failure'].get('property'),'enqueue_writes_caller_buffer')

    def test_duration_supplement_catches_early_maintenance_and_missing_retrigger(self):
        for q in ('04','12'):
            source=ROOT/'experiments/backend_r4/tasks'/q/'initial_final.st'
            if not source.exists():self.skipTest('Expanded-check baseline not yet available')
            result=execute_durations(source,q)
            self.assertEqual(result['status'],'fail',q)
        self.assertEqual(result['first_failure']['scenario'],'each_new_fault_restarts_its_minimum_hold')

    def test_cache_changes_when_runtime_changes_and_release_preflight_is_preserved(self):
        fake=self.folder/'backend';(fake/'runtime/include').mkdir(parents=True)
        (fake/'strucpp.exe').write_bytes(b'fixture')
        header=fake/'runtime/include/fixture.hpp';header.write_text('old',encoding='utf-8')
        with patch.dict(os.environ,{'STRUC_PP_HOME':str(fake)}):
            first=cache_dir();header.write_text('changed runtime',encoding='utf-8');second=cache_dir()
            self.assertNotEqual(first,second)
        legacy=base_cache_dir()/'strucpp-0.7.0/strucpp'
        question=next(q for q in questions() if q['id']=='18')
        with patch.dict(os.environ,{'STRUC_PP_HOME':str(legacy)}):
            self.assertEqual(preflight(question)['status'],'backend_variant_unavailable')

    def test_registered_compiler_bundle_and_runtime_match_installed_manifest(self):
        metadata=info();import hashlib
        for relative,digest in metadata['artifacts_sha256'].items():
            with self.subTest(path=relative):self.assertEqual(hashlib.sha256((toolchain_dir()/relative).read_bytes()).hexdigest(),digest)

    def test_receipt_is_stale_when_backend_or_evaluation_protocol_changes(self):
        import hashlib
        from plc_agent.engine import source_hash_for_receipt
        from plc_agent.extended_eval import evaluation_fingerprint
        from plc_agent.storage import Project,Session
        from plc_agent.toolbox import Toolbox
        project=Project.create('receipt identity',self.folder);session=Session.create(project)
        source=project.workspace/'a.st';source.write_text('fixture source',encoding='utf-8')
        receipt={'source':'a.st','source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                 'backend_fingerprint':info()['fingerprint'],'evaluation_fingerprint':evaluation_fingerprint()}
        self.assertTrue(source_hash_for_receipt(Toolbox(session),receipt))
        self.assertFalse(source_hash_for_receipt(Toolbox(session),{**receipt,'backend_fingerprint':'different compiler'}))
        self.assertFalse(source_hash_for_receipt(Toolbox(session),{**receipt,'evaluation_fingerprint':'different oracle'}))


if __name__=='__main__':unittest.main()
