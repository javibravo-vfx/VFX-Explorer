# -*- coding: utf-8 -*-
"""Estructura de pipeline:
   {root}\\{prefix}{PROJECT}\\{SEQ}\\{SHOT}\\{DEPT}\\{TASK}\\{stages}

Los departamentos pueden tener tasks (3D\\1_matchmove\\1_projects…), ir directo a los stages
(Comp\\1_projects, 2_review, 3_publish) o tener carpetas sueltas (_input\\plates…).
Se configura todo en VFX Explorer (ya no depende de Studio Toolbar; su config se importa una vez)."""

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

    def subfolders(self):
        """Stages: las carpetas de trabajo dentro de un task (o directo en un departamento sin tasks)."""
        v = self.cfg["pipeline_stages"]
        if v is None:
            v = "1_projects, 2_review, 3_publish"
        return [x.strip() for x in v.split(",") if x.strip()]

    def task_depts(self):
        v = self.cfg["pipeline_task_depts"]
        if v is None:
            v = "3D"
        return [x.strip().lower() for x in v.split(",") if x.strip()]

    def dept_kind(self, project, seq, shot, dept):
        """«task»: el departamento tiene tasks (3D) · «stage»: va directo a projects/review/publish (Comp, DMP)
        · «folder»: carpetas sueltas (_input)."""
        if not dept:
            return "task"
        if dept.lower() in self.task_depts():
            return "task"
        kids = {k.lower() for k in _listdirs(self.dept_dir(project, seq, shot, dept))}
        if kids & {x.lower() for x in self.subfolders()}:
            return "stage"
        if not self.task_depts() and not dept.startswith("_"):
            return "task"
        return "folder"

    def available(self):
        return os.path.isdir(self.base())

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
        return [d.strip().lower() for d in (self.cfg["pipeline_depts"] or "").split(",") if d.strip()]

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
