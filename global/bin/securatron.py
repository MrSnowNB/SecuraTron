#!/usr/bin/env python3
"""
Securatron CLI — Registry and Inspection Tool

Operator-facing CLI for managing and querying the atom/molecule registry.
Separate from dispatch.py to keep concerns clean.
"""

import sys
import os
import json
import re
import argparse
import yaml
from pathlib import Path
from datetime import datetime, timezone
from difflib import get_close_matches

BASE_DIR = Path.home() / ".securatron"
REGISTRY_DIR = BASE_DIR / "global" / "registry"
ATOMS_DIR = REGISTRY_DIR / "atoms"
MOLECULES_DIR = REGISTRY_DIR / "molecules"
TOOLS_DIR = BASE_DIR / "global" / "tools"
SKILLS_DIR = BASE_DIR / "global" / "skills"
PARSERS_FILE = BASE_DIR / "global" / "bin" / "parsers.py"

# =============================================================================
# Registry Helpers
# =============================================================================

def _load_entry(filepath):
    """Load a single registry entry from an .md file."""
    with open(filepath) as f:
        content = f.read()
    
    # Extract YAML frontmatter
    if not content.startswith("---"):
        return None
    
    parts = content.split("---", 2)
    if len(parts) < 3:
        return None
    
    try:
        frontmatter = yaml.safe_load(parts[1])
    except yaml.YAMLError as e:
        print(f"Error parsing YAML frontmatter in {filepath}: {e}", file=sys.stderr)
        return None
    
    body = parts[2].strip()
    frontmatter['_body'] = body
    frontmatter['_path'] = str(filepath)
    frontmatter['_modified'] = datetime.fromtimestamp(
        filepath.stat().st_mtime, tz=timezone.utc
    ).isoformat()
    
    return frontmatter


def _scan_registry(kind=None):
    """Scan the registry directory and return all entries."""
    entries = []
    
    for search_dir in [ATOMS_DIR, MOLECULES_DIR]:
        if not search_dir.exists():
            continue
        if kind and not search_dir.name.endswith(kind):
            continue
        
        for md_file in sorted(search_dir.glob("*.md")):
            entry = _load_entry(md_file)
            if entry:
                entry['_kind'] = search_dir.name.replace('s', '')  # atoms -> atom
                entries.append(entry)
    
    return entries


def _search_entries(entries, query, fields=None):
    """Search entries by query string in specified fields."""
    if not query:
        return entries
    
    if fields is None:
        fields = ['id', 'description', 'body']
    
    results = []
    for entry in entries:
        for field in fields:
            text = str(entry.get(field, '')).lower()
            if query.lower() in text:
                results.append(entry)
                break
    
    return results


def _generate_entry_from_source(kind, atom_id):
    """Auto-generate registry entry from source YAML and Python/bash files."""
    if kind == 'atom':
        yaml_path = TOOLS_DIR / f"{atom_id}.yaml"
        if not yaml_path.exists():
            # Also check subdirectories: TOOLS_DIR/atom_id/atom_id.yaml
            sub_path = TOOLS_DIR / atom_id / f"{atom_id}.yaml"
            if sub_path.exists():
                yaml_path = sub_path
            else:
                # Also check TOOLS_DIR/atom_id/atom.yaml
                alt_path = TOOLS_DIR / atom_id / "atom.yaml"
                if alt_path.exists():
                    yaml_path = alt_path
                else:
                    return None
    else:
        yaml_path = SKILLS_DIR / f"{atom_id}.yaml"
        if not yaml_path.exists():
            return None
    
    with open(yaml_path) as f:
        source = yaml.safe_load(f)
    
    # Build entry
    entry = {
        'id': source.get('id', atom_id),
        'kind': kind,
        'version': source.get('version', 1),
        'status': source.get('tier', 'draft'),
        'author': source.get('author', 'unknown'),
        'created': source.get('created', datetime.now(timezone.utc).isoformat()),
        'modified': datetime.now(timezone.utc).isoformat(),
        'description': source.get('description', ''),
    }
    
    # Auto-generate inputs
    if 'inputs' in source:
        entry['inputs'] = []
        for k, v in source['inputs'].items():
            if isinstance(v, dict):
                entry['inputs'].append({
                    'name': k,
                    'type': v.get('type', 'string'),
                    'required': v.get('required', False),
                    'default': v.get('default', ''),
                    'description': v.get('description', ''),
                })
            else:
                entry['inputs'].append({
                    'name': k,
                    'type': 'string',
                    'required': False,
                    'description': str(v),
                })
    
    # Auto-generate outputs
    if 'outputs' in source:
        output_val = source['outputs']
        if isinstance(output_val, list):
            entry['outputs'] = output_val
        elif isinstance(output_val, dict):
            entry['outputs'] = [output_val.get('type', 'structured')]
        else:
            entry['outputs'] = [str(output_val)]
    
    # Implementation type
    impl = source.get('implementation', {})
    if impl.get('kind') == 'shell':
        entry['implements'] = impl.get('cmd', 'shell script')
        entry['impl_kind'] = 'shell'
    elif impl.get('kind') == 'python':
        entry['implements'] = f"python method: {impl.get('method', 'unknown')}"
        entry['impl_kind'] = 'python'
    elif impl.get('kind') == 'compose':
        entry['implements'] = 'molecule (DAG composition)'
        entry['impl_kind'] = 'compose'
    
    # Parser
    if 'outputs' in source and isinstance(source['outputs'], dict):
        entry['parser'] = source['outputs'].get('parser', 'none')
    else:
        entry['parser'] = 'none'
    
    # Molecule-specific: build DAG summary
    if kind == 'molecule':
        dag = impl.get('dag', {})
        steps = []
        for step_id, cfg in dag.items():
            step_info = {
                'id': step_id,
                'atom': cfg.get('atom', 'unknown'),
            }
            if 'depends_on' in cfg:
                step_info['depends_on'] = cfg['depends_on']
            if 'name' in cfg:
                step_info['name'] = cfg['name']
            steps.append(step_info)
        entry['steps'] = steps
    
    # Manual editable body template
    entry['_body'] = f"""## Description
{source.get('description', '')}

## Usage Notes
<!-- Add any operational notes, gotchas, or tips here -->

## Gotchas
<!-- Known pitfalls and edge cases -->
"""
    
    return entry


def _write_entry(entry):
    """Write a registry entry to an .md file."""
    if entry['kind'] == 'atom':
        target_dir = ATOMS_DIR
    else:
        target_dir = MOLECULES_DIR
    
    target_dir.mkdir(parents=True, exist_ok=True)
    
    filepath = target_dir / f"{entry['id']}.md"
    
    # Write YAML frontmatter
    fm_fields = {}
    for key in ['id', 'kind', 'version', 'status', 'author', 'created', 'modified',
                'description', 'inputs', 'outputs', 'implements', 'impl_kind', 'parser',
                'steps']:
        if key in entry:
            fm_fields[key] = entry[key]
    
    body = entry.get('_body', '')
    
    with open(filepath, 'w') as f:
        f.write("---\n")
        yaml.dump(fm_fields, f, default_flow_style=False, sort_keys=False, width=120)
        f.write("---\n")
        f.write(body)
    
    return str(filepath)


# =============================================================================
# CLI Commands
# =============================================================================

def cmd_list(args):
    """List all atoms or molecules."""
    entries = _scan_registry()
    
    # Apply filters (filter by entry-level 'kind' field)
    if args.kind:
        entries = [e for e in entries if e.get('kind') == args.kind]
    if args.status:
        entries = [e for e in entries if e.get('status') == args.status]
    
    if not entries:
        print("No entries found.")
        return
    
    # Display table
    if args.format == 'json':
        output = []
        for e in entries:
            out = {k: v for k, v in e.items() if not k.startswith('_')}
            output.append(out)
        print(json.dumps(output, indent=2))
    else:
        # Table view
        print(f"{'ID':<35} {'Kind':<10} {'Status':<12} {'Version':<8} {'Parser':<25}")
        print("-" * 92)
        for e in entries:
            pid = e.get('id', '?')
            pkind = e.get('kind', '?')
            pstatus = e.get('status', '?')
            pver = str(e.get('version', '?'))
            parser = e.get('parser', 'none')
            # Truncate parser for display
            if len(parser) > 23:
                parser = parser[:20] + "..."
            print(f"{pid:<35} {pkind:<10} {pstatus:<12} {pver:<8} {parser:<25}")
    
    print(f"\nTotal: {len(entries)}")


def cmd_describe(args):
    """Describe a specific atom or molecule."""
    entries = _scan_registry()
    entry = next((e for e in entries if e.get('id') == args.id), None)
    
    if not entry:
        # Fuzzy search
        matches = get_close_matches(args.id, [e.get('id', '') for e in entries], n=3, cutoff=0.6)
        if matches:
            print(f"Did you mean one of these?")
            for m in matches:
                print(f"  {m}")
        else:
            print(f"No entry found for '{args.id}'.")
        return
    
    # Print formatted output
    print("=" * 60)
    print(f"  {entry.get('id', 'unknown')}")
    print("=" * 60)
    print(f"  Kind:        {entry.get('kind', '?')}")
    print(f"  Version:     {entry.get('version', '?')}")
    print(f"  Status:      {entry.get('status', '?')}")
    print(f"  Author:      {entry.get('author', '?')}")
    print(f"  Created:     {entry.get('created', '?')}")
    print(f"  Modified:    {entry.get('modified', '?')}")
    print(f"  Implements:  {entry.get('implements', '?')}")
    print(f"  Impl Kind:   {entry.get('impl_kind', '?')}")
    print(f"  Parser:      {entry.get('parser', 'none')}")
    
    # Inputs
    if entry.get('inputs'):
        print(f"\n  Inputs:")
        for inp in entry['inputs']:
            req = "*" if inp.get('required') else ""
            default = f" (default: {inp.get('default', '')})" if inp.get('default') else ""
            print(f"    - {inp['name']} ({inp.get('type', 'string')}) {req}{default}")
            if inp.get('description'):
                print(f"      {inp['description']}")
    
    # Outputs
    if entry.get('outputs'):
        print(f"\n  Outputs: {entry['outputs']}")
    
    # Molecule steps
    if entry.get('steps'):
        print(f"\n  Steps:")
        for step in entry['steps']:
            dep = ""
            if step.get('depends_on'):
                dep = f" (depends: {step['depends_on']})"
            print(f"    - {step['id']}: {step.get('atom', '?')}{dep}")
    
    # Body
    body = entry.get('_body', '')
    if body:
        print(f"\n  {body}")
    
    print(f"\n  File: {entry.get('_path', '?')}")


def cmd_search(args):
    """Search entries by query."""
    entries = _scan_registry()
    results = _search_entries(entries, args.query, fields=args.fields.split(','))
    
    if not results:
        print(f"No entries matching '{args.query}'.")
        return
    
    print(f"Search results for '{args.query}':\n")
    
    for e in results:
        print(f"  {e.get('id', '?')} ({e.get('kind', '?')}) — {e.get('status', '?')}")
        desc = e.get('description', '')
        if desc:
            print(f"    {desc[:100]}{'...' if len(desc) > 100 else ''}")
    
    print(f"\nTotal: {len(results)}")


def cmd_regenerate(args):
    """Regenerate registry entries from source YAML files."""
    atoms_created = []
    molecules_created = []
    
    # Scan atom YAMLs (top-level + subdirectories, deduped)
    if TOOLS_DIR.exists():
        seen_ids = set()
        # First pass: collect top-level IDs (these take priority)
        for yaml_file in sorted(TOOLS_DIR.glob("*.yaml")):
            seen_ids.add(yaml_file.stem)
        # Second pass: generate from top-level YAMLs
        for yaml_file in sorted(TOOLS_DIR.glob("*.yaml")):
            atom_id = yaml_file.stem
            entry = _generate_entry_from_source('atom', atom_id)
            if entry:
                path = _write_entry(entry)
                atoms_created.append(atom_id)
                print(f"  Generated: {atom_id} -> {path}")
        # Third pass: subdirectory YAMLs (only if no top-level YAML exists with same ID)
        for yaml_file in sorted(TOOLS_DIR.rglob("*.yaml")):
            if yaml_file.parent == TOOLS_DIR:
                continue  # already handled above
            atom_id = yaml_file.parent.name
            if atom_id in seen_ids:
                continue  # top-level YAML already handles this atom
            seen_ids.add(atom_id)
            entry = _generate_entry_from_source('atom', atom_id)
            if entry:
                path = _write_entry(entry)
                atoms_created.append(atom_id)
                print(f"  Generated: {atom_id} -> {path}")
    
    # Scan molecule YAMLs
    if SKILLS_DIR.exists():
        for yaml_file in sorted(SKILLS_DIR.glob("*.yaml")):
            molecule_id = yaml_file.stem
            entry = _generate_entry_from_source('molecule', molecule_id)
            if entry:
                path = _write_entry(entry)
                molecules_created.append(molecule_id)
                print(f"  Generated: {molecule_id} -> {path}")
    
    print(f"\nDone: {len(atoms_created)} atoms, {len(molecules_created)} molecules regenerated")


def cmd_diff(args):
    """Show diff between registry and source YAMLs (detect drift)."""
    drift = []
    
    # Check atoms (top-level + subdirs)
    if TOOLS_DIR.exists():
        for yaml_file in sorted(TOOLS_DIR.rglob("*.yaml")):
            if yaml_file.parent == TOOLS_DIR:
                atom_id = yaml_file.stem
            else:
                atom_id = yaml_file.parent.name
            md_file = ATOMS_DIR / f"{atom_id}.md"
        if not md_file.exists():
            drift.append(f"ATOM MISSING: {atom_id} (yaml exists, no registry entry)")
        else:
            # Compare version and parser
            with open(yaml_file) as f:
                source = yaml.safe_load(f)
            entry = _load_entry(md_file)
            if entry:
                if str(source.get('version', 1)) != str(entry.get('version', '?')):
                    drift.append(f"VERSION DRIFT: {atom_id} (yaml={source.get('version')}, registry={entry.get('version')})")
                if 'outputs' in source and isinstance(source['outputs'], dict):
                    yaml_parser = source['outputs'].get('parser', 'none')
                    if yaml_parser != entry.get('parser', 'none'):
                        drift.append(f"PARSER DRIFT: {atom_id} (yaml={yaml_parser}, registry={entry.get('parser')})")
    
    # Check molecules
    for yaml_file in sorted(SKILLS_DIR.glob("*.yaml")):
        mol_id = yaml_file.stem
        md_file = MOLECULES_DIR / f"{mol_id}.md"
        if not md_file.exists():
            drift.append(f"MOLECULE MISSING: {mol_id} (yaml exists, no registry entry)")
    
    if drift:
        print("Drift detected:")
        for d in drift:
            print(f"  - {d}")
    else:
        print("No drift detected. Registry is in sync with source YAMLs.")


# =============================================================================
# Main
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        prog="securatron",
        description="Securatron Registry CLI — inspect atoms, molecules, and registry health"
    )
    subparsers = parser.add_subparsers(dest="command", help="Sub-commands")
    
    # list
    p_list = subparsers.add_parser("list", help="List all atoms or molecules")
    p_list.add_argument("--kind", choices=["atom", "molecule"], default=None,
                        help="Filter by kind")
    p_list.add_argument("--status", choices=["draft", "tested", "promoted", "deprecated"],
                        default=None, help="Filter by status")
    p_list.add_argument("--format", choices=["table", "json"], default="table",
                        help="Output format")
    
    # describe
    p_desc = subparsers.add_parser("describe", help="Describe a specific atom or molecule")
    p_desc.add_argument("id", help="Atom or molecule ID (e.g., web.browser.drill)")
    
    # search
    p_search = subparsers.add_parser("search", help="Search entries by query")
    p_search.add_argument("query", help="Search query")
    p_search.add_argument("--fields", default="id,description,body",
                          help="Comma-separated fields to search (default: id,description,body)")
    
    # regenerate
    subparsers.add_parser("regenerate", help="Regenerate registry entries from source YAMLs")
    
    # diff
    subparsers.add_parser("diff", help="Check for drift between registry and source YAMLs")
    
    args = parser.parse_args()
    
    if args.command == "list":
        cmd_list(args)
    elif args.command == "describe":
        cmd_describe(args)
    elif args.command == "search":
        cmd_search(args)
    elif args.command == "regenerate":
        cmd_regenerate(args)
    elif args.command == "diff":
        cmd_diff(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
