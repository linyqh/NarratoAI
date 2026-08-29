# Bundled subtitle fonts

These fonts are bundled into every NarratoAI portable package so startup does not need to download a fallback font.

## Default redistributable fonts

- `SourceHanSansCN-Regular.otf`: Source Han Sans SC Regular. Default clean sans-serif subtitle font.
- `SourceHanSerifSC-SemiBold.otf`: Source Han Serif SC SemiBold. Good for cinematic and narration-heavy subtitles.
- `LXGWWenKaiScreen.ttf`: LXGW WenKai Screen Regular. A warmer Chinese subtitle option tuned for screen reading.

License files for these fonts are kept in `licenses/`.

- Source Han Sans: SIL Open Font License 1.1, Adobe official repository.
- Source Han Serif: SIL Open Font License 1.1, Adobe official repository.
- LXGW WenKai Screen: SIL Open Font License 1.1, LXGW official repository.

## Custom local fonts

Any `.ttf`, `.ttc`, or `.otf` file placed in this directory is copied into the macOS and Windows portable packages.

Current custom fonts:

- `Charm-Bold.ttf`
- `Charm-Regular.ttf`
- `MicrosoftYaHeiBold.ttc`
- `MicrosoftYaHeiNormal.ttc`
- `STHeitiLight.ttc`
- `STHeitiMedium.ttc`
- `UTM Kabel KT.ttf`

Confirm redistribution rights before publishing packages that include custom or operating-system fonts.
