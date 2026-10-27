from __future__ import annotations

import asyncio
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from textual.widgets import Button, Input, TextArea

from plc_agent.config import ModelConfig
from plc_agent.storage import Project, Session
from plc_agent.tui import FilePicker, Settings, Workbench
from plc_probe.config import cache_dir
from test_agent_core import ScriptedProvider


class TUITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        asyncio.get_running_loop().set_debug(False)
        self.temp = tempfile.TemporaryDirectory(dir=cache_dir())
        self.addCleanup(self.temp.cleanup)
        self.project = Project.create("终端测试", Path(self.temp.name))
        self.session = Session.create(self.project)
        self.config = ModelConfig(base_url="http://localhost:1/v1", model="ui-fixture")

    async def test_mode_toggle_upload_button_and_small_terminal(self):
        app = Workbench(self.session, self.config, provider_factory=lambda cfg: ScriptedProvider([]))
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.click("#mode")
            self.assertEqual(self.session.data["mode"], "execute")
            await pilot.press("ctrl+p")
            self.assertEqual(self.session.data["mode"], "plan")
            await pilot.click("#upload")
            await pilot.pause()
            self.assertIsInstance(app.screen, FilePicker)
            await pilot.press("escape")
            await pilot.pause()
            self.assertNotIsInstance(app.screen, FilePicker)
            await pilot.resize_terminal(80, 25)
            await pilot.pause()
            self.assertFalse(app.query_one("#sidebar").display)
            self.assertTrue(app.query_one("#composer", TextArea).display)

    async def test_file_picker_imports_selected_file(self):
        path = Path(self.temp.name) / "上传 测试.st"
        path.write_text("FUNCTION_BLOCK Example END_FUNCTION_BLOCK", encoding="utf-8")
        app = Workbench(self.session, self.config, provider_factory=lambda cfg: ScriptedProvider([]))
        async with app.run_test(size=(120, 40)) as pilot:
            app.action_upload()
            await pilot.pause()
            app.screen.query_one("#file-path", Input).value = str(path)
            await pilot.click("#upload-confirm")
            for _ in range(40):
                await pilot.pause(.05)
                if not app.busy:
                    break
            self.assertEqual(len(self.project.data["attachments"]), 1)
            self.assertEqual(self.project.data["attachments"][0]["name"], path.name)

    async def test_configuration_screen_does_not_expose_existing_secret(self):
        self.config.api_key = "do-not-render-me"
        app = Workbench(self.session, self.config, provider_factory=lambda cfg: ScriptedProvider([]))
        async with app.run_test(size=(120, 45)) as pilot:
            app.action_config()
            await pilot.pause()
            self.assertIsInstance(app.screen, Settings)
            key = app.screen.query_one("#api-key", Input)
            self.assertTrue(key.password)
            self.assertEqual(key.value, "")
            self.assertNotIn("do-not-render-me", app.export_screenshot())

    async def test_send_message_and_resume_rendered_history(self):
        app = Workbench(self.session, self.config, provider_factory=lambda cfg: ScriptedProvider([{"text": "先确认停止优先级"}]))
        async with app.run_test(size=(120, 40)) as pilot:
            app.query_one("#composer", TextArea).load_text("帮我制定计划")
            await pilot.click("#send")
            for _ in range(50):
                await pilot.pause(.05)
                if not app.busy:
                    break
            self.assertFalse(app.busy)
            self.assertEqual(self.session.data["status"], "idle")
            self.assertTrue(any(e.get("text") == "先确认停止优先级" for e in self.session.events()))
            self.assertEqual(app.query_one("#composer", TextArea).text, "")

    async def test_solve_command_in_plan_mode_saves_plan_without_executing(self):
        self.config=ModelConfig()
        app=Workbench(self.session,self.config,provider_factory=lambda cfg:ScriptedProvider([]))
        async with app.run_test(size=(120,40)) as pilot:
            app.query_one('#composer',TextArea).load_text('/solve 05')
            await pilot.click('#send')
            for _ in range(30):
                await pilot.pause(.05)
                if not app.busy:break
            self.assertFalse(app.busy)
            self.assertTrue(self.session.data['plan'])
            self.assertFalse((self.project.workspace/'candidate.st').exists())

    async def test_unconfigured_model_keeps_user_composer_text(self):
        app=Workbench(self.session,ModelConfig(),provider_factory=lambda cfg:ScriptedProvider([]))
        async with app.run_test(size=(120,40)) as pilot:
            app.query_one('#composer',TextArea).load_text('请保存我的需求')
            await pilot.click('#send');await pilot.pause()
            self.assertEqual(app.query_one('#composer',TextArea).text,'请保存我的需求')
            self.assertFalse(app.busy)

    async def test_memory_settings_round_trip_and_clear_key(self):
        app=Workbench(self.session,self.config,provider_factory=lambda cfg:ScriptedProvider([]))
        self.config.api_key='old-secret'
        from textual.widgets import Checkbox
        async with app.run_test(size=(120,45)) as pilot:
            app.action_config();await pilot.pause()
            screen=app.screen
            screen.query_one('#compact-keep',Input).value='4'
            screen.query_one('#compact-target',Input).value='0.45'
            screen.query_one('#compact-output',Input).value='1024'
            screen.query_one('#request-timeout',Input).value='120'
            screen.query_one('#clear-key',Checkbox).value=True
            saved=[]
            with patch.dict('os.environ',{},clear=True),patch.object(ModelConfig,'save',lambda cfg:saved.append(cfg)):
                screen.save();await pilot.pause()
            self.assertEqual(saved[0].compact_keep_turns,4)
            self.assertEqual(saved[0].compact_summary_tokens,1024)
            self.assertEqual(saved[0].api_key,'')
            self.assertEqual(app.config.timeout,120)


if __name__ == "__main__":
    unittest.main()
