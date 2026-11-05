"""Sistema de design utilitário para o AutoCortesBR (Desktop Dark UI).

Paleta sóbria em tons de grafite neutro, tipografia limpa e cores semânticas
diretas (azul para ação principal, verde para sucesso/publicado, âmbar para
progresso ativo e vermelho para erro/exclusão).
"""

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

# --- Superfícies (Grafite Neutro) ---
BG = "#0F1115"
BG_2 = "#13161C"
PANEL = "#161920"
PANEL_2 = "#1C2029"
PANEL_3 = "#242936"

# --- Tipografia ---
TEXT = "#F3F4F6"
MUTED = "#9CA3AF"
FAINT = "#6B7280"

# --- Ação e Semântica Direta ---
ACCENT = "#2563EB"
ACCENT_HOVER = "#1D4ED8"
ACCENT_SOFT = "rgba(37, 99, 235, 0.14)"
SUCCESS = "#10B981"
SUCCESS_SOFT = "rgba(16, 185, 129, 0.14)"
WARNING = "#F59E0B"
WARNING_SOFT = "rgba(245, 158, 11, 0.14)"
DANGER = "#EF4444"
DANGER_SOFT = "rgba(239, 68, 68, 0.12)"

# --- Bordas ---
LINE = "#232834"
LINE_STRONG = "#32394A"
LINE_ACCENT = "rgba(37, 99, 235, 0.45)"

# Aliases de compatibilidade com módulos existentes
LIME = ACCENT
LIME_DEEP = ACCENT_HOVER
VIOLET = ACCENT
VIOLET_SOFT = "#60A5FA"
CORAL = DANGER
LINE_LIME = LINE_ACCENT


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
    border-radius: 4px;
    padding: 5px 8px;
}}

/* ---------- Header & Navegação ---------- */
#Header {{
    background: {BG_2};
    border-bottom: 1px solid {LINE};
}}
#BrandMark {{
    background: {ACCENT};
    border-radius: 6px;
    color: #FFFFFF;
    font-weight: 700;
    font-size: 12px;
}}
#Brand {{
    font-size: 15px;
    font-weight: 700;
    color: {TEXT};
}}
#BrandTag {{
    background: {PANEL_2};
    border: 1px solid {LINE_STRONG};
    border-radius: 4px;
    color: {MUTED};
    font-family: "{mono}";
    font-size: 10px;
    font-weight: 600;
    padding: 1px 6px;
}}
#NavBar {{
    background: {PANEL};
    border: 1px solid {LINE};
    border-radius: 7px;
}}
QPushButton#NavTab {{
    background: transparent;
    border: none;
    border-radius: 5px;
    padding: 6px 14px;
    font-size: 12px;
    font-weight: 600;
    color: {MUTED};
}}
QPushButton#NavTab:hover:!checked {{
    color: {TEXT};
    background: rgba(255, 255, 255, 0.03);
}}
QPushButton#NavTab:checked {{
    background: {ACCENT};
    color: #FFFFFF;
}}
#StatusPill {{
    background: {PANEL};
    border: 1px solid {LINE_STRONG};
    border-radius: 5px;
    color: {MUTED};
    font-family: "{mono}";
    font-size: 11px;
    padding: 4px 10px;
}}
#StatusPill[state="busy"] {{
    border-color: {WARNING};
    color: {WARNING};
    background: {WARNING_SOFT};
}}
#StatusPill[state="done"] {{
    border-color: {SUCCESS};
    color: {SUCCESS};
    background: {SUCCESS_SOFT};
}}
#StatusPill[state="error"] {{
    border-color: {DANGER};
    color: {DANGER};
    background: {DANGER_SOFT};
}}

/* ---------- Tipografia e Textos ---------- */
#Eyebrow {{
    color: {FAINT};
    font-family: "{mono}";
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.8px;
}}
#Title {{
    font-size: 18px;
    font-weight: 700;
}}
#Subtitle, #Muted {{
    color: {MUTED};
    font-size: 12px;
}}
#Faint, #LocalNote {{
    color: {FAINT};
    font-size: 11px;
}}

/* ---------- Painéis ---------- */
#Panel, #SourcePanel {{
    background: {PANEL};
    border: 1px solid {LINE};
    border-radius: 8px;
}}
#PanelTitle {{
    font-size: 14px;
    font-weight: 600;
    color: {TEXT};
}}
#PanelTitleCompact {{
    font-size: 13px;
    font-weight: 600;
    color: {TEXT};
}}
#FieldLabel {{
    color: {MUTED};
    font-size: 12px;
    font-weight: 500;
}}
#FieldHint {{
    color: {FAINT};
    font-family: "{mono}";
    font-size: 11px;
}}

/* ---------- Inputs ---------- */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit {{
    background: {PANEL_2};
    border: 1px solid {LINE_STRONG};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
    color: {TEXT};
    selection-background-color: {ACCENT};
    selection-color: #FFFFFF;
}}
QLineEdit#MonoInput {{
    font-family: "{mono}";
    font-size: 11px;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{
    border: 1px solid {ACCENT};
}}
QLineEdit:read-only {{
    color: {MUTED};
}}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled, QPlainTextEdit:disabled {{
    color: {FAINT};
    background: {BG_2};
    border-color: {LINE};
}}
QSpinBox::up-button, QSpinBox::down-button,
QDoubleSpinBox::up-button, QDoubleSpinBox::down-button {{
    width: 0px;
    border: none;
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QComboBox QAbstractItemView {{
    background: {PANEL_2};
    border: 1px solid {LINE_STRONG};
    selection-background-color: {ACCENT};
    selection-color: #FFFFFF;
    outline: none;
    padding: 4px;
}}

/* ---------- Botões ---------- */
QPushButton {{
    background: {PANEL_2};
    border: 1px solid {LINE_STRONG};
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 12px;
    font-weight: 600;
    color: {TEXT};
}}
QPushButton:hover {{
    background: {PANEL_3};
    border-color: #434C63;
}}
QPushButton:disabled {{
    color: {FAINT};
    background: {BG_2};
    border-color: {LINE};
}}
QPushButton#Primary {{
    background: {ACCENT};
    color: #FFFFFF;
    border: 1px solid {ACCENT};
    border-radius: 6px;
    font-weight: 600;
}}
QPushButton#Primary:hover {{
    background: {ACCENT_HOVER};
    border-color: {ACCENT_HOVER};
}}
QPushButton#Primary:disabled {{
    background: {PANEL_2};
    border-color: {LINE};
    color: {FAINT};
}}
QPushButton#ProcessButton {{
    background: {ACCENT};
    color: #FFFFFF;
    border: 1px solid {ACCENT};
    border-radius: 6px;
    padding: 10px 16px;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton#ProcessButton:hover {{
    background: {ACCENT_HOVER};
    border-color: {ACCENT_HOVER};
}}
QPushButton#ProcessButton:disabled {{
    background: {PANEL_2};
    border-color: {LINE};
    color: {FAINT};
}}
QPushButton#Ghost {{
    background: {PANEL_2};
    border: 1px solid {LINE_STRONG};
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 12px;
    color: {TEXT};
}}
QPushButton#Ghost:hover {{
    background: {PANEL_3};
    border-color: #434C63;
}}
QPushButton#IconBtn {{
    background: {PANEL_2};
    border: 1px solid {LINE};
    border-radius: 5px;
    padding: 4px 8px;
    color: {MUTED};
    font-size: 12px;
}}
QPushButton#IconBtn:hover {{
    border-color: {LINE_STRONG};
    color: {TEXT};
    background: {PANEL_3};
}}
QPushButton#Link {{
    background: transparent;
    border: none;
    color: {MUTED};
    padding: 2px 6px;
    font-size: 11px;
}}
QPushButton#Link:hover {{
    color: {TEXT};
}}

/* ---------- Abas Segmentadas e Sublinhadas ---------- */
#Segmented {{
    background: {BG_2};
    border: 1px solid {LINE};
    border-radius: 6px;
}}
QPushButton#Segment {{
    background: transparent;
    border: none;
    border-radius: 4px;
    padding: 4px 12px;
    font-size: 11px;
    font-weight: 600;
    color: {MUTED};
}}
QPushButton#Segment:checked {{
    background: {PANEL_3};
    color: {TEXT};
}}
QPushButton#Segment:hover:!checked {{
    color: {TEXT};
}}

#UnderlineBar {{
    background: {BG_2};
    border-bottom: 1px solid {LINE};
}}
QPushButton#UnderlineTab {{
    background: transparent;
    border: none;
    border-bottom: 2px solid transparent;
    border-radius: 0px;
    padding: 10px 14px;
    font-size: 12px;
    font-weight: 600;
    color: {MUTED};
}}
QPushButton#UnderlineTab:checked {{
    color: {TEXT};
    border-bottom: 2px solid {ACCENT};
}}
QPushButton#UnderlineTab:hover:!checked {{
    color: {TEXT};
}}

/* ---------- Dropzone e Arquivo Selecionado ---------- */
QPushButton#Dropzone {{
    background: {BG_2};
    border: 1px dashed {LINE_STRONG};
    border-radius: 6px;
    padding: 18px 16px;
    color: {MUTED};
    font-size: 12px;
    font-weight: 500;
}}
QPushButton#Dropzone:hover {{
    border-color: {ACCENT};
    background: {ACCENT_SOFT};
    color: {TEXT};
}}
#FileSelected {{
    background: {PANEL_2};
    border: 1px solid {LINE_STRONG};
    border-radius: 6px;
}}
#FileSelectedBadge {{
    background: {ACCENT_SOFT};
    border-radius: 5px;
    color: {ACCENT};
    font-weight: 700;
}}

/* ---------- Progresso e Etapas ---------- */
QProgressBar {{
    background: {PANEL_2};
    border: none;
    border-radius: 3px;
    max-height: 6px;
    min-height: 6px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    border-radius: 3px;
    background: {ACCENT};
}}
#StageLabel {{
    color: {TEXT};
    font-family: "{mono}";
    font-size: 11px;
    font-weight: 600;
}}
#Percent {{
    color: {ACCENT};
    font-family: "{mono}";
    font-size: 14px;
    font-weight: 700;
}}
#Step {{
    background: {BG_2};
    border: 1px solid {LINE};
    border-radius: 6px;
}}
#Step[state="active"] {{
    border-color: {WARNING};
    background: {WARNING_SOFT};
}}
#Step[state="done"] {{
    border-color: rgba(16, 185, 129, 0.35);
    background: rgba(16, 185, 129, 0.06);
}}
#Step[state="error"] {{
    border-color: {DANGER};
    background: {DANGER_SOFT};
}}
#StepDot {{
    background: {FAINT};
    border-radius: 3px;
    margin-top: 4px;
}}
#Step[state="active"] #StepDot {{
    background: {WARNING};
}}
#Step[state="done"] #StepDot {{
    background: {SUCCESS};
}}
#Step[state="error"] #StepDot {{
    background: {DANGER};
}}
#StepTitle {{
    font-size: 11px;
    font-weight: 600;
    color: {MUTED};
}}
#Step[state="active"] #StepTitle {{
    color: {TEXT};
}}
#Step[state="done"] #StepTitle {{
    color: {TEXT};
}}
#StepHint {{
    color: {FAINT};
    font-size: 10px;
}}

QPlainTextEdit#Log {{
    background: {BG};
    border: 1px solid {LINE};
    border-radius: 6px;
    padding: 8px 10px;
    color: {MUTED};
    font-family: "{mono}";
    font-size: 11px;
    selection-background-color: {ACCENT};
    selection-color: #FFFFFF;
}}

/* ---------- Resumo e Auxiliares ---------- */
#SummaryKey {{
    color: {FAINT};
    font-size: 12px;
}}
#SummaryValue {{
    color: {TEXT};
    font-family: "{mono}";
    font-size: 11px;
}}
#Separator {{
    background: {LINE};
    max-height: 1px;
    min-height: 1px;
}}
#MiniPill {{
    background: {PANEL_2};
    border: 1px solid {LINE_STRONG};
    border-radius: 4px;
    color: {MUTED};
    font-family: "{mono}";
    font-size: 10px;
    padding: 2px 7px;
}}
#CodeBlock {{
    background: {BG};
    border: 1px solid {LINE};
    border-radius: 5px;
    color: {TEXT};
    font-family: "{mono}";
    font-size: 11px;
    padding: 6px 10px;
}}

/* ---------- Resultados (Cortes) ---------- */
#ResultCard {{
    background: {PANEL};
    border: 1px solid {LINE};
    border-radius: 8px;
}}
#ResultCard:hover {{
    border-color: {LINE_STRONG};
}}
#ResultMedia {{
    background: {BG};
    border: 1px solid {LINE_STRONG};
    border-radius: 6px;
    color: {TEXT};
    font-family: "{mono}";
    font-size: 11px;
    font-weight: 600;
}}
#ResultMedia:hover {{
    border-color: {ACCENT};
    background: {PANEL_2};
}}
#ClipCat {{
    background: {PANEL_2};
    border: 1px solid {LINE_STRONG};
    border-radius: 4px;
    color: {MUTED};
    font-family: "{mono}";
    font-size: 10px;
    font-weight: 600;
    padding: 2px 6px;
}}
#ClipScore {{
    background: {SUCCESS_SOFT};
    color: {SUCCESS};
    border: 1px solid rgba(16, 185, 129, 0.35);
    border-radius: 4px;
    font-family: "{mono}";
    font-weight: 700;
    font-size: 11px;
    padding: 2px 6px;
}}
#ClipScore[tier="mid"] {{
    background: {ACCENT_SOFT};
    color: #60A5FA;
    border: 1px solid rgba(37, 99, 235, 0.35);
}}
#ClipTime {{
    color: {FAINT};
    font-family: "{mono}";
    font-size: 11px;
}}
#ClipTitle {{
    font-size: 13px;
    font-weight: 600;
    color: {TEXT};
}}
#ClipHook {{
    border-left: 2px solid {ACCENT};
    padding-left: 8px;
    color: {MUTED};
    font-size: 12px;
}}
#ClipAnalysis {{
    color: {FAINT};
    font-size: 11px;
}}
#ClipPath {{
    color: {FAINT};
    font-family: "{mono}";
    font-size: 10px;
}}
#ResultsEmpty {{
    background: {BG_2};
    border: 1px dashed {LINE_STRONG};
    border-radius: 6px;
    color: {FAINT};
    font-size: 12px;
    padding: 24px 16px;
}}

/* ---------- Projetos e Publicação ---------- */
QPushButton#PublishedBtn {{
    background: {PANEL_2};
    border: 1px solid {LINE_STRONG};
    border-radius: 5px;
    padding: 5px 10px;
    font-size: 11px;
    font-weight: 600;
    color: {MUTED};
}}
QPushButton#PublishedBtn:hover {{
    background: {SUCCESS_SOFT};
    border-color: {SUCCESS};
    color: {SUCCESS};
}}
QPushButton#PublishedBtn[published="true"],
QPushButton#PublishedBtn:checked {{
    background: {SUCCESS_SOFT};
    border: 1px solid {SUCCESS};
    color: {SUCCESS};
    font-weight: 700;
}}
QPushButton#Danger {{
    background: {DANGER_SOFT};
    border: 1px solid rgba(239, 68, 68, 0.35);
    border-radius: 6px;
    padding: 6px 12px;
    font-size: 12px;
    font-weight: 600;
    color: #F87171;
}}
QPushButton#Danger:hover {{
    background: rgba(239, 68, 68, 0.22);
    border-color: {DANGER};
    color: #FCA5A5;
}}
#ProjectAccordion {{
    background: {PANEL};
    border: 1px solid {LINE};
    border-radius: 8px;
}}
#ProjectAccordion[expanded="true"] {{
    border: 1px solid {LINE_STRONG};
}}
QPushButton#ProjectHeaderBtn {{
    background: transparent;
    border: none;
    border-radius: 8px;
    padding: 12px 16px;
    text-align: left;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton#ProjectHeaderBtn:hover {{
    background: rgba(255, 255, 255, 0.02);
}}
#ProjectClipCard {{
    background: {BG_2};
    border: 1px solid {LINE};
    border-radius: 6px;
}}

/* ---------- Configurações ---------- */
#SettingsHead {{
    background: {BG_2};
    border-bottom: 1px solid {LINE};
}}
#SettingsPreviewBox {{
    background: {PANEL};
    border: 1px solid {LINE};
    border-radius: 8px;
}}
#SectionTitle {{
    color: {FAINT};
    font-family: "{mono}";
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 0.8px;
    padding-top: 2px;
}}
#Note {{
    color: {FAINT};
    font-size: 11px;
}}
#Footer {{
    background: {BG_2};
    border-top: 1px solid {LINE};
}}
#StudioFooter {{
    border-top: 1px solid {LINE};
    color: {FAINT};
    font-family: "{mono}";
    font-size: 10px;
}}

/* ---------- Scrollbars ---------- */
QScrollBar:vertical {{
    background: {BG};
    width: 8px;
    margin: 0px;
}}
QScrollBar::handle:vertical {{
    background: {PANEL_3};
    border-radius: 4px;
    min-height: 28px;
}}
QScrollBar::handle:vertical:hover {{
    background: {LINE_STRONG};
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
    """Aplica paleta utilitária escura e folha de estilo limpa."""
    app.setStyle("Fusion")

    sans = _pick_font(
        ["Segoe UI Variable Text", "Inter", "Segoe UI"], "Segoe UI"
    )
    serif = sans
    mono = _pick_font(
        ["JetBrains Mono", "Cascadia Code", "Consolas"], "Consolas"
    )

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(BG))
    palette.setColor(QPalette.WindowText, QColor(TEXT))
    palette.setColor(QPalette.Base, QColor(PANEL_2))
    palette.setColor(QPalette.AlternateBase, QColor(PANEL))
    palette.setColor(QPalette.Text, QColor(TEXT))
    palette.setColor(QPalette.Button, QColor(PANEL_2))
    palette.setColor(QPalette.ButtonText, QColor(TEXT))
    palette.setColor(QPalette.Highlight, QColor(ACCENT))
    palette.setColor(QPalette.HighlightedText, QColor("#FFFFFF"))
    palette.setColor(QPalette.PlaceholderText, QColor(FAINT))
    palette.setColor(QPalette.ToolTipBase, QColor(PANEL_3))
    palette.setColor(QPalette.ToolTipText, QColor(TEXT))
    app.setPalette(palette)

    font = QFont(sans)
    font.setPointSizeF(9.5)
    app.setFont(font)
    app.setStyleSheet(stylesheet(sans, serif, mono))
    app.setProperty("serif_family", serif)
