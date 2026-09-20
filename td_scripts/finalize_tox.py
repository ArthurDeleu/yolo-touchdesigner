# Makes the yolo component portable and saves it for the team. Paste into the textport:
#   exec(open('/Users/arthurdeleu/Code/TDYolo/yolo-touchdesigner/td_scripts/finalize_tox.py').read())
#
# Portable means: Dev mode off (page served from the embedded VFS, not a dev server),
# no DAT synced to a file on this machine (text embedded instead), the served index.html
# matching the bundle in the VFS, and no parameter pointing into /Users/... .
# Prints every fix and every remaining problem; saves only when nothing blocks.
import os, re

SAVE_PATH = '/Users/arthurdeleu/Code/Aluvision/touchdesigner/yolo.tox'
REPO = '/Users/arthurdeleu/Code/TDYolo/yolo-touchdesigner'

hits = [c for c in root.findChildren(type=COMP) if c.op('yolo_server/virtualFile') is not None]
assert len(hits) == 1, 'expected exactly one yolo component, found %r' % [h.path for h in hits]
yolo = hits[0]
blockers = []
print('component       :', yolo.path)

# 1. Dev off
if hasattr(yolo.par, 'Dev') and yolo.par.Dev.eval():
    yolo.par.Dev = False
    print('fix             : Dev mode turned OFF (page will reload from the VFS)')

# 2. embed every file-synced DAT inside the component
for d in yolo.findChildren(type=DAT):
    f = d.par.file.eval() if hasattr(d.par, 'file') else ''
    sync = d.par.syncfile.eval() if hasattr(d.par, 'syncfile') else False
    if f or sync:
        txt = d.text
        if hasattr(d.par, 'syncfile'): d.par.syncfile = False
        d.par.file = ''
        if not d.text.strip() and txt.strip():
            d.text = txt
        print('fix             : embedded %s (was synced to %s)' % (d.path, f or '?'))

# 3. served index.html must reference the bundle that is in the VFS
vfs = yolo.op('yolo_server/virtualFile').vfs
vfs_js = sorted(x.name for x in vfs.find(pattern='index-*.js'))
idx = yolo.op('index_html')
refs = re.findall(r'index-[\w-]+\.js', idx.text) if idx is not None else []
disk = sorted(x for x in os.listdir(os.path.join(REPO, 'dist', 'assets')) if x.startswith('index-') and x.endswith('.js')) if os.path.isdir(os.path.join(REPO, 'dist', 'assets')) else []
print('bundle          : VFS %s | index.html refs %s | dist %s' % (vfs_js, refs, disk))
if not refs or not all(r in vfs_js for r in refs):
    blockers.append('index.html references a bundle that is not in the VFS -> run embed_seg_models.py first')
if disk and disk != vfs_js:
    blockers.append('dist/assets bundle differs from the VFS bundle -> npm run build + embed_seg_models.py, or the tox ships an older web app')

# 4. anything still pointing at this machine
for o in yolo.findChildren():
    for p in o.pars():
        try:
            v = p.eval()
        except Exception:
            continue
        if isinstance(v, str) and '/Users/' in v:
            print('!! path on this machine:', o.path + '.' + p.name, '=', v)
            blockers.append('%s.%s points into /Users/' % (o.name, p.name))

# 5. page URL sanity
wr = yolo.op('webrender1')
url = wr.par.url.eval() if wr is not None else ''
if '5173' in url:
    blockers.append('webrender URL still targets the dev server: ' + url[:60])
print('page url        :', url[:80] + ('...' if len(url) > 80 else ''))

# 6. leftovers from today's diagnostics
for k in ('diag_rx_wrapped', 'diag_rx_count', 'diag_rx_before', 'diag_seg_snap'):
    try: yolo.unstore(k)
    except Exception: pass

# 7. save
if blockers:
    print('NOT SAVED. Fix these first:')
    for b in blockers: print('  -', b)
else:
    yolo.save(SAVE_PATH)
    mb = os.path.getsize(SAVE_PATH) / (1 << 20)
    print('SAVED           : %s (%.0f MB)' % (SAVE_PATH, mb))
    print('next            : cd ~/Code/Aluvision && git add touchdesigner/yolo.tox && git commit && git push  (LFS handles the blob)')
    print('Remi            : git pull && git lfs pull, drop touchdesigner/yolo.tox into his project, wire a TOP or pick a webcam.')
