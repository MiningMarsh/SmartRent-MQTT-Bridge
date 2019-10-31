from string import Template

def isAutoMode( mode):
    return mode == 'heat_cool' or mode == 'auto'

class SetThermostatModeCommand:
    def matches(self, cmd):
        return cmd == 'mode/set'

    def serialize(self, device, value):
        self.value = value
        self.device = device
        if isAutoMode(value):
            return False

        return Template('["$streamId","$stream_command_index","devices:$deviceId","update_attributes",{"device_id":"$deviceId","attributes":[{"name":"mode","value":"$value"}]}]').substitute(streamId=str(device.stream_id), stream_command_index=str(device.stream_command_index), deviceId=str(device.id), value=value)

class SetTargetTempCommand:
    def __init__(self, mode):
        self.mode = mode

    def matches(self, cmd):
        return cmd == Template('target/$mode/temp/set').substitute(mode=self.mode)

    def serialize(self, device, value):
        self.value = value
        self.device = device
        return Template('["$streamId","$stream_command_index","devices:$deviceId","update_attributes",{"device_id":"$deviceId","attributes":[{"name":"$mode","value":"$value"}]}]').substitute(streamId=str(device.stream_id), stream_command_index=str(device.stream_command_index), deviceId=str(device.id), value=value, mode=f'{self.mode}ing_setpoint')

stream_count = 0
def getStreamId():
    global stream_count
    stream_count += 1
    return stream_count

class Device:
    def __init__(self, device_id, availableCommands):
        self.id = device_id
        self.stream_id = getStreamId()
        self.stream_command_index = 0
        self.availableCommands = availableCommands

    def serializeCommand(self, command, value):
        self.cmd = next(c for c in self.availableCommands if c.matches(command))
        if not self.cmd:
            return
        self.stream_command_index += 1
        return self.cmd.serialize(self, value)

    def getLastCommand(self):
        if not self.cmd:
            return None
        return self.cmd


class NullDevice:
    def __init__(self):
         self.id = "NullDevice"
    def serializeCommand(self, command, value):
        return False
    def getLastCommand(self):
        return False

class DeviceOrNullDeviceSpecification:
    def __init__(self, device_id):
        self.device_id = device_id
    def isAMatch(self, device):
        return device.id == self.device_id or device.id == "NullDevice"

class Devices:
    def __init__(self, devices):
        self.allDevices = []
        for key, value in devices.items():
            if value[2] == 'thermostat':
                self.allDevices.append(Device(key, [
                    SetThermostatModeCommand(),
                    SetTargetTempCommand('cool'),
                    SetTargetTempCommand('heat')
                ]))
        self.allDevices.append(NullDevice())

    def getDevice(self, device_id):
        spec = DeviceOrNullDeviceSpecification(device_id)
        return next(d for d in self.allDevices if spec.isAMatch(d))
