import pathlib
import runpy
import sys

scripts = pathlib.Path(__file__).resolve().parent
if len(sys.argv) < 2:
    raise SystemExit('用法: quality_gate.py snapshot|check|review [参数]')
action = sys.argv[1]
if action not in ('snapshot', 'check', 'review'):
    raise SystemExit('未知操作')
entry = scripts / ('review_skill.py' if action == 'review' else 'skill_check.py')
sys.path.insert(0, str(scripts))
sys.argv = [str(entry)] + (sys.argv[2:] if action == 'review' else sys.argv[1:])
runpy.run_path(str(entry), run_name='__main__')
