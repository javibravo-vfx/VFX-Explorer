# -*- coding: utf-8 -*-
"""Estructura de pipeline:
   {root}\\{prefix}{PROJECT}\\{SEQ}\\{SHOT}\\{DEPT}\\{TASK}\\{stages}

Los departamentos pueden tener tasks (3D\\1_matchmove\\1_projects…), ir directo a los stages
(Comp\\1_projects, 2_review, 3_publish) o tener carpetas sueltas (_input\\plates…).
Se configura todo en VFX Explorer (ya no depende de the toolbar; su config se importa una vez)."""

import os
import json

STM_DIR = os.path.expanduser(os.path.join("~", ".studio-toolbar"))
STM_CONFIG = os.path.join(STM_DIR, "pipeline_config.ini")

STM_DEFAULTS = {
    "root_drive": "T:",
    "project_prefix": "VFX-",
    "seq_exclude": "3D,SOURCE,FOOTAGE,AUDIO,RENDER",
    "tasks": "1_matchmove,2_model,3_retopo,4_rigging,5_shaders,6_animation,7_fx,8_lighting",
    "sub_projects": "1_projects",
    "sub_review": "2_review",
    "sub_publish": "3_publish",
    "extra_subs": "",
}


# Departamentos (Settings › Pipeline). Cada uno es una carpeta dentro del shot:
#   · con tasks: Dept\<task>\<folders>; cada línea de tasks es «task: carpetas dentro de la primera folder»
#   · sin tasks: Dept\<folders> directamente (las «stages»: 1_projects, 2_review…)
# El ＋ de la barra crea tasks y departamentos con esta plantilla.
DEFAULT_DEPTS = [
    {"name": "3D", "has_tasks": True,
     "tasks": "1_matchmove: footage, textures\n2_model: textures\n3_retopo: textures\n4_rigging: textures\n"
              "5_shaders: textures\n6_animation: textures\n7_fx: textures, cache\n8_lighting: textures, cache, import",
     "folders": "1_projects, 2_review, 3_publish"},
    {"name": "DMP", "has_tasks": False, "tasks": "", "folders": "1_projects, 2_review, 3_publish"},
    {"name": "Comp", "has_tasks": False, "tasks": "", "folders": "0_assets, 1_projects, 2_prerenders, 3_review, 4_publish"},
]


def legacy_departments(cfg):
    """Arma la lista de departamentos desde la config de antes de 0.18 (sin perder lo que se había tocado)."""
    import copy
    deps = copy.deepcopy(DEFAULT_DEPTS)
    tpl = cfg["pipeline_templates"] or {}
    stages = cfg["pipeline_stages"]
    d3, dmp, comp = deps
    d3["name"] = tpl.get("3d_name") or d3["name"]
    d3["tasks"] = tpl.get("3d_tasks", d3["tasks"])
    d3["folders"] = tpl.get("3d_task_subs") or (stages if stages is not None else d3["folders"])
    dmp["name"] = tpl.get("dmp_name") or dmp["name"]
    dmp["folders"] = tpl.get("dmp_subs", dmp["folders"])
    comp["name"] = tpl.get("comp_name") or comp["name"]
    comp["folders"] = tpl.get("comp_subs", comp["folders"])
    stage_f = stages if stages is not None else "1_projects, 2_review, 3_publish"
    names = {d["name"].lower() for d in deps}
    td = cfg["pipeline_task_depts"]
    for n in [x.strip() for x in (td or "").split(",") if x.strip()]:
        if n.lower() not in names:
            deps.append({"name": n, "has_tasks": True, "tasks": "", "folders": stage_f})
            names.add(n.lower())
    for n in [x.strip() for x in (cfg["pipeline_depts"] or "").split(",") if x.strip()]:
        if n.lower() not in names:
            deps.append({"name": n, "has_tasks": False, "tasks": "", "folders": stage_f})
            names.add(n.lower())
    return deps


def split_list(v):
    return [x.strip() for x in str(v or "").replace("\n", ",").split(",") if x.strip()]


def parse_tasks(text):
    """«1_matchmove: footage, textures» por línea → [(task, [subs])]."""
    out = []
    for line in str(text or "").splitlines():
        if not line.strip():
            continue
        name, _, subs = line.partition(":")
        name = name.strip()
        if name:
            out.append((name, split_list(subs)))
    return out


def _listdirs(path):
    try:
        with os.scandir(path) as it:
            return sorted((d.name for d in it if d.is_dir() and not d.name.startswith(".")), key=str.lower)
    except OSError:
        return []


class Pipeline:
    def __init__(self, cfg):
        self.cfg = cfg
        self.data = dict(STM_DEFAULTS)
        self.source = "defaults"
        self.reload()

    def reload(self):
        self.data = dict(STM_DEFAULTS)
        self.source = "VFX Explorer"
        self.data["root_drive"] = self.cfg["pipeline_root"] or "T:"
        self.data["project_prefix"] = self.cfg["pipeline_prefix"] or "VFX-"
        self.data["seq_exclude"] = self.cfg["pipeline_seq_exclude"] or ""

    # ---------------- config derivada ----------------
    @property
    def prefix(self):
        return self.data.get("project_prefix", "VFX-")

    def base(self):
        root = (self.data.get("root_drive") or "T:").rstrip("\\/")
        if len(root) == 2 and root[1] == ":":
            return root + os.sep
        return root or os.sep

    def seq_exclude(self):
        return {s.strip().upper() for s in self.data.get("seq_exclude", "").split(",") if s.strip()}

    # ---------------- departamentos
    def departments(self):
        v = self.cfg["pipeline_departments"]
        if v is None:
            return legacy_departments(self.cfg)
        return [d for d in v if (d.get("name") or "").strip()]

    # ---------------- carpeta de plates / input
    def input_name(self):
        v = self.cfg["pipeline_input"]
        return (v if v is not None else "_input").strip() or "_input"

    def input_subs(self):
        v = self.cfg["pipeline_input_subs"]
        return split_list("plates, refs" if v is None else v)

    def input_dir(self, project, seq, shot):
        return self.dept_path(project, seq, shot, self.input_name())

    def plates_dir(self, project, seq, shot):
        d = self.input_dir(project, seq, shot)
        subs = self.input_subs()
        return os.path.join(d, self._existing(d, subs[0])) if (d and subs) else d

    def create_input(self, project, seq, shot):
        d = self.input_dir(project, seq, shot)
        if not d:
            return ""
        os.makedirs(d, exist_ok=True)
        for sub in self.input_subs():
            os.makedirs(os.path.join(d, sub), exist_ok=True)
        return d

    def only_listed(self):
        """El desplegable Dept muestra solo los departamentos definidos (si no, todas las carpetas del shot)."""
        v = self.cfg["pipeline_only_depts"]
        if v is None:
            return bool((self.cfg["pipeline_depts"] or "").strip())
        return bool(v)

    def dept_def(self, dept):
        for d in self.departments():
            if d["name"].strip().lower() == (dept or "").lower():
                return d
        return None

    def dept_folders(self, dept):
        d = self.dept_def(dept)
        return split_list(d["folders"]) if d else self.subfolders()

    def dept_tasks(self, dept):
        d = self.dept_def(dept)
        return parse_tasks(d["tasks"]) if d and d.get("has_tasks") else []

    def subfolders(self):
        """Carpetas de trabajo conocidas (todas las de los departamentos), para reconocer «stages»."""
        out = []
        for d in self.departments():
            for x in split_list(d["folders"]):
                if x.lower() not in [o.lower() for o in out]:
                    out.append(x)
        return out or ["1_projects", "2_review", "3_publish"]

    def task_depts(self):
        return [d["name"].strip().lower() for d in self.departments() if d.get("has_tasks")]

    def _existing(self, parent, name):
        """La carpeta tal como existe (sin importar mayúsculas) o el nombre de la plantilla."""
        for d in _listdirs(parent):
            if d.lower() == name.lower():
                return d
        return name

    def dept_path(self, project, seq, shot, name):
        """Ruta del departamento en el shot (respeta las mayúsculas de lo que ya exista)."""
        sd = self.shot_dir(project, seq, shot)
        return os.path.join(sd, self._existing(sd, name.strip())) if sd else ""

    def create_task(self, project, seq, shot, dept, task):
        r"""Dept\<task>\<1ª folder>\(footage, textures…) + las otras folders."""
        base = self.dept_path(project, seq, shot, dept)
        if not base or not task:
            return ""
        td = os.path.join(base, task)
        subs = self.dept_folders(dept)
        inner = dict(self.dept_tasks(dept)).get(task, [])
        if subs:
            for x in inner or [""]:
                os.makedirs(os.path.join(td, subs[0], x) if x else os.path.join(td, subs[0]), exist_ok=True)
            for sub in subs[1:]:
                os.makedirs(os.path.join(td, sub), exist_ok=True)
        else:
            os.makedirs(td, exist_ok=True)
        return td

    def create_dept(self, project, seq, shot, dept):
        """Departamento sin tasks con sus folders (con tasks: solo la carpeta)."""
        d = self.dept_path(project, seq, shot, dept)
        if not d:
            return ""
        os.makedirs(d, exist_ok=True)
        dd = self.dept_def(dept)
        if dd and not dd.get("has_tasks"):
            for sub in split_list(dd["folders"]):
                os.makedirs(os.path.join(d, sub), exist_ok=True)
        return d

    def dept_kind(self, project, seq, shot, dept):
        """«task»: el departamento tiene tasks (3D) · «stage»: va directo a sus folders (Comp, DMP)
        · «folder»: carpetas sueltas (_input)."""
        if not dept:
            return "task"
        if dept.lower() == self.input_name().lower():
            return "folder"
        dd = self.dept_def(dept)
        if dd:
            return "task" if dd.get("has_tasks") else "stage"
        kids = {k.lower() for k in _listdirs(self.dept_dir(project, seq, shot, dept))}
        if kids & {x.lower() for x in self.subfolders()}:
            return "stage"
        if not self.task_depts() and not dept.startswith("_"):
            return "task"
        return "folder"

    def available(self):
        from .core import safe_isdir
        return safe_isdir(self.base(), 0.4)

    # ---------------- listados ----------------
    def projects(self):
        p = self.prefix
        return [d[len(p):] for d in _listdirs(self.base()) if d.startswith(p)]

    def project_dir(self, project):
        return os.path.join(self.base(), f"{self.prefix}{project}") if project else ""

    def sequences(self, project):
        ex = self.seq_exclude()
        return [d for d in _listdirs(self.project_dir(project)) if d[:1].isdigit() and d.upper() not in ex]

    def seq_dir(self, project, seq):
        return os.path.join(self.project_dir(project), seq) if project and seq else ""

    def shots(self, project, seq):
        return [d for d in _listdirs(self.seq_dir(project, seq)) if d.startswith(f"{project}_")]

    def shot_dir(self, project, seq, shot):
        return os.path.join(self.seq_dir(project, seq), shot) if project and seq and shot else ""

    # departamento = carpeta al nivel de 3D dentro del shot (3D, Comp, DMP, 2D…)
    def dept_filter(self):
        return [d["name"].strip().lower() for d in self.departments()] + [self.input_name().lower()] \
            if self.only_listed() else []

    def depts(self, project, seq, shot):
        dirs = _listdirs(self.shot_dir(project, seq, shot))
        only = self.dept_filter()
        if only:
            dirs = [d for d in dirs if d.lower() in only]
        return dirs

    def dept_dir(self, project, seq, shot, dept):
        return os.path.join(self.shot_dir(project, seq, shot), dept) if shot and dept else ""

    def three_d_dir(self, project, seq, shot):
        sd = self.shot_dir(project, seq, shot)
        if not sd:
            return ""
        for d in _listdirs(sd):
            if d.lower() == "3d":
                return os.path.join(sd, d)
        return os.path.join(sd, "3D")

    def tasks(self, project, seq, shot, dept=None):
        base = self.dept_dir(project, seq, shot, dept) if dept else self.three_d_dir(project, seq, shot)
        return _listdirs(base)

    def task_dir(self, project, seq, shot, task, dept=None):
        if not (task and shot):
            return ""
        base = self.dept_dir(project, seq, shot, dept) if dept else self.three_d_dir(project, seq, shot)
        return os.path.join(base, task)

    def shot_subdirs(self, project, seq, shot):
        return _listdirs(self.shot_dir(project, seq, shot))

    def task_subdirs(self, project, seq, shot, task, dept=None):
        return _listdirs(self.task_dir(project, seq, shot, task, dept))

    # ---------------- parseo ----------------
    def parse(self, path):
        """...\\VFX-XXX\\seq\\shot\\{depto}\\task\\... -> dict(project, seq, shot, dept, task) o None."""
        parts = [p for p in str(path).replace("/", "\\").split("\\") if p]
        pre = self.prefix
        idx = next((i for i, p in enumerate(parts) if p.startswith(pre) and len(p) > len(pre)), None)
        if idx is None:
            return None
        out = {"project": parts[idx][len(pre):], "seq": "", "shot": "", "dept": "", "task": ""}
        if len(parts) > idx + 1:
            out["seq"] = parts[idx + 1]
        if len(parts) > idx + 2:
            out["shot"] = parts[idx + 2]
        if len(parts) > idx + 3:
            out["dept"] = parts[idx + 3]
        if len(parts) > idx + 4:
            out["task"] = parts[idx + 4]
        return out
