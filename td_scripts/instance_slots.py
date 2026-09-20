# Script CHOP callbacks: maps tracked instance ids in segmentation_data to a fixed set of
# slots, so each person lands on a stable channel downstream. Output channels:
#   slot0..slot{N-1}  packed id occupying the slot, or -1 when free
#   count             number of occupied slots
#   slot{k}_x/_y      centroid of that slot's mask, normalised 0..1 (bottom-left origin)
#
# Why a second tracker: the page's IoU tracker gives ids that are stable frame to frame
# but arbitrary and ever increasing. Effects want "person 1 / person 2". This table is
# the translation, with two kinds of memory the page cannot provide:
#   HOLD_FRAMES   keep a slot reserved after its id disappears (occlusion, dropped frame)
#   REACQUIRE_R   a new id whose centroid is within this radius (in map pixels) of a
#                 held slot's last centroid inherits that slot instead of taking a new one
import numpy as np

N_SLOTS      = 8      # slots 0-3 -> seg_mask RGBA, slots 4-7 -> seg_mask2 RGBA
HOLD_FRAMES  = 45     # ~0.75 s at 60 fps
REACQUIRE_R  = 24.0   # map pixels (map is 160 wide -> 15% of the frame)
MIN_PIXELS   = 12     # ignore fragments smaller than this

def onSetupParameters(scriptOp):
    return

def onPulse(par):
    return

def _state(scriptOp):
    st = scriptOp.fetch('slots_state', None)
    if st is None or len(st['id']) != N_SLOTS:
        st = {'id': [None] * N_SLOTS, 'miss': [0] * N_SLOTS, 'cx': [0.0] * N_SLOTS, 'cy': [0.0] * N_SLOTS}
    return st

def onCook(scriptOp):
    seg = scriptOp.parent().op('segmentation_data')   # sibling of the Script CHOP, wherever this DAT sits
    st = _state(scriptOp)
    a = seg.numpyArray()[..., 0] if seg is not None else None
    H, W = (a.shape if a is not None else (1, 1))

    # ids present this frame, with pixel count and centroid
    present = {}
    if a is not None:
        m = a > 0
        if m.any():
            ids_img = (np.floor(a) - 1).astype(np.int32)
            ys, xs = np.nonzero(m)
            vals = ids_img[ys, xs]
            for pid in np.unique(vals):
                sel = vals == pid
                n = int(sel.sum())
                if n >= MIN_PIXELS:
                    present[int(pid)] = (n, float(xs[sel].mean()), float(ys[sel].mean()))

    # 1. age existing slots; refresh the ones still present
    for k in range(N_SLOTS):
        pid = st['id'][k]
        if pid is None:
            continue
        if pid in present:
            st['miss'][k] = 0
            st['cx'][k], st['cy'][k] = present[pid][1], present[pid][2]
        else:
            st['miss'][k] += 1
            if st['miss'][k] > HOLD_FRAMES:
                st['id'][k] = None

    # 2. new ids: largest first, re-acquire a held slot nearby, else lowest free slot
    assigned = set(p for p in st['id'] if p is not None)
    for pid, (n, cx, cy) in sorted(present.items(), key=lambda kv: -kv[1][0]):
        if pid in assigned:
            continue
        best, best_d = None, REACQUIRE_R
        for k in range(N_SLOTS):
            if st['id'][k] is not None and st['miss'][k] > 0:      # held, not seen this frame
                d = ((st['cx'][k] - cx) ** 2 + (st['cy'][k] - cy) ** 2) ** 0.5
                if d < best_d:
                    best, best_d = k, d
        if best is None:
            free = [k for k in range(N_SLOTS) if st['id'][k] is None]
            if not free:
                continue                                              # more people than slots
            best = free[0]
        st['id'][best], st['miss'][best], st['cx'][best], st['cy'][best] = pid, 0, cx, cy
        assigned.add(pid)

    scriptOp.store('slots_state', st)

    # 3. output
    scriptOp.clear()
    scriptOp.numSamples = 1
    for k in range(N_SLOTS):
        scriptOp.appendChan('slot%d' % k)[0] = -1 if st['id'][k] is None else st['id'][k]
    scriptOp.appendChan('count')[0] = sum(1 for p in st['id'] if p is not None)
    for k in range(N_SLOTS):
        scriptOp.appendChan('slot%d_x' % k)[0] = st['cx'][k] / max(W - 1, 1)
        scriptOp.appendChan('slot%d_y' % k)[0] = 1.0 - st['cy'][k] / max(H - 1, 1)   # numpy row 0 = top
    return
