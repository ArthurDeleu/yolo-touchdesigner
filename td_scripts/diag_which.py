# Lists every yolo component in the project with the state that matters. Paste into the textport:
#   exec(open('/Users/arthurdeleu/Code/TDYolo/yolo-touchdesigner/td_scripts/diag_which.py').read())
import numpy as np
hits = [c for c in root.findChildren(type=COMP) if c.op('yolo_server/virtualFile') is not None]
print('%d yolo component(s):' % len(hits))
for y in hits:
    ws = y.op('yolo_server/webserver1')
    seg = y.op('segmentation_data')
    inst = y.op('seg_instances')
    wr = y.op('webrender1')
    a = seg.numpyArray()[..., 0] if seg is not None else None
    ids = (np.unique(np.floor(a[a > 0])).astype(int) - 1).tolist() if a is not None else []
    vis = None
    if inst is not None:
        o = inst.numpyArray(); vis = int((o[..., 3] > 0.05).sum())
    print('--- %s' % y.path)
    print('    receiver patched :', 'yes' if ws is not None and 'patched' in str(ws.par.callbacks.val) else 'NO')
    print('    seg TOP locked   :', seg.lock if seg is not None else '-', '| dev mode:', y.par.Dev.eval() if hasattr(y.par, 'Dev') else '-', '| input wired:', len(y.inputs))
    print('    map ids          :', ids[:8], '->', 'INSTANCE' if ids and min(ids) >= 100 else ('CLASS' if ids else 'empty'))
    print('    seg_instances    :', ('%d visible px' % vis) if vis is not None else 'missing', '| seg_mask:', 'present' if y.op('seg_mask') else 'missing')
    print('    webrender url    :', (wr.par.url.eval()[:60] + '...') if wr is not None else '-')
print('View seg_instances INSIDE the component that says "receiver patched: yes" and shows visible px.')
print('Two components each run a page and a model; keep one and delete the other when you are done comparing.')
