"""Run the actual Windows launcher and update a disposable previous installation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from zipfile import ZipFile


def verify(previous, current, output):
    if sys.platform != 'win32':
        raise RuntimeError('Native Windows is required; this check must not be simulated')
    output.mkdir(parents=True, exist_ok=True)
    report = {'system':'Windows', 'success':False}
    with tempfile.TemporaryDirectory(prefix='bricklabo-portable-') as disposable:
        home = Path(disposable); root = home / 'BrickLabo'
        with ZipFile(previous) as archive:
            archive.extractall(home)
        version = json.loads((root/'app/structure.json').read_text(encoding='utf-8'))['version']
        with ZipFile(current) as archive:
            target_version = json.loads(archive.read('BrickLabo/app/structure.json'))['version']
        environment = dict(os.environ, QT_QPA_PLATFORM='windows', PYTHONUTF8='1')
        for name in ('PYTHONPATH','PYTHONHOME','QT_PLUGIN_PATH','QT_QPA_PLATFORM_PLUGIN_PATH','BRICKLABO_ROOT'):
            environment.pop(name, None)
        def launch(expected):
            subprocess.run([str(root/'BrickLabo.exe'),'--self-test'], cwd=home, env=environment, check=True, timeout=120)
            data = json.loads((root/'Donnees/diagnostic.json').read_text(encoding='utf-8'))
            assert data['status']=='ok' and data['version']==expected, data
            assert all(data[name] for name in ('fts5','undo','render3d','thumbnail')), data
            return data
        report['previous_diagnostic'] = launch(version)
        (root/'Donnees/validation-private-marker.bin').write_bytes(b'disposable collection marker')
        driver = home/'apply_update.py'
        driver.write_text('''import hashlib,json,sys
from pathlib import Path
from atelier import software_updates as updates
root=Path(sys.argv[1]);archive=Path(sys.argv[2]);version=sys.argv[3];receipt=Path(sys.argv[4])
class LocalArchive:
    def __enter__(self):
        self.file=archive.open('rb');self.headers={'Content-Length':str(archive.stat().st_size)};return self
    def read(self,size=-1):return self.file.read(size)
    def __exit__(self,*args):self.file.close()
with archive.open('rb') as stream:sha=hashlib.file_digest(stream,'sha256').hexdigest()
entry={'tag_name':'v'+version,'draft':False,'prerelease':False,'assets':[{'name':'BrickLabo_v'+version+'_Complet.zip','size':archive.stat().st_size,'state':'uploaded','digest':'sha256:'+sha,'browser_download_url':'https://github.com/sdu07git/BrickLabo/releases/download/v'+version+'/BrickLabo_v'+version+'_Complet.zip'}]}
release=updates.select_release([entry]);assert release.installable
prepared=updates.prepare_update(root,release,opener=lambda *a,**kw:LocalArchive())
receipt.write_text(json.dumps({'stage':str(prepared.stage),'pin':prepared.pin}),encoding='utf-8')
prepared.handed_off=True;prepared.release_lease()
''',encoding='utf-8')
        receipt=home/'prepared.json'
        # Preparation runs in the OLD embedded interpreter. Deployment runs in
        # the updater's separate, verified interpreter after the old one exits.
        subprocess.run([str(root/'app/python.exe'), '-B', str(driver), str(root), str(current.resolve()), target_version, str(receipt)],
                       cwd=home, env=environment, check=True, timeout=240)
        prepared=json.loads(receipt.read_text(encoding='utf-8'));stage=Path(prepared['stage'])
        apply=home/'deploy_update.py'
        apply.write_text('''import importlib.util,sys
from pathlib import Path
stage=Path(sys.argv[1]);pin=sys.argv[2]
spec=importlib.util.spec_from_file_location('installer',stage/'i.py')
installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)
plan,root,stage=installer.validate_plan(stage/'plan.json',pin)
installer.verify_runner(plan,stage)
with installer.acquire_lease(stage/'maj'),installer.acquire_lease(root/'Donnees/maj/verrou'):
    installer.deploy(plan,root,stage,restart=False)
''',encoding='utf-8')
        subprocess.run([str(stage/'r/python.exe'),'-I','-B',str(apply),str(stage),prepared['pin']],
                       cwd=home,env=environment,check=True,timeout=240)
        assert (root/'Donnees/validation-private-marker.bin').read_bytes()==b'disposable collection marker'
        report['current_diagnostic'] = launch(target_version)
        report.update(version=target_version, from_version=version, update_preserved_data=True,
                      launcher_executed=True, success=True)
    (output/'portable-windows.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('previous',type=Path);parser.add_argument('current',type=Path)
    parser.add_argument('--output',type=Path,required=True)
    options=parser.parse_args()
    if options.current.is_dir():
        from check_release import ROOT
        version=json.loads((ROOT/'app/structure.json').read_text(encoding='utf-8'))['version']
        options.current=options.current/('BrickLabo_v'+version+'_Complet.zip')
    verify(options.previous,options.current,options.output)
