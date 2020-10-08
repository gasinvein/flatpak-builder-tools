#!/usr/bin/env python3

import copy
import json
import os
import re
import argparse
import yaml

MULTILIB_PROP = "x-multilib"
VARIANTS = {
    "native": {
        "prop": "x-native-module"
    },
    "compat": {
        "prop": "x-compat32-module",
        "name-suffix": "-32bit"
    }
}

UNCLEANUP_PATTERNS = [
    r"^/include",
    r"^/lib/.+/include",
    r"^/lib/pkgconfig",
    r"^/share/pkgconfig",
    r"^/share/aclocal",
    r"^/lib/cmake"
]

def load_dict_file(dict_file):
    with open(dict_file, "r") as f:
        if any(dict_file.endswith(i) for i in [".yml", ".yml.in", ".yaml", "yaml.in"]):
            loader = yaml.safe_load
        elif any(dict_file.endswith(i) for i in [".json", ".json.in"]):
            loader = json.load
        else:
            raise ValueError(f"Unknown format of {dict_file}")
        d = loader(f)
    return d

def save_dict_file(dict_data, dict_file):
    with open(dict_file, "w") as f:
        if any(dict_file.endswith(i) for i in [".yml", ".yaml"]):
            writer = yaml.dump
        elif dict_file.endswith(".json"):
            writer = lambda o, f: json.dump(o, f, indent=4, sort_keys=False)
        else:
            raise ValueError(f"Unknown format of {dict_file}")
        writer(dict_data, f)

def merge_dicts(base_dict, update_dict, append_list=True):
    merged_dict = copy.deepcopy(base_dict)
    for upd_key, upd_val in update_dict.items():
        if isinstance(merged_dict.get(upd_key), dict) and isinstance(upd_val, dict):
            merged_dict[upd_key] = merge_dicts(merged_dict[upd_key], upd_val)
        elif append_list and isinstance(merged_dict.get(upd_key), list) and isinstance(upd_val, list):
            merged_dict[upd_key] += upd_val
        else:
            merged_dict[upd_key] = upd_val
    return merged_dict

def multilibify(holder_object, holder_file, base_dir=None, variants=None):
    holder_dir = os.path.dirname(holder_file)
    if base_dir is None:
        base_dir = holder_dir

    if variants is None:
        variants = {}
        for v, opts in VARIANTS.items():
            variants[v] = holder_object.pop(opts["prop"], {})
            if isinstance(variants[v], str):
                variants[v] = load_dict_file(os.path.join(holder_dir, variants[v]))

    holder_multilib = holder_object.pop(MULTILIB_PROP, True)
    orig_modules = holder_object["modules"]
    modules = []

    for orig_module in orig_modules:
        module_file = holder_file

        if isinstance(orig_module, str):
            module_file = os.path.join(holder_dir, orig_module)
            orig_module = load_dict_file(module_file)

        for source in orig_module["sources"]:
            if "path" in source:
                source_path = os.path.join(os.path.dirname(module_file), source["path"])
                source["path"] = os.path.relpath(source_path, base_dir)

        if not orig_module.pop(MULTILIB_PROP, holder_multilib):
            modules.append(orig_module)
            continue

        module_variants = {}
        for v, props in variants.items():
            module_props = orig_module.pop(VARIANTS[v]["prop"], {})
            module_variants[v] = merge_dicts(props, module_props, append_list=False)

        for v, props in module_variants.items():
            new_module = merge_dicts(orig_module, props)
            new_module["name"] = "{0}{1}".format(orig_module["name"], VARIANTS[v].get("name-suffix", ""))
            if "modules" in new_module:
                new_module = multilibify(new_module, module_file, base_dir, variants={v: props})
            modules.append(new_module)

    holder_object["modules"] = modules
    return holder_object

def uncleanup(holder_object, uncleanup_regexps=None):
    if uncleanup_regexps is None:
        uncleanup_regexps = [re.compile(r) for r in UNCLEANUP_PATTERNS]
    if "cleanup" in holder_object:
        new_cleanup = []
        for p in holder_object["cleanup"]:
            if not any(r.match(p) for r in uncleanup_regexps):
                new_cleanup.append(p)
        holder_object["cleanup"] = new_cleanup
    if "modules" in holder_object:
        for module in holder_object["modules"]:
            uncleanup(module, uncleanup_regexps)
    return holder_object

def main():
    parser = argparse.ArgumentParser("Make flatpak-builder modules multilib")
    parser.add_argument("-u", "--uncleanup", action="store_true", help="Undo cleanup rules")
    parser.add_argument("source_manifest")
    parser.add_argument("target_manifest")
    args = parser.parse_args()
    holder_object = load_dict_file(args.source_manifest)
    multilibify(holder_object, args.source_manifest)
    if args.uncleanup:
        uncleanup(holder_object)
    save_dict_file(holder_object, args.target_manifest)

if __name__ == "__main__":
    main()
