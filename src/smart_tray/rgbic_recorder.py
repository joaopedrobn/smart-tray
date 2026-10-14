"""GUI coordinator for serialized, bounded, read-only RGBIC observations."""
import json
from pathlib import Path
import time
from PySide6.QtCore import QObject, QRunnable, QTimer, Signal, Slot, Qt
from .adapters import DeviceState
from .rgbic_capture import SCENES, MASKED_ID, Observation, save_report, scene_definition


class CaptureSignals(QObject):
    done = Signal(object)


class CaptureTask(QRunnable):
    def __init__(self, reader):
        super().__init__()
        self.reader = reader
        self.signals = CaptureSignals()

    def run(self):
        try:
            result = self.reader.capture()
        except Exception:
            result = None  # Never propagate exception text or transport objects.
        self.signals.done.emit(result)


class SceneRecorder(QObject):
    changed = Signal()

    def __init__(self, controller, reader, directory, schema_path, parent=None,
                 *, interval_ms=2000, observe_seconds=10, prepare_seconds=120):
        super().__init__(parent)
        self.controller, self.reader = controller, reader
        self.directory = Path(directory)
        self.definition = scene_definition(schema_path)
        self.interval_ms, self.observe_seconds, self.prepare_seconds = interval_ms, observe_seconds, prepare_seconds
        self.index = 0
        self.phase = 'idle'
        self.session = self.task = self.result = None
        self.path = ''
        self.note = ''
        self.deadline = None
        self.final_sample_requested = False
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self._tick)
        self.heartbeat = QTimer(self)
        self.heartbeat.setInterval(500)
        self.heartbeat.timeout.connect(self.changed)
        controller.changed.connect(self._controller_changed)
        self.catalog = self._catalog()

    def _catalog(self):
        rows = []
        files = []
        for path in self.directory.glob('*.json'):
            try:
                files.append((path.stat().st_mtime,path))
            except OSError:
                continue
        for _,path in sorted(files,reverse=True)[:20]:
            try:
                if path.stat().st_size>1000000:
                    continue
                report = json.loads(path.read_text(encoding='utf-8'))
                if not isinstance(report,dict) or report.get('device_id_masked')!=MASKED_ID or report.get('scene') not in SCENES:
                    continue
                changes = report.get('changes',{})
                rows.append({'name':report['scene'],'detail':f'{len(changes)} DPS alterados · correlação não validada'})
            except (OSError,ValueError,TypeError):
                continue
        return rows

    @property
    def active(self):
        return self.phase in ('baseline','prepared','observing','cancelling')

    def view(self):
        count = len(self.session.frames) if self.session else 0
        names = {'idle':'Selecione um efeito para descobrir.',
            'baseline':'Consultando a fita e capturando o estado inicial…',
            'prepared':f'Escolha {SCENES[self.index]} no Smart Life. Depois clique em Concluir captura.',
            'observing':'Observando as alterações por 10 segundos…',
            'cancelling':'Finalizando a leitura em andamento…',
            'saved':'Captura salva. Correlação observada; nenhuma escrita validada.',
            'error':'Captura interrompida. Confira a conexão e tente iniciar uma nova sessão.',
            'cancelled':'Captura encerrada sem enviar comandos.'}
        remaining = max(0,self.deadline-time.monotonic()) if self.deadline else 0
        return {'names':list(SCENES),'sceneIndex':self.index,'name':SCENES[self.index],
            'phase':self.phase,'active':self.active,'canStart':not self.active and not self.controller.stopping
                and not self.controller.writing and 'led' not in self.controller.busy,
            'canConclude':self.phase=='prepared','canNext':not self.active and self.phase in ('saved','error','cancelled'),
            'instruction':names[self.phase], 'note':self.note,'sampleCount':count,
            'secondsRemaining':round(remaining),'progress':max(0,min(1,1-remaining/self.observe_seconds))
                if self.phase=='observing' else 0,
            'resultText':self.describe(), 'savedPath':self.path,'catalog':self.catalog}

    def describe(self):
        if not self.result:
            return ''
        result = self.result
        lines = [result['scene'] + ' · ' + str(result['sample_count']) + ' leituras',
            'Confiança: ' + ('média, candidata a teste' if result['candidate'] else
                'baixa, apenas correlação' if result['changes'] else 'sem evidência observável')]
        if not result['changes']:
            lines.append('Nenhum DPS mudou. Isso não prova incompatibilidade: o comando pode não aparecer nas consultas de estado.')
        for dp,change in result['changes'].items():
            lines.append('\nDPS '+dp+' · mudanças: '+str(change['transitions'])+
                (' · varia durante a captura' if change['continuously_changing'] else ' · sem variação contínua observada'))
            for title,key in (('Antes','before'),('Depois','after')):
                value = change[key]
                lines.append(title+': '+json.dumps(value,ensure_ascii=False))
        if result['candidate']:
            lines.extend(['\nProposta para revisão — não executada:',
                json.dumps(result['candidate']['command'],ensure_ascii=False),
                'Requer fita ligada em Cena. Aguarda autorização específica e confirmação visual.'])
        elif result['changes']:
            lines.append('\nNenhum payload de efeito seguro identificado para reprodução. Não serão testados DPS por tentativa e erro.')
        lines.append('\nEscritas enviadas: 0. Comandos validados: nenhum.')
        return '\n'.join(lines)

    def select(self,index):
        if type(index) is not int or not 0<=index<len(SCENES) or self.active:
            return False
        self.index=index
        self.changed.emit()
        return True

    def start(self):
        if self.active or self.task or not self.controller.reserve_led_observation(self):
            return False
        self.phase='baseline'
        self.session=Observation(SCENES[self.index],self.definition)
        self.result=None
        self.path=self.note=''
        self.deadline=None
        self.heartbeat.start()
        self.changed.emit()
        self._read()
        return True

    def conclude(self):
        if self.phase!='prepared':
            return False
        self.phase='observing'
        self.final_sample_requested=False
        self.deadline=time.monotonic()+self.observe_seconds
        self.timer.stop()
        if not self.task:
            self._read()  # Immediate sample, then a bounded observation window.
        self.changed.emit()
        return True

    def next(self):
        if self.active:
            return False
        self.index=(self.index+1)%len(SCENES)
        self.phase='idle'
        self.session=self.result=None
        self.path=self.note=''
        self.changed.emit()
        return True

    def cancel(self,force=False):
        if not self.active:
            return
        self.timer.stop(); self.heartbeat.stop()
        self.phase='cancelling'
        if not self.task or force:
            self._finish('cancelled')
        else:
            self.changed.emit()

    def _controller_changed(self):
        if self.controller.stopping:
            self.cancel(force=True)

    def _read(self):
        if self.task or not self.active or self.controller.stopping:
            return
        self.task=CaptureTask(self.reader)
        self.task.signals.done.connect(self._received,Qt.ConnectionType.QueuedConnection)
        self.controller.pool.start(self.task)

    @Slot(object)
    def _received(self,frame):
        self.task=None
        if self.phase=='cancelling':
            self._finish('cancelled')
            return
        if not self.active or self.controller.stopping:
            return
        if frame is None:
            self.controller.states['led']=DeviceState('unknown',{},'Captura indisponível')
            self._finish('failed')
            return
        if frame.state is not None:
            self.controller.states['led']=frame.state
            self.controller.changed.emit()
        self.session.add(frame)
        if self.phase=='baseline':
            self.phase='prepared'
            self.deadline=time.monotonic()+self.prepare_seconds
        try:
            self.path=str(save_report(self.directory,self.session.report(self.phase)))
        except OSError:
            self.note='Não foi possível salvar. A captura foi interrompida.'
            self._finish('failed')
            return
        self.changed.emit()
        self._schedule()

    def _schedule(self):
        remaining=(self.deadline or time.monotonic())-time.monotonic()
        if remaining<=0:
            if self.phase=='observing' and not self.final_sample_requested:
                self.final_sample_requested=True
                self._read()
            else:
                self._finish('completed' if self.phase=='observing' else 'cancelled')
        else:
            self.timer.start(max(1,min(self.interval_ms,round(remaining*1000))))

    def _tick(self):
        if self.deadline and time.monotonic()>=self.deadline:
            if self.phase=='observing':
                self.final_sample_requested=True
                self._read()  # Include a final snapshot at the end of the window.
            else:
                self._finish('cancelled')
        else:
            self._read()

    def _finish(self,status):
        self.timer.stop(); self.heartbeat.stop()
        self.phase={'completed':'saved','failed':'error','cancelled':'cancelled'}[status]
        try:
            if self.session and self.session.frames:
                self.result=self.session.report(status)
                self.path=str(save_report(self.directory,self.result))
                self.catalog=self._catalog()
        except OSError:
            self.phase='error'
            self.note='Não foi possível salvar o catálogo. Os dados continuam visíveis nesta sessão.'
        finally:
            self.controller.release_led_observation(self)
            self.changed.emit()
