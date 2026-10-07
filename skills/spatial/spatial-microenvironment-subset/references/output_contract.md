# Output contract

subset returns a new AnnData and leaves the input unchanged. Expression X,
layers and raw are sliced without normalization. selection_table returns
coordinates, center identities, role and nearest-center distance, plus the
selection label columns. selection_figure returns a Figure without writing it.

The CLI writes spatial_microenvironment_subset.h5ad, report.md, result.json,
commands.sh and requirements.txt. Its tables are:

- tables/selected_observations.csv: all selected observations, labels and distances.
- tables/center_observations.csv: selected centers only; empty when centers are excluded.
- tables/label_composition.csv: full-input and subset counts/percentages per label.
- tables/selection_summary.csv: parameters, resolved units and selection counts.

figures/microenvironment_selection.png is written when the selection plot
succeeds. Missing center labels or an empty filtered selection raise errors.

obs contains microenv_role, microenv_is_center, microenv_within_radius,
microenv_nearest_center and microenv_distance_native. microenv_distance_microns
exists only when coordinate scale is known. The legacy selection metadata
remains in uns['omicsclaw_spatial_microenvironment']; the separate library
run record is removed by run_info(keep=False) before the CLI writes H5AD.
