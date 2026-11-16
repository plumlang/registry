#!/usr/bin/env python3
# SPDX-License-Identifier: MIT WITH Plumlang-trademarks
"""Keep the Orchard index: the tool behind the registry's workflows.

    python3 tools/orchard.py validate
        Check the whole index: every index file against its schema and the
        name rules, every bundle against its sha256, and search.json.
    python3 tools/orchard.py parse-issue publish|yank
        Read a publish or yank request (the issue form's body, in the
        ISSUE_BODY environment variable), check every field with strict
        patterns, and write them to $GITHUB_OUTPUT.
    python3 tools/orchard.py add-version BUNDLE --package NAME --owner LOGIN --repository URL
        Record a bundle that `plum package` made: check it, check ownership
        and that the version is new and higher, then write
        packages/NAME/VERSION.plumpkg, index/NA/NAME.json and search.json.
    python3 tools/orchard.py yank NAME VERSION --owner LOGIN
        Mark a version yanked.
    python3 tools/orchard.py search
        Write search.json again from the index.

The formats are described in plumlang/plumlang's docs/orchard.md. Messages
for the issue go to the file named by ORCHARD_MESSAGE, when it is set.
Only the Python standard library is used (3.11 or later, for tomllib).
"""

import datetime
import hashlib
import json
import os
import re
import sys
import tomllib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_BUNDLE = 1048576

# Names a package can't have: the first part of every standard module of
# plum (`plum stdlib`), and reserved words. plum package refuses them too;
# keep this list in step with it.
RESERVED = {
    "math", "str", "io", "os", "time", "fs", "json", "task", "net", "hash",
    "plum", "std", "stdlib", "orchard",
}
# Plumlang's keywords: `seed NAME` (with '-' as '_') couldn't name these.
KEYWORDS = {
    "and", "as", "bad", "branch", "break", "catch", "continue", "else", "false",
    "finally", "for", "good", "if", "in", "is", "kind", "match", "none", "not",
    "or", "plant", "return", "root", "seed", "self", "spawn", "super", "throw",
    "trait", "tree", "true", "try", "weak", "while",
}

NAME = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
VERSION = re.compile(r"(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})\.(0|[1-9][0-9]{0,8})")
PARTIAL = r"(?:0|[1-9][0-9]{0,8})(?:\.(?:0|[1-9][0-9]{0,8})){0,2}"
RANGE = re.compile(r"\*|(?:\^|~|=|>=)? *" + PARTIAL)
SHA = re.compile(r"[0-9a-f]{64}")
LOGIN = re.compile(r"[A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38}")
REPOSITORY = re.compile(r"https://github\.com/([A-Za-z0-9](?:[A-Za-z0-9]|-(?=[A-Za-z0-9])){0,38})/([A-Za-z0-9._-]{1,100})")
TAG = re.compile(r"[A-Za-z0-9][A-Za-z0-9._/+-]{0,99}")
FOLDER = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}(?:/[A-Za-z0-9_][A-Za-z0-9_.-]{0,99}){0,15}")
PART = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*")
DEVICES = {"con", "prn", "aux", "nul"} | {f"com{i}" for i in range(1, 10)} | {f"lpt{i}" for i in range(1, 10)}
TIME = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")


class Refused(Exception):
    """A request or an index that breaks a rule: the message says which."""


def say(message):
    """Print a message, and keep it for the issue's reply."""
    print(message)
    path = os.environ.get("ORCHARD_MESSAGE")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(message + "\n")


def name_problem(name):
    if not isinstance(name, str) or not 2 <= len(name) <= 40:
        return "a package name has 2 to 40 characters"
    if not NAME.fullmatch(name):
        return ("a package name has lowercase letters, digits and single '-', "
                "starts with a letter and doesn't end with '-'")
    if name in RESERVED:
        return f"'{name}' is a standard module's name, or reserved"
    if name.replace("-", "_") in KEYWORDS:
        return f"'{name}' is a keyword of Plumlang"
    return None


def version_key(version):
    return tuple(int(p) for p in version.split("."))


def path_problem(path):
    """The rules of plum's plum_package_path_problem (src/orchard/manifest.c)."""
    if not 1 <= len(path) <= 200:
        return "a path has 1 to 200 characters"
    parts = path.split("/")
    if len(parts) > 16:
        return "a path is at most 16 directories deep"
    for part in parts:
        if not PART.fullmatch(part) or part.endswith(".") or len(part) > 100:
            return "each part is letters, digits, '_', '-' and '.', not starting with '.' or '-'"
        if part.split(".")[0].lower() in DEVICES:
            return "a device name like CON or NUL"
    last = parts[-1]
    if last.endswith(".plum") and len(last) > 5:
        return None
    if len(parts) == 1 and (path in ("plum.toml", "README.md") or path.startswith("LICENSE")):
        return None
    return "a package holds .plum files, and plum.toml, README.md and LICENSE* at its top"


def index_path(name):
    return os.path.join(ROOT, "index", name[:2], name + ".json")


def bundle_path(name, version):
    return os.path.join(ROOT, "packages", name, version + ".plumpkg")


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def check_bundle(raw, name=None, version=None):
    """A bundle's bytes, checked: its manifest (as a dict) and files."""
    if len(raw) > MAX_BUNDLE:
        raise Refused(f"the bundle is {len(raw)} bytes; the limit is {MAX_BUNDLE}")
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as e:
        raise Refused(f"the bundle isn't UTF-8 JSON: {e}")
    if not isinstance(data, dict) or sorted(data) != ["files", "format", "name", "version"]:
        raise Refused("a bundle has exactly files, format, name and version")
    if data["format"] != 1:
        raise Refused("the bundle's format isn't 1")
    if name is not None and data["name"] != name:
        raise Refused(f"the bundle is of '{data['name']}', not '{name}'")
    if version is not None and data["version"] != version:
        raise Refused(f"the bundle is version {data['version']}, not {version}")
    files = data["files"]
    if not isinstance(files, dict) or "plum.toml" not in files:
        raise Refused("the bundle has no plum.toml")
    lowered = set()
    for path, text in files.items():
        problem = path_problem(path)
        if problem:
            raise Refused(f"the bundle has a bad path '{path}': {problem}")
        if path.lower() in lowered:
            raise Refused(f"the bundle has two files named '{path}' but for case")
        lowered.add(path.lower())
        if not isinstance(text, str) or "\0" in text:
            raise Refused(f"'{path}' isn't text")
    # the bytes plum package writes: sorted keys, no spaces
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    if canonical.encode("utf-8") != raw:
        raise Refused("the bundle isn't in the form plum package writes (sorted keys, no spaces)")
    try:
        manifest = tomllib.loads(files["plum.toml"])
    except tomllib.TOMLDecodeError as e:
        raise Refused(f"the bundle's plum.toml isn't TOML: {e}")
    package = manifest.get("package", {})
    if package.get("name") != data["name"] or package.get("version") != data["version"]:
        raise Refused("the bundle's plum.toml names another package or version")
    deps = manifest.get("dependencies", {})
    for dep, rng in deps.items():
        if name_problem(dep) or not isinstance(rng, str) or not RANGE.fullmatch(rng.strip()):
            raise Refused(f"the dependency {dep} = {rng!r} isn't valid")
    return manifest, files


# ------------------------------------------------------------------
# The whole index
# ------------------------------------------------------------------

def load_index(name):
    path = index_path(name)
    return read_json(path) if os.path.exists(path) else None


def all_indexes():
    out = []
    base = os.path.join(ROOT, "index")
    for prefix in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        for file in sorted(os.listdir(os.path.join(base, prefix))):
            out.append((prefix, file, read_json(os.path.join(base, prefix, file))))
    return out


def search_data():
    packages = []
    for _, _, index in all_indexes():
        versions = sorted(index["versions"], key=lambda v: version_key(v["version"]))
        live = [v for v in versions if not v["yanked"]]
        newest = (live or versions)[-1]
        entry = {
            "name": index["name"],
            "version": newest["version"],
            "description": index["description"],
            "keywords": index["keywords"],
            "repository": index["repository"],
        }
        if not live:
            entry["yanked"] = True
        packages.append(entry)
    packages.sort(key=lambda p: p["name"])
    return {"packages": packages}


def write_search():
    write_json(os.path.join(ROOT, "search.json"), search_data())


def validate_index(prefix, file, index):
    where = f"index/{prefix}/{file}"
    keys = ["name", "owners", "description", "repository", "keywords", "versions"]
    if not isinstance(index, dict) or list(index) != keys:
        raise Refused(f"{where}: the keys are {', '.join(keys)}, in that order")
    name = index["name"]
    problem = name_problem(name)
    if problem:
        raise Refused(f"{where}: {problem}")
    if file != name + ".json" or prefix != name[:2]:
        raise Refused(f"{where}: belongs at index/{name[:2]}/{name}.json")
    owners = index["owners"]
    if not isinstance(owners, list) or not owners or not all(isinstance(o, str) and LOGIN.fullmatch(o) for o in owners):
        raise Refused(f"{where}: owners is a list of GitHub logins")
    if not isinstance(index["description"], str) or len(index["description"].encode()) > 300:
        raise Refused(f"{where}: the description is text of at most 300 bytes")
    if not isinstance(index["repository"], str) or not REPOSITORY.fullmatch(index["repository"]):
        raise Refused(f"{where}: repository is https://github.com/OWNER/REPO")
    if not isinstance(index["keywords"], list) or not all(isinstance(k, str) and re.fullmatch(r"[a-z0-9-]{1,30}", k) for k in index["keywords"]):
        raise Refused(f"{where}: keywords are lowercase words")
    versions = index["versions"]
    if not isinstance(versions, list) or not versions:
        raise Refused(f"{where}: versions is a list of at least one version")
    seen = []
    vkeys = ["version", "sha256", "dependencies", "plum", "published", "yanked"]
    for v in versions:
        if not isinstance(v, dict) or list(v) != vkeys:
            raise Refused(f"{where}: each version has {', '.join(vkeys)}, in that order")
        if not isinstance(v["version"], str) or not VERSION.fullmatch(v["version"]):
            raise Refused(f"{where}: {v['version']!r} isn't MAJOR.MINOR.PATCH")
        if seen and version_key(v["version"]) <= version_key(seen[-1]):
            raise Refused(f"{where}: versions go from oldest to newest, each once")
        seen.append(v["version"])
        if not isinstance(v["sha256"], str) or not SHA.fullmatch(v["sha256"]):
            raise Refused(f"{where}: {v['version']}: sha256 is 64 lowercase hex digits")
        deps = v["dependencies"]
        if not isinstance(deps, dict) or any(name_problem(d) or not isinstance(r, str) or not RANGE.fullmatch(r) for d, r in deps.items()):
            raise Refused(f"{where}: {v['version']}: dependencies map package names to ranges")
        if not isinstance(v["plum"], str) or not RANGE.fullmatch(v["plum"]):
            raise Refused(f"{where}: {v['version']}: plum is a version range")
        if not isinstance(v["published"], str) or not TIME.fullmatch(v["published"]):
            raise Refused(f"{where}: {v['version']}: published is YYYY-MM-DDTHH:MM:SSZ")
        if not isinstance(v["yanked"], bool):
            raise Refused(f"{where}: {v['version']}: yanked is true or false")
        path = bundle_path(name, v["version"])
        if not os.path.exists(path):
            raise Refused(f"{where}: {v['version']}: packages/{name}/{v['version']}.plumpkg is missing")
        with open(path, "rb") as f:
            raw = f.read()
        if hashlib.sha256(raw).hexdigest() != v["sha256"]:
            raise Refused(f"packages/{name}/{v['version']}.plumpkg doesn't match its sha256 in {where}")
        manifest, _ = check_bundle(raw, name, v["version"])
        if manifest.get("dependencies", {}) != deps:
            raise Refused(f"{where}: {v['version']}: dependencies differ from the bundle's plum.toml")
    return seen


def cmd_validate(_args):
    count = 0
    listed = set()
    for prefix, file, index in all_indexes():
        try:
            for version in validate_index(prefix, file, index):
                listed.add(f"{index['name']}/{version}.plumpkg")
        except (KeyError, TypeError) as e:
            raise Refused(f"index/{prefix}/{file}: malformed ({e})")
        count += 1
    base = os.path.join(ROOT, "packages")
    for name in sorted(os.listdir(base)) if os.path.isdir(base) else []:
        for file in sorted(os.listdir(os.path.join(base, name))):
            if f"{name}/{file}" not in listed:
                raise Refused(f"packages/{name}/{file} isn't in any index file")
    path = os.path.join(ROOT, "search.json")
    if not os.path.exists(path) or read_json(path) != search_data():
        raise Refused("search.json is out of date: run python3 tools/orchard.py search")
    say(f"orchard: {count} packages, {len(listed)} versions, every bundle matches its sha256")


# ------------------------------------------------------------------
# Requests: the issue forms
# ------------------------------------------------------------------

def form_fields(body):
    """The answers of an issue form: '### Label' then the text."""
    fields = {}
    label = None
    lines = []
    for line in body.replace("\r\n", "\n").split("\n"):
        if line.startswith("### "):
            if label is not None:
                fields[label] = "\n".join(lines).strip()
            label = line[4:].strip()
            lines = []
        elif label is not None:
            lines.append(line)
    if label is not None:
        fields[label] = "\n".join(lines).strip()
    return {k: ("" if v == "_No response_" else v) for k, v in fields.items()}


def field(fields, label, pattern, what, optional=False):
    value = fields.get(label, "")
    if value == "" and optional:
        return ""
    if len(value) > 200 or not pattern.fullmatch(value):
        raise Refused(f"**{label}**: `{value[:80]}` isn't {what}")
    return value


def cmd_parse_issue(args):
    kind = args[0] if args else ""
    fields = form_fields(os.environ.get("ISSUE_BODY", ""))
    out = {}
    out["package"] = field(fields, "Package", NAME, "a package name")
    problem = name_problem(out["package"])
    if problem:
        raise Refused(f"**Package**: {problem}")
    if kind == "publish":
        out["repository"] = field(fields, "Repository", REPOSITORY, "https://github.com/OWNER/REPO")
        if out["repository"].endswith(".git"):
            out["repository"] = out["repository"][:-4]
        if out["repository"].rsplit("/", 1)[1] in ("", ".", ".."):
            raise Refused("**Repository**: that isn't a repository's name")
        out["tag"] = field(fields, "Tag", TAG, "a tag (letters, digits, '.', '_', '-', '+', '/')")
        if ".." in out["tag"] or out["tag"].endswith(".lock") or out["tag"].endswith("/"):
            raise Refused("**Tag**: that isn't a tag name git allows")
        out["folder"] = field(fields, "Folder", FOLDER, "a folder like packages/weather", optional=True)
        if any(p in (".", "..") for p in out["folder"].split("/")):
            raise Refused("**Folder**: no '.' or '..'")
    elif kind == "yank":
        out["version"] = field(fields, "Version", VERSION, "a version, MAJOR.MINOR.PATCH")
    else:
        raise Refused("parse-issue publish|yank")
    target = os.environ.get("GITHUB_OUTPUT")
    lines = "".join(f"{k}={v}\n" for k, v in out.items())
    if target:
        with open(target, "a", encoding="utf-8") as f:
            f.write(lines)
    else:
        sys.stdout.write(lines)


# ------------------------------------------------------------------
# Changing the index
# ------------------------------------------------------------------

def option(args, name):
    if name not in args or args.index(name) + 1 >= len(args):
        raise Refused(f"{name} is needed")
    return args[args.index(name) + 1]


def same_repository(a, b):
    def norm(u):
        u = (u or "").strip().rstrip("/")
        return (u[:-4] if u.endswith(".git") else u).lower()
    return norm(a) == norm(b)


def cmd_add_version(args):
    bundle = args[0]
    package = option(args, "--package")
    owner = option(args, "--owner")
    repository = option(args, "--repository")
    if not LOGIN.fullmatch(owner):
        raise Refused(f"'{owner}' isn't a GitHub login")
    with open(bundle, "rb") as f:
        raw = f.read()
    manifest, _ = check_bundle(raw, package)
    meta = manifest["package"]
    version = meta["version"]
    if not VERSION.fullmatch(version):
        raise Refused(f"{version!r} isn't MAJOR.MINOR.PATCH")
    if not same_repository(meta.get("repository"), repository):
        raise Refused(f"plum.toml says repository = {meta.get('repository')!r}, "
                      f"but the request is for {repository}")
    index = load_index(package)
    if index is None:
        index = {"name": package, "owners": [owner], "description": "", "repository": repository,
                 "keywords": [], "versions": []}
        say(f"`{package}` is a new package; **@{owner}** owns it.")
    elif owner.lower() not in (o.lower() for o in index["owners"]):
        raise Refused(f"`{package}` belongs to {', '.join('@' + o for o in index['owners'])}; "
                      f"only an owner can publish it")
    if index["versions"]:
        newest = max(index["versions"], key=lambda v: version_key(v["version"]))["version"]
        if version_key(version) <= version_key(newest):
            raise Refused(f"{package} {version} isn't newer than {newest}, the latest published "
                          f"(yanked ones count): raise the version")
    index["description"] = meta.get("description", "")
    index["repository"] = repository
    index["keywords"] = meta.get("keywords", [])
    index["versions"].append({
        "version": version,
        "sha256": hashlib.sha256(raw).hexdigest(),
        "dependencies": manifest.get("dependencies", {}),
        "plum": meta.get("plum", "*"),
        "published": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "yanked": False,
    })
    path = bundle_path(package, version)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(raw)
    write_json(index_path(package), index)
    write_search()
    validate_index(package[:2], package + ".json", index)
    say(f"Published **{package} {version}** (sha256 `{hashlib.sha256(raw).hexdigest()}`).")
    say(f"Install it with `plum add {package}`.")
    print(f"version={version}")
    target = os.environ.get("GITHUB_OUTPUT")
    if target:
        with open(target, "a", encoding="utf-8") as f:
            f.write(f"version={version}\n")


def cmd_yank(args):
    package, version = args[0], args[1]
    owner = option(args, "--owner")
    index = load_index(package)
    if index is None:
        raise Refused(f"there is no package `{package}`")
    if owner.lower() not in (o.lower() for o in index["owners"]):
        raise Refused(f"only an owner of `{package}` can yank it")
    for v in index["versions"]:
        if v["version"] == version:
            if v["yanked"]:
                raise Refused(f"{package} {version} is already yanked")
            v["yanked"] = True
            write_json(index_path(package), index)
            write_search()
            say(f"Yanked **{package} {version}**. Lock files that have it still install it; "
                f"nothing new will pick it.")
            return
    raise Refused(f"{package} has no version {version}")


def main(argv):
    commands = {
        "validate": cmd_validate,
        "parse-issue": cmd_parse_issue,
        "add-version": cmd_add_version,
        "yank": cmd_yank,
        "search": lambda _a: write_search(),
    }
    if len(argv) < 2 or argv[1] not in commands:
        print(__doc__)
        return 2
    try:
        commands[argv[1]](argv[2:])
    except Refused as e:
        say(f"Refused: {e}")
        return 1
    except (IndexError, OSError) as e:
        say(f"Refused: {e}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
