# Orchard

Orchard is the package registry of [Plumlang](https://github.com/plumlang/plumlang),
a small, fast, memory-safe programming language. This repository is the
registry: an index of every published package, the packages themselves, and
the workflows that publish them. There is no server and there are no
accounts; your GitHub identity is your identity, and every change to the
index is a commit you can read.

```sh
plum search weather
plum add weather
```

```plum
seed weather

drop(weather.forecast("Kolkata"))
```

The `plum` side (the commands, `plum.toml`, `plum.lock`, version ranges and
the formats below in full) is documented in
[docs/orchard.md](https://github.com/plumlang/plumlang/blob/main/docs/orchard.md).

## What is here

| Path | What |
|---|---|
| `index/NA/NAME.json` | One file per package, under the first two letters of its name: its owners, description, repository, keywords, and every version with its sha256, dependencies, the Plumlang versions it supports, when it was published, and whether it is yanked. |
| `packages/NAME/VERSION.plumpkg` | The bundles: each version's files, as `plum package` made them from the release's tag. |
| `search.json` | Every package's name, newest version, description and keywords, for `plum search` and the website. |
| `examples/hello-orchard/` | The source of `hello-orchard`, the example package. |
| `tools/orchard.py` | Checks the index and records publishes and yanks; used by the workflows. |
| `tools/round-trip.sh` | Publishes the example into a fresh index, then adds and runs it with a real `plum`. |
| `.github/workflows/` | `publish.yml`, `yank.yml` and `validate.yml`, and the shared Elixpo workflows. |

`plum` reads the index from `https://raw.githubusercontent.com/plumlang/registry/main`,
or from the URL in `PLUM_ORCHARD`. A mirror or a CDN can serve the same
files at another address; nothing in `plum` changes.

## Publishing a package

1. Write the package: a directory with a `plum.toml` that has a `name`, a
   `version`, an `entry` (and a `lib`, if what `seed NAME` imports isn't the
   entry), and `repository = "https://github.com/OWNER/REPO"`. The
   repository must be public.
2. In that directory, run `plum package`. It checks the manifest, runs
   `plum check` on every `.plum` file, keeps the files a package may hold
   (`.plum` files, and `plum.toml`, `README.md` and `LICENSE*` at the top),
   and checks that the bundle is under 1 MB. Fix anything it reports.
3. Commit, tag the release (for example `v1.2.0`), and push the tag.
4. Run `plum publish`. It checks the package again and prints a link that
   opens a publish request here, filled in with the package, the repository
   and the tag (`plum publish --tag TAG` for another tag). If the package
   isn't at the top of its repository, fill in its folder.
5. Submit the request while signed in to GitHub as yourself.

The publish workflow then checks out the tag, runs `plum package` on it
with the latest `plum`, checks the name, the version and that you may
publish it, commits the bundle and the index, and replies on the issue. If
something is wrong it says what; fix it and edit the issue to try again.

The bundle Orchard serves is the one it built from your tag, so what people
install is exactly what is in your repository at that tag.

## Rules

### Names

- A name has 2 to 40 characters: lowercase letters, digits and single
  `-`, starting with a letter and not ending with `-`. In code, a `-` is
  written `_`: `seed hello_orchard`.
- Names of Plumlang's standard modules (`json`, `net`, `hash`, ...) and
  `plum`, `std`, `stdlib` and `orchard` are reserved, as are keywords.
- **The first publisher of a name owns it.** Only its owners publish new
  versions and yank. An owner can ask, in an issue, for others to be added
  as owners.
- Names are not reserved in advance and are not for sale.

### Versions

- Versions are `MAJOR.MINOR.PATCH`. Each new version must be higher than
  every version published before, yanked ones included.
- A published version never changes and is never deleted: its sha256 is in
  people's lock files.
- **Yanking**: an owner opens a "Yank a version" issue. A yanked version
  stays installable from lock files that already have it, so nobody's
  build breaks, but `plum` never chooses it again. Publish a fixed, higher
  version to replace it.

### Content policy

By publishing you confirm that you may publish the code under the licence
it names. Packages that break these rules are removed, and their names may
be taken back:

- **No malware.** Nothing that harms, spies on, or takes over the machines
  or accounts of the people who use it, or that hides what it does.
- **No squatting.** Don't publish names you don't intend to maintain, empty
  or placeholder packages, or names chosen to be mistaken for another
  package or project.
- **No secrets.** Don't publish passwords, tokens, keys or other people's
  personal data. A published version can't be changed: if you published a
  secret, revoke it at once, then report it.
- No code you have no right to publish, and nothing illegal.

Report a package that breaks the rules, or a security problem in one, to
hello@elixpo.com, not in a public issue.

## Running the registry

What the maintainers set up, in the repository's settings:

- **Labels** `publish` and `yank`, which the issue forms add and the
  workflows look for.
- **Actions → General → Workflow permissions**: "Read and write
  permissions" may stay off; the workflows ask for `contents: write` and
  `issues: write` themselves, and only those jobs.
- **Branch protection on `main`**: the publish and yank workflows push their
  commits to `main` with the workflow's token, so `github-actions[bot]` (or
  the GitHub Actions app) must be allowed to bypass the pull request rule.
  Changes by people still go through pull requests, checked by
  `validate.yml`.
- **Variables** (Actions → Variables), both optional:
  - `PLUM_SOURCE`: `release` installs the latest release of `plum` with its
    `install.sh`; `commit` (the default, until a release has `plum
    package`) builds it from source.
  - `PLUM_COMMIT`: the plumlang/plumlang commit to build, a full SHA.
    Default: the one pinned in the workflows.

No secrets are needed: the workflows use the token GitHub gives each run.

## Contributing

Changes to the tools, workflows and documentation are welcome; see
[CONTRIBUTING.md](CONTRIBUTING.md). Packages are published through the
issue form, not by pull request.

## Licence

The code here is MIT and the documentation CC-BY-4.0, both with the
Plumlang trademarks exception; the index metadata (`index/`,
`search.json`) is CC0-1.0, free for anyone to mirror and build on. Each
package keeps its own licence. See [LICENSE](LICENSE) and
[NOTICE](NOTICE).

---

Orchard is an [Elixpo](https://elixpo.com) production, created by
Ayushman Bhattacharya, Subhro Koley and Rohan Hudati.
