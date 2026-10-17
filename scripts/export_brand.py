"""Export every application icon from the same versioned Cinna artwork."""
import hashlib
import json
from pathlib import Path
from PIL import Image, ImageDraw

root = Path(__file__).resolve().parents[1]
project = json.loads((root / 'project.json').read_text('utf-8'))
source = root / project['brand']['source']
master = Image.open(source).convert('RGBA').resize((1024,1024),Image.Resampling.LANCZOS)
master.save(root / 'resources/icon-master.png')

def rounded(size: int, radius: int):
    image = master.resize((size, size), Image.Resampling.LANCZOS)
    mask = Image.new('L', (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size-1, size-1), radius, fill=255)
    image.putalpha(mask)
    return image

assets = root / 'frontend/assets'
docs = root / 'docs/assets'
assets.mkdir(parents=True, exist_ok=True)
docs.mkdir(parents=True, exist_ok=True)
rounded(256, 56).save(assets / 'cinna-icon.png')
for size in (16,32,48):
    rounded(size, round(size*112/512)).save(assets / f'favicon-{size}.png')
rounded(180,39).save(assets / 'apple-touch-icon.png')
rounded(512, 112).save(docs / 'icon.png')
rounded(1024, 224).save(root / 'resources/app.ico', sizes=[(16,16),(20,20),(24,24),(32,32),(40,40),(48,48),(64,64),(96,96),(128,128),(256,256)])
sidebar=Image.new('RGB',(164,314),'#FFFCF6')
sidebar_icon=rounded(148,32)
sidebar.paste(sidebar_icon,(8,58),sidebar_icon)
sidebar.save(root/'resources/installer-sidebar.bmp')
header=Image.new('RGB',(150,57),'#FFFCF6')
header_icon=rounded(48,11)
header.paste(header_icon,(98,4),header_icon)
header.save(root/'resources/installer-header.bmp')
exports=[root/'resources/app.ico',root/'resources/icon-master.png',root/'resources/installer-sidebar.bmp',root/'resources/installer-header.bmp',docs/'icon.png',assets/'cinna-icon.png',assets/'apple-touch-icon.png',*[assets/f'favicon-{size}.png' for size in (16,32,48)]]
manifest={'brandVersion':project['brand']['version'],'series':project['series'],'projectName':project['projectName'],'developer':project['developer'],'sourceSha256':hashlib.sha256(source.read_bytes()).hexdigest(),'files':{file.relative_to(root).as_posix():hashlib.sha256(file.read_bytes()).hexdigest() for file in exports}}
(root/'resources/brand/manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),'utf-8')
print('Cinna icon, Windows ICO and README image exported.')
