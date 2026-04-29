# Contributing to MantaIt Agent

Thanks for your interest in contributing to MantaIt Agent. This project is an open-source desktop agent for operating professional software, and it improves every time someone shares a real workflow, fixes a rough edge, or adds support for a new app.

This guide explains how to get set up, what we welcome, and how we work together.

## Ways to contribute

- **Software adapters**: add support for new professional apps (Office, design, 3D, video, audio, CAD, and beyond).
- **Skills and workflows**: share reusable creative or productivity workflows that the agent can run.
- **Agent runtime**: improve planning, perception, tool use, memory, or safety.
- **Computer control**: enhance native automation through Windows COM, OS APIs, scripts, and plugins.
- **Examples and demos**: real tasks, screen recordings, before/after results.
- **Documentation**: fix typos, improve guides, translate content, write tutorials.
- **Bug reports and ideas**: open issues with clear repro steps or use cases.

## Getting set up

> The setup flow will evolve as the runtime stabilizes. Check the latest README before starting.

```bash
git clone https://github.com/UseIt-AI/OpenCreativeWork.git
cd OpenCreativeWork
```

Detailed install and run instructions will live in the README under **Install Quick Start**. Contributions to that section are also welcome.

## Working on issues

1. Browse [open issues](https://github.com/UseIt-AI/OpenCreativeWork/issues) or open a new one.
2. Comment on the issue you want to take so we avoid duplicate work.
3. For larger changes (new adapters, runtime changes, breaking APIs), please open an issue or discussion first to align on direction.

## Pull requests

- Keep PRs focused. Smaller PRs review faster and ship sooner.
- Include context: what changed, why, and how to test it.
- Add screenshots, recordings, or logs when they help explain UI or agent behavior.
- Update related docs and examples when behavior changes.
- Run formatters and linters before pushing.

A typical PR description includes:

```text
## Summary
What this PR changes and why.

## How to test
Steps a reviewer can follow to verify the change.

## Notes
Trade-offs, known limitations, follow-ups.
```

## Adding a new software adapter

If you want MantaIt Agent to support a new app, please:

1. Open an issue describing the app, why it matters, and which workflows you want to enable.
2. Note which native interface you plan to use (COM, scripting engine, plugin SDK, app API, etc.).
3. Share an example workflow the adapter should support end to end.
4. Submit a PR with the adapter, sample tasks, and minimal docs.

We prefer real, end-to-end workflows over partial coverage that no one can actually run.

## Coding conventions

- Prefer clarity over cleverness.
- Keep functions and modules small and focused.
- Name things after what they do, not how they do it.
- Avoid comments that just narrate the code; explain intent or trade-offs when helpful.
- Match the existing project style and patterns.

## Issue reports

A good issue includes:

- What you tried to do
- What happened
- What you expected
- Logs, screenshots, or recordings if available
- OS, app versions, and any relevant environment details

## Community and conduct

We want MantaIt Agent to be a friendly, focused, and ambitious community. Be respectful, assume good intent, and help others when you can.

If anything feels off, or you want to discuss a sensitive topic privately, reach out through Discord or open a private issue.

## Thank you

Every adapter, fix, and idea moves this project forward. Thank you for helping AI work with the tools real creators and professionals use every day.
