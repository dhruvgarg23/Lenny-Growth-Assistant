"""Static layout-guard tests for the better-layout hardening spec (issue #1).

Single test seam for the layout work: assert externally observable layout
contracts on the declared markup/metadata instead of pixel snapshots. What
these guards cannot cover (supported widths incl. 320px, 200% zoom, RTL
mirror, notched-device safe areas, pseudo-localization + one locale) stays
on the manual browser checklist in the spec.
"""
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "frontend" / "src"
APP = (SRC / "App.jsx").read_text()
CHAT = (SRC / "components" / "ChatPane.jsx").read_text()
SIDEBAR = (SRC / "components" / "SessionSidebar.jsx").read_text()
ARTIFACT = (SRC / "components" / "ArtifactViewer.jsx").read_text()
INDEX_HTML = (REPO / "frontend" / "index.html").read_text()
JSX_FILES = sorted(SRC.rglob("*.jsx"))


def test_session_list_reachable_below_desktop_breakpoint():
    # Docked sidebar (desktop) plus a second, mobile-only rendering path.
    assert APP.count("<SessionSidebar") >= 2
    # A mobile-only disclosure control opens it; the drawer dismisses back.
    assert "md:hidden" in APP
    assert "Close sessions" in APP or "close sessions" in APP.lower()


def test_chrome_clears_notch_and_uses_fluid_viewport():
    assert "viewport-fit=cover" in INDEX_HTML
    assert "env(safe-area-inset-top)" in APP
    assert "env(safe-area-inset-bottom)" in APP
    assert "h-dvh" in APP
    assert "w-screen" not in APP
    assert "h-screen" not in APP


def test_no_physical_direction_utilities():
    banned = [
        r"(?<![\w-])(left|right)-(?=\d)",  # left-0 / right-3 ...
        r"border-[lr](?=[\s\"'`])",  # border-l / border-r
        r"text-(left|right)(?=[\s\"'`])",  # text-left / text-right
        r"(?<![\w-])[mp][lr]-\d",  # ml- / mr- / pl- / pr-
    ]
    hits = []
    for path in JSX_FILES:
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            for pattern in banned:
                if re.search(pattern, line):
                    hits.append(f"{path.name}:{lineno}: {line.strip()}")
    assert not hits, "physical direction utilities must use logical (start/end) forms:\n" + "\n".join(hits)


def test_model_menu_bounded_and_badge_truncates():
    assert "max-w-[calc(100vw-2rem)]" in APP  # menu never exceeds the viewport
    assert "max-w-[38vw]" in APP  # badge label bounded on narrow phones
    assert "truncate" in APP


def test_degraded_status_visible_at_phone_width():
    lines = [line for line in APP.splitlines() if "DB connected" in line or "DB degraded" in line]
    assert lines, " backend/DB status indicator must be rendered"
    assert not any("hidden" in line for line in lines), (
        "degraded status must not hide below a breakpoint:\n" + "\n".join(lines)
    )


def test_fixed_widths_carry_fluid_caps():
    for name, text in (("App.jsx", APP), ("SessionSidebar.jsx", SIDEBAR)):
        for lineno, line in enumerate(text.splitlines(), 1):
            if re.search(r"w-\[(300px|520px)\]", line):
                assert "max-w-" in line, f"{name}:{lineno} fixed width needs a fluid cap"
    # Long session titles wrap (with full text available) instead of hard-clipping.
    assert "break-words" in SIDEBAR
    assert "title={" in SIDEBAR


def test_shared_reading_column_and_margin():
    assert "max-w-2xl" in APP  # composer shares the conversation column width
    assert "max-w-3xl" not in APP
    assert "max-w-2xl" in CHAT


def test_control_breathing_room():
    assert "flex flex-wrap items-center gap-3" in APP  # mode switcher row
    assert "flex items-end gap-3" in APP  # composer input row
    assert "mt-4 flex flex-wrap gap-3" in CHAT  # example tip pills
    assert "flex gap-3" in ARTIFACT  # Copy / Close row
    assert "flex gap-2" not in ARTIFACT


def test_artifact_panel_docks_on_content_fit():
    # Content-derived gate (sidebar 300 + panel ~440 + chat fit), not a device preset.
    assert "xl:" not in APP
    assert "min-[1200px]" in APP
    assert "min(440px" in APP
    assert "Close" in APP  # full-screen viewer keeps its dismiss path


def test_pane_footers_and_frame_stay_stable():
    assert SIDEBAR.count("shrink-0") >= 2  # list header/footer never compress away
    assert "min-h-[520px]" not in ARTIFACT
    assert "dvh" in ARTIFACT


def test_dom_order_matches_reading_order():
    assert APP.index("<header") < APP.index("<SessionSidebar")
    assert APP.index("<SessionSidebar") < APP.index("<ChatPane")
    assert APP.index("<ChatPane") < APP.index("<ArtifactViewer")
