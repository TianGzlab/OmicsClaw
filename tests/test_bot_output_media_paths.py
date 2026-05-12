from bot.core import _collect_output_media_paths


def test_collect_output_media_paths_preserves_nested_figure_locations(tmp_path):
    run_dir = tmp_path / "spatial-domains__graphst__20260505_122949__8bc46746"
    figures_dir = run_dir / "figures"
    figures_dir.mkdir(parents=True)
    (figures_dir / "spatial_domains.png").write_bytes(b"png")
    (run_dir / "tables").mkdir()
    (run_dir / "tables" / "domain_summary.csv").write_text("domain,count\n0,1\n", encoding="utf-8")
    (run_dir / "reproducibility").mkdir()
    (run_dir / "reproducibility" / "analysis_notebook.ipynb").write_text("{}", encoding="utf-8")

    collected = _collect_output_media_paths(run_dir)

    assert collected.figure_paths == [figures_dir / "spatial_domains.png"]
    assert collected.table_paths == [run_dir / "tables" / "domain_summary.csv"]
    assert collected.notebook_paths == [run_dir / "reproducibility" / "analysis_notebook.ipynb"]
