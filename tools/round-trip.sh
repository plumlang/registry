#!/bin/sh
# SPDX-License-Identifier: MIT WITH Plumlang-trademarks
#
# The whole road a package travels, offline: publish examples/hello-orchard
# into a fresh copy of the registry the way the publish workflow does
# (plum package, then tools/orchard.py add-version), check the index, then
# `plum add` it into a new project from that copy, through
# PLUM_ORCHARD=file://..., and run it. Also checks that the bundle in this
# repository is the one `plum package` makes from the example's source.
#
# Usage: sh tools/round-trip.sh /path/to/plum
set -u
PLUM=${1:?usage: sh tools/round-trip.sh /path/to/plum}
case $PLUM in
    /*) ;;
    *) PLUM=$(pwd)/$PLUM ;;
esac
root=$(cd "$(dirname "$0")/.." && pwd)
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
fail() {
    echo "round trip: FAIL: $*"
    exit 1
}

PLUM_HOME="$tmp/home"
export PLUM_HOME NO_COLOR=1

# 1. Package the example, as the workflow does with a checked-out tag.
cp -R "$root/examples/hello-orchard" "$tmp/source"
(cd "$tmp/source" && "$PLUM" package --out "$tmp") >"$tmp/package.txt" 2>&1 ||
    { cat "$tmp/package.txt"; fail "plum package"; }
cat "$tmp/package.txt"
bundle="$tmp/hello-orchard-1.0.0.plumpkg"

# 2. The bundle committed here is that same bundle, byte for byte.
cmp -s "$bundle" "$root/packages/hello-orchard/1.0.0.plumpkg" ||
    fail "packages/hello-orchard/1.0.0.plumpkg isn't what plum package makes of examples/hello-orchard"

# 3. Publish it into an empty registry.
mkdir -p "$tmp/registry"
cp -R "$root/tools" "$tmp/registry/tools"
python3 "$tmp/registry/tools/orchard.py" add-version "$bundle" --package hello-orchard \
    --owner Circuit-Overtime --repository https://github.com/plumlang/registry || fail "add-version"
python3 "$tmp/registry/tools/orchard.py" validate || fail "validate"
# publishing the same version again is refused
python3 "$tmp/registry/tools/orchard.py" add-version "$bundle" --package hello-orchard \
    --owner Circuit-Overtime --repository https://github.com/plumlang/registry >/dev/null &&
    fail "the same version was published twice"
# and someone who doesn't own the name can't publish it
python3 "$tmp/registry/tools/orchard.py" add-version "$bundle" --package hello-orchard \
    --owner someone-else --repository https://github.com/plumlang/registry >/dev/null &&
    fail "a stranger published a version"

# validate notices a bundle changed after it was published
published="$tmp/registry/packages/hello-orchard/1.0.0.plumpkg"
cp "$published" "$tmp/kept.plumpkg"
sed 's/from the orchard/from elsewhere/' "$tmp/kept.plumpkg" >"$published"
python3 "$tmp/registry/tools/orchard.py" validate >/dev/null && fail "validate missed a changed bundle"
cp "$tmp/kept.plumpkg" "$published"

# 4. Add it to a project, from that registry, and run it.
PLUM_ORCHARD="file://$tmp/registry"
export PLUM_ORCHARD
mkdir -p "$tmp/app"
cd "$tmp/app" || exit 1
printf '[package]\nname = "app"\nversion = "0.1.0"\nentry = "main.plum"\n' >plum.toml
printf 'seed hello_orchard\ndrop(hello_orchard.greet("Ada"))\ndrop(hello_orchard.cheer("Ada"))\n' >main.plum
"$PLUM" search greeting | grep -q '^hello-orchard 1.0.0' || fail "plum search"
"$PLUM" add hello-orchard || fail "plum add"
grep -q '^hello-orchard = "^1.0.0"$' plum.toml || fail "plum.toml has no dependency"
grep -q "^sha256 = \"$(sed -n 's/.*"sha256": "\([0-9a-f]*\)".*/\1/p' "$tmp/registry/index/he/hello-orchard.json")\"$" plum.lock ||
    fail "plum.lock doesn't have the published sha256"
out=$("$PLUM" run .) || fail "plum run"
[ "$out" = "$(printf 'Hello, Ada, from the orchard!\nHELLO, ADA, FROM THE ORCHARD!')" ] || fail "the program printed: $out"

# 5. Yanking keeps locked installs working and stops new resolutions.
cd "$tmp/registry" || exit 1
python3 tools/orchard.py yank hello-orchard 1.0.0 --owner Circuit-Overtime || fail "yank"
python3 tools/orchard.py validate || fail "validate after the yank"
cd "$tmp/app" || exit 1
rm -rf "$PLUM_HOME"
"$PLUM" install || fail "a yanked version from plum.lock"
mkdir -p "$tmp/app2"
cd "$tmp/app2" || exit 1
printf '[package]\nname = "app2"\nversion = "0.1.0"\nentry = "main.plum"\n' >plum.toml
"$PLUM" add hello-orchard 2>"$tmp/err" && fail "a yanked version was resolved"
grep -q "yanked" "$tmp/err" || fail "the error doesn't say the version was yanked"

echo "round trip: published, validated, added, run and yanked hello-orchard 1.0.0"
