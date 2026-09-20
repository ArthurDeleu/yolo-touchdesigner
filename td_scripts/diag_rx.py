# Tests TouchDesigner's binary receive path in isolation. Paste into the textport:
#   exec(open('/Users/arthurdeleu/Code/TDYolo/yolo-touchdesigner/td_scripts/diag_rx.py').read())
# 1. feeds a synthetic 160x160 map (all texels = 777.5) straight into onWebSocketReceiveBinary
#    and checks 1 s later whether segmentation_data now holds it -> proves/disproves the copy path
# 2. wraps onWebSocketReceiveBinary with a counter and prints, 5 s later, how many binary
#    messages the page delivered and the header of the first one
import struct
import numpy as np

hits = [c for c in root.findChildren(type=COMP) if c.op('yolo_server/virtualFile') is not None]
yolo = hits[0]
srv = yolo.op('yolo_server')
cb = srv.op('webserver_callbacks')
m = cb.module
ws = srv.op('webserver1')
seg = yolo.op('segmentation_data')

print('callbacks DAT   :', cb.path)
print('has rx binary   :', hasattr(m, 'onWebSocketReceiveBinary'), '| module seg ref:', getattr(m, 'segmentation_data', '(no attr)'))
print('consts          : type=%s dtype=%s layout=%s ver=%s hdr=%s' % tuple(getattr(m, k, '?') for k in ('TYPE_SEGMENTATION', 'DTYPE_FLOAT32', 'LAYOUT_HW', 'PROTOCOL_VERSION', 'BINARY_HEADER_BYTES')))
print('seg TOP         :', seg.path, seg.width, seg.height, seg.pixelFormat, '| callbacks par:', seg.par.callbacks.eval() if hasattr(seg.par, 'callbacks') else '(none)')
sdc = op(seg.par.callbacks.eval()) if hasattr(seg.par, 'callbacks') and seg.par.callbacks.eval() else None
if sdc is not None:
    print('--- Script TOP callbacks DAT (first 25 lines) ---')
    print('\n'.join(sdc.text.splitlines()[:25]))
    print('--- end ---')

# 1. synthetic injection
h = w = 160
hdr = struct.pack('<BBBBHHII', 11, 2, 2, 1, h, w, 1, 1)
body = np.full((h, w), 777.5, dtype='<f4').tobytes()
client = srv.op('active_client').text.strip()
before = float(seg.numpyArray()[..., 0].mean())
try:
    m.onWebSocketReceiveBinary(ws, client, hdr + body)
    print('inject          : called onWebSocketReceiveBinary with a 777.5 map, no exception')
except Exception as e:
    print('inject          : RAISED', repr(e))
yolo.store('diag_rx_before', before)
run(f'''
import numpy as np
y = op({yolo.path!r}); a = op({seg.path!r}).numpyArray()[..., 0]
print("inject result   : mean before %.3f, after %.3f -> %s" % (y.fetch("diag_rx_before"), float(a.mean()),
      "COPY PATH WORKS (TOP took the synthetic map)" if abs(float(a.mean()) - 777.5) < 1 else "COPY PATH BROKEN: TOP did not take the injected map"))
''', delayMilliSeconds=1000)

# 2. count what the page delivers
if not yolo.fetch('diag_rx_wrapped', False):
    _orig = m.onWebSocketReceiveBinary
    def _counted(webServerDAT, client, data, _orig=_orig, _y=yolo):
        n = _y.fetch('diag_rx_count', 0) + 1
        _y.store('diag_rx_count', n)
        if n == 1:
            try:
                t, d, l, v, hh, ww, s, f = struct.unpack_from('<BBBBHHII', data, 0)
                print('first page binary: type=%d dtype=%d layout=%d ver=%d %dx%d bytes=%d' % (t, d, l, v, ww, hh, len(data)))
            except Exception as e:
                print('first page binary: header unpack failed', e, len(data))
        try:
            return _orig(webServerDAT, client, data)
        except Exception as e:
            print('rx handler RAISED:', repr(e))
            raise
    m.onWebSocketReceiveBinary = _counted
    yolo.store('diag_rx_wrapped', True)
    yolo.store('diag_rx_count', 0)
    print('wrapper         : installed on onWebSocketReceiveBinary')
run(f'''
y = op({yolo.path!r})
print("page binaries   : %d received by TD in 5 s (0 = maps never reach TD, or TD does not dispatch to the patched function)" % y.fetch("diag_rx_count", 0))
''', delayMilliSeconds=5000)
print('(two more lines follow, after 1 s and 5 s)')
