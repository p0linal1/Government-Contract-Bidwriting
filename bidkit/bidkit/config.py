#!/usr/bin/env python3
"""
config.py — load and validate a per-opportunity `opportunity.json`; resolve paths.

Why: every bid has its own workbook layouts, form labels, format rules, and signer values.
Keeping them in one config (instead of in code) is what lets bidkit stay generic and lets a
bid be re-run months later without archaeology.

Inputs : path to opportunity.json (paths inside are relative to that file's directory).
Outputs: an `Opportunity` object with dict-style access + `resolve(path)` helper.
Guards : missing required sections raise ConfigError with the exact key path.

CLI:  python3 -m bidkit.config <opportunity.json>      # validates and prints a summary
"""
import json, os, sys

REQUIRED_TOP = ["id", "format", "fonts", "folders"]
REQUIRED_FORMAT = ["font_family_allow", "min_font_pt", "margin_in", "page_size", "page_limit"]
REQUIRED_FONTS = ["regular", "bold", "italic", "bold_italic"]


class ConfigError(Exception):
    pass


class Opportunity:
    def __init__(self, data, base_dir):
        self.data = data
        self.base_dir = os.path.abspath(base_dir)

    # dict-style access ---------------------------------------------------------------
    def __getitem__(self, k): return self.data[k]
    def get(self, k, default=None): return self.data.get(k, default)
    @property
    def id(self): return self.data["id"]

    # helpers -------------------------------------------------------------------------
    def resolve(self, path):
        """Resolve a config path relative to the opportunity folder (absolute passthrough)."""
        if not path:
            return path
        return path if os.path.isabs(path) else os.path.normpath(os.path.join(self.base_dir, path))

    def folder(self, key, create=False):
        p = self.resolve(self.data["folders"][key])
        if create:
            os.makedirs(p, exist_ok=True)
        return p

    def workbook(self, key):
        try:
            wb = self.data["workbooks"][key]
        except KeyError:
            raise ConfigError(f"workbooks.{key} not defined in {self.id}")
        return wb

    def form(self, key):
        try:
            return self.data["forms"][key]
        except KeyError:
            raise ConfigError(f"forms.{key} not defined in {self.id}")


def _strip_comments(obj):
    """Drop any key starting with '_' (used for _comment) recursively."""
    if isinstance(obj, dict):
        return {k: _strip_comments(v) for k, v in obj.items() if not k.startswith("_")}
    if isinstance(obj, list):
        return [_strip_comments(v) for v in obj]
    return obj


def load(path):
    path = os.path.abspath(path)
    if not os.path.exists(path):
        raise ConfigError(f"config not found: {path}")
    with open(path, encoding="utf-8") as fh:
        try:
            raw = json.load(fh)
        except json.JSONDecodeError as e:
            raise ConfigError(f"invalid JSON in {path}: {e}")
    data = _strip_comments(raw)
    for k in REQUIRED_TOP:
        if k not in data:
            raise ConfigError(f"missing required key '{k}' in {path}")
    for k in REQUIRED_FORMAT:
        if k not in data["format"]:
            raise ConfigError(f"missing required key 'format.{k}' in {path}")
    for k in REQUIRED_FONTS:
        if k not in data["fonts"]:
            raise ConfigError(f"missing required key 'fonts.{k}' in {path}")
    # per-workbook sanity. Requirement-style workbooks need the uniform column model;
    # form-style ones (label + value grids, "form_style": true) only need path + header_row.
    for wk, wb in data.get("workbooks", {}).items():
        for k in ("path", "header_row"):
            if k not in wb:
                raise ConfigError(f"missing 'workbooks.{wk}.{k}' in {path}")
        if not wb.get("form_style"):
            if "cols" not in wb:
                raise ConfigError(f"missing 'workbooks.{wk}.cols' in {path} (or set form_style: true)")
            for c in ("num", "req", "resp", "comment"):
                if c not in wb["cols"]:
                    raise ConfigError(f"missing 'workbooks.{wk}.cols.{c}' in {path}")
    for fk, f in data.get("forms", {}).items():
        for k in ("path", "page", "fields"):
            if k not in f:
                raise ConfigError(f"missing 'forms.{fk}.{k}' in {path}")
    return Opportunity(data, os.path.dirname(path))


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cfg", help="path to opportunity.json")
    a = ap.parse_args(argv)
    try:
        opp = load(a.cfg)
    except ConfigError as e:
        print(f"CONFIG ERROR: {e}"); return 1
    print(f"opportunity {opp.id}  base={opp.base_dir}")
    print(f"  format: {opp['format']}")
    print(f"  workbooks: {list(opp.get('workbooks', {}).keys())}")
    print(f"  forms: {list(opp.get('forms', {}).keys())}")
    for k, v in opp["folders"].items():
        print(f"  folder {k}: {opp.resolve(v)}")
    missing_fonts = [k for k, p in opp["fonts"].items() if not os.path.exists(p)]
    if missing_fonts:
        print(f"  WARNING: font files not found for {missing_fonts}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
