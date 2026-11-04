# Open-source provenance and honest portfolio presentation

This **ElyraOps AI demo** was authored as a distinct local portfolio application. It does **not** contain or secretly rebrand the DocsGPT source tree. The open-source DocsGPT project was consulted as a general reference for features and product direction:

- Upstream: https://github.com/arc53/DocsGPT
- Upstream license: MIT (`https://github.com/arc53/DocsGPT/blob/main/LICENSE`)

If you want to include the **entire upstream DocsGPT codebase**, link it explicitly as a Git submodule:

```bash
bash scripts/add-upstream-submodule.sh
git submodule update --init --recursive
```

This does **not** merge DocsGPT into the original ElyraOps application or make them interoperable. Building a secure integration is additional engineering work.

When incorporating any substantial portion of MIT-licensed source code, retain the original license/copyright notice in the distributed files and document any derivative modifications. A repo rename or new UI must not be used to claim you authored upstream source code. In your portfolio, separate "built by me" from "adapted or integrated" and keep the actual code provenance transparent.
