"""Compatibility runner for CellBender checkpoint issues.

This wrapper patches CellBender's posterior generation so a failed checkpoint
serialization does not abort the whole remove-background workflow. The trained
model remains in memory, which is sufficient to compute the posterior and write
denoised outputs for the current run.
"""

from __future__ import annotations

import logging
import sys


def _install_checkpoint_compatibility_patch() -> None:
    """Patch CellBender to compute posterior without requiring ckpt.tar.gz."""
    import cellbender.remove_background.posterior as posterior_mod
    import cellbender.remove_background.run as run_mod

    Posterior = posterior_mod.Posterior
    PRmu = posterior_mod.PRmu
    PRq = posterior_mod.PRq

    logger = logging.getLogger("cellbender")

    def _compat_load_or_compute_posterior_and_save(dataset_obj, inferred_model, args):
        posterior = Posterior(
            dataset_obj=dataset_obj,
            vi_model=inferred_model,
            posterior_batch_size=args.posterior_batch_size,
            debug=args.debug,
        )

        def _do_posterior_regularization() -> None:
            device = "cuda" if getattr(args, "use_cuda", False) else "cpu"
            if args.posterior_regularization == "PRq":
                posterior.regularize_posterior(
                    regularization=PRq,
                    alpha=args.prq_alpha,
                    device=device,
                )
            elif args.posterior_regularization == "PRmu":
                posterior.regularize_posterior(
                    regularization=PRmu,
                    raw_count_matrix=dataset_obj.data["matrix"],
                    fpr=args.fpr[0],
                    per_gene=False,
                    device=device,
                )
            elif args.posterior_regularization == "PRmu_gene":
                posterior.regularize_posterior(
                    regularization=PRmu,
                    raw_count_matrix=dataset_obj.data["matrix"],
                    fpr=args.fpr[0],
                    per_gene=True,
                    device=device,
                )
            else:
                posterior.clear_regularized_posterior()

        logger.warning(
            "Checkpoint compatibility mode enabled: computing posterior from the in-memory "
            "model because checkpoint serialization is unavailable in this environment."
        )

        posterior.cell_noise_count_posterior_coo()
        _do_posterior_regularization()

        posterior_file = args.output_file[:-3] + "_posterior.h5"
        if posterior.save(file=posterior_file):
            logger.info("Saved posterior without relying on checkpoint tarball: %s", posterior_file)
        else:
            logger.warning("Failed to save posterior file in compatibility mode.")

        return posterior

    posterior_mod.load_or_compute_posterior_and_save = _compat_load_or_compute_posterior_and_save
    run_mod.load_or_compute_posterior_and_save = _compat_load_or_compute_posterior_and_save


def main() -> int:
    _install_checkpoint_compatibility_patch()

    from cellbender.base_cli import main as cellbender_main

    return int(cellbender_main() or 0)


if __name__ == "__main__":
    raise SystemExit(main())
