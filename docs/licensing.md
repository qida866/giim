# Licensing and third-party materials

Reviewed for release preparation on October 16–19, 2026. **No code license has been added.** This document records decisions still needed; it does not grant rights over third-party material.

## Project code: owner decision required

There is no existing `LICENSE` file or license declaration in `pyproject.toml`. Without a license, default copyright restrictions apply; GitHub public visibility permits viewing/forking under its terms but is not a general open-source reuse grant. See [GitHub's licensing explanation](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository).

Two reasonable choices for the original project code:

- **[MIT](https://choosealicense.com/licenses/mit/):** permits use, modification, redistribution and commercial reuse subject to retaining its notice; includes warranty/liability disclaimers. It does not require downstream projects to publish their source. This is a simple choice if broad reuse of the portfolio code is intended.
- **[Apache-2.0](https://choosealicense.com/licenses/apache-2.0/):** also permits broad reuse, with an explicit patent grant/termination framework and additional notice/change-marking requirements. This may be preferable when those protections matter.

Before choosing, confirm ownership and any school/employer/contributor obligations. A code license must explicitly exclude publisher content, externally licensed model weights and other third-party materials. No license, copyright holder, contributor agreement or redistribution permission has been invented on the owner's behalf.

## Models and software dependencies

The upstream [BAAI/bge-m3 model card](https://huggingface.co/BAAI/bge-m3) identifies the model as MIT licensed. GIIM downloads the model separately and uses its dense 1,024-dimensional representation; weights are excluded from Git. Keep the upstream license/attribution if redistributing a model bundle. The model's license does not license input articles or guarantee the correctness of generated output.

The installed Phase 3 image metadata was also inspected (a selected direct-dependency inventory, not a complete transitive audit):

| Distribution | Version | Declared license metadata |
|---|---|---|
| FastAPI | 0.136.1 | MIT |
| SQLAlchemy | 2.0.49 | MIT |
| asyncpg | 0.31.0 | Apache-2.0 |
| qdrant-client | 1.18.0 | Apache-2.0 |
| scikit-learn | 1.8.0 | BSD-3-Clause |
| sentence-transformers | 5.5.0 | Apache-2.0 |
| torch | 2.11.0+cpu | BSD-3-Clause |
| openai SDK | 2.36.0 | Apache-2.0 |
| feedparser | 6.0.12 | BSD-2-Clause |
| NumPy | 2.4.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |

[Qdrant's source license](https://github.com/qdrant/qdrant/blob/master/LICENSE) is Apache-2.0. Other Python packages and container base images retain their own licenses and notices; the project code license does not replace them. `requirements.lock` records versions, not a complete software bill of materials or license-compliance certification. Review exact distributions and notices before redistributing a prebuilt image. No new runtime dependency was introduced for this release preparation.

The OpenAI Python SDK is used as a client for a configured compatible endpoint. The current default endpoint/model is DeepSeek; there is no claim of a bundled model license or affiliation with a provider. Hosted API terms, costs and data handling are separate from software licenses. Avoid sending confidential input without an appropriate provider agreement.

## News and evaluation data

The public release intentionally withholds original publisher excerpts, quoted raw model outputs and source-level operational snapshots. It includes aggregate measurements and authored synthetic examples only. The full local research archive and unpublished development commits remain intact; they are not ancestors of this release branch. Existing public Git history is preserved.

The synthetic examples are not the corpus used to produce historical Phase 3 metrics. See [evaluation methodology](evaluation.md) for exact reproduction limits. Publicly reachable RSS feeds do not by themselves grant redistribution permission; feed-specific usage restrictions remain in the source registry.

No project code license is added automatically. Retaining the repository without a license is possible, but does not grant general open-source reuse rights. Model and publisher rights remain separate from any future code license.

## Screenshots and historical notes

The new documentation images use authored, explicitly synthetic UI data in a separate temporary database. They are actual browser captures of the existing frontend, not generated mockups or claims about real-world coverage. They avoid redistributing source articles and do not enter the evaluation corpus or existing application database.

Development notes and `PROJECT_HANDOFF.md` remain in the local research repository and are excluded from the public release tree. Already-public development notes and author metadata remain in existing history, which this update does not rewrite.
