---
name: PDF Web Publisher
description: Three local themes for a public talk archive and an image-only slide stage.
colors:
  programme-bg: "#f1f3f7"
  programme-surface: "#ffffff"
  programme-ink: "#172139"
  programme-muted: "#536079"
  programme-accent: "#214dcc"
  programme-accent-ink: "#ffffff"
  programme-line: "#ccd2df"
  programme-stage: "#dfe4ee"
  programme-hover: "#e5eafb"
  programme-error: "#a1262e"
  screening-bg: "#151917"
  screening-surface: "#202622"
  screening-ink: "#edf2e9"
  screening-muted: "#adb9aa"
  screening-accent: "#cee598"
  screening-accent-ink: "#192015"
  screening-line: "#3d493f"
  screening-stage: "#0c100e"
  screening-hover: "#2c362b"
  screening-error: "#ffb8af"
  field-bg: "#edf5ef"
  field-surface: "#f9fcf8"
  field-ink: "#17392b"
  field-muted: "#476752"
  field-accent: "#216b46"
  field-accent-ink: "#ffffff"
  field-line: "#b9cfbe"
  field-stage: "#d6e5d9"
  field-hover: "#dcece0"
  field-error: "#a1262e"
typography:
  display:
    fontFamily: '"Segoe UI", "Helvetica Neue", Arial, sans-serif'
    fontSize: "clamp(2.25rem, 5.3vw, 4.5rem)"
    fontWeight: 650
    lineHeight: 1.06
    letterSpacing: "-.035em"
  display-field:
    fontFamily: '"Segoe UI", "Helvetica Neue", Arial, sans-serif'
    fontSize: "clamp(2.25rem, 4.5vw, 3.5rem)"
    fontWeight: 650
    lineHeight: 1.06
    letterSpacing: "-.035em"
  headline:
    fontFamily: '"Segoe UI", "Helvetica Neue", Arial, sans-serif'
    fontSize: "clamp(1.25rem, 2.2vw, 1.8rem)"
    fontWeight: 650
    lineHeight: 1.2
    letterSpacing: "-.025em"
  headline-screening:
    fontFamily: '"Segoe UI", "Helvetica Neue", Arial, sans-serif'
    fontSize: "clamp(1.4rem, 2.5vw, 2rem)"
    fontWeight: 650
    lineHeight: 1.2
    letterSpacing: "-.025em"
  headline-field:
    fontFamily: '"Segoe UI", "Helvetica Neue", Arial, sans-serif'
    fontSize: "21px"
    fontWeight: 650
    lineHeight: 1.2
    letterSpacing: "-.025em"
  title:
    fontFamily: '"Segoe UI", "Helvetica Neue", Arial, sans-serif'
    fontSize: "clamp(1.1rem, 2.3vw, 1.6rem)"
    fontWeight: 650
    lineHeight: 1.25
    letterSpacing: "-.02em"
  body:
    fontFamily: '"Segoe UI", "Helvetica Neue", Arial, sans-serif'
    fontSize: "14px"
    lineHeight: 1.55
  label:
    fontFamily: '"Segoe UI", "Helvetica Neue", Arial, sans-serif'
    fontSize: "13px"
    fontWeight: 650
rounded:
  control: "4px"
spacing:
  "8": "8px"
  "12": "12px"
  "16": "16px"
  "24": "24px"
  "28": "28px"
  "32": "32px"
  "36": "36px"
  "48": "48px"
components:
  control:
    backgroundColor: "transparent"
    textColor: "{colors.programme-ink}"
    rounded: "{rounded.control}"
    padding: "{spacing.12}"
  control-hover:
    backgroundColor: "{colors.programme-hover}"
    textColor: "{colors.programme-accent}"
  control-active:
    backgroundColor: "{colors.programme-accent}"
    textColor: "{colors.programme-accent-ink}"
  search:
    backgroundColor: "{colors.programme-surface}"
    textColor: "{colors.programme-ink}"
    rounded: "{rounded.control}"
    padding: "12px 36px 12px 44px"
  archive-row:
    padding: "28px 0"
  archive-row-screening:
    padding: "36px 0"
  archive-row-field:
    padding: "23px 0"
---

# Design System: PDF Web Publisher

## Overview

**Creative North Star: "Covers, titles, and a viewing stage"**

The archive gives talks a clear place in a programme; the viewer gives each slide the largest uninterrupted region. Three user-pinned themes express the same system through palette, cover size, and catalog density. Local system type and precise outline SVG controls keep the interface subordinate to the published imagery.

The implemented page contract in `scripts/publish.py::render_html` records the intent:

- **THESIS:** Covers and titles orient a public talk archive; slides own the viewing stage.
- **OWN-WORLD:** Programme uses gray/cobalt rows; Screening Room charcoal/large covers; Field Notes mint/numbered entries. Local system type and precise SVG controls.
- **STORY:** Find a talk, open its cover, move through image-only slides, return to the archive.
- **FIRST VIEWPORT:** Archive title and search precede cover/title rows; a deck opens on its fitted slide with navigation directly below.
- **FORM:** user-pinned themes; seed `db88faca`.

**Key Characteristics:**

- Three distinct gallery rhythms; one shared slide viewer.
- Flat surfaces, fine dividers, contained imagery, and restrained accent states.
- Visible keyboard focus and touch-sized controls across themes.

## Colors

Each theme has one primary accent and a complete neutral set. The frontmatter preserves the CSS hex values; the source maps these theme-prefixed names to `--bg`, `--surface`, `--ink`, `--muted`, `--accent`, `--accent-ink`, `--line`, `--stage`, `--hover`, and `--error`.

### Primary

- **Programme cobalt:** navigation, tags, progress, focus, and selected controls.
- **Screening Room pale lime:** the same interaction roles against charcoal.
- **Field Notes forest green:** the same interaction roles against mint.

### Neutral

| Theme | Background and surfaces | Text and structure |
|---|---|---|
| Programme | Cool light gray page, white controls, blue-gray slide stage | Navy ink, slate secondary text, pale gray dividers |
| Screening Room | Charcoal page, green-charcoal surfaces, near-black stage | Off-white ink, sage secondary text, dark green-gray dividers; dark native controls |
| Field Notes | Pale mint page, near-white green surfaces, mint stage | Deep green ink, muted green secondary text, sage dividers |

Error text uses the theme's error color; selected controls pair accent with accent-ink. The sidecar's derived tonal strips are preview metadata, not additional production colors.

## Typography

**Display and body font:** the user-approved local stack, **"Segoe UI", "Helvetica Neue", Arial, sans-serif**. No web-font dependency. Font synthesis is disabled.

Titles use weight (650), tight tracking, and overflow wrapping for long Unicode content; archive and talk titles also use balanced wrapping. The hierarchy is fluid rather than a fixed modular ratio: archive display, talk headline, viewer title, compact body, then labels and metadata. Descriptions stop at (70ch); boot notices stop at (65ch).

At widths up to (640px), the archive title is (42px) in Programme and Screening Room; Field Notes retains its more specific fluid display rule. Talk titles become (19px), (25px), and (18px) respectively. The viewer title becomes (21px). Metadata and descriptions compact to (12px); small footers reach (11px). Slide counters and catalog ordinals use tabular numerals.

## Layout

The body supports a minimum width of (280px). Desktop galleries share minimum (48px) side gutters and a title/search header; search is (320px) wide. Fine horizontal rules separate whole-row links.

| Theme | Maximum gallery width | Desktop row |
|---|---|---|
| Programme | 1160px | 264px cover, flexible details, trailing action; 32px gap; 28px vertical padding |
| Screening Room | 1240px | Cover at minmax(280px, 43%); details and action stacked alongside; 40px gap; 36px vertical padding |
| Field Notes | 1060px | 36px ordinal, 160px cover, flexible details, action; 24px gap; 23px vertical padding |

At (960px), galleries use (24px) gutters and a (280px) search field; covers narrow and action labels hide. At (640px), gutters become (18px), the header stacks, and search fills the width. Programme keeps a (110px) cover beside text. Screening Room becomes a full-width cover above details and restores the written action. Field Notes retains its ordinal with an (82px) cover. Whole rows remain links when the visible action is hidden.

The shared viewer caps at (1440px), with minimum (36px) desktop gutters, (20px) gutters below (960px), and edge-to-edge content below (640px). Its stage height is `clamp(240px, 65vh, 840px)`, changing to `clamp(230px, 49vh, 640px)` on mobile. Canvas dimensions are bounded by the stage without cropping. Covers and thumbnails use a (16:9) frame and contain the source image.

Thumbnails use an auto-fill grid with (130px) minimum cells and (16px) gaps; mobile uses (95px) and (10px). The panel scrolls within `min(65vh, 600px)`, or (40vh) when expanded.

## Elevation & Depth

There are no shadows. Page, surface, and stage tones establish depth; (1px) dividers establish structure. Fullscreen uses the same palette. Its fixed fallback fills (100dvh), locks page scroll, and sits above the archive at z-index (20); the focus-revealed skip link uses (30).

## Shapes

Imagery, catalog rows, the player, and progress strip remain rectangular. Only buttons and inputs use the small control radius (4px). Icons are (20px) within a (24-unit) viewBox, with rounded joins/caps and stroke width (1.65). The thumbnail selection is a (2px) accent border; the progress strip is (3px) high.

## Components

### Archive rows, tags, and search

An entire cover/title row is the navigation target. Hover turns its title to the accent with a fine underline and shifts its arrow (4px). Tags are plain accent text prefixed with `#`, not separate filter buttons. Search has a persistent label, a leading icon, themed fill and (1px) border, minimum height (48px), and inset text. Results announce a count; empty and missing-cover states use short explanatory text.

### Viewer controls and navigation

Controls have minimum dimensions (44 × 44px), (12px) padding, and a transparent resting fill. Hover uses hover/accent; expanded or pressed controls use accent/accent-ink. Disabled controls have opacity (.38). The back link retains a minimum height of (44px). Mobile hides control labels while preserving accessible labels.

**The Visible Focus Rule.** Keyboard focus uses a (3px) accent outline with (4px) offset; do not remove it.

Arrow/Page keys navigate, Home/End jump, T opens thumbnails, F expands, and Escape closes temporary views. Horizontal swipes navigate while vertical panning and pinch zoom remain available. The counter announces position; loading is a status and errors are alerts with Retry. Thumbnails identify the current slide and return focus to the stage after selection. Expanded fallback mode contains keyboard focus, makes obscured siblings inert, and restores the prior focus on exit.

Only the row arrow (.2s) and progress fill (.22s) transition, both with `cubic-bezier(.16, 1, .3, 1)`. Reduced-motion preference disables transitions and animations and restores automatic scroll behavior.

### Print

Printing hides the viewer, its heading and hint, gallery imagery and search, and the skip link. A viewer prints the on-screen-viewing notice. The root print colors become black on white.

## Do's and Don'ts

### Do:

- **Do** keep all three palettes paired with their implemented gallery layouts.
- **Do** fit source slides and covers without cropping their content.
- **Do** preserve labeled controls, visible focus, and the mobile control sizes.
- **Do** use the approved local font stack and shared viewer behavior.

### Don't:

- **Don't** turn catalog tags into filter controls without implementing that behavior.
- **Don't** replace image-led viewing with decorative interface panels.
- **Don't** remove the reduced-motion or print treatments.

