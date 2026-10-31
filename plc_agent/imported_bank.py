"""Versioned, data-only imports. Built-in frozen tasks are never overwritten."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import uuid
from . import dataset
from .storage import atomic_json

FORMATS = {'bank_trace', 'complete_input_trace', 'profile_trace', 'struct_rows', 'analog_reference_rows', 'fifo_reference_rows'}
NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_]{0,63}\Z')
DTYPE = re.compile(r'(?:[A-Za-z_][A-Za-z0-9_]*(?:\(\d{1,4}\))?|ARRAY\[(?:\*|-?\d{1,6}\.\.-?\d{1,6})\] OF [A-Za-z_][A-Za-z0-9_]*)\Z', re.I)

def digest(value):
    return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False).encode()).hexdigest()

class ImportedBank:
    def __init__(self, home): self.root = Path(home)/'imported_banks'
    def catalog(self, include_builtin=True):
        rows = list(dataset.catalog()['tasks']) if include_builtin else []
        for file in sorted(self.root.glob('*/bank.json')):
            bank = json.loads(file.read_text(encoding='utf-8'))
            rows += [{'id':key, 'title':'[导入] '+t['title'], 'bank_version':bank['version']}
                     for key,t in bank['tasks'].items()]
        return {'schema':'plc-workbench-catalog-v1','tasks':rows}
    def load(self, key):
        if not key.startswith('IMPORT_'): return dataset.load(key)
        match = re.fullmatch(r'IMPORT_([a-f0-9]{32})__([A-Za-z_][A-Za-z0-9_]{0,63})',key)
        if not match: raise ValueError('Invalid imported task ID')
        bank = json.loads((self.root/match[1]/'bank.json').read_text(encoding='utf-8'))
        task=deepcopy(bank['tasks'][key])
        measured=task.pop('dataset_sha256')
        if digest(task)!=measured: raise ValueError('导入题库内容发生变化，请重新导入创建版本')
        task['dataset_sha256']=measured
        return task
    def import_files(self, files, target=None):
        if not isinstance(files,list) or not 1<=len(files)<=1000: raise ValueError('请选择 1–1000 个文件')
        if sum(len(f.get('content','')) for f in files)>128000000: raise ValueError('导入总大小不能超过 128 MB')
        tasks, specs, texts, metadata, maps, buckets = {}, {}, [], {}, [], []
        sources=[]
        for f in files:
            name=Path(f['name']).name; content=f['content'].lstrip('\ufeff')
            sources.append({'name':name,'sha256':hashlib.sha256(content.encode()).hexdigest()})
            if name.lower().endswith(('.ltl','.md','.txt')):
                stem=Path(name).stem
                bind=stem if re.fullmatch(r'(PUBLIC|CUSTOM)_\d\d',stem) else target
                if not bind: raise ValueError('文本文件需要选择目标题目，或使用 PUBLIC_01.ltl 这类文件名')
                texts.append((bind,name,content)); continue
            if not name.lower().endswith('.json'): raise ValueError('只接受 JSON、LTL、Markdown 或 TXT 数据文件')
            value=json.loads(content,parse_constant=lambda s: (_ for _ in ()).throw(ValueError('不能使用非有限数字')))
            schema=value.get('schema','') if isinstance(value,dict) else ''
            if schema in ('plc-ltl-requirements-v1','plc-constraints-v1'):
                for row in value['tasks']:
                    if row['id'] in specs: raise ValueError('重复规约 ID: '+row['id'])
                    specs[row['id']]=row
            elif isinstance(value,dict) and {'easy','medium','hard'}<=value.keys():
                for bucket in ('easy','medium','hard'):
                    for row in value[bucket]:
                        if 'id' in row and 'en' in row: metadata[row['id']]=row
                buckets.append(value)
            elif isinstance(value,list) and value and 'input_path' in value[0]: maps.extend(value)
            else:
                rows=value if isinstance(value,list) else value.get('tasks',[value])
                for row in rows:
                    if not isinstance(row,dict) or 'id' not in row: raise ValueError('任务需要 id 字段')
                    if row['id'] in tasks: raise ValueError('重复任务 ID: '+row['id'])
                    tasks[row['id']]=row
        # Explicit mappings from the teammate delivery connect difficulty buckets to IDs.
        for mapping in maps:
            for bucket in buckets:
                rows=bucket.get(mapping['bucket'],[])
                index=mapping['index_zero_based']
                if index<len(rows) and 'en' in rows[index]:
                    en=rows[index]['en']
                    if mapping.get('en_sha256') and hashlib.sha256(en.encode()).hexdigest()!=mapping['en_sha256']:
                        raise ValueError('题号映射 SHA256 不匹配')
                    metadata.setdefault(mapping['id'],{})['en']=en
        ids=set(tasks)|set(specs)|set(metadata)
        ids.update(bind for bind,_,_ in texts)
        if not ids: raise ValueError('未找到任务；分桶英文题库请同时导入题号映射或含 ID 的元数据')
        version=uuid.uuid4().hex; result={}
        for ident in sorted(ids):
            row=tasks.get(ident,{})
            try: base=self.load(ident)
            except (ValueError,FileNotFoundError): base={}
            task={**base,**row}
            if ident in metadata:
                task['requirements']=metadata[ident]['en']
                task['provenance']=metadata[ident].get('provenance',{})
            if ident in specs:
                spec=specs[ident]
                if 'constraints' in spec: task['constraints']=spec['constraints']
                if 'properties' in spec or 'text' in spec or 'ltl' in spec:
                    task['ltl']={**spec.get('ltl',spec), 'status':'specification_not_proved'}
            for bind,name,content in texts:
                if ident!=bind: continue
                if name.lower().endswith('.md'): task['requirements']=content
                elif name.lower().endswith('.ltl'): task['ltl']={'text':content,'status':'specification_not_proved'}
                else: task['constraints']=[content]
            task.setdefault('title',ident)
            constraints=task.get('constraints',[])
            if not isinstance(constraints,list) or any(not isinstance(c,str) for c in constraints): raise ValueError('constraints 必须是文本列表')
            if not task.get('block') or not task.get('requirements') or not task.get('interface'):
                raise ValueError(f'{ident}: 新任务必须包含 block、requirements、interface；现有题可单独导入约束')
            if not NAME.fullmatch(task['block']): raise ValueError('无效功能块名称')
            seen=set()
            for p in task['interface']:
                if p['direction'] not in ('Input','Output','Input/Output') or not NAME.fullmatch(p['name']): raise ValueError('无效接口')
                if p['name'].upper() in seen: raise ValueError('接口重名')
                seen.add(p['name'].upper())
                if not DTYPE.fullmatch(p['type']): raise ValueError('不支持的接口类型: '+p['type'])
            fmt=task.setdefault('adapter_format','bank_trace')
            if fmt not in FORMATS: raise ValueError('不支持的执行适配器: '+fmt)
            if fmt in ('struct_rows','analog_reference_rows','fifo_reference_rows') and (not base or fmt!=base['adapter_format'] or task['interface']!=base['interface'] or task['block']!=base['block']):
                raise ValueError('特殊执行桥仅支持接口不变的内置题版本')
            task.setdefault('scenarios',[]); task.setdefault('ltl',{})
            if isinstance(task['ltl'],dict): task['ltl']['status']='specification_not_proved'
            scenarios=task['scenarios']
            if not isinstance(scenarios,list) or len(scenarios)>500: raise ValueError('测试场景必须是列表，最多500个')
            if sum(len(c.get('trace',c.get('rows',[]))) for c in scenarios)>20000: raise ValueError('测试扫描总数不能超过20000')
            original=task.get('original_id',ident)
            if not NAME.fullmatch(original): raise ValueError('无效任务 ID')
            key=f'IMPORT_{version}__{original}'
            task.update(id=key,original_id=original,bank_version=version,execution_status='not_executed')
            task.pop('dataset_sha256',None)
            task['dataset_sha256']=digest(task)
            result[key]=task
        record={'schema':'plc-imported-bank-v1','version':version,'sources':sources,'tasks':result}
        atomic_json(self.root/version/'bank.json',record)
        return {'version':version,'count':len(result),'tasks':[{'id':k,'title':v['title']} for k,v in result.items()]}
