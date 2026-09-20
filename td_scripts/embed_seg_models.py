# Paste into the TouchDesigner Textport (or run from a Script DAT) with yolo.tox
# loaded in the project. Ships the YOLO11 segmentation models inside the .tox:
#   1. copies the .onnx files into the yolo_server VFS
#   2. swaps the built web bundle (dist/assets/*) for the one you just built
#   3. extends the "Segmentation Model" menu
# Then save the .tox (right-click yolo > Save Component .tox).
#
# Prereq on the shell side, from the repo root:
#   npm i && npm run build
#
# Quick test WITHOUT embedding: run `npm run dev`, turn on About > Dev in the
# .tox, and pick the model from the menu -- Dev mode loads the page from the
# Vite dev server (localhost:5173), which serves public/models directly.

import os


def _find_yolo(preferred):
    """The yolo component wherever it sits in this project: the preferred path if it
    exists, otherwise the first COMP anywhere that contains yolo_server/virtualFile."""
    o = op(preferred)
    if o is not None and o.op('yolo_server/virtualFile') is not None:
        return o
    hits = [c for c in root.findChildren(type=COMP) if c.op('yolo_server/virtualFile') is not None]
    if len(hits) > 1:
        print('[find] several yolo components, using the first:', [h.path for h in hits])
    if hits:
        print('[find] yolo component at', hits[0].path)
        return hits[0]
    raise RuntimeError('no yolo component found (nothing contains yolo_server/virtualFile); '
                       'is yolo.tox loaded in this project?')

YOLO = _find_yolo('/project1/yolo')                              # searched for if not at this path
REPO = '/Users/arthurdeleu/Code/TDYolo/yolo-touchdesigner'         # <- this checkout

SEG_MODELS = [
    # (menu value == file stem, menu label)
    ('yolo26n-seg', 'Yolo26 Nano'),
    ('yolo11n-seg', 'Yolo11 Nano'),
    ('yolo11s-seg', 'Yolo11 Small'),
    ('yolo11m-seg', 'Yolo11 Medium'),
]

vfs = YOLO.op('yolo_server/virtualFile').vfs

def _replace(path):
    name = os.path.basename(path)
    for old in vfs.find(pattern=name):
        old.destroy()
    vfs.addFile(path)
    print('[embed] added', name, os.path.getsize(path) // (1 << 20), 'MB')

# 1. models (skip yolo26n-seg: already in the VFS)
for stem, _ in SEG_MODELS:
    path = os.path.join(REPO, 'public', 'models', stem + '.onnx')
    if os.path.exists(path):
        _replace(path)
    else:
        print('[embed] missing on disk, skipped:', path)

# 2. rebuilt bundle: drop the stale hashed assets, add the fresh ones
dist_assets = os.path.join(REPO, 'dist', 'assets')
if os.path.isdir(dist_assets):
    for old in vfs.find(pattern='index-*'):
        old.destroy()
    for fn in os.listdir(dist_assets):
        _replace(os.path.join(dist_assets, fn))
    # index.html is served from the `index_html` textDAT (file = dist/index.html,
    # sync on); repoint + reload so the hashed <script src> matches the new bundle.
    idx = YOLO.op('index_html')
    idx.par.file = os.path.join(REPO, 'dist', 'index.html')
    try:
        idx.par.loadonstartpulse.pulse()
    except Exception:
        pass
else:
    print('[embed] no dist/assets -- run `npm run build` first; bundle left unchanged')

# 3. menu
p = YOLO.par.Segmentationmodel
p.menuNames = [s for s, _ in SEG_MODELS]
p.menuLabels = [l for _, l in SEG_MODELS]
print('[embed] Segmentation Model menu:', p.menuNames)
