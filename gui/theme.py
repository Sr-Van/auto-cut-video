"""Sistema de design utilitário para o AutoCortesBR (Desktop Dark UI).

Paleta sóbria em tons de grafite neutro, tipografia limpa e cores semânticas
diretas (azul para ação principal, verde para sucesso/publicado, âmbar para
progresso ativo e vermelho para erro/exclusão).
"""

from pathlib import Path

from PySide6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PySide6.QtWidgets import QApplication

# --- Superfícies (Preto Serpente, neutro sem tom azulado) ---
BG = "#121212"       # Preto Serpente
BG_2 = "#161616"
PANEL = "#1A1A1A"
PANEL_2 = "#212121"
PANEL_3 = "#2B2B2B"

# --- Tipografia ---
TEXT = "#F5F5F4"
MUTED = "#A8A29E"
FAINT = "#8F8A84"  # >= 4.5:1 sobre os paineis (WCAG AA)

# --- Ação e Semântica Direta ---
ACCENT = "#F5C400"        # Amarelo Cobra: acao principal, selecao, destaque
ACCENT_HOVER = "#D9A21B"  # Ouro Escamado: hover, detalhes, icones
ACCENT_SOFT = "rgba(245, 196, 0, 0.12)"
ACCENT_TEXT = "#F5C400"   # amarelo sobre preto ja passa AA para texto
ON_ACCENT = "#121212"     # texto sobre amarelo (branco falharia contraste)
SUCCESS = "#22C55E"
SUCCESS_SOFT = "rgba(34, 197, 94, 0.14)"
WARNING = "#D9A21B"
WARNING_SOFT = "rgba(217, 162, 27, 0.14)"
DANGER = "#EF4444"
DANGER_SOFT = "rgba(239, 68, 68, 0.12)"

# --- Bordas ---
LINE = "#262626"
LINE_STRONG = "#383838"
LINE_ACCENT = "rgba(245, 196, 0, 0.45)"

# Aliases de compatibilidade com módulos existentes
LIME = ACCENT
LIME_DEEP = ACCENT_HOVER
VIOLET = ACCENT
VIOLET_SOFT = ACCENT_HOVER
CORAL = DANGER
LINE_LIME = LINE_ACCENT


ASSETS_DIR = Path(__file__).resolve().parent / "assets"


def _pick_font(candidates, fallback):
    families = set(QFontDatabase.families())
    for name in [*candidates, fallback]:
        if name in families:
            return name
    # Nenhuma candidata instalada: usa a fonte real do sistema.
    return QFontDatabase.systemFont(QFontDatabase.GeneralFont).family()


def stylesheet(sans: str, serif: str, mono: str) -> str:
    assets = ASSETS_DIR.as_posix()
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
    color: {ON_ACCENT};
    font-weight: 700;
    font-size: 12px;
}}
#Brand {{
    font-size: 15px;
    font-weight: 700;
    color: {TEXT};
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
    color: {ON_ACCENT};
}}
#StatusPill {{
    background: {PANEL};
    border: 1px solid {LINE_STRONG};
    border-radius: 5px;
    color: {MUTED};
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
    font-size: 11px;
}}

/* ---------- Inputs ---------- */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit {{
    min-height: 20px;
    background: {PANEL_2};
    border: 1px solid {LINE_STRONG};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 12px;
    color: {TEXT};
    selection-background-color: {ACCENT};
    selection-color: {ON_ACCENT};
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
QSpinBox, QDoubleSpinBox {{
    padding-right: 20px;
}}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 18px;
    border: none;
    border-left: 1px solid {LINE};
    border-top-right-radius: 6px;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 18px;
    border: none;
    border-left: 1px solid {LINE};
    border-bottom-right-radius: 6px;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background: {PANEL_3};
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url("{assets}/chevron-up.svg");
    width: 9px;
    height: 5px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow,
QComboBox::down-arrow {{
    image: url("{assets}/chevron-down.svg");
    width: 9px;
    height: 5px;
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}

/* ---------- Foco por teclado ---------- */
QPushButton:focus, QToolButton:focus, QCheckBox:focus, QRadioButton:focus,
QTabBar::tab:focus, #PresetCard:focus {{
    border: 1px solid {ACCENT_TEXT};
    outline: none;
}}
QComboBox QAbstractItemView {{
    background: {PANEL_2};
    border: 1px solid {LINE_STRONG};
    selection-background-color: {ACCENT};
    selection-color: {ON_ACCENT};
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
    border-color: #4A4A4A;
}}
QPushButton:disabled {{
    color: {FAINT};
    background: {BG_2};
    border-color: {LINE};
}}
QPushButton#Primary {{
    background: {ACCENT};
    color: {ON_ACCENT};
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
    color: {ON_ACCENT};
    border: 1px solid {ACCENT};
    border-radius: 8px;
    padding: 14px 18px;
    font-size: 15px;
    font-weight: 800;
}}
QPushButton#ProcessButton:hover {{
    background: {ACCENT_HOVER};
    border-color: {ACCENT_HOVER};
}}
QPushButton#ProcessButton:disabled {{
    background: {PANEL_2};
    border: 1px solid {LINE};
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
    border-color: #4A4A4A;
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
    color: {ACCENT_TEXT};
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
    font-size: 11px;
    font-weight: 600;
}}
#Percent {{
    color: {ACCENT_TEXT};
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
    border-color: rgba(34, 197, 94, 0.35);
    background: {BG_2};
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
    selection-color: {ON_ACCENT};
}}

/* ---------- Resumo e Auxiliares ---------- */
#SummaryKey {{
    color: {FAINT};
    font-size: 12px;
}}
#SummaryValue {{
    color: {TEXT};
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
    font-size: 10px;
    font-weight: 600;
    padding: 2px 6px;
}}
#ClipScore {{
    background: {SUCCESS_SOFT};
    color: {SUCCESS};
    border: 1px solid rgba(34, 197, 94, 0.35);
    border-radius: 4px;
    font-weight: 700;
    font-size: 11px;
    padding: 2px 6px;
}}
#ClipScore[tier="mid"] {{
    background: {PANEL_2};
    color: {MUTED};
    border: 1px solid {LINE_STRONG};
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
#ProjectHeaderArrow {{
    color: {MUTED};
    font-size: 12px;
}}
#ProjectHeaderTitle {{
    font-size: 13px;
    font-weight: 600;
}}
#ProjectHeaderMeta {{
    color: {MUTED};
    font-size: 11px;
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
    color: {TEXT};
    font-size: 12px;
    font-weight: 600;
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

/* ---------- Fluxo guiado (Cortar) ---------- */
#PageTitle {{
    font-size: 18px;
    font-weight: 800;
    color: {TEXT};
}}
#StepTitleBig {{
    font-size: 15px;
    font-weight: 800;
    color: {TEXT};
}}
#StepNum {{
    border: 1px solid {LINE_STRONG};
    border-radius: 12px;
    color: {MUTED};
    font-size: 11px;
    font-weight: 700;
}}
#StepNum[state="active"] {{
    border-color: {ACCENT};
    color: {ACCENT_TEXT};
}}
#StepNum[state="done"] {{
    border-color: {SUCCESS};
    color: {SUCCESS};
    background: {SUCCESS_SOFT};
}}
#InfoBanner {{
    background: {PANEL_2};
    border: 1px solid {LINE_STRONG};
    border-left: 3px solid {ACCENT};
    border-radius: 6px;
    color: {TEXT};
    font-size: 12px;
    padding: 10px 12px;
}}
#SourceDrop {{
    background: {BG_2};
    border: 1px dashed {LINE_STRONG};
    border-radius: 8px;
}}
#SourceDrop[drag="true"] {{
    border: 1px dashed {ACCENT};
    background: {ACCENT_SOFT};
}}
#SourceHint {{
    color: {FAINT};
    font-size: 11px;
}}
#SourceHint[state="error"] {{
    color: #F87171;
}}
#SourceHint[state="ok"] {{
    color: {SUCCESS};
}}
#FileName {{
    color: {TEXT};
    font-size: 13px;
    font-weight: 700;
}}
#OutputPath {{
    color: {MUTED};
    font-size: 12px;
}}
#WarnText {{
    color: {WARNING};
    font-size: 12px;
}}
#OptionCard {{
    background: {BG_2};
    border: 1px solid {LINE};
    border-radius: 8px;
}}
#OptionCard:hover {{
    border-color: {LINE_STRONG};
}}
#OptionCard[selected="true"] {{
    background: {ACCENT_SOFT};
    border: 1px solid {ACCENT};
}}
#OptionCard:focus {{
    border: 1px solid {ACCENT_TEXT};
}}
#OptionCard:disabled {{
    background: {BG};
}}
#OptionName {{
    color: {TEXT};
    font-size: 12px;
    font-weight: 700;
}}
#OptionCard[selected="true"] #OptionName {{
    color: {ACCENT_TEXT};
}}
#OptionTag {{
    color: {FAINT};
    font-size: 11px;
}}
#PresetStrip {{
    background: #0B0B0B;
    border-radius: 5px;
}}
QPushButton#MoreCard {{
    background: transparent;
    border: 1px dashed {LINE_STRONG};
    border-radius: 8px;
    color: {MUTED};
    font-size: 12px;
}}
QPushButton#MoreCard:hover {{
    border-color: {ACCENT};
    color: {TEXT};
}}
QPushButton#DashedButton {{
    background: transparent;
    border: 1px dashed {LINE_STRONG};
    border-radius: 6px;
    color: {MUTED};
    font-size: 12px;
    padding: 4px 10px;
}}
QPushButton#DashedButton:hover {{
    color: {TEXT};
    border-color: {MUTED};
}}
QPushButton#LinkUnderline {{
    background: transparent;
    border: none;
    color: {MUTED};
    padding: 0px;
    font-size: 12px;
    text-decoration: underline;
}}
QPushButton#LinkUnderline:hover {{
    color: {TEXT};
}}
QPushButton#Link:disabled, QPushButton#LinkUnderline:disabled {{
    background: transparent;
    color: {LINE_STRONG};
}}

#ChoiceSeg {{
    background: {BG_2};
    border: 1px solid {LINE_STRONG};
    border-radius: 6px;
}}
#ChoiceSeg QPushButton#Segment {{
    padding: 6px 10px;
    font-size: 12px;
}}
#ChoiceSeg QPushButton#Segment:checked {{
    background: {ACCENT};
    color: {ON_ACCENT};
    font-weight: 800;
}}
#FilterSeg {{
    background: {BG};
    border: 1px solid {LINE};
    border-radius: 6px;
}}
#FilterSeg QPushButton#Segment {{
    padding: 4px 7px;
}}
#FilterSeg QPushButton#Segment:checked {{
    background: {ACCENT};
    color: {ON_ACCENT};
    font-weight: 800;
}}
#ActionFooter {{
    background: {BG_2};
    border-top: 1px solid {LINE};
}}

/* ---------- Processando ---------- */
#BigPercent {{
    color: {ACCENT_TEXT};
    font-size: 30px;
    font-weight: 800;
}}
#EtaLabel {{
    color: {TEXT};
    font-size: 13px;
    font-weight: 700;
}}
#StepRow {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 7px;
}}
#StepRow[state="active"] {{
    background: {WARNING_SOFT};
    border: 1px solid {WARNING};
}}
#StepRow[state="error"] {{
    background: {DANGER_SOFT};
    border: 1px solid {DANGER};
}}
#StepBadge {{
    border: 1px solid {LINE_STRONG};
    border-radius: 13px;
    color: {MUTED};
    font-size: 11px;
    font-weight: 700;
}}
#StepRow[state="active"] #StepBadge {{
    border-color: {WARNING};
    color: {WARNING};
}}
#StepRow[state="done"] #StepBadge {{
    border-color: {SUCCESS};
    color: {SUCCESS};
    background: {SUCCESS_SOFT};
}}
#StepRow[state="error"] #StepBadge {{
    border-color: {DANGER};
    color: {DANGER};
}}
#StepRowTitle {{
    color: {MUTED};
    font-size: 13px;
    font-weight: 700;
}}
#StepRow[state="active"] #StepRowTitle {{
    color: {ACCENT_TEXT};
}}
#StepRow[state="done"] #StepRowTitle {{
    color: {TEXT};
}}
#StepRowHint {{
    color: {FAINT};
    font-size: 11px;
}}
#StepRowStatus {{
    color: {FAINT};
    font-size: 11px;
}}
#StepRow[state="active"] #StepRowStatus {{
    color: {WARNING};
    font-weight: 700;
}}
#StepRow[state="error"] #StepRowStatus {{
    color: #F87171;
}}
#ErrorBanner {{
    background: {DANGER_SOFT};
    border: 1px solid rgba(239, 68, 68, 0.45);
    border-radius: 8px;
}}
#ErrorTitle {{
    color: #F87171;
    font-size: 14px;
    font-weight: 800;
}}
#ErrorText {{
    color: {TEXT};
    font-size: 12px;
}}

/* ---------- Card de corte ---------- */
#ClipCard {{
    background: {PANEL};
    border: 1px solid {LINE};
    border-radius: 8px;
}}
#ClipCard:hover {{
    border-color: {LINE_STRONG};
}}
#ClipCard[posted="true"] {{
    border: 1px solid {SUCCESS};
}}
#ClipThumbArea {{
    background: #0E0E0E;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
}}
#PubChip {{
    background: {SUCCESS_SOFT};
    border: 1px solid {SUCCESS};
    border-radius: 9px;
    color: {SUCCESS};
    font-size: 10px;
    font-weight: 700;
    padding: 1px 8px;
}}
QPushButton#PostButton {{
    background: {ACCENT};
    border: 1px solid {ACCENT};
    color: {ON_ACCENT};
    font-weight: 800;
    padding: 6px 14px;
}}
QPushButton#PostButton:hover {{
    background: {ACCENT_HOVER};
    border-color: {ACCENT_HOVER};
}}
QPushButton#MarkPublished {{
    background: {SUCCESS_SOFT};
    border: 1px solid {SUCCESS};
    color: {SUCCESS};
    font-weight: 700;
    padding: 6px 12px;
}}
QToolButton#MoreBtn {{
    background: {PANEL_2};
    border: 1px solid {LINE_STRONG};
    border-radius: 6px;
    color: {TEXT};
    font-size: 14px;
    font-weight: 700;
    padding: 3px 9px;
}}
QToolButton#MoreBtn:hover {{
    border-color: {ACCENT};
    color: {ACCENT_TEXT};
}}
QToolButton#MoreBtn::menu-indicator {{
    image: none;
    width: 0px;
}}
QMenu {{
    background: {PANEL_2};
    border: 1px solid {LINE_STRONG};
    border-radius: 8px;
    padding: 6px;
}}
QMenu::item {{
    padding: 7px 14px 7px 10px;
    border-radius: 5px;
    color: {TEXT};
    font-size: 12px;
}}
QMenu::item:selected {{
    background: {PANEL_3};
}}
QMenu::item:disabled {{
    color: {FAINT};
}}
QMenu::separator {{
    height: 1px;
    background: {LINE_STRONG};
    margin: 5px 4px;
}}
#ResultsEmptyBox {{
    background: {BG_2};
    border: 1px dashed {LINE_STRONG};
    border-radius: 8px;
}}

/* ---------- Toast ---------- */
#Toast {{
    background: {PANEL_2};
    border: 1px solid {LINE_STRONG};
    border-left: 3px solid {ACCENT};
    border-radius: 8px;
}}
#ToastIcon {{
    color: {ACCENT_TEXT};
    font-size: 15px;
    font-weight: 800;
}}
#ToastTitle {{
    color: {TEXT};
    font-size: 12px;
    font-weight: 700;
}}
#ToastBody {{
    color: {MUTED};
    font-size: 12px;
}}

/* ---------- Projetos (lista + detalhe) ---------- */
#ProjectsSide {{
    background: {BG_2};
    border-right: 1px solid {LINE};
}}
#ProjectsSideList {{
    background: {BG_2};
}}
#ProjectRow {{
    background: transparent;
    border: none;
    border-bottom: 1px solid {LINE};
    border-left: 3px solid transparent;
}}
#ProjectRow:hover {{
    background: rgba(255, 255, 255, 0.03);
}}
#ProjectRow[selected="true"] {{
    background: {PANEL_2};
    border-left: 3px solid {ACCENT};
}}
#ProjectRow:focus {{
    border-left: 3px solid {ACCENT_TEXT};
}}
#ProjectRowTitle {{
    color: {TEXT};
    font-size: 12px;
    font-weight: 700;
}}
#ProjectRowMeta {{
    color: {FAINT};
    font-size: 11px;
}}
#ProjectRowMeta[missing="true"] {{
    color: {WARNING};
}}
#DetailTitle {{
    color: {TEXT};
    font-size: 17px;
    font-weight: 800;
}}
QPushButton#DangerLink {{
    background: transparent;
    border: none;
    color: {FAINT};
    font-size: 12px;
    padding: 4px 6px;
}}
QPushButton#DangerLink:hover {{
    color: #F87171;
}}
#ListEmpty {{
    color: {FAINT};
    font-size: 12px;
    padding: 24px 16px;
}}

/* ---------- Ajustes (navegação lateral) ---------- */
#SideNav {{
    background: {BG_2};
    border-right: 1px solid {LINE};
}}
QPushButton#SideNavItem {{
    background: transparent;
    border: none;
    border-left: 3px solid transparent;
    border-radius: 6px;
    text-align: left;
    padding: 9px 12px;
    font-size: 13px;
    font-weight: 600;
    color: {MUTED};
}}
QPushButton#SideNavItem:hover:!checked {{
    color: {TEXT};
    background: rgba(255, 255, 255, 0.03);
}}
QPushButton#SideNavItem:checked {{
    background: {PANEL_2};
    border-left: 3px solid {ACCENT};
    color: {TEXT};
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
    background: {BG};
    height: 8px;
    margin: 0px;
}}
QScrollBar::handle:horizontal {{
    background: {PANEL_3};
    border-radius: 4px;
    min-width: 28px;
}}
QMessageBox QLabel {{
    color: {TEXT};
}}
"""


def apply_theme(app: QApplication):
    """Aplica paleta utilitária escura e folha de estilo limpa."""
    app.setStyle("Fusion")

    # JetBrainsMono Nerd Font como fonte única da interface; cai para a
    # JetBrains Mono comum e depois para monoespaçadas do sistema.
    jetbrains = [
        "JetBrainsMono Nerd Font",
        "JetBrainsMono NF",
        "JetBrainsMono Nerd Font Mono",
        "JetBrains Mono",
    ]
    mono = _pick_font([*jetbrains, "Cascadia Code"], "Consolas")
    sans = mono
    serif = sans

    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(BG))
    palette.setColor(QPalette.WindowText, QColor(TEXT))
    palette.setColor(QPalette.Base, QColor(PANEL_2))
    palette.setColor(QPalette.AlternateBase, QColor(PANEL))
    palette.setColor(QPalette.Text, QColor(TEXT))
    palette.setColor(QPalette.Button, QColor(PANEL_2))
    palette.setColor(QPalette.ButtonText, QColor(TEXT))
    palette.setColor(QPalette.Highlight, QColor(ACCENT))
    palette.setColor(QPalette.HighlightedText, QColor(ON_ACCENT))
    palette.setColor(QPalette.PlaceholderText, QColor(FAINT))
    palette.setColor(QPalette.ToolTipBase, QColor(PANEL_3))
    palette.setColor(QPalette.ToolTipText, QColor(TEXT))
    app.setPalette(palette)

    font = QFont(sans)
    font.setPointSizeF(9.5)
    app.setFont(font)
    app.setStyleSheet(stylesheet(sans, serif, mono))
    app.setProperty("serif_family", serif)
