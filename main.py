"""
main.py — CLI entry point for Agentic-JobApply-Companion (local commands).

Subcommands:
  intake   - Parse a resume and create/update the candidate profile
  status   - Show recent application statistics from the database
  profile  - View the stored candidate profile

The main pipeline (scrape → score → apply) runs on GitHub Actions.
See run_pipeline.py for the Actions entry point, and .github/workflows/
for the workflow definitions.
"""

import logging
import sys
from pathlib import Path

import click
from dotenv import load_dotenv

load_dotenv()


# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable debug logging")
def cli(verbose: bool) -> None:
    """Agentic-JobApply-Companion — Semi-autonomous job application copilot."""
    _setup_logging(verbose)


# ---------------------------------------------------------------------------
# intake — Parse resume and build profile
# ---------------------------------------------------------------------------

@cli.command()
@click.option(
    "--resume", "-r",
    type=click.Path(exists=True, path_type=Path),
    required=True,
    help="Path to resume file (PDF or DOCX)",
)
def intake(resume: Path) -> None:
    """Parse a resume and create the candidate profile."""
    from backend.parsing.resume_parser import parse_resume
    from backend.parsing.profile_store import (
        check_profile_gaps,
        load_profile,
        save_profile,
    )

    click.echo(f"📄 Parsing resume: {resume}")

    try:
        profile = parse_resume(resume)
    except Exception as e:
        click.echo(f"❌ Failed to parse resume: {e}", err=True)
        sys.exit(1)

    click.echo(f"✅ Parsed profile for: {profile.name}")
    click.echo(f"   Experience: {len(profile.experience)} entries")
    click.echo(f"   Projects:   {len(profile.projects)} entries")
    click.echo(f"   Skills:     {len(profile.skills)} items")
    click.echo(f"   Education:  {len(profile.education)} entries")

    # Gap check
    gaps = check_profile_gaps(profile)
    if gaps:
        click.echo(f"\n⚠️  Missing fields detected: {', '.join(gaps)}")
        click.echo("You can fill these now or edit data/candidate_profile.json later.\n")

        for gap in gaps:
            value = click.prompt(f"  Enter {gap}", default="", show_default=False)
            if value:
                _apply_gap_value(profile, gap, value)

    # Save profile
    save_profile(profile)
    click.echo(f"\n💾 Profile saved to data/candidate_profile.json")
    click.echo("   Edit manually with: python manage_profile.py edit")


def _apply_gap_value(profile, gap_name: str, value: str) -> None:
    """Apply a gap-filled value to the profile."""
    gap_lower = gap_name.lower()
    if "phone" in gap_lower:
        profile.contact.phone = value
    elif "address" in gap_lower or "location" in gap_lower:
        profile.contact.address = value


# ---------------------------------------------------------------------------
# status — Show pipeline statistics
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--limit", "-n", default=20, help="Number of recent entries to show.")
def status(limit: int) -> None:
    """Show recent application statistics from the database."""
    from backend.database import Database

    db = Database()
    stats = db.get_stats()

    click.echo("📊 Pipeline Statistics")
    click.echo("=" * 40)

    # Job stats
    click.echo("\nJobs:")
    job_stats = stats.get("jobs", {})
    if job_stats:
        for status_name, count in job_stats.items():
            click.echo(f"  {status_name}: {count}")
    else:
        click.echo("  No jobs recorded yet.")

    # Application stats
    click.echo("\nApplications:")
    app_stats = stats.get("applications", {})
    if app_stats:
        for status_name, count in app_stats.items():
            click.echo(f"  {status_name}: {count}")
    else:
        click.echo("  No applications recorded yet.")

    # Usage stats
    click.echo("\nUsage:")
    usage = stats.get("usage", {})
    if usage and usage.get("total_calls"):
        click.echo(f"  Total API calls: {usage['total_calls']}")
        click.echo(f"  Total tokens: {(usage.get('total_tokens_in', 0) or 0) + (usage.get('total_tokens_out', 0) or 0)}")
        cost = usage.get("total_cost", 0) or 0
        click.echo(f"  Estimated cost: ${cost:.4f}")
    else:
        click.echo("  No usage recorded yet.")

    # Recent audit trail
    click.echo(f"\nRecent Activity (last {limit}):")
    trail = db.get_audit_trail(limit=limit)
    if trail:
        for entry in trail:
            click.echo(
                f"  [{entry['timestamp'][:19]}] {entry['action']}: "
                f"{entry['target'][:40]} → {entry['result']}"
            )
    else:
        click.echo("  No activity recorded yet.")

    db.close()


# ---------------------------------------------------------------------------
# profile — View stored profile
# ---------------------------------------------------------------------------

@cli.command()
def profile() -> None:
    """View the stored candidate profile."""
    from backend.parsing.profile_store import load_profile

    prof = load_profile()
    if not prof:
        click.echo("❌ No profile found. Run 'intake' first.", err=True)
        sys.exit(1)

    click.echo(f"👤 {prof.name}")
    click.echo(f"📧 {prof.contact.email}")
    click.echo(f"📱 {prof.contact.phone}")
    click.echo(f"📍 {prof.contact.address}")
    click.echo(f"🔗 GitHub: {prof.contact.github_url}")
    click.echo(f"🔗 LinkedIn: {prof.contact.linkedin_url}")

    click.echo(f"\n💼 Experience ({len(prof.experience)}):")
    for exp in prof.experience:
        click.echo(
            f"  - {exp.title} at {exp.company} "
            f"({exp.type}, {exp.duration_months} months)"
        )

    click.echo(f"\n🛠️  Projects ({len(prof.projects)}):")
    for proj in prof.projects:
        tech = ", ".join(proj.tech_stack) if proj.tech_stack else "N/A"
        click.echo(f"  - {proj.name} ({tech})")

    click.echo(f"\n🎯 Skills: {', '.join(prof.skills)}")

    click.echo(f"\n🎓 Education ({len(prof.education)}):")
    for edu in prof.education:
        click.echo(f"  - {edu.degree} in {edu.field_of_study} from {edu.institution}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    cli()

