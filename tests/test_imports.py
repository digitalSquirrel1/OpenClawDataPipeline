# -*- coding: utf-8 -*-
"""Verify that all modified agent modules import without errors."""
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent          # user_simulator_agent/
_WS   = _ROOT / "WorkingSpace"
sys.path.insert(0, str(_WS))
sys.path.insert(0, str(_ROOT))

from agents.profile_analyzer import PROMPT_TMPL as PA_TMPL
print(f'profile_analyzer.PROMPT_TMPL     : {len(PA_TMPL)} chars  OK')

from agents.user_agent_builder import PROMPT_TMPL as UAB_TMPL
print(f'user_agent_builder.PROMPT_TMPL   : {len(UAB_TMPL)} chars  OK')

from agents.computer_spec_designer import (
    PROMPT_DIRS, PROMPT_PDF, PROMPT_HTML, PROMPT_EXCEL_CSV,
    PROMPT_DOCX, PROMPT_XLSX, PROMPT_MD, PROMPT_IMAGE,
    PROMPT_VIDEO, PROMPT_AUDIO, PROMPT_FILE_COUNTS, PROMPT_ENVCONFIG,
)
prompts = {
    'PROMPT_DIRS': PROMPT_DIRS, 'PROMPT_PDF': PROMPT_PDF,
    'PROMPT_HTML': PROMPT_HTML, 'PROMPT_EXCEL_CSV': PROMPT_EXCEL_CSV,
    'PROMPT_DOCX': PROMPT_DOCX, 'PROMPT_XLSX': PROMPT_XLSX,
    'PROMPT_MD': PROMPT_MD,     'PROMPT_IMAGE': PROMPT_IMAGE,
    'PROMPT_VIDEO': PROMPT_VIDEO, 'PROMPT_AUDIO': PROMPT_AUDIO,
    'PROMPT_FILE_COUNTS': PROMPT_FILE_COUNTS, 'PROMPT_ENVCONFIG': PROMPT_ENVCONFIG,
}
for name, val in prompts.items():
    print(f'  computer_spec_designer.{name:20s}: {len(val)} chars  OK')

print('\nAll imports OK')
