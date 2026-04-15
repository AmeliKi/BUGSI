#!/usr/bin/env python3
"""Generate BUGSI customer presentation from oh22 corporate template."""

from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
import copy

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
TEMPLATE = "Standardvorlage_Präsentation_oh22.pptx"
OUTPUT = "BUGSI_Presentation.pptx"

# Colors (used for manually added shapes on diagram slides)
DARK_BLUE = RGBColor(0, 51, 102)
TEAL = RGBColor(0, 150, 136)
LIGHT_TEAL = RGBColor(224, 242, 241)
LIGHT_GRAY = RGBColor(240, 244, 248)
WHITE = RGBColor(255, 255, 255)
DARK_TEXT = RGBColor(51, 51, 51)
GREEN = RGBColor(76, 175, 80)
ORANGE = RGBColor(255, 152, 0)
LIGHT_ORANGE = RGBColor(255, 243, 224)
LIGHT_GREEN = RGBColor(232, 245, 233)
MEDIUM_GRAY = RGBColor(189, 189, 189)

SLIDE_W = Inches(13.333)
SLIDE_H = Inches(7.5)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def delete_all_slides(prs):
    """Remove every existing slide from the presentation."""
    from pptx.oxml.ns import qn
    sldIdLst = prs.slides._sldIdLst
    for sldId in list(sldIdLst):
        rId = sldId.get(qn("r:id"))
        if rId:
            prs.part.drop_rel(rId)
        sldIdLst.remove(sldId)


def add_slide(prs, layout_index):
    """Add a slide with the given layout index."""
    layout = prs.slide_layouts[layout_index]
    return prs.slides.add_slide(layout)


def set_placeholder(slide, idx, text):
    """Set text on a placeholder by its index."""
    for ph in slide.placeholders:
        if ph.placeholder_format.idx == idx:
            ph.text = text
            return ph
    return None


def fill_content_placeholder(slide, idx, items, font_size=Pt(14)):
    """Fill a placeholder with multiple bullet lines."""
    for ph in slide.placeholders:
        if ph.placeholder_format.idx == idx:
            tf = ph.text_frame
            tf.clear()
            for i, item in enumerate(items):
                if i == 0:
                    p = tf.paragraphs[0]
                else:
                    p = tf.add_paragraph()
                p.text = item
                p.font.size = font_size
            return ph
    return None


def add_text_box(slide, left, top, width, height, text,
                 font_size=Pt(12), bold=False, color=DARK_TEXT,
                 alignment=PP_ALIGN.LEFT, font_name=None):
    """Add a text box shape."""
    txBox = slide.shapes.add_textbox(left, top, width, height)
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = text
    p.font.size = font_size
    p.font.bold = bold
    p.font.color.rgb = color
    p.alignment = alignment
    if font_name:
        p.font.name = font_name
    return txBox


def add_rounded_rect(slide, left, top, width, height,
                     fill_color, text, font_size=Pt(11),
                     text_color=WHITE, bold=True):
    """Add a rounded rectangle shape with centered text."""
    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_color
    shape.line.fill.background()
    tf = shape.text_frame
    tf.word_wrap = True
    tf.paragraphs[0].alignment = PP_ALIGN.CENTER
    tf.paragraphs[0].text = text
    tf.paragraphs[0].font.size = font_size
    tf.paragraphs[0].font.color.rgb = text_color
    tf.paragraphs[0].font.bold = bold
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    return shape


def add_rect(slide, left, top, width, height,
             fill_color, text="", font_size=Pt(11),
             text_color=WHITE, bold=True):
    """Add a plain rectangle shape with centered text."""
    shape = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, left, top, width, height
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill_color
    shape.line.fill.background()
    if text:
        tf = shape.text_frame
        tf.word_wrap = True
        tf.paragraphs[0].alignment = PP_ALIGN.CENTER
        tf.paragraphs[0].text = text
        tf.paragraphs[0].font.size = font_size
        tf.paragraphs[0].font.color.rgb = text_color
        tf.paragraphs[0].font.bold = bold
        tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    return shape


def add_arrow_right(slide, left, top, width, height, color=TEAL):
    """Add a right-pointing arrow shape."""
    shape = slide.shapes.add_shape(
        MSO_SHAPE.RIGHT_ARROW, left, top, width, height
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = color
    shape.line.fill.background()
    return shape


def add_connector_line(slide, start_x, start_y, end_x, end_y,
                       color=MEDIUM_GRAY, width=Pt(2)):
    """Add a straight connector line."""
    connector = slide.shapes.add_connector(
        1, start_x, start_y, end_x, end_y  # 1 = straight
    )
    connector.line.color.rgb = color
    connector.line.width = width
    return connector


def add_callout_box(slide, left, top, width, height, title, text,
                    accent_color=TEAL):
    """Add a callout box with colored left border."""
    # Background rect
    bg = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, left, top, width, height
    )
    bg.fill.solid()
    bg.fill.fore_color.rgb = LIGHT_TEAL
    bg.line.fill.background()
    # Accent bar
    bar = slide.shapes.add_shape(
        MSO_SHAPE.RECTANGLE, left, top, Inches(0.08), height
    )
    bar.fill.solid()
    bar.fill.fore_color.rgb = accent_color
    bar.line.fill.background()
    # Text
    txBox = slide.shapes.add_textbox(
        left + Inches(0.2), top + Inches(0.1),
        width - Inches(0.3), height - Inches(0.2)
    )
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = title
    p.font.size = Pt(12)
    p.font.bold = True
    p.font.color.rgb = DARK_BLUE
    p2 = tf.add_paragraph()
    p2.text = text
    p2.font.size = Pt(11)
    p2.font.color.rgb = DARK_TEXT
    return bg


def add_table(slide, left, top, width, row_height, headers, rows):
    """Add a styled table."""
    n_rows = len(rows) + 1
    n_cols = len(headers)
    table_shape = slide.shapes.add_table(n_rows, n_cols, left, top,
                                          width, row_height * n_rows)
    table = table_shape.table

    # Header row
    for j, hdr in enumerate(headers):
        cell = table.cell(0, j)
        cell.text = hdr
        for p in cell.text_frame.paragraphs:
            p.font.size = Pt(11)
            p.font.bold = True
            p.font.color.rgb = WHITE
            p.alignment = PP_ALIGN.CENTER
        cell.fill.solid()
        cell.fill.fore_color.rgb = DARK_BLUE

    # Data rows
    for i, row in enumerate(rows):
        for j, val in enumerate(row):
            cell = table.cell(i + 1, j)
            cell.text = val
            for p in cell.text_frame.paragraphs:
                p.font.size = Pt(10)
                p.font.color.rgb = DARK_TEXT
                p.alignment = PP_ALIGN.CENTER
            cell.fill.solid()
            cell.fill.fore_color.rgb = LIGHT_GRAY if i % 2 == 0 else WHITE

    return table_shape


# ---------------------------------------------------------------------------
# Slide generators
# ---------------------------------------------------------------------------

def slide_01_title(prs):
    """Slide 1: Title slide."""
    slide = add_slide(prs, 0)
    set_placeholder(slide, 0, "BUGSI")
    set_placeholder(slide, 1,
                    "Autonomous Insect Detection System\n"
                    "Hardware & Software Architecture Overview\n"
                    "April 2026")


def slide_02_agenda(prs):
    """Slide 2: Agenda."""
    slide = add_slide(prs, 2)
    set_placeholder(slide, 0, "Agenda")
    set_placeholder(slide, 13, "Overview of today's presentation")
    fill_content_placeholder(slide, 1, [
        "1.  Project Vision & Requirements",
        "2.  System Overview",
        "3.  Camera System & Design Decisions",
        "4.  Energy & Power Management",
        "5.  Battery Monitoring",
        "6.  Connectivity (LTE & Zigbee)",
        "7.  Cloud Platform (Backend & Frontend)",
        "8.  Security & Authentication",
        "9.  Device Client Software",
        "10. Onboarding & OTA Updates",
        "11. Insect Detection Pipeline",
        "12. Current Status & Roadmap",
    ])


def slide_03_section_vision(prs):
    """Slide 3: Section header - Vision."""
    slide = add_slide(prs, 1)
    set_placeholder(slide, 0, "Project Vision\n& Requirements")
    set_placeholder(slide, 1, "Why we build BUGSI and what it must achieve")


def slide_04_vision(prs):
    """Slide 4: Project vision content."""
    slide = add_slide(prs, 2)
    set_placeholder(slide, 0, "Project Vision")
    set_placeholder(slide, 13, "Autonomous, non-invasive insect monitoring for agriculture")
    fill_content_placeholder(slide, 1, [
        "Non-invasive detection: no traps, no killing - insects fly through freely",
        "Target species: pollinators, pest insects, flying insects (5-60 mm wingspan)",
        "Stakeholders: farmers, research institutions, environmental authorities",
        "Minimum 2 weeks without maintenance; goal: full 8-month season",
        "Operating conditions: 0-40\u00b0C, IP65 enclosure, rain/dust/wind resistant",
        "Detection accuracy target: \u226590% counting accuracy",
        "Solar-powered with LTE connectivity for remote field deployment",
        "Full remote management: configuration, OTA updates, telemetry",
    ])


def slide_05_section_hardware(prs):
    """Slide 5: Section header - Hardware."""
    slide = add_slide(prs, 1)
    set_placeholder(slide, 0, "Hardware\nArchitecture")
    set_placeholder(slide, 1, "Design decisions, components, and rationale")


def slide_06_system_overview(prs):
    """Slide 6: System overview block diagram."""
    slide = add_slide(prs, 7)
    set_placeholder(slide, 0, "System Overview")

    # Central Pi 5
    cx, cy = Inches(5.2), Inches(3.2)
    pw, ph = Inches(2.4), Inches(1.0)
    add_rounded_rect(slide, cx, cy, pw, ph, DARK_BLUE,
                     "Raspberry Pi 5\n4 GB RAM", Pt(13), WHITE)

    # Left side peripherals
    peripherals_left = [
        ("IDS Event Camera\nIMX636 USB3", Inches(1.0), Inches(1.5)),
        ("IDS RGB Camera\nUSB3", Inches(1.0), Inches(3.0)),
        ("Zigbee Coordinator\nClimate Sensor", Inches(1.0), Inches(4.5)),
    ]
    for txt, lx, ly in peripherals_left:
        add_rounded_rect(slide, lx, ly, Inches(2.2), Inches(0.8), TEAL,
                         txt, Pt(10), WHITE)
        add_connector_line(slide, lx + Inches(2.2), ly + Inches(0.4),
                           cx, cy + Inches(0.5))

    # Bottom peripherals
    peripherals_bottom = [
        ("Victron SmartShunt\nBattery Monitor", Inches(3.6), Inches(5.5)),
        ("USB Storage\n64 GB", Inches(6.4), Inches(5.5)),
    ]
    for txt, lx, ly in peripherals_bottom:
        add_rounded_rect(slide, lx, ly, Inches(2.2), Inches(0.8), TEAL,
                         txt, Pt(10), WHITE)
        add_connector_line(slide, lx + Inches(1.1), ly,
                           cx + Inches(1.2), cy + ph)

    # Top: power
    add_rounded_rect(slide, Inches(4.0), Inches(1.2), Inches(2.0), Inches(0.8),
                     RGBColor(255, 193, 7), "Witty Pi 5 HAT+\nDC/DC + RTC + MCU",
                     Pt(10), DARK_TEXT)
    add_connector_line(slide, Inches(5.0), Inches(2.0), cx + Inches(1.2), cy)

    # Right: power source
    add_rounded_rect(slide, Inches(7.2), Inches(1.2), Inches(2.0), Inches(0.7),
                     GREEN, "Solar Panel 50W", Pt(10), WHITE)
    add_rounded_rect(slide, Inches(7.2), Inches(2.2), Inches(2.0), Inches(0.7),
                     GREEN, "MPPT 75/15", Pt(10), WHITE)
    add_rounded_rect(slide, Inches(7.2), Inches(3.2), Inches(2.0), Inches(0.7),
                     GREEN, "LiFePO4 12V 100Ah", Pt(10), WHITE)
    add_connector_line(slide, Inches(8.2), Inches(1.9), Inches(8.2), Inches(2.2))
    add_connector_line(slide, Inches(8.2), Inches(2.9), Inches(8.2), Inches(3.2))
    add_connector_line(slide, Inches(7.2), Inches(2.55), Inches(6.0), Inches(1.6))

    # Right: connectivity
    add_rounded_rect(slide, Inches(9.8), Inches(1.5), Inches(2.2), Inches(0.8),
                     RGBColor(33, 150, 243), "Sixfab LTE\nQuectel EG25-G",
                     Pt(10), WHITE)
    add_connector_line(slide, Inches(9.8), Inches(1.9),
                       cx + pw, cy + Inches(0.3))

    # Far right: cloud
    add_rounded_rect(slide, Inches(10.0), Inches(3.8), Inches(2.4), Inches(1.0),
                     DARK_BLUE, "BUGSI Cloud\nSaaS Platform", Pt(12), WHITE)
    add_arrow_right(slide, Inches(10.5), Inches(2.6), Inches(0.8), Inches(0.5),
                    RGBColor(33, 150, 243))
    add_text_box(slide, Inches(9.9), Inches(2.55), Inches(0.7), Inches(0.5),
                 "LTE", Pt(9), color=RGBColor(33, 150, 243))


def slide_07_event_camera(prs):
    """Slide 7: Event camera details."""
    slide = add_slide(prs, 2)
    set_placeholder(slide, 0, "Event Camera: IDS uEye XLS-E")
    set_placeholder(slide, 13,
                    "Event-driven vision: only transmits pixel changes, "
                    "zero data when nothing moves")
    fill_content_placeholder(slide, 1, [
        "Sensor: Sony IMX636 (neuromorphic event-based vision sensor)",
        "Resolution: 1280 x 720 pixels (0.92 MP) - 9x more than alternatives",
        "Interface: USB 3.0 (5 Gbps) - robust, long-cable capable, bus-powered",
        "Dynamic range: >120 dB (works from dawn to dusk without exposure tuning)",
        "Equivalent frame rate: >10,000 FPS (microsecond temporal resolution)",
        "Power: 0.4-2 W (typically ~1 W) - near-zero when no insects present",
        "Lens: S-Mount (M12) ~3.6mm focal length for wide field of view",
        "Software: IDS Peak SDK + Metavision SDK (Prophesee OpenEB)",
        "",
        "Why event camera? Traditional cameras waste 99%+ of energy capturing",
        "empty frames. Event cameras only consume power when something moves -",
        "perfect for battery-powered field monitoring with sporadic insect activity.",
    ])


def slide_08_rgb_camera(prs):
    """Slide 8: RGB camera details."""
    slide = add_slide(prs, 2)
    set_placeholder(slide, 0, "RGB Camera: High-Resolution Capture")
    set_placeholder(slide, 13,
                    "Triggered only on insect detection - "
                    "full-resolution stored locally, thumbnail uploaded")
    fill_content_placeholder(slide, 1, [
        "Primary: IDS RGB Camera via USB 3.0 (Config A)",
        "Alternative: ArduCam 64MP Hawkeye (9152 x 6944 px) via CSI-2 (Config B)",
        "",
        "Trigger workflow:",
        "  1. Event camera detects motion cluster (insect)",
        "  2. RGB camera captures full-resolution still image",
        "  3. Full image stored on local USB storage (~8 MB each)",
        "  4. 480p thumbnail (~30 KB) uploaded via LTE to cloud",
        "  5. Cooldown period (5-10s) prevents duplicate captures",
        "",
        "Storage: ~50 events/day = ~400 MB local, ~1.5 MB uploaded",
        "All raw images accessible via local web server or USB export",
    ])


def slide_09_camera_decision(prs):
    """Slide 9: Camera comparison table."""
    slide = add_slide(prs, 7)
    set_placeholder(slide, 0, "Design Decision: Camera Selection")

    headers = ["", "IDS uEye XLS-E (Config A)", "Prophesee GenX320 (Config B)"]
    rows = [
        ["Resolution", "1280 x 720 (0.92 MP)", "320 x 320 (0.1 MP)"],
        ["Interface", "USB 3.0 (robust, long cables)", "CSI-2 (FPC, max 30 cm)"],
        ["Power", "0.4-2 W (typ. 1 W)", "<50 mW"],
        ["Dynamic Range", ">120 dB", ">120 dB"],
        ["Sensor", "Sony IMX636 (proven)", "Prophesee (proprietary)"],
        ["Support", "Industrial-grade (IDS)", "Evaluation kit"],
        ["Maturity", "Production ready", "Development stage"],
    ]
    add_table(slide, Inches(0.8), Inches(1.2), Inches(10.5), Inches(0.45),
              headers, rows)

    add_callout_box(
        slide, Inches(0.8), Inches(5.3), Inches(10.5), Inches(1.3),
        "Decision: IDS uEye XLS-E (Config A)",
        "9x higher resolution enables detection of smaller insects (5 mm). "
        "USB 3.0 is mechanically robust for field deployment (vs. fragile 30 cm "
        "flat cable). The ~1 W power difference is negligible against the 1,024 Wh "
        "battery capacity. Industrial support from IDS ensures long-term availability."
    )


def slide_10_energy_system(prs):
    """Slide 10: Energy system block diagram."""
    slide = add_slide(prs, 7)
    set_placeholder(slide, 0, "Energy System Architecture")

    # Solar panel
    add_rounded_rect(slide, Inches(0.8), Inches(1.8), Inches(2.0), Inches(0.9),
                     RGBColor(255, 193, 7), "Solar Panel\n50W Monocrystalline",
                     Pt(11), DARK_TEXT)

    # Arrow
    add_arrow_right(slide, Inches(2.9), Inches(2.0), Inches(0.6), Inches(0.4), TEAL)

    # MPPT
    add_rounded_rect(slide, Inches(3.6), Inches(1.8), Inches(2.2), Inches(0.9),
                     GREEN, "Victron SmartSolar\nMPPT 75/15", Pt(11), WHITE)

    # Arrow
    add_arrow_right(slide, Inches(5.9), Inches(2.0), Inches(0.6), Inches(0.4), TEAL)

    # 12V Bus bar
    add_rect(slide, Inches(6.6), Inches(1.5), Inches(0.15), Inches(3.0),
             ORANGE, "", Pt(9))
    add_text_box(slide, Inches(6.3), Inches(1.0), Inches(0.8), Inches(0.4),
                 "12V Bus", Pt(10), bold=True, color=ORANGE)

    # Battery
    add_rounded_rect(slide, Inches(3.6), Inches(3.6), Inches(2.2), Inches(0.9),
                     RGBColor(33, 150, 243), "LiFePO4 Battery\n12V 100Ah (1,280 Wh)",
                     Pt(11), WHITE)
    add_connector_line(slide, Inches(5.8), Inches(4.0), Inches(6.6), Inches(4.0))

    # SmartShunt
    add_rounded_rect(slide, Inches(3.6), Inches(5.0), Inches(2.2), Inches(0.9),
                     RGBColor(156, 39, 176), "Victron SmartShunt\n500A Coulomb Counter",
                     Pt(10), WHITE)
    add_connector_line(slide, Inches(4.7), Inches(4.5), Inches(4.7), Inches(5.0))
    add_text_box(slide, Inches(2.8), Inches(4.55), Inches(1.6), Inches(0.35),
                 "Battery - path", Pt(9), color=MEDIUM_GRAY)

    # Witty Pi
    add_rounded_rect(slide, Inches(7.4), Inches(1.8), Inches(2.4), Inches(0.9),
                     RGBColor(255, 152, 0), "Witty Pi 5 HAT+\nDC/DC 12V\u21925V + RTC + MCU",
                     Pt(11), DARK_TEXT)
    add_connector_line(slide, Inches(6.75), Inches(2.25), Inches(7.4), Inches(2.25))

    # Arrow to Pi
    add_arrow_right(slide, Inches(9.9), Inches(2.0), Inches(0.6), Inches(0.4), TEAL)

    # Raspberry Pi
    add_rounded_rect(slide, Inches(10.6), Inches(1.5), Inches(2.0), Inches(1.5),
                     DARK_BLUE, "Raspberry Pi 5\n+ Cameras\n+ LTE\n+ Zigbee",
                     Pt(11), WHITE)

    # Key facts at bottom
    add_callout_box(
        slide, Inches(7.4), Inches(3.6), Inches(5.2), Inches(1.0),
        "Key Design Choices",
        "12V single battery (13 kg, within 15 kg limit) | "
        "Witty Pi 5 replaces 3 separate modules (~39 EUR vs ~100+ EUR) | "
        "Wired VE.Direct interfaces (no BLE pairing issues)"
    )

    # VE.Direct labels
    add_text_box(slide, Inches(6.0), Inches(5.15), Inches(1.4), Inches(0.35),
                 "VE.Direct USB", Pt(9), color=MEDIUM_GRAY)
    add_connector_line(slide, Inches(5.8), Inches(5.3), Inches(10.6), Inches(2.8),
                       color=MEDIUM_GRAY, width=Pt(1))


def slide_11_power_scheduling(prs):
    """Slide 11: Power scheduling."""
    slide = add_slide(prs, 2)
    set_placeholder(slide, 0, "Smart Power Scheduling")
    set_placeholder(slide, 13,
                    "Witty Pi 5 HAT+: Three-in-one power management "
                    "(DC/DC + RTC + RP2350 MCU)")
    fill_content_placeholder(slide, 1, [
        "DC/DC Converter: 6-30V input \u2192 5V/5A output (powers Pi via GPIO)",
        "Real-Time Clock: \u00b13.8-5 ppm accuracy, CR2032 backup battery",
        "RP2350 MCU: Runs scheduling scripts independently of Pi OS",
        "",
        "Power Modes:",
        "  Monitoring:  3.5W x 13.5h/day = 47.3 Wh  (event camera active)",
        "  Capture:     7.0W x ~4 min/day = 0.5 Wh   (RGB triggered)",
        "  LTE Upload:  5.0W x ~18 min/day = 1.5 Wh  (on-demand)",
        "  Night/Off:   0.01W x 10h/day = 0.1 Wh     (RTC only)",
        "",
        "Why Witty Pi 5? Replaces separate DC/DC converter + RTC module +",
        "scheduling MCU. One board, ~39 EUR, fewer failure points.",
        "Scheduling survives OS crashes (independent RP2350 MCU).",
    ])


def slide_12_battery_monitoring(prs):
    """Slide 12: Battery monitoring."""
    slide = add_slide(prs, 2)
    set_placeholder(slide, 0, "Precision Battery Monitoring")
    set_placeholder(slide, 13,
                    "LiFePO4 has a flat voltage curve - "
                    "passive monitoring is unreliable")
    fill_content_placeholder(slide, 1, [
        "Problem: LiFePO4 voltage between 20-80% SoC is nearly flat (12.8-13.2V)",
        "  \u2192 Voltage-based estimation has \u00b130% error in the usable range",
        "",
        "Solution: Victron SmartShunt 500A with Coulomb counting",
        "  \u2022 Integrates current over time with Peukert compensation",
        "  \u2022 Auto-sync: resets to 100% when fully charged",
        "  \u2022 Accuracy: \u00b10.4% current, \u00b10.3% voltage",
        "  \u2022 1-second updates via wired VE.Direct serial (not BLE)",
        "",
        "Telemetry data: voltage, current, power, SoC %, consumed Ah, time-to-go",
        "",
        "Why wired VE.Direct? No BLE pairing delays or RF interference.",
        "Deterministic 1-second tick guaranteed. Two USB cables (68 EUR)",
        "provide rock-solid, zero-maintenance data access.",
    ])


def slide_13_energy_budget(prs):
    """Slide 13: Energy budget table."""
    slide = add_slide(prs, 7)
    set_placeholder(slide, 0, "Energy Budget: 18 Days Autonomy Without Sun")

    headers = ["Activity", "Power", "Duration/Day", "Energy/Day"]
    rows = [
        ["Monitoring (Pi + Event Cam)", "3.5 W", "13.5 h", "47.3 Wh"],
        ["Image Capture (50 events)", "7.0 W", "~4 min", "0.5 Wh"],
        ["LTE Upload (6 cycles)", "5.0 W", "~18 min", "1.5 Wh"],
        ["Zigbee Climate Sensor", "0.3 W", "14 h", "4.2 Wh"],
        ["SmartShunt Monitoring", "-", "24 h", "0.1 Wh"],
        ["Night Mode (RTC only)", "0.01 W", "10 h", "0.1 Wh"],
        ["DC/DC Losses (8%)", "-", "-", "+4.3 Wh"],
        ["TOTAL", "", "", "~58 Wh/day"],
    ]
    add_table(slide, Inches(0.5), Inches(1.2), Inches(7.5), Inches(0.42),
              headers, rows)

    # Right side: seasonal balance
    add_text_box(slide, Inches(8.5), Inches(1.2), Inches(4.0), Inches(0.5),
                 "Seasonal Energy Balance", Pt(14), bold=True, color=DARK_BLUE)

    season_data = [
        ("Summer", "~200 Wh", "+142 Wh", GREEN),
        ("Spring/Autumn", "~125 Wh", "+67 Wh", GREEN),
        ("Requirement", "5 days", "18 days", GREEN),
    ]
    for i, (season, solar, surplus, color) in enumerate(season_data):
        y = Inches(1.9) + Inches(0.7) * i
        add_rounded_rect(slide, Inches(8.5), y, Inches(3.8), Inches(0.55),
                         LIGHT_GREEN if color == GREEN else LIGHT_GRAY,
                         f"{season}: Solar {solar}  |  Surplus {surplus}",
                         Pt(11), DARK_TEXT, bold=False)

    # Battery reserve box
    add_callout_box(
        slide, Inches(0.5), Inches(5.5), Inches(11.5), Inches(1.0),
        "Battery Reserve",
        "1,024 Wh usable (80% DoD) \u00f7 58 Wh/day = ~18 days without any sun. "
        "Requirement was 5 days. Positive solar balance in all seasons ensures "
        "indefinite operation during the monitoring season (March-October)."
    )


def slide_14_lte(prs):
    """Slide 14: LTE connectivity."""
    slide = add_slide(prs, 2)
    set_placeholder(slide, 0, "LTE Connectivity: On-Demand Upload")
    set_placeholder(slide, 13,
                    "Sixfab 4G/LTE Kit with Quectel EG25-G - "
                    "GPIO-controlled hardware power cutoff")
    fill_content_placeholder(slide, 1, [
        "Quectel EG25-G: LTE Cat-4 (150 Mbps DL / 50 Mbps UL)",
        "Bands: B1/B3/B7/B8/B20 (full European coverage)",
        "GNSS: GPS, GLONASS, BeiDou, Galileo integrated",
        "",
        "Power strategy: GPIO16 HIGH = modem completely off (0 mA)",
        "  1. GPIO16 LOW \u2192 modem boots (~2s) \u2192 registers (~15s)",
        "  2. Upload ~1.5 MB via HTTPS POST (<1 second at 150 Mbps)",
        "  3. GPIO16 HIGH \u2192 modem off (true hardware cutoff)",
        "  4. Total cycle: ~30 seconds, 6 times/day = ~3 min active",
        "",
        "Data volume: ~1.5 MB/day, ~45 MB/month",
        "SIM: Any Micro SIM card (e.g., 1NCE IoT: 10 EUR / 500 MB / 10 yrs)",
        "",
        "Why LTE (not LoRaWAN)? Full IP = SSH access, OTA updates, remote config.",
        "150 Mbps vs 250 kbps. No gateway infrastructure needed.",
    ])


def slide_15_zigbee(prs):
    """Slide 15: Zigbee sensors."""
    slide = add_slide(prs, 2)
    set_placeholder(slide, 0, "Zigbee Climate Sensors")
    set_placeholder(slide, 13,
                    "Temperature & humidity monitoring with ultra-low-power "
                    "wireless sensors")
    fill_content_placeholder(slide, 1, [
        "Hardware: SONOFF SNZB-02WD or Tuya ZTH01 (IP65, battery-powered)",
        "Coordinator: Silicon Labs EFR32 USB dongle (auto-detected)",
        "",
        "Software stack: zigpy + bellows (pure Python)",
        "  \u2022 Direct library integration, no external processes",
        "  \u2022 Database: SQLite at /var/cache/bugsi/zigbee.db",
        "",
        "Previous approach: zigbee2mqtt + Mosquitto MQTT broker",
        "  \u2022 Required Node.js runtime (~100 MB RAM overhead)",
        "  \u2022 Required MQTT broker process",
        "  \u2022 Complex configuration and pairing",
        "",
        "New approach (zigpy): No Node.js, no MQTT broker, ~100 MB RAM saved.",
        "Single Python process reads sensor data directly.",
        "Auto-detection of dongle serial port and sensor pairing via CLI.",
    ])


def slide_16_section_software(prs):
    """Slide 16: Section header - Software."""
    slide = add_slide(prs, 1)
    set_placeholder(slide, 0, "Software\nArchitecture")
    set_placeholder(slide, 1, "Cloud platform, device client, and detection pipeline")


def slide_17_cloud_platform(prs):
    """Slide 17: Cloud platform."""
    slide = add_slide(prs, 2)
    set_placeholder(slide, 0, "BUGSI Cloud Platform")
    set_placeholder(slide, 13,
                    "Full-stack SaaS for device management, telemetry, and OTA updates")
    fill_content_placeholder(slide, 1, [
        "Backend: FastAPI + SQLAlchemy async + PostgreSQL 16",
        "  \u2022 Async I/O for concurrent device connections",
        "  \u2022 Alembic migrations (auto-run on startup)",
        "  \u2022 OpenTelemetry integration (traces + metrics, Jaeger export)",
        "  \u2022 REST API: telemetry, thumbnails, config, OTA, onboarding",
        "",
        "Frontend: React 19 + TypeScript + Vite + Tailwind CSS",
        "  \u2022 Dashboard with device status, telemetry charts (Recharts)",
        "  \u2022 Device configuration editor with version tracking",
        "  \u2022 OTA deployment management (upload, deploy, track status)",
        "  \u2022 User management with role-based access",
        "  \u2022 i18n: English + German (react-i18next)",
        "",
        "Deployment: Docker Compose (PostgreSQL, Backend, Frontend, opt. Jaeger)",
    ])


def slide_18_security(prs):
    """Slide 18: Security & auth."""
    slide = add_slide(prs, 2)
    set_placeholder(slide, 0, "Security & Authentication")
    set_placeholder(slide, 13,
                    "Multi-layer security with separate auth for users and devices")
    fill_content_placeholder(slide, 1, [
        "User Authentication: JWT tokens (HS256)",
        "  \u2022 Access tokens: 60-minute expiry with unique JTI",
        "  \u2022 Refresh tokens: 7-day expiry, single-use with rotation",
        "  \u2022 httpOnly + SameSite=Strict cookies (prevents XSS + CSRF)",
        "  \u2022 Token blacklist for immediate revocation on logout",
        "",
        "Device Authentication: API Keys",
        "  \u2022 Format: bugsi_{random} (45+ chars), shown once on creation",
        "  \u2022 Storage: SHA-256 hash + 8-char prefix for fast O(1) lookup",
        "  \u2022 Constant-time comparison (hmac.compare_digest)",
        "",
        "Authorization: Role-based (admin/user) + device assignment",
        "Rate Limiting: per-endpoint (login 5/min, telemetry 100/min, OTA 10/min)",
        "Security Headers: HSTS, CSP, X-Frame-Options, X-Content-Type-Options",
        "Audit Logging: all administrative actions tracked with actor + timestamp",
    ])


def slide_19_device_client(prs):
    """Slide 19: Device client architecture diagram."""
    slide = add_slide(prs, 7)
    set_placeholder(slide, 0, "Device Client: Offline-First Daemon")

    # Scheduler box
    add_rect(slide, Inches(0.5), Inches(1.2), Inches(5.5), Inches(2.5),
             LIGHT_GRAY, "", Pt(10))
    add_text_box(slide, Inches(0.7), Inches(1.3), Inches(3.0), Inches(0.3),
                 "Scheduler (Main Loop)", Pt(12), bold=True, color=DARK_BLUE)

    loops = [
        ("Telemetry\nCollect (5 min)", Inches(0.8), Inches(1.8)),
        ("Upload Cycle\n(60 min)", Inches(2.6), Inches(1.8)),
        ("Backup\n(60 min)", Inches(4.4), Inches(1.8)),
    ]
    for txt, lx, ly in loops:
        add_rounded_rect(slide, lx, ly, Inches(1.6), Inches(0.8), TEAL,
                         txt, Pt(9), WHITE)

    # Upload detail
    add_text_box(slide, Inches(0.8), Inches(2.8), Inches(5.0), Inches(0.6),
                 "LTE ON \u2192 Send Telemetry \u2192 Send Thumbnails \u2192 "
                 "Poll Config \u2192 Check OTA \u2192 LTE OFF",
                 Pt(9), color=DARK_TEXT)

    # Buffer Store
    add_rounded_rect(slide, Inches(0.8), Inches(4.0), Inches(2.5), Inches(0.8),
                     DARK_BLUE, "Buffer Store\nSQLite (WAL mode)", Pt(10), WHITE)
    add_connector_line(slide, Inches(2.0), Inches(3.7), Inches(2.0), Inches(4.0))

    # Config Manager
    add_rounded_rect(slide, Inches(3.6), Inches(4.0), Inches(2.5), Inches(0.8),
                     RGBColor(156, 39, 176), "Config Manager\nRemote + Local Fallback",
                     Pt(10), WHITE)

    # Hardware Abstraction Layer
    add_rect(slide, Inches(0.5), Inches(5.2), Inches(5.5), Inches(1.5),
             LIGHT_GRAY, "", Pt(10))
    add_text_box(slide, Inches(0.7), Inches(5.3), Inches(4.0), Inches(0.3),
                 "Hardware Abstraction Layer", Pt(12), bold=True, color=DARK_BLUE)

    hw_modules = [
        "Battery", "Solar", "Climate", "LTE", "Storage", "System"
    ]
    for i, mod in enumerate(hw_modules):
        col = i % 6
        lx = Inches(0.8) + Inches(0.85) * col
        ly = Inches(5.7)
        add_rounded_rect(slide, lx, ly, Inches(0.75), Inches(0.5),
                         GREEN, mod, Pt(8), WHITE, bold=False)

    add_text_box(slide, Inches(0.7), Inches(6.3), Inches(5.0), Inches(0.3),
                 "Real hardware drivers + Mock implementations for development",
                 Pt(9), color=MEDIUM_GRAY)

    # Right side: features
    add_text_box(slide, Inches(6.5), Inches(1.2), Inches(5.5), Inches(0.3),
                 "Key Features", Pt(14), bold=True, color=DARK_BLUE)

    features = [
        "Single Python process (no MQTT broker needed)",
        "SQLite buffer: data safe through power loss",
        "Graceful degradation: missing sensors produce None",
        "CLI: bugsi run | telemetry | config | upload | status",
        "Local web server (aiohttp, port 8080)",
        "  \u2022 Live MJPEG camera stream",
        "  \u2022 Detection image gallery",
        "  \u2022 Config editor (push to cloud)",
        "  \u2022 System status dashboard",
        "Power manager with night/day scheduling",
        "OTA installer with rollback support",
        "85+ automated tests",
    ]
    for i, feat in enumerate(features):
        add_text_box(slide, Inches(6.5), Inches(1.65) + Inches(0.37) * i,
                     Inches(5.5), Inches(0.35), feat, Pt(10), color=DARK_TEXT)


def slide_20_onboarding(prs):
    """Slide 20: Onboarding & OTA."""
    slide = add_slide(prs, 2)
    set_placeholder(slide, 0, "Zero-Touch Deployment & OTA Updates")
    set_placeholder(slide, 13,
                    "Single command onboarding + remote firmware management")
    fill_content_placeholder(slide, 1, [
        "Onboarding: One curl command sets up the entire device",
        '  curl -sfH "X-API-Key: bugsi_..." https://server/api/device-data/onboard | sudo bash',
        "",
        "  Step 1: Save credentials to /mnt/usb/bugsi/credentials.json",
        "  Step 2: Run install_hardware.sh (cameras, Zigbee, LTE, Witty Pi)",
        "  Step 3: Install device client as systemd service (bugsi-daemon)",
        "  Step 4: Install insect detector service (bugsi-detector)",
        "",
        "OTA Update Pipeline:",
        "  1. Admin uploads package (or builds from git commit) in dashboard",
        "  2. Admin deploys to selected device(s)",
        "  3. Device polls during next upload cycle",
        "  4. Downloads package \u2192 SHA-256 verify \u2192 extract \u2192 apply",
        "  5. Reports status: pending \u2192 downloading \u2192 installing \u2192 completed/failed",
        "  Package types: full | daemon_only | config_only | detector_only",
    ])


def slide_21_section_detection(prs):
    """Slide 21: Section header - Detection."""
    slide = add_slide(prs, 1)
    set_placeholder(slide, 0, "Insect Detection\nPipeline")
    set_placeholder(slide, 1,
                    "Event-based real-time clustering and tracking")


def slide_22_detection_pipeline(prs):
    """Slide 22: Detection pipeline diagram."""
    slide = add_slide(prs, 7)
    set_placeholder(slide, 0, "Event-Based Detection Pipeline")

    # Pipeline stages
    stages = [
        ("Event Camera\n(IMX636)", TEAL, Inches(0.3)),
        ("Noise Filter\n(Activity + Trail)", RGBColor(156, 39, 176), Inches(2.5)),
        ("Grid Clustering\n(7x7 px cells)", RGBColor(33, 150, 243), Inches(4.7)),
        ("Object Tracking\n(Nearest-Neighbor)", DARK_BLUE, Inches(6.9)),
        ("Alert + Snapshot\n(Cooldown 2s)", GREEN, Inches(9.1)),
    ]

    for txt, color, lx in stages:
        add_rounded_rect(slide, lx, Inches(1.5), Inches(1.9), Inches(1.0),
                         color, txt, Pt(11), WHITE)

    # Arrows between stages
    for i in range(len(stages) - 1):
        x = stages[i][2] + Inches(1.9)
        add_arrow_right(slide, x, Inches(1.8), Inches(0.5), Inches(0.3), MEDIUM_GRAY)

    # Details below
    details = [
        ("1. Event Stream", "Async pixel-change events from IMX636 sensor. "
         "Only changed pixels are transmitted - no full frames.",
         Inches(0.3), Inches(3.0)),
        ("2. Noise Filtering", "ActivityNoiseFilter removes events <10 ms apart "
         "(hot pixels). TrailFilter removes sensor ghosting artifacts.",
         Inches(0.3), Inches(3.9)),
        ("3. Grid Clustering", "Events quantized into 7x7 px grid cells. "
         "Cells with >10 events activate. Flood-fill groups connected cells into clusters.",
         Inches(0.3), Inches(4.8)),
        ("4. Object Tracking", "Clusters matched frame-to-frame by nearest-neighbor. "
         "Persistent track IDs. Filters by size (10-300 px) to reject noise.",
         Inches(6.0), Inches(3.0)),
        ("5. Alert & Capture", "When valid cluster detected: log event, trigger RGB "
         "camera snapshot, generate thumbnail for cloud upload. 2s cooldown.",
         Inches(6.0), Inches(3.9)),
        ("Configuration", "All parameters tunable via YAML config: grid size, "
         "thresholds, frequency (200 Hz default), min/max object size, motion model.",
         Inches(6.0), Inches(4.8)),
    ]

    for title, desc, lx, ly in details:
        add_text_box(slide, lx, ly, Inches(5.2), Inches(0.3),
                     title, Pt(11), bold=True, color=DARK_BLUE)
        add_text_box(slide, lx, ly + Inches(0.3), Inches(5.2), Inches(0.5),
                     desc, Pt(10), color=DARK_TEXT)

    add_callout_box(
        slide, Inches(0.3), Inches(5.8), Inches(11.5), Inches(0.9),
        "Key Advantage",
        "Operates directly on sparse event coordinates - no image reconstruction "
        "needed for detection. This saves >90% compute vs. traditional frame-based "
        "approaches, enabling real-time processing on Raspberry Pi 5."
    )


def slide_23_section_status(prs):
    """Slide 23: Section header - Status."""
    slide = add_slide(prs, 1)
    set_placeholder(slide, 0, "Current Status\n& Roadmap")
    set_placeholder(slide, 1, "What works today and what comes next")


def slide_24_current_status(prs):
    """Slide 24: Current status checklist."""
    slide = add_slide(prs, 7)
    set_placeholder(slide, 0, "Current Status - April 2026")

    # Hardware column
    add_text_box(slide, Inches(0.5), Inches(1.2), Inches(5.5), Inches(0.4),
                 "Hardware", Pt(16), bold=True, color=DARK_BLUE)

    hw_items = [
        "Hardware installation script (Config A + Config B)",
        "Hardware verification script with automated checks",
        "IDS event camera tested and validated",
        "IDS RGB camera tested and validated",
        "Zigbee integration (zigpy/bellows, auto-detect)",
        "LTE connectivity verified (Sixfab + EG25-G)",
        "Witty Pi 5 power scheduling implemented",
        "Energy budget calculated and validated",
    ]
    for i, item in enumerate(hw_items):
        y = Inches(1.7) + Inches(0.4) * i
        add_rounded_rect(slide, Inches(0.5), y, Inches(0.25), Inches(0.25),
                         GREEN, "\u2713", Pt(10), WHITE)
        add_text_box(slide, Inches(0.9), y, Inches(5.0), Inches(0.35),
                     item, Pt(10), color=DARK_TEXT)

    # Software column
    add_text_box(slide, Inches(6.5), Inches(1.2), Inches(5.5), Inches(0.4),
                 "Software", Pt(16), bold=True, color=DARK_BLUE)

    sw_items = [
        "Full SaaS backend (CRUD, auth, rate limiting)",
        "Frontend dashboard + device management",
        "Config editor with version tracking",
        "OTA deployment pipeline (upload, deploy, track)",
        "Device client daemon with mock hardware",
        "Insect detection pipeline (event clustering)",
        "Docker Compose development environment",
        "Onboarding flow (single curl command)",
        "Telemetry collection + visualization (Recharts)",
        "i18n support (English + German)",
        "85+ backend tests, 30+ device-client tests",
    ]
    for i, item in enumerate(sw_items):
        y = Inches(1.7) + Inches(0.37) * i
        add_rounded_rect(slide, Inches(6.5), y, Inches(0.25), Inches(0.25),
                         GREEN, "\u2713", Pt(10), WHITE)
        add_text_box(slide, Inches(6.9), y, Inches(5.0), Inches(0.35),
                     item, Pt(10), color=DARK_TEXT)


def slide_25_roadmap(prs):
    """Slide 25: Roadmap."""
    slide = add_slide(prs, 7)
    set_placeholder(slide, 0, "Roadmap")

    # Timeline phases
    phases = [
        ("Q2 2026 (Now - June)",
         [
             "Pilot deployment: 3 units in the field",
             "Target date: 30 June 2026",
             "Victron SmartShunt real driver implementation",
             "Victron SmartSolar real driver implementation",
             "Field calibration and counting accuracy baseline",
         ],
         TEAL, Inches(1.2)),
        ("Q3 - Q4 2026",
         [
             "Achieve \u226590% counting accuracy target",
             "8-month autonomous operation validation",
             "GenX320 kernel driver refinements (Config B)",
             "Install script robustness (SD card corruption)",
             "Advanced power management optimization",
         ],
         RGBColor(33, 150, 243), Inches(3.4)),
        ("2027+",
         [
             "Series production planning",
             "Custom carrier board (cost reduction)",
             "ML-based species classification (cloud-side)",
             "Multi-device fleet management dashboard",
             "Integration with agricultural data platforms",
         ],
         ORANGE, Inches(5.6)),
    ]

    for title, items, color, top_y in phases:
        # Phase header
        add_rounded_rect(slide, Inches(0.5), top_y, Inches(3.5), Inches(0.5),
                         color, title, Pt(13), WHITE)
        # Items
        for i, item in enumerate(items):
            y = top_y + Inches(0.6) + Inches(0.3) * i
            add_text_box(slide, Inches(4.3), y, Inches(7.5), Inches(0.3),
                         f"\u2022  {item}", Pt(11), color=DARK_TEXT)

    # Milestone marker
    add_callout_box(
        slide, Inches(0.5), Inches(6.3), Inches(11.5), Inches(0.6),
        "Prototype milestone completed March 2026",
        "Within 1-month timeline and budget. "
        "Next milestone: Pilot with 3 field units by end of June 2026."
    )


def slide_26_summary(prs):
    """Slide 26: Summary."""
    slide = add_slide(prs, 2)
    set_placeholder(slide, 0, "Summary")
    set_placeholder(slide, 13,
                    "Key takeaways from today's presentation")
    fill_content_placeholder(slide, 1, [
        "Event-driven architecture: power consumption only when insects are present",
        "  \u2192 Near-zero idle power vs. traditional cameras",
        "",
        "18-day battery autonomy with positive solar balance in all seasons",
        "  \u2192 Far exceeds 5-day requirement; enables full-season operation",
        "",
        "Full remote management: configuration, OTA updates, SSH access via LTE",
        "  \u2192 No manual visits needed for software updates or config changes",
        "",
        "Offline-first device client: no data loss, graceful degradation",
        "  \u2192 SQLite buffer survives power loss; continues with missing sensors",
        "",
        "Production-ready cloud platform with dashboard, telemetry, and OTA",
        "  \u2192 React frontend + FastAPI backend, Docker deployment",
        "",
        "Prototype complete within timeline and budget",
        "  \u2192 Next: 3 pilot units in the field by June 2026",
    ])


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    prs = Presentation(TEMPLATE)

    # Remove sample slides
    delete_all_slides(prs)

    # Generate all slides
    slide_01_title(prs)
    slide_02_agenda(prs)
    slide_03_section_vision(prs)
    slide_04_vision(prs)
    slide_05_section_hardware(prs)
    slide_06_system_overview(prs)
    slide_07_event_camera(prs)
    slide_08_rgb_camera(prs)
    slide_09_camera_decision(prs)
    slide_10_energy_system(prs)
    slide_11_power_scheduling(prs)
    slide_12_battery_monitoring(prs)
    slide_13_energy_budget(prs)
    slide_14_lte(prs)
    slide_15_zigbee(prs)
    slide_16_section_software(prs)
    slide_17_cloud_platform(prs)
    slide_18_security(prs)
    slide_19_device_client(prs)
    slide_20_onboarding(prs)
    slide_21_section_detection(prs)
    slide_22_detection_pipeline(prs)
    slide_23_section_status(prs)
    slide_24_current_status(prs)
    slide_25_roadmap(prs)
    slide_26_summary(prs)

    prs.save(OUTPUT)
    print(f"Presentation saved: {OUTPUT}")
    print(f"Total slides: {len(prs.slides)}")


if __name__ == "__main__":
    main()
