# Contributing to Orchard

Thank you for helping. This repository is the registry's index and the
tools around it. Two kinds of contribution come here, by different roads.

## Publishing or yanking a package

Use the issue forms, not pull requests:

- **Publish a package**: run `plum publish` in your package's directory
  and follow the link it prints, or open the form by hand. See
  [README.md](README.md#publishing-a-package).
- **Yank a version**: the "Yank a version" form, as an owner of the
  package.

Pull requests that edit `index/`, `packages/` or `search.json` by hand are
closed: the index changes only through the workflows, so every bundle is one
Orchard built from a tag. The exception is a fix by the maintainers, such as
removing a package that breaks the rules.

## Changing the tools, workflows or docs

1. Open an issue first for anything larger than a fix, so we can agree on
   the change.
2. Work on a branch and open a pull request against `main`. Each pull
   request does one thing.
3. Keep the tools to the Python standard library, and pin every action by
   its full commit SHA, as the workflows do.
4. Treat issue text as untrusted: it reaches the shell only through
   environment variables, and `tools/orchard.py` checks every field with a
   strict pattern before anything uses it. Never write
   `${{ github.event.issue... }}` inside a `run:` script.
5. Run the checks before you push:

   ```sh
   python3 tools/orchard.py validate
   sh tools/round-trip.sh /path/to/plum
   ```

   `validate.yml` runs both on every pull request.
6. Sign off every commit (`git commit -s`): the
   [Developer Certificate of Origin](https://developercertificate.org)
   applies. There is no CLA.

The formats (index files, bundles, `search.json`) are defined in
[docs/orchard.md](https://github.com/plumlang/plumlang/blob/main/docs/orchard.md)
in plumlang/plumlang, together with `plum`. A change to a format changes
`plum`, that document and `tools/orchard.py` together.

The `.github` community files and shared workflows (`CODEOWNERS`, the pull
request template, the bug and feature forms, `elixpo-ci.yml` and the rest)
are copied from plumlang/plumlang by its `tools/sync-github.sh`. Change them
there, not here.

## Conduct and security

Be kind and constructive; the Plumlang
[code of conduct](https://github.com/plumlang/plumlang/blob/main/CODE_OF_CONDUCT.md)
applies here. Report security problems, in the registry or in a package,
privately to hello@elixpo.com.

By contributing you agree that your contribution is licensed as
[LICENSE](LICENSE) describes.
