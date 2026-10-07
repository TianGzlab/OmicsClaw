# Observed perturbation signatures

Mixscape is applied to an actual screen with supplied target and control labels.
The API copies AnnData, reuses or computes PCA, then normalizes count-like X
while preserving counts. pertpy computes the perturbation signature and mixture
classification. Both stages receive random_state.

With pertpy 1.0.3, split-based signatures use controls from the same split;
without splitting, the nearest-neighbour path uses n_neighbors. The CLI warns
and disables a missing split column; the API requires an explicit None.

Review target-specific KO/OE versus NP classifications and posterior values;
successful execution alone does not establish a perturbation effect. The
synthetic notebook example includes two known shifts and asserts detection in
both groups. It is an implementation check, not biological validation.
