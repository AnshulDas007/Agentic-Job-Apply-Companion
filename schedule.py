"""
Scheduling module for automated Tier 1 job applications.

Provides utilities to:
  - Generate crontab entries for scheduled pipeline runs
  - Generate GitHub Actions workflow files for cloud-based scheduling
  - Run the pipeline directly for manual/one-shot execution
"""

import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Crontab scheduling
# ---------------------------------------------------------------------------

DEFAULT_CRON_SCHEDULE = "0 9 * * 1-5"  # Weekdays at 9 AM


def generate_crontab_entry(
    schedule: str = DEFAULT_CRON_SCHEDULE,
    project_dir: Optional[str] = None,
    python_path: Optional[str] = None,
    log_file: str = "logs/cron_run.log",
    platforms: Optional[list[str]] = None,
    burn_in: bool = True,
) -> str:
    """
    Generate a crontab entry for scheduled pipeline runs.

    Args:
        schedule: Cron schedule expression (default: weekdays at 9 AM).
        project_dir: Absolute path to the project directory.
        python_path: Path to the venv Python binary.
        log_file: Path to the log file for cron output.
        platforms: Optional list of platforms to scrape.
        burn_in: Whether to enable burn-in mode.

    Returns:
        A crontab entry string.
    """
    if not project_dir:
        project_dir = str(Path.cwd())
    if not python_path:
        python_path = str(Path(project_dir) / "venv" / "bin" / "python")

    cmd_parts = [f"cd {project_dir} &&", python_path, "main.py", "run"]

    if platforms:
        for p in platforms:
            cmd_parts.extend(["-p", p])

    if not burn_in:
        cmd_parts.append("--no-burn-in")

    cmd = " ".join(cmd_parts)
    log_path = str(Path(project_dir) / log_file)

    return f"{schedule} {cmd} >> {log_path} 2>&1"


def install_crontab(
    entry: str,
    comment: str = "Agentic-JobApply-Companion auto-apply",
) -> bool:
    """
    Install a crontab entry (appends to existing crontab).

    Args:
        entry: The crontab entry string.
        comment: A comment to identify this entry.

    Returns:
        True if installation was successful.
    """
    try:
        # Get existing crontab
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
        )
        existing = result.stdout if result.returncode == 0 else ""

        # Check if already installed
        if entry in existing:
            logger.info("Crontab entry already exists.")
            return True

        # Append new entry
        new_crontab = existing.rstrip() + f"\n# {comment}\n{entry}\n"

        process = subprocess.run(
            ["crontab", "-"],
            input=new_crontab,
            capture_output=True,
            text=True,
        )

        if process.returncode == 0:
            logger.info("Crontab entry installed successfully.")
            return True
        else:
            logger.error("Failed to install crontab: %s", process.stderr)
            return False

    except FileNotFoundError:
        logger.error("crontab command not found — cron scheduling unavailable.")
        return False


def remove_crontab(
    comment: str = "Agentic-JobApply-Companion auto-apply",
) -> bool:
    """
    Remove the crontab entry identified by its comment.

    Args:
        comment: The comment identifying the entry to remove.

    Returns:
        True if removal was successful.
    """
    try:
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            return True  # No crontab exists

        lines = result.stdout.split("\n")
        filtered = []
        skip_next = False

        for line in lines:
            if f"# {comment}" in line:
                skip_next = True
                continue
            if skip_next:
                skip_next = False
                continue
            filtered.append(line)

        new_crontab = "\n".join(filtered)
        process = subprocess.run(
            ["crontab", "-"],
            input=new_crontab,
            capture_output=True,
            text=True,
        )

        return process.returncode == 0

    except FileNotFoundError:
        return False


# ---------------------------------------------------------------------------
# GitHub Actions workflow generation
# ---------------------------------------------------------------------------

def generate_github_actions_workflow(
    schedule: str = "0 9 * * 1-5",
    platforms: Optional[list[str]] = None,
    burn_in: bool = True,
) -> str:
    """
    Generate a GitHub Actions workflow YAML for scheduled pipeline runs.

    Args:
        schedule: Cron schedule expression.
        platforms: Optional list of platforms to scrape.
        burn_in: Whether to enable burn-in mode.

    Returns:
        YAML content for .github/workflows/auto-apply.yml
    """
    platform_args = ""
    if platforms:
        platform_args = " ".join(f"-p {p}" for p in platforms)

    burn_in_flag = "" if burn_in else " --no-burn-in"

    return f"""name: Auto-Apply Pipeline

on:
  schedule:
    - cron: '{schedule}'
  workflow_dispatch:  # Allow manual triggers

jobs:
  apply:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m venv venv
          source venv/bin/activate
          pip install -r requirements.txt

      - name: Run pipeline
        env:
          GROQ_API_KEY: ${{{{ secrets.GROQ_API_KEY }}}}
          APIFY_TOKEN: ${{{{ secrets.APIFY_TOKEN }}}}
          GOOGLE_AI_API_KEY: ${{{{ secrets.GOOGLE_AI_API_KEY }}}}
        run: |
          source venv/bin/activate
          python main.py run {platform_args}{burn_in_flag}

      - name: Upload digest
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: daily-digest
          path: data/daily_digest.txt
"""


def save_github_actions_workflow(
    output_path: str = ".github/workflows/auto-apply.yml",
    **kwargs,
) -> str:
    """
    Generate and save a GitHub Actions workflow file.

    Returns:
        The path where the workflow was saved.
    """
    content = generate_github_actions_workflow(**kwargs)

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")

    logger.info("GitHub Actions workflow saved to %s", path)
    return str(path)
