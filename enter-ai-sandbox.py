#!/usr/bin/env python3

# Unified entrypoint for Claude Code or OpenCode AI sandbox environments.
# Uses the AI workspace image built daily in GitHub Actions, including codeburn.
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
#   --harness      opencode (default) | claude | codex
#   --backend      openai (default)   | vertex | modelscorp
#   --pullspec     override the container image pullspec
#   --entrypoint   override entrypoint with an absolute path from the host (mounted to /entrypoint)
#   --codeburn     run the codeburn tool to analyze AI spend (bypasses normal sandbox)
#   --no-cache     skip mounting the claude-project-cache and opencode-cache named volumes
#
# Valid combinations:
#   --harness opencode --backend openai     - OpenCode via OpenAI (default)
#   --harness opencode --backend vertex      - OpenCode via GCP Vertex AI
#   --harness opencode --backend modelscorp  - OpenCode via Models Corp (APIcast)
#   --harness claude   --backend vertex      - Claude Code via GCP Vertex AI (auto-selected)
#   --harness claude   --backend modelscorp  - INVALID
#   --harness claude   --backend openai     - INVALID
#   --harness codex    --backend openai     - Codex via OpenAI (auto-selected)
#   --harness codex    --backend vertex      - INVALID
#   --harness codex    --backend modelscorp  - INVALID
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
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants & Declarative Mappings
# ---------------------------------------------------------------------------

DEFAULT_PULLSPEC = "quay.io/zzlotnik/toolbox:ai-helpers-fedora-44"
CONTAINER_HOME = Path("/home/claude")
GCP_PROJECT_ID = "*****"
HOME_DIR = Path.home()
GCP_VERTEX_REGION = "global"
GCP_CONFIG_DIR = HOME_DIR / ".config/gcloud"
GCP_ADC_FILE = GCP_CONFIG_DIR / "application_default_credentials.json"
OPENAI_AUTH_FILE = HOME_DIR / ".creds/openai-auth.json"
MODELSCORP_CONFIG_FILE = HOME_DIR / ".creds/opencode.json"
MODELSCORP_APIKEYS_FILE = HOME_DIR / ".creds/apikeys.txt"
MODELSCORP_ENVVARS_FILE = HOME_DIR / ".creds/envvars.txt"
JIRA_API_TOKEN_FILE = HOME_DIR / ".creds/zzlotnik-jira-cloud-api-key"
GH_TOKEN_FILE = HOME_DIR / ".creds/gh-readonly-token"

VALID_COMBINATIONS: set[tuple[str, str]] = {
    ("opencode", "vertex"),
    ("opencode", "modelscorp"),
    ("opencode", "openai"),
    ("claude", "vertex"),
    ("codex", "openai"),
}

WORKSPACE_PREFIX_MAP: dict[tuple[str, str], str] = {
    ("claude", "vertex"): "claude-",
    ("codex", "openai"): "codex-openai-",
    ("opencode", "vertex"): "opencode-",
    ("opencode", "modelscorp"): "opencode-modelscorp-",
    ("opencode", "openai"): "opencode-openai-",
}


# ---------------------------------------------------------------------------
# File & Environment Helpers
# ---------------------------------------------------------------------------

def _require_file(path: Path) -> Path:
    """Ensure file exists or abort execution."""
    if not path.is_file():
        sys.exit(f"{path} does not exist, exiting")
    return path


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


def _add_file_secret_env(
    args: list[str],
    file_path: Path,
    env_var: str,
    extra_env: dict[str, str] | None = None,
) -> None:
    """Append environment variable(s) if secret file exists."""
    if file_path.is_file():
        if extra_env:
            for k, v in extra_env.items():
                args += ["--env", f"{k}={v}"]
        args += ["--env", f"{env_var}={file_path.read_text().strip()}"]


def _get_trust_anchor_mount() -> tuple[list[str], bool]:
    """Resolve host PKI trust anchor directory (Toolbox vs native host)."""
    trust_anchor_dir = Path("/etc/pki/ca-trust/source/anchors")
    toolbox_path = Path("/run/host") / trust_anchor_dir.relative_to("/")
    if toolbox_path.is_dir():
        return ["--volume", f"{toolbox_path}:{trust_anchor_dir}:ro"], True
    if trust_anchor_dir.is_dir():
        return ["--volume", f"{trust_anchor_dir}:{trust_anchor_dir}:ro"], True
    return [], False


def _get_kubeconfig_mount(host_workdirs: list[str]) -> list[str]:
    """Find and return volume mount args for the first discovered kubeconfig file."""
    for d in host_workdirs:
        kubeconfig = Path(d) / "kubeconfig"
        if kubeconfig.is_file():
            return [
                "--env", "KUBECONFIG=/kubeconfig",
                "--volume", f"{kubeconfig}:/kubeconfig:z",
            ]
    return []


def find_registry_auth() -> Path | None:
    """Return the first existing container registry auth file, or None."""
    home = Path.home()
    candidates: list[Path] = []

    registry_auth_file_env = os.environ.get("REGISTRY_AUTH_FILE", "")
    if registry_auth_file_env:
        candidates.append(Path(registry_auth_file_env))

    docker_config = Path(os.environ.get("DOCKER_CONFIG", home / ".docker"))
    candidates.append(docker_config / "config.json")

    xdg_runtime = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    candidates.append(xdg_runtime / "containers/auth.json")

    candidates += [
        home / ".config/containers/auth.json",
        home / ".docker/config.json",
    ]

    return next((p for p in candidates if p.is_file()), None)


def is_container_running(name: str) -> bool:
    """Check if container exists and is currently in the running state."""
    result = subprocess.run(
        ["podman", "container", "inspect", "--format", "{{.State.Running}}", name],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def pull_image_if_needed(pullspec: str) -> None:
    """Pull container image if pullspec is not local."""
    if "localhost" not in pullspec:
        subprocess.run(["podman", "pull", pullspec], check=True)


# ---------------------------------------------------------------------------
# Sandbox Configuration Domain Model
# ---------------------------------------------------------------------------

@dataclass
class SandboxConfig:
    harness: str
    backend: str
    workspace: str
    pullspec: str
    host_workdirs: list[str]
    codeburn: bool
    no_cache: bool
    entrypoint: str | None = None

    @property
    def normalized_workspace(self) -> str:
        """Strip any existing prefix then re-add it (idempotency guard)."""
        prefix = WORKSPACE_PREFIX_MAP.get((self.harness, self.backend), f"{self.harness}-")
        return prefix + self.workspace.removeprefix(prefix)

    @property
    def system_prompt_target(self) -> Path:
        """Target path inside container for system prompt file."""
        if self.harness == "claude":
            return CONTAINER_HOME / ".claude/CLAUDE.md"
        if self.harness == "codex":
            return CONTAINER_HOME / ".codex/AGENTS.md"
        return CONTAINER_HOME / ".config/opencode/AGENTS.md"

    @property
    def cache_volume_spec(self) -> str:
        """Volume specification for persistent session cache."""
        if self.harness == "claude":
            return f"claude-project-cache:{CONTAINER_HOME}/.claude/projects:z,U"
        return f"opencode-cache:{CONTAINER_HOME}/.local/share/opencode:z,U"

    def validate(self) -> None:
        """Validate workdir paths and entrypoint location on host."""
        for d in self.host_workdirs:
            if not Path(d).is_dir():
                sys.exit(f"Error: Host workdir {d} does not exist")

        if self.entrypoint:
            ep_path = Path(self.entrypoint)
            if not ep_path.is_absolute():
                sys.exit(f"Error: --entrypoint path must be absolute: {self.entrypoint}")
            if not ep_path.is_file():
                sys.exit(f"Error: Specified --entrypoint file does not exist: {self.entrypoint}")

    def _get_auth_args(self) -> list[str]:
        """Validate required credential files.

        Returns a flat list of ['--env', 'VAR=value', ...] args for the
        modelscorp or openai backend; empty list for vertex.
        """
        # Backend-specific env vars and volume mounts
        if self.harness == "claude":
            return self._claude_auth_args()
        elif self.backend == "vertex":
            _require_file(GCP_ADC_FILE)
            return self._opencode_vertex_auth_args()
        elif self.backend == "openai":
            return self._openai_auth_args()
        elif self.backend == "modelscorp":
            return self._modelscorp_auth_args()

    def build_interactive_podman_args(self) -> tuple[list[str], bool]:
        args, trust_anchor_dir_mounted = self._build_podman_args()
        return ["-it"] + args, trust_anchor_dir_mounted

    def build_detached_podman_args(self) -> tuple[list[str], bool]:
        args, trust_anchor_dir_mounted = self._build_podman_args()
        return ["--detach"] + args, trust_anchor_dir_mounted
    
    def _openai_auth_args(self) -> tuple[list[str]]:
        openai_auth_file = OPENAI_AUTH_FILE
        if not openai_auth_file.is_file():
            sys.exit(f"Error: Expected OpenAI auth file at {openai_auth_file}")

        api_key_env_var_name = "OPENAI_API_KEY"
        api_key = json.loads(openai_auth_file.read_text())[api_key_env_var_name]
        args = ["--env", f"{api_key_env_var_name}={api_key}"]

        if self.harness == "opencode":
            return args

        if self.harness == "codex":
            return args + [
                "--volume", f"{openai_auth_file}:{CONTAINER_HOME}/.codex/auth.json:ro,z"
            ]

    def _claude_auth_args(self) -> tuple[list[str]]:
        return [
            "--env", "CLAUDE_CODE_USE_VERTEX=1",
            "--env", f"CLOUD_ML_REGION={GCP_VERTEX_REGION}",
            "--env", f"ANTHROPIC_VERTEX_PROJECT_ID={GCP_PROJECT_ID}",
            "--volume", f"{GCP_CONFIG_DIR}:{CONTAINER_HOME}/.config/gcloud:z,U",
        ]

    def _opencode_vertex_auth_args(self) -> tuple[list[str]]:
        return [
            "--env", f"GOOGLE_CLOUD_PROJECT={GCP_PROJECT_ID}",
            "--env", f"VERTEX_LOCATION={GCP_VERTEX_REGION}",
            "--env", f"GOOGLE_APPLICATION_CREDENTIALS={CONTAINER_HOME}/.config/gcloud/application_default_credentials.json",
            "--volume", f"{GCP_CONFIG_DIR}:{CONTAINER_HOME}/.config/gcloud:z,U",
        ]

    def _modelscorp_auth_args(self) -> tuple[list[str]]:
        # modelscorp
        _require_file(MODELSCORP_CONFIG_FILE)
        apikeys_file = _require_file(MODELSCORP_APIKEYS_FILE)
        envvars_file = _require_file(MODELSCORP_ENVVARS_FILE)

        provider_env_map = _read_kv_file(envvars_file)
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

        return env_args + [
            "--volume", f"{MODELSCORP_CONFIG_FILE}:{CONTAINER_HOME}/.config/opencode/opencode.json:z,U,ro",
        ]

    def _build_podman_args(self) -> tuple[list[str], bool]:
        """Build the full argument list for `podman run` (excluding image & workspace positionals).

        Returns (args, trust_anchor_dir_mounted).
        """
        primary_workdir = Path(self.host_workdirs[0])
        workspace_name = self.normalized_workspace

        args: list[str] = [
            "--rm",
            "--privileged",
            "--uidmap", "1000:0:1",
            "--uidmap", "0:1:1000",
            "--uidmap", "1001:1001:65536",
            "--gidmap", "1000:0:1",
            "--gidmap", "0:1:1000",
            "--gidmap", "1001:1001:65536",
            "--name", workspace_name,
            "--network=host",
            f"--workdir=/workdir/{primary_workdir.name}",
            "--env", "LANG=en_US.UTF-8",
            "--env", "LC_ALL=en_US.UTF-8",
            "--env", f"AI_TOOL={self.harness}",
        ]

        # Optional secrets
        _add_file_secret_env(
            args,
            JIRA_API_TOKEN_FILE,
            "JIRA_API_TOKEN",
            extra_env={
                "JIRA_URL": "https://redhat.atlassian.net",
                "JIRA_USER": "zzlotnik@redhat.com",
                "JIRA_USERNAME": "zzlotnik@redhat.com",
            },
        )
        _add_file_secret_env(args, GH_TOKEN_FILE, "GH_TOKEN")

        # Entrypoint override flag
        if self.entrypoint:
            args += [
                "--volume", f"{self.entrypoint}:/entrypoint:z,ro",
                "--entrypoint", "/entrypoint",
            ]

        # CA trust anchor mount
        trust_anchor_args, trust_anchor_mounted = _get_trust_anchor_mount()
        args += trust_anchor_args

        # Common system prompt & cache volume mounts across all backends
        system_prompt_file = HOME_DIR / "Repos/oc-oneliners/opencodesystemprompt.md"
        if system_prompt_file.is_file():
            args += ["--volume", f"{system_prompt_file}:{self.system_prompt_target}:ro,z"]

        if not self.no_cache:
            args += ["--volume", self.cache_volume_spec]

        # Set up auth args.
        args += self._get_auth_args()

        # Conditionally mount ~/.config/gws
        gws_dir = HOME_DIR / ".config/gws"
        if gws_dir.is_dir():
            args += ["--volume", f"{gws_dir}:{CONTAINER_HOME}/.config/gws:z,U"]

        # Mount all provided host workdirs
        for d in self.host_workdirs:
            p = Path(d)
            args += ["--volume", f"{p}:/workdir/{p.name}:z"]

        # Registry auth file
        auth_file = find_registry_auth()
        if auth_file is not None:
            args += ["--volume", f"{auth_file}:{CONTAINER_HOME}/.docker/config.json:z,ro"]

        # Kubeconfig injection
        args += _get_kubeconfig_mount(self.host_workdirs)

        return args, trust_anchor_mounted


# ---------------------------------------------------------------------------
# Argument Parsing & CLI Interface
# ---------------------------------------------------------------------------

def parse_args() -> SandboxConfig:
    """Parse command-line arguments and return a SandboxConfig."""
    ap = argparse.ArgumentParser(add_help=False)
    ap.add_argument("--harness", choices=["opencode", "claude", "codex"], default="opencode")
    ap.add_argument("--backend", choices=["vertex", "modelscorp", "openai"], default=None)
    ap.add_argument("--pullspec", default=DEFAULT_PULLSPEC)
    ap.add_argument("--workspace", default=None)
    ap.add_argument("--entrypoint", default=None)
    ap.add_argument("--codeburn", action="store_true", default=False)
    ap.add_argument("--no-cache", action="store_true", default=False)

    known, remainder = ap.parse_known_args()

    backend = known.backend
    if backend is None:
        if known.harness == "claude":
            backend = "vertex"
        elif known.harness == "codex":
            backend = "openai"
        else:
            backend = "openai"

    if known.codeburn:
        return SandboxConfig(
            harness=known.harness,
            backend=backend,
            workspace=known.workspace or "",
            pullspec=known.pullspec,
            host_workdirs=[],
            codeburn=True,
            no_cache=known.no_cache,
            entrypoint=known.entrypoint,
        )

    # Validate combination
    if (known.harness, backend) not in VALID_COMBINATIONS:
        sys.exit(
            f"Error: --harness {known.harness} is not compatible with --backend {backend}."
        )

    if not known.workspace or not remainder:
        _usage(ap)

    cfg = SandboxConfig(
        harness=known.harness,
        backend=backend,
        workspace=known.workspace,
        pullspec=known.pullspec,
        host_workdirs=remainder,
        codeburn=False,
        no_cache=known.no_cache,
        entrypoint=known.entrypoint,
    )

    cfg.workspace = cfg.normalized_workspace
    return cfg


def _usage(ap: argparse.ArgumentParser) -> None:
    name = Path(sys.argv[0]).name
    print(
        f"Usage: {name} --workspace WORKSPACE <host_workdir1> [host_workdir2] ...\n"
        "       [--harness opencode|claude|codex] [--backend vertex|modelscorp|openai]\n"
        "       [--pullspec PULLSPEC] [--entrypoint ABSOLUTE_HOST_PATH]\n"
        f"       {name} --codeburn\n"
        "\n"
        "Defaults: --harness opencode --backend openai\n"
        "Auto-selected backends when --backend is omitted:\n"
        "  --harness claude   -> vertex\n"
        "  --harness codex    -> openai\n"
        "  --harness opencode -> openai"
    )
    sys.exit(1)


# ---------------------------------------------------------------------------
# Codeburn
# ---------------------------------------------------------------------------

def run_codeburn(pullspec: str) -> None:
    """Run the codeburn tool to analyze AI spend.

    Mounts the claude-project-cache, opencode-cache, and codeburn persistent
    volumes then executes the `codeburn` binary inside the container.
    Replaces the current process (exec) so TTY handling works correctly.
    """
    pull_image_if_needed(pullspec)

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
# Main Application Entrypoint
# ---------------------------------------------------------------------------

def main() -> None:
    cfg = parse_args()

    if cfg.codeburn:
        run_codeburn(cfg.pullspec)
        return  # unreachable; exec replaces process

    print(f"Starting sandbox with harness '{cfg.harness}' and backend '{cfg.backend}'")

    cfg.validate()

    if not is_container_running(cfg.workspace):
        pull_image_if_needed(cfg.pullspec)

        podman_args, trust_anchor_dir_mounted = cfg.build_detached_podman_args()

        subprocess.run(
            ["podman", "run"] + podman_args + [cfg.pullspec, cfg.workspace],
            check=True,
        )

        time.sleep(1)

        if not is_container_running(cfg.workspace):
            podman_args, _ = cfg.build_interactive_podman_args()
            subprocess.run(["podman", "run"] + podman_args + [cfg.pullspec, cfg.workspace])
            sys.exit(f"Error: Container '{cfg.workspace}' failed to start or exited unexpectedly.")

        if trust_anchor_dir_mounted:
            subprocess.run(
                ["podman", "exec", "-u=root", "-it", cfg.workspace, "update-ca-trust"],
                check=True,
            )

        time.sleep(1)

    # Replace current process with tmux attach
    os.execvp("podman", ["podman", "exec", "-it", cfg.workspace, "tmux", "attach-session", "-t", cfg.workspace])


if __name__ == "__main__":
    main()
