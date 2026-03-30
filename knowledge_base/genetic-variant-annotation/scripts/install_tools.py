"""
Installation Helper for Annotation Tools

Provides automatic installation of SNPEff and VEP via conda.
"""

import subprocess
import sys
import shutil


def check_conda_available():
    """
    Check if conda is available.

    Returns
    -------
    bool
        True if conda is in PATH
    """
    return shutil.which('conda') is not None


def install_snpeff():
    """
    Install SNPEff via bioconda.

    This is a managed dependency (pre-built binary) that can be safely
    auto-installed in conda environments.

    Returns
    -------
    bool
        True if installation successful

    Raises
    ------
    RuntimeError
        If conda is not available or installation fails
    """
    if not check_conda_available():
        raise RuntimeError(
            "conda is not available. Please install conda first:\n"
            "  https://docs.conda.io/en/latest/miniconda.html\n\n"
            "Or install SNPEff manually:\n"
            "  conda install -c bioconda snpeff"
        )

    print("=" * 70)
    print("Installing SNPEff via bioconda...")
    print("=" * 70)
    print()
    print("This will install:")
    print("  - SNPEff (variant annotation tool)")
    print("  - Java runtime (bundled)")
    print()
    print("Installation size: ~250 MB")
    print("Time: ~2-5 minutes")
    print()

    cmd = [
        'conda', 'install',
        '-c', 'bioconda',
        '-y',  # Auto-confirm
        'snpeff'
    ]

    print("Running:", ' '.join(cmd))
    print()

    try:
        result = subprocess.run(
            cmd,
            check=True,
            text=True
        )

        print()
        print("=" * 70)
        print("✓ SNPEff installed successfully!")
        print("=" * 70)
        print()

        # Verify installation
        from run_snpeff import check_snpeff_installation
        is_installed, snpeff_path, version = check_snpeff_installation()

        if is_installed:
            print(f"  Location: {snpeff_path}")
            print(f"  Version: {version}")
            print()
            return True
        else:
            print("  WARNING: Installation completed but SNPEff not found in PATH")
            print("  You may need to restart your shell or activate your conda environment")
            return False

    except subprocess.CalledProcessError as e:
        print()
        print("=" * 70)
        print("✗ SNPEff installation failed")
        print("=" * 70)
        print()
        print("Please install manually:")
        print("  conda install -c bioconda snpeff")
        print()
        print("Or use VEP instead:")
        print("  conda install -c bioconda ensembl-vep")
        raise RuntimeError(f"SNPEff installation failed: {e}")


def install_vep():
    """
    Install Ensembl VEP via bioconda.

    Note: VEP cache must be installed separately (15-20 GB).

    Returns
    -------
    bool
        True if installation successful

    Raises
    ------
    RuntimeError
        If conda is not available or installation fails
    """
    if not check_conda_available():
        raise RuntimeError(
            "conda is not available. Please install conda first:\n"
            "  https://docs.conda.io/en/latest/miniconda.html\n\n"
            "Or install VEP manually:\n"
            "  conda install -c bioconda ensembl-vep"
        )

    print("=" * 70)
    print("Installing Ensembl VEP via bioconda...")
    print("=" * 70)
    print()
    print("This will install:")
    print("  - Ensembl VEP (variant annotation tool)")
    print("  - Perl dependencies")
    print()
    print("Installation size: ~500 MB")
    print("Time: ~5-10 minutes")
    print()
    print("NOTE: VEP cache must be installed separately (15-20 GB):")
    print("  vep_install -a c -s homo_sapiens -y GRCh38")
    print()

    cmd = [
        'conda', 'install',
        '-c', 'bioconda',
        '-y',  # Auto-confirm
        'ensembl-vep'
    ]

    print("Running:", ' '.join(cmd))
    print()

    try:
        result = subprocess.run(
            cmd,
            check=True,
            text=True
        )

        print()
        print("=" * 70)
        print("✓ VEP installed successfully!")
        print("=" * 70)
        print()

        # Verify installation
        from run_vep import check_vep_installation
        is_installed, vep_path, version = check_vep_installation()

        if is_installed:
            print(f"  Location: {vep_path}")
            print(f"  Version: {version}")
            print()
            print("NEXT STEP: Install VEP cache (required):")
            print("  vep_install -a c -s homo_sapiens -y GRCh38")
            print()
            return True
        else:
            print("  WARNING: Installation completed but VEP not found in PATH")
            print("  You may need to restart your shell or activate your conda environment")
            return False

    except subprocess.CalledProcessError as e:
        print()
        print("=" * 70)
        print("✗ VEP installation failed")
        print("=" * 70)
        print()
        print("Please install manually:")
        print("  conda install -c bioconda ensembl-vep")
        print()
        print("Or use SNPEff instead:")
        print("  conda install -c bioconda snpeff")
        raise RuntimeError(f"VEP installation failed: {e}")


def install_annotation_tool(tool='snpeff'):
    """
    Install the specified annotation tool.

    Parameters
    ----------
    tool : str
        Tool to install ('snpeff' or 'vep')

    Returns
    -------
    bool
        True if installation successful
    """
    if tool.lower() == 'snpeff':
        return install_snpeff()
    elif tool.lower() == 'vep':
        return install_vep()
    else:
        raise ValueError(f"Unknown tool: {tool}. Choose 'snpeff' or 'vep'")


if __name__ == '__main__':
    import argparse

    parser = argparse.ArgumentParser(
        description='Install variant annotation tools via conda'
    )
    parser.add_argument(
        'tool',
        choices=['snpeff', 'vep'],
        help='Tool to install'
    )

    args = parser.parse_args()

    try:
        success = install_annotation_tool(args.tool)
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\nError: {e}", file=sys.stderr)
        sys.exit(1)

