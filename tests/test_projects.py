import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton

from gui.main_window import MainWindow
from gui.clip_card import ClipCard
from gui.projects_dialog import (
    ProjectsDialog,
    open_upload_pages,
    reveal_in_explorer,
)
from utils.report import (
    compute_average_viral_score,
    delete_project,
    load_projects_registry,
    load_report,
    register_project,
    remove_missing_projects,
    save_report,
    update_clip_published,
)


class TestProjectsRegistryAndDialog(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_save_report_includes_published_and_toggle(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out_dir = Path(tmp) / "meu_video"
            clips = [
                {
                    "start": "00:00:10",
                    "end": "00:00:45",
                    "hook": "00:00:12",
                    "category": "EDUCATIVO",
                    "viral_score": 9,
                    "title": "Dica rapida",
                },
                {
                    "start": "00:01:00",
                    "end": "00:01:40",
                    "hook": "00:01:05",
                    "category": "POLÊMICO",
                    "viral_score": 10,
                    "title": "Opiniao forte",
                    "published": True,
                },
            ]
            clip_paths = [
                str(out_dir / "Dica rapida.mp4"),
                str(out_dir / "Opiniao forte.mp4"),
            ]
            report_path = save_report(clips, out_dir, clip_paths)

            loaded = load_report(report_path)
            self.assertEqual(len(loaded), 2)
            self.assertFalse(loaded[0]["published"])
            self.assertTrue(loaded[1]["published"])
            self.assertEqual(loaded[0]["file"], clip_paths[0])

            # Toggle published do primeiro clipe
            updated = update_clip_published(report_path, 0, True)
            self.assertTrue(updated[0]["published"])

            reloaded = load_report(report_path)
            self.assertTrue(reloaded[0]["published"])

            # Verifica se o CSV tambem contem a coluna published atualizada
            csv_text = (out_dir / "relatorio.csv").read_text(encoding="utf-8")
            self.assertIn("published", csv_text)
            self.assertIn("True", csv_text)

    def test_register_and_order_projects_newest_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            reg_path = Path(tmp) / "projetos.json"
            dir_old = Path(tmp) / "video_antigo"
            dir_new = Path(tmp) / "video_novo"

            clips_old = [{"viral_score": 8}, {"viral_score": 9}]
            rep_old = save_report(clips_old, dir_old)
            entry_old = register_project(
                video_name="video_antigo",
                project_dir=dir_old,
                report_path=rep_old,
                clips=clips_old,
                registry_path=reg_path,
            )
            self.assertEqual(entry_old["clips_count"], 2)
            self.assertAlmostEqual(entry_old["average_viral_score"], 8.5)

            # Forca timestamp anterior para garantir teste de ordenacao
            data = json.loads(reg_path.read_text(encoding="utf-8"))
            data[0]["created_at"] = "2026-01-01T10:00:00"
            reg_path.write_text(json.dumps(data), encoding="utf-8")

            clips_new = [
                {"viral_score": 10},
                {"viral_score": 9},
                {"viral_score": 8},
            ]
            rep_new = save_report(clips_new, dir_new)
            entry_new = register_project(
                video_name="video_novo",
                project_dir=dir_new,
                report_path=rep_new,
                clips=clips_new,
                registry_path=reg_path,
            )
            self.assertEqual(entry_new["clips_count"], 3)
            self.assertAlmostEqual(entry_new["average_viral_score"], 9.0)

            projects = load_projects_registry(reg_path)
            self.assertEqual(len(projects), 2)
            self.assertEqual(projects[0]["video_name"], "video_novo")
            self.assertEqual(projects[1]["video_name"], "video_antigo")

    def test_delete_project_removes_entire_folder_and_registry_entry(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            reg_path = Path(tmp) / "projetos.json"
            proj_dir = Path(tmp) / "projeto_para_excluir"
            proj_dir.mkdir(parents=True)
            dummy_clip = proj_dir / "corte_1.mp4"
            dummy_clip.write_bytes(b"mp4data")
            rep_path = save_report(
                [{"viral_score": 10, "title": "Corte 1"}],
                proj_dir,
                [str(dummy_clip)],
            )

            register_project(
                video_name="projeto_para_excluir",
                project_dir=proj_dir,
                report_path=rep_path,
                clips=[{"viral_score": 10, "title": "Corte 1"}],
                clip_paths=[str(dummy_clip)],
                registry_path=reg_path,
            )
            self.assertTrue(proj_dir.exists())
            self.assertEqual(len(load_projects_registry(reg_path)), 1)

            delete_project(proj_dir, registry_path=reg_path)
            self.assertFalse(proj_dir.exists())
            self.assertEqual(len(load_projects_registry(reg_path)), 0)

    def test_main_window_header_has_projects_button_and_no_pipeline_pronto(self) -> None:
        win = MainWindow()
        self.assertTrue(hasattr(win, "projects_button"))
        self.assertIn("Projetos", win.projects_button.text())

        # Verifica que o texto 'Pipeline local pronto' saiu do header
        header_texts = [
            lbl.text() for lbl in win.findChildren(type(win.stage_label))
        ]
        for txt in header_texts:
            self.assertNotIn("Pipeline local pronto", txt)

    def test_projects_dialog_accordion_and_actions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            reg_path = Path(tmp) / "projetos.json"
            proj_dir = Path(tmp) / "video_teste_gui"
            clips = [
                {
                    "title": "Corte Alpha",
                    "viral_score": 9,
                    "start": "00:00:05",
                    "end": "00:00:40",
                    "category": "EDUCATIVO",
                }
            ]
            rep_path = save_report(clips, proj_dir)
            register_project(
                video_name="video_teste_gui",
                project_dir=proj_dir,
                report_path=rep_path,
                clips=clips,
                registry_path=reg_path,
            )

            dialog = ProjectsDialog(registry_path=reg_path)
            self.assertEqual(len(dialog.project_rows), 1)
            # O primeiro projeto ja vem selecionado e seus cortes aparecem no detalhe
            self.assertEqual(dialog.detail.project["video_name"], "video_teste_gui")
            self.assertEqual(len(dialog.detail.clip_cards), 1)
            card: ClipCard = dialog.detail.clip_cards[0]

            # Filtro "Nao publicados" mostra o projeto; "Publicados" nao
            dialog.filter_seg.set_current(1)
            self.assertFalse(dialog.project_rows[0].isHidden())
            dialog.filter_seg.set_current(2)
            self.assertTrue(dialog.project_rows[0].isHidden())
            self.assertTrue(dialog.empty_list.text())
            dialog.filter_seg.set_current(0)
            card = dialog.detail.clip_cards[0]

            # Marcar como publicado pelo card grava no relatorio
            self.assertFalse(card.is_published())
            card.set_published(True)
            self.assertTrue(load_report(rep_path)[0]["published"])
            self.assertIn("1 publicado", dialog.detail.count_line.text())

            # Busca sem resultado mostra mensagem em vez de area vazia
            dialog.search_input.setText("nao-existe-xyz")
            self.assertTrue(dialog.project_rows[0].isHidden())
            self.assertIn("Nenhum projeto encontrado", dialog.empty_list.text())
            dialog.search_input.setText("")

            # Excluir projeto pelo detalhe
            deleted = dialog.detail.confirm_and_delete(skip_confirm=True)
            self.assertTrue(deleted)
            self.assertFalse(proj_dir.exists())
            self.assertEqual(len(dialog.project_rows), 0)

    def test_remove_missing_projects_keeps_disk_untouched(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            reg_path = Path(tmp) / "projetos.json"
            alive = Path(tmp) / "vivo"
            clips = [{"title": "A", "viral_score": 9}]
            rep_alive = save_report(clips, alive)
            register_project(
                video_name="vivo", project_dir=alive, report_path=rep_alive,
                clips=clips, registry_path=reg_path,
            )
            gone = Path(tmp) / "sumiu"
            rep_gone = save_report(clips, gone)
            register_project(
                video_name="sumiu", project_dir=gone, report_path=rep_gone,
                clips=clips, registry_path=reg_path,
            )
            import shutil
            shutil.rmtree(gone)

            dialog = ProjectsDialog(registry_path=reg_path)
            self.assertTrue(dialog.missing_row.isVisibleTo(dialog))
            removed = dialog.remove_missing()
            self.assertEqual(removed, 1)
            self.assertEqual(
                [p["video_name"] for p in load_projects_registry(reg_path)], ["vivo"]
            )
            self.assertTrue(alive.exists())
            self.assertEqual(remove_missing_projects(reg_path), 0)

    def test_compute_average_viral_score_empty(self) -> None:
        self.assertEqual(compute_average_viral_score([]), 0.0)

    def test_integrated_navigation_and_quick_controls_sync(self) -> None:
        win = MainWindow()
        self.assertEqual(win.main_stack.currentIndex(), 0)

        # Alterna para Projetos e Ajustes na mesma janela (sem abrir modais bloqueantes)
        win.open_projects()
        self.assertEqual(win.main_stack.currentIndex(), 1)

        win.open_settings()
        self.assertEqual(win.main_stack.currentIndex(), 2)

        win.workspace_button.setChecked(True)
        self.assertEqual(win.main_stack.currentIndex(), 0)

        # Escolher um estilo na tela Cortar atualiza options e sincroniza com Ajustes
        win.select_quick_preset("stronda_red_box")
        self.assertEqual(win.options.caption_highlight_color, "#EF4444")

        win.open_settings()
        self.assertEqual(
            win.settings_view.preset_grid.selected_preset(), "stronda_red_box"
        )

        # Duração e rigor em linguagem simples mapeiam para os valores técnicos
        win.workspace_button.setChecked(True)
        win.duration_seg.set_current(0)
        self.assertEqual(
            (win.options.min_clip_duration, win.options.max_clip_duration), (15, 40)
        )
        win.rigor_seg.set_current(2)
        self.assertEqual(win.options.min_viral_score, 9)

        # Link e arquivo: uma origem por vez, link inválido não habilita o botão
        win.video_link.setText("isso nao e link")
        self.assertFalse(win.process_button.isEnabled())
        win.video_link.setText("youtu.be/abc123")
        self.assertTrue(win.process_button.isEnabled())
        self.assertEqual(win._active_source()[0], "https://youtu.be/abc123")
        win.video_link.clear()

        # Ao concluir, a tela Cortar mostra os resultados
        win.on_finished(
            {
                "clips": [
                    {
                        "title": "Corte Direto",
                        "viral_score": 9,
                        "start": "00:00:10",
                        "end": "00:00:45",
                        "category": "EDUCATIVO",
                    }
                ],
                "clip_paths": [],
                "report_path": None,
            }
        )
        self.assertEqual(win.workspace_stack.currentIndex(), 2)
        self.assertEqual(win.result_count.text(), "1 corte pronto")
        self.assertEqual(len(win.results_grid.widgets()), 1)

        # "Novo vídeo" volta para a configuração
        win.start_new_video()
        self.assertEqual(win.workspace_stack.currentIndex(), 0)

    def test_postar_opens_upload_pages_without_touching_clipboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dummy_file = Path(tmp) / "corte_teste.mp4"
            dummy_file.write_bytes(b"dummy mp4")
            QApplication.clipboard().setText("titulo copiado antes")

            with patch("webbrowser.open_new_tab") as mock_open_tab, \
                 patch("gui.projects_dialog.reveal_in_explorer") as mock_reveal:
                open_upload_pages(str(dummy_file))

                opened_urls = [call.args[0] for call in mock_open_tab.call_args_list]
                self.assertIn("https://www.youtube.com/upload", opened_urls)
                self.assertIn(
                    "https://www.tiktok.com/tiktokstudio/upload?from=webapp&tab=video",
                    opened_urls,
                )
                mock_reveal.assert_called_once_with(dummy_file.resolve())

            # A área de transferência continua com o que o usuário copiou
            self.assertEqual(QApplication.clipboard().text(), "titulo copiado antes")

            with patch("PySide6.QtGui.QDesktopServices.openUrl") as mock_open_url:
                reveal_in_explorer(str(dummy_file))
                mock_open_url.assert_called_once()
                opened_url = mock_open_url.call_args[0][0]
                self.assertEqual(
                    Path(opened_url.toLocalFile()).resolve(),
                    dummy_file.parent.resolve(),
                )

            # Card do corte: "Postar" é a ação principal e depois vira "Marcar como publicado"
            clip = {"title": "Corte A", "viral_score": 9, "file": str(dummy_file)}
            card = ClipCard(clip, str(dummy_file), 0)
            self.assertEqual(card.post_button.text(), "Postar ↗")
            with patch("gui.projects_dialog.open_upload_pages") as mock_open:
                card.post_button.click()
                mock_open.assert_called_once_with(str(dummy_file))
            self.assertIn("Marcar como publicado", card.post_button.text())
            card.post_button.click()
            self.assertTrue(card.is_published())
            self.assertIn("Postar de novo", card.post_button.text())


if __name__ == "__main__":
    unittest.main()
