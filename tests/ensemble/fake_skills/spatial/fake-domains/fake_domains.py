"""Test fixture: label observations by a coordinate split, or misbehave on request."""

import argparse
import json
import os
import sys
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--input")
    parser.add_argument("--output", required=True)
    parser.add_argument("--demo", action="store_true")
    parser.add_argument(
        "--method",
        choices=[
            "split", "gpu", "needsgpu", "fail", "sleep", "eat", "nolabels", "noresult", "extra",
            "cal", "twod", "grid1", "flaky", "rand",
        ],
        default="split",
    )
    parser.add_argument("--n", type=int, default=3)
    parser.add_argument("--id-column", default="observation")
    parser.add_argument("--exit-code", type=int, default=3)
    parser.add_argument("--seconds", type=float, default=30.0)
    parser.add_argument("--memory-mb", type=int, default=1000)
    parser.add_argument("--data-type", default=None)
    parser.add_argument("--resolution", type=float, default=1.0)
    parser.add_argument("--smooth", type=float, default=0.3)
    parser.add_argument("--alpha", type=float, default=0.5)
    parser.add_argument("--beta", type=int, default=100)
    parser.add_argument("--layers", type=int, default=3)
    parser.add_argument("--fail-above", type=int, default=0)
    args = parser.parse_args()

    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=True)
    print(f"fake-domains: method={args.method}", flush=True)
    print(f"CUDA_VISIBLE_DEVICES={os.environ.get('CUDA_VISIBLE_DEVICES')!r}", flush=True)
    print(f"TMPDIR={os.environ.get('TMPDIR')}", flush=True)
    if args.method == "fail":
        print("fake-domains: failing on purpose", file=sys.stderr, flush=True)
        sys.exit(args.exit_code)
    if args.method == "flaky" and args.fail_above and args.n > args.fail_above:
        print("fake-domains: flaky method failing", file=sys.stderr, flush=True)
        sys.exit(4)
    if args.method == "sleep":
        time.sleep(args.seconds)
    if args.method == "eat":
        blocks = []
        for _ in range(args.memory_mb // 10):
            blocks.append(bytearray(10 * 1024 * 1024))
            time.sleep(0.005)
        time.sleep(30)

    import anndata

    adata = anndata.read_h5ad(args.input)
    x = adata.obsm["spatial"][:, 0]
    span = (x.max() - x.min()) or 1.0
    n = args.n
    noise = 0.0
    if args.method == "cal":
        n = max(1, min(30, int(round(args.resolution * 6))))
        noise = 0.3 * abs(args.smooth - 0.45)
    elif args.method == "twod":
        import math

        noise = 0.3 * abs(args.alpha - 0.7) + 0.04 * abs(math.log(args.beta / 100.0))
    elif args.method == "grid1":
        noise = 0.05 * abs(args.layers - 4)
    labels = [str(min(int((v - x.min()) / span * n), n - 1)) for v in x]
    if args.method == "rand":
        import numpy

        labels = [str(v) for v in numpy.random.randint(0, n, size=len(x))]
    if noise > 0:
        import zlib

        for index, name in enumerate(adata.obs_names):
            draw = zlib.crc32(f"{name}|{args.method}".encode()) % 10_000 / 10_000
            if draw < noise:
                labels[index] = str(zlib.crc32(f"{name}|label".encode()) % n)

    if args.method != "nolabels":
        tables = out / "tables"
        tables.mkdir(exist_ok=True)
        with open(tables / "domain_assignments.csv", "w") as sink:
            sink.write(f"{args.id_column},spatial_domain\n")
            for name, label in zip(adata.obs_names, labels):
                sink.write(f"{name},{label}\n")
            if args.method == "extra":
                sink.write("not-an-observation,0\n")
    (out / "figures").mkdir(exist_ok=True)
    (out / "figures" / "plot.png").write_bytes(b"png")
    (out / "report.md").write_text("report\n")
    adata.obs["spatial_domain"] = labels
    adata.write_h5ad(out / "processed.h5ad")
    if args.method != "noresult":
        (out / "result.json").write_text(json.dumps({"skill": "fake-domains", "summary": {"n_domains": args.n}}))


if __name__ == "__main__":
    main()
