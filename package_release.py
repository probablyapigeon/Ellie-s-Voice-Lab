"""Bundle the built Windows folder and a whitelist of distributable source files."""
import hashlib
import shutil
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parent
release = root / 'releases'; release.mkdir(exist_ok=True)
binary = root / 'dist' / 'BirdVoiceLab'
if not (binary / 'BirdVoiceLab.exe').is_file():
    raise SystemExit('Build the Windows executable first.')
for name in ('README.md', 'LICENSE'):
    shutil.copy2(root / name, binary / name)
shutil.copy2(root / 'docs' / 'FOR_JEN.md', binary / 'READ_ME_FIRST.md')
shutil.make_archive(str(release / 'BirdVoiceLab-0.1.0-Windows'), 'zip', binary.parent, binary.name)
files = [root / p for p in ('README.md', 'LICENSE', '.gitignore', 'app.py', 'lab.py', 'start.cmd', 'package_release.py')]
for directory in ('web', 'tests', 'docs'):
    files.extend(p for p in (root / directory).rglob('*') if p.is_file() and '__pycache__' not in p.parts)
with zipfile.ZipFile(release / 'BirdVoiceLab-0.1.0-Source.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(files):
        archive.write(path, Path('BirdVoiceLab') / path.relative_to(root))
checksums = []
for path in sorted(release.glob('*.zip')):
    checksums.append(hashlib.sha256(path.read_bytes()).hexdigest() + '  ' + path.name)
(release / 'SHA256SUMS.txt').write_text('\n'.join(checksums) + '\n', encoding='utf-8')
print('\n'.join(f'{p.name}: {p.stat().st_size / 1024 / 1024:.1f} MB' for p in release.glob('*.zip')))
