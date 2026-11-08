"""生成可复现的 Blender 安装包和 SHA256；排除测试输出及临时工程。"""
from pathlib import Path
import ast
import hashlib
import zipfile


def _contents(path):
    data = path.read_bytes()
    return data.replace(b'\r\n', b'\n') if path.suffix in {'.py', '.md', '.svg'} else data


def build():
    root = Path(__file__).resolve().parents[1]
    tree = ast.parse((root/'__init__.py').read_text(encoding='utf-8'))
    info = next(ast.literal_eval(node.value) for node in tree.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == 'bl_info' for target in node.targets))
    version = '.'.join(str(number) for number in info['version'])
    files = [root/name for name in ('__init__.py', 'preferences.py', 'automation.py', 'README.md', 'AGENTS.md')]
    for directory in ('core', 'operators', 'ui', 'utils', 'tools'):
        files.extend(sorted((root/directory).glob('*.py')))
    files.extend(sorted((root/'docs').glob('*.md')))
    files.extend(path for path in (root/'ui'/'assets').rglob('*') if path.suffix in {'.png', '.svg'})
    files.sort(key=lambda path: path.relative_to(root).as_posix())
    output = root/'dist'
    output.mkdir(exist_ok=True)
    package = output/f'CineController-{version}.zip'
    with zipfile.ZipFile(package, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in files:
            entry = zipfile.ZipInfo('CineController/'+path.relative_to(root).as_posix())
            entry.compress_type = zipfile.ZIP_DEFLATED
            entry.external_attr = 0o100644 << 16
            archive.writestr(entry, _contents(path), compresslevel=9)
    with zipfile.ZipFile(package) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist()) == len(files)
        for path in files:
            assert archive.read('CineController/'+path.relative_to(root).as_posix()) == _contents(path)
    digest = hashlib.sha256(package.read_bytes()).hexdigest()
    (output/'SHA256SUMS.txt').write_text(f'{digest}  {package.name}\n', encoding='utf-8')
    print(f'已校验 {len(files)} 个文件：{package}')
    print('SHA256: '+digest)
    return package


if __name__ == '__main__':
    build()
