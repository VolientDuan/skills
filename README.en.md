# Skills

Language: [中文](README.md) | **English**

This repository publishes and maintains Codex skills that can be installed, updated, and synced with a standard command workflow.

## Structure

```text
skills/
  gpt-imagegen/
    SKILL.md
    agents/
    scripts/
```

All skills live under the repository-level `skills/` directory. Each skill uses its own subdirectory.

## Included Skills

- [`gpt-imagegen`](skills/gpt-imagegen/) - Image generation and image editing skill powered by an OpenAI-compatible `gpt-image-2` Images API.

## Installation

Install the skills from this repository with the `skills` CLI:

```bash
npx skills add VolientDuan/skills
```

## Update

After installation, sync the latest version with:

```bash
npx skills update VolientDuan/skills
```

## `gpt-imagegen` Configuration

The `gpt-imagegen` skill requires an API base URL and API key before it can generate or edit images:

```bash
export GPT_IMAGE_BASE_URL="https://example.com"
export GPT_IMAGE_API_KEY="YOUR_API_KEY"
```

See [`skills/gpt-imagegen/SKILL.md`](skills/gpt-imagegen/SKILL.md) for full workflow details and command examples.

## Share
🌅 [2026-04-27] Special Share. Core contributor's share on [Linux.do](https://linux.do/).
