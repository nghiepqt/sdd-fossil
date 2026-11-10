<!-- openspec/specs/hardware-bridge-removal/spec.md -->
# hardware-bridge-removal Specification

## Purpose
TBD - created by archiving change <change>. Update Purpose after archive.
## Requirements
### Requirement: Hardware bridge stub is removed from the workspace
The repository SHALL remove the placeholder `<package>` package because hardware wallet support is provided directly by `<package>`.

#### Scenario: Stub package deleted
- **WHEN** the cleanup change is applied
- **THEN** `<path>` SHALL no longer exist in the repository

#### Scenario: Workspace no longer references stub package
- **WHEN** workspace manifests are evaluated after the cleanup
- **THEN** no package-manager or task-runner config SHALL reference `<package>`
