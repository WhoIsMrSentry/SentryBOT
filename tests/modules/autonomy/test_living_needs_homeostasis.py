import pytest
from modules.autonomy.services.living_needs import LivingNeedsEngine

def test_homeostasis_battery_low():
    engine = LivingNeedsEngine()
    out_normal = engine.tick(state={"battery_pct": 100.0, "last_interaction": 0.0})
    out_low = engine.tick(state={"battery_pct": 15.0, "last_interaction": 0.0})
    
    assert out_low["scores"]["energy"] < out_normal["scores"]["energy"]
    assert out_low["scores"]["rest"] > out_normal["scores"]["rest"]

def test_homeostasis_thermal_fatigue():
    engine = LivingNeedsEngine()
    out_cool = engine.tick(state={"cpu_temp": 45.0, "last_interaction": 0.0})
    out_hot = engine.tick(state={"cpu_temp": 82.0, "last_interaction": 0.0})
    
    assert out_hot["scores"]["energy"] < out_cool["scores"]["energy"]
    assert out_hot["scores"]["rest"] > out_cool["scores"]["rest"]
