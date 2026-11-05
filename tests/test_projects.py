import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton

from gui.main_window import MainWindow
from gui.projects_dialog import (
    ProjectAccordionItem,
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
            self.assertEqual(len(dialog.accordion_items), 1)
            item: ProjectAccordionItem = dialog.accordion_items[0]

            # Primeiro item vem expandido por padrao, sanfona alterna ao clicar
            self.assertTrue(item.is_expanded())
            item.toggle()
            self.assertFalse(item.is_expanded())
            item.toggle()
            self.assertTrue(item.is_expanded())

            # Simula clique no botao de publicado dentro do projeto
            pub_buttons = [
                b
                for b in item.findChildren(type(item.header_button))
                if b.objectName() == "PublishedBtn"
            ]
            self.assertEqual(len(pub_buttons), 1)
            pub_btn = pub_buttons[0]
            self.assertEqual(pub_btn.property("published"), "false")

            pub_btn.click()
            self.assertEqual(pub_btn.property("published"), "true")
            self.assertTrue(load_report(rep_path)[0]["published"])

            # Excluir projeto via metodo confirm_and_delete(skip_confirm=True)
            deleted = item.confirm_and_delete(skip_confirm=True)
            self.assertTrue(deleted)
            self.assertFalse(proj_dir.exists())
            self.assertEqual(len(dialog.accordion_items), 0)

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

        # Alterar preset rápido na tela principal atualiza options e sincroniza com settings_view
        idx = win.quick_preset_combo.findData("stronda_red_box")
        self.assertGreaterEqual(idx, 0)
        win.quick_preset_combo.setCurrentIndex(idx)
        self.assertEqual(win.options.caption_highlight_color, "#EF4444")

        win.open_settings()
        self.assertEqual(
            win.settings_view.preset_grid.selected_preset(), "stronda_red_box"
        )

        # Simula finalização de cortes e verifica mudança automática para aba de Cortes Gerados
        win.workspace_button.setChecked(True)
        win.output_tabs.set_current(1)
        self.assertEqual(win.output_stack.currentIndex(), 1)

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
        self.assertEqual(win.output_stack.currentIndex(), 0)
        self.assertEqual(win.result_count.text(), "1 corte")

    def test_postar_button_opens_youtube_and_tiktok_tabs_and_copies_clipboard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            dummy_file = Path(tmp) / "corte_teste.mp4"
            dummy_file.write_bytes(b"dummy mp4")

            with patch("webbrowser.open_new_tab") as mock_open_tab, \
                 patch("gui.projects_dialog.reveal_in_explorer") as mock_reveal:
                open_upload_pages(str(dummy_file))

                # Verifica que as duas abas foram abertas
                opened_urls = [call.args[0] for call in mock_open_tab.call_args_list]
                self.assertIn("https://www.youtube.com/upload", opened_urls)
                self.assertIn(
                    "https://www.tiktok.com/tiktokstudio/upload?from=webapp&tab=video",
                    opened_urls,
                )

                # Verifica que o arquivo foi destacado no gerenciador de arquivos
                mock_reveal.assert_called_once_with(dummy_file.resolve())

                # Verifica que o caminho foi copiado para a área de transferência
                clipboard_text = QApplication.clipboard().text()
                self.assertEqual(
                    Path(clipboard_text).resolve(), dummy_file.resolve()
                )

            # Testa reveal_in_explorer abrindo a pasta onde o vídeo está (imune ao bug de Documents)
            with patch("PySide6.QtGui.QDesktopServices.openUrl") as mock_open_url:
                reveal_in_explorer(str(dummy_file))
                mock_open_url.assert_called_once()
                opened_url = mock_open_url.call_args[0][0]
                self.assertEqual(
                    Path(opened_url.toLocalFile()).resolve(),
                    dummy_file.parent.resolve(),
                )

            # Verifica o botão Postar no ProjectAccordionItem
            reg_path = Path(tmp) / "projetos.json"
            proj_dir = Path(tmp) / "proj"
            clips = [{"title": "Corte A", "viral_score": 9, "file": str(dummy_file)}]
            rep_path = save_report(clips, proj_dir, [str(dummy_file)])
            register_project(
                video_name="proj",
                project_dir=proj_dir,
                report_path=rep_path,
                clips=clips,
                clip_paths=[str(dummy_file)],
                registry_path=reg_path,
            )

            dialog = ProjectsDialog(registry_path=reg_path)
            item = dialog.accordion_items[0]
            post_buttons = [
                b for b in item.findChildren(QPushButton) if b.text() == "Postar"
            ]
            self.assertEqual(len(post_buttons), 1)

            with patch("gui.projects_dialog.open_upload_pages") as mock_open:
                post_buttons[0].click()
                mock_open.assert_called_once_with(str(dummy_file))


if __name__ == "__main__":
    unittest.main()
