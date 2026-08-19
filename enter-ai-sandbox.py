#!/usr/bin/env python3

# Unified entrypoint for Claude Code or OpenCode AI sandbox environments.
# Uses the AI workspace image built daily in GitHub Actions.
#
# I purposely do not use Toolbox for this as I don't want the AI to have
# unfettered access to my homedir. It will mount the provided host_workdir(s)
# into the container under /workdir.
#
# This script will also conditionally check for the presence of a kubeconfig
# file in the workdir root and if one is found, will set the KUBECONFIG env var
# to point to it and mount it into the container.
#
# Flags:
#   --harness      opencode (default) | claude
#   --backend      vertex (default)   | modelscorp
#   --pullspec     override the container image pullspec
#   --codeburn     run the codeburn tool to analyze AI spend (bypasses normal sandbox)
#   --with-skills  keep built-in SKILL.md files in place (default: remove them)
#   --no-cache     skip mounting the claude-project-cache and opencode-cache named volumes
#
# Valid combinations:
#   --harness opencode --backend vertex      - OpenCode via GCP Vertex AI
#   --harness opencode --backend modelscorp  - OpenCode via Models Corp (APIcast)
#   --harness claude   --backend vertex      - Claude Code via GCP Vertex AI
#   --harness claude   --backend modelscorp  - INVALID
#
# For modelscorp, API keys are read from ~/.creds/apikeys.txt
# (format: "provider-id apikey" one per line) and env var names from
# ~/.creds/envvars.txt (format: "provider-id ENV_VAR_NAME" one per line).
# The two files are joined on provider-id and the corresponding
# --env ENV_VAR_NAME=apikey arguments are injected into the container.

# To use:
# 1. Provide a workspace name via --workspace.
# 2. Provide one or more host workdirs to mount as positional arguments.
# Example: ./enter-ai-sandbox.py --workspace myworkspace /path/to/dir1 /path/to/dir2
# Example: ./enter-ai-sandbox.py --harness claude --workspace myworkspace /path/to/dir1
# Example: ./enter-ai-sandbox.py --backend modelscorp --workspace myworkspace /path/to/dir1
# Example: ./enter-ai-sandbox.py --workspace myworkspace --pullspec localhost/ai-helpers-no-podman:latest /path/to/dir1
# Example: ./enter-ai-sandbox.py --codeburn

import argparse
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_PULLSPEC = "quay.io/zzlotnik/toolbox:ai-helpers-fedora-44"
CONTAINER_HOME = Path("/home/claude")
GCP_PROJECT_ID = "*****"
GCP_VERTEX_REGION = "global"


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class SandboxConfig:
    harness: str
    backend: str
    workspace: str
    pullspec: str
    host_workdirs: list[str]
    codeburn: bool
    with_skills: bool
    no_cache: bool


# ---------------------------------------------------------------------------
# Argument parsing
# ---------------------------------------------------------------------------

def parse_args() -> SandboxConfig:
    """Parse command-line arguments and return a SandboxConfig.

    All named flags may appear anywhere among the arguments.
    Remaining positional args are treated as host workdirs.
    """
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--harness", choices=["opencode", "claude"], default="opencode")
    ap.add_argument("--backend", choices=["vertex", "modelscorp"], default="vertex")
    ap.add_argument("--pullspec", default=DEFAULT_PULLSPEC)
    ap.add_argument("--workspace", default=None)
    ap.add_argument("--codeburn", action="store_true", default=False)
    ap.add_argument("--with-skills", action="store_true", default=False)
    ap.add_argument("--no-cache", action="store_true", default=False)

    known, remainder = ap.parse_known_args()

    pullspec = known.pullspec
    if known.codeburn and known.pullspec == DEFAULT_PULLSPEC:
        pullspec = DEFAULT_CODEBURN_PULLSPEC

    if known.codeburn:
        return SandboxConfig(
            harness=known.harness,
            backend=known.backend,
            workspace=known.workspace or "",
            pullspec=pullspec,
            host_workdirs=[],
            codeburn=True,
            with_skills=known.with_skills,
            no_cache=known.no_cache,
        )

    # Validate combination
    if known.harness == "claude" and known.backend == "modelscorp":
        sys.exit(
            "Error: --harness claude is not compatible with --backend modelscorp. "
            "Use --backend vertex with --harness claude."
        )

    if not known.workspace:
        _usage(ap)

    if not remainder:
        _usage(ap)

    return SandboxConfig(
        harness=known.harness,
        backend=known.backend,
        workspace=known.workspace,
        pullspec=pullspec,
        host_workdirs=remainder,
        codeburn=False,
        with_skills=known.with_skills,
        no_cache=known.no_cache,
    )


def _usage(ap: argparse.ArgumentParser) -> None:
    name = Path(sys.argv[0]).name
    print(
        f"Usage: {name} --workspace WORKSPACE <host_workdir1> [host_workdir2] ...\n"
        "       [--harness opencode|claude] [--backend vertex|modelscorp] [--pullspec PULLSPEC]\n"
        f"       {name} --codeburn\n"
        "\n"
        "Defaults: --harness opencode --backend vertex"
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Workspace name normalisation
# ---------------------------------------------------------------------------

def _workspace_prefix(harness: str, backend: str) -> str:
    if harness == "claude":
        return "claude-"
    # opencode
    if backend == "modelscorp":
        return "opencode-modelscorp-"
    return "opencode-"


def normalize_workspace(cfg: SandboxConfig) -> str:
    """Strip any existing prefix then re-add it (idempotency guard)."""
    prefix = _workspace_prefix(cfg.harness, cfg.backend)
    return prefix + cfg.workspace.removeprefix(prefix)


# ---------------------------------------------------------------------------
# Credential preflight
# ---------------------------------------------------------------------------

def _read_kv_file(path: Path) -> dict[str, str]:
    """Parse a whitespace-separated key-value file, ignoring blank lines and comments."""
    result: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split(None, 1)
        if len(parts) == 2:
            result[parts[0]] = parts[1]
    return result


def preflight_credentials(cfg: SandboxConfig) -> list[str]:
    """Validate required credential files.

    Returns a flat list of ['--env', 'VAR=value', ...] args for the
    modelscorp backend; empty list for vertex.
    """
    home = Path.home()

    if cfg.backend == "vertex":
        adc = home / ".config/gcloud/application_default_credentials.json"
        if not adc.is_file():
            sys.exit(f"{adc} does not exist, exiting")
        return []

    # modelscorp
    opencode_config = home / ".creds/opencode.json"
    apikeys_file = home / ".creds/apikeys.txt"
    envvars_file = home / ".creds/envvars.txt"

    for f in (opencode_config, apikeys_file, envvars_file):
        if not f.is_file():
            sys.exit(f"{f} does not exist, exiting")

    # Build provider-id -> env-var-name map from envvars.txt.
    provider_env_map = _read_kv_file(envvars_file)

    # Join with apikeys.txt on provider-id.
    api_keys = _read_kv_file(apikeys_file)

    env_args: list[str] = []
    for provider_id, api_key in api_keys.items():
        if provider_id in provider_env_map:
            env_args += ["--env", f"{provider_env_map[provider_id]}={api_key}"]
        else:
            print(
                f"Warning: no env var mapping found for provider '{provider_id}', skipping",
                file=sys.stderr,
            )

    return env_args


# ---------------------------------------------------------------------------
# Registry auth file discovery
# ---------------------------------------------------------------------------

def find_registry_auth() -> Path | None:
    """Return the first existing container registry auth file, or None."""
    home = Path.home()
    candidates: list[Path] = []

    registry_auth_file_env = os.environ.get("REGISTRY_AUTH_FILE", "")
    if registry_auth_file_env:
        candidates.append(Path(registry_auth_file_env))

    xdg_runtime = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    candidates.append(xdg_runtime / "containers/auth.json")

    docker_config = Path(os.environ.get("DOCKER_CONFIG", home / ".docker"))
    candidates.append(docker_config / "config.json")

    candidates += [
        home / ".config/containers/auth.json",
        home / ".docker/config.json",
    ]

    return next((p for p in candidates if p.is_file()), None)


# ---------------------------------------------------------------------------
# Container helpers
# ---------------------------------------------------------------------------

def container_exists(name: str) -> bool:
    result = subprocess.run(
        ["podman", "container", "inspect", name],
        capture_output=True,
    )
    return result.returncode == 0


# ---------------------------------------------------------------------------
# Main podman args builder
# ---------------------------------------------------------------------------

def build_podman_args(
    cfg: SandboxConfig,
    api_key_env_args: list[str],
) -> tuple[list[str], bool]:
    """Build the full argument list for `podman run` (excluding the image and
    workspace-name positional).

    Returns (args, trust_anchor_dir_mounted).
    """
    home = Path.home()
    primary_workdir = Path(cfg.host_workdirs[0])

    jira_api_token = (home / ".creds/zzlotnik-jira-cloud-api-key").read_text().strip()
    gh_token = (home / ".creds/gh-readonly-token").read_text().strip()

    args: list[str] = [
        "--detach",
        "--rm",
        "--privileged",
        "--uidmap", "1000:0:1",
        "--uidmap", "0:1:1000",
        "--uidmap", "1001:1001:65536",
        "--gidmap", "1000:0:1",
        "--gidmap", "0:1:1000",
        "--gidmap", "1001:1001:65536",
        "--name", cfg.workspace,
        "--network=host",
        f"--workdir=/workdir/{primary_workdir.name}",
        "--env", "JIRA_URL=https://redhat.atlassian.net",
        "--env", "JIRA_USER=zzlotnik@redhat.com",
        "--env", f"JIRA_API_TOKEN={jira_api_token}",
        "--env", f"GH_TOKEN={gh_token}",
        "--env", "LANG=en_US.UTF-8",
        "--env", "LC_ALL=en_US.UTF-8",
        "--env", f"AI_TOOL={cfg.harness}",
        "--env", f"WITH_SKILLS={'true' if cfg.with_skills else 'false'}",
        "--volume", f"{home}/Repos/containerfiles/ai-sandbox/ai-sandbox-entrypoint.sh:/entrypoint.sh:ro,z",
        "--entrypoint", "/entrypoint.sh",
    ]

    # CA trust anchor mount (Toolbox-aware)
    trust_anchor_dir = Path("/etc/pki/ca-trust/source/anchors")
    toolbox_path = Path("/run/host") / trust_anchor_dir.relative_to("/")
    trust_anchor_dir_mounted = False

    if toolbox_path.is_dir():
        args += ["--volume", f"{toolbox_path}:{trust_anchor_dir}:ro"]
        trust_anchor_dir_mounted = True
    elif trust_anchor_dir.is_dir():
        args += ["--volume", f"{trust_anchor_dir}:{trust_anchor_dir}:ro"]
        trust_anchor_dir_mounted = True

    # Harness + backend specific env vars and volume mounts
    if cfg.harness == "claude":
        # claude only supports vertex
        args += [
            "--env", "CLAUDE_CODE_USE_VERTEX=1",
            "--env", f"CLOUD_ML_REGION={GCP_VERTEX_REGION}",
            "--env", f"ANTHROPIC_VERTEX_PROJECT_ID={GCP_PROJECT_ID}",
            "--volume", f"{home}/.config/gcloud:{CONTAINER_HOME}/.config/gcloud:z,U",
        ]
        if not cfg.no_cache:
            args += ["--volume", f"claude-project-cache:{CONTAINER_HOME}/.claude/projects:z,U"]
    elif cfg.backend == "vertex":
        args += [
            "--env", f"GOOGLE_CLOUD_PROJECT={GCP_PROJECT_ID}",
            "--env", f"VERTEX_LOCATION={GCP_VERTEX_REGION}",
            "--env", f"GOOGLE_APPLICATION_CREDENTIALS={CONTAINER_HOME}/.config/gcloud/application_default_credentials.json",
            "--volume", f"{home}/.config/gcloud:{CONTAINER_HOME}/.config/gcloud:z,U",
        ]
        if not cfg.no_cache:
            args += ["--volume", f"opencode-cache:{CONTAINER_HOME}/.local/share/opencode:z,U"]
    else:
        # opencode + modelscorp
        args += [
            "--volume", f"{home}/.creds/opencode.json:{CONTAINER_HOME}/.config/opencode/opencode.json:z,U,ro",
        ]
        args += api_key_env_args

    # Conditionally mount ~/.config/gws
    gws_dir = home / ".config/gws"
    if gws_dir.is_dir():
        args += ["--volume", f"{gws_dir}:{CONTAINER_HOME}/.config/gws:z,U"]

    # Mount all provided workdirs
    for d in cfg.host_workdirs:
        p = Path(d)
        args += ["--volume", f"{p}:/workdir/{p.name}:z"]

    # Registry auth file
    auth_file = find_registry_auth()
    if auth_file is not None:
        args += ["--volume", f"{auth_file}:{CONTAINER_HOME}/.docker/config.json:z"]

    # Kubeconfig injection (first match wins)
    for d in cfg.host_workdirs:
        kubeconfig = Path(d) / "kubeconfig"
        if kubeconfig.is_file():
            args += [
                "--env", "KUBECONFIG=/kubeconfig",
                "--volume", f"{kubeconfig}:/kubeconfig:z",
            ]
            break

    return args, trust_anchor_dir_mounted


# ---------------------------------------------------------------------------
# Codeburn
# ---------------------------------------------------------------------------

DEFAULT_CODEBURN_PULLSPEC = "localhost/codeburn:latest"


def run_codeburn(pullspec: str) -> None:
    """Run the codeburn tool to analyze AI spend.

    Mounts the claude-project-cache, opencode-cache, and codeburn persistent
    volumes then executes the `codeburn` binary inside the container.
    Replaces the current process (exec) so TTY handling works correctly.
    """
    if "localhost" not in pullspec:
        subprocess.run(["podman", "pull", pullspec], check=True)

    os.execvp("podman", [
        "podman", "run", "-it",
        "--rm",
        "--entrypoint=/bin/bash",
        "--volume", f"claude-project-cache:{CONTAINER_HOME}/.claude/projects:ro,z",
        "--volume", f"opencode-cache:{CONTAINER_HOME}/.local/share/opencode:ro,z",
        "--volume", f"codeburn:{CONTAINER_HOME}/.cache/codeburn:rw,z",
        pullspec,
        "-c", "codeburn",
    ])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    cfg = parse_args()

    if cfg.codeburn:
        run_codeburn(cfg.pullspec)
        return  # unreachable; exec replaces the process

    cfg.workspace = normalize_workspace(cfg)

    # Validate workdirs
    for d in cfg.host_workdirs:
        if not Path(d).is_dir():
            sys.exit(f"Host workdir {d} does not exist")

    # Credential preflight
    api_key_env_args = preflight_credentials(cfg)

    if not container_exists(cfg.workspace):
        if "localhost" not in cfg.pullspec:
            subprocess.run(["podman", "pull", cfg.pullspec], check=True)

        podman_args, trust_anchor_dir_mounted = build_podman_args(cfg, api_key_env_args)

        subprocess.run(
            ["podman", "run"] + podman_args + [cfg.pullspec, cfg.workspace],
            check=True,
        )

        if trust_anchor_dir_mounted:
            subprocess.run(
                ["podman", "exec", "-u=root", "-it", cfg.workspace, "update-ca-trust"],
                check=True,
            )

        time.sleep(1)

    # Replace the current process with the tmux attach so signals and TTY
    # handling work exactly as if the shell had exec'd it.
    os.execvp("podman", ["podman", "exec", "-it", cfg.workspace, "tmux", "attach-session", "-t", cfg.workspace])


if __name__ == "__main__":
    main()
