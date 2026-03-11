# -*- coding: utf-8 -*-
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent  # user_simulator_agent/
sys.path.insert(0, str(_ROOT))

from config.config_loader import load_config, get_prompt

cfg = load_config()
print('=== Config sections:', list(cfg.keys()))

checks = [
    ('generate_user_profile_config', 'PROFILE_GENERATION_PROMPT'),
    ('profile_analyzer_config',      'PROMPT_TMPL'),
    ('computer_spec_designer_config','PROMPT_DIRS'),
    ('computer_spec_designer_config','PROMPT_FILE_COUNTS'),
    ('computer_spec_designer_config','PROMPT_ENVCONFIG'),
    ('user_agent_builder_config',    'PROMPT_TMPL'),
]

for section, key in checks:
    path = cfg.get(section, {}).get(key)
    text = get_prompt(path)
    print(f'  OK [{section}.{key}] -> {len(text)} chars  ({path})')

print()
print('batch_generate_config :', cfg.get('batch_generate_config'))
print('generate_user_profile_config:', cfg.get('generate_user_profile_config'))
