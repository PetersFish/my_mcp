---
name: media-ocr-router
description: Route clipboard images, local image paths, and Markdown-embedded media through the best available image workflow. Use when the user asks to inspect a screenshot, copied image, local image path, or Markdown file with images/videos, especially when the model may support multimodal input and you should prefer `load_image` / `load_markdown_images` / `load_markdown_media` before falling back to any non-`load*` tool. Keep this quiet for non-image tasks.
---

# Media OCR Router

## Purpose

Use this skill to turn clipboard images, local image paths, or Markdown-embedded media into the right image-processing path.

The preferred order is:

1. Capture the clipboard image when the user copied a screenshot **and** a clipboard tool is available
2. Prefer `load_image` for a single local image when the current model and client can keep image content in the model context
3. Prefer `load_markdown_images` or `load_markdown_media` when the user gives a Markdown file with embedded images or media and the client can keep MCP image/resource content in context
4. If the media is loaded successfully, directly inspect them yourself and write the descriptions back under the corresponding image entries
5. Fall back to `describe_image` when direct image routing is unavailable or uncertain
6. Use `extract_image_text` or `extract_markdown_image_text` only when the user wants exact transcription and the model cannot directly inspect the loaded media

## Tool names

This skill talks to the `ocr-vlm` MCP server. Use the name your host exposes:

| Capability | OpenCode / Cursor | Claude Code |
| --- | --- | --- |
| load image | `ocr-vlm_load_image` | `mcp__ocr-vlm__load_image` |
| load markdown images | `ocr-vlm_load_markdown_images` | `mcp__ocr-vlm__load_markdown_images` |
| load markdown media | `ocr-vlm_load_markdown_media` | `mcp__ocr-vlm__load_markdown_media` |
| describe image | `ocr-vlm_describe_image` | `mcp__ocr-vlm__describe_image` |
| extract image text | `ocr-vlm_extract_image_text` | `mcp__ocr-vlm__extract_image_text` |
| extract markdown image text | `ocr-vlm_extract_markdown_image_text` | `mcp__ocr-vlm__extract_markdown_image_text` |

In the steps below, `load_image` / `describe_image` / `extract_*` mean whichever host-specific name applies.

`clipboard_image` is **optional** and is not part of `ocr-vlm`. If that tool is missing, skip the clipboard step and ask the user for a local image path.

## When To Use

- The user asks to inspect, describe, or analyze a clipboard screenshot
- The user provides a local image path and wants the model to look at the image
- The user provides a Markdown file with embedded images or videos and wants the content inspected
- The user asks whether to use direct image loading or a non-`load*` fallback
- The current model appears to support multimodal input and direct image loading should be tried first

## Do NOT Use When

- The task is unrelated to images
- The user only wants text OCR and not image interpretation
- The model/client cannot handle image content and the user explicitly wants a text-only fallback path

If the current model is clearly non-vision, skip the direct-image branch and go straight to a non-`load*` fallback such as `describe_image` or `extract_image_text`.

## Routing Rules

### Step 1: Decide the entry point

- If the user says they copied an image or screenshot and `clipboard_image` is available, call it first.
- If `clipboard_image` is unavailable, tell the user the clipboard tool is not installed and ask for a local image path.
- If the user already gave a local file path, use that path directly.

### Step 2: Prefer direct image loading when possible

- If the current model supports image input and the client is expected to preserve MCP image content, call `load_image`.
- Use this path for visual understanding, UI review, architecture diagrams, and other tasks where the model should inspect the image itself.

### Step 2b: Prefer Markdown media loading for embedded assets

- If the user points at a Markdown file that embeds local images or videos, call `load_markdown_images` or `load_markdown_media` first.
- Use `load_markdown_images` when the file only needs image loading.
- Use `load_markdown_media` when the file mixes images and videos or the user asked for all embedded media.
- After loading succeeds, directly inspect the loaded media yourself and append the interpretation beneath each matching image or media reference.
- Only use `extract_markdown_image_text` if the model cannot directly inspect the loaded media or the user explicitly asked for OCR transcription.

### Step 3: Fall back when direct routing is uncertain

- If the current model is non-vision, or the client may not pass image content back into context, call a non-`load*` fallback such as `describe_image`.
- If the user wants exact text, call `extract_image_text` instead of description.

## Required Steps

1. Get the image path from `clipboard_image` when that tool exists, otherwise from the user's local path.
2. Choose `load_image` first when multimodal routing is supported for a single image.
3. Choose `load_markdown_images` or `load_markdown_media` first when the input is a Markdown file with embedded media.
4. If loading succeeds, directly inspect the loaded media yourself and write the result below each corresponding reference.
5. Otherwise choose a non-`load*` fallback such as `describe_image`.
6. If the user explicitly wants exact characters or OCR output, choose `extract_image_text` or `extract_markdown_image_text`.

## Error Handling

- If `clipboard_image` is unavailable, ask the user to provide a local image path. Do not treat this as a hard failure.
- If `clipboard_image` returns an error, tell the user no image was found in the clipboard and ask them to copy one first or provide a path.
- If `load_image` is unavailable in the current client path, fall back to a non-`load*` tool such as `describe_image`.
- If Markdown media loading is unavailable or returns partial results, fall back to direct per-image processing or another non-`load*` tool.
- If the model cannot directly inspect loaded Markdown media, use `extract_markdown_image_text` as the non-`load*` fallback.
- If the VLM fallback fails, surface the failure and suggest retrying or switching to OCR-only transcription.

## Multiple Images

Process multiple images one at a time:

1. Copy or point to image 1 → get the path → choose direct load or fallback → return the result
2. Copy or point to image 2 → repeat
3. Continue as needed

Each call to `clipboard_image` overwrites the previous file, so process images sequentially when that tool is available.
