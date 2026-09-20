# Segmentation pipeline diagnostic. Paste into the TouchDesigner textport:
#   exec(open('/Users/arthurdeleu/Code/TDYolo/yolo-touchdesigner/td_scripts/diag_seg.py').read())
# Answers, from the live project: which bundle is served, which one the browser
# loaded, and whether the packed map carries class ids (all persons = 0) or
# tracked instance ids (>= 1, one per body).
import os, re
import numpy as np

REPO = '/Users/arthurdeleu/Code/TDYolo/yolo-touchdesigner'

hits = [c for c in root.findChildren(type=COMP) if c.op('yolo_server/virtualFile') is not None]
assert hits, 'no yolo component in this project'
yolo = hits[0]
print('yolo component  :', yolo.path)

# 1. what is on disk vs in the VFS vs in the served index.html
disk = sorted(f for f in os.listdir(os.path.join(REPO, 'dist', 'assets')) if f.startswith('index-'))
vfs  = sorted(f.name for f in yolo.op('yolo_server/virtualFile').vfs.find(pattern='index-*'))
html = yolo.op('index_html').text
served = re.findall(r'index-[\w-]+\.js', html)
print('dist/assets     :', disk)
print('VFS             :', vfs)
print('index.html refs :', served, '  (file par:', yolo.op('index_html').par.file.eval(), ')')
ok = bool(served) and all(s in vfs for s in served) and all(s in disk for s in served)
print('bundle chain    :', 'CONSISTENT' if ok else 'BROKEN -> re-run embed_seg_models.py')

# 2. what the browser actually loaded
wr = yolo.op('webrender1')
if wr is not None:
    print('webrender url   :', wr.par.url.eval())
    print('dev mode par    :', yolo.par.Dev.eval() if hasattr(yolo.par, 'Dev') else '(no Dev par)')
    print('=> pulse yolo.par.Reset (Server page) after any embed; Chromium caches the old page.')

# 3. what the packed map contains right now
seg = yolo.op('segmentation_data')
a = seg.numpyArray()[..., 0]
ints = np.unique(np.floor(a[a > 0])).astype(int)
print('map resolution  :', seg.width, 'x', seg.height, seg.pixelFormat)
print('integer ids seen:', ints.tolist(), '-> packed ids', (ints - 1).tolist())
COCO = ['person', 'bicycle', 'car', 'motorcycle', 'airplane', 'bus', 'train', 'truck', 'boat', 'traffic light', 'fire hydrant', 'stop sign', 'parking meter', 'bench', 'bird', 'cat', 'dog', 'horse', 'sheep', 'cow', 'elephant', 'bear', 'zebra', 'giraffe', 'backpack', 'umbrella', 'handbag', 'tie', 'suitcase', 'frisbee', 'skis', 'snowboard', 'sports ball', 'kite', 'baseball bat', 'baseball glove', 'skateboard', 'surfboard', 'tennis racket', 'bottle', 'wine glass', 'cup', 'fork', 'knife', 'spoon', 'bowl', 'banana', 'apple', 'sandwich', 'orange', 'broccoli', 'carrot', 'hot dog', 'pizza', 'donut', 'cake', 'chair', 'couch', 'potted plant', 'bed', 'dining table', 'toilet', 'tv', 'laptop', 'mouse', 'remote', 'keyboard', 'cell phone', 'microwave', 'oven', 'toaster', 'sink', 'refrigerator', 'book', 'clock', 'vase', 'scissors', 'teddy bear', 'hair drier', 'toothbrush']
packed = (ints - 1).tolist()
# Instance ids are packed at >= 100 (SEG_ID_BASE); COCO class ids are 0..79. Disjoint by design.
if len(ints) == 0:
    print('verdict         : nobody in frame (or seg disabled)')
elif max(packed) < 100:
    names = [COCO[i] if 0 <= i < len(COCO) else '?%d' % i for i in packed]
    print('verdict         : CLASS packing ->', names)
    print('                  browser is on the old page: pulse yolo.par.Reset, then re-run this.')
    print('                  (also consider Personsegonly=1 unless you want cups and chairs masked)')
else:
    print('verdict         : INSTANCE packing, %d tracked bodies right now' % sum(1 for i in packed if i >= 100))
    if any(i < 100 for i in packed):
        print('                  (plus class-range ids %r: stale pixels or a mixed frame)' % [i for i in packed if i < 100])

# 4. decoders present
for n in ('seg_mask', 'seg_instances'):
    o = yolo.op(n)
    print('%-15s :' % n, (o.path + ('  errors: ' + o.errors() if o.errors() else '  ok')) if o else 'missing -> run build_seg_mask.py')

# 5. webrender state
if wr is not None:
    print('webrender err   :', wr.errors() or 'none', '| warnings:', wr.warnings() or 'none')
    print('webrender active:', wr.par.active.eval())
ws = yolo.op('yolo_server/webserver1')
try:
    print('ws clients      :', len(ws.webSocketConnections), ws.webSocketConnections)
except Exception as e:
    print('ws clients      : (not readable:', e, ')')

# 5a. does ANY text flow between page and TD? The callbacks fill these DATs.
srv = yolo.op('yolo_server')
def _t(name, n=120):
    o = srv.op(name) if srv else None
    return ('(missing)' if o is None else (o.text.strip()[:n] or '(empty)'))
print('webcam_list DAT :', _t('webcam_list'))                 # page -> TD at socket open
print('tick DAT        :', _t('tick'), '| TD frame now:', int(absTime.frame))   # page's reply to TD sync
print('status DAT      :', _t('status'))
print('predictions DAT :', _t('predictions', 200))
cb = srv.op('webserver_callbacks') if srv else None
print('callbacks route :', ('has predictions.text=data' if cb is not None and 'predictions.text = data' in cb.text else 'UNEXPECTED callback text'), '| busy:', srv.op('webserver1').fetch('busy', None) if srv else None)

# 5b. reports from the page land in the status DAT (see src/utils/report.js)
st = srv.op('status') if srv else None
if st is not None and '"report":true' in st.text:
    import json as _json
    try:
        for r in _json.loads(st.text).get('reports', []):
            print('PAGE REPORT     : [%s] %s | %s' % (r.get('at'), r.get('where'), r.get('message')))
            if r.get('stack') and not str(r.get('where', '')).startswith('info:'):
                print('                  ' + r['stack'][:300].replace(chr(10), chr(10) + ' ' * 18))
    except Exception as e:
        print('PAGE REPORT     : (raw)', st.text[:1500], e)
else:
    print('page report     : none (status DAT holds: %s)' % (st.text.strip()[:80] if st is not None else '(missing)'))

# 6. liveness: is the map changing at all? A dead page leaves the Script TOP
# holding its last frame forever, which looks exactly like a live static scene.
yolo.store('diag_seg_snap', a.copy())
# run() executes later in a fresh namespace, so the recheck must be self-contained:
# it reaches the snapshot through the component's storage, not through this scope.
run(f'''
import numpy as np
y = op({yolo.path!r}); b = op({seg.path!r}).numpyArray()[..., 0]
changed = int(np.count_nonzero(b != y.fetch("diag_seg_snap")))
if changed == 0:
    print("map liveness    : FROZEN (0 pixels changed in 1.5 s). Either the page is not sending frames, or the INPUT IS STILL: a paused video or an empty room gives an identical map every frame. Make sure something moves in frame before reading this as a fault.")
    print("                  next: Segmentationmodel=yolo11n-seg to rule out warmup; still frozen -> Dev mode + npm run dev, re-run diag for BROWSER ERROR")
else:
    print("map liveness    : LIVE (%d pixels changed in 1.5 s)" % changed)
y.unstore("diag_seg_snap")
''', delayMilliSeconds=1500)
print('(liveness result follows in 1.5 s)')
