# PsiCLI

PsiCLI exposes the user-facing `psi` command for setting up and running PSI
packages locally.

## Install

```bash
python -m pip install prosi-psi-cli psihub lllm-core sssn
```

For OS keyring storage, install the optional secure extra:

```bash
python -m pip install "prosi-psi-cli[secure]"
```

## Initialize Local Credentials

Packages can declare launch-time API key requirements in `psi.toml`:

```toml
[requirements.api_keys]
OPENAI_API_KEY = "OpenAI-compatible model access."
ANTHROPIC_API_KEY = "Claude model access."
```

`psi init` checks the selected package and guides setup:

```bash
psi init packages/analyst-tactics
```

By default, `psi` uses the OS keyring when available and falls back to a local
`.env.local` file. You can choose explicitly:

```bash
psi init packages/analyst-tactics --credentials keyring
psi init packages/analyst-tactics --credentials env --env-file .env.local
```

For scripts or CI setup, pass values without echoing them back in command
output:

```bash
psi init packages/analyst-tactics \
  --credentials env \
  --env-file .env.local \
  --set OPENAI_API_KEY=sk-...
```

Common provider names follow the usual Python ecosystem conventions:
`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `TOGETHER_API_KEY`, `GEMINI_API_KEY`,
`GROQ_API_KEY`, `MISTRAL_API_KEY`, `OPENROUTER_API_KEY`, `COHERE_API_KEY`,
`HF_TOKEN`, `TAVILY_API_KEY`, and `EXA_API_KEY`.

## Launch A Package

Download a package folder, then launch its primary resource as a FastAPI
service:

```bash
psi launch packages/analyst-tactics --port 8000
```

Before importing package code, `psi launch` checks declared API key
requirements. It reads values from the current process environment, the local
env file selected with `--env-file`, and the OS keyring unless `--no-keyring` is
set. Missing keys are reported with a `psi init` hint.

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

`psi inspect --json` includes API key readiness without printing secret values.

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
