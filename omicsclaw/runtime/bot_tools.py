from __future__ import annotations

from dataclasses import dataclass

from .engineering_tools import build_engineering_tool_specs
from .tool_registry import ToolRegistry
from .tool_spec import (
    APPROVAL_MODE_ASK,
    PROGRESS_POLICY_ANALYSIS,
    RESULT_POLICY_INSPECTION_REFERENCE,
    RESULT_POLICY_KNOWLEDGE_REFERENCE,
    RESULT_POLICY_MEMORY_WRITE,
    RESULT_POLICY_SUMMARY_OR_MEDIA,
    RESULT_POLICY_WEB_REFERENCE,
    RISK_LEVEL_HIGH,
    RISK_LEVEL_MEDIUM,
    ToolSpec,
)


@dataclass(frozen=True, slots=True)
class BotToolContext:
    skill_names: tuple[str, ...]
    skill_desc_text: str


def build_bot_tool_specs(context: BotToolContext) -> list[ToolSpec]:
    specs = [
        ToolSpec(
            name="omicsclaw",
            description=(
                f"Run an OmicsClaw multi-omics analysis skill. Available canonical skills: {context.skill_desc_text}. "
                "Legacy aliases are also accepted and resolved automatically. "
                "Use mode='demo' to run with built-in synthetic data. "
                "Use mode='file' when the user has sent an omics data file. "
                "If `sc-batch-integration` recommends upstream preparation and the user explicitly agrees, "
                "rerun this tool with `auto_prepare=true` so OmicsClaw performs the recommended "
                "`sc-standardize-input` / `sc-preprocessing` steps before the final integration call. "
                "IMPORTANT: Preserve exact numerical values, warnings, errors, and file paths when relaying results. "
                "By default only a text summary is returned (return_media omitted or empty). "
                "Set return_media ONLY when the user explicitly asks for figures/plots/tables. "
                "Use 'all' to send everything, or a keyword to filter "
                "(e.g. 'umap' for UMAP plots, 'qc' for QC violin, 'cluster' for cluster tables). "
                "Multiple keywords can be comma-separated (e.g. 'umap,qc')."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "skill": {
                        "type": "string",
                        "enum": list(context.skill_names),
                    },
                    "mode": {
                        "type": "string",
                        "enum": ["file", "demo", "path"],
                        "description": (
                            "'demo' = built-in synthetic data; "
                            "'file' = user uploaded a file via messaging; "
                            "'path' = user provided a file path on the server."
                        ),
                    },
                    "return_media": {
                        "type": "string",
                        "description": (
                            "Filter for which figures/tables to send back. "
                            "Omit or leave empty for text summary only (default). "
                            "'all' = send all figures and tables. "
                            "Otherwise a comma-separated list of keywords to match filenames "
                            "(e.g. 'umap', 'qc', 'violin', 'cluster', 'umap,qc'). "
                            "Only set when the user explicitly asks for visual results."
                        ),
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Server-side file path or filename for mode='path'.",
                    },
                    "query": {
                        "type": "string",
                        "description": "Natural language query for auto-routing.",
                    },
                    "extra_args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Additional CLI arguments (e.g. ['--method', 'spagcn']).",
                    },
                    "method": {
                        "type": "string",
                        "description": "Analysis method override passed as --method.",
                    },
                    "batch_key": {
                        "type": "string",
                        "description": (
                            "Batch/sample metadata column passed as --batch-key. "
                            "Especially important for sc-batch-integration. "
                            "If omitted for sc-batch-integration, OmicsClaw will inspect the AnnData object "
                            "and ask the user to choose before running."
                        ),
                    },
                    "confirm_workflow_skip": {
                        "type": "boolean",
                        "description": (
                            "Only for explicit user overrides. "
                            "If true, bypasses the standardize/preprocess workflow pause for sc-batch-integration "
                            "and runs direct integration anyway."
                        ),
                    },
                    "auto_prepare": {
                        "type": "boolean",
                        "description": (
                            "Only when the user explicitly agrees to preparatory steps. "
                            "For sc-batch-integration, automatically runs the recommended upstream workflow "
                            "(`sc-standardize-input` and/or `sc-preprocessing`) before the final integration step."
                        ),
                    },
                    "n_epochs": {
                        "type": "integer",
                        "description": (
                            "Number of training epochs for deep learning methods. "
                            "Defaults per method if omitted: "
                            "cell2location=30000, destvi=2500, stereoscope=150000, tangram=1000. "
                            "Only set when the user explicitly requests a custom epoch count."
                        ),
                    },
                    "data_type": {
                        "type": "string",
                        "description": "Data platform type passed as --data-type.",
                    },
                },
                "required": ["skill", "mode"],
            },
            surfaces=("bot",),
            context_params=("session_id", "chat_id"),
            read_only=False,
            concurrency_safe=False,
            result_policy=RESULT_POLICY_SUMMARY_OR_MEDIA,
            progress_policy=PROGRESS_POLICY_ANALYSIS,
            risk_level=RISK_LEVEL_MEDIUM,
            writes_workspace=True,
            policy_tags=("analysis", "workflow"),
        ),
        ToolSpec(
            name="replot_skill",
            description=(
                "Re-render R Enhanced (ggplot2) plots from an existing skill output directory. "
                "Use this ONLY when the user explicitly asks to 're-draw with R', 'use R Enhanced', "
                "'make it prettier', or 'replot'. "
                "The skill must have been run first (via the omicsclaw tool). "
                "R Enhanced is currently supported for single-cell scRNA skills only "
                "(sc-qc, sc-de, sc-markers, sc-preprocessing, sc-clustering, etc.). "
                "By default returns all generated R Enhanced figures."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "skill": {
                        "type": "string",
                        "description": "Skill alias to replot (e.g. 'sc-qc', 'sc-de', 'sc-markers').",
                    },
                    "output_path": {
                        "type": "string",
                        "description": "Full path to the output directory from the previous skill run.",
                    },
                    "renderer": {
                        "type": "string",
                        "description": "Optional: run only a specific renderer (e.g. 'plot_feature_violin'). Omit to run all renderers.",
                    },
                    "return_media": {
                        "type": "string",
                        "description": "Filter for which R Enhanced figures to send. Default: 'all'. Use a keyword to filter (e.g. 'violin').",
                    },
                    "top_n": {"type": "integer", "description": "Number of top items to label/show."},
                    "font_size": {"type": "integer", "description": "Base font size in points."},
                    "width": {"type": "integer", "description": "Figure width in inches."},
                    "height": {"type": "integer", "description": "Figure height in inches."},
                    "dpi": {"type": "integer", "description": "Output resolution (default 300)."},
                    "palette": {"type": "string", "description": "Color palette name."},
                    "title": {"type": "string", "description": "Custom plot title."},
                },
                "required": ["skill", "output_path"],
            },
            surfaces=("bot",),
            context_params=("session_id", "chat_id"),
            read_only=False,
            concurrency_safe=False,
            result_policy=RESULT_POLICY_SUMMARY_OR_MEDIA,
            progress_policy=PROGRESS_POLICY_ANALYSIS,
            risk_level=RISK_LEVEL_MEDIUM,
            writes_workspace=True,
            policy_tags=("analysis", "workflow"),
        ),
        ToolSpec(
            name="save_file",
            description="Save a file that was sent via messaging to a specific folder. Default: OmicsClaw data/ directory.",
            parameters={
                "type": "object",
                "properties": {
                    "destination_folder": {"type": "string", "description": "Folder path (absolute)."},
                    "filename": {"type": "string", "description": "Optional filename."},
                },
                "required": ["destination_folder"],
            },
            surfaces=("bot",),
            read_only=False,
            concurrency_safe=False,
            risk_level=RISK_LEVEL_MEDIUM,
            writes_workspace=True,
            policy_tags=("workspace", "artifact"),
        ),
        ToolSpec(
            name="write_file",
            description="Create or overwrite a file with the given content. Files are saved to the output/ directory by default. ONLY use when user explicitly asks to create/save a file.",
            parameters={
                "type": "object",
                "properties": {
                    "content": {"type": "string", "description": "Full text content."},
                    "filename": {"type": "string", "description": "Filename with extension."},
                    "destination_folder": {"type": "string", "description": "Folder path (absolute). Default: OmicsClaw data/."},
                },
                "required": ["content", "filename"],
            },
            surfaces=("bot",),
            read_only=False,
            concurrency_safe=False,
            risk_level=RISK_LEVEL_MEDIUM,
            writes_workspace=True,
            policy_tags=("workspace", "artifact"),
        ),
        ToolSpec(
            name="generate_audio",
            description="Generate an MP3 audio file from text using edge-tts.",
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to convert to speech."},
                    "filename": {"type": "string", "description": "Output MP3 filename."},
                    "voice": {"type": "string", "description": "TTS voice. Default: en-GB-RyanNeural."},
                    "rate": {"type": "string", "description": "Speech rate. Default: '-5%'."},
                    "destination_folder": {"type": "string", "description": "Output folder."},
                },
                "required": ["text", "filename"],
            },
            surfaces=("bot",),
            read_only=False,
            concurrency_safe=False,
            writes_workspace=True,
            policy_tags=("artifact",),
        ),
        ToolSpec(
            name="parse_literature",
            description="Parse scientific literature (PDF, URL, DOI, PubMed ID) to extract GEO accessions and metadata, then download datasets. Use when user mentions a paper, sends a PDF, or provides a literature reference.",
            parameters={
                "type": "object",
                "properties": {
                    "input_type": {
                        "type": "string",
                        "enum": ["auto", "url", "doi", "pubmed", "file", "text"],
                        "description": "Type of input (default: auto-detect)",
                    },
                    "input_value": {
                        "type": "string",
                        "description": "URL, DOI, PubMed ID, file path, or text content",
                    },
                    "auto_download": {
                        "type": "boolean",
                        "description": "Automatically download datasets (default: true)",
                    },
                },
                "required": ["input_value"],
            },
            surfaces=("bot",),
            read_only=False,
            concurrency_safe=False,
            risk_level=RISK_LEVEL_MEDIUM,
            writes_workspace=True,
            touches_network=True,
            policy_tags=("knowledge", "network"),
        ),
        ToolSpec(
            name="fetch_geo_metadata",
            description="Fetch metadata for a specific GEO accession (GSE, GSM, or GPL). Use when user asks to fetch, query, or get information about a specific GEO ID.",
            parameters={
                "type": "object",
                "properties": {
                    "accession": {
                        "type": "string",
                        "description": "GEO accession ID (e.g., GSE204716, GSM123456)",
                    },
                    "download": {
                        "type": "boolean",
                        "description": "Download the dataset after fetching metadata (default: false)",
                    },
                },
                "required": ["accession"],
            },
            surfaces=("bot",),
            read_only=False,
            concurrency_safe=False,
            risk_level=RISK_LEVEL_MEDIUM,
            writes_workspace=True,
            touches_network=True,
            policy_tags=("knowledge", "network"),
        ),
        ToolSpec(
            name="list_directory",
            description="List contents of a directory. Use when user wants to see files in a folder.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path (default: current data directory)"},
                },
            },
            surfaces=("bot",),
            read_only=True,
            concurrency_safe=True,
            policy_tags=("workspace", "inspection"),
        ),
        ToolSpec(
            name="inspect_file",
            description="Display contents of a CSV, JSON, or TXT file. Use when user wants to view file contents.",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "Path to file"},
                    "lines": {"type": "integer", "description": "Number of lines to show (default: 20)"},
                },
                "required": ["file_path"],
            },
            surfaces=("bot",),
            read_only=True,
            concurrency_safe=True,
            policy_tags=("workspace", "inspection"),
        ),
        ToolSpec(
            name="download_file",
            description="Download a file from a URL. Use when user provides a direct file URL.",
            parameters={
                "type": "object",
                "properties": {
                    "url": {"type": "string", "description": "File URL"},
                    "destination": {"type": "string", "description": "Destination path (optional)"},
                },
                "required": ["url"],
            },
            surfaces=("bot",),
            read_only=False,
            concurrency_safe=False,
            risk_level=RISK_LEVEL_HIGH,
            approval_mode=APPROVAL_MODE_ASK,
            writes_workspace=True,
            touches_network=True,
            allowed_in_background=False,
            policy_tags=("network", "workspace", "artifact"),
        ),
        ToolSpec(
            name="create_json_file",
            description="Create a JSON file from structured data. Saved to output/ by default. ONLY use when user explicitly asks to save data as JSON.",
            parameters={
                "type": "object",
                "properties": {
                    "data": {"type": "object", "description": "Data to save as JSON"},
                    "filename": {"type": "string", "description": "Filename (without extension)"},
                    "destination": {"type": "string", "description": "Destination folder (optional)"},
                },
                "required": ["data", "filename"],
            },
            surfaces=("bot",),
            read_only=False,
            concurrency_safe=False,
            risk_level=RISK_LEVEL_MEDIUM,
            writes_workspace=True,
            policy_tags=("workspace", "artifact"),
        ),
        ToolSpec(
            name="create_csv_file",
            description="Create a CSV file from tabular data. Saved to output/ by default. ONLY use when user explicitly asks to save data as CSV.",
            parameters={
                "type": "object",
                "properties": {
                    "data": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": {},
                        },
                        "description": "Array of row objects",
                    },
                    "filename": {"type": "string", "description": "Filename (without extension)"},
                    "destination": {"type": "string", "description": "Destination folder (optional)"},
                },
                "required": ["data", "filename"],
            },
            surfaces=("bot",),
            read_only=False,
            concurrency_safe=False,
            risk_level=RISK_LEVEL_MEDIUM,
            writes_workspace=True,
            policy_tags=("workspace", "artifact"),
        ),
        ToolSpec(
            name="make_directory",
            description="Create a new directory under output/. ONLY use when user explicitly asks to create a folder.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path to create"},
                },
                "required": ["path"],
            },
            surfaces=("bot",),
            read_only=False,
            concurrency_safe=False,
            risk_level=RISK_LEVEL_MEDIUM,
            writes_workspace=True,
            policy_tags=("workspace", "artifact"),
        ),
        ToolSpec(
            name="move_file",
            description="Move or rename a file. ONLY use when user explicitly asks to move or rename files.",
            parameters={
                "type": "object",
                "properties": {
                    "source": {"type": "string", "description": "Source file path"},
                    "destination": {"type": "string", "description": "Destination path"},
                },
                "required": ["source", "destination"],
            },
            surfaces=("bot",),
            read_only=False,
            concurrency_safe=False,
            risk_level=RISK_LEVEL_MEDIUM,
            approval_mode=APPROVAL_MODE_ASK,
            writes_workspace=True,
            allowed_in_background=False,
            policy_tags=("workspace", "mutation"),
        ),
        ToolSpec(
            name="remove_file",
            description="Delete a file or directory. ONLY use when user explicitly asks to remove files/folders.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File or directory path to remove"},
                },
                "required": ["path"],
            },
            surfaces=("bot",),
            read_only=False,
            concurrency_safe=False,
            risk_level=RISK_LEVEL_HIGH,
            approval_mode=APPROVAL_MODE_ASK,
            writes_workspace=True,
            allowed_in_background=False,
            policy_tags=("workspace", "destructive"),
        ),
        ToolSpec(
            name="get_file_size",
            description="Get file size in MB. Use when user asks about file size.",
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {"type": "string", "description": "File path"},
                },
                "required": ["file_path"],
            },
            surfaces=("bot",),
            read_only=True,
            concurrency_safe=True,
            policy_tags=("workspace", "inspection"),
        ),
        ToolSpec(
            name="remember",
            description=(
                "Save important information to persistent memory so you can recall it "
                "in future conversations. Use this to remember: user preferences "
                "(language, default methods, DPI settings), biological insights "
                "(cell type annotations, spatial domains found), and project context "
                "(research goals, species, tissue type, disease model). "
                "Memory persists across conversations and bot restarts."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "memory_type": {
                        "type": "string",
                        "enum": ["preference", "insight", "project_context"],
                        "description": (
                            "Type of memory to save. "
                            "'preference' = user settings (language, default method, DPI). "
                            "'insight' = biological discovery (cell types, clusters). "
                            "'project_context' = research context (species, tissue, disease, goal)."
                        ),
                    },
                    "key": {
                        "type": "string",
                        "description": (
                            "For preference: setting name (e.g. 'language', 'default_method', 'dpi'). "
                            "For insight: entity ID (e.g. 'cluster_0', 'domain_3'). "
                            "For project_context: not used."
                        ),
                    },
                    "value": {
                        "type": "string",
                        "description": (
                            "For preference: setting value (e.g. 'Chinese', 'tangram', '300'). "
                            "For insight: biological label (e.g. 'T cells', 'tumor region'). "
                            "For project_context: not used."
                        ),
                    },
                    "domain": {
                        "type": "string",
                        "description": "For preference: scope of the setting (e.g. 'global', 'spatial-preprocess'). Default: 'global'.",
                    },
                    "entity_type": {
                        "type": "string",
                        "description": "For insight: type of entity (e.g. 'cluster', 'spatial_domain', 'cell_type').",
                    },
                    "source_analysis_id": {
                        "type": "string",
                        "description": "For insight: ID of the analysis that produced this insight (optional).",
                    },
                    "confidence": {
                        "type": "string",
                        "enum": ["user_confirmed", "ai_predicted"],
                        "description": "For insight: confidence level. Use 'user_confirmed' when user explicitly states a label.",
                    },
                    "project_goal": {
                        "type": "string",
                        "description": "For project_context: research goal/objective.",
                    },
                    "species": {
                        "type": "string",
                        "description": "For project_context: species (e.g. 'human', 'mouse').",
                    },
                    "tissue_type": {
                        "type": "string",
                        "description": "For project_context: tissue type (e.g. 'brain', 'liver', 'tumor').",
                    },
                    "disease_model": {
                        "type": "string",
                        "description": "For project_context: disease model (e.g. 'breast cancer', 'Alzheimer').",
                    },
                },
                "required": ["memory_type"],
            },
            surfaces=("bot",),
            context_params=("session_id",),
            read_only=False,
            concurrency_safe=False,
            result_policy=RESULT_POLICY_MEMORY_WRITE,
            risk_level=RISK_LEVEL_MEDIUM,
            policy_tags=("memory", "knowledge"),
        ),
        ToolSpec(
            name="recall",
            description=(
                "Retrieve information from persistent memory. Use this to recall: "
                "user preferences, biological insights, project context, dataset info, "
                "and analysis history saved in previous conversations. "
                "You can search by keyword or list memories by type."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Search query to find specific memories. "
                            "E.g. 'language preference', 'cluster annotations', 'species'."
                        ),
                    },
                    "memory_type": {
                        "type": "string",
                        "enum": ["preference", "insight", "project_context", "dataset", "analysis"],
                        "description": "Optional: filter by memory type.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of memories to return (default: 10).",
                    },
                },
            },
            surfaces=("bot",),
            context_params=("session_id",),
            read_only=True,
            concurrency_safe=True,
            policy_tags=("memory", "knowledge"),
        ),
        ToolSpec(
            name="forget",
            description=(
                "Remove a specific memory from persistent storage. "
                "Use when user explicitly asks to forget or remove a saved preference, "
                "insight, or other memory. Provide a query or memory_id to identify "
                "which memory to remove."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "memory_id": {
                        "type": "string",
                        "description": "The memory_id of the memory to forget (if known).",
                    },
                    "query": {
                        "type": "string",
                        "description": "Search query to find the memory to forget.",
                    },
                },
            },
            surfaces=("bot",),
            context_params=("session_id",),
            read_only=False,
            concurrency_safe=False,
            result_policy=RESULT_POLICY_MEMORY_WRITE,
            risk_level=RISK_LEVEL_MEDIUM,
            policy_tags=("memory", "knowledge"),
        ),
        ToolSpec(
            name="consult_knowledge",
            description=(
                "Query the OmicsClaw knowledge base for analysis guidance. "
                "Use this PROACTIVELY when: (1) user is unsure which analysis to run, "
                "(2) user asks about method selection or parameters, "
                "(3) an analysis fails and user needs troubleshooting, "
                "(4) user asks 'how to' or 'which method' questions, "
                "(5) before running complex analyses to check best practices. "
                "Returns relevant decision guides, best practices, or troubleshooting advice."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural language question about methodology, parameters, or troubleshooting",
                    },
                    "category": {
                        "type": "string",
                        "enum": [
                            "decision-guide", "best-practices", "troubleshooting",
                            "workflow", "method-reference", "interpretation",
                            "preprocessing-qc", "statistics", "tool-setup",
                            "domain-knowledge", "knowhow", "reference-script", "all",
                        ],
                        "description": "Filter by document type. Default: 'all'",
                    },
                    "domain": {
                        "type": "string",
                        "enum": [
                            "spatial", "singlecell", "genomics", "proteomics",
                            "metabolomics", "bulkrna", "general", "all",
                        ],
                        "description": "Filter by omics domain. Default: 'all'",
                    },
                },
                "required": ["query"],
            },
            surfaces=("bot",),
            read_only=True,
            concurrency_safe=True,
            result_policy=RESULT_POLICY_KNOWLEDGE_REFERENCE,
            policy_tags=("knowledge", "reference"),
        ),
        ToolSpec(
            name="resolve_capability",
            description=(
                "Resolve whether a user request is fully covered by an existing OmicsClaw skill, "
                "partially covered, or not covered. Use this before non-trivial analysis requests "
                "when skill coverage is uncertain."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The user's analysis request in natural language.",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Optional server-side data path or filename mentioned by the user.",
                    },
                    "domain_hint": {
                        "type": "string",
                        "enum": [
                            "spatial", "singlecell", "genomics", "proteomics",
                            "metabolomics", "bulkrna", "",
                        ],
                        "description": "Optional domain hint if the user has already narrowed the domain.",
                    },
                },
                "required": ["query"],
            },
            surfaces=("bot",),
            read_only=True,
            concurrency_safe=True,
            policy_tags=("planning", "routing"),
        ),
        ToolSpec(
            name="web_method_search",
            description=(
                "Search external web sources for up-to-date method documentation, papers, or workflow guidance. "
                "Use this when resolve_capability indicates no_skill or partial_skill and external references are needed."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query describing the method, package, or analysis goal.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": "Maximum number of search results to fetch. Default: 3.",
                    },
                    "topic": {
                        "type": "string",
                        "enum": ["general", "news", "finance"],
                        "description": "Search topic. Default: general.",
                    },
                },
                "required": ["query"],
            },
            surfaces=("bot",),
            read_only=True,
            concurrency_safe=True,
            result_policy=RESULT_POLICY_WEB_REFERENCE,
            risk_level=RISK_LEVEL_MEDIUM,
            touches_network=True,
            policy_tags=("knowledge", "network"),
        ),
        ToolSpec(
            name="create_omics_skill",
            description=(
                "Create a new OmicsClaw-native skill scaffold under skills/<domain>/<skill-name>/ "
                "using templates/SKILL-TEMPLATE.md as the base structure. Use this only when the user "
                "explicitly wants a reusable new skill added to OmicsClaw. If a previous "
                "custom_analysis_execute run succeeded, you can promote that notebook into the new skill."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "request": {
                        "type": "string",
                        "description": "Original user request describing the desired reusable skill.",
                    },
                    "skill_name": {
                        "type": "string",
                        "description": "Preferred lowercase hyphenated skill alias.",
                    },
                    "domain": {
                        "type": "string",
                        "enum": [
                            "spatial", "singlecell", "genomics", "proteomics",
                            "metabolomics", "bulkrna", "orchestrator",
                        ],
                        "description": "Target OmicsClaw domain for the new skill. Optional if it can be inferred from a promoted autonomous analysis.",
                    },
                    "summary": {
                        "type": "string",
                        "description": "One-line summary of what the skill should do.",
                    },
                    "source_analysis_dir": {
                        "type": "string",
                        "description": "Optional path to a successful custom_analysis_execute output directory to promote into a skill.",
                    },
                    "promote_from_latest": {
                        "type": "boolean",
                        "description": "If true, promote the most recent successful autonomous analysis output when source_analysis_dir is not provided.",
                    },
                    "input_formats": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of domain-specific input format notes.",
                    },
                    "primary_outputs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of primary outputs the new skill should emit.",
                    },
                    "methods": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of primary methods/backends for the skill.",
                    },
                    "trigger_keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of routing keywords users may say naturally.",
                    },
                    "create_tests": {
                        "type": "boolean",
                        "description": "Whether to generate a minimal test scaffold. Default: true.",
                    },
                },
                "required": ["request"],
            },
            surfaces=("bot",),
            read_only=False,
            concurrency_safe=False,
            risk_level=RISK_LEVEL_HIGH,
            approval_mode=APPROVAL_MODE_ASK,
            writes_workspace=True,
            allowed_in_background=False,
            policy_tags=("repo", "skill", "workspace"),
        ),
        ToolSpec(
            name="custom_analysis_execute",
            description=(
                "Execute custom analysis code in a restricted Jupyter notebook when an existing OmicsClaw skill "
                "does not fully cover the request. Provide one self-contained Python snippet. "
                "The notebook exposes INPUT_FILE, ANALYSIS_GOAL, ANALYSIS_CONTEXT, WEB_CONTEXT, and AUTONOMOUS_OUTPUT_DIR. "
                "Shell, package install, and direct network access are blocked."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "goal": {
                        "type": "string",
                        "description": "Short statement of the analysis objective.",
                    },
                    "analysis_plan": {
                        "type": "string",
                        "description": "Concise markdown plan describing what the custom analysis will do.",
                    },
                    "python_code": {
                        "type": "string",
                        "description": "A single self-contained Python snippet to execute inside the restricted notebook.",
                    },
                    "context": {
                        "type": "string",
                        "description": "Optional local context from the conversation or prior skill outputs.",
                    },
                    "web_context": {
                        "type": "string",
                        "description": "Optional external method notes returned by web_method_search.",
                    },
                    "file_path": {
                        "type": "string",
                        "description": "Optional input file path to expose as INPUT_FILE inside the notebook.",
                    },
                    "sources": {
                        "type": "string",
                        "description": "Optional markdown list of cited URLs or source notes to persist alongside the notebook.",
                    },
                    "output_label": {
                        "type": "string",
                        "description": "Optional short label for the output directory prefix.",
                    },
                },
                "required": ["goal", "analysis_plan", "python_code"],
            },
            surfaces=("bot",),
            read_only=False,
            concurrency_safe=False,
            risk_level=RISK_LEVEL_HIGH,
            approval_mode=APPROVAL_MODE_ASK,
            writes_workspace=True,
            policy_tags=("analysis", "workflow", "notebook"),
        ),
        ToolSpec(
            name="inspect_data",
            description=(
                "Instantly inspect an AnnData (.h5ad) file's metadata — cell/gene counts, "
                "obs/var columns, embeddings (obsm), layers, uns keys — WITHOUT loading "
                "the expression matrix. Fast even for very large files. "
                "Also supports pre-run method suitability and parameter preview when "
                "`method` (and optionally `skill`) is provided. "
                "ALWAYS call this when the user asks to 'explore', 'inspect', "
                "'what can I do with', or vaguely 'analyze' a dataset WITHOUT specifying "
                "a concrete analysis pipeline. Returns a formatted summary and suggested "
                "analysis directions. Do NOT call omicsclaw for open-ended exploratory queries."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to the .h5ad file to inspect.",
                    },
                    "skill": {
                        "type": "string",
                        "description": "Optional skill alias for preflight preview (e.g. spatial-domain-identification).",
                    },
                    "method": {
                        "type": "string",
                        "description": "Optional method name for suitability + parameter preview.",
                    },
                    "preview_params": {
                        "type": "boolean",
                        "description": "If true, include a pre-run method suitability and default parameter preview block.",
                    },
                },
                "required": ["file_path"],
            },
            surfaces=("bot",),
            read_only=True,
            concurrency_safe=True,
            result_policy=RESULT_POLICY_INSPECTION_REFERENCE,
            policy_tags=("inspection", "analysis"),
        ),
    ]
    specs.extend(build_engineering_tool_specs())
    return specs


def build_bot_tool_registry(context: BotToolContext) -> ToolRegistry:
    return ToolRegistry(build_bot_tool_specs(context))
