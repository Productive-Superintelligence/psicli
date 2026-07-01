# Psi CLI

`psi` is the user-facing command line for running PSI packages locally.

## Install

```bash
python -m pip install prosi-psi-cli psihub lllm-core sssn
```

## Launch A Package

Download a package folder, then launch its primary resource as a FastAPI
service:

```bash
psi launch packages/analyst-tactics --port 8000
```

The launcher reads `psi.toml` and serves the package's primary resource:

- `tactics.*` resources become LLLM FastAPI tactic services with `/run`;
- `services.*` resources use their FastAPI entrypoint, or fall back to the
  service's declared tactic when present;
- `channels.*` resources become SSSN store services with `/channels`,
  `/events`, `/subscriptions`, `/artifacts`, and `/snapshots`.

Inspect what will be served without starting the server:

```bash
psi inspect packages/analyst-tactics
```

Launch a specific resource when a package has several services:

```bash
psi launch packages/society-sentinel --resource services.sentinel_api --port 8130
```

Direct Python entrypoints work too:

```bash
psi launch my_package.service:create_app --port 8000
```

`psi launch` is intentionally a local server starter. PsiHub owns package
validation, cards, downloads, and metadata; AAAX owns higher-level strategy
composition.
