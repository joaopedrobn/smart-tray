"""Read-only scene evidence. No control payload generation or replay transport."""
import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re
import uuid
from .led_research import LED_ID, LedReader
from .diagnostic import quiet

SCENES = ('Neon World', 'Dreamland', 'Iceland Blue', 'Party', 'Christmas')
GROUPS = ('Mood', 'Mood', 'DIY', 'Life', 'Festival')
MASKED_ID = LED_ID[:6] + '…' + LED_ID[-4:]
SENSITIVE_FIELDS = re.compile(r'local.?key|access.?secret|access.?id|password|passwd|token|authorization|credential', re.I)


def now():
    return datetime.now(timezone.utc).isoformat()


def safe_raw(value, secrets=(), depth=0):
    """Preserve bounded DP data, excluding credentials even inside JSON strings."""
    if depth > 6:
        raise ValueError('Nested data limit')
    if value is None or type(value) in (bool, int):
        if value is not None and any(s and s in str(value) for s in secrets):
            raise ValueError('Unsafe scalar value')
        return value
    if type(value) is float and math.isfinite(value):
        return value
    if isinstance(value, bytes):
        if len(value) > 4096 or any(s and s.encode() in value for s in secrets):
            raise ValueError('Unsafe binary value')
        return value.hex()
    if isinstance(value, str):
        if (len(value) > 8192 or any(s and s in value for s in secrets)
                or SENSITIVE_FIELDS.search(value) or re.search(r'eyJ[\w-]+\.[\w-]+\.[\w-]+',value)):
            raise ValueError('Unsafe string value')
        # Inspect JSON too: escaped property names must not bypass filtering.
        try:
            parsed = json.loads(value)
        except ValueError:
            parsed = None
        if isinstance(parsed,(dict,list,str)):
            safe_raw(parsed,secrets,depth+1)
        return value
    if isinstance(value,list) and len(value) <= 256:
        return [safe_raw(v,secrets,depth+1) for v in value]
    if isinstance(value,dict) and len(value) <= 64:
        result = {}
        for k,v in value.items():
            if not isinstance(k,str) or len(k)>128 or SENSITIVE_FIELDS.search(k):
                raise ValueError('Unsafe object field')
            safe_raw(k,secrets,depth+1)
            result[k] = safe_raw(v,secrets,depth+1)
        return result
    raise ValueError('Unsupported data')


def format_hint(value):
    if isinstance(value,str):
        if re.fullmatch(r'[0-9a-fA-F]+',value) and len(value)%2 == 0:
            return {'encoding':'hex', 'byte_length':len(value)//2}
        if len(value)>=8:
            try:
                raw = base64.b64decode(value,validate=True)
                if base64.b64encode(raw).decode() == value:
                    return {'encoding':'base64', 'byte_length':len(raw)}
            except ValueError:
                pass
        return {'encoding':'string', 'length':len(value)}
    return {'encoding':'native'}


@dataclass
class Frame:
    timestamp: str
    values: dict
    state: object = None


def capture_frame(response, secrets=()):
    if (not isinstance(response,dict) or response.get('Err') or response.get('Error')
            or not isinstance(response.get('dps'),dict) or not response['dps']):
        raise ValueError('Status unavailable')
    values = {}
    for dp,value in response['dps'].items():
        if not str(dp).isdigit() or not 0<int(dp)<=65535:
            continue
        item = {'type':type(value).__name__}
        try:
            item.update(value=safe_raw(value,secrets), format=format_hint(value))
        except ValueError:
            item['omitted'] = 'unsafe_or_oversized'
        values[str(int(dp))] = item
    if not values:
        raise ValueError('No device data')
    return Frame(now(), values)


class SceneReader(LedReader):
    def __init__(self, adapter):
        base = getattr(adapter,'base',adapter)
        super().__init__(base.record,base.store,base.factory)
        self.adapter = adapter

    def capture(self):
        with quiet():
            key = self.store.load(LED_ID)
            if not key:
                raise ValueError('Credential unavailable')
            device = self.factory(self.record,key)
            try:
                response = device.status()
                protected = (key,key.encode().hex(),base64.b64encode(key.encode()).decode())
                frame = capture_frame(response,protected)
                frame.state = self.adapter._state(response,key)
                return frame
            finally:
                device.close()


def scene_definition(path):
    """A cloud ability ID remains a candidate, not an assumed LAN mapping."""
    try:
        schema = json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(schema,dict) or schema.get('device_id_masked') != MASKED_ID:
            return None
        for query in schema.get('queries',[]):
            if not isinstance(query,dict) or query.get('result') != 'schema_read_ok':
                continue
            for e in query.get('entries',[]):
                if (isinstance(e,dict) and e.get('code') == 'dreamlight_scene_mode' and e.get('type','').lower() == 'raw'
                        and e.get('access') in ('rw','wo','wr')):
                    dp = e.get('dp_id') or e.get('ability_id')
                    limit = e.get('constraints',{}).get('maxlen')
                    if type(dp) is int and type(limit) is int and 0<limit<=4096:
                        return {'dp':str(dp),'max_bytes':limit,'code':e['code'],
                            'source':query['source'],'schema_timestamp':schema.get('timestamp'),
                            'mapping':'explicit_dp' if e.get('dp_id') else 'ability_requires_lan_observation'}
    except (OSError,ValueError,TypeError):
        pass
    return None


class Observation:
    def __init__(self, scene, definition=None):
        if scene not in SCENES:
            raise ValueError('Select a known scene name')
        self.scene, self.definition = scene, definition
        self.id = uuid.uuid4().hex
        self.frames = []

    def add(self,frame):
        self.frames.append(frame)

    def report(self,status='completed'):
        if not self.frames:
            raise ValueError('Baseline required')
        first = self.frames[0]
        samples, changes = [], {}
        previous = first.values
        for frame in self.frames[1:]:
            delta = {dp:{'before':previous.get(dp),'after':frame.values.get(dp)}
                for dp in sorted(set(previous)|set(frame.values),key=int)
                if previous.get(dp)!=frame.values.get(dp)}
            samples.append({'timestamp':frame.timestamp,'changes':delta})
            previous = frame.values
        for dp in sorted(set().union(*(set(f.values) for f in self.frames)),key=int):
            series = [f.values.get(dp) for f in self.frames]
            transitions = sum(a!=b for a,b in zip(series,series[1:]))
            if not transitions:
                continue
            after = series[1:]
            changes[dp] = {'before':series[0],'after':series[-1], 'transitions':transitions,
                'continuously_changing':sum(a!=b for a,b in zip(after,after[1:]))>=2,
                'stable_last_samples':len(after)>=2 and after[-1]==after[-2],
                'interpretation':'observed_correlation_not_validated_command'}
        candidate = None
        if status=='completed' and self.definition:
            dp = self.definition['dp']
            item = changes.get(dp,{})
            final = item.get('after') or {}
            fmt = final.get('format',{})
            # Copy the observed string exactly. Never synthesize a scene ID,
            # alter unknown fields, or propose a length/pixel/timer command.
            if (dp not in {'20','21','24','26','46','47','53'} and item.get('stable_last_samples')
                    and not item.get('continuously_changing') and final.get('type')=='str'
                    and isinstance(final.get('value'),str) and fmt.get('encoding') in ('hex','base64')
                    and 0<fmt.get('byte_length',0)<=self.definition['max_bytes']
                    and previous.get('20',{}).get('value') is True
                    and previous.get('21',{}).get('value')=='scene'
                    and '20' not in changes):
                candidate = {'command':{dp:final['value']},'confidence':'observed_stable_schema_candidate',
                    'schema':self.definition,'requires':{'20':True,'21':'scene'},
                    'write_validated':False,'physical_confirmation':False,
                    'approval_required':True,'encoding_conversion_performed':False}
        return {'version':1,'id':self.id,'device_id_masked':MASKED_ID,'scene':self.scene,
            'group':GROUPS[SCENES.index(self.scene)],'started_at':first.timestamp,
            'ended_at':self.frames[-1].timestamp,'status':status,'baseline':first.values,
            'sample_count':len(self.frames),'samples':samples,'changes':changes,'candidate':candidate,
            'confidence':'medium_correlation_only' if candidate else 'low' if changes else 'no_observable_evidence',
            'writes_sent':0,'write_validated':False}


def save_report(directory, report):
    directory = Path(directory)
    directory.mkdir(parents=True,exist_ok=True)
    if not re.fullmatch(r'[0-9a-f]{32}',report['id']):
        raise ValueError('Invalid session')
    path = directory/(report['id']+'.json')
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(path)
    return path
