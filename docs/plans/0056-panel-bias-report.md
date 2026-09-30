# 0056 T3b 面板偏差研究：完整报告

由 `tests/ensemble/test_panel_bias.py::test_full_bias_report` 生成（OmicsClaw 环境，Py3.11，`-m slow`，2026-09-24）。每个配置 N≈5000 个点，候选为合并（K=2…K*−1）、真值（K*）、空间连续再切分（K*+1…2K*）与各 K 的保持簇大小置换（每个 K 3 次）；噪声施加于除置换外的全部候选。argmax 列为集合，分差 ≤1e-9 视为平分。

### grid / stripes / K*=4 / noise=0%

- argmax K, new panel: [8]; old panel: [8]
- spatial_leiden_ami argmax K: [8]; reference Leiden clusters at resolutions 0.1/0.55/1.0: [5, 17, 28]
- CHAOS permutation stderr: median 1.35e-04, relative to |adjusted| median 1.35e-04

| metric | Spearman(raw, K) | Spearman(adjusted, K) | random adjusted mean ± sd |
|---|---|---|---|
| chaos | -0.29 | +0.09 | -0.008 ± 0.028 |
| pas | +0.96 | -0.96 | -0.001 ± 0.007 |
| spatial_leiden_ami | +1.00 | +1.00 | +0.000 ± 0.001 |
| knn_agreement | -1.00 | -1.00 | -0.000 ± 0.005 |
| silhouette_pca | -0.86 | -0.86 | +0.497 ± 0.002 |

| K | kind | new score | old score | chaos adj | pas adj | AMI | silhouette adj |
|---|---|---|---|---|---|---|---|
| 2 | merge | 0.705 | 0.700 | 1.000 | 1.000 | 0.263 | 0.539 |
| 3 | merge | 0.756 | 0.746 | 1.000 | 1.000 | 0.391 | 0.540 |
| 4 | truth | 0.784 | 0.769 | 1.000 | 1.000 | 0.459 | 0.548 |
| 5 | resplit | 0.801 | 0.786 | 1.000 | 1.000 | 0.504 | 0.533 |
| 6 | resplit | 0.821 | 0.804 | 1.000 | 0.999 | 0.554 | 0.519 |
| 7 | resplit | 0.842 | 0.823 | 1.000 | 0.998 | 0.606 | 0.506 |
| 8 | resplit | 0.854 | 0.834 | 1.000 | 0.998 | 0.637 | 0.494 |

### grid / stripes / K*=4 / noise=5%

- argmax K, new panel: [8]; old panel: [8]
- spatial_leiden_ami argmax K: [8]; reference Leiden clusters at resolutions 0.1/0.55/1.0: [5, 17, 28]
- CHAOS permutation stderr: median 1.23e-04, relative to |adjusted| median 2.82e-04

| metric | Spearman(raw, K) | Spearman(adjusted, K) | random adjusted mean ± sd |
|---|---|---|---|
| chaos | +1.00 | +1.00 | -0.008 ± 0.028 |
| pas | +1.00 | +0.96 | -0.001 ± 0.007 |
| spatial_leiden_ami | +1.00 | +1.00 | +0.000 ± 0.001 |
| knn_agreement | -1.00 | +1.00 | -0.000 ± 0.005 |
| silhouette_pca | -0.86 | -0.86 | +0.497 ± 0.002 |

| K | kind | new score | old score | chaos adj | pas adj | AMI | silhouette adj |
|---|---|---|---|---|---|---|---|
| 2 | merge | 0.236 | 0.622 | -0.347 | 0.816 | 0.183 | 0.529 |
| 3 | merge | 0.356 | 0.666 | 0.121 | 0.926 | 0.307 | 0.532 |
| 4 | truth | 0.475 | 0.691 | 0.334 | 0.945 | 0.381 | 0.539 |
| 5 | resplit | 0.534 | 0.707 | 0.437 | 0.946 | 0.425 | 0.527 |
| 6 | resplit | 0.555 | 0.721 | 0.451 | 0.945 | 0.463 | 0.514 |
| 7 | resplit | 0.611 | 0.737 | 0.548 | 0.946 | 0.505 | 0.502 |
| 8 | resplit | 0.639 | 0.749 | 0.586 | 0.946 | 0.539 | 0.491 |

### grid / stripes / K*=4 / noise=15%

- argmax K, new panel: [8]; old panel: [8]
- spatial_leiden_ami argmax K: [8]; reference Leiden clusters at resolutions 0.1/0.55/1.0: [5, 17, 28]
- CHAOS permutation stderr: median 1.31e-04, relative to |adjusted| median 5.11e-04

| metric | Spearman(raw, K) | Spearman(adjusted, K) | random adjusted mean ± sd |
|---|---|---|---|
| chaos | +1.00 | +1.00 | -0.008 ± 0.028 |
| pas | +1.00 | +0.86 | -0.001 ± 0.007 |
| spatial_leiden_ami | +1.00 | +1.00 | +0.000 ± 0.001 |
| knn_agreement | -1.00 | +1.00 | -0.000 ± 0.005 |
| silhouette_pca | -0.86 | -0.86 | +0.497 ± 0.002 |

| K | kind | new score | old score | chaos adj | pas adj | AMI | silhouette adj |
|---|---|---|---|---|---|---|---|
| 2 | merge | 0.139 | 0.502 | -0.732 | 0.510 | 0.093 | 0.517 |
| 3 | merge | 0.235 | 0.535 | -0.203 | 0.777 | 0.198 | 0.518 |
| 4 | truth | 0.308 | 0.556 | 0.094 | 0.825 | 0.263 | 0.523 |
| 5 | resplit | 0.357 | 0.568 | 0.180 | 0.828 | 0.299 | 0.514 |
| 6 | resplit | 0.403 | 0.581 | 0.256 | 0.831 | 0.337 | 0.504 |
| 7 | resplit | 0.433 | 0.594 | 0.294 | 0.830 | 0.374 | 0.495 |
| 8 | resplit | 0.457 | 0.604 | 0.325 | 0.829 | 0.403 | 0.486 |

- tiny-label candidate (2% of observations in 2-member labels): n_labels=54, chaos_skipped_spots=100, adjusted chaos=1.000, pas=0.978, score=0.774

### grid / stripes / K*=7 / noise=0%

- argmax K, new panel: [14]; old panel: [14]
- spatial_leiden_ami argmax K: [14]; reference Leiden clusters at resolutions 0.1/0.55/1.0: [5, 17, 28]
- CHAOS permutation stderr: median 1.32e-04, relative to |adjusted| median 1.32e-04

| metric | Spearman(raw, K) | Spearman(adjusted, K) | random adjusted mean ± sd |
|---|---|---|---|
| chaos | +nan | -0.88 | +0.000 ± 0.029 |
| pas | +0.95 | -0.95 | +0.002 ± 0.009 |
| spatial_leiden_ami | +1.00 | +1.00 | +0.000 ± 0.000 |
| knn_agreement | -1.00 | -1.00 | -0.000 ± 0.004 |
| silhouette_pca | -0.71 | -0.71 | +0.495 ± 0.003 |

| K | kind | new score | old score | chaos adj | pas adj | AMI | silhouette adj |
|---|---|---|---|---|---|---|---|
| 2 | merge | 0.754 | 0.749 | 1.000 | 1.000 | 0.385 | 0.522 |
| 3 | merge | 0.757 | 0.748 | 1.000 | 1.000 | 0.393 | 0.517 |
| 4 | merge | 0.772 | 0.759 | 1.000 | 1.000 | 0.430 | 0.519 |
| 5 | merge | 0.774 | 0.756 | 1.000 | 1.000 | 0.436 | 0.521 |
| 6 | merge | 0.790 | 0.767 | 1.000 | 1.000 | 0.476 | 0.526 |
| 7 | truth | 0.799 | 0.772 | 1.000 | 1.000 | 0.498 | 0.531 |
| 8 | resplit | 0.808 | 0.780 | 1.000 | 0.999 | 0.520 | 0.525 |
| 9 | resplit | 0.816 | 0.787 | 1.000 | 0.999 | 0.541 | 0.519 |
| 10 | resplit | 0.824 | 0.795 | 1.000 | 0.998 | 0.562 | 0.512 |
| 11 | resplit | 0.832 | 0.802 | 1.000 | 0.997 | 0.582 | 0.507 |
| 12 | resplit | 0.839 | 0.809 | 1.000 | 0.996 | 0.600 | 0.500 |
| 13 | resplit | 0.847 | 0.815 | 1.000 | 0.996 | 0.620 | 0.495 |
| 14 | resplit | 0.853 | 0.821 | 1.000 | 0.995 | 0.636 | 0.489 |

### grid / stripes / K*=7 / noise=5%

- argmax K, new panel: [14]; old panel: [14]
- spatial_leiden_ami argmax K: [14]; reference Leiden clusters at resolutions 0.1/0.55/1.0: [5, 17, 28]
- CHAOS permutation stderr: median 1.31e-04, relative to |adjusted| median 2.35e-04

| metric | Spearman(raw, K) | Spearman(adjusted, K) | random adjusted mean ± sd |
|---|---|---|---|
| chaos | +0.99 | +0.99 | +0.000 ± 0.029 |
| pas | +1.00 | +0.37 | +0.002 ± 0.009 |
| spatial_leiden_ami | +1.00 | +1.00 | +0.000 ± 0.000 |
| knn_agreement | -1.00 | +0.19 | -0.000 ± 0.004 |
| silhouette_pca | -0.74 | -0.74 | +0.495 ± 0.003 |

| K | kind | new score | old score | chaos adj | pas adj | AMI | silhouette adj |
|---|---|---|---|---|---|---|---|
| 2 | merge | 0.282 | 0.658 | -1.017 | 0.862 | 0.275 | 0.517 |
| 3 | merge | 0.346 | 0.666 | 0.099 | 0.920 | 0.307 | 0.513 |
| 4 | merge | 0.456 | 0.680 | 0.319 | 0.934 | 0.354 | 0.514 |
| 5 | merge | 0.505 | 0.679 | 0.432 | 0.935 | 0.363 | 0.515 |
| 6 | merge | 0.551 | 0.690 | 0.502 | 0.942 | 0.403 | 0.519 |
| 7 | truth | 0.591 | 0.696 | 0.582 | 0.944 | 0.424 | 0.524 |
| 8 | resplit | 0.606 | 0.703 | 0.597 | 0.943 | 0.446 | 0.519 |
| 9 | resplit | 0.617 | 0.710 | 0.605 | 0.943 | 0.465 | 0.513 |
| 10 | resplit | 0.629 | 0.718 | 0.614 | 0.942 | 0.486 | 0.507 |
| 11 | resplit | 0.644 | 0.725 | 0.634 | 0.941 | 0.507 | 0.502 |
| 12 | resplit | 0.659 | 0.731 | 0.654 | 0.939 | 0.523 | 0.497 |
| 13 | resplit | 0.665 | 0.737 | 0.653 | 0.939 | 0.541 | 0.491 |
| 14 | resplit | 0.683 | 0.743 | 0.679 | 0.939 | 0.559 | 0.486 |

### grid / stripes / K*=7 / noise=15%

- argmax K, new panel: [14]; old panel: [14]
- spatial_leiden_ami argmax K: [14]; reference Leiden clusters at resolutions 0.1/0.55/1.0: [5, 17, 28]
- CHAOS permutation stderr: median 1.20e-04, relative to |adjusted| median 4.07e-04

| metric | Spearman(raw, K) | Spearman(adjusted, K) | random adjusted mean ± sd |
|---|---|---|---|
| chaos | +1.00 | +0.99 | +0.000 ± 0.029 |
| pas | +1.00 | +0.36 | +0.002 ± 0.009 |
| spatial_leiden_ami | +1.00 | +1.00 | +0.000 ± 0.000 |
| knn_agreement | -1.00 | +1.00 | -0.000 ± 0.004 |
| silhouette_pca | -0.82 | -0.82 | +0.495 ± 0.003 |

| K | kind | new score | old score | chaos adj | pas adj | AMI | silhouette adj |
|---|---|---|---|---|---|---|---|
| 2 | merge | 0.179 | 0.526 | -1.255 | 0.589 | 0.152 | 0.510 |
| 3 | merge | 0.235 | 0.537 | -0.198 | 0.768 | 0.202 | 0.507 |
| 4 | merge | 0.288 | 0.548 | 0.072 | 0.808 | 0.243 | 0.507 |
| 5 | merge | 0.346 | 0.548 | 0.204 | 0.814 | 0.255 | 0.507 |
| 6 | merge | 0.384 | 0.558 | 0.254 | 0.826 | 0.292 | 0.509 |
| 7 | truth | 0.409 | 0.563 | 0.294 | 0.828 | 0.313 | 0.511 |
| 8 | resplit | 0.433 | 0.569 | 0.335 | 0.827 | 0.333 | 0.507 |
| 9 | resplit | 0.446 | 0.576 | 0.351 | 0.826 | 0.352 | 0.503 |
| 10 | resplit | 0.464 | 0.581 | 0.381 | 0.825 | 0.367 | 0.499 |
| 11 | resplit | 0.469 | 0.587 | 0.374 | 0.823 | 0.386 | 0.495 |
| 12 | resplit | 0.495 | 0.594 | 0.421 | 0.822 | 0.405 | 0.490 |
| 13 | resplit | 0.507 | 0.600 | 0.434 | 0.821 | 0.422 | 0.486 |
| 14 | resplit | 0.518 | 0.603 | 0.453 | 0.818 | 0.433 | 0.482 |

- tiny-label candidate (2% of observations in 2-member labels): n_labels=57, chaos_skipped_spots=100, adjusted chaos=1.000, pas=0.979, score=0.790

### grid / stripes / K*=10 / noise=0%

- argmax K, new panel: [20]; old panel: [20]
- spatial_leiden_ami argmax K: [20]; reference Leiden clusters at resolutions 0.1/0.55/1.0: [5, 17, 28]
- CHAOS permutation stderr: median 1.55e-04, relative to |adjusted| median 1.55e-04

| metric | Spearman(raw, K) | Spearman(adjusted, K) | random adjusted mean ± sd |
|---|---|---|---|
| chaos | -0.38 | -0.04 | +0.000 ± 0.028 |
| pas | +0.95 | -0.95 | +0.000 ± 0.007 |
| spatial_leiden_ami | +1.00 | +1.00 | +0.000 ± 0.001 |
| knn_agreement | -1.00 | -1.00 | +0.000 ± 0.003 |
| silhouette_pca | -0.69 | -0.69 | +0.493 ± 0.003 |

| K | kind | new score | old score | chaos adj | pas adj | AMI | silhouette adj |
|---|---|---|---|---|---|---|---|
| 2 | merge | 0.750 | 0.746 | 1.000 | 1.000 | 0.375 | 0.516 |
| 3 | merge | 0.765 | 0.758 | 1.000 | 1.000 | 0.412 | 0.513 |
| 4 | merge | 0.779 | 0.768 | 1.000 | 1.000 | 0.448 | 0.511 |
| 5 | merge | 0.779 | 0.762 | 1.000 | 1.000 | 0.449 | 0.509 |
| 6 | merge | 0.783 | 0.761 | 1.000 | 1.000 | 0.458 | 0.509 |
| 7 | merge | 0.787 | 0.761 | 1.000 | 1.000 | 0.467 | 0.512 |
| 8 | merge | 0.794 | 0.764 | 1.000 | 1.000 | 0.486 | 0.514 |
| 9 | merge | 0.798 | 0.763 | 1.000 | 1.000 | 0.495 | 0.518 |
| 10 | truth | 0.796 | 0.756 | 1.000 | 1.000 | 0.490 | 0.522 |
| 11 | resplit | 0.802 | 0.762 | 1.000 | 0.999 | 0.506 | 0.518 |
| 12 | resplit | 0.807 | 0.767 | 1.000 | 0.999 | 0.519 | 0.514 |
| 13 | resplit | 0.813 | 0.772 | 1.000 | 0.998 | 0.533 | 0.510 |
| 14 | resplit | 0.818 | 0.777 | 1.000 | 0.997 | 0.547 | 0.506 |
| 15 | resplit | 0.824 | 0.781 | 1.000 | 0.996 | 0.561 | 0.503 |
| 16 | resplit | 0.828 | 0.785 | 1.000 | 0.996 | 0.573 | 0.499 |
| 17 | resplit | 0.833 | 0.790 | 1.000 | 0.995 | 0.585 | 0.495 |
| 18 | resplit | 0.838 | 0.794 | 1.000 | 0.994 | 0.598 | 0.493 |
| 19 | resplit | 0.843 | 0.798 | 1.000 | 0.993 | 0.610 | 0.489 |
| 20 | resplit | 0.847 | 0.802 | 1.000 | 0.993 | 0.620 | 0.486 |

### grid / stripes / K*=10 / noise=5%

- argmax K, new panel: [20]; old panel: [20]
- spatial_leiden_ami argmax K: [20]; reference Leiden clusters at resolutions 0.1/0.55/1.0: [5, 17, 28]
- CHAOS permutation stderr: median 1.32e-04, relative to |adjusted| median 2.40e-04

| metric | Spearman(raw, K) | Spearman(adjusted, K) | random adjusted mean ± sd |
|---|---|---|---|
| chaos | +1.00 | +0.98 | +0.000 ± 0.028 |
| pas | +1.00 | -0.26 | +0.000 ± 0.007 |
| spatial_leiden_ami | +1.00 | +1.00 | +0.000 ± 0.001 |
| knn_agreement | -1.00 | -0.69 | +0.000 ± 0.003 |
| silhouette_pca | -0.76 | -0.76 | +0.493 ± 0.003 |

| K | kind | new score | old score | chaos adj | pas adj | AMI | silhouette adj |
|---|---|---|---|---|---|---|---|
| 2 | merge | 0.278 | 0.655 | -0.911 | 0.859 | 0.266 | 0.513 |
| 3 | merge | 0.340 | 0.676 | 0.056 | 0.935 | 0.328 | 0.510 |
| 4 | merge | 0.467 | 0.688 | 0.331 | 0.943 | 0.366 | 0.508 |
| 5 | merge | 0.509 | 0.686 | 0.426 | 0.944 | 0.374 | 0.506 |
| 6 | merge | 0.540 | 0.687 | 0.492 | 0.944 | 0.386 | 0.506 |
| 7 | merge | 0.585 | 0.687 | 0.592 | 0.946 | 0.396 | 0.508 |
| 8 | merge | 0.596 | 0.690 | 0.601 | 0.947 | 0.417 | 0.510 |
| 9 | merge | 0.604 | 0.689 | 0.611 | 0.946 | 0.425 | 0.512 |
| 10 | truth | 0.610 | 0.683 | 0.630 | 0.946 | 0.421 | 0.515 |
| 11 | resplit | 0.618 | 0.689 | 0.637 | 0.945 | 0.437 | 0.512 |
| 12 | resplit | 0.641 | 0.694 | 0.678 | 0.944 | 0.452 | 0.509 |
| 13 | resplit | 0.645 | 0.700 | 0.673 | 0.944 | 0.467 | 0.505 |
| 14 | resplit | 0.652 | 0.704 | 0.680 | 0.943 | 0.479 | 0.502 |
| 15 | resplit | 0.658 | 0.708 | 0.685 | 0.942 | 0.491 | 0.499 |
| 16 | resplit | 0.659 | 0.712 | 0.675 | 0.941 | 0.503 | 0.495 |
| 17 | resplit | 0.666 | 0.717 | 0.680 | 0.940 | 0.516 | 0.492 |
| 18 | resplit | 0.675 | 0.720 | 0.689 | 0.939 | 0.528 | 0.489 |
| 19 | resplit | 0.677 | 0.724 | 0.685 | 0.938 | 0.538 | 0.486 |
| 20 | resplit | 0.689 | 0.728 | 0.704 | 0.938 | 0.549 | 0.484 |

### grid / stripes / K*=10 / noise=15%

- argmax K, new panel: [20]; old panel: [20]
- spatial_leiden_ami argmax K: [20]; reference Leiden clusters at resolutions 0.1/0.55/1.0: [5, 17, 28]
- CHAOS permutation stderr: median 1.48e-04, relative to |adjusted| median 3.90e-04

| metric | Spearman(raw, K) | Spearman(adjusted, K) | random adjusted mean ± sd |
|---|---|---|---|
| chaos | +1.00 | +0.98 | +0.000 ± 0.028 |
| pas | +1.00 | -0.40 | +0.000 ± 0.007 |
| spatial_leiden_ami | +1.00 | +1.00 | +0.000 ± 0.001 |
| knn_agreement | -1.00 | +0.90 | +0.000 ± 0.003 |
| silhouette_pca | -0.90 | -0.90 | +0.493 ± 0.003 |

| K | kind | new score | old score | chaos adj | pas adj | AMI | silhouette adj |
|---|---|---|---|---|---|---|---|
| 2 | merge | 0.176 | 0.525 | -1.222 | 0.585 | 0.149 | 0.507 |
| 3 | merge | 0.247 | 0.544 | -0.228 | 0.802 | 0.216 | 0.505 |
| 4 | merge | 0.290 | 0.555 | 0.056 | 0.827 | 0.256 | 0.503 |
| 5 | merge | 0.343 | 0.552 | 0.181 | 0.829 | 0.263 | 0.501 |
| 6 | merge | 0.373 | 0.553 | 0.241 | 0.827 | 0.277 | 0.500 |
| 7 | merge | 0.409 | 0.555 | 0.316 | 0.831 | 0.290 | 0.500 |
| 8 | merge | 0.425 | 0.558 | 0.339 | 0.829 | 0.309 | 0.501 |
| 9 | merge | 0.445 | 0.559 | 0.381 | 0.825 | 0.319 | 0.502 |
| 10 | truth | 0.459 | 0.554 | 0.418 | 0.824 | 0.317 | 0.503 |
| 11 | resplit | 0.461 | 0.558 | 0.411 | 0.822 | 0.331 | 0.501 |
| 12 | resplit | 0.470 | 0.562 | 0.421 | 0.821 | 0.343 | 0.499 |
| 13 | resplit | 0.482 | 0.567 | 0.438 | 0.820 | 0.356 | 0.496 |
| 14 | resplit | 0.485 | 0.570 | 0.439 | 0.819 | 0.365 | 0.494 |
| 15 | resplit | 0.489 | 0.574 | 0.436 | 0.818 | 0.377 | 0.491 |
| 16 | resplit | 0.505 | 0.578 | 0.466 | 0.817 | 0.388 | 0.489 |
| 17 | resplit | 0.515 | 0.582 | 0.477 | 0.815 | 0.402 | 0.486 |
| 18 | resplit | 0.515 | 0.585 | 0.468 | 0.813 | 0.411 | 0.483 |
| 19 | resplit | 0.522 | 0.589 | 0.475 | 0.812 | 0.423 | 0.481 |
| 20 | resplit | 0.523 | 0.592 | 0.472 | 0.810 | 0.432 | 0.479 |

- tiny-label candidate (2% of observations in 2-member labels): n_labels=60, chaos_skipped_spots=100, adjusted chaos=1.000, pas=0.979, score=0.787

### grid / voronoi / K*=4 / noise=0%

- argmax K, new panel: [8]; old panel: [8]
- spatial_leiden_ami argmax K: [8]; reference Leiden clusters at resolutions 0.1/0.55/1.0: [5, 17, 28]
- CHAOS permutation stderr: median 8.83e-05, relative to |adjusted| median 8.83e-05

| metric | Spearman(raw, K) | Spearman(adjusted, K) | random adjusted mean ± sd |
|---|---|---|---|
| chaos | +nan | +nan | -0.000 ± 0.028 |
| pas | +1.00 | -0.89 | -0.001 ± 0.006 |
| spatial_leiden_ami | +0.96 | +0.96 | +0.000 ± 0.001 |
| knn_agreement | -1.00 | -1.00 | -0.001 ± 0.004 |
| silhouette_pca | -0.86 | -0.86 | +0.497 ± 0.002 |

| K | kind | new score | old score | chaos adj | pas adj | AMI | silhouette adj |
|---|---|---|---|---|---|---|---|
| 2 | merge | 0.714 | 0.710 | 1.000 | 0.996 | 0.287 | 0.540 |
| 3 | merge | 0.768 | 0.760 | 1.000 | 0.995 | 0.423 | 0.540 |
| 4 | truth | 0.786 | 0.775 | 1.000 | 0.995 | 0.469 | 0.547 |
| 5 | resplit | 0.816 | 0.802 | 1.000 | 0.995 | 0.543 | 0.527 |
| 6 | resplit | 0.845 | 0.830 | 1.000 | 0.995 | 0.615 | 0.512 |
| 7 | resplit | 0.842 | 0.825 | 1.000 | 0.994 | 0.607 | 0.501 |
| 8 | resplit | 0.850 | 0.832 | 1.000 | 0.994 | 0.627 | 0.501 |

### grid / voronoi / K*=4 / noise=5%

- argmax K, new panel: [8]; old panel: [8]
- spatial_leiden_ami argmax K: [8]; reference Leiden clusters at resolutions 0.1/0.55/1.0: [5, 17, 28]
- CHAOS permutation stderr: median 1.06e-04, relative to |adjusted| median 2.38e-04

| metric | Spearman(raw, K) | Spearman(adjusted, K) | random adjusted mean ± sd |
|---|---|---|---|
| chaos | +1.00 | +1.00 | -0.000 ± 0.028 |
| pas | +0.96 | +0.89 | -0.001 ± 0.006 |
| spatial_leiden_ami | +0.96 | +0.96 | +0.000 ± 0.001 |
| knn_agreement | -1.00 | +0.89 | -0.001 ± 0.004 |
| silhouette_pca | -0.86 | -0.86 | +0.497 ± 0.002 |

| K | kind | new score | old score | chaos adj | pas adj | AMI | silhouette adj |
|---|---|---|---|---|---|---|---|
| 2 | merge | 0.250 | 0.630 | -0.635 | 0.834 | 0.208 | 0.532 |
| 3 | merge | 0.358 | 0.676 | 0.103 | 0.919 | 0.334 | 0.532 |
| 4 | truth | 0.473 | 0.693 | 0.333 | 0.936 | 0.383 | 0.537 |
| 5 | resplit | 0.545 | 0.717 | 0.444 | 0.940 | 0.449 | 0.521 |
| 6 | resplit | 0.587 | 0.743 | 0.480 | 0.942 | 0.518 | 0.507 |
| 7 | resplit | 0.619 | 0.741 | 0.558 | 0.942 | 0.518 | 0.498 |
| 8 | resplit | 0.633 | 0.749 | 0.572 | 0.941 | 0.541 | 0.497 |

### grid / voronoi / K*=4 / noise=15%

- argmax K, new panel: [8]; old panel: [8]
- spatial_leiden_ami argmax K: [8]; reference Leiden clusters at resolutions 0.1/0.55/1.0: [5, 17, 28]
- CHAOS permutation stderr: median 9.13e-05, relative to |adjusted| median 4.67e-04

| metric | Spearman(raw, K) | Spearman(adjusted, K) | random adjusted mean ± sd |
|---|---|---|---|
| chaos | +1.00 | +1.00 | -0.000 ± 0.028 |
| pas | +1.00 | +0.86 | -0.001 ± 0.006 |
| spatial_leiden_ami | +1.00 | +1.00 | +0.000 ± 0.001 |
| knn_agreement | -1.00 | +1.00 | -0.001 ± 0.004 |
| silhouette_pca | -0.89 | -0.89 | +0.497 ± 0.002 |

| K | kind | new score | old score | chaos adj | pas adj | AMI | silhouette adj |
|---|---|---|---|---|---|---|---|
| 2 | merge | 0.150 | 0.506 | -0.951 | 0.545 | 0.104 | 0.519 |
| 3 | merge | 0.239 | 0.540 | -0.225 | 0.772 | 0.212 | 0.519 |
| 4 | truth | 0.304 | 0.559 | 0.083 | 0.818 | 0.267 | 0.522 |
| 5 | resplit | 0.367 | 0.576 | 0.185 | 0.826 | 0.319 | 0.510 |
| 6 | resplit | 0.414 | 0.597 | 0.242 | 0.831 | 0.377 | 0.500 |
| 7 | resplit | 0.429 | 0.600 | 0.269 | 0.829 | 0.388 | 0.492 |
| 8 | resplit | 0.457 | 0.608 | 0.319 | 0.829 | 0.410 | 0.492 |

- tiny-label candidate (2% of observations in 2-member labels): n_labels=54, chaos_skipped_spots=100, adjusted chaos=1.000, pas=0.972, score=0.776

### grid / voronoi / K*=7 / noise=0%

- argmax K, new panel: [14]; old panel: [14]
- spatial_leiden_ami argmax K: [14]; reference Leiden clusters at resolutions 0.1/0.55/1.0: [5, 17, 28]
- CHAOS permutation stderr: median 2.04e-04, relative to |adjusted| median 2.04e-04

| metric | Spearman(raw, K) | Spearman(adjusted, K) | random adjusted mean ± sd |
|---|---|---|---|
| chaos | +0.52 | -0.56 | +0.010 ± 0.027 |
| pas | +1.00 | -0.55 | -0.000 ± 0.006 |
| spatial_leiden_ami | +0.99 | +0.99 | +0.000 ± 0.000 |
| knn_agreement | -1.00 | -1.00 | -0.000 ± 0.003 |
| silhouette_pca | -0.82 | -0.82 | +0.495 ± 0.003 |

| K | kind | new score | old score | chaos adj | pas adj | AMI | silhouette adj |
|---|---|---|---|---|---|---|---|
| 2 | merge | 0.713 | 0.710 | 1.000 | 0.988 | 0.288 | 0.527 |
| 3 | merge | 0.762 | 0.754 | 1.000 | 0.993 | 0.409 | 0.527 |
| 4 | merge | 0.793 | 0.781 | 1.000 | 0.993 | 0.486 | 0.530 |
| 5 | merge | 0.806 | 0.793 | 1.000 | 0.993 | 0.520 | 0.530 |
| 6 | merge | 0.817 | 0.801 | 1.000 | 0.992 | 0.546 | 0.532 |
| 7 | truth | 0.821 | 0.804 | 1.000 | 0.992 | 0.558 | 0.532 |
| 8 | resplit | 0.838 | 0.819 | 1.000 | 0.992 | 0.600 | 0.517 |
| 9 | resplit | 0.845 | 0.824 | 1.000 | 0.992 | 0.616 | 0.516 |
| 10 | resplit | 0.844 | 0.820 | 1.000 | 0.991 | 0.614 | 0.516 |
| 11 | resplit | 0.849 | 0.824 | 1.000 | 0.991 | 0.628 | 0.510 |
| 12 | resplit | 0.855 | 0.828 | 1.000 | 0.991 | 0.641 | 0.504 |
| 13 | resplit | 0.858 | 0.830 | 1.000 | 0.990 | 0.649 | 0.500 |
| 14 | resplit | 0.862 | 0.833 | 1.000 | 0.990 | 0.660 | 0.495 |

### grid / voronoi / K*=7 / noise=5%

- argmax K, new panel: [14]; old panel: [14]
- spatial_leiden_ami argmax K: [14]; reference Leiden clusters at resolutions 0.1/0.55/1.0: [5, 17, 28]
- CHAOS permutation stderr: median 1.65e-04, relative to |adjusted| median 3.09e-04

| metric | Spearman(raw, K) | Spearman(adjusted, K) | random adjusted mean ± sd |
|---|---|---|---|
| chaos | +0.99 | +0.98 | +0.010 ± 0.027 |
| pas | +1.00 | +0.51 | -0.000 ± 0.006 |
| spatial_leiden_ami | +1.00 | +1.00 | +0.000 ± 0.000 |
| knn_agreement | -1.00 | -0.05 | -0.000 ± 0.003 |
| silhouette_pca | -0.81 | -0.81 | +0.495 ± 0.003 |

| K | kind | new score | old score | chaos adj | pas adj | AMI | silhouette adj |
|---|---|---|---|---|---|---|---|
| 2 | merge | 0.239 | 0.626 | -0.330 | 0.802 | 0.196 | 0.521 |
| 3 | merge | 0.362 | 0.669 | 0.134 | 0.910 | 0.315 | 0.521 |
| 4 | merge | 0.486 | 0.699 | 0.348 | 0.934 | 0.399 | 0.523 |
| 5 | merge | 0.524 | 0.711 | 0.408 | 0.934 | 0.434 | 0.523 |
| 6 | merge | 0.557 | 0.720 | 0.463 | 0.934 | 0.462 | 0.525 |
| 7 | truth | 0.588 | 0.723 | 0.529 | 0.933 | 0.474 | 0.525 |
| 8 | resplit | 0.629 | 0.738 | 0.587 | 0.938 | 0.516 | 0.511 |
| 9 | resplit | 0.641 | 0.743 | 0.601 | 0.937 | 0.532 | 0.511 |
| 10 | resplit | 0.647 | 0.742 | 0.613 | 0.936 | 0.536 | 0.511 |
| 11 | resplit | 0.657 | 0.746 | 0.626 | 0.935 | 0.550 | 0.505 |
| 12 | resplit | 0.675 | 0.750 | 0.657 | 0.935 | 0.564 | 0.501 |
| 13 | resplit | 0.678 | 0.753 | 0.655 | 0.934 | 0.574 | 0.496 |
| 14 | resplit | 0.680 | 0.755 | 0.651 | 0.934 | 0.582 | 0.491 |

### grid / voronoi / K*=7 / noise=15%

- argmax K, new panel: [14]; old panel: [14]
- spatial_leiden_ami argmax K: [14]; reference Leiden clusters at resolutions 0.1/0.55/1.0: [5, 17, 28]
- CHAOS permutation stderr: median 1.81e-04, relative to |adjusted| median 5.44e-04

| metric | Spearman(raw, K) | Spearman(adjusted, K) | random adjusted mean ± sd |
|---|---|---|---|
| chaos | +1.00 | +0.99 | +0.010 ± 0.027 |
| pas | +0.99 | +0.51 | -0.000 ± 0.006 |
| spatial_leiden_ami | +1.00 | +1.00 | +0.000 ± 0.000 |
| knn_agreement | -1.00 | +0.86 | -0.000 ± 0.003 |
| silhouette_pca | -0.81 | -0.81 | +0.495 ± 0.003 |

| K | kind | new score | old score | chaos adj | pas adj | AMI | silhouette adj |
|---|---|---|---|---|---|---|---|
| 2 | merge | 0.144 | 0.507 | -0.698 | 0.506 | 0.108 | 0.511 |
| 3 | merge | 0.236 | 0.539 | -0.189 | 0.764 | 0.208 | 0.512 |
| 4 | merge | 0.304 | 0.561 | 0.077 | 0.816 | 0.275 | 0.513 |
| 5 | merge | 0.356 | 0.570 | 0.177 | 0.818 | 0.303 | 0.512 |
| 6 | merge | 0.386 | 0.578 | 0.228 | 0.819 | 0.329 | 0.513 |
| 7 | truth | 0.405 | 0.581 | 0.262 | 0.816 | 0.341 | 0.513 |
| 8 | resplit | 0.444 | 0.596 | 0.313 | 0.825 | 0.383 | 0.501 |
| 9 | resplit | 0.468 | 0.602 | 0.355 | 0.824 | 0.403 | 0.501 |
| 10 | resplit | 0.487 | 0.601 | 0.399 | 0.821 | 0.409 | 0.501 |
| 11 | resplit | 0.492 | 0.607 | 0.393 | 0.821 | 0.426 | 0.496 |
| 12 | resplit | 0.497 | 0.609 | 0.400 | 0.819 | 0.433 | 0.493 |
| 13 | resplit | 0.513 | 0.612 | 0.427 | 0.818 | 0.447 | 0.490 |
| 14 | resplit | 0.528 | 0.615 | 0.456 | 0.817 | 0.456 | 0.486 |

- tiny-label candidate (2% of observations in 2-member labels): n_labels=57, chaos_skipped_spots=100, adjusted chaos=1.000, pas=0.968, score=0.810

### grid / voronoi / K*=10 / noise=0%

- argmax K, new panel: [20]; old panel: [5]
- spatial_leiden_ami argmax K: [20]; reference Leiden clusters at resolutions 0.1/0.55/1.0: [5, 17, 28]
- CHAOS permutation stderr: median 1.68e-04, relative to |adjusted| median 1.68e-04

| metric | Spearman(raw, K) | Spearman(adjusted, K) | random adjusted mean ± sd |
|---|---|---|---|
| chaos | +0.84 | -0.47 | -0.003 ± 0.022 |
| pas | +1.00 | -0.95 | -0.000 ± 0.006 |
| spatial_leiden_ami | +0.90 | +0.90 | +0.000 ± 0.001 |
| knn_agreement | -1.00 | -1.00 | +0.000 ± 0.004 |
| silhouette_pca | -0.77 | -0.77 | +0.493 ± 0.004 |

| K | kind | new score | old score | chaos adj | pas adj | AMI | silhouette adj |
|---|---|---|---|---|---|---|---|
| 2 | merge | 0.732 | 0.728 | 1.000 | 0.990 | 0.336 | 0.516 |
| 3 | merge | 0.792 | 0.784 | 1.000 | 0.994 | 0.482 | 0.513 |
| 4 | merge | 0.845 | 0.835 | 1.000 | 0.995 | 0.615 | 0.515 |
| 5 | merge | 0.866 | 0.853 | 1.000 | 0.994 | 0.667 | 0.517 |
| 6 | merge | 0.856 | 0.841 | 1.000 | 0.994 | 0.643 | 0.516 |
| 7 | merge | 0.852 | 0.835 | 1.000 | 0.993 | 0.632 | 0.517 |
| 8 | merge | 0.858 | 0.840 | 1.000 | 0.992 | 0.649 | 0.518 |
| 9 | merge | 0.853 | 0.833 | 1.000 | 0.991 | 0.638 | 0.520 |
| 10 | truth | 0.852 | 0.830 | 1.000 | 0.990 | 0.635 | 0.522 |
| 11 | resplit | 0.854 | 0.831 | 1.000 | 0.990 | 0.641 | 0.516 |
| 12 | resplit | 0.859 | 0.834 | 1.000 | 0.989 | 0.653 | 0.511 |
| 13 | resplit | 0.863 | 0.836 | 1.000 | 0.989 | 0.662 | 0.505 |
| 14 | resplit | 0.865 | 0.837 | 1.000 | 0.989 | 0.669 | 0.500 |
| 15 | resplit | 0.867 | 0.838 | 1.000 | 0.988 | 0.675 | 0.496 |
| 16 | resplit | 0.868 | 0.837 | 1.000 | 0.988 | 0.676 | 0.496 |
| 17 | resplit | 0.868 | 0.835 | 1.000 | 0.987 | 0.675 | 0.495 |
| 18 | resplit | 0.870 | 0.836 | 1.000 | 0.987 | 0.681 | 0.495 |
| 19 | resplit | 0.871 | 0.837 | 1.000 | 0.986 | 0.684 | 0.494 |
| 20 | resplit | 0.874 | 0.839 | 1.000 | 0.986 | 0.692 | 0.492 |

### grid / voronoi / K*=10 / noise=5%

- argmax K, new panel: [18]; old panel: [20]
- spatial_leiden_ami argmax K: [20]; reference Leiden clusters at resolutions 0.1/0.55/1.0: [5, 17, 28]
- CHAOS permutation stderr: median 1.16e-04, relative to |adjusted| median 2.31e-04

| metric | Spearman(raw, K) | Spearman(adjusted, K) | random adjusted mean ± sd |
|---|---|---|---|
| chaos | +0.99 | +0.98 | -0.003 ± 0.022 |
| pas | +1.00 | -0.40 | -0.000 ± 0.006 |
| spatial_leiden_ami | +0.95 | +0.95 | +0.000 ± 0.001 |
| knn_agreement | -1.00 | -0.40 | +0.000 ± 0.004 |
| silhouette_pca | -0.80 | -0.80 | +0.493 ± 0.004 |

| K | kind | new score | old score | chaos adj | pas adj | AMI | silhouette adj |
|---|---|---|---|---|---|---|---|
| 2 | merge | 0.255 | 0.640 | -0.398 | 0.811 | 0.232 | 0.513 |
| 3 | merge | 0.378 | 0.695 | 0.111 | 0.908 | 0.381 | 0.509 |
| 4 | merge | 0.516 | 0.741 | 0.322 | 0.934 | 0.502 | 0.511 |
| 5 | merge | 0.581 | 0.761 | 0.427 | 0.937 | 0.558 | 0.512 |
| 6 | merge | 0.584 | 0.752 | 0.449 | 0.937 | 0.542 | 0.512 |
| 7 | merge | 0.622 | 0.748 | 0.551 | 0.937 | 0.537 | 0.512 |
| 8 | merge | 0.632 | 0.752 | 0.562 | 0.935 | 0.552 | 0.513 |
| 9 | merge | 0.627 | 0.747 | 0.557 | 0.934 | 0.543 | 0.515 |
| 10 | truth | 0.633 | 0.747 | 0.569 | 0.933 | 0.547 | 0.517 |
| 11 | resplit | 0.641 | 0.748 | 0.581 | 0.932 | 0.555 | 0.511 |
| 12 | resplit | 0.663 | 0.753 | 0.622 | 0.932 | 0.570 | 0.506 |
| 13 | resplit | 0.670 | 0.755 | 0.628 | 0.932 | 0.580 | 0.500 |
| 14 | resplit | 0.678 | 0.757 | 0.641 | 0.932 | 0.588 | 0.495 |
| 15 | resplit | 0.688 | 0.759 | 0.659 | 0.931 | 0.596 | 0.493 |
| 16 | resplit | 0.700 | 0.759 | 0.684 | 0.930 | 0.600 | 0.492 |
| 17 | resplit | 0.693 | 0.757 | 0.670 | 0.929 | 0.598 | 0.491 |
| 18 | resplit | 0.705 | 0.759 | 0.693 | 0.929 | 0.606 | 0.491 |
| 19 | resplit | 0.697 | 0.760 | 0.667 | 0.929 | 0.610 | 0.491 |
| 20 | resplit | 0.703 | 0.762 | 0.675 | 0.928 | 0.618 | 0.488 |

### grid / voronoi / K*=10 / noise=15%

- argmax K, new panel: [20]; old panel: [20]
- spatial_leiden_ami argmax K: [20]; reference Leiden clusters at resolutions 0.1/0.55/1.0: [5, 17, 28]
- CHAOS permutation stderr: median 1.55e-04, relative to |adjusted| median 4.57e-04

| metric | Spearman(raw, K) | Spearman(adjusted, K) | random adjusted mean ± sd |
|---|---|---|---|
| chaos | +1.00 | +0.99 | -0.003 ± 0.022 |
| pas | +1.00 | -0.39 | -0.000 ± 0.006 |
| spatial_leiden_ami | +0.99 | +0.99 | +0.000 ± 0.001 |
| knn_agreement | -1.00 | +0.70 | +0.000 ± 0.004 |
| silhouette_pca | -0.91 | -0.91 | +0.493 ± 0.004 |

| K | kind | new score | old score | chaos adj | pas adj | AMI | silhouette adj |
|---|---|---|---|---|---|---|---|
| 2 | merge | 0.153 | 0.513 | -0.840 | 0.516 | 0.124 | 0.508 |
| 3 | merge | 0.249 | 0.553 | -0.209 | 0.757 | 0.244 | 0.505 |
| 4 | merge | 0.326 | 0.591 | 0.058 | 0.814 | 0.349 | 0.505 |
| 5 | merge | 0.397 | 0.609 | 0.179 | 0.823 | 0.402 | 0.505 |
| 6 | merge | 0.425 | 0.605 | 0.253 | 0.823 | 0.399 | 0.504 |
| 7 | merge | 0.426 | 0.601 | 0.258 | 0.823 | 0.396 | 0.505 |
| 8 | merge | 0.447 | 0.606 | 0.295 | 0.820 | 0.412 | 0.504 |
| 9 | merge | 0.453 | 0.600 | 0.321 | 0.817 | 0.403 | 0.506 |
| 10 | truth | 0.479 | 0.601 | 0.379 | 0.815 | 0.411 | 0.507 |
| 11 | resplit | 0.476 | 0.604 | 0.362 | 0.812 | 0.422 | 0.502 |
| 12 | resplit | 0.493 | 0.609 | 0.389 | 0.811 | 0.438 | 0.497 |
| 13 | resplit | 0.510 | 0.613 | 0.418 | 0.811 | 0.452 | 0.493 |
| 14 | resplit | 0.517 | 0.613 | 0.432 | 0.809 | 0.456 | 0.489 |
| 15 | resplit | 0.513 | 0.614 | 0.416 | 0.809 | 0.462 | 0.487 |
| 16 | resplit | 0.526 | 0.615 | 0.445 | 0.809 | 0.466 | 0.486 |
| 17 | resplit | 0.526 | 0.613 | 0.448 | 0.806 | 0.465 | 0.486 |
| 18 | resplit | 0.536 | 0.615 | 0.466 | 0.804 | 0.473 | 0.486 |
| 19 | resplit | 0.535 | 0.617 | 0.458 | 0.803 | 0.479 | 0.485 |
| 20 | resplit | 0.544 | 0.620 | 0.470 | 0.802 | 0.489 | 0.483 |

- tiny-label candidate (2% of observations in 2-member labels): n_labels=60, chaos_skipped_spots=100, adjusted chaos=1.000, pas=0.968, score=0.839

### poisson / stripes / K*=4 / noise=0%

- argmax K, new panel: [8]; old panel: [8]
- spatial_leiden_ami argmax K: [8]; reference Leiden clusters at resolutions 0.1/0.55/1.0: [8, 26, 36]
- CHAOS permutation stderr: median 1.35e-04, relative to |adjusted| median 1.36e-04

| metric | Spearman(raw, K) | Spearman(adjusted, K) | random adjusted mean ± sd |
|---|---|---|---|
| chaos | +1.00 | +0.18 | +0.005 ± 0.013 |
| pas | +1.00 | -1.00 | +0.003 ± 0.009 |
| spatial_leiden_ami | +1.00 | +1.00 | +0.000 ± 0.001 |
| knn_agreement | -1.00 | -1.00 | +0.002 ± 0.004 |
| silhouette_pca | -0.86 | -0.86 | +0.497 ± 0.002 |

| K | kind | new score | old score | chaos adj | pas adj | AMI | silhouette adj |
|---|---|---|---|---|---|---|---|
| 2 | merge | 0.738 | 0.737 | 0.996 | 0.992 | 0.354 | 0.537 |
| 3 | merge | 0.765 | 0.761 | 0.993 | 0.990 | 0.425 | 0.538 |
| 4 | truth | 0.790 | 0.780 | 0.993 | 0.990 | 0.487 | 0.547 |
| 5 | resplit | 0.805 | 0.794 | 0.993 | 0.989 | 0.525 | 0.534 |
| 6 | resplit | 0.821 | 0.809 | 0.994 | 0.988 | 0.565 | 0.521 |
| 7 | resplit | 0.834 | 0.820 | 0.993 | 0.987 | 0.598 | 0.507 |
| 8 | resplit | 0.849 | 0.834 | 0.994 | 0.986 | 0.636 | 0.494 |

### poisson / stripes / K*=4 / noise=5%

- argmax K, new panel: [8]; old panel: [8]
- spatial_leiden_ami argmax K: [8]; reference Leiden clusters at resolutions 0.1/0.55/1.0: [8, 26, 36]
- CHAOS permutation stderr: median 1.19e-04, relative to |adjusted| median 1.71e-04

| metric | Spearman(raw, K) | Spearman(adjusted, K) | random adjusted mean ± sd |
|---|---|---|---|
| chaos | +1.00 | +1.00 | +0.005 ± 0.013 |
| pas | +1.00 | +0.29 | +0.003 ± 0.009 |
| spatial_leiden_ami | +1.00 | +1.00 | +0.000 ± 0.001 |
| knn_agreement | -1.00 | +1.00 | +0.002 ± 0.004 |
| silhouette_pca | -0.86 | -0.86 | +0.497 ± 0.002 |

| K | kind | new score | old score | chaos adj | pas adj | AMI | silhouette adj |
|---|---|---|---|---|---|---|---|
| 2 | merge | 0.480 | 0.650 | 0.513 | 0.862 | 0.255 | 0.530 |
| 3 | merge | 0.558 | 0.677 | 0.603 | 0.916 | 0.334 | 0.531 |
| 4 | truth | 0.601 | 0.699 | 0.636 | 0.934 | 0.401 | 0.538 |
| 5 | resplit | 0.627 | 0.713 | 0.658 | 0.934 | 0.442 | 0.528 |
| 6 | resplit | 0.647 | 0.727 | 0.673 | 0.933 | 0.479 | 0.515 |
| 7 | resplit | 0.661 | 0.739 | 0.674 | 0.933 | 0.512 | 0.503 |
| 8 | resplit | 0.686 | 0.753 | 0.696 | 0.933 | 0.551 | 0.491 |

### poisson / stripes / K*=4 / noise=15%

- argmax K, new panel: [8]; old panel: [8]
- spatial_leiden_ami argmax K: [8]; reference Leiden clusters at resolutions 0.1/0.55/1.0: [8, 26, 36]
- CHAOS permutation stderr: median 1.06e-04, relative to |adjusted| median 2.50e-04

| metric | Spearman(raw, K) | Spearman(adjusted, K) | random adjusted mean ± sd |
|---|---|---|---|
| chaos | +1.00 | +1.00 | +0.005 ± 0.013 |
| pas | +1.00 | +1.00 | +0.003 ± 0.009 |
| spatial_leiden_ami | +1.00 | +1.00 | +0.000 ± 0.001 |
| knn_agreement | -1.00 | +1.00 | +0.002 ± 0.004 |
| silhouette_pca | -0.89 | -0.89 | +0.497 ± 0.002 |

| K | kind | new score | old score | chaos adj | pas adj | AMI | silhouette adj |
|---|---|---|---|---|---|---|---|
| 2 | merge | 0.282 | 0.522 | 0.264 | 0.599 | 0.141 | 0.519 |
| 3 | merge | 0.386 | 0.543 | 0.358 | 0.775 | 0.218 | 0.518 |
| 4 | truth | 0.446 | 0.563 | 0.423 | 0.822 | 0.281 | 0.523 |
| 5 | resplit | 0.468 | 0.574 | 0.443 | 0.823 | 0.315 | 0.516 |
| 6 | resplit | 0.495 | 0.588 | 0.473 | 0.825 | 0.353 | 0.507 |
| 7 | resplit | 0.508 | 0.598 | 0.475 | 0.825 | 0.383 | 0.496 |
| 8 | resplit | 0.520 | 0.608 | 0.475 | 0.826 | 0.413 | 0.487 |

- tiny-label candidate (2% of observations in 2-member labels): n_labels=54, chaos_skipped_spots=100, adjusted chaos=0.985, pas=0.968, score=0.777

### poisson / stripes / K*=7 / noise=0%

- argmax K, new panel: [14]; old panel: [14]
- spatial_leiden_ami argmax K: [14]; reference Leiden clusters at resolutions 0.1/0.55/1.0: [8, 26, 36]
- CHAOS permutation stderr: median 1.77e-04, relative to |adjusted| median 1.79e-04

| metric | Spearman(raw, K) | Spearman(adjusted, K) | random adjusted mean ± sd |
|---|---|---|---|
| chaos | +1.00 | -0.03 | +0.002 ± 0.013 |
| pas | +1.00 | -1.00 | +0.001 ± 0.009 |
| spatial_leiden_ami | +1.00 | +1.00 | +0.000 ± 0.001 |
| knn_agreement | -1.00 | -0.99 | -0.000 ± 0.003 |
| silhouette_pca | -0.67 | -0.67 | +0.495 ± 0.003 |

| K | kind | new score | old score | chaos adj | pas adj | AMI | silhouette adj |
|---|---|---|---|---|---|---|---|
| 2 | merge | 0.747 | 0.745 | 0.996 | 0.994 | 0.374 | 0.521 |
| 3 | merge | 0.747 | 0.742 | 0.995 | 0.991 | 0.376 | 0.517 |
| 4 | merge | 0.763 | 0.754 | 0.993 | 0.989 | 0.420 | 0.518 |
| 5 | merge | 0.777 | 0.763 | 0.991 | 0.986 | 0.458 | 0.521 |
| 6 | merge | 0.788 | 0.770 | 0.991 | 0.984 | 0.488 | 0.525 |
| 7 | truth | 0.796 | 0.774 | 0.990 | 0.980 | 0.510 | 0.531 |
| 8 | resplit | 0.806 | 0.783 | 0.991 | 0.979 | 0.534 | 0.525 |
| 9 | resplit | 0.815 | 0.791 | 0.991 | 0.979 | 0.556 | 0.519 |
| 10 | resplit | 0.823 | 0.799 | 0.992 | 0.979 | 0.578 | 0.513 |
| 11 | resplit | 0.833 | 0.807 | 0.992 | 0.978 | 0.601 | 0.507 |
| 12 | resplit | 0.839 | 0.813 | 0.992 | 0.977 | 0.617 | 0.502 |
| 13 | resplit | 0.846 | 0.819 | 0.993 | 0.976 | 0.634 | 0.496 |
| 14 | resplit | 0.852 | 0.824 | 0.993 | 0.975 | 0.650 | 0.490 |

### poisson / stripes / K*=7 / noise=5%

- argmax K, new panel: [14]; old panel: [14]
- spatial_leiden_ami argmax K: [14]; reference Leiden clusters at resolutions 0.1/0.55/1.0: [8, 26, 36]
- CHAOS permutation stderr: median 1.72e-04, relative to |adjusted| median 2.50e-04

| metric | Spearman(raw, K) | Spearman(adjusted, K) | random adjusted mean ± sd |
|---|---|---|---|
| chaos | +1.00 | +0.89 | +0.002 ± 0.013 |
| pas | +1.00 | -0.09 | +0.001 ± 0.009 |
| spatial_leiden_ami | +1.00 | +1.00 | +0.000 ± 0.001 |
| knn_agreement | -1.00 | +0.38 | -0.000 ± 0.003 |
| silhouette_pca | -0.68 | -0.68 | +0.495 ± 0.003 |

| K | kind | new score | old score | chaos adj | pas adj | AMI | silhouette adj |
|---|---|---|---|---|---|---|---|
| 2 | merge | 0.482 | 0.656 | 0.507 | 0.859 | 0.270 | 0.517 |
| 3 | merge | 0.527 | 0.658 | 0.583 | 0.900 | 0.286 | 0.512 |
| 4 | merge | 0.565 | 0.672 | 0.614 | 0.925 | 0.336 | 0.513 |
| 5 | merge | 0.596 | 0.684 | 0.643 | 0.931 | 0.381 | 0.516 |
| 6 | merge | 0.623 | 0.692 | 0.682 | 0.929 | 0.411 | 0.518 |
| 7 | truth | 0.632 | 0.697 | 0.682 | 0.927 | 0.436 | 0.523 |
| 8 | resplit | 0.644 | 0.706 | 0.687 | 0.926 | 0.459 | 0.518 |
| 9 | resplit | 0.649 | 0.715 | 0.678 | 0.926 | 0.482 | 0.513 |
| 10 | resplit | 0.667 | 0.723 | 0.701 | 0.926 | 0.504 | 0.508 |
| 11 | resplit | 0.673 | 0.731 | 0.694 | 0.924 | 0.526 | 0.502 |
| 12 | resplit | 0.685 | 0.736 | 0.709 | 0.923 | 0.542 | 0.498 |
| 13 | resplit | 0.685 | 0.743 | 0.690 | 0.923 | 0.560 | 0.493 |
| 14 | resplit | 0.693 | 0.748 | 0.698 | 0.922 | 0.574 | 0.487 |

### poisson / stripes / K*=7 / noise=15%

- argmax K, new panel: [14]; old panel: [14]
- spatial_leiden_ami argmax K: [14]; reference Leiden clusters at resolutions 0.1/0.55/1.0: [8, 26, 36]
- CHAOS permutation stderr: median 1.37e-04, relative to |adjusted| median 2.69e-04

| metric | Spearman(raw, K) | Spearman(adjusted, K) | random adjusted mean ± sd |
|---|---|---|---|
| chaos | +1.00 | +0.99 | +0.002 ± 0.013 |
| pas | +1.00 | +0.10 | +0.001 ± 0.009 |
| spatial_leiden_ami | +1.00 | +1.00 | +0.000 ± 0.001 |
| knn_agreement | -1.00 | +1.00 | -0.000 ± 0.003 |
| silhouette_pca | -0.80 | -0.80 | +0.495 ± 0.003 |

| K | kind | new score | old score | chaos adj | pas adj | AMI | silhouette adj |
|---|---|---|---|---|---|---|---|
| 2 | merge | 0.284 | 0.525 | 0.266 | 0.592 | 0.149 | 0.511 |
| 3 | merge | 0.356 | 0.530 | 0.339 | 0.738 | 0.182 | 0.507 |
| 4 | merge | 0.416 | 0.543 | 0.407 | 0.802 | 0.232 | 0.506 |
| 5 | merge | 0.448 | 0.554 | 0.438 | 0.819 | 0.272 | 0.508 |
| 6 | merge | 0.474 | 0.561 | 0.476 | 0.818 | 0.301 | 0.509 |
| 7 | truth | 0.484 | 0.565 | 0.477 | 0.816 | 0.324 | 0.512 |
| 8 | resplit | 0.498 | 0.574 | 0.489 | 0.816 | 0.347 | 0.508 |
| 9 | resplit | 0.502 | 0.580 | 0.483 | 0.815 | 0.365 | 0.504 |
| 10 | resplit | 0.515 | 0.586 | 0.497 | 0.815 | 0.383 | 0.500 |
| 11 | resplit | 0.528 | 0.595 | 0.508 | 0.814 | 0.406 | 0.496 |
| 12 | resplit | 0.531 | 0.599 | 0.501 | 0.813 | 0.420 | 0.491 |
| 13 | resplit | 0.541 | 0.605 | 0.509 | 0.812 | 0.437 | 0.488 |
| 14 | resplit | 0.556 | 0.611 | 0.530 | 0.811 | 0.454 | 0.483 |

- tiny-label candidate (2% of observations in 2-member labels): n_labels=57, chaos_skipped_spots=100, adjusted chaos=0.986, pas=0.958, score=0.785

### poisson / stripes / K*=10 / noise=0%

- argmax K, new panel: [20]; old panel: [20]
- spatial_leiden_ami argmax K: [20]; reference Leiden clusters at resolutions 0.1/0.55/1.0: [8, 26, 36]
- CHAOS permutation stderr: median 2.07e-04, relative to |adjusted| median 2.09e-04

| metric | Spearman(raw, K) | Spearman(adjusted, K) | random adjusted mean ± sd |
|---|---|---|---|
| chaos | +1.00 | +0.03 | +0.001 ± 0.010 |
| pas | +1.00 | -1.00 | +0.001 ± 0.006 |
| spatial_leiden_ami | +0.99 | +0.99 | +0.000 ± 0.001 |
| knn_agreement | -1.00 | -1.00 | +0.000 ± 0.003 |
| silhouette_pca | -0.60 | -0.60 | +0.493 ± 0.003 |

| K | kind | new score | old score | chaos adj | pas adj | AMI | silhouette adj |
|---|---|---|---|---|---|---|---|
| 2 | merge | 0.738 | 0.737 | 0.996 | 0.992 | 0.354 | 0.514 |
| 3 | merge | 0.759 | 0.754 | 0.994 | 0.989 | 0.409 | 0.510 |
| 4 | merge | 0.786 | 0.777 | 0.993 | 0.990 | 0.477 | 0.510 |
| 5 | merge | 0.788 | 0.776 | 0.990 | 0.986 | 0.487 | 0.510 |
| 6 | merge | 0.786 | 0.769 | 0.990 | 0.983 | 0.483 | 0.510 |
| 7 | merge | 0.784 | 0.764 | 0.989 | 0.981 | 0.481 | 0.511 |
| 8 | merge | 0.794 | 0.770 | 0.989 | 0.979 | 0.508 | 0.515 |
| 9 | merge | 0.790 | 0.761 | 0.989 | 0.975 | 0.500 | 0.518 |
| 10 | truth | 0.792 | 0.758 | 0.988 | 0.972 | 0.507 | 0.522 |
| 11 | resplit | 0.798 | 0.763 | 0.989 | 0.971 | 0.520 | 0.519 |
| 12 | resplit | 0.804 | 0.768 | 0.989 | 0.971 | 0.535 | 0.515 |
| 13 | resplit | 0.810 | 0.773 | 0.990 | 0.970 | 0.549 | 0.511 |
| 14 | resplit | 0.815 | 0.778 | 0.990 | 0.969 | 0.563 | 0.507 |
| 15 | resplit | 0.820 | 0.782 | 0.990 | 0.968 | 0.575 | 0.504 |
| 16 | resplit | 0.825 | 0.788 | 0.991 | 0.968 | 0.589 | 0.500 |
| 17 | resplit | 0.831 | 0.792 | 0.991 | 0.968 | 0.602 | 0.497 |
| 18 | resplit | 0.835 | 0.796 | 0.991 | 0.967 | 0.613 | 0.493 |
| 19 | resplit | 0.839 | 0.800 | 0.991 | 0.966 | 0.623 | 0.490 |
| 20 | resplit | 0.843 | 0.803 | 0.992 | 0.965 | 0.633 | 0.487 |

### poisson / stripes / K*=10 / noise=5%

- argmax K, new panel: [20]; old panel: [20]
- spatial_leiden_ami argmax K: [20]; reference Leiden clusters at resolutions 0.1/0.55/1.0: [8, 26, 36]
- CHAOS permutation stderr: median 1.96e-04, relative to |adjusted| median 2.72e-04

| metric | Spearman(raw, K) | Spearman(adjusted, K) | random adjusted mean ± sd |
|---|---|---|---|
| chaos | +1.00 | +0.93 | +0.001 ± 0.010 |
| pas | +1.00 | -0.60 | +0.001 ± 0.006 |
| spatial_leiden_ami | +1.00 | +1.00 | +0.000 ± 0.001 |
| knn_agreement | -1.00 | -0.63 | +0.000 ± 0.003 |
| silhouette_pca | -0.71 | -0.71 | +0.493 ± 0.003 |

| K | kind | new score | old score | chaos adj | pas adj | AMI | silhouette adj |
|---|---|---|---|---|---|---|---|
| 2 | merge | 0.480 | 0.650 | 0.513 | 0.862 | 0.255 | 0.512 |
| 3 | merge | 0.553 | 0.673 | 0.601 | 0.914 | 0.323 | 0.508 |
| 4 | merge | 0.600 | 0.698 | 0.639 | 0.935 | 0.394 | 0.508 |
| 5 | merge | 0.614 | 0.698 | 0.659 | 0.934 | 0.408 | 0.507 |
| 6 | merge | 0.620 | 0.694 | 0.678 | 0.930 | 0.408 | 0.507 |
| 7 | merge | 0.620 | 0.690 | 0.677 | 0.927 | 0.410 | 0.507 |
| 8 | merge | 0.638 | 0.696 | 0.698 | 0.926 | 0.435 | 0.510 |
| 9 | merge | 0.637 | 0.688 | 0.704 | 0.922 | 0.429 | 0.512 |
| 10 | truth | 0.646 | 0.686 | 0.719 | 0.917 | 0.438 | 0.516 |
| 11 | resplit | 0.647 | 0.692 | 0.707 | 0.916 | 0.453 | 0.513 |
| 12 | resplit | 0.656 | 0.697 | 0.715 | 0.915 | 0.467 | 0.510 |
| 13 | resplit | 0.661 | 0.701 | 0.716 | 0.914 | 0.480 | 0.506 |
| 14 | resplit | 0.661 | 0.706 | 0.704 | 0.913 | 0.493 | 0.503 |
| 15 | resplit | 0.669 | 0.710 | 0.711 | 0.912 | 0.505 | 0.500 |
| 16 | resplit | 0.674 | 0.715 | 0.712 | 0.912 | 0.519 | 0.497 |
| 17 | resplit | 0.686 | 0.721 | 0.724 | 0.912 | 0.534 | 0.493 |
| 18 | resplit | 0.690 | 0.725 | 0.725 | 0.911 | 0.545 | 0.490 |
| 19 | resplit | 0.695 | 0.728 | 0.728 | 0.910 | 0.555 | 0.487 |
| 20 | resplit | 0.698 | 0.730 | 0.727 | 0.909 | 0.563 | 0.484 |

### poisson / stripes / K*=10 / noise=15%

- argmax K, new panel: [20]; old panel: [20]
- spatial_leiden_ami argmax K: [20]; reference Leiden clusters at resolutions 0.1/0.55/1.0: [8, 26, 36]
- CHAOS permutation stderr: median 1.64e-04, relative to |adjusted| median 3.13e-04

| metric | Spearman(raw, K) | Spearman(adjusted, K) | random adjusted mean ± sd |
|---|---|---|---|
| chaos | +1.00 | +0.96 | +0.001 ± 0.010 |
| pas | +1.00 | -0.43 | +0.001 ± 0.006 |
| spatial_leiden_ami | +1.00 | +1.00 | +0.000 ± 0.001 |
| knn_agreement | -1.00 | +0.69 | +0.000 ± 0.003 |
| silhouette_pca | -0.89 | -0.89 | +0.493 ± 0.003 |

| K | kind | new score | old score | chaos adj | pas adj | AMI | silhouette adj |
|---|---|---|---|---|---|---|---|
| 2 | merge | 0.282 | 0.522 | 0.264 | 0.599 | 0.141 | 0.508 |
| 3 | merge | 0.379 | 0.542 | 0.350 | 0.770 | 0.212 | 0.504 |
| 4 | merge | 0.445 | 0.563 | 0.423 | 0.822 | 0.277 | 0.503 |
| 5 | merge | 0.461 | 0.565 | 0.445 | 0.823 | 0.295 | 0.502 |
| 6 | merge | 0.471 | 0.562 | 0.469 | 0.820 | 0.299 | 0.501 |
| 7 | merge | 0.474 | 0.558 | 0.476 | 0.816 | 0.300 | 0.500 |
| 8 | merge | 0.490 | 0.563 | 0.493 | 0.813 | 0.324 | 0.501 |
| 9 | merge | 0.485 | 0.556 | 0.490 | 0.807 | 0.320 | 0.502 |
| 10 | truth | 0.493 | 0.554 | 0.505 | 0.800 | 0.328 | 0.504 |
| 11 | resplit | 0.504 | 0.558 | 0.518 | 0.798 | 0.342 | 0.502 |
| 12 | resplit | 0.505 | 0.563 | 0.510 | 0.797 | 0.356 | 0.500 |
| 13 | resplit | 0.509 | 0.567 | 0.506 | 0.795 | 0.369 | 0.497 |
| 14 | resplit | 0.520 | 0.571 | 0.523 | 0.794 | 0.379 | 0.495 |
| 15 | resplit | 0.524 | 0.575 | 0.521 | 0.792 | 0.392 | 0.492 |
| 16 | resplit | 0.527 | 0.580 | 0.515 | 0.792 | 0.406 | 0.489 |
| 17 | resplit | 0.543 | 0.586 | 0.540 | 0.792 | 0.420 | 0.487 |
| 18 | resplit | 0.538 | 0.588 | 0.522 | 0.791 | 0.428 | 0.484 |
| 19 | resplit | 0.547 | 0.591 | 0.535 | 0.789 | 0.439 | 0.482 |
| 20 | resplit | 0.553 | 0.595 | 0.540 | 0.787 | 0.450 | 0.479 |

- tiny-label candidate (2% of observations in 2-member labels): n_labels=60, chaos_skipped_spots=100, adjusted chaos=0.984, pas=0.949, score=0.781

### poisson / voronoi / K*=4 / noise=0%

- argmax K, new panel: [8]; old panel: [8]
- spatial_leiden_ami argmax K: [8]; reference Leiden clusters at resolutions 0.1/0.55/1.0: [8, 26, 36]
- CHAOS permutation stderr: median 1.15e-04, relative to |adjusted| median 1.16e-04

| metric | Spearman(raw, K) | Spearman(adjusted, K) | random adjusted mean ± sd |
|---|---|---|---|
| chaos | +1.00 | +0.75 | +0.001 ± 0.013 |
| pas | +1.00 | -0.89 | +0.001 ± 0.010 |
| spatial_leiden_ami | +1.00 | +1.00 | +0.000 ± 0.001 |
| knn_agreement | -1.00 | -1.00 | +0.000 ± 0.005 |
| silhouette_pca | -0.89 | -0.89 | +0.497 ± 0.002 |

| K | kind | new score | old score | chaos adj | pas adj | AMI | silhouette adj |
|---|---|---|---|---|---|---|---|
| 2 | merge | 0.706 | 0.706 | 0.992 | 0.992 | 0.276 | 0.544 |
| 3 | merge | 0.756 | 0.753 | 0.992 | 0.994 | 0.401 | 0.543 |
| 4 | truth | 0.786 | 0.779 | 0.994 | 0.993 | 0.475 | 0.548 |
| 5 | resplit | 0.803 | 0.793 | 0.993 | 0.991 | 0.519 | 0.530 |
| 6 | resplit | 0.821 | 0.810 | 0.993 | 0.991 | 0.564 | 0.512 |
| 7 | resplit | 0.832 | 0.819 | 0.993 | 0.988 | 0.594 | 0.502 |
| 8 | resplit | 0.841 | 0.827 | 0.994 | 0.988 | 0.614 | 0.501 |

### poisson / voronoi / K*=4 / noise=5%

- argmax K, new panel: [8]; old panel: [8]
- spatial_leiden_ami argmax K: [8]; reference Leiden clusters at resolutions 0.1/0.55/1.0: [8, 26, 36]
- CHAOS permutation stderr: median 9.98e-05, relative to |adjusted| median 1.52e-04

| metric | Spearman(raw, K) | Spearman(adjusted, K) | random adjusted mean ± sd |
|---|---|---|---|
| chaos | +1.00 | +0.89 | +0.001 ± 0.013 |
| pas | +1.00 | +0.43 | +0.001 ± 0.010 |
| spatial_leiden_ami | +1.00 | +1.00 | +0.000 ± 0.001 |
| knn_agreement | -1.00 | +0.86 | +0.000 ± 0.005 |
| silhouette_pca | -0.89 | -0.89 | +0.497 ± 0.002 |

| K | kind | new score | old score | chaos adj | pas adj | AMI | silhouette adj |
|---|---|---|---|---|---|---|---|
| 2 | merge | 0.442 | 0.628 | 0.485 | 0.843 | 0.198 | 0.535 |
| 3 | merge | 0.547 | 0.671 | 0.593 | 0.919 | 0.316 | 0.535 |
| 4 | truth | 0.596 | 0.696 | 0.636 | 0.934 | 0.387 | 0.539 |
| 5 | resplit | 0.624 | 0.712 | 0.657 | 0.934 | 0.435 | 0.523 |
| 6 | resplit | 0.658 | 0.729 | 0.695 | 0.937 | 0.480 | 0.508 |
| 7 | resplit | 0.658 | 0.737 | 0.672 | 0.934 | 0.507 | 0.498 |
| 8 | resplit | 0.673 | 0.745 | 0.686 | 0.933 | 0.529 | 0.498 |

### poisson / voronoi / K*=4 / noise=15%

- argmax K, new panel: [8]; old panel: [8]
- spatial_leiden_ami argmax K: [8]; reference Leiden clusters at resolutions 0.1/0.55/1.0: [8, 26, 36]
- CHAOS permutation stderr: median 8.65e-05, relative to |adjusted| median 2.13e-04

| metric | Spearman(raw, K) | Spearman(adjusted, K) | random adjusted mean ± sd |
|---|---|---|---|
| chaos | +1.00 | +0.89 | +0.001 ± 0.013 |
| pas | +1.00 | +0.86 | +0.001 ± 0.010 |
| spatial_leiden_ami | +1.00 | +1.00 | +0.000 ± 0.001 |
| knn_agreement | -1.00 | +1.00 | +0.000 ± 0.005 |
| silhouette_pca | -0.86 | -0.86 | +0.497 ± 0.002 |

| K | kind | new score | old score | chaos adj | pas adj | AMI | silhouette adj |
|---|---|---|---|---|---|---|---|
| 2 | merge | 0.253 | 0.505 | 0.251 | 0.559 | 0.101 | 0.520 |
| 3 | merge | 0.378 | 0.538 | 0.354 | 0.779 | 0.201 | 0.520 |
| 4 | truth | 0.436 | 0.562 | 0.408 | 0.819 | 0.273 | 0.523 |
| 5 | resplit | 0.468 | 0.574 | 0.444 | 0.825 | 0.312 | 0.511 |
| 6 | resplit | 0.498 | 0.588 | 0.478 | 0.831 | 0.351 | 0.499 |
| 7 | resplit | 0.507 | 0.598 | 0.471 | 0.829 | 0.382 | 0.492 |
| 8 | resplit | 0.514 | 0.605 | 0.471 | 0.828 | 0.401 | 0.491 |

- tiny-label candidate (2% of observations in 2-member labels): n_labels=54, chaos_skipped_spots=100, adjusted chaos=0.986, pas=0.970, score=0.770

### poisson / voronoi / K*=7 / noise=0%

- argmax K, new panel: [14]; old panel: [14]
- spatial_leiden_ami argmax K: [14]; reference Leiden clusters at resolutions 0.1/0.55/1.0: [8, 26, 36]
- CHAOS permutation stderr: median 1.88e-04, relative to |adjusted| median 1.89e-04

| metric | Spearman(raw, K) | Spearman(adjusted, K) | random adjusted mean ± sd |
|---|---|---|---|
| chaos | +1.00 | +0.38 | +0.000 ± 0.012 |
| pas | +1.00 | -0.98 | -0.002 ± 0.007 |
| spatial_leiden_ami | +0.98 | +0.98 | +0.001 ± 0.001 |
| knn_agreement | -1.00 | -1.00 | -0.000 ± 0.002 |
| silhouette_pca | -0.90 | -0.90 | +0.495 ± 0.003 |

| K | kind | new score | old score | chaos adj | pas adj | AMI | silhouette adj |
|---|---|---|---|---|---|---|---|
| 2 | merge | 0.735 | 0.734 | 0.994 | 0.990 | 0.349 | 0.532 |
| 3 | merge | 0.776 | 0.773 | 0.994 | 0.991 | 0.451 | 0.525 |
| 4 | merge | 0.795 | 0.789 | 0.994 | 0.991 | 0.497 | 0.523 |
| 5 | merge | 0.819 | 0.811 | 0.995 | 0.990 | 0.559 | 0.529 |
| 6 | merge | 0.817 | 0.806 | 0.995 | 0.988 | 0.553 | 0.531 |
| 7 | truth | 0.817 | 0.805 | 0.995 | 0.986 | 0.556 | 0.531 |
| 8 | resplit | 0.838 | 0.824 | 0.995 | 0.986 | 0.607 | 0.516 |
| 9 | resplit | 0.841 | 0.825 | 0.995 | 0.985 | 0.615 | 0.515 |
| 10 | resplit | 0.845 | 0.827 | 0.995 | 0.984 | 0.625 | 0.514 |
| 11 | resplit | 0.847 | 0.828 | 0.995 | 0.983 | 0.633 | 0.510 |
| 12 | resplit | 0.851 | 0.830 | 0.995 | 0.981 | 0.643 | 0.504 |
| 13 | resplit | 0.856 | 0.834 | 0.995 | 0.980 | 0.656 | 0.499 |
| 14 | resplit | 0.859 | 0.836 | 0.994 | 0.979 | 0.664 | 0.495 |

### poisson / voronoi / K*=7 / noise=5%

- argmax K, new panel: [14]; old panel: [14]
- spatial_leiden_ami argmax K: [14]; reference Leiden clusters at resolutions 0.1/0.55/1.0: [8, 26, 36]
- CHAOS permutation stderr: median 2.06e-04, relative to |adjusted| median 2.96e-04

| metric | Spearman(raw, K) | Spearman(adjusted, K) | random adjusted mean ± sd |
|---|---|---|---|
| chaos | +0.99 | +0.90 | +0.000 ± 0.012 |
| pas | +1.00 | +0.25 | -0.002 ± 0.007 |
| spatial_leiden_ami | +1.00 | +1.00 | +0.001 ± 0.001 |
| knn_agreement | -1.00 | +0.25 | -0.000 ± 0.002 |
| silhouette_pca | -0.90 | -0.90 | +0.495 ± 0.003 |

| K | kind | new score | old score | chaos adj | pas adj | AMI | silhouette adj |
|---|---|---|---|---|---|---|---|
| 2 | merge | 0.480 | 0.651 | 0.514 | 0.857 | 0.259 | 0.526 |
| 3 | merge | 0.560 | 0.687 | 0.587 | 0.911 | 0.356 | 0.520 |
| 4 | merge | 0.587 | 0.703 | 0.606 | 0.921 | 0.400 | 0.518 |
| 5 | merge | 0.631 | 0.723 | 0.653 | 0.933 | 0.459 | 0.523 |
| 6 | merge | 0.640 | 0.722 | 0.673 | 0.931 | 0.461 | 0.524 |
| 7 | truth | 0.640 | 0.724 | 0.665 | 0.931 | 0.471 | 0.524 |
| 8 | resplit | 0.670 | 0.742 | 0.687 | 0.935 | 0.521 | 0.509 |
| 9 | resplit | 0.674 | 0.746 | 0.684 | 0.935 | 0.534 | 0.509 |
| 10 | resplit | 0.691 | 0.749 | 0.715 | 0.933 | 0.547 | 0.509 |
| 11 | resplit | 0.697 | 0.750 | 0.721 | 0.930 | 0.555 | 0.505 |
| 12 | resplit | 0.700 | 0.754 | 0.716 | 0.929 | 0.568 | 0.500 |
| 13 | resplit | 0.702 | 0.758 | 0.708 | 0.927 | 0.583 | 0.496 |
| 14 | resplit | 0.707 | 0.759 | 0.714 | 0.925 | 0.591 | 0.491 |

### poisson / voronoi / K*=7 / noise=15%

- argmax K, new panel: [14]; old panel: [14]
- spatial_leiden_ami argmax K: [14]; reference Leiden clusters at resolutions 0.1/0.55/1.0: [8, 26, 36]
- CHAOS permutation stderr: median 1.87e-04, relative to |adjusted| median 3.88e-04

| metric | Spearman(raw, K) | Spearman(adjusted, K) | random adjusted mean ± sd |
|---|---|---|---|
| chaos | +1.00 | +0.99 | +0.000 ± 0.012 |
| pas | +1.00 | +0.19 | -0.002 ± 0.007 |
| spatial_leiden_ami | +1.00 | +1.00 | +0.001 ± 0.001 |
| knn_agreement | -1.00 | +0.98 | -0.000 ± 0.002 |
| silhouette_pca | -0.90 | -0.90 | +0.495 ± 0.003 |

| K | kind | new score | old score | chaos adj | pas adj | AMI | silhouette adj |
|---|---|---|---|---|---|---|---|
| 2 | merge | 0.281 | 0.523 | 0.262 | 0.594 | 0.145 | 0.516 |
| 3 | merge | 0.383 | 0.551 | 0.344 | 0.762 | 0.233 | 0.512 |
| 4 | merge | 0.427 | 0.565 | 0.395 | 0.792 | 0.277 | 0.510 |
| 5 | merge | 0.473 | 0.585 | 0.437 | 0.820 | 0.335 | 0.512 |
| 6 | merge | 0.483 | 0.583 | 0.461 | 0.819 | 0.336 | 0.513 |
| 7 | truth | 0.483 | 0.586 | 0.447 | 0.816 | 0.351 | 0.512 |
| 8 | resplit | 0.512 | 0.602 | 0.473 | 0.824 | 0.396 | 0.501 |
| 9 | resplit | 0.519 | 0.604 | 0.481 | 0.820 | 0.407 | 0.501 |
| 10 | resplit | 0.527 | 0.607 | 0.488 | 0.818 | 0.420 | 0.501 |
| 11 | resplit | 0.534 | 0.610 | 0.498 | 0.816 | 0.430 | 0.497 |
| 12 | resplit | 0.537 | 0.613 | 0.494 | 0.816 | 0.442 | 0.493 |
| 13 | resplit | 0.544 | 0.617 | 0.499 | 0.813 | 0.454 | 0.489 |
| 14 | resplit | 0.552 | 0.619 | 0.513 | 0.811 | 0.462 | 0.486 |

- tiny-label candidate (2% of observations in 2-member labels): n_labels=57, chaos_skipped_spots=100, adjusted chaos=0.989, pas=0.963, score=0.804

### poisson / voronoi / K*=10 / noise=0%

- argmax K, new panel: [15]; old panel: [15]
- spatial_leiden_ami argmax K: [20]; reference Leiden clusters at resolutions 0.1/0.55/1.0: [8, 26, 36]
- CHAOS permutation stderr: median 2.26e-04, relative to |adjusted| median 2.27e-04

| metric | Spearman(raw, K) | Spearman(adjusted, K) | random adjusted mean ± sd |
|---|---|---|---|
| chaos | +1.00 | -0.82 | -0.001 ± 0.014 |
| pas | +1.00 | -0.96 | +0.001 ± 0.006 |
| spatial_leiden_ami | +0.97 | +0.97 | +0.001 ± 0.001 |
| knn_agreement | -1.00 | -1.00 | +0.000 ± 0.003 |
| silhouette_pca | -0.81 | -0.81 | +0.493 ± 0.004 |

| K | kind | new score | old score | chaos adj | pas adj | AMI | silhouette adj |
|---|---|---|---|---|---|---|---|
| 2 | merge | 0.730 | 0.729 | 0.993 | 0.985 | 0.338 | 0.518 |
| 3 | merge | 0.795 | 0.790 | 0.996 | 0.990 | 0.497 | 0.516 |
| 4 | merge | 0.803 | 0.795 | 0.996 | 0.991 | 0.516 | 0.516 |
| 5 | merge | 0.815 | 0.805 | 0.995 | 0.989 | 0.548 | 0.516 |
| 6 | merge | 0.828 | 0.817 | 0.995 | 0.987 | 0.582 | 0.517 |
| 7 | merge | 0.831 | 0.818 | 0.995 | 0.987 | 0.591 | 0.518 |
| 8 | merge | 0.839 | 0.824 | 0.994 | 0.986 | 0.610 | 0.519 |
| 9 | merge | 0.840 | 0.825 | 0.994 | 0.984 | 0.615 | 0.519 |
| 10 | truth | 0.848 | 0.832 | 0.993 | 0.982 | 0.636 | 0.521 |
| 11 | resplit | 0.857 | 0.839 | 0.993 | 0.981 | 0.659 | 0.515 |
| 12 | resplit | 0.864 | 0.845 | 0.993 | 0.980 | 0.677 | 0.510 |
| 13 | resplit | 0.866 | 0.845 | 0.993 | 0.979 | 0.683 | 0.505 |
| 14 | resplit | 0.869 | 0.846 | 0.993 | 0.977 | 0.691 | 0.500 |
| 15 | resplit | 0.871 | 0.847 | 0.993 | 0.976 | 0.697 | 0.497 |
| 16 | resplit | 0.870 | 0.844 | 0.993 | 0.974 | 0.694 | 0.496 |
| 17 | resplit | 0.868 | 0.841 | 0.993 | 0.973 | 0.691 | 0.496 |
| 18 | resplit | 0.868 | 0.839 | 0.993 | 0.972 | 0.691 | 0.495 |
| 19 | resplit | 0.871 | 0.841 | 0.993 | 0.971 | 0.698 | 0.495 |
| 20 | resplit | 0.871 | 0.841 | 0.993 | 0.969 | 0.701 | 0.494 |

### poisson / voronoi / K*=10 / noise=5%

- argmax K, new panel: [19]; old panel: [15]
- spatial_leiden_ami argmax K: [20]; reference Leiden clusters at resolutions 0.1/0.55/1.0: [8, 26, 36]
- CHAOS permutation stderr: median 1.65e-04, relative to |adjusted| median 2.39e-04

| metric | Spearman(raw, K) | Spearman(adjusted, K) | random adjusted mean ± sd |
|---|---|---|---|
| chaos | +1.00 | +0.92 | -0.001 ± 0.014 |
| pas | +1.00 | -0.58 | +0.001 ± 0.006 |
| spatial_leiden_ami | +0.98 | +0.98 | +0.001 ± 0.001 |
| knn_agreement | -1.00 | -0.52 | +0.000 ± 0.003 |
| silhouette_pca | -0.85 | -0.85 | +0.493 ± 0.004 |

| K | kind | new score | old score | chaos adj | pas adj | AMI | silhouette adj |
|---|---|---|---|---|---|---|---|
| 2 | merge | 0.469 | 0.643 | 0.507 | 0.849 | 0.241 | 0.514 |
| 3 | merge | 0.581 | 0.699 | 0.603 | 0.922 | 0.389 | 0.512 |
| 4 | merge | 0.610 | 0.710 | 0.638 | 0.934 | 0.421 | 0.511 |
| 5 | merge | 0.630 | 0.720 | 0.654 | 0.935 | 0.453 | 0.511 |
| 6 | merge | 0.660 | 0.733 | 0.691 | 0.932 | 0.492 | 0.512 |
| 7 | merge | 0.661 | 0.738 | 0.679 | 0.934 | 0.507 | 0.513 |
| 8 | merge | 0.674 | 0.744 | 0.693 | 0.933 | 0.526 | 0.514 |
| 9 | merge | 0.673 | 0.745 | 0.684 | 0.932 | 0.533 | 0.514 |
| 10 | truth | 0.687 | 0.752 | 0.698 | 0.930 | 0.554 | 0.515 |
| 11 | resplit | 0.692 | 0.759 | 0.691 | 0.928 | 0.575 | 0.510 |
| 12 | resplit | 0.705 | 0.765 | 0.704 | 0.927 | 0.595 | 0.505 |
| 13 | resplit | 0.706 | 0.766 | 0.701 | 0.926 | 0.602 | 0.501 |
| 14 | resplit | 0.710 | 0.768 | 0.702 | 0.923 | 0.611 | 0.496 |
| 15 | resplit | 0.718 | 0.770 | 0.711 | 0.922 | 0.622 | 0.493 |
| 16 | resplit | 0.717 | 0.767 | 0.714 | 0.920 | 0.618 | 0.493 |
| 17 | resplit | 0.715 | 0.764 | 0.715 | 0.919 | 0.614 | 0.492 |
| 18 | resplit | 0.714 | 0.763 | 0.710 | 0.917 | 0.616 | 0.492 |
| 19 | resplit | 0.720 | 0.765 | 0.718 | 0.917 | 0.623 | 0.491 |
| 20 | resplit | 0.715 | 0.765 | 0.703 | 0.915 | 0.627 | 0.491 |

### poisson / voronoi / K*=10 / noise=15%

- argmax K, new panel: [20]; old panel: [20]
- spatial_leiden_ami argmax K: [20]; reference Leiden clusters at resolutions 0.1/0.55/1.0: [8, 26, 36]
- CHAOS permutation stderr: median 1.84e-04, relative to |adjusted| median 3.78e-04

| metric | Spearman(raw, K) | Spearman(adjusted, K) | random adjusted mean ± sd |
|---|---|---|---|
| chaos | +1.00 | +0.96 | -0.001 ± 0.014 |
| pas | +1.00 | -0.38 | +0.001 ± 0.006 |
| spatial_leiden_ami | +1.00 | +1.00 | +0.001 ± 0.001 |
| knn_agreement | -1.00 | +0.58 | +0.000 ± 0.003 |
| silhouette_pca | -0.96 | -0.96 | +0.493 ± 0.004 |

| K | kind | new score | old score | chaos adj | pas adj | AMI | silhouette adj |
|---|---|---|---|---|---|---|---|
| 2 | merge | 0.277 | 0.518 | 0.263 | 0.584 | 0.136 | 0.510 |
| 3 | merge | 0.406 | 0.559 | 0.362 | 0.788 | 0.258 | 0.507 |
| 4 | merge | 0.448 | 0.572 | 0.412 | 0.819 | 0.298 | 0.506 |
| 5 | merge | 0.473 | 0.581 | 0.442 | 0.823 | 0.329 | 0.505 |
| 6 | merge | 0.498 | 0.592 | 0.471 | 0.825 | 0.362 | 0.505 |
| 7 | merge | 0.502 | 0.594 | 0.469 | 0.824 | 0.374 | 0.506 |
| 8 | merge | 0.508 | 0.600 | 0.464 | 0.823 | 0.395 | 0.505 |
| 9 | merge | 0.515 | 0.602 | 0.475 | 0.821 | 0.402 | 0.504 |
| 10 | truth | 0.526 | 0.608 | 0.484 | 0.820 | 0.420 | 0.506 |
| 11 | resplit | 0.541 | 0.616 | 0.499 | 0.819 | 0.443 | 0.501 |
| 12 | resplit | 0.549 | 0.621 | 0.504 | 0.815 | 0.461 | 0.497 |
| 13 | resplit | 0.554 | 0.622 | 0.511 | 0.813 | 0.467 | 0.493 |
| 14 | resplit | 0.565 | 0.624 | 0.530 | 0.811 | 0.477 | 0.489 |
| 15 | resplit | 0.561 | 0.624 | 0.517 | 0.808 | 0.482 | 0.487 |
| 16 | resplit | 0.562 | 0.623 | 0.520 | 0.806 | 0.481 | 0.486 |
| 17 | resplit | 0.568 | 0.623 | 0.534 | 0.803 | 0.485 | 0.486 |
| 18 | resplit | 0.560 | 0.620 | 0.517 | 0.800 | 0.484 | 0.485 |
| 19 | resplit | 0.569 | 0.623 | 0.529 | 0.799 | 0.493 | 0.485 |
| 20 | resplit | 0.576 | 0.625 | 0.542 | 0.798 | 0.500 | 0.485 |

- tiny-label candidate (2% of observations in 2-member labels): n_labels=60, chaos_skipped_spots=100, adjusted chaos=0.990, pas=0.962, score=0.836

## 扩大候选 K 的复查（2026-09-25）

owner 批准的 E1。目的：去掉原研究"候选 K 只到 2K*"的边界效应，确认面板的偏好是停在某个 K 还是持续上升，并在研究脚本里评估几种修正，为 0057 前裁定面板权重与校正公式提供证据。**生产代码未改动**（`omicsclaw/` 下无任何修改），面板仍是 `spatial_domains/2`。

### 方法

- 脚本：`docs/plans/0056-panel-bias-study/study.py`（`compute` 生成全部候选的指标原料，`analyse` 重组各方案并出表）。只 import `omicsclaw.ensemble.metrics.spatial` 的 `compute_panel` 等函数；合成数据生成（网格/Poisson 布局、条带/Voronoi 区域、合并、再切分、噪声）逐字取自 `tests/ensemble/test_panel_bias.py`。复现：
  `PYTHONPATH=<repo> /opt/conda/envs/OmicsClaw/bin/python study.py compute --out rows.json` 后 `… analyse --rows rows.json --k-main 40`（OmicsClaw 环境，Py3.11；rapids 环境缺 igraph。100 进程约 2.5 分钟）。
- 配置与原研究相同：{网格, Poisson} × {条带, Voronoi} × K*∈{4,7,10} × 噪声 {0, 5%, 15%}，共 36 个，N≈5000。噪声以同一种子施加到**每个**候选上。
- 候选 K：合并 2…K*−1、真值 K*、空间连续再切分 K*+1…K_max。K_max = max(参照 Leiden 最大簇数, 3K*, 40) = **40**（主表）；为回答"是否停下"另把候选扩到 **60**（表 B、C）。本次参照 Leiden 在分辨率 0.1/0.55/1.0 下的簇数：网格 **5/19/27**，Poisson **8/26/36**（原报告网格为 5/17/28；`sc.pp.neighbors` 在 N=5000 时走近似近邻，本次以单线程 BLAS 运行，差异来自这里，不影响结论）。
- 每个候选记录 CHAOS 的 raw/E_rand/d_min、PAS 的 raw/E、`spatial_leiden_ami`、`knn_agreement` 校正值，以及 silhouette。silhouette 在三种表达信号强度下各算一次：原研究的 2.0，以及 1.0、4.0（表达 = N(0,1) 的 10 维噪声 + 信号 × 区域独热，与原研究同式）；主表用 2.0。
- 偏差度量：面板 argmax K − K*；argmax 平分（差 ≤1e-9）时取**离 K* 最远**的那个（保守）。每格写成"偏差中位数 / |偏差|中位数 / 落在 K*±1 的比例 / 恰为 K* 的比例"。
- 训练/留出：两种划分——按形状（训练条带 18 个，留出 Voronoi 18 个）与按 K*（训练 K*∈{4,10} 24 个，留出 K*=7 12 个）。唯一在数据上选的参数是 silhouette 权重 w∈{0.2, 0.33, 0.5, 0.67}，在训练集上选（K*±1 比例最高，平手取 |偏差| 更小、再平手取更小的 w），只报告留出集。其余权重比例都按原理事先固定，不调。

### 结果一：偏好随 K 单调上升，不停在参照 Leiden 簇数处

各配置下各成员与现状面板的 argmax K（K≤40，信号 2.0；"平n"表示 n 个 K 平分）：

| 布局 | 形状 | K* | 噪声 | CHAOS | PAS | AMI | kNN | silhouette | 现状面板 | 现状面板 K* 处 / 最高 |
|---|---|---|---|---|---|---|---|---|---|---|
| grid | stripes | 4 | 0% | 2–40（平39） | 2–4（平3） | 32 | 2 | 4 | 32 | 0.787 / 0.888 |
| grid | stripes | 4 | 5% | 40 | 8 | 35 | 8 | 4 | 40 | 0.478 / 0.740 |
| grid | stripes | 4 | 15% | 37 | 6 | 35 | 14 | 4 | 37 | 0.310 / 0.583 |
| grid | stripes | 7 | 0% | 2–40（平39） | 2–7（平6） | 37 | 2 | 7 | 29 | 0.813 / 0.888 |
| grid | stripes | 7 | 5% | 37 | 7 | 40 | 4 | 7 | 37 | 0.604 / 0.740 |
| grid | stripes | 7 | 15% | 37 | 7 | 37 | 16 | 7 | 37 | 0.417 / 0.587 |
| grid | stripes | 10 | 0% | 2–40（平39） | 2–10（平9） | 40 | 2 | 10 | 40 | 0.797 / 0.878 |
| grid | stripes | 10 | 5% | 38 | 8 | 40 | 4 | 10 | 39 | 0.610 / 0.737 |
| grid | stripes | 10 | 15% | 37 | 7 | 40 | 20 | 2 | 40 | 0.459 / 0.575 |
| grid | voronoi | 4 | 0% | 2–40（平39） | 2 | 40 | 2 | 4 | 40 | 0.798 / 0.894 |
| grid | voronoi | 4 | 5% | 32 | 7 | 40 | 7 | 4 | 40 | 0.485 / 0.745 |
| grid | voronoi | 4 | 15% | 37 | 6 | 40 | 11 | 4 | 37 | 0.311 / 0.588 |
| grid | voronoi | 7 | 0% | 2–40（平39） | 4 | 38 | 2 | 6 | 38 | 0.834 / 0.887 |
| grid | voronoi | 7 | 5% | 37 | 8 | 38 | 8 | 7 | 37 | 0.597 / 0.743 |
| grid | voronoi | 7 | 15% | 39 | 8 | 40 | 11 | 7 | 39 | 0.414 / 0.583 |
| grid | voronoi | 10 | 0% | 2–8（平7） | 4 | 29 | 3 | 10 | 29 | 0.854 / 0.900 |
| grid | voronoi | 10 | 5% | 31 | 6 | 36 | 6 | 10 | 31 | 0.637 / 0.752 |
| grid | voronoi | 10 | 15% | 36 | 6 | 36 | 14 | 2 | 36 | 0.485 / 0.594 |
| poisson | stripes | 4 | 0% | 2 | 2 | 40 | 2 | 4 | 17 | 0.790 / 0.885 |
| poisson | stripes | 4 | 5% | 39 | 4 | 40 | 8 | 4 | 39 | 0.601 / 0.742 |
| poisson | stripes | 4 | 15% | 40 | 8 | 38 | 14 | 4 | 35 | 0.446 / 0.598 |
| poisson | stripes | 7 | 0% | 2 | 2 | 39 | 2 | 7 | 38 | 0.796 / 0.892 |
| poisson | stripes | 7 | 5% | 37 | 5 | 40 | 5 | 7 | 38 | 0.632 / 0.751 |
| poisson | stripes | 7 | 15% | 30 | 5 | 39 | 14 | 7 | 38 | 0.484 / 0.607 |
| poisson | stripes | 10 | 0% | 2 | 2 | 40 | 2 | 10 | 40 | 0.792 / 0.874 |
| poisson | stripes | 10 | 5% | 26 | 4 | 40 | 4 | 10 | 40 | 0.646 / 0.733 |
| poisson | stripes | 10 | 15% | 33 | 5 | 40 | 20 | 2 | 40 | 0.493 / 0.589 |
| poisson | voronoi | 4 | 0% | 11 | 3 | 40 | 2 | 4 | 35 | 0.786 / 0.883 |
| poisson | voronoi | 4 | 5% | 24 | 6 | 40 | 6 | 4 | 35 | 0.596 / 0.742 |
| poisson | voronoi | 4 | 15% | 33 | 6 | 40 | 12 | 4 | 33 | 0.436 / 0.602 |
| poisson | voronoi | 7 | 0% | 6 | 3 | 40 | 2 | 2 | 39 | 0.817 / 0.884 |
| poisson | voronoi | 7 | 5% | 36 | 9 | 40 | 8 | 2 | 36 | 0.640 / 0.746 |
| poisson | voronoi | 7 | 15% | 33 | 8 | 40 | 14 | 2 | 40 | 0.483 / 0.598 |
| poisson | voronoi | 10 | 0% | 4 | 4 | 40 | 2 | 10 | 35 | 0.848 / 0.881 |
| poisson | voronoi | 10 | 5% | 38 | 5 | 40 | 7 | 10 | 40 | 0.687 / 0.743 |
| poisson | voronoi | 10 | 15% | 34 | 6 | 40 | 14 | 2 | 34 | 0.526 / 0.597 |

- 现状面板的 argmax 在 **17–40**，中位数比 K* 多 **30**；10/36 个配置落在上限 40。K* 处分数比最高分低 **0.033–0.277**（中位数 0.111）。0/36 落在 K*±1。
- 把候选扩到 60 后（表 B），现状面板 argmax 中位数变成 **50（网格）/ 51（Poisson）**，只有 3/36 落在 60 这个新上限；在 K∈[2K*, 60] 段上对 K 的 Spearman 中位数为 +0.85 / +0.89。**偏好没有停下，随上限一起后移**：原研究"偏好最大 K"不是 2K* 截断造成的假象。

表 B　尾段走势（K∈[2K*, 60]）与 argmax 中位数（K≤60）：

| 布局 | 量 | 现状面板 | CHAOS | PAS | AMI | kNN | silhouette |
|---|---|---|---|---|---|---|---|
| grid | 尾段 Spearman 中位数 | +0.85 | +0.94 | −1.00 | +0.85 | −1.00 | −1.00 |
| grid | argmax 中位数 | 50 | 56（6 个无噪声配置全段平分，除外） | 6（2 个平分除外） | 46 | 6 | 6 |
| poisson | 尾段 Spearman 中位数 | +0.89 | +0.78 | −1.00 | +0.96 | −1.00 | −1.00 |
| poisson | argmax 中位数 | 51 | 51 | 5 | 54 | 6 | 4 |

表 C　AMI 的 argmax（K≤60）与参照簇数：

| 布局 | 参照簇数 | AMI argmax K（18 个配置） |
|---|---|---|
| grid | 5/19/27 | 29, 32, 36, 36, 38, 42, 42, 46, 46, 47, 47, 47, 54, 57, 57, 59, 60, 60 |
| poisson | 8/26/36 | 43, 44, 46, 47, 48, 48, 51, 53, 53, 55, 56, 56, 58, 58, 58, 60, 60, 60 |

- **AMI 不与参照簇数重合**：它的 argmax 全都**不小于**最细参照（分辨率 1.0）的簇数，并越过它继续上升（Poisson 参照 36，argmax 43–60）。机制：AMI 取三个分辨率的最大值，被最细的那个参照主导；把区域继续切细的候选与一个 27/36 簇的空间划分越来越一致，AMI 对"比参照更细"的惩罚很弱。它衡量的是"与某一空间尺度的 Leiden 切分的一致程度"，这个尺度由 `LEIDEN_RESOLUTIONS` 决定，与组织的真实区域数无关。
- **CHAOS 在带噪声时同样持续上升**（尾段 Spearman +0.78 到 +0.94，argmax 中位数 51–56），无噪声网格上对 2…40 全部饱和平分，无噪声 Poisson 上反而偏小 K。
- **PAS、kNN agreement、silhouette 在尾段都随 K 下降**（Spearman −1.00）。silhouette 是唯一大体在 K* 取峰的成员：28/36 恰为 K*，偏离的 8 个里 7 个是 argmax=2（K*=10 高噪声，或 Poisson Voronoi K*=7 这一区域布置）。
- CHAOS 的动态范围 (E_rand−d_min)/d_min（无噪声中位数）：网格 K=2/4/10/40 为 0.047/0.207/0.712/2.323，Poisson 为 0.416/0.994/2.169/5.477。小 K 时分母趋 0 的现象属实，但它只解释小 K 端；**CHAOS 在 K 远大于 K* 时仍上升**，而那里分母早已不小（网格 K=20 时 >1.3 d_min）。可能的机制（推测，未单独验证）：分母 E_rand−d_min 随 K 持续增长，噪声点到同标签最近点的距离增长得更慢，所以校正后的噪声惩罚随 K 变小。无论机制如何，这一段的上升都不是分母下限能消除的（见结果二的 b1/b2）。

### 结果二：各修正方案

全部 36 个配置与各划分上的偏差（K≤40，信号 2.0；格式见"方法"）：

| 方案 | 全部 36 | 训练：条带 | 留出：Voronoi | 训练：K*∈{4,10} | 留出：K*=7 |
|---|---|---|---|---|---|
| a_current | +30.0 / 30.0 / 0% / 0% | +30.0 / 30.0 / 0% / 0% | +30.5 / 30.5 / 0% / 0% | +30.0 / 30.0 / 0% / 0% | +31.0 / 31.0 / 0% / 0% |
| b1_floor | +30.0 / 30.0 / 0% / 0% | +30.0 / 30.0 / 0% / 0% | +30.5 / 30.5 / 0% / 0% | +30.0 / 30.0 / 0% / 0% | +31.0 / 31.0 / 0% / 0% |
| b2_reliab | +30.0 / 30.0 / 0% / 0% | +30.0 / 30.0 / 0% / 0% | +30.5 / 30.5 / 0% / 0% | +30.0 / 30.0 / 0% / 0% | +31.0 / 31.0 / 0% / 0% |
| b3_knn | +21.0 / 21.0 / 0% / 0% | +22.5 / 22.5 / 0% / 0% | +18.5 / 18.5 / 0% / 0% | +18.0 / 18.0 / 0% / 0% | +22.5 / 22.5 / 0% / 0% |
| d0_noami | +25.0 / 25.0 / 3% / 3% | +25.0 / 25.0 / 0% / 0% | +25.0 / 25.0 / 6% / 6% | +23.5 / 23.5 / 4% / 4% | +26.5 / 26.5 / 0% / 0% |
| d1_ami01 | +28.5 / 28.5 / 0% / 0% | +30.0 / 30.0 / 0% / 0% | +26.0 / 26.0 / 0% / 0% | +28.0 / 28.0 / 0% / 0% | +29.5 / 29.5 / 0% / 0% |
| d2_noami_floor | +25.0 / 25.0 / 3% / 3% | +25.0 / 25.0 / 6% / 6% | +25.0 / 25.0 / 0% / 0% | +23.5 / 23.5 / 4% / 4% | +26.5 / 26.5 / 0% / 0% |
| c_silmap_0.5 | +29.5 / 29.5 / 3% / 0% | +30.0 / 30.0 / 0% / 0% | +28.5 / 28.5 / 6% / 0% | +29.0 / 29.0 / 0% / 0% | +30.0 / 30.0 / 8% / 0% |
| c_sil0_0.5 | +30.0 / 30.0 / 6% / 3% | +30.0 / 30.0 / 0% / 0% | +30.0 / 30.0 / 11% / 6% | +30.0 / 30.0 / 4% / 4% | +30.5 / 30.5 / 8% / 0% |
| c_sil0_0.67 | +27.5 / 27.5 / 42% / 39% | +30.0 / 30.0 / 39% / 39% | +22.5 / 22.5 / 44% / 39% | +22.5 / 22.5 / 46% / 46% | +30.0 / 30.0 / 33% / 25% |
| e_ami01_0.5 | +26.5 / 26.5 / 33% / 28% | +29.0 / 29.0 / 33% / 33% | +25.0 / 25.0 / 33% / 22% | +26.5 / 26.5 / 33% / 33% | +27.5 / 27.5 / 33% / 17% |
| e_chaos_0.5 | +10.5 / 13.0 / 47% / 42% | +11.5 / 11.5 / 50% / 50% | +10.5 / 13.0 / 44% / 33% | +10.5 / 10.5 / 50% / 50% | +11.5 / 14.0 / 42% / 25% |
| e_floor_0.5 | +16.0 / 16.0 / 33% / 28% | +17.0 / 17.0 / 33% / 33% | +16.0 / 16.0 / 33% / 22% | +16.0 / 16.0 / 33% / 33% | +15.0 / 15.0 / 33% / 17% |
| e_reliab_0.5 | +16.0 / 16.0 / 33% / 28% | +17.0 / 17.0 / 33% / 33% | +16.0 / 16.0 / 33% / 22% | +16.0 / 16.0 / 33% / 33% | +15.0 / 15.0 / 33% / 17% |
| e_knn_0.5 | +0.0 / 0.0 / 67% / 58% | +0.0 / 0.0 / 61% / 61% | +0.0 / 0.0 / 72% / 56% | +0.0 / 0.0 / 67% / 67% | -1.0 / 1.0 / 67% / 42% |
| e_knn_0.67 | +0.0 / 0.0 / 86% / 78% | +0.0 / 0.0 / 83% / 83% | +0.0 / 0.0 / 89% / 72% | +0.0 / 0.0 / 88% / 88% | +0.0 / 0.0 / 83% / 58% |
| e_pas_0.5 | +0.0 / 0.0 / 75% / 64% | +0.0 / 0.0 / 78% / 78% | -0.5 / 0.5 / 72% / 50% | +0.0 / 0.0 / 71% / 71% | -0.5 / 0.5 / 83% / 50% |
| e_pas_0.67 | +0.0 / 0.0 / 89% / 78% | +0.0 / 0.0 / 94% / 94% | +0.0 / 0.0 / 83% / 61% | +0.0 / 0.0 / 88% / 88% | +0.0 / 0.0 / 92% / 58% |
| sil_only | +0.0 / 0.0 / 81% / 78% | +0.0 / 0.0 / 89% / 89% | +0.0 / 0.0 / 72% / 67% | +0.0 / 0.0 / 83% / 83% | +0.0 / 0.0 / 75% / 67% |

方案定义（校正值均裁到 [0,1] 后加权平均，与生产 `combine` 相同）：

- (a) `a_current`：现状，CHAOS 0.4 / PAS 0.2 / AMI 0.4。
- (b) CHAOS 校正公式：
  - `b1_floor`：分母加下限，`(E−CHAOS) / max(E−d_min, d_min)`。原理：随机标签与完美标签相差不到一个平均最近邻间距时，CHAOS 没有分辨力，下限把放大倍数封顶在 1/d_min。
  - `b2_reliab`：公式不变，CHAOS 的权重乘以可靠度 `min(1, (E−d_min)/d_min)`（在 `combine` 里再归一化）。原理同上，但不改校正值本身，而是在它没有分辨力时让它少说话。
  - `b3_knn`：用已实现的 `knn_agreement` 校正值代替 CHAOS。原理：同属"近邻同标签"类，期望是闭式，分母 1−E ≥ 1/2，没有放大问题。
  - `d2_noami_floor`：去 AMI 且用 b1 下限（单独看 CHAOS 修正的作用）。
- (c) 加 silhouette：`c_silmap_w` 用生产现有映射 (s+1)/2；`c_sil0_w` 用原值 s（裁到 [0,1]）。现状三项按 0.4:0.2:0.4 分 1−w。
- (d) AMI：`d0_noami` 去掉；`d1_ami01` 降到 0.1。
- (e) 组合：`e_chaos_w`（去 AMI，CHAOS:PAS=2:1，+ silhouette 原值 w）、`e_floor_w`（同上但 CHAOS 用 b1）、`e_reliab_w`（同上但 CHAOS 用 b2）、`e_knn_w`（去 AMI，kNN:PAS=2:1，+ silhouette）、`e_pas_w`（去 AMI 与 CHAOS，PAS 1−w + silhouette w）、`e_ami01_w`（CHAOS 0.4/PAS 0.2/AMI 0.1 按比例分 1−w，+ silhouette）。2:1 沿用现状 CHAOS:PAS 的比例，不调。

silhouette 用原值而不是 (s+1)/2 的理由：面板约定"1 = 完美、0 = 随机水平"，而 (s+1)/2 把随机水平放在 0.5，等于把它的有效权重减半，同时给每个候选一个 0.5 的常数底。表中 `c_silmap_0.5` 与 `c_sil0_0.5` 分别只有 3% 与 6% 落在 K*±1，说明在 AMI 还在时，两种映射下 silhouette 都压不住。

**在训练集上选 w、留出集上验证**（选中的 w、训练结果、留出结果；留出另列信号 1.0 与 4.0）：

| 方案族 | 划分 | 选中 w | 训练（信号 2.0） | 留出（信号 2.0） | 留出（信号 1.0） | 留出（信号 4.0） |
|---|---|---|---|---|---|---|
| c_sil0 | 训:条带→留:Voronoi | 0.67 | +30.0 / 30.0 / 39% / 39% | +22.5 / 22.5 / 44% / 39% | +30.5 / 30.5 / 0% / 0% | +0.0 / 0.0 / 100% / 100% |
| c_sil0 | 训:K*4,10→留:K*=7 | 0.67 | +22.5 / 22.5 / 46% / 46% | +30.0 / 30.0 / 33% / 25% | +31.0 / 31.0 / 0% / 0% | +0.0 / 0.0 / 100% / 100% |
| e_ami01 | 训:条带→留:Voronoi | 0.67 | +11.5 / 11.5 / 50% / 50% | +10.5 / 11.0 / 50% / 33% | +26.0 / 26.0 / 0% / 0% | +0.0 / 0.0 / 100% / 100% |
| e_ami01 | 训:K*4,10→留:K*=7 | 0.67 | +10.5 / 10.5 / 50% / 50% | +11.5 / 12.0 / 50% / 25% | +29.5 / 29.5 / 0% / 0% | +0.0 / 0.0 / 100% / 100% |
| e_chaos | 训:条带→留:Voronoi | 0.67 | +0.0 / 0.0 / 61% / 61% | +10.5 / 13.0 / 44% / 33% | +25.0 / 25.0 / 0% / 0% | +0.0 / 0.0 / 100% / 100% |
| e_chaos | 训:K*4,10→留:K*=7 | 0.67 | +0.0 / 0.0 / 54% / 54% | +0.0 / 3.0 / 50% / 33% | +26.5 / 26.5 / 0% / 0% | +0.0 / 0.0 / 100% / 100% |
| e_floor | 训:条带→留:Voronoi | 0.67 | +9.0 / 9.0 / 39% / 39% | +16.0 / 16.0 / 33% / 22% | +25.0 / 25.0 / 6% / 6% | +0.0 / 0.0 / 100% / 100% |
| e_floor | 训:K*4,10→留:K*=7 | 0.67 | +11.0 / 11.0 / 38% / 38% | +15.0 / 15.0 / 33% / 17% | +26.5 / 26.5 / 0% / 0% | +0.0 / 0.0 / 100% / 100% |
| e_knn | 训:条带→留:Voronoi | 0.67 | +0.0 / 0.0 / 83% / 83% | +0.0 / 0.0 / 89% / 72% | +0.5 / 3.0 / 22% / 6% | +0.0 / 0.0 / 100% / 100% |
| e_knn | 训:K*4,10→留:K*=7 | 0.67 | +0.0 / 0.0 / 88% / 88% | +0.0 / 0.0 / 83% / 58% | +0.0 / 4.5 / 25% / 0% | +0.0 / 0.0 / 100% / 100% |
| e_pas | 训:条带→留:Voronoi | 0.67 | +0.0 / 0.0 / 94% / 94% | +0.0 / 0.0 / 83% / 61% | -2.0 / 2.5 / 22% / 6% | +0.0 / 0.0 / 100% / 100% |
| e_pas | 训:K*4,10→留:K*=7 | 0.67 | +0.0 / 0.0 / 88% / 88% | +0.0 / 0.0 / 92% / 58% | -1.0 / 2.0 / 42% / 17% | +0.0 / 0.0 / 100% / 100% |
| a_current | 训:条带→留:Voronoi | — | +30.0 / 30.0 / 0% / 0% | +30.5 / 30.5 / 0% / 0% | +30.5 / 30.5 / 0% / 0% | +30.5 / 30.5 / 0% / 0% |
| a_current | 训:K*4,10→留:K*=7 | — | +30.0 / 30.0 / 0% / 0% | +31.0 / 31.0 / 0% / 0% | +31.0 / 31.0 / 0% / 0% | +31.0 / 31.0 / 0% / 0% |
| d0_noami | 训:条带→留:Voronoi | — | +25.0 / 25.0 / 0% / 0% | +25.0 / 25.0 / 6% / 6% | +25.0 / 25.0 / 6% / 6% | +25.0 / 25.0 / 6% / 6% |
| d0_noami | 训:K*4,10→留:K*=7 | — | +23.5 / 23.5 / 4% / 4% | +26.5 / 26.5 / 0% / 0% | +26.5 / 26.5 / 0% / 0% | +26.5 / 26.5 / 0% / 0% |
| sil_only | 训:条带→留:Voronoi | — | +0.0 / 0.0 / 89% / 89% | +0.0 / 0.0 / 72% / 67% | -5.0 / 5.0 / 0% / 0% | +0.0 / 0.0 / 100% / 100% |
| sil_only | 训:K*4,10→留:K*=7 | — | +0.0 / 0.0 / 83% / 83% | +0.0 / 0.0 / 75% / 67% | -5.0 / 5.0 / 0% / 0% | +0.0 / 0.0 / 100% / 100% |

每个族在两种划分下选中的 w 都是候选上限 0.67，即"silhouette 越多越好"。所以下面按 w=0.5（空间证据与表达证据各半，事先定的上限）与 w=0.67 两档如实并列，不把 0.67 当成调出来的最优值。

按噪声分层（全部 36，信号 2.0）：

| 方案 | 噪声 0 | 噪声 5% | 噪声 15% |
|---|---|---|---|
| a_current | +30.0 / 30.0 / 0% / 0% | +30.0 / 30.0 / 0% / 0% | +30.5 / 30.5 / 0% / 0% |
| d0_noami | -4.5 / 4.5 / 8% / 8% | +28.5 / 28.5 / 0% / 0% | +27.0 / 27.0 / 0% / 0% |
| d2_noami_floor | +3.0 / 5.0 / 8% / 8% | +28.5 / 28.5 / 0% / 0% | +27.0 / 27.0 / 0% / 0% |
| e_chaos_0.5 | +0.0 / 0.0 / 92% / 83% | +10.5 / 11.0 / 50% / 42% | +27.0 / 27.0 / 0% / 0% |
| e_floor_0.5 | +2.0 / 2.5 / 50% / 42% | +10.5 / 11.0 / 50% / 42% | +27.0 / 27.0 / 0% / 0% |
| e_knn_0.5 | -5.0 / 5.0 / 33% / 33% | +0.0 / 0.0 / 75% / 58% | +0.0 / 0.0 / 92% / 83% |
| e_pas_0.5 | +0.0 / 0.0 / 83% / 75% | +0.0 / 0.0 / 83% / 67% | -0.5 / 0.5 / 58% / 50% |
| e_ami01_0.5 | +0.0 / 0.0 / 100% / 83% | +29.5 / 29.5 / 0% / 0% | +29.0 / 29.0 / 0% / 0% |
| sil_only | +0.0 / 0.0 / 92% / 83% | +0.0 / 0.0 / 92% / 92% | +0.0 / 0.0 / 58% / 58% |

### 结论

1. **偏好随 K 单调上升，不是边界效应。** 上限从 2K* 扩到 40 再到 60，现状面板的 argmax 始终跟着上限走（中位数 K*+30 → 约 50），0/36 落在 K*±1。
2. **K 扩大后，主推手是 AMI，其次是带噪声的 CHAOS。** 只去掉 AMI（`d0_noami`）时，偏差中位数从 +30 降到 +25，仍几乎全错；这时带噪声的 CHAOS 接手把 argmax 推向 K≈25–40。AMI 追随的是最细参照 Leiden（分辨率 1.0）的尺度，并越过它，与真实区域数无关。
3. **CHAOS 分母加下限或可靠度加权几乎无效。** `b1`、`b2` 与现状完全相同（AMI 仍主导）；去 AMI 后 `e_floor_0.5`、`e_reliab_0.5` 反而比不修正的 `e_chaos_0.5` 差（33% 对 47%），因为下限同时压低了无噪声小 K 候选的 CHAOS（无噪声分层从 92% 降到 50%）。CHAOS 在大 K 的上升是结构性的（见结果一末条），分母下限治不了。
4. **纯空间指标本身不能选出 K*。** 这与 §3.7.2 的预期一致：空间连续地再切分一个真实区域，空间指标照样给高分。能选 K 的只有表达证据。silhouette 单独使用时 81% 落在 K*±1，且只在弱信号（1.0）下失效：这时 silhouette 本身偏向 K=2，任何方案都选不出 K*。
5. **与 silhouette 搭配的空间项里，PAS 最合适，CHAOS 最差。** PAS 在 K≥4 后大致平坦、尾段略降，带噪声时惩罚 K=2–3，它的残余偏向指向小 K，不与 silhouette 冲突；CHAOS 带噪声时的上升会把 argmax 拉回大 K（`e_chaos_0.5` 在 15% 噪声下 0%）。kNN agreement 带噪声时表现好（15% 噪声下 92%），但在无噪声数据上因边界长度惩罚偏向 K=2（无噪声只有 33%）。
6. 推荐方案（`e_pas_0.5`）剩下的错误**全部偏小 K（欠切），没有一例过切**；36 个配置里只有 2 例退到 K=2（Poisson 条带 K*=10 无噪声、Poisson Voronoi K*=7 无噪声，后者 silhouette 本身就在 K=2 取峰）。

### 给 owner 的推荐

**推荐**：0057 用新面板版本 `spatial_domains/3`，计分项只保留 **PAS（校正值）0.5 + silhouette（原值，裁到 [0,1]）0.5**；CHAOS、`spatial_leiden_ami`、`knn_agreement` 降为权重 0 的诊断，照常写进 `metrics.json`。
- 依据：留出 Voronoi 72% 落在 K*±1（偏差中位数 −0.5），留出 K*=7 83%（−0.5），全部 36 个 75%；现状这三个数都是 0%。w=0.5 是"空间与表达各半"的事先上限，不是在数据上调出来的；w=0.67 时这三个数升到 83% / 92% / 89%，说明结论对 w 不敏感，只是方向上 silhouette 越重越好。
- 这需要生产改动（0057 范围）：(i) silhouette 的计分值由 (s+1)/2 改成 s 裁到 [0,1]；(ii) 权重表改动并升版本号；(iii) 输入没有 `X_pca` 时 silhouette 不可用，面板会退化成只有 PAS（偏小 K）。0057 需要定这时是拒绝打分、降级告警，还是退回旧权重。

**备选**：去 AMI，**kNN agreement 1/3 + PAS 1/6 + silhouette 0.5**（`e_knn_0.5`）。留出 Voronoi 72%、K*=7 67%、全部 67%；带噪声时比推荐方案更稳（15% 噪声 92% 对 58%），无噪声时更差（33% 对 83%）。适合 owner 判断真实数据的方法输出更像"带噪声的连续区域"时采用。它保留了一个与 CHAOS 同类（"近邻同标签"）、但期望是闭式且没有分母放大问题的空间项。

**不推荐**：只修 CHAOS 的分母（`b1`/`b2`，无效）；保留 AMI 而只加 silhouette（`c_*`，w≤0.5 时 ≤11%）；AMI 降到 0.1（`e_ami01_0.5` 33%，带噪声时 0%）。若要保留 AMI，需要先改它的参照分辨率，让它不再被最细尺度主导，这需要另做研究。

### 局限

- **全部是合成数据，没有用真实数据验证。** 区域是条带或 Voronoi，表达是各向同性高斯加一维独热信号，噪声是均匀随机改标签。真实组织的区域有层级与梯度，方法输出的误差在空间上成片而不是散点，真实 `X_pca` 上的 silhouette 数值范围与本研究不同。推荐的权重在真实数据（例如带人工注释的 DLPFC 切片）上复核之前，只能算方向性证据。
- **silhouette 的结论依赖信号强度。** 信号 1.0 时 silhouette 自己偏向 K=2，推荐方案留出集只有 22–42% 落在 K*±1；信号 4.0 时几乎所有带 silhouette 的方案都到 100%。0.5 这个权重在"表达信号偏弱"的真实数据上是否足够，本研究回答不了。
- 候选只有"合并/真值/连续再切分"三类，都是空间连续的，没有覆盖"表达上对、空间上碎"的候选（例如纯表达聚类）。区分这类候选正是空间项的用处，推荐方案保留 PAS 0.5 的理由之一在此，但本研究没有量化它。
- K*≤10 且每个区域的表达信号互不相同（`truth % 10`）；K*>10 或相邻区域表达相近的情形未测。
- 平分取离 K* 最远者，是对无噪声网格（CHAOS 全饱和）偏保守的计法。
- 参照 Leiden 簇数与原报告略有不同（网格 5/19/27 对 5/17/28），来自近似近邻的线程敏感性，不改变 AMI 的走势。

## 真实数据验证（Slide-seqV2 小鼠海马，2026-09-25）

owner 批准的 F3。目的：在真实数据上检验"扩大候选 K 的复查"推荐的候选面板（PAS 0.5 + silhouette 0.5），结果决定 F1（0057 是否采用候选面板为默认）。**开发期数据，结论待正式数据集验证。** 生产代码未改动（`omicsclaw/` 下无修改），面板仍是 `spatial_domains/2`。本节只报告事实与逐条通过标准，裁定归 owner。

### 方法

- **数据**：`/workspace/dataset/private/spFoundation_SpatialCorpus/test/slideseqv2_mouse_hippocampus.h5ad`，41,786 个 bead，每 bead UMI 中位数 **76**，只读。
- **预处理**（与冒烟测试相同）：`X ← layers['counts']`，`obs` 只留 `batch`；`spatial-preprocess --data-type slide_seq --species mouse`，其余默认（69 s，无 bead 丢失，`X_pca` 30 维）；预处理后再把 `obs` 剥到只剩 `batch`（E3）。真值 `obs['cell_type']` 只在打分阶段读取，不进入任何候选生成步骤。
- **候选生成**（59 个试验，全部 ok）：
  - 经 `omicsclaw.ensemble`（`open_ensemble` + `EnsembleRunner.fan_out`，同一 `run_id`，`data_type=slide_seq`）跑 53 个：leiden、louvain 的 `resolution` ∈ {0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.7, 1.0, 1.4, 2.0}（`spatial_weight` 默认 0.3），另在 resolution 0.3/1.0 上加 `spatial_weight` ∈ {0, 0.6, 0.9}；spagcn、graphst、cellcharter 的 `n_domains` ∈ {4, 6, 7, 8, 10, 14, 20}（7 为各脚本默认）。自动检测到 4 张 GPU，graphst/cellcharter 的 14 个试验分到 `cuda:0–3`；批墙钟 626 s，各试验 `wall_s` 之和约 4860 s。runner 写出的 `metrics.json` 分数与本研究用 `compute_panel` 的复算逐一相同（51/51，差 0）。
  - leiden/louvain 在调参区间上限 resolution 2.0 时只有 25 个簇，为覆盖到约 40，另用同一 skill 脚本**直接运行**（不经 runner，`tuning.yaml` 的区间 [0.1, 2.0] 会拒绝）resolution ∈ {3, 4.5, 6}，表中以 `*` 标记。
  - 排除：leiden/louvain resolution 0.1 只给出 1 个簇（面板拒绝打分，silhouette 无定义）；louvain 的 `spatial_weight` 对结果**没有影响**（0.6、0.9 与 0.3 的划分逐 bead 相同，4 个重复只计一次）。分析的候选共 **53 个**，K 从 2 到 118。stagate、banksy 缺包，未跑。
  - 缺 `X_pca`（F2）：本研究没有遇到，预处理输出有 `X_pca`。
- **打分**：现状面板直接调用生产 `compute_panel`（CHAOS 0.4 / PAS 0.2 / spatial-Leiden AMI 0.4）；候选面板 = 0.5·clip(PAS 校正值) + 0.5·clip(silhouette 原值)；备选 = kNN 1/3 + PAS 1/6 + silhouette 0.5。silhouette 与合成研究一致：`sklearn.metrics.silhouette_score` 于 `X_pca`，抽样 5000，种子 0（与生产 `SILHOUETTE_SEED` 相同）；另用种子 1、2 与 20000 抽样检验稳定性。
- **外部指标**：只在纳入的 4 类 bead 上算（`CA1_CA2_CA3_Subiculum` 7649、`DentatePyramids` 6606、`Subiculum_Entorhinal_cl2` 2896、`Subiculum_Entorhinal_cl3` 1985，共 19,136）：ARI、AMI、NMI；对过切宽容的 homogeneity 与"多数投票映射准确率"（每个候选簇映射到其中最多的区域）作敏感性分析。多数投票的基线（全判为最大类）为 **0.400**。
- **统计**：Spearman ρ，bootstrap（按候选重抽 4000 次）95% 百分位区间；面板间差异用配对 bootstrap。
- 复现：`PYTHONPATH=<repo> /opt/conda/envs/OmicsClaw/bin/python docs/plans/0056-panel-bias-study/real_data.py {prepare,generate,score,analyse,ceiling} --work /tmp/0056_f3`（中间文件都在 `/tmp/0056_f3`，不进仓库）。

### 先说清楚：这份真值在这份数据上几乎不可恢复

结果解读取决于这一点，所以放在表格之前（`real_data.py ceiling`）：

| 量 | 值 | 说明 |
|---|---|---|
| 纳入 4 类的空间 10-NN 同类比例 | **0.475**（随机 0.313） | 只比随机略高；4 类在切片上大面积交错 |
| 4 类的空间质心 / 标准差（坐标跨度约 4900） | 质心两两间距 ≤ 820，各轴标准差 1010–1370 | 4 类都铺满整张切片，不是四块相互分开的"区域" |
| 用真值本身做空间 kNN 多数投票平滑后的 ARI（k=10/30/100） | **0.223 / 0.166 / 0.142** | 任何空间连续的划分在这份真值上 ARI 的大致上限 |
| 真值在 `X_pca` 上的 silhouette（纳入 bead，抽样 5000） | **−0.010** | 表达嵌入里 4 类也分不开 |
| 标记基因（每万 UMI 均值，与纳入的另外 3 类的最大值比较） | DentatePyramids：Prox1 4.6 对 ≤1.4、C1ql2 8.2 对 ≤0.6；CA1：Wfs1 6.3 对 ≤2.0、Neurod6 15.8 对 ≤5.4；cl2：Tshz2 43.7 对 ≤8.9；cl3：Nr4a2 16.9 对 ≤1.4 | 标签本身与标记一致，不是对错位；是逐 bead 的细胞类型调用，UMI 太低，单个 bead 的表达噪声远大于类间差异 |

所以 53 个候选的 ARI 全落在 **−0.006 到 0.061**，多数投票准确率在 0.400–0.514（基线 0.400）。外部指标的动态范围很窄、噪声大，下面所有相关都是在"接近随机"的区间里比较。此外，这份真值是细胞类型而不是区域：K 越大，簇越容易单独抓到某一类细胞，所以 **ARI 本身随 K 上升**（ρ(ARI, K) = +0.40 [+0.12, +0.62]；homogeneity +0.83，多数投票 +0.84），与"区域数为 4、ARI 惩罚过切"的预设相反。偏好小 K 的面板在这份真值上天然吃亏。

### 结果


试验 59 个，59 个 ok；去掉 K=1 与重复划分后分析 53 个候选；runner fan-out 墙钟 626 s，GPU ['0', '1', '2', '3']。


#### 表 1　全部候选

| 候选 | K | 现状 | 候选面板 | 备选 | CHAOS | PAS | AMI(空间) | kNN | sil | ARI | AMI | NMI | homog. | 多数投票准确率 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cellcharter(n=4) | 4 | 0.655 | 0.463 | 0.430 | 0.866 | 0.916 | 0.313 | 0.816 | 0.011 | 0.025 | 0.013 | 0.013 | 0.012 | 0.411 |
| cellcharter(n=6) | 6 | 0.666 | 0.448 | 0.413 | 0.872 | 0.897 | 0.345 | 0.789 | -0.021 | 0.038 | 0.038 | 0.038 | 0.040 | 0.412 |
| cellcharter(n=7) (默认) | 7 | 0.708 | 0.459 | 0.428 | 0.891 | 0.918 | 0.421 | 0.826 | -0.021 | 0.048 | 0.085 | 0.085 | 0.094 | 0.416 |
| cellcharter(n=8) | 8 | 0.687 | 0.449 | 0.412 | 0.881 | 0.897 | 0.387 | 0.789 | -0.017 | 0.037 | 0.073 | 0.073 | 0.084 | 0.421 |
| cellcharter(n=10) | 10 | 0.664 | 0.397 | 0.351 | 0.879 | 0.794 | 0.383 | 0.657 | -0.051 | 0.032 | 0.075 | 0.076 | 0.095 | 0.426 |
| cellcharter(n=14) | 14 | 0.652 | 0.385 | 0.342 | 0.856 | 0.770 | 0.388 | 0.640 | -0.067 | 0.033 | 0.073 | 0.073 | 0.099 | 0.423 |
| cellcharter(n=20) | 20 | 0.617 | 0.310 | 0.275 | 0.856 | 0.620 | 0.376 | 0.516 | -0.096 | 0.026 | 0.071 | 0.071 | 0.109 | 0.438 |
| graphst(n=4) | 4 | 0.551 | 0.391 | 0.335 | 0.861 | 0.781 | 0.126 | 0.613 | -0.013 | 0.029 | 0.019 | 0.019 | 0.019 | 0.417 |
| graphst(n=6) | 6 | 0.542 | 0.346 | 0.297 | 0.861 | 0.691 | 0.149 | 0.546 | -0.026 | 0.036 | 0.046 | 0.047 | 0.055 | 0.425 |
| graphst(n=7) (默认) | 7 | 0.530 | 0.325 | 0.283 | 0.850 | 0.650 | 0.149 | 0.523 | -0.013 | 0.035 | 0.025 | 0.025 | 0.030 | 0.424 |
| graphst(n=8) | 8 | 0.548 | 0.334 | 0.292 | 0.870 | 0.668 | 0.166 | 0.542 | -0.037 | 0.043 | 0.057 | 0.058 | 0.073 | 0.451 |
| graphst(n=10) | 10 | 0.507 | 0.283 | 0.253 | 0.828 | 0.566 | 0.157 | 0.477 | -0.017 | 0.036 | 0.027 | 0.027 | 0.036 | 0.423 |
| graphst(n=14) | 14 | 0.517 | 0.260 | 0.238 | 0.839 | 0.520 | 0.194 | 0.456 | -0.051 | 0.031 | 0.041 | 0.042 | 0.062 | 0.440 |
| graphst(n=20) | 20 | 0.503 | 0.228 | 0.217 | 0.827 | 0.456 | 0.201 | 0.424 | -0.068 | 0.034 | 0.054 | 0.055 | 0.088 | 0.466 |
| leiden(r=0.15,w=0.3) | 2 | 0.478 | 0.507 | 0.511 | 0.750 | 0.754 | 0.068 | 0.766 | 0.261 | -0.001 | 0.004 | 0.004 | 0.002 | 0.400 |
| leiden(r=0.2,w=0.3) | 3 | 0.405 | 0.388 | 0.389 | 0.648 | 0.554 | 0.087 | 0.556 | 0.222 | 0.001 | 0.004 | 0.004 | 0.003 | 0.400 |
| leiden(r=0.3,w=0.3) | 3 | 0.388 | 0.385 | 0.360 | 0.512 | 0.660 | 0.128 | 0.583 | 0.110 | 0.006 | 0.003 | 0.004 | 0.003 | 0.400 |
| leiden(r=0.3,w=0.6) | 3 | 0.710 | 0.531 | 0.523 | 0.996 | 0.993 | 0.284 | 0.971 | 0.068 | 0.011 | 0.006 | 0.006 | 0.005 | 0.408 |
| leiden(r=0.4,w=0.3) | 4 | 0.398 | 0.339 | 0.318 | 0.521 | 0.614 | 0.168 | 0.551 | 0.065 | 0.012 | 0.005 | 0.005 | 0.004 | 0.403 |
| leiden(r=0.5,w=0.3) | 8 | 0.396 | 0.319 | 0.268 | 0.526 | 0.587 | 0.170 | 0.432 | 0.052 | -0.006 | 0.029 | 0.030 | 0.032 | 0.415 |
| leiden(r=0.3,w=0) | 8 | 0.301 | 0.249 | 0.211 | 0.434 | 0.422 | 0.108 | 0.308 | 0.076 | 0.011 | 0.007 | 0.008 | 0.007 | 0.417 |
| leiden(r=0.7,w=0.3) | 10 | 0.342 | 0.246 | 0.209 | 0.444 | 0.476 | 0.172 | 0.366 | 0.016 | 0.033 | 0.044 | 0.044 | 0.057 | 0.416 |
| leiden(r=0.3,w=0.9) | 12 | 0.862 | 0.499 | 0.493 | 0.999 | 0.997 | 0.657 | 0.980 | -0.056 | 0.055 | 0.103 | 0.103 | 0.149 | 0.493 |
| leiden(r=1,w=0.3) (默认) | 13 | 0.321 | 0.205 | 0.180 | 0.427 | 0.410 | 0.172 | 0.334 | -0.002 | 0.027 | 0.037 | 0.038 | 0.053 | 0.421 |
| leiden(r=1,w=0.6) | 16 | 0.833 | 0.497 | 0.486 | 0.998 | 0.993 | 0.588 | 0.962 | -0.079 | 0.061 | 0.116 | 0.117 | 0.170 | 0.514 |
| leiden(r=1.4,w=0.3) | 18 | 0.292 | 0.173 | 0.156 | 0.389 | 0.345 | 0.170 | 0.295 | -0.093 | 0.022 | 0.038 | 0.039 | 0.057 | 0.421 |
| leiden(r=1,w=0) | 18 | 0.259 | 0.125 | 0.116 | 0.370 | 0.251 | 0.152 | 0.222 | -0.057 | 0.040 | 0.045 | 0.046 | 0.068 | 0.461 |
| leiden(r=2,w=0.3) | 25 | 0.279 | 0.132 | 0.125 | 0.390 | 0.264 | 0.175 | 0.244 | -0.083 | 0.036 | 0.059 | 0.060 | 0.098 | 0.486 |
| leiden(r=3,w=0.3*) | 43 | 0.244 | 0.090 | 0.094 | 0.351 | 0.181 | 0.169 | 0.192 | -0.080 | 0.033 | 0.058 | 0.059 | 0.110 | 0.497 |
| leiden(r=1,w=0.9) | 57 | 0.916 | 0.497 | 0.485 | 0.999 | 0.994 | 0.794 | 0.959 | -0.105 | 0.020 | 0.084 | 0.085 | 0.175 | 0.511 |
| leiden(r=4.5,w=0.3*) | 74 | 0.218 | 0.058 | 0.067 | 0.325 | 0.116 | 0.162 | 0.144 | -0.101 | 0.027 | 0.055 | 0.057 | 0.116 | 0.504 |
| leiden(r=6,w=0.3*) | 118 | 0.203 | 0.044 | 0.053 | 0.307 | 0.088 | 0.157 | 0.115 | -0.099 | 0.019 | 0.050 | 0.054 | 0.118 | 0.503 |
| louvain(r=0.15,w=0.3) | 2 | 0.458 | 0.496 | 0.503 | 0.718 | 0.724 | 0.064 | 0.745 | 0.268 | -0.001 | 0.004 | 0.004 | 0.002 | 0.400 |
| louvain(r=0.2,w=0.3) | 3 | 0.392 | 0.383 | 0.386 | 0.628 | 0.536 | 0.083 | 0.544 | 0.230 | 0.001 | 0.005 | 0.005 | 0.003 | 0.400 |
| louvain(r=0.3,w=0.3) | 4 | 0.407 | 0.336 | 0.321 | 0.543 | 0.606 | 0.172 | 0.560 | 0.066 | 0.009 | 0.005 | 0.005 | 0.004 | 0.406 |
| louvain(r=0.4,w=0.3) | 6 | 0.378 | 0.328 | 0.291 | 0.490 | 0.590 | 0.160 | 0.480 | 0.066 | 0.012 | 0.005 | 0.005 | 0.004 | 0.408 |
| louvain(r=0.3,w=0) | 7 | 0.332 | 0.276 | 0.246 | 0.460 | 0.471 | 0.133 | 0.380 | 0.081 | 0.008 | 0.005 | 0.005 | 0.005 | 0.409 |
| louvain(r=0.5,w=0.3) | 8 | 0.372 | 0.305 | 0.252 | 0.494 | 0.563 | 0.156 | 0.403 | 0.047 | 0.012 | 0.017 | 0.017 | 0.019 | 0.411 |
| louvain(r=0.7,w=0.3) | 10 | 0.337 | 0.248 | 0.212 | 0.437 | 0.475 | 0.169 | 0.367 | 0.020 | 0.042 | 0.040 | 0.041 | 0.052 | 0.423 |
| louvain(r=1,w=0.3) (默认) | 14 | 0.324 | 0.217 | 0.186 | 0.415 | 0.435 | 0.177 | 0.340 | -0.140 | 0.047 | 0.058 | 0.058 | 0.080 | 0.464 |
| louvain(r=1,w=0) | 18 | 0.264 | 0.136 | 0.125 | 0.375 | 0.273 | 0.150 | 0.240 | -0.069 | 0.015 | 0.024 | 0.025 | 0.036 | 0.424 |
| louvain(r=1.4,w=0.3) | 19 | 0.293 | 0.155 | 0.141 | 0.400 | 0.311 | 0.177 | 0.269 | -0.068 | 0.026 | 0.059 | 0.060 | 0.090 | 0.470 |
| louvain(r=2,w=0.3) | 25 | 0.275 | 0.129 | 0.122 | 0.383 | 0.258 | 0.176 | 0.238 | -0.054 | 0.036 | 0.061 | 0.061 | 0.101 | 0.486 |
| louvain(r=3,w=0.3*) | 37 | 0.248 | 0.071 | 0.082 | 0.378 | 0.143 | 0.170 | 0.173 | -0.075 | 0.031 | 0.059 | 0.060 | 0.108 | 0.497 |
| louvain(r=4.5,w=0.3*) | 57 | 0.231 | 0.056 | 0.066 | 0.354 | 0.112 | 0.166 | 0.143 | -0.078 | 0.026 | 0.056 | 0.057 | 0.112 | 0.497 |
| louvain(r=6,w=0.3*) | 82 | 0.222 | 0.042 | 0.055 | 0.348 | 0.084 | 0.165 | 0.122 | -0.093 | 0.018 | 0.055 | 0.057 | 0.119 | 0.504 |
| spagcn(n=4) | 4 | 0.556 | 0.395 | 0.344 | 0.859 | 0.772 | 0.145 | 0.617 | 0.019 | 0.009 | 0.014 | 0.015 | 0.014 | 0.426 |
| spagcn(n=6) | 6 | 0.601 | 0.386 | 0.342 | 0.864 | 0.768 | 0.254 | 0.637 | 0.004 | 0.017 | 0.062 | 0.062 | 0.070 | 0.431 |
| spagcn(n=7) (默认) | 7 | 0.600 | 0.381 | 0.335 | 0.852 | 0.753 | 0.272 | 0.616 | 0.008 | 0.030 | 0.072 | 0.072 | 0.085 | 0.434 |
| spagcn(n=8) | 8 | 0.573 | 0.350 | 0.302 | 0.829 | 0.700 | 0.253 | 0.557 | -0.032 | 0.042 | 0.075 | 0.075 | 0.091 | 0.491 |
| spagcn(n=10) | 10 | 0.589 | 0.365 | 0.321 | 0.819 | 0.724 | 0.292 | 0.591 | 0.006 | 0.016 | 0.050 | 0.051 | 0.063 | 0.437 |
| spagcn(n=14) | 14 | 0.534 | 0.297 | 0.265 | 0.762 | 0.593 | 0.277 | 0.499 | -0.010 | 0.055 | 0.115 | 0.115 | 0.160 | 0.491 |
| spagcn(n=20) | 20 | 0.532 | 0.278 | 0.250 | 0.755 | 0.557 | 0.296 | 0.473 | -0.048 | 0.032 | 0.110 | 0.110 | 0.164 | 0.496 |

#### 表 2　面板与外部指标的 Spearman ρ（全部候选；bootstrap 95% CI，4000 次）

| 面板 / 成员 | ari | ami | nmi | homogeneity | majority_acc | ρ(·, K) |
|---|---|---|---|---|---|---|
| 面板:current | +0.22 [-0.05, +0.44] | +0.28 [-0.03, +0.52] | +0.27 [-0.04, +0.52] | +0.03 [-0.29, +0.33] | -0.13 [-0.45, +0.20] | -0.42 |
| 面板:candidate | -0.11 [-0.38, +0.18] | -0.08 [-0.39, +0.22] | -0.09 [-0.40, +0.22] | -0.32 [-0.60, -0.01] | -0.44 [-0.71, -0.15] | -0.70 |
| 面板:alternate | -0.14 [-0.41, +0.17] | -0.12 [-0.42, +0.19] | -0.12 [-0.42, +0.19] | -0.34 [-0.62, -0.04] | -0.47 [-0.73, -0.17] | -0.72 |
| 成员:chaos | +0.22 [-0.05, +0.46] | +0.23 [-0.07, +0.47] | +0.23 [-0.07, +0.47] | -0.02 [-0.33, +0.29] | -0.15 [-0.46, +0.18] | -0.45 |
| 成员:pas | +0.08 [-0.19, +0.33] | +0.10 [-0.20, +0.37] | +0.10 [-0.21, +0.37] | -0.15 [-0.45, +0.15] | -0.29 [-0.58, +0.03] | -0.58 |
| 成员:spatial_leiden_ami | +0.51 [+0.25, +0.71] | +0.74 [+0.54, +0.87] | +0.74 [+0.54, +0.87] | +0.61 [+0.36, +0.79] | +0.39 [+0.10, +0.61] | +0.31 |
| 成员:knn_agreement | -0.00 [-0.28, +0.28] | +0.02 [-0.29, +0.32] | +0.02 [-0.29, +0.31] | -0.22 [-0.51, +0.09] | -0.36 [-0.64, -0.06] | -0.63 |
| 成员:silhouette | -0.53 [-0.74, -0.25] | -0.68 [-0.83, -0.46] | -0.68 [-0.83, -0.46] | -0.83 [-0.92, -0.68] | -0.83 [-0.91, -0.69] | -0.86 |
| K | +0.40 [+0.12, +0.62] | +0.63 [+0.40, +0.79] | +0.63 [+0.41, +0.79] | +0.83 [+0.71, +0.91] | +0.84 [+0.72, +0.92] | +1.00 |

#### 表 3　分方法：面板与 ARI 的 Spearman ρ [95% CI]

| 方法 | n | K 范围 | 现状 | 候选面板 | 备选 | silhouette | PAS |
|---|---|---|---|---|---|---|---|
| cellcharter | 7 | 4–20 | +0.79 [-0.04, +1.00] | +0.18 [-0.76, +1.00] | +0.21 [-0.69, +1.00] | +0.11 [-0.83, +1.00] | +0.39 [-0.69, +1.00] |
| graphst | 7 | 4–20 | -0.04 [-0.88, +1.00] | +0.04 [-0.87, +0.92] | +0.04 [-0.87, +0.92] | +0.00 [-0.89, +0.75] | +0.04 [-0.87, +0.92] |
| leiden | 18 | 2–118 | -0.16 [-0.68, +0.35] | -0.31 [-0.75, +0.22] | -0.29 [-0.75, +0.25] | -0.58 [-0.84, -0.06] | -0.15 [-0.69, +0.37] |
| louvain | 14 | 2–82 | -0.61 [-0.87, -0.05] | -0.69 [-0.91, -0.18] | -0.69 [-0.91, -0.18] | -0.79 [-0.97, -0.31] | -0.60 [-0.85, -0.08] |
| spagcn | 7 | 4–20 | -0.39 [-0.96, +0.65] | -0.79 [-1.00, -0.06] | -0.79 [-1.00, -0.06] | -0.75 [-1.00, +0.07] | -0.79 [-1.00, -0.06] |

#### 表 4　各面板选中的候选

oracle（ARI 最高）：leiden(r=1,w=0.6)，K=16，ARI 0.061，homogeneity 0.170，多数投票准确率 0.514。
各方法默认参数：leiden(r=1,w=0.3) K=13 ARI 0.027；louvain(r=1,w=0.3) K=14 ARI 0.047；spagcn(n=7) K=7 ARI 0.030；graphst(n=7) K=7 ARI 0.035；cellcharter(n=7) K=7 ARI 0.048。默认 ARI 中位数 **0.035**。

| 面板 | 选中 | K | K−4 | ARI | 相对 oracle | 相对默认中位数 | AMI | NMI | homog. | 多数投票准确率 | ARI 在全部候选中的名次 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| current | leiden(r=1,w=0.9) | 57 | +53 | 0.020 | -0.042 | -0.016 | 0.084 | 0.085 | 0.175 | 0.511 | 34/53 |
| candidate | leiden(r=0.3,w=0.6) | 3 | -1 | 0.011 | -0.051 | -0.025 | 0.006 | 0.006 | 0.005 | 0.408 | 44/53 |
| alternate | leiden(r=0.3,w=0.6) | 3 | -1 | 0.011 | -0.051 | -0.025 | 0.006 | 0.006 | 0.005 | 0.408 | 44/53 |

homogeneity 的 oracle：leiden(r=1,w=0.9)，K=57，0.175。

majority_acc 的 oracle：leiden(r=1,w=0.6)，K=16，0.514。

ami 的 oracle：leiden(r=1,w=0.6)，K=16，0.116。

nmi 的 oracle：leiden(r=1,w=0.6)，K=16，0.117。

各面板前 5 名：

- current：leiden(r=1,w=0.9) K=57 分 0.916 ARI 0.020；leiden(r=0.3,w=0.9) K=12 分 0.862 ARI 0.055；leiden(r=1,w=0.6) K=16 分 0.833 ARI 0.061；leiden(r=0.3,w=0.6) K=3 分 0.710 ARI 0.011；cellcharter(n=7) K=7 分 0.708 ARI 0.048
- candidate：leiden(r=0.3,w=0.6) K=3 分 0.531 ARI 0.011；leiden(r=0.15,w=0.3) K=2 分 0.507 ARI -0.001；leiden(r=0.3,w=0.9) K=12 分 0.499 ARI 0.055；leiden(r=1,w=0.9) K=57 分 0.497 ARI 0.020；leiden(r=1,w=0.6) K=16 分 0.497 ARI 0.061
- alternate：leiden(r=0.3,w=0.6) K=3 分 0.523 ARI 0.011；leiden(r=0.15,w=0.3) K=2 分 0.511 ARI -0.001；louvain(r=0.15,w=0.3) K=2 分 0.503 ARI -0.001；leiden(r=0.3,w=0.9) K=12 分 0.493 ARI 0.055；leiden(r=1,w=0.6) K=16 分 0.486 ARI 0.061

#### 表 5　silhouette 抽样稳定性（样本 5000，种子 0/1/2；另列 20000 样本）

- 每个候选三种子 silhouette 的标准差：中位数 0.0032，最大 0.0127；silhouette 原值范围 -0.147 到 +0.270（20000 样本：-0.144 到 +0.255）；原值 > 0 的候选 20/53。
- 种子两两之间 silhouette 的 Spearman：0-1 +0.995, 0-2 +0.995, 1-2 +0.993；种子 0 对 20000 样本 +0.996。
- candidate：选中候选随种子（0/1/2/20000）：leiden(r=0.3,w=0.6) / leiden(r=0.3,w=0.6) / leiden(r=0.3,w=0.6) / leiden(r=0.3,w=0.6)；与 ARI 的 ρ：-0.111 / -0.120 / -0.096 / -0.102。
- alternate：选中候选随种子（0/1/2/20000）：leiden(r=0.3,w=0.6) / leiden(r=0.3,w=0.6) / leiden(r=0.3,w=0.6) / leiden(r=0.3,w=0.6)；与 ARI 的 ρ：-0.135 / -0.135 / -0.140 / -0.138。

#### 表 6　按 K 分箱的成员指标中位数（全部方法合并）

| K 箱 | n | CHAOS | PAS | AMI(空间) | kNN | silhouette | ARI | homog. | 多数投票准确率 |
|---|---|---|---|---|---|---|---|---|---|
| 2–4 | 11 | 0.718 | 0.724 | 0.128 | 0.613 | 0.068 | 0.009 | 0.004 | 0.403 |
| 5–7 | 8 | 0.857 | 0.722 | 0.207 | 0.581 | -0.004 | 0.033 | 0.048 | 0.420 |
| 8–10 | 11 | 0.819 | 0.587 | 0.170 | 0.477 | 0.006 | 0.033 | 0.057 | 0.423 |
| 11–15 | 6 | 0.800 | 0.557 | 0.235 | 0.477 | -0.053 | 0.040 | 0.089 | 0.452 |
| 16–25 | 10 | 0.395 | 0.328 | 0.177 | 0.282 | -0.069 | 0.033 | 0.094 | 0.468 |
| 26–60 | 4 | 0.366 | 0.162 | 0.169 | 0.183 | -0.079 | 0.029 | 0.111 | 0.497 |

#### 表 7　控制 K：同一 K 下（spagcn/graphst/cellcharter 三方法之间）哪个面板把 ARI 最高者排第一

| K | ARI 最高 | 现状选 | 候选面板选 | 备选选 |
|---|---|---|---|---|
| 4 | graphst (0.029) | cellcharter (0.025) | cellcharter (0.025) | cellcharter (0.025) |
| 6 | cellcharter (0.038) | cellcharter (0.038) | cellcharter (0.038) | cellcharter (0.038) |
| 7 | cellcharter (0.048) | cellcharter (0.048) | cellcharter (0.048) | cellcharter (0.048) |
| 8 | graphst (0.043) | cellcharter (0.037) | cellcharter (0.037) | cellcharter (0.037) |
| 10 | graphst (0.036) | cellcharter (0.032) | cellcharter (0.032) | cellcharter (0.032) |
| 14 | spagcn (0.055) | cellcharter (0.033) | cellcharter (0.033) | cellcharter (0.033) |
| 20 | graphst (0.034) | cellcharter (0.026) | cellcharter (0.026) | cellcharter (0.026) |

命中数：current 2/7，candidate 2/7，alternate 2/7。

#### 表 8　候选子集上的稳健性（面板与 ARI 的 ρ [95% CI]；配对 bootstrap 的 ρ 差）

| 子集 | n | 现状 ρ | 候选面板 ρ | 备选 ρ | 候选−现状 Δρ | 现状选中 K / ARI | 候选面板选中 K / ARI |
|---|---|---|---|---|---|---|---|
| 全部 | 53 | +0.22 [-0.05, +0.44] | -0.11 [-0.38, +0.18] | -0.14 [-0.41, +0.17] | -0.33 [-0.52, -0.16] | 57 / 0.020 | 3 / 0.011 |
| 只用 runner（去掉超出调参区间的 r≥3） | 47 | +0.24 [-0.06, +0.50] | -0.16 [-0.45, +0.16] | -0.19 [-0.48, +0.14] | -0.40 [-0.61, -0.20] | 57 / 0.020 | 3 / 0.011 |
| K ≤ 20 | 44 | +0.35 [+0.06, +0.60] | -0.10 [-0.41, +0.24] | -0.13 [-0.46, +0.21] | -0.45 [-0.68, -0.22] | 12 / 0.055 | 3 / 0.011 |
| 3 ≤ K ≤ 20 | 42 | +0.34 [+0.04, +0.60] | +0.01 [-0.30, +0.34] | -0.02 [-0.34, +0.32] | -0.33 [-0.53, -0.16] | 12 / 0.055 | 3 / 0.011 |
| 只用 spagcn/graphst/cellcharter | 21 | -0.04 [-0.49, +0.42] | -0.12 [-0.54, +0.37] | -0.12 [-0.55, +0.38] | -0.08 [-0.31, +0.17] | 7 / 0.048 | 4 / 0.025 |

### 通过标准（逐条，只报告事实）

| # | 标准 | 结果 | 是否满足 |
|---|---|---|---|
| 1 | 候选面板与 ARI 的 Spearman ρ > 0，且 95% CI 不跨 0 | ρ = **−0.11 [−0.38, +0.18]**（53 个候选）；去掉超出调参区间的候选 −0.16 [−0.45, +0.16]；限定 3≤K≤20 为 +0.01 [−0.30, +0.34]；分方法只有 cellcharter、graphst 的点估计为正（+0.18、+0.04），CI 都跨 0 | **不满足** |
| 2 | 候选面板选中的候选的 ARI ≥ 各方法默认参数 ARI 的中位数 | 选中 leiden(r=0.3, w=0.6)，K=3，ARI **0.011**；默认参数 ARI 中位数 **0.035**（leiden 0.027、louvain 0.047、spagcn 0.030、graphst 0.035、cellcharter 0.048）；oracle 0.061。选中者 ARI 在 53 个里排第 44 | **不满足** |
| 3 | 候选面板的表现优于现状面板 | 与 ARI 的 ρ：候选 −0.11 对现状 +0.22 [−0.05, +0.44]，配对 Δρ = **−0.33 [−0.52, −0.16]**（候选显著更差）；选中者 ARI：候选 0.011 对现状 0.020（现状选 leiden(r=1, w=0.9)，K=57）；K 偏差：候选 **−1** 对现状 **+53**（只有这一项候选更好）；同 K 下三个模型方法之间挑 ARI 最高者：两者都 2/7 | **不满足**（K 偏差一项除外） |

备选面板（kNN 1/3 + PAS 1/6 + silhouette 0.5）与候选面板几乎一样：ρ = −0.14 [−0.41, +0.17]，选中同一个 K=3 候选。

### 成员指标在真实数据上的表现

- **silhouette：测得稳，但方向错。** 抽样稳定性没有问题：三个种子之间每个候选的标准差中位数 0.003（最大 0.013），种子之间及与 20000 抽样的秩相关 ≥ 0.993，两个面板选中的候选在 4 种抽样下都不变。问题在于数值本身：原值在 −0.147 到 +0.270 之间，**只有 20/53 个候选大于 0**（裁到 [0,1] 后其余全是 0，候选面板在这些候选上退化为 0.5·PAS）；与 K 的 ρ = **−0.86**，与 ARI 的 ρ = **−0.53 [−0.74, −0.25]**，与 homogeneity −0.83。最高的 silhouette（0.26–0.27）属于 K=2–3 的 leiden/louvain 划分，它们只是把一个富含 Ttr 的小群（Ependymal、Endothelial_Tip 占主要，脉络丛样；1797 或 2584 个 bead）从其余切开，ARI ≈ 0。也就是说，在每 bead 76 个 UMI 的 `X_pca` 上，silhouette 奖励"把唯一一个表达上极端的小群切出去"的粗划分，这与合成研究里"信号 1.0 时 silhouette 自己偏向 K=2"的现象一致。担忧里"silhouette 噪声很大"不成立，"silhouette 在低 UMI 数据上失效"成立，失效方式是系统性偏向小 K，不是随机噪声。循环性问题在这里无从检验：真值本身在 `X_pca` 上 silhouette 为 −0.010。
- **PAS：偏向小 K，但主要奖励空间平滑。** ρ(PAS, K) = −0.58，ρ(PAS, ARI) = +0.08 [−0.19, +0.33]。它对"空间平滑"的奖励强于对 K 的惩罚：leiden `spatial_weight` 0.6/0.9 的划分无论 K=3 还是 57，PAS 都在 0.99 以上；`spatial_weight`=0 的纯表达划分 PAS 只有 0.25–0.47。所以在真实方法输出上，PAS 的"偏小 K"被"偏空间平滑"压过，并不能单独约束 K。
- **spatial-Leiden AMI** 是与 ARI 相关最强的成员：+0.51 [+0.25, +0.71]（与 AMI/NMI +0.74）。但它也与 K 正相关（+0.31），而这份真值本身奖励较大 K，这一相关不能直接读成"AMI 衡量区域质量"。
- **CHAOS**：+0.22 [−0.05, +0.46]，与现状面板相当；**kNN agreement**：−0.00。
- 按 K 分箱（表 6）：PAS、kNN、silhouette 的中位数随 K 单调下降；ARI 在 K=11–15 箱最高（0.040），homogeneity 与多数投票准确率随 K 单调上升。

### 对过切更宽容的指标（敏感性分析）

homogeneity 与多数投票准确率比 ARI 更偏向大 K（与 K 的 ρ 分别 +0.83、+0.84）。换成它们，候选面板更差：与 homogeneity 的 ρ −0.32 [−0.60, −0.01]，与多数投票准确率 −0.44 [−0.71, −0.15]，两者 CI 都在 0 以下；现状面板分别为 +0.03、−0.13。候选面板选中的 K=3 划分多数投票准确率 0.408，几乎等于"全判为最大类"的基线 0.400；现状选中的 K=57 为 0.511，接近 oracle 0.514。**结论方向不变，且更不利于候选面板**：原本担心 ARI 惩罚过切会冤枉偏大 K 的现状面板，实际情况相反，这份真值（逐 bead 细胞类型）本身就在奖励更细的划分。

### 结论

1. 按 owner 给定的三条标准，**候选面板在这份数据上一条都没有通过**；备选面板同样没有通过。现状面板也谈不上"有效"（ρ +0.22，CI 跨 0；选中 K=57，ARI 0.020，低于默认中位数），但在相关性上显著好于候选面板（配对 Δρ −0.33 [−0.52, −0.16]）。
2. 失败有两个来源，这份数据无法把它们分开：
   - **候选面板自身的问题（数据可以支持）**：silhouette 在低 UMI 的 `X_pca` 上几乎全 ≤ 0，并稳定地偏向把一个极端小群切出去的 K=2–3；PAS 在真实方法输出上主要奖励空间平滑，不能单独约束 K。二者都不随 ARI 变化。
   - **评估真值的问题**：纳入的 4 类是逐 bead 的神经元类型调用，在空间上大面积交错（10-NN 同类比例 0.475，随机 0.313），在表达嵌入里也不可分；用真值本身平滑出来的空间划分 ARI 也只有 0.14–0.22；53 个候选的 ARI 全在 0.06 以下，并且 ARI 随 K 上升。在这样的真值上，任何偏向"少而空间连续的区域"的面板都会吃亏，任何偏大 K 的面板都会占便宜。
3. 因此这次验证**既没有证实候选面板，也不足以证明现状面板正确**。它确实给出了一条与真值无关、可复用的发现：在 Slide-seqV2 这类低 UMI 数据上，按合成研究定义的 silhouette（原值裁到 [0,1]）多数为 0，且偏向 K=2–3；合成研究的推荐依赖"表达信号足够强"这一前提，在这里不成立。

### 局限

- **开发期数据，结论待正式数据集验证。** 真值是细胞类型调用而不是人工区域注释；owner 批准的映射只保留了 4 类神经元，它们在这张切片上不构成空间分离的区域。带层级区域注释、UMI 更高的数据（例如 DLPFC Visium 切片）才能真正回答"面板能否选出区域"。
- 外部指标的动态范围极窄（ARI −0.006 到 0.061），相关系数的 CI 都很宽；分方法的 n 只有 7–18。
- 候选只来自 5 个方法和它们的主参数；leiden/louvain 的 resolution ≥ 3 超出调参区间、未经 runner 运行；louvain 的 `spatial_weight` 在该脚本里没有作用，实际去重后 louvain 只有 14 个候选。
- silhouette 只在预处理默认的 30 维 `X_pca` 上算，没有试 HVG 数、PC 数或其他嵌入；它在别的嵌入上可能表现不同。
- 本研究没有评估 PAS / silhouette 权重以外的新方案，也没有据此调参（避免在同一份开发数据上既调又验）。

## DLPFC 快速验证（151673/151674，2026-09-25）

owner 批准的 G2 第一步：先在本地两张 DLPFC 切片上快速检验内部指标面板，再决定是否扩大到全部 12 张 DLPFC 切片加 CosMx 人肝数据。**生产代码未改动**（`omicsclaw/` 下无修改），面板仍是 `spatial_domains/2`。分析、统计与通过标准沿用上一节 `real_data.py`，只换了数据和真值。本节只报告事实与逐条通过标准，裁定归 owner。

### 方法

- **数据**：`/workspace/algorithm/zhouwg_project/data_external/DLPFC/{151673,151674}.h5ad`，只读。`X` 是**原始整数计数**（float32 存储，逐值核实全为非负整数；每 spot UMI 中位数 4120 / 5334），没有 counts layer，所以直接用 `X`。真值 `obs['sce.layer_guess']`：Layer1–6 加 WM，K\*=7；NaN 的 spot（28 / 38 个）参与聚类，不参与评估。
- **预处理**（每张切片独立一次，与冒烟测试相同的用法）：`X` 取原始计数，`obs` 只留 `in_tissue`、`array_row`、`array_col`（不含任何注释列），保留 `obsm['spatial']` 与 `uns['spatial']`（图像元数据）；`spatial-preprocess --data-type visium --species human`，其余参数用默认值；预处理后再把 `obs` 剥到这三列。真值只由打分阶段从原文件按 spot ID 读取，不进入任何候选生成步骤。
  - **默认 `max_mt_pct=20` 删掉了不少 spot**：151673 从 3639 到 **2898**（−20%），151674 从 3673 到 **3236**（−12%）。人脑皮层的线粒体比例本来就在 15–20%，被删的 spot 集中在上层：151673 的 Layer1/2/3/4 只保留 63%/76%/60%/75%，WM 保留 99%。主分析按"参数固定、用默认值"的要求保留这一步；另做了一个**敏感性分析**（`--max-mt-pct 100`，不删 spot），结论见下文。
- **候选生成**（每张切片 56 个试验，两张切片全部 ok）：
  - 经 `omicsclaw.ensemble`（`open_ensemble` + `EnsembleRunner.fan_out`，`data_type=visium`）跑 50 个：leiden、louvain 的 `resolution` ∈ {0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.7, 1.0, 1.4, 2.0}（`spatial_weight` 取默认 0.3），另在 resolution 0.3、1.0 上加 `spatial_weight` ∈ {0, 0.6, 0.9}；spagcn、graphst、cellcharter 的 `n_domains` ∈ {3, 5, 7, 9, 12, 16}（7 是各脚本的默认值）。runner 自动检测到 4 张 GPU，批墙钟 173 s（151673）和 210 s（151674）。
  - leiden/louvain 没有 `n_domains` 参数，用 resolution 网格覆盖 K；resolution 2.0 时只有 13 个簇，为覆盖到约 30，另用同一 skill 脚本**直接运行** resolution ∈ {3, 4.5, 6}（不经 runner，因为超出 `tuning.yaml` 的区间 [0.1, 2.0]），表中以 `*` 标记。
  - louvain 的 `spatial_weight` 仍然没有作用（0.6、0.9 与 0.3 的划分逐 spot 相同），每张切片去掉 4 个重复后分析 **52 个候选**，K 的范围是 2–70（151673）和 2–67（151674）。stagate、banksy 缺包，未跑。
- **打分**：现状面板直接调用生产 `compute_panel`（CHAOS 0.4 / PAS 0.2 / spatial-Leiden AMI 0.4）；候选面板 = 0.5·clip(PAS 校正值) + 0.5·clip(silhouette 原值)；备选 = kNN 1/3 + PAS 1/6 + silhouette 0.5。spot 数少于 5000，所以 silhouette 用**全部** spot 在 `X_pca`（30 维）上精确计算，没有抽样误差。另算两个有原理支撑、sklearn 已实现的表达紧致度指标：Calinski-Harabasz（CH）和 Davies-Bouldin（取负号，越大越好），只用于第 5 步和对照。
- **外部指标**：ARI、AMI、NMI，只在有 `layer_guess` 的 spot 上算（2870 / 3198 个）。
- **统计与通过标准**：与上一节完全相同。Spearman ρ，按候选重抽 bootstrap 4000 次取 95% 百分位区间；面板之间用配对 bootstrap Δρ。"默认参数"指 leiden/louvain 的 r=1.0、w=0.3，以及三种模型方法的 n=7。
- 复现：`PYTHONPATH=<repo> /opt/conda/envs/OmicsClaw/bin/python docs/plans/0056-panel-bias-study/dlpfc.py {prepare,generate,score,ceiling} --slices 151673 151674`，然后运行 `… analyse --slices 151673 151674`（中间文件在 `/tmp/0056_dlpfc`；敏感性分析加 `--root /tmp/0056_dlpfc_nomt --max-mt-pct 100`）。

### 健全性检查：这份真值可以恢复，预处理没有问题

| 量 | 151673 | 151674 | 说明 |
|---|---|---|---|
| oracle ARI（52 个候选中最高） | **0.557**（louvain 默认，K=6） | **0.506**（louvain r=0.7，K=6） | 落在文献常见的 0.4–0.6 之内 |
| 默认参数 ARI 中位数 | 0.396 | 0.410 | leiden 0.489/0.413，louvain 0.557/0.423，cellcharter 0.396/0.410，spagcn 0.317/0.251，graphst 0.253/0.241 |
| 真值的空间 10-NN 同类比例 | 0.868（随机 0.179） | 0.873（随机 0.170） | 层是空间连续的区域（Slide-seqV2 那份真值只有 0.475 对 0.313） |
| 真值在 `X_pca` 上的 silhouette | **0.060** | **0.052** | 正值但很小：相邻层在表达上是渐变的 |
| 把真值本身当候选打分（只用有标注的 spot） | 现状 0.761，候选 0.511 | 现状 0.771，候选 0.512 | 两个面板都给自己的选中者打出了**更高**的分（见下） |

oracle 在文献范围内，所以没有必要回头排查预处理；上一节 Slide-seqV2 的"真值不可恢复"问题在这里不存在，外部指标的动态范围也足够（ARI 0.10–0.56）。graphst 的 ARI（0.24–0.25）低于文献里 GraphST 在 151673 上的水平，可能与 skill 的默认设置（100 epoch、不做 refine）有关；本研究没有追查，它不影响面板比较。

去掉线粒体过滤后（敏感性分析，spot 一个不删）：oracle 0.537 / 0.502，默认中位数 0.463 / 0.341；候选面板与 ARI 的 ρ 为 +0.23 / +0.22，现状为 +0.23 / +0.34；候选面板仍选 K=2（ARI 0.132 / 0.132），现状面板仍选 leiden(r=1, w=0.9)（K=16/19，ARI 0.208 / 0.241）。**三条通过标准的判定与主分析完全相同**，结论不依赖这一步过滤。

### 通过标准（逐条，每张切片分别报告）

| # | 标准 | 151673 | 151674 | 是否满足 |
|---|---|---|---|---|
| 1 | 候选面板与 ARI 的 Spearman ρ > 0，且 95% CI 不跨 0 | ρ = **+0.27 [−0.06, +0.58]** | ρ = **+0.23 [−0.11, +0.56]** | **两张都不满足**（点估计为正，CI 跨 0） |
| 2 | 候选面板选中者的 ARI ≥ 默认参数 ARI 的中位数 | 选中 leiden(r=0.1)，**K=2**，ARI **0.152**；中位数 0.396；oracle 0.557；在 52 个候选中排第 49 | 选中 leiden(r=0.1)，**K=2**，ARI **0.147**；中位数 0.410；oracle 0.506；排第 46 | **两张都不满足** |
| 3 | 候选面板优于现状面板 | Δρ = +0.08 [−0.22, +0.39]；选中者 ARI 0.152 对现状 0.189 | Δρ = +0.12 [−0.36, +0.59]；选中者 ARI 0.147 对现状 0.257 | **两张都不满足**（ρ 的点估计略高，差异不显著；选中者的 ARI 更低） |

备选面板与候选面板几乎相同：ρ 为 +0.26 [−0.07, +0.56] / +0.23 [−0.11, +0.57]，选中的是同一个 K=2 候选，三条标准同样都不满足。现状面板本身也不合格：ρ 为 +0.19 [−0.10, +0.45] / +0.10 [−0.19, +0.40]，选中者的 ARI 为 0.189 / 0.257，低于默认参数的中位数。

**K 相对 7 层（含 WM）的偏差**：

| 面板 | 151673 选中 | 151674 选中 |
|---|---|---|
| 现状 | leiden(r=1, w=0.9)，K=21，**+14** | leiden(r=1, w=0.9)，K=17，**+10** |
| 候选 | leiden(r=0.1, w=0.3)，K=2，**−5** | leiden(r=0.1, w=0.3)，K=2，**−5** |
| 备选 | 同候选，**−5** | 同候选，**−5** |
| 只用 PAS | leiden(r=0.3, w=0.9)，K=8，+1，ARI 0.332 | leiden(r=0.3, w=0.9)，K=7，0，ARI 0.373 |
| oracle | K=6，−1 | K=6，−1 |

合成研究的方向在真实数据上再次出现：现状面板过切，候选面板欠切。区别在于这里的欠切不是 K*−1，而是直接退到 K=2。

### 两个面板分别在哪里失败

- **候选面板：silhouette 把"白质对灰质"的二分当成最好的划分。** 在两张切片上，silhouette（以及 CH、DB 这两个表达紧致度指标）的 argmax 都是 K=2 的 leiden/louvain 划分，silhouette 约 0.39，而真值的 silhouette 只有 0.05–0.06。K=2 划分基本就是 WM 对其余各层，PAS 也接近 0.93，所以候选面板的前 4 名全是 K=2。silhouette 与 K 的 ρ = −0.91，与 ARI 的 ρ 只有 +0.26 / +0.28（CI 跨 0）。这与合成研究的局限一致：相邻层在表达上是渐变的，"信号弱"时 silhouette 偏向 K=2。它和 Slide-seqV2 的失败是同一种方式（系统性偏向最粗的、能把一个表达极端的组织块切出去的划分），而且这次的真值是可信的。
- **现状面板：奖励强空间平滑的过切划分。** 两张切片上现状面板的 argmax 都是 leiden(r=1, w=0.9)，这是一个几乎只按空间图切分出来的划分：CHAOS 0.999，spatial-Leiden AMI 0.78，但 ARI 只有 0.19 / 0.26。CHAOS 和 AMI 单独使用时也选它。这类"空间上很整齐、层结构不对"的候选，正是纯空间指标无法识别的对抗样本（合成研究结论 4）。
- **两个面板都把真值排在自己的选中者之后**：把真值本身当候选时，现状面板给 0.761 / 0.771，低于它选中的 0.908 / 0.890；候选面板给 0.511 / 0.512，低于它选中的 0.664 / 0.655。所以这不是候选集里缺好候选，而是两个面板的最优点本身就不在真值附近。

### 各成员单独与 ARI 的相关（ρ [95% CI]）

| 成员 | 151673 | 151674 | ρ(·, K)（两张） | 单独选中者 K / ARI（两张） |
|---|---|---|---|---|
| PAS | +0.28 [−0.02, +0.56] | **+0.37 [+0.10, +0.61]** | −0.67 / −0.70 | 8 / 0.332；7 / 0.373 |
| silhouette | +0.26 [−0.09, +0.58] | +0.28 [−0.08, +0.63] | −0.91 / −0.91 | 2 / 0.149；2 / 0.141 |
| kNN agreement | +0.22 [−0.11, +0.53] | +0.25 [−0.06, +0.56] | −0.74 / −0.75 | 8 / 0.332；7 / 0.373 |
| spatial-Leiden AMI | +0.21 [−0.05, +0.44] | +0.12 [−0.15, +0.40] | +0.72 / +0.78 | 21 / 0.189；17 / 0.257 |
| Calinski-Harabasz | +0.21 [−0.13, +0.54] | +0.22 [−0.13, +0.56] | −0.98 / −0.99 | 2 / 0.149；2 / 0.141 |
| −Davies-Bouldin | +0.20 [−0.13, +0.50] | +0.03 [−0.28, +0.34] | −0.86 / −0.56 | 2 / 0.149；2 / 0.140 |
| CHAOS | −0.07 [−0.35, +0.22] | −0.20 [−0.45, +0.13] | −0.06 / +0.16 | 21 / 0.189；17 / 0.257 |

只有 PAS 在一张切片上 CI 不跨 0。spatial-Leiden AMI 与 AMI/NMI 的相关是最强的（+0.48 / +0.39，CI 不跨 0），但与 ARI 的相关弱；它的相关来自整体排序，argmax 仍落在过度平滑的 K=17–21 上。

### 子集与控制 K 的结果

- **去掉极端 K（3 ≤ K ≤ 20）后，候选面板的相关显著为正，并且显著优于现状**：151673 为 ρ +0.41 [+0.10, +0.66]，Δρ +0.40 [+0.07, +0.72]；151674 为 +0.56 [+0.29, +0.75]，Δρ +0.95 [+0.62, +1.20]。但它的选中者变成 K=3（ARI 0.307 / 0.329），仍低于默认中位数。也就是说，候选面板在整体排序上有一些信息，但会把 argmax 推到它允许的最小 K 上。
- **只看 spagcn/graphst/cellcharter（固定 n_domains）**：现状 +0.88 [+0.66, +0.96] / +0.69 [+0.26, +0.90]，候选 +0.51 [+0.00, +0.87] / +0.80 [+0.43, +0.97]。三个方法的质量差距很大（cellcharter 在每个 n 上都是 ARI 最高），两个面板都能把 cellcharter 排在前面：同一个 n 下挑 ARI 最高的方法，现状面板命中 6/6 和 5/6，候选面板两张都是 6/6。面板**区分方法**的能力是有的，失败集中在**选 K**，以及识别"空间过度平滑"这两件事上。

### 第 5 步：成员组合的留一切片检验（只报告，不定案）

两个面板都没通过，所以在现有 5 个成员加 Davies-Bouldin 中搜索组合：1–3 个成员，权重在 0.1 网格上、和为 1，共 861 个组合。在一张切片上选权重，在另一张上检验。训练目标用两种：(a) 与 ARI 的 Spearman ρ（标准 1 的口径）；(b) 训练切片上 argmax 候选的 ARI（标准 2 的口径）。

| 目标 | 训练 → 检验 | 训练上选出的组合 | 检验 ρ [95% CI] | 检验选中 K / ARI | 检验默认中位数 |
|---|---|---|---|---|---|
| (a) ρ | 151673 → 151674 | 0.1·PAS + 0.8·AMI + 0.1·kNN（训练 ρ +0.52） | **+0.39 [+0.14, +0.62]** | 17 / 0.257 | 0.410 |
| (a) ρ | 151674 → 151673 | 0.5·PAS + 0.5·AMI（训练 ρ +0.56） | **+0.45 [+0.20, +0.65]** | 21 / 0.189 | 0.396 |
| (b) 选中者 ARI | 151673 → 151674 | 0.8·PAS + 0.1·kNN + 0.1·DB | +0.23 [−0.09, +0.55] | 2 / 0.147 | 0.410 |
| (b) 选中者 ARI | 151674 → 151673 | 0.9·PAS + 0.1·silhouette | +0.25 [−0.07, +0.55] | 4 / **0.471** | 0.396 |

- 按 ρ 选出的组合都是"PAS + spatial-Leiden AMI"（也就是现状面板去掉 CHAOS）。它们在留出切片上**满足标准 1**（ρ 约 +0.4，CI 不跨 0），但 argmax 仍是 leiden(w=0.9) 这个过度平滑的划分，**不满足标准 2**。两张切片合起来看，ρ 较小值最高的 10 个组合全部是 PAS 与 AMI 为主的组合，它们的 argmax 都落在这个划分上。
- 按选中者 ARI 选出的组合都以 PAS 为主（0.8–0.9），但留出结果不稳定：一个方向选中 K=4、ARI 0.471（高于默认中位数），另一个方向退回 K=2、ARI 0.147；两个方向的 ρ 都跨 0。
- 敏感性分析（不删 spot）得到同样的模式：按 ρ 选出的仍是 0.2·PAS + 0.8·AMI 和 0.5·PAS + 0.5·AMI（留出 ρ +0.58 / +0.51，选中者 K=19 / 16，ARI 0.241 / 0.208）。
- 解读：**没有任何现有成员的线性组合在两个方向上同时满足标准 1 和标准 2。**"整体排序"和"argmax 选得好"在这里是两件不同的事。现有成员里对排序最有用的是 PAS 与 AMI，但 leiden(w=0.9) 这类空间过度平滑的候选会拿到最高分；对选 K 最有用的是 PAS 与表达紧致度，但它们会退到最粗的划分。两个切片、每张 52 个候选，也不足以稳定地估计 3 个权重。

### 结果明细

以下由 `dlpfc.py analyse --slices 151673 151674` 生成（主分析，默认预处理）。

#### 切片 151673

试验 56 个，56 个 ok；runner fan-out 墙钟 173 s，GPU ['0', '1', '2', '3']。K=1 排除：无；重复划分 4 个（louvain(r=0.3,w=0.6) = louvain(r=0.3,w=0.3)；louvain(r=0.3,w=0.9) = louvain(r=0.3,w=0.3)；louvain(r=1,w=0.6) = louvain(r=1,w=0.3)；louvain(r=1,w=0.9) = louvain(r=1,w=0.3)）。分析 52 个候选，K 从 2 到 70。


<details><summary>全部候选（151673）（展开）</summary>


| 候选 | K | 现状 | 候选面板 | 备选 | CHAOS | PAS | AMI(空间) | kNN | sil | CH | −DB | ARI | AMI | NMI |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cellcharter(n=3) | 3 | 0.712 | 0.571 | 0.551 | 0.978 | 0.957 | 0.324 | 0.896 | 0.185 | 1081 | -1.961 | 0.307 | 0.486 | 0.486 |
| cellcharter(n=5) | 5 | 0.737 | 0.525 | 0.495 | 0.974 | 0.959 | 0.389 | 0.870 | 0.091 | 674 | -2.379 | 0.452 | 0.588 | 0.589 |
| cellcharter(n=7) (默认) | 7 | 0.758 | 0.504 | 0.468 | 0.973 | 0.949 | 0.448 | 0.842 | 0.059 | 492 | -2.880 | 0.396 | 0.597 | 0.598 |
| cellcharter(n=9) | 9 | 0.740 | 0.485 | 0.445 | 0.933 | 0.924 | 0.454 | 0.802 | 0.047 | 392 | -3.068 | 0.378 | 0.602 | 0.604 |
| cellcharter(n=12) | 12 | 0.737 | 0.462 | 0.416 | 0.937 | 0.885 | 0.462 | 0.747 | 0.039 | 307 | -3.262 | 0.420 | 0.632 | 0.634 |
| cellcharter(n=16) | 16 | 0.758 | 0.452 | 0.404 | 0.959 | 0.873 | 0.500 | 0.731 | 0.031 | 237 | -3.330 | 0.376 | 0.608 | 0.610 |
| graphst(n=3) | 3 | 0.686 | 0.523 | 0.486 | 0.917 | 0.905 | 0.345 | 0.793 | 0.142 | 1023 | -2.148 | 0.233 | 0.353 | 0.354 |
| graphst(n=5) | 5 | 0.692 | 0.472 | 0.423 | 0.939 | 0.880 | 0.351 | 0.734 | 0.064 | 623 | -2.908 | 0.284 | 0.402 | 0.404 |
| graphst(n=7) (默认) | 7 | 0.645 | 0.370 | 0.324 | 0.904 | 0.709 | 0.355 | 0.572 | 0.031 | 436 | -4.589 | 0.253 | 0.375 | 0.377 |
| graphst(n=9) | 9 | 0.628 | 0.331 | 0.280 | 0.888 | 0.659 | 0.353 | 0.507 | 0.003 | 342 | -5.495 | 0.208 | 0.372 | 0.374 |
| graphst(n=12) | 12 | 0.573 | 0.236 | 0.218 | 0.854 | 0.472 | 0.343 | 0.418 | -0.005 | 251 | -7.637 | 0.202 | 0.349 | 0.352 |
| graphst(n=16) | 16 | 0.567 | 0.199 | 0.190 | 0.871 | 0.398 | 0.348 | 0.371 | -0.013 | 194 | -7.222 | 0.167 | 0.354 | 0.359 |
| leiden(r=0.1,w=0.3) | 2 | 0.691 | 0.664 | 0.657 | 0.956 | 0.940 | 0.302 | 0.920 | 0.388 | 1700 | -1.088 | 0.152 | 0.352 | 0.353 |
| leiden(r=0.15,w=0.3) | 2 | 0.662 | 0.650 | 0.643 | 0.896 | 0.930 | 0.295 | 0.909 | 0.370 | 1639 | -1.145 | 0.152 | 0.347 | 0.348 |
| leiden(r=0.2,w=0.3) | 3 | 0.631 | 0.529 | 0.502 | 0.800 | 0.925 | 0.316 | 0.846 | 0.132 | 997 | -2.120 | 0.371 | 0.515 | 0.516 |
| leiden(r=0.3,w=0.3) | 3 | 0.583 | 0.507 | 0.476 | 0.700 | 0.918 | 0.298 | 0.825 | 0.096 | 764 | -2.353 | 0.393 | 0.509 | 0.509 |
| leiden(r=0.4,w=0.3) | 4 | 0.650 | 0.513 | 0.483 | 0.818 | 0.902 | 0.355 | 0.810 | 0.125 | 800 | -2.229 | 0.464 | 0.564 | 0.565 |
| leiden(r=0.5,w=0.3) | 4 | 0.617 | 0.513 | 0.475 | 0.744 | 0.902 | 0.348 | 0.789 | 0.123 | 864 | -2.309 | 0.479 | 0.561 | 0.562 |
| leiden(r=0.7,w=0.3) | 4 | 0.642 | 0.510 | 0.477 | 0.798 | 0.900 | 0.357 | 0.801 | 0.121 | 801 | -2.299 | 0.473 | 0.570 | 0.571 |
| leiden(r=0.3,w=0) | 4 | 0.551 | 0.472 | 0.426 | 0.641 | 0.819 | 0.326 | 0.682 | 0.125 | 828 | -2.273 | 0.398 | 0.483 | 0.484 |
| leiden(r=0.3,w=0.6) | 4 | 0.744 | 0.538 | 0.514 | 0.994 | 0.984 | 0.374 | 0.913 | 0.091 | 650 | -2.571 | 0.471 | 0.619 | 0.620 |
| leiden(r=1,w=0.3) (默认) | 6 | 0.641 | 0.482 | 0.441 | 0.815 | 0.860 | 0.357 | 0.737 | 0.104 | 549 | -2.654 | 0.489 | 0.598 | 0.599 |
| leiden(r=0.3,w=0.9) | 8 | 0.857 | 0.510 | 0.492 | 0.999 | 0.990 | 0.649 | 0.937 | 0.029 | 300 | -3.698 | 0.332 | 0.464 | 0.466 |
| leiden(r=1,w=0) | 8 | 0.568 | 0.395 | 0.344 | 0.724 | 0.711 | 0.340 | 0.561 | 0.078 | 458 | -2.461 | 0.360 | 0.509 | 0.511 |
| leiden(r=1,w=0.6) | 9 | 0.810 | 0.514 | 0.485 | 0.988 | 0.977 | 0.548 | 0.890 | 0.051 | 335 | -3.382 | 0.468 | 0.596 | 0.598 |
| leiden(r=1.4,w=0.3) | 10 | 0.642 | 0.425 | 0.379 | 0.818 | 0.782 | 0.396 | 0.645 | 0.068 | 373 | -2.842 | 0.408 | 0.559 | 0.561 |
| leiden(r=2,w=0.3) | 13 | 0.616 | 0.381 | 0.340 | 0.790 | 0.700 | 0.399 | 0.576 | 0.062 | 294 | -2.941 | 0.357 | 0.532 | 0.535 |
| leiden(r=1,w=0.9) | 21 | 0.908 | 0.491 | 0.464 | 0.999 | 0.982 | 0.778 | 0.901 | -0.043 | 129 | -6.905 | 0.189 | 0.438 | 0.443 |
| leiden(r=3,w=0.3*) | 25 | 0.554 | 0.277 | 0.251 | 0.732 | 0.522 | 0.392 | 0.442 | 0.032 | 165 | -3.262 | 0.282 | 0.495 | 0.500 |
| leiden(r=4.5,w=0.3*) | 44 | 0.494 | 0.169 | 0.168 | 0.701 | 0.330 | 0.369 | 0.328 | 0.008 | 101 | -3.496 | 0.161 | 0.437 | 0.447 |
| leiden(r=6,w=0.3*) | 70 | 0.461 | 0.111 | 0.122 | 0.696 | 0.218 | 0.348 | 0.252 | 0.003 | 68 | -3.317 | 0.105 | 0.404 | 0.420 |
| louvain(r=0.1,w=0.3) | 2 | 0.687 | 0.658 | 0.654 | 0.952 | 0.927 | 0.303 | 0.914 | 0.389 | 1705 | -1.084 | 0.152 | 0.353 | 0.353 |
| louvain(r=0.15,w=0.3) | 2 | 0.608 | 0.662 | 0.657 | 0.754 | 0.925 | 0.304 | 0.910 | 0.398 | 1709 | -1.052 | 0.149 | 0.348 | 0.349 |
| louvain(r=0.2,w=0.3) | 3 | 0.603 | 0.531 | 0.507 | 0.728 | 0.918 | 0.322 | 0.847 | 0.144 | 1075 | -2.025 | 0.386 | 0.529 | 0.530 |
| louvain(r=0.3,w=0.3) | 3 | 0.607 | 0.528 | 0.504 | 0.738 | 0.911 | 0.324 | 0.838 | 0.145 | 1080 | -1.993 | 0.376 | 0.519 | 0.520 |
| louvain(r=0.3,w=0) | 3 | 0.573 | 0.490 | 0.462 | 0.711 | 0.834 | 0.305 | 0.752 | 0.145 | 1045 | -1.939 | 0.262 | 0.437 | 0.438 |
| louvain(r=0.4,w=0.3) | 4 | 0.604 | 0.512 | 0.473 | 0.715 | 0.898 | 0.345 | 0.780 | 0.126 | 879 | -2.286 | 0.485 | 0.564 | 0.564 |
| louvain(r=0.5,w=0.3) | 4 | 0.601 | 0.511 | 0.472 | 0.708 | 0.896 | 0.345 | 0.778 | 0.127 | 887 | -2.283 | 0.487 | 0.564 | 0.564 |
| louvain(r=0.7,w=0.3) | 4 | 0.610 | 0.510 | 0.471 | 0.734 | 0.893 | 0.345 | 0.777 | 0.126 | 889 | -2.294 | 0.486 | 0.561 | 0.562 |
| louvain(r=1,w=0.3) (默认) | 6 | 0.634 | 0.480 | 0.439 | 0.783 | 0.854 | 0.376 | 0.731 | 0.106 | 576 | -2.506 | 0.557 | 0.612 | 0.614 |
| louvain(r=1,w=0) | 8 | 0.555 | 0.375 | 0.326 | 0.716 | 0.669 | 0.338 | 0.520 | 0.082 | 486 | -2.647 | 0.350 | 0.503 | 0.505 |
| louvain(r=1.4,w=0.3) | 9 | 0.611 | 0.416 | 0.373 | 0.763 | 0.762 | 0.384 | 0.633 | 0.070 | 426 | -2.754 | 0.449 | 0.574 | 0.576 |
| louvain(r=2,w=0.3) | 13 | 0.610 | 0.374 | 0.335 | 0.799 | 0.679 | 0.387 | 0.563 | 0.070 | 304 | -2.674 | 0.385 | 0.544 | 0.547 |
| louvain(r=3,w=0.3*) | 21 | 0.559 | 0.279 | 0.254 | 0.760 | 0.512 | 0.382 | 0.437 | 0.047 | 203 | -2.977 | 0.275 | 0.502 | 0.507 |
| louvain(r=4.5,w=0.3*) | 35 | 0.516 | 0.193 | 0.191 | 0.734 | 0.357 | 0.377 | 0.350 | 0.029 | 132 | -3.104 | 0.192 | 0.457 | 0.465 |
| louvain(r=6,w=0.3*) | 57 | 0.492 | 0.142 | 0.150 | 0.732 | 0.268 | 0.366 | 0.290 | 0.016 | 85 | -3.168 | 0.122 | 0.421 | 0.434 |
| spagcn(n=3) | 3 | 0.697 | 0.535 | 0.502 | 0.959 | 0.915 | 0.325 | 0.816 | 0.155 | 1080 | -2.108 | 0.292 | 0.411 | 0.412 |
| spagcn(n=5) | 5 | 0.707 | 0.475 | 0.432 | 0.968 | 0.880 | 0.359 | 0.750 | 0.071 | 659 | -2.819 | 0.277 | 0.422 | 0.424 |
| spagcn(n=7) (默认) | 7 | 0.696 | 0.441 | 0.398 | 0.939 | 0.824 | 0.389 | 0.695 | 0.059 | 497 | -3.277 | 0.317 | 0.473 | 0.474 |
| spagcn(n=9) | 9 | 0.683 | 0.416 | 0.372 | 0.898 | 0.791 | 0.414 | 0.659 | 0.040 | 385 | -3.401 | 0.280 | 0.462 | 0.464 |
| spagcn(n=12) | 12 | 0.719 | 0.427 | 0.383 | 0.932 | 0.821 | 0.455 | 0.689 | 0.033 | 291 | -3.480 | 0.308 | 0.521 | 0.524 |
| spagcn(n=16) | 16 | 0.686 | 0.389 | 0.345 | 0.890 | 0.764 | 0.443 | 0.634 | 0.013 | 228 | -3.520 | 0.311 | 0.546 | 0.549 |

</details>

面板、成员与外部指标的 Spearman ρ（151673；bootstrap 95% CI，4000 次）：

| 面板 / 成员 | ARI | AMI | NMI | ρ(·, K) |
|---|---|---|---|---|
| 面板:current | +0.19 [-0.10, +0.45] | +0.27 [+0.01, +0.51] | +0.25 [-0.01, +0.50] | -0.18 |
| 面板:candidate | +0.27 [-0.06, +0.58] | +0.11 [-0.22, +0.43] | +0.10 [-0.22, +0.42] | -0.87 |
| 面板:alternate | +0.26 [-0.07, +0.56] | +0.10 [-0.22, +0.42] | +0.09 [-0.23, +0.41] | -0.86 |
| 成员:chaos | -0.07 [-0.35, +0.22] | +0.03 [-0.24, +0.29] | +0.02 [-0.26, +0.28] | -0.06 |
| 成员:pas | +0.28 [-0.02, +0.56] | +0.20 [-0.09, +0.48] | +0.19 [-0.10, +0.46] | -0.67 |
| 成员:spatial_leiden_ami | +0.21 [-0.05, +0.44] | +0.48 [+0.24, +0.67] | +0.48 [+0.24, +0.67] | +0.72 |
| 成员:knn_agreement | +0.22 [-0.11, +0.53] | +0.12 [-0.18, +0.44] | +0.11 [-0.19, +0.42] | -0.74 |
| 成员:silhouette | +0.26 [-0.09, +0.58] | +0.02 [-0.31, +0.36] | +0.01 [-0.32, +0.35] | -0.91 |
| 成员:calinski_harabasz | +0.21 [-0.13, +0.54] | -0.07 [-0.36, +0.25] | -0.08 [-0.37, +0.24] | -0.98 |
| 成员:davies_bouldin | +0.20 [-0.13, +0.50] | +0.00 [-0.32, +0.34] | -0.01 [-0.33, +0.33] | -0.86 |
| K | -0.18 [-0.50, +0.15] | +0.11 [-0.21, +0.40] | +0.12 [-0.19, +0.41] | +1.00 |

选中的候选（151673）：oracle louvain(r=1,w=0.3)，K=6，ARI **0.557**。默认参数：leiden(r=1,w=0.3) K=6 ARI 0.489；louvain(r=1,w=0.3) K=6 ARI 0.557；spagcn(n=7) K=7 ARI 0.317；graphst(n=7) K=7 ARI 0.253；cellcharter(n=7) K=7 ARI 0.396；中位数 **0.396**。

| 面板 | 选中 | K | K−7 | ARI | 相对 oracle | 相对默认中位数 | AMI | NMI | ARI 名次 |
|---|---|---|---|---|---|---|---|---|---|
| current | leiden(r=1,w=0.9) | 21 | +14 | 0.189 | -0.369 | -0.208 | 0.438 | 0.443 | 44/52 |
| candidate | leiden(r=0.1,w=0.3) | 2 | -5 | 0.152 | -0.405 | -0.245 | 0.352 | 0.353 | 49/52 |
| alternate | leiden(r=0.1,w=0.3) | 2 | -5 | 0.152 | -0.405 | -0.245 | 0.352 | 0.353 | 49/52 |
| 成员 chaos 单独 | leiden(r=1,w=0.9) | 21 | +14 | 0.189 | -0.369 | -0.208 | 0.438 | 0.443 | 44/52 |
| 成员 pas 单独 | leiden(r=0.3,w=0.9) | 8 | +1 | 0.332 | -0.225 | -0.064 | 0.464 | 0.466 | 27/52 |
| 成员 spatial_leiden_ami 单独 | leiden(r=1,w=0.9) | 21 | +14 | 0.189 | -0.369 | -0.208 | 0.438 | 0.443 | 44/52 |
| 成员 knn_agreement 单独 | leiden(r=0.3,w=0.9) | 8 | +1 | 0.332 | -0.225 | -0.064 | 0.464 | 0.466 | 27/52 |
| 成员 silhouette 单独 | louvain(r=0.15,w=0.3) | 2 | -5 | 0.149 | -0.408 | -0.247 | 0.348 | 0.349 | 50/52 |
| 成员 calinski_harabasz 单独 | louvain(r=0.15,w=0.3) | 2 | -5 | 0.149 | -0.408 | -0.247 | 0.348 | 0.349 | 50/52 |
| 成员 davies_bouldin 单独 | louvain(r=0.15,w=0.3) | 2 | -5 | 0.149 | -0.408 | -0.247 | 0.348 | 0.349 | 50/52 |

各面板前 5 名：

- current：leiden(r=1,w=0.9) K=21 分 0.908 ARI 0.189；leiden(r=0.3,w=0.9) K=8 分 0.857 ARI 0.332；leiden(r=1,w=0.6) K=9 分 0.810 ARI 0.468；cellcharter(n=16) K=16 分 0.758 ARI 0.376；cellcharter(n=7) K=7 分 0.758 ARI 0.396
- candidate：leiden(r=0.1,w=0.3) K=2 分 0.664 ARI 0.152；louvain(r=0.15,w=0.3) K=2 分 0.662 ARI 0.149；louvain(r=0.1,w=0.3) K=2 分 0.658 ARI 0.152；leiden(r=0.15,w=0.3) K=2 分 0.650 ARI 0.152；cellcharter(n=3) K=3 分 0.571 ARI 0.307
- alternate：leiden(r=0.1,w=0.3) K=2 分 0.657 ARI 0.152；louvain(r=0.15,w=0.3) K=2 分 0.657 ARI 0.149；louvain(r=0.1,w=0.3) K=2 分 0.654 ARI 0.152；leiden(r=0.15,w=0.3) K=2 分 0.643 ARI 0.152；cellcharter(n=3) K=3 分 0.551 ARI 0.307

子集稳健性与配对比较（151673）：

| 子集 | n | 现状 ρ | 候选面板 ρ | 备选 ρ | 候选−现状 Δρ | 备选−现状 Δρ | 现状选中 K / ARI | 候选选中 K / ARI | 备选选中 K / ARI |
|---|---|---|---|---|---|---|---|---|---|
| 全部 | 52 | +0.19 [-0.10, +0.45] | +0.27 [-0.06, +0.58] | +0.26 [-0.07, +0.56] | +0.08 [-0.22, +0.39] | +0.07 [-0.22, +0.37] | 21 / 0.189 | 2 / 0.152 | 2 / 0.152 |
| 只用 runner | 46 | -0.07 [-0.34, +0.21] | +0.06 [-0.28, +0.41] | +0.04 [-0.29, +0.39] | +0.13 [-0.27, +0.52] | +0.11 [-0.27, +0.49] | 21 / 0.189 | 2 / 0.152 | 2 / 0.152 |
| 3 ≤ K ≤ 20 | 41 | +0.01 [-0.29, +0.30] | +0.41 [+0.10, +0.66] | +0.39 [+0.08, +0.64] | +0.40 [+0.07, +0.72] | +0.38 [+0.06, +0.68] | 8 / 0.332 | 3 / 0.307 | 3 / 0.307 |
| 只用 spagcn/graphst/cellcharter | 18 | +0.88 [+0.66, +0.96] | +0.51 [+0.00, +0.87] | +0.51 [+0.00, +0.87] | -0.36 [-0.77, -0.03] | -0.36 [-0.77, -0.03] | 16 / 0.376 | 3 / 0.307 | 3 / 0.307 |

控制 K：同一 n_domains 下 spagcn/graphst/cellcharter 之间（151673）

| n | ARI 最高 | 现状选 | 候选选 | 备选选 |
|---|---|---|---|---|
| 3 | cellcharter (0.307) | cellcharter (0.307) | cellcharter (0.307) | cellcharter (0.307) |
| 5 | cellcharter (0.452) | cellcharter (0.452) | cellcharter (0.452) | cellcharter (0.452) |
| 7 | cellcharter (0.396) | cellcharter (0.396) | cellcharter (0.396) | cellcharter (0.396) |
| 9 | cellcharter (0.378) | cellcharter (0.378) | cellcharter (0.378) | cellcharter (0.378) |
| 12 | cellcharter (0.420) | cellcharter (0.420) | cellcharter (0.420) | cellcharter (0.420) |
| 16 | cellcharter (0.376) | cellcharter (0.376) | cellcharter (0.376) | cellcharter (0.376) |

命中数：current 6/6，candidate 6/6，alternate 6/6。

按 K 分箱的中位数（151673）

| K 箱 | n | CHAOS | PAS | AMI(空间) | kNN | silhouette | ARI |
|---|---|---|---|---|---|---|---|
| 2–4 | 20 | 0.776 | 0.913 | 0.325 | 0.820 | 0.137 | 0.381 |
| 5–6 | 5 | 0.939 | 0.880 | 0.359 | 0.737 | 0.091 | 0.452 |
| 7–8 | 6 | 0.921 | 0.768 | 0.372 | 0.633 | 0.059 | 0.341 |
| 9–12 | 9 | 0.898 | 0.791 | 0.414 | 0.659 | 0.040 | 0.378 |
| 13–20 | 5 | 0.871 | 0.700 | 0.399 | 0.576 | 0.031 | 0.357 |
| 21–200 | 7 | 0.732 | 0.357 | 0.377 | 0.350 | 0.016 | 0.189 |

#### 切片 151674

试验 56 个，56 个 ok；runner fan-out 墙钟 210 s，GPU ['0', '1', '2', '3']。K=1 排除：无；重复划分 4 个（louvain(r=0.3,w=0.6) = louvain(r=0.3,w=0.3)；louvain(r=0.3,w=0.9) = louvain(r=0.3,w=0.3)；louvain(r=1,w=0.6) = louvain(r=1,w=0.3)；louvain(r=1,w=0.9) = louvain(r=1,w=0.3)）。分析 52 个候选，K 从 2 到 67。


<details><summary>全部候选（151674）（展开）</summary>


| 候选 | K | 现状 | 候选面板 | 备选 | CHAOS | PAS | AMI(空间) | kNN | sil | CH | −DB | ARI | AMI | NMI |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| cellcharter(n=3) | 3 | 0.702 | 0.565 | 0.542 | 0.960 | 0.964 | 0.312 | 0.895 | 0.166 | 988 | -2.126 | 0.329 | 0.514 | 0.515 |
| cellcharter(n=5) | 5 | 0.748 | 0.522 | 0.491 | 0.982 | 0.963 | 0.406 | 0.871 | 0.080 | 611 | -2.578 | 0.430 | 0.604 | 0.604 |
| cellcharter(n=7) (默认) | 7 | 0.778 | 0.507 | 0.476 | 0.985 | 0.957 | 0.482 | 0.865 | 0.057 | 453 | -3.035 | 0.410 | 0.602 | 0.603 |
| cellcharter(n=9) | 9 | 0.776 | 0.480 | 0.444 | 0.978 | 0.918 | 0.502 | 0.812 | 0.041 | 345 | -3.450 | 0.367 | 0.549 | 0.551 |
| cellcharter(n=12) | 12 | 0.793 | 0.482 | 0.449 | 0.967 | 0.920 | 0.554 | 0.822 | 0.043 | 288 | -3.032 | 0.319 | 0.527 | 0.529 |
| cellcharter(n=16) | 16 | 0.756 | 0.422 | 0.382 | 0.958 | 0.814 | 0.525 | 0.696 | 0.029 | 223 | -3.418 | 0.282 | 0.528 | 0.531 |
| graphst(n=3) | 3 | 0.708 | 0.523 | 0.481 | 0.958 | 0.911 | 0.357 | 0.785 | 0.134 | 943 | -2.236 | 0.266 | 0.390 | 0.391 |
| graphst(n=5) | 5 | 0.694 | 0.465 | 0.419 | 0.889 | 0.870 | 0.411 | 0.732 | 0.060 | 538 | -3.885 | 0.305 | 0.377 | 0.379 |
| graphst(n=7) (默认) | 7 | 0.673 | 0.419 | 0.361 | 0.903 | 0.819 | 0.371 | 0.646 | 0.018 | 402 | -3.642 | 0.241 | 0.367 | 0.369 |
| graphst(n=9) | 9 | 0.688 | 0.391 | 0.334 | 0.924 | 0.779 | 0.406 | 0.607 | 0.004 | 309 | -4.108 | 0.240 | 0.380 | 0.383 |
| graphst(n=12) | 12 | 0.673 | 0.350 | 0.299 | 0.919 | 0.700 | 0.414 | 0.548 | -0.004 | 241 | -4.772 | 0.212 | 0.373 | 0.376 |
| graphst(n=16) | 16 | 0.653 | 0.304 | 0.267 | 0.902 | 0.607 | 0.426 | 0.497 | -0.012 | 186 | -5.167 | 0.207 | 0.385 | 0.389 |
| leiden(r=0.1,w=0.3) | 2 | 0.639 | 0.655 | 0.646 | 0.811 | 0.944 | 0.314 | 0.919 | 0.366 | 1491 | -1.130 | 0.147 | 0.358 | 0.358 |
| leiden(r=0.15,w=0.3) | 2 | 0.620 | 0.651 | 0.645 | 0.774 | 0.935 | 0.308 | 0.916 | 0.367 | 1488 | -1.125 | 0.144 | 0.353 | 0.353 |
| leiden(r=0.2,w=0.3) | 2 | 0.665 | 0.632 | 0.627 | 0.896 | 0.918 | 0.308 | 0.904 | 0.345 | 1443 | -1.206 | 0.154 | 0.350 | 0.351 |
| leiden(r=0.3,w=0.3) | 3 | 0.612 | 0.525 | 0.505 | 0.670 | 0.946 | 0.387 | 0.885 | 0.104 | 843 | -2.998 | 0.461 | 0.594 | 0.594 |
| leiden(r=0.4,w=0.3) | 3 | 0.641 | 0.519 | 0.494 | 0.768 | 0.939 | 0.366 | 0.866 | 0.099 | 816 | -3.086 | 0.447 | 0.571 | 0.572 |
| leiden(r=0.3,w=0.6) | 3 | 0.697 | 0.545 | 0.529 | 0.859 | 0.986 | 0.391 | 0.939 | 0.103 | 837 | -3.148 | 0.433 | 0.592 | 0.593 |
| leiden(r=0.3,w=0) | 4 | 0.544 | 0.465 | 0.427 | 0.615 | 0.819 | 0.335 | 0.703 | 0.112 | 724 | -2.387 | 0.433 | 0.507 | 0.507 |
| leiden(r=0.5,w=0.3) | 5 | 0.667 | 0.490 | 0.459 | 0.773 | 0.899 | 0.446 | 0.806 | 0.081 | 518 | -2.801 | 0.440 | 0.524 | 0.525 |
| leiden(r=0.7,w=0.3) | 6 | 0.674 | 0.476 | 0.439 | 0.803 | 0.876 | 0.443 | 0.765 | 0.077 | 445 | -2.982 | 0.429 | 0.499 | 0.501 |
| leiden(r=0.3,w=0.9) | 7 | 0.865 | 0.519 | 0.503 | 0.999 | 0.991 | 0.668 | 0.944 | 0.047 | 312 | -3.964 | 0.373 | 0.479 | 0.481 |
| leiden(r=1,w=0.3) (默认) | 10 | 0.658 | 0.431 | 0.392 | 0.776 | 0.807 | 0.466 | 0.691 | 0.054 | 307 | -2.826 | 0.413 | 0.498 | 0.500 |
| leiden(r=1,w=0.6) | 10 | 0.840 | 0.517 | 0.493 | 0.999 | 0.984 | 0.610 | 0.909 | 0.051 | 289 | -3.220 | 0.380 | 0.535 | 0.537 |
| leiden(r=1.4,w=0.3) | 11 | 0.655 | 0.427 | 0.387 | 0.767 | 0.804 | 0.470 | 0.683 | 0.050 | 302 | -2.742 | 0.335 | 0.489 | 0.491 |
| leiden(r=1,w=0) | 11 | 0.536 | 0.322 | 0.287 | 0.676 | 0.579 | 0.376 | 0.473 | 0.066 | 321 | -2.791 | 0.324 | 0.434 | 0.436 |
| leiden(r=2,w=0.3) | 16 | 0.657 | 0.383 | 0.346 | 0.803 | 0.719 | 0.479 | 0.608 | 0.047 | 234 | -2.850 | 0.299 | 0.482 | 0.485 |
| leiden(r=1,w=0.9) | 17 | 0.890 | 0.489 | 0.465 | 1.000 | 0.979 | 0.737 | 0.907 | -0.014 | 151 | -4.551 | 0.257 | 0.478 | 0.482 |
| leiden(r=3,w=0.3*) | 25 | 0.630 | 0.325 | 0.290 | 0.796 | 0.630 | 0.463 | 0.524 | 0.021 | 155 | -2.955 | 0.240 | 0.453 | 0.458 |
| leiden(r=4.5,w=0.3*) | 45 | 0.582 | 0.251 | 0.230 | 0.761 | 0.485 | 0.451 | 0.421 | 0.017 | 99 | -3.034 | 0.155 | 0.428 | 0.437 |
| leiden(r=6,w=0.3*) | 67 | 0.547 | 0.182 | 0.178 | 0.755 | 0.360 | 0.432 | 0.348 | 0.005 | 70 | -3.125 | 0.109 | 0.406 | 0.420 |
| louvain(r=0.1,w=0.3) | 2 | 0.614 | 0.644 | 0.640 | 0.769 | 0.917 | 0.306 | 0.905 | 0.370 | 1499 | -1.113 | 0.140 | 0.346 | 0.347 |
| louvain(r=0.15,w=0.3) | 2 | 0.616 | 0.643 | 0.639 | 0.774 | 0.916 | 0.307 | 0.904 | 0.370 | 1503 | -1.114 | 0.141 | 0.347 | 0.348 |
| louvain(r=0.2,w=0.3) | 2 | 0.619 | 0.645 | 0.641 | 0.778 | 0.921 | 0.308 | 0.907 | 0.370 | 1501 | -1.116 | 0.142 | 0.349 | 0.350 |
| louvain(r=0.3,w=0.3) | 3 | 0.599 | 0.521 | 0.497 | 0.657 | 0.934 | 0.373 | 0.862 | 0.108 | 869 | -2.971 | 0.437 | 0.568 | 0.569 |
| louvain(r=0.4,w=0.3) | 3 | 0.614 | 0.518 | 0.493 | 0.700 | 0.924 | 0.374 | 0.849 | 0.112 | 870 | -2.937 | 0.409 | 0.547 | 0.548 |
| louvain(r=0.5,w=0.3) | 4 | 0.616 | 0.498 | 0.465 | 0.719 | 0.883 | 0.379 | 0.784 | 0.113 | 725 | -2.419 | 0.443 | 0.533 | 0.534 |
| louvain(r=0.3,w=0) | 4 | 0.572 | 0.472 | 0.437 | 0.678 | 0.832 | 0.336 | 0.728 | 0.111 | 747 | -2.525 | 0.373 | 0.489 | 0.490 |
| louvain(r=0.7,w=0.3) | 6 | 0.641 | 0.474 | 0.435 | 0.754 | 0.860 | 0.420 | 0.744 | 0.088 | 471 | -2.847 | 0.506 | 0.546 | 0.547 |
| louvain(r=1,w=0.3) (默认) | 8 | 0.663 | 0.446 | 0.404 | 0.796 | 0.814 | 0.454 | 0.690 | 0.077 | 400 | -2.849 | 0.423 | 0.511 | 0.513 |
| louvain(r=1,w=0) | 8 | 0.557 | 0.404 | 0.357 | 0.661 | 0.725 | 0.369 | 0.586 | 0.083 | 405 | -2.496 | 0.403 | 0.485 | 0.487 |
| louvain(r=1.4,w=0.3) | 11 | 0.664 | 0.414 | 0.372 | 0.793 | 0.785 | 0.474 | 0.659 | 0.043 | 310 | -2.823 | 0.368 | 0.520 | 0.523 |
| louvain(r=2,w=0.3) | 14 | 0.648 | 0.389 | 0.348 | 0.800 | 0.727 | 0.457 | 0.604 | 0.051 | 264 | -2.779 | 0.322 | 0.490 | 0.493 |
| louvain(r=3,w=0.3*) | 21 | 0.621 | 0.324 | 0.290 | 0.793 | 0.610 | 0.455 | 0.510 | 0.038 | 187 | -2.898 | 0.263 | 0.477 | 0.482 |
| louvain(r=4.5,w=0.3*) | 36 | 0.612 | 0.278 | 0.253 | 0.808 | 0.529 | 0.458 | 0.453 | 0.028 | 121 | -3.003 | 0.188 | 0.459 | 0.466 |
| louvain(r=6,w=0.3*) | 54 | 0.577 | 0.195 | 0.189 | 0.808 | 0.378 | 0.446 | 0.359 | 0.013 | 87 | -3.063 | 0.129 | 0.432 | 0.442 |
| spagcn(n=3) | 3 | 0.690 | 0.518 | 0.478 | 0.971 | 0.883 | 0.313 | 0.764 | 0.152 | 1017 | -2.072 | 0.300 | 0.416 | 0.417 |
| spagcn(n=5) | 5 | 0.708 | 0.469 | 0.424 | 0.972 | 0.863 | 0.366 | 0.727 | 0.075 | 586 | -3.012 | 0.313 | 0.402 | 0.403 |
| spagcn(n=7) (默认) | 7 | 0.706 | 0.444 | 0.404 | 0.928 | 0.848 | 0.414 | 0.731 | 0.039 | 431 | -3.121 | 0.251 | 0.400 | 0.402 |
| spagcn(n=9) | 9 | 0.714 | 0.433 | 0.389 | 0.935 | 0.822 | 0.439 | 0.690 | 0.045 | 360 | -3.140 | 0.291 | 0.453 | 0.455 |
| spagcn(n=12) | 12 | 0.716 | 0.412 | 0.374 | 0.920 | 0.788 | 0.477 | 0.673 | 0.036 | 276 | -3.335 | 0.272 | 0.438 | 0.440 |
| spagcn(n=16) | 16 | 0.708 | 0.407 | 0.371 | 0.881 | 0.785 | 0.497 | 0.677 | 0.029 | 214 | -3.673 | 0.250 | 0.448 | 0.452 |

</details>

面板、成员与外部指标的 Spearman ρ（151674；bootstrap 95% CI，4000 次）：

| 面板 / 成员 | ARI | AMI | NMI | ρ(·, K) |
|---|---|---|---|---|
| 面板:current | +0.10 [-0.19, +0.40] | +0.16 [-0.10, +0.41] | +0.15 [-0.11, +0.40] | +0.08 |
| 面板:candidate | +0.23 [-0.11, +0.56] | +0.11 [-0.22, +0.46] | +0.10 [-0.23, +0.46] | -0.88 |
| 面板:alternate | +0.23 [-0.11, +0.57] | +0.13 [-0.21, +0.47] | +0.12 [-0.21, +0.46] | -0.87 |
| 成员:chaos | -0.20 [-0.45, +0.13] | -0.07 [-0.36, +0.23] | -0.08 [-0.36, +0.23] | +0.16 |
| 成员:pas | +0.37 [+0.10, +0.61] | +0.32 [+0.03, +0.56] | +0.32 [+0.02, +0.55] | -0.70 |
| 成员:spatial_leiden_ami | +0.12 [-0.15, +0.40] | +0.39 [+0.11, +0.63] | +0.39 [+0.11, +0.63] | +0.78 |
| 成员:knn_agreement | +0.25 [-0.06, +0.56] | +0.19 [-0.13, +0.50] | +0.18 [-0.14, +0.49] | -0.75 |
| 成员:silhouette | +0.28 [-0.08, +0.63] | +0.05 [-0.29, +0.41] | +0.04 [-0.30, +0.39] | -0.91 |
| 成员:calinski_harabasz | +0.22 [-0.13, +0.56] | -0.04 [-0.36, +0.29] | -0.05 [-0.37, +0.29] | -0.99 |
| 成员:davies_bouldin | +0.03 [-0.28, +0.34] | -0.10 [-0.41, +0.24] | -0.11 [-0.41, +0.24] | -0.56 |
| K | -0.23 [-0.57, +0.12] | +0.04 [-0.29, +0.36] | +0.05 [-0.28, +0.37] | +1.00 |

选中的候选（151674）：oracle louvain(r=0.7,w=0.3)，K=6，ARI **0.506**。默认参数：leiden(r=1,w=0.3) K=10 ARI 0.413；louvain(r=1,w=0.3) K=8 ARI 0.423；spagcn(n=7) K=7 ARI 0.251；graphst(n=7) K=7 ARI 0.241；cellcharter(n=7) K=7 ARI 0.410；中位数 **0.410**。

| 面板 | 选中 | K | K−7 | ARI | 相对 oracle | 相对默认中位数 | AMI | NMI | ARI 名次 |
|---|---|---|---|---|---|---|---|---|---|
| current | leiden(r=1,w=0.9) | 17 | +10 | 0.257 | -0.249 | -0.153 | 0.478 | 0.482 | 35/52 |
| candidate | leiden(r=0.1,w=0.3) | 2 | -5 | 0.147 | -0.359 | -0.263 | 0.358 | 0.358 | 46/52 |
| alternate | leiden(r=0.1,w=0.3) | 2 | -5 | 0.147 | -0.359 | -0.263 | 0.358 | 0.358 | 46/52 |
| 成员 chaos 单独 | leiden(r=1,w=0.9) | 17 | +10 | 0.257 | -0.249 | -0.153 | 0.478 | 0.482 | 35/52 |
| 成员 pas 单独 | leiden(r=0.3,w=0.9) | 7 | +0 | 0.373 | -0.133 | -0.037 | 0.479 | 0.481 | 18/52 |
| 成员 spatial_leiden_ami 单独 | leiden(r=1,w=0.9) | 17 | +10 | 0.257 | -0.249 | -0.153 | 0.478 | 0.482 | 35/52 |
| 成员 knn_agreement 单独 | leiden(r=0.3,w=0.9) | 7 | +0 | 0.373 | -0.133 | -0.037 | 0.479 | 0.481 | 18/52 |
| 成员 silhouette 单独 | louvain(r=0.15,w=0.3) | 2 | -5 | 0.141 | -0.366 | -0.269 | 0.347 | 0.348 | 49/52 |
| 成员 calinski_harabasz 单独 | louvain(r=0.15,w=0.3) | 2 | -5 | 0.141 | -0.366 | -0.269 | 0.347 | 0.348 | 49/52 |
| 成员 davies_bouldin 单独 | louvain(r=0.1,w=0.3) | 2 | -5 | 0.140 | -0.366 | -0.270 | 0.346 | 0.347 | 50/52 |

各面板前 5 名：

- current：leiden(r=1,w=0.9) K=17 分 0.890 ARI 0.257；leiden(r=0.3,w=0.9) K=7 分 0.865 ARI 0.373；leiden(r=1,w=0.6) K=10 分 0.840 ARI 0.380；cellcharter(n=12) K=12 分 0.793 ARI 0.319；cellcharter(n=7) K=7 分 0.778 ARI 0.410
- candidate：leiden(r=0.1,w=0.3) K=2 分 0.655 ARI 0.147；leiden(r=0.15,w=0.3) K=2 分 0.651 ARI 0.144；louvain(r=0.2,w=0.3) K=2 分 0.645 ARI 0.142；louvain(r=0.1,w=0.3) K=2 分 0.644 ARI 0.140；louvain(r=0.15,w=0.3) K=2 分 0.643 ARI 0.141
- alternate：leiden(r=0.1,w=0.3) K=2 分 0.646 ARI 0.147；leiden(r=0.15,w=0.3) K=2 分 0.645 ARI 0.144；louvain(r=0.2,w=0.3) K=2 分 0.641 ARI 0.142；louvain(r=0.1,w=0.3) K=2 分 0.640 ARI 0.140；louvain(r=0.15,w=0.3) K=2 分 0.639 ARI 0.141

子集稳健性与配对比较（151674）：

| 子集 | n | 现状 ρ | 候选面板 ρ | 备选 ρ | 候选−现状 Δρ | 备选−现状 Δρ | 现状选中 K / ARI | 候选选中 K / ARI | 备选选中 K / ARI |
|---|---|---|---|---|---|---|---|---|---|
| 全部 | 52 | +0.10 [-0.19, +0.40] | +0.23 [-0.11, +0.56] | +0.23 [-0.11, +0.57] | +0.12 [-0.36, +0.59] | +0.13 [-0.35, +0.60] | 17 / 0.257 | 2 / 0.147 | 2 / 0.147 |
| 只用 runner | 46 | -0.12 [-0.39, +0.20] | +0.03 [-0.32, +0.40] | +0.04 [-0.31, +0.41] | +0.15 [-0.43, +0.70] | +0.16 [-0.42, +0.71] | 17 / 0.257 | 2 / 0.147 | 2 / 0.147 |
| 3 ≤ K ≤ 20 | 40 | -0.39 [-0.60, -0.11] | +0.56 [+0.29, +0.75] | +0.58 [+0.32, +0.76] | +0.95 [+0.62, +1.20] | +0.97 [+0.65, +1.21] | 17 / 0.257 | 3 / 0.329 | 3 / 0.329 |
| 只用 spagcn/graphst/cellcharter | 18 | +0.69 [+0.26, +0.90] | +0.80 [+0.43, +0.97] | +0.83 [+0.49, +0.98] | +0.11 [-0.25, +0.53] | +0.14 [-0.19, +0.55] | 12 / 0.319 | 3 / 0.329 | 3 / 0.329 |

控制 K：同一 n_domains 下 spagcn/graphst/cellcharter 之间（151674）

| n | ARI 最高 | 现状选 | 候选选 | 备选选 |
|---|---|---|---|---|
| 3 | cellcharter (0.329) | graphst (0.266) | cellcharter (0.329) | cellcharter (0.329) |
| 5 | cellcharter (0.430) | cellcharter (0.430) | cellcharter (0.430) | cellcharter (0.430) |
| 7 | cellcharter (0.410) | cellcharter (0.410) | cellcharter (0.410) | cellcharter (0.410) |
| 9 | cellcharter (0.367) | cellcharter (0.367) | cellcharter (0.367) | cellcharter (0.367) |
| 12 | cellcharter (0.319) | cellcharter (0.319) | cellcharter (0.319) | cellcharter (0.319) |
| 16 | cellcharter (0.282) | cellcharter (0.282) | cellcharter (0.282) | cellcharter (0.282) |

命中数：current 5/6，candidate 6/6，alternate 6/6。

按 K 分箱的中位数（151674）

| K 箱 | n | CHAOS | PAS | AMI(空间) | kNN | silhouette | ARI |
|---|---|---|---|---|---|---|---|
| 2–4 | 17 | 0.774 | 0.921 | 0.335 | 0.885 | 0.134 | 0.329 |
| 5–6 | 6 | 0.846 | 0.873 | 0.415 | 0.754 | 0.078 | 0.429 |
| 7–8 | 6 | 0.915 | 0.834 | 0.434 | 0.710 | 0.052 | 0.388 |
| 9–12 | 11 | 0.920 | 0.804 | 0.470 | 0.683 | 0.043 | 0.324 |
| 13–20 | 6 | 0.892 | 0.756 | 0.488 | 0.643 | 0.029 | 0.269 |
| 21–200 | 6 | 0.794 | 0.507 | 0.453 | 0.437 | 0.019 | 0.172 |


#### 合并两张切片

| 面板 | 各切片 ρ | 平均 ρ | 选中 ARI（各切片） | K−7（各切片） |
|---|---|---|---|---|
| current | +0.19 / +0.10 | +0.14 | 0.189 / 0.257 | +14 / +10 |
| candidate | +0.27 / +0.23 | +0.25 | 0.152 / 0.147 | -5 / -5 |
| alternate | +0.26 / +0.23 | +0.25 | 0.152 / 0.147 | -5 / -5 |

#### 第 5 步明细

成员：chaos, pas, spatial_leiden_ami, knn_agreement, silhouette, davies_bouldin（前五个按面板的校正值/原值裁到 [0,1]；Davies-Bouldin 取负后在切片内 min-max 缩放）。组合为 1–3 个成员，权重在 0.1 网格上、和为 1，共 861 个。训练切片上按与 ARI 的 Spearman ρ 选最优，在另一切片上报告 ρ（bootstrap CI）、选中候选的 K 与 ARI。

| 训练 → 检验 | 训练上最优组合 | 训练 ρ | 检验 ρ [95% CI] | 检验选中 | K | ARI | 检验 oracle ARI | 检验默认中位数 |
|---|---|---|---|---|---|---|---|---|
| 151673 → 151674 | 0.1·pas + 0.8·spatial_leiden_ami + 0.1·knn_agreement | +0.52 | +0.39 [+0.14, +0.62] | leiden(r=1,w=0.9) | 17 | 0.257 | 0.506 | 0.410 |
| 151674 → 151673 | 0.5·pas + 0.5·spatial_leiden_ami | +0.56 | +0.45 [+0.20, +0.65] | leiden(r=1,w=0.9) | 21 | 0.189 | 0.557 | 0.396 |

同上，但训练目标换成"训练切片上 argmax 候选的 ARI"（平手取 ρ 更高者）：

| 训练 → 检验 | 训练上最优组合 | 训练选中 ARI | 检验 ρ [95% CI] | 检验选中 | K | ARI | 检验 oracle ARI | 检验默认中位数 |
|---|---|---|---|---|---|---|---|---|
| 151673 → 151674 | 0.8·pas + 0.1·knn_agreement + 0.1·davies_bouldin | +0.47 (ρ +0.28) | +0.23 [-0.09, +0.55] | leiden(r=0.1,w=0.3) | 2 | 0.147 | 0.506 | 0.410 |
| 151674 → 151673 | 0.9·pas + 0.1·silhouette | +0.43 (ρ +0.29) | +0.25 [-0.07, +0.55] | leiden(r=0.3,w=0.6) | 4 | 0.471 | 0.557 | 0.396 |

两张切片上 ρ 的较小值最高的 10 个组合（描述性，同时用了两张切片，不是检验）：

| 组合 | ρ 151673 | ρ 151674 | 选中 K / ARI（151673） | 选中 K / ARI（151674） |
|---|---|---|---|---|
| 0.3·pas + 0.7·spatial_leiden_ami | +0.50 | +0.49 | 21 / 0.189 | 17 / 0.257 |
| 0.2·pas + 0.7·spatial_leiden_ami + 0.1·knn_agreement | +0.49 | +0.49 | 21 / 0.189 | 17 / 0.257 |
| 0.4·pas + 0.6·spatial_leiden_ami | +0.49 | +0.55 | 21 / 0.189 | 17 / 0.257 |
| 0.3·pas + 0.6·spatial_leiden_ami + 0.1·knn_agreement | +0.45 | +0.55 | 21 / 0.189 | 17 / 0.257 |
| 0.5·pas + 0.5·spatial_leiden_ami | +0.45 | +0.56 | 21 / 0.189 | 17 / 0.257 |
| 0.2·pas + 0.8·spatial_leiden_ami | +0.52 | +0.43 | 21 / 0.189 | 17 / 0.257 |
| 0.1·pas + 0.7·spatial_leiden_ami + 0.2·knn_agreement | +0.41 | +0.48 | 21 / 0.189 | 17 / 0.257 |
| 0.3·pas + 0.6·spatial_leiden_ami + 0.1·davies_bouldin | +0.40 | +0.41 | 21 / 0.189 | 17 / 0.257 |
| 0.2·pas + 0.7·spatial_leiden_ami + 0.1·davies_bouldin | +0.48 | +0.40 | 21 / 0.189 | 17 / 0.257 |
| 0.2·pas + 0.7·spatial_leiden_ami + 0.1·silhouette | +0.39 | +0.41 | 21 / 0.189 | 17 / 0.257 |

### 结论

1. **按 owner 给定的三条标准，候选面板在两张 DLPFC 切片上都没有通过；备选面板同样没有通过。** 标准 1：ρ 点估计为正（+0.27 / +0.23），但 CI 跨 0；标准 2：两张切片都选中 K=2（WM 对灰质），ARI 0.15，远低于默认中位数（0.40 / 0.41）；标准 3：Δρ 不显著，选中者的 ARI 还比现状低。去掉线粒体过滤后判定不变。
2. 与 Slide-seqV2 不同，**这次的真值可信**：层是空间连续的区域，oracle ARI 为 0.56 / 0.51，在文献范围内。所以这次的失败可以归到面板本身，不能再归到真值上。
3. 失败方式与合成研究的预测一致，而且在两张切片之间高度可重复：候选面板靠 silhouette 选 K，在层间表达渐变的组织上退到最粗的划分；现状面板靠 CHAOS 和 AMI，被空间过度平滑的划分（leiden w=0.9）吸引，发生过切。两个面板都把真值排在自己的选中者之后。
4. 面板**并非毫无信息**：在固定 K 时区分方法（cellcharter 对 spagcn/graphst）几乎全对；在 3 ≤ K ≤ 20 的范围内，候选面板与 ARI 的相关显著为正，并且显著优于现状。问题集中在 argmax 选 K 上，以及识别"空间整齐但层结构错误"的候选上。
5. 第 5 步：现有成员的任何线性组合都没有在两个方向的留一检验中同时满足标准 1 和 2。PAS 在各项中最稳（唯一在一张切片上单独 CI 不跨 0 的成员，也是单独选 K 最接近 7 的成员）；PAS + AMI 的排序最好，但 argmax 有问题。这只是给 G3 的证据，不是推荐。

### 对"是否扩大到 12 张切片加 CosMx 肝"的建议

- **不建议为了复检现有的两个面板而扩大。** 两张切片上的失败方式一致、机制清楚（K=2 的 WM 二分；w=0.9 的过度平滑），而且对预处理不敏感。再加 10 张切片，大概率只是把"不通过"重复 10 次。
- **建议在 G3 先裁定一个新的规则，并在数据之外事先写定，再用扩大后的数据做留出检验。** 这两张切片已经用来看过数据、做过第 5 步的搜索，只能算开发集；其余 10 张 DLPFC 切片加 CosMx 肝可以作为干净的留出集。成本很低：每张切片的候选生成约 3–4 分钟（4 张 GPU），打分不到 1 分钟。可以考虑的方向（都未经检验，只列出来）：
  - 把"选 K"和"给候选打分"拆开，例如只在候选之间的 K 共识附近做选择，或者用 top-k 的 regret 替代 argmax 作为通过标准之一；
  - 给空间项加一个针对"空间过度平滑"的约束（例如要求划分与表达有最低一致性），专门处理 leiden w=0.9 这类候选；
  - 标准 1（ρ）与标准 2（argmax）在这里给出相反的最优组合，G3 需要先定以哪一条为主。
- 若 owner 仍想先确认第 1–3 条在更多切片上的结论，扩大的代价确实低，可以直接用 `dlpfc.py` 跑（`--slices` 支持任意切片 ID；CosMx 需要另写 `prepare` 和真值映射）。

### 局限

- 只有两张切片，而且来自同一供体（151673/151674 是 Br8100 的相邻切片），不能代表供体之间的差异；每张 52 个候选，bootstrap 的 CI 很宽。
- 候选只来自 5 个方法及其主参数；leiden/louvain 的 resolution ≥ 3 超出了调参区间，没有经过 runner；louvain 的 `spatial_weight` 没有作用。graphst 的 ARI 低于文献水平，原因没有追查。
- silhouette、CH、DB 都只在预处理默认的 30 维 `X_pca` 上计算，没有试其他 HVG 数、PC 数或嵌入。
- "把真值当候选打分"只用有标注的 spot，参照 Leiden 分区是在这个子集上重算的，与候选的打分口径略有不同，只作定性参考。
- 第 5 步的权重是在同一对切片上选出、又在同一对切片上检验的（互为留出），只有 2 折，而且 861 个组合的多重比较没有校正。
