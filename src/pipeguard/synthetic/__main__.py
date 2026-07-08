"""Package entry point: ``python -m pipeguard.synthetic`` regenerates the demo runs.

Kept as a thin module distinct from ``generator`` so ``runpy`` does not re-import a
module the package ``__init__`` already loaded — which is what makes the older
``python -m pipeguard.synthetic.generator`` form emit a ``RuntimeWarning``.
"""

from .generator import main

if __name__ == "__main__":
    main()
