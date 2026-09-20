# Exercises TouchDesigner's binary frame sender step by step, synchronously,
# bypassing the ThreadManager path. Paste into the textport:
#   exec(open('/Users/arthurdeleu/Code/TDYolo/yolo-touchdesigner/td_scripts/diag_sender.py').read())
# Then re-run diag_seg.py: a BROWSER ERROR line reading info:first-frame-accepted
# proves the page is fine and the threaded sender is what never delivers.

hits = [c for c in root.findChildren(type=COMP) if c.op('yolo_server/virtualFile') is not None]
assert hits, 'no yolo component in this project'
yolo = hits[0]
snd = yolo.op('chopexec3')
assert snd is not None, 'chopexec3 (frame sender) not found in ' + yolo.path
m = snd.module
print('sender DAT      :', snd.path)

# 1. thread machinery
try:
    cls = m._get_td_task_class()
    print('TDTask class    :', cls)
except Exception as e:
    print('TDTask lookup   : RAISED', repr(e))

# 2. source TOP and its shape
top = m.top
print('source TOP      :', top.path if top else None, '|', (top.width, top.height, top.pixelFormat) if top else '')
a = top.numpyArray(delayed=False) if top else None
print('numpy shape     :', None if a is None else (a.shape, a.dtype))

# 3. pack
rc = {'success': False, 'payload': None, 'h_final': 0, 'w_final': 0, 'error': None}
if a is not None:
    m._repack_task_fn(a.copy(), a.shape[0], a.shape[1], a.shape[2], rc)
print('repack          :', 'ok' if rc['success'] else 'FAILED', '| h,w =', rc['h_final'], rc['w_final'], '| bytes =', None if rc['payload'] is None else rc['payload'].nbytes, '| error =', rc['error'])

# 4. client + send, synchronously
client = m.client_op.text.strip()
print('active client   :', repr(client))
print('busy before     :', m.webserver.fetch('busy', None))
if rc['success'] and client:
    m.webserver.store('busy', False)
    m._send_payload(client, m.webserver, rc['payload'], rc['h_final'], rc['w_final'], 1)
    print('sent            : one frame, synchronously. Now re-run diag_seg.py and read the BROWSER ERROR line.')
else:
    print('sent            : nothing (repack failed or no client)')
