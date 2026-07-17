"""Пути каталога и lab для совместных анимаций."""

from __future__ import annotations

from pathlib import Path

from ..anabarra_layout import library_root, project_data_dir
from ..config import Config


def interaction_catalog_path(config: Config) -> Path:
    return project_data_dir(config) / "interaction_catalog.json"


def interaction_lab_root(config: Config) -> Path:
    """U:\\Anabarra\\Library\\Lab\\Interactions\\"""
    root = library_root(config) / "Lab" / "Interactions"
    root.mkdir(parents=True, exist_ok=True)
    return root


def interaction_scene_dir(config: Config, slug: str) -> Path:
  safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in slug.strip().lower())
  p = interaction_lab_root(config) / (safe or "scene")
  p.mkdir(parents=True, exist_ok=True)
  return p


def actor_dir(config: Config, slug: str, role: str) -> Path:
    safe_role = "".join(c if c.isalnum() or c in "-_" else "_" for c in role.strip().lower())
    p = interaction_scene_dir(config, slug) / "actors" / (safe_role or "actor")
    p.mkdir(parents=True, exist_ok=True)
    return p
