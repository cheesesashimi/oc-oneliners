#!/usr/bin/env python3
"""
Repository Ownership Analysis Tool

Analyzes git blame data with time-weighting to identify top contributors per directory.
Integrates with existing OWNERS files to provide ownership recommendations.

Usage:
    python3 hack/analyze-ownership.py

Output:
    - ownership_report.md (Markdown report)
    - ownership_report.json (JSON report)

Assisted-by: Claude Code (Sonnet 4.5)
"""

import os
import sys
import json
import yaml
import subprocess
import re
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Set, Tuple
from datetime import datetime, timezone
from pathlib import Path
from multiprocessing import Pool, cpu_count
from collections import defaultdict
import math

# Configuration
LAMBDA = 0.5  # Exponential decay parameter (half-life of 2 years)
SECONDS_PER_YEAR = 365.25 * 24 * 60 * 60
MAX_WORKERS = min(8, cpu_count())
BLAME_TIMEOUT = 30  # seconds
TOP_N_CONTRIBUTORS = 50  # Number of top contributors to show per directory

# Directories to exclude from analysis
EXCLUDE_DIRS = {"vendor", ".git"}


@dataclass
class AuthorStats:
    """Statistics for a single author's contributions."""

    name: str
    email: str
    weighted_lines: float = 0.0
    raw_lines: int = 0

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return {
            "name": self.name,
            "email": self.email,
            "weighted_lines": round(self.weighted_lines, 2),
            "raw_lines": self.raw_lines,
        }


@dataclass
class DirectoryStats:
    """Statistics and ownership information for a directory."""

    path: str
    owners_file: Optional[str] = None
    approvers: List[str] = field(default_factory=list)
    reviewers: List[str] = field(default_factory=list)
    authors: Dict[str, AuthorStats] = field(default_factory=dict)
    total_files: int = 0
    analyzed_files: int = 0

    def add_contribution(
        self,
        author_key: str,
        name: str,
        email: str,
        weighted_lines: float,
        raw_lines: int,
    ):
        """Add contribution data for an author."""
        if author_key not in self.authors:
            self.authors[author_key] = AuthorStats(name=name, email=email)

        self.authors[author_key].weighted_lines += weighted_lines
        self.authors[author_key].raw_lines += raw_lines

    def get_top_contributors(
        self, n: int = TOP_N_CONTRIBUTORS
    ) -> List[Tuple[AuthorStats, float]]:
        """Get top N contributors sorted by weighted lines with percentages."""
        if not self.authors:
            return []

        total_weighted = sum(a.weighted_lines for a in self.authors.values())
        sorted_authors = sorted(
            self.authors.values(), key=lambda a: a.weighted_lines, reverse=True
        )[:n]

        return [
            (
                author,
                (
                    (author.weighted_lines / total_weighted * 100)
                    if total_weighted > 0
                    else 0
                ),
            )
            for author in sorted_authors
        ]


class OwnershipAnalyzer:
    """Main analyzer class."""

    def __init__(self, repo_path: str = "."):
        self.repo_path = Path(repo_path).resolve()
        self.current_time = datetime.now(timezone.utc).timestamp()
        self.aliases: Dict[str, List[str]] = {}
        self.owners_map: Dict[str, DirectoryStats] = {}
        self.directory_stats: Dict[str, DirectoryStats] = {}

    def run(self):
        """Execute the full analysis pipeline."""
        print("=" * 80)
        print("Repository Ownership Analysis")
        print("=" * 80)
        print(f"Repository: {self.repo_path}")
        print(f"Time weighting: Exponential decay (λ={LAMBDA})")
        print(f"Workers: {MAX_WORKERS}")
        print()

        # Phase 1: Discover files
        print("Phase 1: Discovering files...")
        files = self._discover_files()
        print(f"  Found {len(files)} files to analyze")

        # Phase 2: Load OWNERS configuration
        print("\nPhase 2: Loading OWNERS configuration...")
        self._load_owners_aliases()
        self._load_owners_files()
        print(f"  Loaded {len(self.owners_map)} OWNERS files")
        print(f"  Loaded {len(self.aliases)} alias groups")

        # Phase 3: Analyze git blame
        print("\nPhase 3: Analyzing git blame (parallel)...")
        file_contributions = self._analyze_files_parallel(files)
        successful = sum(1 for c in file_contributions if c is not None)
        print(f"  Successfully analyzed {successful}/{len(files)} files")

        # Phase 4: Aggregate by directory
        print("\nPhase 4: Aggregating contributions by directory...")
        self._aggregate_by_directory(file_contributions)
        print(f"  Aggregated data for {len(self.directory_stats)} directories")

        # Phase 5: Enrich with OWNERS data
        print("\nPhase 5: Enriching with OWNERS data...")
        self._enrich_with_owners()

        # Phase 6: Generate reports
        print("\nPhase 6: Generating reports...")
        self._generate_markdown_report()
        self._generate_json_report()

        print("\n" + "=" * 80)
        print("Analysis complete!")
        print("  - ownership_report.md")
        print("  - ownership_report.json")
        print("=" * 80)

    def _discover_files(self) -> List[str]:
        """Discover all tracked files excluding vendor directories."""
        try:
            result = subprocess.run(
                ["git", "ls-files"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
            )

            files = []
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue

                # Skip excluded directories
                parts = line.split("/")
                if any(part in EXCLUDE_DIRS for part in parts):
                    continue

                files.append(line)

            return files
        except subprocess.CalledProcessError as e:
            print(f"Error discovering files: {e}", file=sys.stderr)
            return []

    def _load_owners_aliases(self):
        """Load alias definitions from OWNERS_ALIASES file."""
        aliases_file = self.repo_path / "OWNERS_ALIASES"
        if not aliases_file.exists():
            return

        try:
            with open(aliases_file, "r") as f:
                data = yaml.safe_load(f)
                if data and "aliases" in data:
                    self.aliases = data["aliases"]
        except Exception as e:
            print(f"Warning: Failed to load OWNERS_ALIASES: {e}", file=sys.stderr)

    def _load_owners_files(self):
        """Find and parse all OWNERS files."""
        try:
            result = subprocess.run(
                ["find", ".", "-name", "OWNERS", "-not", "-path", "*/vendor/*"],
                cwd=self.repo_path,
                capture_output=True,
                text=True,
                check=True,
            )

            for line in result.stdout.strip().split("\n"):
                if not line or line == ".":
                    continue

                owners_file = line.lstrip("./")
                self._parse_owners_file(owners_file)

        except subprocess.CalledProcessError as e:
            print(f"Warning: Failed to find OWNERS files: {e}", file=sys.stderr)

    def _parse_owners_file(self, owners_file: str):
        """Parse a single OWNERS file."""
        full_path = self.repo_path / owners_file
        directory = str(Path(owners_file).parent)
        if directory == ".":
            directory = "."

        try:
            with open(full_path, "r") as f:
                data = yaml.safe_load(f)

            if not data:
                return

            stats = DirectoryStats(path=directory, owners_file=str(full_path))

            # Parse approvers
            if "approvers" in data:
                stats.approvers = self._resolve_aliases(data["approvers"])

            # Parse reviewers
            if "reviewers" in data:
                stats.reviewers = self._resolve_aliases(data["reviewers"])

            self.owners_map[directory] = stats

        except Exception as e:
            print(f"Warning: Failed to parse {owners_file}: {e}", file=sys.stderr)

    def _resolve_aliases(self, entries: List[str]) -> List[str]:
        """Resolve alias groups to individual usernames."""
        resolved = []
        for entry in entries:
            if entry in self.aliases:
                resolved.extend(self.aliases[entry])
            else:
                resolved.append(entry)
        return sorted(set(resolved))

    def _analyze_files_parallel(self, files: List[str]) -> List[Optional[dict]]:
        """Analyze files in parallel using multiprocessing."""
        with Pool(processes=MAX_WORKERS) as pool:
            results = pool.map(
                self._analyze_file_wrapper,
                [(f, self.repo_path, self.current_time) for f in files],
            )
        return results

    @staticmethod
    def _analyze_file_wrapper(args: Tuple[str, Path, float]) -> Optional[dict]:
        """Wrapper for multiprocessing (must be static method)."""
        file_path, repo_path, current_time = args
        return OwnershipAnalyzer._analyze_file(file_path, repo_path, current_time)

    @staticmethod
    def _analyze_file(
        file_path: str, repo_path: Path, current_time: float
    ) -> Optional[dict]:
        """Analyze a single file using git blame."""
        try:
            result = subprocess.run(
                ["git", "blame", "--line-porcelain", file_path],
                cwd=repo_path,
                capture_output=True,
                text=True,
                timeout=BLAME_TIMEOUT,
                check=True,
            )

            # Parse blame output
            authors = defaultdict(
                lambda: {"weighted": 0.0, "raw": 0, "name": "", "email": ""}
            )
            current_commit = None

            for line in result.stdout.split("\n"):
                if not line:
                    continue

                # Start of new blame block
                if line[0] != "\t" and " " in line:
                    parts = line.split(" ", 1)
                    if len(parts[0]) == 40:  # SHA-1 hash
                        current_commit = parts[0]
                        continue

                # Parse metadata lines
                if line.startswith("author "):
                    author_name = line[7:]
                    if current_commit:
                        authors[current_commit]["name"] = author_name
                elif line.startswith("author-mail "):
                    author_email = line[12:].strip("<>")
                    if current_commit:
                        authors[current_commit]["email"] = author_email
                elif line.startswith("author-time "):
                    timestamp = int(line[12:])
                    if current_commit:
                        # Calculate time-weighted contribution
                        age_seconds = current_time - timestamp
                        age_years = age_seconds / SECONDS_PER_YEAR
                        weight = math.exp(-LAMBDA * age_years)

                        authors[current_commit]["weighted"] += weight
                        authors[current_commit]["raw"] += 1

            # Aggregate by author email (unique identifier)
            author_stats = defaultdict(
                lambda: {"name": "", "email": "", "weighted": 0.0, "raw": 0}
            )
            for commit_data in authors.values():
                email = commit_data["email"]
                if email:
                    author_stats[email]["email"] = email
                    author_stats[email]["name"] = commit_data["name"]
                    author_stats[email]["weighted"] += commit_data["weighted"]
                    author_stats[email]["raw"] += commit_data["raw"]

            return {"file": file_path, "authors": dict(author_stats)}

        except subprocess.TimeoutExpired:
            print(f"  Warning: Timeout analyzing {file_path}", file=sys.stderr)
            return None
        except subprocess.CalledProcessError:
            # Binary files or files git blame can't process
            return None
        except Exception as e:
            print(f"  Warning: Error analyzing {file_path}: {e}", file=sys.stderr)
            return None

    def _aggregate_by_directory(self, file_contributions: List[Optional[dict]]):
        """Aggregate file contributions to all parent directories."""
        for contribution in file_contributions:
            if not contribution:
                continue

            file_path = contribution["file"]
            authors = contribution["authors"]

            # Get all parent directories
            path_parts = Path(file_path).parts
            directories = ["."]  # Root always included

            for i in range(len(path_parts) - 1):  # Exclude the file itself
                dir_path = "/".join(path_parts[: i + 1])
                directories.append(dir_path)

            # Add contribution to all parent directories
            for directory in directories:
                if directory not in self.directory_stats:
                    self.directory_stats[directory] = DirectoryStats(path=directory)

                dir_stats = self.directory_stats[directory]
                dir_stats.total_files += 1
                dir_stats.analyzed_files += 1

                for email, author_data in authors.items():
                    dir_stats.add_contribution(
                        author_key=email,
                        name=author_data["name"],
                        email=author_data["email"],
                        weighted_lines=author_data["weighted"],
                        raw_lines=author_data["raw"],
                    )

    def _enrich_with_owners(self):
        """Enrich directory stats with OWNERS information."""
        for directory, stats in self.directory_stats.items():
            # Find applicable OWNERS file by walking up the tree
            current = directory
            while current is not None:
                if current in self.owners_map:
                    owners = self.owners_map[current]
                    stats.owners_file = owners.owners_file
                    stats.approvers = owners.approvers.copy()
                    stats.reviewers = owners.reviewers.copy()
                    break

                # Move up one level
                if current == ".":
                    break
                parent = str(Path(current).parent)
                if parent == current or parent == "":
                    current = "."
                else:
                    current = parent

    def _generate_markdown_report(self):
        """Generate Markdown report."""
        output_file = self.repo_path / "ownership_report.md"

        with open(output_file, "w") as f:
            # Header
            f.write("# Repository Ownership Analysis\n\n")
            f.write(
                f"**Analysis Date**: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            )
            f.write(f"**Repository**: {self.repo_path.name}\n")
            f.write(f"**Time Weighting**: Exponential decay (λ={LAMBDA})\n")
            f.write(f"**Total Directories**: {len(self.directory_stats)}\n")
            f.write(f"**OWNERS Files**: {len(self.owners_map)}\n\n")
            f.write("---\n\n")

            # Table of contents
            f.write("## Table of Contents\n\n")
            sorted_dirs = sorted(self.directory_stats.keys())
            for directory in sorted_dirs:
                if directory == ".":
                    anchor = "root"
                    display = "/ (Root)"
                else:
                    anchor = directory.replace("/", "-").replace(".", "")
                    display = directory
                f.write(f"- [{display}](#{anchor})\n")
            f.write("\n---\n\n")

            # Directory details
            for directory in sorted_dirs:
                stats = self.directory_stats[directory]

                # Directory header
                if directory == ".":
                    f.write("## Directory: / (Root) {#root}\n\n")
                else:
                    anchor = directory.replace("/", "-").replace(".", "")
                    f.write(f"## Directory: {directory} {{#{anchor}}}\n\n")

                # OWNERS file info
                if stats.owners_file:
                    f.write(f"**OWNERS File**: `{stats.owners_file}`\n\n")
                else:
                    f.write("**OWNERS File**: None\n\n")

                # Configured owners
                if stats.approvers or stats.reviewers:
                    f.write("### Configured Owners\n\n")

                    if stats.approvers:
                        f.write(f"**Approvers** ({len(stats.approvers)}):\n")
                        for approver in stats.approvers:
                            f.write(f"- {approver}\n")
                        f.write("\n")

                    if stats.reviewers:
                        f.write(f"**Reviewers** ({len(stats.reviewers)}):\n")
                        for reviewer in stats.reviewers:
                            f.write(f"- {reviewer}\n")
                        f.write("\n")

                # Top contributors
                top_contributors = stats.get_top_contributors()

                if top_contributors:
                    f.write(
                        f"### Top {min(len(top_contributors), TOP_N_CONTRIBUTORS)} Contributors (by time-weighted lines)\n\n"
                    )
                    f.write(
                        "| Rank | Author | Email | Weighted Lines | Raw Lines | % |\n"
                    )
                    f.write(
                        "|------|--------|-------|----------------|-----------|---|\n"
                    )

                    for rank, (author, percentage) in enumerate(top_contributors, 1):
                        f.write(
                            f"| {rank} | {author.name} | {author.email} | "
                            f"{author.weighted_lines:,.1f} | {author.raw_lines:,} | "
                            f"{percentage:.1f}% |\n"
                        )
                    f.write("\n")

                # Summary
                total_weighted = sum(a.weighted_lines for a in stats.authors.values())
                f.write("**Summary**:\n")
                f.write(f"- Total contributors: {len(stats.authors)}\n")
                f.write(f"- Total files: {stats.total_files}\n")
                f.write(f"- Total weighted lines: {total_weighted:,.1f}\n")
                f.write("\n---\n\n")

        print(f"  Generated: {output_file}")

    def _generate_json_report(self):
        """Generate JSON report."""
        output_file = self.repo_path / "ownership_report.json"

        report = {
            "metadata": {
                "repository": self.repo_path.name,
                "analysis_date": datetime.now().isoformat(),
                "time_weighting": {
                    "method": "exponential_decay",
                    "lambda": LAMBDA,
                    "half_life_years": math.log(2) / LAMBDA,
                },
                "total_directories": len(self.directory_stats),
                "owners_files": len(self.owners_map),
            },
            "directories": [],
        }

        for directory in sorted(self.directory_stats.keys()):
            stats = self.directory_stats[directory]
            top_contributors = stats.get_top_contributors()
            total_weighted = sum(a.weighted_lines for a in stats.authors.values())

            dir_data = {
                "path": directory,
                "owners_file": stats.owners_file,
                "owners": {"approvers": stats.approvers, "reviewers": stats.reviewers},
                "statistics": {
                    "total_files": stats.total_files,
                    "total_contributors": len(stats.authors),
                    "total_weighted_lines": round(total_weighted, 2),
                },
                "top_contributors": [
                    {
                        "rank": rank,
                        "name": author.name,
                        "email": author.email,
                        "weighted_lines": round(author.weighted_lines, 2),
                        "raw_lines": author.raw_lines,
                        "percentage": round(percentage, 2),
                    }
                    for rank, (author, percentage) in enumerate(top_contributors, 1)
                ],
            }

            report["directories"].append(dir_data)

        with open(output_file, "w") as f:
            json.dump(report, f, indent=2)

        print(f"  Generated: {output_file}")


def main():
    """Main entry point."""
    if len(sys.argv) > 2:
        print("Usage: analyze-ownership.py [repository_path]")
        sys.exit(1)

    repo_path = sys.argv[1] if len(sys.argv) == 2 else "."

    analyzer = OwnershipAnalyzer(repo_path)
    analyzer.run()


if __name__ == "__main__":
    main()
