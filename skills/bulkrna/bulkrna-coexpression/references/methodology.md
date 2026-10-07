# Co-expression method

R WGCNA computes Pearson correlations on the expression scale supplied by
the caller. `pickSoftThreshold` evaluates candidate powers; the first
signed scale-free R-squared above 0.8 is selected, otherwise the highest
fit is used. An explicit power overrides that selection.

`blockwiseModules` detects modules with the chosen power, the requested
minimum module size and merge cut height 0.25. The seed defaults to
WGCNA's 54321 and one R thread is used. Module identifiers are WGCNA color
names; grey means unassigned and is excluded from the module count.

Hub genes are the top absolute correlations with each module eigengene.
This ranks association within a module, not causal regulatory influence.
The function library exposes the threshold-fit and hub tables separately.

The legacy CLI could not finish integer input because WGCNA's compiled
correlation routine expected doubles; the matrix bridge now converts
storage to double. Its figure helper also accepts the actual color-string
module identifiers. The file `module_dendrogram.png` remains an assignment
overview for filename compatibility; it is not a dendrogram.
