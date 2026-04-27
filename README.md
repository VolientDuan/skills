# Skills

语言：**中文** | [English](README.en.md)

这个仓库用于发布和维护 Codex skills，方便通过统一命令安装、更新和同步。

## 目录结构

```text
skills/
  gpt-imagegen/
    SKILL.md
    agents/
    scripts/
```

所有 skill 都放在仓库根目录的 `skills/` 文件夹下，每个 skill 使用独立子目录。

## 已包含的 Skills

- [`gpt-imagegen`](skills/gpt-imagegen/) - 基于 OpenAI 兼容 `gpt-image-2` Images API 的图片生成与图片编辑 skill。

## 安装

使用 `skills` CLI 安装本仓库中的 skills：

```bash
npx skills add VolientDuan/skills
```

## 更新

已安装后，可以使用下面的命令同步最新版本：

```bash
npx skills update VolientDuan/skills
```

## `gpt-imagegen` 配置

`gpt-imagegen` 在生成或编辑图片前需要配置 API base URL 和 API key：

```bash
export GPT_IMAGE_BASE_URL="https://example.com"
export GPT_IMAGE_API_KEY="YOUR_API_KEY"
```

完整工作流和命令示例见 [`skills/gpt-imagegen/SKILL.md`](skills/gpt-imagegen/SKILL.md)。
