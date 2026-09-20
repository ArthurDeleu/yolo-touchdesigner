# Fixes the float-map receive path for TouchDesigner builds where copyNumpyArray on a
# locked Script TOP silently does nothing (seen on 2025.33230). Paste into the textport:
#   exec(open('/Users/arthurdeleu/Code/TDYolo/yolo-touchdesigner/td_scripts/patch_seg_receiver.py').read())
#
# Before: yolo_server/webserver_callbacks._copy_float_map calls target.copyNumpyArray(arr)
#         from the websocket callback, relying on the Script TOP being locked.
# After : it stores the array on the Script TOP under 'pending_map' and force-cooks it;
#         the Script TOP's callbacks DAT copies it in from onCook, the documented context.
# Applies to segmentation_data and depth_data. Re-runnable. Persist with the tox save.
import re

hits = [c for c in root.findChildren(type=COMP) if c.op('yolo_server/virtualFile') is not None]
assert hits, 'no yolo component in this project'
yolo = hits[0]
cb = yolo.op('yolo_server/webserver_callbacks')
assert cb is not None, 'webserver_callbacks DAT not found'

def make_editable(dat):
    # "The operator is not editable" comes from a locked DAT or one synced to a file.
    # Embed the text (drop the file link) and unlock, reporting what was found.
    flags = []
    if dat.lock:
        dat.lock = False; flags.append('lock')
    f = dat.par.file.eval() if hasattr(dat.par, 'file') else ''
    if hasattr(dat.par, 'syncfile') and dat.par.syncfile.eval():
        dat.par.syncfile = False; flags.append('syncfile(%s)' % f)
    if f:
        dat.par.file = ''; flags.append('file cleared')
    print('[patch] %s: %s' % (dat.name, ('cleared ' + ', '.join(flags)) if flags else 'no lock/sync flags'))

def set_text(dat, text):
    make_editable(dat)
    try:
        dat.text = text
    except Exception as e:
        print('[patch] %s: STILL not editable (%s). lock=%s syncfile=%s file=%r' % (
            dat.name, e, dat.lock, getattr(dat.par, 'syncfile', None) and dat.par.syncfile.eval(),
            getattr(dat.par, 'file', None) and dat.par.file.eval()))
        raise

def resolve_source(dat):
    """Follow Null/Select/In DATs back to the Text DAT that actually holds the script."""
    chain, seen = [], set()
    while dat is not None and dat.path not in seen:
        seen.add(dat.path); chain.append('%s(%s)' % (dat.name, dat.OPType))
        if isinstance(dat, textDAT):
            return dat, chain
        nxt = None
        if hasattr(dat.par, 'dat') and dat.par.dat.eval():
            nxt = dat.par.dat.eval()          # selectDAT
        elif dat.inputs:
            nxt = dat.inputs[0]               # nullDAT / inDAT etc.
        dat = nxt
    return None, chain

src, chain = resolve_source(cb)
print('[patch] callbacks chain:', ' <- '.join(chain), '| editable source:', src.path if src else 'NONE')
ws = yolo.op('yolo_server/webserver1')
if src is None:
    # No editable source: give the web server its own Text DAT with the same code, patched.
    src = yolo.op('yolo_server/webserver_callbacks_patched') or yolo.op('yolo_server').create(textDAT, 'webserver_callbacks_patched')
    src.nodeX, src.nodeY = cb.nodeX, cb.nodeY - 120
    if not src.text.strip():
        src.text = cb.text
    ws.par.callbacks = src.name
    print('[patch] webserver1.par.callbacks -> %s (replacement Text DAT)' % src.path)
cb = src

# 1. receive callback: store + cook instead of a direct copy
txt = cb.text
if "target.store('pending_map'" in txt:
    print('[patch] webserver_callbacks already patched')
else:
    m = re.search(r'^([ \t]*)target\.copyNumpyArray\(arr\)[ \t]*$', txt, flags=re.M)
    assert m, 'could not find target.copyNumpyArray(arr) in webserver_callbacks'
    ind = m.group(1)
    new = (
        f"{ind}# TD 2025+: copyNumpyArray outside onCook only works on a locked op, and a locked\n"
        f"{ind}# Script TOP never refreshes its output. Hand the array over and cook the op so the\n"
        f"{ind}# copy happens inside its onCook (see the Script TOP's callbacks DAT).\n"
        f"{ind}target.store('pending_map', arr.copy())\n"
        f"{ind}target.cook(force=True)"
    )
    set_text(cb, txt[:m.start()] + new + txt[m.end():])
    print('[patch] webserver_callbacks: _copy_float_map now stores + cooks')

# 2. Script TOP callbacks: copy from onCook
ONCOOK = '''# Callbacks for the float-map Script TOPs (segmentation_data / depth_data).
# The websocket receive callback stores the newest map under 'pending_map' and
# force-cooks this operator; copyNumpyArray is only legal here, inside onCook.

def onSetupParameters(scriptOp):
	return

def onPulse(par):
	return

def onCook(scriptOp):
	a = scriptOp.fetch('pending_map', None)
	if a is not None:
		scriptOp.copyNumpyArray(a)
	return
'''
done = set()
for name in ('segmentation_data', 'depth_data'):
    top = yolo.op(name)
    if top is None:
        print('[patch] %s: not present, skipped' % name); continue
    if top.lock:
        top.lock = False
        print('[patch] %s: unlocked' % name)
    dat = op(top.par.callbacks.eval()) if top.par.callbacks.eval() else None
    if dat is None:
        dat = yolo.create(textDAT, name + '_callbacks')
        dat.nodeX, dat.nodeY = top.nodeX, top.nodeY - 120
        top.par.callbacks = dat.name
        print('[patch] %s: created callbacks DAT %s' % (name, dat.path))
    if dat is not None and not isinstance(dat, textDAT):
        s2, ch2 = resolve_source(dat)
        print('[patch] %s: callbacks chain %s -> %s' % (name, ' <- '.join(ch2), s2.path if s2 else 'NONE'))
        if s2 is None:
            s2 = yolo.create(textDAT, name + '_callbacks')
            s2.nodeX, s2.nodeY = top.nodeX, top.nodeY - 120
            top.par.callbacks = s2.name
            print('[patch] %s: callbacks -> new Text DAT %s' % (name, s2.path))
        dat = s2
    if dat.path not in done:
        if "fetch('pending_map'" in dat.text:
            print('[patch] %s: callbacks DAT %s already patched' % (name, dat.name))
        else:
            set_text(dat, ONCOOK)
            print('[patch] %s: callbacks DAT %s rewritten (onCook copies pending_map)' % (name, dat.name))
        done.add(dat.path)

print('[patch] done. Maps from the page should now land within a second; run diag_seg.py to confirm.')
print('[patch] persist:  op(%r).save(%r)' % (yolo.path, yolo.par.externaltox.eval() if hasattr(yolo.par, 'externaltox') else '<path to yolo.tox>'))
