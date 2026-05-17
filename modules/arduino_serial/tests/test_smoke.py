"""arduino_serial smoke tests."""


def test_import_service():
    from modules.arduino_serial.xArduinoSerialService import xArduinoSerialService

    assert xArduinoSerialService is not None


def test_config_loader():
    from modules.arduino_serial.config_loader import load_config

    cfg = load_config()
    assert isinstance(cfg, dict)


def test_contract_builders():
    from modules.arduino_serial.contract import build_set_servo_cmd, SERVO_INDEX_PAN

    cmd = build_set_servo_cmd(SERVO_INDEX_PAN, 90)
    assert isinstance(cmd, dict)
