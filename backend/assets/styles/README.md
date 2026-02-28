# Art Style Reference Images

Drop one reference image per art style here. The filename must match the art style enum value exactly.

The image is passed to `gemini-3.1-flash-image-preview` alongside the scene prompt for true visual style transfer — Gemini will match the colour palette, textures, and rendering technique of the reference image.

If an image is missing for a style, the system falls back to text-only style guidance (the prompt suffix still applies).

## Required filenames

| Art Style | Filename |
|-----------|----------|
| realism | `realism.png` |
| comic | `comic.png` |
| creepy_comic | `creepy_comic.png` |
| painting | `painting.png` |
| ghibli | `ghibli.png` |
| polaroid | `polaroid.png` |
| disney | `disney.png` |
| monochrome | `monochrome.png` |
| colour_block | `colour_block.png` |
| runway | `runway.png` |
| risograph | `risograph.png` |
| technicolour | `technicolour.png` |
| gothic_clay | `gothic_clay.png` |
| dynamite | `dynamite.png` |
| salon | `salon.png` |
| sketch | `sketch.png` |
| cinematic | `cinematic.png` |
| steampunk | `steampunk.png` |
| sunrise | `sunrise.png` |

## Tips

- Use a representative 9:16 portrait image in the target style (character or scene)
- PNG or JPG both work
- Aim for ~512×910 or larger — smaller images still work but higher quality = better transfer
- The image does NOT need to show the same subject as the video — just needs to exemplify the visual style
