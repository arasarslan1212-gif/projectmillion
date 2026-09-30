"""Deploy the app (the Dockerfile at the repository root) to a Hugging Face Space, from CI.

Creates the Space if it doesn't exist (private by default), copies the data keys into the Space's secrets, uploads
the build context and waits until the new version runs. On a failed build or start it prints the Space's logs.

Environment:
  HF_TOKEN            a Hugging Face access token with write permission (required)
  HF_SPACE            owner/name of the Space (default: <token owner>/candor)
  HF_SPACE_PRIVATE    "false" to make a new Space public (default: private, i.e. personal use)
  SEC_USER_AGENT, FINNHUB_API_KEY, TIINGO_API_KEY, FRED_API_KEY, FMP_API_KEY
                      copied into the Space's secrets when set (the container reads them at start)
Usage: python deploy/hf_space.py   (needs huggingface_hub; see .github/workflows/deploy.yml)
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from huggingface_hub import HfApi

ROOT = Path(__file__).resolve().parents[1]
SECRETS = [
    "SEC_USER_AGENT",
    "FINNHUB_API_KEY",
    "TIINGO_API_KEY",
    "FRED_API_KEY",
    "FMP_API_KEY",
]
# what the Dockerfile builds from
CONTEXT = [
    "Dockerfile",
    ".dockerignore",
    "deploy/start.sh",
    "apps/web",
    "services/engine",
    "config",
]
SKIP = ("services/engine/tests/",)

CARD = """---
title: Candor
emoji: 📈
colorFrom: indigo
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
short_description: Explainable stock research on live market data
---

# Candor: explainable stock research

Type a US ticker and the engine researches it live: fundamentals from SEC filings, prices and news from the configured
providers, the app's Trust Rating and 12-month range, analysts, risks, and the reasoning behind every number.

Deployed from {source} by its deploy workflow; edit the code there, not here.
For education and information only; not investment advice.
"""


def stage(dest: Path, source: str) -> int:
    # tracked and new files alike, minus what .gitignore excludes (builds, caches, local data)
    cmd = [
        "git",
        "ls-files",
        "-z",
        "--cached",
        "--others",
        "--exclude-standard",
        "--",
        *CONTEXT,
    ]
    out = subprocess.run(cmd, cwd=ROOT, capture_output=True, check=True)
    files = [f for f in out.stdout.decode().split("\0") if f and not f.startswith(SKIP)]
    for f in files:
        (dest / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / f, dest / f)
    (dest / "README.md").write_text(CARD.format(source=source))
    return len(files)


def main() -> int:
    token = os.environ.get("HF_TOKEN")
    if not token:
        print("HF_TOKEN is not set; nothing to deploy.")
        return 1
    api = HfApi(token=token)
    owner = api.whoami()["name"]
    repo = os.environ.get("HF_SPACE") or f"{owner}/candor"
    private = os.environ.get("HF_SPACE_PRIVATE", "true").lower() != "false"
    api.create_repo(
        repo, repo_type="space", space_sdk="docker", private=private, exist_ok=True
    )
    print(f"Space: https://huggingface.co/spaces/{repo}")

    set_keys = [k for k in SECRETS if os.environ.get(k)]
    for k in set_keys:
        api.add_space_secret(repo, k, os.environ[k])
    print(
        f"Secrets set: {', '.join(set_keys) or 'none (the app will run on the synthetic market)'}"
    )

    source = (
        os.environ.get("GITHUB_SERVER_URL", "https://github.com")
        + "/"
        + os.environ.get("GITHUB_REPOSITORY", "")
    )
    with tempfile.TemporaryDirectory() as tmp:
        n = stage(Path(tmp), source)
        sha = os.environ.get("GITHUB_SHA", "")[:7]
        info = api.upload_folder(
            repo_id=repo,
            repo_type="space",
            folder_path=tmp,
            commit_message=f"Deploy {sha}".strip(),
            delete_patterns=[
                "**"
            ],  # an exact copy: files removed from the app go from the Space too
        )
    print(f"Uploaded {n} files: {getattr(info, 'commit_url', '')}")

    # The Space may report its previous version as running for a moment before the new build starts.
    for _ in range(18):
        if api.get_space_runtime(repo).stage != "RUNNING":
            break
        time.sleep(5)
    runtime = api.wait_for_space(repo, timeout=40 * 60, poll_interval=15)
    print(f"Space stage: {runtime.stage}")
    if runtime.stage != "RUNNING":
        build = runtime.stage in ("BUILD_ERROR", "CONFIG_ERROR")
        print(f"--- {'build' if build else 'run'} logs (last lines) ---")
        try:
            lines = list(api.fetch_space_logs(repo, build=build))
            print("\n".join(lines[-80:]))
        except Exception as e:  # noqa: BLE001 - the logs are a diagnostic; their absence mustn't hide the stage
            print(f"(logs unavailable: {e})")
        return 1
    host = (
        api.space_info(repo).host
        or f"https://{repo.replace('/', '-').replace('_', '-').lower()}.hf.space"
    )
    print(f"Running: {host}")
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a") as fh:
            fh.write(
                f"### Deployed\n\n- App: {host}\n- Space: https://huggingface.co/spaces/{repo}\n"
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
