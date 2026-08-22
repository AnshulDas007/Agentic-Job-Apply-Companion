#!/usr/bin/env python3
"""
CLI tool for managing the CandidateProfile.
"""

import click
import yaml
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from backend.parsing.profile_store import load_profile, save_profile

console = Console()

@click.group()
def cli():
    """Agentic-JobApply-Companion Profile Manager."""
    pass

@cli.command()
def view():
    """View the current candidate profile."""
    profile = load_profile()
    if not profile:
        console.print("[red]No profile found. Run `python main.py intake` first.[/red]")
        return
        
    console.print(Panel(f"[bold green]Candidate Profile: {profile.name}[/bold green]"))
    
    # Contact
    contact_table = Table(title="Contact Info", show_header=False)
    contact_table.add_column("Field", style="cyan")
    contact_table.add_column("Value", style="white")
    for k, v in profile.contact.model_dump().items():
        contact_table.add_row(k, str(v))
    console.print(contact_table)
    
    # Experience
    if profile.experience:
        exp_table = Table(title="Experience", show_lines=True)
        exp_table.add_column("Company")
        exp_table.add_column("Title")
        exp_table.add_column("Duration")
        exp_table.add_column("Type")
        for exp in profile.experience:
            exp_table.add_row(exp.company, exp.title, f"{exp.duration_months} mos", exp.type)
        console.print(exp_table)
        
    # Projects
    if profile.projects:
        proj_table = Table(title="Projects", show_lines=True)
        proj_table.add_column("Name")
        proj_table.add_column("Tech Stack")
        for proj in profile.projects:
            proj_table.add_row(proj.name, ", ".join(proj.tech_stack))
        console.print(proj_table)

@cli.command()
def edit():
    """Interactively edit profile fields."""
    profile = load_profile()
    if not profile:
        console.print("[red]No profile found. Run `python main.py intake` first.[/red]")
        return
        
    # Simplified edit loop (in a real app, this would be a full nested dict editor or use questionary)
    console.print("[yellow]For manual editing, it is recommended to edit data/candidate_profile.yaml directly and run `python manage_profile.py validate`.[/yellow]")
    
    # Allow simple contact edits as a demo
    field = click.prompt("Which contact field would you like to edit? (phone/email/address/github_url/linkedin_url)", type=str, default="")
    if field and hasattr(profile.contact, field):
        current_val = getattr(profile.contact, field)
        new_val = click.prompt(f"Enter new value for {field} (current: {current_val})", type=str)
        setattr(profile.contact, field, new_val)
        save_profile(profile)
        console.print(f"[green]Updated {field} and saved profile.[/green]")
    else:
        console.print("No changes made.")

@cli.command()
@click.option('--format', 'export_format', type=click.Choice(['json', 'yaml']), default='yaml')
def export(export_format):
    """Export profile to stdout."""
    profile = load_profile()
    if not profile:
        console.print("No profile found.")
        return
        
    if export_format == 'json':
        print(profile.model_dump_json(indent=2))
    else:
        print(yaml.dump(profile.model_dump(), default_flow_style=False, sort_keys=False))

@cli.command()
def validate():
    """Validate the profile files."""
    try:
        from backend.parsing.profile_schema import CandidateProfile
        with open("data/candidate_profile.yaml", "r") as f:
            data = yaml.safe_load(f)
        profile = CandidateProfile(**data)
        save_profile(profile)
        console.print("[bold green]Profile is valid and JSON has been synced![/bold green]")
    except Exception as e:
        console.print(f"[bold red]Validation failed:[/bold red] {e}")

if __name__ == '__main__':
    cli()
