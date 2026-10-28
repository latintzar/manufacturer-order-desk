# Dependency notices

MIT covers Peter Neyra’s original source. Dependencies and their assets retain their own terms.

| Component | Location and notice |
| --- | --- |
| Three.js 0.160.0 | `app/src/prototypes/orders/vendor/three.min.js`; MIT notice in `THREE-LICENSE`; exact upstream hash in `provenance.json` |
| Inter | `app/public/inter.woff2`; SIL OFL in `inter-OFL.txt` |
| Fraunces | `app/public/fonts/fraunces/`; SIL OFL notice beside the font |
| Shared browser libraries | `harness/web/vendor/`; retained Marked, DOMPurify, D3, Mermaid, KaTeX and Highlight notices beside their pinned files |
| Chatwoot CE package | `harness/deploy/chatwoot/CHATWOOT-LICENSE`; container versions and digest remain in its Compose source |
| PyMuPDF | Python PDF extraction/rendering dependency in the retained worker; upstream [AGPL or commercial terms](https://pymupdf.readthedocs.io/en/latest/about.html#license-and-copyright) and [COPYING](https://github.com/pymupdf/PyMuPDF/blob/main/COPYING) |
| Python packages | Exact verified environment in `requirements.lock`; upstream distribution metadata supplies each package’s notices |
| Integration brand marks | `app/public/connection-brands/`; identify the optional upstream services and retain their owners |

The new Sample Hardware illustrations are generated fictional catalogue assets. Their prompts and original PNGs are in `fixtures/sample-hardware/images/`. The original manufacturer’s catalogue, photographs, PDFs, logo and customer state are excluded from this release.

[made by atelier neyra](https://atelierneyra.com)
