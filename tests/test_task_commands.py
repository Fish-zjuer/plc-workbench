import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from plc_agent.config import ModelConfig,ROOT
from plc_agent.storage import Project,Session
from plc_agent.task_store import TaskStore
from plc_probe.config import cache_dir

class TaskCommandTests(unittest.TestCase):
    def test_cli_plan_accept_and_default_plan_run_need_no_model_key(self):
        with tempfile.TemporaryDirectory(dir=cache_dir()) as folder:
            env=dict(os.environ,PLC_AGENT_HOME=folder)
            def command(*args):
                run=subprocess.run([sys.executable,"-m","plc_agent","task",*args],cwd=ROOT,env=env,
                                   capture_output=True,text=True,encoding="utf-8",timeout=30)
                self.assertEqual(run.returncode,0,run.stderr)
                return json.loads(run.stdout)
            plan=command("plan",str(ROOT/"examples/tasks/interlocked_start.json"),"--new","CLI fixture")
            task_id=plan["task_id"];project=plan["project_id"]
            self.assertFalse(plan["accepted"])
            self.assertEqual(command("accept",task_id,"--project",project)["status"],"contract_accepted")
            result=command("run",task_id,"--project",project)
            self.assertEqual(result["status"],"planned")
            self.assertFalse((Path(folder)/"projects"/project/"workspace/code").exists())

class TaskUITests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        asyncio.get_running_loop().set_debug(False)

    async def test_task_inspector_requires_human_checkbox_before_confirmation(self):
        from plc_agent.tui import Workbench
        from plc_agent.task_ui import TaskInspector
        from textual.widgets import Button,Checkbox
        with tempfile.TemporaryDirectory(dir=cache_dir()) as folder:
            project=Project.create('Task inspector',Path(folder));session=Session.create(project)
            store=TaskStore(session)
            spec=json.loads((ROOT/'examples/tasks/interlocked_start.json').read_text(encoding='utf-8'))
            task_id=store.create(spec)['task_id']
            app=Workbench(session,ModelConfig())
            async with app.run_test(size=(130,42)) as pilot:
                await pilot.click('#tasks');await pilot.pause()
                self.assertIsInstance(app.screen,TaskInspector)
                self.assertTrue(app.screen.query_one('#task-confirm',Button).disabled)
                app.screen.query_one('#task-consent',Checkbox).value=True
                await pilot.pause()
                self.assertFalse(app.screen.query_one('#task-confirm',Button).disabled)
                await pilot.click('#task-confirm')
                for _ in range(50):
                    await pilot.pause(.05)
                    if not app.busy and not isinstance(app.screen,TaskInspector):break
                self.assertTrue(store.accepted(task_id))
                self.assertEqual(session.data['mode'],'plan')
                self.assertFalse(list(project.workspace.rglob('*.st')))

    async def test_tui_import_show_accept_and_run_in_plan_mode(self):
        from plc_agent.tui import Workbench
        with tempfile.TemporaryDirectory(dir=cache_dir()) as folder:
            project=Project.create("TUI task fixture",Path(folder));session=Session.create(project)
            config=ModelConfig(base_url="http://localhost:1/v1",model="unreachable-fixture")
            app=Workbench(session,config)
            async with app.run_test(size=(130,42)) as pilot:
                async def action(command):
                    app.command(command)
                    for _ in range(100):
                        await pilot.pause(.05)
                        if not app.busy:return
                    self.fail("TUI task command did not complete")
                await action('/task plan "'+str(ROOT/"examples/tasks/interlocked_start.json")+'"')
                task_id=session.data["task_plan"]["id"]
                await action("/task show "+task_id)
                await action("/task accept "+task_id)
                self.assertTrue(TaskStore(session).accepted(task_id))
                await action("/task run "+task_id)
                self.assertEqual(session.data["mode"],"plan")
                self.assertFalse((project.workspace/"code").exists())
                self.assertFalse(app.busy)

if __name__=="__main__":unittest.main()
