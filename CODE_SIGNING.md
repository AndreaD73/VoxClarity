# Code signing policy

> **Status: planned.** VoxClarity releases are not yet digitally signed. The text below describes the policy
> that will apply once the signing certificate is granted. Until then, Windows SmartScreen may warn about the
> installer (see the README).

Free code signing provided by [SignPath.io](https://signpath.io), certificate by [SignPath Foundation](https://signpath.org).

## What is signed

Only the Windows installer `VoxClarity-Setup-<version>.exe` of this repository
(<https://github.com/AndreaD73/VoxClarity>), built from the tagged source by the GitHub Actions workflow
[`.github/workflows/release.yml`](.github/workflows/release.yml) on a GitHub-hosted runner. The signed
file carries the product name "VoxClarity" and the release version. Third-party components (Python
packages, PyTorch, ffmpeg) are downloaded by the installer from their official sources with pinned
checksums; they are not part of the signed file and are not signed by this project.

## Team roles

| Role | Who | Responsibility |
|---|---|---|
| Author | Andrea D. ([@AndreaD73](https://github.com/AndreaD73)) | Commits the source code |
| Reviewer | Andrea D. ([@AndreaD73](https://github.com/AndreaD73)) | Reviews any change that does not come from the owner |
| Approver | Andrea D. ([@AndreaD73](https://github.com/AndreaD73)) | Approves every signing request, one per release |

The project currently has a single maintainer who holds all three roles. Contributions from other people
are accepted only through pull requests that the owner reviews before merging. All team members use
multi-factor authentication for GitHub and for SignPath.

## Privacy policy

VoxClarity runs entirely on your computer. **No audio, recording, file name, text or personal data is
ever sent to the author or to any third party by the program.** The network connections that exist are:

- **Installation** (`install.ps1`): downloads Python 3.12 (winget or python.org, only if missing), the
  Python packages from PyPI and PyTorch's official package index, and an ffmpeg build from the BtbN
  GitHub project. It sends nothing but the normal web request.
- **First start**: the AI models (about 1 GB) are downloaded once from Hugging Face. Hugging Face
  telemetry is disabled (`HF_HUB_DISABLE_TELEMETRY=1`).
- **"Check for updates" button** (About window): only when you press it, the program asks the GitHub API
  (`api.github.com/repos/AndreaD73/VoxClarity/releases/latest`) for the latest release. The request
  contains the program name and version in the User-Agent header (`VoxClarity/<version>`) and, as for any
  web request, your IP address is visible to GitHub. There is no automatic or background check.
- **"Report a problem" button**: opens a pre-filled GitHub issue page in your browser (version, Windows
  version, graphics card name). Nothing is sent until you submit it yourself.

The program's local server listens only on `127.0.0.1`. There is no telemetry, no analytics and no
account. Logs stay on your PC in `%APPDATA%\VoxClarity\logs`. The installer and uninstaller change nothing
outside the installation folder, your Start-menu/desktop shortcuts and the per-user uninstall entry; the
uninstaller removes what the installer created and asks before deleting your settings.

See also the [Privacy and security section of the README](README.md#privacy-and-security).
