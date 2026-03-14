# 🧬 Contributing to OmicsClaw

We welcome contributions from anyone working in multi-omics analysis, bioinformatics, computational biology, or related fields.

## How to Contribute a Skill

### 1. Copy the template

```bash
cp -r templates/SKILL-TEMPLATE.md skills/<domain>/<skill-name>/SKILL.md
```

### 2. Define your skill

Edit `SKILL.md` with:
- **YAML frontmatter**: name, description, domain, dependencies
- **Markdown body**: Methodology, capabilities, workflow, input/output formats, and safety rules

### 3. Implement the skill

Create the Python implementation alongside SKILL.md:

```
skills/<domain>/<skill-name>/
├── SKILL.md              # Required
├── <skill_name>.py       # Required
└── tests/                # Required
    └── test_<skill>.py
```

### 4. Test locally

```bash
# Run demo mode
python omicsclaw.py run <skill-name> --demo

# Run tests
python -m pytest skills/<domain>/<skill-name>/tests/ -v
```

### 5. Submit

```bash
git checkout -b add-<skill-name>
git add skills/<domain>/<skill-name>/
git commit -m "Add <skill-name> skill for <domain>"
git push -u origin add-<skill-name>
# Open PR on GitHub
```

## Skill Guidelines

1. **Local-first**: All data processing happens locally. No mandatory cloud uploads.
2. **Reproducible**: Generate reports with version info and run commands.
3. **Single responsibility**: Each skill does one analysis task well.
4. **Documented**: Include SKILL.md with methodology and examples.
5. **Safe**: Warn before destructive actions. Include research-use disclaimer.
6. **Standardized output**: Follow the output structure (report.md, result.json, figures/).

## Naming Conventions

- Skill folder: lowercase, hyphens (`spatial-domains`, `vcf-ops`)
- Python files: lowercase, underscores (`spatial_domains.py`)
- Skill name in YAML: matches folder name exactly

## Code Standards

- Python 3.11+
- Type hints encouraged
- Use `pathlib` for file paths
- No hardcoded absolute paths
- Tests with pytest
- Follow existing skill patterns

## Supported Domains

OmicsClaw organizes skills by omics domain:

- `skills/spatial/` - Spatial transcriptomics (16 skills)
- `skills/singlecell/` - Single-cell omics (5 skills)
- `skills/genomics/` - Genomics (8 skills)
- `skills/proteomics/` - Proteomics (6 skills)
- `skills/metabolomics/` - Metabolomics (5 skills)
- `skills/orchestrator/` - Multi-domain routing

## For AI Agents Contributing Skills

AI coding agents should follow the same workflow, plus:

1. Read [`AGENTS.md`](AGENTS.md) for project structure and conventions
2. Read the target skill's `SKILL.md` before modifying code
3. Use `python omicsclaw.py list` to verify skills load correctly
4. Run `python -m pytest -v` to confirm all tests pass
5. Regenerate catalog: `python scripts/generate_catalog.py`

## SKILL.md Quality Checklist

Every SKILL.md should include:

- [ ] **YAML frontmatter** with name, description, version, domain, tags
- [ ] **Why This Exists** (problem it solves)
- [ ] **Core Capabilities** (what it does)
- [ ] **Workflow** (step-by-step methodology)
- [ ] **Input/Output** (data formats and structure)
- [ ] **Dependencies** (required and optional packages)
- [ ] **CLI Reference** (usage examples with --demo)
- [ ] **Safety** (local-first, disclaimer, no hallucination)

## Skill Ideas We Need

If you're looking for something to build:

**Spatial Transcriptomics:**
- Spatial niche identification with advanced methods
- 3D tissue reconstruction
- Multi-slice alignment and integration

**Single-Cell:**
- Multi-modal integration (RNA + ATAC + protein)
- Cell state dynamics
- Rare cell type detection

**Genomics:**
- Long-read variant calling
- Structural variant annotation
- Population genetics analysis

**Proteomics:**
- DIA-NN integration
- Protein-protein interaction networks
- PTM site prediction

**Metabolomics:**
- Metabolic pathway analysis
- Compound identification
- Flux balance analysis

**Multi-Omics:**
- Cross-omics integration
- Multi-view factor analysis
- Systems biology modeling

## Questions?

Open an issue on [GitHub](https://github.com/OmicsClaw/OmicsClaw/issues) or check the documentation. 🧬
