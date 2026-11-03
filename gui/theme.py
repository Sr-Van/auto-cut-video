"""Tema visual do GUI, espelhando os tokens do design em site/assets/base.css e studio.css."""

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

# --- tokens (site/assets/base.css + studio.css) ---
BG = "#08080c"
BG_2 = "#0b0b10"
PANEL = "#0d0d13"
PANEL_2 = "#16161f"
PANEL_3 = "#1c1c27"
TEXT = "#f6f5f1"
MUTED = "#a4a2b0"
FAINT = "#71707e"
LIME = "#c9ff4f"
LIME_DEEP = "#a5e32c"
VIOLET = "#8b5cf6"
VIOLET_SOFT = "#b79aff"
CORAL = "#ff7a59"
LINE = "rgba(255, 255, 255, 0.075)"
LINE_STRONG = "rgba(255, 255, 255, 0.14)"
LINE_LIME = "rgba(201, 255, 79, 0.28)"


def _pick_font(candidates, fallback):
    families = set(QFontDatabase.families())
    for name in candidates:
        if name in families:
            return name
    return fallback


def stylesheet(sans: str, serif: str, mono: str) -> str:
    return f"""
* {{
    font-family: "{sans}";
    color: {TEXT};
}}
QMainWindow, QDialog, #Root {{
    background: {BG};
}}
QWidget#Root, QScrollArea, QScrollArea > QWidget > QWidget {{
    background: {BG};
}}
QToolTip {{
    background: {PANEL_3};
    color: {TEXT};
    border: 1px solid {LINE_STRONG};
    padding: 6px 8px;
}}

/* ---------- header ---------- */
#Header {{
    background: {BG_2};
    border-bottom: 1px solid {LINE};
}}
#BrandMark {{
    background: {LIME};
    border-radius: 8px;
    color: #0a0b07;
    font-weight: 800;
    font-size: 14px;
}}
#Brand {{
    font-size: 19px;
    font-weight: 700;
    letter-spacing: -0.4px;
}}
#BrandTag {{
    background: transparent;
    border: 1px solid {LINE_STRONG};
    border-radius: 4px;
    color: {FAINT};
    font-family: "{mono}";
    font-size: 9px;
    font-weight: 500;
    padding: 1px 5px;
}}
#ServerPill {{
    background: rgba(201, 255, 79, 0.06);
    border: 1px solid rgba(201, 255, 79, 0.22);
    border-radius: 14px;
    color: {LIME};
    font-family: "{mono}";
    font-size: 11px;
    padding: 4px 12px;
}}

/* ---------- intro ---------- */
#Eyebrow {{
    color: {LIME};
    font-family: "{mono}";
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 1.6px;
}}
#Title {{
    font-size: 32px;
    font-weight: 700;
    letter-spacing: -1px;
}}
#Subtitle, #Muted {{
    color: {MUTED};
    font-size: 13px;
}}
#Faint {{
    color: {FAINT};
    font-size: 11px;
}}
#LocalNote {{
    color: {FAINT};
    font-family: "{mono}";
    font-size: 11px;
}}

/* ---------- panels ---------- */
#Panel {{
    background: {PANEL};
    border: 1px solid {LINE};
    border-radius: 18px;
}}
#SourcePanel {{
    background: {PANEL};
    border: 1px solid rgba(201, 255, 79, 0.20);
    border-radius: 18px;
}}
#PanelTitle {{
    font-size: 18px;
    font-weight: 600;
    letter-spacing: -0.4px;
}}
#PanelTitleCompact {{
    font-size: 15px;
    font-weight: 600;
    letter-spacing: -0.3px;
}}
#FieldLabel {{
    color: {MUTED};
    font-size: 12px;
    font-weight: 500;
}}
#FieldHint {{
    color: {FAINT};
    font-family: "{mono}";
    font-size: 10px;
}}

/* ---------- inputs ---------- */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: rgba(255, 255, 255, 0.03);
    border: 1px solid {LINE_STRONG};
    border-radius: 10px;
    padding: 8px 12px;
    font-size: 13px;
    selection-background-color: {LIME};
    selection-color: #0a0a0d;
}}
QLineEdit#MonoInput {{
    font-family: "{mono}";
    font-size: 12px;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1px solid {LIME};
}}
QLineEdit:read-only {{
    color: {MUTED};
}}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{
    color: {FAINT};
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    width: 0px;
    border: none;
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox QAbstractItemView {{
    background: {PANEL_2};
    border: 1px solid {LINE_STRONG};
    selection-background-color: {PANEL_3};
    selection-color: {LIME};
    outline: none;
    padding: 4px;
}}

/* ---------- botoes ---------- */
QPushButton {{
    background: rgba(255, 255, 255, 0.025);
    border: 1px solid {LINE_STRONG};
    border-radius: 18px;
    padding: 8px 16px;
    font-size: 12px;
    font-weight: 600;
}}
QPushButton:hover {{
    background: rgba(255, 255, 255, 0.06);
    border-color: rgba(255, 255, 255, 0.25);
}}
QPushButton:disabled {{
    color: {FAINT};
    border-color: {LINE};
}}
QPushButton#Primary {{
    background: {LIME};
    color: #0a0b07;
    border: 1px solid {LIME};
    border-radius: 18px;
    font-weight: 700;
}}
QPushButton#Primary:hover {{
    background: {LIME_DEEP};
    border-color: {LIME_DEEP};
}}
QPushButton#Primary:disabled {{
    background: {PANEL_3};
    border-color: {LINE};
    color: {FAINT};
}}
QPushButton#ProcessButton {{
    background: {LIME};
    color: #0a0b07;
    border: none;
    border-radius: 24px;
    padding: 14px;
    font-size: 14px;
    font-weight: 700;
}}
QPushButton#ProcessButton:hover {{
    background: {LIME_DEEP};
}}
QPushButton#ProcessButton:disabled {{
    background: {PANEL_3};
    color: {MUTED};
}}
QPushButton#Ghost {{
    background: rgba(255, 255, 255, 0.025);
    border: 1px solid {LINE_STRONG};
    border-radius: 17px;
    padding: 7px 14px;
    font-size: 12px;
}}
QPushButton#Ghost:hover {{
    background: rgba(255, 255, 255, 0.06);
    border-color: rgba(255, 255, 255, 0.25);
}}
QPushButton#IconBtn {{
    background: rgba(255, 255, 255, 0.025);
    border: 1px solid {LINE};
    border-radius: 8px;
    padding: 4px 8px;
    color: {MUTED};
    font-size: 12px;
}}
QPushButton#IconBtn:hover {{
    border-color: {LINE_STRONG};
    color: {TEXT};
}}
QPushButton#Link {{
    background: transparent;
    border: none;
    color: {FAINT};
    padding: 2px 4px;
    font-size: 11px;
}}
QPushButton#Link:hover {{
    color: {TEXT};
}}

/* abas segmentadas (Link / Arquivo) */
#Segmented {{
    background: rgba(0, 0, 0, 0.25);
    border: 1px solid {LINE};
    border-radius: 9px;
}}
QPushButton#Segment {{
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 5px 14px;
    font-size: 11px;
    font-weight: 500;
    color: {FAINT};
}}
QPushButton#Segment:checked {{
    background: rgba(255, 255, 255, 0.09);
    color: {TEXT};
}}
QPushButton#Segment:hover:!checked {{
    color: {TEXT};
}}

/* abas sublinhadas (.settings-tabs) */
#UnderlineBar {{
    background: {BG};
    border-bottom: 1px solid {LINE};
}}
QPushButton#UnderlineTab {{
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    border-radius: 0px;
    padding: 11px 14px;
    font-size: 12px;
    font-weight: 600;
    color: {FAINT};
}}
QPushButton#UnderlineTab:checked {{
    color: {TEXT};
    border-bottom: 2px solid {LIME};
}}
QPushButton#UnderlineTab:hover:!checked {{
    color: {TEXT};
}}

/* dropzone e arquivo selecionado */
QPushButton#Dropzone {{
    background: rgba(0, 0, 0, 0.16);
    border: 1px dashed rgba(255, 255, 255, 0.16);
    border-radius: 12px;
    padding: 26px 20px;
    color: {MUTED};
    font-size: 12px;
    font-weight: 500;
}}
QPushButton#Dropzone:hover {{
    border-color: {LINE_LIME};
    background: rgba(201, 255, 79, 0.04);
    color: {TEXT};
}}
#FileSelected {{
    background: rgba(201, 255, 79, 0.04);
    border: 1px solid {LINE};
    border-radius: 10px;
}}
#FileSelectedBadge {{
    background: rgba(201, 255, 79, 0.10);
    border-radius: 8px;
    color: {LIME};
    font-weight: 700;
}}

/* ---------- progresso ---------- */
QProgressBar {{
    background: rgba(255, 255, 255, 0.07);
    border: none;
    border-radius: 3px;
    max-height: 5px;
    min-height: 5px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    border-radius: 3px;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
        stop:0 {VIOLET}, stop:1 {LIME});
}}
#StageLabel {{
    color: {MUTED};
    font-family: "{mono}";
    font-size: 11px;
}}
#Percent {{
    color: {LIME};
    font-family: "{mono}";
    font-size: 17px;
    font-weight: 600;
}}
#Step {{
    background: rgba(255, 255, 255, 0.015);
    border: 1px solid {LINE};
    border-radius: 8px;
}}
#Step[state="active"] {{
    border-color: rgba(201, 255, 79, 0.26);
    background: rgba(201, 255, 79, 0.05);
}}
#Step[state="done"] {{
    border-color: {LINE_STRONG};
}}
#Step[state="error"] {{
    border-color: {CORAL};
}}
#StepDot {{
    background: #35343f;
    border-radius: 3px;
    margin-top: 4px;
}}
#Step[state="active"] #StepDot,
#Step[state="done"] #StepDot {{
    background: {LIME};
}}
#Step[state="error"] #StepDot {{
    background: {CORAL};
}}
#StepTitle {{
    font-size: 11px;
    font-weight: 600;
    color: #6c6b77;
}}
#Step[state="active"] #StepTitle {{
    color: {TEXT};
}}
#Step[state="done"] #StepTitle {{
    color: #9695a1;
}}
#StepHint {{
    color: #4a4954;
    font-size: 10px;
}}

QPlainTextEdit#Log {{
    background: rgba(0, 0, 0, 0.25);
    border: 1px solid {LINE};
    border-radius: 9px;
    padding: 10px 12px;
    color: #7b7a87;
    font-family: "{mono}";
    font-size: 11px;
    selection-background-color: {LIME};
    selection-color: #0a0a0d;
}}

/* ---------- resumo e ajuda ---------- */
#SummaryKey {{
    color: {FAINT};
    font-size: 12px;
}}
#SummaryValue {{
    color: {MUTED};
    font-family: "{mono}";
    font-size: 11px;
}}
#Separator {{
    background: rgba(255, 255, 255, 0.045);
    max-height: 1px;
    min-height: 1px;
}}
#MiniPill {{
    background: transparent;
    border: 1px solid {LINE};
    border-radius: 11px;
    color: {MUTED};
    font-family: "{mono}";
    font-size: 10px;
    padding: 2px 8px;
}}
#CodeBlock {{
    background: rgba(0, 0, 0, 0.24);
    border: 1px solid {LINE};
    border-radius: 7px;
    color: {LIME};
    font-family: "{mono}";
    font-size: 11px;
    padding: 8px 10px;
}}

/* ---------- resultados ---------- */
#ResultCard {{
    background: {PANEL};
    border: 1px solid {LINE};
    border-radius: 14px;
}}
#ResultMedia {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #2c2548, stop:1 #0c0b12);
    border: 1px solid {LINE};
    border-radius: 9px;
    color: {LIME};
    font-family: "{mono}";
    font-size: 11px;
}}
#ClipCat {{
    border: 1px solid {LINE};
    border-radius: 9px;
    color: {MUTED};
    font-family: "{mono}";
    font-size: 10px;
    padding: 2px 7px;
}}
#ClipScore {{
    background: rgba(201, 255, 79, 0.12);
    color: {LIME};
    border-radius: 5px;
    font-family: "{mono}";
    font-weight: 600;
    font-size: 11px;
    padding: 2px 7px;
}}
#ClipTime {{
    color: {FAINT};
    font-family: "{mono}";
    font-size: 11px;
}}
#ClipTitle {{
    font-size: 14px;
    font-weight: 600;
}}
#ClipHook {{
    border-left: 2px solid rgba(201, 255, 79, 0.45);
    padding-left: 8px;
    color: #c0bfc9;
    font-size: 12px;
}}
#ClipAnalysis {{
    color: {FAINT};
    font-size: 11px;
}}
#ClipPath {{
    color: #4e4d59;
    font-family: "{mono}";
    font-size: 10px;
}}
#ResultsEmpty {{
    border: 1px dashed {LINE};
    border-radius: 14px;
    color: {FAINT};
    font-size: 12px;
    padding: 28px 18px;
}}

/* ---------- projetos e publicacao ---------- */
QPushButton#PublishedBtn {{
    background: rgba(255, 255, 255, 0.025);
    border: 1px solid {LINE_STRONG};
    border-radius: 14px;
    padding: 5px 12px;
    font-size: 11px;
    font-weight: 600;
    color: {MUTED};
}}
QPushButton#PublishedBtn:hover {{
    background: rgba(34, 197, 94, 0.10);
    border-color: rgba(34, 197, 94, 0.45);
    color: #86efac;
}}
QPushButton#PublishedBtn[published="true"],
QPushButton#PublishedBtn:checked {{
    background: rgba(34, 197, 94, 0.16);
    border: 1px solid #22c55e;
    color: #4ade80;
    font-weight: 700;
}}
QPushButton#PublishedBtn[published="true"]:hover,
QPushButton#PublishedBtn:checked:hover {{
    background: rgba(34, 197, 94, 0.26);
    border-color: #4ade80;
    color: #86efac;
}}
QPushButton#Danger {{
    background: rgba(239, 68, 68, 0.08);
    border: 1px solid rgba(239, 68, 68, 0.35);
    border-radius: 17px;
    padding: 7px 14px;
    font-size: 12px;
    font-weight: 600;
    color: #f87171;
}}
QPushButton#Danger:hover {{
    background: rgba(239, 68, 68, 0.18);
    border-color: #ef4444;
    color: #fca5a5;
}}
#ProjectAccordion {{
    background: {PANEL};
    border: 1px solid {LINE};
    border-radius: 14px;
}}
#ProjectAccordion[expanded="true"] {{
    border: 1px solid rgba(201, 255, 79, 0.24);
}}
QPushButton#ProjectHeaderBtn {{
    background: transparent;
    border: none;
    border-radius: 14px;
    padding: 14px 18px;
    text-align: left;
    font-size: 14px;
    font-weight: 600;
}}
QPushButton#ProjectHeaderBtn:hover {{
    background: rgba(255, 255, 255, 0.025);
}}
#ProjectClipCard {{
    background: rgba(255, 255, 255, 0.02);
    border: 1px solid {LINE};
    border-radius: 12px;
}}


/* ---------- configuracoes ---------- */
#SettingsHead {{
    background: {BG};
    border-bottom: 1px solid {LINE};
}}
#SettingsPreviewBox {{
    background: rgba(0, 0, 0, 0.18);
    border: 1px solid {LINE};
    border-radius: 12px;
}}
#SectionTitle {{
    color: {FAINT};
    font-family: "{mono}";
    font-size: 10px;
    letter-spacing: 1.3px;
    padding-top: 4px;
}}
#Note {{
    color: {FAINT};
    font-size: 11px;
}}
#Footer {{
    background: #101017;
    border-top: 1px solid {LINE};
}}
#StudioFooter {{
    border-top: 1px solid {LINE};
    color: #4c4b57;
    font-family: "{mono}";
    font-size: 10px;
}}

/* ---------- scrollbars ---------- */
QScrollBar:vertical {{
    background: #0a0a0e;
    width: 10px;
    margin: 0px;
}}
QScrollBar::handle:vertical {{
    background: #2a2a35;
    border: 2px solid #0a0a0e;
    border-radius: 5px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: #3a3a48;
}}
QScrollBar::add-line, QScrollBar::sub-line,
QScrollBar::add-page, QScrollBar::sub-page {{
    background: none;
    height: 0px;
    width: 0px;
}}
QScrollBar:horizontal {{
    height: 0px;
}}
QMessageBox QLabel {{
    color: {TEXT};
}}
"""


def apply_theme(app: QApplication):
    """Aplica paleta escura + QSS com os tokens do site."""
    app.setStyle("Fusion")

    sans = _pick_font(["Sora", "Segoe UI Variable Text", "Segoe UI"], "Segoe UI")
    serif = _pick_font(["Instrument Serif", "Georgia"], "Georgia")
    mono = _pick_font(["JetBrains Mono", "Cascadia Code", "Consolas"], "Consolas")

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(BG))
    palette.setColor(QPalette.WindowText, QColor(TEXT))
    palette.setColor(QPalette.Base, QColor(BG_2))
    palette.setColor(QPalette.AlternateBase, QColor(PANEL))
    palette.setColor(QPalette.Text, QColor(TEXT))
    palette.setColor(QPalette.Button, QColor(PANEL_2))
    palette.setColor(QPalette.ButtonText, QColor(TEXT))
    palette.setColor(QPalette.Highlight, QColor(LIME))
    palette.setColor(QPalette.HighlightedText, QColor("#0a0a0d"))
    palette.setColor(QPalette.PlaceholderText, QColor(FAINT))
    palette.setColor(QPalette.ToolTipBase, QColor(PANEL_3))
    palette.setColor(QPalette.ToolTipText, QColor(TEXT))
    app.setPalette(palette)

    font = QFont(sans)
    font.setPointSizeF(10)
    app.setFont(font)
    app.setStyleSheet(stylesheet(sans, serif, mono))
    app.setProperty("serif_family", serif)
