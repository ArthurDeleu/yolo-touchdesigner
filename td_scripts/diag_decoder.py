# Checks the TD-side decode chain segmentation_data -> flip2 -> seg_instances / seg_mask.
# Paste into the textport:
#   exec(open('/Users/arthurdeleu/Code/TDYolo/yolo-touchdesigner/td_scripts/diag_decoder.py').read())
# The packed value (id + 1 + alpha*0.99) needs 32-bit float all the way: in 16-bit float
# the alpha fraction is lost above id ~1000 (ulp = 1.0) and the output goes black.
import numpy as np
hits = [c for c in root.findChildren(type=COMP) if c.op('yolo_server/virtualFile') is not None]
yolo = hits[0]

def show(o):
    if o is None: return 'missing'
    ins = [i.path for i in o.inputs]
    return '%-16s %4dx%-4d %-26s <- %s' % (o.name, o.width, o.height, o.pixelFormat, ins or '(no input)')

seg  = yolo.op('segmentation_data')
flip = yolo.op('flip2')
inst = yolo.op('seg_instances')
mask = yolo.op('seg_mask')
for o in (seg, flip, inst, mask):
    print('chain           :', show(o))

# fix the intermediate format if it is anything but 32-bit float
if flip is not None and '32-bit' not in flip.pixelFormat:
    try:
        flip.par.format = 'rgba32float'
        flip.cook(force=True)
        print('fix             : flip2 pixel format -> 32-bit float (was losing the alpha fraction)')
    except Exception as e:
        print('fix             : could not set flip2 format:', e)
else:
    print('flip2 format    : already 32-bit float' if flip is not None else 'flip2 missing')

# what reaches the decoder, and what it produces
if flip is not None:
    a = flip.numpyArray()[..., 0]
    ids = np.unique(np.floor(a[a > 0])).astype(int)
    frac = a[a > 0] - np.floor(a[a > 0])
    print('decoder input   : ids %s | alpha fraction range %.3f..%.3f (0..0 means precision lost)' % ((ids - 1).tolist()[:8], float(frac.min()) if frac.size else 0, float(frac.max()) if frac.size else 0))
if inst is not None:
    inst.cook(force=True)
    o = inst.numpyArray()
    print('seg_instances   : %d of %d pixels have alpha > 0.05 | errors: %s' % (int((o[..., 3] > 0.05).sum()), o.shape[0] * o.shape[1], inst.errors() or 'none'))
