import os
import yaml

def load_config(overrides=None):
    config_path = os.path.join(os.path.dirname(__file__), "config", "config.yml")
    if not os.path.exists(config_path):
        return overrides or {}
    
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    
    if overrides:
        config.update(overrides)
        
    return config
