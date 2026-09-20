# Rebuilds the segmentation mask decoders inside the yolo component.
#
# Two decoders read the same packed float map from segmentation_data:
#   seg_mask       per-class RGBA split      (unpack_seg_pixel.glsl)      -> web app SEG_PACK_MODE=class
#   seg_instances  per-body colour, no cap   (unpack_seg_instances.glsl)  -> web app SEG_PACK_MODE=instance (default)
# The web app decides what the integer part of each texel means (class id vs tracked
# instance id), so only the decoder matching the app's mode produces sensible output.
#
# Run from TouchDesigner: paste into a Text DAT and right-click -> Run Script,
# or in the textport:  exec(open('/Users/arthurdeleu/Code/TDYolo/yolo-touchdesigner/td_scripts/build_seg_mask.py').read())
#
# Creates (or updates, re-runnable):
#   <yolo>/flip2      Flip TOP    (reused from the stock tox; seg_flip is created only if it is missing)
#   <yolo>/seg_pixel  Text DAT    (shader text, embedded; not synced to a file)
#   <yolo>/seg_mask   GLSL Multi TOP, pixel mode, 2D texture output, all uniforms bound
#   <yolo>/seg_inst_pixel  Text DAT   (instance shader text, embedded)
#   <yolo>/seg_instances   GLSL Multi TOP, same layout, colours each tracked body
#   <yolo>/instance_slots  Script CHOP: instance id -> slot table (slot0..7, count, centroids)
#   <yolo>/seg_mask2       GLSL Multi TOP: slots 4-7 as RGBA (seg_mask now carries slots 0-3)
#   <yolo>/seg_layers      GLSL TOP (compute) -> 2D texture array, layer k = person in slot k; Out TOP 'layers'
#
# Then PERSIST the work (see the notes at the bottom): either turn off
# "Reload .tox on Start" on the yolo component, or save the component back to its .tox.

YOLO_PATH   = '/project1/yolo'
SHADER_PATH = '/Users/arthurdeleu/Code/TDYolo/yolo-touchdesigner/td_scripts/unpack_seg_pixel.glsl'
INST_SHADER_PATH = '/Users/arthurdeleu/Code/TDYolo/yolo-touchdesigner/td_scripts/unpack_seg_instances.glsl'
OUT_W, OUT_H = 1280, 1280
CLASSES = (0, 2, 15, 16)          # R=person G=car B=cat A=dog; -1 = channel off
THRESHOLD, SOFTNESS = 0.5, 1.0    # softness 0 = raw bicubic alpha
PALETTE = (0.0, 0.85, 1.0, 0.0)   # hue offset, saturation, value, hue step (0 = golden ratio)
SLOTS_PATH = '/Users/arthurdeleu/Code/TDYolo/yolo-touchdesigner/td_scripts/instance_slots.py'
LAYERS_SHADER_PATH = '/Users/arthurdeleu/Code/TDYolo/yolo-touchdesigner/td_scripts/unpack_seg_slots_layers.glsl'
N_LAYERS = 8
LAYER_RES = 640
PICK_SHADER_PATH = '/Users/arthurdeleu/Code/TDYolo/yolo-touchdesigner/td_scripts/pick_layer.glsl'


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

yolo = _find_yolo(YOLO_PATH)

src = yolo.op('segmentation_data')
assert src is not None, 'segmentation_data Script TOP not found inside ' + YOLO_PATH

def get_or_create(parent, optype, name):
    o = parent.op(name)
    if o is None:
        o = parent.create(optype, name)
    return o

# --- Flip TOP -------------------------------------------------------------
# The stock yolo.tox already ships `flip2` on segmentation_data with the right
# orientation. Reuse it; only create our own flip if it is missing.
flip = yolo.op('flip2')
if flip is None:
    flip = get_or_create(yolo, flipTOP, 'seg_flip')
    flip.par.flipy = True
    flip.inputConnectors[0].connect(src)
    flip.nodeX, flip.nodeY = src.nodeX + 200, src.nodeY

# --- shader DAT (embedded) --------------------------------------------------
dat = get_or_create(yolo, textDAT, 'seg_pixel')
dat.par.syncfile = False
dat.par.file = ''
with open(SHADER_PATH, 'r', encoding='utf-8') as fh:
    dat.text = fh.read()
dat.nodeX, dat.nodeY = flip.nodeX + 200, flip.nodeY - 150

# --- GLSL Multi TOP ---------------------------------------------------------
g = get_or_create(yolo, glslmultiTOP, 'seg_mask')
g.inputConnectors[0].connect(flip)
g.nodeX, g.nodeY = flip.nodeX + 200, flip.nodeY

g.par.mode      = 'vertexpixel'
g.par.pixeldat  = dat.name
g.par.vertexdat = ''
g.par.type      = 'texture2d'

g.par.outputresolution = 'custom'
g.par.resolutionw = OUT_W
g.par.resolutionh = OUT_H
try:
    g.par.format = 'rgba32float'
except Exception as e:
    print('pixel format not set (menu name differs?):', e)

def expr(par, e):
    par.mode = ParMode.EXPRESSION
    par.expr = e

g.par.uniname0 = 'uClasses'
for comp, val in zip('xyzw', CLASSES):
    p = getattr(g.par, 'value0' + comp)
    p.mode = ParMode.CONSTANT
    p.val = val

g.par.uniname1 = 'uInRes'
expr(g.par.value1x, 'me.inputs[0].width')
expr(g.par.value1y, 'me.inputs[0].height')

g.par.uniname2 = 'uOutRes'
expr(g.par.value2x, 'me.par.resolutionw')
expr(g.par.value2y, 'me.par.resolutionh')

g.par.uniname3 = 'uEdge'
g.par.value3x.mode = ParMode.CONSTANT; g.par.value3x = THRESHOLD
g.par.value3y.mode = ParMode.CONSTANT; g.par.value3y = SOFTNESS

# --- instance slot table -----------------------------------------------------
# A Script CHOP maps the page's instance ids to fixed slots (see instance_slots.py).
# seg_mask's four channels then follow slots 0-3 instead of fixed class ids, and a
# second copy, seg_mask2, follows slots 4-7. Each channel = one person's mask.
sdat = get_or_create(yolo, textDAT, 'instance_slots_callbacks')
sdat.par.syncfile = False
sdat.par.file = ''
with open(SLOTS_PATH, 'r', encoding='utf-8') as fh:
    sdat.text = fh.read()
schop = get_or_create(yolo, scriptCHOP, 'instance_slots')
schop.par.callbacks = sdat.name
schop.nodeX, schop.nodeY = src.nodeX, src.nodeY - 300
sdat.nodeX, sdat.nodeY = schop.nodeX, schop.nodeY - 120

def drive_slots(gtop, first_slot):
    for i, comp in enumerate('xyzw'):
        expr(getattr(gtop.par, 'value0' + comp), "op('instance_slots')['slot%d']" % (first_slot + i))

drive_slots(g, 0)
g2 = get_or_create(yolo, glslmultiTOP, 'seg_mask2')
g2.inputConnectors[0].connect(flip)
g2.nodeX, g2.nodeY = g.nodeX, g.nodeY + 150
for pname in ('mode', 'pixeldat', 'vertexdat', 'type', 'outputresolution', 'resolutionw', 'resolutionh', 'format',
              'uniname0', 'uniname1', 'uniname2', 'uniname3', 'value3x', 'value3y'):
    try:
        getattr(g2.par, pname).val = getattr(g.par, pname).val
    except Exception as e:
        print('seg_mask2 par', pname, e)
expr(g2.par.value1x, 'me.inputs[0].width');  expr(g2.par.value1y, 'me.inputs[0].height')
expr(g2.par.value2x, 'me.par.resolutionw');  expr(g2.par.value2y, 'me.par.resolutionh')
drive_slots(g2, 4)

g.cook(force=True)
g2.cook(force=True)
schop.cook(force=True)

# --- per-person texture array ------------------------------------------------
# One GLSL TOP (compute) -> 2D texture array, layer k = slot k. This is the output to
# instance from: Geometry COMP instances pick their layer by texture index.
ldat = get_or_create(yolo, textDAT, 'seg_layers_compute')
ldat.par.syncfile = False
ldat.par.file = ''
with open(LAYERS_SHADER_PATH, 'r', encoding='utf-8') as fh:
    ldat.text = fh.read()
gl = get_or_create(yolo, glslmultiTOP, 'seg_layers')
gl.inputConnectors[0].connect(flip)
gl.nodeX, gl.nodeY = g.nodeX, g.nodeY + 300
ldat.nodeX, ldat.nodeY = gl.nodeX, gl.nodeY - 150
def set_menu(par, *wanted):
    # pick a menu entry by substring; menu names differ between TD builds
    names = list(par.menuNames)
    for w in wanted:
        for n in names:
            if w.lower() in n.lower():
                par.val = n
                return n
    print('!! menu', par.owner.name + '.' + par.name, 'offers', names, '- nothing matched', wanted)
    return None

def set_par(o, pname, val):
    try:
        p = getattr(o.par, pname)
    except Exception:
        print('!!', o.name, 'has no parameter', pname, '- available:', [q.name for q in o.pars() if pname[:4] in q.name])
        return False
    try:
        p.val = val
        return True
    except Exception as e:
        print('!!', o.name + '.' + pname, '=', repr(val), 'failed:', e)
        return False

print('seg_layers mode  ->', set_menu(gl.par.mode, 'compute'))
for pname in ('computedat', 'computeshader', 'compute'):
    if hasattr(gl.par, pname):
        set_par(gl, pname, ldat.name); print('seg_layers shader par:', pname); break
else:
    print('!! no compute-shader DAT parameter found on GLSL TOP; pars:', [q.name for q in gl.pars() if 'dat' in q.name or 'comp' in q.name])
set_par(gl, 'pixeldat', '')
set_par(gl, 'vertexdat', '')
print('seg_layers type  ->', set_menu(gl.par.type, '2darray', 'array'))
if not set_par(gl, 'depth', N_LAYERS):
    for pname in ('outputdepth', 'arraydepth', 'layers'):
        if hasattr(gl.par, pname):
            set_par(gl, pname, N_LAYERS); break
if hasattr(gl.par, 'outputaccess'):
    set_menu(gl.par.outputaccess, 'writeonly', 'write')
if hasattr(gl.par, 'format'):
    set_menu(gl.par.format, 'r8fixed', 'mono8', 'r8')
gl.par.outputresolution = 'custom'
gl.par.resolutionw = LAYER_RES
gl.par.resolutionh = LAYER_RES
try:
    expr(gl.par.dispatchsizex, 'int(math.ceil(me.par.resolutionw / 8))')
    expr(gl.par.dispatchsizey, 'int(math.ceil(me.par.resolutionh / 8))')
    gl.par.dispatchsizez = 1
except Exception as e:
    print('seg_layers dispatch pars ->', e)
gl.par.uniname0 = 'uSlotsA'
for i, comp in enumerate('xyzw'):
    expr(getattr(gl.par, 'value0' + comp), "op('instance_slots')['slot%d']" % i)
gl.par.uniname1 = 'uSlotsB'
for i, comp in enumerate('xyzw'):
    expr(getattr(gl.par, 'value1' + comp), "op('instance_slots')['slot%d']" % (4 + i))
gl.par.uniname2 = 'uEdge'
gl.par.value2x.mode = ParMode.CONSTANT; gl.par.value2x = THRESHOLD
gl.par.value2y.mode = ParMode.CONSTANT; gl.par.value2y = SOFTNESS
ol = get_or_create(yolo, outTOP, 'out_layers')
ol.inputConnectors[0].connect(gl)
ol.nodeX, ol.nodeY = gl.nodeX + 200, gl.nodeY
ol.par.label = 'layers'
gl.cook(force=True)

# --- one output per person -------------------------------------------------------
# mask_slot{k}: person in slot k as a mono TOP (picked from the texture array), and
# out_person{k+1}: an Out TOP for it, so the component shows one connector per person.
# Out connectors are ordered by node position, top to bottom; these sit under the others.
pdat = get_or_create(yolo, textDAT, 'pick_layer_pixel')
pdat.par.syncfile = False
pdat.par.file = ''
with open(PICK_SHADER_PATH, 'r', encoding='utf-8') as fh:
    pdat.text = fh.read()
pdat.nodeX, pdat.nodeY = gl.nodeX + 200, gl.nodeY + 150
person_outs = []
for k in range(N_LAYERS):
    pk = get_or_create(yolo, glslmultiTOP, 'mask_slot%d' % k)
    pk.inputConnectors[0].connect(gl)
    pk.nodeX, pk.nodeY = gl.nodeX + 400, gl.nodeY - 130 * k
    pk.par.mode = 'vertexpixel'
    pk.par.pixeldat = pdat.name
    pk.par.vertexdat = ''
    pk.par.type = 'texture2d'
    pk.par.outputresolution = 'input'
    pk.par.uniname0 = 'uLayer'
    pk.par.value0x.mode = ParMode.CONSTANT; pk.par.value0x = k
    po = get_or_create(yolo, outTOP, 'out_person%d' % (k + 1))
    po.inputConnectors[0].connect(pk)
    po.nodeX, po.nodeY = pk.nodeX + 200, pk.nodeY
    po.par.label = 'person %d' % (k + 1)
    pk.cook(force=True)
    person_outs.append((pk, po))

# slot table out of the tox as a CHOP connector: slot0..7 (id or -1), count, slotN_x/_y
oc = get_or_create(yolo, outCHOP, 'out_slots')
oc.inputConnectors[0].connect(schop)
oc.nodeX, oc.nodeY = schop.nodeX + 200, schop.nodeY
oc.par.label = 'slots'

print('--- seg_mask build ---')
print('slots out:', oc.path, '(CHOP connector "slots")')
bad = [pk.name + ': ' + pk.errors() for pk, _ in person_outs if pk.errors()]
print('persons :', ', '.join(po.par.label.eval() for _, po in person_outs), '| errors:', bad or 'none')
print('layers  :', gl.path, gl.width, gl.height, 'x', N_LAYERS, '| type:', gl.par.type.eval(), '| errors:', gl.errors() or 'none', '| exposed as', ol.name)
print('slots   :', schop.path, 'channels:', [c.name for c in schop.chans()][:9], '| errors:', schop.errors() or 'none')
print('seg_mask2:', g2.path, '| errors:', g2.errors() or 'none')
print('input   :', src.path, src.width, src.height, src.pixelFormat)
print('output  :', g.path, g.width, g.height, g.par.type.eval(), g.par.mode.eval())
print('errors  :', g.errors() or 'none')
print('warnings:', g.warnings() or 'none')

# --- instance colour decoder --------------------------------------------------
# Same input, same resampling, but one colour per tracked body instead of one
# channel per class. Output is premultiplied RGBA.
idat = get_or_create(yolo, textDAT, 'seg_inst_pixel')
idat.par.syncfile = False
idat.par.file = ''
with open(INST_SHADER_PATH, 'r', encoding='utf-8') as fh:
    idat.text = fh.read()
idat.nodeX, idat.nodeY = dat.nodeX, dat.nodeY - 150

gi = get_or_create(yolo, glslmultiTOP, 'seg_instances')
gi.inputConnectors[0].connect(flip)
gi.nodeX, gi.nodeY = g.nodeX, g.nodeY - 150

gi.par.mode      = 'vertexpixel'
gi.par.pixeldat  = idat.name
gi.par.vertexdat = ''
gi.par.type      = 'texture2d'
gi.par.outputresolution = 'custom'
gi.par.resolutionw = OUT_W
gi.par.resolutionh = OUT_H
try:
    gi.par.format = 'rgba8fixed'      # colour output; 8-bit is plenty and cheaper downstream
except Exception as e:
    print('pixel format not set (menu name differs?):', e)

gi.par.uniname0 = 'uInRes'
expr(gi.par.value0x, 'me.inputs[0].width')
expr(gi.par.value0y, 'me.inputs[0].height')

gi.par.uniname1 = 'uOutRes'
expr(gi.par.value1x, 'me.par.resolutionw')
expr(gi.par.value1y, 'me.par.resolutionh')

gi.par.uniname2 = 'uEdge'
gi.par.value2x.mode = ParMode.CONSTANT; gi.par.value2x = THRESHOLD
gi.par.value2y.mode = ParMode.CONSTANT; gi.par.value2y = SOFTNESS

gi.par.uniname3 = 'uPalette'
for comp, val in zip('xyzw', PALETTE):
    pp = getattr(gi.par, 'value3' + comp)
    pp.mode = ParMode.CONSTANT
    pp.val = val

gi.cook(force=True)

# Expose the instance colours on the component: an Out TOP adds an output connector
# next to the existing ones, so downstream networks can wire it without diving in.
oi = get_or_create(yolo, outTOP, 'out_instances')
oi.inputConnectors[0].connect(gi)
oi.nodeX, oi.nodeY = gi.nodeX + 200, gi.nodeY
oi.par.label = 'instances'

print('--- seg_instances build ---')
print('exposed :', oi.path, '(component TOP output connector "instances")')
print('output  :', gi.path, gi.width, gi.height, gi.par.type.eval(), gi.par.mode.eval())
print('errors  :', gi.errors() or 'none')
print('warnings:', gi.warnings() or 'none')

# --- persistence check -------------------------------------------------------
# Parameter names for the reload flag differ between builds; find it by name.
ext    = yolo.par.externaltox.eval() if hasattr(yolo.par, 'externaltox') else ''
reload_pars = [p for p in yolo.pars() if 'reload' in p.name.lower() or 'tox' in p.name.lower()]
print('--- persistence ---')
print('externaltox :', ext or '(none)')
for p in reload_pars:
    print('  %-22s %-32s = %r' % (p.name, p.label, p.eval()))
if ext:
    print('!! This component is file-backed by', ext)
    print('!! If any "Reload ... on Start" flag above is True, edits inside are discarded on open.')
    print('!! Either set that flag False, or persist now with:')
    print('!!   op(%r).save(%r)' % (yolo.path, ext))
