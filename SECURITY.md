# Security

## How secrets are handled

- Every API key and token (YouTube, Meta, AI providers, ElevenLabs, Pixabay, Typefully) is stored only in
  **GitHub Actions secrets**. None is ever committed, printed to a log or written to a file in this repository.
- Workflows run with the minimum `GITHUB_TOKEN` permissions they need (`contents: write` to save results,
  `actions: write` only for the Clock that starts other workflows).
- OAuth client files and tokens are listed in [`.gitignore`](.gitignore) so they can't be committed by accident.
- Logs in [`logs/`](logs) record what a run did, never credentials or personal data.

## Reporting a vulnerability

Please use **[Report a vulnerability](../../security/advisories/new)** (GitHub private security advisories) rather
than a public issue. Include what you found and how to reproduce it. Reports are acknowledged within a few days.

## Content concerns

To report an error in something FinanceHubW published, or a rights concern about footage, open an issue. Corrections
are logged publicly in [`docs/corrections.json`](docs/corrections.json).
