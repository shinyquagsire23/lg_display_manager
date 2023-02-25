import struct
import hid

import time
import rumps
import os

LG_MONITOR_CONTROL_VID = 0x043E
LG_MONITOR_CONTROL_PID = 0x9A39
LG_MONITOR_DDCCI_I2C_ADDR = 0x37
LG_MONITOR_SERDB_I2C_ADDR = 0x59
LG_MONITOR_FLASH_I2C_ADDR = 0x49

#SPI_FLASH_SIZE = 0x10000
SPI_FLASH_SIZE = 0x1000000

# From flashrom
MSTARDDC_SPI_WRITE = 0x10
MSTARDDC_SPI_READ = 0x11
MSTARDDC_SPI_END_READ = 0x12
MSTARDDC_SPI_RESET = 0x24

# 0 - no split
# 1 - left-right half and half
# 2 - top-bottom half and half
# 3 - left-right 3/4 and 1/4
# 4 - left-right 1/4 and 3/4
# 5 - left-right 2/3 and 1/3
# 6 - 1:1 PIP top left
# 7 - 1:1 PIP top right
# 8 - 1:1 PIP bottom left
# 9 - 1:1 PIP bottom right
# A - change PIP ratio to 16:9
# B - three-way, center slightly larger
# C - also three-way?
# D - Quad split
# E - invalid
LG_SPLIT_NONE = 0x0
LG_SPLIT_LEFT_RIGHT_HALF_HALF = 0x1
LG_SPLIT_TOP_BOTTOM = 0x2
LG_SPLIT_LEFT_RIGHT_3_4__1_4 = 0x3
LG_SPLIT_LEFT_RIGHT_1_4__3_4 = 0x4
LG_SPLIT_LEFT_RIGHT_2_3__1_3 = 0x5
LG_SPLIT_SQUARE_PIP_TOP_LEFT = 0x6
LG_SPLIT_SQUARE_PIP_TOP_RIGHT = 0x7
LG_SPLIT_SQUARE_PIP_BOTTOM_LEFT = 0x8
LG_SPLIT_SQUARE_PIP_BOTTOM_RIGHT = 0x9
LG_SPLIT_PIP_16_9 = 0xA
LG_SPLIT_THREE_WAY_SPLIT = 0xB
LG_SPLIT_THREE_WAY_SPLIT_2 = 0xC
LG_SPLIT_QUAD_SPLIT = 0xD
LG_SPLIT_FIX_AUDIO = 0xE

# Split sound source
LG_SOUND_MAIN = 0
LG_SOUND_SUB = 1

# LG monitor enum
LG_MONITOR_HDMI1 = 0
LG_MONITOR_HDMI2 = 1
LG_MONITOR_DP1 = 2
LG_MONITOR_USB_C = 3

# DDC monitor enum
MONITOR_AUTO = 0x0
MONITOR_HDMI1 = 0x90
MONITOR_HDMI2 = 0x91
MONITOR_DP1 = 0xd0
MONITOR_DP2 = 0xd1
MONITOR_DP3 = 0xd2
MONITOR_USB_C = 0xd2

device = None

#
# Helpers
#
def msg_checksum(msg):
    sum = 0x6E^0x50
    for i in range(0, len(msg)):
        sum ^= msg[i]
    return sum

def msg_add_checksum(msg):
    sum = 0x6E
    for i in range(8, len(msg)):
        sum ^= msg[i]
    msg += [sum]
    return msg

def msg_add_checksum_2(msg):
    sum = 0x6E
    for i in range(0, len(msg)):
        sum ^= msg[i]
    msg += [sum]
    return msg

def hex_dump(b, prefix=""):
    p = prefix
    b = bytes(b)
    for i in range(0, len(b)):
        if i != 0 and i % 16 == 0:
            print (p)
            p = prefix
        p += ("%02x " % b[i])
    print (p)
    print ("")

class LgUsbMonitorControl:

    def __init__(self):
        # USB
        self.has_usb = False
        self.dev = None
        self.ep_in = None
        self.ep_out = None

    def init_usb(self):
        self.dev = hid.device()
        self.dev.open(LG_MONITOR_CONTROL_VID, LG_MONITOR_CONTROL_PID)

        self.has_usb = True

    def fix_connection(self):
        self.init_usb()

        # Drain anything waiting?
        for i in range(0,10):
            self.read_raw(0x40, 10)

        run_patches()

    def send_raw(self, pkt):
        if not self.has_usb:
            return

        try:
            self.dev.write(bytes(pkt + [0] * (0x40 - len(pkt))))
        except Exception as e:
            print ("Failed to write", e)
            self.fix_connection()

    def read_raw(self, amt=0x40, timeout=200):
        if not self.has_usb:
            return

        try:
            return bytes(self.dev.read(amt, timeout))
        except Exception as e:
            print ("Failed to read", e)
            self.fix_connection()

        return []

    def send_to_i2c(self, addr, data):
        wrapped = [0x08, 0x01, 0x55, 0x03, len(data), 0x00, 0x03]
        wrapped += [addr]
        wrapped += data
        #hex_dump(wrapped)
        self.send_raw(wrapped)

    def begin_read_from_i2c(self, addr, to_read):
        wrapped = [0x08, 0x02, 0x55, 0x04, to_read, 0x00, 0xb]
        wrapped += [addr]
        #hex_dump(wrapped)
        self.send_raw(wrapped)

    def read_from_i2c(self, addr, expected_back):
        data = bytes()

        if expected_back <= 0:
            return data

        time.sleep(0.01)
        needed = expected_back
        while needed > 0:
            to_read = 0x3C
            if to_read > needed:
                to_read = needed
            self.begin_read_from_i2c(addr, to_read)
        
            data_tmp = self.read_raw(0x100)

            amt_gotten = data_tmp[0] - 4
            needed -= amt_gotten
            
            data += data_tmp[4:4+amt_gotten]

        return data
    
    def wrap_send_vcp_2(self, data, expected_back=0xb):
        return self.wrap_send_vcp_4(data, expected_back, 0x51)
    
    def wrap_send_vcp_3(self, data, expected_back=0xb):
        return self.wrap_send_vcp_4(data, expected_back, 0x50)
    
    def wrap_send_vcp_4(self, data, expected_back=0xb, which_device=0x51):
        data_len = len(data)
        data = [0x00 | data_len] + data
        data = [which_device] + data
        data = msg_add_checksum_2(data)

        self.send_to_i2c(LG_MONITOR_DDCCI_I2C_ADDR, data)
        
        return self.read_from_i2c(LG_MONITOR_DDCCI_I2C_ADDR, expected_back)
    
    def get_vcp(self, idx):
        for i in range(0, 1000):
        
            data = self.wrap_send_vcp_2([0x01, idx])
            
            #hex_dump(data)
            if (len(data) < 0xb):
                hex_dump(data)
                continue
            
            data_len = data[1] & 0x7F
            if data_len > len(data)-1-2:
                data_len =len(data)-1-2

            test = msg_checksum(data[1:1+data_len+2])

            if (test == 0 and data[2] == 2 and data[4] == idx):
                return data[9] | data[8] << 8
            time.sleep(0.1)
        return -1
    
    def set_vcp(self, idx, val, val2=0):
        for i in range(0, 10):
        
            data = self.wrap_send_vcp_2([0x03, idx,(val >> 8) & 0xFF,(val >> 0) & 0xFF])
            
            #hex_dump(data)
            if (len(data) < 0xb):
                hex_dump(data)
                continue
            
            data_len = data[1] & 0x7F
            if data_len > len(data)-1-2:
                data_len =len(data)-1-2

            test = msg_checksum(data[1:1+data_len+2])

            if (test == 0 and data[4] == idx):
                return data[9]
            time.sleep(0.1)
        return -1

    def lg_special(self, idx, val):
        for i in range(0, 10):

            data = self.wrap_send_vcp_3([0x03,idx,(val >> 8) & 0xFF, val & 0xFF], 0x26)

            device.read_raw()
            #hex_dump(data)
            if (len(data) < 0x26):
                #hex_dump(data)
                continue
            
            data_len = data[1] & 0x7F
            if data_len > len(data)-1-2:
                data_len = len(data)-1-2

            return data
        return bytes([])

    def lg_special_u32(self, idx, val):
        for i in range(0, 10):

            data = self.wrap_send_vcp_3(list(struct.pack("<BB", 0x03, idx))+list(struct.pack(">L",val)), 0x26)

            #hex_dump(data)
            if (len(data) < 0x26):
                hex_dump(data)
                continue
            
            data_len = data[1] & 0x7F
            if data_len > len(data)-1-2:
                data_len = len(data)-1-2

            return data
        return bytes([0,0,0,0,0,0,0,0,0,0])

    def lg_special_u32_u8(self, idx, val, val2):
        for i in range(0, 10):

            data = self.wrap_send_vcp_3(list(struct.pack("<BB", 0x03, idx))+list(struct.pack(">LB",val,val2)), 0x26)

            #hex_dump(data)
            if (len(data) < 0x26):
                hex_dump(data)
                continue
            
            data_len = data[1] & 0x7F
            if data_len > len(data)-1-2:
                data_len =len(data)-1-2

            return data
        return bytes([0,0,0,0,0,0,0,0,0,0])

    def lg_special_f3(self, val):
        for i in range(0, 1):
            data = self.wrap_send_vcp_4([0xf3,(val >> 8) & 0xFF, val & 0xFF], 0x26)

        hex_dump(data)
        return data

    def lg_special_cc_data(self, idx, val):
        data = self.wrap_send_vcp_4([0xcc,idx] + val, 0)
        return data
    
    def lg_special_cc_u32(self, idx, val):
        data = self.wrap_send_vcp_4([0xcc,idx,val & 0xFF, (val >> 8) & 0xFF, (val >> 16) & 0xFF, (val >>24) & 0xFF], 0)
        return data
    
    # Not atomic
    def lg_arbwrite_str16(self, addr, val):
        self.lg_arbwrite(addr, list(val.encode("utf-16"))[2:] + [0,0])
    
    def lg_arbwrite_u32(self, addr, val):
        self.lg_arbwrite(addr, list(struct.pack("<L", val)))
    
    def lg_arbwrite_u16(self, addr, val):
        self.lg_arbwrite(addr, list(struct.pack("<H", val)))
    
    def lg_arbwrite_u8(self, addr, val):
        self.lg_arbwrite(addr, [val & 0xFF])
    
    def lg_arbwrite_u32_be(self, addr, val):
        self.lg_arbwrite(addr, list(struct.pack(">L", val)))

    def lg_arbwrite_u24_be(self, addr, val):
        self.lg_arbwrite_u16_be(addr, val>>8)
        self.lg_arbwrite_u8(addr+2, val & 0xFF)
        
    def lg_arbwrite_u16_be(self, addr, val):
        self.lg_arbwrite(addr, list(struct.pack(">H", val)))
    
    def lg_arbwrite(self, addr, val):
        self.lg_special_cc_u32(0xf6, addr)
        self.lg_special_cc_u32(0xf6, addr)
        self.lg_special_cc_data(0xf4, val)

    # Atomic
    def my_arbwrite_str16(self, addr, val):
        self.my_arbwrite(addr, list(val.encode("utf-16"))[2:] + [0,0])
    
    def my_arbwrite_u32(self, addr, val):
        self.my_arbwrite(addr, list(struct.pack("<L", val)))
    
    def my_arbwrite_u16(self, addr, val):
        self.my_arbwrite(addr, list(struct.pack("<H", val)))
    
    def my_arbwrite_u8(self, addr, val):
        self.my_arbwrite(addr, [val & 0xFF])
    
    def my_arbwrite_u32_be(self, addr, val):
        self.my_arbwrite(addr, list(struct.pack(">L", val)))

    def my_arbwrite_u24_be(self, addr, val):
        self.my_arbwrite_u16_be(addr, val>>8)
        self.my_arbwrite_u8(addr+2, val & 0xFF)
        
    def my_arbwrite_u16_be(self, addr, val):
        self.my_arbwrite(addr, list(struct.pack(">H", val)))
    
    def my_arbwrite(self, addr, val):
        for i in range(0, len(val)):
            self.lg_special_u32_u8(0xd5, addr+i, val[i])

    # Also atomic
    def lg_arbread_u32(self, addr):
        return struct.unpack("<L", bytes(self.lg_arbread_data(addr, 4)))[0]

    def lg_arbread_u16(self, addr):
        return struct.unpack("<H", bytes(self.lg_arbread_data(addr, 2)))[0]

    def lg_arbread_u32_be(self, addr):
        return struct.unpack(">L", bytes(self.lg_arbread_data(addr, 4)))[0]

    def lg_arbread_u16_be(self, addr):
        return struct.unpack(">H", bytes(self.lg_arbread_data(addr, 2)))[0]

    def lg_arbread_u8(self, addr):
        data = device.lg_special_u32(0xd1, addr)
        val = data[1]
        while data[0] != 0x82:
            data = device.lg_special_u32(0xd1, addr)
            val = data[1]
        return val

    def lg_arbread_data(self, addr, data_len):
        vals = []
        for i in range(0, data_len):
            val = self.lg_arbread_u8(addr+i)
            #print (hex(i),hex(val))
            vals += [val]
        return vals

    def lg_get_cur_monitor_sound(self):
        return self.lg_arbread_u8(MONITOR_INFO_STRUCT+0x2b5)

    def lg_set_cur_monitor_sound(self, val):
        self.my_arbwrite_u8(MONITOR_INFO_STRUCT+0x2b5, val & 0xFF)

    def lg_get_cur_primary(self):
        return self.lg_arbread_u8(MONITOR_INFO_STRUCT+0x2d0)

    def lg_get_cur_secondary(self):
        return self.lg_arbread_u8(MONITOR_INFO_STRUCT+0x2d1)

    def lg_set_cur_primary(self, val):
        self.my_arbwrite_u8(MONITOR_INFO_STRUCT+0x2d0, val & 0xFF)

    def lg_set_cur_secondary(self, val):
        self.my_arbwrite_u8(MONITOR_INFO_STRUCT+0x2d1, val & 0xFF)

    def lg_set_split(self, val):
        if val > LG_SPLIT_FIX_AUDIO:
            return
        if self.lg_get_split() == val:
            return

        self.set_vcp(0xd7, val)

    def lg_get_split(self):
        return self.get_vcp(0xd7)

    def lg_monitor_to_ddc(self, val):
        my_lut = [MONITOR_HDMI1, MONITOR_HDMI2, MONITOR_DP1, MONITOR_USB_C, MONITOR_USB_C]
        if val >= len(my_lut):
            return 0
        return my_lut[val]

    def lg_set_primary_input(self, val):
        device.lg_special(0xF4, self.lg_monitor_to_ddc(val))

    def lg_reset_monitor(self):
        device.lg_special(0xF5, 0)

#
# SPI Flash
#
def SPI_Flash_Tx(data):
    device.send_to_i2c(LG_MONITOR_FLASH_I2C_ADDR, [MSTARDDC_SPI_WRITE] + data)

def SPI_Flash_Rx(data_len):
    if data_len <= 0:
        return bytes([])

    device.send_to_i2c(LG_MONITOR_FLASH_I2C_ADDR, [MSTARDDC_SPI_READ])
    data = device.read_from_i2c(LG_MONITOR_FLASH_I2C_ADDR, data_len)
    device.send_to_i2c(LG_MONITOR_FLASH_I2C_ADDR, [MSTARDDC_SPI_END_READ])
    return data

def SPI_Flash_U8Cmd(idx, to_read):
    SPI_Flash_Tx([idx])
    return SPI_Flash_Rx(to_read)

def SPI_Flash_Addr24Cmd(idx, addr, to_read):
    SPI_Flash_Tx([idx, (addr>>16) & 0xFF, (addr>>8) & 0xFF, (addr>>0) & 0xFF])
    return SPI_Flash_Rx(to_read)

def SPI_Flash_Addr24AndDummyCmd(idx, addr, to_read):
    SPI_Flash_Tx([idx, (addr>>16) & 0xFF, (addr>>8) & 0xFF, (addr>>0) & 0xFF, 0])
    return SPI_Flash_Rx(to_read)

def SPI_Flash_Dump(fpath):
    f = open(fpath, "wb")
    for i in range(0, SPI_FLASH_SIZE, 0x1000):
        print (hex(i))
        data = SPI_Flash_Addr24Cmd(0x3, i, 0x1000)
        f.write(data)
    f.close()

# Exits ISP mode
def SPI_Flash_Reset():
    device.send_to_i2c(LG_MONITOR_FLASH_I2C_ADDR, [MSTARDDC_SPI_RESET])
    device.send_to_i2c(LG_MONITOR_FLASH_I2C_ADDR, [MSTARDDC_SPI_END_READ])

#
# LG MStar stuff
#
def Enter_SerialDebugMode():
    device.send_to_i2c(LG_MONITOR_SERDB_I2C_ADDR, [0x53, 0x45, 0x52, 0x44, 0x42]) # "SERDB"

def Enter_SingleStepMode():
    device.send_to_i2c(LG_MONITOR_SERDB_I2C_ADDR, [0x10, 0xc0, 0xc1, 0x53])
    device.send_to_i2c(LG_MONITOR_SERDB_I2C_ADDR, [0x10, 0x1F, 0xc1, 0x53])

def MST_i2cCh0Config():
    device.send_to_i2c(LG_MONITOR_SERDB_I2C_ADDR, [0x80])
    device.send_to_i2c(LG_MONITOR_SERDB_I2C_ADDR, [0x82])
    device.send_to_i2c(LG_MONITOR_SERDB_I2C_ADDR, [0x84])
    device.send_to_i2c(LG_MONITOR_SERDB_I2C_ADDR, [0x51])
    device.send_to_i2c(LG_MONITOR_SERDB_I2C_ADDR, [0x7F])
    device.send_to_i2c(LG_MONITOR_SERDB_I2C_ADDR, [0x37])
    device.send_to_i2c(LG_MONITOR_SERDB_I2C_ADDR, [0x61])

def MST_i2cCh4Config():
    device.send_to_i2c(LG_MONITOR_SERDB_I2C_ADDR, [0x80])
    device.send_to_i2c(LG_MONITOR_SERDB_I2C_ADDR, [0x82])
    device.send_to_i2c(LG_MONITOR_SERDB_I2C_ADDR, [0x85])
    device.send_to_i2c(LG_MONITOR_SERDB_I2C_ADDR, [0x53])
    device.send_to_i2c(LG_MONITOR_SERDB_I2C_ADDR, [0x7F])


def MST_IicBusCtrl():
    device.send_to_i2c(LG_MONITOR_SERDB_I2C_ADDR, [0x35])
    device.send_to_i2c(LG_MONITOR_SERDB_I2C_ADDR, [0x71])

def MST_DbgReadScalerReg(a, b):
    device.send_to_i2c(LG_MONITOR_SERDB_I2C_ADDR, [0x10, a, b])
    return device.read_from_i2c(LG_MONITOR_SERDB_I2C_ADDR, 1)

def Exit_SerialDebugMode():
    device.send_to_i2c(LG_MONITOR_SERDB_I2C_ADDR, [0x34])
    device.send_to_i2c(LG_MONITOR_SERDB_I2C_ADDR, [0x45])

def MST_EnterSerialDbg_ConfigGPIOreg():
    print ("MST_EnterSerialDbg_ConfigGPIOreg")
    Enter_SerialDebugMode()
    Enter_SingleStepMode()
    MST_i2cCh0Config()
    
    MST_IicBusCtrl()
    val_idk = device.read_from_i2c(LG_MONITOR_SERDB_I2C_ADDR, 0x1)
    print (val_idk)

    val_26 = MST_DbgReadScalerReg(4, 0x26)[0]
    val_28 = MST_DbgReadScalerReg(4, 0x28)[0]

    print (hex(val_26), hex(val_28))
    
    Exit_SerialDebugMode()

def MST_EnterSerialDbg_pausingR2():
    print ("MST_EnterSerialDbg_pausingR2")
    Enter_SerialDebugMode()
    Enter_SingleStepMode()
    MST_i2cCh4Config()
    MST_IicBusCtrl()

    device.send_to_i2c(LG_MONITOR_SERDB_I2C_ADDR, [0x10, 0x00, 0x10, 0x0F, 0xD7])

    val_idk = device.read_from_i2c(LG_MONITOR_SERDB_I2C_ADDR, 0x1)

    device.send_to_i2c(LG_MONITOR_SERDB_I2C_ADDR, [0x10, 0x00, 0x10, 0x0F, 0xD7])

    print (val_idk)

#
# Main Func
#
def MST_EnterIspMode():
    print ("MST_EnterIspMode")
    MST_EnterSerialDbg_ConfigGPIOreg()
    MST_EnterSerialDbg_pausingR2()

    device.send_to_i2c(LG_MONITOR_FLASH_I2C_ADDR, [0x4D, 0x53, 0x54, 0x41, 0x52]) # "MSTAR"
    print ("Entering ISP mode now...")

    hex_dump(SPI_Flash_U8Cmd(0x5, 0x1)) # Read SR1
    hex_dump(SPI_Flash_U8Cmd(0x9F, 0x3)) # Read ID

    SPI_Flash_Dump("spi_flash.bin")

    # LG sends to LG_MONITOR_SERDB_I2C_ADDR:
    #  val_26 = MST_DbgReadScalerReg(4, 0x26)[0] ? 
    #  c0 c1 ff
    #  1f
    #  45

    SPI_Flash_Reset()

    # Added
    Exit_SerialDebugMode()

if __name__ == "__main__":
    device = LgUsbMonitorControl()
    device.init_usb()

    scalar_fw_version = device.lg_special(0xc9,0)[0:0+3]
    model_str = bytes(device.lg_special(0xca,0)[0:0+7])

    if scalar_fw_version != bytes([0x82, 0x03, 0x30]) or model_str != b"28MQ780":
        print("Please read the README and don't run random scripts on your monitor.")
        print("Scalar version:", scalar_fw_version)
        print("Model:", model_str)
        exit(1)

    MST_EnterIspMode()