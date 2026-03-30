#!/usr/bin/env python3
"""
Verification Script for Genetic Variant Annotation Changes

Verifies that all critical changes from the review have been implemented:
1. export_all() function exists
2. _save_plot() function exists
3. SKILL.md has correct structure
4. test_pickle_load.py exists
"""

import sys
from pathlib import Path
import ast
import re

def check_function_exists(file_path, function_name):
    """Check if a function exists in a Python file."""
    try:
        with open(file_path, 'r') as f:
            tree = ast.parse(f.read())

        functions = [node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)]
        return function_name in functions
    except Exception as e:
        return False, str(e)

def check_skill_md_structure():
    """Check SKILL.md has correct structure."""
    skill_path = Path("SKILL.md")
    if not skill_path.exists():
        return False, "SKILL.md not found"

    with open(skill_path, 'r') as f:
        content = f.read()

    checks = {
        "Has 4 steps": len(re.findall(r'\*\*Step \d+ -', content)) == 4,
        "Has export_all": "export_all(" in content,
        "Has verification messages": content.count("✅ VERIFICATION") >= 4,
        "Has enforcement banner": "🚨 **MANDATORY" in content,
        "Has pickle in Outputs": "analysis_object.pkl" in content,
        "Input files is question #1": "1. **Input Files** (ASK THIS FIRST)" in content,
    }

    return all(checks.values()), checks

def main():
    print("="*70)
    print("VERIFICATION: GENETIC VARIANT ANNOTATION CHANGES")
    print("="*70)
    print()

    all_passed = True

    # Check 1: export_all() function
    print("1. Checking export_all() function...")
    export_file = Path("scripts/export_results.py")
    if not export_file.exists():
        print("   ❌ scripts/export_results.py not found")
        all_passed = False
    else:
        has_export_all = check_function_exists(export_file, "export_all")
        if has_export_all:
            print("   ✓ export_all() function exists")

            # Check it saves pickle
            with open(export_file, 'r') as f:
                content = f.read()
            if "pickle.dump" in content:
                print("   ✓ Saves pickle object")
            else:
                print("   ❌ Does not save pickle object")
                all_passed = False

            if "=== Export Complete ===" in content:
                print("   ✓ Has verification message")
            else:
                print("   ❌ Missing verification message")
                all_passed = False
        else:
            print("   ❌ export_all() function not found")
            all_passed = False

    print()

    # Check 2: _save_plot() function
    print("2. Checking _save_plot() function...")
    plot_file = Path("scripts/plot_variant_distribution.py")
    if not plot_file.exists():
        print("   ❌ scripts/plot_variant_distribution.py not found")
        all_passed = False
    else:
        has_save_plot = check_function_exists(plot_file, "_save_plot")
        if has_save_plot:
            print("   ✓ _save_plot() function exists")

            # Check it saves both PNG and SVG
            with open(plot_file, 'r') as f:
                content = f.read()
            if "format='png'" in content and "format='svg'" in content:
                print("   ✓ Saves both PNG and SVG")
            else:
                print("   ❌ Does not save both formats")
                all_passed = False

            # Check fallback
            if "except Exception" in content:
                print("   ✓ Has graceful fallback")
            else:
                print("   ❌ Missing graceful fallback")
                all_passed = False
        else:
            print("   ❌ _save_plot() function not found")
            all_passed = False

    print()

    # Check 3: SKILL.md structure
    print("3. Checking SKILL.md structure...")
    passed, checks = check_skill_md_structure()
    if isinstance(checks, dict):
        for check, result in checks.items():
            if result:
                print(f"   ✓ {check}")
            else:
                print(f"   ❌ {check}")
                all_passed = False
    else:
        print(f"   ❌ {checks}")
        all_passed = False

    print()

    # Check 4: test_pickle_load.py exists
    print("4. Checking test_pickle_load.py...")
    test_file = Path("scripts/test_pickle_load.py")
    if test_file.exists():
        print("   ✓ test_pickle_load.py exists")
        has_test_func = check_function_exists(test_file, "test_pickle_load")
        if has_test_func:
            print("   ✓ test_pickle_load() function exists")
        else:
            print("   ❌ test_pickle_load() function not found")
            all_passed = False
    else:
        print("   ❌ test_pickle_load.py not found")
        all_passed = False

    print()

    # Check 5: Line count
    print("5. Checking SKILL.md line count...")
    skill_path = Path("SKILL.md")
    if skill_path.exists():
        with open(skill_path, 'r') as f:
            line_count = len(f.readlines())
        if line_count <= 400:
            print(f"   ✓ SKILL.md has {line_count} lines (under 400 target)")
        elif line_count < 500:
            print(f"   ⚠️  SKILL.md has {line_count} lines (over 400 target, under 500 max)")
        else:
            print(f"   ❌ SKILL.md has {line_count} lines (over 500 max)")
            all_passed = False

    print()

    # Check 6: File organization
    print("6. Checking file organization...")
    required_files = [
        "SKILL.md",
        "scripts/export_results.py",
        "scripts/plot_variant_distribution.py",
        "scripts/load_example_data.py",
        "scripts/test_pickle_load.py",
        ".gitignore"
    ]

    for file_path in required_files:
        if Path(file_path).exists():
            print(f"   ✓ {file_path}")
        else:
            print(f"   ❌ {file_path} not found")
            all_passed = False

    print()
    print("="*70)

    if all_passed:
        print("✓✓✓ ALL VERIFICATIONS PASSED ✓✓✓")
        print("="*70)
        print()
        print("The genetic-variant-annotation skill has been successfully updated")
        print("with all critical changes from the CLAUDE.md compliance review.")
        print()
        print("Key changes verified:")
        print("  ✓ 4-step workflow in SKILL.md")
        print("  ✓ export_all() saves pickle objects")
        print("  ✓ PNG + SVG pattern with fallback")
        print("  ✓ Verification messages present")
        print("  ✓ Test script for pickle loading")
        print("  ✓ Proper file organization")
        return 0
    else:
        print("❌ SOME VERIFICATIONS FAILED")
        print("="*70)
        print()
        print("Please review the failures above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())

