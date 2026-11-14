"""Split the left elevator of the Learjet 60 glTF model into its own node ("elevator_left")
so the viewer can hide it when it separates. Geometry is unchanged; triangles are only
re-grouped. Usage: python3 split_elevator.py <source model dir> <output dir>"""
import json, os, shutil, struct, sys
import numpy as np
src, out = sys.argv[1], sys.argv[2]
g = json.load(open(os.path.join(src, 'scene.gltf')))
buf = bytearray(open(os.path.join(src, 'scene.bin'), 'rb').read())

def acc(i):
    a = g['accessors'][i]; bv = g['bufferViews'][a['bufferView']]
    n = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3, 'VEC4': 4}[a['type']]; dt = {5126: 'f4', 5123: 'u2', 5125: 'u4', 5121: 'u1'}[a['componentType']]
    off = bv.get('byteOffset', 0) + a.get('byteOffset', 0); stride = bv.get('byteStride'); sz = n * np.dtype(dt).itemsize
    if stride and stride != sz:
        raw = np.frombuffer(bytes(buf), dtype='u1', count=stride * (a['count'] - 1) + sz, offset=off)
        idx = (np.arange(a['count'])[:, None] * stride + np.arange(sz)[None, :]).ravel()
        return raw[idx].copy().view(dt).reshape(a['count'], n)
    return np.frombuffer(bytes(buf), dtype=dt, count=a['count'] * n, offset=off).reshape(a['count'], n)

def components(v, tris):
    _, inv = np.unique(np.round(v, 3), axis=0, return_inverse=True); inv = inv.ravel()
    parent = np.arange(inv.max() + 1)
    def find(a):
        while parent[a] != a: parent[a] = parent[parent[a]]; a = parent[a]
        return a
    for t in tris:
        a, b, c = find(inv[t[0]]), find(inv[t[1]]), find(inv[t[2]]); parent[b] = a; parent[c] = a
    return np.array([find(inv[t[0]]) for t in tris])

# Nose is +Z, up is +Y, so the left side of the aircraft is +X.
# A connected piece belongs to the left elevator if it sits on the left half of the T-tail, aft of the hinge line.
def is_left_elevator(mesh, lo, hi):
    if lo[0] < 0.0 or lo[1] < 2.3: return False
    if mesh == 33: return hi[2] < -8.0 and lo[2] < -8.8            # elevator skin
    if mesh == 24: return hi[2] < -8.0 and lo[2] > -8.7             # elevator leading-edge and end faces
    if mesh == 37: return hi[2] < -8.4                               # static wicks on the elevator trailing edge
    return False

new_prims = []; moved = {}
for mi in (33, 24, 37):
    prim = g['meshes'][mi]['primitives'][0]
    v = acc(prim['attributes']['POSITION']); tris = acc(prim['indices']).ravel().reshape(-1, 3).astype(np.uint32)
    lab = components(v, tris); take = np.zeros(len(tris), bool)
    for l in np.unique(lab):
        pts = v[np.unique(tris[lab == l])]
        if is_left_elevator(mi, pts.min(0), pts.max(0)): take |= lab == l
    moved[mi] = int(take.sum())
    for sel, target in ((~take, 'keep'), (take, 'elev')):
        data = tris[sel].astype('<u4').tobytes()
        while len(buf) % 4: buf.append(0)
        off = len(buf); buf.extend(data)
        g['bufferViews'].append({'buffer': 0, 'byteOffset': off, 'byteLength': len(data), 'target': 34963})
        g['accessors'].append({'bufferView': len(g['bufferViews']) - 1, 'componentType': 5125, 'count': int(sel.sum()) * 3, 'type': 'SCALAR'})
        if target == 'keep': prim['indices'] = len(g['accessors']) - 1
        else: new_prims.append({'attributes': dict(prim['attributes']), 'indices': len(g['accessors']) - 1, 'material': prim['material'], 'mode': 4})
g['buffers'][0]['byteLength'] = len(buf)
g['meshes'].append({'name': 'elevator_left', 'primitives': new_prims})
g['nodes'].append({'name': 'elevator_left', 'mesh': len(g['meshes']) - 1})
g['nodes'][3].setdefault('children', []).append(len(g['nodes']) - 1)
g['asset'].setdefault('extras', {})['modified'] = 'Left elevator triangles regrouped into a separate node (elevator_left); geometry unchanged. Same license (CC-BY-NC-SA-4.0).'
os.makedirs(os.path.join(out, 'textures'), exist_ok=True)
json.dump(g, open(os.path.join(out, 'scene.gltf'), 'w'), separators=(',', ':'))
open(os.path.join(out, 'scene.bin'), 'wb').write(bytes(buf))
for f in os.listdir(os.path.join(src, 'textures')): shutil.copy(os.path.join(src, 'textures', f), os.path.join(out, 'textures', f))
shutil.copy(os.path.join(src, 'license.txt'), os.path.join(out, 'license.txt'))
print('triangles moved to elevator_left per source mesh:', moved, '| bin bytes', len(buf))
