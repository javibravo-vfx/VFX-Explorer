"""Tests sin GUI: python tests/test_core.py"""
import os, sys, tempfile, shutil
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from vfxexplorer.core import scan_dir, group_files, parse_query, entry_matches, compress_ranges, resolve_refs
from vfxexplorer.library import Library
from vfxexplorer.pipeline import Pipeline
from vfxexplorer import fileops


def touch(p, data=b"x"):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(data)


def names(d):
    return {e.name: e for e in scan_dir(d)}


def test_grouping():
    g = {e.name: e for e in group_files("/x", [(n, 1, 0) for n in [
        "shot_v001.exr", "shot_v002.exr", "a.0998.dpx", "a.0999.dpx", "frame0001.exr", "frame0002.exr",
        "render.1001.exr", "clip_001.mov", "clip_002.mov", "p.8.png", "p.9.png", "p.10.png"]])}
    assert "shot_v001.exr" in g and "shot_v002.exr" in g, "versiones no son frames"
    assert g["a.####.dpx"].frames == [998, 999]
    assert "frame####.exr" in g and "render.1001.exr" in g and "clip_001.mov" in g
    assert g["p.#.png"].pad == 0 and g["p.#.png"].frames == [8, 9, 10]
    assert compress_ranges([1, 2, 3, 5, 7, 8]) == "1-3, 5, 7-8"


def test_query():
    q = parse_query("plate #fuego ★3")
    assert q.names == ["plate"] and q.tags == ["fuego"] and q.min_rating == 3
    e = group_files("/x", [("plate.1001.exr", 1, 0), ("plate.1002.exr", 1, 0)])[0]
    meta = {e.key(): {"tags": ["Fuego", "exterior"], "rating": 4}}.get
    assert entry_matches(e, q, "all", meta=meta)
    assert not entry_matches(e, parse_query("#agua"), "all", meta=meta)
    assert not entry_matches(e, parse_query("★5"), "all", meta=meta)
    assert entry_matches(e, parse_query("*pla*"), "seq")
    assert not entry_matches(e, parse_query(""), "video")


def test_library_and_refs(tmp):
    d = os.path.join(tmp, "lib")
    for i in range(1, 4):
        touch(os.path.join(d, f"fire.{i:04d}.exr"))
    touch(os.path.join(d, "rock.fbx"))
    ents = names(d)
    lib = Library(os.path.join(tmp, "library.json"))
    fire, rock = ents["fire.####.exr"], ents["rock.fbx"]
    lib.edit_tags([(fire.key(), fire.ref()), (rock.key(), rock.ref())], ["fuego", "vfx"], [])
    lib.edit_tags([(rock.key(), rock.ref())], ["roca"], ["fuego", "vfx"])
    assert lib.tags(fire.key()) == ["fuego", "vfx"] and lib.tags(rock.key()) == ["roca"]
    lib.set_rating([(fire.key(), fire.ref())], 4)
    lib.add_to_collection("Elementos", [(fire.key(), fire.ref())])
    lib.save()
    lib2 = Library(os.path.join(tmp, "library.json"))
    found, missing = resolve_refs(lib2.refs_in_collection("Elementos"))
    assert [e.name for e in found] == ["fire.####.exr"] and not missing
    assert dict(lib2.all_tags()) == {"fuego": 1, "vfx": 1, "roca": 1}
    lib2.set_rating([(fire.key(), fire.ref())], 0)
    lib2.edit_tags([(fire.key(), fire.ref())], [], ["fuego", "vfx"])
    lib2.remove_from_collection("Elementos", [fire.key()])
    assert fire.key() not in lib2.items, "se limpian ítems vacíos"


def test_rename_renumber(tmp):
    d = os.path.join(tmp, "ren")
    for i in range(1, 6):
        touch(os.path.join(d, f"plate_v001.{i:04d}.exr"), str(i).encode())
    e = names(d)["plate_v001.####.exr"]
    # renumerar 1-5 -> 3-7 (se pisa: requiere dos fases)
    fileops.apply_renames(fileops.rename_plan(e, "plate_v001", start_frame=3))
    e = names(d)["plate_v001.####.exr"]
    assert e.frames == [3, 4, 5, 6, 7]
    assert open(os.path.join(d, "plate_v001.0003.exr")).read() == "1"
    fileops.apply_renames(fileops.rename_plan(e, "sh010_plate_v002", start_frame=1001))
    e = names(d)["sh010_plate_v002.####.exr"]
    assert e.first == 1001 and e.last == 1005
    touch(os.path.join(d, "otro.exr"))
    try:
        fileops.apply_renames(fileops.rename_plan(names(d)["otro.exr"], "sh010_plate_v002.1001.exr"))
        raise AssertionError("debía fallar")
    except FileExistsError:
        pass


def test_rename_inline(tmp):
    d = os.path.join(tmp, "inl")
    for i in (1001, 1002, 1003):
        touch(os.path.join(d, f"plate_v001.{i}.exr"))
    e = names(d)["plate_v001.####.exr"]
    fileops.apply_renames(fileops.seq_rename_from_text(e, "sh020_plate_v002_#####.exr"))
    assert sorted(os.listdir(d)) == ["sh020_plate_v002_01001.exr", "sh020_plate_v002_01002.exr",
                                     "sh020_plate_v002_01003.exr"]
    e = names(d)["sh020_plate_v002_#####.exr"]
    fileops.apply_renames(fileops.seq_rename_from_text(e, "final"))
    assert "final_01001.exr" in os.listdir(d)
    try:
        fileops.seq_rename_from_text(names(d)["final_#####.exr"], "x.####.jpg")
        raise AssertionError("debía fallar: cambio de extensión")
    except ValueError:
        pass


def run_worker(op, sources, dest, overwrite=False):
    w = fileops.FileOpWorker(op, sources, dest, overwrite)
    res = {}
    w.done.connect(lambda ok, err, c: res.update(ok=ok, err=err, c=c))
    w.run()   # sincrónico para el test
    return res


def test_copy_move(tmp):
    src = os.path.join(tmp, "src")
    dst = os.path.join(tmp, "dst")
    os.makedirs(dst)
    for i in range(1, 4):
        touch(os.path.join(src, "asset", "tex", f"t.{i:04d}.exr"), b"a" * 1000)
    touch(os.path.join(src, "single.mov"), b"m" * 20000)
    assert fileops.validate_transfer([os.path.join(src, "asset")], os.path.join(src, "asset", "tex"), "copy")
    assert fileops.validate_transfer([os.path.join(src, "single.mov")], src, "copy")
    r = run_worker("copy", [os.path.join(src, "asset"), os.path.join(src, "single.mov")], dst)
    assert r["ok"] == 4 and not r["err"], r
    assert os.path.getsize(os.path.join(dst, "single.mov")) == 20000
    assert len(fileops.plan_conflicts([os.path.join(src, "asset")], dst)) == 3
    r = run_worker("copy", [os.path.join(src, "asset")], dst, overwrite=False)
    assert r["ok"] == 0
    dst2 = os.path.join(tmp, "dst2")
    os.makedirs(dst2)
    r = run_worker("move", [os.path.join(dst, "asset"), os.path.join(dst, "single.mov")], dst2)
    assert not os.path.exists(os.path.join(dst, "asset")) and os.path.isfile(os.path.join(dst2, "asset", "tex", "t.0002.exr"))
    # mover fusionando con carpeta existente
    os.makedirs(os.path.join(dst, "asset", "tex"))
    touch(os.path.join(dst, "asset", "tex", "t.0009.exr"))
    r = run_worker("move", [os.path.join(dst, "asset")], dst2)
    assert sorted(os.listdir(os.path.join(dst2, "asset", "tex"))) == ["t.0001.exr", "t.0002.exr", "t.0003.exr", "t.0009.exr"]
    assert not os.path.exists(os.path.join(dst, "asset"))
    paths, cut = fileops.read_clip_mime(fileops.make_clip_mime([os.path.join(dst2, "single.mov")], cut=True))
    assert cut and paths


def test_pipeline(tmp):
    root = os.path.join(tmp, "T")
    sd = os.path.join(root, "VFX-MOR", "101", "MOR_1001A_930", "3D", "8_lighting", "1_projects")
    os.makedirs(sd)
    os.makedirs(os.path.join(root, "VFX-MOR", "AUDIO"))
    os.makedirs(os.path.join(root, "VFX-MOR", "102", "MOR_1002A_010", "2D"))

    class C(dict):
        def __getitem__(self, k):
            return self.get(k)
    p = Pipeline(C(pipeline_use_stm=False, pipeline_root=root, pipeline_prefix="VFX-", pipeline_seq_exclude="AUDIO",
                   pipeline_depts=""))
    assert p.projects() == ["MOR"]
    assert p.sequences("MOR") == ["101", "102"]
    assert p.shots("MOR", "101") == ["MOR_1001A_930"]
    os.makedirs(os.path.join(root, "VFX-MOR", "101", "MOR_1001A_930", "Comp", "v001"))
    os.makedirs(os.path.join(root, "VFX-MOR", "101", "MOR_1001A_930", "DMP"))
    assert p.depts("MOR", "101", "MOR_1001A_930") == ["3D", "Comp", "DMP"]
    assert p.tasks("MOR", "101", "MOR_1001A_930", "3D") == ["8_lighting"]
    assert p.tasks("MOR", "101", "MOR_1001A_930", "Comp") == ["v001"]
    info = p.parse(sd)
    assert info == {"project": "MOR", "seq": "101", "shot": "MOR_1001A_930", "dept": "3D", "task": "8_lighting"}, info


if __name__ == "__main__":
    from PySide6.QtCore import QCoreApplication
    app = QCoreApplication([])
    tmp = tempfile.mkdtemp()
    try:
        for name, fn in list(globals().items()):
            if name.startswith("test_"):
                args = [os.path.join(tmp, name)] if fn.__code__.co_argcount else []
                if args:
                    os.makedirs(args[0])
                fn(*args)
                print("ok ", name)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("TODOS LOS TESTS OK")
