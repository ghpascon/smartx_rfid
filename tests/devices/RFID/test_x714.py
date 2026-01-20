import pytest
from unittest.mock import Mock, patch

from smartx_rfid.devices.RFID.X714._main import X714


class TestX714:
    """Test suite for X714 RFID Reader class"""

    def test_create_object_default(self):
        """Test creating X714 object with default parameters"""
        # Mock the problematic on_event import
        with patch("smartx_rfid.devices.RFID.X714._main.on_event", Mock()):
            x714_device = X714()

            # Check if object is instance of X714 class
            assert isinstance(x714_device, X714)

            # Check basic default attributes
            assert x714_device.name == "X714"
            assert x714_device.connection_type == "SERIAL"
            assert x714_device.port == "AUTO"
            assert x714_device.baudrate == 115200
            assert x714_device.is_connected is False
            assert x714_device.buzzer is False

    def test_create_object_serial_config(self):
        """Test creating X714 object with SERIAL configuration"""
        with patch("smartx_rfid.devices.RFID.X714._main.on_event", Mock()):
            x714_device = X714(
                name="TEST_X714",
                connection_type="SERIAL",
                port="COM3",
                baudrate=9600,
                vid=0x0403,
                pid=0x6001,
            )

            # Check if object is instance of X714 class
            assert isinstance(x714_device, X714)

            # Check SERIAL configuration
            assert x714_device.name == "TEST_X714"
            assert x714_device.connection_type == "SERIAL"
            assert x714_device.port == "COM3"
            assert x714_device.baudrate == 9600
            assert x714_device.vid == 0x0403
            assert x714_device.pid == 0x6001
            assert x714_device.is_auto is False

    def test_create_object_tcp_config(self):
        """Test creating X714 object with TCP configuration"""
        with patch("smartx_rfid.devices.RFID.X714._main.on_event", Mock()):
            x714_device = X714(
                name="TCP_X714",
                connection_type="TCP",
                ip="192.168.1.200",
                tcp_port=4001,
            )

            # Check TCP configuration
            assert x714_device.name == "TCP_X714"
            assert x714_device.connection_type == "TCP"
            assert x714_device.ip == "192.168.1.200"
            assert x714_device.tcp_port == 4001

    def test_create_object_ble_config(self):
        """Test creating X714 object with BLE configuration"""
        with patch("smartx_rfid.devices.RFID.X714._main.on_event", Mock()):
            x714_device = X714(
                name="BLE_X714",
                connection_type="BLE",
                ble_name="CUSTOM_SMTX",
            )

            # Check BLE configuration
            assert x714_device.name == "BLE_X714"
            assert x714_device.connection_type == "BLE"
            assert x714_device.ble_name == "CUSTOM_SMTX"

    def test_invalid_connection_type(self):
        """Test creating X714 with invalid connection type defaults to SERIAL"""
        with patch("smartx_rfid.devices.RFID.X714._main.on_event", Mock()):
            with patch("logging.warning") as mock_warning:
                x714_device = X714(connection_type="INVALID")

                # Should default to SERIAL and log warning
                assert x714_device.connection_type == "SERIAL"
                mock_warning.assert_called_once()

    def test_antenna_configuration_default(self):
        """Test default antenna configuration"""
        with patch("smartx_rfid.devices.RFID.X714._main.on_event", Mock()):
            x714_device = X714()

            # Check antenna configuration
            assert "1" in x714_device.ant_dict
            assert x714_device.ant_dict["1"]["active"] is True
            assert x714_device.ant_dict["1"]["power"] == 22
            assert x714_device.ant_dict["1"]["rssi"] == -120

            # Other antennas should be inactive by default
            assert x714_device.ant_dict["2"]["active"] is False

    def test_antenna_configuration_custom_active(self):
        """Test custom active antenna configuration"""
        with patch("smartx_rfid.devices.RFID.X714._main.on_event", Mock()):
            x714_device = X714(active_ant=[1, 2, 3], read_power=25, read_rssi=-100)

            # Check antenna configuration
            assert x714_device.ant_dict["1"]["active"] is True
            assert x714_device.ant_dict["2"]["active"] is True
            assert x714_device.ant_dict["3"]["active"] is True
            assert x714_device.ant_dict["4"]["active"] is False

            # Check power and RSSI settings
            assert x714_device.ant_dict["1"]["power"] == 25
            assert x714_device.ant_dict["1"]["rssi"] == -100

    def test_antenna_configuration_custom_dict(self):
        """Test custom antenna dictionary configuration"""
        custom_ant_dict = {
            "1": {"active": True, "power": 30, "rssi": -90},
            "2": {"active": True, "power": 28, "rssi": -95},
        }

        with patch("smartx_rfid.devices.RFID.X714._main.on_event", Mock()):
            x714_device = X714(ant_dict=custom_ant_dict)

            # Should use provided dictionary
            assert x714_device.ant_dict == custom_ant_dict

    def test_write_method_serial(self):
        """Test write method with SERIAL connection type"""
        with patch("smartx_rfid.devices.RFID.X714._main.on_event", Mock()):
            x714_device = X714(connection_type="SERIAL")
            x714_device.write_serial = Mock()

            # Test writing data
            x714_device.write("test command")

            # Should call write_serial
            x714_device.write_serial.assert_called_once_with("test command", True)

    def test_on_receive_tag_data(self):
        """Test on_receive method with tag data"""
        with patch("smartx_rfid.devices.RFID.X714._main.on_event", Mock()):
            x714_device = X714()
            x714_device.on_tag = Mock()

            # Test tag data
            tag_data = "#t+@E200123456789012|300833B2DDD901148000000F|1|-75"
            x714_device.on_receive(tag_data)

            # Should call on_tag with parsed data
            x714_device.on_tag.assert_called_once()
            call_args = x714_device.on_tag.call_args[0][0]
            assert call_args["epc"] == "e200123456789012"
            assert call_args["tid"] == "300833b2ddd901148000000f"
            assert call_args["ant"] == 1
            assert call_args["rssi"] == 75

    def test_on_receive_read_start_stop(self):
        """Test on_receive method with read start/stop commands"""
        with patch("smartx_rfid.devices.RFID.X714._main.on_event", Mock()):
            x714_device = X714()

            # Test read start
            x714_device.on_start()
            assert x714_device.is_reading is True

            # Test read stop
            x714_device.on_stop()
            assert x714_device.is_reading is False

    def test_on_connected_callback(self):
        """Test on_connected callback"""
        with patch("smartx_rfid.devices.RFID.X714._main.on_event", Mock()):
            x714_device = X714()
            x714_device.config_reader = Mock()
            x714_device.on_event = Mock()

            # Test on_connected
            x714_device.on_connected()

            # Should call config_reader and on_event
            x714_device.config_reader.assert_called_once()
            x714_device.on_event.assert_called_once_with("X714", "connected", True)


if __name__ == "__main__":
    pytest.main([__file__])
