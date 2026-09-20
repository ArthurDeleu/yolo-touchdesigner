# Operator flags on the segmentation chain. Paste into the textport:
#   exec(open('/Users/arthurdeleu/Code/TDYolo/yolo-touchdesigner/td_scripts/diag_flags.py').read())
# A locked Script TOP ignores copyNumpyArray and keeps its last texture forever.
hits = [c for c in root.findChildren(type=COMP) if c.op('yolo_server/virtualFile') is not None]
yolo = hits[0]
for name in ('segmentation_data', 'flip2', 'seg_mask', 'seg_instances', 'webrender1'):
    o = yolo.op(name)
    if o is None:
        print('%-18s: missing' % name); continue
    print('%-18s: lock=%-5s bypass=%-5s cooking=%-5s errors=%s' % (name, o.lock, o.bypass, o.allowCooking, o.errors() or 'none'))
seg = yolo.op('segmentation_data')
if seg.lock:
    seg.lock = False
    print('-> segmentation_data was LOCKED. Unlocked it. The next map from the page will show; re-run diag_seg.py.')
elif seg.bypass:
    seg.bypass = False
    print('-> segmentation_data was BYPASSED. Cleared it.')
elif not seg.allowCooking:
    seg.allowCooking = True
    print('-> segmentation_data had cooking disabled. Re-enabled it.')
else:
    print('-> no lock/bypass/cook flag set on segmentation_data; the freeze is elsewhere.')
